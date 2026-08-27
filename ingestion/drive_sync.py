"""Sync incremental de pastas públicas do Google Drive (sem OAuth).

Estratégia: a pasta raiz é listada via `embeddedfolderview?id=<ID>#list`
(HTML público), a árvore é percorrida (BFS paralelo) e apenas os arquivos
com extensões suportadas pela pipeline são baixados para um diretório de
staging (`documents/drive/...`), preservando a hierarquia original. O
`DocumentLoader` já faz `rglob` recursivo, então os arquivos baixados são
indexados pela pipeline existente.

Seleção de pastas: o usuário pode escolher quais subpastas da árvore serão
indexadas. A seleção fica persistida em `<dest>/.drive_selection.json` como
uma lista de `{folder_id, path}`. Quando a seleção existe, apenas essas
pastas são sincronizadas; quando vazia, a pasta raiz inteira é usada.

O sync é incremental via manifesto local (`<dest>/.drive_manifest.json`),
que compara id + data de modificação. Arquivos removidos no Drive (ou que
saíram da seleção) são apagados localmente, permitindo que o indexador
detecte o stale.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

LIST_URL = "https://drive.google.com/embeddedfolderview?id={folder_id}#list"
DOWNLOAD_URL = "https://drive.google.com/uc?export=download&id={file_id}"
DOWNLOAD_URL_CONFIRM = (
    "https://drive.google.com/uc?export=download&id={file_id}&confirm={token}"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
MANIFEST_NAME = ".drive_manifest.json"
SELECTION_NAME = ".drive_selection.json"


@dataclass
class DriveEntry:
    """Item (pasta ou arquivo) retornado pelo `embeddedfolderview`."""

    entry_id: str
    name: str
    is_folder: bool
    modified: str = ""
    kind: str = "unknown"


@dataclass
class SelectedFolder:
    """Pasta selecionada para indexação.

    `path` é o caminho relativo dentro do diretório de destino (a hierarquia
    original é preservada), ex.: `MANUAIS/HP`.
    """

    folder_id: str
    path: str = ""

    def to_dict(self) -> Dict:
        return {"folder_id": self.folder_id, "path": self.path}

    @classmethod
    def from_dict(cls, data: Dict) -> "SelectedFolder":
        return cls(folder_id=str(data.get("folder_id", "")), path=str(data.get("path", "")))


@dataclass
class SyncResult:
    """Relatório de uma execução do sync."""

    files_remote: int = 0
    folders: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    removed: int = 0
    bytes_downloaded: int = 0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "files_remote": self.files_remote,
            "folders": self.folders,
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "failed": self.failed,
            "removed": self.removed,
            "bytes_downloaded": self.bytes_downloaded,
            "errors": self.errors,
        }


_ENTRY_SPLIT = 'class="flip-entry" id="'
_ENTRY_SPLIT_ALT = "flip-entry"
_HREF_RE = re.compile(
    r'href="https://drive\.google\.com/(drive/folders|file/d)/([^"/]+)',
    re.IGNORECASE,
)
_HREF_RE_LOOSE = re.compile(
    r'https://drive\.google\.com/(drive/folders|file/d)/([^"/\s?&#]+)',
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r'flip-entry-title">(.*?)</div>', re.DOTALL | re.IGNORECASE)
_TITLE_RE_ALT = re.compile(
    r'(?:entry-title|flip-entry-title|data-tooltip|title)="([^"]+)"|>([^<]{2,120})</div>\s*<div class="flip-entry-last-modified',
    re.DOTALL | re.IGNORECASE,
)
_MODIFIED_RE = re.compile(r'flip-entry-last-modified"><div>([^<]*)</div>', re.IGNORECASE)


def sanitize_name(name: str) -> str:
    """Remove caracteres inválidos para nomes de arquivo no Windows."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name).strip().strip(".")
    return cleaned or "untitled"


def _decode_response(data: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue
    return data.decode("utf-8", errors="replace")


class GoogleDriveSync:
    def __init__(
        self,
        folder_id: str,
        dest_dir: str,
        extensions: Optional[Set[str]] = None,
        logger: Optional[logging.Logger] = None,
        timeout: int = 60,
    ):
        if not isinstance(dest_dir, str) or not dest_dir.strip():
            raise ValueError(
                f"dest_dir inválido: {dest_dir!r}. "
                "Verifique a configuração GOOGLE_DRIVE_DEST_DIR."
            )
        self.folder_id = folder_id
        self.dest_dir = Path(dest_dir)
        self.logger = logger
        self.timeout = timeout
        self.max_workers = max(1, int(os.getenv("GOOGLE_DRIVE_WORKERS", "8")))
        self.extensions = extensions or {
            ".pdf", ".docx", ".txt", ".md", ".markdown",
            ".csv", ".xlsx", ".xls", ".jpg", ".jpeg", ".png",
            ".bmp", ".tif", ".tiff",
        }

    # ------------------------------------------------------------------ #
    # HTTP
    # ------------------------------------------------------------------ #

    def _request(self, url: str, retries: int = 3) -> bytes:
        last_error: Optional[Exception] = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(
                    url, headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                    }
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = resp.read()
                    # Detecta rate-limit / captcha do Google
                    if len(data) < 500 and b"Too many requests" in data:
                        raise RuntimeError("Google Drive rate-limited (Too many requests)")
                    return data
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    # Backoff exponencial + jitter
                    time.sleep(2 ** attempt + (0.5 if attempt > 0 else 0))
                else:
                    self._log_error(f"Request failed after {retries} retries: {url} -> {e}")
        raise last_error

    def list_folder(self, folder_id: str) -> List[DriveEntry]:
        """Lista os itens de uma pasta via `embeddedfolderview`."""
        url = LIST_URL.format(folder_id=folder_id)
        body = self._request(url)
        text = _decode_response(body)
        return self._parse_entries(text)

    @staticmethod
    def _parse_entries(html_text: str) -> List[DriveEntry]:
        entries: List[DriveEntry] = []
        # Estratégia 1: split clássico flip-entry
        if _ENTRY_SPLIT in html_text:
            for chunk in html_text.split(_ENTRY_SPLIT)[1:]:
                entry_id = chunk.split('"')[0]
                href = _HREF_RE.search(chunk)
                if not href:
                    # Tenta padrão mais solto dentro do chunk
                    href = _HREF_RE_LOOSE.search(chunk)
                if not href:
                    continue
                kind, kind_id = href.group(1), href.group(2)
                title_m = _TITLE_RE.search(chunk)
                if not title_m:
                    title_m = _TITLE_RE_ALT.search(chunk)
                name = ""
                if title_m:
                    # Pega primeiro grupo não vazio
                    for g in title_m.groups():
                        if g:
                            name = html.unescape(g).strip()
                            break
                mod_m = _MODIFIED_RE.search(chunk)
                modified = mod_m.group(1).strip() if mod_m else ""
                # Fallback: se nome vazio, tenta extrair do href title próximo
                if not name:
                    name = kind_id or entry_id
                entries.append(
                    DriveEntry(
                        entry_id=kind_id or entry_id,
                        name=name,
                        is_folder=(kind.lower() == "drive/folders"),
                        modified=modified,
                        kind=kind,
                    )
                )
            if entries:
                return entries

        # Estratégia 2: fallback — varre todos os hrefs do HTML (robusto a mudanças de classe)
        seen: set = set()
        for m in _HREF_RE.finditer(html_text):
            kind, kind_id = m.group(1), m.group(2)
            if kind_id in seen:
                continue
            seen.add(kind_id)
            # Janela de 1500 chars ao redor do href para buscar título/modified
            start = max(0, m.start() - 800)
            end = min(len(html_text), m.end() + 1200)
            window = html_text[start:end]
            title_m = _TITLE_RE.search(window)
            if not title_m:
                title_m = _TITLE_RE_ALT.search(window)
            name = ""
            if title_m:
                for g in title_m.groups():
                    if g:
                        name = html.unescape(g).strip()
                        break
            # Se ainda vazio, tenta extrair texto entre > e < próximo ao href
            if not name:
                # Último recurso: usa o próprio id como nome
                name = kind_id
            mod_m = _MODIFIED_RE.search(window)
            modified = mod_m.group(1).strip() if mod_m else ""
            entries.append(
                DriveEntry(
                    entry_id=kind_id,
                    name=html.unescape(name).strip()[:200],
                    is_folder=(kind.lower() == "drive/folders"),
                    modified=modified,
                    kind=kind,
                )
            )

        # Deduplica por entry_id (fallback pode repetir)
        if entries:
            deduped: Dict[str, DriveEntry] = {}
            for e in entries:
                if e.entry_id not in deduped:
                    deduped[e.entry_id] = e
            entries = list(deduped.values())

        return entries

    # ------------------------------------------------------------------ #
    # Árvore
    # ------------------------------------------------------------------ #

    def walk(
        self,
        folder_id: str = "",
        prefix: str = "",
        errors: Optional[List[str]] = None,
    ) -> Tuple[List[Tuple[str, DriveEntry]], int]:
        """Percorre a árvore via BFS com listagem paralela.

        Retorna `(arquivos, total_de_pastas)` onde cada arquivo é
        `(rel_path, entry)`. Pastas que falham ao listar são registradas em
        `errors` e não interrompem a varredura.
        """
        root = folder_id or self.folder_id
        files: List[Tuple[str, DriveEntry]] = []
        folders = 0
        # Fila BFS: (folder_id, prefix relativo da pasta)
        queue = [(root, prefix)]
        while queue:
            batch = queue[: self.max_workers]
            del queue[: self.max_workers]

            results: List[Tuple[str, str, List[DriveEntry], Optional[Exception]]] = []

            def _list(item: Tuple[str, str]) -> Tuple[str, str, List[DriveEntry], Optional[Exception]]:
                fid, rel = item
                try:
                    return fid, rel, self.list_folder(fid), None
                except Exception as e:
                    return fid, rel, [], e

            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                results = list(pool.map(_list, batch))

            for fid, rel, entries, error in results:
                if error is not None:
                    (errors if errors is not None else []).append(
                        f"{fid} (list): {error}"
                    )
                    self._log_error(f"Failed to list folder {fid}: {error}")
                    continue
                for entry in entries:
                    if entry.is_folder:
                        folders += 1
                        child_prefix = f"{rel}{sanitize_name(entry.name)}/"
                        queue.append((entry.entry_id, child_prefix))
                    else:
                        files.append(
                            (f"{rel}{sanitize_name(entry.name)}", entry)
                        )
        return files, folders

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #

    def download_file(self, file_id: str, dest_path: Path) -> int:
        """Baixa um arquivo público e retorna o número de bytes.

        Trata a página de confirmação do Google (arquivos grandes) reenviando
        a requisição com o token `confirm` quando o retorno for HTML.
        """
        url = DOWNLOAD_URL.format(file_id=file_id)
        data = self._request(url)
        text = _decode_response(data)
        if self._looks_like_html(text) and "name=\"confirm\"" in text:
            token = re.search(r'name="confirm"\s+value="([^"]+)"', text)
            if token:
                confirm_url = DOWNLOAD_URL_CONFIRM.format(
                    file_id=file_id, token=urllib.parse.quote(token.group(1))
                )
                data = self._request(confirm_url)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data)
        return len(data)

    @staticmethod
    def _looks_like_html(text: str) -> bool:
        stripped = text.lstrip()
        return (
            stripped.startswith("<html")
            or stripped.startswith("<!DOCTYPE")
            or "<form" in stripped
        )

    # ------------------------------------------------------------------ #
    # Manifesto
    # ------------------------------------------------------------------ #

    def _manifest_path(self) -> Path:
        return self.dest_dir / MANIFEST_NAME

    def _load_manifest(self) -> Dict[str, Dict]:
        path = self._manifest_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_manifest(self, manifest: Dict[str, Dict]) -> None:
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        self._manifest_path().write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ------------------------------------------------------------------ #
    # Seleção de pastas
    # ------------------------------------------------------------------ #

    def _selection_path(self) -> Path:
        return self.dest_dir / SELECTION_NAME

    def load_selection(self) -> List[SelectedFolder]:
        """Carrega a seleção de pastas persistida (vazia = raiz inteira)."""
        path = self._selection_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            folders = data.get("folders", []) if isinstance(data, dict) else data
            return [
                SelectedFolder.from_dict(item)
                for item in folders
                if isinstance(item, dict) and item.get("folder_id")
            ]
        except (json.JSONDecodeError, OSError):
            return []

    def save_selection(self, selection: List[SelectedFolder]) -> None:
        """Persiste a seleção de pastas."""
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        payload = [s.to_dict() for s in selection if s.folder_id]
        self._selection_path().write_text(
            json.dumps({"folders": payload}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ #
    # Sync
    # ------------------------------------------------------------------ #

    def sync(self, force: bool = False) -> SyncResult:
        result = SyncResult()
        manifest = self._load_manifest()
        remote_manifest: Dict[str, Dict] = {}
        walk_errors: List[str] = []

        selection = self.load_selection()
        roots: List[Tuple[str, str]] = [
            (s.folder_id, s.path.rstrip("/")) for s in selection
        ]
        if not roots:
            roots = [(self.folder_id, "")]

        files: List[Tuple[str, DriveEntry]] = []
        folders = 0
        for folder_id, prefix in roots:
            root_files, root_folders = self.walk(
                folder_id, prefix=f"{prefix}/" if prefix else "", errors=walk_errors
            )
            files.extend(root_files)
            folders += root_folders

        if walk_errors:
            result.errors.extend(walk_errors[:50])
            self._log_error(
                f"Drive walk: {len(walk_errors)} pasta(s) falharam"
            )

        result.files_remote = len(files)
        result.folders = folders
        self._log_info(
            f"Drive sync: {len(files)} arquivos, {folders} pastas "
            f"({len(roots)} raiz/raízes, seleção={'sim' if selection else 'não'})"
        )

        for rel_path, entry in files:
            ext = Path(rel_path).suffix.lower()
            if ext not in self.extensions:
                result.skipped += 1
                continue
            remote_manifest[rel_path] = {
                "id": entry.entry_id,
                "modified": entry.modified,
            }
            dest = self.dest_dir / rel_path
            recorded = manifest.get(rel_path)
            if (
                not force
                and recorded
                and recorded.get("id") == entry.entry_id
                and recorded.get("modified") == entry.modified
                and dest.exists()
                and dest.stat().st_size > 0
            ):
                result.skipped += 1
                continue
            try:
                size = self.download_file(entry.entry_id, dest)
                remote_manifest[rel_path]["size"] = size
                result.downloaded += 1
                result.bytes_downloaded += size
                self._log_info(f"Downloaded: {rel_path} ({size} bytes)")
            except Exception as e:
                result.failed += 1
                result.errors.append(f"{rel_path}: {e}")
                self._log_error(f"Failed to download {rel_path}: {e}")

        # Remoção de arquivos que não existem mais no Drive / fora da seleção
        for rel_path, recorded in manifest.items():
            if rel_path in remote_manifest:
                continue
            local = self.dest_dir / rel_path
            try:
                if local.exists():
                    local.unlink()
                    result.removed += 1
                    self._log_info(f"Removed stale: {rel_path}")
            except OSError as e:
                self._log_error(f"Failed to remove {rel_path}: {e}")

        self._save_manifest(remote_manifest)
        self._log_info(
            f"Drive sync done: {result.downloaded} baixados, "
            f"{result.skipped} ignorados, {result.failed} falhas, "
            f"{result.removed} removidos"
        )
        return result

    def _log_info(self, message: str) -> None:
        if self.logger:
            self.logger.info(message)

    def _log_error(self, message: str) -> None:
        if self.logger:
            self.logger.error(message)
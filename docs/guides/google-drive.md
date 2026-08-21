# Google Drive

O Watson sincroniza **pastas públicas** do Google Drive **sem OAuth** — ideal para repositórios técnicos compartilhados (ex.: a "AREA TECNICA").

---

## Como funciona

Para pastas públicas, o Watson usa a interface `embeddedfolderview?id=<ID>#list` do Google Drive para listar o conteúdo e baixa os arquivos via `uc?export=download` (tratando a página de confirmação de arquivos grandes).

- **Sem OAuth** — não requer credenciais, apenas o ID de uma pasta pública.
- **Download paralelo** — vários arquivos baixados simultaneamente.
- **Sincronização incremental** — estado persistido em `.drive_manifest.json` (id + data de modificação).
- **Seleção de pastas** — persistida em `.drive_selection.json`, compartilhada com a API.

---

## Configuração

No `.env`:

```env
# ID da pasta pública raiz
GOOGLE_DRIVE_FOLDER_ID=1AbCdEfGhIjKlMnOpQrStUvWxYz12345
# Onde os arquivos são salvos (padrão)
GOOGLE_DRIVE_DEST_DIR=documents/drive
# Timeout por download (s)
GOOGLE_DRIVE_SYNC_TIMEOUT=60
```

O ID da pasta é a parte após `folders/` na URL de compartilhamento:

```
https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz12345
                                                       ^^^^^^^^^^^^^^^^^
```

> A pasta deve estar configurada como **"Qualquer pessoa com o link pode ver"**.

---

## Operações

### Sincronizar e indexar tudo

```bash
python drive_index.py
```

Baixa os arquivos do Drive para `documents/drive` e indexa tudo (Drive + documentos locais).

### Apenas sincronizar (sem indexar)

```bash
python drive_index.py --sync-only
```

### Selecionar pastas

```bash
python drive_select.py
```

Interface interativa para navegar e marcar/desmarcar pastas:

- `<número>` — entrar em uma pasta.
- `..` — voltar.
- `marcar` / `desmarcar` — marcar/desmarcar a pasta atual.
- `lista` — mostrar a seleção atual.
- `limpar` — limpar a seleção (volta à raiz).
- `salvar` — persistir a seleção.
- `sair` — sair.

A seleção é compartilhada com a API (`/api/drive/selection`).

---

## Pela API

| Endpoint | Método | Descrição |
|---|---|---|
| `/api/drive/folder/{id}` | GET | Lista pastas/arquivos de um diretório |
| `/api/drive/selection` | GET/POST | Lê/salva a seleção de pastas |
| `/api/drive/sync` | POST | Sincroniza as pastas selecionadas |
| `/api/drive/clear` | POST | Remove arquivos baixados e limpa a seleção |

Ver [Referência da API](../api/api-reference.md) para os formatos de request/response.

---

## Extensões sincronizadas

O Drive sincroniza arquivos com extensões suportadas:

`pdf`, `docx`, `txt`, `md`/`markdown`, `csv`, `xlsx`/`xls`, `jpg`/`jpeg`/`png`/`bmp`/`tif`/`tiff`.

---

## Comportamento de remoção

- Arquivos removidos do Drive **ou** fora da seleção são apagados localmente.
- Isso garante que o índice reflita o estado atual do Drive após a reindexação.

---

## Próximos passos

- [Guia de uso](usage.md)
- [Monitoramento](monitoring.md)

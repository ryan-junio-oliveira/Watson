import logging
import re
from typing import Any, Dict, List, Optional

from googlesearch import search as google_search

STOP_WORDS = {
    "qual", "foi", "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "no", "na", "nos", "nas",
    "em", "com", "para", "por", "que", "é", "e", "ou", "se",
    "como", "quem", "onde", "quando", "quanto", "porque",
    "meu", "minha", "seu", "sua", "nosso", "nossa",
    "tem", "têm", "está", "estão", "era", "eram",
    "vai", "vão", "vamos", "veja", "saber", "sabe",
    "pode", "podem", "dever", "devem", "precisa", "precisam",
    "mais", "menos", "muito", "pouco", "algum", "alguma",
    "este", "esta", "esse", "essa", "aquele", "aquela",
    "ser", "estar", "ter", "haver", "fazer", "dizer",
    "sobre", "após", "antes", "durante", "mediante",
    "obter", "descobrir", "encontrar", "procurar", "buscar",
    "informação", "informacao", "resposta", "explicação", "explicacao",
    "obrigado", "obrigada", "bom", "boa", "bem", "mal",
    "por", "favor", "pfv", "preciso", "gostaria",
}


def _clean(query: str) -> str:
    return query.strip().rstrip("?").strip()


def _keywords(query: str) -> str:
    words = re.sub(r'[^\w\sà-úÀ-Ú]', ' ', query.lower()).split()
    kept = [w for w in words if w not in STOP_WORDS and len(w) > 2]
    return " ".join(kept[:10]) if kept else query


class WebSearch:
    def __init__(
        self,
        max_results: int = 5,
        logger: Optional[logging.Logger] = None,
    ):
        self.max_results = max_results
        self.logger = logger

    def search(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        k = max_results or self.max_results
        original = _clean(query)
        keywords = _keywords(original)

        queries = []
        if keywords:
            queries.append(keywords)
        if original != keywords:
            queries.append(original)

        seen: Dict[str, Dict[str, Any]] = {}

        for q in queries:
            if len(seen) >= k:
                break
            if self.logger:
                self.logger.info(f"Searching Google: '{q[:80]}'")
            results = self._google(q, k * 3)
            for r in results:
                url = r.get("href", "")
                if url and url not in seen:
                    seen[url] = r
            if len(seen) >= k:
                break

        final = list(seen.values())[:k]
        if self.logger:
            self.logger.info(f"Google returned {len(final)} unique results")
        return final

    def _google(self, query: str, count: int) -> List[Dict[str, Any]]:
        try:
            results = []
            for r in google_search(query, num_results=count, advanced=True):
                results.append({
                    "title": r.title,
                    "body": r.description,
                    "href": r.url,
                })
            return results
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Google search failed for '{query[:60]}': {e}")
            return self._fallback_ddg(query, count)

    def _fallback_ddg(self, query: str, count: int) -> List[Dict[str, Any]]:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=count))
                return [
                    {"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")}
                    for r in raw
                ]
        except Exception as e:
            if self.logger:
                self.logger.error(f"DDGS fallback also failed: {e}")
            return []

    @staticmethod
    def format_results(results: List[Dict[str, Any]]) -> str:
        parts = []
        for r in results:
            url = r.get("href", "")
            title = r.get("title", "Sem título")
            body = r.get("body", "")
            if url:
                parts.append(f"[{url}]\n{title}\n{body}")
        return "\n\n---\n\n".join(parts)

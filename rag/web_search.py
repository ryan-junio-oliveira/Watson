"""Web Search provider — modo `web` isolado (§ web_search).

Isolado do RAG local: quando `Mode.web` é ativado o ChatBot não toca
no Chroma, apenas busca na web, converte resultados em Evidence com
`provider="web"` e `url` obrigatório para citação.

Providers:
- searxng: self-hosted SearXNG (free, sem key) — http://localhost:8080 — recomendado gratuito
- google: Google Custom Search JSON API (precisa GOOGLE_API_KEY + GOOGLE_CX)
- tavily: exige TAVILY_API_KEY (https://tavily.com) — equivalente Google
- serper: exige SERPER_API_KEY (https://serper.dev)
- duckduckgo: legacy, mantido apenas como último fallback (instável)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

import httpx

from rag.evidence import Evidence

try:
    from core.config import Config  # type: ignore
except Exception:
    Config = object  # type: ignore


@dataclass
class WebResult:
    title: str
    url: str
    snippet: str
    content: str = ""


class WebSearchProvider:
    def __init__(
        self,
        provider: str = "duckduckgo",
        api_key: str = "",
        max_results: int = 5,
        timeout: int = 15,
        tavily_search_depth: str = "basic",
        trusted_domains: str = "",
        logger: Optional[logging.Logger] = None,
        google_api_key: str = "",
        google_cx: str = "",
        serper_api_key: str = "",
        searxng_url: str = "",
    ):
        self.provider = (provider or "duckduckgo").lower().strip()
        self.api_key = (api_key or "").strip()
        self.max_results = max(1, int(max_results))
        self.timeout = max(5, int(timeout))
        self.tavily_search_depth = tavily_search_depth or "basic"
        self.trusted_domains = [d.strip().lower() for d in (trusted_domains or "").split(",") if d.strip()]
        self.logger = logger
        self.google_api_key = (google_api_key or "").strip()
        self.google_cx = (google_cx or "").strip()
        self.serper_api_key = (serper_api_key or "").strip()
        self.searxng_url = (searxng_url or "http://localhost:8080").strip().rstrip("/")

    # --- API pública ---

    def search(self, query: str, k: Optional[int] = None) -> List[Evidence]:
        k = max(1, int(k or self.max_results))
        q = (query or "").strip()
        if not q:
            return []
        fetch_k = min(k * 3, 15) if self.trusted_domains else k
        results: List[WebResult] = []
        try:
            if self.provider == "searxng":
                results = self._search_searxng(q, fetch_k)
            elif self.provider == "google":
                if self.google_api_key and self.google_cx:
                    results = self._search_google(q, fetch_k)
                elif self.serper_api_key:
                    results = self._search_serper(q, fetch_k)
                elif self.api_key:
                    self._log("Google sem GOOGLE_API_KEY/CX, fallback para Tavily (Google-quality)")
                    results = self._search_tavily(q, fetch_k)
                else:
                    self._log("Google sem credenciais, fallback para SearXNG", level="warning")
                    results = self._search_searxng(q, fetch_k)
            elif self.provider == "tavily" and self.api_key:
                results = self._search_tavily(q, fetch_k)
            elif self.provider == "serper" and self.serper_api_key:
                results = self._search_serper(q, fetch_k)
            else:
                if self.provider in ("tavily", "google") and not self.api_key and not self.google_api_key and not self.serper_api_key:
                    self._log(f"{self.provider} sem API key, tentando SearXNG fallback", level="warning")
                # Provider desconhecido ou sem credenciais: tenta SearXNG > Google > Tavily > Serper
                try:
                    results = self._search_searxng(q, fetch_k)
                    if results:
                        self._log(f"SearXNG recuperou {len(results)} resultados")
                    else:
                        raise RuntimeError("SearXNG vazio")
                except Exception:
                    if self.google_api_key and self.google_cx:
                        results = self._search_google(q, fetch_k)
                    elif self.api_key:
                        results = self._search_tavily(q, fetch_k)
                    elif self.serper_api_key:
                        results = self._search_serper(q, fetch_k)
                    else:
                        results = self._search_duckduckgo(q, fetch_k)
        except Exception as e:
            self._log(f"Web search failed ({self.provider}): {e}", level="warning")
            # fallback em cascata: SearXNG -> Google -> Tavily -> Serper -> DuckDuckGo (último)
            for fallback in [self._search_searxng, self._search_google, self._search_tavily, self._search_serper]:
                try:
                    if fallback == self._search_google and not (self.google_api_key and self.google_cx):
                        continue
                    if fallback == self._search_tavily and not self.api_key:
                        continue
                    if fallback == self._search_serper and not self.serper_api_key:
                        continue
                    results = fallback(q, k)
                    if results:
                        self._log(f"Fallback {fallback.__name__} recuperou {len(results)} resultados")
                        break
                except Exception:
                    continue
            if not results:
                try:
                    results = self._search_duckduckgo(q, k)
                except Exception:
                    pass
        # Deduplica por url normalizada (evita duplicatas do DuckDuckGo)
        deduped: List[WebResult] = []
        seen_urls: set = set()
        for r in results:
            norm = (r.url or "").strip().lower().rstrip("/")
            if norm and norm in seen_urls:
                continue
            if norm:
                seen_urls.add(norm)
            deduped.append(r)
        results = deduped

        # Re-rankeia por confiabilidade: domínios trusted no topo (Google bem rankeado)
        if self.trusted_domains:
            results = self._rank_by_trust(results)

        # Enriquece top-3 com conteúdo real da página para resposta factual (não só snippet)
        if results:
            for r in results[: min(3, len(results))]:
                if len(r.content or "") < 400:
                    fetched = self._fetch_page_content(r.url)
                    if fetched and len(fetched) > len(r.content or ""):
                        r.content = fetched[:4000]

        evidences: List[Evidence] = []
        for idx, r in enumerate(results[:k]):
            content = (r.content or r.snippet or "").strip()
            if not content:
                continue
            evidences.append(
                Evidence(
                    provider="web",
                    source=r.url,
                    title=r.title or r.url,
                    url=r.url,
                    content=content[:4000],
                    metadata={
                        "provider": "web",
                        "web_provider": self.provider,
                        "rank": idx + 1,
                        "snippet": r.snippet[:500] if r.snippet else "",
                    },
                    source_type="web",
                    score=1.0 - (idx * 0.05),
                )
            )
        return evidences

    # --- Providers ---

    def _rank_by_trust(self, results: List[WebResult]) -> List[WebResult]:
        def is_trusted(url: str) -> bool:
            low = (url or "").lower()
            return any(dom in low for dom in self.trusted_domains)

        trusted = [r for r in results if is_trusted(r.url)]
        others = [r for r in results if not is_trusted(r.url)]
        # Mantém ordem relativa mas trusted primeiro
        ranked = trusted + others
        if trusted and self.logger:
            self._log(f"Trust ranking: {len(trusted)} trusted no topo de {len(results)}")
        return ranked

    def _search_tavily(self, query: str, k: int) -> List[WebResult]:
        url = "https://api.tavily.com/search"
        # Se trusted_domains configurado, passa para Tavily filtrar por domínios confiáveis
        include_domains = self.trusted_domains[:10] if self.trusted_domains else None
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": min(k * 2, 10) if include_domains else k,
            "search_depth": self.tavily_search_depth,
            "include_answer": False,
            "include_raw_content": False,
        }
        if include_domains:
            payload["include_domains"] = include_domains
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            resp = client.post(url, json=payload, headers={"Content-Type": "application/json"})
            resp.raise_for_status()
            data = resp.json()
        out: List[WebResult] = []
        for item in (data.get("results") or [])[:k]:
            out.append(
                WebResult(
                    title=(item.get("title") or "").strip(),
                    url=(item.get("url") or "").strip(),
                    snippet=(item.get("content") or item.get("snippet") or "").strip(),
                    content=(item.get("content") or item.get("snippet") or "").strip(),
                )
            )
        return [r for r in out if r.url]

    def _search_google(self, query: str, k: int) -> List[WebResult]:
        """Google Custom Search JSON API — https://developers.google.com/custom-search/v1"""
        if not (self.google_api_key and self.google_cx):
            raise RuntimeError("Google Custom Search precisa de GOOGLE_API_KEY e GOOGLE_CX")
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": self.google_api_key,
            "cx": self.google_cx,
            "q": query,
            "num": min(k, 10),
            "hl": "pt-BR",
            "gl": "br",
        }
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        out: List[WebResult] = []
        for item in (data.get("items") or [])[:k]:
            out.append(
                WebResult(
                    title=(item.get("title") or "").strip(),
                    url=(item.get("link") or "").strip(),
                    snippet=(item.get("snippet") or "").strip(),
                    content=(item.get("snippet") or "").strip(),
                )
            )
        return [r for r in out if r.url]

    def _search_searxng(self, query: str, k: int) -> List[WebResult]:
        """SearXNG — self-hosted, free, sem key. Requer SEARXNG_URL (default http://localhost:8080)"""
        url = f"{self.searxng_url}/search"
        params = {"q": query, "format": "json", "categories": "general"}
        headers = {
            "Accept": "application/json",
            "User-Agent": "Watson/1.0",
            "X-Forwarded-For": "127.0.0.1",
            "X-Real-IP": "127.0.0.1",
        }
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        out: List[WebResult] = []
        # SearXNG JSON: {"results": [{"title":..., "url":..., "content":...}, ...]}
        # Alguns forks usam "results" ou "organic"
        items = data.get("results") or data.get("organic") or []
        for item in items[:k]:
            out.append(
                WebResult(
                    title=(item.get("title") or "").strip(),
                    url=(item.get("url") or item.get("link") or "").strip(),
                    snippet=(item.get("content") or item.get("snippet") or "").strip(),
                    content=(item.get("content") or item.get("snippet") or "").strip(),
                )
            )
        # Fallback: se JSON vazio, tenta HTML parsing simples
        if not out:
            # Tenta buscar HTML e extrair links
            try:
                params_html = {"q": query}
                headers_html = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers_html) as client2:
                    resp2 = client2.get(f"{self.searxng_url}/search", params=params_html, headers=headers_html)
                    resp2.raise_for_status()
                    html = resp2.text
                    # Extrai hrefs
                    hrefs = re.findall(r'href="(https?://[^"]+)"', html)
                    titles = re.findall(r'<h3[^>]*>(.*?)</h3>', html, flags=re.DOTALL)
                    for i, href in enumerate(hrefs[:k]):
                        title = self._strip_html(titles[i] if i < len(titles) else href)
                        if href and "searxng" not in href.lower():
                            out.append(WebResult(title=title or href, url=href, snippet=title, content=title))
            except Exception:
                pass
        return [r for r in out if r.url]

    def _search_serper(self, query: str, k: int) -> List[WebResult]:
        """Serper.dev — Google via API simples (https://serper.dev)"""
        if not self.serper_api_key:
            raise RuntimeError("Serper precisa de SERPER_API_KEY")
        url = "https://google.serper.dev/search"
        payload = {"q": query, "num": min(k, 10), "gl": "br", "hl": "pt-br"}
        headers = {"X-API-KEY": self.serper_api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        out: List[WebResult] = []
        for item in (data.get("organic") or [])[:k]:
            out.append(
                WebResult(
                    title=(item.get("title") or "").strip(),
                    url=(item.get("link") or "").strip(),
                    snippet=(item.get("snippet") or "").strip(),
                    content=(item.get("snippet") or "").strip(),
                )
            )
        return [r for r in out if r.url]

    def _search_duckduckgo(self, query: str, k: int) -> List[WebResult]:
        # DuckDuckGo HTML lite — sem API key, respeita k
        # Usa html.duckduckgo.com/html/?q=...
        search_url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }
        results: List[WebResult] = []
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            resp = client.post(search_url, data={"q": query}, headers=headers)
            # fallback GET se POST falhar
            if resp.status_code >= 400:
                resp = client.get(search_url, params={"q": query})
            resp.raise_for_status()
            html = resp.text
            # parse simples via regex — evita beautifulsoup
            # cada resultado tem <a rel="nofollow" class="result__url" href="..."> e <h2 class="result__title">
            # extrair blocos
            blocks = re.findall(r'class="result__title".*?</a>.*?class="result__snippet".*?</a>', html, flags=re.DOTALL | re.IGNORECASE)
            if not blocks:
                # fallback: captura hrefs uddg
                hrefs = re.findall(r'href="//duckduckgo\.com/l/\?uddg=([^&"]+)', html)
                titles = re.findall(r'class="result__title[^"]*".*?>(.*?)</a>', html, flags=re.DOTALL)
                snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, flags=re.DOTALL)
                for i, enc in enumerate(hrefs[:k]):
                    try:
                        from urllib.parse import unquote

                        url = unquote(enc)
                    except Exception:
                        url = enc
                    title = self._strip_html(titles[i] if i < len(titles) else url)
                    snippet = self._strip_html(snippets[i] if i < len(snippets) else "")
                    if url.startswith("//"):
                        url = "https:" + url
                    if url:
                        results.append(WebResult(title=title or url, url=url, snippet=snippet, content=snippet))
                return results[:k]
            for block in blocks[:k]:
                href_m = re.search(r'href="([^"]+)"', block)
                title_m = re.search(r'class="result__title[^"]*".*?>(.*?)</a>', block, flags=re.DOTALL)
                snippet_m = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, flags=re.DOTALL)
                raw_href = href_m.group(1) if href_m else ""
                # uddg param = url real
                url = ""
                if "uddg=" in raw_href:
                    try:
                        from urllib.parse import parse_qs, unquote, urlparse

                        qs = parse_qs(urlparse(raw_href).query)
                        if "uddg" in qs:
                            url = unquote(qs["uddg"][0])
                        else:
                            m = re.search(r'uddg=([^&]+)', raw_href)
                            url = unquote(m.group(1)) if m else raw_href
                    except Exception:
                        url = raw_href
                else:
                    url = raw_href
                if url.startswith("//"):
                    url = "https:" + url
                title = self._strip_html(title_m.group(1) if title_m else url)
                snippet = self._strip_html(snippet_m.group(1) if snippet_m else "")
                if url and snippet:
                    results.append(WebResult(title=title or url, url=url, snippet=snippet, content=snippet))
        return results[:k]

    def _fetch_page_content(self, url: str) -> str:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
            }
            with httpx.Client(timeout=8, follow_redirects=True, headers=headers) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code != 200 or not resp.text:
                    return ""
                html = resp.text
                # remove scripts/styles
                html = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
                html = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
                # tenta extrair <article> ou <main> primeiro
                m = re.search(r"<article.*?</article>", html, flags=re.DOTALL | re.IGNORECASE)
                if m:
                    html = m.group(0)
                else:
                    m = re.search(r"<main.*?</main>", html, flags=re.DOTALL | re.IGNORECASE)
                    if m:
                        html = m.group(0)
                # extrai parágrafos
                paras = re.findall(r"<p[^>]*>(.*?)</p>", html, flags=re.DOTALL | re.IGNORECASE)
                if paras:
                    text = " ".join(self._strip_html(p) for p in paras[:12])
                else:
                    text = self._strip_html(html)
                text = re.sub(r"\s+", " ", text).strip()
                return text[:3500]
        except Exception:
            return ""

    @staticmethod
    def _strip_html(s: str) -> str:
        s = re.sub(r"<[^>]+>", "", s or "")
        s = re.sub(r"\s+", " ", s).strip()
        # decodifica entidades básicas
        s = s.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'").replace("&#39;", "'")
        s = s.replace("&lt;", "<").replace("&gt;", ">")
        return s

    def _log(self, msg: str, level: str = "info") -> None:
        if not self.logger:
            return
        fn = getattr(self.logger, level, self.logger.info)
        try:
            fn(msg)
        except Exception:
            pass

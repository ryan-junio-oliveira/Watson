# Configuração — Referência completa do `.env`

Todas as configurações são centralizadas em `core/config.py` (dataclass `Config`) e sobrescritas via **variáveis de ambiente** ou arquivo **`.env`**.

> `core/config.py:7` `load_dotenv()` lê `e:/Sistemas/Dok Solutions/Watson/.env` na importação. `.env.example` é o template versionado; `.env` é `gitignore`. Copie `cp .env.example .env` e edite, ou use `http://localhost:9000/config` (UI web).

Após alterar `.env`, **reinicie a API** (`docker compose restart` ou reinicie o processo) para aplicar `OLLAMA_MODEL`/`WEB_SEARCH_PROVIDER`/etc.

---

## 1.1 Perfis Watson — Flash / Plus / Pro

Selecione no chat (`⚡ Flash` · `⚖️ Plus` · `🧠 Pro`) ou via `.env` `WATSON_PROFILE`. O perfil simplifica as 58 variáveis em três modos — igual Gemini/ChatGPT.

> **A ideia é não configurar 58 vars uma a uma.** O perfil define velocidade vs qualidade. Em `Pro`, `analisar` já é ativo por padrão (sem precisar ligar `analyze`). `Plus` foi removido — `flash` cobre o rápido e `pro` o inteligente.

| Perfil | Objetivo | Quando usar | Velocidade¹ | Qualidade | Tokens / Chunk por baixo (`core/config.py:290`) |
|---|---|---|---|---|---|
| **⚡ Flash** — *default* | Mais rápido | Dia a dia, health-check, maioria RAG/web | ~0.8–1.2s | Boa (sem raciocínio) | `max_tokens=2048` · `chunk=800`/`overlap=150` · `TOP_K=5` · `rewriter=false` (3 queries) · `reasoning=2048` · `reranker=false` · `temp=0.1` |
| **🧠 Pro** | Mais inteligente (pensamento profundo) | Análise, comparação, percentual, auditoria | ~4–8s (CPU) | Muito boa | `max_tokens=4096` · `chunk=1200`/`overlap=250` · `TOP_K=12` · `rewriter=true` (5 queries) · `reasoning=4096` · `reranker=true`+`mmr` · `analyst=4096` `think`+`qwen3:8b` · `temp=0.2` |

¹ CPU 8–16 GB, `gemma3:4b`. Com `qwen3:8b` em `Pro`, +2–3s e qualidade ainda maior.

**Como escolher:**
- Chat: seletor `Flash / Plus / Pro` no composer (`presentation/chat.html:251`) — persiste em `watson-profile` (localStorage). `Pro` já envia `analyze=true` (sem mostrar switch).
- API: `POST /api/chat { "question": "...", "profile": "pro" }` (`cli/api.py:60` `resolve_profile_and_analyze()`) ou `profile` no `history`. `dokviewermanager` já envia `profile` (`WatsonProvider.php:36`).
- `.env` / `docker-compose`: `WATSON_PROFILE=plus` (default equilibrado). `flash` economiza LLM calls; `pro` ativa `qwen3:8b` se `ANALYST_MODEL` não setado (`core/config.py:344`).
- Fallback: se `ANALYST_MODEL=qwen3:8b` não estiver baixado (`docker exec watson-ollama ollama list` só mostra `gemma3:4b`), `Pro` faz fallback automático para `gemma` sem quebrar (`rag/chatbot.py:510`).

**Validado — Plus removido:** `Flash` (rápido) falhava em consulta pobre como `"erro na impressora E123"` sem `rewriter`; `Pro` com `rewriter` + 5 queries cobre esses casos. `Flash` + `Pro` são suficientes.

**API relacionada:**
- `WATSON_PROFILE` (`core/config.py:290`), `TOP_K`, `ENABLE_QUERY_REWRITER`, `USE_RERANKER`, `ENABLE_REASONING`, `ANALYST_MODEL/THINK` — veja seções abaixo para overrides quando `profile=custom`.

---

## 1. Arquivo `.env`

```bash
cp .env.example .env      # Windows: copy .env.example .env
# ou edite via web: http://localhost:9000/config → Salvar → Reiniciar
```

Ordem no arquivo não importa; chaves são `UPPER_SNAKE_CASE`. Segredos (`*_KEY`, `*_TOKEN`) são mascarados em `GET /api/config` como `***xxxx`.

---

## 2. Referência por seção

### 🧠 Ollama — LLM principal

| Variável | Padrão | Tipo | Descrição | Quando alterar |
|---|---|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | url | Host do Ollama | Docker → `http://ollama:11434` |
| `OLLAMA_MODEL` | `gemma3:4b` | string | Modelo principal. Leve e rápido, bom PT-BR. Alternativas: `qwen3:8b` (melhor reasoning), `deepseek-r1:7b` (CoT nativo), `gemma3:12b/27b` | Troque para `qwen3:8b` se quiser `think` (`llm/ollama_client.py:42` só ativa para `qwen3/qwq/deepseek-r1`) |
| `OLLAMA_TIMEOUT` | `300` | int (s) | Timeout por geração | Aumente para `600` se modelo grande em CPU for lento |

### 🎛️ Modelo LLM (geração)

| Variável | Padrão | Descrição |
|---|---|---|
| `TEMPERATURE` | `0.1` | `0.0` determinístico/fiel (RAG), `0.7` criativo. `rag/prompt.py` depende de baixa para não inventar |
| `MAX_TOKENS` | `2048` | Limite de tokens da resposta. `3072` para reasoning longo |

### 🔢 Embeddings — busca vetorial

| Variável | Padrão | Descrição |
|---|---|---|
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-base` | 768 dims, multilíngue, bom PT-BR. Alternativa: `intfloat/multilingual-e5-large` (+qualidade, +RAM) |
| `EMBEDDING_DEVICE` | `cpu` | `cuda` se tiver GPU/NVIDIA |
| `EMBEDDING_BATCH_SIZE` | `32` | Lote por chamada de embedding |
| `EMBEDDING_NORMALIZE` | `true` | Normaliza vetores — `e5` exige `true` |
| `EMBEDDING_CACHE_PATH` | `database/embedding_cache.sqlite3` | Cache SQLite evita re-embedar docs já indexados |

### 📁 Documentos

| Variável | Padrão | Descrição |
|---|---|---|
| `DOCUMENTS_DIR` | `documents` | Pasta local de PDFs/DOCXs/TXTs (`#` comentado = default) |

### ☁️ Google Drive — pasta pública sem OAuth

| Variável | Padrão | Descrição |
|---|---|---|
| `GOOGLE_DRIVE_FOLDER_ID` | `` | ID da pasta pública raiz (ex: `1AbC...`). Vazio = desativa Drive |
| `GOOGLE_DRIVE_DEST_DIR` | `documents/drive` | Onde salva cópias locais |
| `GOOGLE_DRIVE_SYNC_TIMEOUT` | `60` | Timeout por download (s) |
| `GOOGLE_DRIVE_WORKERS` | `8` | Paralelismo de downloads (mín 1) |

### 🔤 OCR — PDFs escaneados

| Variável | Padrão | Descrição |
|---|---|---|
| `TESSERACT_CMD` | `` (vazio) | Caminho binário. Linux usa `PATH`, Windows usa `libs/tesseract` se vazio |
| `OCR_LANG` | `por+eng` | Idiomas do Tesseract |
| `OCR_DPI` | `200` | DPI de renderização do PDF para OCR (maior = melhor, mais lento) |
| `OCR_MIN_TEXT_CHARS` | `20` | Se PDF tem <20 chars nativos, considera escaneado e faz OCR |

### 🖼️ Imagens e deduplicação

| Variável | Padrão | Descrição |
|---|---|---|
| `IMAGE_DIR` | `database/images` | Cache de imagens extraídas de PDFs |
| `VISION_MODEL` | `moondream` | Ollama vision para descrever fotos técnicas. `moondream` 1.8B leve/ rápido, `qwen2.5vl` 8B pesado/preciso. Vazio = desativa |
| `DEDUP_CROSS_DOC` | `true` | Remove chunks idênticos entre documentos diferentes |
| `DEDUP_PERSIST_PATH` | `database/dedup.json` | Arquivo que guarda hashes já vistos |

### ✅ Quality gate — descarta chunks ruins

| Variável | Padrão | Descrição |
|---|---|---|
| `QUALITY_MIN_CHARS` | `20` | Mínimo geral por chunk |
| `QUALITY_MIN_CHARS_TABLE` | `10` | Mínimo para tabelas |
| `QUALITY_MIN_CHARS_IMAGE` | `30` | Mínimo para descrição de imagem |
| `QUALITY_TABLE_MIN_PIPES` | `4` | Tabela precisa ter ≥4 `|` para ser considerada |
| `QUALITY_OCR_THRESHOLD` | `0.6` | Score mínimo de confiança do OCR |

### ✂️ Chunking e banco vetorial

| Variável | Padrão | Descrição |
|---|---|---|
| `CHUNK_SIZE` | `1000` | Tamanho do recorte em chars |
| `CHUNK_OVERLAP` | `200` | Sobreposição entre recortes (preserva contexto) |
| `INDEX_BATCH_SIZE` | `100` | Lote de inserção no ChromaDB |
| `VECTOR_DB_DIR` | `database/chroma` | Pasta do Chroma (`#` comentado = default) |

### 🔍 Retrieval — busca

| Variável | Padrão | Descrição |
|---|---|---|
| `TOP_K` | `5` | Chunks por consulta (rewriter divide `TOP_K` entre 5 queries) |
| `SIMILARITY_THRESHOLD` | `0.0` / vazio | Score mínimo. Vazio/null = sem filtro; `0.25` filtra lixo de baixa similaridade |
| `USE_MMR` | `false` | Max Marginal Relevance — diversifica (evita 5 chunks iguais) |
| `MMR_FETCH_K` | `20` | Candidatos para MMR |
| `MMR_LAMBDA` | `0.5` | 0=diversidade, 1=relevância |
| `USE_RERANKER` | `false` | Re-ranking com CrossEncoder (`ms-marco-MiniLM`) — melhora ranking, +CPU |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Modelo de reranking |

### 🧠 Watson Reasoning / Analyst — raciocínio avançado

| Variável | Padrão | Descrição |
|---|---|---|
| `ENABLE_REASONING` | `false` | Ativa `REASONING_SYSTEM_PROMPT` (`rag/prompt.py:37`) e `think` se modelo suportar (`qwen3/qwq`) |
| `ENABLE_ANALYST` | `true` | Analista proativo gera `conclusions`/`follow_up`/`additional_info` (chips na UI) |
| `ANALYST_MAX_FOLLOWUPS` | `3` | Máximo de perguntas de acompanhamento |
| `REASONING_TOP_K` | `12` | `TOP_K` quando reasoning precisa (maior contexto) |
| `REASONING_TEMPERATURE` | `0.2` | Temperatura para CoT (um pouco mais criativa) |
| `REASONING_MAX_TOKENS` | `3072` | Tokens para raciocínio longo |
| `ENABLE_QUERY_EXPANSION` | `true` | Gera variantes determinísticas + RRF (fallback do rewriter) |
| `QUERY_EXPANSION_VARIANTS` | `3` | Número de variantes |
| `ENABLE_RERANKER_REASONING` | `true` | Só rerankeia quando reasoning pedir |

### ✨ Query Understanding Layer — LLM intermediário NOVO

| Variável | Padrão | Descrição |
|---|---|---|
| `ENABLE_QUERY_REWRITER` | `true` | Ativa `rag/query_rewriter.py:15` — transforma `erro na impressora E123` (pobre) → 5 queries `código E123 troubleshooting / manual impressora ...` preservando `código de erro` + `entities` + `intent=troubleshooting` → `RRF` + boost por entidade (`rag/chatbot.py:225`) |
| `QUERY_REWRITER_MODEL` | `` (vazio) | Modelo do rewriter. Vazio = usa `OLLAMA_MODEL`. Recomendado `gemma3:1b` leve (100ms) |
| `QUERY_REWRITER_MAX_EXPANDED` | `5` | Máximo de queries expandidas (3-5) |

> **Fallback:** se LLM falhar/offline, `query_rewriter.py:120` `_fallback_rewrite` faz o mesmo por regex/template mantendo termos técnicos. Metadados vão em `metadata.rewritten`/`expanded_queries` para debug.

### 🔌 API Server

| Variável | Padrão | Descrição |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Host do FastAPI |
| `API_PORT` | `9000` | Porta (`http://localhost:9000`, chat em `/`, docs em `/docs`, config em `/config`) |
| `API_AUTH_TOKEN` | `` | Token exigido em `X-API-Token` ou `Authorization: Bearer`. Vazio = sem auth (dev) |
| `API_RATE_ENABLED` | `true` | Liga rate limiting |
| `API_RATE_LIMIT` | `30` | Requisições por janela |
| `API_RATE_WINDOW` | `60` | Janela em segundos (30/60s) |

### 📝 Logging e métricas

| Variável | Padrão | Descrição |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG/INFO/WARNING/ERROR` |
| `LOG_FILE` | `logs/ai_agent.log` | Arquivo de log |
| `AGENT_NAME` | `Watson` | Nome exibido no chat e saudação |
| `METRICS_DB` | `database/metrics.db` | SQLite do dashboard (`/dashboard` → KPIs, tokens, latência) |

### 🌐 Web Search — modo `web` isolado

| Variável | Padrão | Descrição |
|---|---|---|
| `WEB_SEARCH_ENABLED` | `true` | Liga `mode=web` (toggle no chat). Isolado do RAG local |
| `WEB_SEARCH_PROVIDER` | `duckduckgo` | `duckduckgo` (default, free sem key), `searxng`/`google` opcionais (`SEARXNG_URL` ou `GOOGLE_API_KEY+GOOGLE_CX`), `tavily` (`WEB_SEARCH_API_KEY`), `serper` (`SERPER_API_KEY`) |
| `SEARXNG_URL` | `http://localhost:8080` | URL do SearXNG (`docker run -d -p 8080:8080 searxng/searxng`) — só usado se `provider=searxng` |
| `GOOGLE_API_KEY` | `` | Google Custom Search `console.cloud.google.com` (opcional) |
| `GOOGLE_CX` | `` | ID do mecanismo `programmablesearchengine.google.com` (opcional) |
| `SERPER_API_KEY` | `` | `serper.dev` (2500/mês grátis, opcional) |
| `WEB_SEARCH_API_KEY` | `` | Tavily `tavily.com` (1000/mês grátis, opcional) |
| `WEB_SEARCH_MAX_RESULTS` | `5` | Resultados por busca |
| `WEB_SEARCH_TIMEOUT` | `15` | Timeout (s) |
| `TAVILY_SEARCH_DEPTH` | `basic` | `basic` ou `advanced` (Tavily) |
| `WEB_SEARCH_TRUSTED_DOMAINS` | `g1.globo.com,uol.com.br,...` | Prioriza no ranking (ex: `cnnbrasil.com,band.uol.com.br`) |

Cascata em `rag/web_search.py:56`: `searxng → google → tavily → serper → duckduckgo`. Sem nenhuma key, cai no SearXNG (se estiver rodando) ou duckduckgo instável.

---

## 3. Exemplos práticos

**Mínimo para rodar:**
```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b
```

**Tudo free (sem pagar):**
```env
WEB_SEARCH_PROVIDER=searxng
SEARXNG_URL=http://localhost:8080
ENABLE_QUERY_REWRITER=true
```

**Google oficial (100/dia grátis):**
```env
WEB_SEARCH_PROVIDER=google
GOOGLE_API_KEY=sua_key
GOOGLE_CX=017_seu_cx
```

**Proteção API:**
```env
API_AUTH_TOKEN=um-texto-longo-aleatorio
# use: curl -H "X-API-Token: um-texto-longo-aleatorio" http://localhost:9000/api/chat
```

---

## 4. Edição via web

Acesse `http://localhost:9000/config` → edita todos os campos agrupados com explicação, teste SearXNG (`/api/config/test/searxng`), `Salvar .env` → reinicie a API.

`GET /api/config` e `POST /api/config` (`cli/api.py:2003`) também permitem automação.

---

## 5. Próximos passos

- [Início rápido](quickstart.md)
- [Arquitetura](../architecture/overview.md)
- [Guia de uso](../guides/usage.md)
- [Referência API](../api/api-reference.md)

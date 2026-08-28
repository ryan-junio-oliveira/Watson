# Estrutura do Projeto

Organização de pastas e responsabilidades de cada módulo. Mantida minimalista — 9 pastas de código + 3 de dados.

---

## Visão geral

```
Watson/
├── core/                     # Núcleo — config e injeção de dependência
│   ├── config.py             # Configurações centralizadas (dataclass + .env)
│   └── factories.py          # Fábricas build_* (DI, single source of wiring)
├── cli/                      # Entrypoints (8 CLIs) — canônicos
│   ├── api.py                # API REST FastAPI + SSE (uvicorn cli.api:app)
│   ├── app.py                # Chat interativo no terminal (python cli/app.py)
│   ├── index.py              # Indexação CLI (python cli/index.py)
│   ├── drive_index.py        # Sync Google Drive + indexação
│   ├── drive_select.py       # Seleção de pastas Drive (CLI interativo)
│   ├── watch.py              # Watcher — polling + reindex incremental
│   ├── reset_app.py          # Reset total (chroma, manifest, caches)
│   └── service.py            # Serviço Windows (win32serviceutil)
├── scripts/                  # Operação (10 sh/bat, sem .py)
│   ├── start.bat / start.sh      # Menu inicializador (1-8 + setup auto)
│   ├── setup.bat / setup.sh      # Cria .venv + pip + .env + Ollama pull
│   ├── stop.bat / stop.sh        # Mata processo por porta/PID
│   ├── cleanup.bat / cleanup.sh  # Remove caches/build/logs
│   ├── build.bat                 # PyInstaller (watson.spec → dist/watson)
│   └── setup_supervisor.sh       # Instalação Linux supervisord
├── ingestion/                # PIPELINE DE INDEXAÇÃO (arquivo → vetores)
│   ├── loader.py             # Descoberta recursiva + despacho por adapter
│   ├── models.py             # Domínio (LoadedDocument, Page, Section, Table, ImageRef)
│   ├── splitter.py           # Chunking semântico por tipo (1000/200)
│   ├── embeddings.py         # Embeddings sentence-transformers (e5-base, cache)
│   ├── embedding_cache.py    # Cache SQLite de embeddings (evita recomputo)
│   ├── indexer.py            # Orquestrador incremental (hash + manifest + dedup)
│   ├── vector_store.py       # Interface + ChromaVectorStore (collection "documents")
│   ├── manifest.py           # Manifesto JSON atômico (estado por documento)
│   ├── contracts.py          # Contrato estável (ChunkContract, PipelineVersion)
│   ├── quality.py            # Quality gate (filtra chunks <20 chars etc)
│   ├── dedup.py              # Dedup intra/cross-doc (persistido em dedup.json)
│   ├── identity.py           # Inferência fabricante/modelo do filename
│   ├── drive_sync.py         # Google Drive público (sem OAuth, paralelo, staging)
│   └── adapters/             # Adaptadores por fonte (registry → ext)
│       ├── registry.py       # Registro extensão → adapter
│       ├── base.py           # ABC SourceAdapter
│       ├── pdf_adapter.py    # PDF (PyMuPDF + PyMuPDF4LLM + OCR seletivo 300dpi)
│       ├── docx_adapter.py   # Word (python-docx)
│       ├── csv_adapter.py    # CSV
│       ├── xlsx_adapter.py   # Excel (openpyxl)
│       ├── text_adapter.py   # TXT/MD
│       ├── image_adapter.py  # Imagens (PIL + OCR + Vision)
│       ├── ocr.py            # Tesseract wrapper (por+eng, dpi)
│       └── vision.py         # Visão Ollama (moondream/qwen2.5vl, resize 1024, num_ctx 4096/8192)
├── rag/                      # PIPELINE DE CONSULTA (pergunta → resposta + fontes)
│   ├── chatbot.py            # Orquestrador (retrieve → rerank → prompt → LLM)
│   ├── retriever.py          # Busca vetorial (top-k, MMR, threshold, retrieve_all)
│   ├── evidence.py           # Evidence + normalizer + aggregator (metadados ricos)
│   ├── prompt.py             # PromptBuilder (system + evidências + modo auto/rag)
│   ├── response.py           # Modelos AgentResponse, Source, Mode, Verdict
│   ├── reranker.py           # CrossEncoder rerank opcional (ms-marco)
│   ├── analyst.py            # Analista proativo (reflexão + follow-ups)
│   ├── calculator.py         # Cálculo determinístico (percentuais, sem LLM)
│   ├── reasoning.py          # CoT / reasoning avançado (quando ENABLE_REASONING)
│   └── query_expander.py     # Expansão de query (multi-variantes + RRF)
├── llm/                      # INTEGRAÇÃO LLM
│   └── ollama_client.py      # Cliente Ollama (generate/stream, think, num_ctx dinâmico, métricas)
├── metrics/                  # OBSERVABILIDADE (SQLite thread-safe)
│   └── store.py              # MetricsStore (llm_calls, requests, documents, index_events)
├── presentation/             # APRESENTAÇÃO
│   ├── dashboard.html        # Dashboard web (Chart.js, métricas)
│   └── formatter.py          # ApiFormatter (formata AgentResponse → JSON API)
├── utils/                    # UTILITÁRIOS
│   └── logger.py             # Setup logger com rotação + console
├── tests/                    # TESTES (pytest, testpaths=["tests"])
│   ├── conftest.py           # Fixtures (tmp_documents_dir, mocks)
│   ├── test_api.py           # API (49 tests, mocks cli.api.*)
│   ├── test_adapters.py      # Adapters
│   ├── test_chatbot.py       # Chatbot
│   ├── test_retriever.py     # Retriever
│   └── ...                   # 29 test_*.py (nenhum depende de documents/ físico)
├── docs/                     # DOCUMENTAÇÃO MkDocs
│   ├── index.md
│   ├── getting-started/      # instalação, quickstart, configuration
│   ├── architecture/         # overview, ingestion-pipeline, rag-pipeline
│   ├── guides/               # usage, google-drive, analyst-mode, monitoring
│   ├── api/                  # api-reference, integration
│   ├── operations/           # deployment, troubleshooting
│   └── development/          # project-structure, development, testing
├── database/                 # DADOS PERSISTENTES (gitignore, regenerável)
│   ├── chroma/               # ChromaDB (chroma.sqlite3 + index_manifest.json)
│   ├── embedding_cache.sqlite3
│   ├── metrics.db
│   ├── images/               # Imagens extraídas de PDFs
│   ├── dedup.json
│   └── index_jobs.json
├── documents/                # DOCUMENTOS PARA INDEXAR (gitignore)
│   ├── manuais_teste/        # 49 PDFs PT-BR (quando populado localmente)
│   ├── drive/                # Staging Google Drive (dest_dir)
│   └── examples/             # Exemplos soltos (images.jpg etc, não indexado em prod)
├── logs/                     # LOGS (gitignore, rotação)
├── libs/                     # BINÁRIOS TERCEIROS (gitignore, exceto tesseract)
│   └── tesseract/            # Tesseract embarcado Windows + tessdata (por, eng)
├── .env.example              # Template de config (commitado)
├── .env                      # Config real (gitignore)
├── requirements.txt          # Deps Python
├── pyproject.toml            # Build/lint/mypy/pytest (testpaths=["tests"])
├── watson.spec               # PyInstaller (entry cli/api.py, hiddenimports ML)
├── watson-supervisord.conf   # Supervisor Linux
├── CHANGELOG.md              # Histórico
└── NEW_VERSION.md            # Notas da versão atual
```

---

## Responsabilidades por camada

### `core/` — Núcleo
| Arquivo | O que faz | Por que separado |
|---|---|---|
| `core/config.py` | `Config` dataclass + `load_dotenv()` — 40+ vars (`OLLAMA_MODEL`, `VISION_MODEL=moondream`, `CHUNK_SIZE`, `TOP_K` etc) | Single source of verdade; todo módulo importa daqui, não de `.env` direto |
| `core/factories.py` | `build_*` (chatbot, retriever, indexer, loader, analyst, reranker) + `ensure_directories` + `preload_models` | Evita duplicação de wiring entre `cli/api.py`, `cli/app.py`, `cli/index.py` etc |

### `cli/` — Entrypoints (8 CLIs)
| Arquivo | Comando | Papel |
|---|---|---|
| `cli/api.py` | `uvicorn cli.api:app` | FastAPI, SSE, auth `X-API-Token`, rate-limit, jobs async `/api/index/async` |
| `cli/app.py` | `python cli/app.py` | Chat terminal (`chat_loop`) |
| `cli/index.py` | `python cli/index.py` | Indexação local (`run_index(sync_drive=False)`) |
| `cli/drive_index.py` | `python cli/drive_index.py [--sync-only]` | Drive sync + index |
| `cli/drive_select.py` | `python cli/drive_select.py` | CLI interativo para `.drive_selection.json` |
| `cli/watch.py` | `python cli/watch.py [--interval 30]` | Polling `documents/` via hash (sem watchdog) |
| `cli/reset_app.py` | `python cli/reset_app.py [--yes --no-docs]` | Limpa chroma, manifest, caches, `database/images`, métricas |
| `cli/service.py` | `python cli/service.py install` | Wrapper win32service (PyInstaller) |

Sem shims na raiz — canônicos são `cli.*`.

### `scripts/` — Operação (sh/bat)
| Arquivo | Plataforma | O que faz |
|---|---|---|
| `start.bat` / `start.sh` | Win / Linux | Menu 1-8 (API, prompt, index, drive, reset, watcher) + `setup` auto, lê `core.config` para `API_HOST:PORT` |
| `setup.bat` / `setup.sh` | Win / Linux | Cria `.venv`, `pip install -r requirements.txt`, garante `.env`, `database/`, `logs/`, `VISION_MODEL`, `ollama pull` |
| `stop.bat` / `stop.sh` | Win / Linux | Mata por porta (`netstat`/`lsof` + `pgrep uvicorn cli.api:app`) |
| `cleanup.bat` / `cleanup.sh` | Ambos | Remove `__pycache__`, `dist/`, `database/chroma`, caches |
| `build.bat` | Win | `PyInstaller watson.spec` → `dist/watson` + `watson.log` |
| `setup_supervisor.sh` | Linux | Instala `supervisord` |

Todos resolvem `ROOT` como `..` a partir de `scripts/` (`ROOT=%~dp0..` / `ROOT_DIR=$(cd $SCRIPT_DIR/..)`).

### `ingestion/` — Indexação
Transforma arquivos brutos em chunks vetorizados. **Não conhece** `rag/` — comunica via `contracts.py` + `vector_store`.

- **Flow:** `loader.py` (rglob + `registry`) → `pdf_adapter.py` (native text → OCR seletivo se `<20 chars` → `PyMuPDF4LLM` markdown) → `splitter.py` (1000/200 por tipo) → `quality.py` → `dedup.py` → `embeddings.py` (cache SQLite) → `vector_store.py` (Chroma collection `documents`) + `manifest.py`.
- **Adapters** desacoplados: adicionar formato = novo `SourceAdapter` + `registry.register`, sem tocar `loader.py`.

### `rag/` — Consulta
Transforma pergunta em resposta com fontes. **Não conhece** detalhes de `ingestion/`.

- `retriever.py` (top-k, MMR, threshold) → `evidence.py` (normaliza `Document` → `Evidence` com `page`, `section`, `manufacturer/model`, `relevance_score`) → `prompt.py` → `chatbot.py` → `llm/ollama_client.py`.
- `analyst.py`, `reasoning.py`, `query_expander.py`, `reranker.py`, `calculator.py` são opcionais e só ativados via `core/config`.

### `llm/` — Integração LLM
`ollama_client.py` encapsula `ollama.Client` (generate/stream, `think`, `num_ctx` dinâmico `len(prompt)/3 + max_tokens`, `THINK_PATTERN` strip, retry, métricas). Desacoplado para trocar provedor sem tocar `rag/`.

### `metrics/` + `presentation/` — Observabilidade e UI
`metrics/store.py` persiste `llm_calls`, `requests`, `documents`, `index_events` em SQLite thread-safe. `presentation/formatter.py` formata `AgentResponse` → JSON API. `dashboard.html` consome `/api/metrics/*`.

### `utils/`
`logger.py` — `setup_logger` com rotação `RotatingFileHandler` + console, usado por `core/`, `cli/`, `ingestion/`.

### `tests/` — Testes
`pyproject.toml: testpaths=["tests"]` — só coleta `tests/`. 29 `test_*.py` usam mocks/fixtures (`conftest.py: tmp_documents_dir`) e **nenhum** depende de `documents/` físico (e2e movidos para fora). `test_api.py` patcha `cli.api.*`.

### `docs/`
MkDocs. `project-structure.md` (este arquivo) é a referência de pastas. Demais guias em `getting-started/`, `architecture/`, `guides/`, `api/`, `operations/`, `development/`.

---

## Diretórios de dados (gitignore)

| Diretório | Conteúdo | Regenerável | Config |
|---|---|---|---|
| `documents/` | Documentos para indexar | Não (fonte) | `DOCUMENTS_DIR=documents` |
| `documents/drive/` | Staging Drive | Sim (re-sync) | `GOOGLE_DRIVE_DEST_DIR` |
| `documents/manuais_teste/` | 49 PDFs PT-BR locais (ex) | Sim (re-download) | — |
| `database/chroma/` | ChromaDB + `index_manifest.json` | Sim (`cli/index.py`) | `VECTOR_DB_DIR` |
| `database/embedding_cache.sqlite3` | Cache embeddings | Sim | `EMBEDDING_CACHE_PATH` |
| `database/metrics.db` | Métricas | Sim | `METRICS_DB` |
| `database/images/` | Imagens extraídas | Sim | `IMAGE_DIR` |
| `logs/` | `ai_agent.log`, `service.log` | Sim | `LOG_FILE` |
| `libs/tesseract/` | Binário Windows + `tessdata` | Não (vendored) | `TESSERACT_CMD` |

Remoção limpa: `python cli/reset_app.py --yes --no-docs` (mantém `documents/`) ou `scripts/cleanup.*` (tudo).

---

## Fluxo de dados

```
Indexação:  documents|drive → loader → pdf_adapter (native/OCR/vision) → splitter → quality/dedup → embeddings (+cache) → Chroma + manifest
Consulta:   pergunta → retriever (top-k) → evidence → prompt (mode auto/rag) → ollama_client → resposta + sources (page/section/model)
```

Detalhes: `docs/architecture/overview.md`, `ingestion-pipeline.md`, `rag-pipeline.md`.

---

## Por que não menos pastas?

5 pastas de domínio (`ingestion`, `rag`, `llm`, `metrics`, `presentation`) poderiam virar 3 (`ingestion`, `rag+llm`, `observability`), mas perderiam SRP: trocar LLM, trocar dashboard ou isolar indexação ficariam acoplados. Atual (9 pastas de código) é o mínimo útil — cada uma tem 1-12 arquivos com propósito único.

---

## Próximos passos

- [Desenvolvimento](development.md)
- [Testes](testing.md)

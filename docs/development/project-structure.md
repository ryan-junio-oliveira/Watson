# Estrutura do Projeto

Organização de pastas e responsabilidades de cada módulo.

---

## Visão geral

```
Watson/
├── api.py                    # API REST FastAPI (chat, indexação, Drive, métricas, dashboard)
├── app.py                    # Chat interativo no terminal
├── index.py                  # Indexação de documentos locais (CLI)
├── drive_index.py            # Sincronização do Drive + indexação
├── drive_select.py           # Seleção de pastas do Drive (CLI)
├── watch.py                  # Watcher — reindexação automática
├── reset_app.py              # Reset total (vetores, docs, cache, métricas)
├── service.py                # Serviço Windows (win32serviceutil)
├── config.py                 # Configurações centralizadas (dataclass + .env)
├── requirements.txt          # Dependências Python
├── pyproject.toml            # Configuração de build/lint/type
├── .env.example              # Exemplo de configuração
│
├── ingestion/                # PIPELINE DE INDEXAÇÃO
│   ├── loader.py             # Descoberta e carregamento de documentos
│   ├── models.py             # Modelos de domínio (Page, Section, Table, LoadedDocument)
│   ├── splitter.py           # Chunking semântico por tipo de fonte
│   ├── embeddings.py         # Geração de embeddings (sentence-transformers)
│   ├── embedding_cache.py    # Cache persistente de embeddings (SQLite)
│   ├── indexer.py            # Orquestrador de indexação incremental
│   ├── vector_store.py       # Interface + ChromaVectorStore
│   ├── manifest.py           # Manifesto de indexação (JSON atômico)
│   ├── contracts.py          # Contrato estável (ChunkContract, PipelineVersion)
│   ├── quality.py            # Portão de qualidade dos chunks
│   ├── dedup.py              # Deduplicação intra/cross-documento
│   ├── identity.py           # Inferência de fabricante/modelo
│   ├── drive_sync.py         # Sincronização de Google Drive (sem OAuth)
│   └── adapters/             # Adaptadores de fonte
│       ├── registry.py       # Mapeamento extensão → adaptador
│       ├── base.py           # ABC SourceAdapter
│       ├── pdf_adapter.py    # PDF (PyMuPDF + OCR seletivo)
│       ├── docx_adapter.py   # Word
│       ├── csv_adapter.py    # CSV
│       ├── xlsx_adapter.py   # Excel
│       ├── text_adapter.py   # TXT/Markdown
│       ├── image_adapter.py  # Imagens (OCR + visão)
│       ├── ocr.py            # Utilitários Tesseract
│       └── vision.py         # Análise por modelo de visão
│
├── rag/                      # PIPELINE DE CONSULTA (RAG)
│   ├── chatbot.py            # Orquestrador (retrieve → prompt → LLM → resposta)
│   ├── retriever.py          # Busca vetorial (top-k, MMR, threshold)
│   ├── evidence.py           # Modelo Evidence + normalizador + agregador
│   ├── prompt.py             # Construção de prompts
│   ├── response.py           # Modelos de resposta (AgentResponse, Source, Mode)
│   ├── reranker.py           # Re-ranking com CrossEncoder (opcional)
│   ├── analyst.py            # Analista proativo (reflexão, perguntas, busca)
│   └── calculator.py         # Cálculo determinístico verificado
│
├── llm/                      # INTEGRAÇÃO COM LLM
│   └── ollama_client.py      # Cliente Ollama (generate, stream, think, métricas)
│
├── metrics/                  # MÉTRICAS
│   ├── store.py              # MetricsStore (SQLite, thread-safe)
│   └── __init__.py
│
├── presentation/             # APRESENTAÇÃO
│   ├── dashboard.html        # Dashboard web de métricas
│   └── formatter.py          # Formatação de saída (API/CLI)
│
├── utils/                    # UTILITÁRIOS
│   └── logger.py             # Logging com rotação + console
│
├── tests/                    # TESTES (pytest)
│   ├── conftest.py           # Fixtures compartilhadas
│   ├── test_api.py           # Endpoints, auth, jobs, drive, métricas
│   ├── test_indexer.py       # Indexação incremental
│   ├── test_chatbot.py       # Chat/RAG
│   ├── test_retriever.py     # Recuperação
│   └── ...                   # (30+ arquivos)
│
├── docs/                     # DOCUMENTAÇÃO
│   ├── index.md
│   ├── getting-started/
│   ├── architecture/
│   ├── guides/
│   ├── api/
│   ├── operations/
│   └── development/
│
├── documents/                # Documentos para indexar
├── database/                 # Dados persistentes (chroma, metrics, images, caches)
└── logs/                     # Logs da aplicação
```

---

## Responsabilidades por camada

### Camada de aplicação (raiz)

| Arquivo | Responsabilidade |
|---|---|
| `api.py` | API REST/SSE, middleware de auth/tracing, jobs assíncronos, dashboard |
| `app.py` | Chat interativo no terminal |
| `index.py` | Indexação de documentos locais via CLI |
| `drive_index.py` | Sync do Drive + indexação |
| `drive_select.py` | Seleção interativa de pastas do Drive |
| `watch.py` | Watcher de reindexação automática |
| `reset_app.py` | Reset total |
| `service.py` | Serviço Windows |
| `config.py` | Configuração central |

### `ingestion/` — Indexação

Responsável por transformar arquivos brutos em **chunks vetorizados** no ChromaDB, com qualidade, dedup e incrementalidade. **Não conhece** a camada de consulta — comunica-se via contrato (`contracts.py`).

### `rag/` — Consulta

Responsável por transformar uma **pergunta** em uma **resposta com fontes**. Recupera evidências, monta prompt e gera a resposta via LLM. **Não conhece** os detalhes de indexação — lê o vetor via `Retriever`.

### `llm/` — Integração com LLM

Encapsula o cliente Ollama (geração, streaming, raciocínio, remoção de bloco de pensamento, métricas).

### `metrics/` — Observabilidade

Persiste métricas de LLM, requisições, documentos e indexação em SQLite, alimentando o dashboard.

### `presentation/` — Apresentação

Dashboard web e formatação de saída para API/CLI, separando o pipeline da apresentação.

---

## Diretórios de dados

| Diretório | Conteúdo |
|---|---|
| `documents/` | Documentos a indexar |
| `documents/drive/` | Arquivos baixados do Google Drive |
| `database/chroma/` | Banco vetorial ChromaDB |
| `database/metrics.db` | Métricas SQLite |
| `database/embedding_cache.sqlite3` | Cache de embeddings |
| `database/images/` | Imagens extraídas/OCR |
| `logs/` | Logs com rotação |

---

## Próximos passos

- [Desenvolvimento](development.md)
- [Testes](testing.md)

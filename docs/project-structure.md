# Estrutura do Projeto

```
Watson/
├── api.py                  # Servidor FastAPI (modo API) - v2.0.0
├── app.py                  # Chat interativo via terminal (modo CLI)
├── index.py                # Indexacao via linha de comando
├── config.py               # Configuracoes centralizadas (dataclass + .env)
├── requirements.txt        # Dependencias Python
├── .env.example            # Exemplo de configuracao
├── .gitignore              # Arquivos ignorados pelo Git
│
├── ingestion/              # Pipeline de indexacao
│   ├── loader.py           # Leitura de PDF, DOCX, TXT, MD, imagens (com OCR)
│   ├── db_loader.py        # Leitura de banco MySQL (com filtro de colunas sensiveis + anti SQL injection)
│   ├── splitter.py         # Chunking de texto (RecursiveCharacterTextSplitter + metadata enriquecida)
│   ├── embeddings.py       # Geracao de embeddings (HuggingFace)
│   └── indexer.py          # Indexacao no ChromaDB com cache SHA-256
│
├── search/                 # Pipeline de busca web (modular, SOLID)
│   ├── provider.py         # Classe abstrata SearchProvider
│   ├── google_provider.py  # Provedor Google (googlesearch-python)
│   ├── ddgs_provider.py    # Provedor DuckDuckGo (ddgs)
│   ├── fetcher.py          # Download de paginas (httpx com retry/backoff/cache)
│   ├── extractor.py        # Extracao de conteudo HTML (trafilatura)
│   ├── cleaner.py          # Limpeza de texto (entidades HTML, whitespace)
│   ├── chunker.py          # Chunking de texto web (RecursiveCharacterTextSplitter)
│   └── reranker.py         # Re-ranking web com CrossEncoder
│
├── rag/                    # Pipeline de consulta (Hybrid RAG Agent)
│   ├── chatbot.py          # Orquestrador: Planner → Busca → Extracao → Sintese → Validacao
│   ├── response.py         # Modelos internos: AgentResponse, Source
│   ├── evidence.py         # Modelo Evidence + EvidenceNormalizer + EvidenceAggregator
│   ├── planner.py          # Classificador de intencao (rag vs web vs ambos)
│   ├── prompt.py           # Construcao de prompts com system prompt + evidencias
│   ├── retriever.py        # Busca vetorial por similaridade (top-k, MMR, threshold)
│   ├── reranker.py         # Re-ranking RAG com CrossEncoder (opcional)
│   └── validator.py        # Validacao factual + ConfidenceScorer + ValidationResult
│
├── presentation/           # Camada de apresentacao (ResponseFormatter)
│   └── formatter.py        # ApiFormatter, CliFormatter - separa pipeline do output
│
├── llm/                    # Integracao com modelo de linguagem
│   └── ollama_client.py    # Cliente Ollama (generate, streaming, list models)
│
├── utils/                  # Utilitarios
│   └── logger.py           # Logging em arquivo com rotacao + console
│
├── tests/                  # Testes unitarios (pytest) - 156 testes
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_chatbot.py
│   ├── test_chunker.py
│   ├── test_cleaner.py
│   ├── test_db_loader.py
│   ├── test_embeddings.py
│   ├── test_evidence.py
│   ├── test_extractor.py
│   ├── test_fetcher.py
│   ├── test_indexer.py
│   ├── test_loader.py
│   ├── test_ollama_client.py
│   ├── test_presentation.py
│   ├── test_prompt.py
│   ├── test_retriever.py
│   ├── test_search_provider.py
│   ├── test_search_reranker.py
│   └── test_splitter.py
│
├── docs/                   # Documentacao detalhada
│   ├── installation.md
│   ├── configuration.md
│   ├── api-reference.md    # Referencia completa da API v2.0.0
│   ├── database-indexing.md
│   ├── integration.md
│   └── project-structure.md
│
├── documents/              # Documentos para indexar (PDF, DOCX, etc.)
├── database/chroma/        # Banco vetorial ChromaDB (persistente)
└── logs/                   # Logs da aplicacao (com rotacao automatica)
```

## Novidades na v2.0.0

### Arquitetura

- **Camada de Apresentacao**: Novo pacote `presentation/` com `ResponseFormatter` (API, CLI). Separa o pipeline de IA do output.
- **AgentResponse**: Modelo interno padrao. Substitui `ChatResult`. Contem `answer`, `evidences`, `confidence`, `verdict`, `issues`, `metadata`, `execution_time`.
- **Source**: Modelo estruturado de fontes (`title`, `url`, `provider`). Fontes nao sao mais concatenadas ao texto.
- **Diagnosticos internos**: Validacao, logs do planner, erros de parsing nunca sao expostos na resposta.

### API

- **Contrato estavel**: Respostas seguem `{success, answer, confidence, sources, metadata}`.
- **Streaming limpo**: Stream termina com `[DONE]` + JSON metadata. Evento `[VALIDATION]` removido.
- **Erros estruturados**: Erros internos retornam `{success: false, error: {code, message}}`.

### Pipeline

- **Hybrid RAG Agent**: Pipeline completo: Planner → Retriever/Search → Fetcher → Extractor → Cleaner → Chunker → Reranker → Aggregator → PromptBuilder → LLM → FactValidator → ConfidenceScorer.
- **Search Web**: Provedor DDGS primario, Google fallback.
- **Evidence**: Modelo unificado `Evidence` com normalizador e agregador.

### Seguranca

- **SQL Injection**: Nomes de tabela do MySQL sao validados e escapados
- **Log Rotation**: Logs rotacionam a cada 10 MB (5 backups)

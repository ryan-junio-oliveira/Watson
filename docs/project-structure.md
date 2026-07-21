# Estrutura do Projeto

```
Watson/
├── api.py                  # Servidor FastAPI (modo API) - v1.1.0
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
├── rag/                    # Pipeline de consulta
│   ├── retriever.py        # Busca vetorial por similaridade (top-k, MMR, threshold)
│   ├── reranker.py         # Re-ranking com CrossEncoder (opcional)
│   ├── prompt.py           # Construcao de prompts com system prompt + contexto
│   └── chatbot.py          # Orquestracao RAG + loop de chat
│
├── llm/                    # Integracao com modelo de linguagem
│   └── ollama_client.py    # Cliente Ollama (generate, streaming, list models)
│
├── utils/                  # Utilitarios
│   └── logger.py           # Logging em arquivo com rotacao + console
│
├── tests/                  # Testes unitarios (pytest) - 80 testes
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_chatbot.py
│   ├── test_db_loader.py
│   ├── test_embeddings.py
│   ├── test_indexer.py
│   ├── test_loader.py
│   ├── test_ollama_client.py
│   ├── test_prompt.py
│   ├── test_retriever.py
│   └── test_splitter.py
│
├── docs/                   # Documentacao detalhada
│   ├── installation.md
│   ├── configuration.md
│   ├── api-reference.md    # Referencia completa da API v1.1.0
│   ├── database-indexing.md
│   ├── integration.md
│   └── project-structure.md
│
├── documents/              # Documentos para indexar (PDF, DOCX, etc.)
├── database/chroma/        # Banco vetorial ChromaDB (persistente)
└── logs/                   # Logs da aplicacao (com rotacao automatica)
```

## Novidades na v1.1.0

### API
- **Streaming SSE**: Endpoint `/api/chat/stream` para respostas em tempo real
- **CORS**: Middleware habilitado para integracoes cross-origin
- **Request Tracing**: Header `X-Request-ID` em todas as respostas
- **Health Check aprimorado**: Verifica conexao real com Ollama

### Seguranca
- **SQL Injection**: Nomes de tabela do MySQL sao validados e escapados
- **Log Rotation**: Logs rotacionam a cada 10 MB (5 backups)

### Pipeline
- **Metadata enriquecida**: Chunks incluem `chunk_index`, `total_chunks`, `chunk_size`
- **Retriever resiliente**: Trata ChromaDB vazio sem crash
# Estrutura do Projeto

```
Watson/
├── api.py                  # Servidor FastAPI (modo API)
├── app.py                  # Chat interativo via terminal (modo CLI)
├── index.py                # Indexacao via linha de comando
├── config.py               # Configuracoes centralizadas (dataclass + .env)
├── requirements.txt        # Dependencias Python
├── .env.example            # Exemplo de configuracao
├── .gitignore              # Arquivos ignorados pelo Git
│
├── ingestion/              # Pipeline de indexacao
│   ├── loader.py           # Leitura de PDF, DOCX, TXT, MD, imagens (com OCR)
│   ├── db_loader.py        # Leitura de banco MySQL (com filtro de colunas sensiveis)
│   ├── splitter.py         # Chunking de texto (RecursiveCharacterTextSplitter)
│   ├── embeddings.py       # Geracao de embeddings (HuggingFace)
│   └── indexer.py          # Indexacao no ChromaDB com cache SHA-256
│
├── rag/                    # Pipeline de consulta
│   ├── retriever.py        # Busca vetorial por similaridade (top-k)
│   ├── prompt.py           # Construcao de prompts com system prompt + contexto
│   └── chatbot.py          # Orquestracao RAG + loop de chat
│
├── llm/                    # Integracao com modelo de linguagem
│   └── ollama_client.py    # Cliente Ollama (generate, streaming, list models)
│
├── utils/                  # Utilitarios
│   └── logger.py           # Logging em arquivo + console
│
├── tests/                  # Testes unitarios (pytest)
│   ├── conftest.py
│   ├── test_chatbot.py
│   ├── test_embeddings.py
│   ├── test_indexer.py
│   ├── test_loader.py
│   ├── test_retriever.py
│   └── test_splitter.py
│
├── docs/                   # Documentacao detalhada
│   ├── installation.md
│   ├── configuration.md
│   ├── api-reference.md
│   ├── database-indexing.md
│   ├── integration.md
│   └── project-structure.md
│
├── documents/              # Documentos para indexar (PDF, DOCX, etc.)
├── database/chroma/        # Banco vetorial ChromaDB (persistente)
└── logs/                   # Logs da aplicacao
```

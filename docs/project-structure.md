# Estrutura do Projeto

```
Watson/
├── api.py                  # Servidor FastAPI (modo API) - v2.1.0
├── app.py                  # Chat interativo via terminal (modo CLI)
├── index.py                # Indexacao via linha de comando
├── config.py               # Configuracoes centralizadas (dataclass + .env)
├── requirements.txt        # Dependencias Python
├── .env.example            # Exemplo de configuracao
├── .gitignore              # Arquivos ignorados pelo Git
│
├── ingestion/              # Pipeline de indexacao
│   ├── loader.py           # Leitura de PDF, DOCX, TXT, MD, imagens (com OCR)
│   ├── splitter.py         # Chunking de texto (RecursiveCharacterTextSplitter + metadata enriquecida)
│   ├── embeddings.py       # Geracao de embeddings (HuggingFace)
│   └── indexer.py          # Indexacao no ChromaDB com cache SHA-256
│
├── rag/                    # Pipeline de consulta (RAG)
│   ├── chatbot.py          # Orquestrador: Recuperacao → Geracao → Validacao
│   ├── response.py         # Modelos: AgentResponse, Source, Mode
│   ├── evidence.py         # Modelo Evidence + EvidenceNormalizer + EvidenceAggregator
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
├── tests/                  # Testes unitarios (pytest)
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_chatbot.py
│   ├── test_embeddings.py
│   ├── test_evidence.py
│   ├── test_indexer.py
│   ├── test_loader.py
│   ├── test_ollama_client.py
│   ├── test_presentation.py
│   ├── test_prompt.py
│   ├── test_retriever.py
│   └── test_splitter.py
│
├── docs/                   # Documentacao detalhada
│   ├── installation.md
│   ├── configuration.md
│   ├── api-reference.md    # Referencia completa da API v2.1.0
│   ├── integration.md
│   └── project-structure.md
│
├── documents/              # Documentos para indexar (PDF, DOCX, etc.)
├── database/chroma/        # Banco vetorial ChromaDB (persistente)
└── logs/                   # Logs da aplicacao (com rotacao automatica)
```

## Novidades na v2.1.0

### Simplificacao

- **RAG-only**: Agente consulta apenas documentos indexados. Sem busca na internet.
- **Codigo removido**: Planner (classificador de intencao) e QueryRefiner removidos. Busca web desabilitada por padrao.
- **Configuracao simplificada**: `ENABLE_PLANNER` e variaveis de busca web removidas do uso padrao.

### Pipeline

- **Pipeline**: Pergunta → ChromaDB (busca vetorial) → LLM (gemma3:4b) → Validacao (anti-alucinacao).
- **2 chamadas LLM**: Geracao + Validacao. Classificacao de intencao removida.
- **Sem rede externa**: Nao faz requisicoes HTTP para buscadores. Apenas Ollama local + ChromaDB local.

### Performance

- **Modelo menor**: Padrao `gemma3:4b` (4B parametros), ~2x mais rapido que `qwen3:8b`.
- **Tokens reduzidos**: `MAX_TOKENS=1024` (antes 2048).
- **Preload**: Embeddings e reranker carregados no startup.

### Historico (v2.0.0)

- **Camada de Apresentacao**: `ResponseFormatter` (API, CLI).
- **AgentResponse**: Modelo interno padrao com `answer`, `evidences`, `confidence`, `verdict`.
- **Source**: Modelo estruturado de fontes.
- **Contrato estavel**: Respostas seguem `{success, answer, confidence, sources, metadata}`.

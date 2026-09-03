# Arquitetura — Visão Geral

O Watson RAG é um sistema de **Retrieval-Augmented Generation** que combina um pipeline de **indexação** (documentos → vetores) e um pipeline de **consulta** (pergunta → resposta com fontes).

---

## Componentes

```
┌────────────────────────────────────────────────────────────────────┐
│                            Watson RAG                             │
│                                                                    │
│  ┌─────────────────┐   ┌─────────────────┐   ┌──────────────────┐ │
│  │  INGESTION      │   │   QUERY (RAG)   │   │   LLM (Ollama)   │ │
│  │  document →     │   │  question →     │   │  generate/stream │ │
│  │  vectors        │   │  answer+sources │   │  think (opcional)│ │
│  └─────────────────┘   └─────────────────┘   └──────────────────┘ │
│                                                                    │
│  ┌─────────────────┐   ┌─────────────────┐   ┌──────────────────┐ │
│  │  ChromaDB       │   │  METRICS        │   │  API (FastAPI)   │ │
│  │  vector store   │   │  SQLite + dash  │   │  REST + SSE      │ │
│  └─────────────────┘   └─────────────────┘   └──────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

| Componente | Módulo | Responsabilidade |
|---|---|---|
| **Indexação** | `ingestion/` | Transforma documentos em chunks vetorizados com qualidade e dedup |
| **Consulta** | `rag/` | Recupera evidências, monta prompt e gera resposta com fontes |
| **LLM** | `llm/ollama_client.py` | Integração com Ollama (geração, streaming, raciocínio) |
| **Banco vetorial** | `ingestion/vector_store.py` | Persistência de vetores via ChromaDB |
| **Métricas** | `metrics/` | Observabilidade em SQLite + dashboard web |
| **API** | `api.py` | Interface REST/SSE para consumidores externos |

---

## Fluxo de dados

### Indexação

```
Documentos / Google Drive
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ DocumentLoader  (descobre arquivos, distribui por)  │
│        │                                            │
│        ▼                                            │
│ SourceAdapters (PDF / DOCX / CSV / XLSX / TXT /     │
│                 Imagem) → LoadedDocument            │
│        │                                            │
│        ▼                                            │
│ DocumentSplitter (chunks semânticos por tipo)       │
│        │                                            │
│        ▼                                            │
│ QualityGate (rejeita chunks de baixa qualidade)     │
│        │                                            │
│        ▼                                            │
│ Deduplicator (rejeita duplicatas intra-doc)         │
│        │                                            │
│        ▼                                            │
│ EmbeddingGenerator (cacheado + versionado)          │
│        │                                            │
│        ▼                                            │
│ ChromaVectorStore (delete+add atômico)              │
│        │                                            │
│        ▼                                            │
│ ManifestStore (commit de hashes e versões)          │
└─────────────────────────────────────────────────────┘
```

### Consulta

```
Pergunta
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ Retriever (top-k, MMR/threshold, rerank opcional)   │
│        │                                            │
│        ▼                                            │
│ EvidenceNormalizer + EvidenceAggregator             │
│        │ (dedup + rank)                             │
│        ▼                                            │
│ Calculator (injetar fatos verificados)              │
│        │                                            │
│        ▼                                            │
│ PromptBuilder (system + evidências + histórico)     │
│        │                                            │
│        ▼                                            │
│ OllamaClient (generate / stream, think opcional)    │
│        │                                            │
│        ▼                                            │
│ strip thinking → AgentResponse (resposta + fontes)  │
│        │                                            │
│        ▼                                            │
│ [opcional] Analyst (reflexão, perguntas, busca)     │
│        │                                            │
│        ▼                                            │
│ MetricsStore (registro da requisição)               │
└─────────────────────────────────────────────────────┘
```

---

## Decisões de design

- **100% local** — sem chamadas a APIs externas de busca ou nuvem. Privacidade garantida.
- **RAG-only** — o agente consulta **exclusivamente** documentos indexados.
- **Indexação incremental** — reindexa apenas o que mudou (hash de conteúdo + versões de pipeline), economizando tempo e recursos.
- **Contrato estável** — `ingestion/contracts.py` define `ChunkContract` e `IndexingManifest`, mantendo a compatibilidade entre indexação e consulta.
- **Qualidade e dedup** — chunks ruins são rejeitados e duplicatas intra-documento eliminadas antes de indexar.
- **Cálculo determinístico** — a aritmética (percentuais, somas, médias) é resolvida por código, não pelo LLM, evitando alucinações numéricas.
- **Observabilidade** — métricas unificadas de LLM, requisições, documentos e indexação em um único SQLite.

---

## Interface com sistemas externos

A interface web (DokViewerManager) e outros consumidores usam a **API REST** em `api.py`. A comunicação é documentada em:

- [Referência da API](../api/api-reference.md)
- [Integração](../api/integration.md)

---

---

## Interfaces web

| URL | O que é |
|---|---|
| `/` | Chat — seletor Flash/Plus/Pro, streaming SSE, fontes com chips |
| `/compare` | Comparar — mesma pergunta em Flash vs Plus vs Pro lado a lado |
| `/config` | Configuração — edita `.env` por sessões (Ollama/RAG/Web Search/Sistema) |
| `/dashboard` | Dashboard — tokens, latência, documentos |
| `/docs` | Swagger — referência interativa da API |

---

## Próximos passos

Você entendeu a arquitetura (passo 1 da [Jornada](../index.md#jornada-recomendada--do-zero-à-produção)). Siga para:

- **[Instalação](../getting-started/installation.md)** → **[Início rápido](../getting-started/quickstart.md)** → **[Configuração — Perfis](../getting-started/configuration.md#11-perfis-watson--flash--plus--pro)**
- Ou aprofunde: [Ingestão](ingestion-pipeline.md) → [RAG](rag-pipeline.md)

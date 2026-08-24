# Configuração

Todas as configurações são centralizadas em `config.py` (dataclass `Config`) e podem ser sobrescritas via **variáveis de ambiente** ou arquivo **`.env`**.

> O `.env` é lido automaticamente na importação do `config.py` via `python-dotenv`.

---

## Arquivo `.env`

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

Edite conforme necessário. O arquivo é re-lido a cada inicialização do processo.

---

## Referência de variáveis

### 🧠 Modelo LLM (Ollama)

| Variável | Padrão | Descrição |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL do servidor Ollama |
| `OLLAMA_MODEL` | `gemma3:4b` | Modelo de geração |
| `OLLAMA_TIMEOUT` | `300` | Timeout (s) por chamada ao Ollama |
| `TEMPERATURE` | `0.1` | Temperatura (0 = determinístico, 1 = criativo) |
| `MAX_TOKENS` | `2048` | Máximo de tokens por resposta |

### 🔢 Embeddings

| Variável | Padrão | Descrição |
|---|---|---|
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-base` | Modelo de embeddings (multilíngue, 768 dims) |
| `EMBEDDING_DEVICE` | `cpu` | Dispositivo (`cpu` ou `cuda`) |
| `EMBEDDING_BATCH_SIZE` | `32` | Lote de documentos por chamada |
| `EMBEDDING_NORMALIZE` | `true` | Normaliza vetores (recomendado) |
| `EMBEDDING_CACHE_PATH` | `database/embedding_cache.sqlite3` | Cache persistente de embeddings |

### ✂️ Chunking e indexação

| Variável | Padrão | Descrição |
|---|---|---|
| `CHUNK_SIZE` | `1000` | Tamanho do chunk em caracteres |
| `CHUNK_OVERLAP` | `200` | Sobreposição entre chunks |
| `INDEX_BATCH_SIZE` | `100` | Lote de inserção no ChromaDB |
| `DOCUMENTS_DIR` | `documents` | Diretório de documentos |
| `VECTOR_DB_DIR` | `database/chroma` | Diretório do banco vetorial |

### 🔍 Recuperação (retrieval)

| Variável | Padrão | Descrição |
|---|---|---|
| `TOP_K` | `5` | Chunks recuperados por consulta |
| `SIMILARITY_THRESHOLD` | *(vazio)* | Score mínimo de similaridade. Vazio/ausente = sem filtro; um valor como `0.0` filtra scores negativos |
| `USE_MMR` | `false` | Usa Max Marginal Relevance (diversidade) |
| `MMR_FETCH_K` | `20` | Candidatos para MMR |
| `MMR_LAMBDA` | `0.5` | Equilíbrio relevância × diversidade |
| `USE_RERANKER` | `false` | Habilita re-ranking com CrossEncoder |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Modelo de re-ranking |

### 🖼️ OCR e visão

| Variável | Padrão | Descrição |
|---|---|---|
| `TESSERACT_CMD` | `libs/tesseract` | Caminho do Tesseract (vazio = PATH no Linux) |
| `OCR_LANG` | `por+eng` | Idiomas do OCR |
| `OCR_DPI` | `300` | Resolução para OCR de PDFs |
| `OCR_MIN_TEXT_CHARS` | `20` | Mínimo de caracteres para considerar texto nativo |
| `IMAGE_DIR` | `database/images` | Diretório de imagens extraídas |
| `VISION_MODEL` | *(vazio)* | Modelo de visão Ollama p/ descrever imagens (ex.: `llava`) |

### 🧠 Watson Analista

| Variável | Padrão | Descrição |
|---|---|---|
| `ENABLE_REASONING` | `false` | Habilita modo `think` para perguntas analíticas (modelos qwen3/qwq) |
| `ENABLE_ANALYST` | `true` | Habilita o Analista proativo |
| `ANALYST_MAX_FOLLOWUPS` | `3` | Máximo de perguntas de acompanhamento |

### 🌐 Google Drive (pasta pública)

| Variável | Padrão | Descrição |
|---|---|---|
| `GOOGLE_DRIVE_FOLDER_ID` | *(vazio)* | ID da pasta pública raiz |
| `GOOGLE_DRIVE_DEST_DIR` | `documents/drive` | Onde os arquivos do Drive são salvos |
| `GOOGLE_DRIVE_SYNC_TIMEOUT` | `60` | Timeout (s) por requisição de download |
| `GOOGLE_DRIVE_WORKERS` | `8` | Downloads paralelos durante o sync (mínimo 1) |

### 🔌 API

| Variável | Padrão | Descrição |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Host do servidor FastAPI |
| `API_PORT` | `9000` | Porta do servidor |
| `API_AUTH_TOKEN` | *(vazio)* | Token exigido no header `X-API-Token`. Vazio = auth desativada |

### 📊 Métricas e logs

| Variável | Padrão | Descrição |
|---|---|---|
| `METRICS_DB` | `database/metrics.db` | Banco SQLite de métricas |
| `LOG_LEVEL` | `INFO` | Nível de log (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FILE` | `logs/ai_agent.log` | Caminho do arquivo de log |
| `AGENT_NAME` | `Watson` | Nome exibido pelo agente |

---

## Autenticação da API

A API expõe endpoints de escrita na rede. Para protegê-la, defina um token:

```env
API_AUTH_TOKEN=um-texto-longo-e-aleatorio
```

Toda chamada a `/api/*` (exceto `/api/health`) passa a exigir o header:

```bash
curl -H "X-API-Token: SEU_TOKEN" http://localhost:9000/api/models
# ou
curl -H "Authorization: Bearer SEU_TOKEN" http://localhost:9000/api/models
```

Se `API_AUTH_TOKEN` estiver vazio, a autenticação fica desativada (apenas para desenvolvimento local).

---

## Modelo de geração: qual usar?

| Modelo | Tamanho | Velocidade (CPU) | Qualidade | Uso |
|---|---|---|---|---|
| `gemma3:4b` | 4B | Rápida | Boa | Padrão recomendado para CPU |
| `qwen3:8b` | 8B | Média | Melhor | Qualidade superior, mais lento |
| `qwen3` / `qwq` | — | — | — | Suportam modo `think` (raciocínio) |

> A escolha depende do seu hardware. Em CPU, `gemma3:4b` oferece o melhor equilíbrio entre velocidade e qualidade.

---

## Próximos passos

- [Início rápido](quickstart.md)
- [Arquitetura](../architecture/overview.md)
- [Guia de uso](../guides/usage.md)

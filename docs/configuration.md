# Configuracao

Todas as configuracoes sao centralizadas em `config.py` e podem ser sobrescritas via variaveis de ambiente ou arquivo `.env`.

## Arquivo `.env`

```bash
cp .env.example .env
```

## Tabela de Configuracoes

| Variavel | Padrao | Descricao |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL do servidor Ollama |
| `OLLAMA_MODEL` | `gemma3:4b` | Modelo LLM para respostas |
| `OLLAMA_TIMEOUT` | `180` | Timeout em segundos para chamadas ao Ollama |
| `TEMPERATURE` | `0.1` | Temperatura do modelo (0.0 = deterministico, 1.0 = criativo) |
| `MAX_TOKENS` | `1024` | Maximo de tokens por resposta |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Modelo de embeddings (sentence-transformers) |
| `EMBEDDING_DEVICE` | `cpu` | Dispositivo para embeddings (`cpu` ou `cuda`) |
| `CHUNK_SIZE` | `1000` | Tamanho de cada chunk em caracteres |
| `CHUNK_OVERLAP` | `200` | Sobreposicao entre chunks consecutivos |
| `TOP_K` | `5` | Numero de chunks recuperados por consulta |
| `SIMILARITY_THRESHOLD` | `0.0` | Score minimo de similaridade (0.0 = sem filtro) |
| `USE_MMR` | `false` | Usar Max Marginal Relevance para diversidade |
| `MMR_FETCH_K` | `20` | Candidatos extras para MMR |
| `MMR_LAMBDA` | `0.5` | Balanco relevancia vs diversidade (MMR) |
| `USE_RERANKER` | `false` | Habilitar re-ranking com CrossEncoder |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Modelo de reranker |
| `INDEX_BATCH_SIZE` | `100` | Lote de chunks para insercao no ChromaDB |
| `DOCUMENTS_DIR` | `documents` | Diretorio para documentos a serem indexados |
| `VECTOR_DB_DIR` | `database/chroma` | Diretorio do banco vetorial ChromaDB |
| `ENABLE_VALIDATOR` | `true` | Validacao anti-alucinacao das respostas |
| `MIN_CONFIDENCE` | `0.5` | Confianca minima aceitavel |
| `LOG_LEVEL` | `INFO` | Nivel de logging (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FILE` | `logs/ai_agent.log` | Caminho do arquivo de log |
| `API_HOST` | `0.0.0.0` | Host do servidor API |
| `API_PORT` | `9000` | Porta do servidor API |

---

## Pipeline de consulta

O Watson consulta **apenas documentos indexados** (PDF, DOCX, TXT, MD):

```
Pergunta → ChromaDB (busca vetorial) → LLM (geracao) → Validacao (anti-alucinacao)
```

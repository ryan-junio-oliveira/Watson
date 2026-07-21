# Referencia da API

Servidor FastAPI padrao na porta `9000`. Documentacao interativa disponivel em `/docs` (Swagger) e `/redoc`.

## Endpoints

### `GET /api/health`

Verifica se a API esta operacional.

```json
{
  "status": "ok",
  "documents_dir": "documents",
  "chroma_dir": "database/chroma",
  "db_configured": true,
  "ollama_model": "qwen3:8b"
}
```

---

### `GET /api/models`

Lista os modelos disponiveis no servidor Ollama.

```json
{
  "models": ["qwen3:8b", "llama3.2:3b", "mistral:7b"]
}
```

---

### `POST /api/chat`

Endpoint principal de perguntas e respostas com RAG.

**Body:**
```json
{
  "question": "Quantas licencas estao prestes a expirar?",
  "history": [
    {"role": "user", "content": "Qual o total de clientes?"},
    {"role": "assistant", "content": "Temos 15 clientes ativos."}
  ],
  "model": "qwen3:8b"
}
```

| Campo | Tipo | Obrigatorio | Descricao |
|---|---|---|---|
| `question` | string | sim | Pergunta em linguagem natural |
| `history` | array | nao | Historico da conversa para contexto |
| `model` | string | nao | Modelo Ollama (usa o padrao da config se omitido) |

**Erros:**
| Status | Significado |
|---|---|
| 400 | Pergunta vazia ou invalida |
| 503 | Chatbot nao inicializado |
| 500 | Erro interno (LLM, ChromaDB, etc.) |

---

### `POST /api/index`

Indexa documentos e banco de dados simultaneamente. Apenas arquivos novos ou modificados sao processados.

```json
{
  "status": "ok",
  "documents_indexed": 5,
  "db_indexed": 150,
  "total_chunks": 1200
}
```

---

### `POST /api/index/documents`

Indexa apenas documentos (PDF, DOCX, TXT, MD, imagens) do diretorio configurado.

---

### `POST /api/index/database`

Indexa apenas o banco de dados MySQL. Requer `DB_CONNECTION_STRING` configurado.

---

### `POST /api/documents/upload`

Upload de um arquivo para o diretorio de documentos. Apos o upload, execute `/api/index/documents` para indexa-lo.

```bash
curl -X POST http://localhost:9000/api/documents/upload \
  -F "file=@contrato.pdf"
```

```json
{
  "status": "ok",
  "filename": "contrato.pdf",
  "size": 102400
}
```

---

### `POST /api/clear`

Remove todos os documentos e limpa o banco vetorial ChromaDB.

---

### `POST /api/clear/documents`

Remove apenas os arquivos de documentos do diretorio. O banco vetorial permanece intacto.

---

### `POST /api/clear/vectorstore`

Remove apenas o banco vetorial ChromaDB. Os arquivos de documentos permanecem no diretorio.

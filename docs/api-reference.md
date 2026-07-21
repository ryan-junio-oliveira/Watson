# Referencia da API

Servidor FastAPI padrao na porta `9000`. Documentacao interativa disponivel em `/docs` (Swagger) e `/redoc`.

**Versao atual:** 1.1.0

---

## Endpoints

### `GET /api/health`

Verifica se a API esta operacional e se o Ollama esta acessivel.

**Response (200 - OK):**
```json
{
  "status": "ok",
  "documents_dir": "documents",
  "chroma_dir": "database/chroma",
  "db_configured": true,
  "ollama_model": "qwen3:8b"
}
```

**Response (503 - Degradado):**
```json
{
  "status": "degraded",
  "documents_dir": "documents",
  "chroma_dir": "database/chroma",
  "db_configured": true,
  "ollama_model": "qwen3:8b"
}
```

| Campo | Tipo | Descricao |
|---|---|---|
| `status` | string | `"ok"` (tudo funcionando) ou `"degraded"` (Ollama indisponivel) |
| `documents_dir` | string | Diretorio de documentos configurado |
| `chroma_dir` | string | Diretorio do banco vetorial ChromaDB |
| `db_configured` | bool | Se o banco MySQL esta configurado |
| `ollama_model` | string | Modelo Ollama configurado |

---

### `GET /api/models`

Lista os modelos disponiveis no servidor Ollama.

**Response (200):**
```json
{
  "models": ["qwen3:8b", "llama3.2:3b", "mistral:7b"]
}
```

Em caso de falha de conexao com Ollama, retorna apenas o modelo configurado como fallback.

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

**Response (200):**
```json
{
  "answer": "Existem 5 servidores cadastrados no sistema."
}
```

**Erros:**
| Status | Significado |
|---|---|
| 400 | Pergunta vazia ou invalida |
| 503 | Chatbot nao inicializado |
| 500 | Erro interno (LLM, ChromaDB, etc.) |

---

### `POST /api/chat/stream`

**Novo na v1.1.0** - Endpoint de chat com resposta em **streaming (SSE)**.

Envia uma pergunta e recebe a resposta token por token em tempo real via Server-Sent Events.

**Body** (mesmo formato do `/api/chat`):
```json
{
  "question": "Quais servidores estao cadastrados?",
  "history": null,
  "model": null
}
```

**Response:** Stream de eventos SSE no formato:
```
data: token_1
data: token_2
data: token_3
data: [DONE]
```

**Exemplo com curl:**
```bash
curl -N -X POST http://localhost:9000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "Quais servidores estao cadastrados?"}'
```

**Exemplo com JavaScript:**
```javascript
const eventSource = new EventSource('/api/chat/stream');
// Nota: use fetch com streaming para POST
const response = await fetch('/api/chat/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ question: "Quais servidores?" })
});
const reader = response.body.getReader();
// Processar o stream...
```

**Erros:**
| Status | Significado |
|---|---|
| 400 | Pergunta vazia ou invalida |
| 503 | Chatbot nao inicializado |

---

### `POST /api/index`

Indexa documentos e banco de dados simultaneamente. Apenas arquivos novos ou modificados sao processados.

**Response (200):**
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

**Response (200):**
```json
{
  "status": "ok",
  "filename": "contrato.pdf",
  "size": 102400
}
```

**Erros:**
| Status | Significado |
|---|---|
| 400 | Nenhum arquivo enviado ou nome invalido |
| 409 | Arquivo ja existe |
| 413 | Arquivo muito grande (max 50 MB) |

---

### `POST /api/clear`

Remove todos os documentos e limpa o banco vetorial ChromaDB.

**Response (200):**
```json
{
  "status": "ok",
  "documents_removed": 10,
  "vectorstore_files_removed": 25
}
```

---

### `POST /api/clear/documents`

Remove apenas os arquivos de documentos do diretorio. O banco vetorial permanece intacto.

---

### `POST /api/clear/vectorstore`

Remove apenas o banco vetorial ChromaDB. Os arquivos de documentos permanecem no diretorio.

---

## Headers de Resposta

| Header | Descricao |
|---|---|
| `X-Request-ID` | ID unico de cada requisicao para tracing e correlacao de logs |

---

## Seguranca

- **CORS**: Habilitado para todas origens (configuravel)
- **SQL Injection**: Nomes de tabela do MySQL sao validados e escapados
- **Colunas sensiveis**: `password`, `senha`, `token`, `secret`, etc. sao automaticamente filtradas na indexacao do banco

---

## Modelos de Dados

### ChatRequest
```json
{
  "question": "string (obrigatorio)",
  "history": [
    {"role": "user|assistant", "content": "string"}
  ],
  "model": "string (opcional)"
}
```

### ChatResponse
```json
{
  "answer": "string"
}
```

### IndexResponse
```json
{
  "status": "string",
  "documents_indexed": "integer",
  "db_indexed": "integer",
  "total_chunks": "integer"
}
```

### HealthResponse
```json
{
  "status": "string (ok|degraded)",
  "documents_dir": "string",
  "chroma_dir": "string",
  "db_configured": "boolean",
  "ollama_model": "string"
}
```

### ErrorResponse
```json
{
  "detail": "string"
}
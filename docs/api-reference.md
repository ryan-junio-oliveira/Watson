# Referencia da API

Servidor FastAPI padrao na porta `9000`. Documentacao interativa disponivel em `/docs` (Swagger) e `/redoc`.

**Versao atual:** 2.0.0

---

## Arquitetura da Resposta

Todas as respostas da API seguem um contrato estavel e previsivel, separando **apresentacao** do **pipeline interno**:

```
Pipeline de IA → AgentResponse (interno) → ResponseFormatter → JSON estavel
```

Diagnosticos internos (validacao, logs do planner, erros de parsing) **nunca** sao expostos na resposta.

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

Endpoint principal de perguntas e respostas.

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
| `mode` | string | nao | Fonte de conhecimento: `"auto"` (planner decide), `"knowledge"` (apenas LLM), `"rag"` (documentos indexados), `"web"` (internet), `"all"` (ambos). Padrao: `"auto"`. Em `"rag"`, `"web"` ou `"all"`, o LLM nao pode usar conhecimento proprio se nao encontrar resultados — apenas informa que nao encontrou. |

**Response (200):**
```json
{
  "success": true,
  "answer": "Existem 5 servidores cadastrados no sistema.",
  "confidence": 0.94,
  "sources": [
    {
      "title": "Dicio",
      "url": "https://www.dicio.com.br/morango/",
      "provider": "web"
    }
  ],
  "metadata": {
    "provider": "web",
    "evidence_count": 3,
    "execution_time_ms": 814,
    "verdict": "consistent"
  }
}
```

| Campo | Tipo | Descricao |
|---|---|---|
| `success` | bool | `true` para respostas bem-sucedidas |
| `answer` | string | Texto da resposta gerada |
| `confidence` | float | Nivel de confianca (0.0 a 1.0) |
| `sources` | array | Lista de fontes utilizadas (vide modelo `Source`) |
| `metadata` | object | Metadados da execucao (vide modelo `ChatMetadata`) |

**Response (500 - Erro interno):**
```json
{
  "success": false,
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "O servico de busca nao respondeu"
  }
}
```

**Erros:**
| Status | Significado |
|---|---|
| 400 | Pergunta vazia ou invalida |
| 500 | Erro interno (formato `ChatErrorResponse`) |
| 503 | Chatbot nao inicializado |

---

### `POST /api/chat/stream`

Endpoint de chat com resposta em **streaming (SSE)**.

Envia uma pergunta e recebe a resposta token por token em tempo real.

**Body** (mesmo formato do `/api/chat`):
```json
{
  "question": "Quais servidores estao cadastrados?"
}
```

**Response:** Stream de eventos SSE no formato:
```
data: token_1
data: token_2
data: token_3
data: [DONE]
data: {"confidence": 0.94, "sources": [...], "metadata": {...}}
```

Sequencia de eventos:
1. `data: <texto>\n\n` — tokens individuais da resposta
2. `data: [DONE]\n\n` — fim do texto da resposta
3. `data: <JSON>\n\n` — metadados finais (confidence, sources, metadata)

> **Nota:** Eventos de validacao interna (`[VALIDATION]`) **nao** sao mais emitidos a partir da v2.0.0.

**Exemplo com curl:**
```bash
curl -N -X POST http://localhost:9000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "Quais servidores estao cadastrados?"}'
```

**Exemplo com JavaScript:**
```javascript
const response = await fetch('/api/chat/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ question: "Quais servidores?" })
});
const reader = response.body.getReader();
// Processar o stream ate [DONE], depois ler o JSON final
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
  "model": "string (opcional)",
  "mode": "auto|knowledge|rag|web|all (opcional, padrao: auto)"
}
```

### ChatSuccessResponse (v2.0.0)
```json
{
  "success": true,
  "answer": "string",
  "confidence": 0.0 a 1.0,
  "sources": [
    {
      "title": "string",
      "url": "string",
      "provider": "string (opcional)"
    }
  ],
  "metadata": {
    "provider": "string (rag|web|hybrid)",
    "evidence_count": "integer",
    "execution_time_ms": "integer",
    "verdict": "string (consistent|partial|inconsistent|unknown)",
    "issues": ["string (opcional)"]
  }
}
```

### ChatErrorResponse (v2.0.0)
```json
{
  "success": false,
  "error": {
    "code": "string",
    "message": "string"
  }
}
```

### Source
```json
{
  "title": "string",
  "url": "string",
  "provider": "string (opcional)"
}
```

### ChatMetadata
```json
{
  "provider": "string (rag|web|hybrid)",
  "evidence_count": "integer",
  "execution_time_ms": "integer",
  "verdict": "string (consistent|partial|inconsistent|unknown)",
  "issues": ["string (opcional)"]
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

### ErrorResponse (legado)
```json
{
  "detail": "string"
}
```

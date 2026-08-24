# Referência da API

Servidor FastAPI, padrão na porta `9000`. Documentação interativa em `/docs` (Swagger) e `/redoc`.

**Versão atual:** `0.0.1`

---

## Visão geral

Todas as respostas seguem um contrato estável. O Watson consulta **exclusivamente documentos indexados** (RAG).

```
Adapters (PDF/OCR/DOCX/CSV/XLSX/imagem) → Chunking semântico → Embeddings → ChromaDB → LLM (Ollama) → JSON estável
```

Cada fonte retornada carrega **metadados ricos** (fabricante, modelo, seção, página e códigos de erro) para citação no chat.

---

## Autenticação

Se `API_AUTH_TOKEN` estiver definido no `.env`, toda chamada a `/api/*` (exceto `/api/health`) exige um destes headers:

```bash
X-API-Token: SEU_TOKEN
# ou
Authorization: Bearer SEU_TOKEN
```

Sem o token correto, a API retorna **401** com `WWW-Authenticate: Bearer`.

---

## Headers de resposta

| Header | Descrição |
|---|---|
| `X-Request-ID` | ID único de cada requisição para tracing e correlação de logs |

---

## Endpoints

### `GET /api/health`

Público (não exige token). Verifica se a API está operacional e se o Ollama está acessível.

**Response (200):**
```json
{
  "status": "ok",
  "documents_dir": "documents",
  "chroma_dir": "database/chroma",
  "ollama_model": "gemma3:4b"
}
```

**Response (503 — degradado):**
```json
{
  "status": "degraded",
  "documents_dir": "documents",
  "chroma_dir": "database/chroma",
  "ollama_model": "gemma3:4b"
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `status` | string | `"ok"` ou `"degraded"` (Ollama indisponível) |
| `documents_dir` | string | Diretório de documentos |
| `chroma_dir` | string | Diretório do banco vetorial |
| `ollama_model` | string | Modelo Ollama configurado |

---

### `GET /api/models`

Lista os modelos disponíveis no servidor Ollama.

**Response (200):**
```json
{
  "models": ["gemma3:4b", "llama3.2:3b"]
}
```

Em falha de conexão com o Ollama, retorna apenas o modelo configurado como fallback.

---

### `POST /api/chat`

Endpoint principal de perguntas e respostas.

**Body:**
```json
{
  "question": "Como corrigir o erro E123 na impressora E52645?",
  "history": [
    {"role": "user", "content": "Qual o total de clientes?"},
    {"role": "assistant", "content": "Temos 15 clientes ativos."}
  ],
  "mode": "auto",
  "analyze": false
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `question` | string | sim | Pergunta em linguagem natural |
| `history` | array | não | Histórico da conversa (`user`/`assistant`) |
| `mode` | string | não | `"auto"` ou `"rag"` (equivalentes — ambos usam RAG). Padrão: `"auto"` |
| `analyze` | bool | não | Se `true`, roda a análise proativa (conclusões, perguntas, busca). Padrão: `false` |

**Response (200):**
```json
{
  "success": true,
  "answer": "Para desatolar papel preso, siga: 1. ... (Fonte: seção Troubleshooting, página 142)",
  "confidence": 0.94,
  "sources": [
    {
      "title": "HP LASER JET E52645.pdf",
      "url": "",
      "provider": "rag",
      "page": 142,
      "section": "Troubleshooting",
      "manufacturer": "HP",
      "model": "E52645",
      "error_codes": ["E123"]
    }
  ],
  "metadata": {
    "provider": "rag",
    "evidence_count": 3,
    "execution_time_ms": 814,
    "verdict": "ok"
  },
  "follow_up": null,
  "conclusions": null,
  "additional_info": null
}
```

**Campos de cada `source`:**

| Campo | Tipo | Descrição |
|---|---|---|
| `title` | string | Nome do documento/fonte |
| `url` | string | URL (vazio para documentos internos) |
| `provider` | string | Sempre `"rag"` |
| `page` | integer/null | Página onde o trecho foi encontrado |
| `section` | string | Seção do documento (headings) |
| `manufacturer` | string | Fabricante inferido |
| `model` | string | Modelo do equipamento |
| `error_codes` | array | Códigos de erro detectados |

**Campos da análise proativa** (quando `analyze=true`):

| Campo | Tipo | Descrição |
|---|---|---|
| `follow_up` | array | Perguntas de acompanhamento |
| `conclusions` | array | Conclusões da análise sobre a resposta |
| `additional_info` | array | Informação adicional buscada no acervo |

**Response (500 — erro interno):**
```json
{
  "success": false,
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "O serviço não respondeu"
  }
}
```

**Erros:**

| Status | Significado |
|---|---|
| 400 | Pergunta vazia ou inválida |
| 401 | Token de autenticação ausente/incorreto |
| 500 | Erro interno (`ChatErrorResponse`) |
| 503 | Chatbot não inicializado |

---

### `POST /api/chat/stream`

Chat com resposta em **streaming (SSE)**. Cada token é enviado como JSON para preservar newlines e formatação.

**Body** (mesmo formato de `/api/chat`).

**Response:** stream de eventos SSE:

```
data: {"content": "Para desatolar"}
data: {"content": " papel preso, siga:"}
data: {"content": "\\n\\n1. Abra a porta frontal."}
data: [DONE]
data: {"confidence": 0.94, "sources": [...], "metadata": {...}}
```

Sequência:
1. `data: {"content": "<token>"}` — cada token da resposta.
2. `data: [DONE]` — fim do texto.
3. `data: <JSON>` — metadados finais (`confidence`, `sources`, `metadata`, `follow_up`, etc.).

**Exemplo com cURL:**
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
const decoder = new TextDecoder();
let buffer = '';
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const events = buffer.split('\n\n');
  buffer = events.pop();
  for (const ev of events) {
    const line = ev.trim();
    if (!line.startsWith('data: ')) continue;
    const payload = JSON.parse(line.slice(6));
    if (payload.content) process.stdout.write(payload.content);
    if (payload.sources) console.log('\nSources:', payload.sources);
  }
}
```

**Erros:**

| Status | Significado |
|---|---|
| 400 | Pergunta vazia ou inválida |
| 401 | Token ausente/incorreto |
| 503 | Chatbot não inicializado |

---

### `POST /api/index`

Indexa documentos de forma **incremental** (hash + versões de parser/chunking/embedding). Apenas arquivos novos ou alterados são processados.

**Response (200):**
```json
{
  "status": "ok",
  "documents_indexed": 5,
  "total_chunks": 1200
}
```

---

### `POST /api/index/documents`

Indexa apenas documentos do diretório configurado, sem sincronizar o Drive. Comportamento idêntico ao `POST /api/index` — a sincronização do Drive só ocorre via `/api/index/async` com `sync_drive=true`.

---

### `POST /api/index/async`

Indexação em **segundo plano**. Não bloqueia a requisição; retorna um `job_id`.

**Body:**
```json
{
  "mode": "all",
  "sync_drive": false
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `mode` | string | `"all"` ou `"documents"` |
| `sync_drive` | bool | Se `true`, sincroniza o Drive antes de indexar. Padrão: `false` |

**Response (200):**
```json
{
  "status": "started",
  "job_id": "abc123def456"
}
```

> Se já houver um job em andamento, retorna **409 Conflict**.

---

### `GET /api/index/status/{job_id}`

Consulta o status/progresso de um job de indexação.

**Response (200):**
```json
{
  "status": "running",
  "progress": 4,
  "total": 10,
  "message": "manual.pdf",
  "result": null,
  "error": null
}
```

**Status possíveis:** `running` | `done` | `error` | `cancelled`.

Quando `done`, `result` contém o resumo (`documents_indexed`, `total_chunks`). Jobs com mais de 1h são descartados automaticamente.

---

### `POST /api/index/cancel/{job_id}`

Solicita cancelamento cooperativo de um job.

**Response (200):**
```json
{
  "status": "cancelling",
  "job_id": "abc123def456"
}
```

> O status do job passa a `cancelled` no polling de `GET /api/index/status/{job_id}`, assim que o worker abortar entre documentos.

---

### `POST /api/documents/upload`

Upload de um arquivo para o diretório de documentos. Após o upload, execute `/api/index/documents` para indexá-lo.

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
| 400 | Nenhum arquivo enviado ou nome inválido |
| 401 | Token ausente/incorreto |
| 409 | Arquivo já existe |
| 413 | Arquivo muito grande (máx. 50 MB) |

---

### `POST /api/clear`

Remove todos os documentos, o banco vetorial **e** o manifesto de indexação.

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

Remove apenas os arquivos de documentos. O banco vetorial permanece intacto.

---

### `POST /api/clear/vectorstore`

Remove apenas o banco vetorial e o manifesto. Os arquivos permanecem no diretório.

---

### `GET /api/drive/folder/{folder_id}`

Lista pastas e arquivos de um diretório do Google Drive.

**Response (200):**
```json
{
  "items": [
    {"id": "1Aa...", "name": "MANUAIS", "type": "folder"},
    {"id": "2Bb...", "name": "manual-e52645.pdf", "type": "file", "modified": "2025-01-01"}
  ]
}
```

---

### `GET /api/drive/selection`

Lê a seleção de pastas do Drive.

**Response (200):**
```json
{
  "folders": [
    {"folder_id": "1Aa...", "path": "MANUAIS/HP"}
  ],
  "selected": 1
}
```

---

### `POST /api/drive/selection`

Salva a seleção de pastas do Drive.

**Body:**
```json
{
  "folders": [
    {"folder_id": "1Aa...", "path": "MANUAIS/HP"}
  ]
}
```

---

### `POST /api/drive/sync`

Sincroniza as pastas selecionadas do Drive para disco. Pode demorar.

**Response (200):**
```json
{
  "status": "ok",
  "files_remote": 40,
  "folders": 5,
  "downloaded": 12,
  "skipped": 25,
  "failed": 0,
  "removed": 1,
  "bytes_downloaded": 10485760,
  "errors": []
}
```

---

### `POST /api/drive/clear`

Remove os arquivos baixados do Drive e limpa a seleção.

**Response (200):**
```json
{
  "status": "ok",
  "removed": 12
}
```

---

### Endpoints de métricas

| Endpoint | Método | Descrição |
|---|---|---|
| `/api/metrics/summary` | GET | Resumo geral — `?hours=` |
| `/api/metrics/tokens` | GET | Série de tokens entrada/saída — `?hours=` |
| `/api/metrics/requests` | GET | Série de requisições — `?hours=` |
| `/api/metrics/models` | GET | Tokens por modelo — `?hours=` |
| `/api/metrics/llm-calls` | GET | Chamadas recentes de LLM — `?limit=` |
| `/api/metrics/requests-log` | GET | Requisições recentes — `?limit=` |
| `/api/metrics/documents` | GET | Histórico de documentos/chunks |
| `/api/metrics/index-events` | GET | Eventos recentes de indexação — `?limit=` |

---

### `GET /dashboard`

Serve o dashboard de métricas (HTML single-page). Excluído do schema OpenAPI.

---

## Modelos de dados

### ChatRequest
```json
{
  "question": "string (obrigatório)",
  "history": [{"role": "user|assistant", "content": "string"}],
  "mode": "auto|rag (padrão: auto)",
  "analyze": "bool (padrão: false)"
}
```

### ChatSuccessResponse
```json
{
  "success": true,
  "answer": "string",
  "confidence": "float 0.0-1.0",
  "sources": [
    {
      "title": "string",
      "url": "string",
      "provider": "string (rag)",
      "page": "integer|null",
      "section": "string",
      "manufacturer": "string",
      "model": "string",
      "error_codes": ["string"]
    }
  ],
  "metadata": {
    "provider": "string (rag)",
    "evidence_count": "integer",
    "execution_time_ms": "integer",
    "verdict": "string",
    "issues": ["string (opcional)"],
    "fallback": "\"no_documents\" (presente apenas quando não há documentos indexados)"
  },
  "follow_up": ["string (opcional)"],
  "conclusions": ["string (opcional)"],
  "additional_info": ["string (opcional)"]
}
```

### ChatErrorResponse
```json
{
  "success": false,
  "error": {
    "code": "string",
    "message": "string"
  }
}
```

### IndexResponse
```json
{
  "status": "string",
  "documents_indexed": "integer",
  "total_chunks": "integer"
}
```

### ClearResponse
```json
{
  "status": "string",
  "documents_removed": "integer",
  "vectorstore_files_removed": "integer"
}
```

### HealthResponse
```json
{
  "status": "string (ok|degraded)",
  "documents_dir": "string",
  "chroma_dir": "string",
  "ollama_model": "string"
}
```

### DriveSyncResponse
```json
{
  "status": "string",
  "files_remote": "integer",
  "folders": "integer",
  "downloaded": "integer",
  "skipped": "integer",
  "failed": "integer",
  "removed": "integer",
  "bytes_downloaded": "integer",
  "errors": ["string"]
}
```

---

## Segurança

- **CORS**: habilitado para todas as origens.
- **Auth**: token via `API_AUTH_TOKEN` (opcional, exceto `/api/health`).
- **Tracing**: header `X-Request-ID` em toda resposta.

---

## Próximos passos

- [Integração](integration.md) — exemplos de consumo
- [Monitoramento](../guides/monitoring.md)

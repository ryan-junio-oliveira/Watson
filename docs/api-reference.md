# Referencia da API

Servidor FastAPI padrao na porta `9000`. Documentacao interativa disponivel em `/docs` (Swagger) e `/redoc`.

**Versao atual:** 3.0.0

---

## Arquitetura da Resposta

Todas as respostas da API seguem um contrato estavel e previsivel:

```
Adapters (PDF/OCR/DOCX/CSV/XLSX/imagem) → Chunking semantico → Embeddings multilíngues → ChromaDB → LLM (Ollama) → JSON estavel
```

O Watson consulta **exclusivamente documentos indexados** (RAG). Diagnosticos internos (validacao, logs) **nunca** sao expostos na resposta.

Cada fonte retornada carrega **metadata rica** (fabricante, modelo, seção, página e códigos de erro) para citação no chat.

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
  "ollama_model": "gemma3:4b"
}
```

**Response (503 - Degradado):**
```json
{
  "status": "degraded",
  "documents_dir": "documents",
  "chroma_dir": "database/chroma",
  "ollama_model": "gemma3:4b"
}
```

| Campo | Tipo | Descricao |
|---|---|---|
| `status` | string | `"ok"` (tudo funcionando) ou `"degraded"` (Ollama indisponivel) |
| `documents_dir` | string | Diretorio de documentos configurado |
| `chroma_dir` | string | Diretorio do banco vetorial ChromaDB |
| `ollama_model` | string | Modelo Ollama configurado |

---

### `GET /api/models`

Lista os modelos disponiveis no servidor Ollama.

**Response (200):**
```json
{
  "models": ["gemma3:4b", "llama3.2:3b"]
}
```

Em caso de falha de conexao com Ollama, retorna apenas o modelo configurado como fallback.

---

### `POST /api/chat`

Endpoint principal de perguntas e respostas. **Consulta apenas documentos indexados (RAG).**

**Body:**
```json
{
  "question": "Como corrigir o erro E123 na impressora E52645?",
  "history": [
    {"role": "user", "content": "Qual o total de clientes?"},
    {"role": "assistant", "content": "Temos 15 clientes ativos."}
  ],
  "mode": "auto"
}
```

| Campo | Tipo | Obrigatorio | Descricao |
|---|---|---|---|
| `question` | string | sim | Pergunta em linguagem natural |
| `history` | array | nao | Historico da conversa para contexto |
| `mode` | string | nao | Modo de consulta: `"auto"` ou `"rag"` (ambos usam RAG sobre documentos). Padrao: `"auto"` |

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
    "verdict": "consistent"
  }
}
```

| Campo | Tipo | Descricao |
|---|---|---|
| `success` | bool | `true` para respostas bem-sucedidas |
| `answer` | string | Texto da resposta gerada |
| `confidence` | float | Nivel de confianca (0.0 a 1.0) |
| `sources` | array | Lista de documentos utilizados como fonte (com metadata rica) |
| `metadata` | object | Metadados da execucao (vide modelo `ChatMetadata`) |

**Campos ricos de cada `source`:**
| Campo | Tipo | Descricao |
|---|---|---|
| `title` | string | Nome do documento/fonte |
| `url` | string | URL (vazio para documentos internos) |
| `provider` | string | Sempre `"rag"` |
| `page` | integer/null | Numero da pagina onde o trecho foi encontrado |
| `section` | string | Secao do documento (headings) |
| `manufacturer` | string | Fabricante inferido (ex.: `HP`) |
| `model` | string | Modelo do equipamento (ex.: `E52645`) |
| `error_codes` | array | Codigos de erro detectados no trecho (ex.: `["E123"]`) |

**Response (500 - Erro interno):**
```json
{
  "success": false,
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "O servico nao respondeu"
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

Envia uma pergunta e recebe a resposta token por token em tempo real. **Cada token é enviado como JSON** (`{"content": ...}`) para preservar newlines, espaços e formatação markdown.

**Body** (mesmo formato do `/api/chat`):
```json
{
  "question": "Quais servidores estao cadastrados?"
}
```

**Response:** Stream de eventos SSE no formato:
```
data: {"content": "Para desatolar"}
data: {"content": " papel preso, siga:"}
data: {"content": "\\n\\n1. Abra a porta frontal."}
data: [DONE]
data: {"confidence": 0.94, "sources": [...], "metadata": {...}}
```

Sequencia de eventos:
1. `data: {"content": "<token>"}\n\n` — cada token da resposta (JSON preserva quebras de linha)
2. `data: [DONE]\n\n` — fim do texto da resposta
3. `data: <JSON>\n\n` — metadados finais (confidence, sources ricas, metadata)

> **Nota:** Eventos de validacao interna **nao** sao expostos no stream.

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
    const payload = JSON.parse(line.slice(6)); // {"content": "..."} ou {"done":..., "metadata":...}
    // payload.content = token acumulado; payload.metadata = metadados finais
  }
}
```

**Erros:**
| Status | Significado |
|---|---|
| 400 | Pergunta vazia ou invalida |
| 503 | Chatbot nao inicializado |

---

### `POST /api/index`

Indexa documentos de forma **incremental** (por hash e versões de parser/chunking/embedding). Apenas arquivos novos ou alterados sao processados.

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

Indexa apenas documentos (PDF, DOCX, TXT, MD, CSV, XLSX, imagens) do diretorio configurado, com **OCR seletivo** (Tesseract apenas em páginas sem texto nativo).

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

Remove todos os documentos e limpa o banco vetorial ChromaDB **e o manifesto de indexação**.

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

Remove apenas o banco vetorial ChromaDB e o manifesto. Os arquivos de documentos permanecem no diretorio.

---

## Headers de Resposta

| Header | Descricao |
|---|---|
| `X-Request-ID` | ID unico de cada requisicao para tracing e correlacao de logs |

---

## Seguranca

- **CORS**: Habilitado para todas origens (configuravel)

---

## Modelos de Dados

### ChatRequest
```json
{
  "question": "string (obrigatorio)",
  "history": [
    {"role": "user|assistant", "content": "string"}
  ],
  "mode": "auto|rag (opcional, padrao: auto)"
}
```

### ChatSuccessResponse (v3.0.0)
```json
{
  "success": true,
  "answer": "string",
  "confidence": 0.0 a 1.0,
  "sources": [
    {
      "title": "string",
      "url": "string (vazio para docs internos)",
      "provider": "string (sempre 'rag')",
      "page": "integer|null",
      "section": "string",
      "manufacturer": "string",
      "model": "string",
      "error_codes": ["string"]
    }
  ],
  "metadata": {
    "provider": "string (sempre 'rag')",
    "evidence_count": "integer",
    "execution_time_ms": "integer",
    "verdict": "string (consistent|partial|inconsistent|unknown)",
    "issues": ["string (opcional)"]
  }
}
```

### ChatErrorResponse (v3.0.0)
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
  "provider": "string (opcional)",
  "page": "integer|null",
  "section": "string",
  "manufacturer": "string",
  "model": "string",
  "error_codes": ["string"]
}
```

### ChatMetadata
```json
{
  "provider": "string (sempre 'rag')",
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
  "total_chunks": "integer"
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

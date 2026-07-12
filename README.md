# Watson — Agente RAG Local

Sistema de **Retrieval-Augmented Generation (RAG)** que indexa documentos (PDF, DOCX, TXT, imagens) e dados de banco MySQL em vetores, permitindo perguntas em linguagem natural com respostas geradas por LLM local via **Ollama**.

Oferece **dois modos de operação**:
- **Terminal interativo** (`app.py`) — para testes rápidos e uso direto
- **API REST** (`api.py`) — para integração com sistemas externos

---

## Sumário

- [Arquitetura](#arquitetura)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Modos de Operação](#modos-de-operação)
  - [Modo Terminal (app.py)](#1-modo-terminal-apppy)
  - [Modo API (api.py)](#2-modo-api-apipy)
  - [Indexação via CLI (index.py)](#3-indexação-via-cli-indexpy)
- [API Endpoints](#api-endpoints)
- [Testando o Watson](#testando-o-watson)
  - [Teste via Terminal](#teste-via-terminal)
  - [Teste via API](#teste-via-api)
- [Integração com Sistemas Externos](#integração-com-sistemas-externos)
  - [Python](#python)
  - [Node.js](#nodejs)
  - [PHP / Laravel](#php--laravel)
  - [cURL](#curl)
  - [Agendamento (cron)](#agendamento-cron)
- [Indexação de Banco de Dados](#indexação-de-banco-de-dados)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Testes](#testes)

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                        Watson (RAG)                             │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────────┐  │
│  │  Documentos   │   │   MySQL DB   │   │  Upload de Arquivo │  │
│  │  (PDF/DOCX/   │   │  (tabelas)   │   │  POST /upload     │  │
│  │   TXT/MD/IMG) │   │              │   │                    │  │
│  └──────┬───────┘   └──────┬───────┘   └────────┬───────────┘  │
│         │                  │                     │              │
│         ▼                  ▼                     ▼              │
│  ┌─────────────────────────────────────────────────────┐       │
│  │                   Indexador                         │       │
│  │  Loader → Splitter (chunks) → Embeddings → ChromaDB │       │
│  │  (SHA-256 cache para reindexação incremental)       │       │
│  └──────────────────────┬──────────────────────────────┘       │
│                         │                                      │
│                         ▼                                      │
│  ┌─────────────────────────────────────────────────────┐       │
│  │                   Consulta (RAG)                     │       │
│  │  Pergunta → Embedding → ChromaDB (top-k)            │       │
│  │                     → Prompt Builder                 │       │
│  │                     → Ollama (LLM local)             │       │
│  │                     → Resposta                       │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                 │
│  ┌─────────────────┐              ┌─────────────────────────┐   │
│  │  app.py (CLI)   │              │  api.py (FastAPI :8000) │   │
│  │  Terminal chat   │              │  REST + Swagger /docs  │   │
│  └─────────────────┘              └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │                                    ▲
         │                                    │ HTTP/JSON
         ▼                                    │
  ┌─────────────────┐            ┌──────────────────────────┐
  │  Usuário local  │            │  Sistemas Externos       │
  │  (testes)       │            │  (Python, PHP, Node,     │
  └─────────────────┘            │   Go, Java, etc.)        │
                                 └──────────────────────────┘
```

### Fluxo de Indexação

```
Documento/MySQL → Loader → Splitter (chunks de N caracteres)
                         → Embeddings (all-MiniLM-L6-v2)
                         → ChromaDB (persistente em disco)
                         → index_control.json (cache SHA-256)
```

### Fluxo de Consulta (por pergunta)

```
Pergunta → Embedding → Busca por similaridade no ChromaDB
                     → Top-K chunks mais relevantes
                     → PromptBuilder (system + contexto + pergunta)
                     → Ollama (LLM local)
                     → Resposta em linguagem natural
```

---

## Instalação

### 1. Instalar Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:8b        # ou outro modelo de sua preferência
ollama serve                # inicia o servidor Ollama
```

### 2. Ambiente Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Tesseract OCR (para imagens e PDFs escaneados)

```bash
sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-eng
```

### 4. Verificar instalação

```bash
python -c "from llm.ollama_client import OllamaClient; c = OllamaClient(); print(c.list_models())"
```

---

## Configuração

Todas as configurações são centralizadas em `config.py` e podem ser sobrescritas via **variáveis de ambiente** ou arquivo **`.env`**.

### Arquivo `.env` (recomendado)

Copie o arquivo de exemplo e ajuste:

```bash
cp .env.example .env
```

### Tabela de Configurações

| Variável | Padrão | Descrição |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL do servidor Ollama |
| `OLLAMA_MODEL` | `qwen3:8b` | Modelo LLM para respostas |
| `OLLAMA_TIMEOUT` | `120` | Timeout em segundos para chamadas ao Ollama |
| `TEMPERATURE` | `0.1` | Temperatura do modelo (0.0 = determinístico, 1.0 = criativo) |
| `MAX_TOKENS` | `2048` | Máximo de tokens por resposta |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Modelo de embeddings (sentence-transformers) |
| `CHUNK_SIZE` | `1000` | Tamanho de cada chunk em caracteres |
| `CHUNK_OVERLAP` | `200` | Sobreposição entre chunks consecutivos |
| `TOP_K` | `5` | Número de chunks recuperados por consulta |
| `INDEX_BATCH_SIZE` | `100` | Lote de chunks para inserção no ChromaDB |
| `DOCUMENTS_DIR` | `documents` | Diretório para documentos a serem indexados |
| `VECTOR_DB_DIR` | `database/chroma` | Diretório do banco vetorial ChromaDB |
| `LOG_LEVEL` | `INFO` | Nível de logging (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FILE` | `logs/ai_agent.log` | Caminho do arquivo de log |
| `API_HOST` | `0.0.0.0` | Host do servidor API |
| `API_PORT` | `8000` | Porta do servidor API |
| `DB_CONNECTION_STRING` | — | String de conexão MySQL (`mysql+pymysql://user:pass@host:3306/db`) |
| `DB_TABLES` | — | Lista JSON de tabelas para indexar (`["licenses","clients"]`) |

---

## Modos de Operação

### 1. Modo Terminal (`app.py`)

Ideal para testes rápidos e uso interativo. Conecta direto no ChromaDB e Ollama, sem servidor HTTP.

```bash
python app.py
```

Comportamento:
- Abre um prompt interativo `> ` para digitar perguntas
- Faz **streaming** da resposta (token por token, igual ChatGPT)
- Histórico de conversa NÃO é mantido entre perguntas
- Comandos especiais: `exit` ou `quit` para sair

### 2. Modo API (`api.py`)

Servidor REST FastAPI para integração com sistemas externos.

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Com reload automático (desenvolvimento):

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Acesso à documentação interativa:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 3. Indexação via CLI (`index.py`)

Indexa apenas documentos do diretório configurado, sem iniciar servidor ou chat.

```bash
python index.py
```

Útil para scripts e cron jobs que precisam apenas manter o índice atualizado.

---

## API Endpoints

### `GET /api/health`

Verifica se a API está operacional.

**Resposta:**
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

Lista os modelos disponíveis no servidor Ollama.

**Resposta:**
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
  "question": "Quantas licenças estão prestes a expirar?",
  "history": [
    {"role": "user", "content": "Qual o total de clientes?"},
    {"role": "assistant", "content": "Temos 15 clientes ativos."}
  ],
  "model": "qwen3:8b"
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `question` | string | sim | Pergunta em linguagem natural |
| `history` | array | não | Histórico da conversa para contexto |
| `model` | string | não | Modelo Ollama (usa o padrão da config se omitido) |

**Resposta:**
```json
{
  "answer": "Existem 3 licenças que expiram nos próximos 30 dias: Empresa A (15/08/2026), Empresa B (22/08/2026) e Empresa C (05/09/2026)."
}
```

**Erros:**
| Status | Significado |
|---|---|
| 400 | Pergunta vazia ou inválida |
| 503 | Chatbot não inicializado |
| 500 | Erro interno (LLM, ChromaDB, etc.) |

---

### `POST /api/index`

Indexa **documentos** e **banco de dados** simultaneamente. Apenas arquivos novos ou modificados desde a última indexação são processados.

**Resposta:**
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

Indexa **apenas documentos** (PDF, DOCX, TXT, MD, imagens) do diretório configurado.

---

### `POST /api/index/database`

Indexa **apenas o banco de dados MySQL**. Requer `DB_CONNECTION_STRING` configurado.

---

### `POST /api/documents/upload`

Faz upload de um arquivo para o diretório de documentos. Após o upload, execute `/api/index/documents` para indexá-lo.

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@contrato.pdf"
```

**Resposta:**
```json
{
  "status": "ok",
  "filename": "contrato.pdf",
  "size": 102400
}
```

---

### `POST /api/clear`

Remove **todos** os documentos e limpa o banco vetorial ChromaDB.

**Resposta:**
```json
{
  "status": "ok",
  "documents_removed": 5,
  "vectorstore_files_removed": 42
}
```

---

### `POST /api/clear/documents`

Remove **apenas os arquivos de documentos** do diretório. O banco vetorial permanece intacto (chunks órfãos).

---

### `POST /api/clear/vectorstore`

Remove **apenas o banco vetorial ChromaDB**. Os arquivos de documentos permanecem no diretório.

---

## Testando o Watson

### Teste via Terminal

O modo mais rápido para validar se o LLM está funcionando:

```bash
# 1. Ative o ambiente virtual
source .venv/bin/activate

# 2. Certifique-se de que o Ollama está rodando
ollama list

# 3. Execute o chat interativo
python app.py
```

Exemplo de sessão:

```
=== Agente RAG Local ===
Digite 'exit' ou 'quit' para sair.

> Quem é você?
(streaming da resposta...)

> Quais documentos estão indexados?
(streaming da resposta...)

> exit
```

Se o banco vetorial estiver vazio (nunca indexou nada), as respostas indicarão que não há contexto disponível — isso é esperado. Indexe primeiro:

```bash
# Indexar documentos
python index.py

# Ou via API (com servidor rodando)
curl -X POST http://localhost:8000/api/index/documents
```

### Teste via API

Com o servidor rodando (`uvicorn api:app --host 0.0.0.0 --port 8000`):

```bash
# 1. Health check
curl http://localhost:8000/api/health

# 2. Listar modelos disponíveis
curl http://localhost:8000/api/models

# 3. Indexar documentos
curl -X POST http://localhost:8000/api/index/documents

# 4. Indexar banco de dados (se configurado)
curl -X POST http://localhost:8000/api/index/database

# 5. Indexar tudo
curl -X POST http://localhost:8000/api/index

# 6. Fazer uma pergunta
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Quantas licenças ativas existem?"}'

# 7. Perguntar com histórico
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "E quantas estão bloqueadas?",
    "history": [
      {"role": "user", "content": "Quantas licenças ativas existem?"},
      {"role": "assistant", "content": "Existem 12 licenças ativas."}
    ]
  }'

# 8. Upload de documento
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@documentos/manual.pdf"

# 9. Limpar tudo
curl -X POST http://localhost:8000/api/clear
```

Para formatar a resposta como JSON legível:

```bash
curl -s http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Qual o total de clientes?"}' \
  | python -m json.tool
```

Acesse a documentação interativa no navegador:
- http://localhost:8000/docs (Swagger UI)
- http://localhost:8000/redoc (ReDoc)

---

## Integração com Sistemas Externos

### Python

```python
import requests

API_URL = "http://localhost:8000"

# Health check
health = requests.get(f"{API_URL}/api/health")
print(health.json())

# Fazer pergunta
res = requests.post(f"{API_URL}/api/chat", json={
    "question": "Qual o status do cliente XYZ?",
    "history": [],
})
print(res.json()["answer"])

# Fazer pergunta com histórico
res = requests.post(f"{API_URL}/api/chat", json={
    "question": "E qual o contato dele?",
    "history": [
        {"role": "user", "content": "Qual o status do cliente XYZ?"},
        {"role": "assistant", "content": "O cliente XYZ está ativo."},
    ],
})
print(res.json()["answer"])

# Upload de documento
with open("relatorio.pdf", "rb") as f:
    res = requests.post(f"{API_URL}/api/documents/upload", files={"file": f})
print(res.json())

# Indexar
res = requests.post(f"{API_URL}/api/index")
print(res.json())

# Limpar vetores
res = requests.post(f"{API_URL}/api/clear/vectorstore")
print(res.json())
```

### Node.js

```javascript
const API_URL = 'http://localhost:8000';

// Health check
const health = await fetch(`${API_URL}/api/health`);
console.log(await health.json());

// Fazer pergunta
const res = await fetch(`${API_URL}/api/chat`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ question: 'Quantos clientes estão ativos?' }),
});
const data = await res.json();
console.log(data.answer);

// Upload de documento (com FormData)
const FormData = require('form-data');
const fs = require('fs');
const form = new FormData();
form.append('file', fs.createReadStream('contrato.pdf'));
const uploadRes = await fetch(`${API_URL}/api/documents/upload`, {
  method: 'POST',
  body: form,
});
console.log(await uploadRes.json());
```

### PHP / Laravel

```php
use Illuminate\Support\Facades\Http;

$apiUrl = 'http://localhost:8000';

// Fazer pergunta
$response = Http::post("$apiUrl/api/chat", [
    'question' => 'Quais licenças estão expirando este mês?',
    'history' => [],
]);
$answer = $response->json()['answer'];

// Upload de documento
$response = Http::attach(
    'file', file_get_contents(storage_path('app/contrato.pdf')), 'contrato.pdf'
)->post("$apiUrl/api/documents/upload");

// Indexar
Http::post("$apiUrl/api/index");
```

### cURL

```bash
# Pergunta simples
curl -s http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Qual o total de instalações?"}' \
  | jq .answer

# Upload
curl -s -X POST http://localhost:8000/api/documents/upload \
  -F "file=@documento.pdf" | jq .

# Indexar documents
curl -s -X POST http://localhost:8000/api/index | jq .

# Health check
curl -s http://localhost:8000/api/health | jq .
```

### Agendamento (cron)

Para manter os vetores sempre atualizados:

```bash
# Reindexar documentos e banco a cada hora
0 * * * * curl -X POST http://localhost:8000/api/index

# Reindexar apenas o banco a cada 30 minutos
*/30 * * * * curl -X POST http://localhost:8000/api/index/database

# Reindexar apenas documentos toda madrugada
0 3 * * * curl -X POST http://localhost:8000/api/index/documents

# Indexação via CLI (sem servidor)
0 * * * * cd /caminho/watson && /caminho/.venv/bin/python index.py
```

---

## Indexação de Banco de Dados

O Watson conecta em bancos MySQL e converte **cada linha de cada tabela** em um documento texto que passa por chunking, embeddings e armazenamento no ChromaDB.

### Formato dos documentos gerados

Cada registro do banco vira um documento no formato:

```
[Tabela: licenses]
id: 1
client_id: 5
product: DokViewer
license_key: ABC-123
expires_at: 2026-08-15
status: active
created_at: 2025-08-15T10:00:00
updated_at: 2026-07-01T14:30:00
```

### Colunas sensíveis

Colunas que contenham no nome: `password`, `senha`, `secret`, `token`, `recovery_codes`, `two_factor` ou `remember_token` são **automaticamente excluídas** da indexação.

### Detecção de mudanças incrementais

- O Watson calcula hash SHA-256 do conteúdo de cada registro
- Na reindexação, apenas registros com conteúdo diferente são reprocessados
- Registros que não existem mais são removidos do índice vetorial
- O cache fica em `database/chroma/index_control.json`

### Exemplos de perguntas que o RAG consegue responder

| Pergunta | Origem dos dados |
|---|---|
| "Quantas licenças estão prestes a expirar?" | Tabela `licenses` |
| "Qual cliente tem mais instalações?" | Tabelas `clients` + `installations` |
| "Liste as licenças bloqueadas" | Tabela `licenses` |
| "Quem renovou este mês?" | Tabela `license_renewal_history` |
| "Mostre dados do contrato da Empresa X" | Documento PDF em `documents/` |
| "O que diz a cláusula 5 do contrato?" | Documento DOCX em `documents/` |

### Limitações importantes

- A indexação do banco **não altera os dados originais** — apenas copia o conteúdo para vetores
- Consultas como "quantas licenças" funcionam por **similaridade semântica**, não por SQL direto
- Para dados críticos, a resposta do LLM deve ser verificada com a fonte original
- O Watson não faz agregações numéricas precisas (somas, médias) — use o banco original para isso

---

## Estrutura do Projeto

```
Watson/
├── api.py                  # Servidor FastAPI (modo API)
├── app.py                  # Chat interativo via terminal (modo CLI)
├── index.py                # Indexação via linha de comando
├── config.py               # Configurações centralizadas (dataclass + .env)
├── requirements.txt        # Dependências Python
├── .env.example            # Exemplo de configuração
├── .gitignore              # Arquivos ignorados pelo Git
├── README.md               # Documentação
│
├── ingestion/              # Pipeline de indexação
│   ├── loader.py           # Leitura de PDF, DOCX, TXT, MD, imagens (com OCR)
│   ├── db_loader.py        # Leitura de banco MySQL (com filtro de colunas sensíveis)
│   ├── splitter.py         # Chunking de texto (RecursiveCharacterTextSplitter)
│   ├── embeddings.py       # Geração de embeddings (HuggingFace)
│   └── indexer.py          # Indexação no ChromaDB com cache SHA-256
│
├── rag/                    # Pipeline de consulta
│   ├── retriever.py        # Busca vetorial por similaridade (top-k)
│   ├── prompt.py           # Construção de prompts com system prompt + contexto
│   └── chatbot.py          # Orquestração RAG + loop de chat
│
├── llm/                    # Integração com modelo de linguagem
│   └── ollama_client.py    # Cliente Ollama (generate, streaming, list models)
│
├── utils/                  # Utilitários
│   └── logger.py           # Logging em arquivo + console
│
├── tests/                  # Testes unitários (pytest)
│   ├── conftest.py
│   ├── test_chatbot.py
│   ├── test_embeddings.py
│   ├── test_indexer.py
│   ├── test_loader.py
│   ├── test_retriever.py
│   └── test_splitter.py
│
├── documents/              # Documentos para indexar (PDF, DOCX, etc.)
├── database/chroma/        # Banco vetorial ChromaDB (persistente)
└── logs/                   # Logs da aplicação
```

---

## Testes

```bash
# Executar todos os testes
pytest tests/ -v

# Executar com cobertura
pytest tests/ -v --cov=. --cov-report=term-missing

# Executar um teste específico
pytest tests/test_chatbot.py -v

# Executar testes com output detalhado
pytest tests/ -v --tb=long
```

# Watson — Agente RAG Local

Sistema de **Retrieval-Augmented Generation (RAG)** que indexa documentos (PDF, DOCX, TXT, imagens), arquivos do Google Drive e dados de banco MySQL em vetores (ChromaDB), permitindo perguntas em linguagem natural com respostas geradas por LLM local via **Ollama**.

A interface web fica no **DokViewerManager** (Laravel), que consome a API do Watson.

---

## Requisitos

- Python 3.10+
- [Ollama](https://ollama.com) com modelo LLM baixado (ex.: `ollama pull qwen3:8b`)
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (opcional, para PDFs escaneados)
- MySQL (opcional, para indexação de banco)

## Início rápido

**Windows:** rode `start.bat` — ele executa o `setup.bat` automaticamente (cria o venv `.venv`, instala dependências e gera o `.env` a partir do exemplo) e abre o menu de operações.

**Linux/macOS:** rode `./start.sh` — ele executa o `setup.sh` automaticamente (cria o venv `.venv`, instala dependências e gera o `.env`) e abre o mesmo menu.

Para configurar manualmente:

```bash
# 1. Ambiente Python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configurar
cp .env.example .env   # edite com suas credenciais

# 3. Executar (use o inicializador ou direto)
python app.py                              # chat no terminal
uvicorn api:app --host 0.0.0.0 --port 9000 # API REST
```

Documentação interativa da API: http://localhost:9000/docs

---

## Menu do inicializador (start.bat / start.sh)

| Opção | Comando | Descrição |
|---|---|---|
| 1. API | `uvicorn api:app` | Servidor FastAPI (http://0.0.0.0:9000) |
| 2. Prompt | `python app.py` | Chat interativo no terminal |
| 3. Index | `python index.py` | Indexa `documents/` + banco (sem Drive) |
| 4. Drive + Index | `python drive_index.py` | Sincroniza Drive e indexa tudo |
| 5. Drive Sync | `python drive_index.py --sync-only` | Só baixa os arquivos do Drive |
| 6. Seleção Drive | `python drive_select.py` | Escolhe pastas do Drive a indexar |
| 7. Reset Total | `python reset_app.py --yes` | Apaga vetores e `documents/` |
| 8. Watcher | `python watch.py` | Reindexa automaticamente ao detectar mudanças |

> **Drive público**: o Google Drive da "AREA TECNICA" é público (sem OAuth). O Watson lista as pastas via `embeddedfolderview` e baixa os arquivos por `uc?export=download`. A seleção de pastas fica em `.drive_selection.json` e é compartilhada com a API (`/api/drive/selection`).

---

## Configuração (.env)

Copie `.env.example` para `.env` e ajuste. Principais variáveis:

| Variável | Padrão | Descrição |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL do Ollama |
| `OLLAMA_MODEL` | `qwen3:8b` | Modelo de geração |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-base` | Modelo de embeddings |
| `DB_CONNECTION_STRING` | — | Conexão MySQL (`mysql+pymysql://user:senha%40encoded@host/db`) |
| `GOOGLE_DRIVE_FOLDER_ID` | — | ID da pasta raiz do Drive público |
| `GOOGLE_DRIVE_DEST_DIR` | `documents/drive` | Onde os arquivos do Drive são salvos |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `9000` | Bind da API |
| `API_AUTH_TOKEN` | vazio | **Token de auth da API** (ver abaixo) |
| `OCR_*` | — | Configuração de OCR (Tesseract) |

> **Senhas com caracteres especiais**: use URL-encoding (ex.: `@` vira `%40`). Veja `docs/configuration.md`.

### Autenticação da API (opcional)

A API expõe endpoints de escrita (`/api/index`, `/api/clear`, `/api/documents/upload`, `/api/chat`) na rede. Para proteger, defina um token:

```env
API_AUTH_TOKEN=qualquer-texto-longo-e-aleatorio
```

Toda chamada a `/api/*` (exceto `/api/health`) passa a exigir o header:

```bash
curl -H "X-API-Token: SEU_TOKEN" http://localhost:9000/api/models
# ou
curl -H "Authorization: Bearer SEU_TOKEN" http://localhost:9000/api/models
```

Se `API_AUTH_TOKEN` estiver vazio, a autenticação fica desativada (apenas para dev local).

---

## Modo voz (terminal / "2. Prompt")

O chat interativo pode capturar suas perguntas via microfone (Whisper local) e
responder **falando** com uma voz neural humana (edge-tts, ex: `pt-BR-FranciscaNeural`).

```bash
pip install faster-whisper sounddevice edge-tts miniaudio
```

Depois habilite no `.env`:

```env
VOICE_ENABLED=true
VOICE_STT_MODEL=base      # quanto maior, melhor (tiny/base/small/medium/large-v3)
VOICE_LANGUAGE=pt
VOICE_NAME=pt-BR-FranciscaNeural
```

Ao iniciar `python app.py`, o chat passa a ouvir suas perguntas pelo microfone
(detecta silêncio automaticamente) e fala as respostas. Diga "sair" ou
"encerrar" para sair. O pipeline RAG não muda: apenas as pontas (entrada de
áudio / saída de voz) foram adicionadas.

---

## Endpoints da API

| Endpoint | Método | Descrição |
|---|---|---|
| `/api/health` | GET | Status da API + conexão com Ollama (público) |
| `/api/models` | GET | Lista modelos disponíveis no Ollama |
| `/api/chat` | POST | Pergunta/resposta com RAG |
| `/api/chat/stream` | POST | Chat com streaming (SSE) |
| `/api/index/async` | POST | **Indexação em segundo plano** (retorna `job_id`) |
| `/api/index/status/{job_id}` | GET | Status/progresso do job (`progress`, `total`, `message`) |
| `/api/index/cancel/{job_id}` | POST | Cancela um job em andamento |
| `/api/documents/upload` | POST | Upload de arquivo (novo doc → indexado) |
| `/api/drive/folder/{id}` | GET | Lista pastas/arquivos do Drive |
| `/api/drive/selection` | GET/POST | Lê/salva a seleção de pastas do Drive |
| `/api/drive/sync` | POST | Sincroniza Drive (pode demorar) |
| `/api/drive/clear` | POST | Remove arquivos baixados do Drive |
| `/api/clear` | POST | Limpa tudo (docs + vetores) |
| `/api/clear/documents` | POST | Limpa apenas documentos |
| `/api/clear/vectorstore` | POST | Limpa apenas banco vetorial |

### Indexação assíncrona (jobs)

`POST /api/index/async` não bloqueia a requisição — o trabalho roda em thread de fundo:

```bash
curl -X POST http://localhost:9000/api/index/async \
  -H "Content-Type: application/json" \
  -d '{"mode": "all"}'
# → {"status": "started", "job_id": "abc123"}

curl http://localhost:9000/api/index/status/abc123
# → {"status": "running", "progress": 4, "total": 10, "message": "manual.pdf", ...}
```

- `mode`: `all` | `documents` | `database`
- `sync_drive`: `true`/`false` (padrão `false` — a indexação de documentos NÃO sincroniza o Drive por padrão; use o endpoint `/api/drive/sync` ou a opção 4 do menu para isso)
- Se já houver um job rodando, retorna **409 Conflict**.
- `POST /api/index/cancel/{job_id}` solicita cancelamento cooperativo (o status vira `cancelled`).
- Jobs com mais de 1h são descartados automaticamente (prune a cada novo job).

---

## Watcher de documentos

Monitora `documents/` (incluindo `documents/drive`) e reindexa automaticamente quando há arquivos novos, alterados ou removidos:

```bash
python watch.py                 # verifica a cada 30s
python watch.py --interval 60   # intervalo customizado
```

Usa polling leve (tamanho + mtime por arquivo), sem dependências externas. O estado fica em `logs/.watch_state.json`.

---

## Fluxos

```
Indexação:  Documentos/Drive/MySQL → Loader → Splitter → Embeddings → ChromaDB
Consulta:   Pergunta → Embedding → ChromaDB (top-k) → Prompt Builder → Ollama → Resposta
```

---

## Documentação detalhada

| Arquivo | Conteúdo |
|---|---|
| [Instalação](docs/installation.md) | Guia completo (Ollama, Python, Tesseract) |
| [Configuração](docs/configuration.md) | Variáveis de ambiente, URL-encoding em senhas |
| [Referência da API](docs/api-reference.md) | Todos os endpoints com request/response |
| [Indexação de Banco](docs/database-indexing.md) | MySQL, colunas sensíveis, incremental |
| [Integração](docs/integration.md) | Exemplos em Python, Node.js, PHP, cURL, cron |
| [Estrutura do Projeto](docs/project-structure.md) | Arquitetura de pastas e módulos |

---

## Estrutura do projeto

```
Watson/
├── api.py                  # API FastAPI (chat, indexação async, drive, auth)
├── app.py                  # Chat interativo no terminal
├── index.py                # Indexação CLI (documentos locais + banco)
├── drive_index.py          # Sincronização do Drive + indexação
├── drive_select.py         # Seleção de pastas do Drive no terminal
├── watch.py                # Watcher de documentos (reindexação automática)
├── reset_app.py            # Reset total (vetores + documents/)
├── config.py               # Configurações (.env)
├── ingestion/              # Pipeline de indexação (loader, splitter, embeddings, indexer, drive_sync)
├── rag/                    # Pipeline de consulta (retriever, prompt)
├── llm/                    # Integração Ollama
├── tests/                  # Testes unitários
└── docs/                   # Documentação detalhada
```

---

## Testes

```bash
pytest tests/ -q
```

Suíte cobre: API (endpoints, auth, jobs, drive), indexação incremental, embeddings, OCR, splitter, retriever, chat e watcher.

---

## Limpeza e manutenção

```bash
./cleanup.sh   # Linux/macOS
cleanup.bat    # Windows
```

Remove logs antigos, caches de embeddings, `.ruff_cache`, `.mypy_cache`, imagens temporárias e artefatos de testes.
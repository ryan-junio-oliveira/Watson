# Watson -- Agente RAG Local

Sistema de **Retrieval-Augmented Generation (RAG)** que indexa documentos (PDF, DOCX, TXT, imagens) e dados de banco MySQL em vetores, permitindo perguntas em linguagem natural com respostas geradas por LLM local via **Ollama**.

---

## Modos de operacao

| Modo | Comando | Descricao |
|---|---|---|
| **Terminal** | `python app.py` | Chat interativo para testes rapidos |
| **API REST** | `uvicorn api:app --port 9000` | Servidor para integracao com sistemas externos |
| **CLI** | `python index.py` | Indexacao via linha de comando (cron jobs) |

---

## Inicio rapido

```bash
# 1. Instalar Ollama e baixar modelo
ollama pull qwen3:8b

# 2. Ambiente Python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Configurar
cp .env.example .env   # edite com suas credenciais

# 4. Executar
python app.py          # modo terminal
# ou
uvicorn api:app --host 0.0.0.0 --port 9000  # modo API
```

Documentacao interativa da API: http://localhost:9000/docs

---

## Fluxo de indexacao

```
Documentos/MySQL -> Loader -> Splitter (chunks) -> Embeddings -> ChromaDB
```

## Fluxo de consulta

```
Pergunta -> Embedding -> ChromaDB (top-k) -> Prompt Builder -> Ollama -> Resposta
```

---

## Endpoints principais

| Endpoint | Metodo | Descricao |
|---|---|---|
| `/api/health` | GET | Status da API |
| `/api/chat` | POST | Perguntas e respostas com RAG |
| `/api/index` | POST | Indexa documentos + banco |
| `/api/index/documents` | POST | Indexa apenas documentos |
| `/api/index/database` | POST | Indexa apenas banco MySQL |
| `/api/documents/upload` | POST | Upload de arquivo |
| `/api/clear` | POST | Limpa tudo (docs + vetores) |

---

## Documentacao detalhada

| Arquivo | Conteudo |
|---|---|
| [Instalacao](docs/installation.md) | Guia completo de instalacao (Ollama, Python, Tesseract) |
| [Configuracao](docs/configuration.md) | Variaveis de ambiente, URL-encoding em senhas |
| [Referencia da API](docs/api-reference.md) | Todos os endpoints com request/response |
| [Indexacao de Banco](docs/database-indexing.md) | Como indexar MySQL, colunas sensiveis, incrementais |
| [Integracao](docs/integration.md) | Exemplos em Python, Node.js, PHP, cURL, cron |
| [Estrutura do Projeto](docs/project-structure.md) | Arquitetura de pastas e modulos |

---

## Estrutura do projeto

```
Watson/
├── api.py / app.py / index.py   # Entrypoints
├── config.py                     # Configuracoes
├── ingestion/                    # Pipeline de indexacao
├── rag/                          # Pipeline de consulta
├── llm/                          # Integracao Ollama
├── tests/                        # Testes unitarios
└── docs/                         # Documentacao detalhada
```

---

## Testes

```bash
pytest tests/ -v
```

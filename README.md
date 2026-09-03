<div align="center">

# Watson

**Plataforma RAG 100% local — de documentos técnicos a respostas com fontes citadas**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org) [![Ollama](https://img.shields.io/badge/LLM-Ollama-000?logo=ollama)](https://ollama.com) [![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com) [![ChromaDB](https://img.shields.io/badge/Vector-ChromaDB-4B8BBE)](https://www.trychroma.com) [![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[Início rápido](#-início-rápido-5-minutos) · [Documentação](docs/index.md) · [API](http://localhost:9000/docs) · [Configuração](docs/getting-started/configuration.md) · [Perfis Flash / Plus / Pro](#-perfis-watson)

</div>

---

## O que é

O Watson lê seus documentos técnicos — **PDF, DOCX, TXT, CSV, XLSX e imagens com OCR** — e também pastas públicas do **Google Drive**, transforma tudo em vetores semânticos no **ChromaDB** e responde perguntas em linguagem natural usando um **LLM local (Ollama)**. Cada resposta vem com **fontes citadas** (título, seção, página, fabricante, modelo, código de erro) — sem enviar dados para a nuvem.

```
Documentos  →  Loader → Splitter → Embeddings → ChromaDB
Pergunta    →  Retriever → Evidências → Prompt → Ollama → Resposta + Fontes
```

Três interfaces compartilham o mesmo núcleo: **API REST** (FastAPI + SSE streaming), **chat na UI web** (`/`) e **chat no terminal** (`app.py`).

---

## Perfis Watson

Escolha no seletor do chat (`Flash` / `Pro`) ou via `WATSON_PROFILE` / `POST /api/chat { profile }` — igual ao Gemini/ChatGPT. `Plus` foi removido (indistinguível do Flash) e mapeado para `flash`.

| Perfil | Objetivo | Quando usar | Velocidade¹ | Tokens / Chunk |
|---|---|---|---|---|
| **⚡ Flash** `flash` — *default* | Mais rápido | Dia a dia, maioria RAG/web, health-check | ~1s | `2048` tokens · `800`/`150` chunk · `TOP_K=5` · `rewriter 3` · `reasoning 2048` |
| **🧠 Pro** `pro` | Mais inteligente (pensa) | Análise profunda, comparação, percentual, auditoria | ~5–8s | `4096` tokens · `1200`/`250` chunk · `TOP_K=12` · `rewriter 5` · `reasoning 4096` · `qwen3:8b` think |

¹ CPU 8–16 GB com `gemma3:4b`. `Pro` usa `qwen3:8b` se `ANALYST_MODEL` não setado, com fallback para `gemma`. Ver [Configuração — Perfis](docs/getting-started/configuration.md#11-perfis-watson--flash--pro).

---

## Início rápido — 5 minutos

**Pré-requisito:** [Python 3.11](https://python.org) e [Ollama](https://ollama.com) com `ollama pull gemma3:4b` (e `moondream` se usa imagens).

```bash
# 1 — Clonar e rodar (Windows / Linux)
git clone <repo> Watson && cd Watson
# Windows
start.bat
# Linux / macOS
./start.sh

# 2 — Docker (recomendado em produção)
docker compose up -d --build
# Watson em http://localhost:9000  |  Chat http://localhost:9000/  |  SearXNG http://localhost:8080
```

O inicializador cria `.venv`, instala dependências, gera `.env` e abre o menu (API, chat terminal, indexação, Drive). Documentação interativa da API em **http://localhost:9000/docs**.

**Manual (sem inicializador):**

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # edite WATSON_PROFILE, OLLAMA_MODEL, etc
python cli/index.py           # indexa documents/
uvicorn cli.api:app --host 0.0.0.0 --port 9000  # API
python cli/app.py             # chat no terminal
```

> Detalhe passo a passo em [Instalação](docs/getting-started/installation.md) e [Início rápido](docs/getting-started/quickstart.md).

---

## Jornada de leitura — por onde começar

> O Watson tem documentação com **início, meio e fim**. Siga a ordem ou salte para o que precisa.

| # | Se você quer… | Leia | Tempo |
|---|---|---|---|
| 1 | Entender o que o Watson faz | **Este README** + [Arquitetura — Visão geral](docs/architecture/overview.md) | 5 min |
| 2 | Instalar e rodar | [Instalação](docs/getting-started/installation.md) → [Início rápido](docs/getting-started/quickstart.md) | 10 min |
| 3 | Personalizar | [Configuração](docs/getting-started/configuration.md) — todas as 58 vars + perfis Flash/Plus/Pro + `/config` | 8 min |
| 4 | Usar no dia a dia | [Guia de uso](docs/guides/usage.md) — menu, chat, watcher, reset | 5 min |
| 5 | Indexar Drive / imagens | [Google Drive](docs/guides/google-drive.md) · [Ingestão](docs/architecture/ingestion-pipeline.md) | 5 min |
| 6 | Aprofundar respostas | [Modo Analista](docs/guides/analyst-mode.md) — Pro + think + Query Rewriter | 5 min |
| 7 | Integrar via código | [Referência da API](docs/api/api-reference.md) → [Integração](docs/api/integration.md) (Python/Node/PHP/cURL) + `POST /compare` | 10 min |
| 8 | Levar para produção | [Implantação](docs/operations/deployment.md) — Supervisord, serviço Windows, executável | 8 min |
| 9 | Operar com confiança | [Monitoramento](docs/guides/monitoring.md) — dashboard `/dashboard` + métricas | 5 min |
| 10 | Diagnosticar | [Solução de problemas](docs/operations/troubleshooting.md) | 3 min |
| 11 | Contribuir | [Estrutura do projeto](docs/development/project-structure.md) → [Desenvolvimento](docs/development/development.md) → [Testes](docs/development/testing.md) | 10 min |

**Atalhos:** [Índice completo da documentação](docs/index.md) · [Referência da API](docs/api/api-reference.md) · [Configuração — perfis](docs/getting-started/configuration.md#11-perfis-watson--flash--plus--pro)

---

## Documentação

| Área | Onde |
|---|---|
| **Primeiros passos** | [Instalação](docs/getting-started/installation.md) · [Início rápido](docs/getting-started/quickstart.md) · [Configuração](docs/getting-started/configuration.md) |
| **Conceitos** | [Arquitetura](docs/architecture/overview.md) · [Ingestão](docs/architecture/ingestion-pipeline.md) · [RAG](docs/architecture/rag-pipeline.md) |
| **Uso** | [Guia de uso](docs/guides/usage.md) · [Drive](docs/guides/google-drive.md) · [Analista](docs/guides/analyst-mode.md) · [Monitoramento](docs/guides/monitoring.md) |
| **API** | [Referência](docs/api/api-reference.md) · [Integração](docs/api/integration.md) · Swagger `http://localhost:9000/docs` |
| **Operação** | [Implantação](docs/operations/deployment.md) · [Troubleshooting](docs/operations/troubleshooting.md) |
| **Desenvolvimento** | [Estrutura](docs/development/project-structure.md) · [Dev](docs/development/development.md) · [Testes](docs/development/testing.md) |

---

## Interfaces

| Interface | Comando / URL | Para quem |
|---|---|---|
| **Chat web** | `http://localhost:9000/` — seletor Flash/Plus/Pro, streaming SSE, fontes com chips | Usuário final |
| **Comparar modelos** | `http://localhost:9000/compare` — mesma pergunta em Flash vs Plus vs Pro lado a lado | Avaliação |
| **Configuração** | `http://localhost:9000/config` — edita `.env` por sessões (Ollama/RAG/Web Search/Sistema) | Admin |
| **Dashboard** | `http://localhost:9000/dashboard` — tokens, latência, documentos | Operação |
| **API** | `http://localhost:9000/docs` — Swagger | Integração |
| **Terminal** | `python cli/app.py` — `analisar:` / `aprofundar:` | Dev / suporte |

---

## Stack

`Python 3.11` · `Ollama (gemma3:4b / qwen3:8b / moondream)` · `ChromaDB` · `FastAPI + SSE` · `SentenceTransformers (e5-base)` · `Tesseract OCR` · `SearXNG / DuckDuckGo / Google` (web search) · `SQLite` (métricas)

---

## Testes e licença

```bash
pytest tests/ -q   # 300+ testes: API, ingestão, retriever, analyst, métricas
```

Licença **MIT** — veja `LICENSE`. Dúvidas operacionais em [Solução de problemas](docs/operations/troubleshooting.md) e na própria API em `/docs`.

---

<p align="center"><i>Comece por <a href="docs/getting-started/quickstart.md">Início rápido</a> → depois <a href="docs/getting-started/configuration.md">Configuração</a> (perfis) → <a href="docs/guides/usage.md">Guia de uso</a>. Quando estiver pronto para integrar, vá para <a href="docs/api/integration.md">Integração</a>.</i></p>

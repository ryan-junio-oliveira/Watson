<div align="center">

# 🤖 Watson RAG

**Agente de IA de Retrieval-Augmented Generation (RAG) 100% local para documentos técnicos**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-000000?logo=ollama)](https://ollama.com)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![ChromaDB](https://img.shields.io/badge/Vector-ChromaDB-4B8BBE)](https://www.trychroma.com)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Indexa** PDFs, DOCX, planilhas, imagens e arquivos do Google Drive em vetores; **entende** perguntas em linguagem natural e **responde** com fontes citadas — tudo processado localmente, sem enviar dados para a nuvem.

</div>

---

## ✨ Destaques

- **100% local** — LLM (Ollama), embeddings e banco vetorial (ChromaDB) rodam na sua máquina. Nenhum dado sai do ambiente.
- **RAG com fontes citadas** — cada resposta referencia seção, página, fabricante e modelo dos documentos.
- **Indexação incremental** — reindexa apenas arquivos novos ou alterados (hash + versões de parser/chunking/embedding).
- **OCR embutido** — Tesseract aplicado seletivamente apenas em páginas/ imagens sem texto nativo.
- **Google Drive (público, sem OAuth)** — sincroniza pastas públicas e indexa automaticamente.
- **Modo Analista** — análise proativa sob demanda: conclusões, perguntas de acompanhamento e busca adicional no acervo.
- **Cálculo verificado** — a camada de cálculo determinística resolve percentuais/somas/médias sem depender de aritmética do LLM.
- **Dashboard de métricas** — acompanhe uso de tokens, chamadas de LLM, documentos e histórico em uma UI web.
- **Múltiplas interfaces** — API REST (FastAPI), streaming SSE, chat no terminal e watcher de reindexação.
- **Multi-plataforma** — scripts para Windows e Linux/macOS, incluindo serviço Windows e gerenciamento por supervisord.

---

## 🚀 Início rápido

> Pré-requisito: [Python 3.10+](https://python.org) e [Ollama](https://ollama.com) rodando com um modelo baixado (ex.: `ollama pull gemma3:4b`).

**Windows:**

```bat
start.bat
```

**Linux / macOS:**

```bash
./start.sh
```

O inicializador cria o ambiente (`.venv`), instala dependências, gera o `.env` e abre o menu de operações (API, chat, indexação, Drive, etc.).

Documentação interativa da API: <http://localhost:9000/docs>

### Instalação manual

```bash
# 1. Ambiente Python
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configurar
cp .env.example .env             # edite com suas credenciais

# 3. Executar
python app.py                    # chat no terminal
uvicorn api:app --host 0.0.0.0 --port 9000   # API REST
```

---

## 📚 Documentação

| Área | Conteúdo |
|---|---|
| **[Início](docs/index.md)** | Página principal da documentação e guia de navegação |
| **[Instalação](docs/getting-started/installation.md)** | Guia completo — Ollama, Python, Tesseract |
| **[Início rápido](docs/getting-started/quickstart.md)** | Primeira indexação e primeira pergunta |
| **[Configuração](docs/getting-started/configuration.md)** | Todas as variáveis de ambiente e defaults |
| **[Arquitetura](docs/architecture/overview.md)** | Visão geral do sistema e fluxo de dados |
| **[Guia de Uso](docs/guides/usage.md)** | Menu do inicializador, chat, watcher, reset |
| **[Google Drive](docs/guides/google-drive.md)** | Sincronização de pastas públicas |
| **[Modo Analista](docs/guides/analyst-mode.md)** | Análise proativa e raciocínio |
| **[Monitoramento](docs/guides/monitoring.md)** | Dashboard de métricas e logs |
| **[Referência da API](docs/api/api-reference.md)** | Todos os endpoints, modelos e erros |
| **[Integração](docs/api/integration.md)** | Exemplos em Python, Node.js, PHP e cURL |
| **[Implantação](docs/operations/deployment.md)** | Supervisord, serviço Windows, build executável |
| **[Solução de problemas](docs/operations/troubleshooting.md)** | Guia de diagnóstico e correções |
| **[Estrutura do Projeto](docs/development/project-structure.md)** | Arquitetura de pastas e módulos |
| **[Desenvolvimento](docs/development/development.md)** | Contribuindo e boas práticas |
| **[Testes](docs/development/testing.md)** | Como rodar e estender a suíte |

---

## 🗺️ Visão geral do fluxo

```
Indexação:  Documentos/Drive → Loader → Splitter → Quality/Dedup → Embeddings → ChromaDB
Consulta:   Pergunta → Retriever (top-k) → Evidências → Prompt Builder → Ollama → Resposta + Fontes
```

Saiba mais em [Arquitetura](docs/architecture/overview.md).

---

## 📦 Componentes principais

| Componente | Descrição |
|---|---|
| `api.py` | API REST FastAPI (chat, indexação assíncrona, Drive, métricas) |
| `app.py` | Chat interativo no terminal |
| `index.py` | Indexação de documentos locais (CLI) |
| `drive_index.py` / `drive_select.py` | Sincronização e seleção de pastas do Drive |
| `watch.py` | Watcher — reindexa automaticamente ao detectar mudanças |
| `reset_app.py` | Reset total do índice e documentos |
| `ingestion/` | Pipeline de indexação (adapters, loader, splitter, embeddings, indexer) |
| `rag/` | Pipeline de consulta (retriever, chatbot, analyst, calculator) |
| `llm/` | Cliente Ollama (geração e streaming) |
| `metrics/` | Armazenamento de métricas (SQLite) + dashboard |
| `presentation/` | Dashboard web e formatação de saída |

---

## 🧪 Testes

```bash
pytest tests/ -q
```

Suíte com mais de 300 testes cobrindo API, indexação incremental, embeddings, OCR, splitter, retriever, chat, analista, métricas e watcher.

---

## 📄 Licença

Este projeto é distribuído sob a licença **MIT**.

---

*Documentação detalhada disponível em [`docs/`](docs/index.md).*

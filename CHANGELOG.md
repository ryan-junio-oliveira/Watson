# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/spec/v2.0.0.html).

---

## [v1.0.0] — 2026-08-21

Primeira versão estável do **Watson RAG** — um agente de IA de Retrieval-Augmented
Generation (RAG) 100% local para consulta de documentos técnicos (PDF, DOCX,
planilhas, imagens e arquivos do Google Drive).

### 🤖 Assistente de IA (Watson / RAG)

- **RAG-only:** consulta exclusivamente documentos indexados, sem pesquisa na
  internet nem conhecimento próprio do modelo. Diagnósticos internos nunca são
  expostos nas respostas.
- **Fontes citadas:** cada resposta referencia seção, página, fabricante, modelo
  e códigos de erro dos documentos utilizados.
- **Streaming (SSE):** resposta token a token via `POST /api/chat/stream`, com
  tokens enviados como JSON para preservar newlines e formatação markdown.
- **Detecção inteligente de contexto:** o `top_k` se ajusta dinamicamente —
  padrão para perguntas simples, `top_k × 2` para perguntas analíticas e
  `top_k × 4` + expansão por documento apenas em pedidos explícitos de
  completude (`todos`, `completo`, `mais informações`).
- **Cálculo verificado:** camada determinística (`rag/calculator.py`) resolve
  percentuais, somas, médias, máximos e mínimos sem depender da aritmética do
  LLM, reduzindo alucinações numéricas.
- **Modo Analista (análise proativa):** sob demanda, gera conclusões, perguntas
  de acompanhamento e busca informação adicional no acervo (`analyze=true`).

### 🖥️ Pipeline de Indexação

- **Adaptadores de fonte:** PDF (com OCR seletivo), DOCX, CSV, XLSX, TXT/Markdown
  e Imagens (OCR + análise por modelo de visão opcional).
- **Chunking semântico:** blocos por cabeçalho/tabela/texto por tipo de fonte,
  com metadados ricos (seção, página, códigos de erro).
- **Indexação incremental:** reindexa apenas arquivos novos ou alterados
  (hash de conteúdo + versões de parser/chunking/embedding).
- **Portão de qualidade e deduplicação:** rejeita chunks de baixa qualidade e
  elimina duplicatas intra-documento.
- **Cache de embeddings** persistente (SQLite) e **manifesto de indexação**
  com escrita atômica.

### 📁 Google Drive (pasta pública)

- **Sincronização sem OAuth:** pasta pública via `embeddedfolderview` + download
  por `uc?export=download`.
- **Seleção de pastas:** navegação e marcação de pastas a indexar, persistida em
  `.drive_selection.json` e compartilhada com a API.
- **Sincronização incremental** com manifesto local e download paralelo.

### 🔌 API REST (FastAPI)

- **Endpoints de chat** (`/api/chat`) e streaming (`/api/chat/stream`).
- **Indexação assíncrona** em segundo plano com `job_id`, polling de status e
  cancelamento cooperativo (`/api/index/async`, `/api/index/status/{id}`,
  `/api/index/cancel/{id}`).
- **Endpoints de Drive** (listagem, seleção, sync, limpeza).
- **Upload de documentos** (máx. 50 MB).
- **Limpeza** granular (documentos, vectorstore ou ambos).
- **Autenticação por token** (`X-API-Token` / `Authorization: Bearer`).
- **Métricas:** endpoints de summary, tokens, requisições, modelos, chamadas de
  LLM, documentos e eventos de indexação.

### 📊 Dashboard e Métricas

- **MetricsStore (SQLite):** registra chamadas de LLM, requisições, documentos
  e eventos de indexação de forma unificada.
- **Dashboard web** em `/dashboard`: KPIs, gráficos de tokens/requisições/modelos,
  histórico de documentos e tabelas de eventos recentes, com auto-refresh.

### ⚙️ Interface de Linha de Comando

- **Chat interativo** no terminal (`app.py`) com mensagens de status e comando
  `aprofundar` para análise proativa.
- **Indexação** (`index.py`), **Drive + Index** (`drive_index.py`),
  **Seleção do Drive** (`drive_select.py`).
- **Watcher** (`watch.py`): reindexação automática ao detectar mudanças.
- **Reset total** (`reset_app.py`).
- **Inicializador** (`start.bat`/`start.sh`) com menu de operações e setup automático.

### 🖥️ Implantação

- **Multi-plataforma:** scripts para Windows e Linux/macOS.
- **Serviço Windows** (`service.py` — `WatsonRAG`).
- **Supervisord (Linux)** com `setup_supervisor.sh` e `watson-supervisord.conf`.
- **Build executável** via PyInstaller (`build.bat` + `watson.spec`).

### 🧪 Testes

- Suíte com mais de 300 testes (pytest) cobrindo:
  - API (endpoints, autenticação, jobs, Drive, métricas)
  - Indexação incremental, adaptadores, contratos, dedup, qualidade
  - RAG/Chat, detecção de contexto, streaming e timeouts
  - Embeddings, cache, splitter, retriever, analista, calculadora
  - OCR, visão, sync do Drive, manifest e watcher

### 📄 Documentação

- `README.md` reescrito como landing page profissional.
- Documentação reestruturada em `docs/` por jornada de uso (instalação,
  configuração, arquitetura, guias, API, operações e desenvolvimento).

### 🔌 Dependências Principais

- Python 3.10+
- FastAPI, Uvicorn
- Ollama (LLM local) — modelo padrão `gemma3:4b`
- ChromaDB (banco vetorial)
- Sentence-Transformers (embeddings) — `intfloat/multilingual-e5-base`
- PyMuPDF / PyMuPDF4LLM, python-docx, openpyxl, Tesseract (OCR)

---

O formato deste changelog segue [Keep a Changelog](https://keepachangelog.com/).

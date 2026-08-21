# Watson RAG v1.0.0 — Notas de Lançamento

> **Data de Lançamento:** 21 de Agosto de 2026  
> **Versão:** v1.0.0  
> **Tag recomendada:** `v1.0.0`

---

## Visão Geral

Primeira versão estável do **Watson RAG** — um agente de IA de **Retrieval-Augmented Generation (RAG)** 100% local para consulta de documentos técnicos. O Watson indexa PDFs, DOCX, planilhas, imagens e arquivos do **Google Drive** em vetores (ChromaDB) e responde perguntas em linguagem natural com **fontes citadas**, usando um LLM local via **Ollama** — tudo processado no próprio ambiente, sem enviar dados à nuvem.

Nesta versão inicial estão incluídos o pipeline completo de indexação incremental, o pipeline de consulta RAG com modo analista e cálculo verificado, a API REST com streaming e indexação assíncrona, o dashboard de métricas, o console de linha de comando e os scripts de implantação multi-plataforma.

## Novidades da v1.0.0

### 🤖 Assistente de IA (Watson / RAG)

- **RAG-only:** o Watson consulta exclusivamente documentos indexados, sem pesquisa na internet nem conhecimento próprio do modelo.
- **Streaming (SSE):**
  - Resposta token a token via `POST /api/chat/stream`.
  - Tokens enviados como **JSON** (`{"content": ...}`) para preservar newlines e formatação markdown.
  - Metadados finais (`confidence`, `sources`, `metadata`) ao término do stream.
- **Fontes citadas:** cada resposta referencia seção, página, fabricante, modelo e códigos de erro dos documentos utilizados.
- **Detecção inteligente de contexto:**
  - `top_k` padrão para perguntas simples.
  - `top_k × 2` para perguntas analíticas (cálculo, comparação, tendência).
  - `top_k × 4` + expansão por documento apenas em pedidos explícitos de completude (`todos`, `completo`, `mais informações`).
  - Listagens genéricas usam o `top_k` padrão, evitando prompts gigantes e respostas lentas.
- **Cálculo verificado:** a camada determinística (`rag/calculator.py`) resolve percentuais, somas, médias, máximos e mínimos sem depender da aritmética do LLM.
- **Modo "Analisar" (análise proativa):** gera conclusões, perguntas de acompanhamento e busca informação adicional no acervo (`analyze=true` ou comando `aprofundar` no terminal).

### 🖥️ Pipeline de Indexação

- **Adaptadores de fonte:** PDF (com OCR seletivo), DOCX, CSV, XLSX, TXT/Markdown e Imagens (OCR + análise por modelo de visão opcional).
- **Chunking semântico:** blocos por cabeçalho/tabela/texto, com metadados ricos (seção, página, códigos de erro).
- **Indexação incremental:** reindexa apenas arquivos novos ou alterados (hash de conteúdo + versões de parser/chunking/embedding).
- **Portão de qualidade e deduplicação:** rejeita chunks de baixa qualidade e elimina duplicatas intra-documento.
- **Cache de embeddings** persistente e **manifesto de indexação** com escrita atômica.

### 📁 Google Drive (pasta pública)

- **Sincronização sem OAuth:** pasta pública via `embeddedfolderview` + download por `uc?export=download`.
- **Seleção de pastas:** navegação e marcação de pastas a indexar, persistida em `.drive_selection.json` e compartilhada com a API.
- **Sincronização incremental** com manifesto local e download paralelo.

### 🔌 API REST (FastAPI)

- **Chat** (`/api/chat`) e **streaming** (`/api/chat/stream`).
- **Indexação assíncrona** em segundo plano com `job_id`, polling de status e cancelamento cooperativo.
- **Endpoints de Drive** (listagem, seleção, sync, limpeza).
- **Upload de documentos** (máx. 50 MB).
- **Limpeza granular** (documentos, vectorstore ou ambos).
- **Autenticação por token** (`X-API-Token` / `Authorization: Bearer`).
- **Métricas:** summary, tokens, requisições, modelos, chamadas de LLM, documentos e eventos de indexação.
- **Documentação interativa** em `/docs` (Swagger) e `/redoc`.

### 📊 Dashboard e Métricas

- **MetricsStore (SQLite):** registro unificado de chamadas de LLM, requisições, documentos e eventos de indexação.
- **Dashboard web** em `/dashboard`: KPIs, gráficos de tokens/requisições/modelos, histórico de documentos e tabelas de eventos recentes, com auto-refresh.

### ⚙️ Interface de Linha de Comando

- **Chat interativo** no terminal (`app.py`) com mensagens de status e comando `aprofundar`.
- **Indexação** (`index.py`), **Drive + Index** (`drive_index.py`), **Seleção do Drive** (`drive_select.py`).
- **Watcher** (`watch.py`): reindexação automática ao detectar mudanças.
- **Reset total** (`reset_app.py`).
- **Inicializador** (`start.bat`/`start.sh`) com menu de operações e setup automático.

### 🖥️ Implantação

- **Multi-plataforma:** scripts para Windows e Linux/macOS.
- **Serviço Windows** (`service.py` — `WatsonRAG`).
- **Supervisord (Linux)** com `setup_supervisor.sh` e `watson-supervisord.conf`.
- **Build executável** via PyInstaller (`build.bat` + `watson.spec`).

### 🧪 Testes

- Suíte com mais de 300 testes (pytest) cobrindo API, indexação, adaptadores, contratos, dedup, qualidade, RAG/Chat, streaming, timeouts, embeddings, cache, splitter, retriever, analista, calculadora, OCR, visão, sync do Drive, manifest e watcher.

### 📄 Documentação

- `README.md` reescrito como landing page profissional.
- Documentação reestruturada em `docs/` por jornada de uso (instalação, configuração, arquitetura, guias, API, operações e desenvolvimento).

## Observações

- Tag recomendada: `v1.0.0`.
- Requer Python 3.10+ e o servidor **Ollama** rodando com um modelo baixado (padrão `gemma3:4b`).
- O **Tesseract OCR** é opcional (necessário apenas para PDFs escaneados e imagens).
- Para sincronização do Google Drive, configure `GOOGLE_DRIVE_FOLDER_ID` no `.env` apontando para uma pasta **pública**.
- Para proteger a API, defina `API_AUTH_TOKEN` no `.env` (header `X-API-Token`).
- Documentação detalhada disponível em [`docs/`](docs/index.md).

# Watson — Documentação

> **Comece aqui.** Esta página é o índice mestre: de onde você veio, para onde ir e em que ordem ler. Todo link abaixo tem um propósito na jornada.

---

## Como usar esta documentação

**Se é sua primeira vez:** siga a **Jornada recomendada** na ordem (1 → 11). Cada etapa depende da anterior e termina com um “Próximo passo” que leva você adiante.

**Se já conhece o Watson:** use o **Mapa por objetivo** para saltar direto ao que precisa.

O Watson é um **RAG 100% local**: lê PDFs, DOCXs, planilhas e imagens (com OCR), transforma em vetores no ChromaDB e responde com um LLM local (Ollama) citando **fontes exatas** (título, seção, página, fabricante, modelo, código de erro) — sem nuvem.

---

## Jornada recomendada — do zero à produção

| Passo | O que você vai fazer | Documento | Entregável |
|---|---|---|---|
| **1** | Entender o produto | [README](../README.md) + [Arquitetura — Visão geral](architecture/overview.md) | Visão de fluxo `documentos → vetores → pergunta → resposta` |
| **2** | Instalar dependências | [Instalação](getting-started/installation.md) | Ollama + Python + Tesseract funcionando |
| **3** | Rodar a primeira pergunta | [Início rápido](getting-started/quickstart.md) | `documents/` indexado + resposta no terminal/API |
| **4** | Escolher perfil e ajustar | [Configuração](getting-started/configuration.md) — **Flash / Plus / Pro** | `WATSON_PROFILE=plus` (ou `pro` com `qwen3:8b`) em `.env` ou `/config` |
| **5** | Usar no dia a dia | [Guia de uso](guides/usage.md) | Menu, chat, watcher, reset, limpeza |
| **6** | Indexar conteúdo real | [Google Drive](guides/google-drive.md) + [Ingestão](architecture/ingestion-pipeline.md) | Drive sincronizado, OCR seletivo compreendido |
| **7** | Obter respostas melhores | [Modo Analista](guides/analyst-mode.md) + [RAG](architecture/rag-pipeline.md) | `Pro` + Query Rewriter + reranker dominados |
| **8** | Integrar em outro sistema | [Referência da API](api/api-reference.md) → [Integração](api/integration.md) | `curl` / Python / Node / PHP / DokViewerManager funcionando |
| **9** | Operar com confiança | [Monitoramento](guides/monitoring.md) | Dashboard `/dashboard` + métricas compreendidas |
| **10** | Levar para produção | [Implantação](operations/deployment.md) | Supervisord / serviço Windows / executável |
| **11** | Resolver imprevistos | [Solução de problemas](operations/troubleshooting.md) | Diagnóstico rápido |
| **12** | Evoluir o projeto | [Desenvolvimento](development/development.md) → [Testes](development/testing.md) | Ambiente de dev e suíte de 300+ testes |

Ao final do passo 11 você tem o Watson em produção. O passo 12 é para quem vai estender o código.

---

## Mapa por objetivo — “quero…”

| Quero… | Vá direto para |
|---|---|
| Instalar do zero | [Instalação](getting-started/installation.md) |
| Rodar em 5 minutos | [Início rápido](getting-started/quickstart.md) |
| Entender Flash vs Plus vs Pro | [Configuração — Perfis](getting-started/configuration.md#11-perfis-watson--flash--plus--pro) |
| Editar `.env` sem abrir o terminal | `http://localhost:9000/config` + [Configuração](getting-started/configuration.md) |
| Comparar os 3 perfis lado a lado | `http://localhost:9000/compare` |
| Ver como documentos viram vetores | [Ingestão](architecture/ingestion-pipeline.md) |
| Ver como perguntas viram respostas | [RAG](architecture/rag-pipeline.md) |
| Usar chat, watcher ou reset | [Guia de uso](guides/usage.md) |
| Sincronizar Drive sem OAuth | [Google Drive](guides/google-drive.md) |
| Respostas com raciocínio profundo | [Modo Analista](guides/analyst-mode.md) |
| Ver tokens, latência e saúde | [Monitoramento](guides/monitoring.md) + `/dashboard` |
| Consumir a API | [Referência da API](api/api-reference.md) + Swagger `http://localhost:9000/docs` |
| Exemplo em Python / Node / PHP | [Integração](api/integration.md) |
| Subir com Docker / serviço | [Implantação](operations/deployment.md) |
| Resolver erro `Model not found` / `Connection refused` | [Solução de problemas](operations/troubleshooting.md) |
| Entender pastas e módulos | [Estrutura do projeto](development/project-structure.md) |
| Rodar testes | [Testes](development/testing.md) |

---

## Estrutura da documentação

```
docs/
├── index.md                          ← você está aqui (índice mestre)
├── getting-started/
│   ├── installation.md               # Pré-requisitos por SO
│   ├── quickstart.md                 # Primeira indexação e pergunta
│   └── configuration.md              # 58 vars + perfis Flash/Plus/Pro + /config + /compare
├── architecture/
│   ├── overview.md                   # Visão geral e decisões de design
│   ├── ingestion-pipeline.md         # Loader → Splitter → Quality → Embeddings → Chroma
│   └── rag-pipeline.md               # Retriever → Prompt → Ollama → Analyst → Metrics
├── guides/
│   ├── usage.md                      # Menu, chat, watcher, reset
│   ├── google-drive.md               # Sync de pasta pública
│   ├── analyst-mode.md               # Pro + think + Query Rewriter
│   └── monitoring.md                 # Dashboard e logs
├── api/
│   ├── api-reference.md              # Endpoints, modelos, erros
│   └── integration.md                # cURL / Python / Node / PHP / Laravel
├── operations/
│   ├── deployment.md                 # Supervisord, Windows, build
│   └── troubleshooting.md            # Diagnóstico
└── development/
    ├── project-structure.md          # Pastas e responsabilidades
    ├── development.md                # Como contribuir
    └── testing.md                    # Suíte de testes
```

---

## Convenções

- **Código → doc:** sempre que um conceito aparece, há o caminho do arquivo e linha — ex: `core/config.py:290` `WATSON_PROFILE`, `rag/chatbot.py:335` perfis por request, `presentation/chat.html:251` seletor.
- **Ambiente:** `.env.example` é o template versionado (118 vars comentadas), `.env` é o ativo (essencial, editável em `/config`). Após alterar, `docker compose restart watson`.
- **Portas:** API `9000`, Ollama `11434`, SearXNG `8080`. Swagger em `/docs`, chat em `/`, comparar em `/compare`, config em `/config`, dashboard em `/dashboard`.

---

## Próximo passo

Se acabou de chegar: **[Instalação](getting-started/installation.md)** → **[Início rápido](getting-started/quickstart.md)** → **[Configuração — Perfis](getting-started/configuration.md#11-perfis-watson--flash--plus--pro)**.

Se já instalou: **[Guia de uso](guides/usage.md)** ou **[Referência da API](api/api-reference.md)**.

---

<p align="center"><i>Dúvida? Comece pelo <a href="../README.md">README</a> (5 min) e siga a Jornada acima. Ao final você terá o Watson indexando seus documentos e respondendo com fontes.</i></p>

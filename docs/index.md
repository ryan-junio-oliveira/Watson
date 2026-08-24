# 📖 Documentação do Watson RAG

Bem-vindo à documentação oficial do **Watson RAG** — um agente de IA de Retrieval-Augmented Generation (RAG) totalmente local para consulta de documentos técnicos.

Esta documentação está organizada por jornada de uso, para que você encontre rapidamente o que precisa.

---

## 🧭 Navegação

### 🚀 Começando

| Documento | Descrição |
|---|---|
| [Instalação](getting-started/installation.md) | Pré-requisitos e instalação de Ollama, Python e Tesseract em Windows e Linux |
| [Início rápido](getting-started/quickstart.md) | Primeira indexação e primeira pergunta em poucos passos |
| [Configuração](getting-started/configuration.md) | Referência completa de variáveis de ambiente e defaults |

### 🏗️ Arquitetura

| Documento | Descrição |
|---|---|
| [Visão geral](architecture/overview.md) | Componentes, fluxo de dados e decisões de design |
| [Pipeline de indexação](architecture/ingestion-pipeline.md) | Como os documentos viram vetores: adapters, loader, splitter, qualidade, dedup |
| [Pipeline de consulta (RAG)](architecture/rag-pipeline.md) | Como as perguntas são respondidas: retriever, evidências, prompt, LLM |

### 🛠️ Guias

| Documento | Descrição |
|---|---|
| [Guia de uso](guides/usage.md) | Menu do inicializador, chat no terminal, watcher, reset e limpeza |
| [Google Drive](guides/google-drive.md) | Sincronização de pastas públicas sem OAuth |
| [Modo Analista](guides/analyst-mode.md) | Análise proativa, raciocínio e cálculo verificado |
| [Monitoramento](guides/monitoring.md) | Dashboard de métricas, logs e observabilidade |

### 🔌 API e Integração

| Documento | Descrição |
|---|---|
| [Referência da API](api/api-reference.md) | Todos os endpoints, modelos de dados e códigos de erro |
| [Integração](api/integration.md) | Exemplos de consumo em Python, Node.js, PHP, Laravel e cURL |

### ⚙️ Operações

| Documento | Descrição |
|---|---|
| [Implantação](operations/deployment.md) | Supervisord (Linux), serviço Windows e build executável |
| [Solução de problemas](operations/troubleshooting.md) | Diagnóstico dos problemas mais comuns |

### 🧑‍💻 Desenvolvimento

| Documento | Descrição |
|---|---|
| [Estrutura do projeto](development/project-structure.md) | Organização de pastas e responsabilidades de cada módulo |
| [Desenvolvimento](development/development.md) | Guia para contribuir e boas práticas |
| [Testes](development/testing.md) | Como rodar e estender a suíte de testes |

---

## 📌 Em uma frase

O Watson lê documentos técnicos (PDF, DOCX, planilhas, imagens, Drive), converte o conteúdo em **chunks semânticos**, gera **embeddings** e armazena em um **banco vetorial** (ChromaDB). Quando você faz uma pergunta, ele recupera os trechos mais relevantes, monta um prompt com **fontes citadas** e usa um **LLM local (Ollama)** para gerar a resposta — tudo sem depender de nuvem.

---

## ⚡ Links rápidos

- [README](../README.md) — visão geral e início rápido
- [Início rápido](getting-started/quickstart.md)
- [Referência da API](api/api-reference.md)
- [Guia de uso](guides/usage.md)
- [Solução de problemas](operations/troubleshooting.md)

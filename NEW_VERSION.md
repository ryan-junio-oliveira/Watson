# Watson RAG 0.0.1 — Lançamento Oficial

**Data:** 24 de agosto de 2026
**Tag:** `v0.0.1`

---

Estamos lançando a primeira versão oficial do **Watson RAG**, o agente de inteligência artificial para consulta de documentos técnicos da Dok Solutions.

Depois de meses de desenvolvimento, testes e amadurecimento, o Watson está pronto para produção: um assistente que indexa todo o acervo técnico da empresa e responde perguntas em linguagem natural — com fontes citadas, funcionando inteiramente no ambiente do cliente.

## O que é o Watson

Um agente de IA que **indexa** manuais, especificações, planilhas, imagens e arquivos do Google Drive em um banco vetorial local, **entende** perguntas em português e **responde** com trechos extraídos dos documentos — sempre indicando seção, página, fabricante e modelo da fonte. Nenhum dado sai do ambiente: o modelo de linguagem (Ollama), os embeddings e o banco vetorial (ChromaDB) rodam 100% locais.

## Tudo o que o sistema entrega

### Assistente de IA com fontes citadas
- Respostas baseadas exclusivamente nos documentos indexados — sem pesquisa na internet nem invenção do modelo.
- Cada resposta referencia a fonte: seção, página, fabricante, modelo e códigos de erro.
- Resposta transmitida token a token (streaming), ideal para interfaces web.
- Detecção inteligente de contexto: perguntas analíticas recebem mais evidências; pedidos explícitos de completude ("todos", "completo") expandem automaticamente a busca por documento.
- Modo Analista sob demanda: conclusões, sugestões de próximos passos e busca adicional no acervo.
- Cálculo verificado: percentuais, somas, médias, máximos e mínimos são resolvidos por uma camada determinística — não pela aritmética do modelo.

### Indexação de documentos
- Formatos suportados: PDF, DOCX, CSV, XLSX, TXT/Markdown e imagens.
- OCR embutido (Tesseract), aplicado seletivamente apenas nas páginas sem texto nativo.
- Chunking semântico que preserva a estrutura dos documentos (títulos, tabelas, seções).
- Indexação incremental: apenas arquivos novos ou alterados são reprocessados.
- Controle de qualidade e deduplicação automática dos blocos indexados.
- Upload de arquivos direto pela API (até 50 MB).
- Watcher opcional que reindexa sozinho ao detectar mudanças na pasta de documentos.

### Google Drive sem configuração complexa
- Sincronização de pastas públicas do Drive sem OAuth nem credenciais.
- Seleção visual das pastas a indexar, com sincronização incremental e downloads paralelos.
- Arquivos removidos ou alterados no Drive são refletidos no índice automaticamente na próxima sync.

### API REST completa
- Endpoints de chat (síncrono e streaming), modelos disponíveis, saúde do serviço e métricas.
- Indexação assíncrona em segundo plano, com progresso consultável e cancelamento cooperativo.
- Autenticação por token (`X-API-Token`) pronta para ambientes de rede.
- Documentação interativa Swagger/ReDoc incluída.

### Dashboard de métricas
- Painel web com KPIs de uso: tokens consumidos, requisições, chamadas de LLM e documentos indexados.
- Gráficos por hora e por modelo, histórico de documentos e eventos recentes de indexação.
- Retenção de 30 dias de histórico, sem manutenção manual.

### Operação e implantação simples
- Inicializador com menu completo: API, chat no terminal, indexação, Google Drive e reset.
- Instalação para Windows e Linux/macOS com setup automático do ambiente.
- Serviço Windows nativo e gerenciamento por supervisord no Linux.
- Build de executável via PyInstaller para distribuição sem Python instalado.
- Reset total seguro: índice, caches, métricas e documentos em um único comando.

### Qualidade
- Suíte com mais de 300 testes automatizados cobrindo API, indexação, RAG, OCR, Drive, métricas e watcher.
- Documentação completa e auditada contra o código: instalação, configuração, arquitetura, API e operações.

## Observações

- Requer Python 3.10+ e o **Ollama** rodando com um modelo baixado (padrão `gemma3:4b`).
- O **Tesseract OCR** é opcional — necessário apenas para PDFs escaneados e imagens.
- Para proteger a API em rede, defina `API_AUTH_TOKEN` no `.env`.
- Documentação detalhada disponível em [`docs/`](docs/index.md).

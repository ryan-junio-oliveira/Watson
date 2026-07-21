# Plano de Melhorias - Watson RAG

## Análise Completada
- [x] README.md - Visão geral do projeto
- [x] api.py - Endpoints FastAPI
- [x] app.py - Chat modo terminal
- [x] config.py - Configurações
- [x] rag/chatbot.py - Chatbot RAG
- [x] rag/retriever.py - Retrieval
- [x] rag/prompt.py - Prompt builder
- [x] rag/reranker.py - Re-ranker
- [x] llm/ollama_client.py - Cliente Ollama
- [x] ingestion/indexer.py - Indexador
- [x] ingestion/embeddings.py - Embeddings
- [x] ingestion/loader.py - Loader de documentos
- [x] ingestion/splitter.py - Splitter
- [x] ingestion/db_loader.py - Loader MySQL
- [x] utils/logger.py - Logger
- [x] requirements.txt - Dependências

## Melhorias Implementadas ✓

### Alta Prioridade
- [x] 1. Adicionar CORS middleware na API
- [x] 2. Endpoint de chat com streaming (SSE) - `/api/chat/stream`
- [x] 3. Health check real do Ollama (verifica conexão ativa)
- [x] 4. Log rotation (RotatingFileHandler, 10 MB, 5 backups)
- [x] 5. Corrigir SQL injection no db_loader (validação de identificadores)

### Média Prioridade
- [x] 6. Melhorar PromptBuilder com histórico estruturado (já existia)
- [x] 7. Adicionar request_id para tracing (middleware + header X-Request-ID)
- [x] 8. Melhorar metadata dos chunks (chunk_index, total_chunks, chunk_size)
- [x] 9. Melhorar tratamento de erros no retriever quando ChromaDB vazio

### Testes
- [x] 80/80 testes passando (após ajustes no teste do db_loader)

## Resumo das Mudanças

### `api.py`
- CORS middleware adicionado
- Novo endpoint `/api/chat/stream` com SSE streaming
- Health check agora verifica conexão real com Ollama
- Middleware `add_request_id` para tracing com header `X-Request-ID`
- Logs incluem request_id para correlação

### `utils/logger.py`
- Migrado de `FileHandler` para `RotatingFileHandler`
- 10 MB por arquivo, mantém 5 backups

### `ingestion/db_loader.py`
- Removido SQL injection: `text(f"SELECT * FROM {table_name}")` → `_quote_identifier()` validado
- Validação de nomes de tabela contra regex seguro
- Cache de nomes de tabelas para performance

### `ingestion/splitter.py`
- Metadata enriquecida: `chunk_index`, `total_chunks`, `chunk_size`, `file_size`

### `rag/retriever.py`
- Tratamento de erro para ChromaDB vazio ou não inicializado
- Verifica `collection.count()` antes de buscar
- Retorna lista vazia graciosamente em vez de crash
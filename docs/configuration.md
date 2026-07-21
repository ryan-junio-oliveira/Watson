# Configuracao

Todas as configuracoes sao centralizadas em `config.py` e podem ser sobrescritas via variaveis de ambiente ou arquivo `.env`.

## Arquivo `.env`

```bash
cp .env.example .env
```

## Tabela de Configuracoes

| Variavel | Padrao | Descricao |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL do servidor Ollama |
| `OLLAMA_MODEL` | `qwen3:8b` | Modelo LLM para respostas |
| `OLLAMA_TIMEOUT` | `120` | Timeout em segundos para chamadas ao Ollama |
| `TEMPERATURE` | `0.1` | Temperatura do modelo (0.0 = deterministico, 1.0 = criativo) |
| `MAX_TOKENS` | `2048` | Maximo de tokens por resposta |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Modelo de embeddings (sentence-transformers) |
| `CHUNK_SIZE` | `1000` | Tamanho de cada chunk em caracteres |
| `CHUNK_OVERLAP` | `200` | Sobreposicao entre chunks consecutivos |
| `TOP_K` | `5` | Numero de chunks recuperados por consulta |
| `INDEX_BATCH_SIZE` | `100` | Lote de chunks para insercao no ChromaDB |
| `DOCUMENTS_DIR` | `documents` | Diretorio para documentos a serem indexados |
| `VECTOR_DB_DIR` | `database/chroma` | Diretorio do banco vetorial ChromaDB |
| `LOG_LEVEL` | `INFO` | Nivel de logging (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FILE` | `logs/ai_agent.log` | Caminho do arquivo de log |
| `API_HOST` | `0.0.0.0` | Host do servidor API |
| `API_PORT` | `9000` | Porta do servidor API |
| `DB_HOST` | — | Host do MySQL |
| `DB_PORT` | `3306` | Porta do MySQL |
| `DB_USER` | — | Usuario do MySQL |
| `DB_PASSWORD` | — | Senha do MySQL (qualquer caractere especial funciona) |
| `DB_NAME` | — | Nome do banco de dados |
| `DB_TABLES` | — | Lista JSON de tabelas para indexar |

---

## Conexao com o banco de dados

O Watson oferece **dois formas** de configurar a conexao MySQL:

### Forma recomendada: variaveis separadas

```bash
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=@Admini20m07p
DB_NAME=dokviewermanager
```

A `DB_CONNECTION_STRING` e montada automaticamente pelo `config.py`, aplicando **URL-encoding no password** de forma transparente. Voce pode usar qualquer caractere especial na senha sem se preocupar.

### Forma alternativa: connection string raw

```bash
DB_CONNECTION_STRING=mysql+pymysql://root:%40Admini20m07p@localhost:3306/dokviewermanager
```

Se `DB_CONNECTION_STRING` estiver definida, ela tem prioridade sobre as variaveis separadas. Neste caso, a senha **precisa estar URL-encoded manualmente**.

### Tabela de referencia de encoding

Usado apenas se optar pela `DB_CONNECTION_STRING` raw:

| Caractere | Codigo | Exemplo |
|---|---|---|
| `@` | `%40` | `@senha` -> `%40senha` |
| `%` | `%25` | `senha%123` -> `senha%25123` |
| `#` | `%23` | `senha#abc` -> `senha%23abc` |
| `/` | `%2F` | `senha/abc` -> `senha%2Fabc` |
| `:` | `%3A` | `senha:abc` -> `senha%3Aabc` |
| `?` | `%3F` | `senha?abc` -> `senha%3Fabc` |
| ` ` (espaco) | `%20` | `minha senha` -> `minha%20senha` |

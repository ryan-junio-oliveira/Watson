# Indexacao de Banco de Dados

O Watson conecta em bancos MySQL e converte cada linha de cada tabela em um documento texto que passa por chunking, embeddings e armazenamento no ChromaDB.

## Configuracao

Defina no `.env`:

```bash
DB_CONNECTION_STRING=mysql+pymysql://user:senha@host:3306/dbname
DB_TABLES=["licenses","clients","installations"]
```

- `DB_TABLES` aceita JSON array ou lista separada por virgulas
- Se omitido ou `["*"]`, todas as tabelas sao indexadas
- Se a senha tiver caracteres especiais, veja [Configuracao > URL-encoding](configuration.md#url-encoding-em-senhas-do-banco-de-dados)

## Formato dos documentos gerados

Cada registro do banco vira um documento:

```
[Tabela: licenses]
id: 1
client_id: 5
product: DokViewer
license_key: ABC-123
expires_at: 2026-08-15
status: active
created_at: 2025-08-15T10:00:00
updated_at: 2026-07-01T14:30:00
```

## Colunas sensiveis

Colunas que contenham no nome: `password`, `senha`, `secret`, `token`, `recovery_codes`, `two_factor` ou `remember_token` sao **automaticamente excluidas** da indexacao.

## Deteccao de mudancas incrementais

- Hash SHA-256 do conteudo de cada registro e calculado
- Na reindexacao, apenas registros com conteudo diferente sao reprocessados
- Registros que nao existem mais sao removidos do indice vetorial
- O cache fica em `database/chroma/index_control.json`

## Exemplos de perguntas que o RAG consegue responder

| Pergunta | Origem dos dados |
|---|---|
| "Quantas licencas estao prestes a expirar?" | Tabela `licenses` |
| "Qual cliente tem mais instalacoes?" | Tabelas `clients` + `installations` |
| "Liste as licencas bloqueadas" | Tabela `licenses` |
| "Quem renovou este mes?" | Tabela `license_renewal_history` |

## Limitacoes

- A indexacao do banco **nao altera os dados originais**
- Consultas como "quantas licencas" funcionam por **similaridade semantica**, nao por SQL direto
- Para dados criticos, a resposta do LLM deve ser verificada com a fonte original
- O Watson nao faz agregacoes numericas precisas (somas, medias) — use o banco original para isso

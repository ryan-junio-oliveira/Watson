# Monitoramento

O Watson registra **métricas de uso** em um banco SQLite e expõe um **dashboard web** para acompanhar o desempenho e o histórico.

---

## Dashboard web

Acesse em <http://localhost:9000/dashboard> (quando a API estiver rodando).

Um painel single-page (claro/escuro) com:

- **KPIs** — chamadas de LLM, tokens, requisições, documentos/chunks indexados.
- **Gráficos**:
  - Tokens de entrada/saída (barras).
  - Requisições ao longo do tempo (linha).
  - Tokens por modelo (barras horizontais).
  - Histórico de documentos/chunks (linha).
- **Tabelas** — chamadas recentes de LLM, requisições recentes, eventos recentes de indexação.
- **Filtros** — seletor de período (horas).
- **Atualização** — auto-refresh a cada 15s + botão manual.

---

## Métricas armazenadas

O `MetricsStore` usa SQLite (`METRICS_DB`, padrão `database/metrics.db`) com quatro tabelas:

| Tabela | O que registra |
|---|---|
| `llm_calls` | Cada chamada ao Ollama: modelo, tipo (generate/stream), tokens de prompt/completion, durações, sucesso/erro |
| `requests` | Cada requisição de chat: endpoint, pergunta, modo, provedor, nº de evidências, tempo de execução, flag `analyze`, sucesso/erro |
| `documents` | Snapshot de documentos/chunks indexados, com detalhamento por tipo |
| `index_events` | Eventos de indexação: documentos processados, chunks indexados, erros |

---

## Endpoints de métricas (API)

| Endpoint | Método | Descrição |
|---|---|---|
| `/api/metrics/summary` | GET | Resumo geral (chamadas, tokens, requisições, docs) — aceita `?hours=` |
| `/api/metrics/tokens` | GET | Série temporal de tokens entrada/saída — `?hours=` |
| `/api/metrics/requests` | GET | Série temporal de requisições (total/sucesso) — `?hours=` |
| `/api/metrics/models` | GET | Tokens por modelo — `?hours=` |
| `/api/metrics/llm-calls` | GET | Log recente de chamadas de LLM — `?limit=` |
| `/api/metrics/requests-log` | GET | Log recente de requisições — `?limit=` |
| `/api/metrics/documents` | GET | Histórico de documentos/chunks indexados |
| `/api/metrics/index-events` | GET | Eventos recentes de indexação — `?limit=` |

> **Retenção:** o banco de métricas mantém os registros dos últimos **30 dias** (`MetricsStore.prune()`); registros mais antigos são removidos automaticamente.

---

## Logs

O logging usa `utils/logger.py` com **rotação** de arquivos (máx. 10 MB × 5 backups) e saída no console (configurável).

| Variável | Padrão | Descrição |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Nível de log |
| `LOG_FILE` | `logs/ai_agent.log` | Arquivo de log |

Exemplos de linhas de log:

```
INFO     | Question: quais sao os pins das impressoras hp
INFO     | Retrieved 10 chunks for query: quais sao os pins...
INFO     | AgentResponse: evidence=5, time=12.34s
INFO     | Stream result: time=12.34s
WARNING  | Reflection failed: timed out
```

> Dica: para depuração detalhada, defina `LOG_LEVEL=DEBUG` no `.env`.

---

## Solução de problemas de performance

Se as respostas estiverem lentas, verifique:

1. **Contexto recuperado** — perguntas com `todos`/`completo` expandem muito o prompt (top_k × 4 + até 12 chunks). Reforce apenas quando necessário.
2. **Modelo** — em CPU, `gemma3:4b` é mais rápido que `qwen3:8b`.
3. **Analista** — a análise proativa adiciona chamadas de LLM. Considere desativar se o tempo for crítico.
4. **Hardware** — uma GPU acelera drasticamente a geração.

Veja [Solução de problemas](../operations/troubleshooting.md).

---

## Próximos passos

- [Referência da API](../api/api-reference.md)
- [Solução de problemas](../operations/troubleshooting.md)

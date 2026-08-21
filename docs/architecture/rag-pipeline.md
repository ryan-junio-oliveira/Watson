# Pipeline de Consulta (RAG)

O pipeline de consulta transforma uma pergunta em linguagem natural em uma **resposta com fontes citadas**, usando recuperação vetorial e geração por LLM local.

---

## Fluxo de consulta

```
Pergunta
   │
   ▼
Retriever (top-k, MMR/threshold, rerank opcional)
   │  (documentos relevantes)
   ▼
EvidenceNormalizer → EvidenceAggregator (dedup + rank)
   │  (evidências ranqueadas)
   ▼
Calculator (injetar fatos verificados)
   │  (evidências + fatos computados)
   ▼
PromptBuilder (system + evidências + histórico)
   │  (prompt pronto)
   ▼
OllamaClient (generate / stream, think opcional)
   │  (resposta bruta)
   ▼
strip thinking → AgentResponse (resposta + fontes + metadata)
   │
   ▼
[opcional] Analyst (reflexão, perguntas, busca adicional)
   │
   ▼
MetricsStore (registro)
```

---

## Módulos

### `rag/retriever.py` — Recuperação vetorial

- Envolve o Chroma (collection `"documents"`).
- `retrieve()` retorna top-k documentos:
  - **Similaridade** (`similarity_search_with_relevance_scores`) com `similarity_threshold` opcional.
  - **MMR** (`max_marginal_relevance_search`) para diversidade quando `USE_MMR=true`.
  - Guarda `relevance_score` nos metadados.
- Verifica coleção vazia antes de buscar.
- `retrieve_all_from_source()` — retorna **todos** os chunks de uma fonte (usado em perguntas de listagem), lendo o índice e filtrando por `source`.

### `rag/evidence.py` — Modelo e agregação de evidências

- `Evidence` — contrato rico: seção, subseção, página inicial/final, fabricante, modelo, códigos de erro, `chunk_id`, `context_label`.
- `EvidenceNormalizer.from_chroma_document()` — converte documentos recuperados em evidências.
- `EvidenceAggregator` — `collect()` (dedup por id), `rank()` (ordena por score), `format_for_prompt()`, `sources_text()`.

### `rag/prompt.py` — Construção de prompts

- `SYSTEM_PROMPT` — persona de **analista meticuloso**: instruído a calcular percentuais/somas/médias, mostrar a conta, nunca inventar dados, citar seções/páginas e responder em português.
- `NO_EVIDENCE_PROMPT` — usado quando não há evidências: é honesto, não inventa e sugere reformulações.
- `build()` e `build_with_history()` — formatam blocos de evidência + pergunta.

### `rag/response.py` — Modelos de resposta

- `Mode` — enum `auto` | `rag` (ambos usam RAG).
- `Source` — título, url, provider, página, seção, fabricante, modelo, códigos de erro (`from_evidence`).
- `AgentResponse` — `answer`, `evidences`, `confidence`, `verdict`, `issues`, `metadata`, `execution_time`; campos opcionais do analista (`conclusions`, `follow_up`, `additional_info`); propriedade `sources`.

### `rag/chatbot.py` — Orquestrador

O `ChatBot` coordena todo o fluxo de consulta:

- **Recuperação dinâmica** (`_retrieve_rag`):
  - `top_k × 4` se o usuário pedir **explicitamente** contexto completo (`todos`, `completo`, `mais informações`).
  - `top_k × 2` para perguntas **analíticas**.
  - `top_k` padrão caso contrário (perguntas de listagem genéricas usam o padrão para não inflar o prompt).
  - Expansão de contexto por documento (top-2 fontes, máx. 12 chunks) **apenas** em pedidos explícitos de completude.
- **Rerank opcional** via `rag/reranker.py` (CrossEncoder) quando `USE_RERANKER=true`.
- **Fatos computados** — injeta resultados do `Calculator` nas evidências.
- **Raciocínio** (`_should_reason`) — habilita modo `think` para perguntas analíticas, se `ENABLE_REASONING=true` e o modelo suportar (qwen3/qwq).
- **Streaming** — `ask_stream`, `ask_stream_with_history` (token a token).
- **Analista** — `_run_analyst()` aplica a análise proativa sob demanda.
- **CLI** — `chat_loop()` com mensagens de status rotativas, comando `aprofundar` e saudação por horário.

### `rag/analyst.py` — Analista proativo

Análise **sob demanda** (não polui a resposta principal). `analyze()`:
1. **Reflexão** — prompt `_REFLECTION_PROMPT` sobre a própria resposta; extrai `CONCLUSOES:`, `PERGUNTAS:` e `TOPICOS:`.
2. **Busca proativa** — para tópicos detectados, recupera mais evidências (k=3, score ≥ 0.1).
3. **Síntese** — `_SYNTHESIS_PROMPT` resume a informação adicional em poucas frases.

Entrega dados estruturados (conclusões, perguntas de acompanhamento, info adicional, fontes extras) sem modificar a resposta principal.

### `rag/calculator.py` — Cálculo determinístico

Camada de cálculo que **não depende de aritmética do LLM**:
- `NumberExtractor` — parseia números pt-BR (`1.234,56`), fatos de mês, fatos chave:valor.
- `IntentDetector` — detecta intenção por regex (percent_change, difference, sum, average, max, min).
- `compute_for_question()` retorna um `ComputedFact` injetado no prompt como "cálculo verificado", e o modelo apenas narra a conclusão.

### `rag/reranker.py` — Re-ranking

Re-ranking com CrossEncoder (opcional, `USE_RERANKER=true`), melhorando a ordem das evidências recuperadas.

---

## LLM — `llm/ollama_client.py`

- `ask()` — geração síncrona; registra métricas; `think` opcional (com fallback automático para `think=False` se o modelo de raciocínio falhar); remove bloco de raciocínio.
- `ask_stream()` — streaming; remove o bloco ` thinking ... response` incrementalmente via máquina de estados em buffer.
- `supports_thinking()` — true apenas para modelos com `qwen3`/`qwq` no nome.
- `_strip_thinking()` — regex `^\s*thinking\b.*?response\b` removendo o raciocínio inicial.
- `list_models()` — lista modelos do Ollama (fallback para o configurado).
- **Métricas** — registra cada chamada (tokens, durações, sucesso/erro).

---

## Próximos passos

- [Guia do Modo Analista](../guides/analyst-mode.md)
- [Referência da API](../api/api-reference.md)
- [Visão geral da arquitetura](overview.md)

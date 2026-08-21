# Modo Analista, Raciocínio e Cálculo

O Watson oferece capacidades além da resposta básica de RAG: **análise proativa**, **raciocínio** (think) e **cálculo determinístico verificado**.

---

## Analista proativo (sob demanda)

O **Analista** aprofunda a análise de uma resposta **quando solicitado** — não polui a resposta principal. Ele entrega:

- **Conclusões** — o que ficou respondido, suposições assumidas e incertezas.
- **Perguntas de acompanhamento** — sugestões úteis baseadas nos dados.
- **Informação adicional** — síntese de novas evidências recuperadas do acervo.
- **Fontes extras** — evidências adicionais encontradas na busca proativa.

### Como funciona

1. **Reflexão** — o Watson recebe a pergunta, sua resposta e as evidências, e produz blocos estruturados `CONCLUSOES:`, `PERGUNTAS:` e `TOPICOS:`.
2. **Busca proativa** — para os tópicos detectados, recupera mais evidências do acervo (k=3, score ≥ 0.1).
3. **Síntese** — resume o que a informação nova acrescenta.

### Configuração

| Variável | Padrão | Descrição |
|---|---|---|
| `ENABLE_ANALYST` | `true` | Liga/desliga o Analista |
| `ANALYST_MAX_FOLLOWUPS` | `3` | Máximo de perguntas de acompanhamento |

### Ativando

**No terminal:** digite `aprofundar` (ou `analisar`) após uma resposta.

**Pela API:** envie `"analyze": true` no corpo da requisição:

```json
{
  "question": "Qual o erro E123 da E52645?",
  "analyze": true
}
```

A resposta inclui `conclusions`, `follow_up` e `additional_info`.

> **Nota de performance**: a análise proativa adiciona chamadas de LLM. Em ambientes de CPU, isso aumenta a latência. Se o tempo de resposta for crítico, considere desativar o Analista ou ativá-lo apenas sob demanda.

---

## Raciocínio (modo `think`)

Para modelos que suportam raciocínio explícito (nomes com `qwen3` ou `qwq`), o Watson pode habilitar o modo `think` em perguntas **analíticas** (cálculo, comparação, análise, tendência).

| Variável | Padrão | Descrição |
|---|---|---|
| `ENABLE_REASONING` | `false` | Habilita raciocínio automático para perguntas analíticas |

O bloco de raciocínio é removido da resposta final automaticamente (`_strip_thinking`).

> Modelos como `gemma3:4b` **não** suportam o modo `think`; para raciocínio, use `qwen3`/`qwq`.

---

## Cálculo determinístico verificado

O Watson **não depende da aritmética do LLM** para cálculos. Uma camada determinística (`rag/calculator.py`) resolve a matemática:

- **`NumberExtractor`** — parseia números pt-BR (`1.234,56`), fatos de mês e pares chave:valor.
- **`IntentDetector`** — detecta intenção por regex: `percent_change`, `difference`, `sum`, `average`, `max`, `min`.

O resultado é injetado no prompt como um **"cálculo verificado"**, e o modelo apenas **narra a conclusão** — reduzindo alucinações numéricas.

**Exemplo:**

```
Pergunta: "Qual o aumento percentual de janeiro para fevereiro?"

Cálculo verificado injetado:
(120 − 90) ÷ 90 = +33,3%
```

O prompt instrui o modelo a mostrar a conta de forma curta e verificável.

---

## Detecção inteligente de contexto

O Watson ajusta dinamicamente a quantidade de contexto recuperado:

| Situação | Comportamento |
|---|---|
| Pergunta padrão | `top_k` normal (rápido) |
| Pergunta analítica (cálculo/comparação/tendência) | `top_k × 2` |
| Pedido **explícito** de completude (`todos`, `completo`, `mais informações`) | `top_k × 4` + expansão por documento (até 12 chunks extras) |
| Listagem genérica (`quais sao ...`) | `top_k` padrão — **sem** expansão (evita prompt gigante) |

> **Performance**: a expansão total de contexto gera prompts grandes e pode demorar muito em CPU. Use "todos/completo" apenas quando realmente precisar de tudo.

---

## Próximos passos

- [Pipeline de consulta (RAG)](../architecture/rag-pipeline.md)
- [Monitoramento](monitoring.md)

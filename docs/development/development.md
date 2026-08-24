# Desenvolvimento

Guia para desenvolvedores que desejam contribuir ou estender o Watson RAG.

---

## Ambiente de desenvolvimento

```bash
# Criar e ativar o venv
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt

# Configurar
cp .env.example .env
```

> Não rode `cleanup.bat`/`cleanup.sh` enquanto estiver desenvolvendo, pois remove artefatos de build.

---

## Ferramentas

| Ferramenta | Uso |
|---|---|
| [ruff](https://docs.astral.sh/ruff) | Lint e formatação |
| [mypy](http://mypy-lang.org) | Checagem de tipos |
| [pytest](https://docs.pytest.org) | Testes |

Configuração em `pyproject.toml` (target `py39`, line-length `100`).

```bash
ruff check .          # lint
ruff format .         # formatação
mypy .                # tipos
pytest tests/ -q      # testes
```

---

## Fluxo de trabalho

1. **Crie um branch** para sua feature/correção.
2. **Escreva testes** primeiro ou junto do código.
3. **Rode a suíte** completa antes de commitar.
4. **Rode lint + tipos** para manter o padrão.
5. Abra um PR descrevendo a mudança.

---

## Adicionando um novo formato de documento

Para suportar um novo tipo de arquivo (ex.: `.odt`, `.rtf`):

1. Crie um adaptador em `ingestion/adapters/` (ex.: `odt_adapter.py`).
2. Estenda `SourceAdapter` (ABC) implementando `extract(filepath) -> LoadedDocument` e definindo `source_type` e `supported_extensions`.
3. Registre-o em `registry.build_default_registry()`.
4. Adicione testes em `tests/test_adapters.py`.
5. Rode a suíte.

---

## Modificando o chunking

O chunking vive em `ingestion/splitter.py`. Se você alterar o algoritmo, **incremente as versões**:

```python
PARSER_VERSION = "1.1"
CHUNKING_VERSION = "2.0"
```

Isso força a reindexação dos documentos ao rodar (sinal de pipeline alterado).

---

## Adicionando endpoints de API

1. Defina os modelos Pydantic de request/response em `api.py`.
2. Adicione o roteador com a anotação `@app.<método>`.
3. Adicione testes em `tests/test_api.py` (auth, sucesso, erros).
4. Documente em [`docs/api/api-reference.md`](../api/api-reference.md).

---

## Adicionando métricas

1. Adicione o método em `metrics/store.py`.
2. Chame-o no ponto relevante do pipeline.
3. Adicione o endpoint em `api.py`.
4. Se aplicável, atualize o dashboard `presentation/dashboard.html`.
5. Adicione testes em `tests/test_metrics.py`.

---

## Boas práticas

- **Separação de responsabilidades**: `ingestion/` não conhece `rag/` e vice-versa; comunique-se via contratos.
- **Contratos estáveis**: altere `contracts.py` com cuidado; mude versões de pipeline quando mudar o schema.
- **Sem lógica de apresentação no pipeline**: use `presentation/formatter.py`.
- **Cálculo no código, não no LLM**: use `rag/calculator.py` para aritmética.
- **Cobertura**: adicione testes para qualquer mudança de comportamento.

---

## Próximos passos

- [Estrutura do projeto](project-structure.md)
- [Testes](testing.md)

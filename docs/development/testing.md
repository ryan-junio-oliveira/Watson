# Testes

O Watson possui uma suíte de **mais de 300 testes** cobrindo API, indexação, embeddings, OCR, splitter, retriever, chat, analista, métricas e watcher.

---

## Executando os testes

```bash
pytest tests/ -q          # suíte completa
pytest tests/test_api.py  # apenas um arquivo
pytest -k "retriever"     # testes que casam com o nome
```

A configuração de caminhos está em `pyproject.toml` (`testpaths`).

---

## Estrutura da suíte

| Arquivo | Cobre |
|---|---|
| `test_api.py` | Endpoints, auth, jobs de indexação, Drive, métricas |
| `test_indexer.py` | Indexação incremental, manifest, reindexação |
| `test_chatbot.py` | Chat/RAG, detecção de contexto, streaming, timeouts |
| `test_retriever.py` | Recuperação, MMR, `retrieve_all_from_source` |
| `test_calculator.py` | Cálculo determinístico e extração de números |
| `test_analyst.py` | Reflexão, síntese e busca proativa |
| `test_prompt.py` | Construção de prompts |
| `test_evidence.py` | Modelo e agregação de evidências |
| `test_adapters.py` | Adaptadores (PDF, DOCX, CSV, XLSX, TXT, imagem) |
| `test_embeddings.py` / `test_embeddings_v2.py` | Geração de embeddings |
| `test_embedding_cache.py` | Cache de embeddings |
| `test_models.py` | Modelos de domínio da ingestão |
| `test_loader.py` | Carregador de documentos |
| `test_splitter.py` / `test_splitter_v2.py` | Chunking semântico |
| `test_quality.py` | Portão de qualidade |
| `test_dedup.py` | Deduplicação |
| `test_manifest.py` | Manifesto de indexação |
| `test_contracts.py` / `test_contract_retrieval.py` | Contrato e compatibilidade |
| `test_identity.py` | Inferência de fabricante/modelo |
| `test_ocr.py` | Tesseract e resolução de caminho |
| `test_vision.py` | Análise por modelo de visão |
| `test_drive_sync.py` | Sincronização do Google Drive |
| `test_metrics.py` | Armazenamento de métricas |
| `test_ollama_client.py` | Cliente Ollama (geração, stream, think) |
| `test_presentation.py` | Formatação de saída |
| `test_watch.py` | Watcher |
| `conftest.py` | Fixtures compartilhadas |

---

## Fixtures disponíveis

`tests/conftest.py` fornece fixtures comuns:

- `sample_text` — texto de exemplo.
- `tmp_text_file` / `tmp_md_file` — arquivos temporários.
- `loaded_text_doc` — documento carregado.
- `tmp_documents_dir` — diretório de documentos temporário.

---

## Testes manuais (e2e)

Existem scripts de validação manual, fora da suíte automática:

| Script | Uso |
|---|---|
| `tests/e2e_manual.py` | Validação manual do fluxo ponta a ponta |
| `tests/e2e_retrieval.py` | Validação de recuperação com dados reais |

---

## Boas práticas

- Use **mocks** para Ollama e ChromaDB nos testes unitários (não dependa de serviços externos).
- Cada mudança de comportamento deve vir com testes.
- Testes de API usam `TestClient` do FastAPI.
- Mantenha os testes rápidos — evite chamadas reais de LLM/embeddings na suíte.

---

## Próximos passos

- [Desenvolvimento](development.md)
- [Estrutura do projeto](project-structure.md)

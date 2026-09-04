# Pipeline de Indexação

O pipeline de indexação transforma arquivos brutos em **chunks semânticos vetorizados** armazenados no ChromaDB. Ele é **incremental**: apenas o que mudou é reprocessado.

---

## Visão geral do módulo

```
Documentos / Drive
   │
   ▼
Loader ──→ Adapters ──→ LoadedDocument ──→ Splitter ──→ Quality ──→ Dedup
                                                                      │
                                                                      ▼
                                                          Embeddings (cache)
                                                                      │
                                                                      ▼
                                                          VectorStore (Chroma)
                                                                      │
                                                                      ▼
                                                          ManifestStore (commit)
```

---

## Módulos

### `ingestion/models.py` — Modelos de domínio

Representam o estágio intermediário entre a extração e o chunking:

- `Page` — número, texto, flag de OCR.
- `Section` — cabeçalho, nível e página.
- `Table` — cabeçalhos, linhas, representação markdown.
- `ImageRef` — referência a imagem extraída.
- `LoadedDocument` — conteúdo + estrutura rica (páginas, seções, tabelas, imagens).
- Helpers de hash: `sha256_text`, `sha256_file`, `compute_document_id` (`doc_` + sha1[:12]), `compute_source_id` (`src_` + sha1[:12]).

### `ingestion/loader.py` — Carregador

- Descobre arquivos recursivamente (`rglob`) em `DOCUMENTS_DIR`.
- Filtra pelas extensões suportadas (registry de adapters).
- Delega cada arquivo ao `SourceAdapter.extract()` correto.
- Preenche metadados padrão (filepath, filename, file_type, modified_at, file_size, source_id).
- Infere `manufacturer`/`model` via `identity.py`.

### `ingestion/adapters/` — Adaptadores de fonte

Cada adaptador extrai um `LoadedDocument` de um tipo de arquivo:

| Adapter | Extensões | Tecnologia |
|---|---|---|
| `PdfAdapter` | `.pdf` | PyMuPDF + PyMuPDF4LLM + OCR seletivo |
| `DocxAdapter` | `.docx` | python-docx |
| `TextAdapter` | `.txt`, `.md`, `.markdown` | leitura UTF-8 |
| `CsvAdapter` | `.csv` | stdlib csv |
| `XlsxAdapter` | `.xlsx`, `.xls` | openpyxl |
| `ImageAdapter` | `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tif`, `.tiff` | Tesseract + visão opcional |

O **`PdfAdapter`** é o mais sofisticado:
1. Extrai texto nativo por página.
2. Páginas com pouco texto ou baixa densidade alfanumérica (< 0.4) são marcadas para OCR.
3. Páginas com texto nativo geram markdown rico (cabeçalhos, tabelas) via PyMuPDF4LLM.
4. Páginas apenas de imagem são processadas com Tesseract a 300 dpi.
5. Imagens embutidas são extraídas (xref) e salvas em `IMAGE_DIR`.

O **`ImageAdapter`** roda OCR e, opcionalmente, uma análise de visão (modelo `VISION_MODEL`) que classifica a imagem (`screenshot`/`photograph`/`diagram`/`table`/etc.) e descreve seu conteúdo.

`ocr.py` resolve o binário do Tesseract de forma cross-platform e `vision.py` encapsula a análise por modelo de visão.

### `ingestion/splitter.py` — Chunking semântico

Chunking por bloco, dependendo do tipo de fonte:

- **PDF/DOCX/Markdown** — blocos a partir de cabeçalhos (`#`-nível), tabelas e texto; seções/subseções rastreadas.
- **CSV/XLSX** — cada tabela vira um bloco preservando a estrutura.
- **Imagens** — um único bloco.
- Blocos grandes → divisão recursiva respeitando `CHUNK_SIZE`/`CHUNK_OVERLAP`; chunks pequenos mesclados.
- Detecta códigos de erro (ex.: `E123`, `ERR-456`).
- Gera metadados ricos (seção, página, fabricante, modelo, códigos de erro).
- Versões: `PARSER_VERSION = "1.1"`, `CHUNKING_VERSION = "2.0"`.

### `ingestion/embeddings.py` — Geração de vetores

- Envolve Sentence-Transformers.
- Detecta automaticamente o prefixo E5 (`query: ` / `passage: `) para a família multilingual-e5.
- Normaliza vetores por padrão.
- `embedding_version = <basename>-<dimensão>` (ex.: `multilingual-e5-base-768`) usado como sinal de reindexação.
- Usa cache persistente chaveado por `(content_hash, model, version)`.
- Expõe wrapper compatível com LangChain.

### `ingestion/embedding_cache.py` — Cache de embeddings

- Cache SQLite persistente (stdlib, vetores float32 empacotados).
- Chave: `(content_hash, model, version)`.
- Thread-safe (lock).
- Métodos: get/set em lote, count, clear, close.

### `ingestion/quality.py` — Portão de qualidade

Avalia cada chunk antes de indexar. Quatro sub-scores combinados:

```
total = 0.35*texto + 0.25*estrutura + 0.20*ocr + 0.20*metadados
```

Defaults: `min_total=0.35`, `min_text=0.15`, `min_chars=20`. Chunks abaixo do limite são **rejeitados** (contados, não indexados).

### `ingestion/dedup.py` — Deduplicação

- **Intra-documento**: conteúdo idêntico no mesmo documento → **rejeitado** (ruído).
- **Cross-documento**: mesmo conteúdo em documentos diferentes → **mantido** (contexto importa), marcado `duplicate_of`.

### `ingestion/indexer.py` — Orquestrador

É o coração da indexação:

- `needs_reindex()` — compara o manifesto (status, hashes, versões) com o documento atual.
- `has_pending_changes()` — retorna documentos pendentes + fontes órfãs (arquivos removidos).
- `_process_document()` — fluxo atômico por documento: split → quality → dedup → embed (cache) → **delete old + add new** no vetor → commit no manifesto. Uma falha não destrói a versão anterior nem bloqueia os demais.
- Controles: `index_document`, `reindex_document`, `delete_document`, `delete_by_source_id`, `reindex_source`, `reindex_all`, `clear_vectorstore`, `clear_documents`, `clear_all`.

### `ingestion/vector_store.py` — Banco vetorial

- Interface `VectorStore` (add, delete_by_document, delete_by_source, delete_by_path, count, clear).
- Implementação `ChromaVectorStore` (langchain_chroma, collection `"documents"`, persistente em `database/chroma`).

### `ingestion/manifest.py` — Manifesto de indexação

- Fonte de verdade por documento.
- Persistência JSON com escrita atômica (temp + `os.replace`), thread-safe.
- Armazena hashes, versões de pipeline, status e estatísticas.
- Default: `<chroma_dir>/index_manifest.json`.

### `ingestion/contracts.py` — Contrato estável

- Define `CHUNK_METADATA_KEYS`, `clean_metadata()`, `PipelineVersion` (com `.signature()`).
- `ChunkContract` — schema rico por chunk + `to_metadata()`/`from_metadata()`.
- `IndexingManifest` — persistência do estado.

### `ingestion/identity.py` — Inferência de fabricante/modelo

Infere fabricante (HP, CANON, EPSON, BROTHER, etc.) e modelo (ex.: `Modelo-X`, `MFC-7860DW`) a partir do nome do arquivo.

### `ingestion/drive_sync.py` — Sincronização do Google Drive

- Sincroniza **pastas públicas** sem OAuth, raspando o `embeddedfolderview?id=<ID>#list`.
- Download via `uc?export=download` (trata a página de confirmação de arquivos grandes).
- Varredura BFS com listagem paralela (`ThreadPoolExecutor`).
- Sincronização incremental via manifesto local `.drive_manifest.json`.
- Seleção de pastas persistida em `.drive_selection.json`.
- Arquivos removidos ou fora da seleção são apagados localmente.

---

## Como funciona a indexação incremental

A cada execução, `has_pending_changes()` compara o manifesto com o estado atual:

1. **Arquivo novo** → `needs_reindex()` retorna true → processa.
2. **Arquivo alterado** → hash de conteúdo ou metadados mudou → processa.
3. **Versão de pipeline mudou** (parser/chunking/embedding) → reindexa.
4. **Arquivo removido** → detectado como órfão → removido do vetor e do manifesto.

Isso garante que apenas o necessário seja reprocessado.

---

## Próximos passos

- [Pipeline de consulta (RAG)](rag-pipeline.md)
- [Visão geral da arquitetura](overview.md)

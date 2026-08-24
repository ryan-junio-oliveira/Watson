# Início Rápido

Este guia leva você da instalação à primeira pergunta respondida em poucos minutos.

> **Pré-requisito**: instalação concluída conforme o [guia de instalação](installation.md) e o Ollama rodando.

---

## 1. Iniciar o inicializador

**Windows:**

```bat
start.bat
```

**Linux / macOS:**

```bash
./start.sh
```

O inicializador executa o setup automático (venv + dependências + `.env`) e exibe o menu:

```
============================================
          WATSON RAG - Inicializador
============================================

 [1] API             - Iniciar servidor FastAPI
 [2] Prompt          - Chat interativo no terminal
 [3] Index           - Indexar documentos locais (documents/)
 [4] Drive + Index   - Sincronizar Google Drive e indexar
 [5] Drive Sync      - Apenas sincronizar Google Drive
 [6] Selecao Drive   - Escolher pastas do Drive p/ indexar
 [7] Reset Total     - Limpar banco vetorial e documentos
 [8] Watcher         - Reindexar automaticamente ao detectar mudancas
 [9] Sair
```

---

## 2. Adicionar documentos

Coloque seus arquivos em `documents/` na raiz do projeto. Formatos suportados:

| Extensão | Tipo |
|---|---|
| `.pdf` | PDF (texto nativo + OCR seletivo) |
| `.docx` | Word |
| `.txt`, `.md`, `.markdown` | Texto/Markdown |
| `.csv`, `.xlsx`, `.xls` | Planilhas |
| `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tif`, `.tiff` | Imagens (OCR) |

---

## 3. Indexar os documentos

No menu, escolha **`3` (Index)** para indexar os documentos locais.

Alternativamente, pela linha de comando:

```bash
python index.py
```

O processo é **incremental**: apenas arquivos novos ou alterados são reprocessados. O log mostra o progresso:

```
[1/4] Venv ja existe em .venv.
[3/4] Instalando dependencias (requirements.txt)...
[4/4] .env ja existe.
Indexing documents/ ...
  ✓ manual-hp-e52645.pdf (12 chunks)
  ✓ contrato-locacao.docx (8 chunks)
Indexacao concluida! Total: 20 chunks
```

---

## 4. Fazer uma pergunta

### No terminal (menu → opção 2)

```bash
python app.py
```

```
> Qual o erro E123 da impressora E52645?

Watson está analisando sua resposta...
[resposta é exibida em tempo real]

Sources
-------
  • HP LASER JET E52645.pdf
```

### Pela API (menu → opção 1)

```bash
curl -s http://localhost:9000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Qual o erro E123 da impressora E52645?"}' | jq .
```

Documentação interativa: <http://localhost:9000/docs>

---

## 5. (Opcional) Sincronizar o Google Drive

Se você tem uma pasta pública do Google Drive, configure `GOOGLE_DRIVE_FOLDER_ID` no `.env` e use a opção **`4` (Drive + Index)** do menu.

Veja o [guia do Google Drive](../guides/google-drive.md).

---

## Resolução de problemas rápidos

| Sintoma | Solução |
|---|---|
| `Connection refused` ao consultar o Ollama | Rode `ollama serve` e verifique `OLLAMA_BASE_URL` |
| `Model not found` | Baixe o modelo: `ollama pull gemma3:4b` |
| Nenhum resultado na consulta | Verifique se os documentos foram indexados (opção 3) |
| Resposta lenta | Considere um modelo menor ou GPU; veja [solução de problemas](../operations/troubleshooting.md) |

Consulte também a [solução de problemas](../operations/troubleshooting.md).

---

## Próximos passos

- [Configuração](configuration.md) — personalize o comportamento
- [Guia de uso](../guides/usage.md) — todas as operações disponíveis
- [Google Drive](../guides/google-drive.md) — sincronização de pastas

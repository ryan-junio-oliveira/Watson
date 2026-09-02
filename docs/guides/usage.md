# Guia de Uso

Este guia cobre todas as operações do dia a dia: inicializador, chat no terminal, indexação, watcher, reset e limpeza.

---

## Inicializador (menu de operações)

O `start.bat` (Windows) e o `start.sh` (Linux/macOS) executam o setup automático e abrem o menu:

| Opção | Ação | Comando equivalente |
|---|---|---|
| **1. API** | Inicia o servidor FastAPI | `uvicorn api:app --host 0.0.0.0 --port 9000` |
| **2. Prompt** | Chat interativo no terminal | `python app.py` |
| **3. Index** | Indexa documentos locais (`documents/`) | `python index.py` |
| **4. Drive + Index** | Sincroniza Google Drive e indexa tudo | `python drive_index.py` |
| **5. Drive Sync** | Apenas sincroniza o Drive | `python drive_index.py --sync-only` |
| **6. Seleção Drive** | Escolhe pastas do Drive a indexar | `python drive_select.py` |
| **7. Reset Total** | Limpa vetores e documentos | `python reset_app.py --yes` |
| **8. Watcher** | Reindexa automaticamente ao detectar mudanças | `python watch.py` |
| **9. Sair** | Encerra | — |

---

## Chat interativo (terminal)

```bash
python app.py
```

- Digite sua pergunta e o Watson responde em tempo real, com mensagens de status rotativas.
- Ao final, mostra as **fontes** utilizadas.
- Comandos: `exit`, `quit`, `sair`, `encerrar` para sair.
- Comando **`aprofundar`** (ou `analisar`) após uma resposta ativa a análise proativa sobre a resposta anterior.

```
> Qual o erro E123 da E52645?

Watson está analisando sua resposta...
[resposta em tempo real]

Sources
-------
  • HP LASER JET E52645.pdf

Perguntas para aprofundar:
  1. Qual o procedimento de troca do fusor?
  (digite 'aprofundar' para mais conclusões/busca)
```

---

## Indexação de documentos

### Indexar documentos locais

```bash
python index.py
```

Indexa tudo em `DOCUMENTS_DIR` (padrão `documents/`), **sem** sincronizar o Drive.

### Indexação incremental

O indexador compara hashes e versões de pipeline com o manifesto; apenas arquivos **novos ou alterados** são reprocessados. Arquivos removidos são purgados automaticamente.

---

## Watcher (reindexação automática)

Monitora `documents/` (incluindo `documents/drive`) e reindexa quando há arquivos novos, alterados ou removidos:

```bash
python watch.py                 # verifica a cada 30s
python watch.py --interval 60   # intervalo customizado (mín. 5s)
```

- Usa **polling leve** (tamanho + mtime por arquivo), sem dependências externas.
- Estado persistido em `logs/.watch_state.json`.
- Rode no servidor como serviço para manutenção contínua.

---

## Reset total

```bash
python reset_app.py --yes        # limpa vetores + docs + cache + métricas
python reset_app.py --yes --no-docs   # mantém documentos, limpa apenas vetores
```

O reset remove:
- Banco vetorial ChromaDB e manifesto
- Cache de embeddings
- Imagens de OCR
- Métricas
- Documentos (por padrão; use `--no-docs` para preservar)

> ⚠️ **Atenção**: resetar é irreversível. A indexação posterior recomeça do zero.

---

## Limpeza e manutenção

Remove artefatos de build/teste/logs antigos:

```bash
./cleanup.sh        # Linux/macOS
cleanup.bat         # Windows
```

Limpa `__pycache__`, `.pytest_cache`, caches de lint, `build/`, `dist/`, `logs/`, `database/chroma/`, cache de embeddings, imagens de OCR, `.coverage`, entre outros.

---

## Parar o servidor

```bash
./stop.sh           # Linux/macOS
stop.bat            # Windows
```

- **Linux/macOS (`stop.sh`):** primeiro tenta `supervisorctl -c /etc/supervisor/supervisord.conf stop watson` (evita `autorestart`). Se não houver supervisord, faz fallback para `lsof`/`pgrep` e `kill` na porta configurada.
- **Windows (`stop.bat`):** primeiro tenta parar o serviço `WatsonRAG` (`cli/service.py stop` + `sc stop WatsonRAG`), depois faz fallback para `netstat`/`taskkill` na porta configurada.

> **Produção Linux (supervisord):** o `kill` direto não basta — com `autorestart=true` o supervisord reinicia o processo. Use sempre `sudo supervisorctl -c /etc/supervisor/supervisord.conf stop watson` ou simplesmente `./stop.sh` (que já faz isso).

---

## Próximos passos

- [Google Drive](google-drive.md)
- [Modo Analista](analyst-mode.md)
- [Monitoramento](monitoring.md)

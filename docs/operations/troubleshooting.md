# Solução de Problemas

Guia de diagnóstico para os problemas mais comuns do Watson RAG.

---

## Problemas de instalação

### `Ollama` não conecta / `Connection refused`

**Causa:** o servidor Ollama não está rodando ou a URL está errada.

**Solução:**
```bash
ollama serve                                # inicia o servidor
curl http://localhost:11434/api/tags        # verifica se responde
```
Confirme `OLLAMA_BASE_URL` no `.env`.

### `Model not found`

**Causa:** o modelo configurado em `OLLAMA_MODEL` não foi baixado.

**Solução:**
```bash
ollama pull gemma3:4b        # baixa o modelo
```

### `Tesseract not found`

**Causa:** Tesseract não instalado ou `TESSERACT_CMD` incorreto.

**Solução:** veja [Instalação — Tesseract](../getting-started/installation.md#3-instalar-o-tesseract-ocr-opcional). Verifique com `tesseract --version`.

### `venv` inválido (copiado de outra máquina)

**Causa:** o ambiente virtual foi copiado de outro sistema e não funciona.

**Solução:** delete `.venv` e rode o setup novamente:
```bash
rm -rf .venv
./start.sh
```

---

## Problemas de indexação

### Nenhum documento é indexado

- Verifique se há arquivos em `DOCUMENTS_DIR` (`documents/`) com extensões suportadas.
- Confira os logs (`logs/ai_agent.log`) para erros de adaptador.
- Teste um único arquivo para isolar o problema.

### PDFs escaneados não têm texto

**Causa:** OCR não configurado.

**Solução:** instale o Tesseract e configure `TESSERACT_CMD`. O OCR é aplicado automaticamente apenas em páginas sem texto nativo.

### O índice não reflete arquivos removidos

Rode uma indexação completa — o indexador detecta arquivos órfãos e os remove do vetor:
```bash
python index.py
```

---

## Problemas de consulta

### Nenhum resultado / "Não encontrei"

- Confirme que os documentos foram indexados (opção 3 do menu).
- Reformule a pergunta com outros termos.
- Verifique se os chunks relevantes passaram pelo portão de qualidade.

### Resposta muito lenta

A latência depende do **tamanho do prompt** e do **hardware**:

| Causa | Solução |
|---|---|
| Pergunta com `todos`/`completo` expande muito o contexto | Use esses termos apenas quando realmente precisar de tudo |
| Modelo grande em CPU | Considere `gemma3:4b` (mais rápido) em vez de `qwen3:8b` |
| Analista proativo adiciona chamadas de LLM | Desative `ENABLE_ANALYST=false` ou ative apenas sob demanda |
| Sem GPU | Uma GPU acelera drasticamente a geração |

### Resposta com dados inventados (alucinação)

- O Watson já injeta **cálculos verificados** deterministicamente.
- Verifique se os documentos indexados contêm a informação correta.
- Confira o portão de qualidade e a similaridade (`SIMILARITY_THRESHOLD`).

---

## Problemas da API

### 401 Unauthorized

**Causa:** `API_AUTH_TOKEN` configurado, mas o header não foi enviado.

**Solução:**
```bash
curl -H "X-API-Token: SEU_TOKEN" http://localhost:9000/api/models
```

### 409 Conflict ao indexar

**Causa:** já existe um job de indexação em andamento.

**Solução:** aguarde concluir ou cancele via `POST /api/index/cancel/{job_id}`.

### 503 Chatbot não inicializado

**Causa:** falha no startup (Ollama indisponível, modelos não carregados).

**Solução:** verifique os logs e o estado do Ollama.

---

## Problemas do Supervisord (Linux)

| Sintoma | Causa / Solução |
|---|---|
| `Error: .ini file does not include supervisorctl section` | Rodou `supervisorctl` sem `-c`. Use sempre `-c /etc/supervisor/supervisord.conf` |
| `PermissionError` / `Permission denied` | Socket acessível apenas por root. Use `sudo` |
| `unix:///var/run/supervisor.sock no such file` | Supervisord não está rodando. `sudo systemctl start supervisor` |
| Serviço para em segundos | Veja o log: `sudo supervisorctl -c /etc/supervisor/supervisord.conf tail -f watson` (ex.: Ollama fora do ar, porta 9000 ocupada) |

---

## Problemas de banco vetorial

### Corrupção / necessidade de reset

```bash
python reset_app.py --yes --no-docs   # limpa apenas vetores, preserva documentos
python index.py                       # reindexa do zero
```

---

## Diagnóstico rápido

1. Verifique o estado do Ollama: `curl http://localhost:11434/api/tags`.
2. Verifique o estado da API: `curl http://localhost:9000/api/health`.
3. Consulte os logs: `tail -f logs/ai_agent.log` (ou `LOG_LEVEL=DEBUG`).
4. Teste um documento isolado.

---

## Próximos passos

- [Implantação](deployment.md)
- [Monitoramento](../guides/monitoring.md)

# Integração com Sistemas Externos

Exemplos de consumo da API do Watson em diversas linguagens.

> **Nota:** se `API_AUTH_TOKEN` estiver configurado, inclua o header de autenticação em todas as chamadas (exceto `/api/health`).

---

## Python

```python
import json
import requests

API_URL = "http://localhost:9000"
TOKEN = ""  # preencha se API_AUTH_TOKEN estiver definido

HEADERS = {"Content-Type": "application/json"}
if TOKEN:
    HEADERS["X-API-Token"] = TOKEN


def health():
    r = requests.get(f"{API_URL}/api/health")
    print(r.json())


def ask(question: str, analyze: bool = False):
    r = requests.post(f"{API_URL}/api/chat", json={
        "question": question,
        "analyze": analyze,
    }, headers=HEADERS)
    data = r.json()
    print(data["answer"])
    print(f"Confiança: {data['confidence']:.0%}")
    print(f"Fontes: {[s['title'] for s in data['sources']]}")
    if data.get("conclusions"):
        print("Conclusões:", data["conclusions"])
    return data


def ask_stream(question: str):
    with requests.post(
        f"{API_URL}/api/chat/stream",
        json={"question": question},
        headers=HEADERS,
        stream=True,
    ) as r:
        buffer = ""
        for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
            if not chunk:
                continue
            buffer += chunk
            while "\n\n" in buffer:
                event, buffer = buffer.split("\n\n", 1)
                if event.startswith("data: "):
                    payload = event[6:]
                    if payload == "[DONE]":
                        break
                    elif payload.startswith("{"):
                        meta = json.loads(payload)
                        if meta.get("sources"):
                            print("\nSources:", [s["title"] for s in meta["sources"]])
                    else:
                        print(payload, end="", flush=True)


def upload_and_index(filename: str):
    with open(filename, "rb") as f:
        r = requests.post(f"{API_URL}/api/documents/upload",
                          files={"file": f})
        print("Upload:", r.json())
    r = requests.post(f"{API_URL}/api/index/documents", headers=HEADERS)
    print("Indexação:", r.json())


# Exemplos de uso
health()
ask("Qual o erro E123 da Modelo-X?")
ask_stream("Liste os servidores?")
```

---

## Node.js

```javascript
const API_URL = 'http://localhost:9000';
const TOKEN = ''; // preencha se necessário

const headers = { 'Content-Type': 'application/json' };
if (TOKEN) headers['X-API-Token'] = TOKEN;

// Health check
const health = await fetch(`${API_URL}/api/health`);
console.log(await health.json());

// Consulta RAG
const res = await fetch(`${API_URL}/api/chat`, {
  method: 'POST',
  headers,
  body: JSON.stringify({ question: 'Quais servidores estao cadastrados?' }),
});
const data = await res.json();
console.log(data.answer);
console.log(`Confianca: ${(data.confidence * 100).toFixed(0)}%`);

// Streaming (SSE)
const streamRes = await fetch(`${API_URL}/api/chat/stream`, {
  method: 'POST',
  headers,
  body: JSON.stringify({ question: 'Liste os servidores?' }),
});
const reader = streamRes.body.getReader();
const decoder = new TextDecoder();
let buf = '';
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  const parts = buf.split('\n\n');
  buf = parts.pop() || '';
  for (const part of parts) {
    const payload = part.replace(/^data: /, '');
    if (payload === '[DONE]') continue;
    try {
      const meta = JSON.parse(payload);
      if (meta.content) process.stdout.write(meta.content);
      if (meta.sources) console.log('\nSources:', meta.sources.map(s => s.title));
    } catch { /* ignore */ }
  }
}

// Upload de documento
const fs = require('fs');
const FormData = require('form-data');
const form = new FormData();
form.append('file', fs.createReadStream('contrato.pdf'));
const uploadRes = await fetch(`${API_URL}/api/documents/upload`, {
  method: 'POST',
  body: form,
});
console.log(await uploadRes.json());
```

---

## PHP / Laravel

```php
use Illuminate\Support\Facades\Http;

$apiUrl = 'http://localhost:9000';
$token = ''; // preencha se necessário

// Fazer pergunta (com análise proativa)
$response = Http::withToken($token)
    ->post("$apiUrl/api/chat", [
        'question' => 'Quais licencas estao expirando este mes?',
        'analyze'  => true,
    ]);
$data = $response->json();
$answer = $data['answer'];
$confidence = $data['confidence'];
$conclusions = $data['conclusions'] ?? [];

// Upload de documento
$response = Http::attach(
    'file', file_get_contents(storage_path('app/contrato.pdf')), 'contrato.pdf'
)->post("$apiUrl/api/documents/upload");

// Indexar
Http::post("$apiUrl/api/index/documents");

// Indexação assíncrona + acompanhamento
$job = Http::post("$apiUrl/api/index/async", ['mode' => 'all'])->json();
$jobId = $job['job_id'];
$status = Http::get("$apiUrl/api/index/status/$jobId")->json();
```

---

## cURL

```bash
BASE=http://localhost:9000
TOKEN=""   # preencha se necessário

# Health check (público)
curl -s $BASE/api/health | jq .

# Pergunta simples
curl -s $BASE/api/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Token: $TOKEN" \
  -d '{"question": "Qual o total de instalacoes?"}' \
  | jq '.answer'

# Com fontes e análise proativa
curl -s $BASE/api/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Token: $TOKEN" \
  -d '{"question": "Qual o total?", "analyze": true}' \
  | jq '{answer, confidence, conclusions, sources: [.sources[].title]}'

# Streaming
curl -N -X POST $BASE/api/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Token: $TOKEN" \
  -d '{"question": "Liste os servidores?"}'

# Upload
curl -s -X POST $BASE/api/documents/upload \
  -H "X-API-Token: $TOKEN" \
  -F "file=@documento.pdf" | jq .

# Indexar
curl -s -X POST $BASE/api/index/documents -H "X-API-Token: $TOKEN" | jq .

# Indexação assíncrona
curl -s -X POST $BASE/api/index/async \
  -H "Content-Type: application/json" \
  -H "X-API-Token: $TOKEN" \
  -d '{"mode": "all"}' | jq .
```

---

## Agendamento (cron)

```bash
# Reindexar documentos a cada hora
0 * * * * curl -s -X POST http://localhost:9000/api/index/documents

# Sincronizar Drive + indexar toda madrugada
0 3 * * * curl -s -X POST http://localhost:9000/api/index/async \
  -H "Content-Type: application/json" \
  -d '{"mode": "all", "sync_drive": true}'

# Indexação via CLI (sem servidor)
0 * * * * cd /caminho/watson && /caminho/.venv/bin/python index.py
```

---

## Próximos passos

- [Referência da API](api-reference.md)
- [Implantação](../operations/deployment.md)

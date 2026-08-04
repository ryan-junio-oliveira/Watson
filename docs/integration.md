# Integracao com Sistemas Externos

## Python

```python
import requests

API_URL = "http://localhost:9000"

# Health check
health = requests.get(f"{API_URL}/api/health")
print(health.json())

# Consulta documentos indexados
res = requests.post(f"{API_URL}/api/chat", json={
    "question": "Qual o status do cliente XYZ?",
})
data = res.json()
print(data["answer"])
print(f"Confianca: {data['confidence']:.0%}")
print(f"Fontes: {[s['title'] for s in data['sources']]}")

# Com historico
res = requests.post(f"{API_URL}/api/chat", json={
    "question": "E qual o contato dele?",
    "history": [
        {"role": "user", "content": "Qual o status do cliente XYZ?"},
        {"role": "assistant", "content": "O cliente XYZ esta ativo."},
    ],
})
print(res.json()["answer"])

# Streaming (SSE)
import json
response = requests.post(
    f"{API_URL}/api/chat/stream",
    json={"question": "Liste os servidores?"},
    stream=True,
)
buffer = ""
for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
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
                print(f"Stream concluido: confianca={meta['confidence']}")
            else:
                print(payload, end="", flush=True)

# Upload de documento
with open("relatorio.pdf", "rb") as f:
    res = requests.post(f"{API_URL}/api/documents/upload", files={"file": f})
print(res.json())

# Indexar
res = requests.post(f"{API_URL}/api/index")
print(res.json())

# Limpar vetores
res = requests.post(f"{API_URL}/api/clear/vectorstore")
print(res.json())
```

## Node.js

```javascript
const API_URL = 'http://localhost:9000';

// Health check
const health = await fetch(`${API_URL}/api/health`);
console.log(await health.json());

// Consulta documentos indexados
const res = await fetch(`${API_URL}/api/chat`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ question: 'Quais servidores estao cadastrados?' }),
});
const data = await res.json();
console.log(data.answer);
console.log(`Confianca: ${(data.confidence * 100).toFixed(0)}%`);

// Streaming (SSE)
const streamRes = await fetch(`${API_URL}/api/chat/stream`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
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
      console.log('Stream metadata:', meta);
    } catch {
      process.stdout.write(payload);
    }
  }
}

// Upload de documento
const FormData = require('form-data');
const fs = require('fs');
const form = new FormData();
form.append('file', fs.createReadStream('contrato.pdf'));
const uploadRes = await fetch(`${API_URL}/api/documents/upload`, {
  method: 'POST',
  body: form,
});
console.log(await uploadRes.json());
```

## PHP / Laravel

```php
use Illuminate\Support\Facades\Http;

$apiUrl = 'http://localhost:9000';

// Fazer pergunta
$response = Http::post("$apiUrl/api/chat", [
    'question' => 'Quais licencas estao expirando este mes?',
    'history' => [],
]);
$data = $response->json();
$answer = $data['answer'];
$confidence = $data['confidence'];

// Upload de documento
$response = Http::attach(
    'file', file_get_contents(storage_path('app/contrato.pdf')), 'contrato.pdf'
)->post("$apiUrl/api/documents/upload");

// Indexar
Http::post("$apiUrl/api/index");
```

## cURL

```bash
# Pergunta simples
curl -s http://localhost:9000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Qual o total de instalacoes?"}' \
  | jq '.answer'

# Com fontes e metadata
curl -s http://localhost:9000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Qual o total?"}' \
  | jq '{answer, confidence, sources: [.sources[].title]}'

# Streaming
curl -N -X POST http://localhost:9000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "Liste os servidores?"}'

# Upload
curl -s -X POST http://localhost:9000/api/documents/upload \
  -F "file=@documento.pdf" | jq .

# Indexar
curl -s -X POST http://localhost:9000/api/index | jq .

# Health check
curl -s http://localhost:9000/api/health | jq .
```

## Agendamento (cron)

```bash
# Reindexar tudo a cada hora
0 * * * * curl -X POST http://localhost:9000/api/index

# Reindexar apenas o banco a cada 30 minutos
*/30 * * * * curl -X POST http://localhost:9000/api/index/database

# Reindexar apenas documentos toda madrugada
0 3 * * * curl -X POST http://localhost:9000/api/index/documents

# Indexacao via CLI (sem servidor)
0 * * * * cd /caminho/watson && /caminho/.venv/bin/python index.py
```

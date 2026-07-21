# Integracao com Sistemas Externos

## Python

```python
import requests

API_URL = "http://localhost:9000"

# Health check
health = requests.get(f"{API_URL}/api/health")
print(health.json())

# Fazer pergunta
res = requests.post(f"{API_URL}/api/chat", json={
    "question": "Qual o status do cliente XYZ?",
    "history": [],
})
print(res.json()["answer"])

# Fazer pergunta com historico
res = requests.post(f"{API_URL}/api/chat", json={
    "question": "E qual o contato dele?",
    "history": [
        {"role": "user", "content": "Qual o status do cliente XYZ?"},
        {"role": "assistant", "content": "O cliente XYZ esta ativo."},
    ],
})
print(res.json()["answer"])

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

// Fazer pergunta
const res = await fetch(`${API_URL}/api/chat`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ question: 'Quantos clientes estao ativos?' }),
});
const data = await res.json();
console.log(data.answer);

// Upload de documento (com FormData)
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
$answer = $response->json()['answer'];

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
  | jq .answer

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

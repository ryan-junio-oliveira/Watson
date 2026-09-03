# Instalação

Guia completo para instalar o Watson RAG em **Windows** e **Linux/macOS**.

---

## 1. Pré-requisitos

| Requisito | Versão | Obrigatório |
|---|---|---|
| [Python](https://python.org) | 3.10+ | ✅ Sim |
| [Ollama](https://ollama.com) | recente | ✅ Sim |
| [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) | — | ⚠️ Opcional (PDFs/imagens escaneadas) |

> **Sobre o hardware**: o modelo LLM roda via Ollama. Para respostas rápidas em CPU, recomenda-se um modelo pequeno (ex.: `gemma3:4b`). GPUs aceleram significativamente a geração.

---

## 2. Instalar o Ollama

### Windows

1. Baixe o instalador em <https://ollama.com/download>.
2. Execute e siga o assistente.
3. Baixe um modelo de geração:

```bat
ollama pull gemma3:4b
```

### Linux / macOS

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma3:4b
```

### Verificar o Ollama

```bash
ollama serve            # inicia o servidor (se não estiver rodando)
curl http://localhost:11434/api/tags   # lista modelos disponíveis
```

O servidor Ollama deve estar acessível em `http://localhost:11434` (configurável em `.env`).

---

## 3. Instalar o Tesseract OCR (opcional)

O Tesseract é usado para extrair texto de **imagens** e de **PDFs escaneados**. Se você só trabalha com documentos com texto nativo, pode pular.

### Linux (Debian/Ubuntu)

```bash
sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-eng
```

### Windows

1. Baixe o instalador em <https://github.com/UB-Mannheim/tesseract/wiki>.
2. Instale e anote o caminho (ex.: `C:\Program Files\Tesseract-OCR\tesseract.exe`).
3. Configure `TESSERACT_CMD` no `.env` ou deixe vazio para o padrão `libs/tesseract`.

### Verificar

```bash
tesseract --version
```

---

## 4. Clonar e preparar o projeto

```bash
git clone <seu-repositorio> Watson
cd Watson
```

---

## 5. Instalar dependências

### Via inicializador (recomendado)

**Windows:**
```bat
start.bat
```

**Linux/macOS:**
```bash
./start.sh
```

O script cria o ambiente virtual (`.venv`), instala `requirements.txt`, gera o `.env` a partir do `.env.example` e abre o menu de operações.

### Manualmente

```bash
# Criar e ativar o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt

# Configurar ambiente
cp .env.example .env               # Windows: copy .env.example .env
```

---

## 6. Configurar o `.env`

Abra o `.env` e ajuste ao menos:

```env
OLLAMA_MODEL=gemma3:4b          # modelo de geração baixado no Ollama
GOOGLE_DRIVE_FOLDER_ID=         # (opcional) ID da pasta pública do Drive
API_AUTH_TOKEN=                 # (opcional) token de autenticação da API
```

Consulte a [referência completa de configuração](configuration.md).

---

## 7. Verificar a instalação

```bash
# Listar modelos disponíveis no Ollama (via API do Watson)
python -c "from llm.ollama_client import OllamaClient; print(OllamaClient().list_models())"

# Verificar o Tesseract
python -c "from ingestion.adapters.ocr import verify_tesseract; verify_tesseract()"
```

Se tudo estiver OK, prossiga para o [início rápido](quickstart.md).

---

---

## Próximos passos

Você concluiu a **instalação** (passo 2 da [Jornada](../index.md#jornada-recomendada--do-zero-à-produção)). Continue em:

1. **[Início rápido](quickstart.md)** ← próximo (primeira indexação e pergunta)
2. Depois: [Configuração — Perfis](configuration.md#11-perfis-watson--flash--plus--pro) (Flash/Plus/Pro)

> Dica: use Docker (`docker compose up -d`) para não instalar Python/Ollama/Tesseract manualmente — veja [Implantação](../operations/deployment.md).

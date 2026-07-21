# Instalacao

## 1. Instalar Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:8b
ollama serve
```

## 2. Ambiente Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Tesseract OCR (imagens e PDFs escaneados)

```bash
sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-eng
```

## 4. Verificar instalacao

```bash
python -c "from llm.ollama_client import OllamaClient; c = OllamaClient(); print(c.list_models())"
```

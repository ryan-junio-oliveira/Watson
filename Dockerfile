# Watson RAG - Dockerfile
# Requisito único no host: Docker + Docker Compose
# Ollama roda como serviço separado (docker-compose.yml) — sem Tesseract no host.

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    TOKENIZERS_PARALLELISM=false \
    TRANSFORMERS_NO_ADVISORY_WARNINGS=1 \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/huggingface

WORKDIR /app

# --- Dependências de sistema ---
# tesseract-ocr + por/eng: OCR seletivo (pymupdf renderiza a 200dpi, sem poppler)
# curl: healthcheck; libgl1/libglib2.0-0: runtime do pymupdf/Pillow sem warnings
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-por \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version

# --- Dependências Python (layer cacheado) ---
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# --- Código ---
COPY . .

# Garante diretórios de dados e permissões (também refeito no entrypoint para volumes)
RUN mkdir -p database/chroma database/images documents logs .cache/huggingface \
    && chmod -R u+rw database 2>/dev/null || true \
    && chmod +x docker/entrypoint.sh

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://localhost:9000/api/health/ready || exit 1

ENTRYPOINT ["./docker/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "cli.api:app", "--host", "0.0.0.0", "--port", "9000"]

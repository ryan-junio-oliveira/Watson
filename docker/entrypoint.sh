#!/usr/bin/env bash
set -eu
if [ -n "${BASH_VERSION:-}" ]; then
    set -o pipefail
fi

# Watson RAG - Entrypoint Docker
# Espelha scripts/setup.sh (sem venv/ollama pull que são de host):
# - garante .env, diretórios e permissões de escrita no volume.

ROOT=/app
cd "$ROOT"

# 1. Garantir .env (não sobrescreve se já existe via bind/volume)
if [ ! -f "$ROOT/.env" ]; then
    if [ -f "$ROOT/.env.example" ]; then
        echo "[entrypoint] Criando .env a partir de .env.example..."
        cp "$ROOT/.env.example" "$ROOT/.env"
        # Dentro do compose o Ollama está em http://ollama:11434; se .env ainda
        # aponta para localhost, corrige automaticamente (não quebra host bare-metal).
        if grep -q "OLLAMA_BASE_URL=http://localhost:11434" "$ROOT/.env"; then
            # Só corrige se OLLAMA_BASE_URL não foi injetado via environment do compose
            if [ "${OLLAMA_BASE_URL:-}" = "http://ollama:11434" ] || grep -q "ollama" <<< "${OLLAMA_BASE_URL:-}"; then
                sed -i 's|OLLAMA_BASE_URL=http://localhost:11434|OLLAMA_BASE_URL=http://ollama:11434|' "$ROOT/.env" || true
                echo "[entrypoint] OLLAMA_BASE_URL ajustado para http://ollama:11434"
            fi
        fi
    else
        echo "[entrypoint] AVISO: .env e .env.example não encontrados."
    fi
else
    echo "[entrypoint] .env já existe."
fi

# 2. Garantir METRICS_DB e VISION_MODEL no .env (mesma lógica de setup.sh:85)
if [ -f "$ROOT/.env" ] && ! grep -q "^METRICS_DB=" "$ROOT/.env"; then
    echo "METRICS_DB=database/metrics.db" >> "$ROOT/.env"
    echo "[entrypoint] METRICS_DB adicionado ao .env"
fi
if [ -f "$ROOT/.env" ] && ! grep -q "^VISION_MODEL=" "$ROOT/.env"; then
    echo "VISION_MODEL=moondream" >> "$ROOT/.env"
    echo "[entrypoint] VISION_MODEL adicionado ao .env"
fi

# 3. Garantir diretórios de dados (volumes podem chegar vazios)
mkdir -p "$ROOT/database/chroma" "$ROOT/database/images" "$ROOT/documents" "$ROOT/logs" "$ROOT/.cache/huggingface"

# 4. Permissões de escrita no banco (evita "readonly database" em bind mounts Linux)
if [ -d "$ROOT/database" ]; then
    chmod -R u+rw "$ROOT/database" 2>/dev/null || true
fi

# 5. Info útil
echo "[entrypoint] Watson iniciando..."
echo "  OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://ollama:11434}"
echo "  API_HOST=${API_HOST:-0.0.0.0} API_PORT=${API_PORT:-9000}"

exec "$@"

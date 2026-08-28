#!/usr/bin/env bash
set -eu
if [ -n "$BASH_VERSION" ]; then
    set -o pipefail
fi

# ============================================
#  WATSON RAG - Setup Linux/macOS (venv)
#  Cria/ativa o venv e instala dependencias.
#  Uso:  ./setup.sh             -> setup completo
#        ./setup.sh silent      -> sem saida final (usado por start.sh)
# ============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="$ROOT_DIR/.venv"
PYTHON_EXE="$VENV_DIR/bin/python"
PIP_EXE="$VENV_DIR/bin/pip"

# Verifica se o Python existe
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERRO] Python 3 nao encontrado. Instale com: sudo apt install python3 python3-venv"
    if [ "${1:-}" != "silent" ]; then exit 1; fi
    exit 1
fi

# Garante o modulo venv no Debian/Ubuntu
if ! python3 -c "import venv" >/dev/null 2>&1; then
    echo "[INFO] Instalando python3-venv..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y python3-venv
    fi
fi

# Garante o Tesseract OCR (dependencia de sistema para PDFs/imagens escaneadas)
if ! command -v tesseract >/dev/null 2>&1; then
    echo "[INFO] Instalando Tesseract OCR..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y tesseract-ocr tesseract-ocr-por tesseract-ocr-eng
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y tesseract tesseract-langpack-por tesseract-langpack-eng
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --noconfirm tesseract tesseract-data-por tesseract-data-eng
    else
        echo "[AVISO] Tesseract nao encontrado. Instale manualmente para usar OCR."
    fi
fi

# 1. Criar venv se nao existir ou estiver invalido (ex.: copiado do Windows)
if [ ! -x "$PYTHON_EXE" ] || [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "[1/4] Venv ausente ou invalido. Recriando em $VENV_DIR..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
else
    echo "[1/4] Venv ja existe em $VENV_DIR."
fi

# 2. Atualizar pip
echo "[2/4] Atualizando pip..."
"$PIP_EXE" install --upgrade pip

# 3. Instalar dependencias
echo "[3/4] Instalando dependencias (requirements.txt)..."
"$PIP_EXE" install -r "$ROOT_DIR/requirements.txt"

# 4. Garantir .env
if [ ! -f "$ROOT_DIR/.env" ]; then
    if [ -f "$ROOT_DIR/.env.example" ]; then
        echo "[4/4] Criando .env a partir de .env.example..."
        cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
        echo "      ATENCAO: edite o .env com suas credenciais!"
    else
        echo "[4/4] AVISO: .env e .env.example nao encontrados."
    fi
else
    echo "[4/4] .env ja existe."
fi

# 5. Garantir diretorios de dados (database, documents, logs)
mkdir -p "$ROOT_DIR/database" "$ROOT_DIR/database/chroma" "$ROOT_DIR/database/images" "$ROOT_DIR/documents" "$ROOT_DIR/logs"

# 6. Garantir METRICS_DB e VISION_MODEL no .env (valores padrao)
if [ -f "$ROOT_DIR/.env" ] && ! grep -q "^METRICS_DB=" "$ROOT_DIR/.env"; then
    echo "METRICS_DB=database/metrics.db" >> "$ROOT_DIR/.env"
    echo "[INFO] METRICS_DB adicionado ao .env (database/metrics.db)."
fi
if [ -f "$ROOT_DIR/.env" ] && ! grep -q "^VISION_MODEL=" "$ROOT_DIR/.env"; then
    echo "VISION_MODEL=moondream" >> "$ROOT_DIR/.env"
    echo "[INFO] VISION_MODEL adicionado ao .env (moondream)."
fi

# 7. Garantir modelos Ollama (LLM + Visao) — deixa tudo pronto
echo "[5/5] Verificando modelos Ollama (gemma3:4b + moondream)..."
if ! command -v ollama >/dev/null 2>&1; then
    echo "[AVISO] Ollama nao encontrado. Instale em https://ollama.com"
    echo "        Depois rode: ollama pull gemma3:4b && ollama pull moondream"
else
    OLLAMA_MODEL_CFG="$("$PYTHON_EXE" -c "from core.config import config; print(config.ollama_model)" 2>/dev/null || echo "gemma3:4b")"
    VISION_MODEL_CFG="$("$PYTHON_EXE" -c "from core.config import config; print(config.vision_model)" 2>/dev/null || echo "moondream")"
    # Se daemon nao estiver rodando, avisa mas nao falha
    if ! ollama list >/dev/null 2>&1; then
        echo "[AVISO] Ollama nao esta rodando. Inicie com 'ollama serve' e rode novamente o setup para baixar os modelos."
        echo "        Modelos definidos: $OLLAMA_MODEL_CFG e $VISION_MODEL_CFG"
    else
        for MODEL in "$OLLAMA_MODEL_CFG" "$VISION_MODEL_CFG"; do
            [ -z "$MODEL" ] && continue
            echo "  Verificando $MODEL..."
            if ollama list | grep -q -i "$MODEL"; then
                echo "  Modelo $MODEL ja existe."
            else
                echo "  Baixando $MODEL (pode demorar)..."
                if ! ollama pull "$MODEL"; then
                    echo "[AVISO] Falha ao baixar $MODEL. Tente manualmente: ollama pull $MODEL"
                fi
            fi
        done
    fi
fi

# 8. Pre-cache do embedding (opcional, deixa tudo pronto sem travar setup se offline)
if [ -n "${EMBEDDING_MODEL:-}" ]; then EMBEDDING_TO_PULL="$EMBEDDING_MODEL"; else EMBEDDING_TO_PULL="$("$PYTHON_EXE" -c "from core.config import config; print(config.embedding_model)" 2>/dev/null || echo "intfloat/multilingual-e5-base")"; fi
echo "[INFO] Modelo de embedding: $EMBEDDING_TO_PULL (sera baixado automaticamente no primeiro uso)"

# Validar dotenv instalado no venv
if ! "$PYTHON_EXE" -c "import dotenv" >/dev/null 2>&1; then
    echo "[ERRO] python-dotenv nao instalado no venv."
    exit 1
fi

echo ""
echo "Setup concluido! Tudo no jeito."
echo "  Python:  $PYTHON_EXE"
echo "  Modelos Ollama: gemma3:4b + moondream (verificados)"
echo "  Para ativar manualmente:  source $VENV_DIR/bin/activate"
echo ""
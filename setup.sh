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
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
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
"$PIP_EXE" install -r "$SCRIPT_DIR/requirements.txt"

# 4. Garantir .env
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    if [ -f "$SCRIPT_DIR/.env.example" ]; then
        echo "[4/4] Criando .env a partir de .env.example..."
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
        echo "      ATENCAO: edite o .env com suas credenciais!"
    else
        echo "[4/4] AVISO: .env e .env.example nao encontrados."
    fi
else
    echo "[4/4] .env ja existe."
fi

# 5. Garantir diretorio de dados (metrics/chroma/images)
mkdir -p "$SCRIPT_DIR/database"

# 6. Garantir METRICS_DB no .env (valor padrao)
if [ -f "$SCRIPT_DIR/.env" ] && ! grep -q "^METRICS_DB=" "$SCRIPT_DIR/.env"; then
    echo "METRICS_DB=database/metrics.db" >> "$SCRIPT_DIR/.env"
    echo "[INFO] METRICS_DB adicionado ao .env (database/metrics.db)."
fi

# Validar dotenv instalado no venv
if ! "$PYTHON_EXE" -c "import dotenv" >/dev/null 2>&1; then
    echo "[ERRO] python-dotenv nao instalado no venv."
    exit 1
fi

echo ""
echo "Setup concluido!"
echo "  Python:  $PYTHON_EXE"
echo "  Para ativar manualmente:  source $VENV_DIR/bin/activate"
echo ""
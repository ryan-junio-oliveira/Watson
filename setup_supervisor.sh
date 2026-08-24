#!/usr/bin/env bash
set -eu
if [ -n "$BASH_VERSION" ]; then
    set -o pipefail
fi

PROJECT_DIR="/home/administrador/palace/Watson"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_BIN="$VENV_DIR/bin"
CONF_DEST="/etc/supervisor/conf.d/watson.conf"
MAIN_CONF="/etc/supervisor/supervisord.conf"
SOCKET="/var/run/supervisor.sock"

echo "============================================"
echo "  WATSON RAG - Instalador Linux (supervisor)"
echo "============================================"

# 1. Instalar supervisor
echo ""
echo "[1/6] Instalando supervisor..."
if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y supervisor
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y supervisor
elif command -v yum >/dev/null 2>&1; then
    yum install -y supervisor
elif command -v pacman >/dev/null 2>&1; then
    pacman -S --noconfirm supervisor
else
    echo "ERRO: gerenciador de pacotes nao suportado. Instale o supervisor manualmente."
    exit 1
fi

# 2. Instalar Tesseract OCR (dependencia do sistema)
#    suporta o OCR de PDFs/imagens escaneadas no Linux
echo ""
echo "[2/6] Instalando Tesseract OCR..."
if command -v tesseract >/dev/null 2>&1; then
    echo "  Tesseract ja instalado: $(tesseract --version 2>&1 | head -1)"
else
    if command -v apt-get >/dev/null 2>&1; then
        apt-get install -y tesseract-ocr tesseract-ocr-por tesseract-ocr-eng
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y tesseract tesseract-langpack-por tesseract-langpack-eng
    elif command -v pacman >/dev/null 2>&1; then
        pacman -S --noconfirm tesseract tesseract-data-por tesseract-data-eng
    else
        echo "  AVISO: instale o tesseract manualmente no seu gerenciador de pacotes."
    fi
fi

# 3. Garantir que o config principal do supervisor esteja valido
#    (o erro ".ini file does not include supervisorctl section" ocorre
#     quando o arquivo principal nao possui as secoes necessarias)
echo ""
echo "[3/6] Verificando configuracao principal do supervisor..."
if [ ! -f "$MAIN_CONF" ]; then
    echo "  Configuracao principal nao encontrada. Criando..."
    mkdir -p "$(dirname "$MAIN_CONF")"
    cat > "$MAIN_CONF" <<'EOF'
[unix_http_server]
file=/var/run/supervisor.sock
chmod=0770
chown=root:administrador

[supervisord]
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid
childlogdir=/var/log/supervisor
minfds=1024
minprocs=200

[rpcinterface:supervisor]
supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix:///var/run/supervisor.sock

[include]
files=/etc/supervisor/conf.d/*.conf
EOF
elif ! grep -q "^\[supervisorctl\]" "$MAIN_CONF"; then
    echo "  Seção [supervisorctl] ausente. Adicionando..."
    if grep -q "^\[include\]" "$MAIN_CONF"; then
        sed -i '/^\[include\]/i [supervisorctl]\nserverurl=unix:\/\/\/var\/run\/supervisor.sock\n' "$MAIN_CONF"
    else
        cat >> "$MAIN_CONF" <<'EOF'

[supervisorctl]
serverurl=unix:///var/run/supervisor.sock
EOF
    fi
else
    echo "  Configuracao principal OK."
fi

# 4. Criar venv e instalar dependencias (TUDO dentro do venv, nada no sistema)
echo ""
echo "[4/6] Preparando ambiente Python (venv)..."

# Garantir que o modulo venv esteja disponivel no sistema (Debian/Ubuntu)
if ! python3 -c "import venv" >/dev/null 2>&1; then
    echo "  Instalando python3-venv..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get install -y python3-venv
    fi
fi

if [ ! -x "$VENV_BIN/python" ] || [ ! -f "$VENV_BIN/activate" ]; then
    echo "  Venv invalido ou ausente. Recriando em $VENV_DIR..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

# Ativa o venv para todo o restante do script
# shellcheck disable=SC1091
source "$VENV_BIN/activate"
echo "  Venv ativado: $(which python)"

"$VENV_BIN/pip" install --upgrade pip
"$VENV_BIN/pip" install -r "$PROJECT_DIR/requirements.txt"

# Confirma que as dependencias estao no venv
if ! "$VENV_BIN/python" -c "import dotenv" >/dev/null 2>&1; then
    echo "  ERRO: python-dotenv nao instalou no venv. Tente:"
    echo "  source $VENV_BIN/activate && pip install -r $PROJECT_DIR/requirements.txt"
    exit 1
fi
echo "  Dependencias OK (venv)."

# 5. Instalar configuracao do programa watson
echo ""
echo "[5/6] Instalando configuracao do watson..."
if [ -f "$CONF_DEST" ]; then
    cp "$CONF_DEST" "${CONF_DEST}.bak"
    echo "  Backup criado em ${CONF_DEST}.bak"
fi
cp "$PROJECT_DIR/watson-supervisord.conf" "$CONF_DEST"

mkdir -p "$PROJECT_DIR/logs"

# Garantir permissoes de escrita no banco (evita "readonly database" no ChromaDB/SQLite)
if [ -d "$PROJECT_DIR/database" ]; then
    echo "  Garantindo permissoes de escrita no banco..."
    chmod -R u+rw "$PROJECT_DIR/database"
fi

# 6. Iniciar supervisord (se nao estiver rodando) e carregar o programa
echo ""
echo "[6/6] Iniciando supervisord e carregando o watson..."
if [ ! -S "$SOCKET" ]; then
    supervisord -c "$MAIN_CONF"
    sleep 2
fi
supervisorctl -c "$MAIN_CONF" reread
supervisorctl -c "$MAIN_CONF" update
supervisorctl -c "$MAIN_CONF" start watson

echo ""
echo "============================================"
echo "  Instalacao concluida!"
echo ""
echo "  Status:      supervisorctl -c $MAIN_CONF status watson"
echo "  Logs:        tail -f $PROJECT_DIR/logs/supervisor.log"
echo "  API:         http://localhost:9000/docs"
echo "============================================"
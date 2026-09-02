#!/usr/bin/env bash
set -eu
if [ -n "$BASH_VERSION" ]; then
    set -o pipefail
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

API_PORT=$(python3 -c "from core.config import config; print(config.api_port)" 2>/dev/null || echo "9000")

# Config do supervisord (mesmo do setup_supervisor.sh)
MAIN_CONF="/etc/supervisor/supervisord.conf"
CONF_DEST="/etc/supervisor/conf.d/watson.conf"

echo "============================================"
echo "        PARANDO WATSON RAG"
echo "============================================"
echo ""

# ── 1. Tentar parar via supervisord (evita autorestart) ──
SUPERVISOR_STOPPED=false
if command -v supervisorctl >/dev/null 2>&1; then
    # Detecta se supervisord está rodando e tem o programa watson
    if [ -f "$MAIN_CONF" ] || [ -f "$CONF_DEST" ] || [ -S /var/run/supervisor.sock ]; then
        echo "[1/3] Tentando parar via supervisord (supervisorctl stop watson)..."
        # Tenta com -c se existir, senao sem -c
        for CONF in "$MAIN_CONF" "/etc/supervisord.conf" ""; do
            if [ -n "$CONF" ] && [ ! -f "$CONF" ]; then
                continue
            fi
            if [ -n "$CONF" ]; then
                CMD=(supervisorctl -c "$CONF")
            else
                CMD=(supervisorctl)
            fi
            # Verifica se o programa watson existe no supervisord
            if "${CMD[@]}" status watson >/dev/null 2>&1; then
                echo "  -> ${CMD[*]} stop watson"
                if "${CMD[@]}" stop watson 2>&1; then
                    echo "  Programa 'watson' parado via supervisord (STOPPED, nao reinicia sozinho)."
                    SUPERVISOR_STOPPED=true
                    break
                else
                    echo "  Aviso: falha ao parar via ${CMD[*]} stop watson"
                fi
            elif "${CMD[@]}" status watson:watson >/dev/null 2>&1; then
                echo "  -> ${CMD[*]} stop watson:*"
                "${CMD[@]}" stop watson:* 2>&1 || true
                SUPERVISOR_STOPPED=true
                break
            fi
        done
        if [ "$SUPERVISOR_STOPPED" = false ]; then
            echo "  Nenhum programa 'watson' encontrado no supervisord ou supervisord nao esta rodando."
        fi
    else
        echo "[1/3] supervisord nao detectado (sem $MAIN_CONF / socket). Pulando."
    fi
else
    echo "[1/3] supervisorctl nao encontrado. Pulando parada via supervisord."
fi

echo ""
echo "[2/3] Procurando processo na porta $API_PORT..."
PID=$(lsof -ti:"$API_PORT" 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "Encontrado PID: $PID - Encerrando..."
    # Se parou via supervisor, o processo ja deve ter sumido; se ainda existe, mata
    if kill -15 "$PID" 2>/dev/null; then
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            echo "  SIGTERM nao encerrou, usando SIGKILL..."
            kill -9 "$PID" 2>/dev/null || true
        fi
    else
        kill -9 "$PID" 2>/dev/null || true
    fi
    echo "Processo $PID encerrado."
    if [ "$SUPERVISOR_STOPPED" = true ]; then
        echo "  (era fallback - supervisord ja tinha parado o watson)"
    else
        echo "  ATENCAO: se o watson roda via supervisord com autorestart=true, ele pode reiniciar."
        echo "  Use 'sudo supervisorctl -c $MAIN_CONF stop watson' para parar corretamente."
    fi
else
    echo "Nenhum processo encontrado na porta $API_PORT."
fi

echo ""
echo "[3/3] Procurando processos Python do Watson..."
PIDS=$(pgrep -f "uvicorn cli\.api:app" 2>/dev/null || pgrep -f "uvicorn.*api:app" 2>/dev/null || true)
if [ -n "$PIDS" ]; then
    for pid in $PIDS; do
        # Evita matar o proprio grep
        if [ "$pid" != "$$" ]; then
            echo "Encerrando PID: $pid"
            kill -15 "$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
        fi
    done
    sleep 1
    # Confirma se ainda restou algo e força
    REMAIN=$(pgrep -f "uvicorn cli\.api:app" 2>/dev/null || true)
    if [ -n "$REMAIN" ]; then
        for pid in $REMAIN; do
            kill -9 "$pid" 2>/dev/null || true
        done
    fi
    echo "Processos encerrados."
else
    echo "Nenhum processo Python do Watson encontrado."
fi

echo ""
if [ "$SUPERVISOR_STOPPED" = true ]; then
    echo "Operacao concluida. Watson parado via supervisord (para reiniciar: sudo supervisorctl -c $MAIN_CONF start watson)."
else
    echo "Operacao concluida. (se via supervisord, use supervisorctl stop watson para evitar restart automatico)"
fi

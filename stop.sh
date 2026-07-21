#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

API_PORT=$(python3 -c "from config import config; print(config.api_port)" 2>/dev/null || echo "9000")

echo "============================================"
echo "        PARANDO WATSON RAG"
echo "============================================"
echo ""

echo "Procurando processo na porta $API_PORT..."
PID=$(lsof -ti:"$API_PORT" 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "Encontrado PID: $PID - Encerrando..."
    kill -15 "$PID" 2>/dev/null || kill -9 "$PID" 2>/dev/null
    echo "Processo $PID encerrado."
else
    echo "Nenhum processo encontrado na porta $API_PORT."
fi

echo ""
echo "Procurando processos Python do Watson..."
PIDS=$(pgrep -f "uvicorn api:app" 2>/dev/null || true)
if [ -n "$PIDS" ]; then
    for pid in $PIDS; do
        echo "Encerrando PID: $pid"
        kill -15 "$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null
    done
    echo "Processos encerrados."
else
    echo "Nenhum processo Python do Watson encontrado."
fi

echo ""
echo "Operacao concluida."

#!/usr/bin/env bash
set -eu
if [ -n "$BASH_VERSION" ]; then
    set -o pipefail
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Usa o Python do venv se existir, senao cai para python3 do sistema
if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PY="$SCRIPT_DIR/.venv/bin/python"
elif [ -x "$SCRIPT_DIR/venv/bin/python" ]; then
    PY="$SCRIPT_DIR/venv/bin/python"
else
    PY=python3
fi

read -r API_HOST API_PORT <<< "$("$PY" -c "from config import config; print(config.api_host, config.api_port)" 2>/dev/null || echo "0.0.0.0 9000")"

show_menu() {
    clear
    echo "============================================"
    echo "           WATSON RAG - Inicializador"
    echo "============================================"
    echo ""
    echo "Escolha o modo de operacao:"
    echo ""
    echo "  [1] API             - Iniciar servidor FastAPI (http://$API_HOST:$API_PORT)"
    echo "  [2] Prompt          - Chat interativo no terminal"
    echo "  [3] Index           - Indexar documentos locais (documents/) + banco"
    echo "  [4] Drive + Index   - Sincronizar Google Drive e indexar"
    echo "  [5] Drive Sync      - Apenas sincronizar Google Drive"
    echo "  [6] Selecao Drive   - Escolher pastas do Drive p/ indexar"
    echo "  [7] Reset Total     - Limpar banco vetorial e documentos"
    echo "  [8] Watcher         - Reindexar automaticamente ao detectar mudancas"
    echo "  [9] Sair"
    echo ""
}

while true; do
    show_menu
    read -rp "Digite o numero da opcao: " opcao

    case "$opcao" in
        1)
            echo ""
            echo "============================================"
            echo "Iniciando servidor API em http://$API_HOST:$API_PORT"
            echo "Documentacao: http://localhost:$API_PORT/docs"
            echo "============================================"
            echo ""
            "$PY" -m uvicorn api:app --host "$API_HOST" --port "$API_PORT"
            echo ""
            echo "Servidor encerrado."
            read -rp "Pressione Enter para continuar..."
            ;;
        2)
            echo ""
            echo "============================================"
            echo "Iniciando chat interativo..."
            echo "Digite 'exit' ou 'quit' para sair."
            echo "============================================"
            echo ""
            "$PY" app.py
            echo ""
            echo "Chat encerrado."
            read -rp "Pressione Enter para continuar..."
            ;;
        3)
            echo ""
            echo "============================================"
            echo "Indexando documentos locais (documents/) + banco"
            echo "(sem sincronizar o Google Drive - use a opcao 4 para isso)"
            echo "============================================"
            echo ""
            "$PY" index.py
            echo ""
            echo "Indexacao concluida!"
            read -rp "Pressione Enter para continuar..."
            ;;
        4)
            echo ""
            echo "============================================"
            echo "Sincronizando Google Drive e indexando..."
            echo "Isso pode demorar. Sem limite de tempo (CLI)."
            echo "============================================"
            echo ""
            "$PY" drive_index.py
            echo ""
            echo "Concluido!"
            read -rp "Pressione Enter para continuar..."
            ;;
        5)
            echo ""
            echo "============================================"
            echo "Sincronizando Google Drive (somente sync)..."
            echo "============================================"
            echo ""
            "$PY" drive_index.py --sync-only
            echo ""
            echo "Sync concluido!"
            read -rp "Pressione Enter para continuar..."
            ;;
        6)
            echo ""
            echo "============================================"
            echo "Selecao de pastas do Google Drive"
            echo "============================================"
            echo ""
            "$PY" drive_select.py
            echo ""
            read -rp "Pressione Enter para continuar..."
            ;;
        7)
            echo ""
            echo "============================================"
            echo "Reset total - limpar banco vetorial e documentos"
            echo "============================================"
            echo ""
            "$PY" reset_app.py --yes
            echo ""
            echo "Reset concluido!"
            read -rp "Pressione Enter para continuar..."
            ;;
        8)
            echo ""
            echo "============================================"
            echo "Watcher de documentos - reindexacao automatica"
            echo "Monitora documents/ e indexa mudancas."
            echo "Pressione Ctrl+C para parar."
            echo "============================================"
            echo ""
            "$PY" watch.py
            echo ""
            echo "Watcher encerrado."
            read -rp "Pressione Enter para continuar..."
            ;;
        9)
            exit 0
            ;;
        *)
            echo "Opcao invalida! Tente novamente."
            sleep 2
            ;;
    esac
done

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

read -r API_HOST API_PORT <<< "$(python3 -c "from config import config; print(config.api_host, config.api_port)" 2>/dev/null || echo "0.0.0.0 9000")"

show_menu() {
    clear
    echo "============================================"
    echo "           WATSON RAG - Inicializador"
    echo "============================================"
    echo ""
    echo "Escolha o modo de operacao:"
    echo ""
    echo "  [1] API       - Iniciar servidor FastAPI (http://$API_HOST:$API_PORT)"
    echo "  [2] Prompt    - Chat interativo no terminal"
    echo "  [3] Index     - Indexar documentos e sair"
    echo "  [4] Sair"
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
            python3 -m uvicorn api:app --host "$API_HOST" --port "$API_PORT"
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
            python3 app.py
            echo ""
            echo "Chat encerrado."
            read -rp "Pressione Enter para continuar..."
            ;;
        3)
            echo ""
            echo "============================================"
            echo "Indexando documentos..."
            echo "============================================"
            echo ""
            python3 index.py
            echo ""
            echo "Indexacao concluida!"
            read -rp "Pressione Enter para continuar..."
            ;;
        4)
            exit 0
            ;;
        *)
            echo "Opcao invalida! Tente novamente."
            sleep 2
            ;;
    esac
done

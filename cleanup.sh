#!/bin/bash
# Watson Cleanup - Remove todos artefatos e lixo do repositorio
# Uso: chmod +x cleanup.sh && ./cleanup.sh

set -e

echo "============================================"
echo " Watson - Limpeza de artefatos e lixo"
echo "============================================"
echo ""

# Python Bytecode Cache
echo "[1/7] Removendo __pycache__..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
echo "    removido"

# pytest Cache
echo "[2/7] Removendo .pytest_cache..."
rm -rf .pytest_cache 2>/dev/null
echo "    removido"

# Build Artifacts (PyInstaller)
echo "[3/7] Removendo build/..."
rm -rf build 2>/dev/null
echo "    removido"

# Distribution Artifacts
echo "[4/7] Removendo dist/..."
rm -rf dist 2>/dev/null
echo "    removido"

# Logs
echo "[5/7] Removendo logs/..."
rm -rf logs 2>/dev/null
echo "    removido"

# ChromaDB (regeneravel)
echo "[6/7] Removendo database/chroma/..."
rm -rf database/chroma 2>/dev/null
echo "    removido"

# .pyc soltos
echo "[7/7] Removendo .pyc soltos..."
find . -name "*.pyc" -delete 2>/dev/null
echo "    removido"

echo ""
echo "============================================"
echo " Limpeza concluida!"
echo " Revise o git status antes de commit:"
echo "     git status"
echo "============================================"

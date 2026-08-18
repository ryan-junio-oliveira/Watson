#!/bin/bash
# Watson Cleanup - Remove todos artefatos e lixo do repositorio
# Uso: chmod +x cleanup.sh && ./cleanup.sh

echo "============================================"
echo " Watson - Limpeza de artefatos e lixo"
echo "============================================"
echo ""

# Python Bytecode Cache
echo "[1/14] Removendo __pycache__..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "    removido"

# pytest Cache
echo "[2/14] Removendo .pytest_cache..."
rm -rf .pytest_cache 2>/dev/null || true
echo "    removido"

# ruff Cache
echo "[3/14] Removendo .ruff_cache..."
rm -rf .ruff_cache 2>/dev/null || true
echo "    removido"

# mypy Cache
echo "[4/14] Removendo .mypy_cache..."
rm -rf .mypy_cache 2>/dev/null || true
echo "    removido"

# Build Artifacts (PyInstaller)
echo "[5/14] Removendo build/..."
rm -rf build 2>/dev/null || true
echo "    removido"

# Distribution Artifacts
echo "[6/14] Removendo dist/..."
rm -rf dist 2>/dev/null || true
echo "    removido"

# Logs
echo "[7/14] Removendo logs/ e *.log soltos..."
rm -rf logs 2>/dev/null || true
find . -name "*.log" -delete 2>/dev/null || true
echo "    removido"

# ChromaDB (regeneravel)
echo "[8/14] Removendo database/chroma/..."
rm -rf database/chroma 2>/dev/null || true
echo "    removido"

# Cache de Embeddings (regeneravel)
echo "[9/14] Removendo database/embedding_cache.sqlite3..."
rm -f database/embedding_cache.sqlite3 2>/dev/null || true
echo "    removido"

# Imagens OCR (regeneravel)
echo "[10/14] Removendo database/images/..."
rm -rf database/images 2>/dev/null || true
echo "    removido"

# Artefatos de teste (mocks gravando em disco)
echo "[11/14] Removendo MagicMock/..."
rm -rf MagicMock 2>/dev/null || true
echo "    removido"

# .pyc soltos
echo "[12/14] Removendo .pyc soltos..."
find . -name "*.pyc" -delete 2>/dev/null || true
echo "    removido"

# egg-info
echo "[13/14] Removendo *.egg-info..."
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
echo "    removido"

# Cobertura de testes
echo "[14/14] Removendo .coverage e htmlcov/..."
rm -f .coverage 2>/dev/null || true
rm -rf htmlcov 2>/dev/null || true
echo "    removido"

echo ""
echo "============================================"
echo " Limpeza concluida!"
echo " Revise o git status antes de commit:"
echo "     git status"
echo "============================================"
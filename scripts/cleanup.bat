@echo off
title Watson Cleanup - Removendo arquivos lixo
set "ROOT=%~dp0.."
pushd "%ROOT%" >nul
echo ============================================
echo  Watson - Limpeza de artefatos e lixo
echo ============================================
echo.

:: === Python Bytecode Cache ===
echo [1/14] Removendo __pycache__...
for /d /r . %%d in (__pycache__) do @if exist "%%d" (
    rmdir /s /q "%%d" 2>nul
    echo     removido: %%d
)

:: === pytest Cache ===
echo [2/14] Removendo .pytest_cache...
if exist ".pytest_cache" (
    rmdir /s /q ".pytest_cache"
    echo     removido: .pytest_cache
)

:: === ruff Cache ===
echo [3/14] Removendo .ruff_cache...
if exist ".ruff_cache" (
    rmdir /s /q ".ruff_cache"
    echo     removido: .ruff_cache
)

:: === mypy Cache ===
echo [4/14] Removendo .mypy_cache...
if exist ".mypy_cache" (
    rmdir /s /q ".mypy_cache"
    echo     removido: .mypy_cache
)

:: === Build Artifacts (PyInstaller) ===
echo [5/14] Removendo build/...
if exist "build" (
    rmdir /s /q "build"
    echo     removido: build/
)

:: === Distribution Artifacts ===
echo [6/14] Removendo dist/...
if exist "dist" (
    rmdir /s /q "dist"
    echo     removido: dist/
)

:: === Logs ===
echo [7/14] Removendo logs/ e *.log soltos...
if exist "logs" (
    rmdir /s /q "logs"
    echo     removido: logs/
)
del /s /q *.log 2>nul

:: === ChromaDB (regeneravel) ===
echo [8/14] Removendo database/chroma/...
if exist "database\chroma" (
    rmdir /s /q "database\chroma"
    echo     removido: database/chroma/
)

:: === Cache de Embeddings (regeneravel) ===
echo [9/14] Removendo database/embedding_cache.sqlite3...
if exist "database\embedding_cache.sqlite3" (
    del /q "database\embedding_cache.sqlite3"
    echo     removido: database/embedding_cache.sqlite3
)

:: === Imagens OCR (regeneravel) ===
echo [10/14] Removendo database/images/...
if exist "database\images" (
    rmdir /s /q "database\images"
    echo     removido: database/images/
)

:: === Artefatos de teste (mocks gravando em disco) ===
echo [11/14] Removendo MagicMock/...
if exist "MagicMock" (
    rmdir /s /q "MagicMock"
    echo     removido: MagicMock/
)

:: === .pyc soltos ===
echo [12/14] Removendo .pyc soltos...
if exist "*.pyc" del /s /q *.pyc 2>nul

:: === egg-info ===
echo [13/14] Removendo *.egg-info...
for /d /r . %%d in (*.egg-info) do @if exist "%%d" (
    rmdir /s /q "%%d" 2>nul
    echo     removido: %%d
)

:: === Cobertura de testes ===
echo [14/14] Removendo .coverage e htmlcov/...
if exist ".coverage" (
    del /q ".coverage"
    echo     removido: .coverage
)
if exist "htmlcov" (
    rmdir /s /q "htmlcov"
    echo     removido: htmlcov/
)

echo.
echo ============================================
echo  Limpeza concluida!
echo  Revise o git status antes de commit:
echo     git status
echo ============================================
pause
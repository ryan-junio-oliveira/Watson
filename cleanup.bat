@echo off
title Watson Cleanup - Removendo arquivos lixo
echo ============================================
echo  Watson - Limpeza de artefatos e lixo
echo ============================================
echo.

:: === Python Bytecode Cache ===
echo [1/7] Removendo __pycache__...
for /d /r . %%d in (__pycache__) do @if exist "%%d" (
    rmdir /s /q "%%d" 2>nul
    echo     removido: %%d
)

:: === pytest Cache ===
echo [2/7] Removendo .pytest_cache...
if exist ".pytest_cache" (
    rmdir /s /q ".pytest_cache"
    echo     removido: .pytest_cache
)

:: === Build Artifacts (PyInstaller) ===
echo [3/7] Removendo build/...
if exist "build" (
    rmdir /s /q "build"
    echo     removido: build/
)

:: === Distribution Artifacts ===
echo [4/7] Removendo dist/...
if exist "dist" (
    rmdir /s /q "dist"
    echo     removido: dist/
)

:: === Logs ===
echo [5/7] Removendo logs/...
if exist "logs" (
    rmdir /s /q "logs"
    echo     removido: logs/
)

:: === ChromaDB (regeneravel) ===
echo [6/7] Removendo database/chroma/...
if exist "database\chroma" (
    rmdir /s /q "database\chroma"
    echo     removido: database/chroma/
)

:: === .pyc soltos ===
echo [7/7] Removendo .pyc soltos...
if exist "*.pyc" del /s /q *.pyc 2>nul

echo.
echo ============================================
echo  Limpeza concluida!
echo  Revise o git status antes de commit:
echo     git status
echo ============================================
pause

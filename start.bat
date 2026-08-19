@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion
title Watson RAG

:: Chamar setup automatico (sem pausa) para garantir venv + dependencias
call "%~dp0setup.bat" silent
if errorlevel 1 exit /b 1

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

for /f "tokens=1,2" %%a in ('"%PYTHON_EXE%" -c "from config import config; print(config.api_host, config.api_port)"' 2^>nul) do (
    set API_HOST=%%a
    set API_PORT=%%b
)
if "%API_HOST%"=="" set API_HOST=0.0.0.0
if "%API_PORT%"=="" set API_PORT=9000

:menu
cls
echo ============================================
echo           WATSON RAG - Inicializador
echo ============================================
echo.
echo Escolha o modo de operacao:
echo.
echo  [1] API             - Iniciar servidor FastAPI (http://%API_HOST%:%API_PORT%)
echo  [2] Prompt          - Chat interativo no terminal
echo  [3] Index           - Indexar documentos locais (documents/) + banco
echo  [4] Drive + Index   - Sincronizar Google Drive e indexar
echo  [5] Drive Sync      - Apenas sincronizar Google Drive
echo  [6] Selecao Drive   - Escolher pastas do Drive p/ indexar
echo  [7] Reset Total     - Limpar banco vetorial e documentos
echo  [8] Watcher         - Reindexar automaticamente ao detectar mudancas
echo  [9] Sair
echo.
set /p opcao="Digite o numero da opcao: "

if "%opcao%"=="1" goto api
if "%opcao%"=="2" goto prompt
if "%opcao%"=="3" goto index
if "%opcao%"=="4" goto drive_index
if "%opcao%"=="5" goto drive_sync
if "%opcao%"=="6" goto drive_select
if "%opcao%"=="7" goto reset
if "%opcao%"=="8" goto watch
if "%opcao%"=="9" exit /b 0
echo Opcao invalida! Tente novamente.
timeout /t 2 >nul
goto menu

:api
echo.
echo ============================================
echo Iniciando servidor API em http://%API_HOST%:%API_PORT%
echo Documentacao: http://localhost:%API_PORT%/docs
echo ============================================
echo.
"%PYTHON_EXE%" -m uvicorn api:app --host %API_HOST% --port %API_PORT%
echo.
echo Servidor encerrado.
pause
goto menu

:prompt
echo.
echo ============================================
echo Iniciando chat interativo...
echo Digite 'exit' ou 'quit' para sair.
echo ============================================
echo.
"%PYTHON_EXE%" app.py
echo.
echo Chat encerrado.
pause
goto menu

:index
echo.
echo ============================================
echo Indexando documentos locais (documents/) + banco
echo (sem sincronizar o Google Drive - use a opcao 4 para isso)
echo ============================================
echo.
"%PYTHON_EXE%" index.py
echo.
echo Indexacao concluida!
pause
goto menu

:drive_index
echo.
echo ============================================
echo Sincronizando Google Drive e indexando...
echo Isso pode demorar. Sem limite de tempo (CLI).
echo ============================================
echo.
"%PYTHON_EXE%" drive_index.py
echo.
echo Concluido!
pause
goto menu

:drive_sync
echo.
echo ============================================
echo Sincronizando Google Drive (somente sync)...
echo ============================================
echo.
"%PYTHON_EXE%" drive_index.py --sync-only
echo.
echo Sync concluido!
pause
goto menu

:reset
echo.
echo ============================================
echo Reset total - limpar banco vetorial e documentos
echo ============================================
echo.
"%PYTHON_EXE%" reset_app.py --yes
echo.
echo Reset concluido!
pause
goto menu

:drive_select
echo.
echo ============================================
echo Selecao de pastas do Google Drive
echo ============================================
echo.
"%PYTHON_EXE%" drive_select.py
echo.
pause
goto menu

:watch
echo.
echo ============================================
echo Watcher de documentos - reindexacao automatica
echo Monitora documents/ e indexa mudancas.
echo Pressione Ctrl+C para parar.
echo ============================================
echo.
"%PYTHON_EXE%" watch.py
echo.
echo Watcher encerrado.
pause
goto menu
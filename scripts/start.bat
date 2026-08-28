@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion
title Watson RAG
:: Ops esta em ops/ -> ROOT eh um nivel acima
set "ROOT=%~dp0.."
pushd "%ROOT%" >nul
set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"

:: Chamar setup automatico (sem pausa) para garantir venv + dependencias
:: Loga saida do setup para diagnostico se falhar
call "%ROOT%\ops\setup.bat" silent
if errorlevel 1 (
    echo.
    echo [ERRO] O setup falhou. Veja as mensagens acima.
    echo Para resolver, rode manualmente:  "%ROOT%\ops\setup.bat"
    echo.
    echo Tentando continuar mesmo assim para mostrar o menu...
    pause
)

:: Host/porta para exibicao do menu. O uvicorn/app.py leem o .env por conta
:: propria, entao aqui usamos apenas valores informativos (robusto no Windows).
set "API_HOST=0.0.0.0"
set "API_PORT=9000"

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
"%PYTHON_EXE%" -m uvicorn cli.api:app --host %API_HOST% --port %API_PORT%
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
"%PYTHON_EXE%" cli\app.py
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
"%PYTHON_EXE%" cli\index.py
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
"%PYTHON_EXE%" cli\drive_index.py
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
"%PYTHON_EXE%" cli\drive_index.py --sync-only
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
"%PYTHON_EXE%" cli\reset_app.py --yes
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
"%PYTHON_EXE%" cli\drive_select.py
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
"%PYTHON_EXE%" cli\watch.py
echo.
echo Watcher encerrado.
pause
goto menu
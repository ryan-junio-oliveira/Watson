@echo off
chcp 65001 >nul 2>nul
title Watson RAG

for /f "tokens=1,2" %%a in ('python -c "from config import config; print(config.api_host, config.api_port)"' 2^>nul) do (
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
echo  [1] API       - Iniciar servidor FastAPI (http://%API_HOST%:%API_PORT%)
echo  [2] Prompt    - Chat interativo no terminal
echo  [3] Index     - Indexar documentos e sair
echo  [4] Sair
echo.
set /p opcao="Digite o numero da opcao: "

if "%opcao%"=="1" goto api
if "%opcao%"=="2" goto prompt
if "%opcao%"=="3" goto index
if "%opcao%"=="4" exit /b 0
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
python -m uvicorn api:app --host %API_HOST% --port %API_PORT%
echo.
echo Servidor encerrado.
pause
exit /b 0

:prompt
echo.
echo ============================================
echo Iniciando chat interativo...
echo Digite 'exit' ou 'quit' para sair.
echo ============================================
echo.
python app.py
echo.
echo Chat encerrado.
pause
exit /b 0

:index
echo.
echo ============================================
echo Indexando documentos...
echo ============================================
echo.
python index.py
echo.
echo Indexacao concluida!
pause
exit /b 0

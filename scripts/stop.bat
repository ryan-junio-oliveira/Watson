@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion
title Watson RAG - Parar
set "ROOT=%~dp0.."
pushd "%ROOT%" >nul
set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

:: Chamar setup automatico (sem pausa) para garantir venv
call "%ROOT%\scripts\setup.bat" silent
if errorlevel 1 exit /b 1

for /f "tokens=1,2" %%a in ('"%PYTHON_EXE%" -c "from core.config import config; print(config.api_host, config.api_port)"' 2^>nul) do (
    set API_HOST=%%a
    set API_PORT=%%b
)
if "%API_PORT%"=="" set API_PORT=9000

echo ============================================
echo        PARANDO WATSON RAG
echo ============================================
echo.

:: ── 1. Tentar parar via servico Windows (evita restart do servico) ──
echo [1/3] Verificando servico Windows WatsonRAG...
sc query WatsonRAG >nul 2>nul
if %errorlevel% equ 0 (
    echo   Servico WatsonRAG encontrado. Tentando parar...
    :: Tenta via service.py primeiro (graceful)
    if exist "%ROOT%\cli\service.py" (
        "%PYTHON_EXE%" "%ROOT%\cli\service.py" stop 2>nul
    )
    :: Fallback via sc / net
    sc stop WatsonRAG >nul 2>nul
    net stop WatsonRAG >nul 2>nul
    timeout /t 3 >nul 2>nul
    sc query WatsonRAG | findstr /i "STOPPED" >nul 2>nul
    if !errorlevel! equ 0 (
        echo   Servico WatsonRAG parado.
    ) else (
        echo   Aviso: servico ainda nao esta STOPPED (pode estar em STOP_PENDING).
        sc query WatsonRAG
    )
) else (
    echo   Servico WatsonRAG nao instalado. Pulando.
)

echo.
echo [2/3] Procurando processo na porta %API_PORT%...
set PID=
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%API_PORT% " ^| findstr LISTENING' 2^>nul) do (
    set PID=%%p
)
if not "%PID%"=="" (
    echo Encontrado PID: %PID% - Encerrando...
    taskkill /F /PID %PID% >nul 2>nul
    if %errorlevel% equ 0 (echo Processo %PID% encerrado.) else (echo Erro ao encerrar processo %PID% - pode ja ter sido parado pelo servico.)
) else (
    echo Nenhum processo encontrado na porta %API_PORT%.
)

echo.
echo [3/3] Procurando processos Python do Watson via PowerShell...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn|cli\.api:app|watson' -and $_.CommandLine -notmatch 'stop\.bat' } | ForEach-Object { Write-Host 'Encerrando PID:' $_.ProcessId '(' $_.CommandLine ')'; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host 'OK' }" 2>nul

echo.
echo Operacao concluida. Se rodava como servico, use 'python cli\service.py start' ou 'sc start WatsonRAG' para reiniciar.
pause

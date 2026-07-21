@echo off
chcp 65001 >nul 2>nul
title Watson RAG - Parar

for /f "tokens=1,2" %%a in ('python -c "from config import config; print(config.api_host, config.api_port)"' 2^>nul) do (
    set API_HOST=%%a
    set API_PORT=%%b
)
if "%API_PORT%"=="" set API_PORT=9000

echo ============================================
echo        PARANDO WATSON RAG
echo ============================================
echo.

echo Procurando processo na porta %API_PORT%...
set PID=
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%API_PORT% " ^| findstr LISTENING' 2^>nul) do (
    set PID=%%p
)
if not "%PID%"=="" (
    echo Encontrado PID: %PID% - Encerrando...
    taskkill /F /PID %PID% >nul 2>nul
    if %errorlevel% equ 0 (echo Processo %PID% encerrado.) else (echo Erro ao encerrar processo %PID%.)
) else (
    echo Nenhum processo encontrado na porta %API_PORT%.
)

echo.
echo Procurando processos Python do Watson via PowerShell...
powershell -Command "Get-Process python* | Where-Object { $_.CommandLine -match 'uvicorn|watson|api:app' } | ForEach-Object { Write-Host 'Encerrando PID:' $_.Id; Stop-Process -Id $_.Id -Force; Write-Host 'OK' }" 2>nul

echo.
echo Operacao concluida.
pause

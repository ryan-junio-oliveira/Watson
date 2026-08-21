@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion

:: ============================================
::  WATSON RAG - Setup Windows (venv)
::  Cria/ativa o venv e instala dependencias.
::  Uso:  setup.bat            -> setup completo com pausa
::        call setup.bat silent -> sem pausa (usado por outros scripts)
:: ============================================

set "VENV_DIR=.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

:: Verifica se o Python existe no sistema
where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH. Instale o Python 3 e marque "Add to PATH".
    if not "%~1"=="silent" pause
    exit /b 1
)

:: 1. Criar venv se nao existir
if not exist "%PYTHON_EXE%" (
    echo [1/4] Criando venv em %VENV_DIR%...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERRO] Falha ao criar venv. Verifique a instalacao do Python.
        if not "%~1"=="silent" pause
        exit /b 1
    )
) else (
    echo [1/4] Venv ja existe em %VENV_DIR%.
)

:: 2. Atualizar pip (via python -m pip para nao travar o pip.exe em uso no Windows)
echo [2/4] Atualizando pip...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [AVISO] Nao foi possivel atualizar o pip. Continuando com a versao atual...
)

:: 3. Instalar dependencias
echo [3/4] Instalando dependencias (requirements.txt)...
"%PYTHON_EXE%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    if not "%~1"=="silent" pause
    exit /b 1
)

:: 4. Garantir .env
if not exist ".env" (
    if exist ".env.example" (
        echo [4/4] Criando .env a partir de .env.example...
        copy ".env.example" ".env" >nul
        echo       ATENCAO: edite o .env com suas credenciais!
    ) else (
        echo [4/4] AVISO: .env e .env.example nao encontrados.
    )
) else (
    echo [4/4] .env ja existe.
)

:: 5. Garantir diretorio de dados (metrics/chroma/images)
if not exist "database" mkdir "database"

:: 6. Garantir METRICS_DB no .env (valor padrao)
if exist ".env" (
    findstr /B /C:"METRICS_DB=" ".env" >nul 2>nul
    if errorlevel 1 (
        echo [INFO] Adicionando METRICS_DB ao .env
        echo METRICS_DB=database/metrics.db>> ".env"
    )
)

:: Validar dotenv instalado no venv
"%PYTHON_EXE%" -c "import dotenv" >nul 2>nul
if errorlevel 1 (
    echo [ERRO] python-dotenv nao instalado no venv.
    if not "%~1"=="silent" pause
    exit /b 1
)

echo.
echo Setup concluido!
echo   Python:  %PYTHON_EXE%
echo   Para ativar manualmente:  %VENV_DIR%\Scripts\activate
echo.
if not "%~1"=="silent" pause
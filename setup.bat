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

:: 5. Garantir diretorios de dados (database, documents, logs)
if not exist "database" mkdir "database"
if not exist "database\chroma" mkdir "database\chroma"
if not exist "database\images" mkdir "database\images"
if not exist "documents" mkdir "documents"
if not exist "logs" mkdir "logs"

:: 6. Garantir METRICS_DB no .env (valor padrao)
if exist ".env" (
    findstr /B /C:"METRICS_DB=" ".env" >nul 2>nul
    if errorlevel 1 (
        echo [INFO] Adicionando METRICS_DB ao .env
        echo METRICS_DB=database/metrics.db>> ".env"
    )
)

:: 6b. Garantir VISION_MODEL padrao no .env
if exist ".env" (
    findstr /B /C:"VISION_MODEL=" ".env" >nul 2>nul
    if errorlevel 1 (
        echo [INFO] Adicionando VISION_MODEL padrao ao .env
        echo VISION_MODEL=qwen2.5vl>> ".env"
    )
)

:: 7. Garantir modelos Ollama (LLM + Visao) — deixa tudo pronto
echo [5/5] Verificando modelos Ollama (gemma3:4b + qwen2.5vl)...
where ollama >nul 2>nul
if errorlevel 1 (
    echo [AVISO] Ollama nao encontrado no PATH. Instale em https://ollama.com
    echo         Depois rode:  ollama pull gemma3:4b ^&^& ollama pull qwen2.5vl
) else (
    :: Lê modelos do .env via Python do venv (robusto a mudancas no .env.example)
    for /f "delims=" %%A in ('"%PYTHON_EXE%" -c "from config import config; print(config.ollama_model)" 2^>nul') do set "OLLAMA_MODEL_CFG=%%A"
    for /f "delims=" %%A in ('"%PYTHON_EXE%" -c "from config import config; print(config.vision_model)" 2^>nul') do set "VISION_MODEL_CFG=%%A"
    if not defined OLLAMA_MODEL_CFG set "OLLAMA_MODEL_CFG=gemma3:4b"
    if not defined VISION_MODEL_CFG set "VISION_MODEL_CFG=qwen2.5vl"
    :: Tenta listar (se daemon nao estiver rodando, avisa mas nao falha o setup)
    ollama list >nul 2>nul
    if errorlevel 1 (
        echo [AVISO] Ollama nao esta rodando. Inicie com 'ollama serve' e rode novamente o setup para baixar os modelos.
        echo         Modelos definidos: !OLLAMA_MODEL_CFG! e !VISION_MODEL_CFG!
    ) else (
        for %%M in ("!OLLAMA_MODEL_CFG!" "!VISION_MODEL_CFG!") do (
            set "MODEL=%%~M"
            if not "!MODEL!"=="" (
                echo   Verificando !MODEL!...
                ollama list | findstr /I /C:"!MODEL!" >nul 2>nul
                if errorlevel 1 (
                    echo   Baixando !MODEL! (pode demorar)...
                    ollama pull "!MODEL!"
                    if errorlevel 1 echo [AVISO] Falha ao baixar !MODEL!. Tente manualmente: ollama pull !MODEL!
                ) else (
                    echo   Modelo !MODEL! ja existe.
                )
            )
        )
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
echo Setup concluido! Tudo no jeito.
echo   Python:  %PYTHON_EXE%
echo   Modelos Ollama: gemma3:4b + qwen2.5vl (verificados)
echo   Para ativar manualmente:  %VENV_DIR%\Scripts\activate
echo.
if not "%~1"=="silent" pause
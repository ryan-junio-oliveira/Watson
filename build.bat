@echo off
chcp 65001 >nul 2>nul
title Watson RAG - Build

echo ============================================
echo       WATSON RAG - Gerando Executavel
echo ============================================
echo.

:: Verificar se pyinstaller esta instalado
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [ERRO] PyInstaller nao encontrado. Instalando...
    pip install pyinstaller
)

:: Limpar builds anteriores
if exist dist\watson rmdir /s /q dist\watson
if exist build\watson rmdir /s /q build\watson

echo [1/3] Gerando executavel com PyInstaller...
echo.
pyinstaller watson.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao gerar executavel!
    pause
    exit /b 1
)

:: Copiar .env para o diretorio do executavel
echo.
echo [2/3] Copiando arquivos de configuracao...
if not exist dist\watson\.env (
    if exist .env (
        copy .env dist\watson\.env >nul
        echo   .env copiado
    ) else (
        echo   AVISO: .env nao encontrado, copie manualmente
    )
)

:: Copiar documents/ se existir
if exist documents (
    xcopy /E /I /Q documents dist\watson\documents >nul
    echo   documents/ copiado
)

:: Criar diretorios necessarios
if not exist dist\watson\logs mkdir dist\watson\logs
if not exist dist\watson\database\chroma mkdir dist\watson\database\chroma

echo.
echo [3/3] Build concluido!
echo.
echo ============================================
echo   Executavel: dist\watson\watson.exe
echo ============================================
echo.
echo Para instalar como servico (Admin):
echo   dist\watson\watson.exe install
echo   dist\watson\watson.exe start
echo.
echo Para remover o servico:
echo   dist\watson\watson.exe stop
echo   dist\watson\watson.exe remove
echo.
echo Para rodar direto (sem servico):
echo   dist\watson\watson.exe
echo.
pause

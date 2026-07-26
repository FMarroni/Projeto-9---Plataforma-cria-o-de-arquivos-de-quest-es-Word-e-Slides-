@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

title Coruj.IA

set "VENV_DIR=backend\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "PORTA=8000"
set "PYTHON_VERSAO=3.12.7"

echo ============================================
echo   Coruj.IA
echo ============================================
echo.

rem --- Ja esta rodando? So abre o navegador e sai. ---
netstat -ano | findstr /r /c:"127.0.0.1:%PORTA% .*LISTENING" >nul
if %errorlevel%==0 (
    echo Ja esta em execucao - abrindo o navegador...
    start "" "http://127.0.0.1:%PORTA%"
    goto :fim
)

rem --- Primeira vez neste PC: prepara o Python (instala se precisar) e cria o .venv ---
if not exist "%VENV_PY%" (
    echo Primeira execucao neste computador - preparando o ambiente.
    echo Isso pode levar alguns minutos e so acontece uma vez.
    echo.

    call :localizar_python
    if "!PY_LAUNCHER!"=="" (
        call :instalar_python
        call :localizar_python
    )

    if "!PY_LAUNCHER!"=="" (
        echo.
        echo ERRO: nao foi possivel preparar o Python automaticamente
        echo ^(sem conexao com a internet, ou o download/instalacao falhou^).
        echo Instale manualmente em https://www.python.org/downloads/
        echo marcando a opcao "Add python.exe to PATH", e rode este arquivo de novo.
        echo.
        pause
        goto :fim
    )

    echo Usando Python: !PY_LAUNCHER!
    !PY_LAUNCHER! -m venv "%VENV_DIR%"
    if not exist "%VENV_PY%" (
        echo.
        echo ERRO: nao foi possivel criar o ambiente Python ^(.venv^).
        pause
        goto :fim
    )
)

rem --- Garante que as dependencias estao instaladas/atualizadas (rapido se ja estiver tudo certo) ---
echo Verificando dependencias...
"%VENV_PY%" -m pip install --quiet --disable-pip-version-check -r backend\requirements.txt
if not %errorlevel%==0 (
    echo.
    echo ERRO ao instalar as dependencias. Verifique sua conexao com a internet e tente novamente.
    echo.
    pause
    goto :fim
)

rem --- Sobe o servidor numa janela separada (fechar essa janela desliga a plataforma) ---
echo.
echo Iniciando...
start "Coruj.IA - Servidor (NAO FECHE esta janela enquanto estiver usando a plataforma)" ^
    "%VENV_PY%" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port %PORTA%

timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:%PORTA%"

goto :fim


:localizar_python
rem Tenta achar um Python 3 ja utilizavel - no PATH, ou numa instalacao por
rem usuario recem-feita cujo PATH desta sessao ainda nao foi atualizado.
set "PY_LAUNCHER="

where py >nul 2>nul
if !errorlevel!==0 (
    py -3.12 -c "1" >nul 2>nul
    if !errorlevel!==0 (
        set "PY_LAUNCHER=py -3.12"
        goto :eof
    )
    py -3 -c "1" >nul 2>nul
    if !errorlevel!==0 (
        set "PY_LAUNCHER=py -3"
        goto :eof
    )
)

where python >nul 2>nul
if !errorlevel!==0 (
    python -c "1" >nul 2>nul
    if !errorlevel!==0 (
        set "PY_LAUNCHER=python"
        goto :eof
    )
)

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PY_LAUNCHER=%LocalAppData%\Programs\Python\Python312\python.exe"
    goto :eof
)
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        set "PY_LAUNCHER=%%D\python.exe"
        goto :eof
    )
)

goto :eof


:instalar_python
echo Python nao encontrado neste computador.
echo Baixando e instalando automaticamente ^(so para o seu usuario, sem precisar
echo de permissao de administrador^)...
echo.

set "ARQ_INSTALADOR=%TEMP%\python-instalador-corujia.exe"
set "PY_URL=https://www.python.org/ftp/python/%PYTHON_VERSAO%/python-%PYTHON_VERSAO%-amd64.exe"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "PY_URL=https://www.python.org/ftp/python/%PYTHON_VERSAO%/python-%PYTHON_VERSAO%-arm64.exe"

if exist "%ARQ_INSTALADOR%" del "%ARQ_INSTALADOR%" >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -UseBasicParsing -Uri '%PY_URL%' -OutFile '%ARQ_INSTALADOR%' } catch { exit 1 }"

if not exist "%ARQ_INSTALADOR%" (
    echo ERRO: nao foi possivel baixar o instalador do Python.
    goto :eof
)

echo Instalando Python %PYTHON_VERSAO% ^(pode levar 1-2 minutos^)...
start /wait "" "%ARQ_INSTALADOR%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0 Include_pip=1

del "%ARQ_INSTALADOR%" >nul 2>nul
goto :eof


:fim
endlocal

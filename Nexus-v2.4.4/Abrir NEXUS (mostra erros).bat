@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
for %%V in (3.13 3.12 3.11) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
    )
)
if not defined PY set "PY=python"
%PY% -c "import sys; sys.exit(0 if sys.version_info[:2]>=(3,11) else 1)" >nul 2>nul
if not %errorlevel%==0 (
    echo.
    echo O Python encontrado e antigo demais. O NEXUS precisa do Python 3.11 ou mais novo.
    echo Baixe em https://www.python.org/downloads/ marcando "Add python.exe to PATH" e tente de novo.
    echo.
    pause
    exit /b 1
)
echo Usando: %PY%
%PY% -c "import sys; print('Versao do Python:', sys.version.split()[0])"
echo.
%PY% -c "import sounddevice, PyQt6, google.genai, numpy, psutil, requests, cryptography" >nul 2>nul
if not %errorlevel%==0 (
    echo Faltam pacotes do NEXUS neste Python. Instalando agora - pode levar varios minutos...
    echo.
    %PY% instalar_pacotes.py
    echo.
)
echo Abrindo o NEXUS... esta janela mostra qualquer erro, nao feche.
echo.
%PY% main.py
echo.
echo ----- O NEXUS fechou. Se apareceu algum erro acima, copie e mande. -----
pause

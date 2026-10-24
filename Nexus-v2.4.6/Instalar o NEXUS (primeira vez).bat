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
echo Instalando o que o NEXUS precisa. So na primeira vez, pode levar varios minutos...
echo Se algum pacote opcional nao existir para o seu Python, ele e pulado e o resto segue.
echo.
%PY% instalar_pacotes.py
set "RES=%errorlevel%"
echo.
if not "%RES%"=="0" (
    echo ----- FALTOU ALGO ESSENCIAL. Copie o texto desta janela e mande. -----
) else (
    echo ----- Pronto. Agora abra o NEXUS pelo "Abrir NEXUS (mostra erros).bat". -----
)
pause

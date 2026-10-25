@echo off
rem ==========================================================
rem  NEXUS Ultra 2026 - Andre Luiz Lima Menezes
rem  Gera o Nexus.exe nesta pasta (rode uma vez; leva alguns minutos).
rem ==========================================================
chcp 65001 >nul
cd /d "%~dp0"
title Gerando o Nexus.exe

where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado. Instale em https://www.python.org/downloads/
    echo e marque "Add python.exe to PATH" durante a instalacao.
    pause
    exit /b 1
)

echo.
echo [1/4] Preparando o gerador de .exe...
python -m pip install --upgrade --quiet pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 goto erro

echo [2/4] Conferindo as bibliotecas do Nexus...
python -m pip install --quiet -r requirements.txt
if errorlevel 1 goto erro
rem Palavra de ativacao ("Hey Jarvis"): no .exe ela precisa ir junto.
python -m pip install --quiet openwakeword >nul 2>nul

echo [3/4] Gerando o Nexus.exe (pode levar de 3 a 10 minutos)...
python -m PyInstaller nexus.spec --noconfirm --clean --log-level WARN
if errorlevel 1 goto erro

echo [4/4] Colocando o Nexus.exe na pasta do Nexus...
if exist "_internal" rmdir /s /q "_internal"
xcopy /e /i /y /q "dist\Nexus\_internal" "_internal" >nul
copy /y "dist\Nexus\Nexus.exe" "Nexus.exe" >nul
rmdir /s /q build >nul 2>nul
rmdir /s /q dist >nul 2>nul

echo.
echo Pronto! O Nexus.exe esta nesta pasta.
echo Abra com dois cliques. Para um atalho com icone na area de trabalho,
echo use Configuracoes ^> AVANCADO ^> Criar atalho na area de trabalho, dentro do Nexus.
echo.
echo Importante: deixe o Nexus.exe e a pasta _internal aqui, junto do main.py.
pause
exit /b 0

:erro
echo.
echo Algo deu errado. Veja a mensagem acima.
echo Dica: rode "python setup.py" antes, para instalar tudo o que o Nexus usa.
pause
exit /b 1

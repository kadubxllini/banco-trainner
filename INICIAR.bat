@echo off
title Banco de Dados - Trainner RH

pushd "%~dp0"

:: Ativando o suporte a cores no Windows
for /F "delims=#" %%E in ('"prompt #$E# & for %%a in (1) do rem"') do set "ESC=%%E"
set "A=%ESC%[94m"
set "B=%ESC%[38;2;255;255;0m"
set "VERMELHO=%ESC%[91m"
set "RESET=%ESC%[0m"

echo ==========================================
echo Gerenciando Backups de Seguranca...
echo ==========================================
:: Roda o script de backup e limpeza
python backup_manager.py
echo.
echo Backup atualizado e limpo com sucesso!
echo.
echo ==========================================
echo Iniciando o sistema...
echo O navegador vai abrir automaticamente.
echo %A%   ______              %B%_%A%                          
echo %A%  /_  __/%B%_____ %A%____ _ %B%(_)%A%____   %B%____   %A%___   %B%_____
echo %A%   / /  %B%/ ___/%A%/ __ `/%B%/ /%A%/ __ \ %B%/ __ \ %A%/ _ \ %B%/ ___/
echo %A%  / /  %B%/ /   %A%/ /_/ /%B%/ /%A%/ / / /%B%/ / / /%A%/  __/%B%/ /    
echo %A% /_/  %B%/_/    %A%\____/%B%/_/%A%/_/ /_/%B%/_/ /_/ %A%\___/%B%/_/%RESET%
echo.
echo %VERMELHO%ATENCAO: Para desligar o sistema, basta FECHAR ESTA JANELA PRETA!%RESET%
echo ==========================================
echo.

:: Abre o navegador
start http://127.0.0.1:5000

:: Roda o servidor
python app.py

:: Se houver erro (como Python nao instalado), a janela nao fecha sozinha
if %ERRORLEVEL% neq 0 (
    echo.
    echo %VERMELHO%ERRO: O sistema nao pode ser iniciado.%RESET%
    pause
)
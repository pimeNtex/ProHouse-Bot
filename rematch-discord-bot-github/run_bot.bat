@echo off
title Rematch Discord Bot
cls
echo ===================================================
echo             Rematch Discord Bot - Start            
echo ===================================================
echo.
echo [1/2] Verificando e limpando portas/processos antigos...
:: We can use netstat to find if port 55555 is in use, or taskkill any python processes.
:: But to be safe, let's try to terminate any other python process running bot.py.
:: Wmic/powershell command is robust.
powershell -Command "Get-CimInstance Win32_Process -Filter 'Name = ''python.exe''' | Where-Object {$_.CommandLine -like '*bot.py*'} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo [2/2] Iniciando o Discord Bot...
echo.
python bot.py
if %errorlevel% neq 0 (
    echo.
    echo [ERRO] O bot parou com codigo de erro %errorlevel%.
) else (
    echo.
    echo Bot finalizado com sucesso.
)
echo.
echo Pressione qualquer tecla para fechar...
pause >nul

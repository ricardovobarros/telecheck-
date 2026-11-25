@echo off
cd /d "%~dp0"
title Telecheck API - NAO FECHAR
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) { exit 10 } else { exit 0 }"
if %ERRORLEVEL%==10 exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0esconder_da_barra.ps1"
echo.
echo ============================================================
echo  TELECHECK - API EM EXECUCAO
echo  Esta janela e o servidor da API na porta 8080.
echo  NAO FECHE. Se fechar, o Telecheck para de responder.
echo ============================================================
echo.
call .venv\Scripts\activate.bat
uvicorn servidor:app --host 0.0.0.0 --port 8080

@echo off
title InstAI server
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
:loop
".venv\Scripts\python.exe" -m instai.serve
echo.
echo  The server stopped; restarting in 5 seconds ... (close this window to quit)
timeout /t 5 >nul
goto loop

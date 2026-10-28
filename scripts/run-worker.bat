@echo off
title InstAI worker
cd /d "%~dp0.."
set "PYTHONIOENCODING=utf-8"
:loop
".venv\Scripts\python.exe" manage.py run_worker
echo.
echo  The worker stopped; restarting in 5 seconds ... (close this window to quit)
timeout /t 5 >nul
goto loop

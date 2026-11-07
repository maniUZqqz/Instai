@echo off
cd /d "%~dp0.."
set "IVER=?"
if exist VERSION set /p IVER=<VERSION
title InstAI worker v%IVER%
set "PYTHONIOENCODING=utf-8"
:loop
".venv\Scripts\python.exe" manage.py run_worker
echo.
echo  The worker stopped; restarting in 5 seconds ... (close this window to quit)
timeout /t 5 >nul
goto loop

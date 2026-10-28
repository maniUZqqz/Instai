@echo off
title InstAI worker (PC B)
rem ================================================================
rem  InstAI worker for the SECOND computer (PC B). Double-click it.
rem  First run: it prepares Python and the packages, then asks ONCE for
rem  the address of the main PC (shown in InstAI > Production lab > Workers)
rem  and the pairing code. After that it just waits for GPU work and runs it
rem  on THIS computer's GPU (ComfyUI / voice models must be set up here).
rem  Console text is English on purpose (the Windows console garbles Persian).
rem ================================================================
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "INSTAI_WORKER_MODE=1"
if not defined INSTAI_DATA_DIR set "INSTAI_DATA_DIR=%~dp0data-worker"

set "PY="
if not exist ".venv\Scripts\python.exe" goto find_python
".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if not errorlevel 1 goto have_venv
ren ".venv" ".venv-broken-%RANDOM%"
:find_python
for %%V in (3.12 3.13 3.11 3.10) do if not defined PY py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
if not defined PY python -c "import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>nul && set "PY=python"
if not defined PY if exist "tools\python312\python.exe" set "PY=tools\python312\python.exe"
if defined PY goto have_python
echo  [..] Python 3.10-3.13 was not found. Installing Python 3.12 for this user only ...
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\install-python.ps1"
if exist "tools\python312\python.exe" set "PY=tools\python312\python.exe"
if not defined PY goto fail
:have_python
echo  [..] Creating the virtual environment (.venv) ...
%PY% -m venv .venv
if errorlevel 1 goto fail
:have_venv

".venv\Scripts\python.exe" scripts\bootstrap.py --worker
if errorlevel 2 goto fail

echo.
echo  [OK] Starting the worker. Keep this window open (close it to stop the worker).
:loop
".venv\Scripts\python.exe" -m instai.remote.agent
echo.
echo  The worker stopped; restarting in 10 seconds ... (close this window to quit)
timeout /t 10 >nul
goto loop

:fail
echo.
echo  [!!] Could not prepare this computer. Check the internet connection and run START-WORKER.bat again.
if not "%INSTAI_NO_PAUSE%"=="1" pause
exit /b 1

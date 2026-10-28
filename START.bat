@echo off
title InstAI
rem ================================================================
rem  InstAI - the ONLY file you need to run.
rem  Double-click it. It checks and repairs the environment (Python, virtual
rem  environment, packages, ffmpeg, UI, database), prints a short checklist,
rem  starts the server and the worker, and opens the browser.
rem  Running it again when everything is fine takes a few seconds.
rem  Console text is English on purpose (the Windows console garbles Persian).
rem
rem  Optional switches (environment variables): INSTAI_NO_BROWSER=1, INSTAI_NO_PAUSE=1, INSTAI_SKIP_BENCH_PROMPT=1
rem  NOTE: this folder may contain spaces and parentheses; all paths below are relative on purpose.
rem ================================================================
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

echo.
echo  InstAI - starting
echo  -----------------

rem ---- 1. Python 3.10 - 3.13 --------------------------------------
set "PY="
if not exist ".venv\Scripts\python.exe" goto find_python
".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if not errorlevel 1 goto have_venv
echo  [..] The virtual environment is broken (was the folder moved?). Setting it aside and creating a new one ...
ren ".venv" ".venv-broken-%RANDOM%"
:find_python
for %%V in (3.12 3.13 3.11 3.10) do if not defined PY py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
if not defined PY python -c "import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>nul && set "PY=python"
if not defined PY if exist "tools\python312\python.exe" set "PY=tools\python312\python.exe"
if defined PY goto have_python
echo  [..] Python 3.10-3.13 was not found. Installing Python 3.12 for this user only ...
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\install-python.ps1"
if exist "tools\python312\python.exe" set "PY=tools\python312\python.exe"
if defined PY goto have_python
echo  [!!] Could not install Python automatically. Install Python 3.12 from python.org and run START.bat again.
goto fail

:have_python
echo  [OK] Python: %PY%
echo  [..] Creating the virtual environment (.venv) ...
%PY% -m venv .venv
if errorlevel 1 goto venv_failed
:have_venv
if not exist ".venv\Scripts\python.exe" goto venv_failed

rem ---- 2. packages, .env, ffmpeg, UI build, database, checklist ----
".venv\Scripts\python.exe" scripts\bootstrap.py
if errorlevel 2 goto fail

rem ---- 3. already running? ------------------------------------------
".venv\Scripts\python.exe" scripts\wait_ready.py --once
if not errorlevel 1 goto open_browser

rem ---- 4. start server + worker (each restarts itself if it crashes) ---
echo  [..] Starting the server and the worker ...
start "InstAI server" /min cmd /c "scripts\run-server.bat"
start "InstAI worker" /min cmd /c "scripts\run-worker.bat"
".venv\Scripts\python.exe" scripts\wait_ready.py --timeout 90
if errorlevel 1 goto server_failed

rem ---- 5. first run on a real GPU machine: offer the benchmark -------
if "%INSTAI_SKIP_BENCH_PROMPT%"=="1" goto open_browser
".venv\Scripts\python.exe" scripts\bootstrap.py --bench-needed >nul 2>nul
if errorlevel 1 goto open_browser
echo.
echo  This looks like the first run on a machine with a GPU.
echo  The performance benchmark measures one image, one video shot, one voice line and
echo  two or three language models. It takes about 30 minutes and can also be started
echo  later from the System page (button). Nothing is invented: it only times real runs.
choice /c YN /t 30 /d N /m "  Run the benchmark now"
if errorlevel 2 goto open_browser
".venv\Scripts\python.exe" manage.py benchmark --enqueue

:open_browser
for /f "usebackq delims=" %%U in (`".venv\Scripts\python.exe" scripts\wait_ready.py --print-url`) do set "URL=%%U"
echo.
echo  [OK] InstAI is running at %URL%
if not "%INSTAI_NO_BROWSER%"=="1" start "" "%URL%"
echo  To stop it, run STOP.bat. You can close this window.
if not "%INSTAI_NO_PAUSE%"=="1" timeout /t 8 >nul
exit /b 0

:venv_failed
echo  [!!] The virtual environment could not be created. Delete the .venv folder and run START.bat again.
goto fail

:server_failed
echo  [!!] The server did not answer in time. Look at the "InstAI server" window and data\logs\instai.log
goto fail

:fail
echo.
if not "%INSTAI_NO_PAUSE%"=="1" pause
exit /b 1

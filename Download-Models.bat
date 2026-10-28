@echo off
title InstAI - download models and tools
rem ================================================================
rem  InstAI - downloads the models and tools InstAI can use.
rem  Safe to run again: finished files are skipped, broken downloads continue
rem  where they stopped, nothing is ever deleted.
rem
rem    Download-Models.bat                 the default set (asks once)
rem    Download-Models.bat --list          what is missing, with sizes
rem    Download-Models.bat --check         test every link without downloading
rem    Download-Models.bat --only wan22    only one package (see manifests\*.json)
rem    Download-Models.bat --all           also the optional packs (large)
rem  The optional packs can also be installed from a button in Settings.
rem  Log: data\logs\download-models.log
rem ================================================================
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
  echo [!] Python was not found. Run START.bat once; it prepares Python for you.
  pause
  exit /b 1
)
%PY% "%~dp0scripts\download_models.py" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo Finished. Restart START.bat so InstAI sees the new files.
) else (
  echo Finished with problems - read the summary above, or data\logs\download-models.log
)
pause
exit /b %RC%

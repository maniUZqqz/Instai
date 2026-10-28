@echo off
title InstAI - GPU smoke test
rem ================================================================
rem  Runs the GPU smoke test against YOUR real Ollama / ComfyUI / voice engine.
rem  It reports what works (GPU seen, a Persian script from the local model,
rem  one image, one spoken line, VRAM unloading) and skips what is not running.
rem  Nothing is changed or deleted. Start Ollama and ComfyUI first for the full test.
rem ================================================================
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
if not exist ".venv\Scripts\python.exe" (
  echo Run START.bat once first - it prepares everything.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check --default-timeout 60 --retries 5 -r requirements-test.txt
".venv\Scripts\python.exe" -m pytest -m gpu -s -q -p no:cacheprovider tests\test_gpu_smoke.py
echo.
echo Finished. "skipped" means that service was not running - it is not a failure.
if not "%INSTAI_NO_PAUSE%"=="1" pause

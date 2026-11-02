@echo off
title InstAI - GPU test
rem ================================================================
rem  1) GPU CHECK: is the graphics card really used by Ollama and ComfyUI?
rem     It prints a clear verdict:  VERDICT: GPU USED = YES / PARTLY / NO  and WHY.
rem  2) GPU smoke test against YOUR real Ollama / ComfyUI / voice engine.
rem     It reports what works (GPU seen, a Persian script from the local model,
rem     one image, one spoken line, VRAM unloading) and skips what is not running.
rem  Nothing is changed or deleted. Start Ollama and ComfyUI first for the full test.
rem  Note: in Task Manager the default GPU graph is "3D". AI work shows under "Cuda" or
rem  "Compute_0": click the title of a graph and pick it. Or just read the verdict here.
rem ================================================================
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
if not exist ".venv\Scripts\python.exe" (
  echo Run START.bat once first - it prepares everything.
  pause
  exit /b 1
)
echo.
echo ================ 1/2  GPU CHECK ================
".venv\Scripts\python.exe" scripts\gpu_verdict.py
set "GPUCODE=%errorlevel%"
echo.
echo ================ 2/2  SMOKE TEST ================
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check --default-timeout 60 --retries 5 -r requirements-test.txt
".venv\Scripts\python.exe" -m pytest -m gpu -s -q -p no:cacheprovider tests\test_gpu_smoke.py
echo.
echo ================================================================
if "%GPUCODE%"=="0" echo  GPU CHECK RESULT: GPU USED = YES
if "%GPUCODE%"=="1" echo  GPU CHECK RESULT: GPU USED = NO  - read the lines marked [ NO ] and FIX above.
if "%GPUCODE%"=="2" echo  GPU CHECK RESULT: GPU USED = PARTLY or not conclusive - read the [WARN] lines above.
echo  In the smoke test, "skipped" means that service was not running - it is not a failure.
echo ================================================================
if not "%INSTAI_NO_PAUSE%"=="1" pause

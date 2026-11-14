@echo off
rem  Double-click: InstAI starts by itself when you log in to Windows (Autostart-Off.bat switches it off).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  Run START.bat once first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\autostart.py --on
if not "%INSTAI_NO_PAUSE%"=="1" pause

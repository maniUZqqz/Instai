@echo off
rem  Double-click: InstAI stops starting by itself when you log in to Windows (Autostart-On.bat brings it back).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  Run START.bat once first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\autostart.py --off
if not "%INSTAI_NO_PAUSE%"=="1" pause

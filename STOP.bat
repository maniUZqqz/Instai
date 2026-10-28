@echo off
title InstAI - stop
rem Stops the InstAI server and worker windows started by START.bat. Jobs that were running are re-queued
rem automatically the next time the worker starts (their lease expires). Nothing is deleted.
taskkill /fi "WINDOWTITLE eq InstAI server*" /t /f >nul 2>nul
taskkill /fi "WINDOWTITLE eq InstAI worker*" /t /f >nul 2>nul
echo InstAI stopped.
if not "%INSTAI_NO_PAUSE%"=="1" timeout /t 3 >nul
exit /b 0

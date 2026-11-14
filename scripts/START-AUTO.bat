@echo off
rem  What the Windows Startup shortcut runs when you log in (scripts\autostart.py puts it there, see START.bat step 2c):
rem  START.bat without opening the browser and without waiting for a key. It updates, repairs, and starts the server and the worker as usual.
set "INSTAI_NO_BROWSER=1"
set "INSTAI_NO_PAUSE=1"
call "%~dp0..\START.bat"

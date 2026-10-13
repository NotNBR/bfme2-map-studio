@echo off
rem Opens the map viewer on the map you worked on last. Extra arguments go to
rem `mw`, e.g. Map Workshop.cmd view grey
cd /d "%~dp0"
if not exist "local\venv\Scripts\mw.exe" (
    echo The workshop is not set up yet: run Install.cmd first.
    pause
    exit /b 1
)
"local\venv\Scripts\mw.exe" %*
if errorlevel 1 pause

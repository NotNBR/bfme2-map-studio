@echo off
rem Sets up bfme2-map-workshop: its Python environment, the packages, the game
rem data from your BFME2 installation and a Start-menu shortcut. Run it again
rem at any time; it only does what is missing.
setlocal
cd /d "%~dp0"
title bfme2-map-workshop setup

set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python 3.11 or newer is needed: https://www.python.org/downloads/
    echo Tick "Add python.exe to PATH" while installing, then run Install.cmd again.
    pause
    exit /b 1
)

if not exist "local\venv\Scripts\python.exe" (
    echo Creating the Python environment in local\venv ...
    %PY% -m venv local\venv || goto failed
)
rem Install the packages unless they are already installed for this pyproject.toml.
"local\venv\Scripts\python.exe" -c "import hashlib, pathlib, sys; m = pathlib.Path('local/venv/installed.txt'); sys.exit(not (m.exists() and m.read_text() == hashlib.sha256(pathlib.Path('pyproject.toml').read_bytes()).hexdigest() and pathlib.Path('local/venv/Scripts/mw.exe').exists()))"
if errorlevel 1 (
    echo Installing the packages ...
    "local\venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -e ".[render,video]" || goto failed
    "local\venv\Scripts\python.exe" -c "import hashlib, pathlib; pathlib.Path('local/venv/installed.txt').write_text(hashlib.sha256(pathlib.Path('pyproject.toml').read_bytes()).hexdigest())"
)

rem Finds BFME2 (or asks for its folder) and extracts the game data.
"local\venv\Scripts\mw.exe" setup
if errorlevel 1 goto failed

powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Programs') + '\Map Workshop.lnk'); $s.TargetPath = '%~dp0Map Workshop.cmd'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'BFME2 map workshop viewer'; $s.Save()" >nul 2>nul && echo Added "Map Workshop" to the Start menu.

echo.
"local\venv\Scripts\mw.exe" doctor
echo.
echo Done. Open the viewer with "Map Workshop" (Start menu or Map Workshop.cmd).
pause
exit /b 0

:failed
echo.
echo Setup stopped; the message above says why.
pause
exit /b 1

@echo off
rem Double-click to start the app.
cd /d "%~dp0"
set PYC=
where py >nul 2>nul && set PYC=py -3
if not defined PYC (where python >nul 2>nul && set PYC=python)
if not defined PYC goto nopython
%PYC% -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] < (3,16) else 1)"
if errorlevel 1 goto badver

if not exist ".venv\Scripts\python.exe" (
  echo First run: creating environment ^(needs internet, 1-2 minutes^)...
  %PYC% -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 goto fail
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:nopython
echo Python was not found.
echo Install Python 3.12 from https://www.python.org/downloads/windows/
echo IMPORTANT: tick "Add python.exe to PATH" in the installer, then double-click this file again.
pause
exit /b 1

:badver
echo Your Python version is not supported. Install Python 3.12 from https://www.python.org/downloads/windows/ ^(tick "Add python.exe to PATH"^).
pause
exit /b 1

:fail
echo Something failed ^(internet connection? Python version must be 3.10 - 3.15^).
pause
exit /b 1

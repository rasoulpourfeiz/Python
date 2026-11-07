@echo off
rem Double-click to build KardexApp.exe (output: dist\KardexApp\KardexApp.exe). Run on Windows.
cd /d "%~dp0"
set PYC=
where py >nul 2>nul && set PYC=py -3
if not defined PYC (where python >nul 2>nul && set PYC=python)
if not defined PYC goto nopython
%PYC% -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] < (3,16) else 1)"
if errorlevel 1 goto badver

if not exist ".venv\Scripts\python.exe" (
  %PYC% -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements-build.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --name KardexApp main.py
if errorlevel 1 goto fail
echo.
echo Done: %cd%\dist\KardexApp\KardexApp.exe
start "" "dist\KardexApp"
pause
exit /b 0

:nopython
echo Python was not found. Install Python 3.12 from https://www.python.org/downloads/windows/ ^(tick "Add python.exe to PATH"^).
pause
exit /b 1

:badver
echo Your Python version is not supported. Install Python 3.12 from https://www.python.org/downloads/windows/ ^(tick "Add python.exe to PATH"^).
pause
exit /b 1

:fail
echo Build failed. See messages above.
pause
exit /b 1

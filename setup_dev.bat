@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto :install
py -3 -m venv .venv
if not errorlevel 1 goto :install
python -m venv .venv
if errorlevel 1 goto :error
:install
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 goto :error
echo [OK] Development and build environment is ready.
pause
exit /b 0
:error
echo [ERROR] Setup failed. Review the message above.
pause
exit /b 1

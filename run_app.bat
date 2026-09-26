@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_CMD="
python -c "import PySide6, openpyxl" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=python"
if defined PYTHON_CMD goto :launch
py -3 -c "import PySide6, openpyxl" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if defined PYTHON_CMD goto :launch
if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Required packages are unavailable in the system Python. Creating a project environment...
  py -3 -m venv .venv
  if errorlevel 1 python -m venv .venv
  if errorlevel 1 goto :error
)
.venv\Scripts\python.exe -c "import PySide6, openpyxl" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install --upgrade pip
  if errorlevel 1 goto :error
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)
.venv\Scripts\python.exe run_gui.py
if errorlevel 1 goto :error
exit /b 0
:launch
%PYTHON_CMD% run_gui.py
if errorlevel 1 goto :error
exit /b 0
:error
echo [ERROR] RenameWizard could not start. Review the message above.
pause
exit /b 1

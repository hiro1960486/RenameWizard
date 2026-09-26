@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_CMD="
python -c "import PySide6, openpyxl, PyInstaller" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=python"
if defined PYTHON_CMD goto :build
py -3 -c "import PySide6, openpyxl, PyInstaller" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if defined PYTHON_CMD goto :build
if not exist ".venv\Scripts\pyinstaller.exe" call setup_dev.bat
if errorlevel 1 goto :error
set "PYTHON_CMD=.venv\Scripts\python.exe"
:build
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
%PYTHON_CMD% -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --name RenameWizard_v0.5.0_Windows_x64 ^
  --icon assets\renamewizard_icon.ico ^
  --add-data "assets;assets" ^
  run_gui.py
if errorlevel 1 goto :error
if not exist release mkdir release
copy /y "dist\RenameWizard_v0.5.0_Windows_x64.exe" "release\RenameWizard_v0.5.0_Windows_x64.exe" >nul
if errorlevel 1 goto :error
copy /y README.md release\README.md >nul
if errorlevel 1 goto :error
copy /y LICENSE release\LICENSE >nul
if errorlevel 1 goto :error
copy /y docs\test_report.md release\test_report.md >nul
if errorlevel 1 goto :error
if not exist release\assets mkdir release\assets
copy /y assets\renamewizard_icon.png release\assets\renamewizard_icon.png >nul
if errorlevel 1 goto :error
copy /y assets\renamewizard_icon.ico release\assets\renamewizard_icon.ico >nul
if errorlevel 1 goto :error
powershell -NoProfile -Command "$file='RenameWizard_v0.5.0_Windows_x64.exe'; $h=(Get-FileHash ('release\'+$file) -Algorithm SHA256).Hash; Set-Content -Encoding ascii 'release\RenameWizard_v0.5.0_Windows_x64.exe.sha256.txt' ($h+'  '+$file)"
if errorlevel 1 goto :error
(
  echo # RenameWizard v0.5.0 release status
  echo EXE build succeeded. Manually start the EXE on Windows and confirm the application window and icon before publishing.
  echo Release assets, README, LICENSE, and test report were copied to this folder.
) > release\RELEASE_STATUS.md
echo [OK] release\RenameWizard_v0.5.0_Windows_x64.exe is ready. Start it once on Windows before publishing.
pause
exit /b 0
:error
echo [ERROR] Build failed. Review the message above.
pause
exit /b 1

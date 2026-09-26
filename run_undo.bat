@echo off
setlocal

cd /d "%~dp0"

echo.
echo ===== Undo Debug =====
echo Current Folder:
echo %cd%
echo.

py -3 app\undo.py

echo.
echo ExitCode=%errorlevel%
echo.

pause
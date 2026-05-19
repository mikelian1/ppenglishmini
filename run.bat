@echo off
chcp 65001 >nul
cd /d "%~dp0"

python serve.py --ensure-credential
if errorlevel 1 (
  pause
  exit /b 1
)

python serve.py
pause

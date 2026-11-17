@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv，请先运行: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    exit /b 1
)
".venv\Scripts\python.exe" -m outlook_digest %*

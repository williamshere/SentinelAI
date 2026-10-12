@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv313\Scripts\python.exe" (
    echo SentinelAI needs the supported Python 3.13 environment.
    echo Run the setup commands in README.md first.
    pause
    exit /b 1
)

".venv313\Scripts\python.exe" app.py %*

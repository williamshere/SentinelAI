@echo off
setlocal enabledelayedexpansion
title Sentinel AI - Windows Executable Builder

echo =====================================================================
echo           Sentinel AI - Standalone Windows Packaging Pipeline
echo =====================================================================
echo.

:: 1. Navigate to Project Root
cd /d "%~dp0"

:: 2. Check for Virtual Environment
if exist ".venv\Scripts\activate.bat" (
    echo [*] Activating local virtual environment (.venv)...
    call .venv\Scripts\activate.bat
) else if exist "pyside6_env\Scripts\activate.bat" (
    echo [*] Activating local virtual environment (pyside6_env)...
    call pyside6_env\Scripts\activate.bat
) else (
    echo [!] No virtual environment folder detected. Using system Python...
)

:: 3. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH!
    echo Please install Python 3.11+ and ensure 'Add Python to PATH' is checked.
    pause
    exit /b 1
)

:: 4. Verify / Install PyInstaller and dependencies
echo [*] Checking PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Installing PyInstaller and build dependencies...
    pip install pyinstaller Pillow
)

:: 5. Execute Build Script
echo [*] Launching automated build pipeline...
python build_exe.py %*

if %errorlevel% neq 0 (
    echo.
    echo [FAILED] Build process encountered an error. See output above.
    pause
    exit /b %errorlevel%
)

echo.
echo =====================================================================
echo [SUCCESS] Sentinel AI executable build completed!
echo Executable is located at: dist\SentinelAI\SentinelAI.exe
echo =====================================================================
echo.
pause

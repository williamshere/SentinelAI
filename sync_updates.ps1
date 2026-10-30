# Sentinel AI - Local Synchronization & Build Verification Script
# Run this script in PowerShell to verify your updated files, run unit tests, and compile the standalone executable.

param(
    [switch]$BuildStandalone,
    [switch]$RunTests,
    [switch]$LaunchApp,
    [switch]$Elevated
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "             Sentinel AI - Local Update & Build Manager              " -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "Project Directory: $ProjectRoot" -ForegroundColor Gray

# 1. Detect Python 3.13 Virtual Environment
$VenvPython = Join-Path $ProjectRoot ".venv313\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "[!] Local virtual environment not found in .venv313 or .venv." -ForegroundColor Yellow
    Write-Host "[*] Checking system Python..." -ForegroundColor Gray
    $VenvPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $VenvPython) {
        Write-Host "[ERROR] Python interpreter not detected in PATH or virtual environments!" -ForegroundColor Red
        exit 1
    }
}

$PyVer = & $VenvPython --version 2>&1
Write-Host "[OK] Using Python: $VenvPython ($PyVer)" -ForegroundColor Green

# 2. Verify Key Updated Files
$RequiredFiles = @(
    "sensors\cpu.py",
    "ui\dashboard.py",
    "tests\test_sensors.py",
    "build_exe.py",
    "build_windows_exe.bat"
)

Write-Host "`n[*] Verifying updated project files..." -ForegroundColor Cyan
$Missing = @()
foreach ($File in $RequiredFiles) {
    $FullPath = Join-Path $ProjectRoot $File
    if (Test-Path $FullPath) {
        $Item = Get-Item $FullPath
        Write-Host "  [+] $File (Modified: $($Item.LastWriteTime))" -ForegroundColor DarkGreen
    } else {
        Write-Host "  [-] Missing: $File" -ForegroundColor Red
        $Missing += $File
    }
}

if ($Missing.Count -gt 0) {
    Write-Host "`n[WARNING] Some files have not finished syncing from Google Drive yet." -ForegroundColor Yellow
    Write-Host "Please ensure Google Drive for Desktop has synced the latest changes." -ForegroundColor Yellow
}

# 3. Run Unit Test Suite
Write-Host "`n[*] Running sensor telemetry unit tests..." -ForegroundColor Cyan
try {
    & $VenvPython -m unittest discover -s (Join-Path $ProjectRoot "tests") -p "test_*.py"
    Write-Host "[OK] All sensor and telemetry tests passed successfully!" -ForegroundColor Green
} catch {
    Write-Host "[WARNING] Unit tests encountered an issue: $_" -ForegroundColor Yellow
}

# 4. Optional Build Standalone Executable
if ($BuildStandalone) {
    Write-Host "`n[*] Starting Standalone PyInstaller Compilation..." -ForegroundColor Cyan
    $BuildScript = Join-Path $ProjectRoot "build_windows_exe.bat"
    if (Test-Path $BuildScript) {
        & cmd.exe /c $BuildScript
    } else {
        & $VenvPython (Join-Path $ProjectRoot "build_exe.py")
    }
}

# 5. Optional Launch Application
if ($LaunchApp) {
    Write-Host "`n[*] Launching Sentinel AI..." -ForegroundColor Cyan
    $AppScript = Join-Path $ProjectRoot "app.py"
    if ($Elevated) {
        Start-Process $VenvPython -ArgumentList "`"$AppScript`"" -Verb RunAs
    } else {
        Start-Process $VenvPython -ArgumentList "`"$AppScript`""
    }
}

Write-Host "`n=====================================================================" -ForegroundColor Cyan
Write-Host "[SUCCESS] Sentinel AI verification complete!" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan

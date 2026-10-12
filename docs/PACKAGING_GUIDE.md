# Sentinel AI - Standalone Windows Packaging Guide (.exe Pipeline)

This guide details the build and distribution pipeline for packaging Sentinel AI into a standalone Windows executable (`SentinelAI.exe`) using PyInstaller.

---

## 1. Architecture Overview

Sentinel AI relies on a combination of Qt6 UI widgets (`PySide6`), high-performance hardware sensor bindings (`pynvml` for NVIDIA RTX 5070), Windows native management APIs (`wmi`, `win32com`, `pythoncom`), and SQLite persistence.

To guarantee zero dependencies on the target Windows system, the build pipeline bundles:
* **Python Runtime**: Python 3.11/3.14 embedded interpreter.
* **Qt6 Platform Plugins**: Complete PySide6 dynamic libraries, Windows platform plugins (`qwindows.dll`), and styles.
* **Hardware Sensors & COM DLLs**: `nvml.dll` loader, WMI COM interfaces, and process telemetry drivers.
* **Local Assets & Config**: Custom multi-resolution application icon (`assets/sentinel.ico`) and runtime configuration (`config.py`).
* **Persistent Storage**: Automated creation of local `database/` and `logs/` directories relative to the executable root.

---

## 2. Build Prerequisites

Ensure the following tools are installed in your Windows environment:
* Python 3.10+ (Python 3.11 or higher recommended, with `Add Python to PATH` enabled).
* Microsoft Visual C++ Redistributable (2015–2022).
* Virtual environment (`pyside6_env` or `.venv`) with required dependencies:
  ```powershell
  pip install -r Requirements.txt
  ```

---

## 3. Quick-Start Compilation

### Method A: One-Click Batch Script (Recommended)
Simply double-click `build_windows_exe.bat` or run it from PowerShell:
```cmd
build_windows_exe.bat
```
The script will:
1. Detect and activate `.venv` or `pyside6_env`.
2. Verify PyInstaller installation.
3. Automatically render the high-resolution `assets/sentinel.ico` application icon.
4. Execute PyInstaller using `sentinel.spec`.
5. Prepare the output directory layout with writable `database/` and `logs/` folders.

### Method B: Manual Python CLI
Run `build_exe.py` directly with Python:
```powershell
# Standard Directory Distribution (Recommended: fast launch, modular)
python build_exe.py

# Single Portable Executable (--onefile)
python build_exe.py --onefile
```

---

## 4. Distribution Formats: Directory vs. Single File

| Feature | Standard Distribution (`--onedir`, default) | Portable Single File (`--onefile`) |
| :--- | :--- | :--- |
| **Output Location** | `dist/SentinelAI/SentinelAI.exe` | `dist/SentinelAI.exe` |
| **Launch Speed** | **Instant (< 0.5s)** | 3–6s (unpacks ~120MB to `%TEMP%` on each boot) |
| **Hardware Driver Loading** | Direct file access; highest reliability | Unpacks C-extensions dynamically |
| **Database & Logs** | Stored permanently in `dist/SentinelAI/` | Stored persistently next to `.exe` via `config.py` |
| **Best Used For** | Daily desktop use, Windows Auto-Start, pinned taskbar | USB flash drives, quick portable demonstrations |

*Recommendation*: For daily use on your desktop rig (Core i7-12700 + RTX 5070), use the default `--onedir` format in `dist/SentinelAI/`.

---

## 5. Elevated Privileges & Hardware Sensors

Sentinel AI monitors low-level motherboard and CPU thermal telemetry via LibreHardwareMonitor WMI sensors:
* **Running as Administrator**:
  Right-click `SentinelAI.exe` and select **"Run as administrator"**. This grants direct access to CPU core temperature sensors, fan RPM controllers, and package power registers.
* **Running as Standard User**:
  Sentinel AI will operate in graceful fallback mode: CPU utilization and memory metrics operate normally, CPU power is estimated via the Intel Core i7-12700 dynamic TDP curve, and NVIDIA GPU telemetry operates via NVML.

---

## 6. Windows System Integration & Auto-Start

The compiled `SentinelAI.exe` integrates natively with the Windows Shell:
* **System Tray Minimization**: Closing or minimizing the window tucks Sentinel AI into the Windows notification tray.
* **Auto-Start on Boot**: Inside **Settings ⚙️**, clicking **"Enable Auto-Start on Boot"** writes the exact executable path (`dist\SentinelAI\SentinelAI.exe --minimized`) to `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
* **Verbose Diagnostic Console**: If you ever need to inspect background sensor output or debug Ollama / LM Studio connections, run `dist/SentinelAI/Run_Debug_Console.bat`.

---

## 7. Troubleshooting

* **Windows SmartScreen / Antivirus Warning**:
  Because locally compiled binaries do not contain an expensive commercial code-signing certificate, Windows SmartScreen may show *"Windows protected your PC"*. Click **"More info"** -> **"Run anyway"**.
* **Missing `qwindows.dll` Platform Plugin**:
  If moving the `.exe` out of `dist/SentinelAI/`, ensure the entire folder contents (including `_internal/` or Qt plugins) remain together.

"""
verify_project.py - Sentinel AI Project Integrity & Environment Diagnostics.
Verifies directory tree integrity, missing core modules, virtual environment pathing,
hardware sensor dependencies, and Google Drive sync lock issues.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Core required files manifest
CORE_PROJECT_MANIFEST = {
    "Root Configurations": [
        "app.py",
        "config.py",
        "Requirements.txt",
        "pyproject.toml",
        "sentinel.spec",
        "build_exe.py",
        "build_windows_exe.bat",
        "run_sentinel.bat",
        "verify_project.py",
    ],
    "AI Engine (ai/)": [
        "ai/__init__.py",
        "ai/analyzer.py",
        "ai/chat_engine.py",
        "ai/health.py",
        "ai/predictive.py",
        "ai/prompts.py",
        "ai/recommendations.py",
    ],
    "Core Subsystems (core/)": [
        "core/__init__.py",
        "core/autostart.py",
        "core/driver_manager.py",
        "core/game_mode.py",
        "core/utilities.py",
    ],
    "Database (database/)": [
        "database/__init__.py",
        "database/manager.py",
    ],
    "Hardware Sensors (sensors/)": [
        "sensors/__init__.py",
        "sensors/cpu.py",
        "sensors/disk.py",
        "sensors/gpu.py",
        "sensors/ram.py",
        "sensors/storage_health.py",
    ],
    "User Interface (ui/)": [
        "ui/__init__.py",
        "ui/alert_manager.py",
        "ui/chart_widget.py",
        "ui/dashboard.py",
        "ui/theme.py",
    ],
    "Assets & Documentation": [
        "assets/sentinel.ico",
        "docs/PACKAGING_GUIDE.md",
        "docs/security_ideas.md",
    ],
}

REQUIRED_MODULES = [
    ("PySide6", "PySide6", "GUI and Qt6 framework"),
    ("pynvml", "pynvml", "NVIDIA RTX 5070 GPU telemetry"),
    ("psutil", "psutil", "Process and system memory metrics"),
    ("wmi", "wmi", "Windows Hardware WMI sensor queries"),
    ("win32api", "pywin32", "Windows Win32 native APIs"),
    ("win32com", "pywin32", "Windows COM automation"),
    ("pythoncom", "pywin32", "COM threading apartments"),
    ("sqlite3", "sqlite3", "Standard SQLite persistence"),
    ("PyInstaller", "pyinstaller", "Standalone Windows .exe builder"),
    ("PIL", "Pillow", "Native application icon compiler"),
]


def print_banner(title: str):
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def check_environment():
    print_banner("1. Python Environment Diagnostics")
    print(f" Python Executable : {sys.executable}")
    print(f" Python Version    : {sys.version.split()[0]}")
    print(f" Working Directory : {Path.cwd()}")

    is_venv = hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )
    if is_venv:
        print(f" [OK] Virtual Environment Active: {sys.prefix}")
    else:
        print(" [!] WARNING: Running on Global System Python (Not in a venv)!")

    # Check for hardcoded launcher path mismatches
    prefix_path = Path(sys.prefix)
    cwd_path = Path.cwd()
    if is_venv and prefix_path.name in ("pyside6_env", ".venv"):
        if not prefix_path.exists():
            print(f" [CRITICAL] Virtual environment path is broken or moved: {prefix_path}")
        else:
            print(" [OK] Virtual environment path exists locally.")

    # Check for Google Drive syncing path locks
    cwd_str = str(cwd_path).lower()
    if "my drive" in cwd_str or "google drive" in cwd_str:
        print("\n [!] NOTICE: Project is inside a Google Drive synced directory ('My Drive').")
        print("     Google Drive for Desktop actively locks temporary build files (like build\\sentinel\\localpycs).")
        print("     Recommendation: Pause Google Drive sync or add 'build' & 'dist' to ignore list during PyInstaller builds.")


def check_files():
    print_banner("2. Project Directory File Integrity Audit")
    root = Path.cwd()
    all_ok = True
    missing_files = []

    for category, files in CORE_PROJECT_MANIFEST.items():
        print(f"\n --- {category} ---")
        for rel_path in files:
            p = root / rel_path
            if not p.exists():
                print(f" [MISSING]  {rel_path}")
                missing_files.append(rel_path)
                all_ok = False
            elif p.stat().st_size == 0:
                print(f" [EMPTY]    {rel_path} (0 bytes - corrupted)")
                missing_files.append(rel_path)
                all_ok = False
            else:
                size_kb = p.stat().st_size / 1024
                print(f" [PRESENT]  {rel_path:<30} ({size_kb:>6.1f} KB)")

    return all_ok, missing_files


def check_dependencies():
    print_banner("3. Dependency & Sensor Bindings Audit")
    missing_pkgs = []

    for import_name, pip_name, description in REQUIRED_MODULES:
        try:
            __import__(import_name)
            print(f" [INSTALLED] {import_name:<14} ({description})")
        except ImportError:
            print(f" [MISSING]   {import_name:<14} -> Needs: pip install {pip_name} ({description})")
            if pip_name not in missing_pkgs:
                missing_pkgs.append(pip_name)

    return missing_pkgs


def main():
    print("\n" + "#" * 70)
    print("   SENTINEL AI - PROJECT INTEGRITY & ENVIRONMENT VALIDATOR")
    print("#" * 70)

    check_environment()
    files_ok, missing_files = check_files()
    missing_pkgs = check_dependencies()

    print_banner("4. Summary & Actionable Recommendations")

    if not files_ok:
        print(f"\n [!] CRITICAL: Found {len(missing_files)} missing or corrupted file(s):")
        for f in missing_files:
            print(f"     - {f}")
        print("\n -> FIX: Pull or download these files from your Google Drive project repository.")
    else:
        print("\n [SUCCESS] All core project files and directory trees are present and intact!")

    if missing_pkgs:
        print(f"\n [!] Missing Python packages detected: {', '.join(missing_pkgs)}")
        print("\n -> FIX: Run the following command in your active terminal:")
        print(f"     python -m pip install {' '.join(missing_pkgs)}")
    else:
        print(" [SUCCESS] All Python dependencies and sensor bindings are installed!")

    if files_ok and not missing_pkgs:
        print("\n [READY] Your environment is verified. You can launch Sentinel AI using:")
        print("     python app.py")


if __name__ == "__main__":
    main()

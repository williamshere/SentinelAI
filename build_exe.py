"""
build_exe.py - Build Automation Pipeline for Sentinel AI.
Executes PyInstaller packaging, validates environment dependencies, generates
native application icons, and prepares the standalone Windows distribution.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def print_step(title: str):
    print(f"\n{'=' * 65}")
    print(f" [*] {title}")
    print(f"{'=' * 65}")


def ensure_icon(assets_dir: Path) -> Path:
    """Verifies or generates a high-DPI Windows application icon (.ico)."""
    ico_path = assets_dir / "sentinel.ico"
    if ico_path.exists():
        print(f" [OK] Existing icon found: {ico_path}")
        return ico_path

    print(" [*] Generating native multi-resolution Sentinel AI icon...")
    assets_dir.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw

        sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        images = []
        for w, h in sizes:
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # Outer shield
            m = w * 0.08
            sw = w - 2 * m
            sh = h - 2 * m
            outer = [
                (m, m + sh * 0.2),
                (m + sw * 0.5, m),
                (m + sw, m + sh * 0.2),
                (m + sw, m + sh * 0.65),
                (m + sw * 0.5, m + sh),
                (m, m + sh * 0.65),
            ]
            draw.polygon(outer, fill=(2, 132, 199, 255), outline=(56, 189, 248, 255))

            # Inner crest
            im = w * 0.18
            isw = w - 2 * im
            ish = h - 2 * im
            inner = [
                (im, im + ish * 0.2),
                (im + isw * 0.5, im),
                (im + isw, im + ish * 0.2),
                (im + isw, im + ish * 0.65),
                (im + isw * 0.5, im + ish),
                (im, im + ish * 0.65),
            ]
            draw.polygon(inner, fill=(16, 24, 40, 255), outline=(2, 132, 199, 200))

            # Center core
            rad = w * 0.12
            cx, cy = w * 0.5, h * 0.5
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(56, 189, 248, 255))
            images.append(img)

        images[-1].save(ico_path, format="ICO", sizes=sizes)
        print(f" [OK] Generated multi-resolution icon at: {ico_path}")
    except Exception as e:
        print(f" [!] Pillow icon generation skipped ({e}). Executable will use default icon.")

    return ico_path


def check_dependencies():
    """Verifies that PyInstaller and required dependencies are accessible."""
    print_step("Checking Build Dependencies")
    print(f"Python Executable: {sys.executable}")
    print(f"Python Version: {sys.version.split()[0]}")

    try:
        import PyInstaller
        print(f" [OK] PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print(" [!] PyInstaller not detected. Installing via pip...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.4.0"])

    try:
        import PySide6
        print(f" [OK] PySide6 version: {PySide6.__version__}")
    except ImportError:
        print(" [WARNING] PySide6 not installed in current environment!")


def run_build(onefile: bool = False, clean: bool = True):
    """Executes the PyInstaller build."""
    assets_dir = PROJECT_ROOT / "assets"
    ensure_icon(assets_dir)

    spec_file = PROJECT_ROOT / "sentinel.spec"
    if not spec_file.exists():
        raise FileNotFoundError(f"Missing build spec file: {spec_file}")

    print_step("Executing PyInstaller Compilation")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
    ]

    if clean:
        cmd.append("--clean")
    cmd.append("--noconfirm")

    if onefile:
        print(" [*] Target Mode: Single Portable Executable (--onefile)")
        cmd.extend([
            "--onefile",
            "--windowed",
            f"--icon={assets_dir / 'sentinel.ico'}",
            "--name=SentinelAI",
            "app.py",
        ])
    else:
        print(" [*] Target Mode: Standard Directory Distribution (--onedir)")
        cmd.append(str(spec_file))

    print(f"Command: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(PROJECT_ROOT))

    # Post-build packaging adjustments
    dist_dir = PROJECT_ROOT / "dist" / "SentinelAI"
    if dist_dir.exists():
        print_step("Configuring Runtime Directory Layout")
        # Ensure database and logs directories exist for immediate persistence
        (dist_dir / "database").mkdir(exist_ok=True)
        (dist_dir / "logs").mkdir(exist_ok=True)
        if assets_dir.exists():
            shutil.copytree(assets_dir, dist_dir / "assets", dirs_exist_ok=True)

        # Create convenience debug launcher
        debug_bat = dist_dir / "Run_Debug_Console.bat"
        with open(debug_bat, "w") as f:
            f.write("@echo off\n")
            f.write("title Sentinel AI - Verbose Diagnostic Console\n")
            f.write("echo Starting Sentinel AI with console logging enabled...\n")
            f.write("SentinelAI.exe\n")
            f.write("if %errorlevel% neq 0 pause\n")

        print(f" [OK] Writable runtime folders configured in: {dist_dir}")

    print_step("Build Complete")
    exe_target = (
        PROJECT_ROOT / "dist" / "SentinelAI.exe"
        if onefile
        else PROJECT_ROOT / "dist" / "SentinelAI" / "SentinelAI.exe"
    )
    if exe_target.exists():
        size_mb = exe_target.stat().st_size / (1024 * 1024)
        print(f" [SUCCESS] Output Executable: {exe_target}")
        print(f" File Size: {size_mb:.2f} MB")
    else:
        print(f" [SUCCESS] Build completed in: {PROJECT_ROOT / 'dist'}")


def main():
    parser = argparse.ArgumentParser(description="Sentinel AI PyInstaller Packaging Pipeline")
    parser.add_argument("--onefile", action="store_true", help="Compile as a single standalone executable")
    parser.add_argument("--no-clean", action="store_true", help="Skip cleaning temporary build caches")
    args = parser.parse_args()

    check_dependencies()
    run_build(onefile=args.onefile, clean=not args.no_clean)


if __name__ == "__main__":
    main()

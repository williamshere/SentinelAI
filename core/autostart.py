r"""
core/autostart.py - Windows auto-start on boot management for Sentinel AI.
Supports registry integration (HKCU\Software\Microsoft\Windows\CurrentVersion\Run)
with optional --minimized flag to silently launch in the system tray.
"""
import os
import sys
from pathlib import Path

REGISTRY_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "SentinelAI"


def _get_launch_command(app_path: str | Path | None = None, start_minimized: bool = True) -> str:
    """Constructs the shell execution command for Sentinel AI startup."""
    target_path = app_path
    if not target_path:
        # Resolve path to app.py in project root
        target_path = Path(__file__).resolve().parent.parent / "app.py"

    target_path = Path(target_path).resolve()
    minimized_flag = " --minimized" if start_minimized else ""

    # If running as a bundled/frozen executable (PyInstaller)
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"{minimized_flag}'

    # Standard Python script execution
    python_exe = sys.executable
    # Use pythonw.exe on Windows if available to suppress console window popup
    if os.name == "nt":
        pythonw = Path(python_exe).with_name("pythonw.exe")
        if pythonw.exists():
            python_exe = str(pythonw)

    return f'"{python_exe}" "{target_path}"{minimized_flag}'


def is_autostart_enabled() -> bool:
    """Checks whether Sentinel AI is currently registered to launch on Windows startup."""
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY_PATH, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, APP_NAME)
                return True
        except (FileNotFoundError, OSError):
            return False
        except Exception:
            return False
    else:
        # Linux desktop autostart fallback
        desktop_file = Path.home() / ".config" / "autostart" / f"{APP_NAME}.desktop"
        return desktop_file.exists()


def enable_autostart(app_path: str | Path | None = None, start_minimized: bool = True) -> tuple[bool, str]:
    """
    Registers Sentinel AI in the Windows Startup Registry.
    Returns: (success: bool, message: str)
    """
    cmd = _get_launch_command(app_path=app_path, start_minimized=start_minimized)

    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                return True, "Auto-start enabled successfully (launches minimized to tray on startup)."
        except PermissionError:
            return False, "Failed to set auto-start: Permission denied."
        except Exception as e:
            return False, f"Failed to set auto-start: {str(e)}"
    else:
        try:
            autostart_dir = Path.home() / ".config" / "autostart"
            autostart_dir.mkdir(parents=True, exist_ok=True)
            desktop_file = autostart_dir / f"{APP_NAME}.desktop"
            desktop_content = f"""[Desktop Entry]
Type=Application
Exec={cmd}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Sentinel AI
Comment=Sentinel AI Hardware Telemetry and Security
"""
            desktop_file.write_text(desktop_content, encoding="utf-8")
            return True, "Auto-start desktop entry created successfully."
        except Exception as e:
            return False, f"Failed to enable autostart on Linux: {str(e)}"


def disable_autostart() -> tuple[bool, str]:
    """
    Unregisters Sentinel AI from Windows Startup Registry.
    Returns: (success: bool, message: str)
    """
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
                return True, "Auto-start disabled successfully."
        except FileNotFoundError:
            return True, "Auto-start was not enabled."
        except Exception as e:
            return False, f"Failed to remove auto-start: {str(e)}"
    else:
        desktop_file = Path.home() / ".config" / "autostart" / f"{APP_NAME}.desktop"
        if desktop_file.exists():
            try:
                desktop_file.unlink()
                return True, "Auto-start desktop entry removed."
            except Exception as e:
                return False, f"Failed to remove auto-start file: {str(e)}"
        return True, "Auto-start was not enabled."


def toggle_autostart(app_path: str | Path | None = None, start_minimized: bool = True) -> tuple[bool, bool, str]:
    """
    Toggles current auto-start state.
    Returns: (success: bool, is_now_enabled: bool, message: str)
    """
    currently_enabled = is_autostart_enabled()
    if currently_enabled:
        success, msg = disable_autostart()
        return success, False, msg
    else:
        success, msg = enable_autostart(app_path=app_path, start_minimized=start_minimized)
        return success, True, msg

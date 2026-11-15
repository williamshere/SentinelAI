"""
core/utilities.py - System optimization and elevation utilities for Sentinel AI.
Provides working set RAM trimming, safe disk cleanup, and one-click UAC administrator elevation.
"""
import ctypes
import os
import sys
import tempfile
import time
from pathlib import Path


def clean_ram() -> tuple[bool, str, float]:
    """
    Trims process working sets across user processes using the Windows API (EmptyWorkingSet).
    Returns: (success: bool, message: str, mb_freed: float)
    """
    if os.name != "nt":
        return False, "RAM trimming requires Windows.", 0.0

    try:
        import psutil
        mem_before = psutil.virtual_memory().used
        
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        
        # Explicit pointer widths prevent handle truncation on 64-bit Windows.
        from ctypes import wintypes
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
        psapi.EmptyWorkingSet.restype = wintypes.BOOL
        # PROCESS_QUERY_INFORMATION (0x0400) | PROCESS_SET_QUOTA (0x0100)
        flags = 0x0400 | 0x0100
        trimmed_count = 0
        
        for proc in psutil.process_iter(attrs=["pid"]):
            pid = proc.info.get("pid")
            if pid and pid > 4:
                handle = kernel32.OpenProcess(flags, False, pid)
                if handle:
                    try:
                        if psapi.EmptyWorkingSet(handle):
                            trimmed_count += 1
                    finally:
                        kernel32.CloseHandle(handle)
                        
        mem_after = psutil.virtual_memory().used
        bytes_freed = max(0, mem_before - mem_after)
        mb_freed = round(bytes_freed / (1024 * 1024), 1)
        return True, f"Trimmed {trimmed_count} process working sets (~{mb_freed} MB). This does not guarantee faster performance.", mb_freed
    except Exception as e:
        return False, f"Memory optimization encountered an issue: {e}", 0.0


def clean_disk_temp() -> tuple[bool, str, float]:
    """
    Safely prunes temporary cache and scratch files from the %TEMP% directory.
    Returns: (success: bool, message: str, mb_freed: float)
    """
    temp_dir = Path(tempfile.gettempdir())
    bytes_freed = 0
    files_deleted = 0
    
    if not temp_dir.exists():
        return False, "Temp directory not found", 0.0

    cutoff = time.time() - 86400
    for item in temp_dir.glob("*"):
        try:
            # Skip folders, links, and recent files used by active applications.
            if item.is_symlink() or not item.is_file() or item.stat().st_mtime >= cutoff:
                continue
            size = item.stat().st_size
            item.unlink()
            bytes_freed += size
            files_deleted += 1
        except Exception:
            # Safely bypass in-use locked files without interrupting scan
            continue

    mb_freed = round(bytes_freed / (1024 * 1024), 2)
    return True, f"Cleaned {files_deleted} temporary cache items, freeing ~{mb_freed} MB.", mb_freed


def relaunch_as_admin(app_path: str | Path | None = None) -> bool:
    """
    Prompts Windows UAC to restart Sentinel AI with elevated Administrator privileges.
    """
    if os.name != "nt":
        return False
    try:
        script = app_path or str(Path(sys.argv[0]).resolve())
        # Invoke ShellExecuteW with 'runas' to trigger Windows UAC
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            f'"{script}"',
            None,
            1  # SW_SHOWNORMAL
        )
        # ShellExecute returns > 32 on success
        return ret > 32
    except Exception:
        return False

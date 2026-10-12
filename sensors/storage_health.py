"""Low-frequency Windows storage reliability telemetry.

The query is cached because spawning PowerShell repeatedly is expensive.  When
Windows does not expose SMART data, the result explicitly identifies itself as
an unavailable baseline instead of pretending it is a measured value.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

_cached_result: dict[str, Any] | None = None
_last_query = 0.0
CACHE_TTL_SECONDS = 300.0


def _fallback(source: str = "unavailable") -> dict[str, Any]:
    return {
        "model": "Storage SMART unavailable",
        "media_type": "Unknown",
        "health_percent": 0.0,
        "wear_percent": 0.0,
        "tbw_terabytes": 0.0,
        "temperature_c": 0.0,
        "power_on_hours": 0,
        "unsafe_shutdowns": 0,
        "read_errors": 0,
        "write_errors": 0,
        "available": False,
        "source": source,
    }


def get_storage_health(drive_letter: str = "C:", force_refresh: bool = False) -> dict[str, Any]:
    """Return cached Windows reliability data without creating a visible shell."""
    global _cached_result, _last_query
    now = time.monotonic()
    if _cached_result is not None and not force_refresh and now - _last_query < CACHE_TTL_SECONDS:
        return _cached_result.copy()
    _last_query = now

    if os.name != "nt":
        _cached_result = _fallback("unsupported_platform")
        return _cached_result.copy()

    letter = drive_letter.strip().rstrip(":\\").upper() or "C"
    if len(letter) != 1 or not letter.isalpha():
        raise ValueError(f"Invalid drive letter: {drive_letter!r}")
    command = (
        "$ErrorActionPreference='Stop'; "
        f"$p=Get-Partition -DriveLetter '{letter}'; "
        "$d=Get-Disk -Number $p.DiskNumber; "
        "$pd=Get-PhysicalDisk | Where-Object {$_.DeviceId -eq $d.Number} | Select-Object -First 1; "
        "$r=Get-StorageReliabilityCounter -PhysicalDisk $pd; "
        "[pscustomobject]@{Model=$pd.FriendlyName;MediaType=$pd.MediaType;Wear=$r.Wear;Temperature=$r.Temperature;PowerOnHours=$r.PowerOnHours;ReadErrors=$r.ReadErrorsTotal;WriteErrors=$r.WriteErrorsTotal}|ConvertTo-Json -Compress"
    )
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=5.0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000), startupinfo=startupinfo,
        )
        raw = json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else {}
        wear = float(raw.get("Wear") or 0.0)
        _cached_result = {
            "model": str(raw.get("Model") or "Windows storage device"),
            "media_type": str(raw.get("MediaType") or "SSD"),
            "health_percent": round(max(0.0, 100.0 - wear), 1),
            "wear_percent": wear,
            "tbw_terabytes": 0.0,
            "temperature_c": float(raw.get("Temperature") or 0.0),
            "power_on_hours": int(raw.get("PowerOnHours") or 0),
            "unsafe_shutdowns": 0,
            "read_errors": int(raw.get("ReadErrors") or 0),
            "write_errors": int(raw.get("WriteErrors") or 0),
            "available": bool(raw),
            "source": "windows_storage_api",
        }
    except Exception:
        _cached_result = _fallback("windows_storage_api_unavailable")
    return _cached_result.copy()

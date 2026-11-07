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
        "health_percent": None,
        "wear_percent": None,
        "tbw_terabytes": None,
        "temperature_c": None,
        "power_on_hours": None,
        "unsafe_shutdowns": None,
        "read_errors": None,
        "write_errors": None,
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
        if not isinstance(raw, dict) or not raw:
            _cached_result = _fallback("windows_storage_api_unavailable")
            return _cached_result.copy()

        def optional_number(key: str, cast=float):
            value = raw.get(key)
            if value is None or value == "":
                return None
            try:
                return cast(value)
            except (TypeError, ValueError):
                return None

        wear = optional_number("Wear")
        _cached_result = {
            "model": str(raw.get("Model") or "Windows storage device"),
            "media_type": str(raw.get("MediaType") or "SSD"),
            "health_percent": round(max(0.0, 100.0 - wear), 1) if wear is not None else None,
            "wear_percent": wear,
            "tbw_terabytes": None,
            "temperature_c": optional_number("Temperature"),
            "power_on_hours": optional_number("PowerOnHours", int),
            "unsafe_shutdowns": optional_number("UnsafeShutdowns", int),
            "read_errors": optional_number("ReadErrors", int),
            "write_errors": optional_number("WriteErrors", int),
            "available": True,
            "source": "windows_storage_api",
        }
    except Exception:
        _cached_result = _fallback("windows_storage_api_unavailable")
    return _cached_result.copy()

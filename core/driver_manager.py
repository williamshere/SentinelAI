"""
core/driver_manager.py - Windows System Hardware Driver Audit & Update Manager.
Inspects installed drivers (Display/GPU, Chipset, Audio, Network, Storage) via pnputil and WMI,
detects driver versioning and age, and provides one-click update actions.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger("sentinel.drivers")


class DriverManager:
    """
    Manages hardware driver inventory, version auditing, and device scan utilities.
    """

    def __init__(self):
        pass

    def scan_drivers(self) -> list[dict[str, Any]]:
        """
        Enumerates connected device drivers categorized by subsystem.
        Returns a structured list of driver objects.
        """
        if os.name == "nt":
            # 1. Query Win32_PnPSignedDriver via PowerShell JSON
            ps_cmd = """
            try {
                $categories = @("Display", "Net", "MEDIA", "SCSIAdapter", "System", "hdc")
                $drivers = Get-CimInstance -ClassName Win32_PnPSignedDriver | Where-Object { 
                    $_.DeviceClass -in $categories -and $_.DeviceName -ne $null
                } | Select-Object DeviceName, DeviceClass, DriverVersion, DriverDate, Manufacturer, IsSigned -First 40
                $drivers | ConvertTo-Json -Compress
            } catch {
                Write-Output "[]"
            }
            """
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    capture_output=True,
                    text=True,
                    timeout=8.0,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
                output = res.stdout.strip()
                if output and (output.startswith("[") or output.startswith("{")):
                    raw = json.loads(output)
                    items = [raw] if isinstance(raw, dict) else raw
                    return self._format_driver_entries(items)
            except Exception as e:
                logger.debug(f"PowerShell driver query error: {e}")

        return []

    def _format_driver_entries(self, raw_items: list[dict]) -> list[dict[str, Any]]:
        results = []
        for item in raw_items:
            name = item.get("DeviceName") or "Unknown Device"
            cls = (item.get("DeviceClass") or "").upper()
            ver = item.get("DriverVersion") or "N/A"
            mfg = item.get("Manufacturer") or "Unknown"

            # Parse date
            raw_date = str(item.get("DriverDate") or "")
            date_str = raw_date[:10] if len(raw_date) >= 10 else "Unknown"

            # Determine category
            category = "System"
            if "DISPLAY" in cls:
                category = "Display / GPU"
            elif "NET" in cls:
                category = "Network / LAN"
            elif "MEDIA" in cls:
                category = "Audio / Sound"
            elif "SCSI" in cls or "HDC" in cls:
                category = "Storage Controller"

            results.append({
                "device_name": name,
                "category": category,
                "version": ver,
                "driver_date": date_str,
                "manufacturer": mfg,
                "status": "Installed & Active",
            })
        return results

    def scan_for_hardware_changes(self) -> tuple[bool, str]:
        """Runs Windows pnputil to trigger a Plug and Play hardware scan."""
        if os.name != "nt":
            return False, "Hardware scan requires Windows."
        try:
            res = subprocess.run(
                ["pnputil.exe", "/scan-devices"],
                capture_output=True,
                text=True,
                timeout=15.0,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if res.returncode != 0:
                return False, f"Hardware scan failed (exit {res.returncode}). Administrator access may be required."
            return True, "Plug and Play scan completed. Hardware drivers re-enumerated."
        except Exception as e:
            return False, f"Hardware scan error: {e}"

    def launch_device_manager(self) -> bool:
        """Opens Windows Device Manager (devmgmt.msc)."""
        if os.name != "nt":
            return False
        try:
            os.system("start devmgmt.msc")
            return True
        except Exception:
            return False

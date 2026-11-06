"""Low-impact process-level CPU and memory telemetry."""
from __future__ import annotations

import time

try:
    import psutil
except ImportError:
    psutil = None

PROCESS_SCAN_INTERVAL_SECONDS = 5.0
MAX_PROCESS_ROWS = 50

_last_scan_time = 0.0
_cached_processes: list[dict] = []


def get_process_info() -> dict:
    """Return a cached, CPU-sorted snapshot of processes and their memory use."""
    global _last_scan_time, _cached_processes

    if psutil is None:
        return {"available": False, "processes": []}

    now = time.monotonic()
    if now - _last_scan_time < PROCESS_SCAN_INTERVAL_SECONDS:
        return {"available": True, "processes": list(_cached_processes)}

    try:
        logical_cpus = max(1, psutil.cpu_count(logical=True) or 1)
        total_memory = psutil.virtual_memory().total
        processes = []

        for process in psutil.process_iter(attrs=["pid", "name"]):
            try:
                info = process.info
                memory_bytes = process.memory_info().rss
                cpu_percent = process.cpu_percent(interval=None) / logical_cpus
                processes.append({
                    "pid": info["pid"],
                    "name": info.get("name") or "Unknown",
                    "cpu_percent": min(100.0, max(0.0, cpu_percent)),
                    "memory_bytes": memory_bytes,
                    "memory_percent": (memory_bytes / total_memory * 100.0) if total_memory else 0.0,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        processes.sort(key=lambda item: (-item["cpu_percent"], -item["memory_bytes"]))
        _cached_processes = processes[:MAX_PROCESS_ROWS]
        _last_scan_time = now
        return {"available": True, "processes": list(_cached_processes)}
    except Exception:
        return {"available": False, "processes": []}

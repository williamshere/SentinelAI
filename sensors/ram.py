"""
sensors/ram.py - System memory telemetry.
Degrades gracefully when psutil is unavailable.
"""
try:
    import psutil
except ImportError:
    psutil = None


def get_ram_info():
    if psutil is None:
        return {
            "total": 0,
            "used": 0,
            "free": 0,
            "percent": 0.0,
            "available": False,
        }
    try:
        mem = psutil.virtual_memory()
    except Exception:
        return {
            "total": 0,
            "used": 0,
            "free": 0,
            "percent": 0.0,
            "available": False,
        }
    return {
        "total": mem.total,
        "used": mem.used,
        "free": mem.available,
        "percent": mem.percent,
        "available": True,
    }

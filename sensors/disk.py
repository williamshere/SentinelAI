import os

try:
    import psutil
except ImportError:
    psutil = None


def get_system_drive_mount() -> str:
    """Resolve the active system drive mount point dynamically."""
    if os.name == "nt":
        system_drive = os.environ.get("SystemDrive", "C:")
        return f"{system_drive}\\"
    return "/"


def get_disk_info(mount_point: str | None = None) -> dict:
    """Fetch storage capacity and usage for the primary system disk."""
    target = mount_point or get_system_drive_mount()
    try:
        if psutil is None:
            raise RuntimeError("psutil is not installed")
        disk = psutil.disk_usage(target)
        return {
            "mount": target,
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": float(disk.percent),
            "available": True,
        }
    except Exception:
        return {
            "mount": target,
            "total": 0,
            "used": 0,
            "free": 0,
            "percent": 0.0,
            "available": False,
        }
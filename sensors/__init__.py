"""
sensors package - Hardware sensor telemetry collection for CPU, GPU, RAM, Disk, and Storage Health.
"""
from .cpu import get_cpu_info, is_admin
from .gpu import get_gpu_info
from .ram import get_ram_info
from .disk import get_disk_info
from .network import get_network_info

try:
    from .storage_health import get_storage_health
except ImportError:
    def get_storage_health(drive_letter: str = "C:", force_refresh: bool = False) -> dict:
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
            "source": "unavailable",
        }

__all__ = [
    "get_cpu_info",
    "get_gpu_info",
    "get_ram_info",
    "get_disk_info",
    "get_network_info",
    "get_storage_health",
    "is_admin",
]

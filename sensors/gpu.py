"""
sensors/gpu.py - NVIDIA GPU monitoring module via pynvml with fallback.
Hardened against handle leaks and crashes during extended runtimes.
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning, message=".*pynvml.*")

_nvml_initialized: bool = False
_nvml_available: bool = False
_nvml_handle = None


def _ensure_nvml():
    global _nvml_initialized, _nvml_available, _nvml_handle
    if _nvml_initialized:
        return _nvml_available

    try:
        import pynvml
        pynvml.nvmlInit()
        _nvml_initialized = True
        count = pynvml.nvmlDeviceGetCount()
        if count > 0:
            _nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            _nvml_available = True
        else:
            _nvml_available = False
    except Exception:
        _nvml_initialized = True
        _nvml_available = False

    return _nvml_available


def get_gpu_info() -> dict:
    """Retrieve GPU utilization, memory, temperature, and power metrics safely."""
    # 1. Attempt pynvml with persistent handle
    if _ensure_nvml() and _nvml_handle is not None:
        try:
            import pynvml
            name = pynvml.nvmlDeviceGetName(_nvml_handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8")

            utilization = pynvml.nvmlDeviceGetUtilizationRates(_nvml_handle)
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(_nvml_handle)
            temperature = pynvml.nvmlDeviceGetTemperature(_nvml_handle, pynvml.NVML_TEMPERATURE_GPU)

            try:
                power_mw = pynvml.nvmlDeviceGetPowerUsage(_nvml_handle)
                power_watts = round(power_mw / 1000.0, 1)
            except Exception:
                power_watts = 0.0

            try:
                graphics_clock = pynvml.nvmlDeviceGetClockInfo(_nvml_handle, pynvml.NVML_CLOCK_GRAPHICS)
            except Exception:
                graphics_clock = 0

            return {
                "name": name,
                "usage": float(utilization.gpu),
                "temperature": float(temperature),
                "vram_used": memory_info.used,
                "vram_total": memory_info.total,
                "power_watts": power_watts,
                "clock_mhz": graphics_clock,
                "available": True,
            }
        except Exception:
            pass

    # 2. Fallback to gpustat
    try:
        import gpustat
        gpu = gpustat.GPUStatCollection.new_query().jsonify()[0]
        vram_used_bytes = int(gpu.get("memory.used", 0)) * 1024 * 1024
        vram_total_bytes = int(gpu.get("memory.total", 0)) * 1024 * 1024
        return {
            "name": gpu.get("name", "NVIDIA GPU"),
            "usage": float(gpu.get("utilization.gpu", gpu.get("usage", 0.0))),
            "temperature": float(gpu.get("temperature.gpu", 0.0)),
            "vram_used": vram_used_bytes,
            "vram_total": vram_total_bytes,
            "power_watts": 0.0,
            "clock_mhz": 0,
            "available": True,
        }
    except Exception:
        pass

    # 3. Default fallback
    return {
        "name": "GPU Sensor Unavailable",
        "usage": 0.0,
        "temperature": 0.0,
        "vram_used": 0,
        "vram_total": 0,
        "power_watts": 0.0,
        "clock_mhz": 0,
        "available": False,
    }

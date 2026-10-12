"""
ai/health.py - Weighted PC Health Score formula implementation.
Formula: 40% Thermal + 30% Memory/Storage + 30% Hardware Headroom.
"""


def _calc_gpu_thermal_score(temp: float) -> float:
    """Calculate GPU thermal health score (0-100) based on RTX 5070 curve."""
    if temp <= 0:
        return 100.0
    if temp <= 65.0:
        return 100.0
    elif temp <= 75.0:
        # Scale 100 -> 80
        return 100.0 - ((temp - 65.0) / 10.0) * 20.0
    elif temp <= 85.0:
        # Scale 80 -> 40
        return 80.0 - ((temp - 75.0) / 10.0) * 40.0
    else:
        # Critical throttle zone: Scale 40 -> 0 at 95C+
        return max(0.0, 40.0 - ((temp - 85.0) / 10.0) * 40.0)


def _calc_cpu_thermal_score(temp: float) -> float:
    """Calculate CPU thermal health score (0-100) based on Intel Core i7-12700 curve."""
    if temp <= 0:
        return 100.0
    if temp <= 65.0:
        return 100.0
    elif temp <= 80.0:
        # Scale 100 -> 75
        return 100.0 - ((temp - 65.0) / 15.0) * 25.0
    elif temp <= 90.0:
        # Scale 75 -> 30
        return 75.0 - ((temp - 80.0) / 10.0) * 45.0
    else:
        # Scale 30 -> 0 at 100C+
        return max(0.0, 30.0 - ((temp - 90.0) / 10.0) * 30.0)


def calculate_health_score(metrics: dict) -> dict:
    """
    Computes a comprehensive, normalized 0-100 PC Health Score.
    Weighted Breakdown:
      - 40% Thermal (GPU & CPU Temperatures)
      - 30% Memory & Storage (RAM & Disk availability)
      - 30% Hardware Headroom (CPU & GPU VRAM compute reserve)
    """
    cpu = metrics.get("cpu", {})
    ram = metrics.get("ram", {})
    disk = metrics.get("disk", {})
    gpu = metrics.get("gpu", {})

    # 1. Thermal Sub-Score (40% Weight)
    cpu_temp = float(cpu.get("temperature", 0.0) or 0.0)
    gpu_temp = float(gpu.get("temperature", 0.0) or 0.0) if gpu.get("available") else 0.0

    gpu_thermal = _calc_gpu_thermal_score(gpu_temp) if gpu_temp > 0 else None
    cpu_thermal = _calc_cpu_thermal_score(cpu_temp) if cpu_temp > 0 else None

    if gpu_thermal is not None and cpu_thermal is not None:
        thermal_score = 0.5 * gpu_thermal + 0.5 * cpu_thermal
    elif gpu_thermal is not None:
        thermal_score = gpu_thermal
    elif cpu_thermal is not None:
        thermal_score = cpu_thermal
    else:
        thermal_score = 100.0

    # 2. Memory & Storage Sub-Score (30% Weight)
    ram_pct = float(ram.get("percent", 0.0) or 0.0)
    disk_pct = float(disk.get("percent", 0.0) or 0.0)

    # 100% capacity is bad, 0% is good
    ram_score = max(0.0, 100.0 - (ram_pct * 1.1 if ram_pct > 60 else ram_pct * 0.8))
    disk_score = max(0.0, 100.0 - (disk_pct * 1.2 if disk_pct > 75 else disk_pct * 0.7))
    memory_storage_score = min(100.0, max(0.0, 0.60 * ram_score + 0.40 * disk_score))

    # 3. Hardware Headroom Sub-Score (30% Weight)
    cpu_usage = float(cpu.get("usage", 0.0) or 0.0)
    cpu_headroom = max(0.0, 100.0 - cpu_usage)

    if gpu.get("available") and gpu.get("vram_total", 0) > 0:
        vram_pct = (gpu.get("vram_used", 0) / gpu.get("vram_total", 1)) * 100.0
        vram_headroom = max(0.0, 100.0 - vram_pct)
        headroom_score = 0.50 * cpu_headroom + 0.50 * vram_headroom
    else:
        headroom_score = cpu_headroom

    # Composite Weighted Health Score
    raw_total = (0.40 * thermal_score) + (0.30 * memory_storage_score) + (0.30 * headroom_score)
    total_score = int(round(max(0.0, min(100.0, raw_total))))

    # Status and Palette Mapping
    if total_score >= 90:
        status = "Optimal"
        color = "#34d399"  # Emerald green
    elif total_score >= 75:
        status = "Normal"
        color = "#38bdf8"  # Cyan
    elif total_score >= 60:
        status = "Warning"
        color = "#f59e0b"  # Amber
    else:
        status = "Critical"
        color = "#ef4444"  # Rose red

    return {
        "total_score": total_score,
        "status": status,
        "color": color,
        "thermal_score": round(thermal_score, 1),
        "memory_storage_score": round(memory_storage_score, 1),
        "headroom_score": round(headroom_score, 1),
        "breakdown": {
            "cpu_temp": cpu_temp,
            "gpu_temp": gpu_temp,
            "ram_pct": ram_pct,
            "disk_pct": disk_pct,
            "cpu_usage": cpu_usage,
        },
    }

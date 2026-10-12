"""
ai/recommendations.py - Deterministic rule-based hardware advice and recommendation synthesizer.
"""


def get_deterministic_recommendations(metrics: dict, health_score: dict | None = None) -> list[str]:
    """
    Evaluates raw metrics against known desktop workstation thresholds and produces
    targeted technical recommendations.
    """
    recs = []
    cpu = metrics.get("cpu", {})
    ram = metrics.get("ram", {})
    disk = metrics.get("disk", {})
    gpu = metrics.get("gpu", {})

    cpu_usage = float(cpu.get("usage", 0.0) or 0.0)
    cpu_temp = float(cpu.get("temperature", 0.0) or 0.0)
    ram_pct = float(ram.get("percent", 0.0) or 0.0)
    disk_pct = float(disk.get("percent", 0.0) or 0.0)

    # 1. Thermal checks
    if cpu_temp >= 85.0:
        recs.append("CPU thermal limit critical (>=85°C): Verify Noctua CPU cooler fan curve and repaste contact frame if throttling persists.")
    elif cpu_temp >= 75.0:
        recs.append("CPU running warm (>=75°C): Ramp Arctic chassis exhaust fans to improve enclosure airflow.")

    if gpu.get("available"):
        gpu_temp = float(gpu.get("temperature", 0.0) or 0.0)
        gpu_usage = float(gpu.get("usage", 0.0) or 0.0)
        vram_used = gpu.get("vram_used", 0)
        vram_total = gpu.get("vram_total", 1) or 1
        vram_pct = (vram_used / vram_total) * 100.0

        if gpu_temp >= 82.0:
            recs.append("GPU core temperature elevated (>=82°C): Adjust GPU Tweak III fan profile and inspect lower chassis intake clearance.")
        if vram_pct >= 90.0:
            recs.append(f"RTX 5070 VRAM near capacity ({vram_pct:.1f}%): Reduce context window size or quantize weights for local model inference.")
        elif gpu_usage >= 95.0 and cpu_usage <= 20.0:
            recs.append("GPU bound workload detected: System has significant CPU compute headroom for background logging and analytics.")

    # 2. Memory & Disk checks
    if ram_pct >= 85.0:
        recs.append(f"System memory heavily utilized ({ram_pct:.1f}%): Audit background development servers and container memory limits.")

    if disk_pct >= 88.0:
        recs.append(f"System drive capacity low ({disk_pct:.1f}% used): Prune package caches, old build artifacts, and temp files.")

    # 3. Baseline recommendation if everything is nominal
    if not recs:
        recs.append("System operating within optimal parameters. All thermal and hardware headrooms are healthy.")

    return recs

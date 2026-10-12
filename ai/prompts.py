"""
ai/prompts.py - Prompt engineering templates for local LLM hardware diagnostics.
Designed for quantized Gemma 2 9B and Llama 3.1 8B running locally on NVIDIA RTX 5070.
"""

SYSTEM_DIAGNOSTIC_PROMPT = """You are Sentinel AI, an expert real-time hardware diagnostics and system security engine.
Your task is to analyze telemetry snapshots and alert logs from a high-performance Windows workstation (powered by an Intel Core i7-12700 CPU and NVIDIA GeForce RTX 5070 GPU with 12GB VRAM).

Analyze the provided telemetry metrics and produce a concise, professional diagnostic assessment in the following format:
1. OVERALL ASSESSMENT: One sentence summarizing current hardware stability and threat level.
2. ROOT-CAUSE HYPOTHESIS: Specific explanation of any elevated metrics, thermal behavior, or resource saturation.
3. RECOMMENDED ACTIONS: 2-3 prioritized, technical, actionable remediation steps (e.g. fan curves, background PID termination, undervolting check, storage pruning).

Maintain a direct, highly technical, and concise tone without conversational fluff.
"""


def build_telemetry_prompt(
    metrics: dict,
    alerts: list | None = None,
    health_score: dict | None = None,
    trigger_reason: str | None = None,
) -> str:
    """Constructs a compact, structured prompt payload from telemetry, alerts, and optional trigger event."""
    cpu = metrics.get("cpu", {})
    ram = metrics.get("ram", {})
    disk = metrics.get("disk", {})
    gpu = metrics.get("gpu", {})

    prompt_lines = []

    if trigger_reason:
        prompt_lines.append("### 🚨 TRIGGERING CRITICAL ANOMALY EVENT")
        prompt_lines.append(f"CRITICAL BREACH: {trigger_reason}")
        prompt_lines.append("IMMEDIATE ACTION REQUIRED: Prioritize diagnosing the root cause of this specific anomaly.")
        prompt_lines.append("")

    prompt_lines.extend([
        "### CURRENT SYSTEM TELEMETRY SNAPSHOT",
        f"- CPU Usage: {cpu.get('usage', 0.0):.1f}% | Clock: {cpu.get('frequency', 0.0):.0f} MHz",
        f"- CPU Temp: {cpu.get('temperature', 0.0):.1f}°C | Power: {cpu.get('power_watts', 0.0):.1f} W",
        f"- Memory (RAM): {ram.get('percent', 0.0):.1f}% used ({ram.get('used', 0) / (1024**3):.1f} / {ram.get('total', 0) / (1024**3):.1f} GB)",
        f"- Disk: {disk.get('percent', 0.0):.1f}% capacity ({disk.get('mount', '/')})",
    ])

    if gpu.get("available"):
        prompt_lines.append(
            f"- GPU: {gpu.get('name', 'NVIDIA GPU')} | Usage: {gpu.get('usage', 0.0):.0f}% | Temp: {gpu.get('temperature', 0.0):.0f}°C | Clock: {gpu.get('clock_mhz', 0)} MHz"
        )
        prompt_lines.append(
            f"- VRAM: {gpu.get('vram_used', 0) / (1024**3):.1f} / {gpu.get('vram_total', 0) / (1024**3):.1f} GB | Board Power: {gpu.get('power_watts', 0.0):.0f} W"
        )
    else:
        prompt_lines.append("- GPU: Sensor telemetry unavailable or inactive.")

    if health_score:
        prompt_lines.append(
            f"- Composite PC Health Score: {health_score.get('total_score', 0)}/100 ({health_score.get('status', 'Unknown')})"
        )
        prompt_lines.append(
            f"  (Thermal: {health_score.get('thermal_score', 0)}%, Memory/Storage: {health_score.get('memory_storage_score', 0)}%, Headroom: {health_score.get('headroom_score', 0)}%)"
        )

    if alerts:
        prompt_lines.append("\n### RECENT ALERTS & ANOMALIES (Trailing Window)")
        for a in alerts[:5]:
            ts = a.get("timestamp", "")
            sev = a.get("severity", "info").upper()
            msg = a.get("message", "")
            prompt_lines.append(f"- [{sev}] {ts}: {msg}")
    else:
        prompt_lines.append("\n### RECENT ALERTS: None. All other monitored sensors within baseline bounds.")

    prompt_lines.append("\nProvide concise diagnostic evaluation now:")
    return "\n".join(prompt_lines)

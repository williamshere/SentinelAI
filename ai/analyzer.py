"""
ai/analyzer.py - Local LLM diagnostic analyzer and background QThread worker.
Connects to LM Studio (OpenAI-compatible REST API) or local Ollama with heuristic fallback.
"""
from datetime import datetime
import json
import urllib.request

try:
    from PySide6.QtCore import QThread, Signal
except ImportError:
    # Graceful degradation: pure-logic use (tests, scripts) must not hard-require Qt.
    class QThread:
        def __init__(self, *args, **kwargs): pass
        def start(self): pass
        def isRunning(self): return False
        def wait(self, *args, **kwargs): return True
    def Signal(*args, **kwargs):
        class DummySignal:
            def connect(self, fn): self.fn = fn
            def emit(self, val): getattr(self, "fn", lambda x: None)(val)
        return DummySignal()

try:
    from config import (
        LLM_BACKEND,
        LM_STUDIO_URL,
        OLLAMA_MODEL,
        OLLAMA_TIMEOUT_SECONDS,
        OLLAMA_URL,
    )
except ImportError:
    LLM_BACKEND = "auto"
    LM_STUDIO_URL = "http://localhost:1234/v1"
    OLLAMA_URL = "http://localhost:11434"
    OLLAMA_MODEL = "gemma2:9b"
    OLLAMA_TIMEOUT_SECONDS = 25.0

# Resilient import of prompt templates and recommendations
try:
    from .prompts import SYSTEM_DIAGNOSTIC_PROMPT, build_telemetry_prompt
    from .recommendations import get_deterministic_recommendations
except (ImportError, ValueError):
    try:
        from ai.prompts import SYSTEM_DIAGNOSTIC_PROMPT, build_telemetry_prompt
        from ai.recommendations import get_deterministic_recommendations
    except (ImportError, ModuleNotFoundError):
        try:
            from prompts import SYSTEM_DIAGNOSTIC_PROMPT, build_telemetry_prompt
            from recommendations import get_deterministic_recommendations
        except (ImportError, ModuleNotFoundError):
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
                cpu = metrics.get("cpu", {})
                ram = metrics.get("ram", {})
                gpu = metrics.get("gpu", {})
                disk = metrics.get("disk", {})
                lines = []
                if trigger_reason:
                    lines.append(f"### 🚨 TRIGGERING CRITICAL ANOMALY EVENT\nCRITICAL BREACH: {trigger_reason}\n")
                lines.extend([
                    "### CURRENT SYSTEM TELEMETRY SNAPSHOT",
                    f"- CPU Usage: {cpu.get('usage', 0.0):.1f}% | Clock: {cpu.get('frequency', 0.0):.0f} MHz",
                    f"- CPU Temp: {cpu.get('temperature', 0.0):.1f}°C | Power: {cpu.get('power_watts', 0.0):.1f} W",
                    f"- Memory (RAM): {ram.get('percent', 0.0):.1f}% used ({ram.get('used', 0) / (1024**3):.1f} / {ram.get('total', 0) / (1024**3):.1f} GB)",
                    f"- Disk: {disk.get('percent', 0.0):.1f}% capacity ({disk.get('mount', '/')})",
                ])
                if gpu.get("available"):
                    lines.append(f"- GPU: {gpu.get('name', 'NVIDIA GPU')} | Usage: {gpu.get('usage', 0.0):.0f}% | Temp: {gpu.get('temperature', 0.0):.0f}°C")
                if alerts:
                    lines.append("\n### RECENT ALERTS & ANOMALIES")
                    for a in alerts[:5]:
                        lines.append(f"- [{a.get('severity', 'info').upper()}] {a.get('timestamp', '')}: {a.get('message', '')}")
                return "\n".join(lines)

            def get_deterministic_recommendations(metrics: dict, health_score: dict | None = None) -> list[str]:
                return ["System operating within optimal parameters. All thermal and hardware headrooms are healthy."]


class HardwareAnalyzer:
    """Orchestrates system telemetry analysis using LM Studio, Ollama, or resilient rule engine."""

    def __init__(
        self,
        backend: str = LLM_BACKEND,
        lm_studio_url: str = LM_STUDIO_URL,
        ollama_url: str = OLLAMA_URL,
        model: str = OLLAMA_MODEL,
        timeout_seconds: float = OLLAMA_TIMEOUT_SECONDS,
    ):
        self.backend = backend.lower()
        self.lm_studio_url = lm_studio_url.rstrip("/")
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def analyze(
        self,
        metrics: dict,
        alerts: list | None = None,
        health_score: dict | None = None,
        trigger_reason: str | None = None,
        auto_triggered: bool = False,
    ) -> dict:
        prompt = build_telemetry_prompt(
            metrics=metrics,
            alerts=alerts,
            health_score=health_score,
            trigger_reason=trigger_reason,
        )
        recs = get_deterministic_recommendations(metrics, health_score)

        # 1. Attempt LM Studio (OpenAI-compatible /v1/chat/completions)
        if self.backend in ("auto", "lm_studio"):
            try:
                url = f"{self.lm_studio_url}/chat/completions"
                payload = {
                    "messages": [
                        {"role": "system", "content": SYSTEM_DIAGNOSTIC_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 512,
                    "stream": False,
                }
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=min(6.0, self.timeout_seconds)) as response:
                    if response.status == 200:
                        resp_json = json.loads(response.read().decode("utf-8"))
                        raw_text = resp_json["choices"][0]["message"]["content"].strip()
                        model_id = resp_json.get("model", "LM Studio")
                        if raw_text:
                            summary_line = raw_text.split("\n")[0].strip()
                            if ":" in summary_line:
                                summary_line = summary_line.split(":", 1)[1].strip()
                            return {
                                "success": True,
                                "source": f"LM Studio ({model_id})",
                                "model": model_id,
                                "assessment": raw_text,
                                "summary": summary_line,
                                "recommendations": recs,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "trigger_reason": trigger_reason,
                                "auto_triggered": auto_triggered,
                            }
            except Exception:
                pass

        # 2. Attempt Ollama API
        if self.backend in ("auto", "ollama"):
            try:
                url = f"{self.ollama_url}/api/generate"
                payload = {
                    "model": self.model,
                    "system": SYSTEM_DIAGNOSTIC_PROMPT,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "num_gpu": 99,
                    },
                }
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    if response.status == 200:
                        resp_json = json.loads(response.read().decode("utf-8"))
                        raw_text = resp_json.get("response", "").strip()
                        if raw_text:
                            summary_line = raw_text.split("\n")[0].strip()
                            if ":" in summary_line:
                                summary_line = summary_line.split(":", 1)[1].strip()
                            return {
                                "success": True,
                                "source": f"Ollama ({self.model})",
                                "model": self.model,
                                "assessment": raw_text,
                                "summary": summary_line,
                                "recommendations": recs,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "trigger_reason": trigger_reason,
                                "auto_triggered": auto_triggered,
                            }
            except Exception:
                pass

        # 3. Resilient Rule-Engine Fallback
        score_val = health_score.get("total_score", 100) if health_score else 100
        status_text = health_score.get("status", "Normal") if health_score else "Normal"
        cpu = metrics.get("cpu", {})
        gpu = metrics.get("gpu", {})

        if trigger_reason:
            summary = f"Triggered by {trigger_reason}. System health currently {score_val}/100 ({status_text})."
            hypothesis = f"Incident triggered by {trigger_reason}. CPU load at {cpu.get('usage', 0):.1f}%, GPU load at {gpu.get('usage', 0):.0f}%, GPU temp at {gpu.get('temperature', 0):.0f}°C."
        else:
            summary = f"Workstation stability rated {score_val}/100 ({status_text}). Nominal operations."
            hypothesis = f"Hardware metrics operating within threshold envelopes. CPU at {cpu.get('usage', 0):.1f}%, GPU at {gpu.get('usage', 0):.0f}%."

        fallback_lines = [
            f"OVERALL ASSESSMENT: {summary}",
            f"ROOT-CAUSE HYPOTHESIS: {hypothesis}",
            "RECOMMENDED ACTIONS:",
        ]
        for r in recs[:3]:
            fallback_lines.append(f"- {r}")

        return {
            "success": True,
            "source": "Sentinel Heuristic Engine (Local Fallback)",
            "model": "Rule-Based",
            "assessment": "\n".join(fallback_lines),
            "summary": summary,
            "recommendations": recs,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trigger_reason": trigger_reason,
            "auto_triggered": auto_triggered,
        }


class DiagnosticsWorker(QThread):
    diagnostics_ready = Signal(dict)

    def __init__(
        self,
        metrics: dict,
        alerts: list | None = None,
        health_score: dict | None = None,
        trigger_reason: str | None = None,
        auto_triggered: bool = False,
    ):
        super().__init__()
        self.metrics = metrics
        self.alerts = alerts or []
        self.health_score = health_score or {}
        self.trigger_reason = trigger_reason
        self.auto_triggered = auto_triggered
        self.analyzer = HardwareAnalyzer()
        self._abort = False

    def abort(self):
        """Request early termination; honored between inference stages."""
        self._abort = True

    def run(self):
        if self._abort:
            return
        result = self.analyzer.analyze(
            metrics=self.metrics,
            alerts=self.alerts,
            health_score=self.health_score,
            trigger_reason=self.trigger_reason,
            auto_triggered=self.auto_triggered,
        )
        if self._abort:
            return
        self.diagnostics_ready.emit(result)

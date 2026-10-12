"""
ai package - Local AI diagnostic analytics, health scoring, recommendations, predictive hardware wear, and conversational chat.
"""
from .analyzer import DiagnosticsWorker, HardwareAnalyzer
from .health import calculate_health_score
from .predictive import PredictiveEngine, PredictiveAssessment
from .chat_engine import ChatEngine, ChatWorker
try:
    from .prompts import SYSTEM_DIAGNOSTIC_PROMPT, build_telemetry_prompt
except (ImportError, ValueError):
    pass
from .recommendations import get_deterministic_recommendations

__all__ = [
    "calculate_health_score",
    "HardwareAnalyzer",
    "DiagnosticsWorker",
    "get_deterministic_recommendations",
    "PredictiveEngine",
    "PredictiveAssessment",
    "ChatEngine",
    "ChatWorker",
]

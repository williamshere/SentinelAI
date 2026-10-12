"""
config.py - Centralized configuration for Sentinel AI.

Single source of truth for paths, telemetry cadence, alert thresholds, and
local-LLM inference settings. Supports both source execution and PyInstaller
frozen bundles (assets resolve from the bundle dir; the database and logs
always live next to the executable / project root so they stay writable).
"""
from pathlib import Path
import sys

# Runtime directory resolution for source execution and PyInstaller bundles
if getattr(sys, "frozen", False):
    # Executable root (persistent location on disk)
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = BASE_DIR

ASSETS_DIR = BUNDLE_DIR / "assets"

# Project paths
DATABASE_PATH = BASE_DIR / "database" / "sentinel.db"
LOGS_DIR = BASE_DIR / "logs"

# Ensure runtime directories exist
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Telemetry is intentionally low-impact by default.  Hardware values do not need
# 60 updates/minute, and a two-second cadence avoids competing with games and
# foreground work while still feeling live in the dashboard.
UI_REFRESH_INTERVAL_MS = 2000
DB_LOG_INTERVAL_MS = 30000

# Windows WMI is comparatively expensive and must never be scanned for every
# UI refresh.  The CPU sensor caches a combined WMI read for this interval.
WMI_SENSOR_INTERVAL_SECONDS = 15.0

# Sensor thresholds for alerting
THRESHOLDS = {
    "cpu_high": 80.0,
    "cpu_critical": 90.0,
    "ram_high": 80.0,
    "ram_critical": 90.0,
    "disk_high": 85.0,
    "disk_critical": 92.0,
    "gpu_temp_high": 75.0,
    "gpu_temp_critical": 85.0,
    "gpu_usage_high": 90.0,
}

# Time-based alert debounce (seconds).  On top of the hysteresis in
# ui/alert_manager.py, a repeat WARNING/CRITICAL firing for the same metric
# inside this window is suppressed so a fluttering sensor can't spam the feed.
ALERT_DEBOUNCE_SECONDS = 60

# Telemetry snapshot retention (days).  Older snapshots and alert rows are
# pruned automatically on startup.
RETENTION_DAYS = 7

# Automated AI Diagnostics configuration
AUTO_DIAG_COOLDOWN_SECONDS = 90
# Local model inference can consume substantial GPU/CPU and memory. Keep it
# user-initiated by default; it can be enabled after confirming headroom.
AUTO_DIAGNOSTICS_ENABLED = False

# Local LLM Inference Server Configuration
# LLM_BACKEND: "auto" (attempts LM Studio on 1234 first, falls back to Ollama on 11434), "lm_studio", or "ollama"
LLM_BACKEND = "auto"
LM_STUDIO_URL = "http://localhost:1234/v1"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma2:9b"  # Switchable: "gemma2:9b", "gemma2:27b", "gemma3:latest"
OLLAMA_TIMEOUT_SECONDS = 25.0

# Chat UI watchdog: re-enable the input if a local inference call runs longer
# than this.  The worker thread keeps running; only the UI is released.
CHAT_WATCHDOG_SECONDS = 45

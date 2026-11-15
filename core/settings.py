"""Validated, atomic local preferences; config.py supplies the defaults."""
import json
import os
from pathlib import Path
import tempfile

from config import BASE_DIR, UI_REFRESH_INTERVAL_MS, DB_LOG_INTERVAL_MS, THRESHOLDS

SETTINGS_PATH = BASE_DIR / "settings.json"
DEFAULTS = {
    "refresh_ms": UI_REFRESH_INTERVAL_MS,
    "snapshot_ms": DB_LOG_INTERVAL_MS,
    "stress_seconds": 30,
    "stress_workers": min(4, max(1, (os.cpu_count() or 2) // 2)),
    "stress_load": 50,
    "cpu_limit": 85,
    "gpu_limit": 80,
    "thresholds": dict(THRESHOLDS),
}


def validate(data):
    result = dict(DEFAULTS, thresholds=dict(DEFAULTS["thresholds"]))
    ranges = {"refresh_ms": (1000, 10000), "snapshot_ms": (10000, 300000),
              "stress_seconds": (5, 300), "stress_workers": (1, min(32, os.cpu_count() or 1)),
              "stress_load": (10, 100), "cpu_limit": (50, 95), "gpu_limit": (50, 90)}
    for key, (lo, hi) in ranges.items():
        value = data.get(key, result[key])
        if type(value) is not int or not lo <= value <= hi:
            raise ValueError(f"{key} must be between {lo} and {hi}")
        result[key] = value
    for key, value in data.get("thresholds", {}).items():
        if key not in THRESHOLDS:
            continue
        if type(value) not in (int, float) or not 1 <= value <= (1e12 if key == "network_high" else 100):
            raise ValueError(f"Invalid threshold: {key}")
        result["thresholds"][key] = float(value)
    for prefix in ("cpu", "ram", "disk", "gpu_temp"):
        if result["thresholds"][prefix + "_high"] >= result["thresholds"][prefix + "_critical"]:
            raise ValueError(f"{prefix}: warning must be below critical")
    return result


def load_settings(path=SETTINGS_PATH):
    try:
        return validate(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, AttributeError):
        return validate({})


def save_settings(data, path=SETTINGS_PATH):
    result = validate(data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return result

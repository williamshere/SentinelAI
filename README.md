# SentinelAI

SentinelAI is a local-first Windows hardware telemetry dashboard. It monitors CPU, RAM, disk, and NVIDIA GPU in real time, logs snapshots to a local SQLite database, fires threshold alerts with hysteresis + time debouncing, tracks gaming sessions, and can consult a local LLM (LM Studio or Ollama) for hardware diagnostics. No telemetry ever leaves the machine — there is no cloud account, no analytics, and no network calls except to `localhost` when you ask the AI something.

SentinelAI is configured for low-impact monitoring: telemetry refreshes every two seconds, database snapshots every 30 seconds, WMI sensor scans are cached for 15 seconds, and automatic local-LLM diagnostics are off by default.

## Features

- **Live telemetry** — CPU usage/frequency/temperature/power, RAM, disk, GPU usage/temperature/VRAM/power/clocks, and NVMe SMART health, refreshed every 2 s.
- **Threshold alerts** — edge-triggered warnings/criticals with hysteresis and a 60-second debounce, delivered as desktop toasts and persisted to SQLite. Alerting keeps running when the app is minimized to the system tray.
- **Weighted PC Health Score** — 40% thermals, 30% RAM/disk, 30% thermal headroom, recomputed every tick.
- **Predictive maintenance** — AIO liquid-cooling efficiency (θ in °C/W), GPU hotspot/die-contact spread, and SSD lifespan projection from SMART wear.
- **Game Mode** — automatic detection of 25+ game executables (foreground-window check + throttled process scan, ~zero in-game overhead), Do-Not-Disturb alert suppression while gaming, and post-session reports (duration, peak temps, throttle events). Manual toggle available; turning it off returns to automatic detection.
- **Ask Sentinel AI chat** — conversational diagnostics with live telemetry injected as context. Uses LM Studio (port 1234) or Ollama (port 11434) when available, with an instant offline heuristic engine otherwise.
- **Driver audit** — enumerates installed drivers (GPU, chipset, audio, network, storage) via PowerShell/CIM, plus one-click PnP rescan and Device Manager.
- **Windows auto-start** — optional launch-minimized-to-tray on login (registry-based).
- **Background-first design** — closing the window tucks the app into the system tray; telemetry, DB logging, and alerting continue. Sensors degrade gracefully (no NVIDIA GPU, no admin rights, unreachable LLM server).

## Run on Windows

Use Python 3.11–3.13. Python 3.14 is not supported by this project because the installed Qt bindings crash during import on that interpreter.

```powershell
uv venv --python 3.13 .venv313
.\.venv313\Scripts\Activate.ps1
uv pip install --python .\.venv313\Scripts\python.exe -r Requirements.txt
python app.py
```

After setup, double-click `run_sentinel.bat` to launch the app with the supported environment.

Run the test suite with `python -m pytest`. Keep local LLM inference manual unless the computer has confirmed spare CPU/GPU/RAM capacity; set `AUTO_DIAGNOSTICS_ENABLED = True` in `config.py` only if automatic analysis is desired.

To build a standalone `.exe`, see `docs/PACKAGING_GUIDE.md` (or run `python build_exe.py`, which wraps PyInstaller via `sentinel.spec`).

## Dashboard panels

| View | What you see |
|---|---|
| **Overview** | Metric cards (CPU / RAM / Disk / GPU) with live values and progress bars, PC Health Score, live telemetry chart, recent alerts timeline, AI diagnostics card, threat & incident feed |
| **Logs** | Full event journal (telemetry notes, diagnostics runs, alerts) |
| **Alerts** | Historical + active threshold violations, loaded from SQLite |
| **Ask Sentinel** | Chat with the local model; telemetry, predictive data, recent sessions, and alerts are injected as context automatically |
| **Threats** | Active threat & incident feed |
| **Settings** | Hardware architecture, AI engine status, polling intervals, alert thresholds, auto-start toggle, driver audit |

## Configuration (`config.py`)

All tunables live in one place: refresh intervals (`UI_REFRESH_INTERVAL_MS`, `DB_LOG_INTERVAL_MS`), WMI cache (`WMI_SENSOR_INTERVAL_SECONDS`), alert thresholds (`THRESHOLDS`), debounce (`ALERT_DEBOUNCE_SECONDS`), snapshot retention (`RETENTION_DAYS`, auto-pruned on startup), auto-diagnostics (`AUTO_DIAGNOSTICS_ENABLED`, `AUTO_DIAG_COOLDOWN_SECONDS`), and the local-LLM backend (`LLM_BACKEND`: `"auto"` tries LM Studio on `:1234`, then Ollama on `:11434`; `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`).

## Project structure

```
app.py               Entry point → ui.dashboard.main()
config.py            Centralized settings (single source of truth)
sensors/             cpu, gpu, ram, disk, storage_health — each returns a dict,
                     each degrades to {"available": False} when its backend is missing
core/                game_mode, autostart, driver_manager, utilities
database/            SQLite manager (telemetry snapshots, alerts, gaming sessions,
                     hardware baselines, predictive events)
ai/                  analyzer (diagnostics worker), chat_engine (Ask Sentinel),
                     health (health score), predictive (cooling/SSD models),
                     prompts, recommendations
ui/                  dashboard (all views), chart_widget, alert_manager, theme
tests/               pytest suite (Windows-only tests skip cleanly elsewhere)
assets/              sentinel.ico
docs/                packaging guide, security notes
```

## Privacy posture

Local-first by design: SQLite database, logs, and config all live next to the app. The only network traffic the app ever initiates is `http://127.0.0.1:1234` / `:11434` when you use the AI chat or diagnostics with a local model server running. There is no telemetry upload, analytics, or update phoning-home.

<!-- coderabbit-ai-generated:v1 -->

# Compute Lab

Open **Compute Lab** for timed CPU, GPU, or combined tests with usage charts. CPU workers verify SHA-256 answers and report MB/s. GPU workers verify an OpenCL integer kernel against a CPU reference. These are workload throughput measurements, not universal benchmark scores or hardware stability certification.

## Optional GPU support

From the supported Python environment, run:

```powershell
python -m pip install -e ".[gpu]"
python app.py
```

A compatible GPU and vendor OpenCL driver are required. CPU-only OpenCL devices are excluded. When NVIDIA monitoring is active, compute must uniquely match that GPU by name. Ambiguous matches are rejected. Install the GPU extra before building an executable to bundle GPU support. Windows packaging and real GPU execution require verification on that hardware.

## Saved controls

Settings saves monitoring and database cadence, warning/critical thresholds, duration (5–300 seconds), worker count (up to 32), duty cycle, and stop temperatures in local `settings.json`. Invalid settings preserve the previous file. Load defaults populates the form; Apply & save activates it. During tests, monitoring and WMI thermal polling use a one-second cadence, then return to saved settings. Duty cycle is a workload target; actual utilization varies.

Tests stop on a measured temperature limit, stale telemetry, worker failure, manual Stop, window close, or time limit. Missing measured temperatures block startup unless the explicit unmonitored option is selected. Estimates never provide thermal protection. Application limits supplement hardware protections; they cannot guarantee protection from a stalled driver or OS.

Export results as JSON to retain device names, settings, baseline readings, observed peaks, verified throughput, elapsed time, and stop reason. The integer GPU workload uses about 8 MiB of device buffers and never changes clocks, voltage, or driver settings.

## Monitoring accuracy and performance

The CPU sensor selects the hottest recognized CPU temperature and excludes unrelated sensors. Estimated temperature/power sources remain labeled. Cooling assessment requires measured temperature and sustained package power; GPU hotspot assessment requires an actual hotspot reading. Missing inputs appear as unavailable. The health badge marks incomplete thermal coverage.

Slow SMART reads, driver scans, and cleanup utilities run outside the UI thread. Missing-driver probes are throttled. Driver inventory and actions report unsupported hosts or errors. Cleanup skips directories, symlinks, and files modified within 24 hours. Windows working-set trimming does not guarantee faster performance.

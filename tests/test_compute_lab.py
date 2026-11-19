"""Lifecycle, thermal guards, real CPU work, and atomic settings regression checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QProcess, QCoreApplication, QEvent
import pytest
from core.settings import load_settings, save_settings, validate
from ui.stress_lab import StressLab
from sensors.cpu import _get_cpu_temperature

@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def dispose_test_widgets(app):
    yield
    # Test widgets are top-level windows; production widgets are owned by the dashboard.
    for widget in app.topLevelWidgets():
        if isinstance(widget, StressLab):
            widget.stop()
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def sample(temp=45):
    return {"cpu": {"usage": 20, "temperature": temp, "temp_available": True},
            "gpu": {"available": False}, "ram": {"percent": 30}}


def test_settings_atomic_roundtrip_and_invalid_keeps_previous(tmp_path):
    path = tmp_path / "settings.json"
    values = validate({"refresh_ms": 5000})
    save_settings(values, path)
    assert load_settings(path)["refresh_ms"] == 5000
    values["thresholds"]["cpu_high"] = 99
    with pytest.raises(ValueError):
        save_settings(values, path)
    assert load_settings(path)["thresholds"]["cpu_high"] == 80
    path.write_text('{broken')
    assert load_settings(path)["refresh_ms"] == 2000


def test_cpu_does_not_use_drive_sensor_and_selects_hottest():
    from types import SimpleNamespace
    with patch("sensors.cpu.psutil") as ps, patch("sensors.cpu._read_wmi_cpu_sensors", return_value={"temperature": 0}):
        ps.sensors_temperatures.return_value = {"nvme": [SimpleNamespace(current=55)]}
        assert _get_cpu_temperature()[1] == "unavailable"
        ps.sensors_temperatures.return_value["coretemp"] = [SimpleNamespace(current=45), SimpleNamespace(current=80)]
        assert _get_cpu_temperature()[0] == 80


def test_real_cpu_worker_and_invalid_target():
    result = subprocess.run([sys.executable, "app.py", "--compute-worker", "cpu", "1", "10"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert rows[-1]["event"] == "complete"
    assert rows[-1]["rate"] > 0
    result = subprocess.run([sys.executable, "app.py", "--compute-worker", "invalid", "1", "10"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 1


def test_lab_guards_real_stop_and_restart(app):
    lab = StressLab(validate({"stress_seconds": 5, "stress_workers": 1, "stress_load": 10}))
    metrics = sample()
    metrics["cpu"]["is_estimated_temp"] = True
    lab.update_metrics(metrics)
    lab.start()
    assert not lab.running
    lab.update_metrics(sample())
    lab.start()
    assert lab.running
    processes = list(lab.processes)
    deadline = time.monotonic() + 3
    while not lab.rates and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    assert lab.rates
    lab.update_metrics(sample(90))
    assert not lab.running
    assert "Thermal limit" in lab.report["outcome"]
    assert all(p.state() == QProcess.NotRunning for p in processes)
    lab.update_metrics(sample())
    lab.start()
    lab.stop("Stopped by user")
    assert lab.start_button.isEnabled()
    assert lab.export_button.isEnabled()


def test_stale_telemetry_stops_even_unmonitored(app):
    lab = StressLab(validate({"stress_workers": 1}))
    lab.update_metrics(sample())
    lab.allow_unmonitored.setChecked(True)
    lab.start()
    lab.last_sample -= 20
    lab.tick()
    assert not lab.running
    assert "stale" in lab.report["outcome"]


def test_worker_driver_failure_never_becomes_success(app):
    lab = StressLab(validate({}))
    lab.update_metrics(sample())
    lab.target.setCurrentText("GPU")
    lab.allow_unmonitored.setChecked(True)
    with patch.dict(os.environ, {"OCL_ICD_VENDORS": "/nonexistent/sentinel-opencl"}):
        lab.start()
        deadline = time.monotonic() + 8
        while lab.running and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
    try:
        assert not lab.running
        assert "failed" in lab.report["outcome"].lower()
        assert lab.start_button.isEnabled()
    finally:
        lab.stop()


def test_completed_session_and_export(app, tmp_path):
    lab = StressLab(validate({"stress_seconds": 5, "stress_workers": 1, "stress_load": 10}))
    lab.update_metrics(sample())
    lab.start()
    deadline = time.monotonic() + 9
    while lab.running and time.monotonic() < deadline:
        lab.update_metrics(sample())
        app.processEvents()
        time.sleep(0.02)
    try:
        assert lab.report["outcome"].startswith("Completed")
        assert lab.report["throughput"]["cpu"]["rate"] > 0
        path = tmp_path / "result.json"
        with patch("ui.stress_lab.QFileDialog.getSaveFileName", return_value=(str(path), "JSON")):
            lab.export_button.click()
        assert json.loads(path.read_text())["target"] == "CPU"
    finally:
        lab.stop()


def test_unmeasured_predictions_are_unknown():
    from ai.predictive import PredictiveEngine
    from ai.health import calculate_health_score
    metrics = sample()
    metrics["cpu"].update(is_estimated_temp=True, power_watts=100, power_source="estimated_tdp_curve")
    result = PredictiveEngine().evaluate_system(metrics)
    assert result.cpu_thermal_resistance is None
    assert result.cooling_efficiency_percent is None
    assert result.gpu_hotspot_delta is None
    assert not calculate_health_score(metrics)["thermal_complete"]


def test_safe_cleanup_skips_recent_files_links_and_directories(tmp_path):
    from core.utilities import clean_disk_temp
    old = tmp_path / "old.tmp"
    old.write_bytes(b"old")
    os.utime(old, (time.time() - 172800, time.time() - 172800))
    recent = tmp_path / "recent.tmp"
    recent.write_bytes(b"recent")
    folder = tmp_path / "folder"
    folder.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(recent)
    except OSError as exc:
        pytest.skip(f"Symlinks require elevated privileges on this Windows environment: {exc}")
    with patch("core.utilities.tempfile.gettempdir", return_value=str(tmp_path)):
        ok, _, _ = clean_disk_temp()
    assert ok and not old.exists()
    assert recent.exists() and folder.exists() and link.is_symlink()


def test_gpustat_json_shape_and_missing_probe_cache():
    import sensors.gpu as gpu
    from unittest.mock import MagicMock
    stub = MagicMock()
    stub.GPUStatCollection.new_query.return_value.jsonify.return_value = {"gpus": [{"name": "Test GPU", "memory.used": 4, "memory.total": 8, "utilization.gpu": 60, "temperature.gpu": 50}]}
    with patch.object(gpu, "_ensure_nvml", return_value=False), patch.object(gpu, "_fallback_retry_at", 0), patch.object(gpu, "_fallback_cache", None), patch.dict(sys.modules, {"gpustat": stub}):
        assert gpu.get_gpu_info()["usage"] == 60
        assert gpu.get_gpu_info()["vram_total"] == 8 * 1024**2
        assert stub.GPUStatCollection.new_query.call_count == 1

"""Live, bounded CPU/GPU compute lab with thermal supervision and export."""
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QTemporaryDir, QTimer, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QProgressBar, QCheckBox, QFileDialog)
from ui.chart_widget import TelemetryChartWidget


class StressLab(QWidget):
    active_changed = Signal(bool)

    def __init__(self, settings):
        super().__init__()
        self.setStyleSheet("""
            QPushButton { background: #12344c; color: #e0f2fe; border: 1px solid #247292; border-radius: 6px; padding: 8px 14px; }
            QPushButton:hover { background: #155e75; }
            QPushButton:disabled { background: #15202d; color: #64748b; border-color: #243244; }
            QSpinBox, QComboBox { background: #101f30; color: #e2e8f0; border: 1px solid #334155; border-radius: 4px; padding: 5px; }
            QProgressBar { background: #101f30; border: 1px solid #243244; text-align: center; color: #cbd5e1; }
            QProgressBar::chunk { background: #0891b2; }
        """)
        self.settings = settings
        self.processes = []
        self.metrics = {}
        self.last_sample = 0.0
        self.running = False
        self.report = None
        self.buffers = {}
        self.output_paths = {}
        self.output_offsets = {}
        self.process_kinds = {}
        self.ipc_dir = QTemporaryDir()
        self.rates = {}
        self.completed = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        title = QLabel("Compute Lab")
        title.setStyleSheet("font-size: 30px; font-weight: 700; color: #38bdf8")
        layout.addWidget(title)
        description = QLabel(
            "Real workloads. Verified answers. Live hardware feedback.\n"
            "CPU: SHA-256 integrity & throughput • GPU: OpenCL integer compute & verification.\n"
            "Tests create heat and consume power. Stop limits are app safeguards, not hardware guarantees. "
            "Duty cycle is a workload target; actual device usage varies."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        row = QHBoxLayout()
        self.target = QComboBox()
        self.target.addItems(["CPU", "GPU", "CPU + GPU"])
        self.start_button = QPushButton("Start test")
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton("Stop now")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(lambda: self.stop("Stopped by user"))
        self.export_button = QPushButton("Export result JSON")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export)
        for widget in (self.target, self.start_button, self.stop_button, self.export_button):
            row.addWidget(widget)
        layout.addLayout(row)
        self.allow_unmonitored = QCheckBox("Allow test without a measured temperature (automatic thermal protection unavailable)")
        self.allow_unmonitored.setToolTip("Estimated temperatures never count as thermal protection. Duration and manual stop remain active.")
        layout.addWidget(self.allow_unmonitored)
        self.config_label = QLabel()
        layout.addWidget(self.config_label)
        self.live = QLabel("Waiting for live telemetry…")
        self.live.setStyleSheet("font-size: 17px; color: #67e8f9; padding: 16px; background: #101828; border-radius: 10px")
        self.live.setWordWrap(True)
        layout.addWidget(self.live)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.chart = TelemetryChartWidget("Compute session • latest 60 samples")
        layout.addWidget(self.chart, 1)
        self.status = QLabel("Ready. Configure duration, worker count, load, and stop limits in Settings.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("padding: 14px; color: #cbd5e1; background: #101828; border-radius: 10px")
        layout.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.tick)
        self.apply_settings(settings)

    def apply_settings(self, settings):
        self.settings = settings
        self.config_label.setText(
            f"Next test: {settings['stress_seconds']}s • {settings['stress_workers']} CPU workers • "
            f"{settings['stress_load']}% duty cycle • Stop: CPU {settings['cpu_limit']}°C / GPU {settings['gpu_limit']}°C"
        )

    def temperature(self, kind):
        data = self.metrics.get(kind, {})
        value = data.get("temperature", 0)
        if not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            return None
        if kind == "cpu" and (not data.get("temp_available") or data.get("is_estimated_temp")):
            return None
        if kind == "gpu" and not data.get("available"):
            return None
        return float(value)

    def update_metrics(self, metrics):
        self.metrics = metrics
        self.last_sample = time.monotonic()
        texts = []
        for kind in ("cpu", "gpu"):
            data = metrics.get(kind, {})
            temp = self.temperature(kind)
            usage = data.get("usage", 0)
            temp_text = f"{temp:.1f}°C measured" if temp is not None else "temperature unavailable"
            texts.append(f"{kind.upper()} {usage:.1f}% • {temp_text}")
            if self.running and kind in self.kinds:
                self.report["peak_usage"][kind] = max(self.report["peak_usage"].get(kind, 0), usage)
                if temp is not None:
                    self.report["peak_temperature"][kind] = max(self.report["peak_temperature"].get(kind, 0), temp)
        self.live.setText("\n".join(texts))
        if self.running:
            self.chart.add_snapshot(metrics.get("cpu", {}).get("usage", 0), metrics.get("ram", {}).get("percent", 0), metrics.get("gpu", {}).get("usage", 0))
            self.check_thermal()

    def check_thermal(self):
        for kind in self.kinds:
            temp = self.temperature(kind)
            if temp is not None and temp >= self.active_settings[f"{kind}_limit"]:
                self.stop(f"Thermal limit reached: {kind.upper()} {temp:.1f}°C")
                return False
            if temp is None and not self.unmonitored:
                self.stop(f"Measured {kind.upper()} temperature lost")
                return False
        return True

    def start(self):
        if self.running:
            return
        self.kinds = ["cpu", "gpu"] if self.target.currentIndex() == 2 else [self.target.currentText().lower()]
        self.active_settings = dict(self.settings)
        self.unmonitored = self.allow_unmonitored.isChecked()
        if time.monotonic() - self.last_sample > max(5, self.settings["refresh_ms"] / 1000 * 3):
            self.status.setText("Waiting for fresh telemetry. Try again after monitoring updates.")
            return
        for kind in self.kinds:
            temp = self.temperature(kind)
            if temp is not None and temp >= self.active_settings[f"{kind}_limit"]:
                self.status.setText(f"Cannot start: {kind.upper()} is already at its stop temperature.")
                return
            if temp is None and not self.unmonitored:
                self.status.setText(f"No measured {kind.upper()} temperature. Enable the explicit unmonitored option to proceed.")
                return
        self.report = {"started_at": datetime.now().isoformat(), "target": self.target.currentText(),
                       "settings": dict(self.active_settings), "thermal_protection": not self.unmonitored,
                       "baseline": {k: {"usage": self.metrics.get(k, {}).get("usage"), "temperature": self.temperature(k)} for k in self.kinds},
                       "peak_usage": {}, "peak_temperature": {}, "throughput": {}, "devices": {}}
        self.running = True
        self.active_changed.emit(True)
        self.started = time.monotonic()
        self.processes = []
        self.buffers = {}
        self.rates = {}
        self.completed = set()
        self.progress.setValue(0)
        self.chart.cpu_data.clear()
        self.chart.ram_data.clear()
        self.chart.gpu_data.clear()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.target.setEnabled(False)
        self.allow_unmonitored.setEnabled(False)
        self.status.setText("Starting verified compute workers…")
        for kind in self.kinds:
            count = self.settings["stress_workers"] if kind == "cpu" else 1
            for _ in range(count):
                process = QProcess(self)
                self.processes.append(process)
                self.buffers[process] = b""
                path = str(Path(self.ipc_dir.path()) / f"worker-{time.monotonic_ns()}.jsonl")
                self.process_kinds[process] = kind
                self.output_paths[process] = path
                self.output_offsets[process] = 0
                env = QProcessEnvironment.systemEnvironment()
                env.insert("SENTINEL_COMPUTE_OUTPUT", path)
                if self.metrics.get("gpu", {}).get("available"):
                    env.insert("SENTINEL_GPU_NAME", self.metrics["gpu"].get("name", ""))
                else:
                    env.remove("SENTINEL_GPU_NAME")
                process.setProcessEnvironment(env)
                process.readyReadStandardOutput.connect(lambda p=process, k=kind: self.read_output(p, k))
                process.finished.connect(lambda code, state, p=process: self.finished(p, code))
                process.errorOccurred.connect(lambda error, p=process: self.process_error(p))
                args = [] if getattr(sys, "frozen", False) else [str(Path(__file__).resolve().parents[1] / "app.py")]
                args += ["--compute-worker", kind, str(self.settings["stress_seconds"]), str(self.settings["stress_load"])]
                process.start(sys.executable, args)
        self.timer.start()

    def read_output(self, process, kind):
        if process not in self.output_paths:
            return
        try:
            with open(self.output_paths[process], "rb") as stream:
                stream.seek(self.output_offsets[process])
                self.buffers[process] += stream.read()
                self.output_offsets[process] = stream.tell()
        except FileNotFoundError:
            pass
        self.buffers[process] += bytes(process.readAllStandardOutput())
        lines = self.buffers[process].split(b"\n")
        self.buffers[process] = lines.pop()
        for line in lines:
            try:
                data = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not self.running:
                continue
            if data.get("event") == "error":
                self.stop(f"Workload failed: {data.get('message')}")
                return
            if data.get("event") == "ready":
                self.report["devices"][kind] = data["device"]
            if "rate" in data:
                self.rates[process] = (kind, data["rate"], data["unit"])
            if data.get("event") == "complete":
                self.completed.add(process)

    def finished(self, process, code):
        if process not in self.process_kinds:
            return
        self.read_output(process, self.process_kinds[process])
        if self.running and (code != 0 or process not in self.completed):
            self.stop(f"Worker exited unexpectedly (code {code}); result is incomplete")
        elif self.running and all(p.state() == QProcess.NotRunning for p in self.processes):
            self.stop("Completed: all compute checks passed")

    def process_error(self, process):
        if self.running:
            self.stop(f"Worker error: {process.errorString()}")

    def tick(self):
        if not self.running:
            return
        for process in list(self.processes):
            self.read_output(process, self.process_kinds[process])
            if not self.running:
                return
        elapsed = time.monotonic() - self.started
        seconds = self.active_settings["stress_seconds"]
        self.progress.setValue(min(100, int(elapsed / seconds * 100)))
        if time.monotonic() - self.last_sample > max(5, self.active_settings["refresh_ms"] / 1000 * 3):
            self.stop("Telemetry became stale; test stopped")
            return
        # Includes driver startup/compilation in a bounded wall-clock watchdog.
        if elapsed > seconds + 15:
            self.stop("Worker time limit exceeded")
            return
        self.check_thermal()
        if not self.running:
            return
        totals = self.throughput()
        rates = " • ".join(f"{k.upper()} {v['rate']:.1f} {v['unit']}" for k, v in totals.items())
        self.status.setText(f"Running {elapsed:.1f}s / {seconds}s • {rates or 'initializing compute backend'}")

    def throughput(self):
        totals = {}
        for kind, rate, unit in self.rates.values():
            total = totals.setdefault(kind, {"rate": 0.0, "unit": unit})
            total["rate"] += rate
        return totals

    def stop(self, reason="Stopped on application exit"):
        if not self.running:
            return
        self.running = False
        self.active_changed.emit(False)
        self.timer.stop()
        for process in self.processes:
            if process.state() != QProcess.NotRunning:
                process.kill()
                process.waitForFinished(1000)
        self.report.update(outcome=reason, elapsed_seconds=round(time.monotonic() - self.started, 2), throughput=self.throughput())
        self.status.setText(reason + " • Result includes baseline, peaks, device, settings, and verified throughput.")
        if reason.startswith("Completed"):
            self.progress.setValue(100)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.target.setEnabled(True)
        self.allow_unmonitored.setEnabled(True)
        self.export_button.setEnabled(True)
        for path in self.output_paths.values():
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass
        for process in self.processes:
            process.deleteLater()
        self.processes = []
        self.buffers.clear()
        self.output_paths.clear()
        self.output_offsets.clear()
        self.process_kinds.clear()

    def export(self):
        if not self.report:
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Export compute result", "sentinel-compute.json", "JSON (*.json)")
        if filename:
            try:
                Path(filename).write_text(json.dumps(self.report, indent=2), encoding="utf-8")
                self.status.setText(f"Result exported to {filename}")
            except OSError as exc:
                self.status.setText(f"Could not export result: {exc}")

"""Editable preferences applied to the running telemetry worker."""
import os
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QSpinBox, QPushButton, QLabel, QHBoxLayout
from core.settings import DEFAULTS, save_settings


class PreferencesWidget(QWidget):
    applied = Signal(dict)

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
        layout = QVBoxLayout(self)
        title = QLabel("Live controls • saved on this computer")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #38bdf8")
        layout.addWidget(title)
        form = QFormLayout()
        self.fields = {}
        for key, label, lo, hi, suffix in (
            ("refresh_ms", "Monitoring interval", 1000, 10000, " ms"),
            ("snapshot_ms", "Database snapshot interval", 10000, 300000, " ms"),
            ("stress_seconds", "Default test duration", 5, 300, " s"),
            ("stress_workers", "CPU worker processes", 1, os.cpu_count() or 1, ""),
            ("stress_load", "Workload duty cycle", 10, 100, " %"),
            ("cpu_limit", "CPU test stop temperature", 50, 95, " °C"),
            ("gpu_limit", "GPU test stop temperature", 50, 90, " °C"),
        ):
            spin = QSpinBox()
            spin.setRange(lo, min(32, hi) if key == "stress_workers" else hi)
            spin.setMaximumWidth(260)
            spin.setSuffix(suffix)
            spin.setValue(settings[key])
            self.fields[key] = spin
            form.addRow(label, spin)
        self.thresholds = {}
        for prefix, label in (("cpu", "CPU usage %"), ("ram", "RAM usage %"), ("disk", "Disk usage %"), ("gpu_temp", "GPU temperature °C")):
            row = QHBoxLayout()
            for level in ("high", "critical"):
                key = f"{prefix}_{level}"
                spin = QSpinBox()
                spin.setRange(1, 100)
                spin.setValue(int(settings["thresholds"][key]))
                self.thresholds[key] = spin
                row.addWidget(QLabel("Warning" if level == "high" else "Critical"))
                row.addWidget(spin)
            form.addRow(label, row)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        save = QPushButton("Apply & save settings")
        save.clicked.connect(self.save)
        reset = QPushButton("Load defaults")
        reset.clicked.connect(self.reset)
        buttons.addWidget(save)
        buttons.addWidget(reset)
        layout.addLayout(buttons)
        self.message = QLabel("Changes apply after saving. Stress limits apply to the next test.")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

    def reset(self):
        for key, spin in self.fields.items():
            spin.setValue(DEFAULTS[key])
        for key, spin in self.thresholds.items():
            spin.setValue(int(DEFAULTS["thresholds"][key]))
        self.message.setText("Defaults loaded. Apply & save to use them.")

    def save(self):
        data = dict(self.settings)
        data.update({k: spin.value() for k, spin in self.fields.items()})
        data["thresholds"] = dict(self.settings["thresholds"], **{k: s.value() for k, s in self.thresholds.items()})
        try:
            self.settings = save_settings(data)
        except (OSError, ValueError) as exc:
            self.message.setText(f"Settings were not saved: {exc}")
            return
        self.applied.emit(self.settings)
        self.message.setText("Saved. Monitoring cadence and alert thresholds applied immediately.")

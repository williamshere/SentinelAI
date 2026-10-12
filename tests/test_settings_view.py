"""
test_settings_view.py - Validates Settings View layout, QScrollArea wrapping,
card ID scoping, and settings components in ui/dashboard.py.
"""
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestSettingsViewStructure(unittest.TestCase):

    def setUp(self):
        with open(PROJECT_ROOT / "ui" / "dashboard.py", "r", encoding="utf-8") as f:
            self.dashboard_code = f.read()

    def test_scroll_area_wrapping(self):
        """Ensures the settings view wraps content in a responsive QScrollArea."""
        self.assertIn("scroll = QScrollArea()", self.dashboard_code)
        self.assertIn("scroll.setWidgetResizable(True)", self.dashboard_code)
        self.assertIn("scroll.setWidget(container)", self.dashboard_code)
        self.assertIn("return scroll", self.dashboard_code)

    def test_scoped_card_ids(self):
        """Ensures all settings cards use scoped QSS object names to prevent style leakage."""
        card_ids = [
            "cardSysArch",
            "cardAiEngine",
            "cardTelemetryDb",
            "cardAlertThresh",
            "cardAutostart",
            "cardDrivers",
        ]
        self.assertIn('QFrame#{card_id}', self.dashboard_code)
        self.assertIn('QFrame#cardAutostart', self.dashboard_code)
        self.assertIn('QFrame#cardDrivers', self.dashboard_code)
        for cid in card_ids:
            self.assertIn(cid, self.dashboard_code, f"Missing card ID {cid}")

    def test_label_border_reset(self):
        """Ensures child QLabels explicitly reset borders and padding."""
        self.assertIn("border: none;", self.dashboard_code)
        self.assertIn("background: transparent;", self.dashboard_code)
        self.assertIn("padding: 0px;", self.dashboard_code)

    def test_dynamic_indicators(self):
        """Ensures dynamic driver indicators are referenced for live telemetry updates."""
        self.assertIn("self.settings_cpu_driver_val", self.dashboard_code)
        self.assertIn("self.settings_elevation_val", self.dashboard_code)
        self.assertIn("self.settings_cpu_power_val", self.dashboard_code)
        self.assertIn("self.settings_autostart_status", self.dashboard_code)

    def test_interactive_action_buttons(self):
        """Ensures both Auto-Start and Driver Audit buttons exist and connect to handlers."""
        self.assertIn("btn_autostart.clicked.connect(on_toggle_clicked)", self.dashboard_code)
        self.assertIn("btn_open_drivers.clicked.connect(self._show_drivers_dialog)", self.dashboard_code)

    def test_resilient_icon_paths(self):
        """Ensures the application tray icon searches _MEIPASS and executable root for PyInstaller."""
        self.assertIn("getattr(sys, \"_MEIPASS\"", self.dashboard_code)
        self.assertIn("Path(sys.executable).resolve().parent", self.dashboard_code)


if __name__ == "__main__":
    unittest.main()

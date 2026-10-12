"""
tests/test_alert_manager.py - Unit tests for Sentinel AI alert debouncing and notification dispatch.
Validates hysteresis threshold boundaries, state transitions, units formatting,
and automated critical alert notification callback triggers.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.alert_manager import AlertManager, AlertState


class TestAlertManager(unittest.TestCase):

    def test_initial_state_normal(self):
        am = AlertManager(hysteresis_delta=3.0)
        changed, state, msg = am.evaluate("cpu", 50.0, 80.0, 90.0)
        self.assertFalse(changed)
        self.assertEqual(state, AlertState.NORMAL)
        self.assertIsNone(msg)

    def test_warning_escalation(self):
        am = AlertManager(hysteresis_delta=3.0)
        changed, state, msg = am.evaluate("cpu", 82.0, 80.0, 90.0)
        self.assertTrue(changed)
        self.assertEqual(state, AlertState.WARNING)
        self.assertEqual(msg, "CPU High: 82.0%")

        # Fluctuation above threshold should not re-trigger
        changed2, state2, msg2 = am.evaluate("cpu", 84.0, 80.0, 90.0)
        self.assertFalse(changed2)
        self.assertEqual(state2, AlertState.WARNING)
        self.assertIsNone(msg2)

    def test_critical_escalation_and_notification_callback(self):
        mock_cb = MagicMock()
        am = AlertManager(hysteresis_delta=3.0, notification_callback=mock_cb)

        # Escalate to critical
        changed, state, msg = am.evaluate("gpu_temp", 86.5, 75.0, 85.0)
        self.assertTrue(changed)
        self.assertEqual(state, AlertState.CRITICAL)
        self.assertEqual(msg, "GPU_TEMP Critical: 86.5°C")

        # Verify callback invoked with exact parameters
        mock_cb.assert_called_once_with("gpu_temp", "GPU_TEMP Critical: 86.5°C", AlertState.CRITICAL)

        # Re-evaluating in critical should not re-trigger callback
        mock_cb.reset_mock()
        changed2, state2, _ = am.evaluate("gpu_temp", 88.0, 75.0, 85.0)
        self.assertFalse(changed2)
        self.assertEqual(state2, AlertState.CRITICAL)
        mock_cb.assert_not_called()

    def test_hysteresis_recovery(self):
        am = AlertManager(hysteresis_delta=3.0)
        am.evaluate("cpu", 85.0, 80.0, 90.0)  # WARNING

        # Value dropping slightly below threshold (78%) is within hysteresis (80 - 3 = 77)
        # Should stay in WARNING
        changed, state, _ = am.evaluate("cpu", 78.5, 80.0, 90.0)
        self.assertFalse(changed)
        self.assertEqual(state, AlertState.WARNING)

        # Value dropping below hysteresis boundary (<77%) normalizes
        changed2, state2, msg2 = am.evaluate("cpu", 76.0, 80.0, 90.0)
        self.assertTrue(changed2)
        self.assertEqual(state2, AlertState.NORMAL)
        self.assertEqual(msg2, "CPU Normalized: 76.0%")

    def test_units_formatting_temperature_vs_percentage(self):
        am = AlertManager()
        # Temperature metric gets °C
        _, _, msg_temp = am.evaluate("cpu_temp", 88.0, 75.0, 85.0)
        self.assertIn("°C", msg_temp)

        # Percentage metric gets %
        _, _, msg_ram = am.evaluate("ram_usage", 92.0, 80.0, 90.0)
        self.assertIn("%", msg_ram)


if __name__ == "__main__":
    unittest.main()

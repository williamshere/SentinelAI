"""
tests/test_game_mode.py - Unit tests for Sentinel AI Game Mode & Session Detection.
Validates process scanning, telemetry aggregation, thermal headroom calculations,
database session persistence, and AlertManager Do-Not-Disturb suppression.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.game_mode import GameModeManager, GamingSessionSummary, KNOWN_GAME_PROCESSES
from ui.alert_manager import AlertManager, AlertState


class TestGameMode(unittest.TestCase):

    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_db.start_gaming_session.return_value = 42
        self.mock_db.end_gaming_session.return_value = True

        self.alert_mgr = AlertManager()
        self.manager = GameModeManager(
            db_manager=self.mock_db,
            alert_manager=self.alert_mgr,
        )

    def test_known_game_processes_table(self):
        self.assertIn("overwatch.exe", KNOWN_GAME_PROCESSES)
        self.assertEqual(KNOWN_GAME_PROCESSES["overwatch.exe"], "Overwatch 2")
        self.assertIn("marvelrivals.exe", KNOWN_GAME_PROCESSES)
        self.assertEqual(KNOWN_GAME_PROCESSES["marvelrivals.exe"], "Marvel Rivals")

    def test_check_running_games_overwatch(self):
        mock_psutil = MagicMock()
        proc1 = MagicMock()
        proc1.info = {"name": "chrome.exe"}
        proc2 = MagicMock()
        proc2.info = {"name": "Overwatch.exe"}
        mock_psutil.process_iter.return_value = [proc1, proc2]

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            found, title, proc_name = self.manager.check_running_games()
            self.assertTrue(found)
            self.assertEqual(title, "Overwatch 2")
            self.assertEqual(proc_name, "overwatch.exe")

    def test_check_running_games_marvel_rivals(self):
        mock_psutil = MagicMock()
        proc1 = MagicMock()
        proc1.info = {"name": "Discord.exe"}
        proc2 = MagicMock()
        proc2.info = {"name": "Marvel-Win64-Shipping.exe"}
        mock_psutil.process_iter.return_value = [proc1, proc2]

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            found, title, proc_name = self.manager.check_running_games()
            self.assertTrue(found)
            self.assertEqual(title, "Marvel Rivals")
            self.assertEqual(proc_name, "marvel-win64-shipping.exe")

    def test_check_running_games_none_active(self):
        mock_psutil = MagicMock()
        proc1 = MagicMock()
        proc1.info = {"name": "explorer.exe"}
        mock_psutil.process_iter.return_value = [proc1]

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            found, title, proc_name = self.manager.check_running_games()
            self.assertFalse(found)
            self.assertIsNone(title)
            self.assertIsNone(proc_name)

    def test_session_lifecycle_and_telemetry_aggregation(self):
        self.manager._start_session("Overwatch 2", "overwatch.exe")
        self.assertTrue(self.manager.is_active)
        self.assertEqual(self.manager.current_game, "Overwatch 2")
        self.assertEqual(self.manager.session_id, 42)
        self.assertTrue(self.alert_mgr.is_game_mode())
        self.mock_db.start_gaming_session.assert_called_once_with(
            game_title="Overwatch 2",
            process_name="overwatch.exe"
        )

        samples = [
            {"cpu": {"temperature": 68.0, "power_watts": 65.0, "usage": 45.0},
             "gpu": {"temperature": 65.0, "power_watts": 180.0, "usage": 92.0}},
            {"cpu": {"temperature": 72.0, "power_watts": 75.0, "usage": 55.0},
             "gpu": {"temperature": 70.0, "power_watts": 210.0, "usage": 98.0}},
            {"cpu": {"temperature": 75.0, "power_watts": 85.0, "usage": 60.0},
             "gpu": {"temperature": 74.0, "power_watts": 225.0, "usage": 99.0}},
        ]
        for s in samples:
            self.manager.sample_telemetry(s)

        self.assertEqual(len(self.manager.samples), 3)

        summary = self.manager._end_session()
        self.assertIsNotNone(summary)
        self.assertFalse(self.manager.is_active)
        self.assertFalse(self.alert_mgr.is_game_mode())

        self.assertEqual(summary.max_gpu_temp, 74.0)
        self.assertAlmostEqual(summary.avg_gpu_temp, 69.7, places=1)
        self.assertEqual(summary.max_gpu_power_watts, 225.0)
        self.assertEqual(summary.max_cpu_temp, 75.0)
        self.assertEqual(summary.thermal_headroom_c, 16.0)
        self.assertEqual(summary.throttle_incidents, 0)
        self.assertEqual(summary.health_score_impact, 0.0)

        self.mock_db.end_gaming_session.assert_called_once()
        call_args = self.mock_db.end_gaming_session.call_args[1]
        self.assertEqual(call_args["session_id"], 42)
        self.assertEqual(call_args["stats"]["max_gpu_temp"], 74.0)

    def test_manual_mode_toggle(self):
        is_active, msg = self.manager.toggle_manual_mode()
        self.assertTrue(is_active)
        self.assertTrue(self.manager.is_active)
        self.assertIn("activated manually", msg)

        is_active2, msg2 = self.manager.toggle_manual_mode()
        self.assertFalse(is_active2)
        self.assertFalse(self.manager.is_active)
        self.assertIn("deactivated manually", msg2)

    def test_alert_manager_dnd_behavior(self):
        notification_calls = []
        def notif_callback(k, m, s):
            notification_calls.append((k, m, s))

        alert = AlertManager(notification_callback=notif_callback)

        alert.evaluate("cpu_temp", 92.0, warn_threshold=80.0, crit_threshold=90.0)
        self.assertEqual(len(notification_calls), 1)

        alert.set_game_mode(True)
        self.assertTrue(alert.is_game_mode())

        alert._states.clear()
        notification_calls.clear()

        # Warning alert should not trigger notification
        alert.evaluate("cpu_temp", 85.0, warn_threshold=80.0, crit_threshold=90.0)
        self.assertEqual(len(notification_calls), 0)


if __name__ == "__main__":
    unittest.main()

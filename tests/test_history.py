"""
tests/test_history.py - Verification for History & Trends data layer.
Validates range queries, downsampling, stats aggregation, gaming-session
overlap lookup, and fail-closed metric validation in database/manager.py.
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.manager import DatabaseManager


def _ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class TestHistoryQueries(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(db_path=Path(self.temp_dir.name) / "hist.db")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.now = now
        # 3 snapshots inside the last hour, 1 snapshot 3 days old
        rows = [
            (now - timedelta(minutes=30), 10.0, 40.0),
            (now - timedelta(minutes=20), 20.0, 50.0),
            (now - timedelta(minutes=10), 30.0, 60.0),
            (now - timedelta(days=3), 99.0, 99.0),
        ]
        with self.db._get_connection() as conn:
            for ts, cpu, gpu_temp in rows:
                conn.execute(
                    "INSERT INTO telemetry_snapshots (timestamp, cpu_usage, ram_percent, ram_used_gb, disk_percent, gpu_temp) VALUES (?, ?, 50.0, 8.0, 40.0, ?);",
                    (_ts(ts), cpu, gpu_temp),
                )
            conn.commit()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_series_excludes_out_of_range_rows(self):
        series = self.db.get_history_series(hours=1, metric="cpu_usage")
        self.assertEqual(len(series), 3)
        self.assertEqual([v for _, v in series], [10.0, 20.0, 30.0])

    def test_stats_min_avg_max_count(self):
        stats = self.db.get_history_stats(hours=1, metric="gpu_temp")
        self.assertEqual(stats["count"], 3)
        self.assertAlmostEqual(stats["min"], 40.0)
        self.assertAlmostEqual(stats["avg"], 50.0)
        self.assertAlmostEqual(stats["max"], 60.0)

    def test_stats_empty_range_returns_none_values(self):
        stats = self.db.get_history_stats(hours=0.001, metric="cpu_usage")
        self.assertEqual(stats["count"], 0)
        self.assertIsNone(stats["min"])
        self.assertIsNone(stats["avg"])
        self.assertIsNone(stats["max"])

    def test_series_downsamples_to_max_points(self):
        with self.db._get_connection() as conn:
            base = self.now - timedelta(minutes=59)
            for i in range(600):
                conn.execute(
                    "INSERT INTO telemetry_snapshots (timestamp, cpu_usage, ram_percent, ram_used_gb, disk_percent) VALUES (?, ?, 50.0, 8.0, 40.0);",
                    (_ts(base + timedelta(seconds=i * 5)), float(i % 100)),
                )
            conn.commit()
        series = self.db.get_history_series(hours=1, metric="cpu_usage", max_points=60)
        self.assertLessEqual(len(series), 60)
        self.assertGreater(len(series), 0)

    def test_invalid_metric_fails_closed(self):
        with self.assertRaises(ValueError):
            self.db.get_history_series(hours=1, metric="cpu_usage; DROP TABLE telemetry_snapshots")
        with self.assertRaises(ValueError):
            self.db.get_history_stats(hours=1, metric="not_a_column")

    def test_snapshots_in_range_for_csv(self):
        start = self.now - timedelta(hours=1)
        rows = self.db.get_snapshots_in_range(start, self.now + timedelta(minutes=1))
        self.assertEqual(len(rows), 3)
        self.assertIn("gpu_temp", rows[0])

    def test_gaming_sessions_overlap_range(self):
        sid = self.db.start_gaming_session("Test Game", "game.exe")
        self.db.end_gaming_session(sid, {"duration_seconds": 120})
        start = self.now - timedelta(hours=1)
        found = self.db.get_gaming_sessions_in_range(start, self.now + timedelta(minutes=1))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["game_title"], "Test Game")
        old = self.db.get_gaming_sessions_in_range(
            self.now - timedelta(days=5), self.now - timedelta(days=4)
        )
        self.assertEqual(len(old), 0)


class TestHistoryViewStructure(unittest.TestCase):

    def setUp(self):
        with open(PROJECT_ROOT / "ui" / "dashboard.py", encoding="utf-8") as f:
            self.code = f.read()
        with open(PROJECT_ROOT / "ui" / "theme.py", encoding="utf-8") as f:
            self.theme = f.read()

    def test_history_view_and_nav_registered(self):
        self.assertIn("_create_history_view", self.code)
        self.assertIn("History", self.code)
        self.assertIn("self.history_view", self.code)

    def test_history_controls_and_csv_export(self):
        self.assertIn("history_range_combo", self.code)
        self.assertIn("history_metric_combo", self.code)
        self.assertIn("_export_history_csv", self.code)
        self.assertIn("QFileDialog", self.code)

    def test_blue_black_history_theme(self):
        self.assertIn("HISTORY_BG", self.theme)
        self.assertIn("HISTORY_ACCENT", self.theme)


if __name__ == "__main__":
    unittest.main()
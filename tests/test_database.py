"""
tests/test_database.py - Verification for SQLite database operations.
Validates WAL mode, telemetry persistence including CPU/GPU thermals & wattage,
alert journaling, retention pruning, and non-destructive schema migrations.
"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.manager import DatabaseManager


class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_sentinel.db"
        self.db = DatabaseManager(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_initialization(self):
        self.assertTrue(self.db.db_path.exists())
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0]
            self.assertEqual(mode.lower(), "wal")

    def test_insert_and_fetch_snapshot_with_cpu_thermal_and_power(self):
        sample_metrics = {
            "cpu": {
                "usage": 18.5,
                "frequency": 4800.0,
                "temperature": 47.5,
                "power_watts": 62.0,
            },
            "ram": {"percent": 42.0, "used": 14 * (1024 ** 3)},
            "disk": {"percent": 35.0},
            "gpu": {
                "available": True,
                "usage": 32.0,
                "temperature": 55.0,
                "power_watts": 115.0,
                "vram_used": 4 * (1024 ** 3),
            },
        }

        row_id = self.db.insert_snapshot(sample_metrics)
        self.assertGreater(row_id, 0)

        recent = self.db.get_recent_metrics(minutes=10)
        self.assertEqual(len(recent), 1)
        row = recent[0]
        self.assertEqual(row["cpu_usage"], 18.5)
        self.assertEqual(row["cpu_freq"], 4800.0)
        self.assertEqual(row["cpu_temp"], 47.5)
        self.assertEqual(row["cpu_power_watts"], 62.0)
        self.assertEqual(row["gpu_temp"], 55.0)
        self.assertEqual(row["gpu_power_watts"], 115.0)

    def test_insert_and_fetch_alert(self):
        alert_id = self.db.insert_alert("cpu_high", "warning", "High CPU usage: 82.5%")
        self.assertGreater(alert_id, 0)

        alerts = self.db.get_recent_alerts(limit=5)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_key"], "cpu_high")
        self.assertEqual(alerts[0]["severity"], "warning")
        self.assertIn("High CPU usage", alerts[0]["message"])

    def test_prune_old_records(self):
        self.db.insert_alert("test_key", "info", "Test info message")
        deleted_snapshots, deleted_alerts = self.db.prune_old_records(retention_days=7)
        self.assertIsInstance(deleted_snapshots, int)
        self.assertIsInstance(deleted_alerts, int)

    def test_schema_migration_idempotent(self):
        """Simulate older database schema without cpu_temp and verify non-destructive migration."""
        legacy_dir = tempfile.TemporaryDirectory()
        legacy_db_path = Path(legacy_dir.name) / "legacy_sentinel.db"

        # Create legacy table without cpu_temp and cpu_power_watts
        conn = sqlite3.connect(str(legacy_db_path))
        conn.execute("""
            CREATE TABLE telemetry_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                cpu_usage REAL NOT NULL,
                cpu_freq REAL,
                ram_percent REAL NOT NULL,
                ram_used_gb REAL NOT NULL,
                disk_percent REAL NOT NULL,
                gpu_usage REAL,
                gpu_temp REAL,
                gpu_power_watts REAL,
                gpu_vram_used_gb REAL
            );
        """)
        conn.execute("""
            INSERT INTO telemetry_snapshots (
                timestamp, cpu_usage, cpu_freq, ram_percent, ram_used_gb, disk_percent,
                gpu_usage, gpu_temp, gpu_power_watts, gpu_vram_used_gb
            ) VALUES (CURRENT_TIMESTAMP, 25.0, 4200.0, 40.0, 12.0, 30.0, 10.0, 45.0, 80.0, 2.0);
        """)
        conn.commit()
        conn.close()

        # Instantiate DatabaseManager on legacy database
        migrated_db = DatabaseManager(db_path=legacy_db_path)

        with migrated_db._get_connection() as c:
            cursor = c.cursor()
            cursor.execute("PRAGMA table_info(telemetry_snapshots);")
            cols = {r["name"] for r in cursor.fetchall()}
            self.assertIn("cpu_temp", cols)
            self.assertIn("cpu_power_watts", cols)

            # Ensure existing row preserved
            cursor.execute("SELECT cpu_usage, cpu_temp FROM telemetry_snapshots;")
            row = cursor.fetchone()
            self.assertEqual(row["cpu_usage"], 25.0)
            self.assertIsNone(row["cpu_temp"])  # None for legacy rows prior to migration

        legacy_dir.cleanup()


if __name__ == "__main__":
    unittest.main()

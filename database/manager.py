"""
database/manager.py - SQLite telemetry and alert persistence manager.
Supports CPU and GPU thermal/wattage metrics with automatic schema migration.
"""
import threading
from contextlib import contextmanager
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from config import DATABASE_PATH, RETENTION_DAYS
except ImportError:
    DATABASE_PATH = Path(__file__).resolve().parent / "sentinel.db"
    RETENTION_DAYS = 7


class DatabaseManager:
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Yield a short-lived SQLite connection and always release its file handle.

        SQLite's connection context manager commits transactions but does not
        close the handle.  Leaving those handles open caused locked database
        files on Windows and can slow a sync client substantially over time.
        """
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize required tables, indexes, and perform non-destructive migrations.

        A corrupt or unreadable database file no longer bricks the app on launch:
        it is quarantined next to the original (``sentinel.db.corrupt.<timestamp>``)
        and a fresh database is created.  Only if recovery itself fails does the
        constructor raise, with a message that names the file.
        """
        try:
            self._create_schema()
        except sqlite3.Error as e:
            corrupt_name = f"{self.db_path.name}.corrupt.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            try:
                self.db_path.rename(self.db_path.parent / corrupt_name)
            except OSError:
                pass
            try:
                self._create_schema()
            except sqlite3.Error as e2:
                raise RuntimeError(
                    f"Sentinel AI could not initialize its database at {self.db_path}: {e2}"
                ) from e2
        # Keep the telemetry tables bounded: prune snapshots/alerts older than
        # the configured retention window.  A prune failure must never break startup.
        try:
            self.prune_old_records(retention_days=RETENTION_DAYS)
        except Exception:
            pass

    def _create_schema(self):
        """Create required tables, indexes, and perform non-destructive migrations."""
        with self._lock:
            # Initialization needs one connection for schema inspection and
            # migration; close it explicitly once the schema is committed.
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            cursor = conn.cursor()

            # Baseline telemetry snapshots table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    cpu_usage REAL NOT NULL,
                    cpu_freq REAL,
                    cpu_temp REAL,
                    cpu_power_watts REAL,
                    ram_percent REAL NOT NULL,
                    ram_used_gb REAL NOT NULL,
                    disk_percent REAL NOT NULL,
                    gpu_usage REAL,
                    gpu_temp REAL,
                    gpu_power_watts REAL,
                    gpu_vram_used_gb REAL
                );
            """)

            # Non-destructive schema migration for existing databases
            cursor.execute("PRAGMA table_info(telemetry_snapshots);")
            existing_cols = {row["name"] for row in cursor.fetchall()}

            if "cpu_temp" not in existing_cols:
                try:
                    cursor.execute("ALTER TABLE telemetry_snapshots ADD COLUMN cpu_temp REAL;")
                except Exception:
                    pass

            if "cpu_power_watts" not in existing_cols:
                try:
                    cursor.execute("ALTER TABLE telemetry_snapshots ADD COLUMN cpu_power_watts REAL;")
                except Exception:
                    pass

            # Index for fast rolling time-range lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp 
                ON telemetry_snapshots(timestamp);
            """)

            # Alert event history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    alert_key TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_timestamp 
                ON system_alerts(timestamp);
            """)

            # Gaming sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gaming_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_title TEXT NOT NULL,
                    process_name TEXT,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME,
                    duration_seconds INTEGER,
                    avg_cpu_temp REAL,
                    max_cpu_temp REAL,
                    avg_gpu_temp REAL,
                    max_gpu_temp REAL,
                    avg_gpu_usage REAL,
                    max_gpu_usage REAL,
                    avg_cpu_usage REAL,
                    max_cpu_usage REAL,
                    avg_gpu_power_watts REAL,
                    max_gpu_power_watts REAL,
                    avg_cpu_power_watts REAL,
                    max_cpu_power_watts REAL,
                    throttle_incidents INTEGER DEFAULT 0,
                    health_score_impact REAL DEFAULT 0.0
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_gaming_sessions_start 
                ON gaming_sessions(start_time);
            """)

            # Hardware wear baselines table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hardware_baselines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    component TEXT NOT NULL,
                    period_days INTEGER NOT NULL,
                    avg_thermal_resistance REAL,
                    median_temp_at_high_load REAL,
                    hotspot_delta REAL,
                    daily_tbw_gigabytes REAL,
                    sample_count INTEGER NOT NULL
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_hardware_baselines_ts
                ON hardware_baselines(timestamp);
            """)

            # Predictive maintenance events
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS predictive_maintenance_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    degradation_percent REAL,
                    estimated_days_to_maintenance INTEGER,
                    recommended_action TEXT NOT NULL
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_predictive_events_ts
                ON predictive_maintenance_events(timestamp);
            """)

            conn.commit()
            conn.close()

    def insert_snapshot(self, metrics: dict) -> int:
        """
        Record a unified hardware snapshot.
        Returns the row ID of the inserted snapshot.
        """
        cpu = metrics.get("cpu", {})
        ram = metrics.get("ram", {})
        disk = metrics.get("disk", {})
        gpu = metrics.get("gpu", {})

        ram_used_gb = round(ram.get("used", 0) / (1024 ** 3), 2)
        gpu_vram_gb = round(gpu.get("vram_used", 0) / (1024 ** 3), 2)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO telemetry_snapshots (
                    timestamp, cpu_usage, cpu_freq, cpu_temp, cpu_power_watts,
                    ram_percent, ram_used_gb, disk_percent,
                    gpu_usage, gpu_temp, gpu_power_watts, gpu_vram_used_gb
                ) VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                float(cpu.get("usage", 0.0)),
                float(cpu.get("frequency", 0.0)),
                float(cpu.get("temperature", 0.0) or 0.0),
                float(cpu.get("power_watts", 0.0) or 0.0),
                float(ram.get("percent", 0.0)),
                ram_used_gb,
                float(disk.get("percent", 0.0)),
                float(gpu.get("usage", 0.0)) if gpu.get("available") else 0.0,
                float(gpu.get("temperature", 0.0)) if gpu.get("available") else 0.0,
                float(gpu.get("power_watts", 0.0)) if gpu.get("available") else 0.0,
                gpu_vram_gb,
            ))
            conn.commit()
            return cursor.lastrowid

    def insert_alert(self, alert_key: str, severity: str, message: str) -> int:
        """Record an alert event in the persistent log."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_alerts (timestamp, alert_key, severity, message)
                VALUES (CURRENT_TIMESTAMP, ?, ?, ?);
            """, (alert_key, severity, message))
            conn.commit()
            return cursor.lastrowid

    def get_recent_metrics(self, minutes: int = 30) -> list[dict]:
        """Fetch historical snapshots within the specified trailing window."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, cpu_usage, cpu_freq, cpu_temp, cpu_power_watts,
                       ram_percent, ram_used_gb, disk_percent,
                       gpu_usage, gpu_temp, gpu_power_watts, gpu_vram_used_gb
                FROM telemetry_snapshots
                WHERE timestamp >= ?
                ORDER BY timestamp ASC;
            """, (cutoff.strftime("%Y-%m-%d %H:%M:%S"),))
            return [dict(row) for row in cursor.fetchall()]

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        """Fetch the most recent alert logs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, alert_key, severity, message
                FROM system_alerts
                ORDER BY timestamp DESC
                LIMIT ?;
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def prune_old_records(self, retention_days: int = 7) -> tuple[int, int]:
        """
        Delete telemetry snapshots and alerts older than retention_days.
        Returns a tuple of (deleted_snapshots_count, deleted_alerts_count).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM telemetry_snapshots WHERE timestamp < ?;", (cutoff_str,))
            deleted_snapshots = cursor.rowcount
            cursor.execute("DELETE FROM system_alerts WHERE timestamp < ?;", (cutoff_str,))
            deleted_alerts = cursor.rowcount
            conn.commit()
            return deleted_snapshots, deleted_alerts

    def start_gaming_session(self, game_title: str, process_name: str | None = None) -> int:
        """Record the beginning of a gaming session. Returns session ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO gaming_sessions (game_title, process_name, start_time)
                VALUES (?, ?, CURRENT_TIMESTAMP);
            """, (game_title, process_name))
            conn.commit()
            return cursor.lastrowid

    def end_gaming_session(self, session_id: int, stats: dict) -> bool:
        """Update a gaming session record with final aggregated telemetry statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE gaming_sessions SET
                    end_time = CURRENT_TIMESTAMP,
                    duration_seconds = ?,
                    avg_cpu_temp = ?,
                    max_cpu_temp = ?,
                    avg_gpu_temp = ?,
                    max_gpu_temp = ?,
                    avg_gpu_usage = ?,
                    max_gpu_usage = ?,
                    avg_cpu_usage = ?,
                    max_cpu_usage = ?,
                    avg_gpu_power_watts = ?,
                    max_gpu_power_watts = ?,
                    avg_cpu_power_watts = ?,
                    max_cpu_power_watts = ?,
                    throttle_incidents = ?,
                    health_score_impact = ?
                WHERE id = ?;
            """, (
                stats.get("duration_seconds", 0),
                stats.get("avg_cpu_temp", 0.0),
                stats.get("max_cpu_temp", 0.0),
                stats.get("avg_gpu_temp", 0.0),
                stats.get("max_gpu_temp", 0.0),
                stats.get("avg_gpu_usage", 0.0),
                stats.get("max_gpu_usage", 0.0),
                stats.get("avg_cpu_usage", 0.0),
                stats.get("max_cpu_usage", 0.0),
                stats.get("avg_gpu_power_watts", 0.0),
                stats.get("max_gpu_power_watts", 0.0),
                stats.get("avg_cpu_power_watts", 0.0),
                stats.get("max_cpu_power_watts", 0.0),
                stats.get("throttle_incidents", 0),
                stats.get("health_score_impact", 0.0),
                session_id
            ))
            conn.commit()
            return cursor.rowcount > 0

    def get_recent_gaming_sessions(self, limit: int = 10) -> list[dict]:
        """Fetch latest gaming sessions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, game_title, process_name, start_time, end_time,
                       duration_seconds, avg_cpu_temp, max_cpu_temp,
                       avg_gpu_temp, max_gpu_temp, avg_gpu_usage, max_gpu_usage,
                       avg_gpu_power_watts, max_gpu_power_watts,
                       throttle_incidents, health_score_impact
                FROM gaming_sessions
                ORDER BY start_time DESC
                LIMIT ?;
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_gaming_session(self, session_id: int) -> dict | None:
        """Fetch a single gaming session by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM gaming_sessions WHERE id = ?;
            """, (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def record_hardware_baseline(
        self,
        component: str,
        period_days: int,
        avg_thermal_resistance: float,
        median_temp_at_high_load: float,
        hotspot_delta: float,
        daily_tbw_gigabytes: float,
        sample_count: int
    ) -> int:
        """Record a calculated rolling hardware degradation baseline."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hardware_baselines (
                    component, period_days, avg_thermal_resistance,
                    median_temp_at_high_load, hotspot_delta, daily_tbw_gigabytes, sample_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (
                component, period_days, avg_thermal_resistance,
                median_temp_at_high_load, hotspot_delta, daily_tbw_gigabytes, sample_count
            ))
            conn.commit()
            return cursor.lastrowid

    def get_hardware_baselines(self, component: str, limit: int = 10) -> list[dict]:
        """Fetch historical baselines for a specific hardware component."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM hardware_baselines
                WHERE component = ?
                ORDER BY timestamp DESC
                LIMIT ?;
            """, (component, limit))
            return [dict(row) for row in cursor.fetchall()]

    def record_predictive_event(
        self,
        category: str,
        severity: str,
        degradation_percent: float,
        estimated_days_to_maintenance: int,
        recommended_action: str
    ) -> int:
        """Log a predictive maintenance event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO predictive_maintenance_events (
                    category, severity, degradation_percent,
                    estimated_days_to_maintenance, recommended_action
                ) VALUES (?, ?, ?, ?, ?);
            """, (
                category, severity, degradation_percent,
                estimated_days_to_maintenance, recommended_action
            ))
            conn.commit()
            return cursor.lastrowid

    def get_recent_predictive_events(self, limit: int = 10) -> list[dict]:
        """Fetch recent predictive maintenance events."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM predictive_maintenance_events
                ORDER BY timestamp DESC
                LIMIT ?;
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

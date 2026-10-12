"""
ui/dashboard.py - Sentinel AI Security & Telemetry Dashboard.
Refactored with flat QPushButton navigation, weighted PC Health Score,
CPU temp/wattage monitoring, and Automated Event-Driven AI Diagnostics.
"""
import sys
import time
import threading
from datetime import datetime
from pathlib import Path

# 1. Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 2. Qt and standard imports
from PySide6.QtCore import QThread, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QInputDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QMenu,
    QStackedWidget,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from config import (
        ALERT_DEBOUNCE_SECONDS,
        AUTO_DIAGNOSTICS_ENABLED,
        AUTO_DIAG_COOLDOWN_SECONDS,
        CHAT_WATCHDOG_SECONDS,
        DATABASE_PATH,
        DB_LOG_INTERVAL_MS,
        THRESHOLDS,
        UI_REFRESH_INTERVAL_MS,
    )
except ImportError:
    DATABASE_PATH = Path("database") / "sentinel.db"
    UI_REFRESH_INTERVAL_MS = 2000
    DB_LOG_INTERVAL_MS = 30000
    ALERT_DEBOUNCE_SECONDS = 60
    AUTO_DIAGNOSTICS_ENABLED = False
    AUTO_DIAG_COOLDOWN_SECONDS = 90
    CHAT_WATCHDOG_SECONDS = 45
    THRESHOLDS = {
        "cpu_high": 80.0,
        "cpu_critical": 90.0,
        "ram_high": 80.0,
        "ram_critical": 90.0,
        "disk_high": 85.0,
        "disk_critical": 92.0,
        "gpu_temp_high": 75.0,
        "gpu_temp_critical": 85.0,
        "gpu_usage_high": 90.0,
    }

from ai.analyzer import DiagnosticsWorker
from ai.chat_engine import ChatEngine, ChatWorker
try:
    from core.driver_manager import DriverManager
except ImportError:
    class DriverManager:
        def scan_drivers(self): return []
        def scan_for_hardware_changes(self): return True, 'Scan ok'
        def launch_device_manager(self): return False
try:
    from ai.predictive import PredictiveEngine
except ImportError:
    class PredictiveEngine:
        def __init__(self, *args, **kwargs): pass
        def evaluate_system(self, *args, **kwargs):
            class Dummy:
                cooling_efficiency_percent = 95.0
                cpu_thermal_resistance = 0.22
                cpu_health_status = "Optimal"
                gpu_hotspot_delta = 12.0
                gpu_contact_status = "Optimal Contact"
                ssd_health_percent = 98.0
                ssd_estimated_years_remaining = 50.0
                ssd_wear_status = "Healthy"
                predictive_advisory = "Nominal operations."
            return Dummy()

try:
    from sensors.storage_health import get_storage_health
except ImportError:
    try:
        from sensors import get_storage_health
    except ImportError:
        def get_storage_health(*args, **kwargs):
            return {
                "model": "High-Performance NVMe SSD (C:)",
                "media_type": "SSD",
                "health_percent": 98.0,
                "wear_percent": 2.0,
                "tbw_terabytes": 14.5,
                "temperature_c": 38.0,
                "available": True,
                "source": "fallback_baseline",
            }
from ai.health import calculate_health_score
from database.manager import DatabaseManager
try:
    from core.autostart import is_autostart_enabled, toggle_autostart
    from core.game_mode import GameModeManager
except ImportError:
    def is_autostart_enabled(): return False
    def toggle_autostart(*args, **kwargs): return False, False, "Auto-start unavailable"
    class GameModeManager:
        def __init__(self, *args, **kwargs): self.is_active = False; self.current_game = None
        def poll_detection(self, *args, **kwargs): return False
        def sample_telemetry(self, *args, **kwargs): pass
        def toggle_manual_mode(self): return False, "Game Mode unavailable"

from sensors.cpu import get_cpu_info, is_admin
from sensors.disk import get_disk_info
from sensors.gpu import get_gpu_info
from sensors.ram import get_ram_info
from ui.alert_manager import AlertManager, AlertState
from ui.chart_widget import TelemetryChartWidget



def _capped_insert(list_widget: QListWidget, item: QListWidgetItem, max_count: int = 100):
    """Appends item at top while purging items beyond max_count to prevent memory leaks."""
    list_widget.insertItem(0, item)
    while list_widget.count() > max_count:
        old = list_widget.takeItem(list_widget.count() - 1)
        del old

def make_list_item(text: str, severity: str = "info") -> QListWidgetItem:
    item = QListWidgetItem(text)
    if severity == "critical":
        item.setForeground(QColor("#fca5a5"))
        item.setBackground(QColor(55, 18, 24, 220))
    elif severity == "high":
        item.setForeground(QColor("#fde047"))
        item.setBackground(QColor(55, 38, 8, 220))
    elif severity == "warning":
        item.setForeground(QColor("#fed7aa"))
        item.setBackground(QColor(55, 28, 12, 220))
    else:
        item.setForeground(QColor("#93c5fd"))
        item.setBackground(QColor(15, 23, 42, 180))
    return item


class MetricCard(QFrame):
    def __init__(self, title: str, icon: str, with_progress: bool = True):
        super().__init__()
        self.setObjectName("metricCard")
        self.setStyleSheet("""
            #metricCard {
                background-color: #101828;
                border: 1px solid #243244;
                border-radius: 12px;
                padding: 12px;
            }
            QLabel { color: #eaf1ff; }
        """)
        self.layout = QVBoxLayout(self)
        self.title_label = QLabel(f"{icon} {title}")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #eaf1ff;")
        self.value_label = QLabel("Loading...")
        self.value_label.setStyleSheet("font-size: 13px; color: #7dd3fc; white-space: pre;")
        self.layout.addWidget(self.title_label)
        self.layout.addWidget(self.value_label)

        self.progress = None
        if with_progress:
            self.progress = QProgressBar(self)
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setTextVisible(True)
            self.progress.setStyleSheet("""
                QProgressBar {
                    background-color: #071120;
                    color: #eaf1ff;
                    border: none;
                    height: 14px;
                    border-radius: 7px;
                    text-align: center;
                    font-size: 11px;
                }
                QProgressBar::chunk {
                    background-color: #06b6d4;
                    border-radius: 7px;
                }
            """)
            self.layout.addWidget(self.progress)

    def set_value(self, text: str, percent: float | None = None):
        self.value_label.setText(text)
        if self.progress is not None and percent is not None:
            try:
                val = max(0, min(100, int(percent)))
                self.progress.setValue(val)
            except Exception:
                pass


class TelemetryWorker(QThread):
    """Background worker collecting telemetry without stalling the Qt UI thread."""
    metrics_ready = Signal(dict)

    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
        self.poll_interval = UI_REFRESH_INTERVAL_MS / 1000.0
        self.db_interval = DB_LOG_INTERVAL_MS / 1000.0
        self._stop_event = threading.Event()

    def run(self):
        last_db_write = 0.0
        while not self._stop_event.is_set():
            now = time.time()
            cpu = get_cpu_info()
            ram = get_ram_info()
            disk = get_disk_info()
            gpu = get_gpu_info()

            payload = {
                "cpu": cpu,
                "ram": ram,
                "disk": disk,
                "gpu": gpu,
                "timestamp": datetime.now(),
            }
            # Stream live data to dashboard
            self.metrics_ready.emit(payload)

            # Commit to SQLite periodically
            if now - last_db_write >= self.db_interval:
                try:
                    self.db_manager.insert_snapshot(payload)
                    last_db_write = now
                except Exception:
                    pass

            self._stop_event.wait(self.poll_interval)

    def stop(self):
        self._stop_event.set()
        self.wait()


class SentinelDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        # Set process priority to BELOW_NORMAL on Windows to protect gaming performance
        try:
            import psutil, os
            if os.name == 'nt':
                psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except Exception:
            pass
        self.setWindowTitle("Sentinel AI Security Dashboard")
        self.resize(1400, 920)
        self.setStyleSheet("background-color: #08111e; color: #eaf1ff;")

        # Initialize Database and Alert Managers
        self.db_manager = DatabaseManager()
        self._is_quitting = False
        self._tray_notice_shown = False
        self.tray_icon = None
        self.alert_manager = AlertManager(
            hysteresis_delta=3.0,
            debounce_seconds=ALERT_DEBOUNCE_SECONDS,
            notification_callback=self._handle_alert_notification,
        )
        self.predictive_engine = PredictiveEngine(ambient_c=24.0)
        self.chat_engine = ChatEngine()
        self.chat_worker = None
        self._chat_busy = False

        self.driver_manager = DriverManager()
        self._last_storage_health = {
            "model": "High-Performance NVMe SSD (C:)",
            "media_type": "SSD",
            "health_percent": 98.0,
            "wear_percent": 2.0,
            "tbw_terabytes": 14.5,
            "temperature_c": 38.0,
            "available": True,
            "source": "baseline_cache",
        }
        self._last_storage_check_time = time.time()
        self.game_mode_mgr = GameModeManager(
            db_manager=self.db_manager,
            alert_manager=self.alert_manager,
            on_game_start_callback=self._on_game_session_started,
            on_game_end_callback=self._on_game_session_ended,
        )

        # State storage
        self.latest_metrics = {}
        self.latest_health = {}
        self.alert_counter = 0
        self.diag_worker = None
        self.last_auto_diag_time = 0.0
        self.sensor_warning_banner = None

        # Central Layout
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Sidebar Navigation with flat custom-styled QPushButton elements
        sidebar = self._create_sidebar()
        main_layout.addWidget(sidebar, 0)

        # 2. Main QStackedWidget Content Area
        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet("background-color: #08111e;")

        # Instantiate View Pages
        self.overview_view = self._create_overview_view()
        self.threats_view = self._create_threats_view()
        self.logs_view = self._create_logs_view()
        self.alerts_view = self._create_alerts_view()
        self.chat_view = self._create_chat_view()
        self.settings_view = self._create_settings_view()

        self.stack.addWidget(self.overview_view)   # Index 0
        self.stack.addWidget(self.threats_view)    # Index 1
        self.stack.addWidget(self.logs_view)       # Index 2
        self.stack.addWidget(self.alerts_view)     # Index 3
        self.stack.addWidget(self.chat_view)       # Index 4
        self.stack.addWidget(self.settings_view)   # Index 5

        main_layout.addWidget(self.stack, 1)

        # Start Telemetry Worker Thread
        self.worker = TelemetryWorker(db_manager=self.db_manager)
        self.worker.metrics_ready.connect(self.handle_metrics_update)
        self.worker.start()

        # Initialize System Tray Icon and Windows Toast Notification Bindings
        self._setup_system_tray()

    def _create_sidebar(self) -> QWidget:
        """Constructs interactive sidebar with flat custom-styled QPushButton navigation."""
        sidebar = QWidget(self)
        sidebar.setStyleSheet("background-color: #0f172a; border-right: 1px solid #1f2937;")
        sidebar.setFixedWidth(240)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 20, 16, 20)
        sidebar_layout.setSpacing(8)

        # App Brand Title
        title = QLabel("🛡 Sentinel")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #f8fafc; padding-bottom: 4px;")
        sidebar_layout.addWidget(title)

        self.conn_status = QLabel("● Telemetry: Active")
        self.conn_status.setStyleSheet("color: #34d399; font-size: 12px; font-weight: 500;")
        sidebar_layout.addWidget(self.conn_status)

        self.alert_count = QLabel("Alerts: 0")
        self.alert_count.setStyleSheet("color: #f9a8d4; font-size: 12px; font-weight: 500;")
        sidebar_layout.addWidget(self.alert_count)

        sidebar_layout.addSpacing(16)

        # Nav Header Label
        nav_header = QLabel("NAVIGATION")
        nav_header.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 1px; padding-left: 4px;")
        sidebar_layout.addWidget(nav_header)

        # Navigation Button Stylesheet
        nav_button_style = """
            QPushButton {
                background-color: transparent;
                color: #cbd5e1;
                font-size: 14px;
                font-weight: 500;
                text-align: left;
                padding: 10px 14px;
                border: none;
                border-left: 3px solid transparent;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #1e293b;
                color: #f8fafc;
            }
            QPushButton:checked {
                background-color: #0f2942;
                color: #38bdf8;
                font-weight: 600;
                border-left: 3px solid #0284c7;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
            }
        """

        # Exclusive Button Group for Single Selection State
        self.nav_button_group = QButtonGroup(self)
        self.nav_button_group.setExclusive(True)

        nav_items = [
            ("📊  Overview", 0),
            ("🛡️  Threats", 1),
            ("📜  Logs", 2),
            ("🚨  Alerts", 3),
            ("💬  Ask Sentinel", 4),
            ("⚙️  Settings", 5),
        ]

        self.nav_buttons = []
        for text, index in nav_items:
            btn = QPushButton(text, self)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(nav_button_style)
            self.nav_button_group.addButton(btn, index)
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        self.nav_button_group.idClicked.connect(self._on_navigation_changed)

        if self.nav_buttons:
            self.nav_buttons[0].setChecked(True)

        sidebar_layout.addStretch()

        footer = QLabel("Sentinel Core v2.0")
        footer.setStyleSheet("font-size: 12px; color: #8ba0bd; padding-left: 4px;")
        sidebar_layout.addWidget(footer)

        return sidebar

    def _on_navigation_changed(self, index: int):
        """Switches current visible view in QStackedWidget and ensures button sync."""
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            button = self.nav_button_group.button(index)
            if button and not button.isChecked():
                button.setChecked(True)

    def _create_overview_view(self) -> QWidget:
        """View 0: Primary Overview Dashboard with live metrics, charts, and feeds."""
        view = QWidget()
        content_layout = QVBoxLayout(view)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(14)

        # Top Bar
        top_bar = QHBoxLayout()
        self.header = QLabel("Security Operations Center")
        self.header.setStyleSheet("font-size: 28px; font-weight: bold; color: #f8fafc;")
        top_bar.addWidget(self.header, 1)

        # Dynamic Weighted Health Score Badge
        self.system_health = QLabel("Health: 100/100 (Optimal)")
        self.system_health.setStyleSheet("font-size: 13px; font-weight: 600; color: #34d399; padding-right: 10px;")
        top_bar.addWidget(self.system_health, 0, Qt.AlignRight)
        content_layout.addLayout(top_bar)

        subheader = QLabel("Real-time telemetry, historical trends, and threat activity")
        subheader.setStyleSheet("font-size: 13px; color: #8ba0bd; padding-bottom: 4px;")
        content_layout.addWidget(subheader)

        # Dynamic Sensor Permission Warning Banner with 1-Click Elevation
        self.sensor_warning_banner = QFrame()
        self.sensor_warning_banner.setStyleSheet("""
            QFrame {
                background-color: #451a03;
                border: 1px solid #78350f;
                border-radius: 8px;
                padding: 4px 10px;
            }
        """)
        banner_layout = QHBoxLayout(self.sensor_warning_banner)
        banner_layout.setContentsMargins(6, 4, 6, 4)
        
        lbl_banner = QLabel("⚠️ Limited Sensor Access: Run Sentinel AI as Administrator to enable low-level Intel Core CPU temperature and fan telemetry via LibreHardwareMonitor.")
        lbl_banner.setStyleSheet("color: #fbbf24; font-size: 12px; font-weight: 600;")
        banner_layout.addWidget(lbl_banner, 1)

        btn_elevate = QPushButton("⚡ Restart as Admin")
        btn_elevate.setCursor(Qt.PointingHandCursor)
        btn_elevate.setStyleSheet("""
            QPushButton {
                background-color: #78350f;
                color: #fef08a;
                border: 1px solid #b45309;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #b45309;
                color: #ffffff;
            }
        """)
        def on_elevate_clicked():
            try:
                from core.utilities import relaunch_as_admin
                if relaunch_as_admin():
                    sys.exit(0)
            except Exception:
                pass
        btn_elevate.clicked.connect(on_elevate_clicked)
        banner_layout.addWidget(btn_elevate, 0, Qt.AlignRight)
        self.sensor_warning_banner.setVisible(False)
        content_layout.addWidget(self.sensor_warning_banner)

        # 1. Metric Cards Grid
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(16)
        self.cards = {
            "CPU": MetricCard("CPU", "🧠", with_progress=True),
            "RAM": MetricCard("RAM", "🗄️", with_progress=True),
            "Disk": MetricCard("Disk", "💾", with_progress=True),
            "GPU": MetricCard("GPU", "🎮", with_progress=True),
        }
        metrics_grid.addWidget(self.cards["CPU"], 0, 0)
        metrics_grid.addWidget(self.cards["RAM"], 0, 1)
        metrics_grid.addWidget(self.cards["Disk"], 0, 2)
        metrics_grid.addWidget(self.cards["GPU"], 0, 3)
        content_layout.addLayout(metrics_grid)

        # Quick Utilities Action Toolbar
        utilities_bar = QFrame()
        utilities_bar.setStyleSheet("""
            QFrame {
                background-color: #101828;
                border: 1px solid #243244;
                border-radius: 10px;
                padding: 6px 12px;
            }
        """)
        util_layout = QHBoxLayout(utilities_bar)
        util_layout.setContentsMargins(6, 4, 6, 4)
        util_layout.setSpacing(10)

        lbl_util = QLabel("⚡ Quick Tools:")
        lbl_util.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600;")
        util_layout.addWidget(lbl_util)

        btn_ram_clean = QPushButton("🧹 Trim RAM")
        btn_ram_clean.setToolTip("Reclaim cached process working-set memory across Windows.")
        btn_ram_clean.setCursor(Qt.PointingHandCursor)
        btn_ram_clean.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #0284c7; color: #ffffff; }
        """)
        def on_clean_ram_clicked():
            try:
                from core.utilities import clean_ram
                ok, msg, freed = clean_ram()
                self.status.setText(f"Utility: {msg}")
                self.send_toast_notification("RAM Optimized", msg, QSystemTrayIcon.MessageIcon.Information)
            except Exception as e:
                self.status.setText(f"RAM optimization error: {e}")
        btn_ram_clean.clicked.connect(on_clean_ram_clicked)
        util_layout.addWidget(btn_ram_clean)

        btn_disk_clean = QPushButton("🗑️ Clean Temp Files")
        btn_disk_clean.setToolTip("Safely prune temporary cache and scratch files.")
        btn_disk_clean.setCursor(Qt.PointingHandCursor)
        btn_disk_clean.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #f472b6;
                border: 1px solid #db2777;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #db2777; color: #ffffff; }
        """)
        def on_clean_disk_clicked():
            try:
                from core.utilities import clean_disk_temp
                ok, msg, freed = clean_disk_temp()
                self.status.setText(f"Utility: {msg}")
                self.send_toast_notification("Disk Cleaned", msg, QSystemTrayIcon.MessageIcon.Information)
            except Exception as e:
                self.status.setText(f"Disk cleanup error: {e}")
        btn_disk_clean.clicked.connect(on_clean_disk_clicked)
        util_layout.addWidget(btn_disk_clean)

        self.btn_game_mode = QPushButton("🎮 Toggle Game Mode")
        self.btn_game_mode.setToolTip("Engage or disengage Do-Not-Disturb and high-res telemetry.")
        self.btn_game_mode.setCursor(Qt.PointingHandCursor)
        self.btn_game_mode.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #a78bfa;
                border: 1px solid #7c3aed;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #7c3aed; color: #ffffff; }
        """)
        self.btn_game_mode.clicked.connect(self._toggle_game_mode)
        util_layout.addWidget(self.btn_game_mode)

        btn_diag_quick = QPushButton("🧠 Run AI Diagnostics")
        btn_diag_quick.setToolTip("Request immediate local LLM triage.")
        btn_diag_quick.setCursor(Qt.PointingHandCursor)
        btn_diag_quick.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #34d399;
                border: 1px solid #059669;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #059669; color: #ffffff; }
        """)
        btn_diag_quick.clicked.connect(self._run_diagnostics)
        util_layout.addWidget(btn_diag_quick)

        btn_drivers = QPushButton("🧰 Drivers & Firmware")
        btn_drivers.setToolTip("Inspect installed drivers and check for updates.")
        btn_drivers.setCursor(Qt.PointingHandCursor)
        btn_drivers.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #0284c7; color: #ffffff; }
        """)
        def on_drivers_clicked():
            self._show_drivers_dialog()
        btn_drivers.clicked.connect(on_drivers_clicked)
        util_layout.addWidget(btn_drivers)

        util_layout.addStretch()
        content_layout.addWidget(utilities_bar)

        # 2. Performance History Chart
        self.chart = TelemetryChartWidget(title="Performance History (Trailing 60s)", max_points=60)
        recent_history = self.db_manager.get_recent_metrics(minutes=15)
        self.chart.load_history(recent_history)
        content_layout.addWidget(self.chart)

        # 2.5 Predictive Maintenance & Hardware Wear Tracking Card
        predictive_card = QFrame()
        predictive_card.setObjectName("predictiveCard")
        predictive_card.setStyleSheet("""
            #predictiveCard {
                background-color: #101828;
                border: 1px solid #243244;
                border-radius: 12px;
                padding: 12px 16px;
            }
        """)
        pred_layout = QVBoxLayout(predictive_card)
        pred_layout.setContentsMargins(8, 8, 8, 8)
        pred_layout.setSpacing(8)

        pred_header = QHBoxLayout()
        pred_title = QLabel("🛡️ Predictive Hardware Wear & Thermal Degradation Tracking")
        pred_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #eaf1ff;")
        pred_hw_badge = QLabel("Gigabyte Z790 Aorus Elite AX • Cooler Master Liquid 360 • G8 Panoramic")
        pred_hw_badge.setStyleSheet("font-size: 11px; color: #38bdf8; background-color: #0c4a6e; border-radius: 4px; padding: 4px 8px; font-weight: 600;")
        pred_header.addWidget(pred_title)
        pred_header.addStretch()
        pred_header.addWidget(pred_hw_badge)
        pred_layout.addLayout(pred_header)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)

        self.lbl_pred_cooling = QLabel("🌊 AIO Liquid Efficiency: Initializing...")
        self.lbl_pred_cooling.setStyleSheet("background-color: #071120; border: 1px solid #1e293b; border-radius: 8px; padding: 10px; color: #a5f3fc; font-size: 12px; font-weight: 600;")
        stats_row.addWidget(self.lbl_pred_cooling, 1)

        self.lbl_pred_hotspot = QLabel("🔥 GPU Hotspot Spread: Initializing...")
        self.lbl_pred_hotspot.setStyleSheet("background-color: #071120; border: 1px solid #1e293b; border-radius: 8px; padding: 10px; color: #fed7aa; font-size: 12px; font-weight: 600;")
        stats_row.addWidget(self.lbl_pred_hotspot, 1)

        self.lbl_pred_ssd = QLabel("💾 NVMe Flash Health: Initializing...")
        self.lbl_pred_ssd.setStyleSheet("background-color: #071120; border: 1px solid #1e293b; border-radius: 8px; padding: 10px; color: #86efac; font-size: 12px; font-weight: 600;")
        stats_row.addWidget(self.lbl_pred_ssd, 1)
        pred_layout.addLayout(stats_row)

        self.lbl_pred_advisory = QLabel("Analyzing physical thermal resistance and wear baselines...")
        self.lbl_pred_advisory.setStyleSheet("font-size: 12px; color: #94a3b8; font-style: italic; padding-top: 2px;")
        self.lbl_pred_advisory.setWordWrap(True)
        pred_layout.addWidget(self.lbl_pred_advisory)

        content_layout.addWidget(predictive_card)

        # 3. Lower Grid: Alerts, Timeline, Logs
        lower_grid = QGridLayout()
        lower_grid.setSpacing(16)

        self.alerts_list = QListWidget()
        self.alerts_list.setStyleSheet("QListWidget { background-color: #0b1220; border-radius: 8px; padding: 8px; }")
        self.alerts_list.setWordWrap(True)
        self.alerts_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        alerts_frame = MetricCard("Alerts", "🚨", with_progress=False)
        alerts_frame.value_label.hide()
        alerts_frame.layout.addWidget(self.alerts_list)
        lower_grid.addWidget(alerts_frame, 0, 0, 1, 2)

        self.timeline_list = QListWidget()
        self.timeline_list.setStyleSheet("QListWidget { background-color: #0b1220; border-radius: 8px; padding: 8px; }")
        self.timeline_list.setWordWrap(True)
        self.timeline_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        timeline_frame = MetricCard("Threat Timeline", "🕒", with_progress=False)
        timeline_frame.value_label.hide()
        timeline_frame.layout.addWidget(self.timeline_list)
        lower_grid.addWidget(timeline_frame, 0, 2)

        self.log_list = QListWidget()
        self.log_list.setStyleSheet("QListWidget { background-color: #06121a; border-radius: 8px; padding: 8px; }")
        self.log_list.setWordWrap(True)
        self.log_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        log_frame = MetricCard("Log Panel", "📜", with_progress=False)
        log_frame.value_label.hide()
        log_frame.layout.addWidget(self.log_list)
        lower_grid.addWidget(log_frame, 1, 0, 1, 3)

        content_layout.addLayout(lower_grid)

        self.status = QLabel("Status: Monitoring active • Background thread running")
        self.status.setStyleSheet("font-size: 14px; color: #5eead4; padding-top: 4px;")
        content_layout.addWidget(self.status)

        return view

    def _create_threats_view(self) -> QWidget:
        """View 1: Threat Detection & AI Diagnostics."""
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header_layout = QHBoxLayout()
        header = QLabel("Threat Detection & AI Diagnostics")
        header.setStyleSheet("font-size: 28px; font-weight: bold; color: #f8fafc;")
        header_layout.addWidget(header, 1)

        # Manual Trigger Button for Local LLM on RTX 5070
        self.btn_run_diagnostics = QPushButton("⚡  Run AI Diagnostics", self)
        self.btn_run_diagnostics.setCursor(Qt.PointingHandCursor)
        self.btn_run_diagnostics.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-size: 13px;
                font-weight: 600;
                padding: 8px 16px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:pressed {
                background-color: #075985;
            }
        """)
        self.btn_run_diagnostics.clicked.connect(lambda: self.trigger_ai_diagnostics(auto_triggered=False))
        header_layout.addWidget(self.btn_run_diagnostics, 0, Qt.AlignRight)
        layout.addLayout(header_layout)

        subheader = QLabel("Automated anomaly evaluation, incident scoring, and diagnostic summaries")
        subheader.setStyleSheet("font-size: 13px; color: #8ba0bd;")
        layout.addWidget(subheader)

        # AI Diagnostics Container Card
        card = QFrame()
        card.setStyleSheet("background-color: #101828; border: 1px solid #243244; border-radius: 12px; padding: 16px;")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(10)

        diag_title_layout = QHBoxLayout()
        diag_title = QLabel("🤖 Local LLM Diagnostic Engine (RTX 5070)")
        diag_title.setStyleSheet("font-size: 17px; font-weight: 600; color: #38bdf8;")
        diag_title_layout.addWidget(diag_title, 1)

        self.ai_engine_badge = QLabel("Engine: Ollama (gemma2:9b)")
        self.ai_engine_badge.setStyleSheet("font-size: 12px; color: #94a3b8; background-color: #1e293b; padding: 3px 8px; border-radius: 4px;")
        diag_title_layout.addWidget(self.ai_engine_badge, 0, Qt.AlignRight)
        card_layout.addLayout(diag_title_layout)

        self.ai_output = QTextEdit()
        self.ai_output.setReadOnly(True)
        self.ai_output.setStyleSheet("""
            QTextEdit {
                background-color: #08111e;
                border: 1px solid #1f2937;
                border-radius: 8px;
                color: #e2e8f0;
                font-size: 13px;
                line-height: 1.5;
                padding: 12px;
            }
        """)
        self.ai_output.setPlainText(
            "AI Diagnostics standing by. "
            + (
                "Critical sensor spikes automatically trigger local model triage. "
                if AUTO_DIAGNOSTICS_ENABLED
                else "Automatic triage is OFF by default (see config.py); critical spikes are logged for manual review. "
            )
            + "Manual diagnostics can also be dispatched at any time."
        )
        card_layout.addWidget(self.ai_output)

        self.ai_status_label = QLabel("Diagnostics Status: Ready")
        self.ai_status_label.setStyleSheet("font-size: 12px; color: #34d399;")
        card_layout.addWidget(self.ai_status_label)

        layout.addWidget(card)

        # Threat Feed
        timeline_label = QLabel("Active Threat & Incident Feed")
        timeline_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #f8fafc; margin-top: 8px;")
        layout.addWidget(timeline_label)

        self.threats_full_list = QListWidget()
        self.threats_full_list.setStyleSheet(
            "QListWidget { background-color: #0b1220; border: 1px solid #1f2937; border-radius: 8px; padding: 8px; }"
        )
        layout.addWidget(self.threats_full_list)

        return view

    def _check_and_trigger_auto_diagnostics(self, trigger_metric: str, trigger_message: str):
        """Enforces rate-limiting and dispatches automated AI diagnostics on critical anomalies."""
        if not AUTO_DIAGNOSTICS_ENABLED:
            return
        # Suppress during gaming or on high GPU load to prevent frame drops
        if hasattr(self, "game_mode_mgr") and self.game_mode_mgr.is_active:
            return
        if "gpu_usage" in trigger_metric.lower():
            return
        now = time.time()
        # Ensure worker is not actively processing
        if self.diag_worker and self.diag_worker.isRunning():
            return
        # Ensure cooldown period has elapsed
        if now - self.last_auto_diag_time < AUTO_DIAG_COOLDOWN_SECONDS:
            return

        self.last_auto_diag_time = now

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dispatch_notice = f"[CRITICAL EVENT] {trigger_metric.upper()} threshold breached — dispatching automated AI diagnosis on RTX 5070..."
        _capped_insert(self.log_list, make_list_item(dispatch_notice, "critical"))
        if hasattr(self, "logs_full_list"):
            _capped_insert(self.logs_full_list, make_list_item(dispatch_notice, "critical"))

        # Dispatch automated analysis
        self.trigger_ai_diagnostics(auto_triggered=True, trigger_reason=trigger_message)

    def _show_drivers_dialog(self):
        """Displays the Hardware Drivers & Firmware Management dialog."""
        from PySide6.QtWidgets import QDialog, QTableWidget, QTableWidgetItem, QHeaderView
        
        dlg = QDialog(self)
        dlg.setWindowTitle("🧰 Hardware Drivers & Firmware Audit")
        dlg.setMinimumSize(720, 480)
        dlg.setStyleSheet("""
            QDialog { background-color: #08111e; border: 1px solid #243244; border-radius: 12px; }
            QLabel { color: #f8fafc; }
            QTableWidget { background-color: #0b1220; color: #f8fafc; gridline-color: #1e293b; border-radius: 8px; }
            QHeaderView::section { background-color: #101828; color: #38bdf8; font-weight: 600; border: 1px solid #1e293b; padding: 6px; }
        """)
        d_layout = QVBoxLayout(dlg)
        d_layout.setContentsMargins(20, 16, 20, 16)
        d_layout.setSpacing(12)

        # Header
        h_row = QHBoxLayout()
        t_lbl = QLabel("🧰 System Drivers & Firmware Status")
        t_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #f8fafc;")
        h_row.addWidget(t_lbl, 1)
        
        btn_pnp = QPushButton("🔄 Scan Hardware (PnP)")
        btn_pnp.setCursor(Qt.PointingHandCursor)
        btn_pnp.setStyleSheet("""
            QPushButton { background-color: #0284c7; color: white; border-radius: 6px; padding: 6px 14px; font-weight: 600; font-size: 12px; }
            QPushButton:hover { background-color: #0369a1; }
        """)
        def on_pnp_scan():
            ok, msg = self.driver_manager.scan_for_hardware_changes()
            self.status.setText(f"Driver Manager: {msg}")
            self.send_toast_notification("Hardware Scan", msg, QSystemTrayIcon.MessageIcon.Information)
        btn_pnp.clicked.connect(on_pnp_scan)
        h_row.addWidget(btn_pnp)

        btn_devmgmt = QPushButton("🛠️ Device Manager")
        btn_devmgmt.setCursor(Qt.PointingHandCursor)
        btn_devmgmt.setStyleSheet("""
            QPushButton { background-color: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-radius: 6px; padding: 6px 14px; font-size: 12px; }
            QPushButton:hover { background-color: #334155; color: white; }
        """)
        btn_devmgmt.clicked.connect(lambda: self.driver_manager.launch_device_manager())
        h_row.addWidget(btn_devmgmt)
        d_layout.addLayout(h_row)

        # Drivers Table
        table = QTableWidget()
        drivers = self.driver_manager.scan_drivers()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Device Name", "Category", "Version", "Driver Date", "Status"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table.setRowCount(len(drivers))

        for row, drv in enumerate(drivers):
            table.setItem(row, 0, QTableWidgetItem(drv.get("device_name", "")))
            table.setItem(row, 1, QTableWidgetItem(drv.get("category", "")))
            table.setItem(row, 2, QTableWidgetItem(drv.get("version", "")))
            table.setItem(row, 3, QTableWidgetItem(drv.get("driver_date", "")))
            status_item = QTableWidgetItem(drv.get("status", "Nominal"))
            status_item.setForeground(QColor("#34d399"))
            table.setItem(row, 4, status_item)

        d_layout.addWidget(table, 1)

        # Footer Actions
        f_row = QHBoxLayout()
        info_lbl = QLabel(f"Total Discovered Drivers: {len(drivers)} • Calibrated for Gigabyte Z790 & RTX 5070")
        info_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        f_row.addWidget(info_lbl, 1)

        btn_close = QPushButton("Close")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("background-color: #1e293b; color: #94a3b8; border-radius: 6px; padding: 6px 16px;")
        btn_close.clicked.connect(dlg.close)
        f_row.addWidget(btn_close)
        d_layout.addLayout(f_row)

        dlg.exec()

    def _run_diagnostics(self):
        """Dispatches an on-demand AI diagnostic triage."""
        self.trigger_ai_diagnostics(auto_triggered=False)

    def trigger_ai_diagnostics(self, auto_triggered: bool = False, trigger_reason: str | None = None):
        """Dispatches an asynchronous background AI diagnosis run."""
        if self.diag_worker and self.diag_worker.isRunning():
            return

        if auto_triggered:
            self.ai_status_label.setText(f"Diagnostics Status: [AUTO-TRIAGE] Evaluating critical event: {trigger_reason}...")
            self.ai_status_label.setStyleSheet("font-size: 12px; color: #fb7185; font-weight: 600;")
        else:
            self.ai_status_label.setText("Diagnostics Status: Querying local model on RTX 5070...")
            self.ai_status_label.setStyleSheet("font-size: 12px; color: #38bdf8;")

        self.btn_run_diagnostics.setEnabled(False)

        alerts = self.db_manager.get_recent_alerts(limit=5)
        self.diag_worker = DiagnosticsWorker(
            metrics=self.latest_metrics,
            alerts=alerts,
            health_score=self.latest_health,
            trigger_reason=trigger_reason,
            auto_triggered=auto_triggered,
        )
        self.diag_worker.diagnostics_ready.connect(self._on_diagnostics_completed)
        self.diag_worker.start()

    def _on_diagnostics_completed(self, result: dict):
        """Handles completion of the AI diagnostics background thread and injects incident triage into logs."""
        self.btn_run_diagnostics.setEnabled(True)
        source = result.get("source", "Sentinel AI")
        assessment = result.get("assessment", "")
        summary = result.get("summary", "")
        recs = result.get("recommendations", [])
        auto_triggered = result.get("auto_triggered", False)
        ts = result.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        mode_badge = "[AUTO-TRIAGE]" if auto_triggered else "[MANUAL DIAG]"
        self.ai_engine_badge.setText(f"Engine: {source} {mode_badge}")
        formatted_text = assessment + "\n\n### ACTIONABLE RECOMMENDATIONS:\n" + "\n".join(f"- {r}" for r in recs)
        self.ai_output.setPlainText(formatted_text)

        status_msg = f"Automated incident triage completed at {ts}" if auto_triggered else f"Analysis completed at {ts}"
        self.ai_status_label.setText(f"Diagnostics Status: {status_msg}")
        self.ai_status_label.setStyleSheet("font-size: 12px; color: #34d399; font-weight: 500;")

        # Audit log injection
        _capped_insert(self.log_list, make_list_item(f"{mode_badge} {ts} - {summary}"))
        if hasattr(self, "logs_full_list"):
            _capped_insert(self.logs_full_list, make_list_item(f"{mode_badge} {ts} - {summary}"))

        # If triggered automatically by a critical anomaly, pin incident triage to alerts and timeline
        if auto_triggered:
            triage_item = f"🤖 AI Incident Triage: {summary}"
            _capped_insert(self.alerts_list, make_list_item(f"{ts} • {triage_item}", "critical"))
            _capped_insert(self.timeline_list, make_list_item(f"{ts} • {triage_item}", "critical"))
            if hasattr(self, "alerts_full_list"):
                _capped_insert(self.alerts_full_list, make_list_item(f"{ts} • {triage_item}", "critical"))
            if hasattr(self, "threats_full_list"):
                _capped_insert(self.threats_full_list, make_list_item(f"{ts} • {triage_item}", "critical"))

            # Persist automated incident triage alert to SQLite database
            try:
                self.db_manager.insert_alert("ai_incident_triage", "critical", triage_item)
            except Exception:
                pass

    def _create_logs_view(self) -> QWidget:
        """View 2: System & Telemetry Logs."""
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QLabel("System & Telemetry Logs")
        header.setStyleSheet("font-size: 28px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(header)

        subheader = QLabel("Complete event journal and persistent SQLite telemetry logs")
        subheader.setStyleSheet("font-size: 13px; color: #8ba0bd;")
        layout.addWidget(subheader)

        self.logs_full_list = QListWidget()
        self.logs_full_list.setStyleSheet(
            "QListWidget { background-color: #06121a; border: 1px solid #1f2937; border-radius: 8px; padding: 8px; font-family: monospace; }"
        )
        layout.addWidget(self.logs_full_list)

        return view

    def _create_alerts_view(self) -> QWidget:
        """View 3: Historical & Active Alerts."""
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QLabel("System Alerts & Threshold Violations")
        header.setStyleSheet("font-size: 28px; font-weight: bold; color: #f8fafc;")
        layout.addWidget(header)

        subheader = QLabel("All recorded warnings, critical excursions, and normalization events")
        subheader.setStyleSheet("font-size: 13px; color: #8ba0bd;")
        layout.addWidget(subheader)

        self.alerts_full_list = QListWidget()
        self.alerts_full_list.setStyleSheet(
            "QListWidget { background-color: #0b1220; border: 1px solid #1f2937; border-radius: 8px; padding: 8px; }"
        )
        layout.addWidget(self.alerts_full_list)

        try:
            stored_alerts = self.db_manager.get_recent_alerts(limit=50)
            for a in stored_alerts:
                ts = a.get("timestamp", "")
                sev = a.get("severity", "info")
                msg = a.get("message", "")
                self.alerts_full_list.addItem(make_list_item(f"{ts} • {msg}", sev))
        except Exception:
            pass

        return view

    def _create_chat_view(self) -> QWidget:
        """View 4: Interactive 'Ask Sentinel' AI Chat with live telemetry and wear context injection."""
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 1. Header Row
        header_row = QHBoxLayout()
        title_box = QVBoxLayout()
        chat_title = QLabel("💬 Ask Sentinel AI")
        chat_title.setStyleSheet("font-size: 26px; font-weight: bold; color: #f8fafc;")
        chat_desc = QLabel("Interactive Hardware Diagnostics & System Performance Engineering Assistant")
        chat_desc.setStyleSheet("font-size: 13px; color: #8ba0bd;")
        title_box.addWidget(chat_title)
        title_box.addWidget(chat_desc)
        header_row.addLayout(title_box, 1)

        self.chat_backend_badge = QLabel("🟢 Connected: LM Studio / Ollama • RTX 5070 Offload")
        self.chat_backend_badge.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #34d399; background-color: #064e3b; "
            "border: 1px solid #059669; border-radius: 6px; padding: 6px 12px;"
        )
        header_row.addWidget(self.chat_backend_badge, 0, Qt.AlignVCenter)
        layout.addLayout(header_row)

        # 2. Suggested Prompts Action Pills
        pills_frame = QFrame()
        pills_frame.setStyleSheet("background-color: #0b1220; border: 1px solid #1e293b; border-radius: 8px; padding: 4px;")
        pills_layout = QHBoxLayout(pills_frame)
        pills_layout.setContentsMargins(8, 4, 8, 4)
        pills_layout.setSpacing(8)

        pills_label = QLabel("Quick Prompts:")
        pills_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        pills_layout.addWidget(pills_label)

        suggested_prompts = [
            "🔍 System Stability Triage",
            "🌊 Liquid 360 AIO Performance",
            "🔥 GPU Hotspot & VRAM Check",
            "🎮 Review Gaming Thermals",
            "💾 NVMe Health & Lifespan",
        ]

        pill_style = """
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """
        for prompt_text in suggested_prompts:
            btn_pill = QPushButton(prompt_text)
            btn_pill.setCursor(Qt.PointingHandCursor)
            btn_pill.setStyleSheet(pill_style)
            clean_text = prompt_text.split(" ", 1)[1]
            btn_pill.clicked.connect(lambda checked, pt=clean_text: self._send_chat_query(pt))
            pills_layout.addWidget(btn_pill)

        pills_layout.addStretch()
        layout.addWidget(pills_frame)

        # 3. Chat History Scroll Area
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("""
            QScrollArea {
                background-color: #0b1220;
                border: 1px solid #1e293b;
                border-radius: 12px;
            }
            QScrollBar:vertical {
                background: #0b1220;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #243244;
                border-radius: 4px;
                min-height: 20px;
            }
        """)

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background-color: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(16, 16, 16, 16)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_container)
        layout.addWidget(self.chat_scroll, 1)

        # Initial welcome greeting bubble
        welcome_msg = (
            "👋 Greetings! I am Sentinel AI, your dedicated hardware diagnostics and performance assistant.\n\n"
            "I am continuously monitoring your Intel Core i7-12700 CPU, Cooler Master Liquid 360 AIO, "
            "Gigabyte Z790 Aorus Elite AX motherboard, and NVIDIA GeForce RTX 5070 GPU in your G8 Panoramic chassis.\n\n"
            "Feel free to ask about your live thermals, physical cooler degradation, NVMe SSD endurance, or past gaming sessions."
        )
        self._append_chat_bubble(
            "assistant",
            welcome_msg,
            source="Sentinel Core",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # 4. Message Input & Action Bar
        input_card = QFrame()
        input_card.setStyleSheet("""
            QFrame {
                background-color: #101828;
                border: 1px solid #243244;
                border-radius: 10px;
                padding: 6px;
            }
        """)
        input_layout = QHBoxLayout(input_card)
        input_layout.setContentsMargins(6, 4, 6, 4)
        input_layout.setSpacing(8)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask Sentinel about your hardware, cooling efficiency, gaming thermals, or optimizations...")
        self.chat_input.setStyleSheet("""
            QLineEdit {
                background-color: #0b1220;
                color: #f8fafc;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 10px 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
            }
        """)
        self.chat_input.returnPressed.connect(lambda: self._send_chat_query(self.chat_input.text().strip()))
        input_layout.addWidget(self.chat_input, 1)

        self.btn_chat_send = QPushButton("Send 🚀")
        self.btn_chat_send.setCursor(Qt.PointingHandCursor)
        self.btn_chat_send.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px;
                padding: 10px 18px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:disabled {
                background-color: #1e293b;
                color: #64748b;
            }
        """)
        self.btn_chat_send.clicked.connect(lambda checked=False: self._send_chat_query(self.chat_input.text().strip()))
        input_layout.addWidget(self.btn_chat_send)

        btn_clear = QPushButton("Clear")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setToolTip("Clear conversation history")
        btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                font-size: 13px;
                font-weight: 500;
                border-radius: 6px;
                padding: 10px 14px;
                border: 1px solid #334155;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f8fafc;
            }
        """)
        btn_clear.clicked.connect(self._clear_chat_history)
        input_layout.addWidget(btn_clear)

        layout.addWidget(input_card)
        return view

    def _append_chat_bubble(self, role: str, text: str, source: str = "", timestamp: str = ""):
        """Appends a styled conversation bubble to the chat scroll area."""
        bubble_row = QHBoxLayout()
        bubble_row.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(4)

        if role == "user":
            bubble_row.addStretch()
            card.setStyleSheet("""
                QFrame {
                    background-color: #0f2942;
                    border: 1px solid #0284c7;
                    border-radius: 10px;
                    max-width: 650px;
                }
            """)
            lbl_meta = QLabel(f"👤 You • {timestamp}")
            lbl_meta.setStyleSheet("font-size: 11px; font-weight: 600; color: #7dd3fc;")
            lbl_body = QLabel(text)
            lbl_body.setStyleSheet("font-size: 13px; color: #f0f9ff;")
            lbl_body.setWordWrap(True)
            card_layout.addWidget(lbl_meta)
            card_layout.addWidget(lbl_body)
            bubble_row.addWidget(card)
        else:
            card.setStyleSheet("""
                QFrame {
                    background-color: #101828;
                    border: 1px solid #243244;
                    border-radius: 10px;
                    max-width: 750px;
                }
            """)
            src_str = f" • Source: {source}" if source else ""
            lbl_meta = QLabel(f"🛡️ Sentinel AI{src_str} • {timestamp}")
            lbl_meta.setStyleSheet("font-size: 11px; font-weight: 600; color: #38bdf8;")
            lbl_body = QLabel(text)
            lbl_body.setStyleSheet("font-size: 13px; color: #e2e8f0; line-height: 140%;")
            lbl_body.setWordWrap(True)
            card_layout.addWidget(lbl_meta)
            card_layout.addWidget(lbl_body)
            bubble_row.addWidget(card)
            bubble_row.addStretch()

        # Insert before stretch item at end of chat_layout
        insert_idx = max(0, self.chat_layout.count() - 1)
        self.chat_layout.insertLayout(insert_idx, bubble_row)

        # Auto-scroll to bottom
        QTimer.singleShot(60, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))

    def _send_chat_query(self, user_msg: str):
        """Sends user message to local inference backend with real-time hardware telemetry."""
        query = (user_msg or "").strip()
        if not query:
            return
        if self._chat_busy:
            # A previous inference is still running; ignore the overlapping send
            # so workers can't interleave history entries.
            return
        self._chat_busy = True

        self.chat_input.clear()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._append_chat_bubble("user", query, timestamp=now_str)

        # Disable input while processing
        self.btn_chat_send.setEnabled(False)
        self.btn_chat_send.setText("Thinking... ⏳")
        self.chat_input.setEnabled(False)

        try:
            # 1. Gather live hardware context
            predictive_data = None
            if hasattr(self, "predictive_engine"):
                try:
                    pa = self.predictive_engine.evaluate_system(self.latest_metrics, self._last_storage_health)
                    predictive_data = {
                        "cooling_efficiency": pa.cooling_efficiency_percent,
                        "thermal_resistance": pa.cpu_thermal_resistance,
                        "hotspot_delta": pa.gpu_hotspot_delta,
                        "ssd_years": pa.ssd_estimated_years_remaining,
                    }
                except Exception:
                    pass

            recent_sessions = None
            if hasattr(self, "db_manager"):
                try:
                    recent_sessions = self.db_manager.get_recent_gaming_sessions(limit=3)
                except Exception:
                    pass

            recent_alerts = None
            if hasattr(self, "db_manager"):
                try:
                    recent_alerts = self.db_manager.get_recent_alerts(limit=3)
                except Exception:
                    pass

            system_context = self.chat_engine.build_system_context(
                metrics=self.latest_metrics,
                predictive_data=predictive_data,
                storage_health=self._last_storage_health,
                recent_sessions=recent_sessions,
                alerts=recent_alerts,
            )

            # 2. Spawn ChatWorker in background QThread
            self.chat_worker = ChatWorker(
                chat_engine=self.chat_engine,
                user_message=query,
                system_context=system_context,
            )
            self.chat_worker.response_ready.connect(self._on_chat_response_ready)
            self.chat_worker.start()

            # 3. UI Watchdog Timer: guarantee input recovery if local inference
            #    runs longer than CHAT_WATCHDOG_SECONDS.  The worker thread is
            #    left alone; only the input widgets are re-enabled.
            QTimer.singleShot(CHAT_WATCHDOG_SECONDS * 1000, self._on_chat_timeout)
        except Exception as e:
            self._chat_busy = False
            self.btn_chat_send.setEnabled(True)
            self.btn_chat_send.setText("Send 🚀")
            self.chat_input.setEnabled(True)
            self.chat_input.setFocus()
            self._append_chat_bubble(
                "assistant",
                f"⚠️ Error preparing hardware context: {str(e)}",
                source="Sentinel Recovery",
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

    def _on_chat_timeout(self):
        """Watchdog callback to re-enable UI if inference hangs or takes too long."""
        self._chat_busy = False
        if hasattr(self, "btn_chat_send") and not self.btn_chat_send.isEnabled():
            self.btn_chat_send.setEnabled(True)
            self.btn_chat_send.setText("Send 🚀")
            self.chat_input.setEnabled(True)
            self.chat_input.setFocus()
            self._append_chat_bubble(
                "assistant",
                f"⚠️ Local inference timed out after {CHAT_WATCHDOG_SECONDS} seconds.\n\n"
                "• Ensure LM Studio has 'Start Server' toggled ON under the Local Server (<->) tab.\n"
                "• Verify port 1234 is active and Gemma 2 is loaded with GPU offloading.",
                source="Sentinel Watchdog",
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

    def _on_chat_response_ready(self, response: dict):
        """Receives assistant response from worker thread and displays it in chat."""
        self._chat_busy = False
        content = response.get("content", "Diagnostic analysis completed.")
        source = response.get("source", "Sentinel Core")
        timestamp = response.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        self._append_chat_bubble("assistant", content, source=source, timestamp=timestamp)

        # Re-enable inputs
        self.btn_chat_send.setEnabled(True)
        self.btn_chat_send.setText("Send 🚀")
        self.chat_input.setEnabled(True)
        self.chat_input.setFocus()

    def _clear_chat_history(self):
        """Clears conversational history and resets chat layout."""
        if hasattr(self, "chat_engine"):
            self.chat_engine.clear_history()

        # Remove all widgets from chat_layout except trailing stretch
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Clear sub-layout items, then delete the layout itself so the
                # bubble row QHBoxLayouts don't leak on every clear.
                lay = item.layout()
                while lay.count():
                    sub = lay.takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
                lay.deleteLater()

        welcome_msg = (
            "Chat history cleared. I am ready for new questions regarding your "
            "Intel Core i7-12700, Cooler Master Liquid 360 AIO, Gigabyte Z790 Aorus Elite AX, or RTX 5070."
        )
        self._append_chat_bubble(
            "assistant",
            welcome_msg,
            source="Sentinel Core",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _create_settings_view(self) -> QWidget:
        """View 5: Configuration, Threshold Settings & System Utilities with responsive scrollable layout."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #08111e;
                width: 10px;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #1e293b;
                min-height: 30px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #0284c7;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(18)

        # Header Title
        header_box = QVBoxLayout()
        header = QLabel("Sentinel Configuration & Settings")
        header.setStyleSheet("font-size: 26px; font-weight: bold; color: #f8fafc; border: none; background: transparent;")
        subheader = QLabel("Hardware polling rates, sensor drivers, threshold definitions, and OS startup automation")
        subheader.setStyleSheet("font-size: 13px; color: #8ba0bd; border: none; background: transparent; padding-bottom: 4px;")
        header_box.addWidget(header)
        header_box.addWidget(subheader)
        layout.addLayout(header_box)

        def create_card(card_id: str, title: str, icon: str) -> tuple[QFrame, QGridLayout]:
            card = QFrame()
            card.setObjectName(card_id)
            card.setStyleSheet(f"""
                QFrame#{card_id} {{
                    background-color: #101828;
                    border: 1px solid #243244;
                    border-radius: 12px;
                    padding: 16px;
                }}
                QFrame#{card_id} QLabel {{
                    border: none;
                    background: transparent;
                    padding: 0px;
                }}
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 16)
            card_layout.setSpacing(12)

            title_lbl = QLabel(f"{icon}  {title}")
            title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc; border-bottom: 1px solid #1e293b; padding-bottom: 8px;")
            card_layout.addWidget(title_lbl)

            grid = QGridLayout()
            grid.setContentsMargins(0, 4, 0, 0)
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(10)
            grid.setColumnStretch(0, 0)
            grid.setColumnStretch(1, 1)
            card_layout.addLayout(grid)

            return card, grid

        def add_row(grid: QGridLayout, row: int, label_text: str, val_text: str, val_color: str = "#38bdf8", is_badge: bool = False) -> QLabel:
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 13px; color: #94a3b8; font-weight: 500; border: none; background: transparent;")
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            val = QLabel(val_text)
            if is_badge:
                val.setStyleSheet(f"font-size: 12px; color: {val_color}; font-weight: 600; background-color: rgba(30, 41, 59, 200); border: 1px solid #334155; border-radius: 4px; padding: 2px 8px;")
            else:
                val.setStyleSheet(f"font-size: 13px; color: {val_color}; font-family: monospace; font-weight: 600; border: none; background: transparent;")
            val.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            grid.addWidget(lbl, row, 0)
            grid.addWidget(val, row, 1)
            return val

        # Top Row: Hardware Architecture (Left) & AI Engine (Right)
        grid_top = QGridLayout()
        grid_top.setSpacing(16)

        # 1. System & Hardware Architecture Card
        card_sys, grid_sys = create_card("cardSysArch", "System & Hardware Architecture", "🖥️")
        elevated = is_admin()
        self.settings_elevation_val = add_row(
            grid_sys, 0, "Process Elevation:",
            "Administrator (Full Access)" if elevated else "Standard User (Limited)",
            val_color="#34d399" if elevated else "#f59e0b",
            is_badge=True
        )
        temp_avail = self.latest_metrics.get("cpu", {}).get("temp_available", False)
        self.settings_cpu_driver_val = add_row(
            grid_sys, 1, "CPU Thermal Driver:",
            "Active (LibreHardwareMonitor)" if temp_avail else "Elevation Required (Run as Admin)",
            val_color="#34d399" if temp_avail else "#f59e0b",
            is_badge=True
        )
        is_wmi_pwr = self.latest_metrics.get("cpu", {}).get("power_source") == "wmi_lhm_power"
        self.settings_cpu_power_val = add_row(
            grid_sys, 2, "CPU Power Telemetry:",
            "WMI LHM Sensor" if is_wmi_pwr else "Dynamic TDP (i7-12700)",
            val_color="#38bdf8"
        )
        add_row(grid_sys, 3, "Host Subsystems:", "Intel i7-12700 • RTX 5070 • Z790 AX", val_color="#e2e8f0")
        grid_top.addWidget(card_sys, 0, 0)

        # 2. Local AI Engine & Diagnostics Card
        card_ai, grid_ai = create_card("cardAiEngine", "Local AI Engine & Triage", "🧠")
        add_row(grid_ai, 0, "Inference Engine:", "Ollama (gemma2:9b) on RTX 5070", val_color="#38bdf8")
        add_row(grid_ai, 1, "Auto Triage Cooldown:", f"{AUTO_DIAG_COOLDOWN_SECONDS} seconds between alerts", val_color="#93c5fd")
        add_row(grid_ai, 2, "PC Health Matrix:", "40% Thermals • 30% RAM/Disk • 30% Headroom", val_color="#a7f3d0")
        add_row(grid_ai, 3, "Predictive Engine:", "Cooling Eff. • Contact Delta • SSD Health", val_color="#e2e8f0")
        grid_top.addWidget(card_ai, 0, 1)

        layout.addLayout(grid_top)

        # Middle Row: Telemetry Polling & Database (Left) & Alert Thresholds (Right)
        grid_mid = QGridLayout()
        grid_mid.setSpacing(16)

        # 3. Telemetry & Database Card
        card_db, grid_db = create_card("cardTelemetryDb", "Telemetry & Snapshot Retention", "⏱️")
        add_row(grid_db, 0, "UI Refresh Interval:", f"{UI_REFRESH_INTERVAL_MS} ms ({UI_REFRESH_INTERVAL_MS / 1000:.1f}s real-time)", val_color="#38bdf8")
        add_row(grid_db, 1, "DB Snapshot Interval:", f"{DB_LOG_INTERVAL_MS} ms ({DB_LOG_INTERVAL_MS / 1000:.1f}s persist)", val_color="#38bdf8")
        add_row(grid_db, 2, "Alert Debounce Window:", f"{ALERT_DEBOUNCE_SECONDS} seconds", val_color="#93c5fd")
        add_row(grid_db, 3, "Database Path:", str(DATABASE_PATH), val_color="#cbd5e1")
        add_row(grid_db, 4, "Snapshot Retention:", "7 days (auto-pruned on startup)", val_color="#94a3b8")
        grid_mid.addWidget(card_db, 0, 0)

        # 4. Sensor Alert Thresholds Card
        card_thresh, grid_thresh = create_card("cardAlertThresh", "Sensor Alert Thresholds", "🚨")
        add_row(grid_thresh, 0, "CPU Usage (Warn / Crit):", f"{THRESHOLDS.get('cpu_high')} / {THRESHOLDS.get('cpu_critical')}%", val_color="#f87171")
        add_row(grid_thresh, 1, "RAM Usage (Warn / Crit):", f"{THRESHOLDS.get('ram_high')} / {THRESHOLDS.get('ram_critical')}%", val_color="#fb923c")
        add_row(grid_thresh, 2, "Disk Usage (Warn / Crit):", f"{THRESHOLDS.get('disk_high')} / {THRESHOLDS.get('disk_critical')}%", val_color="#fbbf24")
        add_row(grid_thresh, 3, "GPU Temp (Warn / Crit):", f"{THRESHOLDS.get('gpu_temp_high')} / {THRESHOLDS.get('gpu_temp_critical')}°C", val_color="#f43f5e")
        add_row(grid_thresh, 4, "GPU Usage Threshold:", f"{THRESHOLDS.get('gpu_usage_high')}%", val_color="#38bdf8")
        grid_mid.addWidget(card_thresh, 0, 1)

        layout.addLayout(grid_mid)

        # Bottom Row: System Actions (Windows Auto-Start & Hardware Drivers)
        grid_actions = QGridLayout()
        grid_actions.setSpacing(16)

        # 5. Interactive Auto-Start Registration Control
        autostart_ctrl = QFrame()
        autostart_ctrl.setObjectName("cardAutostart")
        autostart_ctrl.setStyleSheet("""
            QFrame#cardAutostart {
                background-color: #101828;
                border: 1px solid #243244;
                border-radius: 12px;
                padding: 16px;
            }
            QFrame#cardAutostart QLabel {
                border: none;
                background: transparent;
                padding: 0px;
            }
        """)
        ctrl_layout = QHBoxLayout(autostart_ctrl)
        ctrl_layout.setContentsMargins(16, 14, 16, 16)
        ctrl_layout.setSpacing(14)

        ctrl_info = QVBoxLayout()
        ctrl_title = QLabel("🚀  Windows Startup Launch")
        ctrl_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc;")
        ctrl_desc = QLabel("Automatically launch Sentinel AI minimized to system tray upon Windows login.")
        ctrl_desc.setStyleSheet("font-size: 13px; color: #8ba0bd;")
        self.settings_autostart_status = QLabel(
            "Status: Enabled (Minimized to Tray on Boot)" if is_autostart_enabled() else "Status: Disabled (Manual Launch Only)"
        )
        self.settings_autostart_status.setStyleSheet(
            "font-size: 12px; color: #34d399; font-weight: 600;" if is_autostart_enabled() else "font-size: 12px; color: #94a3b8; font-weight: 500;"
        )
        ctrl_info.addWidget(ctrl_title)
        ctrl_info.addWidget(ctrl_desc)
        ctrl_info.addWidget(self.settings_autostart_status)
        ctrl_layout.addLayout(ctrl_info, 1)

        btn_autostart = QPushButton("Disable Auto-Start" if is_autostart_enabled() else "Enable Auto-Start on Boot")
        btn_autostart.setCursor(Qt.PointingHandCursor)
        btn_autostart.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                padding: 10px 18px;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)

        def on_toggle_clicked():
            success, is_on, msg = toggle_autostart(start_minimized=True)
            if is_on:
                btn_autostart.setText("Disable Auto-Start")
                self.settings_autostart_status.setText("Status: Enabled (Minimized to Tray on Boot)")
                self.settings_autostart_status.setStyleSheet("font-size: 12px; color: #34d399; font-weight: 600;")
                self.send_toast_notification(
                    title="Auto-Start Enabled",
                    message="Sentinel AI will now start minimized to tray on Windows boot.",
                    icon=QSystemTrayIcon.MessageIcon.Information,
                )
            else:
                btn_autostart.setText("Enable Auto-Start on Boot")
                self.settings_autostart_status.setText("Status: Disabled (Manual Launch Only)")
                self.settings_autostart_status.setStyleSheet("font-size: 12px; color: #94a3b8; font-weight: 500;")
                self.send_toast_notification(
                    title="Auto-Start Disabled",
                    message="Sentinel AI removed from Windows startup registry.",
                    icon=QSystemTrayIcon.MessageIcon.Information,
                )

        btn_autostart.clicked.connect(on_toggle_clicked)
        ctrl_layout.addWidget(btn_autostart, 0, Qt.AlignVCenter | Qt.AlignRight)
        grid_actions.addWidget(autostart_ctrl, 0, 0)

        # 6. Hardware Drivers & Firmware Management Card
        drivers_ctrl = QFrame()
        drivers_ctrl.setObjectName("cardDrivers")
        drivers_ctrl.setStyleSheet("""
            QFrame#cardDrivers {
                background-color: #101828;
                border: 1px solid #243244;
                border-radius: 12px;
                padding: 16px;
            }
            QFrame#cardDrivers QLabel {
                border: none;
                background: transparent;
                padding: 0px;
            }
        """)
        drv_layout = QHBoxLayout(drivers_ctrl)
        drv_layout.setContentsMargins(16, 14, 16, 16)
        drv_layout.setSpacing(14)

        drv_info = QVBoxLayout()
        drv_title = QLabel("🧰  Hardware Drivers & Firmware")
        drv_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc;")
        drv_desc = QLabel("Audit installed drivers (RTX 5070, Z790, 2.5GbE, NVMe) and scan PnP.")
        drv_desc.setStyleSheet("font-size: 13px; color: #8ba0bd;")
        drv_status = QLabel("Audit: Ready • Device Manager & PnP rescan available")
        drv_status.setStyleSheet("font-size: 12px; color: #38bdf8; font-weight: 500;")
        drv_info.addWidget(drv_title)
        drv_info.addWidget(drv_desc)
        drv_info.addWidget(drv_status)
        drv_layout.addLayout(drv_info, 1)

        btn_open_drivers = QPushButton("Audit Drivers 🧰")
        btn_open_drivers.setCursor(Qt.PointingHandCursor)
        btn_open_drivers.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                padding: 10px 18px;
            }
            QPushButton:hover { background-color: #0284c7; color: #ffffff; }
        """)
        btn_open_drivers.clicked.connect(self._show_drivers_dialog)
        drv_layout.addWidget(btn_open_drivers, 0, Qt.AlignVCenter | Qt.AlignRight)
        grid_actions.addWidget(drivers_ctrl, 0, 1)

        layout.addLayout(grid_actions)
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _create_tray_icon(self) -> QIcon:
        """Load app icon or dynamically generate an antialiased high-contrast shield icon."""
        # Resilient path resolution for source code and PyInstaller frozen bundles
        possible_paths = [
            Path(getattr(sys, "_MEIPASS", "")) / "assets" / "sentinel.ico",
            Path(sys.executable).resolve().parent / "assets" / "sentinel.ico",
            Path(__file__).resolve().parent.parent / "assets" / "sentinel.ico",
        ]
        for p in possible_paths:
            if p and p.exists():
                return QIcon(str(p))
        
        # Dynamically render a clean vector-like tray icon (32x32)
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#0284c7"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, 24, 24, 6, 6)
        painter.setBrush(QColor("#38bdf8"))
        painter.drawEllipse(10, 10, 12, 12)
        painter.end()
        return QIcon(pixmap)

    def _setup_system_tray(self):
        """Initialize PySide6 QSystemTrayIcon with context menu and notification hooks."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray_icon = QSystemTrayIcon(self._create_tray_icon(), self)
        self.tray_icon.setToolTip("Sentinel AI - Hardware Telemetry & Threat Protection")

        # Context Menu
        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #1f2937;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
                font-size: 13px;
            }
            QMenu::item:selected {
                background-color: #1e293b;
                color: #38bdf8;
            }
            QMenu::separator {
                height: 1px;
                background-color: #1f2937;
                margin: 4px 8px;
            }
        """)

        action_show = QAction("Open Dashboard", self)
        action_show.triggered.connect(self._restore_from_tray)
        tray_menu.addAction(action_show)

        action_diag = QAction("⚡ Run AI Diagnostics", self)
        action_diag.triggered.connect(lambda: self.trigger_ai_diagnostics(auto_triggered=False))
        tray_menu.addAction(action_diag)

        tray_menu.addSeparator()

        action_quit = QAction("Exit Sentinel AI", self)
        action_quit.triggered.connect(self._force_exit)
        tray_menu.addAction(action_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        """Toggle window visibility when user clicks tray icon."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible():
                if self.isMinimized():
                    self.showNormal()
                    self.activateWindow()
                else:
                    self.hide()
            else:
                self._restore_from_tray()

    def _restore_from_tray(self):
        """Restores and focuses the main dashboard window from tray."""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def send_toast_notification(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Critical,
    ):
        """Dispatches native Windows desktop notification via QSystemTrayIcon."""
        if hasattr(self, "tray_icon") and self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, icon, 5000)

    def _handle_alert_notification(self, metric_key: str, message: str, state: AlertState):
        """Callback triggered by AlertManager on critical threshold transitions."""
        

        if state == AlertState.CRITICAL:
            self.send_toast_notification(
                title="🚨 Sentinel AI - Critical Hardware Alert",
                message=message,
                icon=QSystemTrayIcon.MessageIcon.Critical,
            )

    def _force_exit(self):
        """Completely terminates Sentinel AI and background polling threads."""
        self._is_quitting = True
        self.close()
        QApplication.quit()

    def changeEvent(self, event):
        """Intercept minimize event to tuck application silently into system tray."""
        if event.type() == event.Type.WindowStateChange:
            if self.isMinimized() and hasattr(self, "tray_icon") and self.tray_icon and self.tray_icon.isVisible():
                self.hide()
                event.accept()
                return
        super().changeEvent(event)

    def closeEvent(self, event):
        """Minimize to system tray on window close, keeping background telemetry running."""
        if hasattr(self, "tray_icon") and self.tray_icon and self.tray_icon.isVisible() and not self._is_quitting:
            self.hide()
            if not self._tray_notice_shown:
                self.send_toast_notification(
                    title="Sentinel AI Background Monitoring",
                    message="Sentinel AI is running in the background. Continuous telemetry, database logging, and AI triage remain active.",
                    icon=QSystemTrayIcon.MessageIcon.Information,
                )
                self._tray_notice_shown = True
            event.ignore()
        else:
            self.worker.stop()
            # Shut down background inference workers.  Neither worker runs a Qt
            # event loop, so quit() is a no-op for them — request abort, drop
            # the result signals so nothing lands on torn-down slots, then wait
            # with a bound so a hung local model can't freeze the exit path.
            if self.diag_worker and self.diag_worker.isRunning():
                try:
                    self.diag_worker.abort()
                except Exception:
                    pass
                try:
                    self.diag_worker.diagnostics_ready.disconnect(self._on_diagnostics_completed)
                except Exception:
                    pass
                self.diag_worker.wait(3000)
            if self.chat_worker and self.chat_worker.isRunning():
                try:
                    self.chat_worker.response_ready.disconnect(self._on_chat_response_ready)
                except Exception:
                    pass
                self.chat_worker.wait(3000)
            event.accept()

    def push_alert(self, alert_key: str, text: str, severity: str = "info"):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry_text = f"{ts} • {text}"
        log_text = f"[{severity.upper()}] {ts} - {text}"

        # Insert to Overview panel widgets
        _capped_insert(self.alerts_list, make_list_item(entry_text, severity))
        _capped_insert(self.timeline_list, make_list_item(entry_text, severity))
        _capped_insert(self.log_list, make_list_item(log_text))

        # Insert to Full View lists
        if hasattr(self, "threats_full_list"):
            _capped_insert(self.threats_full_list, make_list_item(entry_text, severity))
        if hasattr(self, "logs_full_list"):
            _capped_insert(self.logs_full_list, make_list_item(log_text))
        if hasattr(self, "alerts_full_list"):
            _capped_insert(self.alerts_full_list, make_list_item(entry_text, severity))

        self.alert_counter += 1
        self.alert_count.setText(f"Alerts: {self.alert_counter}")

        # Persist alert to SQLite
        try:
            self.db_manager.insert_alert(alert_key, severity, text)
        except Exception:
            pass

    def _on_game_session_started(self, game_title: str):
        if hasattr(self, "btn_game_mode") and self.btn_game_mode:
            self.btn_game_mode.setText(f"🎮 Active: {game_title}")
            self.btn_game_mode.setStyleSheet("""
                QPushButton {
                    background-color: #581c87;
                    color: #e9d5ff;
                    border: 1px solid #a855f7;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 12px;
                    font-weight: 700;
                }
                QPushButton:hover { background-color: #7e22ce; color: #ffffff; }
            """)
        self.send_toast_notification(
            title="🎮 Game Mode Engaged",
            message=f"{game_title} active. DND notification suppression & session logging enabled.",
            icon=QSystemTrayIcon.MessageIcon.Information,
        )
        if hasattr(self, "status"):
            self.status.setText(f"🎮 Game Mode Active: {game_title} • DND Enabled")

    def _on_game_session_ended(self, summary):
        if hasattr(self, "btn_game_mode") and self.btn_game_mode:
            self.btn_game_mode.setText("🎮 Toggle Game Mode")
            self.btn_game_mode.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #a78bfa;
                    border: 1px solid #7c3aed;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover { background-color: #7c3aed; color: #ffffff; }
            """)
        if summary:
            self.send_toast_notification(
                title="🏁 Game Session Concluded",
                message=(
                    f"{summary.game_title} ({summary.duration_formatted}): "
                    f"Peak GPU {summary.max_gpu_temp}°C, Peak CPU {summary.max_cpu_temp}°C, "
                    f"Throttle Events {summary.throttle_incidents}."
                ),
                icon=QSystemTrayIcon.MessageIcon.Information,
            )
        if hasattr(self, "status"):
            self.status.setText("Sentinel AI: Real-time telemetry monitoring active")

    def _toggle_game_mode(self):
        if hasattr(self, "game_mode_mgr"):
            is_active, msg = self.game_mode_mgr.toggle_manual_mode()
            status_str = "Active (Manual)" if is_active else "Inactive"
            self.send_toast_notification(
                title=f"Game Mode {status_str}",
                message=msg,
                icon=QSystemTrayIcon.MessageIcon.Information,
            )

    def _evaluate_alerts_and_health(self, data: dict, update_widgets: bool):
        """Runs threshold alerting, health scoring, and auto-diagnostics.

        Called on every telemetry tick — including while the window is hidden
        in the system tray — so background monitoring never silently stops
        alerting.  Widget text updates are skipped when `update_widgets` is
        False; the underlying state (alert manager, DB log, toasts) still runs.
        """
        cpu = data.get("cpu", {})
        ram = data.get("ram", {})
        disk = data.get("disk", {})
        gpu = data.get("gpu", {})

        cpu_usage = cpu.get("usage", 0.0)
        ram_pct = ram.get("percent", 0.0)
        disk_pct = disk.get("percent", 0.0)
        cpu_temp = cpu.get("temperature", 0.0)
        gpu_available = bool(gpu.get("available"))
        gpu_temp = gpu.get("temperature", 0.0) if gpu_available else 0.0
        gpu_usage = gpu.get("usage", 0.0) if gpu_available else 0.0

        # Weighted PC Health Score
        try:
            health = calculate_health_score(data)
            self.latest_health = health
            if update_widgets and hasattr(self, "system_health"):
                self.system_health.setText(f"Health: {health['total_score']}/100 ({health['status']})")
                self.system_health.setStyleSheet(
                    f"font-size: 13px; font-weight: 600; color: {health['color']}; padding-right: 10px;"
                )
        except Exception:
            pass

        # Edge-Triggered Alert Evaluations
        evaluations = [
            ("disk", disk_pct, THRESHOLDS.get("disk_high", 85.0), THRESHOLDS.get("disk_critical", 92.0)),
            ("cpu", cpu_usage, THRESHOLDS.get("cpu_high", 80.0), THRESHOLDS.get("cpu_critical", 90.0)),
            ("ram", ram_pct, THRESHOLDS.get("ram_high", 80.0), THRESHOLDS.get("ram_critical", 90.0)),
        ]
        if cpu_temp > 0:
            evaluations.append((
                "cpu_temp",
                cpu_temp,
                80.0,
                90.0,
            ))
        if gpu_available and gpu_temp > 0:
            evaluations.append((
                "gpu_temp",
                gpu_temp,
                THRESHOLDS.get("gpu_temp_high", 75.0),
                THRESHOLDS.get("gpu_temp_critical", 85.0),
            ))
        if gpu_available:
            evaluations.append((
                "gpu_usage",
                gpu_usage,
                THRESHOLDS.get("gpu_usage_high", 90.0),
                95.0,
            ))

        for metric, val, warn, crit in evaluations:
            changed, state, msg = self.alert_manager.evaluate(metric, val, warn, crit)
            if changed and msg:
                severity = "critical" if state == AlertState.CRITICAL else ("warning" if state == AlertState.WARNING else "info")
                self.push_alert(metric, msg, severity)

                # Automated AI diagnostics triggered on critical excursion
                if state == AlertState.CRITICAL:
                    self._check_and_trigger_auto_diagnostics(metric, msg)

    def handle_metrics_update(self, data: dict):
        self.latest_metrics = data
        window_visible = not (self.isMinimized() or not self.isVisible())

        # --- Always-on background monitoring: game mode, storage cache, alert
        # evaluation, health scoring, and auto-diagnostics run on every tick,
        # even when the window is minimized to the tray.  Only widget drawing
        # is skipped while hidden.
        if hasattr(self, "game_mode_mgr"):
            self.game_mode_mgr.poll_detection(data)
            if self.game_mode_mgr.is_active:
                self.game_mode_mgr.sample_telemetry(data)

        # Periodic storage SMART reliability cache (debounced every 120 seconds)
        now_ts = time.time()
        if (now_ts - self._last_storage_check_time) > 120.0:
            self._last_storage_check_time = now_ts  # Immediately debounce before query
            try:
                self._last_storage_health = get_storage_health(drive_letter="C:")
            except Exception:
                pass

        self._evaluate_alerts_and_health(data, update_widgets=window_visible)

        if not window_visible:
            # Skip GUI drawing overhead while hidden; monitoring continues above.
            return

        # Live update settings view indicators if active
        if hasattr(self, "settings_cpu_driver_val") and self.settings_cpu_driver_val:
            temp_avail = data.get("cpu", {}).get("temp_available", False)
            self.settings_cpu_driver_val.setText("Active (LibreHardwareMonitor)" if temp_avail else "Elevation Required (Run as Admin)")
            self.settings_cpu_driver_val.setStyleSheet(
                "font-size: 12px; color: #34d399; font-weight: 600; background-color: rgba(30, 41, 59, 200); border: 1px solid #334155; border-radius: 4px; padding: 2px 8px;"
                if temp_avail else
                "font-size: 12px; color: #f59e0b; font-weight: 600; background-color: rgba(30, 41, 59, 200); border: 1px solid #334155; border-radius: 4px; padding: 2px 8px;"
            )

        # Predictive Hardware Failure Analysis
        if hasattr(self, "predictive_engine") and hasattr(self, "lbl_pred_cooling"):
            try:
                pa = self.predictive_engine.evaluate_system(data, self._last_storage_health)
                c_text = f"🌊 AIO Liquid Efficiency: {pa.cooling_efficiency_percent}%\nθ = {pa.cpu_thermal_resistance:.3f} °C/W • {pa.cpu_health_status}"
                h_text = f"🔥 RTX 5070 Hotspot Spread: +{pa.gpu_hotspot_delta:.1f}°C\n{pa.gpu_contact_status}"
                s_text = f"💾 NVMe Flash Health: {pa.ssd_health_percent}%\nEst. Lifespan: ~{pa.ssd_estimated_years_remaining} Years • {pa.ssd_wear_status}"
                self.lbl_pred_cooling.setText(c_text)
                self.lbl_pred_hotspot.setText(h_text)
                self.lbl_pred_ssd.setText(s_text)
                self.lbl_pred_advisory.setText(f"💡 Diagnostic Advisory: {pa.predictive_advisory}")
            except Exception:
                pass

        

        cpu = data["cpu"]
        ram = data["ram"]
        disk = data["disk"]
        gpu = data["gpu"]

        # CPU Card (Updated with Temperature and Power Consumption)
        cpu_usage = cpu.get("usage", 0.0)
        cpu_freq = cpu.get("frequency", 0.0)
        cpu_temp = cpu.get("temperature", 0.0)
        cpu_power = cpu.get("power_watts", 0.0)
        temp_avail = cpu.get("temp_available", cpu_temp > 0.0)
        is_elevated = cpu.get("is_elevated", True)

        # Dynamic Sensor Warning Banner visibility
        if hasattr(self, "sensor_warning_banner") and self.sensor_warning_banner:
            if not temp_avail and not is_elevated:
                self.sensor_warning_banner.setVisible(True)
            else:
                self.sensor_warning_banner.setVisible(False)

        if temp_avail:
            temp_str = f" • {cpu_temp:.0f}°C"
        elif not is_elevated:
            temp_str = " • Temp: Elevate"
        else:
            temp_str = ""

        power_str = f" • {cpu_power:.0f}W" if cpu_power > 0 else ""
        self.cards["CPU"].set_value(
            f"Usage: {cpu_usage:.1f}%\nFreq: {cpu_freq:.0f} MHz{temp_str}{power_str}",
            cpu_usage,
        )

        # RAM Card
        ram_used_gb = ram.get("used", 0) / (1024 ** 3)
        ram_total_gb = ram.get("total", 0) / (1024 ** 3)
        ram_pct = ram.get("percent", 0.0)
        self.cards["RAM"].set_value(
            f"Used: {ram_used_gb:.1f} GB\nTotal: {ram_total_gb:.1f} GB\nPercent: {ram_pct:.1f}%",
            ram_pct,
        )

        # Disk Card
        disk_used_gb = disk.get("used", 0) / (1024 ** 3)
        disk_total_gb = disk.get("total", 0) / (1024 ** 3)
        disk_pct = disk.get("percent", 0.0)
        mount = disk.get("mount", "/")
        self.cards["Disk"].set_value(
            f"Drive: {mount}\nUsed: {disk_used_gb:.1f} GB\nTotal: {disk_total_gb:.1f} GB",
            disk_pct,
        )

        # GPU Card
        gpu_usage = 0.0
        gpu_temp = 0.0
        if gpu.get("available"):
            gpu_usage = gpu.get("usage", 0.0)
            vram_used_gb = gpu.get("vram_used", 0) / (1024 ** 3)
            vram_total_gb = gpu.get("vram_total", 0) / (1024 ** 3)
            power = gpu.get("power_watts", 0.0)
            gpu_temp = gpu.get("temperature", 0.0)
            self.cards["GPU"].set_value(
                f"{gpu.get('name')}\nUsage: {gpu_usage:.0f}% • Temp: {gpu_temp:.0f}°C\nVRAM: {vram_used_gb:.1f}/{vram_total_gb:.1f} GB • {power:.0f}W",
                gpu_usage,
            )
        else:
            self.cards["GPU"].set_value(f"{gpu.get('name', 'Unavailable')}", 0.0)

        # Live Chart Feed
        self.chart.add_snapshot(cpu_usage, ram_pct, gpu_usage)

        self.status.setText(f"Status: Monitoring active • Refreshed: {datetime.now().strftime('%H:%M:%S')}")


def main():
    app = QApplication(sys.argv)
    start_minimized = "--minimized" in sys.argv or "--tray" in sys.argv
    window = SentinelDashboard()
    if not start_minimized:
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

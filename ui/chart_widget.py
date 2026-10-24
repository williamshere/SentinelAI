"""
ui/chart_widget.py - Real-time rolling hardware telemetry chart.
"""
from collections import deque
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

try:
    from ui.theme import DashboardTheme as _Theme

    _H_BG = _Theme.HISTORY_BG.name()
    _H_ACCENT = _Theme.HISTORY_ACCENT.name()
    _H_LIGHT = _Theme.HISTORY_ACCENT_LIGHT.name()
except Exception:  # theme is cosmetic; never block charting
    _H_BG, _H_ACCENT, _H_LIGHT = "#000000", "#2563eb", "#38bdf8"


class TelemetryChartWidget(QFrame):
    def __init__(self, title: str = "Performance History (Trailing 60s)", max_points: int = 60):
        super().__init__()
        self.max_points = max_points
        self.setObjectName("chartCard")
        self.setStyleSheet("""
            #chartCard {
                background-color: #101828;
                border: 1px solid #243244;
                border-radius: 12px;
                padding: 12px;
            }
        """)

        # Data buffers (0-100%)
        self.cpu_data: deque[float] = deque(maxlen=max_points)
        self.ram_data: deque[float] = deque(maxlen=max_points)
        self.gpu_data: deque[float] = deque(maxlen=max_points)

        # Layout & Legend
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        header_layout = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #eaf1ff;")
        header_layout.addWidget(title_label)

        # Color-coded rich text legend
        legend = QLabel(
            '<span style="color: #06b6d4;">■ CPU</span> &nbsp;&nbsp;'
            '<span style="color: #a855f7;">■ RAM</span> &nbsp;&nbsp;'
            '<span style="color: #3b82f6;">■ GPU</span>'
        )
        legend.setTextFormat(Qt.RichText)
        legend.setStyleSheet("font-size: 12px;")
        header_layout.addWidget(legend, 0, Qt.AlignRight)
        layout.addLayout(header_layout)

        layout.addStretch()
        self.setMinimumHeight(160)

    def add_snapshot(self, cpu_val: float, ram_val: float, gpu_val: float):
        """Append a real-time data point and repaint the chart."""
        self.cpu_data.append(max(0.0, min(100.0, float(cpu_val or 0.0))))
        self.ram_data.append(max(0.0, min(100.0, float(ram_val or 0.0))))
        self.gpu_data.append(max(0.0, min(100.0, float(gpu_val or 0.0))))
        self.update()

    def load_history(self, records: list[dict]):
        """Hydrate chart buffer with historical records from database/manager.py."""
        self.cpu_data.clear()
        self.ram_data.clear()
        self.gpu_data.clear()

        for row in records[-self.max_points:]:
            cpu = row.get("cpu_usage")
            ram = row.get("ram_percent")
            gpu = row.get("gpu_usage")

            self.cpu_data.append(float(cpu if cpu is not None else 0.0))
            self.ram_data.append(float(ram if ram is not None else 0.0))
            self.gpu_data.append(float(gpu if gpu is not None else 0.0))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width() - 28
        h = self.height() - 52
        top_offset = 38
        left_offset = 14

        # Bounds check
        if w <= 0 or h <= 0:
            return

        # Draw grid lines (25%, 50%, 75%)
        grid_pen = QPen(QColor(36, 50, 68), 1, Qt.DashLine)
        painter.setPen(grid_pen)
        for pct in [0.25, 0.50, 0.75]:
            y = int(top_offset + h * (1.0 - pct))
            painter.drawLine(left_offset, y, left_offset + w, y)

        if len(self.cpu_data) < 2:
            return

        # Draw telemetry lines
        self._draw_series(painter, self.cpu_data, QColor("#06b6d4"), left_offset, top_offset, w, h)
        self._draw_series(painter, self.ram_data, QColor("#a855f7"), left_offset, top_offset, w, h)
        self._draw_series(painter, self.gpu_data, QColor("#3b82f6"), left_offset, top_offset, w, h)

    def _draw_series(self, painter: QPainter, data: deque, color: QColor, x_off: int, y_off: int, w: int, h: int):
        pen = QPen(color, 2)
        painter.setPen(pen)
        step_x = w / (self.max_points - 1)

        path = QPainterPath()
        start_idx = self.max_points - len(data)
        first = True

        for i, val in enumerate(data):
            x = x_off + (start_idx + i) * step_x
            y = y_off + h * (1.0 - (val / 100.0))
            if first:
                path.moveTo(x, y)
                first = False
            else:
                path.lineTo(x, y)

        painter.drawPath(path)

class HistoryChartWidget(QFrame):
    """Long-range history chart: one metric, blue-on-black, session bands."""

    def __init__(self, title: str = "History"):
        super().__init__()
        self.setObjectName("historyCard")
        self.setStyleSheet("""
            #historyCard {
                background-color: #000000;
                border: 1px solid #1d4ed8;
                border-radius: 12px;
                padding: 12px;
            }
        """)
        self._points: list = []  # [(datetime, float)]
        self._sessions: list = []  # [(start_dt, end_dt_or_None, title)]
        self._range_start = None
        self._range_end = None
        self._unit = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #bfdbfe;")
        header.addWidget(self.title_label)
        self.span_label = QLabel("")
        self.span_label.setStyleSheet("font-size: 12px; color: #60a5fa;")
        header.addWidget(self.span_label, 0, Qt.AlignRight)
        layout.addLayout(header)
        layout.addStretch()
        self.setMinimumHeight(260)

    def set_series(self, points, sessions=None, range_start=None, range_end=None, unit=""):
        """Load [(timestamp_str, value)] plus gaming-session bands."""
        from datetime import datetime as _dt

        parsed = []
        for ts, value in points or []:
            try:
                t = ts if hasattr(ts, "strftime") else _dt.strptime(str(ts), "%Y-%m-%d %H:%M:%S")
                parsed.append((t, float(value)))
            except (TypeError, ValueError):
                continue
        self._points = parsed
        self._sessions = []
        for s in sessions or []:
            try:
                st = s.get("start_time")
                en = s.get("end_time")
                st = st if hasattr(st, "strftime") else _dt.strptime(str(st), "%Y-%m-%d %H:%M:%S")
                en = None if not en else (en if hasattr(en, "strftime") else _dt.strptime(str(en), "%Y-%m-%d %H:%M:%S"))
                self._sessions.append((st, en, s.get("game_title", "Gaming session")))
            except (TypeError, ValueError):
                continue
        self._range_start = range_start
        self._range_end = range_end
        self._unit = unit or ""
        if parsed:
            self.span_label.setText(f"{parsed[0][0]:%Y-%m-%d %H:%M}  to  {parsed[-1][0]:%Y-%m-%d %H:%M}")
        else:
            self.span_label.setText("No data in range")
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        left, top = 56, 42
        w = self.width() - left - 24
        h = self.height() - top - 34
        if w <= 0 or h <= 0:
            return
        if len(self._points) < 2:
            painter.setPen(QColor("#60a5fa"))
            painter.drawText(left, top + 20, "Not enough data in this range yet - telemetry logs every 30 seconds.")
            return
        values = [v for _, v in self._points]
        lo, hi = min(values), max(values)
        pad = max((hi - lo) * 0.1, 1.0)
        lo, hi = lo - pad, hi + pad
        t0 = self._range_start or self._points[0][0]
        t1 = self._range_end or self._points[-1][0]
        span = max((t1 - t0).total_seconds(), 1.0)

        def x_of(t):
            return left + w * ((t - t0).total_seconds() / span)

        def y_of(v):
            return top + h * (1.0 - (v - lo) / (hi - lo))

        # Gaming-session bands
        band = QColor(37, 99, 235, 46)
        for st, en, _title in self._sessions:
            x1 = x_of(st)
            x2 = x_of(en) if en else left + w
            painter.fillRect(int(max(x1, left)), top, int(max(min(x2, left + w) - max(x1, left), 0)), h, band)
        # Grid + y labels
        painter.setPen(QPen(QColor(15, 35, 70), 1, Qt.DashLine))
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = int(top + h * frac)
            painter.drawLine(left, y, left + w, y)
            val = hi - (hi - lo) * frac
            painter.setPen(QColor("#60a5fa"))
            painter.drawText(4, y + 4, f"{val:.0f}{self._unit}")
            painter.setPen(QPen(QColor(15, 35, 70), 1, Qt.DashLine))
        # Series line (electric blue on black)
        path = QPainterPath()
        for i, (t, v) in enumerate(self._points):
            if i == 0:
                path.moveTo(x_of(t), y_of(v))
            else:
                path.lineTo(x_of(t), y_of(v))
        painter.setPen(QPen(QColor("#38bdf8"), 2))
        painter.drawPath(path)
        # Peak dot
        peak_t, peak_v = max(self._points, key=lambda p: p[1])
        painter.setBrush(QColor("#2563eb"))
        painter.setPen(QPen(QColor("#bfdbfe"), 1))
        painter.drawEllipse(int(x_of(peak_t)) - 4, int(y_of(peak_v)) - 4, 8, 8)

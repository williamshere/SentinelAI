"""
ui/chart_widget.py - Real-time rolling hardware telemetry chart.
"""
from collections import deque
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


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
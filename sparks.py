"""Light portal ring around the cursor — minimal, cheap to draw."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen


class SparkEngine:
    """Small golden ring + faint trail dots. No bursts, no particle storms."""

    def __init__(self) -> None:
        self._cursor = QPointF()
        self._cursor_active = False
        self._angle = 0.0
        self._trail: list[tuple[float, float, float]] = []  # x, y, alpha
        self._trail_max = 10

    def set_cursor(self, pos: QPointF, active: bool = True) -> None:
        self._cursor = pos
        self._cursor_active = active

    def trigger_portal_burst(self, x: float, y: float) -> None:
        pass

    @property
    def burst_done(self) -> bool:
        return True

    def spawn_trail(self, x: float, y: float) -> None:
        self._trail.append((x, y, 180.0))
        if len(self._trail) > self._trail_max:
            self._trail.pop(0)

    def clear_trail_anchor(self) -> None:
        self._trail.clear()

    def tick(self) -> None:
        self._angle += 0.05
        faded: list[tuple[float, float, float]] = []
        for x, y, alpha in self._trail:
            na = alpha - 22.0
            if na > 0:
                faded.append((x, y, na))
        self._trail = faded

    def draw(self, painter: QPainter) -> None:
        if not self._cursor_active:
            return

        cx, cy = self._cursor.x(), self._cursor.y()

        painter.setPen(Qt.PenStyle.NoPen)
        for x, y, alpha in self._trail:
            painter.setBrush(QColor(255, 200, 80, int(alpha)))
            painter.drawEllipse(QPointF(x, y), 2.0, 2.0)

        glow = QColor(255, 170, 40, 50)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), 16, 16)

        for radius in (14, 18):
            pen = QPen(QColor(255, 210, 70, 170), 2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            start = int(math.degrees(self._angle) * 16)
            painter.drawArc(
                int(cx - radius), int(cy - radius),
                int(radius * 2), int(radius * 2),
                start, 90 * 16,
            )

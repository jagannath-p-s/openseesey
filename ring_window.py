"""Floating sling-ring icon window with golden glow animation."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

import audit
import state

ASSET_DIR = Path(__file__).resolve().parent
RING_SIZE = 112
ICON_SIZE = 84


class RingWindow(QWidget):
    """Small always-on-top window showing the sling ring icon with golden glow when armed."""

    clicked = Signal()
    moved = Signal(int, int)

    def __init__(self, x: int | None = None, y: int | None = None) -> None:
        super().__init__()
        self._drag_offset = QPoint()
        self._press_global = QPoint()
        self._dragging = False
        self._armed = False
        self._glow_angle = 0.0
        self._pixmap = QPixmap(str(ASSET_DIR / "appicon.png"))

        self.setFixedSize(RING_SIZE, RING_SIZE)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        if x is None or y is None:
            sx, sy = state.get_ring_pos()
            x = x if x is not None else sx
            y = y if y is not None else sy

        self.move(x, y)
        self.setToolTip("Click: toggle sling mode · Drag: move ring · Esc: exit sling / quit · Ctrl+C: quit")

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start(20)

    def set_armed(self, armed: bool) -> None:
        """Toggle armed state and golden glow aura."""
        self._armed = armed
        self.update()

    def is_armed(self) -> bool:
        return self._armed

    def set_position(self, x: int, y: int) -> None:
        """Set ring position, update persistent state and log move."""
        self.move(x, y)
        state.set_ring_pos(x, y)
        audit.log_action("MOVE_RING", f"{x},{y}")
        self.moved.emit(x, y)

    def _on_anim_tick(self) -> None:
        if self._armed:
            self._glow_angle += 0.06
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        center = QPointF(cx, cy)

        # 1. If Armed: Draw Golden Glowing Mandala Aura around the icon
        if self._armed:
            # Concentric pulsating gold glow circles
            for radius, alpha in ((54, 25), (48, 45), (44, 75), (42, 110)):
                glow_color = QColor(255, 170, 0, alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(glow_color)
                painter.drawEllipse(center, radius, radius)

            # Rotating Arc Dashes (Dr. Strange Sling Ring Portal effect)
            for ring_i, r in enumerate((52, 46)):
                segments = 8
                for s in range(segments):
                    if s % 2 == 0:
                        continue
                    a0 = self._glow_angle * (1.0 if ring_i == 0 else -1.2) + (math.tau / segments) * s
                    a1 = a0 + (math.tau / segments) * 0.6
                    pen = QPen(QColor(255, 215, 0, 220), 2.5)
                    painter.setPen(pen)
                    painter.drawArc(
                        int(cx - r),
                        int(cy - r),
                        int(r * 2),
                        int(r * 2),
                        int(math.degrees(a0) * 16),
                        int(math.degrees(a1 - a0) * 16),
                    )

        # 2. Draw Ring Icon
        if self._pixmap.isNull():
            painter.setPen(Qt.GlobalColor.yellow)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "RING")
        else:
            scaled = self._pixmap.scaled(
                ICON_SIZE,
                ICON_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            ix = int((self.width() - scaled.width()) / 2.0)
            iy = int((self.height() - scaled.height()) / 2.0)
            painter.drawPixmap(ix, iy, scaled)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._press_global = event.globalPosition().toPoint()
            self._drag_offset = self._press_global - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double click resets ring to visible desktop position (150, 150)."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_position(150, 150)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            delta = event.globalPosition().toPoint() - self._press_global
            self._dragging = False
            if delta.manhattanLength() > 8:
                self.set_position(self.x(), self.y())
            else:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)



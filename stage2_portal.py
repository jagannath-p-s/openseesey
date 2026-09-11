#!/usr/bin/env python3
"""Stage 2 — cursor sprite + portal burst + idle sparkle."""

import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from sparks import SparkEngine

ASSET = Path(__file__).resolve().parent / "appicon.png"
SPRITE_SIZE = 28


class PortalOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._mouse = QPoint()
        self._pixmap = QPixmap(str(ASSET))
        self._engine = SparkEngine()
        self.setMouseTracking(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def showEvent(self, event) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        QGuiApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
        self._engine.trigger_portal_burst(self._mouse.x(), self._mouse.y())
        super().showEvent(event)

    def _tick(self) -> None:
        self._engine.set_cursor(QPointF(self._mouse), active=True)
        self._engine.tick()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._engine.draw(p)
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                SPRITE_SIZE,
                SPRITE_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = self._mouse.x() - scaled.width() // 2
            y = self._mouse.y() - scaled.height() // 2
            p.drawPixmap(x, y, scaled)
        p.end()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._mouse = event.position().toPoint()
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            QGuiApplication.restoreOverrideCursor()
            self.close()


def main() -> int:
    app = QApplication(sys.argv)
    w = PortalOverlay()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

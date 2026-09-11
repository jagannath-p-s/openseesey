#!/usr/bin/env python3
"""Stage 1 — custom cursor sprite, no portal or gestures."""

import sys
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

ASSET = Path(__file__).resolve().parent / "appicon.png"
SPRITE_SIZE = 28


class CursorOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._mouse = QPoint()
        self._pixmap = QPixmap(str(ASSET))
        self.setMouseTracking(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def showEvent(self, event) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        QGuiApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
        super().showEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
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
    w = CursorOverlay()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

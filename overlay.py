"""Fullscreen overlay — gestures, light portal cursor, vanish."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QWidget

import audit
import gesture_engine
import hit_tester
import icon_registry
import vanish
from sparks import SparkEngine
from state import GestureResult, SlingIconHit

ASSET_DIR = Path(__file__).resolve().parent
CURSOR_SPRITE_SIZE = 28
DESKTOP = Path.home() / "Desktop"


class Overlay(QWidget):
    closed = Signal()
    ring_move_requested = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self._armed = False
        self._drawing = False
        self._gesture_local: list[QPointF] = []
        self._last_local: list[QPointF] = []
        self._last_result: GestureResult | None = None
        self._last_hit_name = ""
        self._fade = 0.0
        self._toast = ""
        self._toast_timer = 0.0
        self._trail_tick = 0
        self._engine = SparkEngine()
        self._ring_pixmap = QPixmap(str(ASSET_DIR / "appicon.png"))

        self.setWindowTitle("OpenSesame")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

        icon_registry.on_ready(self.update)

    def is_armed(self) -> bool:
        return self._armed

    def show_curtain(self) -> None:
        pass

    def hide_curtain(self) -> None:
        pass

    def arm(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        self._armed = True
        self._gesture_local.clear()
        self._engine.clear_trail_anchor()
        QGuiApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.setFocus()
        self.update()

    def disarm(self) -> None:
        vanish.reveal_all(DESKTOP)
        QGuiApplication.restoreOverrideCursor()
        self._armed = False
        self._drawing = False
        self._gesture_local.clear()
        self._engine.set_cursor(QPointF(), active=False)
        self._engine.clear_trail_anchor()
        self.hide()
        self.closed.emit()

    def _tick(self) -> None:
        if self._fade > 0:
            self._fade = max(0.0, self._fade - 0.016)
        if self._toast_timer > 0:
            self._toast_timer = max(0.0, self._toast_timer - 0.016)
            if self._toast_timer <= 0:
                self._toast = ""

        cur = self.mapFromGlobal(QCursor.pos())
        self._engine.set_cursor(QPointF(cur), active=self._armed)
        if self._armed and not self._drawing:
            self._trail_tick += 1
            if self._trail_tick % 2 == 0:
                self._engine.spawn_trail(cur.x(), cur.y())

        self._engine.tick()
        if self._armed:
            self.update()

    def _toast_show(self, msg: str, seconds: float = 2.5) -> None:
        self._toast = msg
        self._toast_timer = seconds

    def _draw_cursor_sprite(self, painter: QPainter) -> None:
        if self._ring_pixmap.isNull():
            return
        cur = self.mapFromGlobal(QCursor.pos())
        scaled = self._ring_pixmap.scaled(
            CURSOR_SPRITE_SIZE,
            CURSOR_SPRITE_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = int(cur.x() - scaled.width() / 2)
        y = int(cur.y() - scaled.height() / 2)
        painter.drawPixmap(x, y, scaled)

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self._armed:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))

        if not icon_registry.calibration_ready():
            p.setFont(QFont("Sans", 14, QFont.Weight.Bold))
            p.setPen(QColor(255, 200, 80))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Calibrating desktop icons…")

        if self._fade > 0 and len(self._last_local) > 1:
            alpha = int(200 * self._fade / 1.8)
            ok = self._last_result and self._last_result.is_circle
            pen = QPen(
                QColor(255, 215, 50, alpha) if ok else QColor(255, 90, 80, alpha),
                3,
                Qt.PenStyle.DashLine,
            )
            p.setPen(pen)
            path = QPainterPath()
            path.moveTo(self._last_local[0])
            for pt in self._last_local[1:]:
                path.lineTo(pt)
            p.drawPath(path)

            if self._last_result:
                lc = self.mapFromGlobal(
                    QPoint(
                        int(self._last_result.centroid_x),
                        int(self._last_result.centroid_y),
                    )
                )
                r = max(20.0, self._last_result.radius)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QRectF(lc.x() - r, lc.y() - r, r * 2, r * 2))
                label = self._last_hit_name or (
                    "empty space" if ok else self._last_result.reason
                )
                p.drawText(
                    int(lc.x() - 100),
                    int(lc.y() + r + 8),
                    200,
                    20,
                    Qt.AlignmentFlag.AlignCenter,
                    f"→ {label}",
                )

        if len(self._gesture_local) > 1:
            pen = QPen(QColor(255, 215, 50, 240), 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            path = QPainterPath()
            path.moveTo(self._gesture_local[0])
            for pt in self._gesture_local[1:]:
                path.lineTo(pt)
            p.drawPath(path)

        self._engine.draw(p)

        self._draw_cursor_sprite(p)

        if self._toast:
            p.setFont(QFont("Sans", 11, QFont.Weight.Bold))
            tw = p.fontMetrics().horizontalAdvance(self._toast) + 32
            tr = QRectF((self.width() - tw) / 2, self.height() - 100, tw, 36)
            p.setPen(QPen(QColor(255, 215, 0), 1))
            p.setBrush(QColor(20, 15, 30, 220))
            p.drawRoundedRect(tr, 8, 8)
            p.setPen(QColor(255, 235, 180))
            p.drawText(tr, Qt.AlignmentFlag.AlignCenter, self._toast)

        icons = icon_registry.current_icons()
        p.setFont(QFont("Sans", 9))
        p.setPen(QColor(255, 200, 100, 200))
        ready = "ready" if icon_registry.calibration_ready() else "calibrating"
        hidden_n = len(vanish.session_hidden())
        p.drawText(
            16,
            self.height() - 16,
            f"OpenSesame · {ready} · {len(icons)} icons · {hidden_n} stashed · Esc restore+exit · Q quit",
        )

        p.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._armed or event.button() != Qt.MouseButton.LeftButton:
            return
        if not icon_registry.calibration_ready():
            if not icon_registry.calibration_ready():
                self._toast_show("⏳ Still calibrating…")
            return
        self._drawing = True
        self._gesture_local = [event.position()]
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drawing:
            self._gesture_local.append(event.position())
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self._drawing or event.button() != Qt.MouseButton.LeftButton:
            return
        self._drawing = False
        self._evaluate()
        event.accept()

    def _evaluate(self) -> None:
        if len(self._gesture_local) < 10:
            self._gesture_local.clear()
            return

        self._last_local = list(self._gesture_local)
        self._fade = 1.8
        self._last_hit_name = ""

        screen_pts = [
            (
                self.mapToGlobal(QPoint(int(p.x()), int(p.y()))).x(),
                self.mapToGlobal(QPoint(int(p.x()), int(p.y()))).y(),
            )
            for p in self._gesture_local
        ]
        self._gesture_local.clear()

        result = gesture_engine.analyze_circle(screen_pts)
        self._last_result = result
        if not result.is_circle:
            self._toast_show(f"Not a circle: {result.reason}")
            return

        if not icon_registry.calibration_ready():
            self._toast_show("⏳ Calibration still running…")
            audit.log_action("GESTURE_DEFERRED", "reason=calibration_not_ready")
            return

        had_stashed = bool(vanish.session_hidden())
        icon_registry.rescan_desktop()
        hit = hit_tester.resolve_hit(result, icon_registry.current_icons())

        if isinstance(hit, SlingIconHit):
            self._last_hit_name = hit.name
            QApplication.clipboard().setText(hit.path)
            audit.log_action("COPIED_TO_CLIPBOARD", f"name='{hit.name}' path='{hit.path}'")

            filename = Path(hit.path).name
            if vanish.hide_icon(DESKTOP, filename):
                audit.log_action("VANISH_OK", f"name={hit.name} path={hit.path}")
                self._toast_show(f"Stashed {hit.name}")
            else:
                self._toast_show(f"Stash failed for {hit.name}")
            return

        if had_stashed:
            self._last_hit_name = "summon"
            name = vanish.reveal_next_at(DESKTOP, result.centroid_x, result.centroid_y)
            if name:
                self._toast_show(f"Summoned {name} at portal")
            else:
                self._toast_show("Summon failed")
            return

        self._last_hit_name = "miss"
        self._toast_show("No icon in the circle — draw around a desktop icon")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self._armed:
            self.disarm()
            event.accept()
            return
        super().keyPressEvent(event)

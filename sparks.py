"""Golden sparkle trail while drawing + burst on accepted circle."""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen


class SparkEngine:
    def __init__(self) -> None:
        self._cursor = QPointF()
        self._cursor_active = False
        self._angle = 0.0
        self._particles: list[dict] = []
        self._burst_until = 0.0
        self._burst_x = 0.0
        self._burst_y = 0.0
        self._burst_radius = 0.0

    def set_cursor(self, pos: QPointF, active: bool = True) -> None:
        self._cursor = pos
        self._cursor_active = active

    def clear_trail_anchor(self) -> None:
        self._particles.clear()
        self._burst_until = 0.0

    def has_active_fx(self) -> bool:
        return bool(self._particles) or self._burst_until > 0

    def spawn_stroke_spark(self, x: float, y: float) -> None:
        for _ in range(3):
            angle = random.uniform(0.0, math.tau)
            speed = random.uniform(0.6, 2.4)
            self._spawn(
                x + random.uniform(-6.0, 6.0),
                y + random.uniform(-6.0, 6.0),
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                life=random.uniform(0.35, 0.75),
                size=random.uniform(3.0, 7.0),
                gold=random.random() > 0.2,
            )

    def trigger_circle_burst(self, x: float, y: float, radius: float) -> None:
        self._burst_x = x
        self._burst_y = y
        self._burst_radius = max(36.0, radius * 1.15)
        self._burst_until = 1.4

        ring_n = max(24, int(self._burst_radius / 3))
        for i in range(ring_n):
            angle = math.tau * i / ring_n
            px = x + math.cos(angle) * self._burst_radius
            py = y + math.sin(angle) * self._burst_radius
            tx = math.cos(angle + math.pi / 2) * random.uniform(1.2, 3.5)
            ty = math.sin(angle + math.pi / 2) * random.uniform(1.2, 3.5)
            self._spawn(
                px, py, tx, ty,
                life=random.uniform(0.55, 1.1),
                size=random.uniform(4.0, 9.0),
                gold=True,
            )

        for _ in range(48):
            angle = random.uniform(0.0, math.tau)
            dist = random.uniform(0.0, self._burst_radius * 0.65)
            speed = random.uniform(1.5, 5.0)
            self._spawn(
                x + math.cos(angle) * dist,
                y + math.sin(angle) * dist,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                life=random.uniform(0.45, 1.0),
                size=random.uniform(3.0, 8.0),
                gold=random.random() > 0.25,
            )

    def tick(self, dt: float = 0.016) -> bool:
        """Advance simulation; returns True if visuals still animating."""
        self._angle += 0.09
        if self._burst_until > 0:
            self._burst_until = max(0.0, self._burst_until - dt)

        alive: list[dict] = []
        for p in self._particles:
            p["life"] -= dt
            if p["life"] <= 0:
                continue
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.035
            alive.append(p)
        self._particles = alive[-180:]
        return self.has_active_fx() or self._cursor_active

    def _spawn(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        *,
        life: float,
        size: float,
        gold: bool,
    ) -> None:
        if len(self._particles) >= 180:
            self._particles.pop(0)
        self._particles.append(
            {
                "x": x,
                "y": y,
                "vx": vx,
                "vy": vy,
                "life": life,
                "max_life": life,
                "size": size,
                "gold": gold,
            }
        )

    def draw(self, painter: QPainter) -> None:
        if self._burst_until > 0:
            pulse = self._burst_until / 1.4
            for ring, width in ((1.12, 5.0), (1.0, 3.0), (0.88, 2.0)):
                r = self._burst_radius * ring * (0.92 + pulse * 0.08)
                alpha = int(200 * pulse / ring)
                pen = QPen(QColor(255, 220, 80, alpha), width)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(self._burst_x, self._burst_y), r, r)

            glow = QColor(255, 190, 50, int(70 * pulse))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(
                QPointF(self._burst_x, self._burst_y),
                self._burst_radius * 0.55,
                self._burst_radius * 0.55,
            )

        for p in self._particles:
            t = p["life"] / p["max_life"]
            alpha = int(255 * t * t)
            if p["gold"]:
                color = QColor(255, int(170 + 70 * t), int(30 + 90 * t), alpha)
            else:
                color = QColor(255, 255, 240, alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            sz = p["size"] * (0.55 + 0.55 * t)
            painter.drawEllipse(QPointF(p["x"], p["y"]), sz, sz)
            if p["gold"] and t > 0.5:
                painter.setBrush(QColor(255, 255, 220, int(alpha * 0.6)))
                painter.drawEllipse(QPointF(p["x"], p["y"]), sz * 0.35, sz * 0.35)

        if not self._cursor_active:
            return

        cx, cy = self._cursor.x(), self._cursor.y()
        for glow_r, alpha in ((32, 35), (24, 55), (18, 80)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 170, 40, alpha))
            painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        for radius, width in ((22, 3.5), (28, 2.5), (34, 2.0)):
            pen = QPen(QColor(255, 210, 70, 190), width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            start = int(math.degrees(self._angle) * 16)
            painter.drawArc(
                int(cx - radius),
                int(cy - radius),
                int(radius * 2),
                int(radius * 2),
                start,
                110 * 16,
            )

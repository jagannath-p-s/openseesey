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

    def spawn_stroke_spark(self, x: float, y: float) -> None:
        for _ in range(2):
            angle = random.uniform(0.0, math.tau)
            speed = random.uniform(0.4, 1.8)
            self._spawn(
                x + random.uniform(-3.0, 3.0),
                y + random.uniform(-3.0, 3.0),
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                life=random.uniform(0.25, 0.55),
                size=random.uniform(1.5, 3.5),
                gold=random.random() > 0.25,
            )

    def trigger_circle_burst(self, x: float, y: float, radius: float) -> None:
        self._burst_x = x
        self._burst_y = y
        self._burst_radius = max(24.0, radius)
        self._burst_until = 1.1

        ring_n = max(16, int(self._burst_radius / 4))
        for i in range(ring_n):
            angle = math.tau * i / ring_n
            px = x + math.cos(angle) * self._burst_radius
            py = y + math.sin(angle) * self._burst_radius
            tx = math.cos(angle + math.pi / 2) * random.uniform(0.8, 2.2)
            ty = math.sin(angle + math.pi / 2) * random.uniform(0.8, 2.2)
            self._spawn(px, py, tx, ty, life=random.uniform(0.45, 0.95), size=random.uniform(2.0, 4.5), gold=True)

        for _ in range(28):
            angle = random.uniform(0.0, math.tau)
            dist = random.uniform(0.0, self._burst_radius * 0.55)
            speed = random.uniform(1.0, 3.5)
            self._spawn(
                x + math.cos(angle) * dist,
                y + math.sin(angle) * dist,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                life=random.uniform(0.35, 0.8),
                size=random.uniform(1.5, 4.0),
                gold=random.random() > 0.3,
            )

    def tick(self, dt: float = 0.016) -> None:
        self._angle += 0.07
        if self._burst_until > 0:
            self._burst_until = max(0.0, self._burst_until - dt)

        alive: list[dict] = []
        for p in self._particles:
            p["life"] -= dt
            if p["life"] <= 0:
                continue
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.04
            alive.append(p)
        self._particles = alive[-140:]

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
        if len(self._particles) >= 140:
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
            pulse = self._burst_until / 1.1
            r = self._burst_radius * (1.05 - pulse * 0.15)
            pen = QPen(QColor(255, 220, 80, int(180 * pulse)), 2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                QPointF(self._burst_x, self._burst_y),
                r,
                r,
            )

        for p in self._particles:
            t = p["life"] / p["max_life"]
            alpha = int(255 * t * t)
            if p["gold"]:
                color = QColor(255, int(180 + 60 * t), int(40 + 80 * t), alpha)
            else:
                color = QColor(255, 255, 240, alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            sz = p["size"] * (0.6 + 0.4 * t)
            painter.drawEllipse(QPointF(p["x"], p["y"]), sz, sz)

        if not self._cursor_active:
            return

        cx, cy = self._cursor.x(), self._cursor.y()
        glow = QColor(255, 170, 40, 45)
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), 14, 14)

        for radius in (12, 16):
            pen = QPen(QColor(255, 210, 70, 160), 2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            start = int(math.degrees(self._angle) * 16)
            painter.drawArc(
                int(cx - radius),
                int(cy - radius),
                int(radius * 2),
                int(radius * 2),
                start,
                100 * 16,
            )

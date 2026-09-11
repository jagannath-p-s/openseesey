"""Dr. Strange-style sparks, portal burst, and idle orbit dots."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

COLORS = (
    QColor(255, 215, 0),
    QColor(255, 165, 0),
    QColor(255, 120, 30),
    QColor(255, 200, 80),
    QColor(255, 255, 220),
)


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: QColor

    @property
    def alive(self) -> bool:
        return self.life > 0

    def tick(self) -> None:
        self.life -= 1
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.96
        self.vy *= 0.96
        self.vy += 0.02


class SparkEngine:
    """Particle pool, one-shot portal burst, and idle orbit sparkle."""

    def __init__(self, max_particles: int = 1200) -> None:
        self.particles: list[Particle] = []
        self.max_particles = max_particles
        self._mandala_angle = 0.0
        self._cursor = QPointF()
        self._cursor_active = False
        self._last_spawn = QPointF()
        self._has_last_spawn = False
        self._burst_origin = QPointF()
        self._burst_start = 0.0
        self._burst_duration = 0.52
        self._burst_active = False
        self._burst_done = False
        self._idle_angle = 0.0

    def set_cursor(self, pos: QPointF, active: bool = True) -> None:
        self._cursor = pos
        self._cursor_active = active

    def trigger_portal_burst(self, x: float, y: float) -> None:
        self._burst_origin = QPointF(x, y)
        self._burst_start = time.monotonic()
        self._burst_active = True
        self._burst_done = False
        for i in range(28):
            angle = (math.tau / 28) * i + random.uniform(-0.1, 0.1)
            speed = random.uniform(2.5, 7.0)
            life = random.uniform(28, 48)
            self._spawn_particle(
                x + math.cos(angle) * 4,
                y + math.sin(angle) * 4,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                life,
                random.uniform(2.5, 5.5),
            )

    @property
    def burst_done(self) -> bool:
        return self._burst_done

    def spawn_at(
        self,
        x: float,
        y: float,
        dx: float = 0.0,
        dy: float = 0.0,
        count: int = 14,
    ) -> None:
        speed = math.hypot(dx, dy)
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            spread = random.uniform(0.5, 2.8) + speed * 0.08
            vx = math.cos(angle) * spread - dx * 0.06
            vy = math.sin(angle) * spread - dy * 0.06
            life = random.uniform(35, 75)
            self._spawn_particle(
                x + random.uniform(-4, 4),
                y + random.uniform(-4, 4),
                vx,
                vy,
                life,
                random.uniform(2.0, 5.0),
            )

    def _spawn_particle(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        life: float,
        size: float,
    ) -> None:
        if len(self.particles) >= self.max_particles:
            self.particles.pop(0)
        self.particles.append(
            Particle(
                x=x,
                y=y,
                vx=vx,
                vy=vy,
                life=life,
                max_life=life,
                size=size,
                color=QColor(random.choice(COLORS)),
            )
        )

    def spawn_trail(self, x: float, y: float) -> None:
        if self._has_last_spawn:
            dx = x - self._last_spawn.x()
            dy = y - self._last_spawn.y()
            dist = math.hypot(dx, dy)
            steps = max(1, int(dist / 6))
            for i in range(steps):
                t = i / steps
                self.spawn_at(
                    self._last_spawn.x() + dx * t,
                    self._last_spawn.y() + dy * t,
                    dx,
                    dy,
                    count=max(4, 12 - i),
                )
        else:
            self.spawn_at(x, y, count=12)

        self._last_spawn = QPointF(x, y)
        self._has_last_spawn = True

    def clear_trail_anchor(self) -> None:
        self._has_last_spawn = False

    def tick(self) -> None:
        if self._burst_active:
            elapsed = time.monotonic() - self._burst_start
            if elapsed >= self._burst_duration:
                self._burst_active = False
                self._burst_done = True

        self._mandala_angle += 0.045
        self._idle_angle += 0.035
        self.particles = [p for p in self.particles if p.alive]
        for p in self.particles:
            p.tick()

    def draw(self, painter: QPainter) -> None:
        if self._burst_active:
            self._draw_burst(painter)

        if self._cursor_active and self._burst_done:
            self._draw_idle_sparkle(painter, self._cursor)
        elif self._cursor_active and not self._burst_active and not self._burst_done:
            self._draw_mandala_glow(painter, self._cursor)

        painter.setPen(Qt.PenStyle.NoPen)
        for p in self.particles:
            ratio = max(0.0, min(1.0, p.life / max(0.001, p.max_life)))
            alpha = int(255 * (ratio ** 1.4))
            color = QColor(p.color)
            color.setAlpha(alpha)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)

    def _draw_burst(self, painter: QPainter) -> None:
        elapsed = time.monotonic() - self._burst_start
        t = min(1.0, elapsed / self._burst_duration)
        cx, cy = self._burst_origin.x(), self._burst_origin.y()
        radius = 12 + t * 90
        alpha = int(220 * (1.0 - t ** 1.6))

        for ring_t, width in ((0.55, 4.0), (0.85, 2.5), (1.0, 1.5)):
            r = radius * ring_t
            pen = QPen(QColor(255, 200, 50, max(0, int(alpha * (1.1 - ring_t)))), width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), r, r)

        segments = 12
        for s in range(segments):
            angle = (math.tau / segments) * s + t * math.tau * 0.8
            dist = radius * 0.75
            dot_x = cx + math.cos(angle) * dist
            dot_y = cy + math.sin(angle) * dist
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 240, 180, max(0, alpha)))
            painter.drawEllipse(QPointF(dot_x, dot_y), 3.5, 3.5)

    def _draw_idle_sparkle(self, painter: QPainter, center: QPointF) -> None:
        cx, cy = center.x(), center.y()
        for i in range(6):
            angle = self._idle_angle + (math.tau / 6) * i
            orbit = 28 + (i % 2) * 6
            dot_x = cx + math.cos(angle) * orbit
            dot_y = cy + math.sin(angle) * orbit
            alpha = 140 + int(60 * math.sin(self._idle_angle * 2 + i))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 210, 80, alpha))
            painter.drawEllipse(QPointF(dot_x, dot_y), 2.5, 2.5)

        glow = QColor(255, 150, 30, 35)
        painter.setBrush(glow)
        painter.drawEllipse(center, 22, 22)

    def _draw_mandala_glow(self, painter: QPainter, center: QPointF) -> None:
        cx, cy = center.x(), center.y()

        for radius, alpha in ((52, 18), (40, 28), (28, 40)):
            glow = QColor(255, 140, 20, alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

        painter.setPen(Qt.PenStyle.NoPen)
        for ring_i, radius in enumerate((30, 22)):
            segments = 8 + ring_i * 4
            for s in range(segments):
                if s % 2 == 0:
                    continue
                a0 = self._mandala_angle + (math.tau / segments) * s
                a1 = a0 + math.tau / segments * 0.55
                pen = QPen(QColor(255, 200, 60, 140 - ring_i * 25), 2 - ring_i * 0.3)
                painter.setPen(pen)
                start_deg = math.degrees(a0)
                span_deg = math.degrees(a1 - a0)
                painter.drawArc(
                    int(cx - radius),
                    int(cy - radius),
                    int(radius * 2),
                    int(radius * 2),
                    int(start_deg * 16),
                    int(span_deg * 16),
                )

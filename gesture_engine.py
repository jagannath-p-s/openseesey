"""Pure circle gesture detection — no Qt, no I/O."""

from __future__ import annotations

import math

import audit
from state import GestureResult


def analyze_circle(points: list[tuple[float, float]]) -> GestureResult:
    n = len(points)
    if n < 12:
        return _reject(n, "Too few points (<12)")

    length = 0.0
    for i in range(n - 1):
        dx = points[i + 1][0] - points[i][0]
        dy = points[i + 1][1] - points[i][1]
        length += math.hypot(dx, dy)
    if length < 60.0:
        return _reject(n, f"Stroke too short ({length:.0f}px)")

    closure = math.hypot(points[-1][0] - points[0][0], points[-1][1] - points[0][1])
    if closure > max(160.0, length * 0.65):
        return _reject(n, "Loop not closed")

    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    radii = [math.hypot(p[0] - cx, p[1] - cy) for p in points]
    radius = sum(radii) / n
    if radius < 15.0:
        return _reject(n, "Circle too small")

    variance = sum((r - radius) ** 2 for r in radii) / n
    cv = math.sqrt(variance) / radius
    if cv > 0.52:
        return _partial(cx, cy, radius, cv, n, points, f"Variance too high (CV={cv:.2f})")

    angle = 0.0
    for i in range(n - 2):
        v1x = points[i + 1][0] - points[i][0]
        v1y = points[i + 1][1] - points[i][1]
        v2x = points[i + 2][0] - points[i + 1][0]
        v2y = points[i + 2][1] - points[i + 1][1]
        l1, l2 = math.hypot(v1x, v1y), math.hypot(v2x, v2y)
        if l1 > 1e-3 and l2 > 1e-3:
            angle += math.atan2(v1x * v2y - v1y * v2x, v1x * v2x + v1y * v2y)

    abs_angle = abs(angle)
    if abs_angle < 3.0 or abs_angle > 25.0:
        return _partial(
            cx, cy, radius, cv, n, points,
            f"Turn angle out of range ({math.degrees(abs_angle):.0f}°)",
        )

    audit.log_debug(
        "GESTURE",
        f"ACCEPTED centroid=({cx:.1f},{cy:.1f}) r={radius:.1f} cv={cv:.2f} pts={n}",
    )
    return GestureResult(
        is_circle=True,
        centroid_x=cx,
        centroid_y=cy,
        radius=radius,
        coverage_variance=cv,
        points_count=n,
        stroke_points=list(points),
        reason="ok",
    )


def _reject(n: int, reason: str) -> GestureResult:
    audit.log_debug("GESTURE", f"REJECTED {reason} pts={n}")
    return GestureResult(is_circle=False, points_count=n, reason=reason)


def _partial(
    cx: float, cy: float, radius: float, cv: float, n: int,
    points: list[tuple[float, float]], reason: str,
) -> GestureResult:
    audit.log_debug("GESTURE", f"REJECTED {reason}")
    return GestureResult(
        is_circle=False,
        centroid_x=cx,
        centroid_y=cy,
        radius=radius,
        coverage_variance=cv,
        points_count=n,
        stroke_points=list(points),
        reason=reason,
    )

"""Pure hit-testing: circle gesture vs icon rects."""

from __future__ import annotations

import math

import audit
from state import GestureResult, HitResult, IconInfo, MoveRingHit, SlingIconHit

PAD = 8.0
MIN_STROKE = 3


def _circle_hits_rect(
    cx: float, cy: float, radius: float,
    left: float, top: float, right: float, bottom: float,
) -> bool:
    closest_x = max(left, min(cx, right))
    closest_y = max(top, min(cy, bottom))
    return math.hypot(cx - closest_x, cy - closest_y) <= radius


def _icon_center(icon: IconInfo) -> tuple[float, float]:
    return icon.screen_x + icon.width / 2, icon.screen_y + icon.height / 2


def resolve_hit(gesture: GestureResult, icons: list[IconInfo]) -> HitResult:
    cx, cy = gesture.centroid_x, gesture.centroid_y
    stroke = gesture.stroke_points

    audit.log_debug(
        "HITTEST",
        f"centroid=({cx:.1f},{cy:.1f}) r={gesture.radius:.1f} icons={len(icons)}",
    )

    touched: list[tuple[float, bool, int, IconInfo]] = []

    for icon in icons:
        left = icon.screen_x - PAD
        top = icon.screen_y - PAD
        right = icon.screen_x + icon.width + PAD
        bottom = icon.screen_y + icon.height + PAD
        icx, icy = _icon_center(icon)
        dist = math.hypot(cx - icx, cy - icy)

        stroke_hits = sum(1 for px, py in stroke if left <= px <= right and top <= py <= bottom)
        centroid_on = left <= cx <= right and top <= cy <= bottom
        circle_overlaps = _circle_hits_rect(cx, cy, gesture.radius, left, top, right, bottom)

        if stroke_hits < MIN_STROKE and not centroid_on and not circle_overlaps:
            audit.log_debug("HITTEST", f"  '{icon.name}' MISS dist={dist:.0f}")
            continue

        touched.append((dist, centroid_on, stroke_hits, icon))
        audit.log_debug(
            "HITTEST",
            f"  '{icon.name}' rect=({icon.screen_x:.0f},{icon.screen_y:.0f}) "
            f"dist={dist:.0f} stroke={stroke_hits} on={centroid_on} overlap={circle_overlaps}",
        )

    if not touched:
        audit.log_debug("HITTEST", "WINNER empty space")
        return MoveRingHit(target_x=cx, target_y=cy)

    # Prefer icon under the circle center; break ties by nearest center.
    on_centroid = [t for t in touched if t[1]]
    pool = on_centroid if on_centroid else touched
    dist, _, stroke_hits, best = min(pool, key=lambda t: (t[0], -t[1], -t[2]))

    audit.log_debug(
        "HITTEST",
        f"WINNER '{best.name}' dist={dist:.1f} on_centroid={bool(on_centroid)} stroke={stroke_hits}",
    )
    return SlingIconHit(
        path=best.path,
        name=best.name,
        screen_x=best.screen_x,
        screen_y=best.screen_y,
        width=best.width,
        height=best.height,
    )

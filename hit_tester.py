"""Pure hit-testing: circle gesture vs icon rects."""

from __future__ import annotations

import math

import audit
from state import GestureResult, HitResult, IconInfo, MoveRingHit, SlingIconHit

PAD = 12.0
MIN_SCORE = 50.0


def resolve_hit(gesture: GestureResult, icons: list[IconInfo]) -> HitResult:
    cx, cy = gesture.centroid_x, gesture.centroid_y
    stroke = gesture.stroke_points
    half_diag = math.hypot(76 / 2, 91 / 2)

    audit.log_debug(
        "HITTEST",
        f"centroid=({cx:.1f},{cy:.1f}) r={gesture.radius:.1f} icons={len(icons)}",
    )

    best: IconInfo | None = None
    best_score = -1.0

    for icon in icons:
        left = icon.screen_x - PAD
        top = icon.screen_y - PAD
        right = icon.screen_x + icon.width + PAD
        bottom = icon.screen_y + icon.height + PAD
        icx = icon.screen_x + icon.width / 2
        icy = icon.screen_y + icon.height / 2
        dist = math.hypot(cx - icx, cy - icy)

        stroke_hits = sum(1 for px, py in stroke if left <= px <= right and top <= py <= bottom)
        centroid_on = left <= cx <= right and top <= cy <= bottom
        circle_covers = dist <= gesture.radius + half_diag

        if stroke_hits == 0 and not centroid_on and not circle_covers:
            audit.log_debug("HITTEST", f"  '{icon.name}' MISS dist={dist:.0f}")
            continue

        score = stroke_hits * 200 + (100 if centroid_on else 0) + (60 if circle_covers else 0) - dist * 0.3
        audit.log_debug(
            "HITTEST",
            f"  '{icon.name}' rect=({icon.screen_x:.0f},{icon.screen_y:.0f}) "
            f"dist={dist:.0f} stroke={stroke_hits} on={centroid_on} covers={circle_covers} "
            f"score={score:.1f}",
        )
        if score > best_score:
            best_score = score
            best = icon

    if best is not None and best_score >= MIN_SCORE:
        audit.log_debug("HITTEST", f"WINNER '{best.name}' score={best_score:.1f}")
        return SlingIconHit(
            path=best.path,
            name=best.name,
            screen_x=best.screen_x,
            screen_y=best.screen_y,
            width=best.width,
            height=best.height,
        )

    audit.log_debug("HITTEST", "WINNER empty space (move ring)")
    return MoveRingHit(target_x=cx, target_y=cy)

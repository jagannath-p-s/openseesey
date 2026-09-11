"""Shared dataclasses and ring persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

CONFIG_DIR = Path.home() / ".config" / "opensesame"
STATE_FILE = CONFIG_DIR / "state.json"

DEFAULT_RING = (120, 120)
ICON_W = 76.0
ICON_H = 91.0


@dataclass(frozen=True)
class IconInfo:
    path: str
    name: str
    gio_x: float
    gio_y: float
    screen_x: float
    screen_y: float
    width: float = ICON_W
    height: float = ICON_H


@dataclass
class GestureResult:
    is_circle: bool
    centroid_x: float = 0.0
    centroid_y: float = 0.0
    radius: float = 0.0
    coverage_variance: float = 0.0
    points_count: int = 0
    stroke_points: list[tuple[float, float]] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class SlingIconHit:
    kind: Literal["sling"] = "sling"
    path: str = ""
    name: str = ""
    screen_x: float = 0.0
    screen_y: float = 0.0
    width: float = ICON_W
    height: float = ICON_H


@dataclass(frozen=True)
class MoveRingHit:
    kind: Literal["move_ring"] = "move_ring"
    target_x: float = 0.0
    target_y: float = 0.0


HitResult = SlingIconHit | MoveRingHit


def _load() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        with STATE_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_ring_pos() -> tuple[int, int]:
    pos = _load().get("ring_pos", {})
    return int(pos.get("x", DEFAULT_RING[0])), int(pos.get("y", DEFAULT_RING[1]))


def set_ring_pos(x: int, y: int) -> None:
    data = _load()
    data["ring_pos"] = {"x": int(x), "y": int(y)}
    _save(data)

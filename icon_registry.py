"""Desktop icon registry — GIO positions, AT-SPI calibration, DING reload."""

from __future__ import annotations

import configparser
import json
import math
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import audit
from desktop_watch import start_desktop_watch
from state import ICON_H, ICON_W, IconInfo

DESKTOP = Path.home() / "Desktop"
CALIB_CACHE = Path.home() / ".config" / "opensesame" / "calib.json"
_GIO = shutil.which("gio") or "gio"
_GNOME_EXT = shutil.which("gnome-extensions") or "gnome-extensions"
_DING_UUID = "ding@rastersoft.com"

GRID_ORIGIN_X = 2
GRID_ORIGIN_Y = 31
GRID_COL_STEP = 80
GRID_ROW_STEP = 95
_ATSPI_SUFFIXES = (
    " Application Selected", " Application",
    " Folder Selected", " Folder",
    " File Selected", " File",
    " Selected",
)

_ATSPI_SCRIPT = r"""
import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi
Atspi.init()
desktop = Atspi.get_desktop(0)
for i in range(desktop.get_child_count()):
    app = desktop.get_child_at_index(i)
    if not app or app.get_name() != 'gjs':
        continue
    for j in range(app.get_child_count()):
        frame = app.get_child_at_index(j)
        if not frame or 'Desktop Icons' not in (frame.get_name() or ''):
            continue
        panel = frame.get_child_at_index(0)
        if not panel:
            continue
        inner = panel.get_child_at_index(0)
        if not inner:
            continue
        for k in range(inner.get_child_count()):
            child = inner.get_child_at_index(k)
            if not child:
                continue
            try:
                if child.get_role_name() != 'filler':
                    continue
                raw = child.get_name() or ''
                ext = child.get_extents(Atspi.CoordType.SCREEN)
                if raw and ext.width > 0:
                    print(f'ICON|{raw}|{ext.x}|{ext.y}|{ext.width}|{ext.height}')
            except Exception:
                pass
"""

_lock = threading.Lock()
_registry: dict[str, IconInfo] = {}
_atspi_rects: dict[str, tuple[float, float, float, float]] = {}
_cal_dx = 0.0
_cal_dy = 0.0
_ready = False
_calibration_ready = False
_listeners: list[Callable[[], None]] = []
_ready_listeners: list[Callable[[], None]] = []
_restore_lock = threading.Lock()
_ding_ext_id: str | None = None


def ding_extension_id() -> str:
    """Resolve installed DING extension UUID (fallback to packaged default)."""
    try:
        r = subprocess.run(
            [_GNOME_EXT, "list"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if "ding" in line.lower():
                    return line.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return _DING_UUID


def _cached_ding_id() -> str:
    global _ding_ext_id
    if _ding_ext_id is None:
        _ding_ext_id = ding_extension_id()
    return _ding_ext_id


def reload_ding() -> bool:
    """Force DING full reload — only reliable path for metadata placement."""
    ext_id = _cached_ding_id()
    audit.log_debug("DING", f"reload start id={ext_id}")
    try:
        r_disable = subprocess.run(
            [_GNOME_EXT, "disable", ext_id],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        time.sleep(0.08)
        r_enable = subprocess.run(
            [_GNOME_EXT, "enable", ext_id],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        ok = r_disable.returncode == 0 and r_enable.returncode == 0
        audit.log_debug(
            "DING",
            f"reload done ok={ok} disable={r_disable.returncode} enable={r_enable.returncode}",
        )
        if not ok:
            audit.log_debug(
                "DING",
                f"reload stderr disable={r_disable.stderr.strip()} enable={r_enable.stderr.strip()}",
            )
        return ok
    except (OSError, subprocess.TimeoutExpired) as err:
        audit.log_debug("DING", f"reload error: {err}")
        return False


def _count_visible_icons() -> int:
    """Fast count of non-hidden desktop entries (DING shows one icon per entry)."""
    hidden = _hidden_filenames()
    return sum(
        1 for entry in DESKTOP.iterdir()
        if not entry.name.startswith(".") and entry.name not in hidden
    )


_atspi_works: bool | None = None


def _atspi_available() -> bool:
    global _atspi_works
    if _atspi_works is not None:
        return _atspi_works
    try:
        r = subprocess.run(
            ["/usr/bin/python3", "-c", _ATSPI_SCRIPT],
            capture_output=True, text=True, timeout=2, check=False,
        )
        _atspi_works = r.returncode == 0 and bool(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        _atspi_works = False
    if not _atspi_works:
        audit.log_debug("DING", "AT-SPI unavailable — using gio scan for ready checks")
    return _atspi_works


def wait_for_ding_ready(
    timeout_s: float = 2.5,
    min_icons: int = 1,
    *,
    fast: bool = False,
) -> bool:
    """Poll until DING has repainted — file count only (registry rebuilt separately)."""
    deadline = time.monotonic() + timeout_s
    time.sleep(0.04)
    while time.monotonic() < deadline:
        gio_count = _count_visible_icons()
        if gio_count >= min_icons:
            audit.log_debug("DING", f"ready via gio scan icons={gio_count} min={min_icons}")
            return True

        if not fast and _atspi_available():
            atspi = _run_atspi()
            if len(atspi) >= min_icons:
                global _atspi_rects
                _atspi_rects = atspi
                audit.log_debug("DING", f"ready icons={len(atspi)} min={min_icons}")
                return True

        time.sleep(0.03)

    audit.log_debug("DING", f"wait timeout min_icons={min_icons}")
    return False


def _hidden_filenames() -> set[str]:
    hidden_file = DESKTOP / ".hidden"
    if not hidden_file.is_file():
        return set()
    return {line.strip() for line in hidden_file.read_text(encoding="utf-8").splitlines() if line.strip()}


def _notify() -> None:
    for cb in _listeners:
        try:
            cb()
        except Exception:
            pass


def _notify_ready() -> None:
    global _ready
    _ready = True
    for cb in _ready_listeners:
        try:
            cb()
        except Exception:
            pass


def on_updated(callback: Callable[[], None]) -> None:
    _listeners.append(callback)


def on_ready(callback: Callable[[], None]) -> None:
    _ready_listeners.append(callback)
    if _ready:
        callback()


def is_ready() -> bool:
    return _ready


def calibration_ready() -> bool:
    return _calibration_ready


def restore_guard() -> threading.Lock:
    """Held during stash→desktop restore so file-monitor events don't race placement."""
    return _restore_lock


def refresh_after_hidden_change() -> None:
    _rebuild_registry()
    _notify()


def rescan_desktop() -> None:
    _rebuild_registry()


def remove_icon(path: str) -> None:
    with _lock:
        _registry.pop(path, None)


def upsert_icon(path: Path, gio_x: int, gio_y: int) -> None:
    info = _icon_from_path(path, (float(gio_x), float(gio_y)))
    with _lock:
        _registry[info.path] = info
    _notify()


def gio_to_screen(gx: float, gy: float, w: float = ICON_W, h: float = ICON_H) -> tuple[float, float, float, float]:
    return gx + _cal_dx, gy + _cal_dy, w, h


def screen_to_gio(sx: float, sy: float) -> tuple[int, int]:
    return int(round(sx - _cal_dx)), int(round(sy - _cal_dy))


def _strip_atspi(name: str) -> str:
    for suffix in _ATSPI_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _display_name(path: Path) -> str:
    if path.suffix == ".desktop":
        try:
            cp = configparser.ConfigParser()
            cp.read(path, encoding="utf-8")
            return cp.get("Desktop Entry", "Name", fallback=path.stem)
        except (configparser.Error, OSError):
            pass
    return path.name


def _scan_paths() -> list[Path]:
    if not DESKTOP.is_dir():
        return []
    hidden = _hidden_filenames()
    out: list[Path] = []
    for entry in sorted(DESKTOP.iterdir()):
        if entry.name.startswith(".") or entry.name in hidden:
            continue
        out.append(entry)
    return out


def _read_gio(path: Path) -> tuple[float, float] | None:
    try:
        r = subprocess.run(
            [_GIO, "info", "-a", "metadata::nautilus-icon-position", str(path)],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if r.returncode != 0:
            return None
        m = re.search(r"nautilus-icon-position:\s*(-?\d+),\s*(-?\d+)", r.stdout)
        if not m:
            return None
        return float(m.group(1)), float(m.group(2))
    except (OSError, subprocess.TimeoutExpired):
        return None


def _run_atspi() -> dict[str, tuple[float, float, float, float]]:
    try:
        r = subprocess.run(
            ["/usr/bin/python3", "-c", _ATSPI_SCRIPT],
            capture_output=True, text=True, timeout=8, check=False,
        )
        if r.returncode != 0:
            return {}
        out: dict[str, tuple[float, float, float, float]] = {}
        for line in r.stdout.splitlines():
            if not line.startswith("ICON|"):
                continue
            parts = line.split("|")
            if len(parts) < 6:
                continue
            name = _strip_atspi(parts[1])
            out[name] = (float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5]))
        return out
    except (OSError, subprocess.TimeoutExpired):
        return {}


def _match_atspi(name: str, basename: str, atspi: dict[str, tuple[float, float, float, float]]) -> tuple[float, float, float, float] | None:
    for key in (name, basename, basename.replace("_", " ")):
        if key in atspi:
            return atspi[key]
    for k, rect in atspi.items():
        if k == name or k == basename or basename in k or name in k:
            return rect
    return None


def _icon_from_path(path: Path, gio: tuple[float, float]) -> IconInfo:
    gx, gy = gio
    name = _display_name(path)
    sx, sy, w, h = gio_to_screen(gx, gy)
    return IconInfo(
        path=str(path),
        name=name,
        gio_x=gx,
        gio_y=gy,
        screen_x=sx,
        screen_y=sy,
        width=w,
        height=h,
    )


def _rebuild_registry(log: bool = False) -> None:
    global _registry
    hidden = _hidden_filenames()
    paths = [p for p in _scan_paths() if p.name not in hidden]
    new: dict[str, IconInfo] = {}

    def read_one(path: Path) -> tuple[str, IconInfo] | None:
        gio = _read_gio(path)
        if gio is None:
            return None
        info = _icon_from_path(path, gio)
        return info.path, info

    workers = min(12, max(4, len(paths)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(read_one, paths, chunksize=1):
            if result is not None:
                path_str, info = result
                new[path_str] = info

    with _lock:
        _registry = new

    if log:
        lines = [f"GIO positions ({len(new)} icons), cal=({_cal_dx:.1f},{_cal_dy:.1f}):"]
        for info in sorted(new.values(), key=lambda i: (i.gio_y, i.gio_x)):
            lines.append(
                f"  gio=({info.gio_x:.0f},{info.gio_y:.0f}) "
                f"screen=({info.screen_x:.0f},{info.screen_y:.0f}) '{info.name}'"
            )
        audit.log_debug("GIO", "\n".join(lines))

    _notify()


def _load_calib_cache() -> tuple[float, float]:
    if not CALIB_CACHE.is_file():
        return 0.0, 0.0
    try:
        data = json.loads(CALIB_CACHE.read_text(encoding="utf-8"))
        return float(data.get("dx", 0.0)), float(data.get("dy", 0.0))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0.0, 0.0


def _save_calib_cache() -> None:
    try:
        CALIB_CACHE.parent.mkdir(parents=True, exist_ok=True)
        CALIB_CACHE.write_text(
            json.dumps({"dx": _cal_dx, "dy": _cal_dy}, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _calibrate() -> None:
    global _cal_dx, _cal_dy, _atspi_rects, _calibration_ready, _atspi_works

    audit.log_debug("CALIB", f"refining offset (cached {_cal_dx:.1f},{_cal_dy:.1f})")

    atspi = _run_atspi()
    _atspi_rects = atspi
    _atspi_works = bool(atspi)
    if not atspi:
        audit.log_debug("CALIB", "AT-SPI unavailable — keeping cached offset")
        _rebuild_registry(log=True)
        _calibration_ready = True
        audit.log_debug("CALIB", "calibration_ready=True")
        return

    offsets: list[tuple[float, float]] = []
    for path in _scan_paths():
        gio = _read_gio(path)
        if gio is None:
            continue
        name = _display_name(path)
        rect = _match_atspi(name, path.name, atspi)
        if rect:
            offsets.append((rect[0] - gio[0], rect[1] - gio[1]))

    if offsets:
        _cal_dx = sum(o[0] for o in offsets) / len(offsets)
        _cal_dy = sum(o[1] for o in offsets) / len(offsets)
        _save_calib_cache()
        audit.log_debug(
            "CALIB",
            f"refined offset=({_cal_dx:.1f},{_cal_dy:.1f}) pairs={len(offsets)}",
        )
    else:
        audit.log_debug("CALIB", "no matched pairs — keeping cached offset")

    _rebuild_registry(log=True)
    _calibration_ready = True
    audit.log_debug("CALIB", "calibration_ready=True")


def _on_file_changed(file_path: str) -> None:
    if _restore_lock.locked():
        return

    path = Path(file_path)
    if path.name in _hidden_filenames():
        with _lock:
            _registry.pop(str(path), None)
        _notify()
        return

    if not path.exists():
        with _lock:
            _registry.pop(str(path), None)
        _notify()
        return

    gio = _read_gio(path)
    if gio is None:
        return

    gx, gy = gio
    name = _display_name(path)
    sx, sy, w, h = gio_to_screen(gx, gy)

    info = IconInfo(
        path=str(path), name=name, gio_x=gx, gio_y=gy,
        screen_x=sx, screen_y=sy, width=w, height=h,
    )
    with _lock:
        _registry[str(path)] = info
    audit.log_debug(
        "GIO",
        f"updated '{name}' gio=({gx:.0f},{gy:.0f}) screen=({sx:.0f},{sy:.0f}) "
        f"cal=({_cal_dx:.1f},{_cal_dy:.1f})",
    )
    _notify()


def _dedupe(icons: list[IconInfo]) -> list[IconInfo]:
    cells: dict[tuple[int, int], IconInfo] = {}
    for icon in icons:
        col = round((icon.gio_x - GRID_ORIGIN_X) / GRID_COL_STEP)
        row = round((icon.gio_y - GRID_ORIGIN_Y) / GRID_ROW_STEP)
        key = (col, row)
        prev = cells.get(key)
        if prev is None:
            cells[key] = icon
            continue
        if icon.path.endswith(".desktop") and not prev.path.endswith(".desktop"):
            cells[key] = icon
        elif prev.path.endswith(".desktop") and not icon.path.endswith(".desktop"):
            pass
        elif len(icon.path) < len(prev.path):
            cells[key] = icon
    return list(cells.values())


def current_icons() -> list[IconInfo]:
    hidden = _hidden_filenames()
    with _lock:
        icons = [
            i for i in _registry.values()
            if Path(i.path).name not in hidden and not is_offscreen(i)
        ]
    return _dedupe(icons)


def get_gio_position(path: str, *, live: bool = False) -> tuple[int, int] | None:
    if live:
        gio = _read_gio(Path(path))
        if gio is None:
            return None
        return int(gio[0]), int(gio[1])

    with _lock:
        info = _registry.get(path)
    if info is None:
        gio = _read_gio(Path(path))
        if gio is None:
            return None
        return int(gio[0]), int(gio[1])
    return int(info.gio_x), int(info.gio_y)


def gio_move(src: Path | str, dst: Path | str) -> bool:
    try:
        r = subprocess.run(
            [_GIO, "move", str(src), str(dst)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if r.returncode != 0:
            audit.log_debug("GIO", f"move failed {src} -> {dst}: {r.stderr.strip()}")
            return False
        return True
    except (OSError, subprocess.TimeoutExpired) as err:
        audit.log_debug("GIO", f"move error {src} -> {dst}: {err}")
        return False


def set_icon_position(path: str, gio_x: int, gio_y: int) -> bool:
    try:
        r = subprocess.run(
            [_GIO, "set", path, "metadata::nautilus-icon-position", f"{gio_x},{gio_y}"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if r.returncode != 0:
            audit.log_debug("GIO", f"set failed path={path} pos={gio_x},{gio_y} err={r.stderr.strip()}")
            return False
        with _lock:
            info = _registry.get(path)
            if info:
                sx, sy, w, h = gio_to_screen(float(gio_x), float(gio_y))
                _registry[path] = IconInfo(
                    path=info.path,
                    name=info.name,
                    gio_x=float(gio_x),
                    gio_y=float(gio_y),
                    screen_x=sx,
                    screen_y=sy,
                    width=w,
                    height=h,
                )
        _notify()
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def set_icon_position_and_wait(path: str, gio_x: int, gio_y: int) -> tuple[bool, tuple[int, int] | None]:
    """Write gio position and confirm metadata via live re-read (pre-reload check)."""
    if not set_icon_position(path, gio_x, gio_y):
        return False, None
    confirmed = get_gio_position(path, live=True)
    if confirmed:
        sx, sy, _, _ = gio_to_screen(float(confirmed[0]), float(confirmed[1]))
        audit.log_debug(
            "GIO",
            f"metadata path={Path(path).name} intended=({gio_x},{gio_y}) "
            f"read={confirmed} screen=({sx:.0f},{sy:.0f}) cal=({_cal_dx:.1f},{_cal_dy:.1f})",
        )
    meta_ok = confirmed == (gio_x, gio_y)
    return meta_ok, confirmed


_OFFSCREEN_MIN = 50000


def is_offscreen(icon: IconInfo) -> bool:
    return int(icon.gio_x) >= _OFFSCREEN_MIN or int(icon.gio_y) >= _OFFSCREEN_MIN


def cell_from_gio(x: float, y: float) -> tuple[int, int]:
    col = round((x - GRID_ORIGIN_X) / GRID_COL_STEP)
    row = round((y - GRID_ORIGIN_Y) / GRID_ROW_STEP)
    return col, row


def gio_for_cell(col: int, row: int) -> tuple[int, int]:
    return GRID_ORIGIN_X + col * GRID_COL_STEP, GRID_ORIGIN_Y + row * GRID_ROW_STEP


def occupied_cells(exclude_path: str = "") -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for icon in current_icons():
        if icon.path == exclude_path:
            continue
        cells.add(cell_from_gio(icon.gio_x, icon.gio_y))
    return cells


def _snap_to_free_cell(naive_x: int, naive_y: int, exclude_path: str) -> tuple[int, int]:
    col = round((naive_x - GRID_ORIGIN_X) / GRID_COL_STEP)
    row = round((naive_y - GRID_ORIGIN_Y) / GRID_ROW_STEP)
    taken = occupied_cells(exclude_path)

    if (col, row) not in taken:
        return gio_for_cell(col, row)

    best = None
    best_dist = float("inf")
    for radius in range(1, 12):
        for dc in range(-radius, radius + 1):
            for dr in range(-radius, radius + 1):
                if abs(dc) != radius and abs(dr) != radius:
                    continue
                c, r = col + dc, row + dr
                if (c, r) in taken:
                    continue
                gx, gy = gio_for_cell(c, r)
                dist = (gx - naive_x) ** 2 + (gy - naive_y) ** 2
                if dist < best_dist:
                    best_dist = dist
                    best = (gx, gy)
        if best is not None:
            return best
    return naive_x, naive_y


def resolve_target_gio(
    portal_cx: float,
    portal_cy: float,
    icon_w: float,
    icon_h: float,
    exclude_path: str,
) -> tuple[int, int]:
    """Pick the free grid cell whose icon center lands closest to the portal."""
    top_left_sx = portal_cx - icon_w / 2
    top_left_sy = portal_cy - icon_h / 2
    naive_gx, naive_gy = screen_to_gio(top_left_sx, top_left_sy)
    naive_col, naive_row = cell_from_gio(float(naive_gx), float(naive_gy))
    taken = occupied_cells(exclude_path)

    best: tuple[int, int] | None = None
    best_dist = float("inf")
    for radius in range(0, 10):
        for dc in range(-radius, radius + 1):
            for dr in range(-radius, radius + 1):
                if radius > 0 and abs(dc) != radius and abs(dr) != radius:
                    continue
                c, r = naive_col + dc, naive_row + dr
                if (c, r) in taken:
                    continue
                gx, gy = gio_for_cell(c, r)
                sx, sy, _, _ = gio_to_screen(float(gx), float(gy))
                icx = sx + icon_w / 2
                icy = sy + icon_h / 2
                dist = math.hypot(portal_cx - icx, portal_cy - icy)
                if dist < best_dist:
                    best_dist = dist
                    best = (gx, gy)

    if best is None:
        best = _snap_to_free_cell(naive_gx, naive_gy, exclude_path)

    audit.log_debug(
        "GIO",
        f"portal=({portal_cx:.0f},{portal_cy:.0f}) gio={best[0]},{best[1]} "
        f"center_dist={best_dist:.0f} cal=({_cal_dx:.1f},{_cal_dy:.1f})",
    )
    return best


def _prefetch_gio() -> None:
    paths = _scan_paths()

    def read_one(p: Path) -> tuple[str, tuple[float, float] | None]:
        return str(p), _read_gio(p)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(read_one, p): p for p in paths}
        for fut in as_completed(futures):
            path_str, gio = fut.result()
            if gio is None:
                continue
            gx, gy = gio
            name = _display_name(Path(path_str))
            sx, sy, w, h = gio_to_screen(gx, gy)
            with _lock:
                _registry[path_str] = IconInfo(
                    path=path_str, name=name, gio_x=gx, gio_y=gy,
                    screen_x=sx, screen_y=sy, width=w, height=h,
                )
    _notify()


def start() -> None:
    global _cal_dx, _cal_dy

    audit.log_debug("DING", "icon_registry starting")
    _cal_dx, _cal_dy = _load_calib_cache()
    _prefetch_gio()
    _rebuild_registry()
    start_desktop_watch(_on_file_changed)
    _notify_ready()
    audit.log_debug("CALIB", f"ready with cached offset=({_cal_dx:.1f},{_cal_dy:.1f})")

    def run() -> None:
        try:
            _calibrate()
        except Exception as err:
            audit.log_debug("CALIB", f"background refine failed: {err}")
            global _calibration_ready
            _calibration_ready = True
        _notify()

    threading.Thread(target=run, name="atspi-calibrate", daemon=True).start()

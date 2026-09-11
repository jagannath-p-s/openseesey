"""Stash desktop icons off-desktop — gio move hide, DING reload only on restore."""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

import audit
import icon_registry
from state import ICON_H, ICON_W

DESKTOP = Path.home() / "Desktop"
DATA_DIR = Path.home() / ".local" / "share" / "opensesame"
STASH_DIR = DATA_DIR / "stash"
PERSIST_FILE = DATA_DIR / "hidden_by_app.json"
HIDDEN_FILE = DESKTOP / ".hidden"

_session: dict[str, dict] = {}
_hide_queue: deque[str] = deque()


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STASH_DIR.mkdir(parents=True, exist_ok=True)


def _save_persisted() -> None:
    _ensure_dirs()
    PERSIST_FILE.write_text(
        json.dumps({"entries": _session, "queue": list(_hide_queue)}, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_persisted() -> tuple[dict[str, dict], list[str]]:
    if not PERSIST_FILE.is_file():
        return {}, []
    try:
        data = json.loads(PERSIST_FILE.read_text(encoding="utf-8"))
        entries = data.get("entries", {})
        queue = data.get("queue", [])
        if isinstance(entries, dict) and isinstance(queue, list):
            return {str(k): v for k, v in entries.items()}, [str(x) for x in queue]
    except (OSError, json.JSONDecodeError):
        pass
    return {}, []


def _original_gio(info: dict) -> tuple[int, int] | None:
    gio = info.get("original_gio") or info.get("gio")
    if gio and len(gio) == 2:
        return int(gio[0]), int(gio[1])
    return None


def _read_hidden_lines() -> list[str]:
    if not HIDDEN_FILE.is_file():
        return []
    return [line.strip() for line in HIDDEN_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_hidden_lines(lines: list[str]) -> None:
    HIDDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    HIDDEN_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _remove_hidden(filename: str) -> None:
    lines = [name for name in _read_hidden_lines() if name != filename]
    _write_hidden_lines(lines)


def _remove_from_queue(filename: str) -> None:
    global _hide_queue
    _hide_queue = deque(name for name in _hide_queue if name != filename)


def _apply_ding_reload(min_icons: int | None = None) -> bool:
    expected = min_icons if min_icons is not None else max(1, len(icon_registry.current_icons()))
    if not icon_registry.reload_ding():
        return False
    icon_registry.wait_for_ding_ready(min_icons=expected)
    icon_registry.rescan_desktop()
    return True


def _rollback_to_stash(dst: Path, stash: Path) -> None:
    if dst.exists() and stash.parent.exists():
        icon_registry.gio_move(dst, stash)
    icon_registry.rescan_desktop()


def _ding_place(dst: Path, gio_x: int, gio_y: int, *, attempts: int = 2) -> tuple[int, int] | None:
    """Write metadata, reload DING, return live gio readback (retries on mismatch)."""
    final: tuple[int, int] | None = None
    for attempt in range(1, attempts + 1):
        icon_registry.set_icon_position(str(dst), gio_x, gio_y)
        expected = max(1, len(icon_registry.current_icons()))
        if not _apply_ding_reload(min_icons=expected):
            return None
        final = icon_registry.get_gio_position(str(dst), live=True)
        if final == (gio_x, gio_y):
            return final
        if attempt < attempts:
            audit.log_debug(
                "STASH",
                f"reload mismatch {dst.name} read={final} attempt={attempt}/{attempts} — retrying",
            )
    return final


def _restore_via_gio(
    stash: Path,
    dst: Path,
    gio_x: int,
    gio_y: int,
    *,
    portal_cx: float | None = None,
    portal_cy: float | None = None,
) -> bool:
    """Move to desktop, write metadata on desktop path, reload DING, verify."""
    with icon_registry.restore_guard():
        if not icon_registry.gio_move(stash, dst):
            return False

        # Overwrite stale xattr from the pre-stash desktop path before DING sees the file.
        icon_registry.set_icon_position(str(dst), gio_x, gio_y)
        final = _ding_place(dst, gio_x, gio_y)

        ok = final == (gio_x, gio_y)
        if final:
            sx, sy, _, _ = icon_registry.gio_to_screen(float(final[0]), float(final[1]))
            note = f"intended=({gio_x},{gio_y}) read={final} screen=({sx:.0f},{sy:.0f}) ok={ok}"
            if portal_cx is not None and portal_cy is not None:
                icx = sx + ICON_W / 2
                icy = sy + ICON_H / 2
                note += f" portal=({portal_cx:.0f},{portal_cy:.0f}) icon_center=({icx:.0f},{icy:.0f})"
            audit.log_debug("STASH", f"restored {dst.name} {note}")

        if not ok:
            _rollback_to_stash(dst, stash)
            return False
        return True


def hide_icon(desktop_dir: Path, filename: str) -> bool:
    """Move icon off-desktop into stash — DING drops it immediately, no reload."""
    if not icon_registry.calibration_ready():
        audit.log_action("STASH_DEFERRED", "reason=calibration_not_ready")
        return False

    src = desktop_dir / filename
    if not src.exists():
        audit.log_debug("STASH", f"hide skipped — not on desktop: {filename}")
        return False

    _ensure_dirs()
    stash_path = STASH_DIR / filename
    if stash_path.exists():
        stash_path = STASH_DIR / f"{filename}.{int(time.time())}"

    gio_pos = icon_registry.get_gio_position(str(src))
    if not icon_registry.gio_move(src, stash_path):
        audit.log_action("STASH_FAIL", f"name={filename} err=gio_move")
        return False

    if src.exists():
        audit.log_action("STASH_FAIL", f"name={filename} err=still_on_desktop")
        return False

    _remove_hidden(filename)

    existing = _session.get(filename)
    if existing is None:
        _session[filename] = {
            "stash": str(stash_path),
            "original_gio": list(gio_pos) if gio_pos else None,
            "last_portal_gio": None,
        }
    else:
        existing["stash"] = str(stash_path)
        if gio_pos:
            existing["original_gio"] = list(gio_pos)

    if filename not in _hide_queue:
        _hide_queue.append(filename)

    _save_persisted()
    icon_registry.rescan_desktop()
    audit.log_action("STASH_ICON", f"name={filename} stash={stash_path}")
    return True


def reveal_icon(
    desktop_dir: Path,
    filename: str,
    *,
    portal_cx: float | None = None,
    portal_cy: float | None = None,
    use_original: bool = False,
) -> bool:
    if not icon_registry.calibration_ready():
        audit.log_action("RESTORE_DEFERRED", "reason=calibration_not_ready")
        return False

    info = _session.get(filename)
    if info is None:
        return False

    stash = Path(info["stash"])
    dst = desktop_dir / filename
    if not stash.exists():
        audit.log_debug("STASH", f"stash missing for {filename}: {stash}")
        _session.pop(filename, None)
        _remove_from_queue(filename)
        _save_persisted()
        return False

    if dst.exists():
        audit.log_debug("STASH", f"restore blocked — already on desktop: {dst}")
        return False

    ok = False
    if portal_cx is not None and portal_cy is not None:
        gio_x, gio_y = icon_registry.resolve_target_gio(
            portal_cx, portal_cy, ICON_W, ICON_H, str(dst),
        )
        ok = _restore_via_gio(
            stash, dst, gio_x, gio_y, portal_cx=portal_cx, portal_cy=portal_cy,
        )
        if ok:
            info["last_portal_gio"] = [gio_x, gio_y]
    elif use_original:
        orig = _original_gio(info)
        if orig is None:
            if icon_registry.gio_move(stash, dst):
                ok = _apply_ding_reload()
        else:
            ok = _restore_via_gio(stash, dst, orig[0], orig[1])
    else:
        if icon_registry.gio_move(stash, dst):
            ok = _apply_ding_reload()

    if not ok:
        audit.log_action("RESTORE_FAIL", f"name={filename}")
        return False

    _session.pop(filename, None)
    _remove_from_queue(filename)
    _save_persisted()
    icon_registry.rescan_desktop()
    audit.log_action(
        "RESTORE_ICON",
        f"name={filename} portal=({portal_cx:.0f},{portal_cy:.0f})"
        if portal_cx is not None
        else f"name={filename} original=True",
    )
    return True


def reveal_all(desktop_dir: Path | None = None) -> None:
    desktop = desktop_dir or DESKTOP
    if not _hide_queue:
        return

    names = list(_hide_queue)
    restored = 0
    for filename in names:
        info = _session.get(filename)
        if info is None:
            continue
        stash = Path(info["stash"])
        dst = desktop / filename
        if not stash.exists() or dst.exists():
            continue
        orig = _original_gio(info)
        if not icon_registry.gio_move(stash, dst):
            continue
        time.sleep(0.05)
        if orig:
            icon_registry.set_icon_position(str(dst), orig[0], orig[1])
        _session.pop(filename, None)
        _remove_from_queue(filename)
        restored += 1

    if restored and _apply_ding_reload(min_icons=max(1, len(icon_registry.current_icons()))):
        _save_persisted()
        if not _hide_queue and PERSIST_FILE.is_file():
            PERSIST_FILE.unlink(missing_ok=True)
        icon_registry.rescan_desktop()

    audit.log_action("RESTORE_ALL", f"count={restored}")


def reveal_next_at(desktop_dir: Path, portal_cx: float, portal_cy: float) -> str | None:
    if not icon_registry.calibration_ready() or not _hide_queue:
        return None

    filename = _hide_queue[0]
    if not reveal_icon(desktop_dir, filename, portal_cx=portal_cx, portal_cy=portal_cy):
        return None

    if not _hide_queue and PERSIST_FILE.is_file():
        PERSIST_FILE.unlink(missing_ok=True)

    audit.log_action(
        "RESTORE_AT_PORTAL",
        f"name={filename} portal=({portal_cx:.0f},{portal_cy:.0f}) queue={len(_hide_queue)}",
    )
    return filename


def session_hidden() -> set[str]:
    return set(_hide_queue)


def recover_orphans(desktop_dir: Path | None = None) -> list[str]:
    global _session, _hide_queue
    desktop = desktop_dir or DESKTOP
    recovered: list[str] = []

    entries, queue = _load_persisted()
    _session.update(entries)
    for name in queue:
        if name not in _hide_queue:
            _hide_queue.append(name)

    for filename in _read_hidden_lines():
        _remove_hidden(filename)

    for filename, info in list(_session.items()):
        stash = Path(info.get("stash", STASH_DIR / filename))
        dst = desktop / filename
        if stash.exists() and not dst.exists():
            orig = _original_gio(info)
            try:
                if orig:
                    _restore_via_gio(stash, dst, orig[0], orig[1])
                else:
                    icon_registry.gio_move(stash, dst)
                recovered.append(filename)
                audit.log_action("RECOVERED_ORPHAN", f"name={filename}")
            except OSError as err:
                audit.log_debug("STASH", f"orphan restore failed {filename}: {err}")

    if STASH_DIR.is_dir():
        for item in STASH_DIR.iterdir():
            name = item.name
            if item.name.count(".") > 1 and item.name.rsplit(".", 1)[-1].isdigit():
                name = item.name.rsplit(".", 1)[0]
            dst = desktop / name
            if (item.is_dir() or item.is_file()) and not dst.exists() and name not in recovered:
                if icon_registry.gio_move(item, dst):
                    recovered.append(name)

    _session.clear()
    _hide_queue.clear()
    if PERSIST_FILE.is_file():
        PERSIST_FILE.unlink(missing_ok=True)

    if recovered:
        icon_registry.rescan_desktop()
    return recovered

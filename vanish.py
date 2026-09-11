"""Stash desktop icons — gio move preserves GVFS metadata."""

from __future__ import annotations

import json
import time
from pathlib import Path

import audit
import icon_registry
from state import ICON_H, ICON_W

DESKTOP = Path.home() / "Desktop"
DATA_DIR = Path.home() / ".local" / "share" / "opensesame"
STASH_DIR = DATA_DIR / "stash"
PERSIST_FILE = DATA_DIR / "hidden_by_app.json"

_session: dict[str, dict] = {}
_session_hidden: set[str] = set()


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STASH_DIR.mkdir(parents=True, exist_ok=True)


def _save_persisted() -> None:
    _ensure_dirs()
    PERSIST_FILE.write_text(
        json.dumps({"entries": _session}, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_persisted() -> dict[str, dict]:
    if not PERSIST_FILE.is_file():
        return {}
    try:
        data = json.loads(PERSIST_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "entries" in data:
            return {str(k): v for k, v in data["entries"].items()}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _original_gio(info: dict) -> tuple[int, int] | None:
    gio = info.get("original_gio") or info.get("gio")
    if gio and len(gio) == 2:
        return int(gio[0]), int(gio[1])
    return None


def hide_icon(desktop_dir: Path, filename: str) -> bool:
    """Stash a desktop item via gio move (metadata migrates with file)."""
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

    existing = _session.get(filename)
    if existing is None:
        _session[filename] = {
            "stash": str(stash_path),
            "original_gio": list(gio_pos) if gio_pos else None,
            "last_portal_gio": None,
        }
    else:
        existing["stash"] = str(stash_path)
        existing["last_portal_gio"] = list(gio_pos) if gio_pos else None

    _session_hidden.add(filename)
    _save_persisted()
    icon_registry.rescan_desktop()
    audit.log_action("STASH_ICON", f"name={filename} stash={stash_path}")
    return True


def _restore_via_gio(
    stash: Path,
    dst: Path,
    gio_x: int,
    gio_y: int,
) -> bool:
    """Set position on stash path, then gio move to desktop — metadata arrives pre-set."""
    if not icon_registry.set_icon_position(str(stash), gio_x, gio_y):
        audit.log_debug("STASH", f"pre-set failed on stash {stash.name} pos={gio_x},{gio_y}")
    if not icon_registry.gio_move(stash, dst):
        return False
    confirmed = icon_registry.get_gio_position(str(dst))
    if confirmed:
        sx, sy, _, _ = icon_registry.gio_to_screen(float(confirmed[0]), float(confirmed[1]))
        audit.log_debug(
            "STASH",
            f"restored {dst.name} intended=({gio_x},{gio_y}) read={confirmed} "
            f"screen=({sx:.0f},{sy:.0f})",
        )
    return True


def reveal_icon(
    desktop_dir: Path,
    filename: str,
    *,
    portal_cx: float | None = None,
    portal_cy: float | None = None,
    use_original: bool = False,
) -> bool:
    """Restore a stashed item — set gio on stash first, then gio move to desktop."""
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
        _session_hidden.discard(filename)
        _save_persisted()
        return False

    if dst.exists():
        audit.log_debug("STASH", f"restore blocked — already exists: {dst}")
        return False

    if portal_cx is not None and portal_cy is not None:
        path_str = str(dst)
        gio_x, gio_y = icon_registry.resolve_target_gio(
            portal_cx, portal_cy, ICON_W, ICON_H, path_str,
        )
        ok = _restore_via_gio(stash, dst, gio_x, gio_y)
        if ok:
            info["last_portal_gio"] = [gio_x, gio_y]
    elif use_original:
        orig = _original_gio(info)
        if orig is None:
            ok = icon_registry.gio_move(stash, dst)
        else:
            ok = _restore_via_gio(stash, dst, orig[0], orig[1])
    else:
        ok = icon_registry.gio_move(stash, dst)

    if not ok:
        audit.log_action("RESTORE_FAIL", f"name={filename}")
        return False

    _session.pop(filename, None)
    _session_hidden.discard(filename)
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
    """Restore every stashed item at its original desktop position (Esc / quit)."""
    desktop = desktop_dir or DESKTOP
    if not _session_hidden:
        return

    names = list(_session_hidden)
    for filename in names:
        reveal_icon(desktop, filename, use_original=True)

    if not _session_hidden and PERSIST_FILE.is_file():
        PERSIST_FILE.unlink(missing_ok=True)

    audit.log_action("RESTORE_ALL", f"count={len(names)}")


def reveal_all_at(desktop_dir: Path, portal_cx: float, portal_cy: float) -> int:
    """Restore stashed items at the portal circle center."""
    if not icon_registry.calibration_ready():
        audit.log_action("RESTORE_DEFERRED", "reason=calibration_not_ready")
        return 0
    if not _session_hidden:
        return 0

    names = list(_session_hidden)
    for filename in names:
        reveal_icon(desktop_dir, filename, portal_cx=portal_cx, portal_cy=portal_cy)

    if not _session_hidden and PERSIST_FILE.is_file():
        PERSIST_FILE.unlink(missing_ok=True)

    audit.log_action(
        "RESTORE_AT_PORTAL",
        f"count={len(names)} portal=({portal_cx:.0f},{portal_cy:.0f})",
    )
    return len(names)


def session_hidden() -> set[str]:
    return set(_session_hidden)


def recover_orphans(desktop_dir: Path | None = None) -> list[str]:
    """On startup, restore any stashed items to desktop at original positions."""
    desktop = desktop_dir or DESKTOP
    recovered: list[str] = []

    entries = _load_persisted()
    for filename, info in entries.items():
        stash = Path(info.get("stash", STASH_DIR / filename))
        dst = desktop / filename
        if not stash.exists() or dst.exists():
            continue
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
                    audit.log_action("RECOVERED_ORPHAN", f"name={name} (untracked)")

    _session.clear()
    _session_hidden.clear()
    if PERSIST_FILE.is_file():
        PERSIST_FILE.unlink(missing_ok=True)

    if recovered:
        icon_registry.rescan_desktop()

    return recovered


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python vanish.py <desktop-filename>")
        raise SystemExit(1)

    target = sys.argv[1]
    print(f"Stashing '{target}' — check your desktop, then press Enter to restore.")
    hide_icon(DESKTOP, target)
    input()
    reveal_icon(DESKTOP, target, use_original=True)
    print("Done.")

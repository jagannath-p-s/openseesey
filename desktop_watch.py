"""Watch ~/Desktop for DING icon position changes via Gio.FileMonitor."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

_GIO_MONITOR_SCRIPT = r"""
import gi
import sys
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

def on_changed(_mon, child, _other, _event):
    path = child.get_path() if child else ""
    if path and not path.rsplit("/", 1)[-1].startswith("."):
        print(path, flush=True)

desk = Gio.File.new_for_path(sys.argv[1])
mon = desk.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES)
mon.connect("changed", on_changed)
GLib.MainLoop().run()
"""

_watch_thread: threading.Thread | None = None


def start_desktop_watch(on_path_changed: Callable[[str], None]) -> None:
    """Spawn a background Gio.FileMonitor on ~/Desktop (system python3 + gi)."""
    global _watch_thread
    if _watch_thread is not None and _watch_thread.is_alive():
        return

    desktop = str(Path.home() / "Desktop")

    def run() -> None:
        try:
            proc = subprocess.Popen(
                ["/usr/bin/python3", "-c", _GIO_MONITOR_SCRIPT, desktop],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            if proc.stdout is None:
                return
            for line in proc.stdout:
                path = line.strip()
                if path:
                    on_path_changed(path)
        except (OSError, subprocess.SubprocessError):
            pass

    _watch_thread = threading.Thread(target=run, name="gio-desktop-watch", daemon=True)
    _watch_thread.start()

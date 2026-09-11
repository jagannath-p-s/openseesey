"""Audit and debug logger for OpenSesame."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path.home() / ".config" / "opensesame"
LOG_FILE = LOG_DIR / "actions.log"
DEBUG_FILE = LOG_DIR / "debug.log"


def reset_logs() -> None:
    """Truncate log files so each app run starts with a clean slate."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE.write_text("", encoding="utf-8")
        DEBUG_FILE.write_text("", encoding="utf-8")
    except Exception as err:
        print(f"[OpenSesame Log Error] Failed to reset logs: {err}")


def log_debug(component: str, message: str) -> None:
    """Append a timestamped debug entry to ~/.config/opensesame/debug.log and print to stdout."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3]
        entry = f"[{timestamp}] [{component.upper()}] {message}\n"

        # Print to terminal/stdout
        sys.stdout.write(entry)
        sys.stdout.flush()

        # Write to debug.log
        with DEBUG_FILE.open("a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as err:
        print(f"[OpenSesame Log Error] Failed to write debug log: {err}")


def log_action(action: str, details: str = "") -> None:
    """Append a timestamped audit log entry to ~/.config/opensesame/actions.log."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = f"{timestamp} {action} {details}".strip() + "\n"
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(entry)

        log_debug("ACTION", f"{action} {details}".strip())
    except Exception as err:
        print(f"[OpenSesame Audit Error] Failed to log action: {err}")


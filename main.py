#!/usr/bin/env python3
"""OpenSesame — sling ring cursor + vanish illusion."""

import signal
import sys

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication

import audit
import icon_registry
import vanish
from overlay import Overlay
from ring_window import RingWindow


def _shutdown(app: QApplication) -> None:
    vanish.reveal_all()
    icon_registry.refresh_after_hidden_change()
    QGuiApplication.restoreOverrideCursor()
    app.quit()


class _KeyFilter(QObject):
    """Catch Esc/Q globally — overlay may not have keyboard focus on Wayland."""

    def __init__(self, on_escape, on_quit) -> None:
        super().__init__()
        self._on_escape = on_escape
        self._on_quit = on_quit

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self._on_escape()
                return True
            if key in (Qt.Key.Key_Q, Qt.Key.Key_W) and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._on_quit()
                return True
        return super().eventFilter(obj, event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OpenSesame")
    app.setQuitOnLastWindowClosed(True)

    audit.reset_logs()
    vanish.recover_orphans()
    audit.log_action("APP_STARTUP", "OpenSesame initialized (vanish mode)")

    icon_registry.start()

    ring = RingWindow()
    overlay = Overlay()

    def toggle() -> None:
        if ring.is_armed():
            ring.set_armed(False)
            overlay.disarm()
        else:
            ring.set_armed(True)
            ring.show()
            ring.raise_()
            overlay.arm()

    def on_disarm() -> None:
        ring.set_armed(False)
        ring.show()
        ring.raise_()

    def on_escape() -> None:
        if overlay.is_armed():
            overlay.disarm()
        else:
            _shutdown(app)

    def on_quit() -> None:
        _shutdown(app)

    ring.clicked.connect(toggle)
    overlay.closed.connect(on_disarm)
    overlay.ring_move_requested.connect(ring.set_position)

    app.installEventFilter(_KeyFilter(on_escape, on_quit))

    quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), ring)
    quit_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
    quit_shortcut.activated.connect(on_quit)

    def handle_sigint(*_args) -> None:
        QTimer.singleShot(0, on_quit)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    sig_poll = QTimer()
    sig_poll.timeout.connect(lambda: None)
    sig_poll.start(200)

    ring.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

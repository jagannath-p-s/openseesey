"""Circle gesture chime — plays once per accepted circle."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

CHIME_PATH = Path(__file__).resolve().parent / "AUD-20260912-WA0000.mp3"

_player: QMediaPlayer | None = None
_output: QAudioOutput | None = None


def play_circle_chime() -> None:
    if not CHIME_PATH.is_file():
        return
    global _player, _output
    if _player is None:
        _player = QMediaPlayer()
        _output = QAudioOutput()
        _output.setVolume(0.85)
        _player.setAudioOutput(_output)
    _player.setSource(QUrl.fromLocalFile(str(CHIME_PATH)))
    _player.play()

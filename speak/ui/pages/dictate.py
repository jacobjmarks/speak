"""Dictate page: mic button, live/final transcript and copy."""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton

from ... import config, hotkey, output
from ..controls import Page, make_card
from ..widgets import MicButton, WaveStrip


LIVE_TAIL_CHARS = 4000  # live text stays pinned to its end, so only the newest part is ever visible


class DictatePage(Page):
    toggle_requested = Signal()

    def __init__(self, level_source):
        super().__init__()
        self.layout_.addStretch(1)
        self._transcript = ""
        self.mic = MicButton(level_source)
        self.mic.clicked.connect(self.toggle_requested)
        self.layout_.addWidget(self.mic, 0, Qt.AlignHCenter)

        self.wave = WaveStrip(level_source)
        self.layout_.addWidget(self.wave, 0, Qt.AlignHCenter)
        self.layout_.addSpacing(8)

        self.card, card_layout = make_card()
        card_layout.setContentsMargins(18, 14, 12, 10)
        self.text = QPlainTextEdit(readOnly=True)
        self.text.setPlaceholderText("Your words appear here")
        self.text.setMinimumHeight(110)
        card_layout.addWidget(self.text)
        row = QHBoxLayout()
        row.addStretch(1)
        self.copy_button = QPushButton("Copy", objectName="ghost", cursor=Qt.PointingHandCursor)
        self.copy_button.clicked.connect(self._copy)
        row.addWidget(self.copy_button)
        card_layout.addLayout(row)
        self.layout_.addWidget(self.card, 2)
        self.layout_.addStretch(1)
        self._revert = QTimer(self, singleShot=True, timeout=lambda: self.mic.set_mode("idle"))
        self.set_shortcut(config.DEFAULTS["hotkey"], config.DEFAULTS["shortcut_mode"])

    def set_shortcut(self, combo: str, mode: str):
        verb = {"auto": "Hold or tap ", "hold": "Hold "}.get(mode, "Press ")
        self._shortcut = verb + hotkey.display(combo)
        if self.mic.mode == "idle":
            self.wave.set_state("idle", self._shortcut)

    def set_palette(self, palette):
        self.mic.palette_ = self.wave.palette_ = palette
        self.mic.update()
        self.wave.update()

    def set_mode(self, mode: str, percent=None, word: str = ""):
        """`word` is the current phase ("Getting ready", "Finishing up") shown over the wave under the mic."""
        self._revert.stop()
        self.mic.set_mode(mode, percent)
        if word and percent is not None:
            word += f" · {int(percent)}%"
        if mode in ("preparing", "processing") and not word and self.wave.mode == mode:
            word = self.wave.text  # keep the last phase word on a bare state change
        self.wave.set_state(mode, word or (self._shortcut if mode == "idle" else ""))
        if mode in ("done", "error"):
            self._revert.start(1200)
            QTimer.singleShot(
                1250, self, lambda: self.mic.mode == "idle" and self.wave.set_state("idle", self._shortcut)
            )

    def set_live(self, text: str):
        self._transcript = text
        self.text.setPlainText(text[-LIVE_TAIL_CHARS:])
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

    def set_result(self, text: str):
        self._transcript = text
        self.text.setPlainText(text)

    def transcript(self) -> str:
        """Everything dictated so far, including any text scrolled out of the live view."""
        return self._transcript

    def _copy(self):
        text = self._transcript
        if text:
            output.copy(text)
            self.copy_button.setText("Copied ✓")
            QTimer.singleShot(1200, self, lambda: self.copy_button.setText("Copy"))

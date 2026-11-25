"""Dictate page: shortcut and status, the latest transcript with Copy, and links to the settings people tune most."""
from datetime import datetime

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ... import config, hotkey, output, tidy
from ..controls import LinkRow, Page, make_card, make_header, make_label
from ..paint import draw_keyboard, draw_lines, draw_mic
from ..widgets import MicButton, WaveStrip


LIVE_TAIL_CHARS = 4000  # live text stays pinned to its end, so only the newest part is ever visible
RELATED = (("hotkey", draw_keyboard, "Shortcut"), ("mic_device", draw_mic, "Microphone"),
           ("tidy", draw_lines, "Tidy up my words"))


class StatusPill(QWidget):
    """Short status word on a tint of its own colour, e.g. "Ready" in green."""

    def __init__(self):
        super().__init__()
        self.text, self.color = "Ready", QColor("#2f8f5b")
        self.setFixedHeight(22)
        self._fit()

    def set_status(self, text: str, color: str):
        self.text, self.color = text, QColor(color)
        self.setAccessibleName(text)
        self._fit()
        self.update()

    def _fit(self):
        font = self.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
        font.setBold(True)
        self._font = font
        self.setFixedWidth(QFontMetrics(font).horizontalAdvance(self.text) + 22)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        tint = QColor(self.color)
        tint.setAlphaF(0.16)
        p.setPen(Qt.NoPen)
        p.setBrush(tint)
        rect = QRectF(self.rect())
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.setFont(self._font)
        p.setPen(self.color)
        p.drawText(rect, Qt.AlignCenter, self.text)


class DictatePage(Page):
    toggle_requested = Signal()
    open_setting = Signal(str)  # a related setting's key

    def __init__(self, level_source):
        super().__init__()
        self._transcript = ""
        self.layout_.setSpacing(10)
        header, _ = make_header("Dictate")
        self.layout_.addWidget(header)
        self.layout_.addSpacing(10)

        status, row = make_card()
        row.setContentsMargins(16, 12, 16, 12)
        line = QHBoxLayout()
        line.setSpacing(14)
        self.mic = MicButton(level_source, size=56)
        self.mic.clicked.connect(self.toggle_requested)
        line.addWidget(self.mic)
        words = QVBoxLayout()
        words.setSpacing(1)
        self.shortcut_label = make_label("", "sectionhead")
        self.shortcut_label.setWordWrap(False)
        words.addWidget(self.shortcut_label)
        hint = make_label("Works in any app, or click the mic", "hint")
        hint.setWordWrap(False)
        words.addWidget(hint)
        line.addLayout(words, 1)
        self.wave = WaveStrip(level_source)
        self.wave.setFixedSize(180, 36)
        line.addWidget(self.wave)
        self.status = StatusPill()
        line.addWidget(self.status)
        row.addLayout(line)
        self.layout_.addWidget(status)

        self.card, card_layout = make_card()
        card_layout.setContentsMargins(18, 12, 12, 10)
        card_layout.setSpacing(4)
        self.meta = make_label("Latest dictation", "hint")
        card_layout.addWidget(self.meta)
        self.text = QPlainTextEdit(readOnly=True)
        self.text.setPlaceholderText("Your words appear here")
        self.text.setMinimumHeight(60)
        card_layout.addWidget(self.text, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.copy_button = QPushButton("Copy", cursor=Qt.PointingHandCursor)
        self.copy_button.clicked.connect(self._copy)
        buttons.addWidget(self.copy_button)
        card_layout.addLayout(buttons)
        self.layout_.addWidget(self.card, 1)

        self.layout_.addSpacing(8)
        self.layout_.addWidget(make_label("Related settings", "sectionhead"))
        links, rows = make_card()
        rows.setContentsMargins(6, 4, 6, 4)
        self.links = {}
        for i, (key, glyph, title) in enumerate(RELATED):
            if i:
                rows.addWidget(QFrame(objectName="divider"))
            link = LinkRow(glyph, title)
            link.activated.connect(lambda k=key: self.open_setting.emit(k))
            rows.addWidget(link)
            self.links[key] = link
        self.layout_.addWidget(links)

        self._revert = QTimer(self, singleShot=True, timeout=lambda: self.mic.set_mode("idle"))
        self.set_shortcut(config.DEFAULTS["hotkey"], config.DEFAULTS["shortcut_mode"])
        self.set_settings(config.DEFAULTS)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.wave.setVisible(self.width() >= 640)  # the status word still says what's happening

    def set_shortcut(self, combo: str, mode: str):
        verb = {"auto": "Hold or tap ", "hold": "Hold "}.get(mode, "Press ")
        self._shortcut = verb + hotkey.display(combo)
        self.shortcut_label.setText(self._shortcut)

    def set_settings(self, settings: dict):
        """Current values for the related-settings links."""
        self.set_shortcut(settings["hotkey"], settings["shortcut_mode"])
        self.links["hotkey"].value.setText(
            f'{hotkey.display(settings["hotkey"])} · {config.SHORTCUT_MODES[settings["shortcut_mode"]]}')
        self.links["mic_device"].value.setText(settings["mic_device"] or "System default")
        style = tidy.style(settings)
        value = config.TIDY_STYLES[style][0]
        if style == "ai":
            value += f" · {tidy.MODEL_SIZES[tidy.model_size(settings)][0]} model size"
        self.links["tidy"].value.setText(value)

    def set_status(self, text: str, color: str):
        self.status.set_status(text, color)

    def set_palette(self, palette):
        for widget in self.findChildren(QWidget):
            if hasattr(widget, "palette_"):
                widget.palette_ = palette
                widget.update()
        self.mic.palette_ = self.wave.palette_ = palette

    def set_mode(self, mode: str, percent=None, word: str = ""):
        """The status label carries the phase word ("Getting ready"); the wave shows only the percentage, if any."""
        self._revert.stop()
        self.mic.set_mode(mode, percent)
        self.wave.set_state(mode, f"{int(percent)}%" if percent is not None and mode in ("preparing", "processing")
                            else "")
        if mode in ("done", "error"):
            self._revert.start(1200)
            QTimer.singleShot(1250, self, lambda: self.mic.mode == "idle" and self.wave.set_state("idle", ""))

    def set_live(self, text: str):
        self._transcript = text
        self.text.setPlainText(text[-LIVE_TAIL_CHARS:])
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

    def set_result(self, text: str):
        self._transcript = text
        self.text.setPlainText(text)
        self.meta.setText(f"Latest dictation · {datetime.now():%H:%M}")

    def transcript(self) -> str:
        """Everything dictated so far, including any text scrolled out of the live view."""
        return self._transcript

    def _copy(self):
        text = self._transcript
        if text:
            output.copy(text)
            self.copy_button.setText("Copied ✓")
            QTimer.singleShot(1200, self, lambda: self.copy_button.setText("Copy"))

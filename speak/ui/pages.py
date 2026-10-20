"""Main-window pages: Dictate, History, Settings, About."""
from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from .. import audio, config, history, hotkey, output, platform_utils, updates
from .widgets import MicButton, ShortcutButton, Toggle, WaveStrip


def _card() -> tuple:
    frame = QFrame(objectName="card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 8, 18, 8)
    layout.setSpacing(0)
    return frame, layout


def _label(text: str, name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    return label


class Page(QWidget):
    def __init__(self):
        super().__init__(objectName="page")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(32, 28, 32, 28)
        self.layout_.setSpacing(14)


# ---------- Dictate ----------

class DictatePage(Page):
    toggle_requested = Signal()

    def __init__(self, level_source):
        super().__init__()
        self.layout_.addStretch(1)
        self.mic = MicButton(level_source)
        self.mic.clicked.connect(self.toggle_requested)
        self.layout_.addWidget(self.mic, 0, Qt.AlignHCenter)

        self.wave = WaveStrip(level_source)
        self.layout_.addWidget(self.wave, 0, Qt.AlignHCenter)
        self.layout_.addSpacing(8)

        self.card, card_layout = _card()
        card_layout.setContentsMargins(18, 14, 12, 10)
        self.text = QPlainTextEdit(readOnly=True)
        self.text.setPlaceholderText("Your words appear here")
        self.text.setMinimumHeight(110)
        card_layout.addWidget(self.text)
        row = QHBoxLayout()
        self.note = _label("", "hint")
        row.addWidget(self.note, 1)
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
            QTimer.singleShot(1250, lambda: self.mic.mode == "idle" and self.wave.set_state("idle", self._shortcut))

    def set_live(self, text: str):
        self.text.setPlainText(text)
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())
        self.note.setText("")

    def set_result(self, text: str, note: str):
        self.text.setPlainText(text)
        self.note.setText(note)

    def _copy(self):
        text = self.text.toPlainText()
        if text:
            output.copy(text)
            self.copy_button.setText("Copied ✓")
            QTimer.singleShot(1200, lambda: self.copy_button.setText("Copy"))


# ---------- History ----------

class HistoryEntry(QFrame):
    def __init__(self, when: str, text: str):
        super().__init__(objectName="entry", cursor=Qt.PointingHandCursor)
        self.text = text
        self.setToolTip("Click to copy")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(3)
        self.when = _label(when, "hint")
        self._when_text = when
        layout.addWidget(self.when)
        body = _label(text)
        body.setTextInteractionFlags(Qt.NoTextInteraction)
        layout.addWidget(body)

    def mouseReleaseEvent(self, e):
        output.copy(self.text)
        self.when.setText("Copied ✓")
        QTimer.singleShot(1000, lambda: self.when.setText(self._when_text))


class HistoryPage(Page):
    open_settings = Signal()

    def __init__(self):
        super().__init__()
        header = QHBoxLayout()
        header.addWidget(_label("History", "title"), 1)
        self.clear_button = QPushButton("Clear all", objectName="danger", cursor=Qt.PointingHandCursor)
        self.clear_button.clicked.connect(self._clear)
        header.addWidget(self.clear_button)
        self.layout_.addLayout(header)

        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.entries = QWidget(objectName="page")
        self.entries_layout = QVBoxLayout(self.entries)
        self.entries_layout.setContentsMargins(0, 0, 6, 0)
        self.entries_layout.setSpacing(4)
        self.scroll.setWidget(self.entries)
        self.layout_.addWidget(self.scroll, 1)

        self.empty = QWidget()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.addStretch(1)
        self.empty_label = _label("", "muted")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setTextFormat(Qt.RichText)
        self.empty_label.linkActivated.connect(lambda _: self.open_settings.emit())
        empty_layout.addWidget(self.empty_label)
        empty_layout.addStretch(2)
        self.layout_.addWidget(self.empty, 1)
        self.enabled = False

    def refresh(self, enabled: bool):
        self.enabled = enabled
        rows = history.recent()
        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for created, text in rows:
            try:
                when = datetime.fromisoformat(created).strftime("%d %b · %H:%M")
            except ValueError:
                when = created
            self.entries_layout.addWidget(HistoryEntry(when, text))
        self.entries_layout.addStretch(1)
        has_rows = bool(rows)
        self.scroll.setVisible(has_rows)
        self.clear_button.setVisible(has_rows)
        self.empty.setVisible(not has_rows)
        self.empty_label.setText("Nothing yet" if enabled else
                                 'History is off. Turn on “Keep history” in <a href="settings">Settings</a>.')

    def _clear(self):
        history.clear()
        self.refresh(self.enabled)

# ---------- Settings ----------

class SettingRow(QWidget):
    def __init__(self, title: str, hint: str, control: QWidget):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 12)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(_label(title))
        self.hint = _label(hint, "hint")
        self.hint.setWordWrap(True)
        self.hint.setVisible(bool(hint))
        text.addWidget(self.hint)
        layout.addLayout(text, 1)
        layout.addSpacing(16)
        layout.addWidget(control, 0, Qt.AlignVCenter)


def _combo(options: dict, current: str) -> QComboBox:
    combo = QComboBox(cursor=Qt.PointingHandCursor)
    for key, label in options.items():
        combo.addItem(label, key)
    index = combo.findData(current)
    combo.setCurrentIndex(max(0, index))
    return combo


LANGUAGES = {"auto": "Detect automatically", "en": "English", "es": "Spanish", "fr": "French", "de": "German",
             "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "ja": "Japanese", "zh": "Chinese"}


class MicCombo(QComboBox):
    """Input devices, re-read from the OS each time the list is opened (when `can_rescan()`)."""

    def __init__(self, current, can_rescan):
        super().__init__(cursor=Qt.PointingHandCursor)
        self.can_rescan = can_rescan
        self._fill(current, rescan=False)

    def _fill(self, current, rescan: bool):
        try:
            names = audio.input_devices(rescan)
        except Exception:
            names = []
        self.blockSignals(True)
        self.clear()
        self.addItem("System default", None)
        for name in names:
            self.addItem(name, name)
        if current and current not in names:
            self.addItem(f"{current} (not connected)", current)
        self.setCurrentIndex(max(0, self.findData(current)))
        self.blockSignals(False)

    def showPopup(self):
        self._fill(self.currentData(), rescan=self.can_rescan())
        super().showPopup()


class SettingsPage(QScrollArea):
    changed = Signal(dict)  # partial settings to merge and save
    shortcut_changed = Signal(str)
    shortcut_recording = Signal(bool)
    check_updates = Signal()

    def __init__(self, settings: dict, can_rescan_mics=lambda: False):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        body = Page()
        self.setWidget(body)
        layout = body.layout_
        layout.addWidget(_label("Settings", "title"))

        # --- basic ---
        card, rows = _card()
        self.shortcut = ShortcutButton(settings["hotkey"])
        self.shortcut.captured.connect(self._on_shortcut)
        self.shortcut.recording.connect(self.shortcut_recording)
        self._row(rows, "Shortcut", "Works in any app", self.shortcut)

        self.shortcut_mode = _combo(config.SHORTCUT_MODES, settings["shortcut_mode"])
        self.shortcut_mode.currentIndexChanged.connect(
            lambda: self.changed.emit({"shortcut_mode": self.shortcut_mode.currentData()}))
        self.shortcut_mode_row = self._row(rows, "How the shortcut works", " ", self.shortcut_mode)
        self._shortcut_mode_hint(settings["shortcut_mode"])

        self.mic = MicCombo(settings["mic_device"], can_rescan_mics)
        self.mic.setMaximumWidth(260)
        self.mic.currentIndexChanged.connect(lambda: self.changed.emit({"mic_device": self.mic.currentData()}))
        self._row(rows, "Microphone", "", self.mic)

        self.tidy = _combo(config.TIDY_LEVELS, settings["tidy"])
        self.tidy.currentIndexChanged.connect(lambda: self.changed.emit({"tidy": self.tidy.currentData()}))
        self.tidy_row = self._row(rows, "Tidy up my words", " ", self.tidy)

        self.corrections = self._toggle(settings["corrections"], "corrections")
        self.corrections_row = self._row(rows, "Fix changes of mind",
                                         "“Tuesday, no, Wednesday” becomes “Wednesday”, even sentences later", self.corrections)

        self.paste = self._toggle(settings["auto_paste"], "auto_paste")
        self._row(rows, "Type into the app I'm using", "Otherwise text is just shown here to copy", self.paste)

        self.enter = self._toggle(settings["press_enter"], "press_enter")
        self.enter.setEnabled(settings["auto_paste"])
        self.enter_row = self._row(rows, "Press Enter afterwards",
                                   "Experimental. Sends messages in chat apps. Skipped if you switched apps",
                                   self.enter)
        if not platform_utils.IS_WINDOWS:
            self.enter_row.hide()

        options = {k: v for k, v in config.CLOSE_ACTIONS.items()}
        self.close_action = _combo(options, settings["close_action"])
        self.close_action.currentIndexChanged.connect(
            lambda: self.changed.emit({"close_action": self.close_action.currentData()}))
        self._row(rows, "When I close the window", "", self.close_action)

        self.login = Toggle()
        try:
            self.login.setChecked(platform_utils.launch_at_login_enabled())
        except Exception:
            self.login.setEnabled(False)
        self.login.toggled.connect(self._on_login)
        self._row(rows, "Start with my computer", "Runs quietly in the tray", self.login)

        self.history = self._toggle(settings["history_enabled"], "history_enabled")
        self._row(rows, "Keep history", "Saved only on this device", self.history)

        self.theme = _combo({t: t for t in config.THEMES}, settings["theme"])
        self.theme.currentIndexChanged.connect(lambda: self.changed.emit({"theme": self.theme.currentData()}))
        self._row(rows, "Appearance", "", self.theme)

        self.updates = _combo(config.UPDATE_MODES, settings["updates"])
        self.updates.currentIndexChanged.connect(lambda: self.changed.emit({"updates": self.updates.currentData()}))
        self.updates_row = self._row(rows, "Updates", " ", self.updates)
        self._last_check = None

        version = QWidget()
        line = QHBoxLayout(version)
        line.setContentsMargins(0, 0, 0, 0)
        self.update_status = _label("", "hint")
        check = QPushButton("Check now", cursor=Qt.PointingHandCursor)
        check.clicked.connect(self.check_updates)
        check.setEnabled(bool(updates.parse(updates.VERSION)))
        line.addWidget(self.update_status)
        line.addWidget(check)
        self._row(rows, "Version", updates.version() if updates.VERSION else "Development build (doesn't update)",
                  version, last=True)
        self._update_hint(settings["updates"])
        layout.addWidget(card)

        # --- indicator ---
        layout.addWidget(_label("While dictating", "section"))
        card, rows = _card()
        self.overlay = self._toggle(settings["overlay_enabled"], "overlay_enabled")
        self._row(rows, "Show indicator", "Hidden when Speak's own window is in front", self.overlay)
        self.position = _combo(config.OVERLAY_POSITIONS, settings["overlay_position"])
        self.position.currentIndexChanged.connect(
            lambda: self.changed.emit({"overlay_position": self.position.currentData()}))
        self._row(rows, "Position", "", self.position)
        self.live = _combo(config.LIVE_PREVIEWS, settings["live_preview"])
        self.live.currentIndexChanged.connect(lambda: self.changed.emit({"live_preview": self.live.currentData()}))
        self._row(rows, "Live text", "Words appear under the indicator as you speak", self.live, last=True)
        layout.addWidget(card)

        # --- advanced (collapsed) ---
        self.advanced_button = QPushButton("Advanced  ›", objectName="ghost", cursor=Qt.PointingHandCursor)
        self.advanced_button.setCheckable(True)
        self.advanced_button.toggled.connect(self._toggle_advanced)
        layout.addWidget(self.advanced_button, 0, Qt.AlignLeft)

        self.advanced, rows = _card()
        self.language = QComboBox(cursor=Qt.PointingHandCursor, editable=True)
        for code, label in LANGUAGES.items():
            self.language.addItem(f"{label} ({code})" if code != "auto" else label, code)
        index = self.language.findData(settings["language"])
        if index >= 0:
            self.language.setCurrentIndex(index)
        else:
            self.language.setEditText(settings["language"])
        self.language.currentIndexChanged.connect(self._on_language)
        self.language.lineEdit().editingFinished.connect(self._on_language)
        self._row(rows, "Language", "Spoken language, or a code like “en”", self.language)

        self.asr_model = _combo(config.ASR_MODELS, settings["model"])
        self.asr_model.currentIndexChanged.connect(lambda: self.changed.emit({"model": self.asr_model.currentData()}))
        self._row(rows, "Speech model", "", self.asr_model)

        models = {"auto": "Automatic (recommended)"}
        models.update({k: v["label"] for k, v in config.CLEANUP_MODELS.items()})
        self.cleanup_model = _combo(models, settings["cleanup_model"])
        self.cleanup_model.currentIndexChanged.connect(
            lambda: self.changed.emit({"cleanup_model": self.cleanup_model.currentData()}))
        self._row(rows, "Tidy-up model", "Automatic picks by tidy level and what your computer runs fast",
                  self.cleanup_model)

        self.unload = _combo(config.UNLOAD_AFTER, settings["unload_after"])
        self.unload.currentIndexChanged.connect(lambda: self.changed.emit({"unload_after": self.unload.currentData()}))
        self._row(rows, "Free up memory when idle",
                  "Unloads the speech and tidy-up models (1 to 4 GB). The next dictation then takes a few seconds to start",
                  self.unload)

        folder = QPushButton("Open", cursor=Qt.PointingHandCursor)
        folder.clicked.connect(lambda: (config.APP_DIR.mkdir(parents=True, exist_ok=True),
                                        platform_utils.open_path(config.APP_DIR)))
        self._row(rows, "Data folder", "Models, logs and settings", folder, last=True)
        self.advanced.setMaximumHeight(0)
        self.advanced.setVisible(False)
        layout.addWidget(self.advanced)
        layout.addStretch(1)
        self._anim = QPropertyAnimation(self.advanced, b"maximumHeight", self, duration=220,
                                        easingCurve=QEasingCurve.OutCubic)
        self._anim.finished.connect(self._anim_done)

    def _row(self, rows: QVBoxLayout, title: str, hint: str, control: QWidget, last: bool = False) -> SettingRow:
        row = SettingRow(title, hint, control)
        rows.addWidget(row)
        if not last:
            divider = QFrame(objectName="divider")
            divider.setFixedHeight(1)
            rows.addWidget(divider)
        return row

    def set_update_status(self, text: str):
        self.update_status.setText(text)

    def set_last_check(self, when):
        self._last_check = when
        self._update_hint(self.updates.currentData())

    def _update_hint(self, mode: str):
        hint = {"auto": "Checks when Speak starts and every 24 hours. Installs when you quit or restart",
                "notify": "Checks when Speak starts and every 24 hours, and shows a button. Nothing installs by itself",
                "off": "Never checks. Use Check now below"}[mode]
        if self._last_check and mode != "off":
            hint += f". Last checked {self._last_check:%H:%M}"
        self.updates_row.hint.setText(hint)

    def set_tidy_summary(self, summary: str, large_model: bool):
        self.tidy_row.hint.setText(summary)
        self.corrections.setEnabled(large_model)
        self.corrections_row.hint.setText(
            "“Tuesday, no, Wednesday” becomes “Wednesday”, even sentences later" if large_model else
            "Needs the large AI: Best, or Automatic with a good graphics card")

    def _shortcut_mode_hint(self, mode: str):
        self.shortcut_mode_row.hint.setText({
            "auto": "Hold while you speak, or tap once to start and again to stop",
            "hold": "Hold while you speak; let go to finish",
            "toggle": "Tap once to start, again to stop"}[mode])

    def _toggle(self, value: bool, key: str) -> Toggle:
        toggle = Toggle()
        toggle.setChecked(value)
        toggle.toggled.connect(lambda on: self.changed.emit({key: on}))
        return toggle

    def set_palette(self, palette):
        for toggle in self.findChildren(Toggle):
            toggle.palette_ = palette
            toggle.update()

    def sync(self, settings: dict):
        """Reflect settings changed elsewhere (e.g. first-close prompt, history page)."""
        for widget, value in ((self.close_action, settings["close_action"]),):
            widget.blockSignals(True)
            widget.setCurrentIndex(max(0, widget.findData(value)))
            widget.blockSignals(False)
        self.history.blockSignals(True)
        self.history.setChecked(settings["history_enabled"])
        self.history.blockSignals(False)
        self.enter.setEnabled(settings["auto_paste"])
        self._update_hint(settings["updates"])
        self._shortcut_mode_hint(settings["shortcut_mode"])

    def _on_shortcut(self, combo: str):
        self.shortcut_changed.emit(combo)

    def _on_language(self):
        data = self.language.currentData()
        text = self.language.currentText().strip()
        if self.language.currentIndex() >= 0 and self.language.itemText(self.language.currentIndex()) == text:
            value = data
        else:
            value = text or "auto"
        self.changed.emit({"language": value})

    def _on_login(self, on: bool):
        try:
            platform_utils.set_launch_at_login(on)
        except Exception:
            self.login.blockSignals(True)
            self.login.setChecked(not on)
            self.login.blockSignals(False)

    def _toggle_advanced(self, open_: bool):
        self.advanced_button.setText("Advanced  ⌄" if open_ else "Advanced  ›")
        self._anim.stop()
        if open_:
            self.advanced.setVisible(True)
        self._anim.setStartValue(self.advanced.maximumHeight() if self.advanced.maximumHeight() < 5000 else
                                 self.advanced.sizeHint().height())
        self._anim.setEndValue(self.advanced.sizeHint().height() if open_ else 0)
        self._anim.start()
        if open_:
            QTimer.singleShot(240, lambda: self.ensureWidgetVisible(self.advanced))

    def _anim_done(self):
        if self.advanced_button.isChecked():
            self.advanced.setMaximumHeight(16_777_215)
        else:
            self.advanced.setVisible(False)


# ---------- About ----------

def _open_url(url: str):
    QDesktopServices.openUrl(QUrl(url))


class AboutPage(Page):
    def __init__(self, logo: QWidget):
        super().__init__()
        head = QHBoxLayout()
        head.setSpacing(14)
        head.addWidget(logo, 0, Qt.AlignVCenter)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(_label("Speak", "title"))
        names.addWidget(_label(f"Version {updates.VERSION}" if updates.VERSION else "Development build", "muted"))
        head.addLayout(names, 1)
        self.layout_.addLayout(head)
        self.layout_.addWidget(_label("Talk anywhere and Speak types it for you. Private, offline and free.", "muted"))
        self.layout_.addSpacing(6)

        self.layout_.addWidget(_label("Support Speak", "section"))
        card, rows = _card()
        rows.setContentsMargins(18, 16, 18, 16)
        rows.setSpacing(12)
        rows.addWidget(_label("Speak is free, with no ads, no account and no paid tier. "
                              "If it saves you time, sponsoring keeps it going and growing."))
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        sponsor = QPushButton("♥  Sponsor on GitHub", objectName="primary", cursor=Qt.PointingHandCursor)
        sponsor.clicked.connect(lambda: _open_url(config.SPONSOR_URL))
        coffee = QPushButton("Buy me a coffee", cursor=Qt.PointingHandCursor)
        coffee.clicked.connect(lambda: _open_url(config.COFFEE_URL))
        buttons.addWidget(sponsor)
        buttons.addWidget(coffee)
        buttons.addStretch(1)
        rows.addLayout(buttons)
        rows.addWidget(_label("GitHub takes no fee from sponsorships, monthly or one-off. "
                              "Or buy a one-off coffee with a card, no account needed.", "hint"))
        self.layout_.addWidget(card)
        self.layout_.addSpacing(6)

        self.layout_.addWidget(_label("Open source", "section"))
        links = _label('Speak is built on open-source software and open models.<br>'
                       '<a href="source">Source code</a> &nbsp;·&nbsp; <a href="notices">Open-source notices</a>'
                       ' &nbsp;·&nbsp; <a href="issues">Report a problem</a>', "muted")
        links.setTextFormat(Qt.RichText)
        links.linkActivated.connect(self._open_link)
        self.layout_.addWidget(links)
        self.layout_.addStretch(1)

    def _open_link(self, link: str):
        notices = platform_utils.notices_file()
        if link == "notices" and notices.is_file():
            platform_utils.open_path(notices)
            return
        _open_url(config.REPO_URL + {"source": "", "issues": "/issues", "notices": "/blob/main/docs/DEVELOPMENT.md#licensing"}[link])

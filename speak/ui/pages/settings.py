"""Settings page: basic card plus a collapsible Advanced section. Every control emits `changed` with a partial settings dict."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget

from ... import config, platform_utils, updates
from ..controls import (LanguageItemDelegate, MicCombo, NoWheelComboBox, Page, SettingRow, make_card, make_combo,
                        make_label)
from ..widgets import ShortcutButton, Toggle


class SettingsPage(QScrollArea):
    changed = Signal(dict)  # partial settings to merge and save
    shortcut_changed = Signal(str)
    shortcut_recording = Signal(bool)
    check_updates = Signal()
    rerun_setup = Signal()

    def __init__(self, settings: dict, can_rescan_mics=lambda: False):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        body = Page()
        body.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setWidget(body)
        layout = body.layout_
        header = QHBoxLayout()
        header.addWidget(make_label("Settings", "title"), 1)
        advanced_label = make_label("Advanced", "hint")
        advanced_label.setWordWrap(False)
        header.addWidget(advanced_label)
        self.advanced_toggle = Toggle()
        self.advanced_toggle.setAccessibleName("Show advanced settings")
        header.addWidget(self.advanced_toggle)
        layout.addLayout(header)
        self._advanced_widgets = []

        # --- dictation ---
        layout.addWidget(make_label("Dictation", "section"))
        card, rows = make_card()
        self.shortcut = ShortcutButton(settings["hotkey"])
        self.shortcut.captured.connect(self._on_shortcut)
        self.shortcut.recording.connect(self.shortcut_recording)
        self._row(rows, "Shortcut", "Works in any app", self.shortcut)

        self.shortcut_mode = make_combo(config.SHORTCUT_MODES, settings["shortcut_mode"])
        self.shortcut_mode.currentIndexChanged.connect(
            lambda: self.changed.emit({"shortcut_mode": self.shortcut_mode.currentData()}))
        self.shortcut_mode_row = self._row(rows, "How the shortcut works", " ", self.shortcut_mode)
        self._shortcut_mode_hint(settings["shortcut_mode"])

        self.mic = MicCombo(settings["mic_device"], can_rescan_mics)
        self.mic.setMaximumWidth(260)
        self.mic.currentIndexChanged.connect(lambda: self.changed.emit({"mic_device": self.mic.currentData()}))
        self._row(rows, "Microphone", "", self.mic)

        self.tidy = make_combo(config.TIDY_LEVELS, settings["tidy"])
        self.tidy.currentIndexChanged.connect(lambda: self.changed.emit({"tidy": self.tidy.currentData()}))
        self.tidy_row = self._row(rows, "Tidy up my words", " ", self.tidy)

        self.corrections = self._toggle(settings["corrections"], "corrections")
        self.corrections_row = self._row(rows, "Fix changes of mind",
                                         "“Tuesday, no, Wednesday” becomes “Wednesday”, even sentences later", self.corrections)

        self.paste = self._toggle(settings["auto_paste"], "auto_paste")
        self._row(rows, "Type into the app I'm using", "Otherwise text is just shown here to copy", self.paste)

        self.enter = self._toggle(settings["press_enter"], "press_enter")
        self.enter.setEnabled(settings["auto_paste"])
        self.paste.toggled.connect(self.enter.setEnabled)
        self.enter_row = self._row(rows, f"Press {'Return' if platform_utils.IS_MAC else 'Enter'} after pasting",
                                   "Experimental. Skipped if you switched apps",
                                   self.enter)
        if not platform_utils.IS_WINDOWS:
            self.enter_row.hide()

        self.enter_before = self._toggle(settings["press_enter_before"], "press_enter_before")
        self.enter_before.setEnabled(settings["auto_paste"])
        self.paste.toggled.connect(self.enter_before.setEnabled)
        self.enter_before_row = self._row(rows, f"Press {'Return' if platform_utils.IS_MAC else 'Enter'} before pasting",
                                          "Experimental. Skipped if you switched apps",
                                          self.enter_before)
        if not platform_utils.IS_WINDOWS:
            self.enter_before_row.hide()

        self.language = NoWheelComboBox(cursor=Qt.PointingHandCursor)
        self.language_delegate = LanguageItemDelegate(self.language)
        self.language.setItemDelegate(self.language_delegate)
        self.language.addItem(config.LANGUAGES["auto"], "auto")
        for title, languages in (
            ("Transcription-ready", config.TRANSCRIPTION_READY_LANGUAGES),
            ("Broad coverage", config.BROAD_COVERAGE_LANGUAGES),
        ):
            self._add_language_section(title)
            for code, label in languages.items():
                self.language.addItem(label, code)
        self.language.setCurrentIndex(max(0, self.language.findData(settings["language"])))
        self.language.setMinimumWidth(280)
        self.language.setMaximumWidth(340)
        self.language.currentIndexChanged.connect(self._on_language)
        language_control = QWidget()
        language_layout = QHBoxLayout(language_control)
        language_layout.setContentsMargins(0, 0, 0, 0)
        language_layout.setSpacing(8)
        language_layout.addWidget(self.language)
        self._row(rows, "Language", "Spoken language, or detect automatically", language_control, advanced=True)

        self.asr_model = make_combo(config.ASR_MODELS, settings["model"])
        self.asr_model.currentIndexChanged.connect(lambda: self.changed.emit({"model": self.asr_model.currentData()}))
        self._row(rows, "Speech model", "", self.asr_model, advanced=True)

        models = {"auto": "Automatic (recommended)"}
        models.update({k: v["label"] for k, v in config.CLEANUP_MODELS.items()})
        self.cleanup_model = make_combo(models, settings["cleanup_model"])
        self.cleanup_model.currentIndexChanged.connect(
            lambda: self.changed.emit({"cleanup_model": self.cleanup_model.currentData()}))
        self._row(rows, "Tidy-up model", "Automatic picks by tidy level and what your computer runs fast",
                  self.cleanup_model, advanced=True)

        self.cleanup_device = make_combo(config.CLEANUP_DEVICES, settings["cleanup_device"])
        self.cleanup_device.currentIndexChanged.connect(
            lambda: self.changed.emit({"cleanup_device": self.cleanup_device.currentData()}))
        self._row(rows, "Tidy-up device", "Choose Automatic, CPU only, or a specific GPU",
                  self.cleanup_device, advanced=True)

        self.unload = make_combo(config.UNLOAD_AFTER, settings["unload_after"])
        self.unload.currentIndexChanged.connect(lambda: self.changed.emit({"unload_after": self.unload.currentData()}))
        self._row(rows, "Free up memory when idle",
                  "Unloads the speech and tidy-up models (1 to 4 GB). The next dictation then takes a few seconds to start",
                  self.unload, advanced=True, last=True)
        layout.addWidget(card)

        # --- indicator ---
        layout.addWidget(make_label("While dictating", "section"))
        card, rows = make_card()
        self.audio_dim = self._toggle(settings["audio_dim_enabled"], "audio_dim_enabled")
        self.audio_dim_row = self._row(
            rows, "Dim system audio", "Lowers output while listening, then restores it. Changes apply next time.",
            self.audio_dim)
        audio_dim_divider = rows.itemAt(rows.count() - 1).widget()
        self.audio_dim_level = QWidget()
        level_layout = QHBoxLayout(self.audio_dim_level)
        level_layout.setContentsMargins(0, 0, 0, 0)
        self.audio_dim_slider = QSlider(Qt.Horizontal)
        self.audio_dim_slider.setAccessibleName("Reduce system audio by")
        self.audio_dim_slider.setRange(10, 90)
        self.audio_dim_slider.setSingleStep(config.AUDIO_DIM_STEP)
        self.audio_dim_slider.setPageStep(10)
        self.audio_dim_slider.setValue(settings["audio_dim_percent"])
        self.audio_dim_value = make_label(f'{settings["audio_dim_percent"]}%')
        self.audio_dim_value.setMinimumWidth(42)
        level_layout.addWidget(self.audio_dim_slider, 1)
        level_layout.addWidget(self.audio_dim_value)
        self.audio_dim_slider.setEnabled(settings["audio_dim_enabled"])
        self.audio_dim_slider.valueChanged.connect(self._on_audio_dim_changed)
        self.audio_dim_level_row = self._row(rows, "Reduce by", "", self.audio_dim_level)
        audio_dim_level_divider = rows.itemAt(rows.count() - 1).widget()
        if not (platform_utils.IS_WINDOWS or platform_utils.IS_MAC):
            for widget in (self.audio_dim_row, audio_dim_divider, self.audio_dim_level_row, audio_dim_level_divider):
                widget.hide()
        self.audio_dim.toggled.connect(self._on_audio_dim_toggled)

        self.overlay = self._toggle(settings["overlay_enabled"], "overlay_enabled")
        self._row(rows, "Show indicator", "Hidden while Speak's Dictate page is in front", self.overlay)
        self.position = make_combo(config.OVERLAY_POSITIONS, settings["overlay_position"])
        self.position.currentIndexChanged.connect(
            lambda: self.changed.emit({"overlay_position": self.position.currentData()}))
        self._row(rows, "Position", "", self.position)
        self.live = make_combo(config.LIVE_PREVIEWS, settings["live_preview"])
        self.live.currentIndexChanged.connect(lambda: self.changed.emit({"live_preview": self.live.currentData()}))
        self._row(rows, "Live text", "Words appear under the indicator as you speak", self.live, last=True)
        layout.addWidget(card)

        # --- app ---
        layout.addWidget(make_label("App", "section"))
        card, rows = make_card()
        options = {k: v for k, v in config.CLOSE_ACTIONS.items()}
        self.close_action = make_combo(options, settings["close_action"])
        self.close_action.currentIndexChanged.connect(
            lambda: self.changed.emit({"close_action": self.close_action.currentData()}))
        self._row(rows, "When I close the window", "", self.close_action)

        self.login = Toggle()
        try:
            self.login.setChecked(platform_utils.launch_at_login_enabled())
        except Exception:
            self.login.setEnabled(False)
        self.login.toggled.connect(self._on_login)
        self._row(rows, "Open at login" if platform_utils.IS_MAC else "Start with my computer",
                  f"Runs quietly in the {platform_utils.TRAY_NAME}", self.login)

        self.history = self._toggle(settings["history_enabled"], "history_enabled")
        self._row(rows, "Keep history", "Saved only on this device", self.history)

        self.theme = make_combo({t: t for t in config.THEMES}, settings["theme"])
        self.theme.currentIndexChanged.connect(lambda: self.changed.emit({"theme": self.theme.currentData()}))
        self._row(rows, "Appearance", "", self.theme)

        setup = QPushButton("Run setup", cursor=Qt.PointingHandCursor)
        setup.clicked.connect(self.rerun_setup)
        self._row(rows, "First-run setup", "Re-pick your microphone and test dictation speed", setup)

        folder = QPushButton("Open", cursor=Qt.PointingHandCursor)
        folder.clicked.connect(lambda: (config.APP_DIR.mkdir(parents=True, exist_ok=True),
                                        platform_utils.open_path(config.APP_DIR)))
        self._row(rows, "Data folder", "Models, logs and settings", folder, advanced=True, last=True)
        layout.addWidget(card)

        # --- updates ---
        layout.addWidget(make_label("Updates", "section"))
        card, rows = make_card()
        self.updates = make_combo(config.UPDATE_MODES, settings["updates"])
        self.updates.currentIndexChanged.connect(lambda: self.changed.emit({"updates": self.updates.currentData()}))
        self.updates_row = self._row(rows, "Updates", " ", self.updates)
        self.prereleases = self._toggle(settings["prereleases"], "prereleases")
        self._row(rows, "Pre-release versions", "Try new versions early; they may have bugs", self.prereleases)
        self._last_check = None

        version = QWidget()
        line = QHBoxLayout(version)
        line.setContentsMargins(0, 0, 0, 0)
        self.update_status = make_label("", "hint")
        check = QPushButton("Check now", cursor=Qt.PointingHandCursor)
        check.clicked.connect(self.check_updates)
        check.setEnabled(updates.updatable())
        line.addWidget(self.update_status)
        line.addWidget(check)
        self._row(rows, "Version", updates.display() + ("" if updates.updatable() else " (doesn't update)"),
                  version, last=True)
        self._update_hint(settings["updates"])
        layout.addWidget(card)

        layout.addStretch(1)
        self.advanced_toggle.setChecked(settings["advanced_settings"] is True)
        self._toggle_advanced(self.advanced_toggle.isChecked())
        self.advanced_toggle.toggled.connect(self._on_advanced_toggled)

    def _row(self, rows: QVBoxLayout, title: str, hint: str, control: QWidget, last: bool = False,
             advanced: bool = False) -> SettingRow:
        row = SettingRow(title, hint, control)
        if advanced:
            if rows.count():
                divider = rows.itemAt(rows.count() - 1).widget()
                if divider and divider.objectName() == "divider":
                    divider.hide()
                    if divider not in self._advanced_widgets:
                        self._advanced_widgets.append(divider)
            row.hide()
            self._advanced_widgets.append(row)
        rows.addWidget(row)
        if not last:
            divider = QFrame(objectName="divider")
            divider.setFixedHeight(1)
            if advanced:
                divider.hide()
                self._advanced_widgets.append(divider)
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

    def set_gpus(self, gpus: list, current: str):
        combo = self.cleanup_device
        combo.blockSignals(True)
        combo.clear()
        for key, label in config.CLEANUP_DEVICES.items():
            combo.addItem(label, key)
        for g in gpus:
            combo.addItem(f"GPU: {g.name}", g.device)
        if combo.findData(current) < 0:
            combo.addItem(f"GPU: Unavailable ({current})", current)
        combo.setCurrentIndex(combo.findData(current))
        combo.blockSignals(False)

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

    def _on_audio_dim_toggled(self, enabled: bool):
        self.audio_dim_slider.setEnabled(enabled)
        self.changed.emit({"audio_dim_enabled": enabled})

    def _on_audio_dim_changed(self, percent: int):
        percent = config.snap_audio_dim_percent(percent)
        if self.audio_dim_slider.value() != percent:
            self.audio_dim_slider.setValue(percent)
            return
        self.audio_dim_value.setText(f"{percent}%")
        self.changed.emit({"audio_dim_percent": percent})

    def set_palette(self, palette):
        for toggle in self.findChildren(Toggle):
            toggle.palette_ = palette
            toggle.update()
        self.language_delegate.muted = QColor(palette.muted)

    def sync(self, settings: dict):
        """Reflect settings changed elsewhere (e.g. first-close prompt, history page)."""
        for widget, value in ((self.close_action, settings["close_action"]),
                              (self.cleanup_device, settings["cleanup_device"]),
                              (self.shortcut_mode, settings["shortcut_mode"]),
                              (self.tidy, settings["tidy"]),
                              (self.cleanup_model, settings["cleanup_model"]),
                              (self.asr_model, settings["model"]),
                              (self.language, settings["language"]),
                              (self.unload, settings["unload_after"]),
                              (self.position, settings["overlay_position"]),
                              (self.live, settings["live_preview"]),
                              (self.theme, settings["theme"]),
                              (self.updates, settings["updates"])):
            widget.blockSignals(True)
            widget.setCurrentIndex(max(0, widget.findData(value)))
            widget.blockSignals(False)
        self.shortcut.set_combo(settings["hotkey"])
        self.history.blockSignals(True)
        self.history.setChecked(settings["history_enabled"])
        self.history.blockSignals(False)
        self.mic.set_device(settings["mic_device"])
        for toggle, value in ((self.corrections, settings["corrections"]),
                              (self.prereleases, settings["prereleases"])):
            toggle.blockSignals(True)
            toggle.setChecked(value)
            toggle.blockSignals(False)
        self.audio_dim.blockSignals(True)
        self.audio_dim.setChecked(settings["audio_dim_enabled"])
        self.audio_dim.blockSignals(False)
        self.audio_dim_slider.blockSignals(True)
        self.audio_dim_slider.setValue(settings["audio_dim_percent"])
        self.audio_dim_slider.blockSignals(False)
        self.audio_dim_slider.setEnabled(settings["audio_dim_enabled"])
        self.audio_dim_value.setText(f'{settings["audio_dim_percent"]}%')
        self.enter.setEnabled(settings["auto_paste"])
        self.enter_before.setEnabled(settings["auto_paste"])
        self._update_hint(settings["updates"])
        self._shortcut_mode_hint(settings["shortcut_mode"])

    def _on_shortcut(self, combo: str):
        self.shortcut_changed.emit(combo)

    def _on_language(self):
        self.changed.emit({"language": self.language.currentData()})

    def _add_language_section(self, title: str):
        self.language.addItem(title)
        item = self.language.model().item(self.language.count() - 1)
        item.setData("section", Qt.UserRole + 1)
        item.setFlags(Qt.ItemIsEnabled)
        item.setForeground(self.language.palette().color(QPalette.Disabled, QPalette.Text))
        font = item.font()
        font.setBold(True)
        item.setFont(font)

    def _on_login(self, on: bool):
        try:
            platform_utils.set_launch_at_login(on)
        except Exception:
            self.login.blockSignals(True)
            self.login.setChecked(not on)
            self.login.blockSignals(False)

    def _toggle_advanced(self, visible: bool):
        for widget in self._advanced_widgets:
            widget.setVisible(visible)

    def _on_advanced_toggled(self, visible: bool):
        self._toggle_advanced(visible)
        self.changed.emit({"advanced_settings": visible})

"""Settings page: one scrolling page per category (picked from the main window's sidebar) plus search results. Each
category holds titled sections; two or more technical or experimental options sit behind a section's "More options".
Every control emits `changed` with a partial settings dict."""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLineEdit, QPushButton,
                               QScrollArea, QSizePolicy, QSlider, QStackedWidget, QVBoxLayout, QWidget)

from ... import config, platform_utils, tidy, updates
from ..controls import (LanguageItemDelegate, MicCombo, NoWheelComboBox, Page, SettingRow, SettingsSection,
                        explicitly_hidden, make_badge, make_combo, make_header, make_label)
from ..widgets import Segmented, ShortcutButton, Toggle

CATEGORIES = {"dictation": "Dictation", "text": "Text & typing", "indicator": "Indicator & sound", "app": "App",
              "updates": "Updates"}
CONTROL_WIDTH = 260  # dropdowns share one width so their edges line up down a section
ENTER = "Return" if platform_utils.IS_MAC else "Enter"
ENTER_HINT = "Skipped if you switched apps"
ENTER_OFF_HINT = "Needs “Type into the app I'm using”"


class SearchField(QLineEdit):
    """Esc clears; Return opens the first result; Down moves into the results."""
    submitted = Signal()
    down = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.text():
            self.clear()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.submitted.emit()
        elif event.key() == Qt.Key_Down:
            self.down.emit()
        else:
            super().keyPressEvent(event)


class SearchResult(QFrame):
    """One matching setting: its title, where it lives, and its badge. Click, Return or Space opens it."""
    activated = Signal()

    def __init__(self, row: SettingRow):
        super().__init__(objectName="result", cursor=Qt.PointingHandCursor)
        self.row = row
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(row.title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        title = make_label(row.title)
        title.setWordWrap(False)
        heading.addWidget(title)
        if row.badge:
            heading.addWidget(make_badge(row.badge), 0, Qt.AlignVCenter)
        heading.addStretch(1)
        layout.addLayout(heading)
        section = row.section
        where = [section.category_label] + ([section.title] if section.title else [])
        if row.advanced:
            where.append("More options")
        layout.addWidget(make_label(" › ".join(where), "hint"))

    def mouseReleaseEvent(self, event):
        self.activated.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activated.emit()
        elif event.key() == Qt.Key_Down:
            self.focusNextChild()
        elif event.key() == Qt.Key_Up:
            self.focusPreviousChild()
        else:
            super().keyPressEvent(event)


class SettingsPage(QWidget):
    changed = Signal(dict)  # partial settings to merge and save
    shortcut_changed = Signal(str)
    shortcut_recording = Signal(bool)
    check_updates = Signal()
    rerun_setup = Signal()

    category_shown = Signal(str)  # a category page is in front (the main window marks it in the sidebar)
    searching = Signal()          # search results are in front

    def __init__(self, settings: dict, can_rescan_mics=lambda: False):
        super().__init__()
        self._settings = dict(settings)
        self.rows = []
        self.sections = {}  # section id -> SettingsSection with a "More options" part
        self.pages = {}     # category key -> its scroll area
        self.category = "dictation"
        self._building = ""
        # Lives in the main window's sidebar ("Find a setting"); this page runs the search.
        self.search = SearchField(objectName="search", placeholderText="Find a setting", clearButtonEnabled=True)
        self.search.setAccessibleName("Find a setting")
        self.search.textChanged.connect(self._on_search)
        self.search.submitted.connect(self._open_first_result)
        self.search.down.connect(self._focus_first_result)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self._dictation(settings, can_rescan_mics)
        self._text(settings)
        self._indicator(settings)
        self._app(settings)
        self._updates(settings)
        self._build_results()

        for section_id, section in self.sections.items():
            section.set_expanded(section_id in settings["expanded_sections"])
            section.toggled.connect(self._on_section_toggled)
        self._refresh_changed()
        self._sync_enter_hints(settings["auto_paste"])
        self._refresh_tidy()
        self.show_category("dictation")

    # ----- layout -----

    def _scroll_page(self, crumb_title: str) -> tuple:
        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = Page()
        body.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        body.layout_.setSpacing(8)
        header, title = make_header(crumb_title, "Settings")
        body.layout_.addWidget(header)
        body.layout_.addSpacing(10)
        scroll.setWidget(body)
        self.stack.addWidget(scroll)
        return scroll, body.layout_, title

    def _page(self, key: str) -> QVBoxLayout:
        scroll, layout, _ = self._scroll_page(CATEGORIES[key])
        self.pages[key] = scroll
        self._building = key
        return layout

    def _section(self, page: QVBoxLayout, title: str = "", section_id: str = "") -> SettingsSection:
        section = SettingsSection(title, CATEGORIES[self._building], section_id)
        if page.count() > 2:
            page.addSpacing(18)
        page.addWidget(section)
        if section_id:
            self.sections[section_id] = section
        return section

    def _row(self, section: SettingsSection, title: str, hint: str, control: QWidget, key=None, keywords: str = "",
             badge: str = "", advanced: bool = False) -> SettingRow:
        if isinstance(control, QComboBox):
            control.setMinimumWidth(CONTROL_WIDTH)
        switch = control if isinstance(control, Toggle) else None
        if switch:
            control = switch.with_state_label()
        row = SettingRow(title, hint, control, badge=badge, keywords=keywords, key=key)
        row.focus_widget = switch or control
        row.category = self._building
        section.add(row, advanced)
        self.rows.append(row)
        return row

    def _unavailable(self, *rows: SettingRow):
        for row in rows:
            row.available = False
            row.hide()

    # ----- categories -----

    def _dictation(self, settings: dict, can_rescan_mics):
        page = self._page("dictation")
        keys = self._section(page, "Shortcut")
        self.shortcut = ShortcutButton(settings["hotkey"])
        self.shortcut.captured.connect(self.shortcut_changed)
        self.shortcut.recording.connect(self.shortcut_recording)
        self._row(keys, "Shortcut", "Works in any app", self.shortcut, "hotkey", "hotkey key keyboard push to talk")
        self.shortcut_mode = make_combo(config.SHORTCUT_MODES, settings["shortcut_mode"])
        self.shortcut_mode.currentIndexChanged.connect(
            lambda: self._emit({"shortcut_mode": self.shortcut_mode.currentData()}))
        self.shortcut_mode_row = self._row(keys, "How the shortcut works", " ", self.shortcut_mode, "shortcut_mode",
                                           "hold tap toggle push to talk mode")
        self._shortcut_mode_hint(settings["shortcut_mode"])

        speech = self._section(page, "Speech")
        self.mic = MicCombo(settings["mic_device"], can_rescan_mics)
        self.mic.setMaximumWidth(CONTROL_WIDTH)
        self.mic.currentIndexChanged.connect(lambda: self._emit({"mic_device": self.mic.currentData()}))
        self._row(speech, "Microphone", "", self.mic, "mic_device", "mic input device audio headset")
        self._language(speech, settings)
        page.addStretch(1)

    def _language(self, section: SettingsSection, settings: dict):
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
        self.language.setMinimumWidth(CONTROL_WIDTH)
        self.language.setMaximumWidth(300)
        self.language.currentIndexChanged.connect(lambda: self._emit({"language": self.language.currentData()}))
        language_control = QWidget()
        language_layout = QHBoxLayout(language_control)
        language_layout.setContentsMargins(0, 0, 0, 0)
        language_layout.addWidget(self.language)
        language_control.setFocusProxy(self.language)  # search focuses the row's control
        self._row(section, "Language", "Spoken language, or detect automatically", language_control, "language",
                  "locale spoken english detect")

    def _text(self, settings: dict):
        page = self._page("text")
        section = self._section(page, "Tidy-up")
        self._model = tidy.model_size(settings)
        self._large = True
        self.tidy = Segmented({k: v[0] for k, v in config.TIDY_STYLES.items()}, tidy.style(settings))
        self.tidy.picked.connect(self._on_tidy_style)
        self.tidy_row = self._row(section, "Tidy up my words", " ", self.tidy, "tidy",
                                  "cleanup punctuation capitals grammar ai llm off quick smart")
        self.model_size = Segmented({k: v[0] for k, v in tidy.MODEL_SIZES.items()}, self._model)
        self.model_size.picked.connect(self._on_model_size)
        self.model_size_row = self._row(section, config.MODEL_SIZE_LABEL, " ", self.model_size, "cleanup_model",
                                        "llm qwen ai small large automatic tidy-up model")
        self.cleanup_device = make_combo(config.CLEANUP_DEVICES, settings["cleanup_device"])
        self.cleanup_device.currentIndexChanged.connect(
            lambda: self._emit({"cleanup_device": self.cleanup_device.currentData()}))
        self.device_row = self._row(section, config.DEVICE_LABEL, config.DEVICE_HINT, self.cleanup_device,
                                    "cleanup_device", "gpu cpu graphics card processor device vulkan cuda performance")
        self.corrections = self._toggle(settings["corrections"], "corrections")
        self.corrections_row = self._row(section, config.CORRECTIONS_LABEL, config.CORRECTIONS_HINT, self.corrections,
                                         "corrections", "self-correction correct mistakes no wait")

        typing = self._section(page, "Typing", "typing")
        self.paste = self._toggle(settings["auto_paste"], "auto_paste")
        self._row(typing, "Type into the app I'm using", "Otherwise text is just shown here to copy", self.paste,
                  "auto_paste", "paste auto-paste clipboard insert")
        self.enter_before = self._toggle(settings["press_enter_before"], "press_enter_before")
        self.enter_before_row = self._row(typing, f"Press {ENTER} before pasting", ENTER_HINT, self.enter_before,
                                          "press_enter_before", "return send submit key", "Experimental", True)
        self.enter = self._toggle(settings["press_enter"], "press_enter")
        self.enter_row = self._row(typing, f"Press {ENTER} after pasting", ENTER_HINT, self.enter, "press_enter",
                                   "return send submit key", "Experimental", True)
        self.paste.toggled.connect(self._sync_enter_hints)
        if not platform_utils.IS_WINDOWS:
            self._unavailable(self.enter_row, self.enter_before_row)
        page.addStretch(1)

    def _indicator(self, settings: dict):
        page = self._page("indicator")
        indicator = self._section(page, "Indicator")
        self.overlay = self._toggle(settings["overlay_enabled"], "overlay_enabled")
        self._row(indicator, "Show indicator", "Hidden while Speak's Dictate page is in front", self.overlay,
                  "overlay_enabled", "overlay pill popup floating")
        self.position = make_combo(config.OVERLAY_POSITIONS, settings["overlay_position"])
        self.position.currentIndexChanged.connect(
            lambda: self._emit({"overlay_position": self.position.currentData()}))
        self._row(indicator, "Position", "", self.position, "overlay_position", "overlay cursor top bottom screen")
        self.live = make_combo(config.LIVE_PREVIEWS, settings["live_preview"])
        self.live.currentIndexChanged.connect(lambda: self._emit({"live_preview": self.live.currentData()}))
        self._row(indicator, "Live text", "Words appear under the indicator as you speak", self.live, "live_preview",
                  "preview transcript overlay words")

        sound = self._section(page, "Sound")
        self.audio_dim = self._toggle(settings["audio_dim_enabled"], "audio_dim_enabled", emit=False)
        self.audio_dim_row = self._row(sound, config.AUDIO_DIM_LABEL, f"{config.AUDIO_DIM_HINT}. Changes apply next time",
                                       self.audio_dim, "audio_dim_enabled", "dim system audio volume duck mute music")
        self.audio_dim_level = QWidget()
        level_layout = QHBoxLayout(self.audio_dim_level)
        level_layout.setContentsMargins(0, 0, 0, 0)
        self.audio_dim_slider = QSlider(Qt.Horizontal)
        self.audio_dim_slider.setAccessibleName("Reduce system audio by")
        self.audio_dim_slider.setRange(10, 90)
        self.audio_dim_slider.setSingleStep(config.AUDIO_DIM_STEP)
        self.audio_dim_slider.setPageStep(10)
        self.audio_dim_slider.setValue(settings["audio_dim_percent"])
        self.audio_dim_slider.setMinimumWidth(180)
        self.audio_dim_value = make_label(f'{settings["audio_dim_percent"]}%')
        self.audio_dim_value.setMinimumWidth(42)
        self.audio_dim_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        level_layout.addWidget(self.audio_dim_slider, 1)
        self.audio_dim_level.setFocusProxy(self.audio_dim_slider)
        level_layout.addWidget(self.audio_dim_value)
        self.audio_dim_slider.setEnabled(settings["audio_dim_enabled"])
        self.audio_dim_slider.valueChanged.connect(self._on_audio_dim_changed)
        self.audio_dim_level_row = self._row(sound, "Reduce by", "", self.audio_dim_level, "audio_dim_percent",
                                             "volume percent level")
        self.audio_dim_level_row.setVisible(settings["audio_dim_enabled"])
        if not (platform_utils.IS_WINDOWS or platform_utils.IS_MAC):
            self._unavailable(self.audio_dim_row, self.audio_dim_level_row)
        self.audio_dim.toggled.connect(self._on_audio_dim_toggled)
        page.addStretch(1)

    def _app(self, settings: dict):
        page = self._page("app")
        general = self._section(page, "General")
        self.theme = make_combo({t: t for t in config.THEMES}, settings["theme"])
        self.theme.currentIndexChanged.connect(lambda: self._emit({"theme": self.theme.currentData()}))
        self._row(general, "Appearance", "", self.theme, "theme", "theme dark light mode colour color")
        self.login = Toggle()
        try:
            self.login.setChecked(platform_utils.launch_at_login_enabled())
        except Exception:
            self.login.setEnabled(False)
        self.login.toggled.connect(self._on_login)
        self._row(general, "Open at login" if platform_utils.IS_MAC else "Start with my computer",
                  f"Runs quietly in the {platform_utils.TRAY_NAME}", self.login, None,
                  "login startup boot autostart launch")
        self.close_action = make_combo(config.CLOSE_ACTIONS, settings["close_action"])
        self.close_action.currentIndexChanged.connect(
            lambda: self._emit({"close_action": self.close_action.currentData()}))
        self._row(general, "When I close the window", "", self.close_action, "close_action",
                  "tray menu bar quit exit minimise minimize")
        setup = QPushButton("Run setup", cursor=Qt.PointingHandCursor)
        setup.clicked.connect(self.rerun_setup)
        self._row(general, "First-run setup", "Re-pick your microphone and test dictation speed", setup, None,
                  "onboarding wizard welcome speed test")

        data = self._section(page, "History & storage")
        self.history = self._toggle(settings["history_enabled"], "history_enabled")
        self._row(data, "Keep history", "Saved only on this device", self.history, "history_enabled",
                  "transcripts privacy save past")
        self.unload = make_combo(config.UNLOAD_AFTER, settings["unload_after"])
        self.unload.currentIndexChanged.connect(lambda: self._emit({"unload_after": self.unload.currentData()}))
        self._row(data, "Free up memory when idle",
                  "Unloads the speech and tidy-up models (1 to 4 GB). The next dictation then takes a few seconds "
                  "to start", self.unload, "unload_after", "unload ram vram idle performance")
        folder = QPushButton("Open", cursor=Qt.PointingHandCursor)
        folder.clicked.connect(lambda: (config.APP_DIR.mkdir(parents=True, exist_ok=True),
                                        platform_utils.open_path(config.APP_DIR)))
        self._row(data, "Data folder", "Models, logs and settings", folder, None, "files logs models location")
        page.addStretch(1)

    def _updates(self, settings: dict):
        page = self._page("updates")
        section = self._section(page)
        self.updates = make_combo(config.UPDATE_MODES, settings["updates"])
        self.updates.currentIndexChanged.connect(lambda: self._emit({"updates": self.updates.currentData()}))
        self.updates_row = self._row(section, "When there's an update", " ", self.updates, "updates",
                                     "updates auto install check")
        self._last_check = None
        version = QWidget()
        line = QHBoxLayout(version)
        line.setContentsMargins(0, 0, 0, 0)
        self.update_status = make_label("", "hint")
        self.update_status.setWordWrap(False)
        check = QPushButton("Check now", cursor=Qt.PointingHandCursor)
        check.clicked.connect(self.check_updates)
        check.setEnabled(updates.updatable())
        line.addWidget(self.update_status)
        line.addWidget(check)
        version.setFocusProxy(check)
        self.prereleases = self._toggle(settings["prereleases"], "prereleases")
        self._row(section, config.PRERELEASES_LABEL,
                  f"{config.PRERELEASES_HINT}. Always on while you run a pre-release",
                  self.prereleases, "prereleases", "pre-release beta preview")
        self._row(section, "Version", updates.display() + ("" if updates.updatable() else " (doesn't update)"),
                  version, None, "about release check now")
        self._update_hint(settings["updates"])
        page.addStretch(1)

    def _build_results(self):
        self.results_page, layout, self.results_title = self._scroll_page("")
        layout.setSpacing(2)
        self.results_layout = QVBoxLayout()
        self.results_layout.setSpacing(2)
        layout.addLayout(self.results_layout)
        self.no_results = make_label("", "muted")
        layout.addWidget(self.no_results)
        layout.addStretch(1)
        self.results = []

    # ----- navigation and search -----

    def show_category(self, key: str):
        self.category = key
        self.clear_search()
        self.stack.setCurrentWidget(self.pages[key])
        self.category_shown.emit(key)

    def clear_search(self):
        """Empty the search and put the current category back in front of any results, without signalling."""
        if self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        self.stack.setCurrentWidget(self.pages[self.category])

    def row_for(self, key: str) -> SettingRow:
        return next(r for r in self.rows if r.key == key)

    def focus_search(self):
        self.search.setFocus(Qt.ShortcutFocusReason)
        self.search.selectAll()

    def matches(self, query: str) -> list:
        """Rows whose title, hint, keywords, section or category contain every word of `query`, title hits first."""
        terms = query.lower().split()
        if not terms:
            return []
        found = [r for r in self.rows if r.available and not explicitly_hidden(r)
                 and all(t in r.search_text() for t in terms)]
        return sorted(found, key=lambda r: not all(t in r.title.lower() for t in terms))

    def _on_search(self, text: str):
        for result in self.results:
            result.hide()
            result.deleteLater()
        self.results = []
        if not text.strip():
            self.show_category(self.category)
            return
        found = self.matches(text)
        for row in found:
            result = SearchResult(row)
            result.activated.connect(lambda r=row: self.reveal(r))
            self.results_layout.addWidget(result)
            self.results.append(result)
        self.results_title.setText(f"{len(found)} result{'' if len(found) == 1 else 's'}" if found else "No results")
        self.no_results.setText(f"No settings match “{text.strip()}”. Try a different word." if not found else "")
        self.no_results.setVisible(not found)
        self.stack.setCurrentWidget(self.results_page)
        self.searching.emit()

    def _open_first_result(self):
        if self.results:
            self.reveal(self.results[0].row)

    def _focus_first_result(self):
        if self.results:
            self.results[0].setFocus(Qt.TabFocusReason)

    def reveal(self, row: SettingRow):
        """Open the row's category (and its section's More options), scroll it into view and flash it."""
        self.show_category(row.category)
        if row.advanced and not row.section.expanded:
            row.section.set_expanded(True)
        scroll = self.pages[row.category]
        row.focus_widget.setFocus(Qt.OtherFocusReason)

        def land():
            scroll.ensureWidgetVisible(row, 0, 48)
            row.flash()
        QTimer.singleShot(0, land)

    # ----- state -----

    def _emit(self, changes: dict):
        self._settings.update(changes)
        self._refresh_changed()
        self.changed.emit(changes)

    def _refresh_changed(self):
        for section in self.sections.values():
            section.set_changed(sum(1 for r in section.rows if r.advanced and r.available and r.key
                                    and self._settings.get(r.key) != config.DEFAULTS.get(r.key)))

    def _on_section_toggled(self, _open: bool):
        self._emit({"expanded_sections": sorted(k for k, s in self.sections.items() if s.expanded)})

    def _sync_enter_hints(self, auto_paste: bool):
        for row in (self.enter_row, self.enter_before_row):
            row.control.setEnabled(auto_paste)
            row.hint.setText(ENTER_HINT if auto_paste else ENTER_OFF_HINT)

    def set_update_status(self, text: str):
        self.update_status.setText(text)

    def set_last_check(self, when):
        self._last_check = when
        self._update_hint(self.updates.currentData())

    def _update_hint(self, mode: str):
        hint = "Never checks. Use Check now below" if mode == "off" else config.UPDATE_MODE_HINTS[mode]
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
        self._large = large_model
        self._refresh_tidy()

    def _on_tidy_style(self, key: str):
        self._emit({"tidy": key} if key != "ai" else tidy.ai_changes(self._model))
        self._refresh_tidy()

    def _on_model_size(self, size: str):
        self._model = size
        self._emit(tidy.ai_changes(size))
        self._refresh_tidy()

    def _refresh_tidy(self):
        """Same rules as first-run setup: model size and device only apply to Smart, corrections need Large."""
        settings = self._settings
        on = tidy.style(settings) == "ai"
        fix = on and self._large
        self.tidy.set_value(tidy.style(settings))
        self.model_size.set_value(self._model if on else "")
        self.model_size.setEnabled(on)
        self.model_size_row.hint.setText(tidy.model_size_hint(settings, self._model) if on else config.TIDY_NOT_USED)
        self.cleanup_device.setEnabled(on)
        self.device_row.hint.setText(config.DEVICE_HINT if on else config.TIDY_NOT_USED)
        self.corrections.setEnabled(fix)
        self.corrections_row.hint.setText(
            config.CORRECTIONS_HINT if fix else config.CORRECTIONS_NEEDS_LARGE if on else config.TIDY_NOT_USED)
        self.corrections.blockSignals(True)  # what can't apply reads as off
        self.corrections.setChecked(bool(settings["corrections"]) and fix)
        self.corrections.blockSignals(False)

    def _shortcut_mode_hint(self, mode: str):
        self.shortcut_mode_row.hint.setText(config.SHORTCUT_MODE_HINTS[mode])

    def _toggle(self, value: bool, key: str, emit: bool = True) -> Toggle:
        toggle = Toggle()
        toggle.setChecked(value)
        if emit:
            toggle.toggled.connect(lambda on: self._emit({key: on}))
        return toggle

    def _on_audio_dim_toggled(self, enabled: bool):
        self.audio_dim_slider.setEnabled(enabled)
        if self.audio_dim_row.available:
            self.audio_dim_level_row.setVisible(enabled)
        self._emit({"audio_dim_enabled": enabled})

    def _on_audio_dim_changed(self, percent: int):
        percent = config.snap_audio_dim_percent(percent)
        if self.audio_dim_slider.value() != percent:
            self.audio_dim_slider.setValue(percent)
            return
        self.audio_dim_value.setText(f"{percent}%")
        self._emit({"audio_dim_percent": percent})

    def set_palette(self, palette):
        for widget in self.findChildren(QWidget):
            if hasattr(widget, "palette_"):
                widget.palette_ = palette
                widget.update()
        self.language_delegate.muted = QColor(palette.muted)

    def sync(self, settings: dict):
        """Reflect settings changed elsewhere (e.g. first-close prompt, history page)."""
        self._settings = dict(settings)
        for widget, value in ((self.close_action, settings["close_action"]),
                              (self.cleanup_device, settings["cleanup_device"]),
                              (self.shortcut_mode, settings["shortcut_mode"]),
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
        self.mic.set_device(settings["mic_device"])
        for toggle, value in ((self.history, settings["history_enabled"]),
                              (self.prereleases, settings["prereleases"]),
                              (self.paste, settings["auto_paste"]),
                              (self.enter, settings["press_enter"]),
                              (self.enter_before, settings["press_enter_before"]),
                              (self.overlay, settings["overlay_enabled"]),
                              (self.audio_dim, settings["audio_dim_enabled"])):
            toggle.blockSignals(True)
            toggle.setChecked(value)
            toggle.blockSignals(False)
        self.audio_dim_slider.blockSignals(True)
        self.audio_dim_slider.setValue(settings["audio_dim_percent"])
        self.audio_dim_slider.blockSignals(False)
        self.audio_dim_slider.setEnabled(settings["audio_dim_enabled"])
        if self.audio_dim_row.available:
            self.audio_dim_level_row.setVisible(settings["audio_dim_enabled"])
        self.audio_dim_value.setText(f'{settings["audio_dim_percent"]}%')
        self._sync_enter_hints(settings["auto_paste"])
        self._update_hint(settings["updates"])
        self._shortcut_mode_hint(settings["shortcut_mode"])
        if tidy.style(settings) == "ai":
            self._model = tidy.model_size(settings)
        self._refresh_tidy()
        self._refresh_changed()

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

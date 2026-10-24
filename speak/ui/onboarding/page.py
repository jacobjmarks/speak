from .steps.welcome import WelcomeStep
from .steps.theme import ThemeStep
from .steps.mic import MicStep
from .steps.keys import KeysStep
from .steps.tidy import TidyStep
from .steps.look import LookStep
from .steps.updates import UpdatesStep
from .steps.done import DoneStep
from .common import COLUMN_WIDTH, Revealer, SHORTCUT_HINTS, _model_choice
from .widgets import OptionGroup, StepDots
from . import common
from PySide6.QtCore import QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget
from ... import config, hotkey, tidy
from .. import theme
from ..pages import Page, _label

class OnboardingPage(Page, WelcomeStep, ThemeStep, MicStep, KeysStep, TidyStep, LookStep, UpdatesStep, DoneStep):
    """Settings are emitted through `changed` as they're picked, like the Settings page.

    `test_requested(pcm, rate)` asks the app to time the pipeline (`pcm` is None for the bundled sample);
    `test_cancelled` asks it to stop one that is running, e.g. because a setting changed under it.
    """
    changed = Signal(dict)
    skipped = Signal()
    finished = Signal()
    test_requested = Signal(object, int)
    test_cancelled = Signal()
    shortcut_recording = Signal(bool)
    WELCOME, THEME, MIC, KEYS, TIDY, LOOK, APP, DONE = range(8)
    SPEED_IDLE = ""

    def __init__(self, settings: dict, can_rescan_mics=lambda: False, logo: QWidget = None):
        super().__init__()
        self.layout_.setContentsMargins(56, 24, 56, 28)
        self.layout_.setSpacing(0)
        self.palette_ = theme.LIGHT
        self._mic = None
        self._heard = False
        self._testing = False   # a speed test is running in the app
        self._tested = False
        self._level = 0.0
        self._out = None
        self._reveals = {}
        self._revealer = Revealer()
        self._tidy = {k: settings[k] for k in ("tidy", "cleanup_model", "cleanup_device", "corrections")}
        self._model = _model_choice(settings)
        self._poll = QTimer(self, interval=60, timeout=self._read_level)
        self._retest = QTimer(self, singleShot=True, interval=900, timeout=self._retest_now)

        top = QHBoxLayout()
        top.addStretch(1)
        self.skip_button = QPushButton("Skip setup", objectName="ghost", cursor=Qt.PointingHandCursor)
        self.skip_button.clicked.connect(self.skipped)
        top.addWidget(self.skip_button)
        self.layout_.addLayout(top)

        self.steps = QStackedWidget()
        self.steps.addWidget(self._welcome_step(logo))
        self.steps.addWidget(self._theme_step(settings))
        self.steps.addWidget(self._mic_step(settings, can_rescan_mics))
        self.steps.addWidget(self._keys_step(settings))
        self.steps.addWidget(self._tidy_step(settings))
        self.steps.addWidget(self._look_step(settings))
        self.steps.addWidget(self._app_step(settings))
        self.steps.addWidget(self._done_step(settings))
        self.layout_.addWidget(self.steps, 1)

        self.bar = QWidget()
        bar = QHBoxLayout(self.bar)
        bar.setContentsMargins(0, 8, 0, 0)
        self.back_button = QPushButton("Back", objectName="ghost", cursor=Qt.PointingHandCursor)
        self.back_button.clicked.connect(lambda: self.go(self.steps.currentIndex() - 1))
        self.dots = StepDots(self.APP - self.THEME + 1)
        self.next_button = QPushButton("Next", objectName="primary", cursor=Qt.PointingHandCursor)
        self.next_button.setProperty("size", "large")
        self.next_button.clicked.connect(lambda: self.go(self.steps.currentIndex() + 1))
        bar.addWidget(self.back_button, 1, Qt.AlignLeft)
        bar.addWidget(self.dots, 0, Qt.AlignCenter)
        bar.addWidget(self.next_button, 1, Qt.AlignRight)
        self.layout_.addWidget(self.bar)
        self.set_gpus(tidy.gpus(), settings["cleanup_device"])
        self._refresh_tidy()
        self._show(0, animate=False)


    def _step(self) -> tuple:
        """(step, column layout): every screen is one centered column."""
        step = QWidget()
        outer = QHBoxLayout(step)
        outer.setContentsMargins(0, 0, 0, 0)
        column = QWidget()
        column.setMaximumWidth(COLUMN_WIDTH)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        outer.addStretch(1)
        outer.addWidget(column, 100)
        outer.addStretch(1)
        return step, layout


    def _heading(self, text: str, lead: str = "") -> tuple:
        heading = _label(text, "heading")
        heading.setAlignment(Qt.AlignCenter)
        if not lead:
            return heading, None
        sub = _label(lead, "lead")
        sub.setAlignment(Qt.AlignCenter)
        return heading, sub


    def _row(self, *widgets, spacing: int = 14) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing)
        for widget in widgets:
            row.addWidget(widget)
        return box


    def _cards(self, group: OptionGroup, cards: dict, on_pick) -> QWidget:
        row = QHBoxLayout()
        row.setSpacing(14)
        holder = QWidget()
        holder.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        for key, card in cards.items():
            group.add(key, card)
            row.addWidget(card)
        group.picked.connect(on_pick)
        return holder


    def _settings_card(self, *rows: QWidget) -> QFrame:
        card = QFrame(objectName="card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 4, 22, 4)
        layout.setSpacing(0)
        for i, row in enumerate(rows):
            if i:
                layout.addWidget(QFrame(objectName="divider"))
            layout.addWidget(row)
        return card


    def go(self, index: int):
        index = max(0, min(index, self.DONE))
        if index == self.steps.currentIndex():
            return
        if self._out is not None and self._out.state() == QPropertyAnimation.Running:
            return
        if not (common.ANIMATE and self.isVisible()):
            self._show(index, animate=False)
            return
        self._revealer.stop()
        step = self.steps.currentWidget()
        effect = QGraphicsOpacityEffect(step)
        step.setGraphicsEffect(effect)
        self._out = QPropertyAnimation(effect, b"opacity", step, duration=150, startValue=1.0, endValue=0.0)
        self._out.finished.connect(lambda: (step.setGraphicsEffect(None), self._show(index, animate=True)))
        self._out.start()


    def _show(self, index: int, animate: bool):
        self._stop_monitor()
        if index != self.TIDY:
            self._cancel_test()
        self.steps.setCurrentIndex(index)
        counted = self.THEME <= index <= self.APP
        self.bar.setVisible(counted)
        self.skip_button.setVisible(index != self.DONE)
        self.back_button.setVisible(index > self.THEME)
        if counted:
            self.dots.set_current(index - self.THEME)
        if index == self.MIC and self.isVisible():
            self._start_monitor()
        if index == self.DONE and common.ANIMATE and self.isVisible():
            QTimer.singleShot(250, self.burst.play)
        self.ambient.set_animating(index == self.WELCOME and self.isVisible())
        if animate:
            self._revealer.play(self._reveals[index], self.steps.widget(index))


    def reset(self):
        """Back to the welcome screen with a clean test, e.g. when setup is re-run from Settings."""
        self._cancel_test()
        self._heard = False
        self.pulse.set_heard(False)
        self._revealer.stop()
        self._show(0, animate=False)


    def showEvent(self, event):
        super().showEvent(event)
        index = self.steps.currentIndex()
        if index == self.MIC:
            self._start_monitor()
        self.ambient.set_animating(index == self.WELCOME)
        self._revealer.play(self._reveals[index], self.steps.currentWidget())


    def hideEvent(self, event):
        super().hideEvent(event)
        self._stop_monitor()
        self._cancel_test()
        self._revealer.stop()
        self.ambient.set_animating(False)


    def set_shortcut(self, combo: str, mode: str):
        self.keycap.setText(hotkey.display(combo))
        self.shortcut_hint.setText(SHORTCUT_HINTS.get(mode, ""))


    def set_tidy_summary(self, summary: str, large_model: bool):
        self._refresh_tidy()


    def set_gpus(self, gpus: list, current: str):
        combo = self.device
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
        if hasattr(self, "model_row"):
            self._refresh_tidy()


    def sync(self, settings: dict):
        """Reflect settings changed elsewhere (the app echoes every change back)."""
        self._tidy.update({k: settings[k] for k in self._tidy})
        if settings["tidy"] in ("auto", "best"):
            self._model = _model_choice(settings)
        self.device.blockSignals(True)
        self.device.setCurrentIndex(max(0, self.device.findData(settings["cleanup_device"])))
        self.device.blockSignals(False)
        self.corrections.blockSignals(True)
        self.corrections.setChecked(settings["corrections"])
        self.corrections.blockSignals(False)
        self._refresh_tidy()
        self.live_options.set_value(settings["live_preview"])
        self.position_options.set_value(settings["overlay_position"])
        self.stage.set_options(settings["live_preview"], settings["overlay_position"])
        self.mode_options.set_value(settings["shortcut_mode"])
        self.theme_options.set_value(settings["theme"])
        self.updates_options.set_value(settings["updates"])
        self.prereleases.blockSignals(True)
        self.prereleases.setChecked(settings["prereleases"])
        self.prereleases.blockSignals(False)
        self.shortcut.set_combo(settings["hotkey"])
        for widget, setter, value in ((self.dim_toggle, "setChecked", settings["audio_dim_enabled"]),
                                      (self.dim_slider, "setValue", settings["audio_dim_percent"])):
            widget.blockSignals(True)
            getattr(widget, setter)(value)
            widget.blockSignals(False)
        self.dim_slider.setEnabled(settings["audio_dim_enabled"])
        self.dim_value.setText(f'{settings["audio_dim_percent"]}%')
        self.set_shortcut(settings["hotkey"], settings["shortcut_mode"])


    def set_palette(self, palette):
        self.palette_ = palette
        for widget in self.findChildren(QWidget):
            if hasattr(widget, "palette_"):
                widget.palette_ = palette
                widget.update()

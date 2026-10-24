from ..common import SHORTCUT_HINTS
from ..widgets import ChoiceCard, ModeGlyph, OptionGroup
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSlider, QWidget
from .... import config, system_audio
from ...pages import SettingRow, _label
from ...widgets import ShortcutButton, Toggle

class KeysStep:
    def _keys_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.setSpacing(14)
        heading, _ = self._heading("Your shortcut")
        layout.addWidget(heading)
        self.shortcut = ShortcutButton(settings["hotkey"])
        self.shortcut.setProperty("size", "large")
        self.shortcut.setMinimumWidth(200)
        self.shortcut.captured.connect(lambda combo: self.changed.emit({"hotkey": combo}))
        self.shortcut.recording.connect(self.shortcut_recording)
        change_hint = _label("Click to change it", "hint")
        change_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.shortcut, 0, Qt.AlignHCenter)
        layout.addWidget(change_hint)
        layout.addSpacing(6)

        self.mode_options = OptionGroup(self)
        # Hold and tap first, so "Hold or tap" reads as the combination of the two.
        cards = {key: ChoiceCard(config.SHORTCUT_MODES[key], SHORTCUT_HINTS[key], visual=ModeGlyph(key))
                 for key in ("hold", "toggle", "auto")}
        self.mode_cards = list(cards.values())
        self.mode_options.set_value(settings["shortcut_mode"])
        modes = self._cards(self.mode_options, cards, lambda key: self.changed.emit({"shortcut_mode": key}))
        self.mode_options.set_value(settings["shortcut_mode"])
        layout.addWidget(modes)
        layout.addSpacing(6)

        self.dim_toggle = Toggle()
        self.dim_toggle.setChecked(settings["audio_dim_enabled"])
        self.dim_toggle.toggled.connect(self._on_dim_toggled)
        dim_row = SettingRow("Quiet other sounds while I talk", "Lowers music and videos, then restores them",
                             self.dim_toggle)
        self.dim_slider = QSlider(Qt.Horizontal)
        self.dim_slider.setAccessibleName("Reduce system audio by")
        self.dim_slider.setRange(10, 90)
        self.dim_slider.setSingleStep(config.AUDIO_DIM_STEP)
        self.dim_slider.setPageStep(10)
        self.dim_slider.setValue(settings["audio_dim_percent"])
        self.dim_slider.setEnabled(settings["audio_dim_enabled"])
        self.dim_slider.valueChanged.connect(self._on_dim_changed)
        self.dim_value = QLabel(f'{settings["audio_dim_percent"]}%')
        self.dim_value.setMinimumWidth(42)
        self.dim_slider.setMinimumWidth(240)
        self.dim_level_row = SettingRow("Reduce by", "", self._row(self.dim_slider, self.dim_value, spacing=10))
        self.dim_card = self._settings_card(dim_row, self.dim_level_row)
        self.dim_card.setVisible(system_audio.SUPPORTED)
        layout.addWidget(self.dim_card)
        layout.addStretch(1)
        self._reveals[self.KEYS] = [heading, self.shortcut, change_hint, *self.mode_cards, self.dim_card]
        return step


    def _on_dim_toggled(self, on: bool):
        self.dim_slider.setEnabled(on)
        self.changed.emit({"audio_dim_enabled": on})


    def _on_dim_changed(self, percent: int):
        percent = config.snap_audio_dim_percent(percent)
        if self.dim_slider.value() != percent:
            self.dim_slider.setValue(percent)
            return
        self.dim_value.setText(f"{percent}%")
        self.changed.emit({"audio_dim_percent": percent})

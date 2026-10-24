from ..widgets import ChoiceCard, OptionGroup, ThemeSwatch
from PySide6.QtWidgets import QWidget
from .... import config

class ThemeStep:
    def _theme_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.setSpacing(16)
        layout.addStretch(1)
        heading, _ = self._heading("Pick your look")
        layout.addWidget(heading)
        layout.addSpacing(6)
        self.theme_options = OptionGroup(self)
        cards = {name: ChoiceCard(name, visual=ThemeSwatch(name)) for name in config.THEMES}
        self.theme_cards = list(cards.values())
        layout.addWidget(self._cards(self.theme_options, cards, lambda key: self.changed.emit({"theme": key})))
        self.theme_options.set_value(settings["theme"])
        layout.addStretch(2)
        self._reveals[self.THEME] = [heading, *self.theme_cards]
        return step

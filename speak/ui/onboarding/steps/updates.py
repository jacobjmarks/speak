from ..common import UPDATE_HINTS
from ..widgets import ChoiceCard, OptionGroup
from PySide6.QtWidgets import QWidget
from .... import config
from ...pages import SettingRow
from ...widgets import Toggle

class UpdatesStep:
    def _app_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.setSpacing(16)
        layout.addStretch(1)
        heading, _ = self._heading("Stay up to date")
        layout.addWidget(heading)
        layout.addSpacing(6)
        self.updates_options = OptionGroup(self)
        cards = {key: ChoiceCard(label, UPDATE_HINTS[key]) for key, label in config.UPDATE_MODES.items()}
        for card in cards.values():
            card.setMinimumHeight(110)
        self.update_cards = list(cards.values())
        layout.addWidget(self._cards(self.updates_options, cards, lambda key: self.changed.emit({"updates": key})))
        self.updates_options.set_value(settings["updates"])
        self.prereleases = Toggle()
        self.prereleases.setChecked(settings["prereleases"])
        self.prereleases.toggled.connect(lambda on: self.changed.emit({"prereleases": on}))
        self.prerelease_card = self._settings_card(
            SettingRow("Try new versions early", "They arrive sooner and may have bugs", self.prereleases))
        layout.addWidget(self.prerelease_card)
        layout.addStretch(2)
        self._reveals[self.APP] = [heading, *self.update_cards, self.prerelease_card]
        return step

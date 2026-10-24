from ..widgets import Segmented
from ..stages import OverlayStage
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from .... import config
from ...pages import _label

class LookStep:
    def _look_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.setSpacing(14)
        heading, _ = self._heading("Your on-screen indicator")
        layout.addWidget(heading)
        self.stage = OverlayStage()
        self.stage.set_options(settings["live_preview"], settings["overlay_position"])
        layout.addWidget(self.stage)

        self.live_options = Segmented(config.LIVE_PREVIEWS, settings["live_preview"])
        self.live_options.picked.connect(lambda key: self._on_overlay({"live_preview": key}))
        self.position_options = Segmented(config.OVERLAY_POSITIONS, settings["overlay_position"])
        self.position_options.picked.connect(lambda key: self._on_overlay({"overlay_position": key}))
        controls = []
        for caption, chips in (("Live text", self.live_options), ("Position", self.position_options)):
            box = QWidget()
            col = QVBoxLayout(box)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(6)
            label = _label(caption, "section")
            label.setAlignment(Qt.AlignCenter)
            col.addWidget(label)
            col.addWidget(chips, 0, Qt.AlignHCenter)
            controls.append(box)
        row = self._row(*controls, spacing=48)
        layout.addWidget(row, 0, Qt.AlignHCenter)
        layout.addStretch(1)
        self._reveals[self.LOOK] = [heading, self.stage, row]
        return step


    def _on_overlay(self, change: dict):
        self.stage.set_options(change.get("live_preview", self.stage.live),
                               change.get("overlay_position", self.stage.position))
        self.changed.emit(change)

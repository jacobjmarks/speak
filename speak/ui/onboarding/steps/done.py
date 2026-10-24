from ..widgets import CheckBurst
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QWidget
from ...pages import _label

class DoneStep:
    def _done_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.addStretch(2)
        self.burst = CheckBurst()
        layout.addWidget(self.burst, 0, Qt.AlignHCenter)
        heading = _label("You're all set", "display")
        heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(heading)
        self.keycap = QLabel("", objectName="keycap")
        self.keycap.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.keycap, 0, Qt.AlignHCenter)
        self.shortcut_hint = _label("", "lead")
        self.shortcut_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.shortcut_hint)
        layout.addSpacing(8)
        go = QPushButton("Finish", objectName="primary", cursor=Qt.PointingHandCursor)
        go.setProperty("size", "large")
        go.clicked.connect(self.finished)
        layout.addWidget(go, 0, Qt.AlignHCenter)
        layout.addSpacing(6)
        self.more_note = _label("More settings, including advanced options, are on the Settings page.", "hint")
        self.more_note.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.more_note)
        layout.addStretch(3)
        self.set_shortcut(settings["hotkey"], settings["shortcut_mode"])
        self._reveals[self.DONE] = [self.burst, heading, self.keycap, self.shortcut_hint, go, self.more_note]
        return step

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget
from ...pages import _label
from ...widgets import WaveStrip

class WelcomeStep:
    def _welcome_step(self, logo) -> QWidget:
        step, layout = self._step()
        layout.addStretch(2)
        self.logo = logo if logo is not None else QWidget()
        layout.addWidget(self.logo, 0, Qt.AlignHCenter)
        layout.addSpacing(10)
        title = _label("Speak", "display")
        title.setAlignment(Qt.AlignCenter)
        lead = _label("Hold a key and talk.\nYour words appear wherever you're typing.", "lead")
        lead.setAlignment(Qt.AlignCenter)
        self.ambient = WaveStrip(lambda: 0.0)
        self.ambient.set_state("processing", "")
        start = QPushButton("Get started", objectName="primary", cursor=Qt.PointingHandCursor)
        start.setProperty("size", "large")
        start.clicked.connect(lambda: self.go(self.THEME))
        layout.addWidget(title)
        layout.addWidget(lead)
        layout.addSpacing(8)
        layout.addWidget(self.ambient, 0, Qt.AlignHCenter)
        layout.addSpacing(8)
        layout.addWidget(start, 0, Qt.AlignHCenter)
        layout.addStretch(3)
        self._reveals[self.WELCOME] = [self.logo, title, lead, self.ambient, start]
        return step

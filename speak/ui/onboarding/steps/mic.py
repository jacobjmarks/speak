from ..common import HEARD_LEVEL
from ..widgets import MicPulse
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget
from .... import audio
from ...pages import MicCombo, _label

class MicStep:
    def _mic_step(self, settings: dict, can_rescan_mics) -> QWidget:
        step, layout = self._step()
        heading, _ = self._heading("Pick your microphone")
        layout.addWidget(heading)
        layout.addStretch(1)
        self.pulse = MicPulse(lambda: self._level)
        layout.addWidget(self.pulse, 0, Qt.AlignHCenter)
        self.mic_status = _label("Say something", "lead")
        self.mic_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.mic_status)
        self.mic_combo = MicCombo(settings["mic_device"], can_rescan_mics)
        self.mic_combo.setMinimumWidth(320)
        self.mic_combo.currentIndexChanged.connect(self._on_mic_changed)
        self.retry_button = QPushButton("Try again", objectName="ghost", cursor=Qt.PointingHandCursor)
        self.retry_button.clicked.connect(self._start_monitor)
        # Takes its space while hidden so the picker above doesn't jump when it appears.
        self.retry_button.setSizePolicy(self.retry_button.sizePolicy().horizontalPolicy(),
                                        QSizePolicy.Fixed)
        policy = self.retry_button.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.retry_button.setSizePolicy(policy)
        self.retry_button.hide()
        layout.addWidget(self.mic_combo, 0, Qt.AlignHCenter)
        layout.addWidget(self.retry_button, 0, Qt.AlignHCenter)
        layout.addStretch(2)
        self._reveals[self.MIC] = [heading, self.pulse, self.mic_status, self.mic_combo, self.retry_button]
        return step


    def _on_mic_changed(self):
        self.changed.emit({"mic_device": self.mic_combo.currentData()})
        if self.steps.currentIndex() == self.MIC and self.isVisible():
            self._start_monitor()


    def _start_monitor(self):
        """(Re)start listening on the chosen device with a fresh check."""
        self._stop_monitor()
        self._heard = False
        self.pulse.set_heard(False)
        self.mic_status.setText("Say something")
        self.retry_button.hide()
        try:
            self._mic = audio.Microphone(lambda chunk: None, self.mic_combo.currentData())
            self._mic.start()
        except Exception:
            self._mic = None
            self.mic_status.setText("Couldn't open this microphone. Try another.")
            self.retry_button.show()
            return
        self.pulse.set_active(True)
        self._poll.start()
        self._read_level()


    def _stop_monitor(self):
        mic, self._mic = self._mic, None
        if mic is not None:
            mic.stop()
        self.pulse.set_active(False)
        self._poll.stop()
        self._level = 0.0


    def _read_level(self):
        self._level = self._mic.level if self._mic is not None else 0.0
        if self._mic is not None and not self._heard and self._level >= HEARD_LEVEL:
            self._heard = True
            self.retry_button.show()
            self.pulse.set_heard(True)
            self.mic_status.setText("Got you")

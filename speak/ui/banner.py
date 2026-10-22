"""In-window notices: errors, missing permissions, updates. One strip above the pages, newest important one first."""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

PRIORITY = {"error": 2, "info": 1}


class Banner(QFrame):
    """Notices are keyed so a later call replaces the earlier one (e.g. download progress).

    `timeout` seconds auto-dismisses; 0 keeps it until `clear(key)` or the user closes it.
    """

    action_clicked = Signal(str)  # key of the notice whose button was pressed

    def __init__(self):
        super().__init__(objectName="banner")
        self._notices = {}  # key -> dict, in update order
        self._shown = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 8, 10)
        layout.setSpacing(12)
        self._text = QLabel()
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.NoTextInteraction)
        layout.addWidget(self._text, 1)
        self._action = QPushButton(objectName="primary", cursor=Qt.PointingHandCursor)
        self._action.clicked.connect(lambda: self._shown and self.action_clicked.emit(self._shown))
        layout.addWidget(self._action)
        close = QPushButton("\u2715", objectName="ghost", cursor=Qt.PointingHandCursor, toolTip="Dismiss")
        close.clicked.connect(lambda: self._shown and self.clear(self._shown))
        layout.addWidget(close)
        self.hide()

    def show_notice(self, key: str, text: str, level: str = "info", action: str = "", enabled: bool = True,
                    timeout: float = 0.0) -> None:
        old = self._notices.pop(key, None)
        if old is not None:
            old["timer"].stop()
        timer = QTimer(self, singleShot=True, timeout=lambda: self.clear(key))
        if timeout:
            timer.start(int(timeout * 1000))
        self._notices[key] = {"text": text, "level": level, "action": action, "enabled": enabled, "timer": timer}
        self._render()

    def clear(self, key: str) -> None:
        notice = self._notices.pop(key, None)
        if notice is not None:
            notice["timer"].stop()
            self._render()

    def _render(self) -> None:
        if not self._notices:
            self._shown = None
            self.hide()
            return
        key = max(reversed(list(self._notices)), key=lambda k: PRIORITY.get(self._notices[k]["level"], 0))
        notice = self._notices[key]
        self._shown = key
        self._text.setText(notice["text"])
        self._action.setText(notice["action"])
        self._action.setVisible(bool(notice["action"]))
        self._action.setEnabled(notice["enabled"])
        self.setProperty("level", notice["level"])
        self.style().unpolish(self)
        self.style().polish(self)
        self.show()

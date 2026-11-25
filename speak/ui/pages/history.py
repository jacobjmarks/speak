"""History page: opt-in transcript list grouped by day; click an entry to copy it. Clearing asks first, inline."""
from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ... import history, output
from ..controls import Page, make_label


class HistoryEntry(QFrame):
    def __init__(self, when: str, text: str):
        super().__init__(objectName="entry", cursor=Qt.PointingHandCursor)
        self.text = text
        self.setToolTip("Click to copy")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(3)
        self.when = make_label(when, "hint")
        self._when_text = when
        layout.addWidget(self.when)
        body = make_label(text)
        body.setTextInteractionFlags(Qt.NoTextInteraction)
        layout.addWidget(body)

    def mouseReleaseEvent(self, e):
        output.copy(self.text)
        self.when.setText("Copied ✓")
        QTimer.singleShot(1000, self, lambda: self.when.setText(self._when_text))


def day_label(day: date, today: date) -> str:
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return f"{day:%A} {day.day} {day:%B}" + ("" if day.year == today.year else f" {day.year}")


class HistoryPage(Page):
    open_settings = Signal()

    def __init__(self):
        super().__init__()
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(make_label("History", "title"), 1)
        self.clear_button = QPushButton("Clear all", objectName="danger", cursor=Qt.PointingHandCursor)
        self.clear_button.clicked.connect(lambda: self._confirming(True))
        header.addWidget(self.clear_button)
        self.confirm = QWidget()
        confirm = QHBoxLayout(self.confirm)
        confirm.setContentsMargins(0, 0, 0, 0)
        confirm.setSpacing(8)
        confirm.addWidget(make_label("Delete every saved dictation?", "muted"))
        self.cancel_button = QPushButton("Cancel", objectName="ghost", cursor=Qt.PointingHandCursor)
        self.cancel_button.clicked.connect(lambda: self._confirming(False))
        self.confirm_button = QPushButton("Delete all", objectName="danger", cursor=Qt.PointingHandCursor)
        self.confirm_button.clicked.connect(self._clear)
        confirm.addWidget(self.cancel_button)
        confirm.addWidget(self.confirm_button)
        self.confirm.hide()
        header.addWidget(self.confirm)
        self.layout_.addLayout(header)

        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.entries = QWidget(objectName="page")
        self.entries_layout = QVBoxLayout(self.entries)
        self.entries_layout.setContentsMargins(0, 0, 6, 0)
        self.entries_layout.setSpacing(4)
        self.scroll.setWidget(self.entries)
        self.layout_.addWidget(self.scroll, 1)

        self.empty = QWidget()
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.addStretch(1)
        self.empty_label = make_label("", "muted")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setTextFormat(Qt.RichText)
        self.empty_label.linkActivated.connect(lambda _: self.open_settings.emit())
        empty_layout.addWidget(self.empty_label)
        empty_layout.addStretch(2)
        self.layout_.addWidget(self.empty, 1)
        self.enabled = False

    def refresh(self, enabled: bool):
        self.enabled = enabled
        rows = history.recent()
        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        today, heading = date.today(), None
        for created, text in rows:
            try:
                stamp = datetime.fromisoformat(created).astimezone()
                day, when = day_label(stamp.date(), today), stamp.strftime("%H:%M")
            except ValueError:
                day, when = "Earlier", created
            if day != heading:
                heading = day
                label = make_label(day, "section")
                label.setContentsMargins(14, 12 if self.entries_layout.count() else 0, 0, 2)
                self.entries_layout.addWidget(label)
            self.entries_layout.addWidget(HistoryEntry(when, text))
        self.entries_layout.addStretch(1)
        has_rows = bool(rows)
        self.scroll.setVisible(has_rows)
        self._confirming(False, focus=False)
        self.clear_button.setVisible(has_rows)
        self.empty.setVisible(not has_rows)
        self.empty_label.setText("Nothing yet" if enabled else
                                 'History is off. Turn on “Keep history” in <a href="settings">Settings</a>.')

    def _confirming(self, on: bool, focus: bool = True):
        self.clear_button.setVisible(not on)
        self.confirm.setVisible(on)
        if focus:
            (self.cancel_button if on else self.clear_button).setFocus()

    def _clear(self):
        history.clear()
        self.refresh(self.enabled)

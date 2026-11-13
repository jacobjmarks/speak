"""Building blocks shared by the main-window pages and the first-run setup: page base, cards, labels, setting rows, form controls."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QBoxLayout, QComboBox, QFrame, QHBoxLayout, QLabel, QStyle, QStyleOptionViewItem,
                               QStyledItemDelegate, QVBoxLayout, QWidget)

from .. import audio


def make_card() -> tuple:
    frame = QFrame(objectName="card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 8, 18, 8)
    layout.setSpacing(0)
    return frame, layout


def make_label(text: str, name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    return label


class Page(QWidget):
    def __init__(self):
        super().__init__(objectName="page")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(32, 28, 32, 28)
        self.layout_.setSpacing(14)


class SettingRow(QWidget):
    def __init__(self, title: str, hint: str, control: QWidget):
        super().__init__()
        self.layout_ = QHBoxLayout(self)
        self.layout_.setSpacing(16)
        self.layout_.setContentsMargins(0, 12, 0, 12)
        self.text = QVBoxLayout()
        self.text.setSpacing(2)
        self.text.addWidget(make_label(title))
        self.hint = make_label(hint, "hint")
        self.hint.setWordWrap(True)
        self.text.addWidget(self.hint)
        self.layout_.addLayout(self.text, 1)
        self.hint.setVisible(bool(hint))
        self.layout_.addWidget(control, 0, Qt.AlignVCenter)
        self.control = control
        self._compact = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < 440
        if compact == self._compact:
            return
        self._compact = compact
        self.layout_.setDirection(QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight)
        self.layout_.setSpacing(8 if compact else 16)
        self.layout_.setAlignment(self.control, Qt.Alignment() if compact and isinstance(self.control, QComboBox)
                                  else Qt.AlignRight if compact else Qt.AlignVCenter)
        self.layout_.setStretch(0, 1 if not compact else 0)


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores the mouse wheel so scrolling the page can't change its value."""

    def wheelEvent(self, event):
        event.ignore()


def make_combo(options: dict, current: str) -> NoWheelComboBox:
    combo = NoWheelComboBox(cursor=Qt.PointingHandCursor)
    for key, label in options.items():
        combo.addItem(label, key)
    index = combo.findData(current)
    combo.setCurrentIndex(max(0, index))
    return combo


class LanguageItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.muted = None

    def paint(self, painter, option, index):
        if index.data(Qt.UserRole + 1) == "section":
            super().paint(painter, option, index)
            return

        option = QStyleOptionViewItem(option)
        self.initStyleOption(option, index)
        text = option.text
        option.text = ""
        option.widget.style().drawControl(QStyle.CE_ItemViewItem, option, painter, option.widget)

        code = str(index.data(Qt.UserRole))
        code_width = option.fontMetrics.horizontalAdvance(code)
        text_rect = option.rect.adjusted(12, 0, -12, 0)
        language_rect = text_rect.adjusted(0, 0, -code_width - 16, 0)
        code_rect = text_rect.adjusted(text_rect.width() - code_width, 0, 0, 0)
        painter.save()
        painter.setFont(option.font)
        text_color = QPalette.HighlightedText if option.state & QStyle.State_Selected else QPalette.Text
        painter.setPen(option.palette.color(text_color))
        painter.drawText(language_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.setPen(self.muted or option.palette.color(QPalette.Disabled, QPalette.Text))
        painter.drawText(code_rect, Qt.AlignVCenter | Qt.AlignRight, code)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(size.height() + (6 if index.data(Qt.UserRole + 1) == "section" else 8))
        return size


class MicCombo(NoWheelComboBox):
    """Input devices, re-read from the OS each time the list is opened (when `can_rescan()`)."""

    def __init__(self, current, can_rescan):
        super().__init__(cursor=Qt.PointingHandCursor)
        self.can_rescan = can_rescan
        self._fill(current, rescan=False)

    def _fill(self, current, rescan: bool):
        try:
            names = audio.input_devices(rescan)
        except Exception:
            names = []
        self.blockSignals(True)
        self.clear()
        self.addItem("System default", None)
        for name in names:
            self.addItem(name, name)
        if current and current not in names:
            self.addItem(f"{current} (not connected)", current)
        self.setCurrentIndex(max(0, self.findData(current)))
        self.blockSignals(False)

    def set_device(self, current):
        self._fill(current, rescan=False)

    def showPopup(self):
        self._fill(self.currentData(), rescan=self.can_rescan())
        super().showPopup()

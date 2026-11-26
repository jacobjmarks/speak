"""Building blocks shared by the main-window pages and the first-run setup: page base, cards, labels, badges, setting rows
and sections, form controls."""
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QBoxLayout, QComboBox, QFrame, QHBoxLayout, QLabel, QStyle, QStyleOptionViewItem,
                               QStyledItemDelegate, QVBoxLayout, QWidget)

from .. import audio
from .paint import draw_chevron
from .widgets import Disclosure, Glyph


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


def make_badge(text: str, tone: str = "warn") -> QLabel:
    """Small tinted pill beside a row title, e.g. "Experimental" (warn) or a neutral note (info)."""
    badge = QLabel(text, objectName="badge")
    badge.setProperty("tone", tone)
    return badge


def explicitly_hidden(widget: QWidget) -> bool:
    """Hidden by a hide() call, as opposed to merely not shown yet because its window isn't."""
    return widget.isHidden() and widget.testAttribute(Qt.WA_WState_ExplicitShowHide)


def _repolish(widget: QWidget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class LinkLabel(QLabel):
    """Rich-text label with links that follow theme changes (QLabel keeps the link colour it was first laid out with)."""

    def __init__(self, text: str = "", name: str = ""):
        super().__init__(text, objectName=name)
        self.setTextFormat(Qt.RichText)
        self.setWordWrap(True)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.PaletteChange:
            text = self.text()
            self.setText("")
            self.setText(text)


def make_header(title: str, crumb: str = "") -> tuple:
    """Page title, optionally after a muted parent crumb ("Settings › Dictation"). Returns (widget, title label)."""
    header = QWidget()
    row = QHBoxLayout(header)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(12)
    if crumb:
        row.addWidget(QLabel(crumb, objectName="crumb"))
        row.addWidget(QLabel("›", objectName="crumb"))
    label = QLabel(title, objectName="title")
    row.addWidget(label)
    row.addStretch(1)
    return header, label


class LinkRow(QFrame):
    """A row that leads somewhere else: glyph, title, current value, and a chevron. Click, Return or Space opens it."""
    activated = Signal()

    def __init__(self, draw, title: str):
        super().__init__(objectName="link", cursor=Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(title)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(14)
        row.addWidget(Glyph(draw, 18))
        text = QVBoxLayout()
        text.setSpacing(1)
        title_label = make_label(title)
        title_label.setWordWrap(False)
        text.addWidget(title_label)
        self.value = make_label("", "hint")
        self.value.setWordWrap(False)
        text.addWidget(self.value)
        row.addLayout(text, 1)
        row.addWidget(Glyph(lambda p, c, s, col: draw_chevron(p, c, s * 0.7, col, right=True), 16))

    def mouseReleaseEvent(self, event):
        if self.rect().contains(event.position().toPoint()):
            self.activated.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activated.emit()
        else:
            super().keyPressEvent(event)


class SettingRow(QWidget):
    """Title + hint on the left, control on the right; stacks under 440 px. `key` names the setting it edits and
    `keywords` add search terms beyond the visible text."""

    def __init__(self, title: str, hint: str, control: QWidget, badge: str = "", keywords: str = "", key=None):
        super().__init__(objectName="row")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.title = title
        self.badge = badge
        self.keywords = keywords
        self.key = key
        self.available = True  # False when the platform can't use it: never shown, never searched
        self.advanced = False
        self.section = None
        self.layout_ = QHBoxLayout(self)
        self.layout_.setSpacing(16)
        self.layout_.setContentsMargins(0, 12, 0, 12)
        self.text = QVBoxLayout()
        self.text.setSpacing(2)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        self.title_label = make_label(title)
        self.title_label.setWordWrap(False)
        heading.addWidget(self.title_label)
        if badge:
            heading.addWidget(make_badge(badge), 0, Qt.AlignVCenter)
        heading.addStretch(1)
        self.text.addLayout(heading)
        self.hint = make_label(hint, "hint")
        self.hint.setWordWrap(True)
        self.text.addWidget(self.hint)
        self.layout_.addLayout(self.text, 1)
        self.hint.setVisible(bool(hint))
        self.layout_.addWidget(control, 0, Qt.AlignVCenter)
        self.control = control
        self.focus_widget = control  # what search focuses; differs when the control is wrapped
        self._compact = None
        self._unflash = QTimer(self, singleShot=True, interval=1600, timeout=lambda: self._set_flag("highlight", False))

    def setVisible(self, visible: bool):
        # Explicit show/hide only (hide() and show() land here); Qt's own hiding during teardown doesn't.
        super().setVisible(visible)
        if getattr(self, "section", None) is not None:
            self.section.refresh()

    def search_text(self) -> str:
        parts = [self.title, self.hint.text(), self.keywords, self.badge]
        if self.section:
            parts += [self.section.title, self.section.category_label]
        return " ".join(parts).lower()

    def set_divider(self, on: bool):
        self._set_flag("divider", on)

    def flash(self):
        """Briefly tint the row, e.g. after search jumps to it."""
        self._set_flag("highlight", True)
        self._unflash.start()

    def _set_flag(self, name: str, on: bool):
        if bool(self.property(name)) != on:
            self.setProperty(name, on)
            _repolish(self)

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


class SettingsSection(QWidget):
    """A titled card of `SettingRow`s. Two or more rows added with `advanced=True` sit behind a "More options" disclosure
    at the foot of the card (a single one just shows); dividers between visible rows are managed here, so hiding a row
    never leaves a stray line."""

    toggled = Signal(bool)

    def __init__(self, title: str = "", category_label: str = "", section_id: str = ""):
        super().__init__()
        self.title = title
        self.category_label = category_label
        self.id = section_id
        self.rows = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        if title:
            outer.addWidget(make_label(title, "sectionhead"))
        self.card = QFrame(objectName="card")
        card = QVBoxLayout(self.card)
        card.setContentsMargins(8, 4, 8, 4)
        card.setSpacing(0)
        self._basic = QVBoxLayout()
        self._basic.setSpacing(0)
        card.addLayout(self._basic)
        self.more = Disclosure("More options")
        self.more.hide()
        self.more.toggled.connect(self._on_toggled)
        card.addWidget(self.more)
        self.advanced = QWidget()
        self._advanced = QVBoxLayout(self.advanced)
        self._advanced.setContentsMargins(0, 0, 0, 0)
        self._advanced.setSpacing(0)
        self.advanced.hide()
        card.addWidget(self.advanced)
        outer.addWidget(self.card)

    @property
    def expanded(self) -> bool:
        return self.more.isChecked()

    def add(self, row: SettingRow, advanced: bool = False) -> SettingRow:
        row.layout_.setContentsMargins(10, 12, 10, 12)
        row.section = self
        row.advanced = advanced
        (self._advanced if advanced else self._basic).addWidget(row)
        self.rows.append(row)
        self.refresh()
        return row

    def set_expanded(self, on: bool):
        """Open or close without emitting `toggled` (restoring a saved state, or revealing a search result)."""
        self.more.blockSignals(True)
        self.more.setChecked(on)
        self.more.blockSignals(False)
        self._show_advanced()

    @property
    def inline(self) -> bool:
        """A lone technical row isn't worth a disclosure: it shows in place, after the others."""
        return len([r for r in self.rows if r.advanced and not explicitly_hidden(r)]) == 1

    def set_changed(self, count: int):
        self.more.set_changed(count)

    def _on_toggled(self, on: bool):
        self._show_advanced()
        self.toggled.emit(on)

    def _show_advanced(self):
        self.advanced.setVisible(self.inline or self.more.isChecked())

    def refresh(self):
        """Re-lay dividers and More options after a row was shown or hidden."""
        basic = [r for r in self.rows if not r.advanced and not explicitly_hidden(r)]
        extra = [r for r in self.rows if r.advanced and not explicitly_hidden(r)]
        for i, row in enumerate(basic):
            row.set_divider(i > 0)
        for i, row in enumerate(extra):
            row.set_divider(bool(basic) or i > 0)
        self.more.divider = bool(basic)
        self.more.set_summary(", ".join(r.title for r in extra))
        self.more.setVisible(len(extra) > 1)
        self._show_advanced()
        if basic or extra or self.parentWidget():
            self.setVisible(bool(basic or extra))


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

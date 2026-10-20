"""Main window (sidebar + pages), app icon, and the first-close prompt."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import updates
from .pages import AboutPage, DictatePage, HistoryPage, SettingsPage
from .widgets import draw_mic

BRAND = "#245b56"
CREAM = "#f4e7c8"


def app_icon(dot: str = "") -> QIcon:
    """Teal rounded square with a cream mic; optional status dot colour (e.g. red while listening)."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(BRAND))
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)
        draw_mic(p, QPointF(size / 2, size * 0.53), size * 0.62, QColor(CREAM))
        if dot:
            r = size * 0.2
            p.setBrush(QColor(dot))
            p.drawEllipse(QPointF(size - r, r), r, r)
        p.end()
        icon.addPixmap(pm)
    return icon


class Logo(QWidget):
    def __init__(self, size: int = 34):
        super().__init__()
        self.setFixedSize(size, size)
        self._pm = app_icon().pixmap(size * 2, size * 2)
        self._pm.setDevicePixelRatio(2)

    def paintEvent(self, e):
        QPainter(self).drawPixmap(0, 0, self._pm)


class StatusDot(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(10, 10)
        self.color = QColor("#999999")

    def set_color(self, c: str):
        self.color = QColor(c)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(QRectF(1, 1, 8, 8))


class MainWindow(QMainWindow):
    close_requested = Signal()
    update_clicked = Signal()

    def __init__(self, settings: dict, level_source, can_rescan_mics=lambda: False):
        super().__init__()
        self.allow_close = False
        self.setWindowTitle("Speak")
        self.setWindowIcon(app_icon())
        self.resize(760, 560)
        self.setMinimumSize(640, 480)

        root = QWidget(objectName="root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget(objectName="sidebar")
        sidebar.setFixedWidth(180)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 22, 14, 16)
        side.setSpacing(4)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(Logo(), 0, Qt.AlignVCenter)
        name = QLabel("Speak")
        name.setStyleSheet("font-size: 15pt; font-weight: 600; letter-spacing: 0.3px;")
        brand.addWidget(name, 1, Qt.AlignVCenter)
        side.addLayout(brand)
        side.addSpacing(26)

        self.stack = QStackedWidget()
        self.dictate = DictatePage(level_source)
        self.history = HistoryPage()
        self.settings = SettingsPage(settings, can_rescan_mics)
        self.about = AboutPage(Logo(56))
        self.nav = QButtonGroup(self)
        for i, (label, page) in enumerate((("Dictate", self.dictate), ("History", self.history),
                                           ("Settings", self.settings), ("About", self.about))):
            self.stack.addWidget(page)
            button = QPushButton(label, objectName="nav", checkable=True, cursor=Qt.PointingHandCursor)
            self.nav.addButton(button, i)
            side.addWidget(button)
        self.nav.button(0).setChecked(True)
        self.nav.idClicked.connect(self.show_page)
        side.addStretch(1)

        self.update_button = QPushButton(objectName="update", cursor=Qt.PointingHandCursor)
        self.update_button.clicked.connect(self.update_clicked)
        self.update_button.hide()
        side.addWidget(self.update_button)
        side.addSpacing(8)

        status = QHBoxLayout()
        self.status_dot = StatusDot()
        self.status_text = QLabel("Ready", objectName="hint")
        status.addWidget(self.status_dot)
        status.addWidget(self.status_text, 1)
        side.addLayout(status)
        version = QLabel(f"Version {updates.VERSION}" if updates.VERSION else "Development build", objectName="hint")
        version.setContentsMargins(2, 4, 0, 0)
        side.addWidget(version)

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

    def show_page(self, index: int):
        self.nav.button(index).setChecked(True)
        self.stack.setCurrentIndex(index)
        if self.stack.currentWidget() is self.history:
            self.history.refresh(self.history.enabled)

    def set_update(self, text: str, tooltip: str = "", enabled: bool = True):
        """Sidebar update button; hidden when `text` is empty."""
        self.update_button.setText(text)
        self.update_button.setToolTip(tooltip)
        self.update_button.setEnabled(enabled)
        self.update_button.setVisible(bool(text))

    def set_status(self, text: str, color: str):
        self.status_text.setText(text)
        self.status_dot.set_color(color)

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        self.close_requested.emit()


class CloseDialog(QDialog):
    """First-close prompt. `choice` is "tray", "exit", or None if dismissed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Speak")
        self.setModal(True)
        self.choice = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(10)
        title = QLabel("Keep Speak running?")
        title.setStyleSheet("font-size: 14pt; font-weight: 600;")
        layout.addWidget(title)
        body = QLabel("Speak can stay in the tray so your shortcut keeps working after you close this window.")
        body.setWordWrap(True)
        layout.addWidget(body)
        hint = QLabel("You can change this anytime in Settings.", objectName="hint")
        layout.addWidget(hint)
        layout.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        quit_button = QPushButton("Quit Speak", cursor=Qt.PointingHandCursor)
        keep = QPushButton("Keep in tray", objectName="primary", cursor=Qt.PointingHandCursor)
        keep.setDefault(True)
        quit_button.clicked.connect(lambda: self._pick("exit"))
        keep.clicked.connect(lambda: self._pick("tray"))
        buttons.addWidget(quit_button)
        buttons.addWidget(keep)
        layout.addLayout(buttons)
        self.setFixedWidth(420)

    def _pick(self, choice: str):
        self.choice = choice
        self.accept()

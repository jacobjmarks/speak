"""Main window (sidebar + pages), app icon, and the first-close prompt."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import updates
from ..platform_utils import IS_MAC, TRAY_NAME, hide_title_text
from .banner import Banner
from .pages import AboutPage, DictatePage, HistoryPage, SetupPage, SettingsPage
from .widgets import draw_mic

BRAND = "#245b56"
CREAM = "#f4e7c8"


def render_icon(size: int, dot: str = "", inset: float = 0.0) -> QPixmap:
    """Teal rounded square with a cream mic; optional status dot colour. `inset` leaves a transparent margin
    (fraction of `size` per side), as macOS app icons expect."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    margin = size * inset
    side = size - 2 * margin
    rect = QRectF(margin, margin, side, side)
    radius = side * 0.225
    if inset:  # macOS style: soft drop shadow, top-lit gradient, thin highlight edge
        for i in range(24):
            spread = side * 0.0025 * i
            p.setBrush(QColor(0, 0, 0, 3))
            p.drawRoundedRect(rect.adjusted(-spread, -spread, spread, spread).translated(0, side * 0.015),
                              radius + spread, radius + spread)
        gradient = QLinearGradient(0, margin, 0, margin + side)
        gradient.setColorAt(0, QColor(BRAND).lighter(125))
        gradient.setColorAt(1, QColor(BRAND).darker(115))
        p.setBrush(gradient)
    else:
        p.setBrush(QColor(BRAND))
    p.drawRoundedRect(rect, radius, radius)
    if inset:
        edge = QLinearGradient(0, margin, 0, margin + side)
        edge.setColorAt(0, QColor(255, 255, 255, 110))
        edge.setColorAt(0.5, QColor(255, 255, 255, 0))
        edge.setColorAt(1, QColor(0, 0, 0, 60))
        p.setPen(QPen(QBrush(edge), max(1.0, side * 0.006)))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(side * 0.003, side * 0.003, -side * 0.003, -side * 0.003), radius, radius)
        p.setPen(Qt.NoPen)
    draw_mic(p, QPointF(size / 2, margin + side * 0.53), side * 0.62, QColor(CREAM))
    if dot:
        r = side * 0.2
        p.setBrush(QColor(dot))
        p.drawEllipse(QPointF(size - margin - r, margin + r), r, r)
    p.end()
    return pm


def app_icon(dot: str = "", inset: float = 0.0) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        icon.addPixmap(render_icon(size, dot, inset))
    return icon


def menu_bar_icon() -> QIcon:
    """Monochrome mic that macOS tints for light/dark menu bars."""
    icon = QIcon()
    for size in (18, 36):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        draw_mic(p, QPointF(size / 2, size * 0.53), size * 0.8, QColor("black"))
        p.end()
        icon.addPixmap(pm)
    icon.setIsMask(True)
    return icon


class Logo(QWidget):
    def __init__(self, size: int = 34):
        super().__init__()
        self.setFixedSize(size, size)
        self._pm = render_icon(size * 2)
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

    def __init__(self, settings: dict, level_source, can_rescan_mics=lambda: False):
        super().__init__()
        self.allow_close = False
        self.setWindowTitle("Speak")
        self.setWindowIcon(app_icon())
        if IS_MAC:  # content runs under the title bar; only the traffic-light buttons remain
            self.setWindowFlags(self.windowFlags() | Qt.ExpandedClientAreaHint | Qt.NoTitleBarBackgroundHint)
            self.setAttribute(Qt.WA_ContentsMarginsRespectsSafeArea, False)  # lay out under the title bar
        self.resize(760, 560)
        self.setMinimumSize(640, 480)

        root = QWidget(objectName="root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget(objectName="sidebar")
        sidebar.setFixedWidth(180)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 22 + (24 if IS_MAC else 0), 14, 16)  # clear of the traffic-light buttons
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

        status = QHBoxLayout()
        self.status_dot = StatusDot()
        self.status_text = QLabel("Ready", objectName="hint")
        status.addWidget(self.status_dot)
        status.addWidget(self.status_text, 1)
        side.addLayout(status)
        version = QLabel(updates.display(), objectName="hint")
        version.setContentsMargins(2, 4, 0, 0)
        side.addWidget(version)

        layout.addWidget(sidebar)
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.banner = Banner()
        self.notice_action = self.banner.action_clicked
        banner_row = QHBoxLayout()
        banner_row.setContentsMargins(24, 16, 24, 0)
        banner_row.addWidget(self.banner)
        column.addLayout(banner_row)
        column.addWidget(self.stack, 1)
        layout.addWidget(content, 1)
        self.setup = SetupPage()
        self.screens = QStackedWidget()  # [root app, first-run setup]
        self.screens.addWidget(root)
        self.screens.addWidget(self.setup)
        self.setCentralWidget(self.screens)

    def show_setup(self, active: bool):
        self.screens.setCurrentIndex(1 if active else 0)

    def show_page(self, index: int):
        self.nav.button(index).setChecked(True)
        self.stack.setCurrentIndex(index)
        if self.stack.currentWidget() is self.history:
            self.history.refresh(self.history.enabled)

    def notify(self, key: str, text: str, level: str = "info", action: str = "", enabled: bool = True,
               timeout: float = 0.0):
        self.banner.show_notice(key, text, level, action, enabled, timeout)

    def clear_notice(self, key: str):
        self.banner.clear(key)

    def set_status(self, text: str, color: str):
        self.status_text.setText(text)
        self.status_dot.set_color(color)

    def showEvent(self, event):
        super().showEvent(event)
        hide_title_text(int(self.winId()))

    def mousePressEvent(self, event):
        if IS_MAC and event.button() == Qt.LeftButton and event.position().y() < 40:
            self.windowHandle().startSystemMove()  # the title bar is gone, so the top strip drags the window
        super().mousePressEvent(event)


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
        body = QLabel(f"Speak can stay in the {TRAY_NAME} so your shortcut keeps working after you close this window.")
        body.setWordWrap(True)
        layout.addWidget(body)
        hint = QLabel("You can change this anytime in Settings.", objectName="hint")
        layout.addWidget(hint)
        layout.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        quit_button = QPushButton("Quit Speak", cursor=Qt.PointingHandCursor)
        keep = QPushButton(f"Keep in {TRAY_NAME}", objectName="primary", cursor=Qt.PointingHandCursor)
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

"""Main window (sidebar with "Find a setting", Dictate, History, every settings category and About, beside the
pages), app icon, and the first-close prompt."""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from ..platform_utils import IS_MAC, TRAY_NAME, hide_title_text, system_app_icon_png
from . import theme
from .banner import Banner
from .onboarding import OnboardingPage
from .paint import (draw_clock, draw_info, draw_keyboard, draw_lines, draw_mic, draw_pill, draw_refresh,
                    draw_search, draw_window)
from .pages.about import AboutPage
from .pages.dictate import DictatePage
from .pages.history import HistoryPage
from .pages.settings import CATEGORIES, SettingsPage
from .pages.setup import SetupPage

BRAND = "#245b56"
CREAM = "#f4e7c8"
MAC_INSET = 0.1  # macOS icons keep a transparent margin around the rounded square


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


DICTATE, HISTORY, SETTINGS, ABOUT = range(4)  # pages in the main stack
SIDEBAR_WIDTH = 236
CATEGORY_GLYPHS = {"dictation": draw_keyboard, "text": draw_lines, "indicator": draw_pill, "app": draw_window,
                   "updates": draw_refresh}


def nav_icon(glyph, muted: str, selected: str) -> QIcon:
    """18 px sidebar glyph: muted at rest, accent when its page is selected."""
    icon = QIcon()
    for state, colour in ((QIcon.Off, muted), (QIcon.On, selected)):
        pm = QPixmap(36, 36)
        pm.setDevicePixelRatio(2)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        glyph(p, QPointF(9, 9.5 if glyph is draw_mic else 9), 16, QColor(colour))
        p.end()
        icon.addPixmap(pm, QIcon.Normal, state)
    return icon


class NavButton(QPushButton):
    """Sidebar entry: glyph and label; the selected one gets a fill and a short accent pill at its left edge."""

    def __init__(self, label: str):
        super().__init__(f"  {label.replace('&', '&&')}", objectName="nav", checkable=True,
                         cursor=Qt.PointingHandCursor)
        self.setAccessibleName(label)
        self.setIconSize(QSize(18, 18))
        self.accent = QColor(theme.LIGHT.accent)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.isChecked():
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(self.accent)
            p.drawRoundedRect(QRectF(1, self.height() / 2 - 8, 3, 16), 1.5, 1.5)


class Logo(QWidget):
    def __init__(self, size: int = 34):
        super().__init__()
        if IS_MAC:  # mac icons carry a transparent margin; grow so the squircle keeps the requested size
            size = round(size / (1 - 2 * MAC_INSET))
        self.setFixedSize(size, size)
        png = system_app_icon_png(size * 2)
        self._pm = QPixmap()
        if not (png and self._pm.loadFromData(png)):
            self._pm = render_icon(size * 2, inset=MAC_INSET if IS_MAC else 0.0)
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
        self.resize(1000, 760)
        self.setMinimumSize(640, 480)

        root = QWidget(objectName="root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.dictate = DictatePage(level_source)
        self.history = HistoryPage()
        self.settings = SettingsPage(settings, can_rescan_mics)
        self.about = AboutPage(Logo(56))
        for page in (self.dictate, self.history, self.settings, self.about):  # DICTATE, HISTORY, SETTINGS, ABOUT
            self.stack.addWidget(page)

        sidebar = QWidget(objectName="sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 18 + (24 if IS_MAC else 0), 12, 14)  # clear of the traffic-light buttons
        side.setSpacing(2)
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 0)
        brand.setSpacing(10)
        brand.addWidget(Logo(28), 0, Qt.AlignVCenter)
        brand.addWidget(QLabel("Speak", objectName="brand"), 1, Qt.AlignVCenter)
        side.addLayout(brand)
        side.addSpacing(16)
        self.search_icon = self.settings.search.addAction(QIcon(), QLineEdit.LeadingPosition)
        side.addWidget(self.settings.search)
        side.addSpacing(12)

        self.nav = QButtonGroup(self)
        self.nav_buttons = {}  # nav key -> button: pages by index name, settings categories by key
        self._nav_glyphs = {}

        def nav_button(key, label, glyph, on_click):
            button = NavButton(label)
            button.clicked.connect(on_click)
            self.nav.addButton(button)
            self.nav_buttons[key] = button
            self._nav_glyphs[key] = glyph
            return button

        side.addWidget(nav_button(DICTATE, "Dictate", draw_mic, lambda: self.show_page(DICTATE)))
        side.addWidget(nav_button(HISTORY, "History", draw_clock, lambda: self.show_page(HISTORY)))
        side.addWidget(QLabel("Settings", objectName="navgroup"))
        for key, label in CATEGORIES.items():
            side.addWidget(nav_button(key, label, CATEGORY_GLYPHS[key], lambda _=False, k=key: self.show_settings(k)))
        side.addStretch(1)
        status = QHBoxLayout()
        status.setContentsMargins(12, 0, 0, 6)
        self.status_dot = StatusDot()
        self.status_text = QLabel("Ready", objectName="hint")
        status.addWidget(self.status_dot)
        status.addWidget(self.status_text, 1)
        side.addLayout(status)
        side.addWidget(nav_button(ABOUT, "About", draw_info, lambda: self.show_page(ABOUT)))

        for i, (label, keys) in enumerate((("Dictate", "Ctrl+1"), ("History", "Ctrl+2"), ("Settings", "Ctrl+3"),
                                           ("About", "Ctrl+4"))):
            QShortcut(QKeySequence(keys), self, activated=lambda index=i: self._shortcut_page(index))
        QShortcut(QKeySequence("Ctrl+,"), self, activated=lambda: self._shortcut_page(SETTINGS))
        QShortcut(QKeySequence.Find, self, activated=self._find)
        self.settings.category_shown.connect(self._on_category_shown)
        self.settings.searching.connect(self._on_searching)
        self.dictate.open_setting.connect(self.open_setting)
        self.history.open_settings.connect(lambda: self.open_setting("history_enabled"))
        self.set_palette(theme.LIGHT)
        self.show_page(DICTATE)

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
        self.onboarding = OnboardingPage(settings, can_rescan_mics, Logo(96))
        self.screens = QStackedWidget()  # [root app, permissions setup, first-run onboarding]
        self.screens.addWidget(root)
        self.screens.addWidget(self.setup)
        self.screens.addWidget(self.onboarding)
        self.setCentralWidget(self.screens)
        self.nav_buttons[DICTATE].setFocus()  # not a caret in Find a setting; Ctrl+F or a click puts it there

    def show_setup(self, active: bool):
        self.screens.setCurrentIndex(1 if active else 0)

    def show_onboarding(self, active: bool):
        if active:
            self.onboarding.reset()
        self.screens.setCurrentIndex(2 if active else 0)

    def show_page(self, index: int):
        """DICTATE, HISTORY, SETTINGS (its current category) or ABOUT."""
        if index != SETTINGS:
            self.settings.clear_search()
        self.stack.setCurrentIndex(index)
        self.nav_buttons[self.settings.category if index == SETTINGS else index].setChecked(True)
        if self.stack.currentWidget() is self.history:
            self.history.refresh(self.history.enabled)

    def show_settings(self, category: str):
        self.settings.show_category(category)
        self.show_page(SETTINGS)

    def open_setting(self, key: str):
        """Jump to one setting, e.g. from Dictate's related settings."""
        self.show_page(SETTINGS)
        self.settings.reveal(self.settings.row_for(key))

    def _on_category_shown(self, key: str):
        if self.stack.currentWidget() is self.settings:
            self.nav_buttons[key].setChecked(True)

    def _on_searching(self):
        self.stack.setCurrentWidget(self.settings)
        self.nav.setExclusive(False)  # no page is current while results show
        for button in self.nav.buttons():
            button.setChecked(False)
        self.nav.setExclusive(True)

    def _find(self):
        if self.screens.currentIndex() == 0:
            self.settings.focus_search()

    def _shortcut_page(self, index: int):
        if self.screens.currentIndex() == 0:  # not while setup or onboarding covers the window
            self.show_page(index)

    def set_palette(self, palette):
        for key, button in self.nav_buttons.items():
            button.setIcon(nav_icon(self._nav_glyphs[key], palette.text, palette.text))
            button.accent = QColor(palette.accent)
        self.search_icon.setIcon(nav_icon(draw_search, palette.muted, palette.muted))

    def notify(self, key: str, text: str, level: str = "info", action: str = "", enabled: bool = True,
               timeout: float = 0.0):
        self.banner.show_notice(key, text, level, action, enabled, timeout)

    def clear_notice(self, key: str):
        self.banner.clear(key)

    def set_status(self, text: str, color: str):
        self.status_text.setText(text)
        self.status_dot.set_color(color)
        self.dictate.set_status(text, color)

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

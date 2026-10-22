"""Palettes and the app-wide Qt style sheet. All colours live here."""
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication


@dataclass(frozen=True)
class Palette:
    bg: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_text: str
    danger: str
    success: str


LIGHT = Palette("#f6f5f1", "#ffffff", "#eeece6", "#e2dfd6", "#1d2523", "#6b7370",
                "#2a6b64", "#ffffff", "#c2413a", "#2f8f5b")
DARK = Palette("#151a19", "#1e2524", "#262e2d", "#323b39", "#eef1ef", "#9aa5a1",
               "#5fc2b5", "#0d1b19", "#ef6a62", "#5cc98d")


def resolve(theme: str) -> Palette:
    if theme == "Light":
        return LIGHT
    if theme == "Dark":
        return DARK
    scheme = QGuiApplication.styleHints().colorScheme()
    return DARK if scheme == Qt.ColorScheme.Dark else LIGHT


def color(hex_value: str, alpha: int = 255) -> QColor:
    c = QColor(hex_value)
    c.setAlpha(alpha)
    return c


def _tint(hex_value: str) -> str:
    c = QColor(hex_value)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, 0.14)"


def stylesheet(p: Palette) -> str:
    return f"""
    * {{ font-size: 10pt; color: {p.text}; }}
    QMainWindow, QWidget#root {{ background: {p.bg}; }}
    QWidget#page {{ background: transparent; }}
    QLabel {{ background: transparent; }}
    QLabel#title {{ font-size: 18pt; font-weight: 600; }}
    QLabel#section {{ font-size: 9pt; font-weight: 600; color: {p.muted}; letter-spacing: 1px; }}
    QLabel#muted, QLabel#hint {{ color: {p.muted}; }}
    QLabel#hint {{ font-size: 9pt; }}
    QFrame#card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 14px; }}
    QFrame#divider {{ background: {p.border}; max-height: 1px; border: none; }}
    QFrame#banner {{ background: {_tint(p.accent)}; border: 1px solid {p.accent}; border-radius: 12px; }}
    QFrame#banner[level="error"] {{ background: {_tint(p.danger)}; border-color: {p.danger}; }}
    QFrame#banner QLabel {{ font-weight: 500; }}

    QWidget#sidebar {{ background: {p.surface}; border-right: 1px solid {p.border}; }}
    QPushButton#nav {{ text-align: left; padding: 9px 14px; border-radius: 10px; border: none;
                       background: transparent; color: {p.muted}; font-weight: 500; }}
    QPushButton#nav:hover {{ background: {p.surface_alt}; color: {p.text}; }}
    QPushButton#nav:checked {{ background: {p.surface_alt}; color: {p.accent}; font-weight: 600; }}

    QPushButton {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px;
                   padding: 7px 14px; }}
    QPushButton:hover {{ border-color: {p.accent}; }}
    QPushButton:disabled {{ color: {p.muted}; }}
    QPushButton#primary {{ background: {p.accent}; color: {p.accent_text}; border: none; font-weight: 600; }}
    QPushButton#primary:hover {{ background: {QColor(p.accent).lighter(110).name()}; }}
    QPushButton#ghost {{ background: transparent; border: none; color: {p.muted}; padding: 6px 8px; }}
    QPushButton#ghost:hover {{ color: {p.text}; }}
    QPushButton#danger {{ background: transparent; border: 1px solid {p.border}; color: {p.danger}; }}
    QPushButton#shortcut {{ font-family: "Consolas", "Menlo", monospace; font-weight: 600;
                            padding: 7px 16px; min-width: 150px; }}
    QPushButton#shortcut[recording="true"] {{ border: 2px solid {p.accent}; color: {p.accent}; }}

    QComboBox {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px;
                 padding: 6px 12px; min-width: 190px; }}
    QComboBox:hover {{ border-color: {p.accent}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border};
                                   selection-background-color: {p.surface_alt}; selection-color: {p.accent};
                                   outline: none; padding: 4px; }}

    QTextEdit, QPlainTextEdit {{ background: transparent; border: none; font-size: 12pt;
                                 selection-background-color: {p.accent}; selection-color: {p.accent_text}; }}
    QFrame#entry {{ background: transparent; border-radius: 10px; }}
    QFrame#entry:hover {{ background: {p.surface_alt}; }}

    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; padding: 6px;
                border-radius: 6px; }}
    QMenu {{ background: {p.surface}; border: 1px solid {p.border}; padding: 4px; border-radius: 8px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {p.surface_alt}; }}
    """

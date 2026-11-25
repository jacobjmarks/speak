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
    warn: str


LIGHT = Palette("#f3f4f2", "#fdfdfc", "#e9ece8", "#e1e4e0", "#1a1f1d", "#5a6460",
                "#2a6b64", "#ffffff", "#b23a33", "#2f8f5b", "#8a5a0e")
DARK = Palette("#1b201f", "#242a29", "#2e3533", "#353d3b", "#eceff0", "#a0aaa6",
               "#6cc4b7", "#0d1b19", "#ef6a62", "#5cc98d", "#e3b35c")


current = LIGHT  # the palette in use; widgets created after a theme change read it (see SpeakApp._apply_theme)


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


def _tint(hex_value: str, alpha: float = 0.14) -> str:
    c = QColor(hex_value)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def stylesheet(p: Palette) -> str:
    return f"""
    * {{ font-size: 10pt; color: {p.text}; }}
    QMainWindow, QWidget#root {{ background: {p.bg}; }}
    QWidget#page {{ background: transparent; }}
    QLabel {{ background: transparent; }}
    QLabel#title {{ font-size: 20pt; font-weight: 600; }}
    QLabel#display {{ font-size: 30pt; font-weight: 700; }}
    QLabel#heading {{ font-size: 22pt; font-weight: 600; }}
    QLabel#lead {{ font-size: 13pt; color: {p.muted}; }}
    QLabel#keycap {{ font-family: "Consolas", "Menlo", monospace; font-size: 20pt; font-weight: 600;
                     padding: 10px 28px; background: {p.surface}; border: 1px solid {p.border};
                     border-bottom: 3px solid {p.border}; border-radius: 12px; }}
    QLabel#section {{ font-size: 9pt; font-weight: 600; color: {p.muted}; letter-spacing: 1px; }}
    QLabel#muted, QLabel#hint {{ color: {p.muted}; }}
    QLabel#hint {{ font-size: 9pt; }}
    QLabel:disabled, QLabel#hint:disabled {{ color: {p.border}; }}
    QFrame#card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; }}
    QFrame#divider {{ background: {p.border}; min-height: 1px; max-height: 1px; border: none; }}
    QFrame#banner {{ background: {_tint(p.accent)}; border: 1px solid {p.accent}; border-radius: 8px; }}
    QFrame#banner[level="error"] {{ background: {_tint(p.danger)}; border-color: {p.danger}; }}
    QFrame#banner QLabel {{ font-weight: 500; }}

    QWidget#sidebar {{ background: {p.bg}; }}
    QPushButton#nav {{ text-align: left; padding: 7px 10px; border-radius: 6px; border: 1px solid transparent;
                       background: transparent; color: {p.text}; }}
    QPushButton#nav:hover {{ background: {p.surface_alt}; }}
    QPushButton#nav:checked {{ background: {p.surface_alt}; font-weight: 600; }}
    QLabel#navgroup {{ font-size: 9pt; font-weight: 600; color: {p.muted}; padding: 12px 0 4px 12px; }}
    QLabel#brand {{ font-size: 12pt; font-weight: 700; }}
    QLabel#crumb {{ font-size: 20pt; color: {p.muted}; }}
    QLabel#sectionhead {{ font-size: 10.5pt; font-weight: 600; }}
    QFrame#link {{ background: transparent; border-radius: 6px; }}
    QFrame#link:hover, QFrame#link:focus {{ background: {p.surface_alt}; }}
    QLineEdit#search {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 6px;
                        padding: 6px 8px; selection-background-color: {p.accent};
                        selection-color: {p.accent_text}; }}
    QLineEdit#search:focus {{ border-color: {p.accent}; }}
    QLabel#badge {{ font-size: 8pt; font-weight: 600; padding: 1px 7px; border-radius: 8px;
                    color: {p.warn}; background: {_tint(p.warn, 0.16)}; }}
    QLabel#badge[tone="info"] {{ color: {p.accent}; background: {_tint(p.accent, 0.14)}; }}
    QWidget#row {{ border-radius: 6px; }}
    QWidget#row[divider="true"] {{ border-top: 1px solid {p.border}; border-radius: 0; }}
    QWidget#row[highlight="true"] {{ background: {_tint(p.accent, 0.16)}; border-radius: 6px;
                                     border-top: 1px solid transparent; }}
    QFrame#result {{ background: transparent; border: 1px solid transparent; border-radius: 6px; }}
    QFrame#result:hover {{ background: {p.surface_alt}; }}
    QFrame#result:focus {{ background: {p.surface_alt}; border-color: {p.accent}; }}

    QPushButton {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 6px;
                   padding: 7px 14px; }}
    QPushButton:hover, QPushButton:focus {{ border-color: {p.accent}; }}
    QPushButton:disabled {{ color: {p.muted}; }}
    QPushButton#primary {{ background: {p.accent}; color: {p.accent_text}; border: none; font-weight: 600; }}
    QPushButton#primary:hover {{ background: {QColor(p.accent).lighter(110).name()}; }}
    QPushButton[size="large"] {{ padding: 12px 32px; font-size: 12pt; border-radius: 14px; }}
    QPushButton#ghost {{ background: transparent; border: none; color: {p.muted}; padding: 6px 8px; }}
    QPushButton#ghost:hover {{ color: {p.text}; }}
    QPushButton#danger {{ background: transparent; border: 1px solid {p.border}; color: {p.danger}; }}
    QPushButton#shortcut {{ font-family: "Consolas", "Menlo", monospace; font-weight: 600;
                            padding: 7px 16px; min-width: 150px; }}
    QPushButton#shortcut[recording="true"] {{ border: 2px solid {p.accent}; color: {p.accent}; }}

    QComboBox {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 6px;
                 padding: 6px 12px; min-width: 190px; }}
    QComboBox:hover, QComboBox:focus {{ border-color: {p.accent}; }}
    QComboBox:disabled {{ color: {p.muted}; }}

    QSlider {{ min-height: 22px; }}
    QSlider::groove:horizontal {{ height: 4px; background: {p.border}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
    QSlider::sub-page:horizontal:disabled {{ background: {p.muted}; }}
    QSlider::handle:horizontal {{ background: {p.surface}; border: 2px solid {p.accent}; width: 12px; height: 12px;
                                  margin: -6px 0; border-radius: 8px; }}
    QSlider::handle:horizontal:hover {{ background: {p.surface_alt}; }}
    QSlider::handle:horizontal:disabled {{ border-color: {p.muted}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border};
                                   selection-background-color: {p.surface_alt}; selection-color: {p.accent};
                                   outline: none; padding: 4px; }}

    QTextEdit, QPlainTextEdit {{ background: transparent; border: none; font-size: 12pt;
                                 selection-background-color: {p.accent}; selection-color: {p.accent_text}; }}
    QFrame#entry {{ background: transparent; border-radius: 6px; }}
    QFrame#entry:hover, QFrame#entry:focus {{ background: {p.surface_alt}; }}

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

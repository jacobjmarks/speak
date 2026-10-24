from .common import _passthrough
from . import common
from PySide6.QtCore import QEasingCurve, QObject, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from .. import theme
from ..pages import _label
from ..widgets import _Animated, draw_check, draw_mic

class StepDots(QWidget):
    """Progress as dots; the current one stretches into a pill."""

    def __init__(self, count: int):
        super().__init__()
        self.count = count
        self.palette_ = theme.LIGHT
        self._value = 0.0
        self._anim = QVariantAnimation(self, duration=360, easingCurve=QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set)
        self.setFixedSize(count * 18 + 28, 14)

    def _set(self, value):
        self._value = float(value)
        self.update()

    def set_current(self, index: int):
        self._anim.stop()
        if common.ANIMATE and self.isVisible():
            self._anim.setStartValue(self._value)
            self._anim.setEndValue(float(index))
            self._anim.start()
        else:
            self._set(index)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        x = 0.0
        for i in range(self.count):
            near = max(0.0, 1 - abs(i - self._value))
            width = 8 + 20 * near
            p.setBrush(QColor(self.palette_.accent if near > 0.5 else self.palette_.border))
            p.drawRoundedRect(QRectF(x, 3, width, 8), 4, 4)
            x += width + 10
        p.end()


class MicPulse(_Animated):
    """Big mic that ripples with your voice, and turns into a check once it has heard you."""

    def __init__(self, level_source):
        super().__init__()
        self.setFixedSize(240, 240)
        self.level_source = level_source
        self.palette_ = theme.LIGHT
        self.active = False
        self._smooth = 0.0
        self._heard_at = None

    def set_active(self, on: bool):
        self.active = on
        self.set_animating(on)

    def set_heard(self, heard: bool):
        if heard and self._heard_at is None:
            self._heard_at = self.phase
        elif not heard:
            self._heard_at = None
        self.set_animating(self.active or heard)
        self.update()

    def paintEvent(self, e):
        pal = self.palette_
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        accent = QColor(pal.accent)
        target = min(1.0, (self.level_source() or 0.0) * 6) if self.active else 0.0
        self._smooth += (target - self._smooth) * 0.25
        p.setPen(Qt.NoPen)
        for i in range(3):
            t = (self.phase * 0.6 + i / 3) % 1.0
            r = 66 + t * (38 + 22 * self._smooth)
            halo = QColor(accent)
            halo.setAlpha(int(110 * (1 - t) * (0.25 + 0.75 * self._smooth)))
            p.setBrush(halo)
            p.drawEllipse(c, r, r)
        r = 58 + 6 * self._smooth
        since = 0.0 if self._heard_at is None else self.phase - self._heard_at
        p.setBrush(QColor(pal.success) if self._heard_at is not None else accent)
        p.drawEllipse(c, r, r)
        if self._heard_at is not None:
            draw_check(p, c, 56, QColor("#ffffff"), min(1.0, since / 0.35))
        else:
            draw_mic(p, c, 60, QColor(pal.accent_text))
        p.end()


class CheckBurst(_Animated):
    """Success mark: disc springs in, then the tick draws itself."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(120, 120)
        self.palette_ = theme.LIGHT
        self._started = None

    def play(self):
        self._started = self.phase
        self.set_animating(True)

    def paintEvent(self, e):
        since = 0.0 if self._started is None else self.phase - self._started
        if since > 1.2:
            self.set_animating(False)
        grow = min(1.0, since / 0.5)
        spring = 1 + 2.2 * (grow - 1) ** 3 + 1.2 * (grow - 1) ** 2
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.palette_.success))
        r = 48 if self._started is None else 48 * max(0.0, spring)
        p.drawEllipse(c, r, r)
        tick = 1.0 if self._started is None else max(0.0, min(1.0, (since - 0.25) / 0.4))
        draw_check(p, c, 52, QColor("#ffffff"), tick)
        p.end()


class ChoiceCard(QAbstractButton):
    """A selectable card: an optional visual on top, a name, one line, and an optional example."""

    def __init__(self, title: str, subtitle: str = "", visual: QWidget = None, example: str = "",
                 compact: bool = False):
        super().__init__()
        self.palette_ = theme.LIGHT
        self._hover = False
        self._radius = 12 if compact else 16
        self._badge_low = visual is not None  # a preview fills the top, so the tick sits by the title
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setAccessibleName(title)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(self)
        margin = 14 if compact else 20
        layout.setContentsMargins(margin, margin - 2, margin, margin - 2)
        layout.setSpacing(4 if compact else 6)
        if visual is not None:
            layout.addWidget(visual)
            layout.addSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 12pt; font-weight: 600;")
        layout.addWidget(self.title_label)
        self.subtitle_label = _label(subtitle, "hint") if subtitle else None
        if self.subtitle_label:
            layout.addWidget(self.subtitle_label)
        self.example_label = _label(example) if example else None
        if self.example_label:
            layout.addSpacing(2)
            self.example_label.setMinimumHeight(2 * self.example_label.fontMetrics().lineSpacing())
            layout.addWidget(self.example_label)
        layout.addStretch(1)
        _passthrough(self)

    def set_texts(self, subtitle: str, example: str = ""):
        if self.subtitle_label:
            self.subtitle_label.setText(subtitle)
        if self.example_label:
            self.example_label.setText(example)
            self.example_label.updateGeometry()
        self.updateGeometry()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        pal, r = self.palette_, self._radius
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        edge = QColor(pal.border)
        width = 1.0
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal.surface))
        p.drawRoundedRect(rect, r, r)
        if self.isChecked():
            edge = QColor(pal.accent)
            width = 2.0
            tint = QColor(pal.accent)
            tint.setAlphaF(0.09)
            p.setBrush(tint)
            p.drawRoundedRect(rect, r, r)
        elif self._hover:
            edge = QColor(pal.muted)
        p.setPen(QPen(edge, width))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, r, r)
        if self.isChecked():
            c = QPointF(rect.right() - 20, rect.bottom() - 20 if self._badge_low else rect.top() + 20)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal.accent))
            p.drawEllipse(c, 10, 10)
            draw_check(p, c, 13, QColor(pal.accent_text))
        if self.hasFocus():
            p.setPen(QPen(QColor(pal.accent), 2, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), r + 1, r + 1)
        p.end()


class OptionGroup(QObject):
    picked = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.cards = {}

    def add(self, key: str, card: QAbstractButton):
        self.group.addButton(card)
        self.cards[key] = card
        card.clicked.connect(lambda _=False, k=key: self.picked.emit(k))

    def set_value(self, key: str):
        card = self.cards.get(key)
        if card is not None:
            card.setChecked(True)


class Chip(QAbstractButton):
    """One pill in a Segmented row, with an optional muted second line; fades when disabled."""

    def __init__(self, text: str, sub: str = ""):
        super().__init__()
        self.setText(text)
        self.sub = sub
        self.palette_ = theme.LIGHT
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self._height = 46 if sub else 34
        self.setFixedHeight(self._height)
        metrics = QFontMetrics(self.font())
        self._width = max(metrics.horizontalAdvance(text), metrics.horizontalAdvance(sub) * 0.85) + 36

    def sizeHint(self):
        return QSize(int(self._width), self._height)

    minimumSizeHint = sizeHint

    def paintEvent(self, e):
        pal = self.palette_
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        checked = self.isChecked()
        radius = rect.height() / 2 if not self.sub else 18
        p.setPen(QPen(QColor(pal.accent if checked else pal.border), 1))
        p.setBrush(QColor(pal.accent) if checked else QColor(pal.surface))
        p.drawRoundedRect(rect, radius, radius)
        p.setPen(QColor(pal.accent_text if checked else pal.text))
        font = self.font()
        font.setWeight(font.Weight.DemiBold if checked else font.Weight.Normal)
        p.setFont(font)
        if self.sub:
            p.drawText(QRectF(rect.left(), rect.top() + 4, rect.width(), 20), Qt.AlignCenter, self.text())
            small = self.font()
            small.setPointSizeF(small.pointSizeF() * 0.85)
            p.setFont(small)
            muted = QColor(pal.accent_text if checked else pal.muted)
            muted.setAlphaF(0.85 if checked else 1.0)
            p.setPen(muted)
            p.drawText(QRectF(rect.left(), rect.top() + 21, rect.width(), 18), Qt.AlignCenter, self.sub)
        else:
            p.drawText(rect, Qt.AlignCenter, self.text())
        if self.hasFocus():
            p.setPen(QPen(QColor(pal.accent), 2, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), radius + 1, radius + 1)
        p.end()


class Segmented(QWidget):
    """A row of exclusive chips: `picked(key)` on click, `set_value` for programmatic changes.

    An option is a label, or a (label, muted second line) pair."""

    picked = Signal(str)

    def __init__(self, options: dict, current: str = ""):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.group = OptionGroup(self)
        self.chips = {}
        for key, option in options.items():
            chip = Chip(*([option] if isinstance(option, str) else option))
            self.group.add(key, chip)
            self.chips[key] = chip
            row.addWidget(chip)
        self.group.picked.connect(self.picked)
        self.set_value(current)

    def set_value(self, key: str):
        """Select `key`; an unknown key (e.g. "") leaves nothing selected."""
        self.group.group.setExclusive(False)
        for chip_key, chip in self.chips.items():
            chip.setChecked(chip_key == key)
        self.group.group.setExclusive(True)


class ModeGlyph(QWidget):
    """The key presses behind a shortcut mode: a held bar, two taps, or both."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.palette_ = theme.LIGHT
        self.setFixedHeight(48)

    def paintEvent(self, e):
        pal = self.palette_
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, mid = self.width(), self.height() / 2
        accent = QColor(pal.accent)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal.surface_alt))
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        p.setBrush(accent)

        def bar(x0, x1):
            p.drawRoundedRect(QRectF(w * x0, mid - 7, w * (x1 - x0), 14), 7, 7)

        def tap(x):
            p.drawEllipse(QPointF(w * x, mid), 7, 7)

        def span(x0, x1):
            line = QColor(accent)
            line.setAlphaF(0.35)
            p.setBrush(line)
            p.drawRoundedRect(QRectF(w * x0, mid - 2, w * (x1 - x0), 4), 2, 2)
            p.setBrush(accent)

        if self.kind == "hold":
            bar(0.2, 0.8)
        elif self.kind == "toggle":
            span(0.2, 0.8)
            tap(0.2)
            tap(0.8)
        else:
            bar(0.1, 0.42)
            span(0.58, 0.9)
            tap(0.58)
            tap(0.9)
        p.end()


class ThemeSwatch(QWidget):
    """A miniature app window in the theme's own colours (System shows both halves)."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.setFixedHeight(110)

    def _mock(self, p, rect, pal):
        p.setPen(QPen(QColor(pal.border), 1))
        p.setBrush(QColor(pal.bg))
        p.drawRoundedRect(rect, 10, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal.surface_alt))
        p.drawRoundedRect(QRectF(rect.left() + 8, rect.top() + 8, rect.width() * 0.22, rect.height() - 16), 5, 5)
        p.setBrush(QColor(pal.surface))
        card = QRectF(rect.left() + rect.width() * 0.22 + 18, rect.top() + 8, rect.width() * 0.78 - 28,
                      rect.height() - 16)
        p.drawRoundedRect(card, 6, 6)
        p.setBrush(QColor(pal.accent))
        p.drawRoundedRect(QRectF(card.left() + 8, card.top() + 10, card.width() * 0.4, 8), 4, 4)
        muted = QColor(pal.muted)
        muted.setAlphaF(0.45)
        p.setBrush(muted)
        p.drawRoundedRect(QRectF(card.left() + 8, card.top() + 28, card.width() * 0.7, 6), 3, 3)
        p.drawRoundedRect(QRectF(card.left() + 8, card.top() + 42, card.width() * 0.5, 6), 3, 3)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.kind == "System":
            self._mock(p, rect, theme.LIGHT)
            clip = QPainterPath()
            clip.addPolygon(QPolygonF([QPointF(rect.right() - rect.width() * 0.5, rect.top()),
                                       QPointF(rect.right(), rect.top()), QPointF(rect.right(), rect.bottom()),
                                       QPointF(rect.right() - rect.width() * 0.7, rect.bottom())]))
            p.setClipPath(clip)
            self._mock(p, rect, theme.DARK)
        else:
            self._mock(p, rect, theme.DARK if self.kind == "Dark" else theme.LIGHT)
        p.end()

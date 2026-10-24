"""First-run setup: a short, visual walk through the choices that matter.

Welcome -> Microphone -> Shortcut -> Tidy up (with a speed test) -> Indicator -> Look & updates -> Done.
Every screen is one centered column; choices are cards or chips with live examples. Options that don't apply to the
current choice stay visible but greyed out. Changing a tidy option cancels the running speed test and re-runs it.
"""
import math

from PySide6.QtCore import (QEasingCurve, QObject, QParallelAnimationGroup, QPauseAnimation, QPoint,
                            QPointF, QPropertyAnimation, QRectF, QSequentialAnimationGroup, QSize, Qt, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QSlider, QStackedWidget, QVBoxLayout, QWidget)

from .. import audio, config, hotkey, system_audio, tidy
from ..benchmark import Result
from ..controller import FINISHING
from . import theme
from .overlay import EDGE, Overlay
from .pages import MicCombo, Page, SettingRow, _combo, _label
from .widgets import BARS, ShortcutButton, Toggle, WaveStrip, _Animated, draw_check, draw_mic

HEARD_LEVEL = 0.04          # mic level (0..1) that counts as "heard you"
AMBER = "#d9a441"
SAY = "um so the meeting is tuesday no wait wednesday"
# What each tidy level really produces for SAY (see cleanup.finalize); the AI example depends on the model.
EXAMPLE_OFF = "Um so the meeting is tuesday no wait wednesday"
EXAMPLE_QUICK = "So the meeting is tuesday no wait wednesday"
EXAMPLE_LITERAL = "So the meeting is Tuesday, no wait, Wednesday."
EXAMPLE_SMART = "The meeting is Wednesday."
STAGE_TEXT = "Hi team, the meeting is on Wednesday at three. Please send me the notes before then."
STAGE_FROZEN_WORDS = 9
COLUMN_WIDTH = 820
ANIMATE = True              # tests switch this off so screens are complete the moment they appear

SHORTCUT_HINTS = {"auto": "Hold while you speak, or tap to start and stop",
                  "hold": "Hold while you speak. Let go to finish",
                  "toggle": "Tap to start. Tap again to stop"}
UPDATE_HINTS = {"auto": "Checks daily and installs when you restart Speak",
                "notify": "Checks daily and tells you. Nothing installs by itself",
                "off": "Never checks. You can check by hand in Settings"}
MODEL_CHOICES = {"auto": ("Automatic", "Best fit"),
                 "small": ("Small", f"Uses ~{round(tidy._memory_required_mb(config.SMALL_MODEL) / 1000)} GB"),
                 "large": ("Large", f"Uses ~{round(tidy._memory_required_mb(config.LARGE_MODEL) / 1000)} GB")}


def _seconds(value: float) -> str:
    return "under 0.1 s" if value < 0.1 else f"{value:.1f} s"


def _passthrough(widget: QWidget):
    """Let clicks on a card's contents reach the card."""
    for child in widget.findChildren(QWidget):
        child.setAttribute(Qt.WA_TransparentForMouseEvents)


def _ai_changes(choice: str) -> dict:
    """Settings behind the AI model chips: Automatic and Large are tidy levels, Small pins the small model."""
    if choice == "small":
        return {"tidy": "auto", "cleanup_model": config.SMALL_MODEL}
    return {"tidy": "best" if choice == "large" else "auto", "cleanup_model": "auto"}


def _model_choice(settings: dict) -> str:
    if settings["tidy"] == "best" or settings.get("cleanup_model") == config.LARGE_MODEL:
        return "large"
    return "small" if settings.get("cleanup_model") == config.SMALL_MODEL else "auto"


def _level(settings: dict) -> str:
    return "ai" if settings["tidy"] in ("auto", "best") else settings["tidy"]


# ---------- motion ----------

class Revealer:
    """Fades and raises widgets in one after another. Effects are removed afterwards so nothing keeps repainting
    through an offscreen buffer."""

    def __init__(self):
        self._group = None
        self._ends = {}

    def stop(self):
        group, self._group = self._group, None
        if group is not None:
            group.stop()
        ends, self._ends = self._ends, {}
        for widget, pos in ends.items():
            try:
                widget.setGraphicsEffect(None)
                if pos is not None:
                    widget.move(pos)
            except RuntimeError:
                pass

    def play(self, widgets, root: QWidget, delay: int = 70, duration: int = 520, rise: int = 24):
        self.stop()
        if not ANIMATE:
            return
        widgets = [w for w in widgets if w is not None]
        for widget in widgets:
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)
            self._ends[widget] = None
        token = self._ends
        QTimer.singleShot(0, lambda: self._start(token, widgets, root, delay, duration, rise))

    def _start(self, token, widgets, root, delay, duration, rise):
        if token is not self._ends:
            return
        if root.layout() is not None:
            root.layout().activate()
        group = QParallelAnimationGroup()
        for i, widget in enumerate(widgets):
            end = widget.pos()
            self._ends[widget] = end
            widget.move(end + QPoint(0, rise))
            step = QParallelAnimationGroup()
            fade = QPropertyAnimation(widget.graphicsEffect(), b"opacity")
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setDuration(duration)
            fade.setEasingCurve(QEasingCurve.OutCubic)
            lift = QPropertyAnimation(widget, b"pos")
            lift.setStartValue(end + QPoint(0, rise))
            lift.setEndValue(end)
            lift.setDuration(duration)
            lift.setEasingCurve(QEasingCurve.OutExpo)
            step.addAnimation(fade)
            step.addAnimation(lift)
            sequence = QSequentialAnimationGroup()
            sequence.addAnimation(QPauseAnimation(i * delay))
            sequence.addAnimation(step)
            group.addAnimation(sequence)
        group.finished.connect(self.stop)
        self._group = group
        group.start()


# ---------- painted pieces ----------

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
        if ANIMATE and self.isVisible():
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
        self.set_animating(on or self._heard_at is not None)

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
        self._t0 = None

    def play(self):
        self._t0 = self.phase
        self.set_animating(True)

    def paintEvent(self, e):
        since = 0.0 if self._t0 is None else self.phase - self._t0
        if since > 1.2:
            self.set_animating(False)
        grow = min(1.0, since / 0.5)
        spring = 1 + 2.2 * (grow - 1) ** 3 + 1.2 * (grow - 1) ** 2
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.palette_.success))
        r = 48 if self._t0 is None else 48 * max(0.0, spring)
        p.drawEllipse(c, r, r)
        tick = 1.0 if self._t0 is None else max(0.0, min(1.0, (since - 0.25) / 0.4))
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


class SpeedStage(_Animated):
    """The real indicator, driven by the speed test so you watch what dictating looks like while it's timed."""

    HEIGHT = 52
    IDLE_TEXT = "Time a sample dictation"

    def __init__(self):
        super().__init__()
        self._palette = theme.LIGHT
        self._overlay = Overlay(lambda: 0.0)
        self._phase = ("idle", "")
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    @property
    def palette_(self):
        return self._palette

    @palette_.setter
    def palette_(self, value):
        self._palette = value
        self._overlay.palette_ = value

    def set_phase(self, mode: str, word: str = ""):
        """`mode` is "idle", or an indicator mode: preparing, listening, processing, done."""
        self._phase = (mode, word)
        self.set_animating(ANIMATE and mode in ("preparing", "listening", "processing") and self.isVisible())
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self.set_phase(*self._phase)

    def hideEvent(self, e):
        super().hideEvent(e)
        self.set_animating(False)

    def paintEvent(self, e):
        pal = self._palette
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        mode, word = self._phase
        if mode == "idle":
            p.setPen(QColor(pal.muted))
            p.drawText(rect, Qt.AlignCenter, word or self.IDLE_TEXT)
            p.end()
            return
        overlay = self._overlay
        overlay.palette_ = pal
        level = 0.0
        if mode == "listening":
            level = abs(math.sin(self.phase * 7)) * (0.35 + 0.6 * abs(math.sin(self.phase * 2.3)))
            if not ANIMATE:
                for i in range(BARS):
                    overlay.snapshot(mode, "", 0.25 + 0.6 * abs(math.sin(i * 0.9)), word)
        pm = overlay.snapshot(mode, "", level, word)
        if mode == "done":
            overlay._mode_t = overlay.phase - 5   # skip the check's draw-in animation
            pm = overlay.snapshot(mode, "", level, word)
        size = pm.deviceIndependentSize()
        p.drawPixmap(QPointF(rect.center().x() - size.width() / 2, rect.center().y() - size.height() / 2), pm)
        p.end()


class OverlayStage(_Animated):
    """A mock screen playing the real indicator: words arrive, "Finishing up", a check, then the text lands.

    The indicator is the app's own `Overlay` rendered offscreen, so its look can't drift from the real thing.
    """

    WORD_SECONDS = 0.3
    PROCESS_SECONDS = 1.1
    DONE_SECONDS = 1.0
    REST_SECONDS = 1.2

    def __init__(self):
        super().__init__()
        self.live = "line"
        self.position = "cursor"
        self._palette = theme.LIGHT
        self._overlay = Overlay(lambda: 0.0)
        self._words = STAGE_TEXT.split()
        self.setFixedHeight(300)
        self.setMinimumWidth(480)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    @property
    def palette_(self):
        return self._palette

    @palette_.setter
    def palette_(self, value):
        self._palette = value
        self._overlay.palette_ = value

    def set_options(self, live: str, position: str):
        self.live, self.position = live, position
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self.set_animating(ANIMATE)

    def hideEvent(self, e):
        super().hideEvent(e)
        self.set_animating(False)

    def _moment(self) -> tuple:
        """(indicator mode or None, words shown, text has landed in the window)"""
        if not ANIMATE:
            return "listening", STAGE_FROZEN_WORDS, False
        listen = len(self._words) * self.WORD_SECONDS + 0.5
        t = self.phase % (listen + self.PROCESS_SECONDS + self.DONE_SECONDS + self.REST_SECONDS)
        if t < listen:
            return "listening", min(len(self._words), int(t / self.WORD_SECONDS)), False
        t -= listen
        if t < self.PROCESS_SECONDS:
            return "processing", len(self._words), False
        t -= self.PROCESS_SECONDS
        return ("done" if t < self.DONE_SECONDS else None), len(self._words), True

    def _snapshot(self, mode: str, words: int):
        overlay = self._overlay
        overlay.preview, overlay.position = self.live, self.position
        overlay.palette_ = self._palette
        text = " ".join(self._words[:words])
        word = FINISHING if mode == "processing" else ""
        if not ANIMATE:
            for i in range(BARS):
                overlay.snapshot(mode, text, 0.25 + 0.6 * abs(math.sin(i * 0.9)), word)
        level = abs(math.sin(self.phase * 7)) * (0.35 + 0.6 * abs(math.sin(self.phase * 2.3)))
        return overlay.snapshot(mode, text, level, word)

    def paintEvent(self, e):
        pal = self._palette
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        screen = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(pal.border), 1))
        p.setBrush(QColor(pal.surface_alt))
        p.drawRoundedRect(screen, 14, 14)
        win = QRectF(screen.left() + 56, screen.top() + 30, screen.width() - 112, screen.height() - 52)
        p.setBrush(QColor(pal.surface))
        p.drawRoundedRect(win, 10, 10)
        p.setPen(Qt.NoPen)
        for i in range(3):
            dot = QColor(pal.muted)
            dot.setAlphaF(0.35)
            p.setBrush(dot)
            p.drawEllipse(QPointF(win.left() + 16 + i * 14, win.top() + 14), 4, 4)

        mode, words, landed = self._moment()
        body = win.adjusted(24, 36, -24, -12)
        if landed:
            font = self.font()
            font.setPointSizeF(10.5)
            p.setFont(font)
            p.setPen(QColor(pal.text))
            p.drawText(body, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, STAGE_TEXT)
        else:
            line = QColor(pal.muted)
            line.setAlphaF(0.22)
            p.setBrush(line)
            for i, frac in enumerate((0.8, 0.62, 0.4)):
                p.drawRoundedRect(QRectF(body.left(), body.top() + 6 + i * 20, body.width() * frac, 7), 3.5, 3.5)

        pointer = QPointF(win.left() + win.width() * 0.4, win.top() + 78)
        if mode is not None:
            pm = self._snapshot(mode, words)
            size = pm.deviceIndependentSize()
            w, h = size.width(), size.height()
            if self.position == "cursor":
                x, y = pointer.x() - w / 2, pointer.y() + 18
            elif self.position == "top":
                x, y = screen.center().x() - w / 2, screen.top() + EDGE
            else:
                x, y = screen.center().x() - w / 2, screen.bottom() - h - EDGE
            x = max(screen.left() + 4, min(x, screen.right() - w - 4))
            y = max(screen.top() + 4, min(y, screen.bottom() - h - 4))
            p.drawPixmap(QPointF(x, y), pm)
        self._draw_pointer(p, pointer, pal)
        p.end()

    def _draw_pointer(self, p, at: QPointF, pal):
        arrow = QPolygonF([QPointF(0, 0), QPointF(0, 17), QPointF(4.5, 13), QPointF(7.5, 20),
                           QPointF(10.5, 18.8), QPointF(7.6, 12), QPointF(13, 12)])
        p.save()
        p.translate(at)
        p.setPen(QPen(QColor(pal.surface), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(QColor(pal.text))
        p.drawPolygon(arrow)
        p.restore()


# ---------- the page ----------

class OnboardingPage(Page):
    """Settings are emitted through `changed` as they're picked, like the Settings page.

    `test_requested(pcm, rate)` asks the app to time the pipeline (`pcm` is None for the bundled sample);
    `test_cancelled` asks it to stop one that is running, e.g. because a setting changed under it.
    """

    changed = Signal(dict)
    skipped = Signal()
    finished = Signal()
    test_requested = Signal(object, int)
    test_cancelled = Signal()
    shortcut_recording = Signal(bool)

    WELCOME, THEME, MIC, KEYS, TIDY, LOOK, APP, DONE = range(8)
    SPEED_IDLE = ""

    def __init__(self, settings: dict, can_rescan_mics=lambda: False, logo: QWidget = None):
        super().__init__()
        self.layout_.setContentsMargins(56, 24, 56, 28)
        self.layout_.setSpacing(0)
        self.palette_ = theme.LIGHT
        self._mic = None
        self._heard = False
        self._testing = False   # a speed test is running in the app
        self._tested = False
        self._level = 0.0
        self._out = None
        self._reveals = {}
        self._revealer = Revealer()
        self._tidy = {k: settings[k] for k in ("tidy", "cleanup_model", "cleanup_device", "corrections")}
        self._model = _model_choice(settings)
        self._poll = QTimer(self, interval=60, timeout=self._read_level)
        self._retest = QTimer(self, singleShot=True, interval=900, timeout=self._retest_now)

        top = QHBoxLayout()
        top.addStretch(1)
        self.skip_button = QPushButton("Skip setup", objectName="ghost", cursor=Qt.PointingHandCursor)
        self.skip_button.clicked.connect(self.skipped)
        top.addWidget(self.skip_button)
        self.layout_.addLayout(top)

        self.steps = QStackedWidget()
        self.steps.addWidget(self._welcome_step(logo))
        self.steps.addWidget(self._theme_step(settings))
        self.steps.addWidget(self._mic_step(settings, can_rescan_mics))
        self.steps.addWidget(self._keys_step(settings))
        self.steps.addWidget(self._tidy_step(settings))
        self.steps.addWidget(self._look_step(settings))
        self.steps.addWidget(self._app_step(settings))
        self.steps.addWidget(self._done_step(settings))
        self.layout_.addWidget(self.steps, 1)

        self.bar = QWidget()
        bar = QHBoxLayout(self.bar)
        bar.setContentsMargins(0, 8, 0, 0)
        self.back_button = QPushButton("Back", objectName="ghost", cursor=Qt.PointingHandCursor)
        self.back_button.clicked.connect(lambda: self.go(self.steps.currentIndex() - 1))
        self.dots = StepDots(self.APP - self.THEME + 1)
        self.next_button = QPushButton("Next", objectName="primary", cursor=Qt.PointingHandCursor)
        self.next_button.setProperty("size", "large")
        self.next_button.clicked.connect(lambda: self.go(self.steps.currentIndex() + 1))
        bar.addWidget(self.back_button, 1, Qt.AlignLeft)
        bar.addWidget(self.dots, 0, Qt.AlignCenter)
        bar.addWidget(self.next_button, 1, Qt.AlignRight)
        self.layout_.addWidget(self.bar)
        self.set_gpus(tidy.gpus(), settings["cleanup_device"])
        self._refresh_tidy()
        self._show(0, animate=False)

    # ----- building blocks -----

    def _step(self) -> tuple:
        """(step, column layout): every screen is one centered column."""
        step = QWidget()
        outer = QHBoxLayout(step)
        outer.setContentsMargins(0, 0, 0, 0)
        column = QWidget()
        column.setMaximumWidth(COLUMN_WIDTH)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        outer.addStretch(1)
        outer.addWidget(column, 100)
        outer.addStretch(1)
        return step, layout

    def _heading(self, text: str, lead: str = "") -> tuple:
        heading = _label(text, "heading")
        heading.setAlignment(Qt.AlignCenter)
        if not lead:
            return heading, None
        sub = _label(lead, "lead")
        sub.setAlignment(Qt.AlignCenter)
        return heading, sub

    def _row(self, *widgets, spacing: int = 14) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing)
        for widget in widgets:
            row.addWidget(widget)
        return box

    def _cards(self, group: OptionGroup, cards: dict, on_pick) -> QWidget:
        row = QHBoxLayout()
        row.setSpacing(14)
        holder = QWidget()
        holder.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        for key, card in cards.items():
            group.add(key, card)
            row.addWidget(card)
        group.picked.connect(on_pick)
        return holder

    def _settings_card(self, *rows: QWidget) -> QFrame:
        card = QFrame(objectName="card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 4, 22, 4)
        layout.setSpacing(0)
        for i, row in enumerate(rows):
            if i:
                layout.addWidget(QFrame(objectName="divider"))
            layout.addWidget(row)
        return card

    def _welcome_step(self, logo) -> QWidget:
        step, layout = self._step()
        layout.addStretch(2)
        self.logo = logo if logo is not None else QWidget()
        layout.addWidget(self.logo, 0, Qt.AlignHCenter)
        layout.addSpacing(10)
        title = _label("Speak", "display")
        title.setAlignment(Qt.AlignCenter)
        lead = _label("Hold a key and talk.\nYour words appear wherever you're typing.", "lead")
        lead.setAlignment(Qt.AlignCenter)
        self.ambient = WaveStrip(lambda: 0.0)
        self.ambient.set_state("processing", "")
        start = QPushButton("Get started", objectName="primary", cursor=Qt.PointingHandCursor)
        start.setProperty("size", "large")
        start.clicked.connect(lambda: self.go(self.THEME))
        layout.addWidget(title)
        layout.addWidget(lead)
        layout.addSpacing(8)
        layout.addWidget(self.ambient, 0, Qt.AlignHCenter)
        layout.addSpacing(8)
        layout.addWidget(start, 0, Qt.AlignHCenter)
        layout.addStretch(3)
        self._reveals[self.WELCOME] = [self.logo, title, lead, self.ambient, start]
        return step

    def _theme_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.setSpacing(16)
        layout.addStretch(1)
        heading, _ = self._heading("Pick your look")
        layout.addWidget(heading)
        layout.addSpacing(6)
        self.theme_options = OptionGroup(self)
        cards = {name: ChoiceCard(name, visual=ThemeSwatch(name)) for name in config.THEMES}
        self.theme_cards = list(cards.values())
        layout.addWidget(self._cards(self.theme_options, cards, lambda key: self.changed.emit({"theme": key})))
        self.theme_options.set_value(settings["theme"])
        layout.addStretch(2)
        self._reveals[self.THEME] = [heading, *self.theme_cards]
        return step

    def _mic_step(self, settings: dict, can_rescan_mics) -> QWidget:
        step, layout = self._step()
        heading, _ = self._heading("Pick your microphone")
        layout.addWidget(heading)
        layout.addStretch(1)
        self.pulse = MicPulse(lambda: self._level)
        layout.addWidget(self.pulse, 0, Qt.AlignHCenter)
        self.mic_status = _label("Say something", "lead")
        self.mic_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.mic_status)
        self.mic_combo = MicCombo(settings["mic_device"], can_rescan_mics)
        self.mic_combo.setMinimumWidth(320)
        self.mic_combo.currentIndexChanged.connect(self._on_mic_changed)
        self.retry_button = QPushButton("Try again", objectName="ghost", cursor=Qt.PointingHandCursor)
        self.retry_button.clicked.connect(self._start_monitor)
        # Takes its space while hidden so the picker above doesn't jump when it appears.
        self.retry_button.setSizePolicy(self.retry_button.sizePolicy().horizontalPolicy(),
                                        QSizePolicy.Fixed)
        policy = self.retry_button.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.retry_button.setSizePolicy(policy)
        self.retry_button.hide()
        layout.addWidget(self.mic_combo, 0, Qt.AlignHCenter)
        layout.addWidget(self.retry_button, 0, Qt.AlignHCenter)
        layout.addStretch(2)
        self._reveals[self.MIC] = [heading, self.pulse, self.mic_status, self.mic_combo, self.retry_button]
        return step

    def _keys_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.setSpacing(14)
        heading, _ = self._heading("Your shortcut")
        layout.addWidget(heading)
        self.shortcut = ShortcutButton(settings["hotkey"])
        self.shortcut.setProperty("size", "large")
        self.shortcut.setMinimumWidth(200)
        self.shortcut.captured.connect(lambda combo: self.changed.emit({"hotkey": combo}))
        self.shortcut.recording.connect(self.shortcut_recording)
        change_hint = _label("Click to change it", "hint")
        change_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.shortcut, 0, Qt.AlignHCenter)
        layout.addWidget(change_hint)
        layout.addSpacing(6)

        self.mode_options = OptionGroup(self)
        # Hold and tap first, so "Hold or tap" reads as the combination of the two.
        cards = {key: ChoiceCard(config.SHORTCUT_MODES[key], SHORTCUT_HINTS[key], visual=ModeGlyph(key))
                 for key in ("hold", "toggle", "auto")}
        self.mode_cards = list(cards.values())
        self.mode_options.set_value(settings["shortcut_mode"])
        modes = self._cards(self.mode_options, cards, lambda key: self.changed.emit({"shortcut_mode": key}))
        self.mode_options.set_value(settings["shortcut_mode"])
        layout.addWidget(modes)
        layout.addSpacing(6)

        self.dim_toggle = Toggle()
        self.dim_toggle.setChecked(settings["audio_dim_enabled"])
        self.dim_toggle.toggled.connect(self._on_dim_toggled)
        dim_row = SettingRow("Quiet other sounds while I talk", "Lowers music and videos, then restores them",
                             self.dim_toggle)
        self.dim_slider = QSlider(Qt.Horizontal)
        self.dim_slider.setAccessibleName("Reduce system audio by")
        self.dim_slider.setRange(10, 90)
        self.dim_slider.setSingleStep(config.AUDIO_DIM_STEP)
        self.dim_slider.setPageStep(10)
        self.dim_slider.setValue(settings["audio_dim_percent"])
        self.dim_slider.setEnabled(settings["audio_dim_enabled"])
        self.dim_slider.valueChanged.connect(self._on_dim_changed)
        self.dim_value = QLabel(f'{settings["audio_dim_percent"]}%')
        self.dim_value.setMinimumWidth(42)
        self.dim_slider.setMinimumWidth(240)
        self.dim_level_row = SettingRow("Reduce by", "", self._row(self.dim_slider, self.dim_value, spacing=10))
        self.dim_card = self._settings_card(dim_row, self.dim_level_row)
        self.dim_card.setVisible(system_audio.SUPPORTED)
        layout.addWidget(self.dim_card)
        layout.addStretch(1)
        self._reveals[self.KEYS] = [heading, self.shortcut, change_hint, *self.mode_cards, self.dim_card]
        return step

    def _tidy_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.setSpacing(12)
        heading, say = self._heading("Tidy up your words", f"You say  “{SAY}”")
        layout.addWidget(heading)
        layout.addWidget(say)

        self.tidy_options = OptionGroup(self)
        self.level_cards = {"off": ChoiceCard("Off", "Exactly as said", example=f"“{EXAMPLE_OFF}”"),
                            "fast": ChoiceCard("Quick", "Removes ums, instant", example=f"“{EXAMPLE_QUICK}”"),
                            "ai": ChoiceCard("Smart", "…", example="…")}
        for card in self.level_cards.values():
            card.setMinimumHeight(140)
        cards = self._cards(self.tidy_options, self.level_cards, self._on_level)
        layout.addWidget(cards)

        self.model_options = Segmented(MODEL_CHOICES, self._model)
        self.model_options.picked.connect(self._on_model)
        self.model_row = SettingRow("Model size", " ", self.model_options)
        self.device = _combo(config.CLEANUP_DEVICES, settings["cleanup_device"])
        self.device.currentIndexChanged.connect(
            lambda: self._config_changed({"cleanup_device": self.device.currentData()}))
        self.device_row = SettingRow("Runs on", " ", self.device)
        self.corrections = Toggle()
        self.corrections.setChecked(settings["corrections"])
        self.corrections.toggled.connect(lambda on: self._config_changed({"corrections": on}))
        self.corrections_row = SettingRow("Fix changes of mind", " ", self.corrections)
        self.options_card = self._settings_card(self.model_row, self.device_row, self.corrections_row)
        layout.addWidget(self.options_card)

        layout.addWidget(self._speed_strip())
        layout.addStretch(1)
        self._reveals[self.TIDY] = [heading, say, *self.level_cards.values(), self.options_card, self.speed_card]
        return step

    def _speed_strip(self) -> QFrame:
        """Fixed-size card: the indicator playing the test on top, buttons left and the result right."""
        self.speed_card = QFrame(objectName="card")
        card = QVBoxLayout(self.speed_card)
        card.setContentsMargins(18, 12, 18, 12)
        card.setSpacing(8)
        self.test_stage = SpeedStage()
        self.latency_label = QLabel("")
        self.latency_label.setFixedSize(100, 34)
        self.latency_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.latency_label.setStyleSheet("font-size: 20pt; font-weight: 700;")
        self.verdict_label = _label(self.SPEED_IDLE, "hint")
        self.verdict_label.setFixedSize(60, 34)
        self.verdict_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.sample_button = QPushButton("Test speed", objectName="primary", cursor=Qt.PointingHandCursor)
        self.sample_button.setToolTip("Time a bundled sample recording")
        self.sample_button.clicked.connect(self._start_test)
        self.details_button = QPushButton("Details", objectName="ghost", cursor=Qt.PointingHandCursor)
        self.details_button.clicked.connect(self._toggle_details)
        policy = self.details_button.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.details_button.setSizePolicy(policy)
        self.details_button.hide()
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.sample_button)
        row.addWidget(self.details_button)
        row.addWidget(self.test_stage, 1)
        row.addWidget(self.verdict_label)
        row.addWidget(self.latency_label)
        card.addLayout(row)

        self.details_box = QWidget()
        details = QVBoxLayout(self.details_box)
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(4)
        self.text_label = _label("", "hint")
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details_label = _label("", "hint")
        details.addWidget(self.text_label)
        details.addWidget(self.details_label)
        self.details_box.hide()
        card.addWidget(self.details_box)
        return self.speed_card

    def _look_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.setSpacing(14)
        heading, _ = self._heading("Your on-screen indicator")
        layout.addWidget(heading)
        self.stage = OverlayStage()
        self.stage.set_options(settings["live_preview"], settings["overlay_position"])
        layout.addWidget(self.stage)

        self.live_options = Segmented(config.LIVE_PREVIEWS, settings["live_preview"])
        self.live_options.picked.connect(lambda key: self._on_overlay({"live_preview": key}))
        self.position_options = Segmented(config.OVERLAY_POSITIONS, settings["overlay_position"])
        self.position_options.picked.connect(lambda key: self._on_overlay({"overlay_position": key}))
        controls = []
        for caption, chips in (("Live text", self.live_options), ("Position", self.position_options)):
            box = QWidget()
            col = QVBoxLayout(box)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(6)
            label = _label(caption, "section")
            label.setAlignment(Qt.AlignCenter)
            col.addWidget(label)
            col.addWidget(chips, 0, Qt.AlignHCenter)
            controls.append(box)
        row = self._row(*controls, spacing=48)
        layout.addWidget(row, 0, Qt.AlignHCenter)
        layout.addStretch(1)
        self._reveals[self.LOOK] = [heading, self.stage, row]
        return step

    def _app_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.setSpacing(16)
        layout.addStretch(1)
        heading, _ = self._heading("Stay up to date")
        layout.addWidget(heading)
        layout.addSpacing(6)
        self.updates_options = OptionGroup(self)
        cards = {key: ChoiceCard(label, UPDATE_HINTS[key]) for key, label in config.UPDATE_MODES.items()}
        for card in cards.values():
            card.setMinimumHeight(110)
        self.update_cards = list(cards.values())
        layout.addWidget(self._cards(self.updates_options, cards, lambda key: self.changed.emit({"updates": key})))
        self.updates_options.set_value(settings["updates"])
        self.prereleases = Toggle()
        self.prereleases.setChecked(settings["prereleases"])
        self.prereleases.toggled.connect(lambda on: self.changed.emit({"prereleases": on}))
        self.prerelease_card = self._settings_card(
            SettingRow("Try new versions early", "They arrive sooner and may have bugs", self.prereleases))
        layout.addWidget(self.prerelease_card)
        layout.addStretch(2)
        self._reveals[self.APP] = [heading, *self.update_cards, self.prerelease_card]
        return step

    def _done_step(self, settings: dict) -> QWidget:
        step, layout = self._step()
        layout.addStretch(2)
        self.burst = CheckBurst()
        layout.addWidget(self.burst, 0, Qt.AlignHCenter)
        heading = _label("You're all set", "display")
        heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(heading)
        self.keycap = QLabel("", objectName="keycap")
        self.keycap.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.keycap, 0, Qt.AlignHCenter)
        self.shortcut_hint = _label("", "lead")
        self.shortcut_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.shortcut_hint)
        layout.addSpacing(8)
        go = QPushButton("Finish", objectName="primary", cursor=Qt.PointingHandCursor)
        go.setProperty("size", "large")
        go.clicked.connect(self.finished)
        layout.addWidget(go, 0, Qt.AlignHCenter)
        layout.addSpacing(6)
        self.more_note = _label("More settings, including advanced options, are on the Settings page.", "hint")
        self.more_note.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.more_note)
        layout.addStretch(3)
        self.set_shortcut(settings["hotkey"], settings["shortcut_mode"])
        self._reveals[self.DONE] = [self.burst, heading, self.keycap, self.shortcut_hint, go, self.more_note]
        return step

    # ----- navigation -----

    def go(self, index: int):
        index = max(0, min(index, self.DONE))
        if index == self.steps.currentIndex():
            return
        if self._out is not None and self._out.state() == QPropertyAnimation.Running:
            return
        if not (ANIMATE and self.isVisible()):
            self._show(index, animate=False)
            return
        self._revealer.stop()
        step = self.steps.currentWidget()
        effect = QGraphicsOpacityEffect(step)
        step.setGraphicsEffect(effect)
        self._out = QPropertyAnimation(effect, b"opacity", step, duration=150, startValue=1.0, endValue=0.0)
        self._out.finished.connect(lambda: (step.setGraphicsEffect(None), self._show(index, animate=True)))
        self._out.start()

    def _show(self, index: int, animate: bool):
        self._stop_monitor()
        if index != self.TIDY:
            self._cancel_test()
        self.steps.setCurrentIndex(index)
        counted = self.THEME <= index <= self.APP
        self.bar.setVisible(counted)
        self.skip_button.setVisible(index != self.DONE)
        self.back_button.setVisible(index > self.THEME)
        if counted:
            self.dots.set_current(index - self.THEME)
        if index == self.MIC and self.isVisible():
            self._start_monitor()
        if index == self.DONE and ANIMATE and self.isVisible():
            QTimer.singleShot(250, self.burst.play)
        self.ambient.set_animating(index == self.WELCOME and self.isVisible())
        if animate:
            self._revealer.play(self._reveals[index], self.steps.widget(index))

    def reset(self):
        """Back to the welcome screen with a clean test, e.g. when setup is re-run from Settings."""
        self._cancel_test()
        self._heard = False
        self.pulse.set_heard(False)
        self._revealer.stop()
        self._show(0, animate=False)

    def showEvent(self, event):
        super().showEvent(event)
        index = self.steps.currentIndex()
        if index == self.MIC:
            self._start_monitor()
        self.ambient.set_animating(index == self.WELCOME)
        self._revealer.play(self._reveals[index], self.steps.currentWidget())

    def hideEvent(self, event):
        super().hideEvent(event)
        self._stop_monitor()
        self._cancel_test()
        self._revealer.stop()
        self.ambient.set_animating(False)

    # ----- microphone -----

    def _on_mic_changed(self):
        self.changed.emit({"mic_device": self.mic_combo.currentData()})
        if self.steps.currentIndex() == self.MIC and self.isVisible():
            self._start_monitor()

    def _start_monitor(self):
        """(Re)start listening on the chosen device with a fresh check."""
        self._stop_monitor()
        self._heard = False
        self.pulse.set_heard(False)
        self.mic_status.setText("Say something")
        self.retry_button.hide()
        try:
            self._mic = audio.Microphone(lambda chunk: None, self.mic_combo.currentData())
            self._mic.start()
        except Exception:
            self._mic = None
            self.mic_status.setText("Couldn't open this microphone. Try another.")
            self.retry_button.show()
            return
        self.pulse.set_active(True)
        self._poll.start()
        self._read_level()

    def _stop_monitor(self):
        mic, self._mic = self._mic, None
        if mic is not None:
            mic.stop()
        self.pulse.set_active(False)
        self._poll.stop()
        self._level = 0.0

    def _read_level(self):
        self._level = self._mic.level if self._mic is not None else 0.0
        if self._mic is not None and not self._heard and self._level >= HEARD_LEVEL:
            self._heard = True
            self.retry_button.show()
            self.pulse.set_heard(True)
            self.mic_status.setText("Got you")

    # ----- shortcut, dimming, look, updates -----

    def _on_dim_toggled(self, on: bool):
        self.dim_slider.setEnabled(on)
        self.changed.emit({"audio_dim_enabled": on})

    def _on_dim_changed(self, percent: int):
        percent = config.snap_audio_dim_percent(percent)
        if self.dim_slider.value() != percent:
            self.dim_slider.setValue(percent)
            return
        self.dim_value.setText(f"{percent}%")
        self.changed.emit({"audio_dim_percent": percent})

    def _on_overlay(self, change: dict):
        self.stage.set_options(change.get("live_preview", self.stage.live),
                               change.get("overlay_position", self.stage.position))
        self.changed.emit(change)

    # ----- tidy options -----

    def _on_level(self, key: str):
        self._config_changed({"tidy": key} if key != "ai" else _ai_changes(self._model))

    def _on_model(self, choice: str):
        self._model = choice
        self._config_changed(_ai_changes(choice))

    def _ai_plan(self) -> tidy.Plan:
        return tidy.plan({**self._tidy, **_ai_changes(self._model)})

    def _refresh_tidy(self):
        """Redraw everything that depends on the tidy choice: card texts, example, and which options apply."""
        level = _level(self._tidy)
        ai = self._ai_plan()
        large = ai.model_id == config.LARGE_MODEL
        where = "graphics card" if ai.device else "processor"
        name = "Large model" if large else "Small model"
        self.level_cards["ai"].set_texts(
            f"{name} · {where}",
            f"“{EXAMPLE_SMART if ai.llm_mode == 'smart' else EXAMPLE_LITERAL}”")
        for key, card in self.level_cards.items():
            card.blockSignals(True)
            card.setChecked(key == level)
            card.blockSignals(False)
        on = level == "ai"
        na = "Not used with Off or Quick"
        if self._model == "auto":
            model_hint = f"Picks what suits this computer: {name} on your {where}"
        elif self._model == "small":
            model_hint = "Quick on any computer. Punctuation and capitals only"
        elif large:
            model_hint = f"Best results. {'About half a second' if ai.device else 'A few seconds'} here"
        else:
            model_hint = "Not enough free memory for Large, so Small is used"
        self.model_options.set_value(self._model if on else "")
        self.model_row.hint.setText(model_hint if on else na)
        self.model_row.setEnabled(on)
        self.device_row.hint.setText("Your graphics card is faster when you have one" if on else na)
        self.device_row.setEnabled(on)
        fix = on and large
        self.corrections_row.hint.setText(
            "“Tuesday, no wait, Wednesday” becomes “Wednesday”" if fix else
            "Needs the Large model" if on else na)
        self.corrections_row.setEnabled(fix)
        # What can't apply reads as off, so a greyed-out switch never looks like an unchangeable "on".
        self.corrections.blockSignals(True)
        self.corrections.setChecked(bool(self._tidy["corrections"]) and fix)
        self.corrections.blockSignals(False)

    def _config_changed(self, change: dict):
        self._tidy.update(change)
        self._refresh_tidy()
        if self._testing:
            self._testing = False
            self.test_cancelled.emit()
        self.changed.emit(change)
        if self._tested:
            self._set_latency("")
            self.verdict_label.setText(self.SPEED_IDLE)
            self.test_stage.set_phase("preparing", "Updating")
            self._retest.start()

    # ----- speed test -----

    def _set_latency(self, text: str, color: str = None):
        self.latency_label.setText(text)
        self.latency_label.setStyleSheet(
            "font-size: 20pt; font-weight: 700;" + (f" color: {color};" if color else ""))

    def _retest_now(self):
        self._start_test()

    def _cancel_test(self):
        """Stop whatever the speed strip is doing and put it back to its starting state."""
        self._retest.stop()
        if self._testing:
            self._testing = False
            self.test_cancelled.emit()
        self._tested = False
        self._set_latency("")
        self.verdict_label.setText(self.SPEED_IDLE)
        self.test_stage.set_phase("idle")
        self.details_box.hide()
        self.details_button.hide()
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        self.sample_button.setEnabled(not busy)

    def _start_test(self):
        self._retest.stop()
        self._tested = True
        self._testing = True
        self._set_busy(True)
        self._set_latency("")
        self.verdict_label.setText(self.SPEED_IDLE)
        self.test_stage.set_phase("preparing", "Getting ready")
        self.details_box.hide()
        self.details_button.hide()
        self.test_requested.emit(None, 0)

    def set_progress(self, message: str, percent=None):
        if not self._testing:
            return
        if message.startswith("Listening"):
            self.test_stage.set_phase("listening")
        elif message.startswith("Tidying"):
            self.test_stage.set_phase("processing", FINISHING)
        else:
            self.test_stage.set_phase("preparing", f"{message} {int(percent)}%" if percent is not None else message)

    def set_result(self, result: Result):
        if not self._testing:  # a test that was cancelled or replaced while it ran
            return
        self._testing = False
        self._set_busy(False)
        rating, _ = result.verdict
        pal = self.palette_
        color = {"good": pal.success, "ok": AMBER, "slow": pal.danger}[rating]
        self._set_latency(_seconds(result.latency_s), color)
        word = {"good": "Fast", "ok": "Good", "slow": "Slow"}[rating]
        self.verdict_label.setText(word)
        self.test_stage.set_phase("done")
        text = " ".join(result.text.split())
        self.text_label.setText(f"“{text}”" if text else "No words recognised.")
        self.details_label.setText(self._details(result))
        self.details_button.show()

    def set_failure(self, message: str):
        if self._testing:
            self._testing = False
            self._fail(message)

    def _fail(self, message: str):
        self._set_latency("")
        self.verdict_label.setText(self.SPEED_IDLE)
        self.test_stage.set_phase("idle", message)
        self._set_busy(False)

    def _details(self, r: Result) -> str:
        plan = r.plan
        if plan.model_id:
            size = "Large" if plan.model_id == config.LARGE_MODEL else "Small"
            tidy_name = f"Smart · {size} model on your {'graphics card' if plan.device else 'processor'}"
        else:
            tidy_name = "Quick" if plan.level == "fast" else "Off"
        lines = [f"Speech {_seconds(r.transcribe_s)} + tidy-up {_seconds(r.tidy_s)} = {_seconds(r.latency_s)} wait",
                 f"Tidy-up: {tidy_name}"]
        if r.raw and " ".join(r.raw.split()) != " ".join(r.text.split()):
            lines.append(f"Before tidy-up: “{' '.join(r.raw.split())}”")
        return "<br>".join(lines)

    def _toggle_details(self):
        self.details_box.setVisible(not self.details_box.isVisible())

    # ----- app hooks -----

    def set_shortcut(self, combo: str, mode: str):
        self.keycap.setText(hotkey.display(combo))
        self.shortcut_hint.setText(SHORTCUT_HINTS.get(mode, ""))

    def set_tidy_summary(self, summary: str, large_model: bool):
        self._refresh_tidy()

    def set_gpus(self, gpus: list, current: str):
        combo = self.device
        combo.blockSignals(True)
        combo.clear()
        for key, label in config.CLEANUP_DEVICES.items():
            combo.addItem(label, key)
        for g in gpus:
            combo.addItem(f"GPU: {g.name}", g.device)
        if combo.findData(current) < 0:
            combo.addItem(f"GPU: Unavailable ({current})", current)
        combo.setCurrentIndex(combo.findData(current))
        combo.blockSignals(False)
        if hasattr(self, "model_row"):
            self._refresh_tidy()

    def sync(self, settings: dict):
        """Reflect settings changed elsewhere (the app echoes every change back)."""
        self._tidy.update({k: settings[k] for k in self._tidy})
        if settings["tidy"] in ("auto", "best"):
            self._model = _model_choice(settings)
        self.device.blockSignals(True)
        self.device.setCurrentIndex(max(0, self.device.findData(settings["cleanup_device"])))
        self.device.blockSignals(False)
        self.corrections.blockSignals(True)
        self.corrections.setChecked(settings["corrections"])
        self.corrections.blockSignals(False)
        self._refresh_tidy()
        self.live_options.set_value(settings["live_preview"])
        self.position_options.set_value(settings["overlay_position"])
        self.stage.set_options(settings["live_preview"], settings["overlay_position"])
        self.mode_options.set_value(settings["shortcut_mode"])
        self.theme_options.set_value(settings["theme"])
        self.updates_options.set_value(settings["updates"])
        self.prereleases.blockSignals(True)
        self.prereleases.setChecked(settings["prereleases"])
        self.prereleases.blockSignals(False)
        self.shortcut.set_combo(settings["hotkey"])
        for widget, setter, value in ((self.dim_toggle, "setChecked", settings["audio_dim_enabled"]),
                                      (self.dim_slider, "setValue", settings["audio_dim_percent"])):
            widget.blockSignals(True)
            getattr(widget, setter)(value)
            widget.blockSignals(False)
        self.dim_slider.setEnabled(settings["audio_dim_enabled"])
        self.dim_value.setText(f'{settings["audio_dim_percent"]}%')
        self.set_shortcut(settings["hotkey"], settings["shortcut_mode"])

    def set_palette(self, palette):
        self.palette_ = palette
        for widget in self.findChildren(QWidget):
            if hasattr(widget, "palette_"):
                widget.palette_ = palette
                widget.update()

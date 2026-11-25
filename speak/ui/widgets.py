"""Custom-painted widgets: spinner, toggle switch, choice chips, disclosure, mic button, level wave, shortcut recorder.
Drawing helpers are in paint.py."""
import math
import threading
import time
from collections import deque

from PySide6.QtCore import (Property, QEasingCurve, QEvent, QObject, QPointF, QPropertyAnimation, QRectF, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from .. import hotkey, permissions
from . import theme
from .paint import BARS, draw_chevron, draw_cross, draw_check, draw_mic, draw_ring, draw_shimmer_text, draw_wave


# ---------- animation helper ----------

class Animated(QWidget):
    """Repaints at ~60 fps while `animating` is True; exposes `phase` (seconds since start)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t0 = time.monotonic()
        self._timer = QTimer(self, interval=16, timeout=self.update)

    @property
    def phase(self) -> float:
        return time.monotonic() - self._t0

    def set_animating(self, on: bool) -> None:
        if on and not self._timer.isActive():
            self._timer.start()
        elif not on and self._timer.isActive():
            self._timer.stop()
            self.update()


class Spinner(Animated):
    def __init__(self, size: int = 22, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.percent = None
        self._color = QColor("#2a6b64")

    def set_color(self, c: str) -> None:
        self._color = QColor(c)

    def showEvent(self, e):
        self.set_animating(True)

    def hideEvent(self, e):
        self.set_animating(False)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = max(2.0, self.width() / 9)
        r = QRectF(w, w, self.width() - 2 * w, self.height() - 2 * w)
        draw_ring(p, r, self._color, w, self.phase, self.percent)


# ---------- glyph ----------

class Glyph(QWidget):
    """A paint.py glyph as a widget, drawn in the palette's text (or muted) colour."""

    def __init__(self, draw, size: int = 18, muted: bool = False, parent=None):
        super().__init__(parent)
        self.draw, self.muted = draw, muted
        self.setFixedSize(size, size)
        self.palette_ = None  # None follows theme.current

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette_ or theme.current
        self.draw(p, QPointF(self.width() / 2, self.height() / 2), self.width() * 0.9,
                  QColor(pal.muted if self.muted else pal.text))


# ---------- toggle switch ----------

class Toggle(QAbstractButton):
    """Painted switch. Takes focus from the keyboard only, so the focus ring marks keyboard navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setFixedSize(48, 28)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self, duration=160, easingCurve=QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)
        self.palette_ = theme.LIGHT
        self.state_label = None  # optional "On"/"Off" label kept in step, see `with_state_label`

    def with_state_label(self) -> QWidget:
        """The switch with an "On"/"Off" word before it, as native settings panes show."""
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.state_label = QLabel("", objectName="hint")
        row.addWidget(self.state_label)
        row.addWidget(self)
        self.toggled.connect(lambda _: self._sync_label())
        self._sync_label()
        return holder

    def _sync_label(self):
        if self.state_label is not None:
            self.state_label.setText("On" if self.isChecked() else "Off")
            self.state_label.setEnabled(self.isEnabled())

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.EnabledChange:
            self._sync_label()

    def _get_knob(self):
        return self._pos

    def _set_knob(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on):
        super().setChecked(on)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self._sync_label()
        self.update()

    def sizeHint(self):
        return QSize(48, 28)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette_
        t = self._pos
        if self.isEnabled():  # outlined when off, filled with the accent when on
            track = _mix(pal.surface, pal.accent, t)
            edge = _mix(pal.muted, pal.accent, t)
            knob = _mix(pal.muted, pal.accent_text, t)
        else:  # unavailable reads as neutral whatever its position, so it never looks switched on
            track, edge, knob = QColor(pal.surface_alt), QColor(pal.border), QColor(pal.border)
        if self.hasFocus():
            p.setPen(QPen(QColor(pal.accent), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(1, 1, 46, 26), 13, 13)
        p.setPen(QPen(edge, 1))
        p.setBrush(track)
        p.drawRoundedRect(QRectF(4.5, 4.5, 39, 19), 9.5, 9.5)
        p.setPen(Qt.NoPen)
        p.setBrush(knob)
        r = 6 + t
        p.drawEllipse(QPointF(14 + t * 20, 14), r, r)


def _mix(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(int(ca.red() + (cb.red() - ca.red()) * t), int(ca.green() + (cb.green() - ca.green()) * t),
                  int(ca.blue() + (cb.blue() - ca.blue()) * t))


# ---------- choice chips (settings and onboarding) ----------

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

    def value(self) -> str:
        return next((key for key, chip in self.chips.items() if chip.isChecked()), "")

    def set_value(self, key: str):
        """Select `key`; an unknown key (e.g. "") leaves nothing selected."""
        self.group.group.setExclusive(False)
        for chip_key, chip in self.chips.items():
            chip.setChecked(chip_key == key)
        self.group.group.setExclusive(True)


# ---------- disclosure ----------

class Disclosure(QAbstractButton):
    """Full-width "More options" row that opens a section's technical rows. Shows how many of those rows differ
    from their defaults, so a changed option is never hidden silently."""

    def __init__(self, text: str = "More options", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setText(text)
        self.setAccessibleName(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(48)
        self.changed_count = 0
        self.summary = ""  # names of the hidden rows, shown on the right while closed
        self.divider = False
        self.palette_ = theme.LIGHT

    def set_summary(self, text: str) -> None:
        self.summary = text
        self.setToolTip(text)
        self.update()

    def set_changed(self, count: int) -> None:
        self.changed_count = count
        self.setAccessibleDescription(f"{count} changed" if count else "")
        self.update()

    def sizeHint(self):
        return QSize(240, 48)

    def enterEvent(self, e):
        super().enterEvent(e)
        self.update()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette_
        rect = QRectF(self.rect())
        if self.divider:
            p.fillRect(QRectF(0, 0, rect.width(), 1), QColor(pal.border))
        hot = self.underMouse() or self.hasFocus()
        if hot:
            p.setPen(QPen(QColor(pal.accent), 2) if self.hasFocus() else Qt.NoPen)
            p.setBrush(QColor(pal.surface_alt))
            p.drawRoundedRect(rect.adjusted(2, 4, -2, -3), 6, 6)
        p.setFont(self.font())
        p.setPen(QColor(pal.text))
        metrics = QFontMetrics(self.font())
        x = 10 + metrics.horizontalAdvance(self.text())
        p.drawText(rect.adjusted(10, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, self.font().pointSizeF() - 1.5))
        if self.changed_count:
            small.setWeight(QFont.DemiBold)
            label = f"{self.changed_count} changed"
            width = QFontMetrics(small).horizontalAdvance(label) + 14
            pill = QRectF(x + 10, rect.center().y() - 9, width, 18)
            tint = QColor(pal.accent)
            tint.setAlphaF(0.16)
            p.setPen(Qt.NoPen)
            p.setBrush(tint)
            p.drawRoundedRect(pill, 9, 9)
            p.setFont(small)
            p.setPen(QColor(pal.accent))
            p.drawText(pill, Qt.AlignCenter, label)
            x = pill.right()
            small.setWeight(QFont.Normal)
        if self.summary and not self.isChecked():
            p.setFont(small)
            p.setPen(QColor(pal.muted))
            room = QRectF(x + 16, 0, rect.right() - 44 - (x + 16), rect.height())
            text = QFontMetrics(small).elidedText(self.summary, Qt.ElideRight, int(room.width()))
            p.drawText(room, Qt.AlignVCenter | Qt.AlignRight, text)
        draw_chevron(p, QPointF(rect.right() - 22, rect.center().y()), 12, QColor(pal.text), up=self.isChecked())


# ---------- mic button ----------

class MicButton(Animated):
    """Large round dictation button. Modes: idle, preparing, listening, processing, done, error."""

    clicked = Signal()

    def __init__(self, level_source, parent=None, size: int = 180):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("Start or stop dictation")
        self.level_source = level_source
        self.mode = "idle"
        self.percent = None
        self._level = 0.0
        self._mode_t = 0.0
        self._hover = False
        self.palette_ = theme.LIGHT

    def set_mode(self, mode: str, percent=None) -> None:
        if mode != self.mode:
            self._mode_t = self.phase
        self.mode, self.percent = mode, percent
        self.set_animating(mode != "idle" or self._hover)
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.set_animating(True)

    def leaveEvent(self, e):
        self._hover = False
        if self.mode == "idle":
            self.set_animating(False)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, e):
        pal = self.palette_
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(self.width() / 180, self.height() / 180)  # drawn at 180 px, scaled to the button's size
        c = QPointF(90, 90)
        base_r = 54
        accent = QColor(pal.accent)
        since = self.phase - self._mode_t

        if self.mode == "listening":
            target = min(1.0, (self.level_source() or 0.0) * 6)
            self._level += (target - self._level) * 0.25
            for i in range(3):
                t = (self.phase * 0.7 + i / 3) % 1.0
                r = base_r + 6 + t * (26 + 14 * self._level)
                halo = QColor(accent)
                halo.setAlpha(int(90 * (1 - t) * (0.4 + 0.6 * self._level)))
                p.setPen(Qt.NoPen)
                p.setBrush(halo)
                p.drawEllipse(c, r, r)
            r = base_r + 4 * self._level
        else:
            self._level = 0.0
            r = base_r + (3 if self._hover and self.mode == "idle" else 0)

        fill = QColor(accent)
        if self.mode in ("preparing", "processing"):
            fill = QColor(pal.surface_alt)
        elif self.mode == "error":
            fill = QColor(pal.danger)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawEllipse(c, r, r)

        if self.mode in ("preparing", "processing"):
            ring = QRectF(c.x() - r - 10, c.y() - r - 10, 2 * r + 20, 2 * r + 20)
            draw_ring(p, ring, accent, 5, self.phase, self.percent)
            dots = QColor(pal.muted)
            for i in range(3):
                a = 0.35 + 0.65 * max(0.0, math.sin(self.phase * 5 - i * 0.7))
                dots.setAlphaF(a)
                p.setBrush(dots)
                p.drawEllipse(QPointF(c.x() - 14 + i * 14, c.y()), 4, 4)
        elif self.mode == "done":
            draw_check(p, c, 46, QColor(pal.accent_text), min(1.0, since / 0.35))
        elif self.mode == "error":
            draw_cross(p, c, 40, QColor("#ffffff"))
        else:
            if self.mode == "listening":
                # rounded "stop" square while recording
                s = 30
                p.setBrush(QColor(pal.accent_text))
                p.drawRoundedRect(QRectF(c.x() - s / 2, c.y() - s / 2, s, s), 7, 7)
            else:
                draw_mic(p, c, 48, QColor(pal.accent_text))


class WaveStrip(Animated):
    """Under the mic button: mic level while listening, the phase word over a wave while working,
    plain hint text otherwise (same look as the overlay pill)."""

    def __init__(self, level_source, parent=None):
        super().__init__(parent)
        self.setFixedSize(240, 40)
        self.level_source = level_source
        self.palette_ = theme.LIGHT
        self.mode, self.text = "idle", ""
        self._levels = deque([0.0] * BARS, maxlen=BARS)
        self._smooth = 0.0
        self._sample = QTimer(self, interval=45, timeout=self._push_level)

    def set_state(self, mode: str, text: str = "") -> None:
        self.mode, self.text = mode, text
        if mode == "listening":
            self._levels.extend([0.0] * BARS)
            self._sample.start()
        else:
            self._sample.stop()
        self.set_animating(mode in ("listening", "preparing", "processing"))
        self.update()

    def _push_level(self):
        target = min(1.0, (self.level_source() or 0.0) * 7)
        self._smooth += (target - self._smooth) * 0.5
        self._levels.append(self._smooth)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette_
        rect = QRectF(self.rect())
        if self.mode == "listening":
            draw_wave(p, rect, self._levels, self.mode, self.phase, pal)
        elif self.mode in ("preparing", "processing"):
            draw_wave(p, rect, self._levels, self.mode, self.phase, pal, bool(self.text))
            if self.text:
                draw_shimmer_text(p, rect, self.text, self.font(), self.phase, pal)
        elif self.text:
            p.setPen(QColor(pal.muted))
            p.drawText(rect, Qt.AlignCenter, self.text)


# ---------- shortcut recorder ----------

class ShortcutButton(QPushButton):
    """Click, press a key combo, done. Emits `captured(combo)`."""

    captured = Signal(str)
    recording = Signal(bool)  # app ignores the global hotkey while True
    _done = Signal(str)

    def __init__(self, combo: str, parent=None):
        super().__init__(parent)
        self.setObjectName("shortcut")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)  # Space/Enter in a captured combo must not re-click it
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.combo = combo
        self.setText(hotkey.display(combo))
        self.setToolTip("Click, then press the shortcut you want")
        self.clicked.connect(self._record)
        self._done.connect(self._finish)

    def set_combo(self, combo: str) -> None:
        self.combo = combo
        self.setText(hotkey.display(combo))

    def _record(self):
        if permissions.missing():
            self.setText("Finish setup first")
            QTimer.singleShot(3000, self, lambda: self.setText(hotkey.display(self.combo)))
            return
        self.setEnabled(False)
        self.setText("Press keys…")
        self.setProperty("recording", True)
        self.style().polish(self)
        self.recording.emit(True)
        hotkey.unregister()

        def run():
            try:
                combo = hotkey.capture()
            except Exception:
                combo = ""
            self._done.emit(combo)

        threading.Thread(target=run, daemon=True).start()

    def _finish(self, combo: str):
        self.setEnabled(True)
        self.setProperty("recording", False)
        self.style().polish(self)
        if combo and combo not in ("esc", "escape"):
            self.combo = combo
        self.setText(hotkey.display(self.combo))
        self.captured.emit(self.combo)
        self.recording.emit(False)

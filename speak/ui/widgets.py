"""Custom-painted widgets: spinner/progress ring, toggle switch, mic button, level wave, shortcut recorder, glyphs."""
import math
import threading
import time
from collections import deque

from PySide6.QtCore import (Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QPushButton, QSizePolicy, QWidget

from .. import hotkey, permissions
from . import theme


# ---------- glyphs ----------

def draw_mic(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    p.save()
    pen = QPen(color, max(1.6, size * 0.09), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    w, h = size * 0.36, size * 0.56
    body = QRectF(center.x() - w / 2, center.y() - size * 0.5, w, h)
    p.setBrush(color)
    p.drawRoundedRect(body, w / 2, w / 2)
    p.setBrush(Qt.NoBrush)
    arc = QRectF(center.x() - size * 0.32, center.y() - size * 0.3, size * 0.64, size * 0.6)
    p.drawArc(arc, 200 * 16, 140 * 16)
    p.drawLine(QPointF(center.x(), center.y() + size * 0.3), QPointF(center.x(), center.y() + size * 0.46))
    p.restore()


def draw_check(p: QPainter, center: QPointF, size: float, color: QColor, progress: float = 1.0) -> None:
    path = QPainterPath(QPointF(center.x() - size * 0.38, center.y() + size * 0.02))
    path.lineTo(center.x() - size * 0.1, center.y() + size * 0.3)
    path.lineTo(center.x() + size * 0.4, center.y() - size * 0.28)
    p.save()
    p.setPen(QPen(color, max(2.0, size * 0.13), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    if progress >= 1:
        p.drawPath(path)
    else:
        length = path.length() * max(0.0, progress)
        trimmed = QPainterPath(path.pointAtPercent(0))
        steps = 24
        for i in range(1, steps + 1):
            t = path.percentAtLength(length * i / steps)
            trimmed.lineTo(path.pointAtPercent(t))
        p.drawPath(trimmed)
    p.restore()


def draw_cross(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    p.save()
    p.setPen(QPen(color, max(2.0, size * 0.13), Qt.SolidLine, Qt.RoundCap))
    d = size * 0.3
    p.drawLine(QPointF(center.x() - d, center.y() - d), QPointF(center.x() + d, center.y() + d))
    p.drawLine(QPointF(center.x() + d, center.y() - d), QPointF(center.x() - d, center.y() + d))
    p.restore()


def draw_ring(p: QPainter, rect: QRectF, color: QColor, width: float, phase: float, percent=None) -> None:
    """Indeterminate spinner when percent is None (phase = seconds), else a determinate arc."""
    p.save()
    track = QColor(color)
    track.setAlpha(45)
    p.setPen(QPen(track, width, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(rect)
    p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap))
    if percent is None:
        span = 70 + 200 * (0.5 + 0.5 * math.sin(phase * 3.2))
        start = -(phase * 330) % 360
        p.drawArc(rect, int(start * 16), int(-span * 16))
    else:
        p.drawArc(rect, 90 * 16, int(-360 * 16 * max(0.0, min(1.0, percent / 100))))
    p.restore()


BARS = 22


def draw_wave(p: QPainter, rect: QRectF, levels, mode: str, phase: float, pal, behind_text: bool = False) -> None:
    """Bars: mic level while listening, a travelling shimmer while preparing/processing (fainter behind text),
    flat otherwise. `levels` holds BARS values in 0..1."""
    step = rect.width() / BARS
    bar_w = max(2.0, step * 0.5)
    mid = rect.center().y()
    p.save()
    p.setPen(Qt.NoPen)
    for i in range(BARS):
        x = rect.left() + i * step + (step - bar_w) / 2
        if mode == "listening":
            h = 3 + levels[i] * (rect.height() - 20) * (0.7 + 0.3 * math.sin(i * 1.7 + phase * 6))
            col = QColor(pal.accent)
        elif mode in ("preparing", "processing"):
            wave = 0.5 + 0.5 * math.sin(phase * 6 - i * 0.45)
            h = 3 + wave * (rect.height() * 0.35 if behind_text else 8)
            col = QColor(pal.accent if behind_text else pal.muted)
            col.setAlphaF((0.35 + 0.5 * wave) * (0.35 if behind_text else 1.0))
        else:
            h = 3
            col = QColor(pal.muted)
            col.setAlphaF(0.4)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(x, mid - h / 2, bar_w, h), bar_w / 2, bar_w / 2)
    p.restore()


def draw_shimmer_text(p: QPainter, rect: QRectF, text: str, font: QFont, phase: float, pal) -> None:
    """Centred text with a light sweeping across it."""
    p.save()
    f = QFont(font)
    f.setPointSizeF(10)
    f.setWeight(QFont.DemiBold)
    p.setFont(f)
    width = QFontMetrics(f).horizontalAdvance(text)
    start = rect.center().x() - width / 2
    sweep = start - 40 + ((phase * 0.9) % 1.6) * (width + 80) / 1.6
    grad = QLinearGradient(sweep - 40, 0, sweep + 40, 0)
    base, shine = QColor(pal.muted), QColor(pal.text)
    grad.setColorAt(0, base)
    grad.setColorAt(0.5, shine)
    grad.setColorAt(1, base)
    p.setPen(QPen(QBrush(grad), 1))
    p.drawText(rect, Qt.AlignCenter, text)
    p.restore()


# ---------- animation helper ----------

class _Animated(QWidget):
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


class Spinner(_Animated):
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


# ---------- toggle switch ----------

class Toggle(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 24)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self, duration=160, easingCurve=QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)
        self.palette_ = theme.LIGHT

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
        self.update()

    def sizeHint(self):
        return QSize(44, 24)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette_
        off, on = QColor(pal.border), QColor(pal.accent)
        t = self._pos
        track = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                       int(off.blue() + (on.blue() - off.blue()) * t))
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, 44, 24), 12, 12)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(3 + t * 20, 3, 18, 18))


# ---------- mic button ----------

class MicButton(_Animated):
    """Large round dictation button. Modes: idle, preparing, listening, processing, done, error."""

    clicked = Signal()

    def __init__(self, level_source, parent=None):
        super().__init__(parent)
        self.setFixedSize(180, 180)
        self.setCursor(Qt.PointingHandCursor)
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
        c = QPointF(self.width() / 2, self.height() / 2)
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


class WaveStrip(_Animated):
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

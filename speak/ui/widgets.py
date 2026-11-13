"""Custom-painted widgets: spinner, toggle switch, mic button, level wave, shortcut recorder. Drawing helpers are in paint.py."""
import math
import threading
import time
from collections import deque

from PySide6.QtCore import (Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton, QPushButton, QSizePolicy, QWidget

from .. import hotkey, permissions
from . import theme
from .paint import BARS, draw_cross, draw_check, draw_mic, draw_ring, draw_shimmer_text, draw_wave


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

class MicButton(Animated):
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

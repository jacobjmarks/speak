"""Floating always-on-top overlay: a pill showing listening/working state, plus live text.

position: "cursor" (under the mouse), "top" / "bottom" (centred on the screen with the mouse).
preview:  "line" (one sliding line under the pill), "full" (wrapping card, last few lines), "off".
While preparing/processing the pill shows a short phase ("Getting ready", "Finishing up") over a soft travelling wave.

Wayland cannot position or pin windows (protocol limit), so there it appears wherever the compositor puts it.
"""
import math
from collections import deque

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QLinearGradient,
                           QPainter, QPen)

from .. import platform_utils
from . import theme
from .widgets import BARS, _Animated, draw_check, draw_cross, draw_ring, draw_shimmer_text, draw_wave

PILL_W, PILL_H = 168, 46
CARD_W = 380
LINE_W, LINE_H = 280, 30
EDGE = 24  # gap from the screen edge for top/bottom positions
MAX_LINES = 3


class Overlay(_Animated):
    def __init__(self, level_source):
        super().__init__(None)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)  # Qt hides Tool windows when the app deactivates
        self.level_source = level_source
        self.palette_ = theme.LIGHT
        self.preview = "line"
        self.position = "cursor"
        self.mode = "listening"
        self.percent = None
        self.word = ""
        self._scroll = 0.0
        self._card_text, self._card_h, self._card_above = "", 0, False
        self.text = ""
        self._mode_t = 0.0
        self._levels = deque([0.0] * BARS, maxlen=BARS)
        self._smooth = 0.0
        self._sample = QTimer(self, interval=45, timeout=self._push_level)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self, duration=220,
                                        easingCurve=QEasingCurve.OutCubic)
        self._fade.finished.connect(self._fade_done)
        self._hide_timer = QTimer(self, singleShot=True, timeout=self.fade_out)
        self._font = QFont(self.font())
        self._font.setPointSizeF(10.5)
        self._anchor = None

    # ----- public API -----

    def set_mode(self, mode: str, percent=None, word: str = "") -> None:
        """Modes: preparing, listening, processing, done, error. `word` labels preparing/processing."""
        self._hide_timer.stop()
        if mode != self.mode:
            self._mode_t = self.phase
        self.mode, self.percent, self.word = mode, percent, word
        if mode == "listening":
            self._sample.start()
        else:
            self._sample.stop()
        if mode == "preparing":
            self._levels.extend([0.0] * BARS)
        if mode in ("done", "error"):
            self._hide_timer.start(900 if mode == "done" else 1600)
        self._show()
        self._relayout()

    def set_text(self, text: str) -> None:
        self.text = text.strip()
        self._relayout()

    def snapshot(self, mode: str, text: str = "", level: float = 0.0, word: str = ""):
        """Render the indicator offscreen as a pixmap (the setup preview); never shows the window."""
        if mode != self.mode:
            self._mode_t = self.phase
        self.mode, self.word, self.percent = mode, word, None
        self.text = text
        self._levels.append(level)
        self._relayout()
        return self.grab()

    def fade_out(self) -> None:
        if not self.isVisible():
            return
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def hide_now(self) -> None:
        self._sample.stop()
        self._hide_timer.stop()
        self._fade.stop()
        self.set_animating(False)
        self.hide()

    # ----- internals -----

    def _show(self):
        if self._fade.endValue() == 0.0:
            self._fade.stop()
        if not self.isVisible():
            self._anchor = QCursor.pos()
            if self.mode in ("preparing", "listening"):
                self.text, self._scroll = "", 0.0
            self.setWindowOpacity(0.0)
            self._relayout()
            self.show()
            platform_utils.keep_visible_when_inactive(int(self.winId()))
            self._fade.stop()
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        elif self.windowOpacity() < 1.0 and self._fade.endValue() != 1.0:
            self._fade.setStartValue(self.windowOpacity())
            self._fade.setEndValue(1.0)
            self._fade.start()
        self.set_animating(True)

    def _fade_done(self):
        if self._fade.endValue() == 0.0:
            self.hide_now()

    def _push_level(self):
        target = min(1.0, (self.level_source() or 0.0) * 7)
        self._smooth += (target - self._smooth) * 0.5
        self._levels.append(self._smooth)

    def _visible_text(self) -> str:
        if not (self.preview != "off" and self.text and self.mode in ("listening", "processing")):
            return ""
        if self.preview == "line":
            return self.text[-300:]
        fm = QFontMetrics(self._font)
        words = self.text.split()
        text = self.text
        start = 0
        while start < len(words):
            text = ("… " if start else "") + " ".join(words[start:])
            rect = fm.boundingRect(QRect(0, 0, CARD_W - 32, 10_000), Qt.TextWordWrap, text)
            if rect.height() <= fm.lineSpacing() * MAX_LINES:
                break
            start += 1
        return text

    def _relayout(self):
        text = self._visible_text()
        fm = QFontMetrics(self._font)
        card_h, card_w = 0, 0
        if text and self.preview == "line":
            card_h, card_w = LINE_H, LINE_W
        elif text:
            card_h = fm.boundingRect(QRect(0, 0, CARD_W - 32, 10_000), Qt.TextWordWrap, text).height() + 24
            card_w = CARD_W
        width = max(PILL_W, card_w) + 24
        height = PILL_H + 24 + (card_h + 8 if text else 0)
        self._card_text, self._card_h, self._card_w = text, card_h, card_w
        self._card_above = self.position == "bottom"
        anchor = self._anchor or QCursor.pos()
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        if self.position == "cursor":
            x = anchor.x() - width // 2
            y = anchor.y() + 18
            if y + height > area.bottom():
                y = anchor.y() - height - 18
        else:
            x = area.center().x() - width // 2
            y = area.top() + EDGE if self.position == "top" else area.bottom() - height - EDGE
        x = max(area.left() + 4, min(x, area.right() - width - 4))
        y = max(area.top() + 4, y)
        self.setGeometry(x, y, width, height)
        self.update()

    def paintEvent(self, e):
        pal = self.palette_
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = theme.color(pal.surface, 242)
        border = theme.color(pal.border)
        accent = QColor(pal.accent)

        pill_top = 12 + (self._card_h + 8 if self._card_text and self._card_above else 0)
        pill = QRectF((self.width() - PILL_W) / 2, pill_top, PILL_W, PILL_H)
        # soft shadow
        for i, a in enumerate((26, 14, 6)):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, a))
            p.drawRoundedRect(pill.adjusted(-2 - i * 2, 1 - i, 2 + i * 2, 4 + i * 2), PILL_H / 2 + i * 2,
                              PILL_H / 2 + i * 2)
        p.setBrush(bg)
        p.setPen(QPen(border, 1))
        p.drawRoundedRect(pill, PILL_H / 2, PILL_H / 2)

        icon_c = QPointF(pill.left() + PILL_H / 2 + 2, pill.center().y())
        since = self.phase - self._mode_t
        if self.mode == "listening":
            pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self.phase * 4))
            red = QColor(pal.danger)
            red.setAlphaF(0.25 * pulse)
            p.setPen(Qt.NoPen)
            p.setBrush(red)
            p.drawEllipse(icon_c, 11, 11)
            red.setAlphaF(1.0)
            p.setBrush(red)
            p.drawEllipse(icon_c, 6, 6)
        elif self.mode in ("preparing", "processing"):
            draw_ring(p, QRectF(icon_c.x() - 10, icon_c.y() - 10, 20, 20), accent, 3, self.phase, self.percent)
        elif self.mode == "done":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal.success))
            p.drawEllipse(icon_c, 12, 12)
            draw_check(p, icon_c, 14, QColor("#ffffff"), min(1.0, since / 0.3))
        elif self.mode == "error":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(pal.danger))
            p.drawEllipse(icon_c, 12, 12)
            draw_cross(p, icon_c, 12, QColor("#ffffff"))

        left = icon_c.x() + 22
        right = pill.right() - 18
        area = QRectF(left, pill.top(), right - left, PILL_H)
        draw_wave(p, area, self._levels, self.mode, self.phase, pal, bool(self.word))
        if self.mode in ("preparing", "processing") and self.word:
            draw_shimmer_text(p, area, self.word, self._font, self.phase, pal)
        self._paint_text(p, pill, bg, border)

    def _paint_text(self, p: QPainter, pill: QRectF, bg: QColor, border: QColor):
        if not self._card_text:
            return
        pal = self.palette_
        top = 12 if self._card_above else pill.bottom() + 8
        card = QRectF((self.width() - self._card_w) / 2, top, self._card_w, self._card_h)
        radius = self._card_h / 2 if self.preview == "line" else 14
        p.setPen(QPen(border, 1))
        p.setBrush(bg)
        p.drawRoundedRect(card, radius, radius)
        p.setFont(self._font)
        col = QColor(pal.text)
        if self.mode == "processing":
            col.setAlphaF(0.55)
        p.setPen(col)
        if self.preview != "line":
            p.drawText(card.adjusted(16, 12, -16, -12), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
                       self._card_text)
            return
        # one line that slides left as words arrive, fading out at the left edge
        inner = card.adjusted(14, 0, -14, 0)
        overflow = max(0.0, QFontMetrics(self._font).horizontalAdvance(self._card_text) - inner.width())
        self._scroll += (overflow - self._scroll) * 0.18
        if abs(overflow - self._scroll) < 0.5:
            self._scroll = overflow
        p.save()
        p.setClipRect(inner)
        p.drawText(QRectF(inner.left() - self._scroll, card.top(), inner.width() + self._scroll, card.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, self._card_text)
        p.restore()
        if self._scroll > 0:
            fade = QLinearGradient(inner.left() + 4, 0, inner.left() + 56, 0)
            solid = QColor(bg)
            solid.setAlpha(255)
            clear = QColor(bg)
            clear.setAlpha(0)
            fade.setColorAt(0, solid)
            fade.setColorAt(1, clear)
            p.setPen(Qt.NoPen)
            p.setBrush(fade)
            p.drawRect(QRectF(inner.left() - 1, card.top() + 1, 57, card.height() - 2))

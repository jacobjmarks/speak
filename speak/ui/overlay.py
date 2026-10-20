"""Floating always-on-top overlay: a pill showing listening/processing state, plus a live-text card below it.

Wayland cannot position or pin windows (protocol limit), so there it appears wherever the compositor puts it.
"""
import math
from collections import deque

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme
from .widgets import _Animated, draw_check, draw_cross, draw_ring

PILL_W, PILL_H = 168, 46
CARD_W = 380
MAX_LINES = 3
BARS = 22


class Overlay(_Animated):
    def __init__(self, level_source):
        super().__init__(None)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.level_source = level_source
        self.palette_ = theme.LIGHT
        self.show_text = True
        self.mode = "listening"
        self.percent = None
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

    def set_mode(self, mode: str, percent=None) -> None:
        """Modes: preparing, listening, processing, done, error."""
        self._hide_timer.stop()
        if mode != self.mode:
            self._mode_t = self.phase
        self.mode, self.percent = mode, percent
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
            self.text = "" if self.mode in ("preparing", "listening") else self.text
            self.setWindowOpacity(0.0)
            self._relayout()
            self.show()
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
        if not (self.show_text and self.text and self.mode in ("listening", "processing")):
            return ""
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
        card_h = 0
        if text:
            card_h = fm.boundingRect(QRect(0, 0, CARD_W - 32, 10_000), Qt.TextWordWrap, text).height() + 24
        width = CARD_W + 24 if text else PILL_W + 24
        height = PILL_H + 24 + (card_h + 8 if text else 0)
        self._card_text, self._card_h = text, card_h
        anchor = self._anchor or QCursor.pos()
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = anchor.x() - width // 2
        y = anchor.y() + 18
        if y + height > area.bottom():
            y = anchor.y() - height - 18
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

        pill = QRectF((self.width() - PILL_W) / 2, 12, PILL_W, PILL_H)
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

        # bars area
        left = icon_c.x() + 22
        right = pill.right() - (48 if self.mode == "preparing" and self.percent is not None else 18)
        mid = pill.center().y()
        step = (right - left) / BARS
        bar_w = max(2.0, step * 0.5)
        p.setPen(Qt.NoPen)
        for i in range(BARS):
            x = left + i * step + (step - bar_w) / 2
            if self.mode == "listening":
                lv = self._levels[i]
                h = 3 + lv * (PILL_H - 20) * (0.7 + 0.3 * math.sin(i * 1.7 + self.phase * 6))
                col = QColor(accent)
            elif self.mode in ("preparing", "processing"):
                # travelling shimmer while we wait
                wave = 0.5 + 0.5 * math.sin(self.phase * 6 - i * 0.45)
                h = 3 + wave * 8
                col = QColor(pal.muted)
                col.setAlphaF(0.35 + 0.5 * wave)
            else:
                h = 3
                col = QColor(pal.muted)
                col.setAlphaF(0.4)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(x, mid - h / 2, bar_w, h), bar_w / 2, bar_w / 2)

        if self.mode == "preparing" and self.percent is not None:
            p.setPen(QColor(pal.muted))
            f = QFont(self._font)
            f.setPointSizeF(8)
            p.setFont(f)
            p.drawText(QRectF(pill.right() - 44, pill.top(), 38, PILL_H), Qt.AlignRight | Qt.AlignVCenter,
                       f"{int(self.percent)}%")

        if self._card_text:
            card = QRectF(12, pill.bottom() + 8, self.width() - 24, self._card_h)
            p.setPen(QPen(border, 1))
            p.setBrush(bg)
            p.drawRoundedRect(card, 14, 14)
            p.setFont(self._font)
            col = QColor(pal.text)
            if self.mode == "processing":
                col.setAlphaF(0.55)
            p.setPen(col)
            p.drawText(card.adjusted(16, 12, -16, -12), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
                       self._card_text)

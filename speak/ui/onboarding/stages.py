from .common import STAGE_FROZEN_WORDS, STAGE_TEXT
from . import common
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy
from ...controller import FINISHING
from .. import theme
from ..overlay import EDGE, Overlay
from ..widgets import BARS, _Animated

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
        self.set_animating(common.ANIMATE and mode in ("preparing", "listening", "processing") and self.isVisible())
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
            if not common.ANIMATE:
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
        self.set_animating(common.ANIMATE)

    def hideEvent(self, e):
        super().hideEvent(e)
        self.set_animating(False)

    def _moment(self) -> tuple:
        """(indicator mode or None, words shown, text has landed in the window)"""
        if not common.ANIMATE:
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
        if not common.ANIMATE:
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

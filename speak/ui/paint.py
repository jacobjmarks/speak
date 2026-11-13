"""Painting helpers shared by the widgets, the overlay and onboarding: glyphs, level wave, shimmer text, progress ring."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen


BARS = 22  # bars in the level wave


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

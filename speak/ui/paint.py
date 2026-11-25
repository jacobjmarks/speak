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


def _stroke(p: QPainter, color: QColor, size: float) -> None:
    p.setPen(QPen(color, max(1.4, size * 0.09), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)


def draw_clock(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    p.save()
    _stroke(p, color, size)
    r = size * 0.4
    p.drawEllipse(center, r, r)
    p.drawPolyline([QPointF(center.x(), center.y() - r * 0.6), center, QPointF(center.x() + r * 0.45, center.y() + r * 0.3)])
    p.restore()


def draw_sliders(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    """Three tracks with knobs: the settings glyph."""
    p.save()
    _stroke(p, color, size)
    half = size * 0.4
    for dy, knob in ((-0.28, -0.14), (0.0, 0.18), (0.28, -0.02)):
        y = center.y() + dy * size
        x = center.x() + knob * size
        gap = size * 0.12
        p.drawLine(QPointF(center.x() - half, y), QPointF(x - gap, y))
        p.drawLine(QPointF(x + gap, y), QPointF(center.x() + half, y))
        p.drawEllipse(QPointF(x, y), size * 0.08, size * 0.08)
    p.restore()


def draw_info(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    p.save()
    _stroke(p, color, size)
    r = size * 0.4
    p.drawEllipse(center, r, r)
    p.drawLine(QPointF(center.x(), center.y() - r * 0.05), QPointF(center.x(), center.y() + r * 0.5))
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(QPointF(center.x(), center.y() - r * 0.45), size * 0.06, size * 0.06)
    p.restore()


def draw_search(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    p.save()
    _stroke(p, color, size)
    r = size * 0.27
    lens = QPointF(center.x() - size * 0.08, center.y() - size * 0.08)
    p.drawEllipse(lens, r, r)
    p.drawLine(QPointF(lens.x() + r * 0.72, lens.y() + r * 0.72), QPointF(center.x() + size * 0.36, center.y() + size * 0.36))
    p.restore()


def draw_keyboard(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    p.save()
    _stroke(p, color, size)
    w, h = size * 0.82, size * 0.56
    p.drawRoundedRect(QRectF(center.x() - w / 2, center.y() - h / 2, w, h), size * 0.08, size * 0.08)
    p.drawLine(QPointF(center.x() - w * 0.25, center.y() + h * 0.18), QPointF(center.x() + w * 0.25, center.y() + h * 0.18))
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    for i in range(4):
        p.drawEllipse(QPointF(center.x() - w * 0.3 + i * w * 0.2, center.y() - h * 0.14), size * 0.045, size * 0.045)
    p.restore()


def draw_lines(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    """Text lines: the text & typing glyph."""
    p.save()
    _stroke(p, color, size)
    for dy, length in ((-0.26, 0.76), (0.0, 0.76), (0.26, 0.48)):
        y = center.y() + dy * size
        p.drawLine(QPointF(center.x() - size * 0.38, y), QPointF(center.x() - size * 0.38 + length * size, y))
    p.restore()


def draw_pill(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    """The indicator pill with a dot: the indicator & sound glyph."""
    p.save()
    _stroke(p, color, size)
    w, h = size * 0.84, size * 0.42
    p.drawRoundedRect(QRectF(center.x() - w / 2, center.y() - h / 2, w, h), h / 2, h / 2)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(QPointF(center.x() - w * 0.24, center.y()), size * 0.08, size * 0.08)
    p.restore()


def draw_window(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    p.save()
    _stroke(p, color, size)
    w, h = size * 0.8, size * 0.64
    rect = QRectF(center.x() - w / 2, center.y() - h / 2, w, h)
    p.drawRoundedRect(rect, size * 0.08, size * 0.08)
    p.drawLine(QPointF(rect.left(), rect.top() + h * 0.3), QPointF(rect.right(), rect.top() + h * 0.3))
    p.restore()


def draw_refresh(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    p.save()
    _stroke(p, color, size)
    r = size * 0.34
    p.drawArc(QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r), 60 * 16, 290 * 16)
    tip = QPointF(center.x() + r * 0.5, center.y() - r * 0.87)
    p.drawPolyline([QPointF(tip.x() - size * 0.02, tip.y() - size * 0.17), tip, QPointF(tip.x() - size * 0.17, tip.y() + size * 0.05)])
    p.restore()


def draw_copy(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    p.save()
    _stroke(p, color, size * 0.9)
    s = size * 0.46
    p.drawRoundedRect(QRectF(center.x() - s * 0.35, center.y() - s * 0.35, s, s), size * 0.07, size * 0.07)
    p.drawPolyline([QPointF(center.x() - s * 0.65, center.y() + s * 0.35), QPointF(center.x() - s * 0.65, center.y() - s * 0.65),
                    QPointF(center.x() + s * 0.35, center.y() - s * 0.65)])
    p.restore()


def draw_chevron(p: QPainter, center: QPointF, size: float, color: QColor, up: bool = False,
                 right: bool = False) -> None:
    p.save()
    _stroke(p, color, size * 1.4)
    p.translate(center)
    p.rotate(-90 if right else 0)
    d = size * 0.3 * (-1 if up else 1)
    p.drawPolyline([QPointF(-size * 0.45, -d * 0.6), QPointF(0, d * 0.6), QPointF(size * 0.45, -d * 0.6)])
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

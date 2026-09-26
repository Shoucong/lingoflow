"""Small vector icons drawn at runtime so they follow the reading theme."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_SIZE = 18  # logical points; buttons show the icon at this size


def _canvas(scale: float = 3.0) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(int(_SIZE * scale), int(_SIZE * scale))
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pixmap, painter


def _pen(color: str, width: float = 1.5) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _icon(draw, color: str) -> QIcon:
    pixmap, painter = _canvas()
    try:
        draw(painter, color)
    finally:
        painter.end()
    return QIcon(pixmap)


def pin_icon(color: str, filled: bool) -> QIcon:
    """Push pin tilted 45°: outline when free, solid when the window is pinned."""

    def draw(painter: QPainter, ink: str) -> None:
        painter.translate(_SIZE / 2, _SIZE / 2)
        painter.rotate(45)
        head = QPainterPath()
        head.addRoundedRect(QRectF(-3.2, -7.4, 6.4, 2.6), 1.0, 1.0)
        body = QPainterPath()
        body.moveTo(-2.2, -4.8)
        body.lineTo(2.2, -4.8)
        body.lineTo(2.6, -0.2)
        body.lineTo(4.6, 1.6)
        body.lineTo(-4.6, 1.6)
        body.lineTo(-2.6, -0.2)
        body.closeSubpath()
        painter.setPen(_pen(ink, 1.4))
        painter.setBrush(QColor(ink) if filled else Qt.GlobalColor.transparent)
        painter.drawPath(head)
        painter.drawPath(body)
        painter.setPen(_pen(ink, 1.5))
        painter.drawLine(QPointF(0, 1.8), QPointF(0, 7.6))

    return _icon(draw, color)


def more_icon(color: str) -> QIcon:
    def draw(painter: QPainter, ink: str) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ink))
        for x in (4.0, 9.0, 14.0):
            painter.drawEllipse(QPointF(x, 9.0), 1.45, 1.45)

    return _icon(draw, color)


def speaker_icon(color: str) -> QIcon:
    def draw(painter: QPainter, ink: str) -> None:
        body = QPainterPath()
        body.moveTo(2.5, 7.0)
        body.lineTo(5.5, 7.0)
        body.lineTo(9.0, 3.8)
        body.lineTo(9.0, 14.2)
        body.lineTo(5.5, 11.0)
        body.lineTo(2.5, 11.0)
        body.closeSubpath()
        painter.setPen(_pen(ink, 1.3))
        painter.setBrush(QColor(ink))
        painter.drawPath(body)
        painter.setBrush(Qt.GlobalColor.transparent)
        painter.setPen(_pen(ink, 1.4))
        painter.drawArc(QRectF(7.0, 5.5, 5.5, 7.0), -55 * 16, 110 * 16)
        painter.drawArc(QRectF(7.0, 2.8, 9.0, 12.4), -55 * 16, 110 * 16)

    return _icon(draw, color)


def stop_icon(color: str) -> QIcon:
    def draw(painter: QPainter, ink: str) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ink))
        painter.drawRoundedRect(QRectF(4.5, 4.5, 9.0, 9.0), 1.6, 1.6)

    return _icon(draw, color)


def copy_icon(color: str) -> QIcon:
    def draw(painter: QPainter, ink: str) -> None:
        painter.setPen(_pen(ink, 1.35))
        painter.setBrush(Qt.GlobalColor.transparent)
        painter.drawRoundedRect(QRectF(6.2, 5.8, 8.6, 9.6), 1.8, 1.8)
        back = QPainterPath()
        back.moveTo(4.0, 12.0)
        back.lineTo(3.6, 12.0)
        back.arcTo(QRectF(2.6, 10.2, 2.0, 2.0), 270, -90)
        back.lineTo(2.6, 3.8)
        back.arcTo(QRectF(2.6, 2.6, 2.4, 2.4), 180, -90)
        back.lineTo(10.4, 2.6)
        back.arcTo(QRectF(9.8, 2.6, 2.4, 2.4), 90, -90)
        back.lineTo(12.2, 4.2)
        painter.drawPath(back)

    return _icon(draw, color)


def check_icon(color: str) -> QIcon:
    def draw(painter: QPainter, ink: str) -> None:
        painter.setPen(_pen(ink, 1.8))
        path = QPainterPath()
        path.moveTo(4.0, 9.4)
        path.lineTo(7.6, 12.8)
        path.lineTo(14.2, 5.4)
        painter.drawPath(path)

    return _icon(draw, color)


def arrow_down_icon(color: str) -> QIcon:
    def draw(painter: QPainter, ink: str) -> None:
        painter.setPen(_pen(ink, 1.5))
        painter.drawLine(QPointF(9.0, 3.5), QPointF(9.0, 13.5))
        path = QPainterPath()
        path.moveTo(5.0, 9.8)
        path.lineTo(9.0, 13.8)
        path.lineTo(13.0, 9.8)
        painter.drawPath(path)

    return _icon(draw, color)

"""Tiny painter-drawn tool icons, so the app needs no image assets."""
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QColor, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QPolygonF, QRadialGradient)

S = 48  # logical drawing size; rendered @2x for sharpness


def _poly(points):
    return QPolygonF([QPointF(x, y) for x, y in points])


def _select(p, c):
    p.setBrush(c)
    p.drawPolygon(_poly([(13, 8), (13, 37), (21, 30), (27, 41), (32, 38.5), (26, 28), (36, 27.5)]))


def _fill(p, c):
    p.save()
    p.translate(22, 25)
    p.rotate(-22)
    p.drawRoundedRect(QRectF(-13, -8, 24, 20), 4, 4)
    handle = QPainterPath()
    handle.moveTo(-9, -8)
    handle.cubicTo(-9, -20, 7, -20, 7, -8)
    p.drawPath(handle)
    p.restore()
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawPolygon(_poly([(38, 25), (43.5, 35), (32.5, 35)]))
    p.drawEllipse(QRectF(32, 32, 12, 12))


def _border(p, c):
    p.setPen(QPen(c, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QColor(c.red(), c.green(), c.blue(), 70))
    p.drawRoundedRect(QRectF(10, 10, 28, 28), 5, 5)


def _image(p, c):
    p.drawRoundedRect(QRectF(8, 10, 32, 28), 4, 4)
    p.setBrush(c)
    p.drawEllipse(QRectF(14, 15, 7, 7))
    p.setPen(Qt.NoPen)
    p.drawPolygon(_poly([(10, 36), (21, 24), (28, 32), (33, 27), (38, 36)]))


def _eyedropper(p, c):
    p.setPen(QPen(c, 6, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(32, 16), QPointF(18, 30))
    p.setPen(QPen(c, 3, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(18, 30), QPointF(12, 38))
    p.setBrush(c)
    p.drawEllipse(QPointF(35, 13), 5, 5)


def _gradient(p, c):
    g = QLinearGradient(8, 0, 40, 0)
    g.setColorAt(0, QColor(c.red(), c.green(), c.blue(), 25))
    g.setColorAt(1, c)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(8, 10, 32, 28), 5, 5)


def _glow(p, c):
    g = QRadialGradient(QPointF(24, 24), 19)
    g.setColorAt(0, c)
    g.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 0))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(24, 24), 19, 19)
    p.setBrush(c)
    p.drawEllipse(QPointF(24, 24), 6, 6)


def _reset(p, c):
    p.drawArc(QRectF(10, 11, 28, 28), 50 * 16, 280 * 16)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawPolygon(_poly([(31, 5), (39, 15), (26, 15)]))


def _merge(p, c):
    p.drawEllipse(QPointF(18, 24), 11, 11)
    p.drawEllipse(QPointF(30, 24), 11, 11)


def _split(p, c):
    p.drawRoundedRect(QRectF(9, 9, 30, 30), 4, 4)
    p.setPen(QPen(c, 3, Qt.DashLine, Qt.RoundCap))
    p.drawLine(QPointF(5, 43), QPointF(43, 5))


_DRAW = {
    "select": _select, "fill": _fill, "border": _border, "image": _image,
    "eyedropper": _eyedropper, "gradient": _gradient, "glow": _glow,
    "reset": _reset, "merge": _merge, "split": _split,
}


def _pixmap(draw, color: str) -> QPixmap:
    pm = QPixmap(S * 2, S * 2)
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(2)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    p.setPen(QPen(c, 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    draw(p, c)
    p.end()
    return pm


def tool_icon(tool_id: str) -> QIcon:
    draw = _DRAW[tool_id]
    icon = QIcon()
    icon.addPixmap(_pixmap(draw, "#c4c9d2"), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_pixmap(draw, "#ffffff"), QIcon.Normal, QIcon.On)
    icon.addPixmap(_pixmap(draw, "#6b7078"), QIcon.Disabled, QIcon.Off)
    return icon

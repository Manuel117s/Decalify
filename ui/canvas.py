"""Zoom/pan canvas. It only reports pixel clicks; all editing logic lives in the controller."""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (QGraphicsPixmapItem, QGraphicsScene, QGraphicsView)

from .widgets import checker_pixmap


class Canvas(QGraphicsView):
    pixel_clicked = Signal(int, int, object)   # x, y (image pixels), Qt.KeyboardModifiers
    pixel_moved = Signal(int, int)             # (-1, -1) when the cursor is off the image
    zoom_changed = Signal(float)
    file_dropped = Signal(str)

    MIN_ZOOM, MAX_ZOOM = 0.02, 64.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Canvas")
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._base = QGraphicsPixmapItem()
        self._base.setZValue(1)
        self._overlay = QGraphicsPixmapItem()
        self._overlay.setZValue(2)
        self._scene.addItem(self._base)
        self._scene.addItem(self._overlay)

        self._img_size = QSize(0, 0)
        self._zoom = 1.0
        self._auto_fit = True
        self._space = False
        self._panning = False
        self._show_checker = True
        self._checker = QBrush(checker_pixmap())

        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#17181a"))
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        self.viewport().setMouseTracking(True)
        self.viewport().setCursor(Qt.CrossCursor)

    # ---------------------------------------------------------------- public API
    @property
    def zoom(self) -> float:
        return self._zoom

    def has_image(self) -> bool:
        return not self._img_size.isEmpty()

    def set_image(self, img: QImage, keep_view: bool = False):
        """Show `img` (the current composite result). keep_view=True keeps zoom/pan."""
        self._img_size = img.size()
        self._base.setPixmap(QPixmap.fromImage(img))
        w, h = img.width(), img.height()
        m = max(w, h) * 0.5
        self._scene.setSceneRect(QRectF(-m, -m, w + 2 * m, h + 2 * m))
        if not keep_view:
            self._overlay.setPixmap(QPixmap())
            self.fit()
        self.viewport().update()

    def set_overlay(self, img: QImage | None):
        """Transparent RGBA image, same size as the base, drawn on top (selection highlight etc.)."""
        self._overlay.setPixmap(QPixmap() if img is None else QPixmap.fromImage(img))

    def set_checkerboard(self, on: bool):
        self._show_checker = on
        self.viewport().update()

    def fit(self):
        if not self.has_image():
            return
        self._auto_fit = True
        self._set_scrollbars(False)   # nothing to scroll when the whole image fits
        w, h = self._img_size.width(), self._img_size.height()
        pad = max(w, h) * 0.04
        self.resetTransform()
        self.fitInView(QRectF(-pad, -pad, w + 2 * pad, h + 2 * pad), Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self._after_zoom()

    def actual_size(self):
        self.set_zoom(1.0)

    def zoom_in(self):
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self):
        self.set_zoom(self._zoom / 1.25)

    def set_zoom(self, z: float, at_cursor: bool = False):
        z = max(self.MIN_ZOOM, min(self.MAX_ZOOM, z))
        if abs(z - self._zoom) < 1e-9:
            return
        self._auto_fit = False
        self._set_scrollbars(True)
        self.setTransformationAnchor(
            QGraphicsView.AnchorUnderMouse if at_cursor else QGraphicsView.AnchorViewCenter)
        f = z / self._zoom
        self.scale(f, f)
        self._zoom = z
        self._after_zoom()

    # ---------------------------------------------------------------- internals
    def _set_scrollbars(self, visible: bool):
        pol = Qt.ScrollBarAsNeeded if visible else Qt.ScrollBarAlwaysOff
        self.setHorizontalScrollBarPolicy(pol)
        self.setVerticalScrollBarPolicy(pol)

    def _after_zoom(self):
        self.setRenderHint(QPainter.SmoothPixmapTransform, self._zoom < 2.0)  # crisp pixels when zoomed in
        self.zoom_changed.emit(self._zoom)

    def _to_pixel(self, pos) -> tuple[int, int] | None:
        s = self.mapToScene(pos.toPoint())
        x, y = int(math.floor(s.x())), int(math.floor(s.y()))
        if 0 <= x < self._img_size.width() and 0 <= y < self._img_size.height():
            return x, y
        return None

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor("#17181a"))
        if self._show_checker and self.has_image():
            painter.save()
            painter.resetTransform()
            r = self.mapFromScene(QRectF(0, 0, self._img_size.width(), self._img_size.height())).boundingRect()
            painter.fillRect(r, self._checker)
            painter.restore()

    def drawForeground(self, painter, rect):
        if self.has_image():
            return
        painter.save()
        painter.resetTransform()
        painter.setPen(QColor("#9aa0aa"))
        f = QFont(self.font())
        f.setPixelSize(18)
        painter.setFont(f)
        painter.drawText(self.viewport().rect(), Qt.AlignCenter, "Drop a PNG here\nor click Import…")
        painter.restore()

    # ---------------------------------------------------------------- events
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._auto_fit and self.has_image():
            self.fit()

    def wheelEvent(self, e):
        if not self.has_image():
            return
        self.set_zoom(self._zoom * (1.15 ** (e.angleDelta().y() / 120.0)), at_cursor=True)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._space = True
            self.viewport().setCursor(Qt.OpenHandCursor)
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._space = False
            self.viewport().setCursor(Qt.CrossCursor)
        super().keyReleaseEvent(e)

    def mousePressEvent(self, e: QMouseEvent):
        self.setFocus()
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and self._space):
            self._panning = True
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            fake = QMouseEvent(e.type(), e.position(), e.globalPosition(), Qt.LeftButton,
                               Qt.LeftButton, e.modifiers())
            super().mousePressEvent(fake)
            return
        if e.button() == Qt.LeftButton and self.has_image():
            pt = self._to_pixel(e.position())
            if pt:
                self.pixel_clicked.emit(pt[0], pt[1], e.modifiers())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pt = self._to_pixel(e.position()) if self.has_image() else None
        self.pixel_moved.emit(*(pt if pt else (-1, -1)))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self._panning:
            self._panning = False
            self.setDragMode(QGraphicsView.NoDrag)
            self.viewport().setCursor(Qt.OpenHandCursor if self._space else Qt.CrossCursor)

    def leaveEvent(self, e):
        self.pixel_moved.emit(-1, -1)
        super().leaveEvent(e)

    # drag & drop a PNG straight onto the canvas
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.isLocalFile():
                self.file_dropped.emit(url.toLocalFile())
                break

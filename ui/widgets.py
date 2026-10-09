"""Small reusable widgets shared by the panels."""
from __future__ import annotations

import os

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFontMetrics, QImage, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QColorDialog, QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QVBoxLayout, QWidget)

CHECKER_A, CHECKER_B = "#d4d4d8", "#f4f4f5"


def checker_pixmap(cell: int = 8, a: str = CHECKER_A, b: str = CHECKER_B) -> QPixmap:
    pm = QPixmap(cell * 2, cell * 2)
    pm.fill(QColor(a))
    p = QPainter(pm)
    p.fillRect(cell, 0, cell, cell, QColor(b))
    p.fillRect(0, cell, cell, cell, QColor(b))
    p.end()
    return pm


def hint_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Hint")
    lbl.setWordWrap(True)
    return lbl


def panel_title(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("PanelTitle")
    return lbl


class ColorButton(QPushButton):
    """Swatch button that opens a color dialog (with alpha)."""
    color_changed = Signal(QColor)

    def __init__(self, color: str = "#000000", parent=None):
        super().__init__(parent)
        self._c = QColor(color)
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self) -> QColor:
        return QColor(self._c)

    def set_color(self, color, emit: bool = True):
        self._c = QColor(color)
        self._refresh()
        if emit:
            self.color_changed.emit(self.color())

    def _pick(self):
        opts = QColorDialog.ColorDialogOption.ShowAlphaChannel | QColorDialog.ColorDialogOption.DontUseNativeDialog
        c = QColorDialog.getColor(self._c, self, "Choose color", opts)
        if c.isValid():
            self.set_color(c)

    def _refresh(self):
        c = self._c
        self.setText(c.name().upper())
        fg = "#000" if c.lightness() > 140 else "#fff"
        self.setStyleSheet(
            f"QPushButton {{ background: rgba({c.red()},{c.green()},{c.blue()},{c.alpha()}); "
            f"color: {fg}; border: 1px solid #555a63; padding: 2px 8px; }}"
        )


class LabeledSlider(QWidget):
    valueChanged = Signal(int)

    def __init__(self, lo: int, hi: int, val: int, suffix: str = "", parent=None):
        super().__init__(parent)
        self._suffix = suffix
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.label = QLabel()
        self.label.setMinimumWidth(46)
        self.label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.label)
        self.slider.valueChanged.connect(self._on)
        self.slider.setValue(val)
        self._on(val)

    def _on(self, v: int):
        self.label.setText(f"{v}{self._suffix}")
        self.valueChanged.emit(v)

    def value(self) -> int:
        return self.slider.value()

    def setValue(self, v: int):
        self.slider.setValue(v)


class ImagePicker(QWidget):
    """Thumbnail + 'Choose…' button for picking a fill image."""
    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = ""
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.thumb = QLabel("none")
        self.thumb.setFixedSize(52, 52)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("border: 1px dashed #3d4148; border-radius: 6px; color: #9aa0aa;")
        col = QVBoxLayout()
        col.setSpacing(3)
        btn = QPushButton("Choose…")
        btn.clicked.connect(self._choose)
        self.name = QLabel("No image")
        self.name.setObjectName("Hint")
        col.addWidget(btn)
        col.addWidget(self.name)
        lay.addWidget(self.thumb)
        lay.addLayout(col, 1)

    def path(self) -> str:
        return self._path

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose fill image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)")
        if path:
            self.set_path(path)

    def set_path(self, path: str):
        self._path = path
        pm = QPixmap(path)
        if pm.isNull():
            self.thumb.setPixmap(QPixmap())
            self.thumb.setText("?")
        else:
            self.thumb.setText("")
            self.thumb.setPixmap(pm.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        fm = QFontMetrics(self.name.font())
        self.name.setText(fm.elidedText(os.path.basename(path), Qt.ElideMiddle, 130))
        self.changed.emit(path)


class PreviewView(QWidget):
    """Checkerboard preview of the selected region, scaled to fit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pm: QPixmap | None = None
        self._checker = QBrush(checker_pixmap())
        self.setMinimumSize(200, 200)

    def set_image(self, img: QImage | None):
        self._pm = None if img is None or img.isNull() else QPixmap.fromImage(img)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -2, -2)
        clip = QPainterPath()
        clip.addRoundedRect(r, 8, 8)
        p.setClipPath(clip)
        p.fillRect(r, QColor("#17181a"))
        if self._pm is None:
            p.setPen(QColor("#9aa0aa"))
            p.drawText(r, Qt.AlignCenter | Qt.TextWordWrap, "No selection\nClick a region on the canvas")
        else:
            box = r.adjusted(10, 10, -10, -10)
            scaled = self._pm.scaled(box.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = box.x() + (box.width() - scaled.width()) // 2
            y = box.y() + (box.height() - scaled.height()) // 2
            p.fillRect(QRect(x, y, scaled.width(), scaled.height()), self._checker)
            p.drawPixmap(x, y, scaled)
        p.setClipping(False)
        p.setPen(QPen(QColor("#3d4148"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 8, 8)

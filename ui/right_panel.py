"""Right panel: selection preview on top, Import / Re-trace / Export at the bottom."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFrame, QMenu, QPushButton, QVBoxLayout

from .widgets import PreviewView, hint_label, panel_title


class RightPanel(QFrame):
    import_clicked = Signal()
    retrace_clicked = Signal()
    export_clicked = Signal(str)   # "png" | "svg" | "selection_png"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidePanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        root.addWidget(panel_title("Selection preview"))
        self.preview = PreviewView()
        self.preview.setFixedHeight(230)      # small preview on top, as in the sketch
        root.addWidget(self.preview)
        self.caption = hint_label("Nothing selected")
        root.addWidget(self.caption)
        root.addStretch(1)                    # pushes Import / Re-trace / Export to the bottom
        root.addSpacing(8)

        self.btn_import = QPushButton("Import…")
        self.btn_import.setObjectName("Primary")
        self.btn_import.clicked.connect(self.import_clicked)

        self.btn_retrace = QPushButton("Re-trace…")
        self.btn_retrace.setToolTip("Tweak the region-detection settings and run detection again")
        self.btn_retrace.clicked.connect(self.retrace_clicked)

        self.btn_export = QPushButton("Export")
        menu = QMenu(self.btn_export)
        menu.addAction("PNG…", lambda: self.export_clicked.emit("png"))
        menu.addAction("SVG (vector)…", lambda: self.export_clicked.emit("svg"))
        menu.addSeparator()
        menu.addAction("Selection only (PNG)…", lambda: self.export_clicked.emit("selection_png"))
        self.btn_export.setMenu(menu)

        for b in (self.btn_import, self.btn_retrace, self.btn_export):
            b.setMinimumHeight(36)
            root.addWidget(b)

    def set_preview(self, img: QImage | None, caption: str = ""):
        self.preview.set_image(img)
        self.caption.setText(caption or "Nothing selected")

    def set_has_image(self, has: bool):
        self.btn_retrace.setEnabled(has)
        self.btn_export.setEnabled(has)

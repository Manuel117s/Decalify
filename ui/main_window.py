"""Main window: menu bar, three-panel layout, status bar, and the signal wiring."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QSplitter, QToolButton, QWidget)

from .canvas import Canvas
from .retrace_dialog import RetraceDialog
from .right_panel import RightPanel
from .tool_panel import ToolPanel

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.webp);;PNG (*.png);;All files (*)"


class MainWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.ctrl = controller
        self.setWindowTitle("Decalify")
        self.resize(1360, 820)
        self.setMinimumSize(980, 600)

        self.canvas = Canvas()
        self.tools = ToolPanel()
        self.right = RightPanel()
        self._retrace_dlg: RetraceDialog | None = None

        self._build_layout()
        self._build_menus()
        self._build_statusbar()
        self._connect()

        self.tools.emit_all()
        self.right.set_has_image(False)
        self.statusBar().showMessage("Ready. Import a PNG to begin (Ctrl+O).")

    # ---------------------------------------------------------------- layout
    def _build_layout(self):
        self.tools.setMinimumWidth(240)
        self.tools.setMaximumWidth(330)
        self.right.setMinimumWidth(250)
        self.right.setMaximumWidth(360)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(10)
        split.addWidget(self.tools)
        split.addWidget(self.canvas)
        split.addWidget(self.right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 0)
        split.setSizes([260, 820, 280])

        central = QWidget()
        central.setObjectName("central")
        lay = QHBoxLayout(central)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(split)
        self.setCentralWidget(central)

    def _act(self, menu, text, slot, shortcut=None, checkable=False, checked=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut if isinstance(shortcut, QKeySequence) else QKeySequence(shortcut))
        if checkable:
            a.setCheckable(True)
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(lambda *_: slot())
        menu.addAction(a)
        return a

    def _build_menus(self):
        mb = self.menuBar()

        m = mb.addMenu("&File")
        self._act(m, "Import image…", self._import, QKeySequence.Open)
        m.addSeparator()
        self.act_export_png = self._act(m, "Export PNG…", lambda: self._export("png"), "Ctrl+E")
        self.act_export_svg = self._act(m, "Export SVG…", lambda: self._export("svg"), "Ctrl+Shift+E")
        self.act_export_sel = self._act(m, "Export selection only…", lambda: self._export("selection_png"))
        m.addSeparator()
        self._act(m, "Quit", self.close, QKeySequence.Quit)

        m = mb.addMenu("&Edit")
        self._act(m, "Undo", self.ctrl.undo, QKeySequence.Undo)
        self._act(m, "Redo", self.ctrl.redo, QKeySequence.Redo)
        m.addSeparator()
        self._act(m, "Select all regions", self.ctrl.select_all, "Ctrl+A")
        self._act(m, "Deselect", self.ctrl.deselect, "Ctrl+D")

        m = mb.addMenu("&View")
        self._act(m, "Zoom in", self.canvas.zoom_in, QKeySequence.ZoomIn)
        self._act(m, "Zoom out", self.canvas.zoom_out, QKeySequence.ZoomOut)
        self._act(m, "Fit to window", self.canvas.fit, "Ctrl+0")
        self._act(m, "Actual size (100%)", self.canvas.actual_size, "Ctrl+1")
        m.addSeparator()
        self._act(m, "Show checkerboard", self.canvas.set_checkerboard, checkable=True, checked=True)
        self._act(m, "Show region outlines", self.ctrl.set_show_outlines, checkable=True, checked=True)

        m = mb.addMenu("&Options")
        self._act(m, "Re-trace settings…", self._open_retrace, "Ctrl+T")
        m.addSeparator()
        self._act(m, "Preferences…", lambda: QMessageBox.information(
            self, "Preferences", "Placeholder: add your app preferences here."))

        m = mb.addMenu("&About")
        self._act(m, "About Decalify", lambda: QMessageBox.about(
            self, "About Decalify",
            "Decalify\nSelect the parts of a PNG and restyle them: fill, border, image fill."))
        self._act(m, "About Qt", lambda: QMessageBox.aboutQt(self))

    def _build_statusbar(self):
        sb = self.statusBar()
        self.lbl_xy = QLabel("—")
        self.lbl_xy.setMinimumWidth(90)
        self.lbl_size = QLabel("")
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setMinimumWidth(48)
        fit = QToolButton()
        fit.setObjectName("StatusBtn")
        fit.setText("Fit")
        fit.clicked.connect(self.canvas.fit)
        one = QToolButton()
        one.setObjectName("StatusBtn")
        one.setText("100%")
        one.clicked.connect(self.canvas.actual_size)
        for w in (self.lbl_xy, self.lbl_size, self.lbl_zoom, fit, one):
            sb.addPermanentWidget(w)

    # ---------------------------------------------------------------- wiring
    def _connect(self):
        c, t, r, cv = self.ctrl, self.tools, self.right, self.canvas

        # UI -> controller
        t.tool_changed.connect(c.set_tool)
        t.options_changed.connect(c.set_options)
        cv.pixel_clicked.connect(c.on_click)
        cv.rect_selected.connect(c.on_rect_select)
        cv.file_dropped.connect(c.open_image)
        r.import_clicked.connect(self._import)
        r.retrace_clicked.connect(self._open_retrace)
        r.export_clicked.connect(self._export)

        # controller -> UI
        c.image_loaded.connect(self._on_image_loaded)
        c.result_changed.connect(lambda img: cv.set_image(img, keep_view=True))
        c.overlay_changed.connect(cv.set_overlay)
        c.preview_changed.connect(r.set_preview)
        c.color_picked.connect(t.set_picked_color)
        c.status.connect(self.statusBar().showMessage)

        # canvas -> status bar
        cv.pixel_moved.connect(lambda x, y: self.lbl_xy.setText("—" if x < 0 else f"x {x}  y {y}"))
        cv.zoom_changed.connect(lambda z: self.lbl_zoom.setText(f"{z * 100:.0f}%"))

    def _on_image_loaded(self, img):
        self.canvas.set_image(img)
        self.right.set_has_image(True)
        self.lbl_size.setText(f"{img.width()} × {img.height()} px   ")
        name = (self.ctrl.path or "").replace("\\", "/").split("/")[-1]
        self.setWindowTitle(f"{name} — Decalify" if name else "Decalify")

    # ---------------------------------------------------------------- actions
    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import image", "", IMAGE_FILTER)
        if path:
            self.ctrl.open_image(path)

    def _export(self, kind: str):
        if self.ctrl.result is None:
            self.statusBar().showMessage("Nothing to export yet.")
            return
        title, flt, ext = {
            "png": ("Export PNG", "PNG image (*.png)", ".png"),
            "svg": ("Export SVG", "SVG vector (*.svg)", ".svg"),
            "selection_png": ("Export selection as PNG", "PNG image (*.png)", ".png"),
        }[kind]
        path, _ = QFileDialog.getSaveFileName(self, title, "", flt)
        if path:
            if not path.lower().endswith(ext):
                path += ext
            self.ctrl.export(kind, path)

    def _open_retrace(self):
        if self._retrace_dlg is None:
            dlg = RetraceDialog(self.ctrl.retrace_params, self)
            dlg.params_changed.connect(lambda p: self.ctrl.retrace(p, preview=True))
            dlg.accepted.connect(lambda: self.ctrl.retrace(dlg.params(), preview=False))
            dlg.rejected.connect(self.ctrl.retrace_cancel)
            self.ctrl.trace_info.connect(dlg.set_info)
            self._retrace_dlg = dlg
        self._retrace_dlg.set_params(self.ctrl.retrace_params)
        self._retrace_dlg.show()
        self._retrace_dlg.raise_()
        self._retrace_dlg.activateWindow()

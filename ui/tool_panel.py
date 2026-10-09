"""Left panel: tool buttons + per-tool options. Emits signals; contains no image logic."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFormLayout,
                               QFrame, QGridLayout, QGroupBox, QScrollArea,
                               QSizePolicy, QSpinBox, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget)

from .icons import tool_icon
from .widgets import (ColorButton, ImagePicker, LabeledSlider, hint_label,
                      panel_title)

# (id, label, shortcut)
CORE_TOOLS = [("select", "Select", "V"), ("fill", "Fill", "F"),
              ("border", "Border", "B"), ("image", "Image fill", "I")]
EXTRA_TOOLS = [("eyedropper", "Eyedropper", "E"), ("gradient", "Gradient", "G"),
               ("glow", "Glow", "L"), ("reset", "Reset", "R"),
               ("merge", "Merge", "M"), ("split", "Split", "X")]

# Option spec per tool:  (label, kind, key, default/args)
#   kinds: combo(list) | check(bool) | color(hex) | slider(lo,hi,val,suffix) | spin(lo,hi,val,suffix) | image
BLEND = ["Normal", "Multiply", "Screen", "Overlay"]
SPECS: dict[str, dict] = {
    "select": {
        "desc": "Click a region to select it. Shift adds to the selection, Alt removes.",
        "rows": [("Mode", "combo", "mode", ["Replace", "Add", "Subtract"]),
                 ("Include holes", "check", "holes", True),
                 ("Select background gaps", "check", "gaps", False),
                 ("Highlight selection", "check", "highlight", True)]},
    "fill": {
        "desc": "Paint the selected regions with a solid color.",
        "rows": [("Color", "color", "color", "#e63946"),
                 ("Opacity", "slider", "opacity", (0, 100, 100, "%")),
                 ("Blend", "combo", "blend", BLEND),
                 ("Keep edge smoothing", "check", "smooth", True)]},
    "border": {
        "desc": "Outline the selected regions.",
        "rows": [("Color", "color", "color", "#000000"),
                 ("Width", "spin", "width", (1, 200, 4, " px")),
                 ("Position", "combo", "position", ["Outside", "Center", "Inside"]),
                 ("Style", "combo", "style", ["Solid", "Dashed", "Dotted"]),
                 ("Corners", "combo", "corners", ["Round", "Miter"]),
                 ("Opacity", "slider", "opacity", (0, 100, 100, "%"))]},
    "image": {
        "desc": "Fill the selected regions with another image.",
        "rows": [("Image", "image", "path", None),
                 ("Fit", "combo", "fit", ["Cover", "Stretch", "Contain", "Tile"]),
                 ("Scale", "slider", "scale", (10, 400, 100, "%")),
                 ("Rotation", "spin", "rotation", (-180, 180, 0, " °")),
                 ("Opacity", "slider", "opacity", (0, 100, 100, "%"))]},
    "eyedropper": {
        "desc": "Click the canvas to pick a color and send it to Fill or Border.",
        "rows": [("Sample from", "combo", "source", ["Result", "Original"]),
                 ("Send to", "combo", "send_to", ["Fill color", "Border color"]),
                 ("Picked", "color", "color", "#000000")]},
    "gradient": {
        "desc": "Fill the selected regions with a gradient.",
        "rows": [("From", "color", "c1", "#ff7a18"),
                 ("To", "color", "c2", "#af002d"),
                 ("Type", "combo", "type", ["Linear", "Radial"]),
                 ("Angle", "spin", "angle", (0, 360, 90, " °")),
                 ("Opacity", "slider", "opacity", (0, 100, 100, "%"))]},
    "glow": {
        "desc": "Add a drop shadow or outer glow behind the selected regions.",
        "rows": [("Color", "color", "color", "#000000"),
                 ("Blur", "spin", "blur", (0, 100, 12, " px")),
                 ("Offset X", "spin", "dx", (-100, 100, 4, " px")),
                 ("Offset Y", "spin", "dy", (-100, 100, 4, " px")),
                 ("Opacity", "slider", "opacity", (0, 100, 60, "%"))]},
    "reset": {
        "desc": "Remove edits from the selected regions.",
        "rows": [("Clear fill", "check", "fill", True),
                 ("Clear border", "check", "border", True),
                 ("Clear image", "check", "image", True),
                 ("Clear effects", "check", "effects", True)]},
    "merge": {
        "desc": "Shift-click several regions, then click once more to merge them into a single region.",
        "rows": [("Fill gaps between", "check", "fill_gaps", False)]},
    "split": {
        "desc": "Draw a cut across a region to split it into two (for shapes that touch).",
        "rows": [("Cut width", "spin", "cut", (1, 50, 2, " px")),
                 ("Cut mode", "combo", "mode", ["Line", "Freehand"])]},
}


def _make_widget(kind: str, arg):
    if kind == "combo":
        w = QComboBox()
        w.addItems(arg)
    elif kind == "check":
        w = QCheckBox()
        w.setChecked(arg)
    elif kind == "color":
        w = ColorButton(arg)
    elif kind == "slider":
        w = LabeledSlider(*arg)
    elif kind == "spin":
        lo, hi, val, suffix = arg
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setValue(val)
        w.setSuffix(suffix)
    elif kind == "image":
        w = ImagePicker()
    else:
        raise ValueError(kind)
    return w


def _read(w):
    if isinstance(w, ColorButton):
        return w.color()
    if isinstance(w, ImagePicker):
        return w.path()
    if isinstance(w, LabeledSlider):
        return w.value()
    if isinstance(w, QSpinBox):
        return w.value()
    if isinstance(w, QComboBox):
        return w.currentText()
    if isinstance(w, QCheckBox):
        return w.isChecked()
    raise TypeError(type(w))


def _signal_of(w):
    if isinstance(w, ColorButton):
        return w.color_changed
    if isinstance(w, ImagePicker):
        return w.changed
    if isinstance(w, (LabeledSlider, QSpinBox)):
        return w.valueChanged
    if isinstance(w, QComboBox):
        return w.currentTextChanged
    return w.toggled  # QCheckBox


class ToolPanel(QFrame):
    tool_changed = Signal(str)            # tool id
    options_changed = Signal(str, dict)   # tool id, {key: value}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidePanel")
        self._labels: dict[str, str] = {}
        self._widgets: dict[str, dict[str, QWidget]] = {}
        self._page_index: dict[str, int] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        root.addWidget(panel_title("Tools"))
        root.addLayout(self._grid(CORE_TOOLS))
        root.addSpacing(4)
        root.addWidget(panel_title("More tools"))
        root.addLayout(self._grid(EXTRA_TOOLS))

        self.opt_box = QGroupBox("Options")
        box_lay = QVBoxLayout(self.opt_box)
        box_lay.setContentsMargins(6, 10, 6, 6)
        self.stack = QStackedWidget()
        for tid, _, _ in CORE_TOOLS + EXTRA_TOOLS:
            self._page_index[tid] = self.stack.addWidget(self._build_page(tid))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.stack)
        box_lay.addWidget(scroll)
        root.addWidget(self.opt_box, 1)

        self.select_tool("select")

    # ---------------------------------------------------------------- building
    def _grid(self, tools):
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (tid, label, key) in enumerate(tools):
            btn = QToolButton()
            btn.setObjectName("ToolButton")
            btn.setText(label)
            btn.setIcon(tool_icon(tid))
            btn.setIconSize(QSize(26, 26))
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setCheckable(True)
            btn.setMinimumHeight(62)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setToolTip(f"{label}  ({key})")
            btn.setShortcut(key)
            btn.setCursor(Qt.PointingHandCursor)
            self._group.addButton(btn)
            btn.clicked.connect(lambda _=False, t=tid: self.select_tool(t))
            self._buttons[tid] = btn
            self._labels[tid] = label
            grid.addWidget(btn, i // 2, i % 2)
        return grid

    def _build_page(self, tid: str) -> QWidget:
        spec = SPECS[tid]
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 2, 4, 4)
        lay.setSpacing(8)
        lay.addWidget(hint_label(spec["desc"]))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)   # field drops under its label if too narrow
        form.setVerticalSpacing(8)
        widgets: dict[str, QWidget] = {}
        for label, kind, key, arg in spec["rows"]:
            w = _make_widget(kind, arg)
            widgets[key] = w
            _signal_of(w).connect(lambda *_, t=tid: self._emit(t))
            if kind == "check":          # checkbox carries its own label: full-width row
                w.setText(label)
                form.addRow(w)
            else:
                form.addRow(label, w)
        lay.addLayout(form)
        lay.addStretch(1)
        self._widgets[tid] = widgets
        return page

    # ---------------------------------------------------------------- public API
    def current_tool(self) -> str:
        for tid, btn in self._buttons.items():
            if btn.isChecked():
                return tid
        return "select"

    def options(self, tid: str | None = None) -> dict:
        tid = tid or self.current_tool()
        return {k: _read(w) for k, w in self._widgets[tid].items()}

    def select_tool(self, tid: str):
        self._buttons[tid].setChecked(True)
        self.stack.setCurrentIndex(self._page_index[tid])
        self.opt_box.setTitle(f"{self._labels[tid]} options")
        self.tool_changed.emit(tid)

    def emit_all(self):
        """Push every tool's current options once (call after wiring signals)."""
        for tid in self._widgets:
            self._emit(tid)
        self.tool_changed.emit(self.current_tool())

    def set_picked_color(self, color: QColor):
        """Used by the eyedropper: store the color and forward it to Fill/Border."""
        eye = self._widgets["eyedropper"]
        eye["color"].set_color(color, emit=False)
        target = "fill" if eye["send_to"].currentText().startswith("Fill") else "border"
        self._widgets[target]["color"].set_color(color)
        self._emit("eyedropper")

    def _emit(self, tid: str):
        self.options_changed.emit(tid, self.options(tid))

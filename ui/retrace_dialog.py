"""Separate window with the knobs of the tracing (region detection) algorithm."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QPushButton, QSpinBox, QVBoxLayout)

from controller import DEFAULT_RETRACE
from .widgets import LabeledSlider, hint_label

MODES = [("Auto (alpha channel, else Otsu)", "auto"), ("Alpha channel only", "alpha"),
         ("Brightness threshold", "threshold"), ("Color distance", "color")]
CONNECTIVITY = [("8-way (diagonals connect)", 8), ("4-way (edges only)", 4)]


class RetraceDialog(QDialog):
    params_changed = Signal(dict)   # emitted on every change while "Live preview" is on

    def __init__(self, params: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Re-trace settings")
        self.setMinimumWidth(400)
        self._building = True

        # --- detection
        self.mode = QComboBox()
        for text, data in MODES:
            self.mode.addItem(text, data)
        self.threshold = LabeledSlider(0, 255, 127)
        self.invert = QCheckBox("Shape is lighter than background")
        det = QGroupBox("Detection")
        f = QFormLayout(det)
        f.addRow("Method", self.mode)
        f.addRow("Threshold", self.threshold)
        f.addRow("", self.invert)

        # --- regions
        self.connectivity = QComboBox()
        for text, data in CONNECTIVITY:
            self.connectivity.addItem(text, data)
        self.min_area = QSpinBox()
        self.min_area.setRange(0, 1_000_000)
        self.min_area.setSuffix(" px²")
        self.include_gaps = QCheckBox("Also trace background gaps as regions")
        self.keep_holes = QCheckBox("Keep enclosed holes as separate regions")
        reg = QGroupBox("Regions")
        f = QFormLayout(reg)
        f.addRow("Connectivity", self.connectivity)
        f.addRow("Ignore smaller than", self.min_area)
        f.addRow("", self.include_gaps)
        f.addRow("", self.keep_holes)

        # --- edges
        self.blur = QSpinBox()
        self.blur.setRange(0, 20)
        self.blur.setSuffix(" px")
        self.close_gaps = QSpinBox()
        self.close_gaps.setRange(0, 20)
        self.close_gaps.setSuffix(" px")
        self.simplify = QDoubleSpinBox()
        self.simplify.setRange(0.0, 10.0)
        self.simplify.setSingleStep(0.1)
        self.simplify.setSuffix(" px")
        self.antialias = QCheckBox("Anti-aliased edges")
        edges = QGroupBox("Edges")
        f = QFormLayout(edges)
        f.addRow("Pre-blur", self.blur)
        f.addRow("Close tiny gaps", self.close_gaps)
        f.addRow("Simplify contours", self.simplify)
        f.addRow("", self.antialias)

        # --- footer
        self.info = hint_label("")
        self.live = QCheckBox("Live preview")
        self.live.setChecked(True)
        reset = QPushButton("Reset defaults")
        reset.clicked.connect(self._reset)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Apply")
        buttons.button(QDialogButtonBox.Ok).setObjectName("Primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(self.live)
        row.addStretch(1)
        row.addWidget(reset)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(hint_label("Change how regions are detected. Live preview re-runs detection as you adjust."))
        root.addWidget(det)
        root.addWidget(reg)
        root.addWidget(edges)
        root.addWidget(self.info)
        root.addLayout(row)
        root.addWidget(buttons)

        for w in (self.mode, self.connectivity):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.invert, self.include_gaps, self.keep_holes, self.antialias):
            w.toggled.connect(self._changed)
        for w in (self.min_area, self.blur, self.close_gaps, self.simplify):
            w.valueChanged.connect(self._changed)
        self.threshold.valueChanged.connect(self._changed)

        self.set_params(params)

    # ---------------------------------------------------------------- API
    def params(self) -> dict:
        return {
            "mode": self.mode.currentData(),
            "threshold": self.threshold.value(),
            "invert": self.invert.isChecked(),
            "connectivity": self.connectivity.currentData(),
            "min_area": self.min_area.value(),
            "include_gaps": self.include_gaps.isChecked(),
            "keep_holes": self.keep_holes.isChecked(),
            "blur": self.blur.value(),
            "close_gaps": self.close_gaps.value(),
            "simplify": self.simplify.value(),
            "antialias": self.antialias.isChecked(),
        }

    def set_params(self, p: dict):
        self._building = True
        self.mode.setCurrentIndex(max(0, self.mode.findData(p["mode"])))
        self.threshold.setValue(p["threshold"])
        self.invert.setChecked(p["invert"])
        self.connectivity.setCurrentIndex(max(0, self.connectivity.findData(p["connectivity"])))
        self.min_area.setValue(p["min_area"])
        self.include_gaps.setChecked(p["include_gaps"])
        self.keep_holes.setChecked(p["keep_holes"])
        self.blur.setValue(p["blur"])
        self.close_gaps.setValue(p["close_gaps"])
        self.simplify.setValue(p["simplify"])
        self.antialias.setChecked(p["antialias"])
        self._building = False
        self._update_enabled()

    def set_info(self, text: str):
        """Controller feedback, e.g. '14 regions found'."""
        self.info.setText(text)

    # ---------------------------------------------------------------- internals
    def _update_enabled(self):
        self.threshold.setEnabled(self.mode.currentData() == "threshold")

    def _changed(self, *_):
        if self._building:
            return
        self._update_enabled()
        if self.live.isChecked():
            self.params_changed.emit(self.params())

    def _reset(self):
        self.set_params(DEFAULT_RETRACE)
        self._changed()

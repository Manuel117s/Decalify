"""
EditorController: the central image processing and state management engine.

The UI never touches pixels directly. It calls methods on EditorController
and responds to Qt signals.
"""
from __future__ import annotations

import cv2
import numpy as np

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter

DEFAULT_RETRACE = {
    "mode": "auto",          # auto | alpha | threshold | color
    "threshold": 127,
    "invert": False,
    "connectivity": 8,       # 4 | 8
    "min_area": 16,          # ignore blobs smaller than this (px²)
    "include_gaps": False,   # also label background gaps
    "keep_holes": True,
    "blur": 0,
    "close_gaps": 0,
    "simplify": 0.8,         # contour simplification (px)
    "antialias": True,
}


def qimage_to_numpy(qimg: QImage) -> np.ndarray:
    """Convert a QImage to a contiguous uint8 NumPy RGBA array."""
    if qimg.isNull():
        return np.zeros((0, 0, 4), dtype=np.uint8)
    qimg_rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
    w, h = qimg_rgba.width(), qimg_rgba.height()
    ptr = qimg_rgba.constBits()
    return np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4)).copy()


def numpy_to_qimage(arr: np.ndarray) -> QImage:
    """Convert a NumPy array (RGBA, RGB, or Grayscale) to a detached QImage."""
    if arr.size == 0:
        return QImage()
    if not arr.flags["C_CONTIGUOUS"]:
        arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    if arr.ndim == 2:
        return QImage(arr.data, w, h, w, QImage.Format_Grayscale8).copy()
    if arr.shape[2] == 4:
        return QImage(arr.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
    if arr.shape[2] == 3:
        return QImage(arr.data, w, h, w * 3, QImage.Format_RGB888).copy()
    raise ValueError(f"Unsupported array shape: {arr.shape}")


def run_segmentation(rgba: np.ndarray, params: dict) -> tuple[np.ndarray, dict[int, dict]]:
    """
    Segment an RGBA NumPy array into connected regions based on parameters.
    Returns:
        labels: 2D np.int32 array with region IDs (0 is background).
        regions: dict mapping region_id -> metadata dictionary.
    """
    if rgba.size == 0:
        return np.zeros((0, 0), dtype=np.int32), {}

    h, w = rgba.shape[:2]
    mode = params.get("mode", "auto")
    threshold = int(params.get("threshold", 127))
    invert = bool(params.get("invert", False))
    connectivity = int(params.get("connectivity", 8))
    conn = 4 if connectivity == 4 else 8
    min_area = int(params.get("min_area", 16))
    include_gaps = bool(params.get("include_gaps", False))
    keep_holes = bool(params.get("keep_holes", True))
    blur = int(params.get("blur", 0))
    close_gaps = int(params.get("close_gaps", 0))
    simplify = float(params.get("simplify", 0.8))

    alpha = rgba[:, :, 3]
    rgb = rgba[:, :, :3]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # 1. Base binary mask generation
    if mode == "alpha":
        mask = (alpha > threshold).astype(np.uint8) * 255
        if invert:
            mask = 255 - mask
    elif mode == "threshold":
        # Invert toggle: shape lighter than background -> BINARY; else BINARY_INV
        thresh_type = cv2.THRESH_BINARY if invert else cv2.THRESH_BINARY_INV
        _, mask = cv2.threshold(gray, threshold, 255, thresh_type)
    elif mode == "color":
        corners = np.vstack([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]])
        bg_color = np.median(corners, axis=0)
        dist = np.linalg.norm(rgb.astype(np.float32) - bg_color.astype(np.float32), axis=2)
        max_dist = np.max(dist) if np.max(dist) > 0 else 1.0
        norm_dist = (dist / max_dist * 255).astype(np.uint8)
        thresh_type = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
        _, mask = cv2.threshold(norm_dist, threshold, 255, thresh_type)
    else:  # "auto"
        has_alpha = np.any(alpha < 250) and np.any(alpha > 10)
        if has_alpha:
            mask = (alpha > threshold).astype(np.uint8) * 255
            if invert:
                mask = 255 - mask
        else:
            thresh_type = (cv2.THRESH_BINARY if invert else cv2.THRESH_BINARY_INV) + cv2.THRESH_OTSU
            _, mask = cv2.threshold(gray, 0, 255, thresh_type)

    # 2. Pre-processing: blur
    if blur > 0:
        k = blur * 2 + 1
        mask = cv2.GaussianBlur(mask, (k, k), 0)
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    # 3. Pre-processing: close tiny gaps
    if close_gaps > 0:
        k = close_gaps * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # 4. Hole filling if keep_holes is False
    if not keep_holes:
        h_pad, w_pad = h + 2, w + 2
        flood_mask = np.zeros((h_pad, w_pad), dtype=np.uint8)
        inv_mask = (255 - mask).copy()
        cv2.floodFill(inv_mask, flood_mask, (0, 0), 0)
        mask = mask | inv_mask

    # 5. Connected components
    n, raw_labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=conn)

    # 6. Filter by min_area and build region records
    labels = np.zeros((h, w), dtype=np.int32)
    regions: dict[int, dict] = {}
    new_rid = 1
    for r in range(1, n):
        area = int(stats[r, cv2.CC_STAT_AREA])
        if area >= min_area:
            labels[raw_labels == r] = new_rid
            bx, by, bw, bh = (
                int(stats[r, cv2.CC_STAT_LEFT]),
                int(stats[r, cv2.CC_STAT_TOP]),
                int(stats[r, cv2.CC_STAT_WIDTH]),
                int(stats[r, cv2.CC_STAT_HEIGHT]),
            )
            cx, cy = float(centroids[r][0]), float(centroids[r][1])

            # Contours for outline drawing and SVG export
            sub = (raw_labels[by:by + bh, bx:bx + bw] == r).astype(np.uint8) * 255
            sub_pad = np.pad(sub, 1, mode="constant")
            cnts, hier = cv2.findContours(sub_pad, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
            adjusted_cnts = [c + np.array([[[bx - 1, by - 1]]], dtype=np.int32) for c in cnts]
            if simplify > 0:
                adjusted_cnts = [cv2.approxPolyDP(c, simplify, closed=True) for c in adjusted_cnts]

            regions[new_rid] = {
                "id": new_rid,
                "bbox": (bx, by, bw, bh),
                "area": area,
                "centroid": (cx, cy),
                "contours": adjusted_cnts,
                "hierarchy": hier,
                "is_gap": False,
            }
            new_rid += 1

    # 7. Include background gaps if requested
    if include_gaps:
        gap_mask = (labels == 0).astype(np.uint8) * 255
        h_pad, w_pad = h + 2, w + 2
        fmask = np.zeros((h_pad, w_pad), dtype=np.uint8)
        cv2.floodFill(gap_mask, fmask, (0, 0), 0)
        gn, glabels, gstats, gcentroids = cv2.connectedComponentsWithStats(gap_mask, connectivity=conn)
        for gr in range(1, gn):
            garea = int(gstats[gr, cv2.CC_STAT_AREA])
            if garea >= min_area:
                labels[glabels == gr] = new_rid
                bx, by, bw, bh = (
                    int(gstats[gr, cv2.CC_STAT_LEFT]),
                    int(gstats[gr, cv2.CC_STAT_TOP]),
                    int(gstats[gr, cv2.CC_STAT_WIDTH]),
                    int(gstats[gr, cv2.CC_STAT_HEIGHT]),
                )
                cx, cy = float(gcentroids[gr][0]), float(gcentroids[gr][1])

                sub = (glabels[by:by + bh, bx:bx + bw] == gr).astype(np.uint8) * 255
                sub_pad = np.pad(sub, 1, mode="constant")
                cnts, hier = cv2.findContours(sub_pad, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
                adjusted_cnts = [c + np.array([[[bx - 1, by - 1]]], dtype=np.int32) for c in cnts]
                if simplify > 0:
                    adjusted_cnts = [cv2.approxPolyDP(c, simplify, closed=True) for c in adjusted_cnts]

                regions[new_rid] = {
                    "id": new_rid,
                    "bbox": (bx, by, bw, bh),
                    "area": garea,
                    "centroid": (cx, cy),
                    "contours": adjusted_cnts,
                    "hierarchy": hier,
                    "is_gap": True,
                }
                new_rid += 1

    return labels, regions


class EditorController(QObject):
    # ---- signals the UI listens to -------------------------------------------------
    image_loaded = Signal(QImage)          # new document: canvas resets zoom to fit
    result_changed = Signal(QImage)        # edited composite: canvas keeps zoom/pan
    overlay_changed = Signal(object)       # QImage (transparent RGBA, same size) | None
    preview_changed = Signal(object, str)  # QImage | None, caption for the preview panel
    color_picked = Signal(QColor)          # eyedropper result
    trace_info = Signal(str)               # text for the re-trace window, e.g. "14 regions"
    status = Signal(str)                   # status-bar message

    def __init__(self):
        super().__init__()
        self.path: str | None = None
        self.original: QImage | None = None
        self.original_np: np.ndarray | None = None
        self.result: QImage | None = None
        self.tool = "select"
        self.options: dict[str, dict] = {}
        self.retrace_params = dict(DEFAULT_RETRACE)
        self.show_outlines = True

        # Segmentation state
        self.labels: np.ndarray | None = None
        self.regions: dict[int, dict] = {}
        self.selected_regions: set[int] = set()

        # Temporary state during live preview in RetraceDialog
        self.preview_labels: np.ndarray | None = None
        self.preview_regions: dict[int, dict] | None = None

        # Per-region styling descriptors
        self.region_styles: dict[int, dict] = {}

    # ---- file ---------------------------------------------------------------------
    def open_image(self, path: str):
        img = QImage(path)
        if img.isNull():
            self.status.emit(f"Could not open {path}")
            return
        self.path = path
        self.original = img.convertToFormat(QImage.Format_RGBA8888)
        self.original_np = qimage_to_numpy(self.original)
        self.result = self.original.copy()
        self.selected_regions.clear()
        self.region_styles.clear()

        self.image_loaded.emit(self.result)
        self.preview_changed.emit(None, "")
        self.overlay_changed.emit(None)
        self.status.emit(f"Opened {path}")

        # Run segmentation on the newly opened image
        self.retrace(self.retrace_params, preview=False)

    def export(self, kind: str, path: str):
        """kind: 'png' | 'svg' | 'selection_png'"""
        if self.result is None:
            return
        if kind == "png":
            ok = self.result.save(path)
            self.status.emit(f"Exported {path}" if ok else f"Failed to save {path}")
        else:
            # TODO(logic): SVG via contours; selection export from selected-region mask
            self.status.emit(f"'{kind}' export is not implemented yet")

    # ---- tracing ------------------------------------------------------------------
    def retrace(self, params: dict, preview: bool = False):
        """Run (or preview) region detection with `params` (see DEFAULT_RETRACE)."""
        if self.original_np is None:
            return

        if not preview:
            self.retrace_params = dict(params)

        labels, regions = run_segmentation(self.original_np, params)
        count = len(regions)
        self.trace_info.emit(
            f"{count} regions found  ·  mode: {params['mode']}, "
            f"connectivity: {params['connectivity']}-way"
        )

        if preview:
            self.preview_labels = labels
            self.preview_regions = regions
            ov = self.build_overlay(labels, selected=set(), show_outlines=True, is_preview=True)
            self.overlay_changed.emit(ov)
            self.status.emit(f"Re-trace preview: {count} regions found")
        else:
            self.labels = labels
            self.regions = regions
            self.preview_labels = None
            self.preview_regions = None
            self.selected_regions.clear()
            self.preview_changed.emit(None, "")
            ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
            self.overlay_changed.emit(ov)
            self.status.emit(f"Re-traced: {count} regions found")

    def retrace_cancel(self):
        """Dialog cancelled: restore the last committed trace."""
        self.retrace(self.retrace_params, preview=False)

    # ---- overlays -----------------------------------------------------------------
    def build_overlay(
        self,
        labels: np.ndarray | None,
        selected: set[int] | None = None,
        show_outlines: bool = True,
        is_preview: bool = False,
    ) -> QImage | None:
        """
        Build transparent RGBA overlay highlighting detected outlines and selected regions.
        """
        if labels is None or labels.size == 0:
            return None

        selected = selected or set()
        h, w = labels.shape
        overlay = np.zeros((h, w, 4), dtype=np.uint8)

        # Region boundary detection via 4-neighbor difference
        if is_preview or show_outlines or selected:
            pad = np.pad(labels, 1, mode="edge")
            diff = (
                (labels != pad[:-2, 1:-1])
                | (labels != pad[2:, 1:-1])
                | (labels != pad[1:-1, :-2])
                | (labels != pad[1:-1, 2:])
            )
            all_boundaries = diff & (labels > 0)

            if is_preview:
                # Vibrant blue/cyan outline for live re-trace preview
                overlay[all_boundaries] = [79, 140, 255, 230]
            elif show_outlines:
                # Subtle muted outline for all detected regions
                overlay[all_boundaries] = [154, 160, 170, 130]

        # Selected region highlight & crisp border
        if selected:
            valid_sel = [r for r in selected if r in self.regions]
            if valid_sel:
                sel_mask = np.isin(labels, valid_sel)
                # Blue tint fill
                overlay[sel_mask] = [79, 140, 255, 75]
                # High-contrast boundary
                pad_s = np.pad(sel_mask, 1, mode="edge")
                diff_s = (
                    (sel_mask != pad_s[:-2, 1:-1])
                    | (sel_mask != pad_s[2:, 1:-1])
                    | (sel_mask != pad_s[1:-1, :-2])
                    | (sel_mask != pad_s[1:-1, 2:])
                )
                overlay[diff_s & sel_mask] = [79, 140, 255, 255]

        # Return None if the overlay is completely transparent
        if not np.any(overlay[:, :, 3] > 0):
            return None

        return numpy_to_qimage(overlay)

    # ---- tools --------------------------------------------------------------------
    def set_tool(self, tool: str):
        self.tool = tool
        self.status.emit(f"Tool: {tool}")

    def set_options(self, tool: str, opts: dict):
        """Called on startup for every tool and again whenever an option changes."""
        self.options[tool] = opts
        # TODO(logic): live style re-rendering for active selection

    def on_click(self, x: int, y: int, modifiers):
        """Canvas click in image pixel coordinates."""
        if self.result is None or self.labels is None:
            return
        if not (0 <= x < self.labels.shape[1] and 0 <= y < self.labels.shape[0]):
            return

        shift = False
        alt = False
        if modifiers:
            if isinstance(modifiers, Qt.KeyboardModifiers):
                shift = bool(modifiers & Qt.ShiftModifier)
                alt = bool(modifiers & Qt.AltModifier)
            else:
                val = modifiers.value if hasattr(modifiers, "value") else int(modifiers)
                shift = bool(val & Qt.ShiftModifier.value)
                alt = bool(val & Qt.AltModifier.value)
        self.status.emit(
            f"{self.tool} click at ({x}, {y})"
            f"{' +shift' if shift else ''}{' +alt' if alt else ''}"
        )

        if self.tool == "eyedropper":
            src = self.original if self.options.get("eyedropper", {}).get("source") == "Original" else self.result
            self.color_picked.emit(src.pixelColor(x, y))
            return

        if self.tool == "select":
            rid = int(self.labels[y, x])
            mode = self.options.get("select", {}).get("Mode", "Replace")

            if rid == 0:
                # Clicked on background: clear selection unless shift/add mode
                if not (shift or mode == "Add"):
                    self.selected_regions.clear()
            else:
                if alt or mode == "Subtract":
                    self.selected_regions.discard(rid)
                elif shift or mode == "Add":
                    self.selected_regions.add(rid)
                else:  # Replace
                    self.selected_regions = {rid}

            ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
            self.overlay_changed.emit(ov)
            self._update_preview()
            return

        # TODO(logic): styling tools (fill, border, image, gradient, glow, reset, merge, split)

    def _update_preview(self):
        """Extract cropped preview and caption for the right panel."""
        if not self.selected_regions or self.original_np is None or self.labels is None:
            self.preview_changed.emit(None, "")
            return

        valid_sel = [r for r in self.selected_regions if r in self.regions]
        if not valid_sel:
            self.preview_changed.emit(None, "")
            return

        min_x = min(self.regions[r]["bbox"][0] for r in valid_sel)
        min_y = min(self.regions[r]["bbox"][1] for r in valid_sel)
        max_x = max(self.regions[r]["bbox"][0] + self.regions[r]["bbox"][2] for r in valid_sel)
        max_y = max(self.regions[r]["bbox"][1] + self.regions[r]["bbox"][3] for r in valid_sel)

        w = max_x - min_x
        h = max_y - min_y
        total_area = sum(self.regions[r]["area"] for r in valid_sel)

        sub_labels = self.labels[min_y:max_y, min_x:max_x]
        sub_mask = np.isin(sub_labels, valid_sel)

        crop = self.original_np[min_y:max_y, min_x:max_x].copy()
        crop[~sub_mask] = [0, 0, 0, 0]

        crop_qimg = numpy_to_qimage(crop)
        if len(valid_sel) == 1:
            rid = valid_sel[0]
            caption = f"Region #{rid} · {w}×{h} px ({total_area} px²)"
        else:
            caption = f"{len(valid_sel)} regions · {w}×{h} px ({total_area} px²)"

        self.preview_changed.emit(crop_qimg, caption)

    # ---- edit menu ----------------------------------------------------------------
    def undo(self):
        self.status.emit("Undo (not implemented)")

    def redo(self):
        self.status.emit("Redo (not implemented)")

    def select_all(self):
        if not self.regions or self.labels is None:
            return
        self.selected_regions = set(self.regions.keys())
        ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
        self.overlay_changed.emit(ov)
        self._update_preview()
        self.status.emit(f"Selected all ({len(self.selected_regions)} regions)")

    def deselect(self):
        self.selected_regions.clear()
        if self.labels is not None:
            ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
            self.overlay_changed.emit(ov)
        else:
            self.overlay_changed.emit(None)
        self.preview_changed.emit(None, "")
        self.status.emit("Deselected all")

    def set_show_outlines(self, on: bool):
        self.show_outlines = on
        if self.labels is not None:
            ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
            self.overlay_changed.emit(ov)

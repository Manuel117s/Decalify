"""
EditorController: the central image processing, segmentation, and styling engine.

The UI never touches pixels directly. It calls methods on EditorController
and responds to Qt signals.
"""
from __future__ import annotations

import copy
import cv2
import numpy as np

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygon,
    QRadialGradient,
)

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

_IMAGE_CACHE: dict[str, np.ndarray] = {}


# =============================================================================
# Format Conversion & Styling Helpers
# =============================================================================

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


def to_rgba(c) -> tuple[int, int, int, int]:
    """Convert a QColor or hex/CSS string to (R, G, B, A) integers 0-255."""
    if isinstance(c, QColor):
        return c.red(), c.green(), c.blue(), c.alpha()
    qc = QColor(c)
    return qc.red(), qc.green(), qc.blue(), qc.alpha()


def to_hex(c) -> str:
    """Convert a QColor or color string to a #RRGGBB hex string."""
    if isinstance(c, QColor):
        return c.name(QColor.HexRgb)
    qc = QColor(c)
    return qc.name(QColor.HexRgb)


def blend_pixels(base_rgb: np.ndarray, fill_rgb: np.ndarray, mode: str) -> np.ndarray:
    """Apply standard blend modes between two float/uint8 RGB arrays."""
    b = base_rgb.astype(np.float32) / 255.0
    f = fill_rgb.astype(np.float32) / 255.0
    if mode == "Multiply":
        res = b * f
    elif mode == "Screen":
        res = 1.0 - (1.0 - b) * (1.0 - f)
    elif mode == "Overlay":
        res = np.where(b < 0.5, 2.0 * b * f, 1.0 - 2.0 * (1.0 - b) * (1.0 - f))
    else:  # Normal
        res = f
    return np.clip(res * 255.0, 0, 255).astype(np.uint8)


def load_image_rgba(path: str) -> np.ndarray | None:
    """Load an image file and return cached RGBA NumPy array."""
    if not path:
        return None
    if path in _IMAGE_CACHE:
        return _IMAGE_CACHE[path]
    qimg = QImage(path)
    if qimg.isNull():
        return None
    arr = qimage_to_numpy(qimg)
    _IMAGE_CACHE[path] = arr
    return arr


def apply_image_fill(
    bw: int,
    bh: int,
    tex_img: np.ndarray,
    fit: str,
    scale: float,
    rotation: float,
) -> np.ndarray:
    """Transform and fit a texture image into a bounding box of size (bw, bh)."""
    tex = tex_img.copy()

    # Apply rotation
    if abs(rotation) > 0.01:
        th, tw = tex.shape[:2]
        center = (tw / 2.0, th / 2.0)
        M = cv2.getRotationMatrix2D(center, -rotation, 1.0)
        tex = cv2.warpAffine(tex, M, (tw, th), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

    th, tw = tex.shape[:2]
    if fit == "Stretch":
        t_w = max(1, int(bw * scale))
        t_h = max(1, int(bh * scale))
        resized = cv2.resize(tex, (t_w, t_h))
        padded = np.zeros((bh, bw, tex.shape[2]), dtype=tex.dtype)
        cw, ch = min(bw, t_w), min(bh, t_h)
        padded[:ch, :cw] = resized[:ch, :cw]
        return padded
    elif fit == "Cover":
        scale_cov = max(bw / tw, bh / th) * scale
        new_w, new_h = max(1, int(tw * scale_cov)), max(1, int(th * scale_cov))
        resized = cv2.resize(tex, (new_w, new_h))
        x0 = max(0, (new_w - bw) // 2)
        y0 = max(0, (new_h - bh) // 2)
        cropped = resized[y0:y0 + bh, x0:x0 + bw]
        if cropped.shape[0] < bh or cropped.shape[1] < bw:
            padded = np.zeros((bh, bw, tex.shape[2]), dtype=tex.dtype)
            padded[:cropped.shape[0], :cropped.shape[1]] = cropped
            return padded
        return cropped
    elif fit == "Contain":
        scale_con = min(bw / tw, bh / th) * scale
        new_w, new_h = max(1, int(tw * scale_con)), max(1, int(th * scale_con))
        resized = cv2.resize(tex, (new_w, new_h))
        padded = np.zeros((bh, bw, tex.shape[2]), dtype=tex.dtype)
        x0 = max(0, (bw - new_w) // 2)
        y0 = max(0, (bh - new_h) // 2)
        padded[y0:y0 + new_h, x0:x0 + new_w] = resized
        return padded
    elif fit == "Tile":
        t_w = max(1, int(tw * scale))
        t_h = max(1, int(th * scale))
        resized = cv2.resize(tex, (t_w, t_h))
        rep_y = int(np.ceil(bh / t_h))
        rep_x = int(np.ceil(bw / t_w))
        tiled = np.tile(resized, (rep_y, rep_x, 1))
        return tiled[:bh, :bw]

    return cv2.resize(tex, (bw, bh))


def render_gradient(bw: int, bh: int, c1, c2, gtype: str, angle: float) -> np.ndarray:
    """Render a linear or radial gradient into an array of size (bw, bh)."""
    qimg = QImage(bw, bh, QImage.Format_RGBA8888)
    p = QPainter(qimg)
    p1 = QColor(c1) if not isinstance(c1, QColor) else c1
    p2 = QColor(c2) if not isinstance(c2, QColor) else c2
    if gtype == "Radial":
        grad = QRadialGradient(QPointF(bw / 2.0, bh / 2.0), max(bw, bh) / 2.0)
    else:
        rad = np.radians(angle)
        diag = np.sqrt(bw**2 + bh**2) / 2.0
        cx, cy = bw / 2.0, bh / 2.0
        pt1 = QPointF(cx - diag * np.cos(rad), cy - diag * np.sin(rad))
        pt2 = QPointF(cx + diag * np.cos(rad), cy + diag * np.sin(rad))
        grad = QLinearGradient(pt1, pt2)
    grad.setColorAt(0, p1)
    grad.setColorAt(1, p2)
    p.fillRect(0, 0, bw, bh, grad)
    p.end()
    ptr = qimg.constBits()
    return np.frombuffer(ptr, dtype=np.uint8).reshape((bh, bw, 4)).copy()


def render_dashed_border(
    w: int,
    h: int,
    contours: list,
    r: int,
    g: int,
    b: int,
    width: int,
    style: str,
    corners: str,
    position: str,
    region_mask: np.ndarray,
) -> np.ndarray:
    """Stroke contours with Dashed or Dotted style using QPainter."""
    layer = QImage(w, h, QImage.Format_RGBA8888)
    layer.fill(Qt.transparent)
    p = QPainter(layer)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen_style = Qt.DashLine if style == "Dashed" else Qt.DotLine
    cap = Qt.RoundCap if corners == "Round" else Qt.SquareCap
    join = Qt.RoundJoin if corners == "Round" else Qt.MiterJoin
    pen = QPen(QColor(r, g, b, 255), width, pen_style, cap, join)
    p.setPen(pen)
    for cnt in contours:
        if len(cnt) < 2:
            continue
        pts = [QPoint(int(pt[0][0]), int(pt[0][1])) for pt in cnt]
        p.drawPolygon(QPolygon(pts))
    p.end()
    arr = qimage_to_numpy(layer)
    if position == "Inside":
        arr[region_mask == 0] = [0, 0, 0, 0]
    elif position == "Outside":
        arr[region_mask > 0] = [0, 0, 0, 0]
    return arr


def contour_to_svg_path(contours: list) -> str:
    """Convert a list of OpenCV contours to an SVG path d-string."""
    subpaths = []
    for c in contours:
        pts = c.reshape(-1, 2)
        if len(pts) < 3:
            continue
        d = f"M {pts[0][0]} {pts[0][1]} " + " ".join(f"L {p[0]} {p[1]}" for p in pts[1:]) + " Z"
        subpaths.append(d)
    return " ".join(subpaths)


def generate_svg(w: int, h: int, regions: dict, region_styles: dict, original_np: np.ndarray) -> str:
    """Generate high-quality vector SVG document representing all styled regions."""
    defs = []
    paths = []

    for rid, rdata in sorted(regions.items()):
        cnts = rdata.get("contours", [])
        if not cnts:
            continue
        d_str = contour_to_svg_path(cnts)
        if not d_str:
            continue

        styles = region_styles.get(rid, {})
        bx, by, bw, bh = rdata["bbox"]

        # Default fallback fill from original image
        sub = (original_np[by:by + bh, bx:bx + bw, 3] > 10)
        if np.any(sub):
            mean_col = np.mean(original_np[by:by + bh, bx:bx + bw, :3][sub], axis=0)
            fill_val = f"rgb({int(mean_col[0])},{int(mean_col[1])},{int(mean_col[2])})"
            fill_op = 1.0
        else:
            fill_val = "none"
            fill_op = 1.0

        filter_attr = ""
        stroke_attr = 'stroke="none"'

        # Glow filter
        if "glow" in styles:
            g = styles["glow"]
            g_col = to_hex(g.get("color", "#000000"))
            blur = int(g.get("blur", 12))
            dx = int(g.get("dx", 4))
            dy = int(g.get("dy", 4))
            g_op = float(g.get("opacity", 60)) / 100.0
            defs.append(f"""
    <filter id="glow_{rid}" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur in="SourceAlpha" stdDeviation="{blur / 2.0}" result="blur" />
      <feOffset in="blur" dx="{dx}" dy="{dy}" result="offset" />
      <feFlood flood-color="{g_col}" flood-opacity="{g_op}" result="color" />
      <feComposite in="color" in2="offset" operator="in" result="shadow" />
      <feMerge>
        <feMergeNode in="shadow" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>""")
            filter_attr = f' filter="url(#glow_{rid})"'

        # Gradient fill
        if "gradient" in styles:
            gr = styles["gradient"]
            c1_hex = to_hex(gr.get("c1", "#ff7a18"))
            c2_hex = to_hex(gr.get("c2", "#af002d"))
            gtype = gr.get("type", "Linear")
            angle = float(gr.get("angle", 90))
            gr_op = float(gr.get("opacity", 100)) / 100.0
            fill_op = gr_op

            if gtype == "Radial":
                defs.append(f"""
    <radialGradient id="grad_{rid}" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{c1_hex}" stop-opacity="{gr_op}" />
      <stop offset="100%" stop-color="{c2_hex}" stop-opacity="{gr_op}" />
    </radialGradient>""")
            else:
                rad = np.radians(angle)
                x1 = int(50 - 50 * np.cos(rad))
                y1 = int(50 - 50 * np.sin(rad))
                x2 = int(50 + 50 * np.cos(rad))
                y2 = int(50 + 50 * np.sin(rad))
                defs.append(f"""
    <linearGradient id="grad_{rid}" x1="{x1}%" y1="{y1}%" x2="{x2}%" y2="{y2}%">
      <stop offset="0%" stop-color="{c1_hex}" stop-opacity="{gr_op}" />
      <stop offset="100%" stop-color="{c2_hex}" stop-opacity="{gr_op}" />
    </linearGradient>""")
            fill_val = f"url(#grad_{rid})"

        # Solid fill
        elif "fill" in styles:
            f = styles["fill"]
            fill_val = to_hex(f.get("color", "#e63946"))
            fill_op = float(f.get("opacity", 100)) / 100.0

        # Border
        if "border" in styles:
            b = styles["border"]
            b_col = to_hex(b.get("color", "#000000"))
            b_w = int(b.get("width", 4))
            b_op = float(b.get("opacity", 100)) / 100.0
            b_style = b.get("style", "Solid")
            b_corn = "round" if b.get("corners", "Round") == "Round" else "miter"

            dash_attr = ""
            if b_style == "Dashed":
                dash_attr = f' stroke-dasharray="{b_w * 3} {b_w * 1.5}"'
            elif b_style == "Dotted":
                dash_attr = f' stroke-dasharray="{b_w} {b_w}"'

            stroke_attr = f'stroke="{b_col}" stroke-width="{b_w}" stroke-opacity="{b_op}" stroke-linejoin="{b_corn}" stroke-linecap="{b_corn}"{dash_attr}'

        path_tag = f'  <path id="region_{rid}" d="{d_str}" fill="{fill_val}" fill-opacity="{fill_op}" fill-rule="evenodd" {stroke_attr}{filter_attr} />'
        paths.append(path_tag)

    defs_str = f"  <defs>{''.join(defs)}\n  </defs>\n" if defs else ""
    paths_str = "\n".join(paths)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
{defs_str}  <g id="regions">
{paths_str}
  </g>
</svg>"""


# =============================================================================
# Segmentation Algorithm
# =============================================================================

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


# =============================================================================
# Main Controller
# =============================================================================

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
        self.result_np: np.ndarray | None = None
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

        # Per-region styling descriptors: {rid: {"fill": {...}, "border": {...}, ...}}
        self.region_styles: dict[int, dict] = {}

        # Split tool state
        self._split_start: tuple[int, int] | None = None

        # Undo / redo history
        self._history: list[dict] = []   # list of state snapshots
        self._history_index: int = -1    # current position in history
        self._MAX_HISTORY = 50           # limit memory usage

    # ---- file ---------------------------------------------------------------------
    def open_image(self, path: str):
        img = QImage(path)
        if img.isNull():
            self.status.emit(f"Could not open {path}")
            return
        self.path = path
        self.original = img.convertToFormat(QImage.Format_RGBA8888)
        self.original_np = qimage_to_numpy(self.original)
        self.result_np = self.original_np.copy()
        self.result = self.original.copy()
        self.selected_regions.clear()
        self.region_styles.clear()
        self._split_start = None
        self._history.clear()
        self._history_index = -1

        self.image_loaded.emit(self.result)
        self.preview_changed.emit(None, "")
        self.overlay_changed.emit(None)
        self.status.emit(f"Opened {path}")

        # Run segmentation on the newly opened image
        self.retrace(self.retrace_params, preview=False)

    def export(self, kind: str, path: str):
        """kind: 'png' | 'svg' | 'selection_png'"""
        if self.result is None or self.original_np is None:
            self.status.emit("Nothing to export")
            return

        if kind == "png":
            ok = self.result.save(path)
            self.status.emit(f"Exported PNG to {path}" if ok else f"Failed to save {path}")
        elif kind == "selection_png":
            if not self.selected_regions or self.labels is None:
                self.status.emit("No region selected to export")
                return
            valid_sel = [r for r in self.selected_regions if r in self.regions]
            if not valid_sel:
                self.status.emit("No region selected to export")
                return
            min_x = min(self.regions[r]["bbox"][0] for r in valid_sel)
            min_y = min(self.regions[r]["bbox"][1] for r in valid_sel)
            max_x = max(self.regions[r]["bbox"][0] + self.regions[r]["bbox"][2] for r in valid_sel)
            max_y = max(self.regions[r]["bbox"][1] + self.regions[r]["bbox"][3] for r in valid_sel)

            sub_labels = self.labels[min_y:max_y, min_x:max_x]
            sub_mask = np.isin(sub_labels, valid_sel)
            source_np = self.result_np if self.result_np is not None else self.original_np
            crop = source_np[min_y:max_y, min_x:max_x].copy()
            crop[~sub_mask] = [0, 0, 0, 0]
            sel_qimg = numpy_to_qimage(crop)
            ok = sel_qimg.save(path)
            self.status.emit(f"Exported selection to {path}" if ok else f"Failed to save {path}")
        elif kind == "svg":
            if not self.regions:
                self.status.emit("No regions to export as SVG")
                return
            w, h = self.original_np.shape[1], self.original_np.shape[0]
            svg_text = generate_svg(w, h, self.regions, self.region_styles, self.original_np)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(svg_text)
                self.status.emit(f"Exported vector SVG to {path}")
            except Exception as e:
                self.status.emit(f"Failed to export SVG: {e}")
        else:
            self.status.emit(f"'{kind}' export is not supported")

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
            self._split_start = None
            self.preview_changed.emit(None, "")
            self.render_composite()
            self.result_changed.emit(self.result)
            ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
            self.overlay_changed.emit(ov)
            self._push_history("Re-trace" if self._history else "Initial trace")
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
                overlay[all_boundaries] = [79, 140, 255, 230]
            elif show_outlines:
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

        if not np.any(overlay[:, :, 3] > 0):
            return None

        return numpy_to_qimage(overlay)

    # ---- composite rendering ------------------------------------------------------
    def render_composite(self):
        """Re-render composite image applying all active styles onto the original image."""
        if self.original_np is None or self.labels is None:
            return

        h, w = self.original_np.shape[:2]
        composite = self.original_np.copy()

        if not self.region_styles:
            self.result_np = composite
            self.result = numpy_to_qimage(self.result_np)
            return

        # -------------------------------------------------------------
        # Pass 1: Glow / Drop Shadows (behind foreground shapes)
        # -------------------------------------------------------------
        has_glow = any("glow" in st for st in self.region_styles.values())
        if has_glow:
            glow_layer = np.zeros((h, w, 4), dtype=np.float32)
            for rid, styles in self.region_styles.items():
                if "glow" not in styles or rid not in self.regions:
                    continue
                g_opts = styles["glow"]
                c = g_opts.get("color", "#000000")
                r, g, b, a = to_rgba(c)
                blur = int(g_opts.get("blur", 12))
                dx = int(g_opts.get("dx", 4))
                dy = int(g_opts.get("dy", 4))
                opacity = float(g_opts.get("opacity", 60)) / 100.0 * (a / 255.0)

                if opacity <= 0:
                    continue

                r_mask = (self.labels == rid).astype(np.uint8) * 255
                M = np.float32([[1, 0, dx], [0, 1, dy]])
                shifted = cv2.warpAffine(r_mask, M, (w, h), flags=cv2.INTER_NEAREST)
                if blur > 0:
                    k = blur * 2 + 1
                    shifted = cv2.GaussianBlur(shifted, (k, k), 0)

                g_alpha = (shifted.astype(np.float32) / 255.0) * opacity
                curr_a = glow_layer[:, :, 3]
                new_a = g_alpha + curr_a * (1.0 - g_alpha)
                for ch, col in enumerate([r, g, b]):
                    glow_layer[:, :, ch] = np.where(
                        new_a > 1e-6,
                        (col * g_alpha + glow_layer[:, :, ch] * curr_a * (1.0 - g_alpha)) / np.maximum(new_a, 1e-6),
                        0.0,
                    )
                glow_layer[:, :, 3] = new_a

            g_a = glow_layer[:, :, 3]
            if np.any(g_a > 0):
                bg_a = composite[:, :, 3].astype(np.float32) / 255.0
                bg_rgb = composite[:, :, :3].astype(np.float32)
                fg_rgb = glow_layer[:, :, :3]
                fg_a = g_a

                # Glow placed behind shapes
                out_a = bg_a + fg_a * (1.0 - bg_a)
                out_rgb = np.where(
                    out_a[:, :, None] > 1e-6,
                    (bg_rgb * bg_a[:, :, None] + fg_rgb * fg_a[:, :, None] * (1.0 - bg_a[:, :, None])) / np.maximum(out_a[:, :, None], 1e-6),
                    0.0,
                )
                composite[:, :, :3] = np.clip(out_rgb, 0, 255).astype(np.uint8)
                composite[:, :, 3] = np.clip(out_a * 255.0, 0, 255).astype(np.uint8)

        # -------------------------------------------------------------
        # Pass 2: Base Region Styles (Fill / Gradient / Image)
        # -------------------------------------------------------------
        for rid, styles in self.region_styles.items():
            if rid not in self.regions:
                continue
            r_mask = (self.labels == rid)
            if not np.any(r_mask):
                continue

            bx, by, bw, bh = self.regions[rid]["bbox"]
            sub_mask = (self.labels[by:by + bh, bx:bx + bw] == rid)

            # Solid Fill
            if "fill" in styles:
                f_opts = styles["fill"]
                r, g, b, a = to_rgba(f_opts.get("color", "#e63946"))
                opacity = float(f_opts.get("opacity", 100)) / 100.0 * (a / 255.0)
                blend = f_opts.get("blend", "Normal")

                if opacity > 0:
                    base_rgb = composite[by:by + bh, bx:bx + bw, :3][sub_mask].astype(np.float32)
                    fill_rgb = np.array([r, g, b], dtype=np.float32)
                    blended = blend_pixels(base_rgb, np.tile(fill_rgb, (len(base_rgb), 1)), blend).astype(np.float32)
                    res_rgb = np.clip(base_rgb * (1.0 - opacity) + blended * opacity, 0, 255).astype(np.uint8)
                    composite[by:by + bh, bx:bx + bw, :3][sub_mask] = res_rgb

            # Gradient Fill
            if "gradient" in styles:
                g_opts = styles["gradient"]
                c1 = g_opts.get("c1", "#ff7a18")
                c2 = g_opts.get("c2", "#af002d")
                gtype = g_opts.get("type", "Linear")
                angle = float(g_opts.get("angle", 90))
                opacity = float(g_opts.get("opacity", 100)) / 100.0

                if opacity > 0 and bw > 0 and bh > 0:
                    grad_img = render_gradient(bw, bh, c1, c2, gtype, angle)
                    base_rgb = composite[by:by + bh, bx:bx + bw, :3][sub_mask].astype(np.float32)
                    grad_rgb = grad_img[:, :, :3][sub_mask].astype(np.float32)
                    res_rgb = np.clip(base_rgb * (1.0 - opacity) + grad_rgb * opacity, 0, 255).astype(np.uint8)
                    composite[by:by + bh, bx:bx + bw, :3][sub_mask] = res_rgb

            # Image Fill
            if "image" in styles:
                i_opts = styles["image"]
                path = i_opts.get("path")
                if path:
                    fit = i_opts.get("fit", "Cover")
                    scale = float(i_opts.get("scale", 100)) / 100.0
                    rotation = float(i_opts.get("rotation", 0))
                    opacity = float(i_opts.get("opacity", 100)) / 100.0

                    if opacity > 0 and bw > 0 and bh > 0:
                        tex_img = load_image_rgba(path)
                        if tex_img is not None and tex_img.size > 0:
                            tex_res = apply_image_fill(bw, bh, tex_img, fit, scale, rotation)
                            base_rgb = composite[by:by + bh, bx:bx + bw, :3][sub_mask].astype(np.float32)
                            tex_rgb = tex_res[:, :, :3][sub_mask].astype(np.float32)
                            tex_a = (tex_res[:, :, 3][sub_mask].astype(np.float32) / 255.0) * opacity
                            res_rgb = np.clip(
                                base_rgb * (1.0 - tex_a[:, None]) + tex_rgb * tex_a[:, None],
                                0,
                                255,
                            ).astype(np.uint8)
                            composite[by:by + bh, bx:bx + bw, :3][sub_mask] = res_rgb

        # -------------------------------------------------------------
        # Pass 3: Borders (on top of shapes)
        # -------------------------------------------------------------
        for rid, styles in self.region_styles.items():
            if "border" not in styles or rid not in self.regions:
                continue
            b_opts = styles["border"]
            r, g, b, a = to_rgba(b_opts.get("color", "#000000"))
            width = int(b_opts.get("width", 4))
            pos = b_opts.get("position", "Outside")
            style = b_opts.get("style", "Solid")
            corners = b_opts.get("corners", "Round")
            opacity = float(b_opts.get("opacity", 100)) / 100.0 * (a / 255.0)

            if opacity <= 0 or width <= 0:
                continue

            r_mask = (self.labels == rid).astype(np.uint8) * 255

            if style in ("Dashed", "Dotted"):
                cnts = self.regions[rid].get("contours", [])
                if cnts:
                    stroke_layer = render_dashed_border(w, h, cnts, r, g, b, width, style, corners, pos, r_mask)
                    s_a = (stroke_layer[:, :, 3].astype(np.float32) / 255.0) * opacity
                    mask_s = s_a > 0
                    if np.any(mask_s):
                        bg_rgb = composite[mask_s, :3].astype(np.float32)
                        bg_a = composite[mask_s, 3].astype(np.float32) / 255.0
                        fg_rgb = stroke_layer[mask_s, :3].astype(np.float32)
                        fg_a = s_a[mask_s]

                        out_a = fg_a + bg_a * (1.0 - fg_a)
                        out_rgb = (fg_rgb * fg_a[:, None] + bg_rgb * bg_a[:, None] * (1.0 - fg_a[:, None])) / np.maximum(out_a[:, None], 1e-6)
                        composite[mask_s, :3] = np.clip(out_rgb, 0, 255).astype(np.uint8)
                        composite[mask_s, 3] = np.clip(out_a * 255.0, 0, 255).astype(np.uint8)
            else:
                morph_shape = cv2.MORPH_ELLIPSE if corners == "Round" else cv2.MORPH_RECT
                k = width * 2 + 1
                kernel = cv2.getStructuringElement(morph_shape, (k, k))

                if pos == "Outside":
                    dilated = cv2.dilate(r_mask, kernel)
                    ring = (dilated > 0) & (r_mask == 0)
                elif pos == "Inside":
                    eroded = cv2.erode(r_mask, kernel)
                    ring = (r_mask > 0) & (eroded == 0)
                else:  # Center
                    w_half = max(1, width // 2)
                    k_h = w_half * 2 + 1
                    k_half = cv2.getStructuringElement(morph_shape, (k_h, k_h))
                    dilated = cv2.dilate(r_mask, k_half)
                    eroded = cv2.erode(r_mask, k_half)
                    ring = (dilated > 0) & (eroded == 0)

                if np.any(ring):
                    bg_rgb = composite[ring, :3].astype(np.float32)
                    bg_a = composite[ring, 3].astype(np.float32) / 255.0
                    fg_rgb = np.array([r, g, b], dtype=np.float32)
                    fg_a = opacity

                    out_a = fg_a + bg_a * (1.0 - fg_a)
                    out_rgb = (fg_rgb * fg_a + bg_rgb * bg_a[:, None] * (1.0 - fg_a)) / np.maximum(out_a[:, None], 1e-6)
                    composite[ring, :3] = np.clip(out_rgb, 0, 255).astype(np.uint8)
                    composite[ring, 3] = np.clip(out_a * 255.0, 0, 255).astype(np.uint8)

        self.result_np = composite
        self.result = numpy_to_qimage(self.result_np)

    # ---- tools --------------------------------------------------------------------
    def set_tool(self, tool: str):
        self.tool = tool
        self._split_start = None
        self.status.emit(f"Tool: {tool}")

    def set_options(self, tool: str, opts: dict):
        """Called on startup for every tool and again whenever an option changes."""
        self.options[tool] = opts
        # Live styling update when dragging sliders or picking colors on active selection
        if self.tool == tool and self.selected_regions:
            if tool in ("fill", "border", "image", "gradient", "glow"):
                self.apply_tool_action(tool, opts)

    def apply_tool_action(self, tool: str, opts: dict):
        """Apply active tool styling or reset to selected regions."""
        if not self.selected_regions:
            return

        for r in self.selected_regions:
            if tool == "fill":
                self.region_styles.setdefault(r, {})["fill"] = dict(opts)
            elif tool == "border":
                self.region_styles.setdefault(r, {})["border"] = dict(opts)
            elif tool == "image":
                self.region_styles.setdefault(r, {})["image"] = dict(opts)
            elif tool == "gradient":
                self.region_styles.setdefault(r, {})["gradient"] = dict(opts)
            elif tool == "glow":
                self.region_styles.setdefault(r, {})["glow"] = dict(opts)
            elif tool == "reset":
                st = self.region_styles.get(r, {})
                if opts.get("fill", True):
                    st.pop("fill", None)
                if opts.get("border", True):
                    st.pop("border", None)
                if opts.get("image", True):
                    st.pop("image", None)
                if opts.get("effects", True):
                    st.pop("gradient", None)
                    st.pop("glow", None)

        self.render_composite()
        self.result_changed.emit(self.result)
        self._update_preview()
        self._push_history(f"Apply {tool}")
        self.status.emit(f"Applied {tool} to {len(self.selected_regions)} region(s)")

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

        rid = int(self.labels[y, x])

        # Select Tool
        if self.tool == "select":
            mode = self.options.get("select", {}).get("Mode", "Replace")
            if rid == 0:
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

        # Styling tools: fill, border, image, gradient, glow, reset
        if self.tool in ("fill", "border", "image", "gradient", "glow", "reset"):
            if rid > 0:
                if rid not in self.selected_regions and not (shift or alt):
                    self.selected_regions = {rid}
                    ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
                    self.overlay_changed.emit(ov)
                self.apply_tool_action(self.tool, self.options.get(self.tool, {}))
            return

        # Merge Tool
        if self.tool == "merge":
            if shift:
                if rid > 0:
                    self.selected_regions.add(rid)
                    ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
                    self.overlay_changed.emit(ov)
                    self._update_preview()
                    self.status.emit(f"Selected {len(self.selected_regions)} regions. Click again without Shift to merge.")
            else:
                if len(self.selected_regions) >= 2:
                    fill_gaps = bool(self.options.get("merge", {}).get("fill_gaps", False))
                    self.merge_selected_regions(fill_gaps=fill_gaps)
                elif rid > 0:
                    self.selected_regions.add(rid)
                    ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
                    self.overlay_changed.emit(ov)
                    self._update_preview()
                    self.status.emit(f"Region #{rid} selected. Shift-click more regions, then click to merge.")
            return

        # Split Tool
        if self.tool == "split":
            cut_w = int(self.options.get("split", {}).get("cut", 2))
            if self._split_start is None:
                self._split_start = (x, y)
                self.status.emit(f"Cut line started at ({x}, {y}). Click the second point across the shape to cut.")
                self._show_split_marker(x, y)
            else:
                p1 = self._split_start
                p2 = (x, y)
                self._split_start = None
                self.split_region_at_line(p1, p2, cut_width=cut_w)
            return

    def _show_split_marker(self, x: int, y: int):
        """Draw an interactive crosshair/point on the overlay at the first cut point."""
        ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
        if ov is None and self.labels is not None:
            ov = numpy_to_qimage(np.zeros((self.labels.shape[0], self.labels.shape[1], 4), dtype=np.uint8))
        if ov is not None:
            p = QPainter(ov)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(QPen(QColor(255, 60, 60, 240), 2))
            p.drawLine(x - 8, y, x + 8, y)
            p.drawLine(x, y - 8, x, y + 8)
            p.setBrush(QColor(255, 60, 60, 80))
            p.drawEllipse(QPoint(x, y), 6, 6)
            p.end()
            self.overlay_changed.emit(ov)

    def on_rect_select(self, x0: int, y0: int, x1: int, y1: int, modifiers):
        """Handle drag-selection rectangle on the canvas."""
        if self.result is None or self.labels is None:
            return
        if self.tool != "select":
            self.on_click(x0, y0, modifiers)
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

        h, w = self.labels.shape[:2]
        min_x = max(0, min(x0, x1))
        max_x = min(w, max(x0, x1) + 1)
        min_y = max(0, min(y0, y1))
        max_y = min(h, max(y0, y1) + 1)

        if min_x >= max_x or min_y >= max_y:
            return

        sub = self.labels[min_y:max_y, min_x:max_x]
        intersected = set(np.unique(sub)) - {0}
        intersected = {int(r) for r in intersected if r in self.regions}

        mode = self.options.get("select", {}).get("Mode", "Replace")
        if alt or mode == "Subtract":
            self.selected_regions.difference_update(intersected)
        elif shift or mode == "Add":
            self.selected_regions.update(intersected)
        else:  # Replace
            self.selected_regions = set(intersected)

        ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
        self.overlay_changed.emit(ov)
        self._update_preview()
        self.status.emit(f"Drag selected {len(self.selected_regions)} region(s)")

    # ---- geometry operations (merge & split) --------------------------------------
    def merge_selected_regions(self, fill_gaps: bool = False):
        """Combine multiple selected regions into a single unified region."""
        if len(self.selected_regions) < 2 or self.labels is None:
            self.status.emit("Select at least 2 regions to merge")
            return

        valid_sel = sorted([r for r in self.selected_regions if r in self.regions])
        if len(valid_sel) < 2:
            return

        target_rid = valid_sel[0]
        absorbed_rids = valid_sel[1:]

        union_mask = np.isin(self.labels, valid_sel)

        if fill_gaps:
            u8_mask = union_mask.astype(np.uint8) * 255
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
            closed = cv2.morphologyEx(u8_mask, cv2.MORPH_CLOSE, k)
            other_regions = (self.labels > 0) & (~union_mask)
            fill_mask = (closed > 0) & (~other_regions)
            self.labels[fill_mask] = target_rid
        else:
            self.labels[union_mask] = target_rid

        self._recompute_region_geom(target_rid)

        # Remove absorbed regions
        for r in absorbed_rids:
            self.regions.pop(r, None)
            self.region_styles.pop(r, None)

        self.selected_regions = {target_rid}
        self.render_composite()
        self.result_changed.emit(self.result)
        ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
        self.overlay_changed.emit(ov)
        self._update_preview()
        self._push_history(f"Merge {len(valid_sel)} regions")
        self.status.emit(f"Merged {len(valid_sel)} regions into Region #{target_rid}")

    def split_region_at_line(self, p1: tuple[int, int], p2: tuple[int, int], cut_width: int = 2):
        """Carve a cut line between p1 and p2 across shapes, splitting into new components."""
        if self.labels is None:
            return

        h, w = self.labels.shape[:2]
        line_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.line(line_mask, p1, p2, 255, thickness=max(1, cut_width))

        cut_pixels = (line_mask > 0) & (self.labels > 0)
        intersected_rids = np.unique(self.labels[cut_pixels])

        if len(intersected_rids) == 0:
            self.status.emit(f"Cut from {p1} to {p2} did not cross any region")
            ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
            self.overlay_changed.emit(ov)
            return

        target_rid = int(intersected_rids[0])
        t_mask = (self.labels == target_rid) & (line_mask == 0)
        conn = 4 if self.retrace_params.get("connectivity", 8) == 4 else 8
        n_comp, raw_comp, stats, centroids = cv2.connectedComponentsWithStats(
            t_mask.astype(np.uint8) * 255,
            connectivity=conn,
        )

        if n_comp - 1 <= 1:
            self.labels[(self.labels == target_rid) & (line_mask > 0)] = 0
            self._recompute_region_geom(target_rid)
            self.status.emit(f"Carved line across Region #{target_rid}")
        else:
            self.labels[self.labels == target_rid] = 0
            new_ids = []
            next_avail_id = max(self.regions.keys()) + 1 if self.regions else 1

            # Assign first component back to target_rid
            self.labels[raw_comp == 1] = target_rid
            self._recompute_region_geom(target_rid)
            new_ids.append(target_rid)

            # Assign new IDs to remaining components
            for c in range(2, n_comp):
                c_area = int(stats[c, cv2.CC_STAT_AREA])
                if c_area >= self.retrace_params.get("min_area", 4):
                    new_rid = next_avail_id
                    next_avail_id += 1
                    self.labels[raw_comp == c] = new_rid
                    self._recompute_region_geom(new_rid)
                    new_ids.append(new_rid)

            self.selected_regions = set(new_ids)
            self.status.emit(f"Split Region #{target_rid} into {len(new_ids)} separate regions!")

        self.render_composite()
        self.result_changed.emit(self.result)
        ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
        self.overlay_changed.emit(ov)
        self._update_preview()
        self._push_history(f"Split Region #{target_rid}")

    def _recompute_region_geom(self, rid: int):
        """Recompute bounding box, area, centroid, and contours for a modified region."""
        reg_mask = (self.labels == rid)
        if not np.any(reg_mask):
            self.regions.pop(rid, None)
            self.region_styles.pop(rid, None)
            return

        coords = np.argwhere(reg_mask)
        min_y, min_x = coords.min(axis=0)
        max_y, max_x = coords.max(axis=0)
        bw = int(max_x - min_x + 1)
        bh = int(max_y - min_y + 1)
        bx, by = int(min_x), int(min_y)
        area = int(np.sum(reg_mask))
        cy = float(np.mean(coords[:, 0]))
        cx = float(np.mean(coords[:, 1]))

        sub = (self.labels[by:by + bh, bx:bx + bw] == rid).astype(np.uint8) * 255
        sub_pad = np.pad(sub, 1, mode="constant")
        cnts, hier = cv2.findContours(sub_pad, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        adj = [c + np.array([[[bx - 1, by - 1]]], dtype=np.int32) for c in cnts]
        simplify = float(self.retrace_params.get("simplify", 0.8))
        if simplify > 0:
            adj = [cv2.approxPolyDP(c, simplify, closed=True) for c in adj]

        self.regions[rid] = {
            "id": rid,
            "bbox": (bx, by, bw, bh),
            "area": area,
            "centroid": (cx, cy),
            "contours": adj,
            "hierarchy": hier,
            "is_gap": False,
        }

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

        source_np = self.result_np if self.result_np is not None else self.original_np
        crop = source_np[min_y:max_y, min_x:max_x].copy()
        crop[~sub_mask] = [0, 0, 0, 0]

        crop_qimg = numpy_to_qimage(crop)
        if len(valid_sel) == 1:
            rid = valid_sel[0]
            caption = f"Region #{rid} · {w}×{h} px ({total_area} px²)"
        else:
            caption = f"{len(valid_sel)} regions · {w}×{h} px ({total_area} px²)"

        self.preview_changed.emit(crop_qimg, caption)

    # ---- history (undo / redo) ---------------------------------------------------
    def _push_history(self, description: str = ""):
        if self.labels is None:
            return
        if self._history_index < len(self._history) - 1:
            self._history = self._history[: self._history_index + 1]

        snapshot = {
            "labels": self.labels.copy(),
            "regions": copy.deepcopy(self.regions),
            "region_styles": copy.deepcopy(self.region_styles),
            "selected_regions": set(self.selected_regions),
            "retrace_params": dict(self.retrace_params),
            "description": description,
        }
        self._history.append(snapshot)
        if len(self._history) > self._MAX_HISTORY:
            self._history.pop(0)
        self._history_index = len(self._history) - 1

    def _restore_snapshot(self, snapshot: dict):
        self.labels = snapshot["labels"].copy()
        self.regions = copy.deepcopy(snapshot["regions"])
        self.region_styles = copy.deepcopy(snapshot["region_styles"])
        self.selected_regions = set(snapshot["selected_regions"])
        if "retrace_params" in snapshot:
            self.retrace_params = dict(snapshot["retrace_params"])
        self._split_start = None
        self.render_composite()
        self.result_changed.emit(self.result)
        ov = self.build_overlay(self.labels, self.selected_regions, self.show_outlines)
        self.overlay_changed.emit(ov)
        self._update_preview()

    def undo(self):
        if self._history_index > 0:
            cur_desc = self._history[self._history_index].get("description", "")
            self._history_index -= 1
            self._restore_snapshot(self._history[self._history_index])
            self.status.emit(f"Undo: {cur_desc}" if cur_desc else "Undo")
        else:
            self.status.emit("Nothing to undo")

    def redo(self):
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            desc = self._history[self._history_index].get("description", "")
            self._restore_snapshot(self._history[self._history_index])
            self.status.emit(f"Redo: {desc}" if desc else "Redo")
        else:
            self.status.emit("Nothing to redo")

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
        self._split_start = None
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

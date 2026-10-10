# Decalify — Project Understanding, Plan & Progress Log

> **Project Tracker**: This document tracks architectural understanding, implementation status, detailed roadmap, and an ongoing log of advancements made to Decalify. It is updated as changes and features are completed.

---

## 1. Project Overview & Architecture

**Decalify** (Region Editor) is an interactive desktop image segmentation and decal/graphic styling tool built in Python using **PySide6 (Qt)**, **OpenCV (`cv2`)**, and **NumPy**.

### Primary Workflow
1. **Load Image:** Input PNG with transparency or raster graphic/mask.
2. **Segmentation & Tracing:** Analyze image pixels into discrete labeled regions using thresholding and connected components (`cv2.connectedComponentsWithStats`).
3. **Region Selection:** Click to select regions with single-select, additive (Shift+Click), or subtractive (Alt+Click) modes.
4. **Restyling Pipeline:** Apply layered non-destructive styles to individual or grouped regions (Fill, Border/Outlines, Texture/Image Fill, Eyedropper, Gradients, Glow/Drop Shadows).
5. **Geometry Operations:** Merge regions or split touching shapes.
6. **Export:** Render composite images to PNG, extract selected regions to transparent PNG, or vectorize contours to SVG paths.

### Architectural Separation (MVC)
The application strictly isolates UI and image processing logic:
- **UI (`ui/`)**: Pure presentation layer. Displays canvas, tool panels, property sliders, and dialogs. Emits signals on user interactions (clicks, parameter changes) and renders `QImage` results provided by the controller. Never manipulates raw pixel arrays.
- **Controller (`controller.py`)**: The central engine. Maintains the image state, OpenCV arrays, segmentation label matrices, per-region style records, selection sets, history stack (Undo/Redo), and export routines. Communicates with the UI exclusively through Qt signals.

---

## 2. Current Implementation Status

### UI Shell (100% Complete)
- **`main.py`**: App entry point, Fusion styling, CLI image argument handling.
- **`ui/main_window.py`**: 3-panel horizontal splitter layout, full menus (File, Edit, View, Options, About), status bar with coordinate and zoom readouts, signal wiring.
- **`ui/canvas.py`**: `QGraphicsView` with smooth zoom, pan (middle-click / Space+drag), pixel coordinate tracking, checkerboard background, overlay rendering, drag-and-drop loading.
- **`ui/tool_panel.py`**: Left panel featuring 10 tools (`select`, `fill`, `border`, `image`, `eyedropper`, `gradient`, `glow`, `reset`, `merge`, `split`) with dynamically generated option forms.
- **`ui/right_panel.py`**: Right panel featuring selection checkerboard preview, dimension/area caption, Import button, Re-trace button, and Export menu.
- **`ui/retrace_dialog.py`**: Modal dialog for granular tuning of detection parameters with live preview.
- **`ui/widgets.py`**: Custom components (`ColorButton`, `LabeledSlider`, `ImagePicker`, `PreviewView`).
- **`ui/icons.py`**: Procedurally rendered vector icons.
- **`ui/theme.py`**: Dark mode Qt stylesheet.

### Core Logic (`controller.py`) (In Progress)
- **Image Import & Conversion**: Completed — fast `QImage` ↔ NumPy RGBA conversion (`qimage_to_numpy`, `numpy_to_qimage`).
- **Tracing / Segmentation**: Completed — OpenCV connected components, all 4 detection modes, filtering, morphology, gap and hole processing (`run_segmentation`).
- **Selection System**: Completed — label map lookup `labels[y, x]`, multi-selection, visual outline overlays, and cropped preview extraction.
- **Styling Engine**: Completed — non-destructive multi-pass rendering pipeline (Fill with blend modes, Outside/Inside/Center Solid & Dashed/Dotted borders, Texture Image Fill, Linear & Radial Gradients, Drop Shadow / Glow, Reset, Eyedropper).
- **Advanced Tools**: In Progress / Next — Merge, Split.
- **Undo / Redo**: Stubbed.
- **Export**: PNG and Selection PNG completed — SVG contour vectorizer next.

---

## 3. Implementation Plan & Milestones

### Phase 1: Core Foundation & Segmentation Engine
- [x] **1.1 NumPy ↔ QImage Bridge**: High-performance conversions between Qt `QImage` (ARGB32/RGBA8888) and NumPy arrays (BGRA / RGBA / Grayscale).
- [x] **1.2 Retrace / Segmentation Algorithm**:
  - Implement detection modes: `auto` (alpha channel detection with Otsu fallback), `alpha`, `threshold` (fixed threshold with invert option), and `color` distance.
  - Apply preprocessing: Gaussian/median `blur`, morphological closing `close_gaps`.
  - Run `cv2.connectedComponentsWithStats` with 4-way or 8-way `connectivity`.
  - Filter blobs by `min_area`.
  - Handle background gaps (`include_gaps`) and hole preservation (`keep_holes`).
  - Store segmentation state: `labels` matrix, bounding boxes, region areas, and contours.
  - Emit real trace information to status bar and retrace dialog.

### Phase 2: Selection System & Visual Feedback
- [x] **2.1 Region Selection Logic**:
  - Map click coordinates `(x, y)` to region ID via `labels[y, x]`.
  - Support selection modes: Replace, Add (or Shift+Click), Subtract (or Alt+Click).
  - Background click handling (`rid == 0`) and `select_all()` / `deselect()`.
- [x] **2.2 Visual Overlays & Outlines**:
  - Generate selection highlight mask (tinted semi-transparent fill + boundary contour) for active regions.
  - Support global region outline display toggle (`set_show_outlines`).
- [x] **2.3 Selection Preview & Metadata**:
  - Extract cropped region bounded alpha image for the right panel `PreviewView`.
  - Display informative caption (dimensions, pixel area, region ID count).

### Phase 3: Per-Region Styling & Rendering Engine
- [x] **3.1 Non-Destructive Style Model**:
  - Maintain a data structure storing per-region styles (Fill, Border, Image Fill, Gradient, Glow).
  - Create a composite renderer that paints original base image + region styling into `self.result`.
  - Live preview update when options change in `set_options()`.
- [x] **3.2 Tool Implementations**:
  - **Fill Tool**: Solid color with opacity, blend modes (Normal, Multiply, Screen, Overlay), and antialiased edge smoothing.
  - **Border Tool**: Morphological ring generation (`dilate - mask` for Outside, `mask - erode` for Inside, centered) with custom width, opacity, color, and dash styles.
  - **Image Fill Tool**: Scale, rotate, and map an external image into region bounding boxes (`Cover`, `Stretch`, `Contain`, `Tile`), clipped to the region mask.
  - **Gradient Tool**: Linear and radial gradients across the region bounding box with angle, colors, and opacity.
  - **Glow / Shadow Tool**: Dilated Gaussian-blurred mask with X/Y offset and color opacity.
  - **Eyedropper Tool**: Sample pixel color from Result or Original at click coordinates and emit to target color swatch.
  - **Reset Tool**: Selectively clear fill, border, image, or effect styles for active regions.

### Phase 4: Advanced Tools & Geometry Operations
- [ ] **4.1 Merge Tool**: Combine multiple selected region IDs into a unified region, with optional gap filling.
- [ ] **4.2 Split Tool**: Partition a shape along a line or cut path into separate connected components.

### Phase 5: Undo / Redo & Export Systems
- [ ] **5.1 Undo / Redo History**:
  - Implement snapshot or delta history stack for region styling, merges, and splits.
  - Hook up keyboard shortcuts (`Ctrl+Z`, `Ctrl+Y`) and Edit menu actions.
- [ ] **5.2 Export Handlers**:
  - **PNG**: Export complete styled composite.
  - **Selection PNG**: Export selected region(s) on transparent background (cropped or canvas-sized).
  - **SVG Vector Export**: Convert region contours via `cv2.findContours` to SVG XML path elements with fills and strokes.

---

## 4. Advancements & Change Log

| Date | Milestone / Change | Details |
|---|---|---|
| 2026-10-09 | **Codebase Review & Project Documentation** | Completed full audit of existing PySide6 UI and controller stubs. Initialized `PROJECT_PROGRESS.md` with system architecture, component breakdown, and step-by-step implementation roadmap. |
| 2026-10-09 | **Phase 1 & Phase 2: Segmentation Engine & Selection System** | Implemented NumPy ↔ QImage bridge (`qimage_to_numpy`, `numpy_to_qimage`), OpenCV connected components segmentation (`auto`, `alpha`, `threshold`, `color` modes, blur, morphology closing, holes, gaps, and area filtering), live re-trace preview and cancellation, vectorized outline generation, multi-region selection (Replace, Add, Subtract), and right panel cropped preview with metadata. Verified with automated controller & GUI integration tests. |
| 2026-10-10 | **Phase 3: Per-Region Styling & Rendering Engine** | Implemented non-destructive styling pipeline: Solid Fill with blend modes (Normal, Multiply, Screen, Overlay), Outside/Center/Inside Solid and Dashed/Dotted borders, Texture Image Fill (Cover, Stretch, Contain, Tile with rotation/scale), Linear & Radial Gradients, Drop Shadow / Outer Glow, live styling updates on option change, Reset tool, Eyedropper integration, and Selection PNG export. Verified with automated unit and GUI integration tests. |

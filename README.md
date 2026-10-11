# Decalify

<div align="center">

**Precision Image Segmentation & Decal Styling Workstation**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-PySide6%20(Qt)-41cd52.svg)](https://wiki.qt.io/Qt_for_Python)
[![Computer Vision](https://img.shields.io/badge/Engine-OpenCV%20%7C%20NumPy-5c3ee8.svg)](https://opencv.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

*Analyze, isolate, re-texture, stroke, gradient, and vectorize parts of any graphic non-destructively.*

</div>

---

## 🌟 Overview

**Decalify** is an interactive desktop workstation designed for designers, sticker makers, decal artists, and game asset creators. It segments raster graphics (PNGs, transparent decals, or flattened artwork) into discrete, individually styleable regions using computer vision algorithms, and lets you restyle or vectorize them with surgical precision.

Built on **PySide6 (Qt)**, **OpenCV**, and **NumPy** under a strict Model-View-Controller (MVC) architecture, the canvas provides real-time hardware-accelerated feedback while preserving the original image.

---

## ✨ Features

### 🔍 Intelligent Auto-Segmentation & Re-Tracing
- **4 Detection Modes**:
  - `Auto`: Automatic alpha channel detection with Otsu intensity fallback.
  - `Alpha`: Isolate non-transparent elements via alpha thresholding.
  - `Threshold`: Fixed luminosity binarization with invert toggle.
  - `Color`: Multi-channel color distance clustering for flat graphics.
- **Morphological Tuning**: Gaussian blur, gap closing (`cv2.morphologyEx`), hole preservation, and small artifact filtering (`min_area`).
- **Interactive Live Re-trace Modal**: Tune parameters with real-time outline previews before committing.

### 🎯 Surgical Selection & Batch Marquee
- **Single-Click Selection**: Direct pixel-to-region index mapping via `labels[y, x]`.
- **Modifiers**:
  - `Shift + Click`: Additive selection.
  - `Alt + Click`: Subtractive selection.
- **Rubber-Band Drag Selection**: Drag an interactive marquee box across the canvas to batch-select all intersected regions.
- **Select All & Deselect**: One-key shortcuts (`Ctrl+A`, `Ctrl+D`).

### 🎨 Non-Destructive Multi-Pass Styling Pipeline
Each region can carry multiple independent, layerable styling descriptors:
- **Solid Fill**: 32-bit RGBA color picker with blend modes (*Normal*, *Multiply*, *Screen*, *Overlay*) and opacity control.
- **Outlines & Borders**: Morphological ring expansion with placement options:
  - `Outside`: Expands outward without clipping internal pixels.
  - `Center`: Straddles the boundary.
  - `Inside`: Shrinks inward along the contour.
  - Styles: *Solid*, *Dashed*, and *Dotted* lines.
- **Texture / Image Fill**: Map external textures or photos into region masks with *Cover*, *Stretch*, *Contain*, and *Tile* mapping modes, plus angle rotation and scaling.
- **Gradients**: Linear (adjustable angle) and Radial gradients with dual-stop color selection and opacity blending.
- **Glow & Drop Shadows**: Directional Gaussian-blurred shadow/glow underlayers with custom blur radius and X/Y offsets.
- **Eyedropper**: Sample color directly from either the raw source graphic or the active composite.
- **Selective Reset**: Clear fills, borders, textures, or effects individually or all at once.

### ✂️ Advanced Geometry Operations
- **Merge Tool**: Fuse multiple disjoint or touching regions into a single unified region, with optional morphological gap filling.
- **Split Tool**: Slice across complex shapes using an interactive 2-point cutting line with visual crosshair guidelines and connected components partitioning.

### ⏪ Undo / Redo History
- Full snapshot history stack capturing label matrices, geometry contours, per-region style dicts, and trace settings.
- Wired to standard shortcuts (`Ctrl+Z`, `Ctrl+Y`) and Edit menu actions with memory bounding.

### 💾 Multi-Format Export
- **Full PNG Composite**: Export high-resolution rendered raster results.
- **Transparent Selection PNG**: Export only the currently selected regions cropped to their bounding box with alpha transparency preserved.
- **Scalable Vector SVG**: Vectorize region contours into clean SVG `<path>` elements (`fill-rule="evenodd"`) with embedded gradients, drop shadow filters, and strokes.

---

## 🖥️ User Interface Layout

```
+-----------------------------------------------------------------------------------+
|  File   Edit   View   Options   About                                             |
+---------------------+---------------------------------------+---------------------+
|  TOOL PANEL         |  CANVAS                               |  INSPECTOR & EXPORT |
|                     |                                       |                     |
|  [Select]   [Fill]  |  * Pan: Middle-drag or Space+drag    |  [Selection Preview]|
|  [Border]   [Image] |  * Zoom: Mouse Wheel                 |  Region #4          |
|  [Eyedrop]  [Grad]  |  * Marquee: Left-drag box             |  240x180 px (43KB)  |
|  [Glow]     [Reset] |  * Click: Target region               |                     |
|  [Merge]    [Split] |                                       |  [ Import Image… ]  |
|  -----------------  |  Checkerboard transparent background  |  [ Re-trace…     ]  |
|  Dynamic Tool       |  Vibrant selection outline overlays   |  [ Export PNG    ]  |
|  Properties &       |                                       |  [ Export SVG    ]  |
|  Sliders            |                                       |  [ Export Sel    ]  |
+---------------------+---------------------------------------+---------------------+
| Status bar: x 412  y 280  |  1024 × 768 px  |  150%  |  [Fit]  [100%]             |
+-----------------------------------------------------------------------------------+
```

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.10+**
- Windows, macOS, or Linux

### Installation (from Source)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/decalify.git
   cd decalify
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch Decalify:**
   ```bash
   python main.py
   # Or directly open an image:
   python main.py shape.png
   ```

---

## 📦 Standalone Executable (.exe)

For Windows users who want to run Decalify without installing Python, standalone release builds are provided.

### Downloading Pre-built Release
Download the latest `Decalify.exe` from the [Releases](https://github.com/Manuel117s/Decalify/releases) page and run it directly.

### Building the Executable Yourself
To build a single-file executable using PyInstaller:

```bash
# Activate your virtual environment
.venv\Scripts\activate

# Build Decalify.exe
pyinstaller --noconfirm --onedir --windowed --name "Decalify" main.py
# Or single-file portable binary:
pyinstaller --noconfirm --onefile --windowed --name "Decalify" main.py
```

The resulting binary will be generated inside the `dist/` directory:
```
dist/Decalify.exe
```

---

## ⌨️ Keyboard Shortcuts & Controls

| Action | Shortcut / Gesture |
|---|---|
| **Open / Import Image** | `Ctrl + O` |
| **Export PNG** | `Ctrl + E` |
| **Export Vector SVG** | `Ctrl + Shift + E` |
| **Undo** | `Ctrl + Z` |
| **Redo** | `Ctrl + Y` |
| **Select All Regions** | `Ctrl + A` |
| **Deselect All** | `Ctrl + D` |
| **Re-trace Settings** | `Ctrl + T` |
| **Zoom In / Out** | `Ctrl + +` / `Ctrl + -` (or `Mouse Wheel`) |
| **Fit to Window** | `Ctrl + 0` |
| **Actual Size (100%)** | `Ctrl + 1` |
| **Pan Canvas** | `Middle-click + Drag` or `Space + Left-click + Drag` |
| **Additive Selection** | `Shift + Left-click` (or Shift + Drag) |
| **Subtractive Selection**| `Alt + Left-click` (or Alt + Drag) |
| **Marquee Selection** | `Left-click + Drag` (Rubber band) |

---

## 🏗️ Architecture & Technology Stack

Decalify strictly isolates presentation from computation:

```
┌─────────────────────────────────────────────────────────────┐
│                       Presentation Layer                    │
│   ui/main_window.py   ui/canvas.py       ui/tool_panel.py   │
│   ui/right_panel.py   ui/retrace_dialog  ui/widgets.py      │
└──────────────────────────────┬──────────────────────────────┘
                               │ Qt Signals & Slots
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                        Engine Core                          │
│                      controller.py                          │
│  * OpenCV (Segmentation, Morphology, Connected Components)   │
│  * NumPy (Mask arrays, 4-way slicing, composite operations) │
│  * QPainter / QImage (Vector SVG rendering, alpha blits)    │
│  * History Stack (Undo / Redo state serialization)          │
└─────────────────────────────────────────────────────────────┘
```

- **PySide6**: High-performance Qt 6 bindings with custom dark palette stylesheet (`ui/theme.py`).
- **OpenCV (`cv2`)**: Connected components analysis, morphological ring dilation/erosion, edge closing, contour hierarchy extraction.
- **NumPy**: Fast vectorized array arithmetic, boolean mask slicing, and compositing.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

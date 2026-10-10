# Decalify

Run:

    pip install -r requirements.txt
    python main.py            # or: python main.py shape.png

Your logic goes in `controller.py` (search for `TODO(logic)`). The UI never touches pixels.

| File | Role |
|---|---|
| `controller.py` | Signals to the UI + methods the UI calls (open, click, options, retrace, export, undo) |
| `ui/main_window.py` | Menus, 3-panel layout, status bar, all signal wiring |
| `ui/tool_panel.py` | Left panel: tool grid + per-tool options (`SPECS` dict: add a tool or option in one line) |
| `ui/right_panel.py` | Selection preview, Import / Re-trace / Export |
| `ui/retrace_dialog.py` | Re-trace settings window (`DEFAULT_RETRACE` params, live preview) |
| `ui/canvas.py` | Zoom/pan canvas: wheel = zoom, middle-drag or Space+drag = pan, click -> `(x, y)` pixel |
| `ui/theme.py` | Dark stylesheet, edit `PALETTE` to recolor |

Controller -> UI signals: `image_loaded`, `result_changed`, `overlay_changed`, `preview_changed`, `color_picked`, `trace_info`, `status`.

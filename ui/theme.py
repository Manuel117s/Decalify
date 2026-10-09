"""Dark theme (Qt stylesheet). Tweak PALETTE to restyle the whole app."""

PALETTE = {
    "bg": "#1b1c1f",
    "panel": "#25272b",
    "panel2": "#2f3238",
    "border": "#3d4148",
    "text": "#e6e8ec",
    "muted": "#9aa0aa",
    "accent": "#4f8cff",
    "accent_hover": "#6a9fff",
    "canvas": "#17181a",
}

_QSS = """
QWidget { background: @panel; color: @text; font-size: 13px; }
QMainWindow, QMainWindow > QWidget#central { background: @bg; }
QLabel, QCheckBox, QRadioButton { background: transparent; }
QLabel#PanelTitle { font-size: 11px; font-weight: 700; color: @muted; }
QLabel#Hint { color: @muted; font-size: 12px; }

QSplitter::handle { background: transparent; }

QMenuBar { background: @panel; border-bottom: 1px solid @border; }
QMenuBar::item { padding: 6px 12px; background: transparent; }
QMenuBar::item:selected { background: @panel2; border-radius: 4px; }
QMenu { background: @panel2; border: 1px solid @border; padding: 4px; }
QMenu::item { padding: 6px 28px 6px 16px; border-radius: 4px; background: transparent; }
QMenu::item:selected { background: @accent; color: white; }
QMenu::item:disabled { color: @muted; }
QMenu::separator { height: 1px; background: @border; margin: 4px 8px; }

QStatusBar { background: @panel; border-top: 1px solid @border; color: @muted; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: @muted; }
QToolButton#StatusBtn { background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 2px 8px; color: @muted; }
QToolButton#StatusBtn:hover { border-color: @accent; color: @text; }

QFrame#SidePanel { background: @panel; border: 1px solid @border; border-radius: 10px; }

QToolButton#ToolButton { background: @panel2; border: 1px solid @border; border-radius: 8px; padding: 6px 4px; color: @text; }
QToolButton#ToolButton:hover { border-color: @accent; }
QToolButton#ToolButton:checked { background: @accent; border-color: @accent; color: white; }

QPushButton { background: @panel2; border: 1px solid @border; border-radius: 6px; padding: 8px 12px; }
QPushButton:hover { border-color: @accent; }
QPushButton:pressed { background: @border; }
QPushButton:disabled { color: @muted; background: @panel; }
QPushButton#Primary { background: @accent; border-color: @accent; color: white; font-weight: 600; }
QPushButton#Primary:hover { background: @accent_hover; }
QPushButton#Primary:disabled { background: @panel2; border-color: @border; color: @muted; }
QPushButton::menu-indicator { subcontrol-position: right center; subcontrol-origin: padding; right: 10px; }

QGroupBox { background: transparent; border: 1px solid @border; border-radius: 8px; margin-top: 14px; padding: 12px 8px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: @muted; }

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { background: @bg; border: 1px solid @border; border-radius: 5px; padding: 4px 6px; min-height: 20px; }
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover { border-color: @accent; }
QComboBox QAbstractItemView { background: @panel2; selection-background-color: @accent; border: 1px solid @border; outline: 0; }

QSlider::groove:horizontal { height: 4px; background: @border; border-radius: 2px; }
QSlider::sub-page:horizontal { background: @accent; border-radius: 2px; }
QSlider::handle:horizontal { background: white; width: 14px; margin: -6px 0; border-radius: 7px; }

QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid @border; background: @bg; }
QCheckBox::indicator:checked { background: @accent; border-color: @accent; }

QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { width: 10px; background: transparent; margin: 0; }
QScrollBar::handle:vertical { background: @border; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 10px; background: transparent; margin: 0; }
QScrollBar::handle:horizontal { background: @border; border-radius: 5px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QToolTip { background: @panel2; color: @text; border: 1px solid @border; padding: 4px; }
QDialog { background: @panel; }
QGraphicsView#Canvas { background: @canvas; border: 1px solid @border; }
"""


def stylesheet() -> str:
    qss = _QSS
    # longest keys first so @accent_hover is not clobbered by @accent
    for key in sorted(PALETTE, key=len, reverse=True):
        qss = qss.replace("@" + key, PALETTE[key])
    return qss

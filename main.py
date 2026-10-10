import sys

from PySide6.QtWidgets import QApplication

from controller import EditorController
from ui.main_window import MainWindow
from ui.theme import stylesheet


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Decalify")
    app.setStyle("Fusion")          # consistent look on every OS; the stylesheet does the rest
    app.setStyleSheet(stylesheet())

    controller = EditorController()
    window = MainWindow(controller)
    window.show()

    if len(sys.argv) > 1:           # python main.py shape.png
        controller.open_image(sys.argv[1])

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

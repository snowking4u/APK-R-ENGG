"""Developer utility: launch the real (windowed) application and capture a
screenshot of the running IDE. Used for visual verification during
development. Not part of the shipped application.

Run from the project root:  python tools/capture_screenshot.py
"""

import os
import sys

os.environ.pop("QT_QPA_PLATFORM", None)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer
from app.ui import MainWindow
from app.main import create_application

OUT = os.path.join(os.environ.get("TEMP", "."), "ide_screenshot.png")


def capture():
    window.grab().save(OUT)
    print("screenshot saved:", OUT, os.path.exists(OUT))


def main():
    global window
    app = create_application([])
    window = MainWindow()
    window.show()

    QTimer.singleShot(1200, capture)
    QTimer.singleShot(1500, window.close)
    QTimer.singleShot(1700, app.quit)
    code = app.exec()
    print("REAL WINDOW RUN EXIT CODE:", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
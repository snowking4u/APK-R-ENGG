"""APK Reverse Engineering IDE - application entry point.

Run from the project root:
    python -m app.main
    or
    python app/main.py
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.core import app_state, logger
from app.ui.theme import load_stylesheet
from app.ui import MainWindow


def create_application(argv=None):
    """Build and return the fully assembled QApplication."""
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("APK Reverse Engineering IDE")
    app.setOrganizationName("APKReverseEngineeringIDE")
    app.setStyle("Fusion")

    stylesheet = load_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)
    else:
        logger.warning("Stylesheet not found; using default palette")

    return app


def main(argv=None):
    app = create_application(argv)

    window = MainWindow()
    window.setAttribute(Qt.WA_DeleteOnClose)
    window.show()

    code = app.exec()
    logger.info("Application exited with code %d" % code)
    return code


if __name__ == "__main__":
    sys.exit(main())
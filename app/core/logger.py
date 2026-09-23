"""Internal application logger.

Provides a small logging mechanism based on a Qt signal so that log
messages can be displayed live in the Console tab of the bottom panel.

Usage:
    from app.core import logger
    logger.info("Application started")
    logger.error("Something failed")
"""

from PySide6.QtCore import QObject, Signal


class AppLogger(QObject):
    """Signal-based logger.

    Every ``log``/``info``/... call emits a single :attr:`message`
    signal carrying the fully formatted ``[LEVEL] text`` line.
    """

    message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def log(self, level, text):
        self.message.emit("[%s] %s" % (level, text))

    def debug(self, text):
        self.log("DEBUG", text)

    def info(self, text):
        self.log("INFO", text)

    def warning(self, text):
        self.log("WARNING", text)

    def error(self, text):
        self.log("ERROR", text)


# Shared application-wide logger instance.
logger = AppLogger()
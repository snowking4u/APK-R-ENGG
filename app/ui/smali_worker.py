"""Asynchronous Smali indexing worker (Phase 04).

The discovery/parsing pipeline lives in :mod:`app.core.smali_index` (pure,
Qt-free). This ``QThread`` only runs it off the UI thread and emits the
finished index, so large APKs do not freeze the project tree.
"""

from PySide6.QtCore import QThread, Signal

from app.core import logger
from app.core.smali_index import build_smali_index


class _SmaliIndexCancelled(Exception):
    """Internal control-flow marker; never shown to the user."""


class SmaliIndexWorker(QThread):
    """Build a Smali index from a list of discovered roots."""

    progress = Signal(int, int)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, roots, parent=None):
        super().__init__(parent)
        self.roots = [str(item) for item in (roots or []) if item]
        self._cancel_pending = False

    def request_cancel(self):
        self._cancel_pending = True

    def run(self):
        def report(current, total):
            if self._cancel_pending:
                raise _SmaliIndexCancelled()
            if current == total or current % 50 == 0:
                self.progress.emit(int(current), int(total or 1))

        try:
            index = build_smali_index(self.roots, progress=report)
        except _SmaliIndexCancelled:
            self.failed.emit("Smali indexing cancelled.")
            return
        except Exception as exc:  # never take the UI down
            message = "Smali indexing failed unexpectedly: %s" % exc
            logger.error(message)
            self.failed.emit(message)
            return

        if self._cancel_pending:
            self.failed.emit("Smali indexing cancelled.")
            return
        self.completed.emit(index)

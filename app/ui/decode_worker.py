"""Asynchronous APK decode worker (Phase 02).

Runs the Phase 02 decode pipeline (validate APK, plan workspace, copy
original, Apktool decode, discover structure, parse manifest) in a
background ``QThread`` so the GUI stays responsive-keyboard driven.

The worker only orchestrates: every stage lives in
:mod:`app.core.apk_decoder` (pure, Qt-free, thread-safe). All signals are
delivered to the Qt event loop of the creating thread.

Signals:
    stage(str)            -- human-readable stage name
    progress(int, int)    -- (current step, total steps)
    completed(object)     -- DecodeReport from apk_decoder
    failed(str)           -- user-facing error message
    log_line(str)         -- one console line
"""

from PySide6.QtCore import QThread, Signal

from app.core import logger
from app.core.apk_decoder import DecodeReport, run_decode


class DecodeWorker(QThread):
    """Decode pipeline executed off the UI thread."""

    stage = Signal(str)
    progress = Signal(int, int)
    completed = Signal(object)
    failed = Signal(str)
    log_line = Signal(str)

    STAGES = (
        "Validating APK...",
        "Preparing project...",
        "Decoding APK...",
        "Loading project...",
        "Completed",
    )

    def __init__(self, apk_path, projects_root, on_conflict=None,
                 timeout=None, parent=None):
        super().__init__(parent)
        self.apk_path = apk_path
        self.projects_root = projects_root
        self.on_conflict = on_conflict
        self.timeout = timeout
        self._cancel_pending = False

    def request_cancel(self):
        self._cancel_pending = True

    # ------------------------------------------------------------------ #
    # QThread entry point (runs on the worker thread).
    # ------------------------------------------------------------------ #
    def run(self):
        report = DecodeReport()

        try:
            self.stage.emit(self.STAGES[0])
            self.progress.emit(1, len(self.STAGES))

            if self._cancel_pending:
                report.error = "Decode cancelled by the user."
                self.failed.emit(report.error)
                return

            report = run_decode(
                apk_path=self.apk_path,
                projects_root=self.projects_root,
                on_conflict=self.on_conflict,
                timeout=self.timeout,
                logger=logger,
            )
        except Exception as exc:  # never take the UI down
            logger.error("Decode worker crashed: %s" % exc)
            report.error = "APK decode failed unexpectedly: %s" % exc

        if report and report.ok:
            logger.info("Decode completed.")
            self.stage.emit(self.STAGES[-1])
            self.progress.emit(len(self.STAGES), len(self.STAGES))
            self.completed.emit(report)
        else:
            message = (report.error if report else
                       "APK decode failed for an unknown reason.")
            logger.error(message)
            self.failed.emit(message)

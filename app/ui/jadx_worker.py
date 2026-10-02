"""Asynchronous JADX decompilation worker (Phase 03).

Mirrors the Phase 02 :class:`~app.ui.decode_worker.DecodeWorker`
architecture: all orchestration lives in :mod:`app.core.decompiler`
(pure, Qt-free, thread-safe) and this ``QThread`` only reports progress
back to the Qt event loop of the creating thread, so the GUI never blocks
while JADX runs.

Signals:
    stage(str)          -- human-readable stage name
    progress(int, int)  -- (current step, total steps)
    completed(object)   -- DecompileReport
    failed(str)         -- user-facing error message
"""

from PySide6.QtCore import QThread, Signal

from app.core import logger
from app.core.decompiler import (DecompileReport, DEFAULT_DECOMPILE_TIMEOUT,
                                 run_decompile)


class JadxWorker(QThread):
    """Java decompilation pipeline executed off the UI thread."""

    stage = Signal(str)
    progress = Signal(int, int)
    completed = Signal(object)
    failed = Signal(str)

    STAGES = (
        "Preparing Java decompilation...",
        "Discovering DEX files...",
        "Starting JADX...",
        "Decompiling classes...",
        "Loading Java sources...",
        "Indexing Java sources...",
        "Updating project tree...",
        "Completed",
    )

    def __init__(self, apk_path="", workspace_root="", decoded_dir="",
                 dex_files=None, clean=False, reuse=True, timeout=None,
                 parent=None):
        super().__init__(parent)
        self.apk_path = apk_path or ""
        self.workspace_root = workspace_root or ""
        self.decoded_dir = decoded_dir or ""
        self.dex_files = list(dex_files or [])
        self.clean = bool(clean)
        self.reuse = bool(reuse)
        self.timeout = timeout or DEFAULT_DECOMPILE_TIMEOUT
        self._cancel_pending = False

    def request_cancel(self):
        self._cancel_pending = True

    # ------------------------------------------------------------------ #
    # QThread entry point (runs on the worker thread).
    # ------------------------------------------------------------------ #
    def run(self):
        report = DecompileReport()

        def emit_stage(text):
            self.stage.emit(text)

        def emit_progress(current, total):
            self.progress.emit(int(current), int(total or 1))

        try:
            if self._cancel_pending:
                self.failed.emit("Java decompilation cancelled by the user.")
                return

            report = run_decompile(
                apk_path=self.apk_path,
                workspace_root=self.workspace_root,
                decoded_dir=self.decoded_dir,
                dex_files=self.dex_files,
                clean=self.clean,
                reuse=self.reuse,
                timeout=self.timeout,
                progress=emit_progress,
                stage=emit_stage,
            )
        except Exception as exc:  # never take the UI down
            logger.error("JADX worker crashed: %s" % exc)
            report.error = "Java decompilation failed unexpectedly: %s" % exc
            report.status = "Failed"

        if report is not None and report.ok:
            logger.info("Java decompilation completed.")
            self.stage.emit(self.STAGES[-1])
            self.completed.emit(report)
        else:
            message = (report.error if report else
                       "Java decompilation failed for an unknown reason.")
            logger.error(message)
            self.failed.emit(message)


class JavaSearchWorker(QThread):
    """Search the Java index off the UI thread (Phase 03)."""

    results = Signal(object)
    failed = Signal(str)

    def __init__(self, index, query, scope="All", case_sensitive=False,
                 limit=200, parent=None):
        super().__init__(parent)
        self.index = index
        self.query = query or ""
        self.scope = scope or "All"
        self.case_sensitive = bool(case_sensitive)
        self.limit = int(limit)

    def run(self):
        try:
            hits = search(self.index, self.query, self.scope,
                          self.case_sensitive, self.limit)
        except Exception as exc:
            logger.error("Java search failed: %s" % exc)
            self.failed.emit("Java search failed: %s" % exc)
            return
        self.results.emit(hits)


def search(index, query, scope="All", case_sensitive=False, limit=200):
    """Run one search (pure function so tests can call it directly)."""
    from app.core.java_index import search_index, search_text

    if index is None:
        return []

    if scope == "Classes":
        return [hit for hit in search_index(index, query, limit)
                if hit.get("kind") == "class"][:limit]
    if scope == "Methods":
        return [hit for hit in search_index(index, query, limit)
                if hit.get("kind") == "method"][:limit]
    if scope == "Packages":
        return [hit for hit in search_index(index, query, limit)
                if hit.get("kind") == "package"][:limit]
    if scope == "Source text":
        return search_text(index, query, limit=limit,
                           case_sensitive=case_sensitive)
    return search_index(index, query, limit) + search_text(
        index, query, limit=limit, case_sensitive=case_sensitive)
"""Main application window.

Assembles menus, toolbar, dock panels, center editor splitter and the
status bar. Phase 01 actions that have no backend yet are wired to a
single ``_not_implemented`` handler so nothing crashes and the user gets
a clear message instead.
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QMessageBox, QSplitter,
                               QStatusBar, QMainWindow, QLabel)

from app import APP_NAME, APP_VERSION, APP_PHASE
from app.core import app_state, logger
from app.core.decompiler import DecompileReport, load_existing_decompilation
from app.core.java_index import (build_index, discover_java_sources,
                                 find_java_source_root, search_index,
                                 search_text)
from app.core.manifest_parser import parse_manifest_file
from app.core.project import current as current_project
from app.core.smali_discovery import discover_smali_roots, find_decoded_dir
from app.core.smali_index import (SmaliIndex, find_java_by_smali,
                                  find_smali_by_java, safe_write_smali,
                                  search_smali)
from app.ui.apk_info_panel import ApkInfoPanel
from app.ui.bottom_panel import BottomPanel, NOT_IMPLEMENTED
from app.ui.code_editor import CodeEditor
from app.ui.project_panel import ProjectExplorer
from app.ui.smali_worker import SmaliIndexWorker
from app.ui.toolbar import MainToolBar

JAVA_PLACEHOLDER = (
    "//  Java Decompiled View\n"
    "//  No APK loaded yet.\n"
    "//\n"
    "//  Decompiled Java sources will appear here in a later phase.\n"
)

SMALI_PLACEHOLDER = (
    "#  Smali View\n"
    "#  No APK loaded yet.\n"
    "#\n"
    "#  Smali disassembly (read/write) will appear here in a later phase.\n"
)


class MainWindow(QMainWindow):
    """Top-level IDE window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)
        self.setDockOptions(QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks)
        self.setAnimated(False)

        self._smali_worker = None
        self._retired_smali_workers = []
        self._smali_generation = 0
        self._current_java_path = None
        self._current_smali_path = None

        self._build_docks()
        self._build_central()
        self._build_menu_bar()
        self._build_toolbar()
        self._build_status_bar()

        self._connect_state()
        self._log_startup()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def _build_docks(self):
        self.project_dock = QDockWidget("Project Explorer", self)
        self.project_dock.setObjectName("ProjectDock")
        self.project_dock.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
        self.project_explorer = ProjectExplorer(self)
        self.project_dock.setWidget(self.project_explorer)
        self.project_dock.setMinimumWidth(200)

        self.bottom_dock = QDockWidget("Bottom Panel", self)
        self.bottom_dock.setObjectName("BottomDock")
        self.bottom_dock.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
        self.bottom_panel = BottomPanel(self)
        self.bottom_dock.setWidget(self.bottom_panel)
        self.bottom_dock.setMinimumHeight(140)

        self.apk_info_dock = QDockWidget("APK Info", self)
        self.apk_info_dock.setObjectName("ApkInfoDock")
        self.apk_info_dock.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
        self.apk_info_panel = ApkInfoPanel(self)
        self.apk_info_dock.setWidget(self.apk_info_panel)
        self.apk_info_dock.setMinimumWidth(220)

        self.addDockWidget(Qt.LeftDockWidgetArea, self.project_dock)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.bottom_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.apk_info_dock)

    def _build_central(self):
        self.java_editor = CodeEditor(
            language="java",
            read_only=True,
            placeholder="Decompiled Java source - not yet available.",
        )
        self.java_editor.set_content(JAVA_PLACEHOLDER)
        self.java_editor.setMinimumWidth(280)

        self.smali_editor = CodeEditor(
            language="smali",
            read_only=False,
            placeholder="Smali source - editable in a later phase.",
        )
        self.smali_editor.set_content(SMALI_PLACEHOLDER)
        self.smali_editor.setMinimumWidth(280)

        self.java_container = self._wrap_with_label("Java Decompiled View", self.java_editor)
        self.smali_container = self._wrap_with_label("Smali View", self.smali_editor)
        self.java_header = getattr(self.java_editor, "header_label", None)
        self.smali_header = getattr(self.smali_editor, "header_label", None)

        self.editor_splitter = QSplitter(Qt.Horizontal, self)
        self.editor_splitter.setObjectName("EditorSplitter")
        self.editor_splitter.setChildrenCollapsible(False)
        self.editor_splitter.addWidget(self.java_container)
        self.editor_splitter.addWidget(self.smali_container)
        self.editor_splitter.setSizes([600, 600])

        self.setCentralWidget(self.editor_splitter)

    @staticmethod
    def _wrap_with_label(title, editor):
        """Small container adding a slim header bar above an editor."""
        from PySide6.QtWidgets import QVBoxLayout, QWidget

        container = QWidget()
        container.setObjectName("EditorContainer")
        header = QLabel(" " + title)
        header.setObjectName("EditorHeader")
        header.setStyleSheet(
            "background-color: #252629; color: #9cdcfe; padding: 3px 6px;"
            " border-bottom: 1px solid #3c3c3c; font-weight: bold;"
        )
        header.setFixedHeight(24)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(editor, 1)
        editor.header_label = header
        return container

    def _build_menu_bar(self):
        bar = self.menuBar()

        # ----- File
        menu_file = bar.addMenu("&File")
        self.action_open_apk = QAction("&Open APK...", self)
        self.action_open_apk.setShortcut(QKeySequence.Open)
        self.action_open_apk.triggered.connect(lambda: self._not_implemented("Open APK"))
        menu_file.addAction(self.action_open_apk)

        self.action_open_project = QAction("Open &Project...", self)
        self.action_open_project.triggered.connect(self._open_project_dialog)
        menu_file.addAction(self.action_open_project)

        menu_file.addSeparator()

        self.action_save = QAction("&Save", self)
        self.action_save.setShortcut(QKeySequence.Save)
        self.action_save.triggered.connect(self._save_current_smali)
        menu_file.addAction(self.action_save)

        self.action_save_as = QAction("Save &As...", self)
        self.action_save_as.triggered.connect(lambda: self._not_implemented("Save As"))
        menu_file.addAction(self.action_save_as)

        menu_file.addSeparator()

        self.action_exit = QAction("E&xit", self)
        self.action_exit.setShortcut(QKeySequence.Quit)
        self.action_exit.triggered.connect(self.close)
        menu_file.addAction(self.action_exit)

        # ----- View
        menu_view = bar.addMenu("&View")

        self.action_view_project = QAction("&Project Explorer", self)
        self.action_view_project.setCheckable(True)
        self.action_view_project.setChecked(True)
        self.action_view_project.toggled.connect(self.project_dock.setVisible)
        self.project_dock.visibilityChanged.connect(self.action_view_project.setChecked)
        menu_view.addAction(self.action_view_project)

        self.action_view_java = QAction("&Java View", self)
        self.action_view_java.setCheckable(True)
        self.action_view_java.setChecked(True)
        self.action_view_java.toggled.connect(self.java_container.setVisible)
        menu_view.addAction(self.action_view_java)

        self.action_view_smali = QAction("&Smali View", self)
        self.action_view_smali.setCheckable(True)
        self.action_view_smali.setChecked(True)
        self.action_view_smali.toggled.connect(self.smali_container.setVisible)
        menu_view.addAction(self.action_view_smali)

        self.action_view_bottom = QAction("&Bottom Panel", self)
        self.action_view_bottom.setCheckable(True)
        self.action_view_bottom.setChecked(True)
        self.action_view_bottom.toggled.connect(self.bottom_dock.setVisible)
        self.bottom_dock.visibilityChanged.connect(self.action_view_bottom.setChecked)
        menu_view.addAction(self.action_view_bottom)

        menu_view.addSeparator()

        self.action_reset_layout = QAction("&Reset Layout", self)
        self.action_reset_layout.triggered.connect(self.reset_layout)
        menu_view.addAction(self.action_reset_layout)

        # ----- Build
        menu_build = bar.addMenu("&Build")
        self.action_rebuild = QAction("&Rebuild", self)
        self.action_rebuild.setShortcut("F7")
        self.action_rebuild.triggered.connect(lambda: self._not_implemented("Rebuild"))
        menu_build.addAction(self.action_rebuild)

        self.action_sign = QAction("&Sign", self)
        self.action_sign.triggered.connect(lambda: self._not_implemented("Sign"))
        menu_build.addAction(self.action_sign)

        self.action_rebuild_sign = QAction("Rebuild && &Sign", self)
        self.action_rebuild_sign.triggered.connect(lambda: self._not_implemented("Rebuild & Sign"))
        menu_build.addAction(self.action_rebuild_sign)

        menu_build.addSeparator()

        self.action_clean = QAction("&Clean", self)
        self.action_clean.triggered.connect(lambda: self._not_implemented("Clean"))
        menu_build.addAction(self.action_clean)

        # ----- Analysis
        menu_analysis = bar.addMenu("&Analysis")
        for name in ("Explain", "Patch Assistant", "Calls", "Called By", "Graph"):
            action = QAction(name, self)
            action.triggered.connect(lambda checked=False, n=name: self._not_implemented(n))
            menu_analysis.addAction(action)

        self.action_search = QAction("Search", self)
        self.action_search.triggered.connect(self._show_search)
        menu_analysis.addAction(self.action_search)

        menu_analysis.addSeparator()
        self.action_locate_smali = QAction("Locate Smali", self)
        self.action_locate_smali.triggered.connect(self._locate_smali)
        menu_analysis.addAction(self.action_locate_smali)
        self.action_locate_java = QAction("Locate Java", self)
        self.action_locate_java.triggered.connect(self._locate_java)
        menu_analysis.addAction(self.action_locate_java)

        # ----- Help
        menu_help = bar.addMenu("&Help")
        self.action_about = QAction("&About", self)
        self.action_about.triggered.connect(self._show_about)
        menu_help.addAction(self.action_about)

    def _build_toolbar(self):
        self.toolbar = MainToolBar(self)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        # Wire shared actions (same objects appear in menus and toolbar).
        self.toolbar.action_open_apk.triggered.connect(self.action_open_apk.trigger)
        self.toolbar.action_save.triggered.connect(self.action_save.trigger)
        self.toolbar.action_rebuild.triggered.connect(self.action_rebuild.trigger)
        self.toolbar.action_sign.triggered.connect(self.action_sign.trigger)
        self.toolbar.action_rebuild_sign.triggered.connect(self.action_rebuild_sign.trigger)
        self.toolbar.action_clean.triggered.connect(self.action_clean.trigger)

    # ------------------------------------------------------------------ #
    # State <-> status bar wiring
    # ------------------------------------------------------------------ #
    def _build_status_bar(self):
        bar = QStatusBar(self)

        self.status_label = QLabel("Ready", bar)
        self.status_label.setObjectName("StatusLabel")
        bar.addWidget(self.status_label)

        bar.addPermanentWidget(self._info_label("status_project"))
        bar.addPermanentWidget(self._info_label("status_classes"))
        bar.addPermanentWidget(self._info_label("status_methods"))
        bar.addPermanentWidget(self._info_label("status_resources"))
        bar.addPermanentWidget(self._info_label("status_smali"))
        bar.addPermanentWidget(self._info_label("status_build"))

        self.setStatusBar(bar)
        self._refresh_status_labels()

    def _info_label(self, object_name):
        label = QLabel("", self)
        label.setObjectName("MutedLabel")
        setattr(self, object_name, label)
        return label

    # ------------------------------------------------------------------ #
    # State <-> status bar wiring
    # ------------------------------------------------------------------ #
    def _connect_state(self):
        app_state.project_changed.connect(self._refresh_status_labels)
        app_state.stats_changed.connect(self._refresh_status_labels)
        app_state.build_status_changed.connect(self._refresh_status_labels)
        app_state.smali_changed.connect(self._refresh_status_labels)

        self.project_explorer.java_activated.connect(self._open_java_file)
        self.project_explorer.smali_activated.connect(self._open_smali_file)
        self.project_explorer.locate_smali_requested.connect(
            self._locate_smali_from_path)
        self.project_explorer.locate_java_requested.connect(
            self._locate_java_from_path)
        self.bottom_panel.search_view.search_requested.connect(self._run_search)
        self.bottom_panel.search_view.open_requested.connect(
            self._open_search_result)
        self.smali_editor.dirty_changed.connect(self._on_smali_dirty_changed)
        self._update_smali_header()

    def _refresh_status_labels(self):
        apk = app_state.apk_path
        project = app_state.project_path or (apk.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] if apk else None)
        self.status_project.setText("Project: %s" % (project if project else "None"))
        self.status_classes.setText("Classes: %d" % app_state.class_count)
        self.status_methods.setText("Methods: %d" % app_state.method_count)
        self.status_resources.setText("Resources: %d" % app_state.resource_count)
        if hasattr(self, "status_smali"):
            marker = " *" if app_state.smali_dirty else ""
            self.status_smali.setText("Smali: %d%s"
                                      % (app_state.smali_file_count, marker))
        self.status_build.setText("Build: %s" % app_state.build_status)

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def reset_layout(self):
        self.removeDockWidget(self.project_dock)
        self.removeDockWidget(self.bottom_dock)
        self.removeDockWidget(self.apk_info_dock)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.project_dock)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.bottom_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.apk_info_dock)
        self.project_dock.show()
        self.bottom_dock.show()
        self.apk_info_dock.show()
        self.action_view_project.setChecked(True)
        self.action_view_bottom.setChecked(True)
        self.action_view_java.setChecked(True)
        self.action_view_smali.setChecked(True)
        self.editor_splitter.setSizes([600, 600])
        self.project_dock.setMinimumWidth(200)
        self.project_dock.resize(260, self.project_dock.height())
        logger.info("Layout reset")

    # ------------------------------------------------------------------ #
    # Phase 04: decoded project loading + Smali index
    # ------------------------------------------------------------------ #
    def _open_project_dialog(self):
        path = QFileDialog.getExistingDirectory(
            self, "Open Decoded Project", "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
        if path:
            self.load_decoded_project(path)

    def load_decoded_project(self, path):
        """Load a decoded project directory (static inspection only).

        Accepts a decoded directory or a workspace containing ``decoded/``.
        No Apktool/JADX process is started here; existing Smali files and
        already-generated Java sources are indexed as-is.
        """
        if not path or not os.path.isdir(path):
            logger.error("Smali discovery failed: project not found: %s"
                         % (path or "?"))
            self.statusBar().showMessage("Project directory not found.", 4000)
            return False
        if not self._confirm_discard_smali():
            return False

        decoded = find_decoded_dir(path)
        roots = discover_smali_roots(decoded) if decoded else []
        if not decoded or not roots:
            logger.error("Smali discovery failed: no Smali directories in %s"
                         % path)
            self.statusBar().showMessage(
                "No Smali directories found in the selected project.", 5000)
            return False

        current_project.reset()
        app_state.clear_project()
        self._current_java_path = None
        self._current_smali_path = None

        root = os.path.abspath(path)
        current_project.name = os.path.basename(root.rstrip("\\/")) or "Project"
        current_project.project_path = root
        current_project.workspace_root = root
        current_project.decoded_dir = decoded
        current_project.smali_dirs = [os.path.basename(item) for item in roots]
        current_project.smali_roots = roots
        current_project.smali_status = "Discovering"

        manifest_path = os.path.join(decoded, "AndroidManifest.xml")
        if os.path.isfile(manifest_path):
            current_project.manifest_path = manifest_path
            manifest = parse_manifest_file(manifest_path)
            current_project.package_name = manifest.package or None
        resource_dir = os.path.join(decoded, "res")
        assets_dir = os.path.join(decoded, "assets")
        apktool_yml = os.path.join(decoded, "apktool.yml")

        apk_path = ""
        original_dir = os.path.join(root, "original")
        if os.path.isdir(original_dir):
            for name in sorted(os.listdir(original_dir)):
                if name.lower().endswith(".apk"):
                    apk_path = os.path.join(original_dir, name)
                    break
        apk_size = None
        if apk_path:
            try:
                apk_size = os.path.getsize(apk_path)
            except OSError:
                apk_size = None

        java_report = self._load_java_report(root, decoded)
        if java_report is not None and java_report.index is not None:
            current_project.apply_decompile_report(java_report)

        self.project_explorer.build_project_tree(
            apk_path=apk_path,
            apk_size=apk_size,
            dex_names=current_project.dex_files,
            resource_dir=resource_dir,
            assets_dir=assets_dir,
            manifest_path=manifest_path,
            apktool_yml_path=apktool_yml,
            package_name=current_project.package_name or "",
            title=current_project.name or "PROJECT",
        )
        if java_report is not None and java_report.index is not None:
            self.project_explorer.set_java_index(
                java_report.index, java_report.java_source_root)
        self.project_explorer.set_smali_index(None, roots)

        current_project.to_state(app_state)
        self._update_apk_info()
        self._update_smali_header()
        self._start_smali_index(roots)
        self.status_label.setText("Project loaded")
        self.statusBar().showMessage("Project loaded: %s" % root, 4000)
        logger.info("Project opened: %s" % root)
        return True

    def _load_java_report(self, root, decoded):
        """Load already-generated Java sources without running JADX."""
        candidates = [root, os.path.dirname(decoded)]
        for workspace in candidates:
            if workspace and os.path.isdir(os.path.join(workspace, "decompiled")):
                report = load_existing_decompilation(workspace)
                if report.index is not None:
                    return report
        source_root = find_java_source_root(root)
        if source_root:
            sources = discover_java_sources(source_root)
            report = DecompileReport()
            report.index = build_index(source_root)
            report.java_sources = sources
            report.java_source_root = source_root
            report.ok = bool(sources)
            report.status = "Completed" if sources else "Idle"
            return report
        return None

    def _start_smali_index(self, roots):
        self._cancel_smali_worker()
        if not roots:
            self.project_explorer.set_smali_index(None, [])
            return
        self._smali_generation += 1
        generation = self._smali_generation
        worker = SmaliIndexWorker(roots, self)
        self._smali_worker = worker
        worker.progress.connect(self._on_smali_progress)
        worker.completed.connect(
            lambda index, g=generation: self._on_smali_index_ready(index, g))
        worker.failed.connect(
            lambda message, g=generation: self._on_smali_index_failed(message, g))
        worker.finished.connect(
            lambda w=worker: self._on_smali_worker_finished(w))
        self.status_label.setText("Indexing Smali...")
        worker.start()

    def _cancel_smali_worker(self):
        worker = self._smali_worker
        if worker is None:
            return
        self._smali_worker = None
        worker.request_cancel()
        self._retired_smali_workers.append(worker)

    def _on_smali_worker_finished(self, worker):
        if self._smali_worker is worker:
            self._smali_worker = None
        if worker in self._retired_smali_workers:
            self._retired_smali_workers.remove(worker)
        worker.deleteLater()

    def _on_smali_progress(self, current, total):
        self.status_label.setText("Indexing Smali... %d/%d" % (current, total))

    def _on_smali_index_ready(self, index, generation):
        if generation != self._smali_generation:
            return
        current_project.apply_smali_index(index)
        current_project.to_state(app_state)
        self.project_explorer.set_smali_index(index, index.roots)
        self._update_apk_info()
        self._refresh_status_labels()
        self.status_label.setText("Smali indexed: %d file(s)" % index.file_count)
        self.statusBar().showMessage(
            "Smali indexed: %d file(s), %d method(s)"
            % (index.file_count, index.method_count), 4000)

    def _on_smali_index_failed(self, message, generation):
        if generation != self._smali_generation:
            return
        logger.error(message)
        current_project.smali_status = "Failed"
        self.project_explorer.set_smali_index(SmaliIndex(current_project.smali_roots),
                                              current_project.smali_roots)
        self._update_apk_info()
        self.status_label.setText("Smali indexing failed")
        self.statusBar().showMessage(message, 5000)

    # ------------------------------------------------------------------ #
    # Phase 04: Java / Smali editors and navigation
    # ------------------------------------------------------------------ #
    def _open_java_file(self, path, line=1):
        if not path:
            return False
        if not self.java_editor.load_file(path):
            logger.error("Java file could not be opened: %s" % path)
            self.statusBar().showMessage("Java file could not be opened.", 4000)
            return False
        self._current_java_path = os.path.abspath(path)
        source = (current_project.java_index.get(self._current_java_path)
                  if current_project.java_index else None)
        class_name = getattr(source, "qualified_name", None) if source else None
        app_state.set_java_selection(source=self._current_java_path,
                                     class_name=class_name)
        self.java_editor.goto_line(line)
        self.project_explorer.select_java_file(self._current_java_path)
        self.status_label.setText("Java: %s" % os.path.basename(path))
        return True

    def _open_smali_file(self, path, line=1):
        if not path:
            return False
        target = os.path.abspath(path)
        if self.smali_editor.file_path == target:
            self.smali_editor.goto_line(line)
            self._set_current_smali(target, line)
            return True
        if not self._confirm_discard_smali():
            return False
        ok, error = self.smali_editor.load_editable_file(path)
        if not ok:
            logger.error("Smali file could not be opened: %s (%s)"
                         % (path, error))
            self.statusBar().showMessage(
                "Smali file could not be opened: %s" % error, 5000)
            return False
        self._current_smali_path = target
        self._set_current_smali(target, line)
        self.smali_editor.goto_line(line)
        self.project_explorer.select_smali_file(target)
        self._update_smali_header()
        self._update_apk_info()
        logger.info("Smali file opened: %s" % target)
        self.status_label.setText("Smali: %s" % os.path.basename(target))
        return True

    def _set_current_smali(self, path, line=1):
        source = (current_project.smali_index.get(path)
                  if current_project.smali_index else None)
        class_name = getattr(source, "class_name", None) if source else None
        method_name = None
        if source is not None:
            for method in source.methods:
                if method.start_line == int(line or 1):
                    method_name = method.name
                    break
        current_project.current_smali_file = path
        app_state.set_smali_selection(source=path, class_name=class_name,
                                      method=method_name)

    def _open_search_result(self, path, line):
        if not path:
            return
        if str(path).lower().endswith(".smali"):
            self._open_smali_file(path, line)
        else:
            self._open_java_file(path, line)

    def _update_smali_header(self):
        if not getattr(self, "smali_header", None):
            return
        path = self.smali_editor.file_path
        if path:
            marker = " *" if self.smali_editor.is_dirty() else ""
            self.smali_header.setText(
                " Smali: %s%s" % (os.path.basename(path), marker))
        else:
            self.smali_header.setText(" Smali View")

    def _on_smali_dirty_changed(self, dirty):
        path = self.smali_editor.file_path
        if path:
            if dirty and path not in current_project.modified_smali_files:
                current_project.modified_smali_files.append(path)
            elif not dirty and path in current_project.modified_smali_files:
                current_project.modified_smali_files.remove(path)
        app_state.smali_dirty = bool(dirty)
        app_state.modified_smali_count = len(current_project.modified_smali_files)
        self._update_smali_header()
        self._update_apk_info()

    def _confirm_discard_smali(self):
        if not self.smali_editor.is_dirty() or not self.smali_editor.file_path:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Unsaved Smali changes")
        box.setText("The current Smali file has unsaved changes.")
        box.setInformativeText("Save the changes before continuing?")
        box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard
                               | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Save)
        result = box.exec()
        if result == QMessageBox.Save:
            return self._save_current_smali()
        if result == QMessageBox.Discard:
            self._discard_smali_changes()
            return True
        return False

    def _discard_smali_changes(self):
        """Reload the current Smali file from disk and clear its dirty state."""
        path = self.smali_editor.file_path
        if path:
            self.smali_editor.load_editable_file(path)
        if path and path in current_project.modified_smali_files:
            current_project.modified_smali_files.remove(path)
        app_state.smali_dirty = False
        app_state.modified_smali_count = len(current_project.modified_smali_files)
        self._update_smali_header()
        self._update_apk_info()

    def _save_current_smali(self):
        path = self.smali_editor.file_path
        if not path:
            self._not_implemented("Save")
            return False
        allowed = list(current_project.smali_roots)
        if not allowed and current_project.decoded_dir:
            allowed = [current_project.decoded_dir]
        ok, error = safe_write_smali(path, self.smali_editor.serialize_text(),
                                     allowed_roots=allowed)
        if not ok:
            logger.error("Smali file could not be saved: %s (%s)"
                         % (path, error))
            self.statusBar().showMessage(
                "Smali file could not be saved: %s" % error, 5000)
            return False
        self.smali_editor.mark_saved()
        if path in current_project.modified_smali_files:
            current_project.modified_smali_files.remove(path)
        app_state.smali_dirty = False
        app_state.modified_smali_count = len(current_project.modified_smali_files)
        self._update_smali_header()
        self._update_apk_info()
        logger.info("Smali file saved: %s" % path)
        self.statusBar().showMessage("Saved: %s" % os.path.basename(path), 3000)
        self.status_label.setText("Saved")
        return True

    # ------------------------------------------------------------------ #
    # Phase 04: search + Java <-> Smali mapping
    # ------------------------------------------------------------------ #
    def _show_search(self):
        self.bottom_dock.show()
        self.bottom_panel.show_search_tab()

    def _run_search(self, query, scope, case_sensitive):
        limit = 200
        if scope.startswith("Smali"):
            hits = search_smali(current_project.smali_index, query, scope,
                                case_sensitive, limit)
        elif scope == "All":
            hits = self._search_java(query, scope, case_sensitive, limit)
            hits += search_smali(current_project.smali_index, query, "Smali",
                                 case_sensitive, limit)
            hits = hits[:limit]
        else:
            hits = self._search_java(query, scope, case_sensitive, limit)
        self.bottom_panel.search_view.show_results(hits)
        self.status_label.setText("Search: %d result(s)" % len(hits))

    def _search_java(self, query, scope, case_sensitive, limit):
        index = current_project.java_index
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
        return (search_index(index, query, limit)
                + search_text(index, query, limit=limit,
                              case_sensitive=case_sensitive))[:limit]

    def _locate_smali(self):
        qualified = None
        if current_project.java_index and self._current_java_path:
            source = current_project.java_index.get(self._current_java_path)
            qualified = getattr(source, "qualified_name", None) if source else None
        qualified = qualified or app_state.current_java_class
        self._locate_smali_for_class(qualified)

    def _locate_smali_from_path(self, path):
        qualified = None
        if current_project.java_index:
            source = current_project.java_index.get(path)
            qualified = getattr(source, "qualified_name", None) if source else None
        self._locate_smali_for_class(qualified)

    def _locate_smali_for_class(self, qualified):
        if not qualified:
            self.statusBar().showMessage("No Java class selected.", 4000)
            return
        matches = find_smali_by_java(current_project.smali_index, qualified)
        if len(matches) == 1:
            self._open_smali_file(matches[0].path, matches[0].class_line)
            return
        if not matches:
            logger.info("No matching Smali file for Java class: %s" % qualified)
            self.statusBar().showMessage(
                "No matching Smali file for %s." % qualified, 5000)
            return
        logger.info("Multiple Smali matches for Java class: %s (%d)"
                    % (qualified, len(matches)))
        self.statusBar().showMessage(
            "Multiple Smali matches for %s (%d); not guessing."
            % (qualified, len(matches)), 5000)

    def _locate_java(self):
        source = None
        if current_project.smali_index and self._current_smali_path:
            source = current_project.smali_index.get(self._current_smali_path)
        self._locate_java_for_source(source)

    def _locate_java_from_path(self, path):
        source = (current_project.smali_index.get(path)
                  if current_project.smali_index else None)
        self._locate_java_for_source(source)

    def _locate_java_for_source(self, source):
        if source is None:
            self.statusBar().showMessage("No Smali class selected.", 4000)
            return
        matches = find_java_by_smali(current_project.java_index, source)
        if len(matches) == 1:
            self._open_java_file(matches[0].path, 1)
            return
        if not matches:
            logger.info("No matching Java source for Smali class: %s"
                        % (source.class_name or source.path))
            self.statusBar().showMessage(
                "No matching Java source for %s."
                % (source.class_name or source.file_name), 5000)
            return
        logger.info("Multiple Java matches for Smali class: %s (%d)"
                    % (source.class_name or source.path, len(matches)))
        self.statusBar().showMessage(
            "Multiple Java matches for %s (%d); not guessing."
            % (source.class_name or source.file_name, len(matches)), 5000)

    def _update_apk_info(self):
        if not getattr(self, "apk_info_panel", None):
            return
        index = current_project.smali_index
        self.apk_info_panel.show_smali_status(
            directories=current_project.smali_roots or None,
            files=index.file_count if index else
            (len(current_project.smali_files) or None),
            classes=index.class_count if index else None,
            methods=index.method_count if index else None,
            modified=len(current_project.modified_smali_files),
        )

    # ------------------------------------------------------------------ #
    # Placeholder handling
    # ------------------------------------------------------------------ #
    def _not_implemented(self, feature):
        logger.info("%s requested - %s" % (feature, NOT_IMPLEMENTED))
        self.status_label.setText("Ready")
        self.statusBar().showMessage("'%s' - %s" % (feature, NOT_IMPLEMENTED), 4000)

    def _show_about(self):
        QMessageBox.about(
            self,
            "About " + APP_NAME,
            "<b>%s</b> v%s<br>%s" % (APP_NAME, APP_VERSION, APP_PHASE)
            + "<br><br>"
            + "An IDE for reverse engineering Android applications "
            + "(APK decoding, analysis, patching and signing).<br>"
            + "<br>"
            + "<i>Current build: Smali discovery, editing, search and "
            + "navigation for existing decoded projects.</i>",
        )

    # ------------------------------------------------------------------ #
    # Startup logging
    # ------------------------------------------------------------------ #
    def _log_startup(self):
        logger.info("Application started")
        logger.info("Ready")
        logger.info("No project loaded")
        logger.debug("Window size: %dx%d" % (self.width(), self.height()))

    # ------------------------------------------------------------------ #
    # Shutdown
    # ------------------------------------------------------------------ #
    def closeEvent(self, event):
        if not self._confirm_discard_smali():
            event.ignore()
            return
        workers = list(self._retired_smali_workers)
        if self._smali_worker is not None:
            workers.append(self._smali_worker)
        for worker in workers:
            worker.request_cancel()
        for worker in workers:
            try:
                worker.wait(3000)
            except RuntimeError:
                pass
        super().closeEvent(event)
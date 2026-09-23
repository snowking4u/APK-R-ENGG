"""Main application window.

Assembles menus, toolbar, dock panels, center editor splitter and the
status bar. Phase 01 actions that have no backend yet are wired to a
single ``_not_implemented`` handler so nothing crashes and the user gets
a clear message instead.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QMessageBox, QSplitter,
                               QStatusBar, QMainWindow, QLabel)

from app import APP_NAME, APP_VERSION, APP_PHASE
from app.core import app_state, logger
from app.ui.bottom_panel import BottomPanel, NOT_IMPLEMENTED
from app.ui.code_editor import CodeEditor
from app.ui.project_panel import ProjectExplorer
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

        self.addDockWidget(Qt.LeftDockWidgetArea, self.project_dock)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.bottom_dock)

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
        self.action_open_project.triggered.connect(lambda: self._not_implemented("Open Project"))
        menu_file.addAction(self.action_open_project)

        menu_file.addSeparator()

        self.action_save = QAction("&Save", self)
        self.action_save.setShortcut(QKeySequence.Save)
        self.action_save.triggered.connect(lambda: self._not_implemented("Save"))
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
        analysis_actions = ("Explain", "Patch Assistant", "Calls", "Called By", "Graph", "Search")
        for name in analysis_actions:
            action = QAction(name, self)
            action.triggered.connect(lambda checked=False, n=name: self._not_implemented(n))
            menu_analysis.addAction(action)

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

    def _refresh_status_labels(self):
        apk = app_state.apk_path
        project = app_state.project_path or (apk.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] if apk else None)
        self.status_project.setText("Project: %s" % (project if project else "None"))
        self.status_classes.setText("Classes: %d" % app_state.class_count)
        self.status_methods.setText("Methods: %d" % app_state.method_count)
        self.status_resources.setText("Resources: %d" % app_state.resource_count)
        self.status_build.setText("Build: %s" % app_state.build_status)

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def reset_layout(self):
        self.removeDockWidget(self.project_dock)
        self.removeDockWidget(self.bottom_dock)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.project_dock)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.bottom_dock)
        self.project_dock.show()
        self.bottom_dock.show()
        self.action_view_project.setChecked(True)
        self.action_view_bottom.setChecked(True)
        self.action_view_java.setChecked(True)
        self.action_view_smali.setChecked(True)
        self.editor_splitter.setSizes([600, 600])
        self.project_dock.setMinimumWidth(200)
        self.project_dock.resize(260, self.project_dock.height())
        logger.info("Layout reset")

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
            + "<i>Current build: UI foundation only. Core reverse engineering "
            + "features arrive in later phases.</i>",
        )

    # ------------------------------------------------------------------ #
    # Startup logging
    # ------------------------------------------------------------------ #
    def _log_startup(self):
        logger.info("Application started")
        logger.info("Ready")
        logger.info("No project loaded")
        logger.debug("Window size: %dx%d" % (self.width(), self.height()))
"""Central application / project state model.

Holds all state required by the IDE. Backend phases (APK loading,
decoding, analysis, build, signing) will update this model through the
explicit setter methods; the UI observes the emitted signals and keeps
itself in sync.

Any field may be updated at any time without touching the UI layer.
"""

from PySide6.QtCore import QObject, Signal


class AppState(QObject):
    # Signals emitted whenever the respective part of the state changes.
    stats_changed = Signal()            # class/method/resource counts
    project_changed = Signal()          # apk/project path, package name
    selection_changed = Signal()        # selected class / method
    source_changed = Signal()           # java / smali source replaced
    build_status_changed = Signal()     # build status
    # Phase 03 (JADX / Java decompilation) additions.
    decompile_status_changed = Signal()  # JADX / decompilation status
    java_changed = Signal()             # java source tree / counts changed

    def __init__(self, parent=None):
        super().__init__(parent)

        # File / project information.
        self._apk_path = None
        self._project_path = None
        self._package_name = None

        # Project statistics.
        self._class_count = 0
        self._method_count = 0
        self._resource_count = 0

        # Current selection.
        self._selected_class = None
        self._selected_method = None

        # Current sources (placeholder, set by later phases).
        self._java_source = ""
        self._smali_source = ""

        # Build status.
        self._build_status = "Idle"

        # Phase 03: JADX / Java decompilation state.
        self._jadx_status = "Not configured"
        self._dex_count = 0
        self._dex_names = []
        self._decompile_status = "Idle"
        self._java_source_count = 0
        self._java_method_count = 0
        self._current_java_source = None
        self._current_java_class = None
        self._current_java_method = None

    # ------------------------------------------------------------------ #
    # File / project information.
    # ------------------------------------------------------------------ #
    @property
    def apk_path(self):
        return self._apk_path

    @apk_path.setter
    def apk_path(self, value):
        self._apk_path = value
        self.project_changed.emit()

    @property
    def project_path(self):
        return self._project_path

    @project_path.setter
    def project_path(self, value):
        self._project_path = value
        self.project_changed.emit()

    @property
    def package_name(self):
        return self._package_name

    @package_name.setter
    def package_name(self, value):
        self._package_name = value
        self.project_changed.emit()

    # ------------------------------------------------------------------ #
    # Statistics.
    # ------------------------------------------------------------------ #
    @property
    def class_count(self):
        return self._class_count

    @class_count.setter
    def class_count(self, value):
        self._class_count = max(0, int(value or 0))
        self.stats_changed.emit()

    @property
    def method_count(self):
        return self._method_count

    @method_count.setter
    def method_count(self, value):
        self._method_count = max(0, int(value or 0))
        self.stats_changed.emit()

    @property
    def resource_count(self):
        return self._resource_count

    @resource_count.setter
    def resource_count(self, value):
        self._resource_count = max(0, int(value or 0))
        self.stats_changed.emit()

    # ------------------------------------------------------------------ #
    # Selection.
    # ------------------------------------------------------------------ #
    @property
    def selected_class(self):
        return self._selected_class

    @selected_class.setter
    def selected_class(self, value):
        self._selected_class = value
        self.selection_changed.emit()

    @property
    def selected_method(self):
        return self._selected_method

    @selected_method.setter
    def selected_method(self, value):
        self._selected_method = value
        self.selection_changed.emit()

    # ------------------------------------------------------------------ #
    # Sources.
    # ------------------------------------------------------------------ #
    @property
    def java_source(self):
        return self._java_source

    @java_source.setter
    def java_source(self, value):
        self._java_source = value or ""
        self.source_changed.emit()

    @property
    def smali_source(self):
        return self._smali_source

    @smali_source.setter
    def smali_source(self, value):
        self._smali_source = value or ""
        self.source_changed.emit()

    # ------------------------------------------------------------------ #
    # Build status.
    # ------------------------------------------------------------------ #
    @property
    def build_status(self):
        return self._build_status

    @build_status.setter
    def build_status(self, value):
        self._build_status = value or "Idle"
        self.build_status_changed.emit()

    # ------------------------------------------------------------------ #
    # Phase 03: JADX / Java decompilation.
    # ------------------------------------------------------------------ #
    @property
    def jadx_status(self):
        return self._jadx_status

    @jadx_status.setter
    def jadx_status(self, value):
        self._jadx_status = value or "Not configured"
        self.decompile_status_changed.emit()

    @property
    def dex_count(self):
        return self._dex_count

    @dex_count.setter
    def dex_count(self, value):
        self._dex_count = max(0, int(value or 0))
        self.decompile_status_changed.emit()

    @property
    def dex_names(self):
        return list(self._dex_names)

    @dex_names.setter
    def dex_names(self, value):
        self._dex_names = list(value or [])
        self.decompile_status_changed.emit()

    @property
    def decompile_status(self):
        return self._decompile_status

    @decompile_status.setter
    def decompile_status(self, value):
        self._decompile_status = value or "Idle"
        self.decompile_status_changed.emit()

    @property
    def java_source_count(self):
        return self._java_source_count

    @java_source_count.setter
    def java_source_count(self, value):
        self._java_source_count = max(0, int(value or 0))
        self.java_changed.emit()

    @property
    def java_method_count(self):
        return self._java_method_count

    @java_method_count.setter
    def java_method_count(self, value):
        self._java_method_count = max(0, int(value or 0))
        self.java_changed.emit()

    @property
    def current_java_source(self):
        return self._current_java_source

    @current_java_source.setter
    def current_java_source(self, value):
        self._current_java_source = value or None
        self.java_changed.emit()

    @property
    def current_java_class(self):
        return self._current_java_class

    @current_java_class.setter
    def current_java_class(self, value):
        self._current_java_class = value or None
        self.java_changed.emit()

    @property
    def current_java_method(self):
        return self._current_java_method

    @current_java_method.setter
    def current_java_method(self, value):
        self._current_java_method = value or None
        self.java_changed.emit()

    def set_java_selection(self, source=None, class_name=None, method=None):
        """Batch-update the Java selection with a single signal emission."""
        self._current_java_source = source or None
        self._current_java_class = class_name or None
        self._current_java_method = method or None
        self.java_changed.emit()

    def set_decompile_summary(self, jadx_status=None, decompile_status=None,
                              dex_count=None, dex_names=None,
                              java_source_count=None, java_method_count=None):
        """Batch-update every Phase 03 value with one signal emission."""
        if jadx_status is not None:
            self._jadx_status = jadx_status or "Not configured"
        if decompile_status is not None:
            self._decompile_status = decompile_status or "Idle"
        if dex_count is not None:
            self._dex_count = max(0, int(dex_count or 0))
        if dex_names is not None:
            self._dex_names = list(dex_names)
        if java_source_count is not None:
            self._java_source_count = max(0, int(java_source_count or 0))
        if java_method_count is not None:
            self._java_method_count = max(0, int(java_method_count or 0))
        self.decompile_status_changed.emit()
        self.java_changed.emit()

    # ------------------------------------------------------------------ #
    # Helpers.
    # ------------------------------------------------------------------ #
    def set_project(self, apk_path=None, project_path=None, package_name=None):
        """Batch-update project info with a single signal emission."""
        self._apk_path = apk_path
        self._project_path = project_path
        self._package_name = package_name
        self.project_changed.emit()

    def clear_project(self):
        """Reset project-related state to safe default values."""
        self._apk_path = None
        self._project_path = None
        self._package_name = None
        self._class_count = 0
        self._method_count = 0
        self._resource_count = 0
        self._selected_class = None
        self._selected_method = None
        self._java_source = ""
        self._smali_source = ""
        self._build_status = "Idle"
        self._jadx_status = "Not configured"
        self._dex_count = 0
        self._dex_names = []
        self._decompile_status = "Idle"
        self._java_source_count = 0
        self._java_method_count = 0
        self._current_java_source = None
        self._current_java_class = None
        self._current_java_method = None
        self.project_changed.emit()
        self.stats_changed.emit()
        self.selection_changed.emit()
        self.source_changed.emit()
        self.build_status_changed.emit()
        self.decompile_status_changed.emit()
        self.java_changed.emit()


# Shared application-wide state instance.
app_state = AppState()
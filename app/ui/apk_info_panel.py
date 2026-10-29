"""APK Info panel (Phase 03).

Read-only factual summary of the opened APK and of the Phase 03 Java
decompilation. Values are always real: unknown facts render as ``N/A`` and
decompilation that has not happened renders as such. The panel never
fabricates a DEX count, a JADX version or a Java source count.
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFormLayout, QFrame, QLabel, QScrollArea,
                               QVBoxLayout, QWidget)


NOT_AVAILABLE = "N/A"

_ROWS = (
    ("Package", "package"),
    ("Version", "version"),
    ("Min SDK", "min_sdk"),
    ("Target SDK", "target_sdk"),
    ("Permissions", "permissions"),
    ("Components", "components"),
    ("APK Size", "apk_size"),
    ("Workspace", "workspace"),
    ("DEX Files", "dex"),
    ("JADX", "jadx"),
    ("Decompilation", "decompile"),
    ("Java Sources", "java_sources"),
    ("Java Classes", "java_classes"),
    ("Java Methods", "java_methods"),
    ("Current Class", "current_class"),
    ("Current Method", "current_method"),
    ("Smali Directories", "smali_directories"),
    ("Smali Files", "smali_files"),
    ("Smali Classes", "smali_classes"),
    ("Smali Methods", "smali_methods"),
    ("Modified Smali", "smali_modified"),
)


def _size_text(size):
    try:
        size = float(size)
    except (TypeError, ValueError):
        return NOT_AVAILABLE
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return "%d %s" % (size, unit) if unit == "B" else "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%.1f GB" % size


class ApkInfoPanel(QWidget):
    """Key/value summary of the APK plus Java decompilation status."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ApkInfoPanel")

        self._values = {}

        form_host = QWidget(self)
        self._form = QFormLayout(form_host)
        self._form.setContentsMargins(8, 8, 8, 8)
        self._form.setSpacing(4)
        self._form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        for title, key in _ROWS:
            label = QLabel(title, self)
            label.setObjectName("ApkInfoLabel")
            value = QLabel(NOT_AVAILABLE, self)
            value.setObjectName("ApkInfoValue")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setWordWrap(True)
            self._form.addRow(label, value)
            self._values[key] = value

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(form_host)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        self.setMinimumWidth(240)

        self.clear()

    # ------------------------------------------------------------------ #
    # Values
    # ------------------------------------------------------------------ #
    def set_value(self, key, text):
        label = self._values.get(key)
        if label is None:
            return False
        label.setText(str(text) if text not in (None, "") else NOT_AVAILABLE)
        return True

    def value(self, key):
        label = self._values.get(key)
        return label.text() if label is not None else NOT_AVAILABLE

    def clear(self):
        for key in self._values:
            self._values[key].setText(NOT_AVAILABLE)

    # ------------------------------------------------------------------ #
    # Phase 02 data
    # ------------------------------------------------------------------ #
    def show_decode_report(self, report, apk_size=None):
        """Display the facts parsed from the decoded project."""
        if report is None:
            self.clear()
            return

        manifest = getattr(report, "manifest", None)
        self.set_value("package", getattr(manifest, "package", None) if manifest else None)

        if manifest is not None:
            version = []
            if getattr(manifest, "version_name", None):
                version.append(str(manifest.version_name))
            if getattr(manifest, "version_code", None) is not None:
                version.append("(%s)" % manifest.version_code)
            self.set_value("version", " ".join(version))
            self.set_value("min_sdk", manifest.min_sdk)
            self.set_value("target_sdk", manifest.target_sdk)
            self.set_value("permissions", manifest.permission_count)
            components = (manifest.activity_count + manifest.service_count
                          + manifest.receiver_count + manifest.provider_count)
            self.set_value("components", components)

        self.set_value("apk_size", _size_text(apk_size))
        workspace = getattr(report, "workspace", None)
        self.set_value("workspace", getattr(workspace, "root", None)
                       if workspace is not None else None)
        self.set_value("dex", _dex_text(getattr(report, "dex_names", None)))

    # ------------------------------------------------------------------ #
    # Phase 03 data
    # ------------------------------------------------------------------ #
    def show_java_status(self, jadx_status="Not configured", dex_count=None,
                         dex_names=None, decompile_status="Idle",
                         java_sources=None, java_methods=None,
                         java_classes=None, current_class=None,
                         current_method=None):
        """Display real decompilation facts only."""
        self.set_value("jadx", jadx_status or "Not configured")
        self.set_value("decompile", decompile_status or "Idle")

        if dex_count is None and dex_names is None:
            self.set_value("dex", NOT_AVAILABLE)
        else:
            self.set_value("dex", _dex_text(dex_names, dex_count))

        if java_sources is None and java_methods is None and java_classes is None:
            self.set_value("java_sources", NOT_AVAILABLE)
            self.set_value("java_classes", NOT_AVAILABLE)
            self.set_value("java_methods", NOT_AVAILABLE)
        else:
            self.set_value("java_sources", java_sources
                           if java_sources is not None else NOT_AVAILABLE)
            self.set_value("java_classes", java_classes
                           if java_classes is not None else NOT_AVAILABLE)
            self.set_value("java_methods", java_methods
                           if java_methods is not None else NOT_AVAILABLE)

        self.set_value("current_class", current_class)
        self.set_value("current_method", current_method)

    # ------------------------------------------------------------------ #
    # Phase 04 data
    # ------------------------------------------------------------------ #
    def show_smali_status(self, directories=None, files=None, classes=None,
                          methods=None, modified=None):
        """Display real Smali discovery/editing facts only."""
        if directories is None:
            self.set_value("smali_directories", NOT_AVAILABLE)
        elif isinstance(directories, (list, tuple)):
            names = [os.path.basename(str(item).rstrip("\\/"))
                     for item in directories if item]
            self.set_value("smali_directories",
                           "%d (%s)" % (len(names), ", ".join(names))
                           if names else NOT_AVAILABLE)
        else:
            self.set_value("smali_directories", directories)

        self.set_value("smali_files", files if files is not None
                       else NOT_AVAILABLE)
        self.set_value("smali_classes", classes if classes is not None
                       else NOT_AVAILABLE)
        self.set_value("smali_methods", methods if methods is not None
                       else NOT_AVAILABLE)
        self.set_value("smali_modified", modified if modified is not None
                       else NOT_AVAILABLE)


def _dex_text(names=None, count=None):
    names = list(names or [])
    if not names and not count:
        return NOT_AVAILABLE
    if not names:
        return str(count)
    if len(names) == 1:
        return "1 (%s)" % names[0]
    return "%d (%s, +%d more)" % (len(names), names[0], len(names) - 1)


def default_workspace_name(path):
    """Directory basename of a workspace path (for compact labels)."""
    return os.path.basename(path.rstrip("\\/")) if path else NOT_AVAILABLE
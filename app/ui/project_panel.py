"""Project Explorer panel.

Shows a placeholder project tree for Phase 01. Later phases will
populate this panel with the real APK structure (classes, resources,
assets, manifest content).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


class ProjectExplorer(QTreeWidget):
    """Dock content showing the loaded project tree."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeWidget.SingleSelection)
        self._build_placeholder_tree()

    def _build_placeholder_tree(self):
        root = QTreeWidgetItem(["PROJECT"])
        root.setExpanded(True)
        root.setFlags(Qt.ItemIsEnabled)

        children = []
        for name in ("Classes", "Resources", "Assets", "Manifest"):
            child = QTreeWidgetItem([name])
            child.setFlags(Qt.ItemIsEnabled)
            children.append(child)
            root.addChild(child)

        self.addTopLevelItem(root)
        self.setCurrentItem(children[0])

    # ------------------------------------------------------------------ #
    # Public API (used by future phases to reflect the real APK)
    # ------------------------------------------------------------------ #
    def clear_tree(self):
        self.clear()
        self._build_placeholder_tree()

    def set_project_name(self, name):
        if self.topLevelItemCount():
            self.topLevelItem(0).setText(0, name or "PROJECT")
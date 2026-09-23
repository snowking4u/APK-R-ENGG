"""Main application toolbar.

Phase 01: Open APK, Save, Rebuild, Sign, Rebuild + Sign, Clean.
Uses Qt standard theme icons. Backend actions are placeholders that
report 'Not implemented yet' via the connected slot.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QStyle, QToolBar


class MainToolBar(QToolBar):
    """Top toolbar hosting project and build-oriented actions."""

    def __init__(self, parent=None):
        super().__init__("Main Toolbar", parent)
        self.setObjectName("MainToolBar")
        self.setMovable(False)
        self.setIconSize(QSize(16, 16))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        style = self.style()

        self.action_open_apk = self._build_action(
            "Open APK",
            style.standardIcon(QStyle.SP_DialogOpenButton),
            "Open APK",
            QKeySequence.Open,
        )
        self.action_save = self._build_action(
            "Save",
            style.standardIcon(QStyle.SP_DialogSaveButton),
            "Save",
            QKeySequence.Save,
        )
        self.addSeparator()
        self.action_rebuild = self._build_action(
            "Rebuild",
            style.standardIcon(QStyle.SP_BrowserReload),
            "Rebuild",
            None,
        )
        self.action_sign = self._build_action(
            "Sign",
            style.standardIcon(QStyle.SP_DialogApplyButton),
            "Sign",
            None,
        )
        self.action_rebuild_sign = self._build_action(
            "Rebuild + Sign",
            style.standardIcon(QStyle.SP_ArrowForward),
            "Rebuild and sign",
            None,
        )
        self.action_clean = self._build_action(
            "Clean",
            style.standardIcon(QStyle.SP_TrashIcon),
            "Clean build outputs",
            None,
        )

        self.addAction(self.action_open_apk)
        self.addAction(self.action_save)
        self.addAction(self.action_rebuild)
        self.addAction(self.action_sign)
        self.addAction(self.action_rebuild_sign)
        self.addAction(self.action_clean)

    def _build_action(self, text, icon, tooltip, shortcut):
        action = QAction(icon, text, self)
        action.setToolTip(tooltip)
        if shortcut:
            action.setShortcut(shortcut)
        return action
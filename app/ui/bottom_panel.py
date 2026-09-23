"""Bottom panel: tabbed area below the editors.

Tabs (Phase 01 placeholders, except Console which is live):
    Explain, Patch Assistant, Calls, Called By, Graph, Search, Console
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QLabel, QPlainTextEdit, QTabWidget,
                               QVBoxLayout, QWidget)

NOT_IMPLEMENTED = "Feature will be implemented in a later development phase."


class _PlaceholderTab(QWidget):
    """Centered, muted placeholder view for future analysis tabs."""

    def __init__(self, title, message=NOT_IMPLEMENTED, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addStretch(1)

        title_label = QLabel(title, self)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #808080; font-weight: bold; font-size: 13px;")
        layout.addWidget(title_label)

        msg_label = QLabel(message, self)
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setStyleSheet("color: #6b6b6b; font-style: italic;")
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)

        layout.addStretch(1)


class ConsoleView(QPlainTextEdit):
    """Read-only console that receives messages from the application logger."""

    _LEVEL_COLORS = {
        "INFO": "#d4d4d4",
        "DEBUG": "#808080",
        "WARNING": "#ce9178",
        "ERROR": "#f14c4c",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(2000)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

    def append_message(self, line):
        """Append a raw ``[LEVEL] text`` line, colored by level."""
        level = line.split("]")[0].lstrip("[").upper()
        color = self._LEVEL_COLORS.get(level, "#d4d4d4")
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.appendHtml('<span style="color:%s;">%s</span>' % (color, escaped))


class BottomPanel(QTabWidget):
    """The complete tabbed bottom panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)

        self.console = ConsoleView()

        for name, widget in (
            ("Explain", _PlaceholderTab("Explain")),
            ("Patch Assistant", _PlaceholderTab("Patch Assistant")),
            ("Calls", _PlaceholderTab("Calls")),
            ("Called By", _PlaceholderTab("Called By")),
            ("Graph", _PlaceholderTab("Graph")),
            ("Search", _PlaceholderTab("Search")),
            ("Console", self.console),
        ):
            self.addTab(widget, name)

        self.setCurrentWidget(self.console)
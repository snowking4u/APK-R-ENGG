"""Bottom panel: tabbed area below the editors.

Tabs: Explain, Patch Assistant, Calls, Called By, Graph, Search, Console

Phase 03 makes **Search** functional for Java sources: class names,
method names, package names and raw Java source text. Clicking a result
requests the corresponding file/line in the Java editor. The other tabs
remain untouched placeholders (their features belong to later phases).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton,
                               QTabWidget, QTreeWidget, QTreeWidgetItem,
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


class SearchView(QWidget):
    """Java search over the Phase 03 source index."""

    #: (path, line) requested by the user.
    open_requested = Signal(str, int)
    #: (query, scope, case_sensitive) submitted by the user.
    search_requested = Signal(str, str, bool)

    SCOPES = ("All", "Classes", "Methods", "Packages", "Source text")

    def __init__(self, parent=None):
        super().__init__(parent)

        self.input = QLineEdit(self)
        self.input.setPlaceholderText("Search class, method, package or Java text...")
        self.input.returnPressed.connect(self.start_search)

        self.scope = QComboBox(self)
        self.scope.addItems(self.SCOPES)

        self.case_sensitive = QCheckBox("Match case", self)

        self.button = QPushButton("Search", self)
        self.button.clicked.connect(self.start_search)

        controls = QHBoxLayout()
        controls.setContentsMargins(6, 6, 6, 2)
        controls.addWidget(self.input, 1)
        controls.addWidget(self.scope)
        controls.addWidget(self.case_sensitive)
        controls.addWidget(self.button)

        self.status = QLabel("No Java index loaded.", self)
        self.status.setObjectName("MutedLabel")

        self.results = QTreeWidget(self)
        self.results.setHeaderLabels(["Kind", "Symbol", "Location"])
        self.results.setRootIsDecorated(False)
        self.results.itemDoubleClicked.connect(self._on_double_click)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        layout.addWidget(self.results, 1)

    # ------------------------------------------------------------------ #
    def set_status(self, text):
        self.status.setText(text or "")

    def start_search(self):
        query = self.input.text().strip()
        if not query:
            self.set_status("Enter a search term.")
            return
        self.search_requested.emit(query, self.scope.currentText(),
                                   self.case_sensitive.isChecked())

    def show_results(self, hits):
        """Render ``[{"kind","name","path","line",...}]`` results."""
        self.results.clear()
        for hit in hits or []:
            line = hit.get("line", 1)
            location = hit.get("path", "")
            if hit.get("text"):
                location = "%s:%d  %s" % (location, line, hit["text"][:80])
            elif line:
                location = "%s:%d" % (location, line)
            item = QTreeWidgetItem([hit.get("kind", ""), hit.get("name", ""),
                                    location])
            item.setData(0, Qt.UserRole, (hit.get("path", ""), int(line or 1)))
            item.setToolTip(2, hit.get("path", ""))
            self.results.addTopLevelItem(item)
        count = self.results.topLevelItemCount()
        self.set_status("%d result(s)." % count if count else "No results.")

    def _on_double_click(self, item, _column=0):
        if item is None:
            return
        path, line = item.data(0, Qt.UserRole) or ("", 1)
        if path:
            self.open_requested.emit(path, int(line or 1))


class BottomPanel(QTabWidget):
    """The complete tabbed bottom panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)

        self.console = ConsoleView()
        self.search_view = SearchView()
        self.search_view.setObjectName("SearchView")

        for name, widget in (
            ("Explain", _PlaceholderTab("Explain")),
            ("Patch Assistant", _PlaceholderTab("Patch Assistant")),
            ("Calls", _PlaceholderTab("Calls")),
            ("Called By", _PlaceholderTab("Called By")),
            ("Graph", _PlaceholderTab("Graph")),
            ("Search", self.search_view),
            ("Console", self.console),
        ):
            self.addTab(widget, name)

        self.setCurrentWidget(self.console)

    # ------------------------------------------------------------------ #
    def show_search_tab(self):
        """Bring the Search tab to the front (used by Analysis > Search)."""
        self.setCurrentWidget(self.search_view)
        self.search_view.input.setFocus()

    def append_console(self, line):
        self.console.append_message(line)
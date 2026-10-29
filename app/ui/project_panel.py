"""Project Explorer panel.

Phase 01 shipped the placeholder tree. Phase 03 turns it into the real
navigational view of a decoded + decompiled project:

    PROJECT
      APK                  (name + size, never modified)
      Classes              (classes.dex, classes2.dex, ... discovered)
      Java                 (JADX output: packages -> classes -> methods)
      Resources
      Assets
      AndroidManifest.xml
      apktool.yml

Everything is generated dynamically from what is actually on disk - no
package name, class name or file is ever hard-coded.

Performance: Java *files* are listed eagerly (cheap), but their method
children are created lazily when a file item is expanded, so a project
with tens of thousands of classes stays responsive.
"""

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem

from app.core import logger
from app.core.smali_parser import method_display_name


class ProjectExplorer(QTreeWidget):
    """Dock content showing the loaded project tree."""

    #: Emitted with (java_file_path, line) when a Java node is activated.
    java_activated = Signal(str, int)
    #: Emitted with (smali_file_path, line) when a Smali node is activated.
    smali_activated = Signal(str, int)
    #: Context-menu requests: Java file -> matching Smali, and vice versa.
    locate_smali_requested = Signal(str)
    locate_java_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeWidget.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

        self._java_root = ""
        self._java_index = None
        self._smali_index = None
        self._items_by_path = {}
        self._smali_items_by_path = {}
        self._method_children_built = set()
        self._smali_method_children_built = set()

        self.itemExpanded.connect(self._on_item_expanded)
        self.itemClicked.connect(self._on_item_clicked)
        self.itemDoubleClicked.connect(self._on_item_clicked)
        self.customContextMenuRequested.connect(self._on_context_menu)

        self._build_placeholder_tree()

    # ------------------------------------------------------------------ #
    # Placeholder (Phase 01 contract: one root, first child selected)
    # ------------------------------------------------------------------ #
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
    # Public API (Phase 01 contract preserved)
    # ------------------------------------------------------------------ #
    def clear_tree(self):
        self.clear()
        self._reset_tracking()
        self._build_placeholder_tree()

    def set_project_name(self, name):
        if self.topLevelItemCount():
            self.topLevelItem(0).setText(0, name or "PROJECT")

    # ------------------------------------------------------------------ #
    # Phase 03: real project structure
    # ------------------------------------------------------------------ #
    def _reset_tracking(self):
        self._items_by_path = {}
        self._smali_items_by_path = {}
        self._method_children_built = set()
        self._smali_method_children_built = set()
        self._smali_index = None

    @staticmethod
    def _node(text, kind="", payload=None, expandable=False):
        item = QTreeWidgetItem([text])
        item.setData(0, Qt.UserRole, {"kind": kind, "payload": payload or {}})
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        if expandable:
            item.setChildIndicatorPolicy(
                QTreeWidgetItem.ShowIndicator)
        return item

    def build_project_tree(self, apk_path="", apk_size=None, dex_names=None,
                           resource_dir="", assets_dir="", manifest_path="",
                           apktool_yml_path="", package_name="", title="PROJECT"):
        """Rebuild the tree from a Phase 02 decode report's facts.

        Nothing is invented: empty values simply produce no child items.
        """
        self.clear()
        self._reset_tracking()

        root = self._node(title, "root")
        root.setExpanded(True)
        self.addTopLevelItem(root)

        first_child = None

        if apk_path:
            label = os.path.basename(apk_path)
            if apk_size:
                label += "  (%s)" % _format_size(apk_size)
            item = self._node(label, "apk", {"path": apk_path})
            root.addChild(item)
            first_child = first_child or item

        classes = self._node("Classes", "classes")
        for name in dex_names or []:
            classes.addChild(self._node(name, "dex", {"name": name}))
        if dex_names:
            classes.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        else:
            classes.setFlags(Qt.ItemIsEnabled)
        root.addChild(classes)
        first_child = first_child or classes

        java = self._node("Java", "java")
        java.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        root.addChild(java)
        first_child = first_child or java

        if resource_dir and os.path.isdir(resource_dir):
            root.addChild(self._node("Resources", "directory",
                                     {"path": resource_dir}))
        if assets_dir and os.path.isdir(assets_dir):
            root.addChild(self._node("Assets", "directory", {"path": assets_dir}))
        if manifest_path and os.path.isfile(manifest_path):
            root.addChild(self._node("AndroidManifest.xml", "manifest",
                                     {"path": manifest_path}))
        if apktool_yml_path and os.path.isfile(apktool_yml_path):
            root.addChild(self._node("apktool.yml", "manifest",
                                     {"path": apktool_yml_path}))
        if package_name:
            root.addChild(self._node(package_name, "package"))

        if first_child is not None:
            self.setCurrentItem(first_child)
        return root

    def set_java_index(self, index, source_root=""):
        """Populate (or clear) the Java section of the tree.

        ``index`` is an :class:`app.core.java_index.JavaIndex`; packages and
        class names are derived from the real directory structure.
        """
        java_item = self._java_item(create=True)
        if java_item is None:
            return 0

        self._java_index = index
        self._java_root = source_root or (index.root if index else "")
        self._items_by_path = {}
        self._method_children_built = set()

        if index is None or not index.sources:
            java_item.setText(0, "Java")
            java_item.setToolTip(0, "No Java sources available")
            return 0

        java_item.setText(0, "Java (%d)" % index.source_count)
        java_item.setToolTip(0, self._java_root)

        # Group files by their parent directory, then build package folders.
        directories = {}
        for source in index.sources:
            directory = os.path.dirname(source.path)
            directories.setdefault(directory, []).append(source)

        root_item = self._node(self._java_root or "sources", "java-root",
                               {"path": self._java_root})
        java_item.addChild(root_item)

        for directory in sorted(directories):
            self._add_directory_item(root_item, directory, directories[directory])
        root_item.setExpanded(True)

        logger.info("Java project tree updated (%d source file(s))"
                    % index.source_count)
        return index.source_count

    def _add_directory_item(self, parent, directory, sources):
        """Create (recursively) the package folder chain for one directory."""
        name = os.path.basename(directory) or os.path.basename(self._java_root)

        existing = None
        for index in range(parent.childCount()):
            child = parent.child(index)
            if child.data(0, Qt.UserRole).get("kind") == "package" and \
                    child.text(0) == name:
                existing = child
                break

        if existing is None:
            existing = self._node(name, "package",
                                 {"path": directory}, expandable=True)
            parent.addChild(existing)

        parent_directory = os.path.dirname(directory)
        if parent_directory and parent_directory != self._java_root and \
                os.path.commonpath([parent_directory, self._java_root]) == \
                self._java_root:
            self._add_directory_item(existing, parent_directory, [])

        for source in sorted(sources, key=lambda item: item.file_name):
            child = self._node(source.class_name or source.file_name, "java-file",
                               {"path": source.path,
                                "class": source.class_name,
                                "package": source.package},
                               expandable=True)
            child.setToolTip(0, source.path)
            existing.addChild(child)
            self._items_by_path[source.path] = child
        return existing

    def _java_item(self, create=False):
        root = self.topLevelItem(0)
        if root is None:
            return None
        for index in range(root.childCount()):
            child = root.child(index)
            if child.data(0, Qt.UserRole).get("kind") == "java":
                return child
        if not create:
            return None
        item = self._node("Java", "java")
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        root.addChild(item)
        return item

    # ------------------------------------------------------------------ #
    # Phase 04: real Smali tree
    # ------------------------------------------------------------------ #
    def set_smali_index(self, index, roots=None):
        """Populate (or clear) the Smali section from a SmaliIndex.

        Passing ``index=None`` with roots creates a lightweight loading
        placeholder while indexing runs in the background.
        """
        smali_item = self._smali_item(create=True)
        if smali_item is None:
            return 0

        smali_item.takeChildren()
        self._smali_items_by_path = {}
        self._smali_method_children_built = set()
        self._smali_index = index

        roots = [os.path.abspath(item) for item in
                 (roots or (getattr(index, "roots", []) if index else []) or [])
                 if item]

        if index is None:
            smali_item.setText(0, "Smali (indexing...)" if roots else "Smali")
            smali_item.setToolTip(
                0, "Smali index is being built" if roots
                else "No Smali sources available")
            for root in roots:
                smali_item.addChild(self._node(
                    os.path.basename(root) or root, "smali-root",
                    {"path": root}, expandable=True))
            smali_item.setExpanded(True)
            return 0

        smali_item.setText(0, "Smali (%d)" % index.file_count)
        smali_item.setToolTip(0, ", ".join(roots) if roots else "Smali sources")

        grouped = {}
        for source in index.files:
            root = source.smali_root or (roots[0] if len(roots) == 1 else "")
            grouped.setdefault(root, []).append(source)

        for root in roots:
            root_item = self._node(os.path.basename(root) or root, "smali-root",
                                   {"path": root}, expandable=True)
            root_item.setToolTip(0, root)
            smali_item.addChild(root_item)
            for source in sorted(grouped.get(root, []),
                                 key=lambda item: item.relative_path):
                self._add_smali_file(root_item, source)
            root_item.setExpanded(True)

        # Defensive: files whose root was not in the supplied list stay visible.
        for root, sources in grouped.items():
            if root in roots:
                continue
            root_item = self._node(os.path.basename(root) or "smali",
                                   "smali-root", {"path": root},
                                   expandable=True)
            smali_item.addChild(root_item)
            for source in sorted(sources, key=lambda item: item.relative_path):
                self._add_smali_file(root_item, source)
            root_item.setExpanded(True)

        smali_item.setExpanded(True)
        logger.info("Smali project tree updated (%d file(s))"
                    % index.file_count)
        return index.file_count

    def _smali_item(self, create=False):
        root = self.topLevelItem(0)
        if root is None:
            return None
        for position in range(root.childCount()):
            child = root.child(position)
            if child.data(0, Qt.UserRole).get("kind") == "smali":
                return child
        if not create:
            return None
        item = self._node("Smali", "smali")
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        insert_at = root.childCount()
        for position in range(root.childCount()):
            if root.child(position).data(0, Qt.UserRole).get("kind") in (
                    "java", "classes"):
                insert_at = position + 1
        root.insertChild(insert_at, item)
        return item

    def _add_smali_file(self, parent, source):
        relative = (source.relative_path or source.file_name).replace("\\", "/")
        parts = [part for part in relative.split("/") if part]
        folder = parent
        for part in parts[:-1]:
            child = self._find_child(folder, part, "smali-package")
            if child is None:
                child = self._node(part, "smali-package", {}, expandable=True)
                folder.addChild(child)
            folder = child

        item = self._node(os.path.basename(source.path), "smali-file",
                          {"path": source.path,
                           "class": source.class_name,
                           "descriptor": source.class_descriptor,
                           "root": source.smali_root,
                           "line": source.class_line},
                          expandable=True)
        item.setToolTip(0, source.path)
        folder.addChild(item)
        self._smali_items_by_path[source.path] = item
        return item

    @staticmethod
    def _find_child(parent, text, kind):
        for position in range(parent.childCount()):
            child = parent.child(position)
            data = child.data(0, Qt.UserRole) or {}
            if data.get("kind") == kind and child.text(0) == text:
                return child
        return None

    def select_smali_file(self, path):
        """Select (and reveal) a Smali file item; True when it was found."""
        item = self._smali_items_by_path.get(path)
        if item is None:
            return False
        self.setCurrentItem(item)
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()
        return True

    # ------------------------------------------------------------------ #
    # Interaction
    # ------------------------------------------------------------------ #
    def _on_item_expanded(self, item):
        data = item.data(0, Qt.UserRole) or {}
        kind = data.get("kind")
        path = data.get("payload", {}).get("path", "")
        if kind == "java-file":
            if path in self._method_children_built:
                return
            self._method_children_built.add(path)
            self._build_method_children(item, path)
        elif kind == "smali-file":
            if path in self._smali_method_children_built:
                return
            self._smali_method_children_built.add(path)
            self._build_smali_method_children(item, path)

    def _build_method_children(self, item, path):
        """Lazily add the methods/fields recorded for one Java file."""
        index = self._java_index
        if index is None:
            return
        source = index.get(path)
        if source is None:
            return

        for field in source.fields:
            child = self._node(field.get("name", ""), "java-field",
                               {"path": path, "line": field.get("line", 1)})
            child.setFlags(Qt.ItemIsEnabled)
            item.addChild(child)

        for method in source.methods:
            name = method.get("name", "")
            prefix = "()" if method.get("kind") == "method" else ""
            child = self._node("%s%s" % (name, prefix), "java-method",
                               {"path": path, "line": method.get("line", 1),
                                "method": name})
            child.setFlags(Qt.ItemIsEnabled)
            item.addChild(child)

    def _build_smali_method_children(self, item, path):
        """Lazily add parsed fields/methods for one Smali file."""
        index = self._smali_index
        if index is None:
            return
        source = index.get(path)
        if source is None:
            return
        if source.parse_error:
            child = self._node("Parse error: %s" % source.parse_error,
                               "smali-error")
            child.setFlags(Qt.ItemIsEnabled)
            item.addChild(child)
            return

        for field in source.fields:
            label = "%s: %s" % (field.name, field.readable_type)
            child = self._node(label, "smali-field",
                               {"path": path, "line": field.line,
                                "field": field.name})
            child.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.addChild(child)

        for method in source.methods:
            label = method.display_name or method.name or "<method>"
            child = self._node(label, "smali-method",
                               {"path": path, "line": method.start_line,
                                "method": method.name,
                                "descriptor": method.descriptor})
            child.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.addChild(child)

    def _on_item_clicked(self, item, _column=0):
        if item is None:
            return
        data = item.data(0, Qt.UserRole) or {}
        kind = data.get("kind")
        payload = data.get("payload") or {}

        if kind == "java-file":
            self.java_activated.emit(payload.get("path", ""), 1)
        elif kind in ("java-method", "java-field"):
            self.java_activated.emit(payload.get("path", ""),
                                     int(payload.get("line", 1) or 1))
        elif kind == "smali-file":
            self.smali_activated.emit(payload.get("path", ""),
                                      int(payload.get("line", 1) or 1))
        elif kind in ("smali-method", "smali-field"):
            self.smali_activated.emit(payload.get("path", ""),
                                      int(payload.get("line", 1) or 1))

    def _on_context_menu(self, position):
        item = self.itemAt(position)
        if item is None:
            return
        data = item.data(0, Qt.UserRole) or {}
        kind = data.get("kind")
        path = (data.get("payload") or {}).get("path", "")
        if not path:
            return

        menu = QMenu(self)
        if kind in ("java-file", "java-method", "java-field"):
            action = menu.addAction("Locate Smali")
            action.triggered.connect(
                lambda _checked=False, p=path: self.locate_smali_requested.emit(p))
        elif kind in ("smali-file", "smali-method", "smali-field"):
            action = menu.addAction("Locate Java")
            action.triggered.connect(
                lambda _checked=False, p=path: self.locate_java_requested.emit(p))
        else:
            return
        menu.exec(self.viewport().mapToGlobal(position))

    def select_java_file(self, path):
        """Select (and reveal) a Java file item; True when it was found."""
        item = self._items_by_path.get(path)
        if item is None:
            return False
        self.setCurrentItem(item)
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()
        return True


def _format_size(size):
    try:
        size = float(size)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return "%.0f %s" % (size, unit) if unit == "B" else "%.1f %s" % (size, unit)
        size /= 1024.0
    return "%.1f GB" % size
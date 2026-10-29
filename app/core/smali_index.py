"""Smali index, search, Java mapping and safe saving (Phase 04).

The index holds lightweight metadata parsed from every discovered Smali
file. File contents are only read while parsing and while searching text;
the full project is never loaded into memory at once.

Nothing here executes Smali, Java or any other project content.
"""

import os
import stat
import tempfile

from app.core import logger
from app.core.smali_discovery import (discover_smali_files, discover_smali_roots,
                                      root_for_path)
from app.core.smali_parser import (SmaliFile, java_name_to_descriptor,
                                   parse_smali_file)

#: Text search never reads more than this from a single file.
MAX_SEARCH_SIZE = 8 * 1024 * 1024  # 8 MiB


class SmaliIndex:
    """Searchable collection of :class:`SmaliFile` metadata entries."""

    def __init__(self, roots=None):
        self.roots = [os.path.abspath(item) for item in (roots or [])]
        self.files = []
        self.by_path = {}
        self.by_descriptor = {}
        self.by_class_name = {}
        self.by_simple_name = {}
        self.by_method = {}

    # -- construction ---------------------------------------------------- #
    def add(self, source):
        self.files.append(source)

    def finalize(self):
        self.by_path = {}
        self.by_descriptor = {}
        self.by_class_name = {}
        self.by_simple_name = {}
        self.by_method = {}
        for source in self.files:
            self.by_path[source.path] = source
            if source.class_descriptor:
                self.by_descriptor.setdefault(source.class_descriptor, []).append(source)
            if source.class_name:
                self.by_class_name.setdefault(source.class_name, []).append(source)
                self.by_simple_name.setdefault(source.simple_name, []).append(source)
            for method in source.methods:
                if method.name:
                    self.by_method.setdefault(method.name, []).append(
                        (source, method))
        return self

    # -- statistics ------------------------------------------------------ #
    @property
    def file_count(self):
        return len(self.files)

    @property
    def class_count(self):
        return len([item for item in self.files if item.class_descriptor])

    @property
    def method_count(self):
        return sum(len(source.methods) for source in self.files)

    @property
    def field_count(self):
        return sum(len(source.fields) for source in self.files)

    @property
    def parse_error_count(self):
        return len([item for item in self.files if item.parse_error])

    def summary(self):
        return {
            "smali_roots": len(self.roots),
            "smali_files": self.file_count,
            "smali_classes": self.class_count,
            "smali_methods": self.method_count,
            "smali_fields": self.field_count,
            "parse_errors": self.parse_error_count,
        }

    # -- lookups --------------------------------------------------------- #
    def get(self, path):
        return self.by_path.get(path)

    def find_by_descriptor(self, descriptor):
        return list(self.by_descriptor.get(descriptor, []))

    def find_by_class_name(self, name):
        return list(self.by_class_name.get(name, []))

    def find_by_simple_name(self, name):
        return list(self.by_simple_name.get(name, []))

    def find_method(self, name):
        return list(self.by_method.get(name, []))

    def __len__(self):
        return len(self.files)

    def __iter__(self):
        return iter(self.files)

    def __repr__(self):
        return "SmaliIndex(roots=%d, files=%d, methods=%d)" % (
            len(self.roots), self.file_count, self.method_count)


# ---------------------------------------------------------------------- #
# Building
# ---------------------------------------------------------------------- #
def build_smali_index(roots=None, files=None, progress=None):
    """Build a :class:`SmaliIndex` from real files. Never raises.

    ``progress(current, total)`` is optional and receives plain ints so the
    Qt worker and the tests can share this function.
    """
    logger.info("Smali discovery started")
    roots = [os.path.abspath(item) for item in (roots or []) if item]
    logger.info("Smali directories discovered: %d" % len(roots))

    if files is None:
        discovered = []
        for root in roots:
            discovered.extend(discover_smali_files(root))
    else:
        discovered = [os.path.abspath(item) for item in files]

    unique = []
    seen = set()
    for path in discovered:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)

    logger.info("Smali files discovered: %d" % len(unique))

    index = SmaliIndex(roots)
    total = len(unique)
    for position, path in enumerate(unique, 1):
        root = root_for_path(path, roots)
        try:
            index.add(parse_smali_file(path, root=root))
        except Exception as exc:  # defensive: one bad file must not stop all
            logger.error("Smali parse failed: %s (%s)" % (path, exc))
            index.add(SmaliFile(path=path, smali_root=root,
                                parse_error=str(exc)))
        if progress:
            progress(position, total)

    index.finalize()
    logger.info("Smali indexing completed")
    return index


def build_index_from_roots(base):
    """Convenience helper: discover roots below ``base`` and index them."""
    roots = discover_smali_roots(base)
    return build_smali_index(roots)


# ---------------------------------------------------------------------- #
# Search
# ---------------------------------------------------------------------- #
def search_smali(index, query, scope="All", case_sensitive=False, limit=200,
                 max_bytes=MAX_SEARCH_SIZE):
    """Search file names, classes, methods and Smali source text.

    Returns ``[{"kind", "name", "path", "line", "text", ...}]``. Only
    ``.smali`` files are ever read; no binary content is scanned.
    """
    results = []
    if index is None or not query:
        return results

    needle = query if case_sensitive else query.lower()

    def matches(text):
        haystack = text or ""
        return needle in (haystack if case_sensitive else haystack.lower())

    def add(kind, name, source, line, text=""):
        if len(results) >= limit:
            return False
        results.append({
            "kind": kind,
            "name": name,
            "path": source.path,
            "line": int(line or 1),
            "text": text,
            "class": source.class_name,
            "package": source.package_name,
        })
        return True

    scope = scope or "All"
    metadata = scope in ("All", "Smali", "Smali files", "Smali classes",
                         "Smali methods")
    text_scope = scope in ("All", "Smali", "Smali source text")

    for source in index.files:
        if len(results) >= limit:
            break
        if metadata:
            if scope in ("All", "Smali", "Smali files"):
                if matches(source.file_name) or matches(source.relative_path):
                    if not add("smali-file", source.file_name, source,
                               source.class_line):
                        break
            if scope in ("All", "Smali", "Smali classes"):
                if matches(source.class_name) or matches(source.class_descriptor):
                    if not add("smali-class", source.class_name or source.file_name,
                               source, source.class_line):
                        break
            if scope in ("All", "Smali", "Smali methods"):
                for method in source.methods:
                    if len(results) >= limit:
                        break
                    if matches(method.name) or matches(method.display_name) or \
                            matches(method.descriptor):
                        add("smali-method", method.display_name, source,
                            method.start_line)

    if text_scope and len(results) < limit:
        for source in index.files:
            if len(results) >= limit:
                break
            try:
                size = os.path.getsize(source.path)
            except OSError:
                continue
            if size > max_bytes:
                continue
            try:
                with open(source.path, "r", encoding="utf-8",
                          errors="replace") as handle:
                    for number, line in enumerate(handle, 1):
                        haystack = line if case_sensitive else line.lower()
                        if needle in haystack:
                            if not add("smali-text", source.file_name, source,
                                       number, line.strip()[:400]):
                                break
            except OSError as exc:
                logger.warning("Smali search skipped %s (%s)"
                               % (source.path, exc))
    return results[:limit]


# ---------------------------------------------------------------------- #
# Java <-> Smali mapping (exact only, never guessed)
# ---------------------------------------------------------------------- #
def find_smali_by_java(index, qualified_name):
    """Return every Smali file matching a Java class name/descriptor."""
    if index is None or not qualified_name:
        return []
    name = qualified_name.strip()
    descriptor = java_name_to_descriptor(name)
    matches = index.find_by_descriptor(descriptor)
    if not matches and not name.startswith("L"):
        matches = index.find_by_class_name(name)
    return matches


def find_java_by_smali(java_index, smali_file):
    """Return every Java source matching a :class:`SmaliFile` (exact)."""
    if java_index is None or smali_file is None:
        return []
    class_name = getattr(smali_file, "class_name", "") or ""
    if not class_name:
        return []
    by_qualified = getattr(java_index, "by_qualified", {}) or {}
    matches = list(by_qualified.get(class_name, []))
    if not matches:
        # Fall back to a linear exact-name lookup for non-finalized indexes.
        matches = [source for source in getattr(java_index, "sources", [])
                   if getattr(source, "qualified_name", "") == class_name]
    return matches


def find_java_by_class_name(java_index, class_name):
    """Return every Java source whose qualified name matches exactly."""
    if java_index is None or not class_name:
        return []
    by_qualified = getattr(java_index, "by_qualified", {}) or {}
    matches = list(by_qualified.get(class_name, []))
    if not matches:
        matches = [source for source in getattr(java_index, "sources", [])
                   if getattr(source, "qualified_name", "") == class_name]
    return matches


# ---------------------------------------------------------------------- #
# Safe saving
# ---------------------------------------------------------------------- #
def safe_write_smali(path, text, allowed_roots=None):
    """Atomically write Smali text inside an allowed decoded-project root.

    The original file is never truncated first: content is written to a
    temporary file in the same directory, flushed and then atomically
    replaced. On any failure the original file remains intact.

    Returns ``(ok, error)`` and never raises.
    """
    if not path:
        return False, "No Smali file path."
    if not str(path).lower().endswith(".smali"):
        return False, "Refusing to write a non-Smali file: %s" % path
    if not allowed_roots:
        return False, "No decoded-project Smali root is available."

    target = os.path.abspath(path)
    allowed = False
    for root in allowed_roots:
        if not root:
            continue
        root = os.path.abspath(root)
        try:
            if os.path.commonpath([target, root]) == root:
                allowed = True
                break
        except (OSError, ValueError):
            continue
    if not allowed:
        return False, "Refusing to write outside the decoded project: %s" % path

    directory = os.path.dirname(target)
    if not os.path.isdir(directory):
        return False, "Target directory does not exist: %s" % directory

    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".smali_", suffix=".tmp", dir=directory)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text if text is not None else "")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            mode = stat.S_IMODE(os.stat(target).st_mode)
            os.chmod(temporary, mode)
        except OSError:
            pass
        os.replace(temporary, target)
        temporary = None
        return True, ""
    except (OSError, UnicodeError, ValueError) as exc:
        return False, "Could not save Smali file: %s" % exc
    finally:
        if temporary and os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass

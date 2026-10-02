"""Lightweight Java source index (Phase 03).

JADX writes real ``.java`` files; this module builds a *lightweight* index
on top of them so the IDE can answer "which file holds this class/method?"
without ever loading whole projects into memory.

What is indexed per file
------------------------
``package``, the first ``class`` / ``interface`` / ``enum`` / ``record``
declaration, method-ish declarations (with line numbers), field-ish
declarations and ``import`` lines.

How it works
------------
Text is stripped of comments and string/char literals (length preserving,
so line numbers stay exact) and then matched with a handful of regular
expressions. This is deliberately **not** a Java compiler front end: it is
conservative, never raises on malformed input and prefers reporting
nothing over inventing a method. Brace depth is used so declarations are
only picked up at class-body level.

No decompiled code is ever executed, compiled or loaded.
"""

import bisect
import json
import os
import re

from app.core.logger import logger


INDEX_FILENAME = "java_index.json"

#: Files larger than this are indexed for metadata only (no method scan).
MAX_PARSE_SIZE = 2 * 1024 * 1024      # 2 MiB
#: Never read more than this per file while scanning text for search.
MAX_SEARCH_SIZE = 8 * 1024 * 1024      # 8 MiB

_SKIP_DIRS = {"resources", "sources_orig", "test", "tests", "__pycache__"}

# Words that can appear before "(" in a *statement*, never in a declaration.
_STATEMENT_WORDS = {
    "return", "new", "if", "else", "for", "while", "do", "switch", "case",
    "catch", "try", "finally", "throw", "throws", "assert", "break",
    "continue", "synchronized", "super", "this", "instanceof", "yield",
    "package", "import", "class", "interface", "enum", "record", "extends",
    "implements", "permits", "default",
}

#: Tokens that are modifiers, so they can never be the return type.
_NOT_A_TYPE = _STATEMENT_WORDS | {
    "public", "protected", "private", "static", "final", "abstract", "native",
    "transient", "volatile", "strictfp", "sealed",
}

_MODIFIERS = (
    "public", "protected", "private", "static", "final", "abstract", "native",
    "synchronized", "transient", "volatile", "strictfp", "default", "sealed",
)

_PACKAGE_RE = re.compile(r"(?m)^[ \t]*package[ \t]+([\w.$]+)[ \t]*;")
_IMPORT_RE = re.compile(r"(?m)^[ \t]*import[ \t]+(?:static[ \t]+)?([\w.$]+(?:\.\*)?)")
_TYPE_RE = re.compile(r"(?m)(?<![.\w$])(@?interface|class|enum|record)[ \t]+"
                      r"([A-Za-z_$][\w$]*)")

_MOD_HEAD = ("(?:(?:" + "|".join(_MODIFIERS) +
             r")\s+|@\w+(?:\s*\([^()]*\))?\s*)*")
_TYPE_TOKEN = r"[A-Za-z_$][\w$.]*(?:\s*<[^<>]*>)?(?:\s*\[\s*\])*"
_TYPE_PARAMS = r"(?:<[^<>]*(?:<[^<>]*>[^<>]*)*>[ \t\n]*)?"
_PARAMS = r"[^;{}()]*(?:\([^()]*\)[^;{}()]*)*(?:\([^()]*\)[^;{}()]*)*"

_METHOD_RE = re.compile(
    r"(?m)^[ \t]*(?P<head>" + _MOD_HEAD + r")"
    + _TYPE_PARAMS +
    r"(?P<ret>" + _TYPE_TOKEN + r")[ \t\n]+"
    r"(?P<name>[A-Za-z_$][\w$]*)[ \t]*\("
    r"(?P<params>" + _PARAMS + r")\)[ \t]*"
    r"(?P<tail>(?:throws[ \t\n]+[\w.$,\s]+?)?)[ \t]*(?P<end>\{|;)"
)

_CONSTRUCTOR_RE = re.compile(
    r"(?m)^[ \t]*(?P<head>(?:(?:" + "|".join(("public", "protected", "private")) +
    r")\s+)+)"
    r"(?P<name>[A-Za-z_$][\w$]*)[ \t]*\("
    r"(?P<params>" + _PARAMS + r")\)[ \t]*"
    r"(?P<tail>(?:throws[ \t\n]+[\w.$,\s]+?)?)[ \t]*\{"
)

_STATIC_INIT_RE = re.compile(
    r"(?m)^[ \t]*(?:(?:" + "|".join(_MODIFIERS) + r")\s+)*static[ \t]*\{"
)

_FIELD_RE = re.compile(
    r"(?m)^[ \t]*(?P<mods>(?:(?:public|protected|private|static|final|"
    r"volatile|transient)\s+)+)"
    + _TYPE_PARAMS +
    r"(?P<type>" + _TYPE_TOKEN + r")[ \t\n]+"
    r"(?P<name>[A-Za-z_$][\w$]*)[ \t]*"
    r"(?:=[^;{}]*)?;[ \t]*$"
)


# ---------------------------------------------------------------------- #
# Text helpers
# ---------------------------------------------------------------------- #
def strip_comments_and_strings(text):
    """Blank out comments and literals, preserving length and newlines."""
    if not text:
        return ""
    out = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        nxt = text[index + 1] if index + 1 < length else ""
        if char == "/" and nxt == "/":
            while index < length and text[index] != "\n":
                out.append(" ")
                index += 1
            continue
        if char == "/" and nxt == "*":
            out.append("  ")
            index += 2
            while index < length:
                if text[index] == "*" and index + 1 < length and text[index + 1] == "/":
                    out.append("  ")
                    index += 2
                    break
                out.append("\n" if text[index] == "\n" else " ")
                index += 1
            continue
        if char in ('"', "'"):
            quote = char
            if text[index:index + 3] == quote * 3:      # text block
                out.append("   ")
                index += 3
                while index < length and text[index:index + 3] != quote * 3:
                    out.append("\n" if text[index] == "\n" else " ")
                    index += 1
                out.append("   ")
                index += 3
                continue
            out.append(" ")
            index += 1
            while index < length:
                if text[index] == "\\":
                    out.append("  ")
                    index += 2
                    continue
                if text[index] == quote:
                    out.append(" ")
                    index += 1
                    break
                if text[index] == "\n":
                    break
                out.append(" ")
                index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _line_starts(text):
    starts = [0]
    for position, char in enumerate(text):
        if char == "\n":
            starts.append(position + 1)
    return starts


def _line_of(starts, position):
    return bisect.bisect_right(starts, position)


def _brace_depths(text):
    """Return the brace depth at the start of every line."""
    depths = []
    depth = 0
    for char in text:
        if char == "\n":
            depths.append(depth)
        elif char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
    depths.append(depth)
    return depths


def read_text(path):
    """Read a Java file defensively (never raises). Returns text or ''."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except (OSError, ValueError) as exc:
        logger.warning("Java source unreadable: %s (%s)" % (path, exc))
        return ""


# ---------------------------------------------------------------------- #
# Index entries
# ---------------------------------------------------------------------- #
class JavaSourceInfo:
    """Metadata extracted from a single ``.java`` file."""

    __slots__ = ("path", "package", "class_name", "class_kind",
                 "class_declared", "methods", "fields", "imports",
                 "line_count", "source_size", "modified", "parse_error")

    def __init__(self, path=""):
        self.path = path
        self.package = ""
        self.class_name = ""
        self.class_kind = "class"
        self.class_declared = False
        self.methods = []       # [{"name": str, "line": int, "kind": str}]
        self.fields = []        # [{"name": str, "line": int}]
        self.imports = []
        self.line_count = 0
        self.source_size = 0
        self.modified = 0.0
        self.parse_error = ""

    # -- helpers --------------------------------------------------------- #
    @property
    def file_name(self):
        return os.path.basename(self.path)

    @property
    def qualified_name(self):
        if self.package and self.class_name:
            return "%s.%s" % (self.package, self.class_name)
        return self.class_name or self.file_name

    @property
    def method_names(self):
        return [item.get("name", "") for item in self.methods]

    def method(self, name):
        """Return the first recorded method dict called ``name``."""
        for item in self.methods:
            if item.get("name") == name:
                return item
        return None

    def to_dict(self):
        return {
            "path": self.path,
            "package": self.package,
            "class_name": self.class_name,
            "class_kind": self.class_kind,
            "class_declared": self.class_declared,
            "methods": [dict(item) for item in self.methods],
            "fields": [dict(item) for item in self.fields],
            "imports": list(self.imports),
            "line_count": self.line_count,
            "source_size": self.source_size,
            "modified": self.modified,
            "parse_error": self.parse_error,
        }

    @classmethod
    def from_dict(cls, data):
        info = cls(data.get("path", ""))
        info.package = data.get("package", "") or ""
        info.class_name = data.get("class_name", "") or ""
        info.class_kind = data.get("class_kind", "class") or "class"
        info.class_declared = bool(data.get("class_declared", False))
        info.methods = [dict(item) for item in data.get("methods", []) or []]
        info.fields = [dict(item) for item in data.get("fields", []) or []]
        info.imports = list(data.get("imports", []) or [])
        info.line_count = int(data.get("line_count", 0) or 0)
        info.source_size = int(data.get("source_size", 0) or 0)
        info.modified = float(data.get("modified", 0.0) or 0.0)
        info.parse_error = data.get("parse_error", "") or ""
        return info

    def __repr__(self):
        return "JavaSourceInfo(%s, package=%r, methods=%d)" % (
            self.file_name, self.package, len(self.methods))


# ---------------------------------------------------------------------- #
# Parsing
# ---------------------------------------------------------------------- #
def parse_java_source(path, text=None, root=""):
    """Parse one Java file into a :class:`JavaSourceInfo`. Never raises."""
    info = JavaSourceInfo(path)

    try:
        if text is None:
            text = read_text(path)
        try:
            stat = os.stat(path)
            info.source_size = stat.st_size
            info.modified = stat.st_mtime
        except OSError:
            info.source_size = len(text or "")

        if not text:
            info.class_name = os.path.splitext(os.path.basename(path))[0]
            return info

        info.line_count = text.count("\n") + 1
        clean = strip_comments_and_strings(text)
        starts = _line_starts(clean)
        depths = _brace_depths(clean)

        match = _PACKAGE_RE.search(clean)
        if match:
            info.package = match.group(1)

        match = _TYPE_RE.search(clean)
        if match:
            info.class_kind = "interface" if match.group(1).startswith("@") \
                else match.group(1)
            info.class_name = match.group(2)
            info.class_declared = True
        else:
            # Not declared in the file (unusual decompiled output): fall back
            # to the file name and flag it as not detected.
            info.class_name = os.path.splitext(os.path.basename(path))[0]

        for found in _IMPORT_RE.finditer(clean):
            name = found.group(1)
            if name and name not in info.imports:
                info.imports.append(name)

        info.methods = _extract_methods(clean, starts, depths, info.class_name)
        info.fields = _extract_fields(clean, starts, depths, info.methods)
    except Exception as exc:  # malformed source must never crash the IDE
        info.parse_error = str(exc)
        logger.warning("Java parse failed for %s (%s)" % (path, exc))

    return info


def _extract_methods(clean, starts, depths, class_name):
    """Return conservative method/constructor records for one file."""
    methods = []
    seen = set()

    for match in _METHOD_RE.finditer(clean):
        name = match.group("name")
        ret = match.group("ret").strip()
        head = (match.group("head") or "").strip()
        if not name or name in _STATEMENT_WORDS:
            continue
        if ret.split("<")[0].strip() in _NOT_A_TYPE:
            continue
        if "." in ret.split("<")[0].strip():
            # ``a.b.c name(...)`` is far more likely an expression than a
            # declaration; JADX never emits it for methods.
            continue
        if "(" in match.group("head") or ")" in ret:
            continue
        if not (head or ret):
            continue
        line = _line_of(starts, match.start()) + 1
        if depths[min(line - 1, len(depths) - 1)] < 1:
            continue
        key = (name, line)
        if key in seen:
            continue
        seen.add(key)
        methods.append({"name": name, "line": line, "kind": "method"})

    for match in _CONSTRUCTOR_RE.finditer(clean):
        name = match.group("name")
        if not name or name in _STATEMENT_WORDS:
            continue
        if class_name and name != class_name:
            continue
        line = _line_of(starts, match.start()) + 1
        if depths[min(line - 1, len(depths) - 1)] < 1:
            continue
        key = (name, line)
        if key in seen:
            continue
        seen.add(key)
        methods.append({"name": name, "line": line, "kind": "constructor"})

    for match in _STATIC_INIT_RE.finditer(clean):
        line = _line_of(starts, match.start()) + 1
        if depths[min(line - 1, len(depths) - 1)] < 1:
            continue
        key = ("<clinit>", line)
        if key in seen:
            continue
        seen.add(key)
        methods.append({"name": "<clinit>", "line": line, "kind": "static-init"})

    methods.sort(key=lambda item: item["line"])
    return methods


def _extract_fields(clean, starts, depths, methods):
    """Return conservative field records for class-body declarations."""
    fields = []
    seen = set()
    method_lines = {item["line"] for item in methods}

    for match in _FIELD_RE.finditer(clean):
        line = _line_of(starts, match.start()) + 1
        if line in method_lines:
            continue
        # Only the outermost class body (depth 1) declares top-level fields.
        if depths[min(line - 1, len(depths) - 1)] != 1:
            continue
        name = match.group("name")
        if not name or name in _STATEMENT_WORDS:
            continue
        if name in seen:
            continue
        seen.add(name)
        fields.append({"name": name, "line": line})

    fields.sort(key=lambda item: item["line"])
    return fields


# ---------------------------------------------------------------------- #
# Discovery
# ---------------------------------------------------------------------- #
def discover_java_sources(root, skip_dirs=_SKIP_DIRS):
    """Discover every ``.java`` file below ``root`` (lazily, on demand).

    Returns a sorted list of absolute paths. Never raises.
    """
    if not root or not os.path.isdir(root):
        return []
    found = []
    for current, directories, files in os.walk(root):
        directories[:] = sorted(name for name in directories
                                if name not in skip_dirs
                                and not name.startswith("."))
        for name in sorted(files):
            if name.lower().endswith(".java"):
                found.append(os.path.join(current, name))
    return found


def find_java_source_root(decompiled_dir):
    """Locate the directory that actually holds the generated Java sources.

    JADX normally writes to ``<out>/sources``; the structure is verified
    instead of assumed. Falls back to any sub-directory that contains
    ``.java`` files. Returns ``""`` when nothing was generated.
    """
    if not decompiled_dir or not os.path.isdir(decompiled_dir):
        return ""

    candidates = [os.path.join(decompiled_dir, "sources"),
                  os.path.join(decompiled_dir, "java")]
    for candidate in candidates:
        if os.path.isdir(candidate) and discover_java_sources(candidate):
            return candidate

    try:
        entries = sorted(os.listdir(decompiled_dir))
    except OSError:
        return ""
    for name in entries:
        candidate = os.path.join(decompiled_dir, name)
        if os.path.isdir(candidate) and name != "resources":
            if discover_java_sources(candidate):
                return candidate
    return ""


# ---------------------------------------------------------------------- #
# Index
# ---------------------------------------------------------------------- #
class JavaIndex:
    """A searchable collection of :class:`JavaSourceInfo` entries."""

    def __init__(self, root=""):
        self.root = root or ""
        self.sources = []
        self.by_path = {}
        self.by_class = {}
        self.by_qualified = {}
        self.by_method = {}

    # -- construction ---------------------------------------------------- #
    def add(self, source):
        self.sources.append(source)

    def finalize(self):
        """(Re)build the lookup dictionaries. Safe to call repeatedly."""
        self.by_path = {}
        self.by_class = {}
        self.by_qualified = {}
        self.by_method = {}
        for source in self.sources:
            self.by_path[source.path] = source
            if source.class_name:
                self.by_class.setdefault(source.class_name, []).append(source)
            if source.qualified_name:
                self.by_qualified.setdefault(source.qualified_name, []).append(source)
            for item in source.methods:
                self.by_method.setdefault(item.get("name", ""), []).append(
                    (source, item.get("line", 1)))
        return self

    # -- statistics ------------------------------------------------------ #
    @property
    def source_count(self):
        return len(self.sources)

    @property
    def method_count(self):
        return sum(len(source.methods) for source in self.sources)

    @property
    def field_count(self):
        return sum(len(source.fields) for source in self.sources)

    @property
    def package_count(self):
        return len({source.package for source in self.sources if source.package})

    def summary(self):
        return {
            "java_sources": self.source_count,
            "java_methods": self.method_count,
            "java_fields": self.field_count,
            "java_packages": self.package_count,
            "parse_errors": len([s for s in self.sources if s.parse_error]),
        }

    # -- lookups --------------------------------------------------------- #
    def get(self, path):
        return self.by_path.get(path)

    def classes(self):
        return [source.class_name for source in self.sources if source.class_name]

    def packages(self):
        return sorted({source.package for source in self.sources if source.package})

    def find_class(self, name):
        """Return the index entry for a class (simple or qualified name)."""
        if not name:
            return None
        for source in self.sources:
            if source.qualified_name == name or source.class_name == name:
                return source
        return None

    def find_method(self, name, class_name=""):
        """Return ``(source, method_dict)`` for a method name."""
        if not name:
            return None
        candidates = self.by_method.get(name) or []
        if class_name:
            for source, line in candidates:
                if source.class_name == class_name or \
                        source.qualified_name == class_name:
                    return source, {"name": name, "line": line, "kind": "method"}
        if candidates:
            source, line = candidates[0]
            return source, {"name": name, "line": line, "kind": "method"}
        return None

    def packages_path(self):
        return [os.path.join(self.root, *package.split("."))
                for package in self.packages()] if self.root else []

    # -- persistence ----------------------------------------------------- #
    def to_dict(self):
        return {
            "version": 1,
            "root": self.root,
            "sources": [source.to_dict() for source in self.sources],
        }

    @classmethod
    def from_dict(cls, data):
        index = cls(data.get("root", ""))
        for item in data.get("sources", []) or []:
            index.add(JavaSourceInfo.from_dict(item))
        return index.finalize()

    def save(self, path):
        """Persist the index as JSON (best effort, never raises)."""
        if not path:
            return False
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            temporary = path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(self.to_dict(), handle)
            if os.path.exists(path):
                os.remove(path)
            os.replace(temporary, path)
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Java index cache not written: %s" % exc)
            return False

    @classmethod
    def load(cls, path):
        """Load a cached index. Returns ``None`` when unavailable."""
        if not path or not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Java index cache unreadable: %s" % exc)
            return None
        try:
            return cls.from_dict(data)
        except Exception as exc:
            logger.warning("Java index cache invalid: %s" % exc)
            return None

    def stale_sources(self):
        """Return entries whose file changed since the index was built."""
        stale = []
        for source in self.sources:
            try:
                stat = os.stat(source.path)
            except OSError:
                continue
            if int(stat.st_size) != int(source.source_size) or \
                    abs(stat.st_mtime - source.modified) > 1:
                stale.append(source)
        return stale

    def __len__(self):
        return len(self.sources)

    def __iter__(self):
        return iter(self.sources)

    def __repr__(self):
        return "JavaIndex(root=%r, sources=%d, methods=%d)" % (
            self.root, self.source_count, self.method_count)


def build_index(root, files=None, progress=None):
    """Build a :class:`JavaIndex` for the Java sources below ``root``.

    ``progress(current, total)`` is optional and called with plain ints so
    both the Qt worker and the tests can use it. Never raises.
    """
    index = JavaIndex(root)
    paths = list(files) if files else discover_java_sources(root)

    total = len(paths)
    for position, path in enumerate(paths, 1):
        try:
            if os.path.getsize(path) > MAX_PARSE_SIZE:
                source = JavaSourceInfo(path)
                source.class_name = os.path.splitext(os.path.basename(path))[0]
                source.parse_error = "file too large for parsing"
            else:
                source = parse_java_source(path, root=root)
            index.add(source)
        except OSError as exc:
            logger.warning("Could not index %s (%s)" % (path, exc))
        if progress:
            progress(position, total)

    return index.finalize()


def refresh_index(index, root=None):
    """Re-parse only the entries that changed since the index was built."""
    root = root or index.root
    updated = JavaIndex(root)
    stale_paths = {source.path for source in index.stale_sources()}
    missing = []

    for source in index.sources:
        if source.path in stale_paths:
            if not os.path.isfile(source.path):
                missing.append(source.path)
                continue
            updated.add(parse_java_source(source.path, root=root))
        else:
            updated.add(source)

    if missing:
        logger.info("Java index dropped %d missing source file(s)" % len(missing))
    return updated.finalize()


# ---------------------------------------------------------------------- #
# Search
# ---------------------------------------------------------------------- #
def search_index(index, query, limit=200):
    """Search class names, method names and packages in the index.

    Returns ``[{"kind", "name", "package", "path", "line"}]``. Never
    touches file contents, so it is fast even for large projects.
    """
    results = []
    if not index or not query:
        return results

    needle = query.lower()
    for source in index.sources:
        if len(results) >= limit:
            break
        if needle in (source.class_name or "").lower():
            results.append({"kind": "class", "name": source.class_name,
                            "package": source.package, "path": source.path,
                            "line": 1})
        elif source.package and needle in source.package.lower():
            results.append({"kind": "package", "name": source.package,
                            "package": source.package, "path": source.path,
                            "line": 1})
        for item in source.methods:
            if len(results) >= limit:
                break
            if needle in (item.get("name", "")).lower():
                results.append({"kind": "method", "name": item.get("name"),
                                "package": source.package, "path": source.path,
                                "line": item.get("line", 1)})
    return results[:limit]


def search_text(index, query, limit=200, case_sensitive=False,
                max_files=None, max_bytes=MAX_SEARCH_SIZE):
    """Search the Java source *text* of every indexed file.

    Returns ``[{"kind": "text", "name": <file name>, "package", "path",
    "line", "text"}]``. Files are streamed line by line and are never kept
    in memory; oversized files are skipped.
    """
    results = []
    if not index or not query:
        return results

    needle = query if case_sensitive else query.lower()
    scanned = 0
    for source in index.sources:
        if len(results) >= limit:
            break
        if max_files is not None and scanned >= max_files:
            break
        if source.source_size and source.source_size > max_bytes:
            continue
        scanned += 1
        try:
            with open(source.path, "r", encoding="utf-8", errors="replace") as handle:
                for number, line in enumerate(handle, 1):
                    haystack = line if case_sensitive else line.lower()
                    if needle in haystack:
                        results.append({
                            "kind": "text",
                            "name": source.file_name,
                            "package": source.package,
                            "path": source.path,
                            "line": number,
                            "text": line.strip()[:400],
                        })
                        if len(results) >= limit:
                            break
        except OSError as exc:
            logger.warning("Java search skipped %s (%s)" % (source.path, exc))
    return results[:limit]
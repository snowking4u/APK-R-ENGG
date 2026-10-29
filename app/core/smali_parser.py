"""Lightweight Smali source model and parser (Phase 04).

The parser is deliberately small: it recognises the structural directives
that the IDE needs for navigation (``.class``, ``.super``, ``.implements``,
``.source``, ``.field``, ``.method`` / ``.end method``) and ignores every
instruction it does not understand. Malformed input must never raise.

No Smali content is executed, compiled or loaded. This is static text
inspection only.
"""

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

PRIMITIVE_NAMES = {
    "V": "void",
    "Z": "boolean",
    "B": "byte",
    "S": "short",
    "C": "char",
    "I": "int",
    "J": "long",
    "F": "float",
    "D": "double",
}

_CLASS_DESCRIPTOR_RE = re.compile(r"L[^;\s]+;")
_FIELD_DECL_RE = re.compile(
    r"(?P<name>[\w$<>-]+):(?P<desc>\[*(?:L[^;\s]+;|[ZBSCIJFDV]))"
)
_METHOD_DECL_RE = re.compile(
    r"^(?P<pre>.*?)(?P<name>[^\s(]+)\s*"
    r"\((?P<params>[^)]*)\)\s*(?P<ret>\S*)"
)
_SOURCE_RE = re.compile(r'"([^"]*)"')


# ---------------------------------------------------------------------- #
# Descriptor helpers
# ---------------------------------------------------------------------- #
def descriptor_to_name(descriptor):
    """Convert a Smali type descriptor to a readable name.

    ``Lcom/example/MainActivity;`` -> ``com.example.MainActivity``
    ``[Ljava/lang/String;``       -> ``java.lang.String[]``
    ``I``                         -> ``int``

    The original descriptor is never modified by callers; this function is
    purely a display helper.
    """
    text = (descriptor or "").strip()
    if not text:
        return ""
    if text.startswith("["):
        return descriptor_to_name(text[1:]) + "[]"
    if text.startswith("L") and text.endswith(";"):
        return text[1:-1].replace("/", ".")
    return PRIMITIVE_NAMES.get(text, text)


def java_name_to_descriptor(name):
    """Convert ``com.example.MainActivity`` to its Smali class descriptor."""
    text = (name or "").strip()
    if not text:
        return ""
    if text.startswith("L") and text.endswith(";"):
        return text
    return "L" + text.replace(".", "/") + ";"


def split_method_descriptor(descriptor):
    """Split ``(Landroid/os/Bundle;)V`` into parameter and return types."""
    text = (descriptor or "").strip()
    if not text.startswith("("):
        return [], ""
    end = text.find(")")
    if end < 0:
        return [], ""
    return _split_type_descriptors(text[1:end]), text[end + 1:]


def _split_type_descriptors(text):
    result = []
    index = 0
    length = len(text)
    while index < length:
        start = index
        while index < length and text[index] == "[":
            index += 1
        if index < length and text[index] == "L":
            end = text.find(";", index)
            if end < 0:
                result.append(text[start:])
                break
            index = end + 1
        elif index < length:
            index += 1
        result.append(text[start:index])
    return result


def method_display_name(name, descriptor):
    """Human-readable method signature for the project tree."""
    params, _return = split_method_descriptor(descriptor)
    readable = ", ".join(descriptor_to_name(item) for item in params)
    return "%s(%s)" % (name or "", readable)


# ---------------------------------------------------------------------- #
# Models
# ---------------------------------------------------------------------- #
@dataclass
class SmaliField:
    name: str = ""
    descriptor: str = ""
    access_flags: str = ""
    line: int = 0

    @property
    def readable_type(self):
        return descriptor_to_name(self.descriptor)

    def to_dict(self):
        return {
            "name": self.name,
            "descriptor": self.descriptor,
            "access_flags": self.access_flags,
            "line": self.line,
        }


@dataclass
class SmaliMethod:
    name: str = ""
    descriptor: str = ""
    access_flags: str = ""
    start_line: int = 0
    end_line: int = 0

    @property
    def display_name(self):
        return method_display_name(self.name, self.descriptor)

    @property
    def parameter_descriptors(self):
        params, _return = split_method_descriptor(self.descriptor)
        return params

    def to_dict(self):
        return {
            "name": self.name,
            "descriptor": self.descriptor,
            "access_flags": self.access_flags,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


@dataclass
class SmaliFile:
    path: str = ""
    relative_path: str = ""
    smali_root: str = ""
    class_descriptor: str = ""
    class_name: str = ""
    package_name: str = ""
    superclass: str = ""
    interfaces: List[str] = field(default_factory=list)
    source_name: str = ""
    fields: List[SmaliField] = field(default_factory=list)
    methods: List[SmaliMethod] = field(default_factory=list)
    class_line: int = 1
    line_count: int = 0
    parse_error: str = ""

    @property
    def file_name(self):
        return os.path.basename(self.path)

    @property
    def simple_name(self):
        if self.class_name:
            return self.class_name.rsplit(".", 1)[-1]
        return os.path.splitext(self.file_name)[0]

    @property
    def qualified_name(self):
        if self.class_name:
            return self.class_name
        return os.path.splitext(self.relative_path or self.file_name)[0].replace(
            "\\", "/").replace("/", ".")

    def method(self, name, descriptor=""):
        for item in self.methods:
            if item.name == name and (not descriptor or item.descriptor == descriptor):
                return item
        return None

    def to_dict(self):
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "smali_root": self.smali_root,
            "class_descriptor": self.class_descriptor,
            "class_name": self.class_name,
            "package_name": self.package_name,
            "superclass": self.superclass,
            "interfaces": list(self.interfaces),
            "source_name": self.source_name,
            "fields": [item.to_dict() for item in self.fields],
            "methods": [item.to_dict() for item in self.methods],
            "class_line": self.class_line,
            "line_count": self.line_count,
            "parse_error": self.parse_error,
        }


# ---------------------------------------------------------------------- #
# Reading
# ---------------------------------------------------------------------- #
def read_smali_text(path, strict=True):
    """Read a Smali file as UTF-8.

    Returns ``(text, error)``. On decoding/IO failure ``text`` is ``None``
    and ``error`` explains the problem. The original file is never touched.
    A leading UTF-8 BOM is stripped from the returned text.
    """
    try:
        with open(path, "r", encoding="utf-8",
                  errors="strict" if strict else "replace",
                  newline="") as handle:
            text = handle.read()
    except UnicodeDecodeError as exc:
        return None, "File is not valid UTF-8: %s" % exc
    except (OSError, ValueError) as exc:
        return None, "Cannot read file: %s" % exc
    if text.startswith("\ufeff"):
        text = text[1:]
    return text, ""


# ---------------------------------------------------------------------- #
# Parsing
# ---------------------------------------------------------------------- #
def parse_smali_source(text, path="", relative_path="", root="", text_error=""):
    """Parse Smali text into a :class:`SmaliFile`. Never raises."""
    info = SmaliFile(path=path, relative_path=relative_path or os.path.basename(path),
                     smali_root=root)
    try:
        if text is None:
            info.parse_error = text_error or "Source unavailable"
            info.class_name = os.path.splitext(os.path.basename(path))[0]
            return info

        info.line_count = len(text.splitlines())
        current_method = None

        for number, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith(".method"):
                if current_method is not None:
                    current_method.end_line = max(current_method.start_line,
                                                  number - 1)
                    info.methods.append(current_method)
                    current_method = None
                current_method = _parse_method_declaration(line, number)
                continue

            if line.startswith(".end method"):
                if current_method is not None:
                    current_method.end_line = number
                    info.methods.append(current_method)
                    current_method = None
                continue

            if current_method is not None:
                # Instructions inside a method are intentionally ignored.
                continue

            if line.startswith(".class"):
                info.class_line = number
                descriptor = _first_class_descriptor(line)
                if descriptor:
                    info.class_descriptor = descriptor
                    info.class_name = descriptor_to_name(descriptor)
                    if "." in info.class_name:
                        info.package_name = info.class_name.rsplit(".", 1)[0]
                continue

            if line.startswith(".super"):
                info.superclass = _first_class_descriptor(line)
                continue

            if line.startswith(".implements"):
                descriptor = _first_class_descriptor(line)
                if descriptor and descriptor not in info.interfaces:
                    info.interfaces.append(descriptor)
                continue

            if line.startswith(".source"):
                match = _SOURCE_RE.search(line)
                info.source_name = match.group(1) if match else \
                    line[len(".source"):].strip()
                continue

            if line.startswith(".field"):
                parsed = _parse_field_declaration(line, number)
                if parsed is not None:
                    info.fields.append(parsed)
                continue

        if current_method is not None:
            current_method.end_line = max(current_method.start_line,
                                          info.line_count or current_method.start_line)
            info.methods.append(current_method)

        if not info.class_name:
            info.class_name = os.path.splitext(os.path.basename(path))[0]
    except Exception as exc:  # malformed input must never crash the IDE
        info.parse_error = str(exc)

    return info


def parse_smali_file(path, root="", relative_path=None, text=None):
    """Read and parse one Smali file. Never raises."""
    if relative_path is None:
        try:
            relative_path = os.path.relpath(path, root) if root else os.path.basename(path)
        except (OSError, ValueError):
            relative_path = os.path.basename(path)

    if text is None:
        text, error = read_smali_text(path)
        return parse_smali_source(text, path=path, relative_path=relative_path,
                                  root=root, text_error=error)
    return parse_smali_source(text, path=path, relative_path=relative_path,
                              root=root)


def _first_class_descriptor(line):
    match = _CLASS_DESCRIPTOR_RE.search(line or "")
    return match.group(0) if match else ""


def _parse_method_declaration(line, number):
    declaration = line[len(".method"):].strip()
    match = _METHOD_DECL_RE.match(declaration)
    if not match:
        return SmaliMethod(name="", descriptor="", access_flags="",
                           start_line=number, end_line=number)
    name = match.group("name")
    descriptor = "(%s)%s" % (match.group("params"), match.group("ret"))
    return SmaliMethod(
        name=name,
        descriptor=descriptor,
        access_flags=(match.group("pre") or "").strip(),
        start_line=number,
        end_line=number,
    )


def _parse_field_declaration(line, number):
    declaration = line[len(".field"):].strip()
    match = _FIELD_DECL_RE.search(declaration)
    if not match:
        return None
    return SmaliField(
        name=match.group("name"),
        descriptor=match.group("desc"),
        access_flags=declaration[:match.start()].strip(),
        line=number,
    )

"""Dynamic Smali discovery (Phase 04).

Smali roots are discovered from the real decoded project structure instead
of assuming a single ``smali/`` directory. Apktool may produce::

    smali/
    smali_classes2/
    smali_classes3/
    smali_classes4/
    ...

Every matching directory is included, and every ``*.smali`` file below it
is discovered recursively. No discovered file is ever executed.
"""

import os
import re

_SMALI_ROOT_RE = re.compile(r"^smali(?:_classes\d+)?$", re.IGNORECASE)


def is_smali_root_name(name):
    """True when ``name`` is a conventional Apktool Smali directory name."""
    return bool(_SMALI_ROOT_RE.match(name or ""))


def _natural_root_key(path):
    name = os.path.basename(path)
    match = re.search(r"(\d+)$", name)
    number = int(match.group(1)) if match else 0
    if name.lower() == "smali":
        return (0, 0, name.lower())
    return (1, number, name.lower())


def discover_smali_roots(base):
    """Return all Smali root directories below ``base``.

    ``base`` may be a decoded project directory (``.../decoded``) or a
    workspace directory that contains ``decoded/``. Returns a sorted list of
    absolute paths. Never raises.
    """
    if not base or not os.path.isdir(base):
        return []

    base = os.path.abspath(base)
    if is_smali_root_name(os.path.basename(base)) and discover_smali_files(base):
        return [base]

    decoded = os.path.join(base, "decoded")
    if os.path.isdir(decoded):
        roots = _roots_in(decoded)
        if roots:
            return roots

    return _roots_in(base)


def _roots_in(directory):
    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        return []

    roots = []
    for entry in entries:
        candidate = os.path.join(directory, entry)
        if not os.path.isdir(candidate):
            continue
        if is_smali_root_name(entry):
            roots.append(os.path.abspath(candidate))
        elif entry.lower().startswith("smali") and discover_smali_files(candidate):
            # Tolerate non-standard names such as smali_extra.
            roots.append(os.path.abspath(candidate))
    roots.sort(key=_natural_root_key)
    return roots


def discover_smali_files(root):
    """Discover every ``*.smali`` file below ``root`` (recursive, sorted)."""
    if not root or not os.path.isdir(root):
        return []
    found = []
    for current, directories, files in os.walk(root):
        directories[:] = sorted(name for name in directories
                                if not name.startswith("."))
        for name in sorted(files):
            if name.lower().endswith(".smali"):
                found.append(os.path.join(current, name))
    return found


def find_decoded_dir(path):
    """Resolve the directory that actually contains Smali roots.

    Accepts a decoded directory, a workspace containing ``decoded/`` or a
    single Smali root. Returns ``""`` when nothing usable is found.
    """
    if not path or not os.path.isdir(path):
        return ""
    if discover_smali_roots(path):
        base = os.path.abspath(path)
        if is_smali_root_name(os.path.basename(base)):
            return os.path.dirname(base)
        decoded = os.path.join(base, "decoded")
        if os.path.isdir(decoded) and discover_smali_roots(decoded):
            return os.path.abspath(decoded)
        return base
    return ""


def root_for_path(path, roots):
    """Return the most specific root containing ``path`` (or ``""``)."""
    target = os.path.abspath(path)
    best = ""
    for root in roots or []:
        root = os.path.abspath(root)
        try:
            if os.path.commonpath([target, root]) == root:
                if len(root) > len(best):
                    best = root
        except (OSError, ValueError):
            continue
    return best

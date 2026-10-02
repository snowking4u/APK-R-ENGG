"""DEX discovery and safe extraction (Phase 03).

APKs may contain several DEX files (``classes.dex``, ``classes2.dex``,
``classes3.dex``, ...). JADX must receive *every* discovered DEX file, so
this module is responsible for finding them and - when the DEX files only
exist inside the APK container - extracting read-only copies into the
generated project workspace.

Security
--------
The APK is untrusted input, therefore entry names coming out of the ZIP
container are **never** used as filesystem paths and never passed to a
subprocess before being validated against the strict
``classes[N].dex`` pattern (:data:`DEX_NAME_PATTERN`). Names containing
path separators, ``..`` or shell metacharacters are rejected outright,
which also removes any shell-injection surface.

Nothing extracted here is ever executed; DEX files are only fed to JADX as
data, and the original APK is opened read-only.
"""

import os
import re
import zipfile

from app.core.logger import logger


#: Only exact ``classes.dex`` / ``classes<N>.dex`` names are accepted.
DEX_NAME_PATTERN = re.compile(r"^classes(\d+)?\.dex$", re.IGNORECASE)

#: Refuse to extract a single absurdly large entry (corrupt/malicious ZIP).
MAX_DEX_SIZE = 1024 * 1024 * 1024  # 1 GiB


def dex_sort_key(name):
    """Numeric ordering: ``classes.dex`` -> 1, ``classes2.dex`` -> 2 ..."""
    match = DEX_NAME_PATTERN.match(os.path.basename(name or ""))
    if not match:
        return 10 ** 6
    return int(match.group(1) or 1)


def is_dex_name(name):
    """True when ``name`` is a valid, root-level DEX file name."""
    if not name or not isinstance(name, str):
        return False
    if "/" in name or "\\" in name:
        return False
    return bool(DEX_NAME_PATTERN.match(name))


def discover_dex_in_apk(apk_path):
    """List the DEX entry names inside an APK container.

    Returns ``(names, error)`` where ``names`` is ordered
    ``classes.dex, classes2.dex, ...``. The APK is opened read-only and is
    never modified. Never raises.
    """
    if not apk_path or not os.path.isfile(apk_path):
        return [], "APK file not found: %s" % (apk_path or "None")

    try:
        with zipfile.ZipFile(apk_path, "r") as archive:
            entries = archive.namelist()
    except zipfile.BadZipFile:
        message = "Cannot read APK container: %s" % apk_path
        logger.error(message)
        return [], message
    except (OSError, RuntimeError) as exc:
        message = "Cannot read APK container: %s" % exc
        logger.error(message)
        return [], message

    names = [name for name in entries if is_dex_name(name)]
    names.sort(key=dex_sort_key)
    return names, ""


def dex_info_in_apk(apk_path):
    """Return ``[(name, size), ...]`` for every DEX entry in the APK."""
    if not apk_path or not os.path.isfile(apk_path):
        return []
    try:
        with zipfile.ZipFile(apk_path, "r") as archive:
            infos = [info for info in archive.infolist()
                     if is_dex_name(info.filename)]
    except (zipfile.BadZipFile, OSError, RuntimeError):
        return []
    infos.sort(key=lambda info: dex_sort_key(info.filename))
    return [(info.filename, info.file_size) for info in infos]


def extract_dex_files(apk_path, destination_dir):
    """Extract every DEX file of ``apk_path`` into ``destination_dir``.

    Only validated ``classes[N].dex`` names are extracted, and only into
    ``destination_dir`` (a directory the IDE generated). Returns
    ``(paths, error)``; never raises.
    """
    names, error = discover_dex_in_apk(apk_path)
    if error:
        return [], error
    if not names:
        message = "No DEX files found in %s" % os.path.basename(apk_path)
        logger.error(message)
        return [], message

    paths = []
    try:
        os.makedirs(destination_dir, exist_ok=True)
    except OSError as exc:
        message = "Could not create DEX staging directory: %s" % exc
        logger.error(message)
        return [], message

    try:
        with zipfile.ZipFile(apk_path, "r") as archive:
            for name in names:
                info = archive.getinfo(name)
                if info.file_size > MAX_DEX_SIZE:
                    message = "Skipped oversized DEX entry: %s" % name
                    logger.warning(message)
                    continue
                target = os.path.join(destination_dir, name)
                with archive.open(info, "r") as source:
                    data = source.read()
                with open(target, "wb") as handle:
                    handle.write(data)
                paths.append(target)
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        message = "Could not extract DEX files: %s" % exc
        logger.error(message)
        return paths, message

    logger.info("Extracted %d DEX file(s) to %s" % (len(paths), destination_dir))
    return paths, ""


def discover_dex_files(directory):
    """Find DEX files that already exist as files inside ``directory``.

    Used as a fallback for already-extracted workspaces. Returns an
    ordered list of absolute paths; never raises.
    """
    if not directory or not os.path.isdir(directory):
        return []
    found = []
    try:
        for entry in os.listdir(directory):
            if not is_dex_name(entry):
                continue
            path = os.path.join(directory, entry)
            if os.path.isfile(path):
                found.append(path)
    except OSError as exc:
        logger.warning("DEX directory listing failed: %s" % exc)
        return []
    found.sort(key=dex_sort_key)
    return found


def dex_summary(paths):
    """Human-readable one-liner describing discovered DEX files."""
    names = [os.path.basename(path) for path in paths or []]
    if not names:
        return "none"
    return "%d (%s)" % (len(names), ", ".join(names))
"""APK validation.

Static, safe validation of an untrusted APK before it is used
anywhere in the IDE.

Phase 02 guarantees:

* The file exists and is readable.
* The extension is ``.apk``.
* The file is a valid ZIP / JAR / APK container.
* ``AndroidManifest.xml`` is present inside the container.
* At least one ``classes*.dex`` file is present.

This module NEVER:

* opens or reads decoded content,
* extracts anything,
* executes anything found inside the APK,
* connects to any network resource,
* modifies the APK.

If anything goes wrong, a structured :class:`ValidationResult` is returned
instead of raising, so the caller can present a friendly message and keep
the application alive.
"""

import os
import zipfile

from app.core.logger import logger


class ValidationResult:
    """Outcome of an APK validation pass."""

    __slots__ = ("ok", "reason", "dex_files")

    def __init__(self, ok, reason="", dex_files=None):
        self.ok = bool(ok)
        self.reason = reason or ""
        self.dex_files = list(dex_files or [])

    def message(self):
        return self.reason if self.reason else ("Valid APK" if self.ok else "Unknown validation error")


def _exists_and_readable(path):
    if not path:
        return False, "APK path is empty"
    if not os.path.exists(path):
        return False, "Path does not exist: %s" % path
    if not os.path.isfile(path):
        return False, "Path is not a file: %s" % path
    if not os.access(path, os.R_OK):
        return False, "Permission denied (not readable): %s" % path
    return True, ""


def _is_apk_extension(path):
    return path.lower().endswith(".apk")


def _list_zip_entries(path):
    """Return the zip entry names, or ``(None, error)`` on failure."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            return zf.namelist(), ""
    except zipfile.BadZipFile:
        return None, "Invalid ZIP/APK container: %s" % path
    except (OSError, RuntimeError) as exc:
        return None, "Cannot read ZIP container: %s" % exc


def validate_apk(path):
    """Validate an APK without ever running or extracting its content.

    Returns a :class:`ValidationResult`; never raises.
    """
    exists, reason = _exists_and_readable(path)
    if not exists:
        logger.error("APK validation failed: %s" % reason)
        return ValidationResult(False, reason)

    if not _is_apk_extension(path):
        reason = "Not an APK file (expected .apk extension): %s" % path
        logger.error("APK validation failed: %s" % reason)
        return ValidationResult(False, reason)

    entries, error = _list_zip_entries(path)
    if entries is None:
        logger.error("APK validation failed: %s" % error)
        return ValidationResult(False, error)

    names = set(entries)

    if "AndroidManifest.xml" not in names:
        reason = "AndroidManifest.xml not found"
        logger.error("APK validation failed: %s" % reason)
        return ValidationResult(False, reason)

    dex_files = sorted(
        name for name in names
        if name.rsplit("/", 1)[-1].startswith("classes") and name.endswith(".dex")
    )
    if not dex_files:
        reason = "No classes*.dex file found"
        logger.error("APK validation failed: %s" % reason)
        return ValidationResult(False, reason)

    logger.info("APK validation successful (%d DEX file(s))" % len(dex_files))
    return ValidationResult(True, "", dex_files)

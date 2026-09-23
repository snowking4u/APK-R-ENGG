"""Full APK decode pipeline (Phase 02).

Pipeline: validate APK -> plan/confirm workspace -> copy original ->
decode with Apktool -> load/inspect the decoded project -> produce a
:class:`DecodeReport` describing the decoded workspace.

This module contains pure orchestration logic with no Qt dependencies, so
it can run on any thread (it is driven by ``decode_worker.py`` from a
QThread, and by tests directly). It never inspects or executes contents of
the APK beyond read-only ZIP / manifest parsing, and never modifies the
source APK.
"""

import os

from app.core import logger
from app.core.apk_validator import validate_apk
from app.core.tool_runner import decode_with_apktool, apktool_missing_message
from app.core.workspace import (plan_workspace, create_workspace_dirs,
                                copy_original)
from app.core.manifest_parser import parse_manifest_file


DEFAULT_DECODE_TIMEOUT = 300  # seconds; generous default for large APKs


class DecodeReport:
    """Summary of a completed (or failed) APK decode."""

    __slots__ = ("ok", "error", "apk_path", "workspace", "manifest_path",
                 "apktool_yml_path", "dex_files", "smali_dirs",
                 "resource_dir", "assets_dir", "manifest", "decode_status",
                 "timed_out", "tool_missing")

    def __init__(self):
        self.ok = False
        self.error = ""
        self.apk_path = ""
        self.workspace = None
        self.manifest_path = ""
        self.apktool_yml_path = ""
        self.dex_files = []
        self.smali_dirs = []
        self.resource_dir = ""
        self.assets_dir = ""
        self.manifest = None
        self.decode_status = "Failed"
        self.timed_out = False
        self.tool_missing = False

    def to_dict(self):
        return {
            "ok": self.ok,
            "error": self.error,
            "apk_path": self.apk_path,
            "manifest_path": self.manifest_path,
            "apktool_yml_path": self.apktool_yml_path,
            "dex_files": list(self.dex_files),
            "smali_dirs": list(self.smali_dirs),
            "resource_dir": self.resource_dir,
            "assets_dir": self.assets_dir,
            "decode_status": self.decode_status,
            "timed_out": self.timed_out,
            "tool_missing": self.tool_missing,
        }


def _discover_decoded(decoded_dir):
    """Inspect a decoded workspace and describe its structure.

    Detects smali/ (and any smali_classes*, smali_classes2, ...),
    res/, assets/, original/, etc. dynamically. Returns a dict.
    """
    info = {
        "manifest_path": "",
        "apktool_yml_path": "",
        "smali_dirs": [],
        "resource_dir": "",
        "assets_dir": "",
        "original_dir": "",
    }

    manifest = os.path.join(decoded_dir, "AndroidManifest.xml")
    if os.path.isfile(manifest):
        info["manifest_path"] = manifest

    apktool_yml = os.path.join(decoded_dir, "apktool.yml")
    if os.path.isfile(apktool_yml):
        info["apktool_yml_path"] = apktool_yml

    try:
        names = sorted(os.listdir(decoded_dir))
    except OSError:
        names = []

    smali_dirs = []
    for entry in names:
        if entry == "smali" or entry.startswith("smali_classes"):
            path = os.path.join(decoded_dir, entry)
            if os.path.isdir(path):
                smali_dirs.append(entry)

    info["smali_dirs"] = sorted(smali_dirs)

    if os.path.isdir(os.path.join(decoded_dir, "res")):
        info["resource_dir"] = os.path.join(decoded_dir, "res")
    if os.path.isdir(os.path.join(decoded_dir, "assets")):
        info["assets_dir"] = os.path.join(decoded_dir, "assets")
    if os.path.isdir(os.path.join(decoded_dir, "original")):
        info["original_dir"] = os.path.join(decoded_dir, "original")

    return info


def _open_apk_dex_list(apk_path):
    """List DEX files (classes.dex, classes2.dex, ...) without executing."""
    from app.core.apk_validator import _list_zip_entries, ValidationResult

    entries, error = _list_zip_entries(apk_path)
    if error:
        return ValidationResult(False, error)
    dex = sorted(
        name for name in entries
        if name.rsplit("/", 1)[-1].startswith("classes") and name.endswith(".dex")
    )
    return ValidationResult(True, "", dex)


def run_decode(apk_path, projects_root, on_conflict, timeout=None):
    """Run the whole decode pipeline synchronously (thread-safe).

    ``on_conflict(workspace_root, name)`` -> "reuse" | "new" | "cancel".
    Returns a :class:`DecodeReport`; never raises.
    """
    report = DecodeReport()
    report.apk_path = apk_path
    timeout = timeout or DEFAULT_DECODE_TIMEOUT

    logger.info("Validation of APK: %s" % apk_path)
    validation = validate_apk(apk_path)
    if not validation.ok:
        report.error = validation.reason
        logger.error("APK validation failed: %s" % validation.reason)
        return report

    dex_list = validation.dex_files or []

    logger.info("Planning workspace for decoded project.")
    plan = plan_workspace(projects_root, os.path.basename(apk_path),
                          on_conflict)
    if plan.cancelled:
        report.error = "Project open cancelled by the user."
        report.decode_status = "Cancelled"
        logger.info("APK open cancelled by the user.")
        return report

    if not create_workspace_dirs(plan):
        report.error = plan.error
        return report

    copied = copy_original(plan)
    if not copied:
        report.error = plan.error
        report.decode_status = "Failed"
        return report

    logger.info("Decoding APK with Apktool...")
    tool = decode_with_apktool(copied, plan.decoded_dir, timeout=timeout)
    if tool.not_found:
        report.error = tool.error or apktool_missing_message()
        report.tool_missing = True
        report.decode_status = "Failed"
        logger.error(report.error)
        return report
    if tool.timed_out:
        report.error = "APK decoding timed out after %d seconds." % timeout
        report.timed_out = True
        report.decode_status = "Timed out"
        logger.error(report.error)
        return report
    if tool.error:
        report.error = tool.error
        report.decode_status = "Failed"
        logger.error(report.error)
        return report
    if tool.returncode != 0:
        detail = (tool.stderr or tool.stdout or "").strip()
        report.error = "Apktool decode failed (exit %s). %s" % (
            tool.returncode, detail[:2000])
        report.decode_status = "Failed"
        logger.error(report.error)
        return report

    logger.info("APK decode completed.")
    report.decode_status = "Decoded"

    structure = _discover_decoded(plan.decoded_dir)
    report.workspace = plan
    report.manifest_path = structure["manifest_path"]
    report.apktool_yml_path = structure["apktool_yml_path"]
    report.smali_dirs = structure["smali_dirs"]
    report.resource_dir = structure["resource_dir"]
    report.assets_dir = structure["assets_dir"]
    report.dex_files = dex_list

    if report.manifest_path:
        report.manifest = parse_manifest_file(report.manifest_path)

    logger.info("Loading project tree from decoded structure.")
    report.ok = True
    return report

"""Workspace planning and creation (Phase 02).

A fresh APK gets its own dedicated workspace under ``projects/``::

    projects/
        <Name>/
            original/app.apk          - pristine copy of the source APK
            decoded/                  - Apktool output
            metadata/                 - parsed manifest / decode info
            logs/                     - per-project log files

The source APK is NEVER modified; a byte-copy lands into ``original/``.

Conflict handling is deliberate and reversible: if a workspace already
exists we ASK the caller (via ``on_conflict`` callback) whether to reuse
it, create a new uniquely-named workspace, or cancel. We never silently
reuse or silently overwrite existing project data.
"""

import os
import shutil

from app.core.logger import logger


class WorkspacePlan:
    """The outcome of planning a workspace for an APK."""

    __slots__ = ("apk_path", "name", "root", "original_dir", "decoded_dir",
                 "metadata_dir", "logs_dir", "reused", "cancelled", "error")

    def __init__(self, apk_path="", name="", root="", original_dir="",
                 decoded_dir="", metadata_dir="", logs_dir="",
                 reused=False, cancelled=False, error=""):
        self.apk_path = apk_path
        self.name = name
        self.root = root
        self.original_dir = original_dir
        self.decoded_dir = decoded_dir
        self.metadata_dir = metadata_dir
        self.logs_dir = logs_dir
        self.reused = reused
        self.cancelled = cancelled
        self.error = error

    @property
    def ok(self):
        return bool(self.root) and not self.error and not self.cancelled

    def to_dict(self):
        return {
            "apk_path": self.apk_path,
            "name": self.name,
            "root": self.root,
            "original_dir": self.original_dir,
            "decoded_dir": self.decoded_dir,
            "metadata_dir": self.metadata_dir,
            "logs_dir": self.logs_dir,
            "reused": self.reused,
            "cancelled": self.cancelled,
            "error": self.error,
        }


def _safe_name(apk_name):
    """Build a filesystem-safe workspace name from an APK file stem."""
    stem = os.path.splitext(os.path.basename(apk_name or ""))[0].strip() or "project"
    cleaned = "".join(
        ch if (ch.isalnum() or ch in " _-.") else "_" for ch in stem
    ).strip()
    return cleaned or "project"


def default_name(apk_path):
    """The default workspace name for an APK."""
    return _safe_name(apk_path)


def plan_workspace(projects_root, basename, on_conflict):
    """Plan storage for decoding ``basename`` under ``projects_root``.

    ``on_conflict(workspace_root, basename)`` must return one of
    ``"reuse"``, ``"new"``, or ``"cancel"``.

    Returns a :class:`WorkspacePlan`; never raises.
    """
    name = _safe_name(basename)
    root = os.path.join(projects_root, name)

    if not os.path.isdir(root):
        return WorkspacePlan(
            name=name, root=root,
            original_dir=os.path.join(root, "original"),
            decoded_dir=os.path.join(root, "decoded"),
            metadata_dir=os.path.join(root, "metadata"),
            logs_dir=os.path.join(root, "logs"),
            reused=False,
        )

    # A workspace already exists: ask the caller.
    decision = on_conflict(root, name) if on_conflict else "new"
    if decision == "reuse":
        return WorkspacePlan(
            name=name, root=root,
            original_dir=os.path.join(root, "original"),
            decoded_dir=os.path.join(root, "decoded"),
            metadata_dir=os.path.join(root, "metadata"),
            logs_dir=os.path.join(root, "logs"),
            reused=True,
        )
    if decision == "new":
        import itertools

        for index in itertools.count(start=1):
            candidate = "%s_%d" % (name, index)
            candidate_root = os.path.join(projects_root, candidate)
            if not os.path.isdir(candidate_root):
                return WorkspacePlan(
                    name=candidate, root=candidate_root,
                    original_dir=os.path.join(candidate_root, "original"),
                    decoded_dir=os.path.join(candidate_root, "decoded"),
                    metadata_dir=os.path.join(candidate_root, "metadata"),
                    logs_dir=os.path.join(candidate_root, "logs"),
                    reused=False,
                )

    return WorkspacePlan(cancelled=True)


def create_workspace_dirs(plan):
    """Create the workspace directory layout for a plan.

    Returns True on success; on failure records ``plan.error`` and returns
    False. Never raises.
    """
    try:
        for directory in (plan.root, plan.original_dir, plan.decoded_dir,
                          plan.metadata_dir, plan.logs_dir):
            os.makedirs(directory, exist_ok=True)
        logger.info("Workspace created: %s" % plan.root)
        return True
    except OSError as exc:
        plan.error = "Could not create workspace directories: %s" % exc
        logger.error("Workspace creation failed: %s" % exc)
        return False


def copy_original(plan):
    """Copy the source APK into the workspace ``original/`` directory.

    The source file is only read; it is never opened for writing, moved or
    deleted. Returns the copied path, or None and sets ``plan.error``.
    """
    if not plan.apk_path:
        plan.error = "No source APK path to copy."
        logger.error("Workspace copy failed: no source APK path.")
        return None
    try:
        destination = os.path.join(plan.original_dir, os.path.basename(plan.apk_path))
        shutil.copy2(plan.apk_path, destination)
        logger.info("Original APK copied to %s" % destination)
        return destination
    except OSError as exc:
        plan.error = "Could not copy APK into workspace: %s" % exc
        logger.error("Workspace copy failed: %s" % exc)
        return None

"""Project model.

Represents an opened APK / project in the IDE. Phase 01 introduced the
in-memory holder, Phase 02 filled in the decoded-workspace values and
Phase 03 adds the JADX / Java decompilation values. Every attribute added
in Phase 03 has a safe default, so the Phase 01 contract is unchanged.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class Project:
    """Describes the currently loaded project.

    Attributes are intentionally simple plain fields. Later phases will
    write into them as real data becomes available.
    """

    name: str = ""
    apk_path: Optional[str] = None
    project_path: Optional[str] = None
    package_name: Optional[str] = None
    class_count: int = 0
    method_count: int = 0
    resource_count: int = 0
    build_status: str = "Idle"

    # ----- Phase 02 (decoded workspace) ------------------------------- #
    workspace_root: Optional[str] = None
    decoded_dir: Optional[str] = None
    smali_dirs: List[str] = field(default_factory=list)
    manifest_path: Optional[str] = None

    # ----- Phase 03 (JADX / Java decompilation) ------------------------ #
    decompiled_dir: Optional[str] = None
    java_source_root: Optional[str] = None
    dex_files: List[str] = field(default_factory=list)
    java_sources: List[str] = field(default_factory=list)
    java_index: Optional[Any] = None
    decompile_status: str = "Idle"
    jadx_status: str = "Not configured"
    dex_count: int = 0

    # ----- Phase 04 (Smali discovery / editor) ------------------------- #
    smali_roots: List[str] = field(default_factory=list)
    smali_files: List[str] = field(default_factory=list)
    smali_index: Optional[Any] = None
    current_smali_file: Optional[str] = None
    modified_smali_files: List[str] = field(default_factory=list)
    smali_status: str = "Idle"
    smali_class_count: int = 0
    smali_method_count: int = 0

    def is_loaded(self) -> bool:
        """True once a project (or at least an APK) has been opened."""
        return bool(self.apk_path or self.project_path)

    def full_name(self) -> str:
        """Display name used by the UI (package name or path basename)."""
        if self.package_name:
            return "%s (%s)" % (self.name, self.package_name)
        if self.name:
            return self.name
        return "Untitled Project"

    # ------------------------------------------------------------------ #
    # Phase 02 helpers.
    # ------------------------------------------------------------------ #
    def apply_decode_report(self, report) -> bool:
        """Populate the project from a Phase 02 :class:`DecodeReport`."""
        workspace = getattr(report, "workspace", None)
        self.name = workspace.name if workspace is not None else ""
        self.project_path = workspace.root if workspace is not None else ""
        self.workspace_root = self.project_path
        self.apk_path = report.apk_path or self.apk_path
        self.decoded_dir = (getattr(workspace, "decoded_dir", "")
                            if workspace is not None else "") or ""
        self.smali_dirs = list(getattr(report, "smali_dirs", []) or [])
        self.manifest_path = getattr(report, "manifest_path", "") or ""
        self.dex_files = list(getattr(report, "dex_names", []) or [])
        self.dex_count = len(self.dex_files)
        manifest = getattr(report, "manifest", None)
        if manifest is not None:
            self.package_name = manifest.package or self.package_name
        return True

    # ------------------------------------------------------------------ #
    # Phase 03 helpers.
    # ------------------------------------------------------------------ #
    def apply_decompile_report(self, report) -> bool:
        """Populate the project from a Phase 03 :class:`DecompileReport`."""
        if report is None:
            return False
        self.decompile_status = getattr(report, "status", "Idle") or "Idle"
        self.jadx_status = getattr(report, "jadx_status", "Not configured") \
            or "Not configured"
        self.decompiled_dir = getattr(report, "decompiled_dir", "") or None
        self.java_source_root = getattr(report, "java_source_root", "") or None
        self.java_sources = list(getattr(report, "java_sources", []) or [])
        self.java_index = getattr(report, "index", None)
        names = list(getattr(report, "dex_names", []) or [])
        if names:
            self.dex_files = names
            self.dex_count = len(names)
        index = self.java_index
        if index is not None:
            self.class_count = index.source_count
            self.method_count = index.method_count
        return True

    def java_class_count(self) -> int:
        """Number of indexed Java classes (``0`` when nothing indexed)."""
        if self.java_index is None:
            return 0
        return self.java_index.source_count

    # ------------------------------------------------------------------ #
    # Phase 04 helpers.
    # ------------------------------------------------------------------ #
    def apply_smali_index(self, index) -> bool:
        """Populate the project from a :class:`SmaliIndex`."""
        self.smali_index = index
        if index is None:
            self.smali_roots = []
            self.smali_files = []
            self.smali_class_count = 0
            self.smali_method_count = 0
            self.smali_status = "Idle"
            return False
        self.smali_roots = list(getattr(index, "roots", []) or [])
        self.smali_files = [item.path for item in getattr(index, "files", [])]
        self.smali_class_count = getattr(index, "class_count", 0)
        self.smali_method_count = getattr(index, "method_count", 0)
        errors = getattr(index, "parse_error_count", 0)
        self.smali_status = ("Indexed (%d parse error(s))" % errors
                             if errors else "Indexed")
        if self.current_smali_file and \
                self.current_smali_file not in self.smali_files:
            self.current_smali_file = None
        return True

    def smali_file_count(self) -> int:
        """Number of discovered Smali files."""
        return len(self.smali_files)

    def reset(self):
        """Restore every field to its safe default value."""
        self.name = ""
        self.apk_path = None
        self.project_path = None
        self.package_name = None
        self.class_count = 0
        self.method_count = 0
        self.resource_count = 0
        self.build_status = "Idle"
        self.workspace_root = None
        self.decoded_dir = None
        self.smali_dirs = []
        self.manifest_path = None
        self.decompiled_dir = None
        self.java_source_root = None
        self.dex_files = []
        self.java_sources = []
        self.java_index = None
        self.decompile_status = "Idle"
        self.jadx_status = "Not configured"
        self.dex_count = 0
        self.smali_roots = []
        self.smali_files = []
        self.smali_index = None
        self.current_smali_file = None
        self.modified_smali_files = []
        self.smali_status = "Idle"
        self.smali_class_count = 0
        self.smali_method_count = 0

    def to_state(self, state):
        """Push this project's values into the central AppState."""
        state.set_project(
            apk_path=self.apk_path,
            project_path=self.project_path,
            package_name=self.package_name,
        )
        state.class_count = self.class_count
        state.method_count = self.method_count
        state.resource_count = self.resource_count
        state.build_status = self.build_status
        state.set_decompile_summary(
            jadx_status=self.jadx_status,
            decompile_status=self.decompile_status,
            dex_count=self.dex_count,
            dex_names=self.dex_files,
            java_source_count=len(self.java_sources),
            java_method_count=self.method_count if self.java_index else 0,
        )
        state.set_smali_summary(
            file_count=len(self.smali_files),
            class_count=self.smali_class_count,
            method_count=self.smali_method_count,
            root_count=len(self.smali_roots),
            modified_count=len(self.modified_smali_files),
            status=self.smali_status,
        )
        state.set_smali_selection(
            source=self.current_smali_file,
            class_name=(self.smali_index.get(self.current_smali_file).class_name
                        if self.smali_index and self.current_smali_file
                        and self.smali_index.get(self.current_smali_file) else None),
        )


# Convenience default project used by the UI until a real one is loaded.
current = Project()
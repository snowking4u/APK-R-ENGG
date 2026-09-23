"""Project model.

Represents an opened APK / project in the IDE. In Phase 01 this is an
in-memory holder only: values are initialized safely to defaults and
will be populated by future phases (APK loading, decoding, analysis).
"""

from dataclasses import dataclass, field
from typing import Optional


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


# Convenience default project used by the UI until a real one is loaded.
current = Project()
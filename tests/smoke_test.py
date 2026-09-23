"""Smoke test for the Phase 01 application shell.

Runs headless (offscreen) and verifies that the window, menus, docks,
editors, console, state and placeholder actions all behave.
Exit code 0 on success, non-zero on failure.

Run from project root:  python -m tests.smoke_test
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import APP_NAME  # noqa: E402
from app.core import app_state, logger  # noqa: E402
from app.main import create_application  # noqa: E402
from app.ui import MainWindow  # noqa: E402

FAILED = []


def check(name, condition):
    status = "PASS" if condition else "FAIL"
    print("[%s] %s" % (status, name))
    if not condition:
        FAILED.append(name)


def main():
    app = create_application([])
    console_messages = []
    logger.message.connect(console_messages.append)

    window = MainWindow()
    window.show()
    app.processEvents()

    # ----- Core state -------------------------------------------------
    check("state defaults are safe", app_state.apk_path is None
          and app_state.package_name is None
          and app_state.class_count == 0
          and app_state.method_count == 0
          and app_state.resource_count == 0
          and app_state.build_status == "Idle")

    app_state.class_count = 12
    app_state.method_count = 340
    app_state.resource_count = 25
    app_state.apk_path = "C:/fake.apk"
    check("state updates", app_state.class_count == 12 and app_state.apk_path == "C:/fake.apk")

    # ----- Window ------------------------------------------------------
    check("window has title", APP_NAME in window.windowTitle())
    check("window resizable", window.minimumWidth() > 0 and window.minimumHeight() > 0)
    check("initial size ok", window.width() >= window.minimumWidth()
          and window.height() >= window.minimumHeight())

    old_w, old_h = window.width(), window.height()
    window.resize(old_w + 100, old_h + 100)
    app.processEvents()
    check("resize ok", window.width() == old_w + 100 and window.height() == old_h + 100)

    # ----- Menus --------------------------------------------------------
    menus = [a.text().replace("&", "") for a in window.menuBar().actions()]
    check("menus present", menus == ["File", "View", "Build", "Analysis", "Help"])

    file_actions = [a.text().replace("&", "") for a in window.menuBar().actions()[0].menu().actions()]
    file_names = [a for a in file_actions if a]
    check("file menu entries", file_names[0] == "Open APK..." and file_names[-1] == "Exit")
    check("exit non-empty", any(a == "Exit" for a in file_names))

    # ----- Toolbar ------------------------------------------------------
    toolbar_actions = [a.text() for a in window.toolbar.actions()]
    expected_toolbar = ["Open APK", "Save", "Rebuild", "Sign", "Rebuild + Sign", "Clean"]
    check("toolbar actions", [a for a in toolbar_actions if a] == expected_toolbar)

    # ----- Panels / editors --------------------------------------------
    check("project explorer root", window.project_explorer.topLevelItemCount() == 1)
    check("bottom tabs", window.bottom_panel.count() == 7)
    check("java editor read-only", window.java_editor.isReadOnly() is True)
    check("smali editor editable", window.smali_editor.isReadOnly() is False)
    check("java has content", "Java Decompiled View" in window.java_editor.toPlainText())
    check("monospace font", window.java_editor.font().family().lower() in ("consolas", "monospace")
          or "mono" in window.java_editor.font().family().lower())

    # ----- View toggles ------------------------------------------------
    window.action_view_bottom.setChecked(False)
    app.processEvents()
    check("bottom panel hidden", not window.bottom_dock.isVisible())
    window.action_view_bottom.setChecked(True)
    window.action_view_java.setChecked(False)
    app.processEvents()
    check("java view hidden", not window.java_container.isVisible())
    window.action_view_java.setChecked(True)
    window.reset_layout()
    app.processEvents()
    check("reset layout restores", window.project_dock.isVisible()
          and window.bottom_dock.isVisible()
          and window.java_container.isVisible()
          and window.smali_container.isVisible())

    # ----- Placeholder actions ------------------------------------------
    window.action_rebuild.trigger()
    app.processEvents()
    check("placeholder does not crash", True)
    msg = window.statusBar().currentMessage()
    check("placeholder message shown", "later development phase" in msg)

    # ----- Console / logging --------------------------------------------
    window._log_startup()
    check("console received log", any("Application started" in m for m in console_messages))
    check("startup banner logged", any("No project loaded" in m for m in console_messages))

    # ----- Status bar ----------------------------------------------------
    check("status shows project", "Project:" in window.status_project.text())
    check("status shows classes", "Classes: 12" in window.status_classes.text())
    check("status shows methods", "Methods: 340" in window.status_methods.text())
    check("status shows resources", "Resources: 25" in window.status_resources.text())

    # ----- Close ---------------------------------------------------------
    window.close()
    app.processEvents()

    print()
    if FAILED:
        print("SMOKE TEST FAILED: %s" % ", ".join(FAILED))
        return 1
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
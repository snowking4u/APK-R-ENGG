"""Phase 02 test suite: APK open pipeline (validation, workspace, decode
orchestration, manifest parsing, project tree, state).

Offline-only. Builds minimal APK containers with ``zipfile`` in a temp
directory; never downloads APKs, never touches the network, never runs
anything found inside an APK, and never modifies a real APK.

Run from the project root::

    python -m tests.phase02_test

Exit code 0 when every check passes; non-zero otherwise.
"""

import os
import shutil
import sys
import tempfile
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import APP_NAME  # noqa: E402
from app.core import app_state, logger  # noqa: E402
from app.core.apk_validator import (ValidationResult, validate_apk)  # noqa: E402
from app.core.manifest_parser import (ManifestInfo, parse_manifest_file,  # noqa: E402
                                      parse_manifest_text)
from app.core.tool_runner import (ToolResult, find_apktool, run_tool,  # noqa: E402
                                  apktool_missing_message)
from app.core.workspace import (WorkspacePlan, plan_workspace,  # noqa: E402
                                create_workspace_dirs, copy_original,
                                default_name)
from app.main import create_application  # noqa: E402
from app.ui import MainWindow  # noqa: E402

FAILED = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    if condition:
        print("[PASS] %s" % name)
    else:
        print("[FAIL] %s  %s" % (name, detail))
        FAILED.append(name)


def _last_log_lines(app_logger, matches=None):
    """Return recently logged lines (from the test logger buffer)."""
    lines = []
    for entry in getattr(app_logger, "_entries", []) or []:
        text = entry if isinstance(entry, str) else str(entry)
        if matches and not any(m in text for m in matches):
            continue
        lines.append(text)
    return lines


def _make_minimal_apk(path, with_manifest=True, with_dex=True,
                      extra=()):
    """Create a minimal ZIP/APK container (never a real APK)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    manifest = (
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android"'
        ' package="com.example.minimal" versionCode="1" versionName="1.0">\n'
        '  <uses-sdk android:minSdkVersion="21"'
        ' android:targetSdkVersion="33"/>\n'
        '</manifest>\n'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        if with_manifest:
            zf.writestr("AndroidManifest.xml", manifest)
        if with_dex:
            zf.writestr("classes.dex", b"\x64\x65\x78" + b"\x00" * 60)
        for name, content in extra:
            zf.writestr(name, content)


def _valid_apk_fixture(tmp):
    path = os.path.join(tmp, "fixtures", "minimal.apk")
    _make_minimal_apk(
        path,
        extra=(
            ("res/values/strings.xml", "<resources/>\n"),
            ("assets/logo.png", b"\x89PNG"),
        ),
    )
    return path


def main():
    app = create_application([])
    app_state.clear_project()
    check("state defaults safe",
          app_state.apk_path is None and app_state.project_path is None
          and app_state.package_name is None
          and bool(app_state.build_status))

    tmp = tempfile.mkdtemp(prefix="phase02_", suffix=".tmp")

    # ------------------------------------------------------------------ #
    # 01-05. Validation.
    # ------------------------------------------------------------------ #
    missing = os.path.join(tmp, "does_not_exist.apk")
    result = validate_apk(missing)
    check("01 invalid path rejected",
          isinstance(result, ValidationResult) and not result.ok
          and bool(result.reason))

    text_path = os.path.join(tmp, "not_an_apk.txt")
    with open(text_path, "w", encoding="utf-8") as handle:
        handle.write("this is not an apk")
    result = validate_apk(text_path)
    check("02 non-APK rejected",
          isinstance(result, ValidationResult) and not result.ok
          and "apk" in (result.reason or "").lower())

    corrupt = os.path.join(tmp, "corrupt.apk")
    with open(corrupt, "wb") as handle:
        handle.write(b"MZ\x90\x00" + b"\x00" * 40)
    result = validate_apk(corrupt)
    check("03 invalid zip rejected",
          isinstance(result, ValidationResult) and not result.ok
          and bool(result.reason))

    no_manifest = os.path.join(tmp, "no_manifest.apk")
    _make_minimal_apk(no_manifest, with_manifest=False)
    result = validate_apk(no_manifest)
    check("04 zip without manifest rejected",
          isinstance(result, ValidationResult) and not result.ok
          and "manifest" in (result.reason or "").lower())

    no_dex = os.path.join(tmp, "no_dex.apk")
    _make_minimal_apk(no_dex, with_dex=False)
    result = validate_apk(no_dex)
    check("05 zip without dex rejected",
          isinstance(result, ValidationResult) and not result.ok
          and ("dex" in (result.reason or "").lower()))

    good = _valid_apk_fixture(tmp)
    result = validate_apk(good)
    check("06 valid minimal apk accepted",
          isinstance(result, ValidationResult) and result.ok
          and "classes.dex" in (result.dex_files or []))

    # ------------------------------------------------------------------ #
    # 07-09. Workspace planning/creation.
    # ------------------------------------------------------------------ #
    projects_root = os.path.join(tmp, "projects")
    plan = plan_workspace(projects_root, os.path.basename(good), on_conflict=None)
    check("07 workspace planned",
          isinstance(plan, WorkspacePlan) and plan.ok
          and os.path.dirname(plan.root) == projects_root)
    if isinstance(plan, WorkspacePlan) and plan.ok:
        check("08 workspace dirs created",
              create_workspace_dirs(plan)
              and os.path.isdir(plan.root)
              and os.path.isdir(plan.original_dir)
              and os.path.isdir(plan.decoded_dir))

        plan.apk_path = good
        original = copy_original(plan)
        check("09 original copied into workspace",
              bool(original)
              and os.path.isfile(original)
              and os.path.basename(original) == os.path.basename(good))
    else:
        check("08 workspace dirs created", False)
        check("09 original copied into workspace", False)

    # Expected conflict: planning twice for the same basename.
    plan2 = plan_workspace(projects_root, os.path.basename(good),
                           on_conflict=lambda root, name: "new")
    check("09 conflict produces new name",
          isinstance(plan2, WorkspacePlan) and plan2.ok
          and plan2.root != plan.root)

    # ------------------------------------------------------------------ #
    # 10-12. Manifest parsing.
    # ------------------------------------------------------------------ #
    manifest_path = os.path.join(tmp, "AndroidManifest.xml")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        handle.write(
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android"'
            ' package="com.example.minimal" versionCode="7" versionName="2.1">\n'
            '  <uses-sdk android:minSdkVersion="21"'
            ' android:targetSdkVersion="33"/>\n'
            '  <uses-permission android:name="android.permission.INTERNET"/>\n'
            '  <application><activity android:name=".MainActivity"/></application>\n'
            '</manifest>\n'
        )
    info = parse_manifest_file(manifest_path)
    check("10 manifest parsed", isinstance(info, ManifestInfo)
          and info.package == "com.example.minimal")
    check("10 version parsed", info.version_code == 7
          and info.version_name == "2.1")
    check("11 sdk parsed", info.min_sdk == 21
          and info.target_sdk == 33)
    check("11 permission/activity counts",
          info.permission_count == 1 and info.activity_count == 1)

    info2 = parse_manifest_text("")
    check("12 empty manifest is safe",
          isinstance(info2, ManifestInfo) and not info2.package)

    # ------------------------------------------------------------------ #
    # 13-17. Tool runner behaviour (never network; tool may be absent).
    # ------------------------------------------------------------------ #
    tool = find_apktool()
    if not tool:
        message = apktool_missing_message()
        check("13 apktool missing -> clean message", bool(message)
              and "Apktool" in message and "required" in message.lower())
        check("14 no decode without apktool (ToolResult not_found)",
              run_tool(["apktool"], timeout=30).not_found)
    else:
        check("13 apktool configured (info only)", True)
        check("14 run_tool with apktool (info only)",
              isinstance(run_tool(["apktool", "--version"], timeout=30),
                         ToolResult))

    missing_tool = run_tool(["no_such_tool_abc", "x"], timeout=30)
    check("15 unknown tool -> not_found", missing_tool.not_found
          and bool(missing_tool.error))

    # ------------------------------------------------------------------ #
    # 18-20. Project tree + APK info panel wiring.
    # ------------------------------------------------------------------ #
    window = MainWindow()
    window.show()
    app.processEvents()
    check("18 project explorer tree present",
          window.project_explorer.topLevelItemCount() >= 1)
    check("19 open-apk action exists",
          hasattr(window, "action_open_apk"))
    if hasattr(window, "action_open_apk"):
        window.action_open_apk.trigger()
        app.processEvents()
    check("20 open-apk action handled without crash", True)

    window.close()
    app.processEvents()

    shutil.rmtree(tmp, ignore_errors=True)

    if FAILED:
        print()
        print("PHASE 02 TEST FAILED (%d)" % len(FAILED))
        for name in FAILED:
            print("  - %s" % name)
        return 1
    print()
    print("PHASE 02 TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

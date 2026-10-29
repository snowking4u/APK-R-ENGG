"""Phase 04 test suite: Smali discovery, parsing, tree, editor, saving,
search, navigation and Java <-> Smali mapping.

Offline-only. Uses temporary decoded-project fixtures; never needs a real
APK, never downloads anything and never executes project content.

Run from the project root::

    python -m tests.phase04_test

Exit code 0 when every check passes; non-zero otherwise.
"""

import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtGui import QTextCursor  # noqa: E402

from app.core import app_state  # noqa: E402
from app.core.java_index import build_index  # noqa: E402
from app.core.project import Project  # noqa: E402
from app.core.smali_discovery import (discover_smali_files,  # noqa: E402
                                      discover_smali_roots, find_decoded_dir)
from app.core.smali_index import (build_smali_index, find_java_by_smali,  # noqa: E402
                                  find_smali_by_java, safe_write_smali,
                                  search_smali)
from app.core.smali_parser import (descriptor_to_name,  # noqa: E402
                                   parse_smali_file, read_smali_text)
from app.main import create_application  # noqa: E402
from app.ui.code_editor import CodeEditor  # noqa: E402
from app.ui.project_panel import ProjectExplorer  # noqa: E402
from app.ui.smali_worker import SmaliIndexWorker  # noqa: E402

FAILED = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    if condition:
        print("[PASS] %s" % name)
    else:
        print("[FAIL] %s  %s" % (name, detail))
        FAILED.append(name)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


MAIN_SMALI = """\
.class public Lcom/example/MainActivity;
.super Landroid/app/Activity;
.implements Ljava/lang/Runnable;
.source "MainActivity.java"

.field private name:Ljava/lang/String;
.field public static final TAG:Ljava/lang/String; = "Main"

# a comment
.method public constructor <init>()V
    .locals 0
    invoke-direct {p0}, Landroid/app/Activity;-><init>()V
    return-void
.end method

.method public onCreate(Landroid/os/Bundle;)V
    .locals 2
    const-string v0, "hello"
    invoke-virtual {p0, v0}, Lcom/example/MainActivity;->doCheck(Ljava/lang/String;)V
    return-void
.end method

.method private doCheck(Ljava/lang/String;)V
    .locals 0
    return-void
.end method
"""

UTIL_SMALI = """\
.class public final Lcom/example/Util;
.super Ljava/lang/Object;
.source "Util.java"

.method public static add(II)I
    .locals 1
    add-int v0, p0, p1
    return v0
.end method
"""

EXTRA_SMALI = """\
.class public Lorg/test/Extra;
.super Ljava/lang/Object;

.method public <init>()V
    .locals 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method
"""

BROKEN_SMALI = """\
.class public Lbroken/Bad;
.super Ljava/lang/Object;
.method public broken(I)V
    .locals 1
    this-instruction-does-not-exist v0
    return-void
"""

JAVA_SOURCE = """\
package com.example;

public class MainActivity {
    public MainActivity() {
    }

    public void onCreate(Bundle state) {
    }

    private void doCheck(String value) {
    }
}
"""


def _make_fixture(tmp):
    decoded = os.path.join(tmp, "decoded")
    main = _write(os.path.join(decoded, "smali", "com", "example",
                               "MainActivity.smali"), MAIN_SMALI)
    util = _write(os.path.join(decoded, "smali_classes2", "com", "example",
                               "Util.smali"), UTIL_SMALI)
    extra = _write(os.path.join(decoded, "smali_classes3", "org", "test",
                                "Extra.smali"), EXTRA_SMALI)
    broken = _write(os.path.join(decoded, "smali", "broken", "Bad.smali"),
                    BROKEN_SMALI)
    _write(os.path.join(decoded, "AndroidManifest.xml"),
           '<manifest package="com.example"/>')
    os.makedirs(os.path.join(decoded, "res", "values"), exist_ok=True)
    os.makedirs(os.path.join(decoded, "assets"), exist_ok=True)
    java_root = os.path.join(tmp, "decompiled", "sources")
    java_file = _write(os.path.join(java_root, "com", "example",
                                    "MainActivity.java"), JAVA_SOURCE)
    return {
        "tmp": tmp,
        "decoded": decoded,
        "main": main,
        "util": util,
        "extra": extra,
        "broken": broken,
        "java_root": java_root,
        "java_file": java_file,
    }


def _find_item(explorer, kind, path=None):
    stack = [explorer.topLevelItem(i)
             for i in range(explorer.topLevelItemCount())]
    while stack:
        item = stack.pop()
        if item is None:
            continue
        data = item.data(0, 0x0100) or {}
        payload = data.get("payload") or {}
        if data.get("kind") == kind and (path is None or payload.get("path") == path):
            return item
        for index in range(item.childCount()):
            stack.append(item.child(index))
    return None


def main():
    app = create_application([])
    app_state.clear_project()
    tmp = tempfile.mkdtemp(prefix="phase04_", suffix=".tmp")
    fixture = _make_fixture(tmp)

    roots = discover_smali_roots(fixture["decoded"])
    root_names = [os.path.basename(item) for item in roots]

    # 01-05. Discovery.
    check("01 smali directory discovered",
          "smali" in root_names and os.path.isdir(roots[0]))
    check("02 smali_classes2 discovered", "smali_classes2" in root_names)
    check("03 multiple Smali roots discovered", len(roots) == 3)
    check("04 decoded directory resolved",
          find_decoded_dir(fixture["decoded"]) == fixture["decoded"])
    files = []
    for root in roots:
        files.extend(discover_smali_files(root))
    check("05 Smali files discovered recursively",
          len(files) == 4 and all(item.lower().endswith(".smali")
                                  for item in files))

    index = build_smali_index(roots)
    main_file = index.get(fixture["main"])

    # 06-15. Parsing.
    check("06 class descriptor parsed",
          main_file is not None
          and main_file.class_descriptor == "Lcom/example/MainActivity;")
    check("07 package parsed",
          main_file is not None and main_file.package_name == "com.example")
    check("08 superclass parsed",
          main_file is not None
          and main_file.superclass == "Landroid/app/Activity;")
    check("09 interface parsed",
          main_file is not None
          and main_file.interfaces == ["Ljava/lang/Runnable;"])
    check("10 fields parsed",
          main_file is not None and len(main_file.fields) == 2
          and {item.name for item in main_file.fields} == {"name", "TAG"})
    check("11 methods parsed",
          main_file is not None
          and {item.name for item in main_file.methods} ==
          {"<init>", "onCreate", "doCheck"})
    constructor = main_file.method("<init>") if main_file else None
    check("12 constructor parsed",
          constructor is not None and constructor.descriptor == "()V")
    on_create = main_file.method("onCreate") if main_file else None
    check("13 method line ranges",
          on_create is not None and on_create.start_line == 16
          and on_create.end_line == 21
          and on_create.descriptor == "(Landroid/os/Bundle;)V")
    broken = parse_smali_file(fixture["broken"])
    check("14 malformed/unknown Smali tolerated",
          broken.class_descriptor == "Lbroken/Bad;"
          and len(broken.methods) == 1
          and broken.methods[0].end_line == broken.line_count
          and not broken.parse_error)
    check("15 descriptor conversion",
          descriptor_to_name("Lcom/example/MainActivity;") ==
          "com.example.MainActivity"
          and descriptor_to_name("[Ljava/lang/String;") == "java.lang.String[]"
          and descriptor_to_name("I") == "int"
          and descriptor_to_name("V") == "void")

    # 16. Tree.
    explorer = ProjectExplorer()
    explorer.build_project_tree(title="PROJECT")
    explorer.set_smali_index(index, roots)
    smali_item = _find_item(explorer, "smali")
    root_items = []
    if smali_item is not None:
        root_items = [smali_item.child(i) for i in range(smali_item.childCount())]
    main_item = explorer._smali_items_by_path.get(fixture["main"])
    if main_item is not None:
        explorer._on_item_expanded(main_item)
    method_items = []
    if main_item is not None:
        method_items = [main_item.child(i) for i in range(main_item.childCount())
                        if (main_item.child(i).data(0, 0x0100) or {}).get("kind")
                        == "smali-method"]
    check("16 Smali project tree generated",
          smali_item is not None and smali_item.text(0).startswith("Smali (4)")
          and len(root_items) == 3 and len(method_items) == 3)

    # 17-18. Java <-> Smali mapping.
    java_index = build_index(fixture["java_root"])
    smali_matches = find_smali_by_java(index, "com.example.MainActivity")
    java_matches = find_java_by_smali(java_index, main_file)
    check("17 Java -> Smali mapping",
          len(smali_matches) == 1
          and smali_matches[0].path == fixture["main"])
    check("18 Smali -> Java mapping",
          len(java_matches) == 1
          and java_matches[0].path == fixture["java_file"])

    # 19-24. Editor, dirty state, save and navigation.
    editor = CodeEditor(language="smali", read_only=False)
    dirty_events = []
    editor.dirty_changed.connect(dirty_events.append)
    loaded, load_error = editor.load_editable_file(fixture["main"])
    check("19 editor is editable",
          not editor.isReadOnly() and loaded)
    check("20 editor loads actual Smali content",
          loaded and ".class public Lcom/example/MainActivity;" in
          editor.toPlainText() and editor.file_path == fixture["main"])

    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    cursor.insertText("\n# edited by phase04 test\n")
    check("21 dirty tracking",
          editor.is_dirty() and dirty_events and dirty_events[-1] is True)

    check("24 method navigation",
          editor.goto_line(on_create.start_line)
          and editor.current_line_number() == on_create.start_line
          and ".method public onCreate" in editor.document().findBlockByNumber(
              on_create.start_line - 1).text())

    saved, save_error = safe_write_smali(
        fixture["main"], editor.serialize_text(), allowed_roots=roots)
    editor.mark_saved()
    with open(fixture["main"], "r", encoding="utf-8") as handle:
        saved_text = handle.read()
    check("22 save writes Smali file",
          saved and "# edited by phase04 test" in saved_text
          and not editor.is_dirty())

    before = saved_text
    denied, denied_error = safe_write_smali(
        fixture["main"], "should not be written",
        allowed_roots=[os.path.join(fixture["decoded"], "smali_classes3")])
    with open(fixture["main"], "r", encoding="utf-8") as handle:
        after = handle.read()
    check("23 save failure preserves original",
          not denied and bool(denied_error) and before == after)

    invalid = os.path.join(tmp, "invalid_utf8.smali")
    with open(invalid, "wb") as handle:
        handle.write(b"\xff\xfe.class public Lbad/Encoding;")
    invalid_text, invalid_error = read_smali_text(invalid)
    invalid_parsed = parse_smali_file(invalid)
    check("23b invalid UTF-8 handled safely",
          invalid_text is None and bool(invalid_error)
          and bool(invalid_parsed.parse_error))

    # 25. Search.
    method_hits = search_smali(index, "onCreate", scope="Smali methods")
    text_hits = search_smali(index, "hello", scope="Smali source text")
    file_hits = search_smali(index, "Util", scope="Smali files")
    check("25 Smali search",
          any(hit["path"] == fixture["main"] and hit["line"] == 16
              for hit in method_hits)
          and any(hit["path"] == fixture["main"] and hit["line"] == 18
                  and "hello" in hit["text"] for hit in text_hits)
          and any(hit["path"] == fixture["util"] for hit in file_hits),
          "methods=%r text=%r files=%r"
          % (method_hits, text_hits, file_hits))

    # 26. AppState.
    summary_events = []
    app_state.smali_changed.connect(lambda: summary_events.append(True))
    app_state.set_smali_summary(file_count=4, class_count=4, method_count=5,
                                root_count=3, modified_count=1, status="Indexed")
    app_state.set_smali_selection(source=fixture["main"],
                                  class_name="com.example.MainActivity",
                                  method="onCreate")
    app_state.smali_dirty = True
    check("26 AppState Smali updates",
          app_state.smali_file_count == 4
          and app_state.smali_class_count == 4
          and app_state.smali_method_count == 5
          and app_state.smali_root_count == 3
          and app_state.modified_smali_count == 1
          and app_state.current_smali_file == fixture["main"]
          and app_state.current_smali_class == "com.example.MainActivity"
          and app_state.current_smali_method == "onCreate"
          and app_state.smali_dirty is True
          and bool(summary_events))

    # 27. Project.
    project = Project()
    applied = project.apply_smali_index(index)
    project.modified_smali_files = [fixture["main"]]
    project.to_state(app_state)
    check("27 Project Smali state updates",
          applied and project.smali_file_count() == 4
          and project.smali_class_count == 4
          and project.smali_method_count == 6
          and project.smali_roots == roots
          and fixture["main"] in project.smali_files
          and app_state.smali_file_count == 4
          and app_state.modified_smali_count == 1)

    worker_failures = []
    worker = SmaliIndexWorker(roots)
    worker.failed.connect(worker_failures.append)
    worker.request_cancel()
    worker.start()
    stopped = worker.wait(5000)
    app.processEvents()
    check("28 Smali worker cancellation is safe",
          stopped and not worker.isRunning()
          and any("cancelled" in message.lower()
                  for message in worker_failures))

    explorer.close()
    editor.close()
    shutil.rmtree(tmp, ignore_errors=True)

    if FAILED:
        print()
        print("PHASE 04 TEST FAILED (%d)" % len(FAILED))
        for name in FAILED:
            print("  - %s" % name)
        return 1
    print()
    print("PHASE 04 TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

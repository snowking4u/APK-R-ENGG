# APK Reverse Engineering IDE

A Windows desktop application for reverse engineering Android APK files
(decode, analyse, patch, rebuild, sign) built with **Python** and
**PySide6 (Qt)**.

> **Current phase: Phase 04 - Smali discovery, editing and navigation.**
> Existing decoded projects can be inspected and their Smali edited and
> saved safely. Rebuilding, signing, patching and analysis graphs are not
> implemented yet.

## Purpose

Provide a professional, dark-themed IDE shell that will eventually host:

- APK loading and decoding (Apktool-based)
- Java decompilation (JADX-style)
- Viewing / editing Smali
- Static analysis (calls, called-by, graphs, search)
- Patching, rebuilding and signing APKs

## Technology

| Item | Choice |
|------|--------|
| Language | Python 3.10+ |
| GUI Framework | PySide6 (Qt 6) |
| Platform | Windows desktop |
| Backend | None (local only) |
| Database | None (in-memory indexes only) |

## Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` only contains `PySide6` — no JADX, Apktool, Android
SDK or other heavy external tools are required. Phase 04 only reads an
already-decoded project directory; it never starts Apktool or JADX.

## Run

```bash
python -m app.main
```

Or:

```bash
python app/main.py
```

## Tests

Non-interactive suites (offscreen Qt, temporary fixtures):

```bash
python -m tests.smoke_test
python -m tests.phase02_test
python -m tests.phase04_test
```

Phase 04 covers Smali root/file discovery, parsing, multiple
`smali_classesN` directories, malformed-file tolerance, project-tree
generation, editor dirty tracking, safe saving, search, method
navigation and Java <-> Smali mapping.

## Implemented features (Phase 04)

- Dark, professional developer-tool theme and full IDE shell
  (menus, toolbar, docks, status bar, Console)
- **Open Project** loads an existing decoded directory (or a workspace
  containing `decoded/`) without running Apktool or JADX
- Dynamic Smali discovery: `smali`, `smali_classes2..N` and other
  non-standard `smali*` roots, scanned recursively
- Smali parser: class, package, superclass, interfaces, source name,
  fields, methods, descriptors and line ranges
- Searchable in-memory Smali index built on a background worker
- Project Explorer Smali tree: roots -> files -> methods, with lazy
  method/field children and navigation
- Editable Smali editor with Smali syntax highlighting, line numbers,
  dirty marker, Save and unsaved-change confirmation
- Safe saving: UTF-8, atomic temp-file replace, decoded-root allow-list
  and clear failure messages; the original file is preserved on failure
- Search scopes: Smali files, classes, methods and source text
- Java <-> Smali mapping by exact class name only (never guessed);
  multiple matches are reported instead of picking one
- APK Info panel shows Smali directories, file/class/method counts and
  modified-file count
- Status bar and Console report indexing, opening, saving and failures
- Placeholder actions never crash: they show
  *"Feature will be implemented in a later development phase."*

## Architecture

```
app/
    main.py                 Application entry point
    ui/
        main_window.py      Main window: menus, docks, navigation
        project_panel.py    Project Explorer tree (Java + Smali)
        code_editor.py      Editor with line numbers / highlighting
        bottom_panel.py     Tabbed bottom panel + Console + Search
        apk_info_panel.py   APK / Smali metadata panel
        smali_worker.py     Background Smali index worker
        toolbar.py          Main toolbar
        syntax.py           Java and Smali highlighting
        theme.py            Dark theme loader
    core/
        state.py            Central AppState (signals + properties)
        project.py          Project model
        smali_discovery.py  Dynamic Smali root/file discovery
        smali_parser.py     Smali class/method/field parser
        smali_index.py      Smali index, search, mapping, safe save
        java_index.py       Existing Java source index
        logger.py           Signal-based internal logger
    resources/
        styles/dark.qss     Dark theme stylesheet
        icons/              Icon assets (reserved)
tests/
    smoke_test.py           Non-interactive launch test
    phase02_test.py         APK/project core tests
    phase04_test.py         Smali discovery/editing tests
```

## Future phases (planned)

| Phase | Content |
|-------|---------|
| 02 | APK loading / project management |
| 03 | APK decoding (Apktool) and Java decompilation (JADX) |
| 04 | Smali discovery, parsing, editing, search and navigation |
| 05 | Static analysis: calls, called-by, graphs |
| 06 | Patching |
| 07 | Rebuilding and signing |
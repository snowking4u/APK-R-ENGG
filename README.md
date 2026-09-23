# APK Reverse Engineering IDE

A Windows desktop application for reverse engineering Android APK files
(decode, analyse, patch, rebuild, sign) built with **Python** and
**PySide6 (Qt)**.

> **Current phase: Phase 01 - UI / Foundation only.**
> No APK decoding, decompilation, smali processing, patching, rebuilding
> or signing is implemented yet.

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
| Database | None (Phase 01) |

## Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` only contains `PySide6` — no JADX, Apktool, Android
SDK or other heavy external tools are required for this phase.

## Run

```bash
python -m app.main
```

Or:

```bash
python app/main.py
```

## Smoke test

A non-interactive launch test that verifies the window, layout, state
and actions without opening a visible window:

```bash
python -m tests.smoke_test
```

## Implemented features (Phase 01)

- Dark, professional developer-tool theme (QSS stylesheet)
- Main window with menu bar, toolbar, dock panels and status bar
- Full menu structure:
  - **File**: Open APK, Open Project, Save, Save As, Exit
  - **View**: Project Explorer, Java View, Smali View, Bottom Panel, Reset Layout
  - **Build**: Rebuild, Sign, Rebuild & Sign, Clean
  - **Analysis**: Explain, Patch Assistant, Calls, Called By, Graph, Search
  - **Help**: About
- Toolbar: Open APK, Save, Rebuild, Sign, Rebuild + Sign, Clean
- Left **Project Explorer** panel with placeholder tree
  (`Classes`, `Resources`, `Assets`, `Manifest`)
- Central horizontal splitter with **Java Decompiled View** (read-only)
  and **Smali View** (editable), monospace fonts, line-number gutters
  and a pluggable syntax-highlighting framework
- Tabbed **bottom panel**: Explain, Patch Assistant, Calls, Called By,
  Graph, Search, **Console**
- Signal-based **Console** that displays application log messages
- **Status bar** with live-updating labels
  (`Ready`, `Project`, `Classes`, `Methods`, `Resources`, `Build`)
- Central application state model (`AppState`) plus a `Project` model
  ready for future phases
- Reusable internal logger (no `print()` scattered in the code)
- Placeholder actions never crash: they show
  *"Feature will be implemented in a later development phase."*

## Architecture

```
app/
    main.py                 Application entry point
    ui/
        main_window.py      Main window: menus, docks, status bar
        project_panel.py    Project Explorer tree
        code_editor.py      Editor with line numbers / highlighting
        bottom_panel.py     Tabbed bottom panel + Console
        toolbar.py          Main toolbar
        syntax.py           Syntax highlighting framework (future-ready)
        theme.py            Dark theme loader
    core/
        state.py            Central AppState (signals + properties)
        project.py          Project model
        logger.py           Signal-based internal logger
    resources/
        styles/dark.qss     Dark theme stylesheet
        icons/              Icon assets (reserved)
    tests/
        smoke_test.py       Non-interactive launch test
```

## Future phases (planned)

| Phase | Content |
|-------|---------|
| 02 | APK loading / project management |
| 03 | APK decoding (Apktool) and resource tree |
| 04 | Java decompilation (JADX integration) |
| 05 | Smali view / editing |
| 06 | Static analysis: calls, called-by, graphs, search |
| 07 | Patching |
| 08 | Rebuilding and signing |
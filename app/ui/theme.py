"""Theme (stylesheets) helpers.

Loads the dark theme QSS file embedded in the application resources.
"""

import os

_THEME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "styles")
_THEME_FILE = os.path.join(_THEME_DIR, "dark.qss")


def stylesheet_path() -> str:
    """Absolute path of the active stylesheet file."""
    return _THEME_FILE


def load_stylesheet() -> str:
    """Return the QSS stylesheet text to apply to the application."""
    try:
        with open(_THEME_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""
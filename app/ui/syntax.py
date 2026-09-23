"""Syntax highlighting architecture (prepared for future phases).

Phase 01 installs the *framework* only: a base highlighter that can be
extended later with real Java / Smali grammars. The shipped subclasses
provide a conservative set of generic rules (keywords, strings, comments)
so the editors look like proper developer views without any real
parsing or analysis.
"""

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtCore import QRegularExpression


def _format(fg, bold=False, italic=False):
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(fg))
    if bold:
        fmt.setFontWeight(QFont.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


_KEYWORD_FORMAT = _format("#569cd6", bold=True)
_STRING_FORMAT = _format("#ce9178")
_COMMENT_FORMAT = _format("#6a9955", italic=True)
_NUMBER_FORMAT = _format("#b5cea8")
_BUILTIN_FORMAT = _format("#4fc1ff")


class BaseHighlighter(QSyntaxHighlighter):
    """Extensible highlighter skeleton.

    Subclasses override :attr:`rules` (a ``[(regex, format), ...]`` list)
    and/or :meth:`highlightBlock` directly to implement real grammars.
    """

    rules = []
    keyword_format = _KEYWORD_FORMAT
    string_format = _STRING_FORMAT
    comment_format = _COMMENT_FORMAT
    number_format = _NUMBER_FORMAT
    builtin_format = _BUILTIN_FORMAT

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            expression = QRegularExpression(pattern)
            match = expression.match(text)
            while match.hasMatch():
                start = match.capturedStart()
                length = match.capturedLength()
                if length > 0:
                    self.setFormat(start, length, fmt)
                match = expression.match(text, start + max(length, 1))


def _keywords_rule(*keywords):
    pattern = "\\b(" + "|".join(keywords) + ")\\b"
    return QRegularExpression(pattern), _KEYWORD_FORMAT


class JavaHighlighter(BaseHighlighter):
    """Placeholder Java highlighter. Extend with full Java grammar later."""

    keywords = (
        "abstract assert boolean break byte case catch char class const "
        "continue default do double else enum extends final finally float "
        "for if goto implements import instanceof int interface long native "
        "new package private protected public return short static strictfp "
        "super switch synchronized this throw throws transient try void "
        "volatile while"
    ).split()

    rules = [
        _keywords_rule(*keywords),
        (r'"[^"\\]*(\\.[^"\\]*)*"', _STRING_FORMAT),
        (r"\b\d[\d_]*[fFlLdD]?\b", _NUMBER_FORMAT),
        (r"//[^\n]*", _COMMENT_FORMAT),
        (r"/\*.*?\*/", _COMMENT_FORMAT),
    ]


class SmaliHighlighter(BaseHighlighter):
    """Placeholder Smali highlighter. Extend with full Smali grammar later."""

    keywords = (
        "move return goto if invoke new-instance const sput iget "
        "field method public private protected static final declared-signed "
        "synchronized volatile bridge synthetic constructor"
    ).split()

    rules = [
        _keywords_rule(*keywords),
        (r'"([^"\\]|\\.)*"', _STRING_FORMAT),
        (r"\b0x[0-9a-fA-F]+\b", _NUMBER_FORMAT),
        (r"#[^\n]*", _COMMENT_FORMAT),
        (r"^\.\w+", _BUILTIN_FORMAT),
    ]


HIGHLIGHTERS = {"java": JavaHighlighter, "smali": SmaliHighlighter}
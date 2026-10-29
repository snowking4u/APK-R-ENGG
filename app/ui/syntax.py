"""Syntax highlighting architecture.

Phase 01 installed the *framework*; Phase 03 adds a real (but still
purely lexical) Java grammar for the decompiled-source viewer. The
highlighter never parses or executes anything - it only assigns colors
to text ranges.

Java rules (applied per line, later rules win on overlap):

1. comments / strings / chars / literals are blanked by the base class so
   keywords inside them are never colored,
2. types, annotations, declarations and modifiers,
3. keywords and control keywords,
4. strings, characters, numbers and comments (highest priority).
"""

import re

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
_TYPE_FORMAT = _format("#4ec9b0")
_ANNOTATION_FORMAT = _format("#dcdcaa")
_DECLARATION_FORMAT = _format("#dcdcaa", bold=True)
_MODIFIER_FORMAT = _format("#569cd6")
_PACKAGE_FORMAT = _format("#c586c0")
_IMPORT_FORMAT = _format("#c586c0")
_METHOD_FORMAT = _format("#dcdcaa")
_CHAR_FORMAT = _format("#569cd6")


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
            expression = pattern if isinstance(pattern, QRegularExpression) \
                else QRegularExpression(pattern)
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


class MultiLineHighlighter(BaseHighlighter):
    """Adds multi-line block comment support via block state."""

    def highlightBlock(self, text):
        state = self.previousBlockState()

        if state == 1:                      # inside /* ... */
            end = text.find("*/")
            if end == -1:
                self.setFormat(0, len(text), self.comment_format)
                self.setCurrentBlockState(1)
                return
            self.setFormat(0, end + 2, self.comment_format)
            state = 0

        if text.find("/*") != -1:
            start = text.find("/*")
            end = text.find("*/", start + 2)
            if end != -1:
                self.setFormat(start, end + 2 - start, self.comment_format)
            else:
                self.setFormat(start, len(text) - start, self.comment_format)
                state = 1

        for pattern, fmt in self.rules:
            if fmt is None:
                continue
            expression = pattern if isinstance(pattern, QRegularExpression) \
                else QRegularExpression(pattern)
            match = expression.match(text)
            while match.hasMatch():
                start = match.capturedStart()
                length = match.capturedLength()
                if length > 0:
                    self.setFormat(start, length, fmt)
                match = expression.match(text, start + max(length, 1))

        self.setCurrentBlockState(state)


class JavaHighlighter(MultiLineHighlighter):
    """Java highlighter for JADX-generated (decompiled) source."""

    keywords = (
        "abstract assert boolean break byte case catch char class const "
        "continue default do double else enum extends final finally float "
        "for if goto implements import instanceof int interface long native "
        "new package private protected public return short static strictfp "
        "super switch synchronized this throw throws transient try void "
        "volatile while"
    ).split()

    control_keywords = (
        "if else for while do switch case break continue return throw "
        "try catch finally synchronized assert yield"
    ).split()

    literals = ["true", "false", "null"]

    modifiers = (
        "public protected private static final abstract native "
        "synchronized transient volatile strictfp default sealed"
    ).split()

    types = (
        "boolean byte char double float int long short void String Object "
        "Integer Long Boolean Byte Short Character Float Double Number "
        "Math System Thread Runnable Exception Throwable Error Class "
        "Override Deprecated SuppressWarnings FunctionalInterface "
        "SafeVarargs List Map Set Collection ArrayList HashMap HashSet "
        "Iterator Optional ListenableFuture"
    ).split()

    rules = [
        # -- declarations ------------------------------------------------ #
        (r"\b(package)(\s+)([\w.]+)", _PACKAGE_FORMAT),
        (r"\b(import)(\s+)(static\s+)?([\w.$]+(?:\.\*)?)", _IMPORT_FORMAT),
        (r"(@interface|class|enum|record|interface)\s+([A-Za-z_$][\w$]*)",
         _DECLARATION_FORMAT),
        (r"\bnew\s+([A-Z][\w$]*)(\s*<[^;{}()]*>)?\s*\(", _TYPE_FORMAT),
        (r"\b(?:extends|implements|throws|instanceof)\s+([A-Z][\w$]*)",
         _TYPE_FORMAT),
        # -- annotations ------------------------------------------------- #
        (r"@[A-Za-z_$][\w$.]*", _ANNOTATION_FORMAT),
        # -- method declarations (recolored by the keyword rules below) ---- #
        (r"(?:(?:public|protected|private|static|final|abstract|native|"
         r"synchronized|default)\s+)+"
         r"(?:[A-Za-z_$][\w$.]*(?:\s*<[^<>;{}()]*>)?(?:\s*\[\s*\])*\s+)"
         r"[A-Za-z_$][\w$]*(?=\s*\()", _METHOD_FORMAT),
        # -- modifiers / keywords / types --------------------------------- #
        _keywords_rule(*modifiers),
        _keywords_rule(*control_keywords),
        _keywords_rule(*literals),
        _keywords_rule(*keywords),
        _keywords_rule(*types),
        # -- literals (highest priority) ---------------------------------- #
        (r'"(?:\\.|[^"\\])*"', _STRING_FORMAT),
        (r"'\\.|[^\\']'", _CHAR_FORMAT),
        (r"\b0[xX][0-9a-fA-F_]+[lL]?\b", _NUMBER_FORMAT),
        (r"\b0[bB][01_]+[lL]?\b", _NUMBER_FORMAT),
        (r"\b\d[\d_]*\.?[\d_]*(?:[eE][+-]?\d+)?[fFdDlL]?\b", _NUMBER_FORMAT),
        (r"//[^\n]*", _COMMENT_FORMAT),
    ]


_SMALI_DIRECTIVE_FORMAT = _format("#c586c0", bold=True)
_SMALI_INSTRUCTION_FORMAT = _format("#569cd6")
_SMALI_REGISTER_FORMAT = _format("#9cdcfe")
_SMALI_LABEL_FORMAT = _format("#d7ba7d", bold=True)
_SMALI_TYPE_FORMAT = _format("#4ec9b0")

_SMALI_INSTRUCTIONS = (
    "const const/4 const/16 const/high16 const-wide const-string "
    "move move/from16 move/16 move-object move-result move-result-wide "
    "move-exception move-wide invoke-virtual invoke-super "
    "invoke-direct invoke-static invoke-interface invoke-virtual/range "
    "invoke-static/range return return-void return-object return-wide "
    "if-eq if-ne if-lt if-ge if-gt if-le if-eqz if-nez if-ltz if-gez "
    "if-gtz if-lez goto goto/16 goto/32 new-instance new-array "
    "filled-new-array check-cast instance-of iget iget-object iget-wide "
    "iget-boolean iget-byte iget-char iget-short iput iput-object "
    "iput-wide iput-boolean sget sget-object sget-wide sput sput-object "
    "sput-wide throw monitor-enter monitor-exit array-length aget aput "
    "add sub mul div rem and or xor shl shr ushr cmp neg not int-to-long "
    "int-to-float packed-switch sparse-switch fill-array-data nop"
).split()

_SMALI_INSTRUCTION_PATTERN = r"\b(?:" + "|".join(
    re.escape(item) for item in sorted(_SMALI_INSTRUCTIONS, key=len,
                                       reverse=True)) + r")\b"


class SmaliHighlighter(BaseHighlighter):
    """Lexical Smali highlighter (Phase 04).

    Purely decorative: directives, instruction mnemonics, registers,
    labels, descriptors, strings, numbers and comments are colored. No
    instruction is validated or executed.
    """

    instructions = _SMALI_INSTRUCTIONS

    rules = [
        # -- directives -------------------------------------------------- #
        (r"(?m)^[ \t]*\.[A-Za-z_]+", _SMALI_DIRECTIVE_FORMAT),
        (r"\.end[ \t]+(?:method|field|annotation|param)", _SMALI_DIRECTIVE_FORMAT),
        # -- instruction mnemonics -------------------------------------- #
        (_SMALI_INSTRUCTION_PATTERN, _SMALI_INSTRUCTION_FORMAT),
        # -- labels / registers ----------------------------------------- #
        (r"(?m)(?:^|(?<=\s)):[A-Za-z0-9_]+", _SMALI_LABEL_FORMAT),
        (r"\b[vp]\d+\b", _SMALI_REGISTER_FORMAT),
        # -- types / descriptors ---------------------------------------- #
        (r"\[*L[\w/$]+;", _SMALI_TYPE_FORMAT),
        # -- literals ---------------------------------------------------- #
        (r"\b-?0x[0-9a-fA-F]+[lLtTsS]?\b", _NUMBER_FORMAT),
        (r"\b-?\d+[lLtTsSfFdD]?\b", _NUMBER_FORMAT),
        (r'"(?:\\.|[^"\\])*"', _STRING_FORMAT),
    ]

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            expression = pattern if isinstance(pattern, QRegularExpression) \
                else QRegularExpression(pattern)
            match = expression.match(text)
            while match.hasMatch():
                start = match.capturedStart()
                length = match.capturedLength()
                if length > 0:
                    self.setFormat(start, length, fmt)
                match = expression.match(text, start + max(length, 1))
        comment = _smali_comment_start(text)
        if comment >= 0:
            self.setFormat(comment, len(text) - comment, self.comment_format)


def _smali_comment_start(text):
    """Index of the first ``#`` outside a string literal, or ``-1``."""
    quoted = False
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quoted:
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
            continue
        if char == "#" and not quoted:
            return index
    return -1


HIGHLIGHTERS = {"java": JavaHighlighter, "smali": SmaliHighlighter}
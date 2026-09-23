"""Code editor widget.

A QPlainTextEdit companion featuring:
  - monospaced font
  - line number gutter
  - optional read-only mode
  - pluggable syntax highlighter (see ``app/ui/syntax.py``)
"""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from app.ui.syntax import HIGHLIGHTERS

_LINE_BG = QColor("#1e1e1e")
_LINE_FG = QColor("#6b6b6b")
_LINE_BORDER = QColor("#2d2e31")
_LINE_SELECTION_BG = QColor("#26282c")


class _LineNumberArea(QWidget):
    """Gutter widget that paints line numbers for a CodeEditor."""

    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    """Rich-text-free editor with a line-number gutter and highlighting."""

    def __init__(self, language="text", read_only=False, placeholder="", parent=None):
        super().__init__(parent)
        self._language = language
        self._line_area = _LineNumberArea(self)

        self.setReadOnly(read_only)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))

        if placeholder:
            self.setPlaceholderText(placeholder)

        self._init_highlighter()

        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)

        self._update_line_area_width(0)
        self._highlight_current_line()
        if read_only:
            # Subtle background tint to signal read-only in the editor list.
            self.setStyleSheet("QPlainTextEdit { background-color: #202126; }")

    # ------------------------------------------------------------------ #
    # Public API (used by future phases)
    # ------------------------------------------------------------------ #
    @property
    def language(self):
        return self._language

    def set_content(self, text):
        """Replace editor content without touching undo history weirdness."""
        self.setPlainText(text or "")

    def highlighter(self):
        return self._highlighter

    # ------------------------------------------------------------------ #
    # Highlighter
    # ------------------------------------------------------------------ #
    def _init_highlighter(self):
        klass = HIGHLIGHTERS.get(self._language)
        self._highlighter = klass(self) if klass else None

    # ------------------------------------------------------------------ #
    # Line number gutter
    # ------------------------------------------------------------------ #
    def line_number_area_width(self):
        digits = max(2, len(str(self.blockCount())))
        return 8 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_area_width(self, _=0):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_area(self, rect, dy):
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def paint_line_numbers(self, event):
        area = self._line_area
        painter = QPainter(area)
        painter.fillRect(event.rect(), _LINE_BG)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(_LINE_FG)
                painter.drawText(0, top, area.width() - 5, self.fontMetrics().height(),
                                 Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

        painter.setPen(_LINE_BORDER)
        painter.drawLine(area.width() - 1, 0, area.width() - 1, area.height())

    # ------------------------------------------------------------------ #
    # Current-line highlight (subtle, IDE-like)
    # ------------------------------------------------------------------ #
    def _highlight_current_line(self):
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(_LINE_SELECTION_BG)
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])
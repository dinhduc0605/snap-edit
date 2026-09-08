"""
text_item.py - Editable text annotation item.

Double-click to enter edit mode; single-click to select and move.
A semi-transparent rounded-rectangle background is painted behind the text.
"""

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import (
    QPen, QBrush, QColor, QPainter, QFont, QTextCursor,
)
from PyQt6.QtWidgets import (
    QGraphicsTextItem,
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)


# Default visual constants
_DEFAULT_FONT_FAMILY = "Segoe UI"
_DEFAULT_FONT_SIZE = 14
_DEFAULT_TEXT_COLOR = QColor("#FF0000")
_DEFAULT_BG_COLOR = QColor(255, 255, 255, 180)
_PLACEHOLDER = "Type here..."
_BG_BORDER_COLOR = QColor(200, 200, 200, 120)
_BG_RADIUS = 4.0


class TextItem(QGraphicsTextItem):
    """
    An editable text annotation with a semi-transparent background.

    * Double-click → enter edit mode (text cursor appears).
    * Click / Escape → exit edit mode, item becomes movable.
    * Placeholder text *"Type here…"* is shown on creation and removed on focus out.

    Parameters
    ----------
    text_color : QColor
        Initial text colour (default red).
    font_size : int
        Initial font size in image pixels (default 14).
    bg_color : QColor
        Background colour (default semi-transparent white).
    parent : QGraphicsItem | None
        Optional parent item.
    """

    def __init__(
        self,
        text_color: QColor = _DEFAULT_TEXT_COLOR,
        font_size: int = _DEFAULT_FONT_SIZE,
        bg_color: QColor = _DEFAULT_BG_COLOR,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)

        self._text_color: QColor = QColor(text_color)
        self._font_size: int = font_size
        self._bg_color: QColor = QColor(bg_color)
        self._is_placeholder: bool = True

        # Flags
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        # Font
        font = QFont(_DEFAULT_FONT_FAMILY, self._font_size)
        # Scene coordinates are image pixels, independent of the export
        # device's DPI; the editor scales defaults for the current monitor.
        font.setPixelSize(self._font_size)
        font.setBold(True)
        self.setFont(font)
        self.setDefaultTextColor(self._text_color)

        # Start with placeholder
        self.setPlainText(_PLACEHOLDER)
        self.document().contentsChanged.connect(self._sync_placeholder_state)

        # Enter edit mode immediately
        self._enter_edit_mode(select_all=True)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def font_size(self) -> int:
        return self._font_size

    @property
    def text_color(self) -> QColor:
        return self._text_color

    @property
    def bg_color(self) -> QColor:
        return self._bg_color

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_font_size(self, size: int) -> None:
        """Change the font size in image pixels."""
        self._font_size = max(6, size)
        font = self.font()
        font.setPixelSize(self._font_size)
        self.setFont(font)
        self.update()

    def set_text_color(self, color: QColor) -> None:
        """Change the text colour."""
        self._text_color = QColor(color)
        self.setDefaultTextColor(self._text_color)
        self.update()

    def set_bg_color(self, color: QColor) -> None:
        """Change the background colour."""
        self._bg_color = QColor(color)
        self.update()

    # ------------------------------------------------------------------
    # Edit-mode helpers
    # ------------------------------------------------------------------

    def _sync_placeholder_state(self) -> None:
        """Mark edited placeholder content as real text."""
        if self._is_placeholder and self.toPlainText() != _PLACEHOLDER:
            self._is_placeholder = False

    def _enter_edit_mode(self, select_all: bool = False) -> None:
        """Enable text editing without selecting existing content."""
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction
        )
        self.setFocus()
        if select_all:
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            self.setTextCursor(cursor)

    def _exit_edit_mode(self) -> None:
        """Disable text editing so the item can be moved."""
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction
        )
        # Clear selection
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)

    # ------------------------------------------------------------------
    # QGraphicsItem overrides
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        """Slightly expanded rect to include the background padding."""
        r = super().boundingRect()
        padding = 4.0
        return r.adjusted(-padding, -padding, padding, padding)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Draw background rect, then delegate text rendering to super."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # --- Background ---
        bg_rect = super().boundingRect().adjusted(-2, -2, 2, 2)
        painter.setPen(QPen(_BG_BORDER_COLOR, 1.0, Qt.PenStyle.SolidLine))
        painter.setBrush(QBrush(self._bg_color))
        painter.drawRoundedRect(bg_rect, _BG_RADIUS, _BG_RADIUS)

        # --- Text ---
        super().paint(painter, option, widget)

    # ------------------------------------------------------------------
    # Event overrides
    # ------------------------------------------------------------------

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Enter edit mode on double-click."""
        if self._is_placeholder and self.toPlainText() == _PLACEHOLDER:
            self._is_placeholder = False
            self.setPlainText("")
        else:
            self._is_placeholder = False
        self._enter_edit_mode()
        super().mouseDoubleClickEvent(event)

        # QGraphicsTextItem selects the word under a double-click. Clear that
        # selection so the next key press inserts text instead of replacing it.
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)

    def focusOutEvent(self, event) -> None:
        """Exit edit mode when focus is lost."""
        self._exit_edit_mode()

        # If text is empty, restore placeholder
        if not self.toPlainText().strip():
            self._is_placeholder = True
            self.setPlainText(_PLACEHOLDER)

        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:
        """Handle Escape key to exit edit mode."""
        if event.key() == Qt.Key.Key_Escape:
            self._exit_edit_mode()
            self.clearFocus()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        If we are NOT in edit mode, accept the press for moving.
        If we ARE in edit mode, let super handle cursor positioning.
        """
        if (
            self.textInteractionFlags()
            == Qt.TextInteractionFlag.NoTextInteraction
        ):
            # Not editing → handle move
            super().mousePressEvent(event)
        else:
            # Editing → let text item handle cursor
            super().mousePressEvent(event)

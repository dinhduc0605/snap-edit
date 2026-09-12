"""Interactive highlight layer for text recognized in an editor screenshot."""
from __future__ import annotations

from collections import defaultdict

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from ocr.worker import OcrLayout, OcrWorker
from theme import ACCENT


_DISCOVERED_FILL = QColor(255, 201, 61, 78)
_DISCOVERED_BORDER = QColor(255, 214, 92, 180)
_SELECTED_FILL = QColor(96, 205, 255, 152)
_SELECTED_BORDER = QColor(196, 239, 255, 235)


class OcrTextOverlay(QGraphicsObject):
    """Draw OCR word boxes and support drag-to-select text in scene pixels."""

    selection_changed = pyqtSignal(str)

    def __init__(self, layout: OcrLayout, bounds: QRectF, parent=None):
        super().__init__(parent)
        self._layout = layout
        self._bounds = QRectF(bounds)
        self._word_rects = [
            QRectF(word.x, word.y, word.width, word.height)
            for word in layout.words
        ]
        self._selected_indices: set[int] = set()
        self._selection_anchor: QPointF | None = None
        self._selection_rect: QRectF | None = None

        self.setZValue(1_000)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setCursor(Qt.CursorShape.IBeamCursor)

    def boundingRect(self) -> QRectF:
        return QRectF(self._bounds)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for index, rect in enumerate(self._word_rects):
            if index in self._selected_indices:
                painter.setBrush(QBrush(_SELECTED_FILL))
                painter.setPen(QPen(_SELECTED_BORDER, 1.0))
            else:
                painter.setBrush(QBrush(_DISCOVERED_FILL))
                painter.setPen(QPen(_DISCOVERED_BORDER, 1.0))
            painter.drawRect(rect)

        if self._selection_rect is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(
                QColor(ACCENT),
                1.0,
                Qt.PenStyle.DashLine,
            ))
            painter.drawRect(self._selection_rect)
        painter.restore()

    @property
    def word_count(self) -> int:
        return len(self._word_rects)

    @property
    def selected_word_count(self) -> int:
        return len(self._selected_indices)

    def has_selection(self) -> bool:
        return bool(self._selected_indices)

    def clear_selection(self) -> None:
        if not self._selected_indices and self._selection_rect is None:
            return
        self._selected_indices.clear()
        self._selection_rect = None
        self._selection_anchor = None
        self.update()
        self.selection_changed.emit("")

    def selected_text(self) -> str:
        """Return selected OCR words in line order, suitable for clipboard."""
        if not self._selected_indices:
            return ""
        if (
            len(self._selected_indices) == len(self._layout.words)
            and self._layout.text
        ):
            return self._layout.text

        lines: dict[int, list] = defaultdict(list)
        for index in self._selected_indices:
            lines[self._layout.words[index].line_index].append(
                self._layout.words[index]
            )

        text_lines = []
        for _, words in sorted(lines.items()):
            words.sort(key=lambda word: (word.word_index, word.x))
            line = " ".join(word.text for word in words)
            if self._layout.language_tag.casefold().startswith("ja"):
                line = OcrWorker._normalize_japanese_text(line)
            text_lines.append(line)
        return "\n".join(text_lines)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self.setFocus()
        self._selection_anchor = event.pos()
        self._selection_rect = QRectF(event.pos(), event.pos())
        self._set_selection_from_rect(self._selection_rect, is_click=True)
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._selection_anchor is None:
            event.ignore()
            return
        self._selection_rect = QRectF(
            self._selection_anchor, event.pos()
        ).normalized()
        self._set_selection_from_rect(self._selection_rect, is_click=False)
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._selection_anchor is not None
        ):
            self._selection_rect = None
            self._selection_anchor = None
            self.update()
            event.accept()
            return
        event.ignore()

    def _set_selection_from_rect(self, rect: QRectF, *, is_click: bool) -> None:
        if is_click:
            selected = {
                index for index, word_rect in enumerate(self._word_rects)
                if word_rect.contains(rect.topLeft())
            }
        else:
            selected = {
                index for index, word_rect in enumerate(self._word_rects)
                if word_rect.intersects(rect)
            }
        if selected == self._selected_indices:
            self.update()
            return
        self._selected_indices = selected
        self.update()
        self.selection_changed.emit(self.selected_text())

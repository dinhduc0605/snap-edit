"""
rect_item.py - Rectangle annotation item.

Draws a rectangle with configurable stroke colour, width, and optional
semi-transparent fill.  Supports 8 resize handles via ResizableItem.
"""

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPen, QBrush, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from .base_item import HandlePosition, ResizableItem


class RectItem(ResizableItem, QGraphicsRectItem):
    """
    A rectangle annotation item with optional fill and resize handles.

    Parameters
    ----------
    rect : QRectF
        Initial rectangle geometry (in item coordinates).
    pen_color : QColor
        Stroke colour (default red).
    pen_width : int
        Stroke width in pixels (default 3).
    parent : QGraphicsItem | None
        Optional parent item.
    """

    def __init__(
        self,
        rect: QRectF,
        pen_color: QColor = QColor("#FF0000"),
        pen_width: int = 3,
        parent: QGraphicsItem | None = None,
    ) -> None:
        QGraphicsRectItem.__init__(self, rect, parent)
        self._init_resizable(pen_color, pen_width)

        self._fill_enabled: bool = False
        self.setAcceptHoverEvents(True)

        # Apply initial pen
        self._apply_pen()

    # ------------------------------------------------------------------
    # Fill management
    # ------------------------------------------------------------------

    @property
    def fill_enabled(self) -> bool:
        """Whether the interior has a fill."""
        return self._fill_enabled

    def set_fill_enabled(self, enabled: bool) -> None:
        """Enable or disable the fill."""
        self._fill_enabled = enabled
        self.update()

    def toggle_fill(self) -> None:
        """Toggle the fill on / off."""
        self._fill_enabled = not self._fill_enabled
        self.update()

    # ------------------------------------------------------------------
    # Pen helpers
    # ------------------------------------------------------------------

    def _apply_pen(self) -> None:
        """Rebuild and apply the QPen from current properties."""
        pen = QPen(self._pen_color, self._pen_width, Qt.PenStyle.SolidLine)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        self.setPen(pen)

    def set_pen_color(self, color: QColor) -> None:
        """Override to also update the Qt pen."""
        super().set_pen_color(color)
        self._apply_pen()

    def set_pen_width(self, width: int) -> None:
        """Override to also update the Qt pen."""
        super().set_pen_width(width)
        self._apply_pen()

    # ------------------------------------------------------------------
    # QGraphicsItem overrides
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        """Expand bounding rect to contain resize handles."""
        r = super().boundingRect()
        margin = max(self._pen_width, 8) / 2.0 + 2.0
        return r.adjusted(-margin, -margin, margin, margin)

    def shape(self) -> QPainterPath:
        """Include resize handles in hit-testing for hover and drag."""
        path = super().shape()
        for handle_rect in self.get_handle_rects(self.rect()):
            path.addRect(handle_rect.adjusted(-5, -5, 5, 5))
        return path

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the rectangle, optional fill, and resize handles."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # --- Fill ---
        if self._fill_enabled:
            fill_color = QColor(self._pen_color)
            fill_color.setAlpha(255)
            painter.setBrush(QBrush(fill_color))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # --- Stroke ---
        pen = QPen(self._pen_color, self._pen_width, Qt.PenStyle.SolidLine)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(pen)

        painter.drawRect(self.rect())

        # --- Resize handles ---
        if self.isSelected():
            self.draw_handles(painter, self.rect())
        elif self._hover_handle != HandlePosition.NONE:
            self.draw_handles(painter, self.rect(), self._hover_handle)

    # ------------------------------------------------------------------
    # Mouse events – delegate to ResizableItem helpers
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.resizable_mouse_press(event, self.rect()):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        new_rect = self.resizable_mouse_move(event)
        if new_rect is not None:
            self.prepareGeometryChange()
            self.setRect(new_rect)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.resizable_mouse_release(event):
            return
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event) -> None:
        self.resizable_hover_move(event, self.rect())
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.resizable_hover_leave(event)
        super().hoverLeaveEvent(event)

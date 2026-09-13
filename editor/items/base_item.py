"""
base_item.py - ResizableItem mixin for annotation items.

Provides 8 resize handles (4 corners + 4 edge midpoints) that appear
when an item is selected. Handles are drawn as white-filled squares
with blue borders. Dragging a handle resizes the item's geometry.
"""

from enum import IntEnum
from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPen, QBrush, QColor, QPainter, QCursor
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
)


class HandlePosition(IntEnum):
    """Enum for the 8 resize handle positions."""
    TOP_LEFT = 0
    TOP_MID = 1
    TOP_RIGHT = 2
    MID_LEFT = 3
    MID_RIGHT = 4
    BOT_LEFT = 5
    BOT_MID = 6
    BOT_RIGHT = 7
    NONE = -1


# Visual constants for resize handles
HANDLE_SIZE: int = 8
HANDLE_HALF: float = HANDLE_SIZE / 2.0
HANDLE_FILL_COLOR = QColor(255, 255, 255)
HANDLE_BORDER_COLOR = QColor(30, 120, 255)
MIN_ITEM_SIZE: float = 10.0
HANDLE_HIT_MARGIN: float = 5.0


def constrained_event_pos(item: QGraphicsItem, event: QGraphicsSceneMouseEvent) -> QPointF:
    """Return an item-local pointer position constrained to the screenshot."""
    scene = item.scene()
    clamp = getattr(scene, "clamp_to_image", None)
    if callable(clamp):
        return item.mapFromScene(clamp(event.scenePos()))
    return event.pos()


def constrain_item_position_change(
    item: QGraphicsItem, change: QGraphicsItem.GraphicsItemChange, value,
):
    """Keep movable annotations inside the image when their position changes."""
    if change != QGraphicsItem.GraphicsItemChange.ItemPositionChange:
        return value
    scene = item.scene()
    clamp = getattr(scene, "constrain_item_position", None)
    if callable(clamp):
        return clamp(item, QPointF(value))
    return value


class ResizableItem:
    """
    Mixin class that adds resize-handle behaviour to QGraphicsItem subclasses.

    Usage:
        class MyItem(ResizableItem, QGraphicsRectItem):
            ...

    The host class must ultimately inherit from QGraphicsItem.
    """

    def _init_resizable(
        self,
        pen_color: QColor = QColor("#FF0000"),
        pen_width: int = 3,
    ) -> None:
        """Initialise resizable-item state. Call from the host __init__."""
        self._pen_color: QColor = QColor(pen_color)
        self._pen_width: int = pen_width
        self._active_handle: HandlePosition = HandlePosition.NONE
        self._drag_origin: Optional[QPointF] = None
        self._drag_rect_origin: Optional[QRectF] = None
        self._hover_handle: HandlePosition = HandlePosition.NONE

        # Common flags for every annotation item
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def pen_color(self) -> QColor:
        """Current pen / stroke colour."""
        return self._pen_color

    @property
    def pen_width(self) -> int:
        """Current pen / stroke width in pixels."""
        return self._pen_width

    def set_pen_color(self, color: QColor) -> None:
        """Set the pen colour and repaint."""
        self._pen_color = QColor(color)
        self.update()

    def set_pen_width(self, width: int) -> None:
        """Set the pen width and repaint."""
        self._pen_width = max(1, width)
        self.update()

    # ------------------------------------------------------------------
    # Handle geometry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_handle_rects(rect: QRectF) -> list[QRectF]:
        """
        Return a list of 8 handle rectangles for the given bounding *rect*,
        ordered by :class:`HandlePosition`.
        """
        x0, y0 = rect.left(), rect.top()
        x1, y1 = rect.right(), rect.bottom()
        xm = (x0 + x1) / 2.0
        ym = (y0 + y1) / 2.0

        def _rect(cx: float, cy: float) -> QRectF:
            return QRectF(cx - HANDLE_HALF, cy - HANDLE_HALF,
                          HANDLE_SIZE, HANDLE_SIZE)

        return [
            _rect(x0, y0),   # TOP_LEFT
            _rect(xm, y0),   # TOP_MID
            _rect(x1, y0),   # TOP_RIGHT
            _rect(x0, ym),   # MID_LEFT
            _rect(x1, ym),   # MID_RIGHT
            _rect(x0, y1),   # BOT_LEFT
            _rect(xm, y1),   # BOT_MID
            _rect(x1, y1),   # BOT_RIGHT
        ]

    @staticmethod
    def get_handle_at_pos(
        pos: QPointF, rect: QRectF, hit_margin: float = 0.0,
    ) -> HandlePosition:
        """Return the handle under *pos*, or ``HandlePosition.NONE``."""
        for idx, hr in enumerate(ResizableItem.get_handle_rects(rect)):
            if hr.adjusted(-hit_margin, -hit_margin, hit_margin, hit_margin).contains(pos):
                return HandlePosition(idx)
        return HandlePosition.NONE

    @staticmethod
    def _cursor_for_handle(handle: HandlePosition) -> QCursor:
        """Return an appropriate resize cursor for *handle*."""
        mapping = {
            HandlePosition.TOP_LEFT:  Qt.CursorShape.SizeFDiagCursor,
            HandlePosition.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
            HandlePosition.BOT_LEFT:  Qt.CursorShape.SizeBDiagCursor,
            HandlePosition.BOT_RIGHT: Qt.CursorShape.SizeFDiagCursor,
            HandlePosition.TOP_MID:   Qt.CursorShape.SizeVerCursor,
            HandlePosition.BOT_MID:   Qt.CursorShape.SizeVerCursor,
            HandlePosition.MID_LEFT:  Qt.CursorShape.SizeHorCursor,
            HandlePosition.MID_RIGHT: Qt.CursorShape.SizeHorCursor,
        }
        return QCursor(mapping.get(handle, Qt.CursorShape.ArrowCursor))

    # ------------------------------------------------------------------
    # Painting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def draw_handles(
        painter: QPainter, rect: QRectF,
        only: HandlePosition = HandlePosition.NONE,
    ) -> None:
        """Draw all handles, or only the hovered handle, around *rect*."""
        painter.save()
        painter.setPen(QPen(HANDLE_BORDER_COLOR, 1.0, Qt.PenStyle.SolidLine))
        painter.setBrush(QBrush(HANDLE_FILL_COLOR))
        for idx, hr in enumerate(ResizableItem.get_handle_rects(rect)):
            if only != HandlePosition.NONE and idx != int(only):
                continue
            painter.drawRect(hr)
        painter.restore()

    # ------------------------------------------------------------------
    # Resize logic
    # ------------------------------------------------------------------

    @staticmethod
    def compute_resized_rect(
        handle: HandlePosition,
        origin_rect: QRectF,
        origin_pos: QPointF,
        current_pos: QPointF,
    ) -> QRectF:
        """
        Compute a new rectangle by dragging *handle* from *origin_pos*
        to *current_pos*, starting from *origin_rect*.
        """
        dx = current_pos.x() - origin_pos.x()
        dy = current_pos.y() - origin_pos.y()

        r = QRectF(origin_rect)

        if handle in (
            HandlePosition.TOP_LEFT, HandlePosition.TOP_MID,
            HandlePosition.TOP_RIGHT,
        ):
            new_top = r.top() + dy
            if r.bottom() - new_top >= MIN_ITEM_SIZE:
                r.setTop(new_top)

        if handle in (
            HandlePosition.BOT_LEFT, HandlePosition.BOT_MID,
            HandlePosition.BOT_RIGHT,
        ):
            new_bot = r.bottom() + dy
            if new_bot - r.top() >= MIN_ITEM_SIZE:
                r.setBottom(new_bot)

        if handle in (
            HandlePosition.TOP_LEFT, HandlePosition.MID_LEFT,
            HandlePosition.BOT_LEFT,
        ):
            new_left = r.left() + dx
            if r.right() - new_left >= MIN_ITEM_SIZE:
                r.setLeft(new_left)

        if handle in (
            HandlePosition.TOP_RIGHT, HandlePosition.MID_RIGHT,
            HandlePosition.BOT_RIGHT,
        ):
            new_right = r.right() + dx
            if new_right - r.left() >= MIN_ITEM_SIZE:
                r.setRight(new_right)

        return r

    # ------------------------------------------------------------------
    # Mouse-event helpers (call from host overrides)
    # ------------------------------------------------------------------

    def resizable_mouse_press(
        self, event: QGraphicsSceneMouseEvent, rect: QRectF,
    ) -> bool:
        """
        Call at the start of ``mousePressEvent``.
        Returns ``True`` if a resize handle was grabbed (caller should
        accept the event and skip the super call).
        """
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        handle = self.get_handle_at_pos(event.pos(), rect, HANDLE_HIT_MARGIN)
        if handle != HandlePosition.NONE:
            self._active_handle = handle
            self._drag_origin = event.pos()
            self._drag_rect_origin = QRectF(rect)
            self.setCursor(self._cursor_for_handle(handle))
            event.accept()
            return True
        return False

    def resizable_hover_move(
        self, event: QGraphicsSceneMouseEvent, rect: QRectF,
    ) -> None:
        """Show a resize handle and cursor as the pointer approaches it."""
        handle = self.get_handle_at_pos(event.pos(), rect, HANDLE_HIT_MARGIN)
        if handle == self._hover_handle:
            return
        self._hover_handle = handle
        if handle == HandlePosition.NONE:
            self.unsetCursor()
        else:
            self.setCursor(self._cursor_for_handle(handle))
        self.update()

    def resizable_hover_leave(self, event: QGraphicsSceneMouseEvent) -> None:
        """Clear hover-only resize affordances when leaving the item."""
        if self._hover_handle == HandlePosition.NONE:
            return
        self._hover_handle = HandlePosition.NONE
        self.unsetCursor()
        self.update()

    def resizable_mouse_move(
        self, event: QGraphicsSceneMouseEvent,
    ) -> Optional[QRectF]:
        """
        Call inside ``mouseMoveEvent``.
        Returns the new ``QRectF`` when a handle is being dragged,
        or ``None`` if no resize is in progress.
        """
        if self._active_handle == HandlePosition.NONE:
            return None

        new_rect = self.compute_resized_rect(
            self._active_handle,
            self._drag_rect_origin,
            self._drag_origin,
            constrained_event_pos(self, event),
        )
        return new_rect

    def itemChange(self, change, value):
        return super().itemChange(
            change, constrain_item_position_change(self, change, value)
        )

    def resizable_mouse_release(
        self, event: QGraphicsSceneMouseEvent,
    ) -> bool:
        """
        Call inside ``mouseReleaseEvent``.
        Returns ``True`` if a resize operation was ended.
        """
        if self._active_handle != HandlePosition.NONE:
            self._active_handle = HandlePosition.NONE
            self._drag_origin = None
            self._drag_rect_origin = None
            self.unsetCursor()
            event.accept()
            return True
        return False

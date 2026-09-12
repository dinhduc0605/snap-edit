"""
arrow_item.py - Arrow annotation item.

Draws a straight line between two points with a filled arrowhead at
the end point.  The arrowhead rotates to match the line angle.
"""

import math

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPen, QBrush, QColor, QPainter, QPainterPath,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)


# Handle visual constants
_HANDLE_RADIUS: float = 5.0
_HANDLE_FILL = QColor(255, 255, 255)
_HANDLE_BORDER = QColor(30, 120, 255)


class ArrowItem(QGraphicsPathItem):
    """
    A straight-line annotation with a filled arrowhead at the end.

    When selected, circular drag handles appear at each endpoint.
    The arrowhead is a filled triangle whose size scales with pen width.

    Parameters
    ----------
    start : QPointF
        Start point (item coordinates).
    end : QPointF
        End point / arrow tip (item coordinates).
    pen_color : QColor
        Line and arrowhead colour (default red).
    pen_width : int
        Line width in pixels (default 3).
    parent : QGraphicsItem | None
        Optional parent item.
    """

    def __init__(
        self,
        start: QPointF,
        end: QPointF,
        pen_color: QColor = QColor("#FF0000"),
        pen_width: int = 3,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)

        self._start_point: QPointF = QPointF(start)
        self._end_point: QPointF = QPointF(end)
        self._pen_color: QColor = QColor(pen_color)
        self._pen_width: int = pen_width

        # Drag state: 0 = start handle, 1 = end handle, -1 = none
        self._dragging_handle: int = -1
        self._hover_handle: int = -1

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True
        )
        self.setAcceptHoverEvents(True)

        self._update_path()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def start_point(self) -> QPointF:
        return QPointF(self._start_point)

    @property
    def end_point(self) -> QPointF:
        return QPointF(self._end_point)

    @property
    def pen_color(self) -> QColor:
        return self._pen_color

    @property
    def pen_width(self) -> int:
        return self._pen_width

    def set_pen_color(self, color: QColor) -> None:
        """Set the line/arrow colour and repaint."""
        self._pen_color = QColor(color)
        self.update()

    def set_pen_width(self, width: int) -> None:
        """Set the line width (also affects arrowhead size) and repaint."""
        self._pen_width = max(1, width)
        self.update()

    def set_endpoints(self, start: QPointF, end: QPointF) -> None:
        """Update start and end points of the arrow."""
        self.prepareGeometryChange()
        self._start_point = QPointF(start)
        self._end_point = QPointF(end)
        self._update_path()
        self.update()

    # ------------------------------------------------------------------
    # Arrowhead geometry
    # ------------------------------------------------------------------

    def _arrowhead_polygon(self) -> QPolygonF:
        """
        Compute the arrowhead triangle at the end point.

        The nominal size scales with pen width, but is capped relative to the
        arrow length so a short arrow cannot turn into an oversized triangle.
        """
        base, height, length = self._arrowhead_dimensions()
        if length <= 0:
            return QPolygonF()

        angle = math.atan2(
            self._end_point.y() - self._start_point.y(),
            self._end_point.x() - self._start_point.x(),
        )

        # Tip at end point
        tip = self._end_point

        # Two base corners, rotated around the tip
        left = QPointF(
            tip.x() - height * math.cos(angle) + (base / 2) * math.sin(angle),
            tip.y() - height * math.sin(angle) - (base / 2) * math.cos(angle),
        )
        right = QPointF(
            tip.x() - height * math.cos(angle) - (base / 2) * math.sin(angle),
            tip.y() - height * math.sin(angle) + (base / 2) * math.cos(angle),
        )

        return QPolygonF([tip, left, right])

    def _arrowhead_dimensions(self) -> tuple[float, float, float]:
        """Return arrowhead base, height, and total arrow length.

        A head may use at most 60% of the arrow's length. Its base preserves
        the normal aspect ratio while shrinking with it, so even a very short
        arrow remains a compact, readable arrow instead of a large triangle.
        """
        dx = self._end_point.x() - self._start_point.x()
        dy = self._end_point.y() - self._start_point.y()
        length = math.hypot(dx, dy)
        if length <= 0:
            return 0.0, 0.0, 0.0

        nominal_base = max(4.0 * self._pen_width, 12.0)
        nominal_height = max(6.0 * self._pen_width, 12.0)
        height = min(nominal_height, length * 0.6)
        base = min(nominal_base, height * nominal_base / nominal_height)
        return base, height, length

    # ------------------------------------------------------------------
    # Path construction
    # ------------------------------------------------------------------

    def _update_path(self) -> None:
        """Rebuild the QPainterPath from start/end points."""
        path = QPainterPath()
        path.moveTo(self._start_point)
        path.lineTo(self._end_point)
        # Also include arrowhead polygon in the path for hit testing
        poly = self._arrowhead_polygon()
        path.addPolygon(poly)
        path.closeSubpath()
        self.setPath(path)

    # ------------------------------------------------------------------
    # QGraphicsItem overrides
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        """Expand bounding rect for handles and arrowhead."""
        r = super().boundingRect()
        margin = max(self._pen_width * 3, _HANDLE_RADIUS * 2, 14) / 2.0 + 4.0
        return r.adjusted(-margin, -margin, margin, margin)

    def shape(self) -> QPainterPath:
        """Return a wider shape for easier mouse interaction."""
        stroker_path = QPainterPath()
        stroker_path.moveTo(self._start_point)
        stroker_path.lineTo(self._end_point)
        # Include arrowhead
        stroker_path.addPolygon(self._arrowhead_polygon())
        stroker_path.closeSubpath()

        from PyQt6.QtGui import QPainterPathStroker
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._pen_width + 8, 14))
        result = stroker.createStroke(stroker_path)
        for center in (self._start_point, self._end_point):
            result.addEllipse(QRectF(
                center.x() - _HANDLE_RADIUS - 5,
                center.y() - _HANDLE_RADIUS - 5,
                (_HANDLE_RADIUS + 5) * 2,
                (_HANDLE_RADIUS + 5) * 2,
            ))
        return result

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the line, arrowhead, and endpoint handles when selected."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Draw the shaft only up to the arrowhead base. A FlatCap keeps the
        # end square without adding a visible block to short arrows.
        dx = self._end_point.x() - self._start_point.x()
        dy = self._end_point.y() - self._start_point.y()
        _, height, length = self._arrowhead_dimensions()

        if length > height:
            angle = math.atan2(dy, dx)
            line_end = QPointF(
                self._end_point.x() - height * math.cos(angle),
                self._end_point.y() - height * math.sin(angle),
            )

            # --- Line ---
            pen = QPen(self._pen_color, self._pen_width, Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawLine(self._start_point, line_end)

        # --- Arrowhead (filled triangle) ---
        arrowhead = self._arrowhead_polygon()
        if not arrowhead.isEmpty():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._pen_color))
            painter.drawPolygon(arrowhead)

        # --- Handles ---
        if self.isSelected():
            self._draw_endpoint_handle(painter, self._start_point)
            self._draw_endpoint_handle(painter, self._end_point)
        elif self._hover_handle == 0:
            self._draw_endpoint_handle(painter, self._start_point)
        elif self._hover_handle == 1:
            self._draw_endpoint_handle(painter, self._end_point)

    @staticmethod
    def _draw_endpoint_handle(painter: QPainter, center: QPointF) -> None:
        """Draw a single circular endpoint handle."""
        painter.save()
        painter.setPen(QPen(_HANDLE_BORDER, 1.5, Qt.PenStyle.SolidLine))
        painter.setBrush(QBrush(_HANDLE_FILL))
        rect = QRectF(center.x() - _HANDLE_RADIUS, center.y() - _HANDLE_RADIUS, _HANDLE_RADIUS * 2, _HANDLE_RADIUS * 2)
        painter.drawEllipse(rect)
        painter.restore()

    # ------------------------------------------------------------------
    # Handle hit-testing
    # ------------------------------------------------------------------

    def _handle_at(self, pos: QPointF) -> int:
        """
        Return 0 if *pos* hits the start handle, 1 for the end handle,
        or -1 for neither.
        """
        if self._point_in_handle(pos, self._start_point):
            return 0
        if self._point_in_handle(pos, self._end_point):
            return 1
        return -1

    @staticmethod
    def _point_in_handle(pos: QPointF, center: QPointF) -> bool:
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        return (dx * dx + dy * dy) <= (_HANDLE_RADIUS + 5) ** 2

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._handle_at(event.pos())
            if handle != -1:
                self._dragging_handle = handle
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._dragging_handle == 0:
            self.prepareGeometryChange()
            self._start_point = event.pos()
            self._update_path()
            self.update()
            return
        if self._dragging_handle == 1:
            self.prepareGeometryChange()
            self._end_point = event.pos()
            self._update_path()
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._dragging_handle != -1:
            self._dragging_handle = -1
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event) -> None:
        handle = self._handle_at(event.pos())
        if handle != self._hover_handle:
            self._hover_handle = handle
            if handle == -1:
                self.unsetCursor()
            else:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hover_handle = -1
        self.unsetCursor()
        self.update()
        super().hoverLeaveEvent(event)

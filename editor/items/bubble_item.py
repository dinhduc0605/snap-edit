"""
bubble_item.py - Numbered circle bubble annotation item.

Draws a filled circle with a centred number in white bold text.
A drop shadow gives the bubble a premium, elevated look.
"""

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPen, QBrush, QColor, QPainter, QPainterPath,
    QFont,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsDropShadowEffect,
    QStyleOptionGraphicsItem,
    QWidget,
)


# Visual constants
_DEFAULT_BUBBLE_SIZE: float = 32.0
_SHADOW_BLUR: int = 8
_SHADOW_OFFSET = QPointF(2.0, 2.0)
_SHADOW_COLOR = QColor(0, 0, 0, 80)
_TEXT_COLOR = QColor(255, 255, 255)
_FONT_FAMILY = "Segoe UI"
_DEFAULT_FONT_PIXEL_SIZE = 16


class BubbleItem(QGraphicsItem):
    """
    A numbered circle bubble (1, 2, 3, …).

    The bubble is filled with a configurable colour and displays the
    number in white bold text.  A subtle drop shadow is applied for
    a premium aesthetic.

    Parameters
    ----------
    number : int
        The number displayed inside the bubble.
    bubble_color : QColor
        Fill colour (default red).
    bubble_size : float
        Base diameter in scene units (default 32).
    parent : QGraphicsItem | None
        Optional parent item.
    """

    def __init__(
        self,
        number: int,
        bubble_color: QColor = QColor("#FF0000"),
        parent: QGraphicsItem | None = None,
        bubble_size: float = _DEFAULT_BUBBLE_SIZE,
    ) -> None:
        super().__init__(parent)

        self._number: int = number
        self._bubble_color: QColor = QColor(bubble_color)
        self._bubble_size: float = max(16.0, min(128.0, float(bubble_size)))

        # Flags – movable and selectable, NOT resizable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(_SHADOW_BLUR)
        shadow.setOffset(_SHADOW_OFFSET)
        shadow.setColor(_SHADOW_COLOR)
        self.setGraphicsEffect(shadow)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def number(self) -> int:
        return self._number

    @number.setter
    def number(self, value: int) -> None:
        self._number = value
        self.update()

    @property
    def bubble_color(self) -> QColor:
        return self._bubble_color

    def set_bubble_color(self, color: QColor) -> None:
        """Set the bubble fill colour and repaint."""
        self._bubble_color = QColor(color)
        self.update()

    @property
    def bubble_size(self) -> float:
        return self._bubble_size

    def set_bubble_size(self, size: float) -> None:
        """Set the base diameter while preserving the DPI item scale."""
        size = max(16.0, min(128.0, float(size)))
        if abs(size - self._bubble_size) < 0.01:
            return
        self.prepareGeometryChange()
        self._bubble_size = size
        self.update()

    # ------------------------------------------------------------------
    # QGraphicsItem overrides
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        """
        Bounding rect includes the bubble plus padding for the
        drop-shadow offset and blur.
        """
        margin = _SHADOW_BLUR / 2.0 + 4.0
        return QRectF(
            -margin, -margin,
            self._bubble_size + 2 * margin,
            self._bubble_size + 2 * margin,
        )

    def shape(self) -> QPainterPath:
        """Circular hit-test shape matching the visible bubble."""
        path = QPainterPath()
        path.addEllipse(QRectF(0.0, 0.0, self._bubble_size, self._bubble_size))
        return path

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the filled circle and centred number text."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # --- Circle ---
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._bubble_color))
        painter.drawEllipse(QRectF(0.0, 0.0, self._bubble_size, self._bubble_size))

        # --- Subtle highlight ring when selected ---
        if self.isSelected():
            highlight_pen = QPen(QColor(255, 255, 255, 200), 2.0,
                                 Qt.PenStyle.SolidLine)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(
                -1.0, -1.0,
                self._bubble_size + 2.0, self._bubble_size + 2.0,
            ))

        # --- Number text ---
        text = str(self._number)
        font = QFont(_FONT_FAMILY)
        font.setPixelSize(max(8, round(
            _DEFAULT_FONT_PIXEL_SIZE * self._bubble_size / _DEFAULT_BUBBLE_SIZE
        )))
        font.setBold(True)

        # Build a glyph path so centering uses the visible strokes instead of
        # the font's advance widths (notably important for "1" in 10, 11...).
        text_path = QPainterPath()
        text_path.addText(QPointF(0.0, 0.0), font, text)
        text_bounds = text_path.boundingRect()

        # Keep multi-digit labels comfortably inside the fixed-size bubble.
        text_max_width = self._bubble_size - 8.0
        if text_bounds.width() > text_max_width:
            fitted_size = max(
                8,
                int(font.pixelSize() * text_max_width / text_bounds.width()),
            )
            font.setPixelSize(fitted_size)
            text_path = QPainterPath()
            text_path.addText(QPointF(0.0, 0.0), font, text)
            text_bounds = text_path.boundingRect()

        bubble_center = QPointF(self._bubble_size / 2.0, self._bubble_size / 2.0)
        painter.save()
        painter.translate(bubble_center - text_bounds.center())
        painter.fillPath(text_path, QBrush(_TEXT_COLOR))
        painter.restore()

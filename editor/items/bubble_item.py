"""
bubble_item.py - Numbered circle bubble annotation item.

Draws a filled circle with a centred number in white bold text.
A drop shadow gives the bubble a premium, elevated look.
"""

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPen, QBrush, QColor, QPainter, QPainterPath,
    QFont, QFontMetrics,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsDropShadowEffect,
    QStyleOptionGraphicsItem,
    QWidget,
)


# Visual constants
_BUBBLE_SIZE: float = 32.0
_SHADOW_BLUR: int = 8
_SHADOW_OFFSET = QPointF(2.0, 2.0)
_SHADOW_COLOR = QColor(0, 0, 0, 80)
_TEXT_COLOR = QColor(255, 255, 255)
_FONT_FAMILY = "Segoe UI"
_FONT_SIZE = 12


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
    parent : QGraphicsItem | None
        Optional parent item.
    """

    def __init__(
        self,
        number: int,
        bubble_color: QColor = QColor("#FF0000"),
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)

        self._number: int = number
        self._bubble_color: QColor = QColor(bubble_color)

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
            _BUBBLE_SIZE + 2 * margin,
            _BUBBLE_SIZE + 2 * margin,
        )

    def shape(self) -> QPainterPath:
        """Circular hit-test shape matching the visible bubble."""
        path = QPainterPath()
        path.addEllipse(QRectF(0.0, 0.0, _BUBBLE_SIZE, _BUBBLE_SIZE))
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
        painter.drawEllipse(QRectF(0.0, 0.0, _BUBBLE_SIZE, _BUBBLE_SIZE))

        # --- Subtle highlight ring when selected ---
        if self.isSelected():
            highlight_pen = QPen(QColor(255, 255, 255, 200), 2.0,
                                 Qt.PenStyle.SolidLine)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(
                -1.0, -1.0,
                _BUBBLE_SIZE + 2.0, _BUBBLE_SIZE + 2.0,
            ))

        # --- Number text ---
        font = QFont(_FONT_FAMILY, _FONT_SIZE)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(_TEXT_COLOR))

        text = str(self._number)
        fm = QFontMetrics(font)
        text_rect = fm.boundingRect(text)

        # Centre the text in the bubble
        cx = _BUBBLE_SIZE / 2.0
        cy = _BUBBLE_SIZE / 2.0
        x = cx - text_rect.width() / 2.0
        y = cy + fm.ascent() / 2.0 - fm.descent() / 2.0

        painter.drawText(QPointF(x, y), text)

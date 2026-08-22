"""Shared Fluent-styled widgets used across SnapEdit surfaces."""

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QSpinBox, QStyle, QStyleOptionSpinBox

from theme import TEXT_DISABLED, TEXT_SECONDARY


class FluentSpinBox(QSpinBox):
    """QSpinBox with DPI-independent painted up/down chevrons."""

    def paintEvent(self, event):
        super().paintEvent(event)

        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(TEXT_SECONDARY if self.isEnabled() else TEXT_DISABLED)
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        controls = (
            (QStyle.SubControl.SC_SpinBoxUp, True),
            (QStyle.SubControl.SC_SpinBoxDown, False),
        )
        for sub_control, points_up in controls:
            rect = self.style().subControlRect(
                QStyle.ComplexControl.CC_SpinBox,
                option,
                sub_control,
                self,
            )
            if not rect.isValid():
                continue

            cx = float(rect.center().x())
            cy = float(rect.center().y())
            offset = -0.5 if points_up else 0.5
            if points_up:
                painter.drawLine(
                    QPointF(cx - 3.5, cy + 1.5 + offset),
                    QPointF(cx, cy - 1.5 + offset),
                )
                painter.drawLine(
                    QPointF(cx, cy - 1.5 + offset),
                    QPointF(cx + 3.5, cy + 1.5 + offset),
                )
            else:
                painter.drawLine(
                    QPointF(cx - 3.5, cy - 1.5 + offset),
                    QPointF(cx, cy + 1.5 + offset),
                )
                painter.drawLine(
                    QPointF(cx, cy + 1.5 + offset),
                    QPointF(cx + 3.5, cy - 1.5 + offset),
                )

        painter.end()

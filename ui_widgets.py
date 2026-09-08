"""Shared Fluent-styled widgets used across SnapEdit surfaces."""

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QLabel, QSpinBox,
    QStyle, QStyleOptionSpinBox, QToolButton, QVBoxLayout,
)

from theme import (
    BORDER, CONTROL_RADIUS, HOVER, SURFACE, TEXT_DISABLED, TEXT_PRIMARY,
    TEXT_SECONDARY,
)


BASIC_COLORS = (
    ("Black", "#000000"),
    ("Dark gray", "#666666"),
    ("Gray", "#B7B7B7"),
    ("White", "#FFFFFF"),
    ("Red", "#FF0000"),
    ("Orange", "#FF9900"),
    ("Yellow", "#FFFF00"),
    ("Green", "#00B050"),
    ("Cyan", "#00B0F0"),
    ("Blue", "#0070C0"),
    ("Purple", "#7030A0"),
    ("Magenta", "#FF00FF"),
)


class BasicColorDialog(QDialog):
    """Compact Fluent-styled picker containing only common solid colors."""

    def __init__(self, initial: QColor = QColor("#FF0000"), parent=None,
                 title: str = "Choose color"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background: {SURFACE};
                color: {TEXT_PRIMARY};
            }}
            QLabel {{ color: {TEXT_SECONDARY}; }}
            QToolButton {{
                border: 2px solid transparent;
                border-radius: {CONTROL_RADIUS}px;
                min-width: 30px;
                min-height: 30px;
            }}
            QToolButton:hover {{
                border-color: {TEXT_PRIMARY};
                background: {HOVER};
            }}
            QDialogButtonBox QPushButton {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {CONTROL_RADIUS}px;
                color: {TEXT_PRIMARY};
                padding: 6px 16px;
            }}
            QDialogButtonBox QPushButton:hover {{ background: {HOVER}; }}
        """)
        self._selected = QColor(initial)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        label = QLabel("Basic colors")
        layout.addWidget(label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        for index, (name, value) in enumerate(BASIC_COLORS):
            color = QColor(value)
            button = QToolButton()
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.setStyleSheet(
                f"QToolButton {{ background: {value}; border: 2px solid "
                f"{'#FFFFFF' if color == self._selected else 'transparent'}; }}"
                f"QToolButton:hover {{ border-color: {TEXT_PRIMARY}; }}"
            )
            button.clicked.connect(lambda checked=False, c=color: self._choose(c))
            grid.addWidget(button, index // 6, index % 6)
        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected_color(self) -> QColor:
        return QColor(self._selected)

    def _choose(self, color: QColor):
        self._selected = QColor(color)
        self.accept()

    @classmethod
    def get_color(cls, initial: QColor, parent=None,
                  title: str = "Choose color") -> QColor:
        dialog = cls(initial, parent, title)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selected_color
        return QColor()


class FluentSpinBox(QSpinBox):
    """QSpinBox with DPI-independent painted up/down chevrons."""

    def paintEvent(self, event):
        super().paintEvent(event)

        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(TEXT_SECONDARY if self.isEnabled() else TEXT_DISABLED)
        scale = self.property("uiScale") or 1.0
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
            painter.save()
            painter.translate(cx, cy)
            painter.scale(scale, scale)
            cx = cy = 0.0
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
            painter.restore()

        painter.end()

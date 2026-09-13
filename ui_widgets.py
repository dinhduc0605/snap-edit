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


def _paint_transparency_hatch(painter: QPainter, rect, selected: bool = False):
    """Paint a full-size diagonal hatch conventionally used for transparency."""
    painter.fillRect(rect, QColor("#F2F2F2"))
    painter.save()
    painter.setClipRect(rect)
    painter.setPen(QPen(QColor("#8A8A8A"), 1.5))
    for offset in range(rect.left() - rect.height(), rect.right() + rect.height(), 6):
        painter.drawLine(offset, rect.bottom(), offset + rect.height(), rect.top())
    painter.restore()
    border_color = TEXT_PRIMARY if selected else BORDER
    painter.setPen(QPen(QColor(border_color), 2 if selected else 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(rect)


class TransparentSwatchButton(QToolButton):
    """A full-size diagonal hatch swatch for selecting no color."""

    def __init__(self, selected: bool, parent=None):
        super().__init__(parent)
        self._selected = selected
        self.setFixedSize(30, 30)
        self.setToolTip("No background color")
        self.setAccessibleName("Transparent")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        _paint_transparency_hatch(
            painter, rect, selected=self._selected or self.underMouse()
        )
        painter.end()


class TransparencyPreviewButton(QToolButton):
    """A wide color-preview button that renders transparent colors as hatching."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_transparent = False

    def set_color_preview(self, color: QColor):
        self._is_transparent = color.alpha() == 0
        if not self._is_transparent:
            self.setStyleSheet(
                f"background: rgba({color.red()}, {color.green()}, {color.blue()}, "
                f"{color.alpha() / 255.0});"
            )
        else:
            self.setStyleSheet("")
        self.update()

    @property
    def is_transparent_preview(self) -> bool:
        return self._is_transparent

    def paintEvent(self, event):
        if not self._is_transparent:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        _paint_transparency_hatch(painter, self.rect().adjusted(1, 1, -1, -1))
        painter.end()


class BasicColorDialog(QDialog):
    """Compact Fluent-styled picker containing only common solid colors."""

    def __init__(self, initial: QColor = QColor("#FF0000"), parent=None,
                 title: str = "Choose color", allow_transparent: bool = False):
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
                color: {TEXT_PRIMARY};
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
        if allow_transparent:
            transparent = TransparentSwatchButton(self._selected.alpha() == 0)
            transparent.clicked.connect(
                lambda: self._choose(QColor(0, 0, 0, 0))
            )
            grid.addWidget(transparent, 0, 0)
        for index, (name, value) in enumerate(BASIC_COLORS):
            color = QColor(value)
            button = QToolButton()
            button.setFixedSize(30, 30)
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.setStyleSheet(
                f"QToolButton {{ background: {value}; border: 2px solid "
                f"{'#FFFFFF' if color == self._selected else 'transparent'}; }}"
                f"QToolButton:hover {{ border-color: {TEXT_PRIMARY}; }}"
            )
            button.clicked.connect(lambda checked=False, c=color: self._choose(c))
            position = index + int(allow_transparent)
            grid.addWidget(button, position // 6, position % 6)
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
                  title: str = "Choose color",
                  allow_transparent: bool = False) -> QColor:
        dialog = cls(initial, parent, title, allow_transparent)
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

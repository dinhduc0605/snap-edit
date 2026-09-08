"""
Toolbar widget for the SnapEdit editor.
Provides tool selection, color picker, and stroke size controls.
Uses emoji text icons (no external icon library required).
"""
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPointF, QRectF, QSignalBlocker
from PyQt6.QtGui import (
    QColor, QIcon, QPainter, QPixmap, QFont, QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QToolButton, QButtonGroup,
    QFrame, QCheckBox, QLabel,
)

from theme import (
    ACCENT, ACCENT_SUBTLE, BASE, BORDER,
    BORDER_SUBTLE, CONTROL_RADIUS, HOVER, PRESSED, SURFACE,
    SURFACE_ALT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TYPE_BODY_PT,
    TYPE_CAPTION_PT, OVERLAY_RADIUS,
)
from ui_widgets import BasicColorDialog, FluentSpinBox


def _toolbar_icon(name: str, size: int = 24) -> QIcon:
    """Create a crisp, font-independent toolbar icon."""
    dpr = 2.0
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(TEXT_PRIMARY)
    pen = QPen(color, 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    scale = size / 22.0
    painter.scale(scale, scale)

    if name == "select":
        path = QPainterPath(QPointF(4.0, 2.5))
        path.lineTo(4.0, 17.5)
        path.lineTo(8.2, 13.4)
        path.lineTo(11.6, 20.0)
        path.lineTo(14.4, 18.5)
        path.lineTo(10.9, 12.2)
        path.lineTo(17.0, 12.2)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "text":
        painter.drawLine(QPointF(5.0, 18.0), QPointF(11.0, 4.0))
        painter.drawLine(QPointF(11.0, 4.0), QPointF(17.0, 18.0))
        painter.drawLine(QPointF(7.5, 12.5), QPointF(14.5, 12.5))
    elif name == "line":
        painter.drawLine(QPointF(3.0, 11.0), QPointF(19.0, 11.0))
    elif name == "arrow":
        painter.drawLine(QPointF(3.0, 11.0), QPointF(18.5, 11.0))
        painter.drawLine(QPointF(13.5, 6.0), QPointF(18.5, 11.0))
        painter.drawLine(QPointF(13.5, 16.0), QPointF(18.5, 11.0))
    elif name == "rect":
        painter.drawRoundedRect(QRectF(4.0, 5.0, 14.0, 12.0), 1.5, 1.5)
    elif name == "ellipse":
        painter.drawEllipse(QRectF(4.0, 4.0, 14.0, 14.0))
    elif name == "bubble":
        painter.drawEllipse(QRectF(3.0, 3.0, 16.0, 16.0))
        painter.drawLine(QPointF(9.5, 9.0), QPointF(11.0, 7.5))
        painter.drawLine(QPointF(11.0, 7.5), QPointF(11.0, 15.0))
        painter.drawLine(QPointF(9.0, 15.0), QPointF(13.0, 15.0))
    elif name in ("undo", "redo"):
        painter.save()
        if name == "redo":
            painter.translate(22.0, 0.0)
            painter.scale(-1.0, 1.0)
        path = QPainterPath(QPointF(8.0, 5.0))
        path.lineTo(3.5, 9.5)
        path.lineTo(8.0, 14.0)
        painter.drawPath(path)
        curve = QPainterPath(QPointF(4.0, 9.5))
        curve.cubicTo(8.0, 6.0, 16.5, 6.0, 18.0, 14.5)
        painter.drawPath(curve)
        painter.restore()
    elif name == "copy":
        painter.drawRoundedRect(QRectF(7.0, 4.0, 11.0, 13.0), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(4.0, 7.0, 11.0, 12.0), 1.5, 1.5)
    elif name == "gallery":
        painter.drawRoundedRect(QRectF(3.0, 4.0, 16.0, 14.0), 1.5, 1.5)
        painter.drawEllipse(QRectF(13.5, 6.5, 2.5, 2.5))
        landscape = QPainterPath(QPointF(5.0, 15.5))
        landscape.lineTo(9.0, 11.0)
        landscape.lineTo(11.5, 13.5)
        landscape.lineTo(14.0, 10.5)
        landscape.lineTo(17.0, 15.5)
        painter.drawPath(landscape)
    elif name == "save":
        painter.drawRoundedRect(QRectF(4.0, 3.0, 14.0, 16.0), 1.5, 1.5)
        painter.drawRect(QRectF(7.0, 3.0, 7.5, 5.0))
        painter.drawRoundedRect(QRectF(7.0, 12.0, 8.0, 7.0), 1.0, 1.0)
    painter.end()
    return QIcon(pixmap)


def _make_btn(icon_name: str, tooltip: str, checkable: bool = False,
              size: int = 24) -> QToolButton:
    """Create a styled QToolButton with a vector icon."""
    btn = QToolButton()
    btn.setIcon(_toolbar_icon(icon_name))
    btn.setIconSize(QSize(24, 24))
    btn.setProperty("iconName", icon_name)
    btn.setToolTip(tooltip)
    btn.setCheckable(checkable)
    btn.setFixedSize(size, size)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setAccessibleName(tooltip.split(" (")[0])
    return btn


class ColorButton(QToolButton):
    """A button that displays and allows picking a color (solid rectangle icon)."""

    color_changed = pyqtSignal(QColor)

    def __init__(self, initial_color: QColor = QColor("#FF3B30"), parent=None):
        super().__init__(parent)
        self._color = initial_color
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick_color)
        self._update_icon()

    def _update_icon(self):
        scale = self.property("uiScale") or 1.0
        size = round(24 * scale)
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.setDevicePixelRatio(2.0)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(scale, scale)
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 24, 24, 4, 4)
        painter.end()
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(size, size))

    def _pick_color(self):
        color = BasicColorDialog.get_color(self._color, self, "Stroke color")
        if color.isValid():
            self._color = color
            self._update_icon()
            self.color_changed.emit(color)

    @property
    def color(self) -> QColor:
        return self._color

    @color.setter
    def color(self, c: QColor):
        self._color = c
        self._update_icon()


class TextColorButton(QToolButton):
    """
    Color picker button that shows a bold 'A' letter rendered in the chosen color,
    with a thin white underline bar — like the Word text-color button.
    """

    color_changed = pyqtSignal(QColor)

    def __init__(self, initial_color: QColor = QColor("#FF0000"), parent=None):
        super().__init__(parent)
        self._color = initial_color
        self.setFixedSize(32, 32)
        self.setToolTip("Text Color")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick_color)
        self._update_icon()

    def _update_icon(self):
        size = 24
        scale = self.property("uiScale") or 1.0
        physical_size = round(size * scale)
        pixmap = QPixmap(physical_size * 2, physical_size * 2)
        pixmap.setDevicePixelRatio(2.0)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.scale(scale, scale)

        # Draw 'A' in current text color with a lighter, elegant font
        font = QFont("Segoe UI")
        font.setPixelSize(16)
        painter.setFont(font)
        painter.setPen(self._color)
        painter.drawText(0, -2, size, size, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "A")

        # Draw thin underline color bar
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawRect(4, size - 4, size - 8, 2)

        painter.end()
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(physical_size, physical_size))

    def _pick_color(self):
        color = BasicColorDialog.get_color(self._color, self, "Text color")
        if color.isValid():
            self._color = color
            self._update_icon()
            self.color_changed.emit(color)

    @property
    def color(self) -> QColor:
        return self._color

    @color.setter
    def color(self, c: QColor):
        self._color = c
        self._update_icon()


class ToolType:
    """Enum-like class for tool types."""
    SELECT  = "select"
    GRAB    = "grab"
    TEXT    = "text"
    ARROW   = "arrow"
    LINE    = "line"
    RECT    = "rect"
    ELLIPSE = "ellipse"
    BUBBLE  = "bubble"


class Toolbar(QWidget):
    """
    Main toolbar for the editor.
    Emits signals when tool, color, or stroke size changes.

    Layout (left → right):
      Select | Text [TextColor] [TextBG] [TextSize] | Line Arrow Rect Ellipse
             | StrokeColor StrokeSize Fill | Bubble | → Undo Redo Copy Save
    """

    tool_changed             = pyqtSignal(str)
    color_changed            = pyqtSignal(QColor)
    stroke_width_changed     = pyqtSignal(int)
    fill_changed             = pyqtSignal(bool)
    text_color_changed       = pyqtSignal(QColor)
    text_bg_color_changed    = pyqtSignal(QColor)
    text_size_changed        = pyqtSignal(int)
    bubble_size_changed      = pyqtSignal(int)
    undo_requested           = pyqtSignal()
    redo_requested           = pyqtSignal()
    save_file_requested      = pyqtSignal()
    copy_clipboard_requested = pyqtSignal()
    gallery_requested        = pyqtSignal()

    def __init__(self, initial_color: QColor = QColor("#FF3B30"),
                 initial_width: int = 5, parent=None, *,
                 initial_bubble_size: int = 32,
                 initial_text_size: int = 14,
                 initial_text_color: QColor | None = None,
                 initial_text_bg_color: QColor | None = None,
                 initial_fill: bool = False):
        super().__init__(parent)
        self._current_tool = ToolType.SELECT
        self._setup_ui(
            initial_color, initial_width, initial_bubble_size,
            initial_text_size, initial_text_color, initial_text_bg_color,
            initial_fill,
        )
        self._apply_styles()

    def _setup_ui(self, initial_color: QColor, initial_width: int,
                  initial_bubble_size: int, initial_text_size: int,
                  initial_text_color: QColor | None,
                  initial_text_bg_color: QColor | None,
                  initial_fill: bool):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        command_row = QHBoxLayout()
        command_row.setContentsMargins(0, 0, 0, 0)
        command_row.setSpacing(4)
        self._command_row = command_row

        self._tool_label = QLabel("Tools")
        self._tool_label.setObjectName("groupLabel")
        command_row.addWidget(self._tool_label)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._tool_buttons: dict[str, QToolButton] = {}

        # Primary tools stay visible; properties are contextual.
        for tool_type, icon_name, tooltip in [
            (ToolType.SELECT,  "select",  "Select (V)"),
            (ToolType.TEXT,    "text",    "Text (T)"),
            (ToolType.LINE,    "line",    "Line (L)"),
            (ToolType.ARROW,   "arrow",   "Arrow (A)"),
            (ToolType.RECT,    "rect",    "Rectangle (R)"),
            (ToolType.ELLIPSE, "ellipse", "Ellipse (E)"),
            (ToolType.BUBBLE,  "bubble",  "Number bubble (B)"),
        ]:
            btn = _make_btn(icon_name, tooltip, checkable=True)
            self._button_group.addButton(btn)
            self._tool_buttons[tool_type] = btn
            command_row.addWidget(btn)

        command_row.addWidget(self._create_separator())

        # Text properties.
        self._text_context = QWidget(self)
        text_layout = QHBoxLayout(self._text_context)
        text_layout.setContentsMargins(4, 0, 4, 0)
        text_layout.setSpacing(8)
        self._text_context_label = QLabel("Text")
        self._text_context_label.setObjectName("contextTitle")
        text_layout.addWidget(self._text_context_label)

        self._text_color_btn = TextColorButton(
            initial_text_color or QColor("#FF0000")
        )
        self._text_color_btn.color_changed.connect(self.text_color_changed.emit)
        self._text_color_btn.setAccessibleName("Text color")
        text_layout.addWidget(self._text_color_btn)

        self._text_bg_btn = ColorButton(
            initial_text_bg_color or QColor("#FFFFFF")
        )
        self._text_bg_btn.setToolTip("Text Background Color")
        self._text_bg_btn.setAccessibleName("Text background color")
        self._text_bg_btn.color_changed.connect(self.text_bg_color_changed.emit)
        text_layout.addWidget(self._text_bg_btn)

        self._text_size_spin = FluentSpinBox()
        self._text_size_spin.setRange(6, 288)
        self._text_size_spin.setValue(initial_text_size)
        self._text_size_spin.setSuffix(" px")
        self._text_size_spin.setFixedWidth(72)
        self._text_size_spin.setToolTip("Text Size")
        self._text_size_spin.setAccessibleName("Text size")
        self._text_size_spin.valueChanged.connect(self.text_size_changed.emit)
        text_layout.addWidget(self._text_size_spin)

        # Shape and bubble properties.
        self._shape_context = QWidget(self)
        shape_layout = QHBoxLayout(self._shape_context)
        shape_layout.setContentsMargins(4, 0, 4, 0)
        shape_layout.setSpacing(8)
        self._shape_context_label = QLabel("Shape")
        self._shape_context_label.setObjectName("contextTitle")
        shape_layout.addWidget(self._shape_context_label)

        self._color_button = ColorButton(initial_color)
        self._color_button.setToolTip("Stroke Color")
        self._color_button.setAccessibleName("Stroke color")
        self._color_button.color_changed.connect(self.color_changed.emit)
        shape_layout.addWidget(self._color_button)

        self._width_spin = FluentSpinBox()
        self._width_spin.setRange(1, 80)
        self._width_spin.setValue(initial_width)
        self._width_spin.setSuffix(" px")
        self._width_spin.setFixedWidth(72)
        self._width_spin.setToolTip("Stroke width")
        self._width_spin.setAccessibleName("Stroke width")
        self._width_spin.valueChanged.connect(self.stroke_width_changed.emit)
        shape_layout.addWidget(self._width_spin)

        self._bubble_size_spin = FluentSpinBox()
        self._bubble_size_spin.setRange(16, 128)
        self._bubble_size_spin.setValue(initial_bubble_size)
        self._bubble_size_spin.setSuffix(" px")
        self._bubble_size_spin.setFixedWidth(84)
        self._bubble_size_spin.setToolTip("Bubble size")
        self._bubble_size_spin.setAccessibleName("Bubble size")
        self._bubble_size_spin.valueChanged.connect(self.bubble_size_changed.emit)
        shape_layout.addWidget(self._bubble_size_spin)

        self._fill_cb = QCheckBox("Fill")
        self._fill_cb.setChecked(initial_fill)
        self._fill_cb.setAccessibleName("Fill shape")
        self._fill_cb.toggled.connect(self.fill_changed.emit)
        shape_layout.addWidget(self._fill_cb)

        command_row.addStretch(1)

        command_row.addWidget(self._create_separator())

        # Global commands.
        self._undo_btn = _make_btn("undo", "Undo (Ctrl+Z)")
        self._undo_btn.setObjectName("commandButton")
        self._undo_btn.clicked.connect(self.undo_requested.emit)
        command_row.addWidget(self._undo_btn)

        self._redo_btn = _make_btn("redo", "Redo (Ctrl+Y)")
        self._redo_btn.setObjectName("commandButton")
        self._redo_btn.clicked.connect(self.redo_requested.emit)
        command_row.addWidget(self._redo_btn)

        self._clipboard_btn = _make_btn("copy", "Copy to clipboard (Ctrl+C)")
        self._clipboard_btn.setObjectName("commandButton")
        self._clipboard_btn.setText("Copy")
        self._clipboard_btn.clicked.connect(self.copy_clipboard_requested.emit)
        command_row.addWidget(self._clipboard_btn)

        self._gallery_btn = _make_btn("gallery", "Gallery (Ctrl+G)")
        self._gallery_btn.setObjectName("commandButton")
        self._gallery_btn.setText("Gallery")
        self._gallery_btn.clicked.connect(self.gallery_requested.emit)
        command_row.addWidget(self._gallery_btn)

        self._save_btn = _make_btn("save", "Save file (Ctrl+S)")
        self._save_btn.setObjectName("commandButton")
        self._save_btn.setText("Save")
        self._save_btn.clicked.connect(self.save_file_requested.emit)
        command_row.addWidget(self._save_btn)

        layout.addLayout(command_row)

        self._context_bar = QFrame(self)
        self._context_bar.setObjectName("contextBar")
        context_layout = QHBoxLayout(self._context_bar)
        context_layout.setContentsMargins(12, 4, 8, 4)
        context_layout.setSpacing(8)
        self._context_title = QLabel("Properties")
        self._context_title.setObjectName("contextTitle")
        context_layout.addWidget(self._context_title)
        context_layout.addWidget(self._create_separator())
        self._context_hint = QLabel("Select a tool to see its properties")
        self._context_hint.setObjectName("contextHint")
        context_layout.addWidget(self._context_hint)
        context_layout.addWidget(self._text_context)
        context_layout.addWidget(self._shape_context)
        context_layout.addStretch(1)
        layout.addWidget(self._context_bar)

        self._tool_buttons[ToolType.SELECT].setChecked(True)
        self._button_group.buttonClicked.connect(self._on_tool_clicked)
        self._update_context_controls(ToolType.SELECT)

    def _create_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(28)
        sep.setStyleSheet(f"color: {BORDER_SUBTLE};")
        return sep

    def _update_context_controls(self, tool_type: str):
        is_text = tool_type == ToolType.TEXT
        is_shape = tool_type in (
            ToolType.LINE, ToolType.ARROW, ToolType.RECT,
            ToolType.ELLIPSE, ToolType.BUBBLE,
        )
        self._text_context.setVisible(is_text)
        self._shape_context.setVisible(is_shape)
        self._context_hint.setVisible(not is_text and not is_shape)
        self._context_title.setText(
            "Text properties" if is_text else
            "Shape properties" if is_shape else
            "Properties"
        )

        if not is_shape:
            return

        is_bubble = tool_type == ToolType.BUBBLE
        supports_fill = tool_type in (ToolType.RECT, ToolType.ELLIPSE)
        self._shape_context_label.setText(
            "Bubble" if is_bubble else "Shape" if supports_fill else "Stroke"
        )
        self._width_spin.setVisible(not is_bubble)
        self._bubble_size_spin.setVisible(is_bubble)
        self._fill_cb.setVisible(supports_fill)

    def resizeEvent(self, event):
        """Reduce secondary chrome at medium/small window widths."""
        self._update_compact_mode()
        super().resizeEvent(event)

    def _update_compact_mode(self):
        scale = self.property("uiScale") or 1.0
        compact = self.width() < 1008 * scale
        self._tool_label.setVisible(not compact)
        self._text_context_label.setVisible(not compact)
        self._shape_context_label.setVisible(not compact)
        style = (
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if compact else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        for button in (self._clipboard_btn, self._gallery_btn, self._save_btn):
            button.setToolButtonStyle(style)
        self.update_scale(scale)

    def apply_ui_scale(self, scale: float, stroke_width: int, text_size: int,
                       bubble_size: int | None = None):
        """Refresh raster assets and defaults after the layout is DPI-scaled."""
        for btn in self.findChildren(QToolButton):
            name = btn.property("iconName")
            if name:
                btn.setIcon(_toolbar_icon(name, round(24 * scale)))
        for btn in (self._color_button, self._text_color_btn, self._text_bg_btn):
            btn._update_icon()
        # Scaling must not trigger edits of the currently selected annotation.
        with QSignalBlocker(self._width_spin), QSignalBlocker(self._text_size_spin), \
                QSignalBlocker(self._bubble_size_spin):
            self._width_spin.setValue(stroke_width)
            self._text_size_spin.setValue(text_size)
            if bubble_size is not None:
                self._bubble_size_spin.setValue(bubble_size)
        self._update_compact_mode()

    def set_command_state(self, can_undo: bool, can_redo: bool):
        """Keep command affordances in sync with the canvas history."""
        self._undo_btn.setEnabled(can_undo)
        self._redo_btn.setEnabled(can_redo)

    def _on_tool_clicked(self, button: QToolButton):
        for tool_type, btn in self._tool_buttons.items():
            if btn is button:
                self._current_tool = tool_type
                self._update_context_controls(tool_type)
                self.tool_changed.emit(tool_type)
                break

    def _apply_styles(self):
        self.update_scale(1.0)

    def update_scale(self, factor: float):
        """Update the sizes of toolbar elements based on a scale factor."""
        btn_size = int(44 * factor)
        icon_size = max(20, int(24 * factor))
        icon_buttons = list(self._tool_buttons.values()) + [
            self._undo_btn, self._redo_btn,
        ]
        for btn in icon_buttons:
            btn.setFixedSize(btn_size, btn_size)
            btn.setIcon(_toolbar_icon(btn.property("iconName"), icon_size))
            btn.setIconSize(QSize(icon_size, icon_size))

        for btn, width in (
            (self._clipboard_btn, 88),
            (self._gallery_btn, 96),
            (self._save_btn, 80),
        ):
            if btn.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon:
                btn.setFixedSize(round(width * factor), btn_size)
            else:
                btn.setFixedSize(btn_size, btn_size)
            btn.setIcon(_toolbar_icon(btn.property("iconName"), icon_size))
            btn.setIconSize(QSize(icon_size, icon_size))

        btn_box = int(36 * factor)
        for color_btn in [self._color_button, self._text_color_btn, self._text_bg_btn]:
            color_btn.setFixedSize(btn_box, btn_box)
            color_btn.setIconSize(QSize(icon_size, icon_size))

        self._width_spin.setFixedWidth(int(84 * factor))
        self._text_size_spin.setFixedWidth(int(84 * factor))
        self._bubble_size_spin.setFixedWidth(int(84 * factor))
        self.setMinimumHeight(int(112 * factor))

        self.setStyleSheet(f"""
            Toolbar {{
                background: {BASE};
                border-bottom: 1px solid {BORDER_SUBTLE};
            }}
            QFrame#contextBar {{
                background: {SURFACE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: {OVERLAY_RADIUS}px;
            }}
            QLabel#groupLabel {{
                color: {TEXT_MUTED};
                font-family: 'Segoe UI Variable', 'Segoe UI';
                font-size: {TYPE_CAPTION_PT}pt;
                font-weight: 600;
                padding: 0 4px;
            }}
            QLabel#contextHint {{
                color: {TEXT_MUTED};
                font-family: 'Segoe UI Variable', 'Segoe UI';
                font-size: {TYPE_CAPTION_PT}pt;
            }}
            QToolButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: {CONTROL_RADIUS}px;
                color: {TEXT_PRIMARY};
                padding: {int(7 * factor)}px;
            }}
            QToolButton#commandButton {{
                font-family: 'Segoe UI Variable', 'Segoe UI';
                font-size: {TYPE_BODY_PT}pt;
                font-weight: 600;
            }}
            QToolButton:hover {{
                background: {HOVER};
                border-color: {BORDER};
            }}
            QToolButton:checked {{
                background: {ACCENT_SUBTLE};
                border-color: {BORDER};
                border-bottom: 2px solid {ACCENT};
            }}
            QToolButton:pressed {{
                background: {PRESSED};
            }}
            ColorButton, TextColorButton {{
                padding: 0px;
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {CONTROL_RADIUS}px;
            }}
            ColorButton:hover, TextColorButton:hover {{
                background: {HOVER};
                border-color: {TEXT_SECONDARY};
            }}
            QLabel#contextTitle {{
                color: {TEXT_SECONDARY};
                font-family: 'Segoe UI Variable', 'Segoe UI';
                font-size: {TYPE_BODY_PT}pt;
                font-weight: 600;
                padding: 0 2px;
            }}
            QCheckBox {{
                color: {TEXT_PRIMARY};
                spacing: 6px;
                font-family: 'Segoe UI Variable', 'Segoe UI';
                font-size: {TYPE_BODY_PT}pt;
            }}
            QCheckBox::indicator {{
                width: {int(16 * factor)}px;
                height: {int(16 * factor)}px;
                border: 1px solid {BORDER};
                background: {SURFACE};
                border-radius: 3px;
            }}
            QCheckBox::indicator:checked {{
                background: {ACCENT};
                border-color: {ACCENT};
            }}
            QSpinBox {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {CONTROL_RADIUS}px;
                color: {TEXT_PRIMARY};
                padding: 4px 8px;
                min-height: {int(30 * factor)}px;
                font-family: 'Segoe UI Variable', 'Segoe UI';
                font-size: {TYPE_BODY_PT}pt;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: {SURFACE_ALT};
                border: none;
                width: {int(22 * factor)}px;
            }}
            QSpinBox::up-button {{
                border-top-right-radius: 4px;
            }}
            QSpinBox::down-button {{
                border-bottom-right-radius: 4px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: {HOVER};
            }}
            QSpinBox::up-arrow, QSpinBox::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
                border: none;
            }}
            QSpinBox:focus {{
                border-color: {ACCENT};
            }}
        """)

    @property
    def current_tool(self) -> str:
        return self._current_tool

    @property
    def current_color(self) -> QColor:
        return self._color_button.color

    @property
    def current_stroke_width(self) -> int:
        return self._width_spin.value()

    def set_tool(self, tool_type: str):
        """Programmatically set the active tool."""
        if tool_type in self._tool_buttons:
            self._tool_buttons[tool_type].setChecked(True)
            self._current_tool = tool_type
            self._update_context_controls(tool_type)
            self.tool_changed.emit(tool_type)

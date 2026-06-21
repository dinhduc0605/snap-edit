"""
Toolbar widget for the SnapEdit editor.
Provides tool selection, color picker, and stroke size controls.
Uses emoji text icons (no external icon library required).
"""
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QFont, QAction
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout,
    QToolButton, QButtonGroup,
    QColorDialog, QSpinBox, QFrame, QCheckBox
)


def _make_btn(text: str, tooltip: str, checkable: bool = False,
              size: int = 24) -> QToolButton:
    """Create a styled QToolButton with a text icon."""
    btn = QToolButton()
    btn.setText(text)
    btn.setToolTip(tooltip)
    btn.setCheckable(checkable)
    btn.setFixedSize(size, size)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 24, 24, 4, 4)
        painter.end()
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(24, 24))

    def _pick_color(self):
        color = QColorDialog.getColor(self._color, self, "Pick Color",
                                      QColorDialog.ColorDialogOption.ShowAlphaChannel)
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
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Draw 'A' in current text color with a lighter, elegant font
        font = QFont("Segoe UI", 14)
        painter.setFont(font)
        painter.setPen(self._color)
        painter.drawText(0, -2, size, size, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, "A")

        # Draw thin underline color bar
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawRect(4, size - 4, size - 8, 2)

        painter.end()
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(size, size))

    def _pick_color(self):
        color = QColorDialog.getColor(self._color, self, "Text Color")
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
    undo_requested           = pyqtSignal()
    redo_requested           = pyqtSignal()
    save_file_requested      = pyqtSignal()
    copy_clipboard_requested = pyqtSignal()

    def __init__(self, initial_color: QColor = QColor("#FF3B30"),
                 initial_width: int = 3, parent=None):
        super().__init__(parent)
        self._current_tool = ToolType.SELECT
        self._setup_ui(initial_color, initial_width)
        self._apply_styles()

    def _setup_ui(self, initial_color: QColor, initial_width: int):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._tool_buttons: dict[str, QToolButton] = {}

        # ── 1. Select ──────────────────────────────────────────────────
        btn = _make_btn("\uE8B0", "Select (V)", checkable=True)
        self._button_group.addButton(btn)
        self._tool_buttons[ToolType.SELECT] = btn
        layout.addWidget(btn)

        layout.addWidget(self._create_separator())

        # ── 2. Text tool + text-specific settings ──────────────────────
        btn = _make_btn("\uE8D2", "Text (T)", checkable=True)
        self._button_group.addButton(btn)
        self._tool_buttons[ToolType.TEXT] = btn
        layout.addWidget(btn)

        # Text color — "A" icon
        self._text_color_btn = TextColorButton(QColor("#FF0000"))
        self._text_color_btn.color_changed.connect(self.text_color_changed.emit)
        layout.addWidget(self._text_color_btn)

        # Text background color — solid rectangle icon
        self._text_bg_btn = ColorButton(QColor(255, 255, 255, 180))
        self._text_bg_btn.setToolTip("Text Background Color")
        self._text_bg_btn.color_changed.connect(self.text_bg_color_changed.emit)
        layout.addWidget(self._text_bg_btn)

        # Text size
        self._text_size_spin = QSpinBox()
        self._text_size_spin.setRange(6, 72)
        self._text_size_spin.setValue(14)
        self._text_size_spin.setSuffix("pt")
        self._text_size_spin.setFixedWidth(70)
        self._text_size_spin.setToolTip("Text Size")
        self._text_size_spin.valueChanged.connect(self.text_size_changed.emit)
        layout.addWidget(self._text_size_spin)

        layout.addWidget(self._create_separator())

        # ── 3. Shape tools ─────────────────────────────────────────────
        for tool_type, emoji, tooltip in [
            (ToolType.LINE,    "—",      "Line (L)"),
            (ToolType.ARROW,   "\uE72A", "Arrow (A)"),
            (ToolType.RECT,    "\uE71A", "Rectangle (R)"),
            (ToolType.ELLIPSE, "\uEA3A", "Ellipse (E)"),
        ]:
            btn = _make_btn(emoji, tooltip, checkable=True)
            self._button_group.addButton(btn)
            self._tool_buttons[tool_type] = btn
            layout.addWidget(btn)

        layout.addWidget(self._create_separator())

        # ── 4. Stroke color, size, Fill ────────────────────────────────
        self._color_button = ColorButton(initial_color)
        self._color_button.setToolTip("Stroke Color")
        self._color_button.color_changed.connect(self.color_changed.emit)
        layout.addWidget(self._color_button)

        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 20)
        self._width_spin.setValue(initial_width)
        self._width_spin.setSuffix("px")
        self._width_spin.setFixedWidth(70)
        self._width_spin.valueChanged.connect(self.stroke_width_changed.emit)
        layout.addWidget(self._width_spin)

        self._fill_cb = QCheckBox("Fill")
        self._fill_cb.toggled.connect(self.fill_changed.emit)
        layout.addWidget(self._fill_cb)

        layout.addWidget(self._create_separator())

        # ── 5. Bubble ──────────────────────────────────────────────────
        btn = _make_btn("①", "Number Bubble (B)", checkable=True)
        self._button_group.addButton(btn)
        self._tool_buttons[ToolType.BUBBLE] = btn
        layout.addWidget(btn)

        # Right spacer
        layout.addStretch()

        layout.addWidget(self._create_separator())

        # ── 6. Undo / Redo / Copy / Save ──────────────────────────────
        self._undo_btn = _make_btn("\uE7A7", "Undo (Ctrl+Z)")
        self._undo_btn.clicked.connect(self.undo_requested.emit)
        layout.addWidget(self._undo_btn)

        self._redo_btn = _make_btn("\uE7A6", "Redo (Ctrl+Y)")
        self._redo_btn.clicked.connect(self.redo_requested.emit)
        layout.addWidget(self._redo_btn)

        self._clipboard_btn = _make_btn("\uE8C8", "Copy to Clipboard (Ctrl+C)")
        self._clipboard_btn.clicked.connect(self.copy_clipboard_requested.emit)
        layout.addWidget(self._clipboard_btn)

        self._save_btn = _make_btn("\uE74E", "Save File (Ctrl+S)")
        self._save_btn.clicked.connect(self.save_file_requested.emit)
        layout.addWidget(self._save_btn)

        # Default selection
        self._tool_buttons[ToolType.SELECT].setChecked(True)
        self._button_group.buttonClicked.connect(self._on_tool_clicked)

    def _create_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(30)
        sep.setStyleSheet("color: #3A3A50;")
        return sep

    def _on_tool_clicked(self, button: QToolButton):
        for tool_type, btn in self._tool_buttons.items():
            if btn is button:
                self._current_tool = tool_type
                self.tool_changed.emit(tool_type)
                break

    def _apply_styles(self):
        self.update_scale(1.0)

    def update_scale(self, factor: float):
        """Update the sizes of toolbar elements based on a scale factor."""
        btn_size  = int(48 * factor)
        font_size = int(20 * factor)

        fluent_font = QFont("Segoe Fluent Icons", int(12 * factor))

        for btn in self._tool_buttons.values():
            btn.setFixedSize(btn_size, btn_size)
            btn.setFont(fluent_font)

        for btn in [self._undo_btn, self._redo_btn,
                    self._clipboard_btn, self._save_btn]:
            btn.setFixedSize(btn_size, btn_size)
            btn.setFont(fluent_font)

        icon_size = int(24 * factor)
        btn_box   = int(32 * factor)
        for color_btn in [self._color_button, self._text_color_btn, self._text_bg_btn]:
            color_btn.setFixedSize(btn_box, btn_box)
            color_btn.setIconSize(QSize(icon_size, icon_size))

        self._width_spin.setFixedWidth(int(70 * factor))
        self._text_size_spin.setFixedWidth(int(70 * factor))

        self.setStyleSheet(f"""
            Toolbar {{
                background: #202020;
                border-bottom: none;
            }}
            QToolButton {{
                background: transparent;
                border: none;
                border-radius: 4px;
                color: #FFFFFF;
                padding: {int(8 * factor)}px;
            }}
            QToolButton:hover {{
                background: #333333;
                border-radius: 0px;
            }}
            QToolButton:checked {{
                background: #333333;
                border-radius: 0px;
            }}
            QToolButton:pressed {{
                background: #2A2A2A;
            }}
            ColorButton, TextColorButton {{
                padding: 0px;
                border-radius: 4px;
            }}
            QCheckBox {{
                color: #FFFFFF;
                font-size: {font_size}px;
            }}
            QCheckBox::indicator {{
                width: {int(24 * factor)}px;
                height: {int(24 * factor)}px;
                border: 1px solid #3A3A50;
                background: #363650;
                border-radius: 4px;
            }}
            QCheckBox::indicator:checked {{
                background: #60CDFF;
                border: 1px solid #60CDFF;
            }}
            QSpinBox {{
                background: #363650;
                border: 1px solid #3A3A50;
                border-radius: 4px;
                color: #E0E0F0;
                padding: 4px;
                font-size: {font_size}px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: #2A2A3C;
                border: none;
                width: {int(16 * factor)}px;
            }}
            QSpinBox::up-button {{
                border-top-right-radius: 4px;
            }}
            QSpinBox::down-button {{
                border-bottom-right-radius: 4px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: #7C5CFC;
            }}
            QSpinBox:focus {{
                border-color: #7C5CFC;
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
            self.tool_changed.emit(tool_type)

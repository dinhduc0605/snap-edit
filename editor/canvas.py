"""
Canvas (QGraphicsScene) for the SnapEdit editor.
Manages the background screenshot and all annotation items.
"""
import weakref
from PyQt6 import sip
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QEvent
from PyQt6.QtGui import (
    QPixmap, QColor, QPainter, QTransform, QUndoStack, QUndoCommand
)
from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsPixmapItem, QGraphicsView,
    QGraphicsItem,
    QWidget, QHBoxLayout, QLabel, QToolButton,
    QDialog, QApplication, QVBoxLayout, QFrame
)
from ui_widgets import BasicColorDialog, FluentSpinBox
from ui_scaling import WindowScaler
from editor.toolbar import ToolType
from theme import (
    ACCENT, BASE, BORDER, BORDER_SUBTLE, CONTENT, CONTROL_RADIUS,
    HOVER, OVERLAY_RADIUS, SURFACE, SURFACE_ALT, TEXT_PRIMARY,
    TEXT_SECONDARY, TYPE_BODY_PT, TYPE_SUBTITLE_PT,
)


_POPUP_STYLESHEET = f"""
    QDialog {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: {OVERLAY_RADIUS}px;
        color: {TEXT_PRIMARY};
        font-family: 'Segoe UI Variable', 'Segoe UI';
        font-size: {TYPE_BODY_PT}pt;
    }}
    QLabel {{
        color: {TEXT_SECONDARY};
        font-size: {TYPE_BODY_PT}pt;
    }}
    QLabel#popupTitle {{
        color: {TEXT_PRIMARY};
        font-size: {TYPE_SUBTITLE_PT}pt;
        font-weight: 600;
    }}
    QSpinBox {{
        background: {SURFACE_ALT};
        border: 1px solid {BORDER};
        border-radius: {CONTROL_RADIUS}px;
        color: {TEXT_PRIMARY};
        padding: 6px 10px;
        font-size: {TYPE_BODY_PT}pt;
    }}
    QSpinBox:focus {{ border-color: {ACCENT}; }}
    QSpinBox::up-button, QSpinBox::down-button {{
        background: {SURFACE};
        border: none;
        width: 22px;
    }}
    QSpinBox::up-button {{ border-top-right-radius: {CONTROL_RADIUS}px; }}
    QSpinBox::down-button {{ border-bottom-right-radius: {CONTROL_RADIUS}px; }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
        background: {HOVER};
    }}
    QSpinBox::up-arrow, QSpinBox::down-arrow {{
        image: none;
        width: 0px;
        height: 0px;
        border: none;
    }}
    QToolButton {{
        background: {SURFACE_ALT};
        border: 1px solid {BORDER};
        border-radius: {CONTROL_RADIUS}px;
        color: {TEXT_PRIMARY};
        padding: 6px 10px;
        font-size: {TYPE_BODY_PT}pt;
    }}
    QToolButton:hover {{ background: {HOVER}; }}
    QCheckBox {{
        color: {TEXT_PRIMARY};
        spacing: 8px;
        font-size: {TYPE_BODY_PT}pt;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {BORDER};
        background: {SURFACE_ALT};
        border-radius: 3px;
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}
"""


class AddItemCommand(QUndoCommand):
    """Undo command for adding an annotation item."""

    def __init__(self, scene: 'AnnotationCanvas', item: QGraphicsItem, description: str = "Add item"):
        super().__init__(description)
        self._scene = scene
        self._item = item

    def redo(self):
        self._scene.addItem(self._item)

    def undo(self):
        self._scene.removeItem(self._item)


class AddBubbleCommand(AddItemCommand):
    """Undoable bubble addition that keeps numbering in sync."""

    def __init__(self, scene: 'AnnotationCanvas', item: QGraphicsItem, number: int):
        super().__init__(scene, item, f"Add bubble #{number}")
        self._number = number

    def redo(self):
        super().redo()
        self._scene._bubble_counter = self._number
        self._scene.bubble_count_changed.emit(self._number)

    def undo(self):
        super().undo()
        self._scene._bubble_counter = self._number - 1
        self._scene.bubble_count_changed.emit(self._scene._bubble_counter)


class RemoveItemCommand(QUndoCommand):
    """Undo command for removing an annotation item."""

    def __init__(self, scene: 'AnnotationCanvas', item: QGraphicsItem, description: str = "Remove item"):
        super().__init__(description)
        self._scene = scene
        self._item = item

    def redo(self):
        self._scene.removeItem(self._item)

    def undo(self):
        self._scene.addItem(self._item)



class _ItemSettingsPopup(QDialog):
    """Transient property editor, destroyed (not just hidden) on completion."""

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item
        self._disposed = False
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        self.item = None
        if hasattr(self, "_ui_scaler"):
            self._ui_scaler.dispose()

    def done(self, result):
        self.dispose()
        super().done(result)


class TextSettingsPopup(_ItemSettingsPopup):
    """A custom frameless dialog for text settings that doesn't auto-close when dialogs open."""

    def __init__(self, item, parent=None):
        super().__init__(item, parent)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(_POPUP_STYLESHEET)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # --- Helper: build a widget action row ---
        def _make_row(label_text, widget):
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(112)
            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight)
            return container

        # --- Section title ---
        title_container = QWidget()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(8, 4, 8, 2)
        title_lbl = QLabel("Text")
        title_lbl.setObjectName("popupTitle")
        title_layout.addWidget(title_lbl)
        layout.addWidget(title_container)

        # Draw a separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet(
            f"background-color: {BORDER_SUBTLE}; max-height: 1px; border: none;"
        )
        layout.addWidget(sep)

        # Helper: format QColor to CSS rgba
        def _rgba_css(color):
            return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha() / 255.0})"

        # --- Text color row ---
        tc_btn = QToolButton()
        tc_btn.setFixedSize(96, 32)
        tc_btn.setStyleSheet(f"background: {_rgba_css(item.text_color)};")
        tc_btn.setToolTip("Pick text color")
        tc_btn.setAccessibleName("Text color")
        def _pick_text_color():
            color = BasicColorDialog.get_color(item.text_color, self, "Text color")
            if color.isValid():
                item.set_text_color(color)
                tc_btn.setStyleSheet(f"background: {_rgba_css(color)};")
        tc_btn.clicked.connect(_pick_text_color)
        layout.addWidget(_make_row("Text color", tc_btn))

        # --- Background color row ---
        bg_btn = QToolButton()
        bg_btn.setFixedSize(96, 32)
        bg_btn.setStyleSheet(f"background: {_rgba_css(item.bg_color)};")
        bg_btn.setToolTip("Pick background color")
        bg_btn.setAccessibleName("Text background color")
        def _pick_bg_color():
            color = BasicColorDialog.get_color(
                item.bg_color, self, "Background color"
            )
            if color.isValid():
                item.set_bg_color(color)
                bg_btn.setStyleSheet(f"background: {_rgba_css(color)};")
        bg_btn.clicked.connect(_pick_bg_color)
        layout.addWidget(_make_row("Background", bg_btn))

        # --- Text size row ---
        size_spin = FluentSpinBox()
        size_spin.setRange(6, 288)
        size_spin.setValue(item.font_size)
        size_spin.setSuffix(" px")
        size_spin.setFixedSize(96, 32)
        size_spin.setAccessibleName("Text size")
        def _apply_size(val):
            item.set_font_size(val)
        size_spin.valueChanged.connect(_apply_size)
        layout.addWidget(_make_row("Text size", size_spin))
        self._ui_scaler = WindowScaler(self)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                active_win = QApplication.activeWindow()
                if active_win and (active_win == self or active_win.parent() == self or isinstance(active_win, BasicColorDialog)):
                    return
                self.close()
        super().changeEvent(event)


class ShapeSettingsPopup(_ItemSettingsPopup):
    """A custom frameless dialog for shape settings that doesn't auto-close when dialogs open."""
    
    def __init__(self, item, parent=None):
        super().__init__(item, parent)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(_POPUP_STYLESHEET)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        def _make_row(label_text, widget):
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(112)
            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight)
            return container

        # --- Section title ---
        title_container = QWidget()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(8, 4, 8, 2)
        title_lbl = QLabel("Shape")
        title_lbl.setObjectName("popupTitle")
        title_layout.addWidget(title_lbl)
        layout.addWidget(title_container)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet(
            f"background-color: {BORDER_SUBTLE}; max-height: 1px; border: none;"
        )
        layout.addWidget(sep)

        def _rgba_css(color):
            return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha() / 255.0})"

        # --- Stroke color row ---
        sc_btn = QToolButton()
        sc_btn.setFixedSize(96, 32)
        sc_btn.setStyleSheet(f"background: {_rgba_css(item.pen_color)};")
        sc_btn.setToolTip("Pick stroke color")
        sc_btn.setAccessibleName("Stroke color")
        def _pick_stroke_color():
            color = BasicColorDialog.get_color(item.pen_color, self, "Stroke color")
            if color.isValid():
                item.set_pen_color(color)
                sc_btn.setStyleSheet(f"background: {_rgba_css(color)};")
        sc_btn.clicked.connect(_pick_stroke_color)
        layout.addWidget(_make_row("Stroke color", sc_btn))

        # --- Stroke size row ---
        size_spin = FluentSpinBox()
        size_spin.setRange(1, 80)
        size_spin.setValue(item.pen_width)
        size_spin.setSuffix(" px")
        size_spin.setFixedSize(96, 32)
        size_spin.setAccessibleName("Stroke width")
        def _apply_size(val):
            item.set_pen_width(val)
        size_spin.valueChanged.connect(_apply_size)
        layout.addWidget(_make_row("Stroke width", size_spin))

        # --- Fill rows (if applicable) ---
        if hasattr(item, 'fill_enabled'):
            from PyQt6.QtWidgets import QCheckBox
            fill_cb = QCheckBox()
            # A label-less checkbox otherwise keeps an invisible text area to
            # its right, which made its indicator look offset from the other
            # right-aligned controls in this popup.
            fill_cb.setFixedSize(32, 32)
            fill_cb.setStyleSheet("QCheckBox { margin: 0; padding: 0; }")
            fill_cb.setChecked(item.fill_enabled)
            fill_cb.setAccessibleName("Enable fill")
            
            def _toggle_fill(checked):
                item.set_fill_enabled(checked)
            fill_cb.toggled.connect(_toggle_fill)
            
            layout.addWidget(_make_row("Enable fill", fill_cb))

        self._ui_scaler = WindowScaler(self)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                active_win = QApplication.activeWindow()
                if active_win and (active_win == self or active_win.parent() == self or isinstance(active_win, BasicColorDialog)):
                    return
                self.close()
        super().changeEvent(event)


class BubbleSettingsPopup(_ItemSettingsPopup):
    """Compact property editor for a numbered bubble annotation."""

    def __init__(self, item, parent=None):
        super().__init__(item, parent)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(_POPUP_STYLESHEET)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        def _make_row(label_text, widget):
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(8)
            label = QLabel(label_text)
            label.setFixedWidth(112)
            row.addWidget(label)
            row.addStretch(1)
            row.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight)
            return container

        title = QLabel("Bubble")
        title.setObjectName("popupTitle")
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(8, 4, 8, 2)
        title_layout.addWidget(title)
        layout.addLayout(title_layout)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet(
            f"background-color: {BORDER_SUBTLE}; max-height: 1px; border: none;"
        )
        layout.addWidget(separator)

        def _rgba_css(color):
            return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha() / 255.0})"

        color_button = QToolButton()
        color_button.setFixedSize(96, 32)
        color_button.setStyleSheet(f"background: {_rgba_css(item.bubble_color)};")
        color_button.setToolTip("Pick bubble color")
        color_button.setAccessibleName("Bubble color")

        def _pick_color():
            color = BasicColorDialog.get_color(item.bubble_color, self, "Bubble color")
            if color.isValid():
                item.set_bubble_color(color)
                color_button.setStyleSheet(f"background: {_rgba_css(color)};")

        color_button.clicked.connect(_pick_color)
        layout.addWidget(_make_row("Color", color_button))

        size_spin = FluentSpinBox()
        size_spin.setRange(16, 128)
        size_spin.setValue(round(item.bubble_size))
        size_spin.setSuffix(" px")
        size_spin.setFixedSize(96, 32)
        size_spin.setAccessibleName("Bubble size")
        size_spin.valueChanged.connect(item.set_bubble_size)
        layout.addWidget(_make_row("Size", size_spin))

        self._ui_scaler = WindowScaler(self)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                active_win = QApplication.activeWindow()
                if active_win and (
                    active_win == self
                    or active_win.parent() == self
                    or isinstance(active_win, BasicColorDialog)
                ):
                    return
                self.close()
        super().changeEvent(event)


class AnnotationCanvas(QGraphicsScene):
    """
    Custom QGraphicsScene that manages screenshot background
    and annotation items (shapes, text, bubbles).
    """

    item_added = pyqtSignal()
    bubble_count_changed = pyqtSignal(int)
    ocr_selection_changed = pyqtSignal(str)

    def __init__(self, pixmap: QPixmap = None, parent=None):
        super().__init__(parent)
        self._background_item = None
        self._ocr_overlay = None
        self._disposed = False
        self._settings_popup = None
        self._current_tool = ToolType.SELECT
        self._pen_color = QColor("#FF3B30")
        self._pen_width = 3
        self._bubble_counter = 0
        self._drawing = False
        self._draw_start = QPointF()
        self._current_draw_item = None
        self._undo_stack = QUndoStack(self)
        self._fill_enabled = False
        self._text_color = QColor("#FF0000")
        self._text_bg_color = QColor(255, 255, 255, 180)
        self._text_size = 14
        self._bubble_size = 32.0
        self._annotation_scale = 1.0

        if pixmap:
            self.set_background(pixmap)

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        popup = self._settings_popup
        self._settings_popup = None
        if popup is not None and not sip.isdeleted(popup):
            popup.close()
        self._drawing = False
        self._current_draw_item = None
        self._undo_stack.clear()
        self.clear_ocr_overlay()
        self.clear()
        self._background_item = None

    def _show_settings_popup(self, popup_type, item, event):
        old_popup = self._settings_popup
        if old_popup is not None and not sip.isdeleted(old_popup):
            old_popup.close()
        popup = popup_type(item, event.widget())
        self._settings_popup = popup
        scene_ref, popup_ref = weakref.ref(self), weakref.ref(popup)

        def forget_popup():
            scene = scene_ref()
            if scene is not None and scene._settings_popup is popup_ref():
                scene._settings_popup = None

        popup.destroyed.connect(forget_popup)
        popup.move(event.screenPos())
        popup.show()
        popup.raise_()
        popup.activateWindow()

    def set_annotation_scale(self, scale: float, pen_width: int, text_size: int,
                            bubble_size: int | None = None):
        """Scale defaults only; never mutate existing/selected image content."""
        self._annotation_scale = scale
        self._pen_width = pen_width
        self._text_size = text_size
        if bubble_size is not None:
            self._bubble_size = max(16.0, min(128.0, bubble_size / scale))

    def set_background(self, pixmap: QPixmap):
        """Set the screenshot as the scene background."""
        self.clear_ocr_overlay()
        if self._background_item:
            self.removeItem(self._background_item)
        self._background_item = QGraphicsPixmapItem(pixmap)
        self._background_item.setZValue(-1000)
        self._background_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._background_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        
        self.addItem(self._background_item)
        self.setSceneRect(self._background_item.boundingRect())

    def set_tool(self, tool: str):
        """Set the current drawing tool."""
        self._current_tool = tool
        if tool != ToolType.OCR:
            self.clear_ocr_overlay()
        # Deselect all when changing tool
        for item in self.selectedItems():
            item.setSelected(False)
        # Notify any attached view
        for view in self.views():
            if hasattr(view, 'set_tool'):
                view.set_tool(tool)

    def show_ocr_layout(self, layout):
        """Place an interactive, non-exported highlight layer over OCR words."""
        from editor.ocr_overlay import OcrTextOverlay

        self.clear_ocr_overlay()
        overlay = OcrTextOverlay(layout, self.sceneRect())
        overlay.selection_changed.connect(self.ocr_selection_changed)
        self._ocr_overlay = overlay
        self.addItem(overlay)

    def clear_ocr_overlay(self):
        """Discard transient OCR UI without touching annotations or undo state."""
        overlay = self._ocr_overlay
        self._ocr_overlay = None
        if overlay is not None and not sip.isdeleted(overlay):
            self.removeItem(overlay)
            overlay.deleteLater()
        self.ocr_selection_changed.emit("")

    def has_ocr_overlay(self) -> bool:
        return self._ocr_overlay is not None and not sip.isdeleted(self._ocr_overlay)

    def selected_ocr_text(self) -> str:
        if not self.has_ocr_overlay():
            return ""
        return self._ocr_overlay.selected_text()

    def has_ocr_selection(self) -> bool:
        return self.has_ocr_overlay() and self._ocr_overlay.has_selection()

    def ocr_word_count(self) -> int:
        if not self.has_ocr_overlay():
            return 0
        return self._ocr_overlay.word_count

    def set_pen_color(self, color: QColor):
        """Set the pen color for new items and selected items."""
        self._pen_color = color
        # Update selected items
        for item in self.selectedItems():
            if hasattr(item, 'set_pen_color'):
                item.set_pen_color(color)
            if hasattr(item, 'set_text_color'):
                item.set_text_color(color)
            if hasattr(item, 'set_bubble_color'):
                item.set_bubble_color(color)

    def set_pen_width(self, width: int):
        """Set the pen width for new items and selected items."""
        self._pen_width = width
        for item in self.selectedItems():
            if hasattr(item, 'set_pen_width'):
                item.set_pen_width(width)
            if hasattr(item, 'set_font_size'):
                item.set_font_size(width + 10)

    def set_fill_enabled(self, enabled: bool):
        self._fill_enabled = enabled
        for item in self.selectedItems():
            if hasattr(item, 'set_fill_enabled'):
                item.set_fill_enabled(enabled)

    def set_text_color(self, color: QColor):
        """Set the default text color for new text items."""
        self._text_color = color
        for item in self.selectedItems():
            if hasattr(item, 'set_text_color'):
                item.set_text_color(color)

    def set_text_bg_color(self, color: QColor):
        """Set the default text background color for new text items."""
        self._text_bg_color = color
        for item in self.selectedItems():
            if hasattr(item, 'set_bg_color'):
                item.set_bg_color(color)

    def set_text_size(self, size: int):
        """Set the default font size for new text items."""
        self._text_size = size
        for item in self.selectedItems():
            if hasattr(item, 'set_font_size'):
                item.set_font_size(size)

    def set_bubble_size(self, size: float):
        """Set the logical default and update selected bubbles."""
        self._bubble_size = max(16.0, min(128.0, float(size)))
        for item in self.selectedItems():
            if hasattr(item, 'set_bubble_size'):
                item.set_bubble_size(self._bubble_size)

    @property
    def undo_stack(self) -> QUndoStack:
        return self._undo_stack

    def undo(self):
        if self._undo_stack.canUndo():
            self._undo_stack.undo()

    def redo(self):
        if self._undo_stack.canRedo():
            self._undo_stack.redo()

    def delete_selected(self):
        """Delete all selected annotation items."""
        for item in self.selectedItems():
            if item is not self._background_item:
                cmd = RemoveItemCommand(self, item, "Delete item")
                self._undo_stack.push(cmd)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        pos = event.scenePos()

        if self._current_tool in (ToolType.SELECT, ToolType.GRAB):
            super().mousePressEvent(event)
            return

        if self._current_tool == ToolType.OCR:
            super().mousePressEvent(event)
            return

        if self._current_tool == ToolType.BUBBLE:
            self._add_bubble(pos)
            return

        if self._current_tool == ToolType.TEXT:
            from editor.items.text_item import TextItem

            item = self.itemAt(pos, QTransform())
            if isinstance(item, TextItem):
                # Text mode is also the edit affordance for existing text.
                # Enable interaction before forwarding the same mouse press so
                # QGraphicsTextItem places the cursor at the click location.
                item.setSelected(True)
                item.begin_editing()
                super().mousePressEvent(event)
                return
            self._add_text(pos)
            return

        # Start drawing shape/line/arrow
        self._drawing = True
        self._draw_start = pos
        self._current_draw_item = None

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._current_tool == ToolType.OCR:
            super().mouseMoveEvent(event)
            return
        if self._drawing and self._current_tool in (ToolType.ARROW, ToolType.LINE,
                                                      ToolType.RECT, ToolType.ELLIPSE):
            pos = event.scenePos()
            if self._current_draw_item is None:
                self._current_draw_item = self._create_shape_item(self._draw_start, pos)
                if self._current_draw_item:
                    self.addItem(self._current_draw_item)
            else:
                self._update_shape_item(self._current_draw_item, self._draw_start, pos)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._current_tool == ToolType.OCR:
            super().mouseReleaseEvent(event)
            return
        if self._drawing and self._current_draw_item is not None:
            self._drawing = False
            # Remove and re-add via undo command
            self.removeItem(self._current_draw_item)
            cmd = AddItemCommand(self, self._current_draw_item, f"Add {self._current_tool}")
            self._undo_stack.push(cmd)
            self._current_draw_item = None
            self.item_added.emit()
        elif self._drawing:
            self._drawing = False
        else:
            super().mouseReleaseEvent(event)

    def _create_shape_item(self, start: QPointF, end: QPointF):
        """Create a new shape item based on current tool."""
        # Lazy import to avoid circular imports
        from editor.items.rect_item import RectItem
        from editor.items.ellipse_item import EllipseItem
        from editor.items.line_item import LineItem
        from editor.items.arrow_item import ArrowItem

        if self._current_tool == ToolType.RECT:
            item = RectItem(QRectF(start, end).normalized())
            item.set_pen_color(self._pen_color)
            item.set_pen_width(self._pen_width)
            if hasattr(item, 'set_fill_enabled'):
                item.set_fill_enabled(self._fill_enabled)
            return item
        elif self._current_tool == ToolType.ELLIPSE:
            item = EllipseItem(QRectF(start, end).normalized())
            item.set_pen_color(self._pen_color)
            item.set_pen_width(self._pen_width)
            if hasattr(item, 'set_fill_enabled'):
                item.set_fill_enabled(self._fill_enabled)
            return item
        elif self._current_tool == ToolType.LINE:
            item = LineItem(start, end)
            item.set_pen_color(self._pen_color)
            item.set_pen_width(self._pen_width)
            return item
        elif self._current_tool == ToolType.ARROW:
            item = ArrowItem(start, end)
            item.set_pen_color(self._pen_color)
            item.set_pen_width(self._pen_width)
            return item
        return None

    def _update_shape_item(self, item, start: QPointF, end: QPointF):
        """Update shape geometry during drag."""
        from editor.items.rect_item import RectItem
        from editor.items.ellipse_item import EllipseItem
        from editor.items.line_item import LineItem
        from editor.items.arrow_item import ArrowItem

        if isinstance(item, (RectItem, EllipseItem)):
            item.setRect(QRectF(start, end).normalized())
        elif isinstance(item, (LineItem, ArrowItem)):
            item.set_endpoints(start, end)

    def _add_bubble(self, pos: QPointF):
        """Add a numbered bubble at the given position."""
        from editor.items.bubble_item import BubbleItem
        number = self._bubble_counter + 1
        item = BubbleItem(number, self._pen_color, bubble_size=self._bubble_size)
        item.setScale(self._annotation_scale)
        radius = (self._bubble_size / 2.0) * self._annotation_scale
        item.setPos(pos.x() - radius, pos.y() - radius)
        cmd = AddBubbleCommand(self, item, number)
        self._undo_stack.push(cmd)
        self.item_added.emit()

    def _add_text(self, pos: QPointF):
        """Add a text item at the given position."""
        from editor.items.text_item import TextItem
        item = TextItem(self._text_color, self._text_size, self._text_bg_color)
        item.setPos(pos)
        cmd = AddItemCommand(self, item, "Add text")
        self._undo_stack.push(cmd)
        self.item_added.emit()

    def export_to_pixmap(self) -> QPixmap:
        """Render the entire scene (background + annotations) to a QPixmap."""
        # Deselect all items to hide handles
        for item in self.selectedItems():
            item.setSelected(False)

        rect = self.sceneRect()
        pixmap = QPixmap(int(rect.width()), int(rect.height()))
        pixmap.fill(Qt.GlobalColor.white)
        overlay = self._ocr_overlay
        overlay_visible = self.has_ocr_overlay() and overlay.isVisible()
        if overlay_visible:
            overlay.setVisible(False)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self.render(painter, QRectF(pixmap.rect()), rect)
        finally:
            painter.end()
            if overlay_visible and not sip.isdeleted(overlay):
                overlay.setVisible(True)
        return pixmap

    def get_annotation_items(self) -> list:
        """Get all annotation items (excluding background)."""
        return [item for item in self.items()
                if item is not self._background_item and item is not self._ocr_overlay]

    def contextMenuEvent(self, event):
        """Show settings context menu on right-click over an item in Select mode."""
        if self._current_tool != ToolType.SELECT:
            super().contextMenuEvent(event)
            return

        from editor.items.text_item import TextItem
        from editor.items.rect_item import RectItem
        from editor.items.ellipse_item import EllipseItem
        from editor.items.line_item import LineItem
        from editor.items.arrow_item import ArrowItem
        from editor.items.bubble_item import BubbleItem

        pos = event.scenePos()
        item = self.itemAt(pos, __import__('PyQt6.QtGui', fromlist=['QTransform']).QTransform())

        if isinstance(item, TextItem):
            item.setSelected(True)
            self._show_settings_popup(TextSettingsPopup, item, event)
            return
        elif isinstance(item, BubbleItem):
            item.setSelected(True)
            self._show_settings_popup(BubbleSettingsPopup, item, event)
            return
        elif isinstance(item, (RectItem, EllipseItem, LineItem, ArrowItem)):
            item.setSelected(True)
            self._show_settings_popup(ShapeSettingsPopup, item, event)
            return

        super().contextMenuEvent(event)



class CanvasView(QGraphicsView):
    zoom_changed = pyqtSignal(float)

    """
    Custom QGraphicsView for the annotation canvas.
    Supports:
      - Zoom with Ctrl+Scroll wheel
      - Zoom in/out/reset via methods
      - Grab/Pan mode (drag to pan the canvas)
    """

    def __init__(self, scene: AnnotationCanvas, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._zoom = 1.0
        self._grab_mode = False
        self._prev_drag_mode = QGraphicsView.DragMode.NoDrag
        self._pan_drag_active = False
        self.setStyleSheet("""
            QGraphicsView {
                background: %s;
                border: none;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: %s;
                border: none;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: %s;
                border-radius: 4px;
                min-width: 28px;
                min-height: 28px;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background: %s;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                width: 0px;
                height: 0px;
            }
        """ % (CONTENT, BASE, BORDER, HOVER))

    def set_tool(self, tool: str):
        """Switch between grab/pan mode and normal mode."""
        if tool == ToolType.GRAB:
            self._grab_mode = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        else:
            self._grab_mode = False
            self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def zoom_in(self):
        """Zoom in by 20%."""
        self._apply_zoom(1.2)

    def zoom_out(self):
        """Zoom out by 20%."""
        self._apply_zoom(1 / 1.2)

    def zoom_reset(self):
        """Fit image to view."""
        self.fit_in_view_nice()

    def _apply_zoom(self, factor: float):
        new_zoom = self._zoom * factor
        if 0.05 <= new_zoom <= 20.0:
            self._zoom = new_zoom
            self.scale(factor, factor)
            self.zoom_changed.emit(self._zoom)

    def wheelEvent(self, event):
        """Zoom in/out with Ctrl+scroll."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self._apply_zoom(1.15 if delta > 0 else 1 / 1.15)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag
        ):
            self._pan_drag_active = True
            # Fast resampling while the image is moving avoids expensive
            # smooth scaling for every mouse-move repaint. Full-quality
            # filtering is restored as soon as the drag finishes.
            self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._pan_drag_active:
            self._finish_pan_drag()

    def _finish_pan_drag(self):
        if not self._pan_drag_active:
            return
        self._pan_drag_active = False
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.viewport().update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Control and not event.isAutoRepeat():
            self._prev_drag_mode = self.dragMode()
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Control and not event.isAutoRepeat():
            self.setDragMode(self._prev_drag_mode)
            if not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
                self._finish_pan_drag()
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        """Restore normal rendering if the window loses focus mid-pan."""
        self._finish_pan_drag()
        super().focusOutEvent(event)

    def fit_in_view_nice(self):
        """Fit an oversized scene to the canvas bounds, never upscaling."""
        if self.scene():
            scene_rect = self.scene().sceneRect()
            viewport_rect = self.viewport().rect()
            if (
                scene_rect.width() <= viewport_rect.width()
                and scene_rect.height() <= viewport_rect.height()
            ):
                self.resetTransform()
                self.centerOn(scene_rect.center())
                self._zoom = 1.0
            else:
                scale = min(
                    viewport_rect.width() / scene_rect.width(),
                    viewport_rect.height() / scene_rect.height(),
                )
                self.resetTransform()
                self.scale(scale, scale)
                self.centerOn(scene_rect.center())
                self._zoom = scale
            self.zoom_changed.emit(self._zoom)

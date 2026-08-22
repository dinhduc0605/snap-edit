"""
Canvas (QGraphicsScene) for the SnapEdit editor.
Manages the background screenshot and all annotation items.
"""
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QEvent
from PyQt6.QtGui import (
    QPixmap, QPen, QColor, QPainter, QBrush, QKeySequence,
    QUndoStack, QUndoCommand
)
from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsPixmapItem, QGraphicsView,
    QGraphicsItem, QGraphicsDropShadowEffect, QMenu, QWidgetAction,
    QWidget, QHBoxLayout, QLabel, QSpinBox, QColorDialog, QToolButton,
    QDialog, QApplication, QVBoxLayout, QFrame
)
from editor.toolbar import ToolType


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



class TextSettingsPopup(QDialog):
    """A custom frameless dialog for text settings that doesn't auto-close when dialogs open."""
    
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("""
            QDialog {
                background: #2A2A3C;
                border: 1px solid #3A3A50;
                border-radius: 6px;
            }
            QLabel { color: #8A8AB0; font-size: 22px; padding: 4px 8px 2px 8px; }
            QSpinBox {
                background: #363650; border: 1px solid #3A3A50;
                border-radius: 4px; color: #E0E0F0; padding: 3px; min-width: 120px;
                font-size: 22px;
            }
            QToolButton {
                background: transparent; border: 1px solid #3A3A50;
                border-radius: 4px; color: #E0E0F0; padding: 4px 8px;
                font-size: 22px;
            }
            QToolButton:hover { background: #3A3A50; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # --- Helper: build a widget action row ---
        def _make_row(label_text, widget):
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(150)
            row.addWidget(lbl)
            row.addWidget(widget)
            return container

        # --- Section title ---
        title_container = QWidget()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(8, 6, 8, 4)
        title_lbl = QLabel("Text Settings")
        title_lbl.setStyleSheet("color: #7C5CFC; font-weight: bold; font-size: 24px;")
        title_layout.addWidget(title_lbl)
        layout.addWidget(title_container)

        # Draw a separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: #3A3A50; max-height: 1px; border: none;")
        layout.addWidget(sep)

        # Helper: format QColor to CSS rgba
        def _rgba_css(color):
            return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha() / 255.0})"

        # --- Text color row ---
        tc_btn = QToolButton()
        tc_btn.setFixedSize(120, 40)
        tc_btn.setStyleSheet(f"background: {_rgba_css(item.text_color)};")
        tc_btn.setToolTip("Pick text color")
        def _pick_text_color():
            color = QColorDialog.getColor(item.text_color, self, "Text Color")
            if color.isValid():
                item.set_text_color(color)
                tc_btn.setStyleSheet(f"background: {_rgba_css(color)};")
        tc_btn.clicked.connect(_pick_text_color)
        layout.addWidget(_make_row("Text Color:", tc_btn))

        # --- Background color row ---
        bg_btn = QToolButton()
        bg_btn.setFixedSize(120, 40)
        bg_btn.setStyleSheet(f"background: {_rgba_css(item.bg_color)};")
        bg_btn.setToolTip("Pick background color")
        def _pick_bg_color():
            color = QColorDialog.getColor(
                item.bg_color, self, "Background Color",
                QColorDialog.ColorDialogOption.ShowAlphaChannel
            )
            if color.isValid():
                item.set_bg_color(color)
                bg_btn.setStyleSheet(f"background: {_rgba_css(color)};")
        bg_btn.clicked.connect(_pick_bg_color)
        layout.addWidget(_make_row("BG Color:", bg_btn))

        # --- Text size row ---
        size_spin = QSpinBox()
        size_spin.setRange(6, 72)
        size_spin.setValue(item.font_size)
        size_spin.setSuffix(" pt")
        size_spin.setFixedSize(120, 40)
        def _apply_size(val):
            item.set_font_size(val)
        size_spin.valueChanged.connect(_apply_size)
        layout.addWidget(_make_row("Text Size:", size_spin))

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                active_win = QApplication.activeWindow()
                if active_win and (active_win == self or active_win.parent() == self or isinstance(active_win, QColorDialog)):
                    return
                self.close()
        super().changeEvent(event)


class ShapeSettingsPopup(QDialog):
    """A custom frameless dialog for shape settings that doesn't auto-close when dialogs open."""
    
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("""
            QDialog {
                background: #2A2A3C;
                border: 1px solid #3A3A50;
                border-radius: 6px;
            }
            QLabel { color: #8A8AB0; font-size: 22px; padding: 4px 8px 2px 8px; }
            QSpinBox {
                background: #363650; border: 1px solid #3A3A50;
                border-radius: 4px; color: #E0E0F0; padding: 3px; min-width: 120px;
                font-size: 22px;
            }
            QToolButton {
                background: transparent; border: 1px solid #3A3A50;
                border-radius: 4px; color: #E0E0F0; padding: 4px 8px;
                font-size: 22px;
            }
            QToolButton:hover { background: #3A3A50; }
            QCheckBox {
                color: #8A8AB0;
                font-size: 22px;
                padding: 4px;
            }
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
                border: 1px solid #3A3A50;
                background: #363650;
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background: #60CDFF;
                border: 1px solid #60CDFF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        def _make_row(label_text, widget):
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(150)
            row.addWidget(lbl)
            row.addWidget(widget)
            return container

        # --- Section title ---
        title_container = QWidget()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(8, 6, 8, 4)
        title_lbl = QLabel("Shape Settings")
        title_lbl.setStyleSheet("color: #7C5CFC; font-weight: bold; font-size: 24px;")
        title_layout.addWidget(title_lbl)
        layout.addWidget(title_container)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: #3A3A50; max-height: 1px; border: none;")
        layout.addWidget(sep)

        def _rgba_css(color):
            return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha() / 255.0})"

        # --- Stroke color row ---
        sc_btn = QToolButton()
        sc_btn.setFixedSize(120, 40)
        sc_btn.setStyleSheet(f"background: {_rgba_css(item.pen_color)};")
        sc_btn.setToolTip("Pick stroke color")
        def _pick_stroke_color():
            color = QColorDialog.getColor(item.pen_color, self, "Stroke Color")
            if color.isValid():
                item.set_pen_color(color)
                sc_btn.setStyleSheet(f"background: {_rgba_css(color)};")
        sc_btn.clicked.connect(_pick_stroke_color)
        layout.addWidget(_make_row("Stroke Color:", sc_btn))

        # --- Stroke size row ---
        size_spin = QSpinBox()
        size_spin.setRange(1, 40)
        size_spin.setValue(item.pen_width)
        size_spin.setSuffix(" px")
        size_spin.setFixedSize(120, 40)
        def _apply_size(val):
            item.set_pen_width(val)
        size_spin.valueChanged.connect(_apply_size)
        layout.addWidget(_make_row("Stroke Size:", size_spin))

        # --- Fill rows (if applicable) ---
        if hasattr(item, 'fill_enabled'):
            from PyQt6.QtWidgets import QCheckBox
            fill_cb = QCheckBox("Enable Fill")
            fill_cb.setChecked(item.fill_enabled)
            
            def _toggle_fill(checked):
                item.set_fill_enabled(checked)
            fill_cb.toggled.connect(_toggle_fill)
            
            layout.addWidget(_make_row("Fill:", fill_cb))

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                active_win = QApplication.activeWindow()
                if active_win and (active_win == self or active_win.parent() == self or isinstance(active_win, QColorDialog)):
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

    def __init__(self, pixmap: QPixmap = None, parent=None):
        super().__init__(parent)
        self._background_item = None
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

        if pixmap:
            self.set_background(pixmap)

    def set_background(self, pixmap: QPixmap):
        """Set the screenshot as the scene background."""
        if self._background_item:
            self.removeItem(self._background_item)
        self._background_item = QGraphicsPixmapItem(pixmap)
        self._background_item.setZValue(-1000)
        self._background_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._background_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        
        # Add drop shadow for Snipping Tool aesthetic
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 5)
        self._background_item.setGraphicsEffect(shadow)

        self.addItem(self._background_item)
        self.setSceneRect(self._background_item.boundingRect())

    def set_tool(self, tool: str):
        """Set the current drawing tool."""
        self._current_tool = tool
        # Deselect all when changing tool
        for item in self.selectedItems():
            item.setSelected(False)
        # Notify any attached view
        for view in self.views():
            if hasattr(view, 'set_tool'):
                view.set_tool(tool)

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

        if self._current_tool == ToolType.BUBBLE:
            self._add_bubble(pos)
            return

        if self._current_tool == ToolType.TEXT:
            self._add_text(pos)
            return

        # Start drawing shape/line/arrow
        self._drawing = True
        self._draw_start = pos
        self._current_draw_item = None

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
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
        item = BubbleItem(number, self._pen_color)
        item.setPos(pos.x() - 16, pos.y() - 16)
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
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.render(painter, QRectF(pixmap.rect()), rect)
        painter.end()
        return pixmap

    def get_annotation_items(self) -> list:
        """Get all annotation items (excluding background)."""
        return [item for item in self.items()
                if item is not self._background_item]

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

        pos = event.scenePos()
        item = self.itemAt(pos, __import__('PyQt6.QtGui', fromlist=['QTransform']).QTransform())

        if isinstance(item, TextItem):
            item.setSelected(True)
            self._settings_popup = TextSettingsPopup(item, event.widget())
            self._settings_popup.move(event.screenPos())
            self._settings_popup.show()
            self._settings_popup.raise_()
            self._settings_popup.activateWindow()
            return
        elif isinstance(item, (RectItem, EllipseItem, LineItem, ArrowItem)):
            item.setSelected(True)
            self._shape_settings_popup = ShapeSettingsPopup(item, event.widget())
            self._shape_settings_popup.move(event.screenPos())
            self._shape_settings_popup.show()
            self._shape_settings_popup.raise_()
            self._shape_settings_popup.activateWindow()
            return

        super().contextMenuEvent(event)



class CanvasView(QGraphicsView):
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
        self.setStyleSheet("""
            QGraphicsView {
                background: #202020;
                border: none;
            }
        """)

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

    def wheelEvent(self, event):
        """Zoom in/out with Ctrl+scroll."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            self._apply_zoom(1.15 if delta > 0 else 1 / 1.15)
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Control and not event.isAutoRepeat():
            self._prev_drag_mode = self.dragMode()
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Control and not event.isAutoRepeat():
            self.setDragMode(self._prev_drag_mode)
        super().keyReleaseEvent(event)
    def fit_in_view_nice(self):
        """Fit the scene in view with some padding."""
        if self.scene():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()

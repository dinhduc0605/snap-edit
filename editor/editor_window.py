"""
Main editor window for SnapEdit.
Combines toolbar, canvas, and provides save/export functionality.
"""
import os
from datetime import datetime
from PyQt6 import sip
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (
    QPixmap, QKeySequence, QShortcut, QColor
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFileDialog, QApplication, QStatusBar, QLabel, QDialog, QToolButton,
)
from editor.toolbar import Toolbar, ToolType
from editor.canvas import AnnotationCanvas, CanvasView
from editor.gallery_dialog import GalleryDialog
from settings.config import Config
from ui_scaling import WindowScaler, screen_at_cursor
from theme import (
    BASE, BORDER_SUBTLE, TEXT_MUTED, TEXT_SECONDARY, TYPE_BODY_PT,
)


_FALLBACK_EDITOR_WIDTH = 1200
_FALLBACK_EDITOR_HEIGHT = 800
_MIN_EDITOR_WIDTH = 640
_MIN_EDITOR_HEIGHT = 480
_EDITOR_SCREEN_RATIO = 0.8


class EditorWindow(QMainWindow):
    """
    Screenshot editor window with annotation tools.
    """

    closed = pyqtSignal()
    gallery_image_selected = pyqtSignal(QPixmap)
    settings_requested = pyqtSignal()

    def __init__(self, pixmap: QPixmap, config: Config,
                 recent_screenshots=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._disposed = False
        self._config = config
        self._logical_stroke_width = float(config.stroke_width)
        self._logical_text_size = float(config.text_size)
        self._logical_bubble_size = float(config.bubble_size)
        self._text_color = QColor(config.get("text_color", "#FF0000"))
        self._text_bg_color = QColor(config.get("text_bg_color", "#FFFFFF"))
        self._pixmap = pixmap
        self._recent_screenshots = (
            recent_screenshots if recent_screenshots is not None else []
        )
        self._setup_window()
        self._setup_ui()
        self._setup_shortcuts()
        self._connect_signals()
        self._ui_scaler = WindowScaler(self, resize_window=False)
        self._ui_scaler.scale_changed.connect(self._on_ui_scale_changed)
        self._on_ui_scale_changed(self._ui_scaler.scale)

    def _setup_window(self):
        self.setWindowTitle("SnapEdit — Editor")
        self.setMinimumSize(_MIN_EDITOR_WIDTH, _MIN_EDITOR_HEIGHT)

        # Keep the initial editor size independent of screenshot dimensions.
        w = _FALLBACK_EDITOR_WIDTH
        h = _FALLBACK_EDITOR_HEIGHT
        screen = screen_at_cursor()
        if screen:
            screen_rect = screen.availableGeometry()
            w = round(screen_rect.width() * _EDITOR_SCREEN_RATIO)
            h = round(screen_rect.height() * _EDITOR_SCREEN_RATIO)

            x = (screen_rect.width() - w) // 2 + screen_rect.x()
            y = (screen_rect.height() - h) // 2 + screen_rect.y()
            self.move(x, y)
        self.resize(w, h)

        self.setStyleSheet("""
            QMainWindow {
                background: %s;
            }
            QStatusBar {
                background: %s;
                color: %s;
                border-top: 1px solid %s;
                font-family: 'Segoe UI Variable', 'Segoe UI';
                font-size: %dpt;
                padding: 0 8px;
            }
            QStatusBar QLabel {
                color: %s;
                padding: 0 4px;
            }
            QStatusBar QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                color: %s;
                min-width: 28px;
                min-height: 28px;
                padding: 2px 6px;
            }
            QStatusBar QToolButton:hover {
                background: %s;
                border-color: %s;
            }
        """ % (
            BASE, BASE, TEXT_SECONDARY, BORDER_SUBTLE, TYPE_BODY_PT,
            TEXT_SECONDARY, TEXT_SECONDARY, BORDER_SUBTLE, TEXT_SECONDARY,
        ))

    def resizeEvent(self, event):
        if hasattr(self, "_hint_label"):
            self._hint_label.setVisible(
                event.size().width() >= 900 * (self.property("uiScale") or 1.0)
            )
        super().resizeEvent(event)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        initial_color = QColor(self._config.stroke_color)
        initial_width = self._config.stroke_width
        self._toolbar = Toolbar(
            initial_color,
            initial_width,
            initial_bubble_size=round(self._logical_bubble_size),
            initial_text_size=round(self._logical_text_size),
            initial_text_color=self._text_color,
            initial_text_bg_color=self._text_bg_color,
            initial_fill=bool(self._config.get("fill_shapes", False)),
        )
        layout.addWidget(self._toolbar)

        # Canvas
        self._canvas = AnnotationCanvas(self._pixmap, self)
        self._canvas.set_pen_color(initial_color)
        self._canvas.set_pen_width(initial_width)
        self._canvas.set_text_color(self._text_color)
        self._canvas.set_text_bg_color(self._text_bg_color)
        self._canvas.set_fill_enabled(bool(self._config.get("fill_shapes", False)))
        self._view = CanvasView(self._canvas)
        # Keep a visible gutter around the complete canvas region so the
        # screenshot does not visually merge into the editor's chrome.
        self._canvas_container = QWidget()
        canvas_layout = QVBoxLayout(self._canvas_container)
        canvas_layout.setContentsMargins(16, 16, 16, 16)
        canvas_layout.setSpacing(0)
        canvas_layout.addWidget(self._view)
        layout.addWidget(self._canvas_container)

        # Status bar
        self._statusbar = QStatusBar()
        self._statusbar.setFixedHeight(40)
        self.setStatusBar(self._statusbar)
        self._size_label = QLabel(
            f"{self._pixmap.width()} × {self._pixmap.height()} px"
        )
        self._size_label.setAccessibleName("Image dimensions")
        self._statusbar.addWidget(self._size_label)

        zoom_controls = QWidget()
        zoom_layout = QHBoxLayout(zoom_controls)
        zoom_layout.setContentsMargins(4, 0, 4, 0)
        zoom_layout.setSpacing(2)
        zoom_out = QToolButton()
        zoom_out.setText("−")
        zoom_out.setToolTip("Zoom out (Ctrl+-)")
        zoom_out.setAccessibleName("Zoom out")
        zoom_out.clicked.connect(self._view.zoom_out)
        zoom_layout.addWidget(zoom_out)
        self._zoom_label = QLabel("100%")
        self._zoom_label.setMinimumWidth(48)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_label.setAccessibleName("Zoom level")
        zoom_layout.addWidget(self._zoom_label)
        zoom_in = QToolButton()
        zoom_in.setText("+")
        zoom_in.setToolTip("Zoom in (Ctrl++)")
        zoom_in.setAccessibleName("Zoom in")
        zoom_in.clicked.connect(self._view.zoom_in)
        zoom_layout.addWidget(zoom_in)
        fit_button = QToolButton()
        fit_button.setText("Fit")
        fit_button.setToolTip("Fit image to view (Ctrl+0)")
        fit_button.setAccessibleName("Fit image to view")
        fit_button.clicked.connect(self._view.zoom_reset)
        zoom_layout.addWidget(fit_button)
        self._statusbar.addPermanentWidget(zoom_controls)

        self._hint_label = QLabel(
            "V Select   ·   Ctrl+wheel Zoom   ·   Ctrl+Z Undo   ·   Del Delete"
        )
        self._hint_label.setStyleSheet(f"color: {TEXT_MUTED};")
        self._statusbar.addPermanentWidget(self._hint_label)
        self._view.zoom_changed.connect(self._on_zoom_changed)

    def showEvent(self, event):
        super().showEvent(event)
        # Use the first laid-out frame, without an arbitrary 100 ms delay.
        self.centralWidget().layout().activate()
        self._view.fit_in_view_nice()

    def load_capture(self, pixmap: QPixmap):
        """Supply the first capture to the unused, prebuilt editor."""
        self._pixmap = pixmap
        self._canvas.set_background(pixmap)
        self._size_label.setText(f"{pixmap.width()} × {pixmap.height()} px")
        # Capture can take place on a different monitor from app startup.
        screen = screen_at_cursor()
        if screen is not None:
            self.setScreen(screen)
            self._ui_scaler.refresh()
            rect = screen.availableGeometry()
            self.resize(round(rect.width() * _EDITOR_SCREEN_RATIO),
                        round(rect.height() * _EDITOR_SCREEN_RATIO))
            self.move(rect.center() - self.rect().center())

    def _on_ui_scale_changed(self, scale):
        width = max(1, min(80, round(self._logical_stroke_width * scale)))
        text_size = max(6, min(288, round(self._logical_text_size * scale)))
        bubble_size = max(16, min(128, round(self._logical_bubble_size * scale)))
        self._toolbar.apply_ui_scale(scale, width, text_size, bubble_size)
        # Only defaults for NEW annotations follow DPI. Existing image content
        # must remain unchanged when dragging the editor to another monitor.
        self._canvas.set_annotation_scale(scale, width, text_size, bubble_size)
        self._hint_label.setVisible(self.width() >= 900 * scale)

    def _on_stroke_width_changed(self, width):
        self._logical_stroke_width = width / self._ui_scaler.scale
        self._canvas.set_pen_width(width)
        self._persist_editor_property("stroke_width", round(self._logical_stroke_width))

    def _on_text_size_changed(self, size):
        self._logical_text_size = size / self._ui_scaler.scale
        self._canvas.set_text_size(size)
        self._persist_editor_property("text_size", round(self._logical_text_size))

    def _on_bubble_size_changed(self, size):
        self._logical_bubble_size = size / self._ui_scaler.scale
        self._canvas.set_bubble_size(self._logical_bubble_size)
        self._persist_editor_property("bubble_size", round(self._logical_bubble_size))

    def _on_color_changed(self, color):
        self._canvas.set_pen_color(color)
        self._persist_editor_property("stroke_color", color.name())

    def _on_text_color_changed(self, color):
        self._text_color = QColor(color)
        self._canvas.set_text_color(color)
        self._persist_editor_property("text_color", color.name())

    def _on_text_bg_color_changed(self, color):
        self._text_bg_color = QColor(color)
        self._canvas.set_text_bg_color(color)
        self._persist_editor_property("text_bg_color", color.name())

    def _on_fill_changed(self, enabled):
        self._canvas.set_fill_enabled(enabled)
        self._persist_editor_property("fill_shapes", bool(enabled))

    def _persist_editor_property(self, key, value):
        """Persist editor defaults without breaking lightweight test configs."""
        if not hasattr(self._config, "_config_path"):
            self._config._data[key] = value
            return
        self._config.set(key, value)

    def _setup_shortcuts(self):
        # Tool shortcuts
        shortcuts = {
            'V': ToolType.SELECT,
            'A': ToolType.ARROW,
            'L': ToolType.LINE,
            'R': ToolType.RECT,
            'E': ToolType.ELLIPSE,
            'T': ToolType.TEXT,
            'B': ToolType.BUBBLE,
        }
        for key, tool in shortcuts.items():
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(lambda t=tool: self._toolbar.set_tool(t))

        # Undo / Redo
        QShortcut(QKeySequence.StandardKey.Undo, self).activated.connect(self._canvas.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self).activated.connect(self._canvas.redo)

        # Zoom
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self._view.zoom_in)
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(self._view.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self._view.zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self._view.zoom_reset)

        # Save / Copy
        QShortcut(QKeySequence.StandardKey.Save, self).activated.connect(self._save_file)
        QShortcut(QKeySequence.StandardKey.Copy, self).activated.connect(self._copy_clipboard)
        QShortcut(QKeySequence("Ctrl+G"), self).activated.connect(self._open_gallery)
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(
            self.settings_requested.emit
        )

        # Delete
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self).activated.connect(self._canvas.delete_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self).activated.connect(self._canvas.delete_selected)

    def _connect_signals(self):
        self._toolbar.tool_changed.connect(self._canvas.set_tool)
        self._toolbar.color_changed.connect(self._on_color_changed)
        self._toolbar.stroke_width_changed.connect(self._on_stroke_width_changed)
        self._toolbar.fill_changed.connect(self._on_fill_changed)
        self._toolbar.text_color_changed.connect(self._on_text_color_changed)
        self._toolbar.text_bg_color_changed.connect(self._on_text_bg_color_changed)
        self._toolbar.text_size_changed.connect(self._on_text_size_changed)
        self._toolbar.bubble_size_changed.connect(self._on_bubble_size_changed)
        self._toolbar.undo_requested.connect(self._canvas.undo)
        self._toolbar.redo_requested.connect(self._canvas.redo)
        self._toolbar.save_file_requested.connect(self._save_file)
        self._toolbar.copy_clipboard_requested.connect(self._copy_clipboard)
        self._toolbar.gallery_requested.connect(self._open_gallery)
        self._canvas.undo_stack.canUndoChanged.connect(
            lambda enabled: self._toolbar.set_command_state(
                enabled, self._canvas.undo_stack.canRedo()
            )
        )
        self._canvas.undo_stack.canRedoChanged.connect(
            lambda enabled: self._toolbar.set_command_state(
                self._canvas.undo_stack.canUndo(), enabled
            )
        )
        self._toolbar.set_command_state(
            self._canvas.undo_stack.canUndo(), self._canvas.undo_stack.canRedo()
        )

    def _on_zoom_changed(self, value: float):
        self._zoom_label.setText(f"{round(value * 100)}%")

    def _open_gallery(self):
        dialog = GalleryDialog(
            self._recent_screenshots,
            self._config.save_directory,
            self,
        )
        pixmap = QPixmap()
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted and not sip.isdeleted(dialog):
                pixmap = QPixmap(dialog.selected_pixmap)
        finally:
            # Read the result before disposal; emitting it replaces this editor.
            if not sip.isdeleted(dialog):
                dialog.dispose()
                dialog.deleteLater()
        if not self._disposed and not pixmap.isNull():
            self.gallery_image_selected.emit(pixmap)

    def _save_file(self):
        """Save the annotated screenshot to a file."""
        save_dir = self._config.save_directory
        fmt = self._config.default_format
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = os.path.join(save_dir, f"SnapEdit_{timestamp}.{fmt}")

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Image", default_name,
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp);;All Files (*)"
        )
        if file_path:
            pixmap = self._canvas.export_to_pixmap()
            pixmap.save(file_path)
            self._statusbar.showMessage(f"Saved to {file_path}", 5000)

    def _copy_clipboard(self):
        """Copy the annotated screenshot to clipboard."""
        pixmap = self._canvas.export_to_pixmap()
        clipboard = QApplication.clipboard()
        clipboard.setPixmap(pixmap)
        self._statusbar.showMessage("Copied to clipboard", 3000)

    def dispose(self):
        """Release native image buffers without waiting for Python cyclic GC."""
        if self._disposed:
            return
        self._disposed = True
        self._ui_scaler.dispose()
        for dialog in self.findChildren(QDialog):
            if not sip.isdeleted(dialog):
                dialog.close()
                if hasattr(dialog, "dispose"):
                    dialog.dispose()
                dialog.deleteLater()
        self._pixmap = QPixmap()
        # Do not clear the controller's shared recent-capture list.
        self._recent_screenshots = []
        self._view.setScene(None)
        self._canvas.dispose()

    def closeEvent(self, event):
        super().closeEvent(event)
        if event.isAccepted() and not self._disposed:
            self.dispose()
            self.closed.emit()

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
    QMainWindow, QWidget, QVBoxLayout,
    QFileDialog, QApplication, QStatusBar, QLabel, QDialog
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

    def __init__(self, pixmap: QPixmap, config: Config,
                 recent_screenshots=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._disposed = False
        self._config = config
        self._logical_stroke_width = float(config.stroke_width)
        self._logical_text_size = 14.0
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
        """ % (
            BASE, BASE, TEXT_SECONDARY, BORDER_SUBTLE, TYPE_BODY_PT,
            TEXT_SECONDARY,
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
        self._toolbar = Toolbar(initial_color, initial_width)
        layout.addWidget(self._toolbar)

        # Canvas
        self._canvas = AnnotationCanvas(self._pixmap, self)
        self._canvas.set_pen_color(initial_color)
        self._canvas.set_pen_width(initial_width)
        self._view = CanvasView(self._canvas)
        layout.addWidget(self._view)

        # Status bar
        self._statusbar = QStatusBar()
        self._statusbar.setFixedHeight(28)
        self.setStatusBar(self._statusbar)
        self._size_label = QLabel(
            f"{self._pixmap.width()} × {self._pixmap.height()} px"
        )
        self._size_label.setAccessibleName("Image dimensions")
        self._statusbar.addWidget(self._size_label)

        self._hint_label = QLabel(
            "V Select   ·   Ctrl+wheel Zoom   ·   Ctrl+Z Undo   ·   Del Delete"
        )
        self._hint_label.setStyleSheet(f"color: {TEXT_MUTED};")
        self._statusbar.addPermanentWidget(self._hint_label)

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
        self._toolbar.apply_ui_scale(scale, width, text_size)
        # Only defaults for NEW annotations follow DPI. Existing image content
        # must remain unchanged when dragging the editor to another monitor.
        self._canvas.set_annotation_scale(scale, width, text_size)
        self._hint_label.setVisible(self.width() >= 900 * scale)

    def _on_stroke_width_changed(self, width):
        self._logical_stroke_width = width / self._ui_scaler.scale
        self._canvas.set_pen_width(width)

    def _on_text_size_changed(self, size):
        self._logical_text_size = size / self._ui_scaler.scale
        self._canvas.set_text_size(size)

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

        # Delete
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self).activated.connect(self._canvas.delete_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self).activated.connect(self._canvas.delete_selected)

    def _connect_signals(self):
        self._toolbar.tool_changed.connect(self._canvas.set_tool)
        self._toolbar.color_changed.connect(self._canvas.set_pen_color)
        self._toolbar.stroke_width_changed.connect(self._on_stroke_width_changed)
        self._toolbar.fill_changed.connect(self._canvas.set_fill_enabled)
        self._toolbar.text_color_changed.connect(self._canvas.set_text_color)
        self._toolbar.text_bg_color_changed.connect(self._canvas.set_text_bg_color)
        self._toolbar.text_size_changed.connect(self._on_text_size_changed)
        self._toolbar.undo_requested.connect(self._canvas.undo)
        self._toolbar.redo_requested.connect(self._canvas.redo)
        self._toolbar.save_file_requested.connect(self._save_file)
        self._toolbar.copy_clipboard_requested.connect(self._copy_clipboard)
        self._toolbar.gallery_requested.connect(self._open_gallery)

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

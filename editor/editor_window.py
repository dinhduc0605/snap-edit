"""
Main editor window for SnapEdit.
Combines toolbar, canvas, and provides save/export functionality.
"""
import os
from datetime import datetime
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (
    QPixmap, QKeySequence, QShortcut, QColor
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QFileDialog, QApplication, QStatusBar, QLabel
)
from editor.toolbar import Toolbar, ToolType
from editor.canvas import AnnotationCanvas, CanvasView
from settings.config import Config
from theme import (
    BASE, BORDER_SUBTLE, TEXT_MUTED, TEXT_SECONDARY,
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

    def __init__(self, pixmap: QPixmap, config: Config, parent=None):
        super().__init__(parent)
        self._config = config
        self._pixmap = pixmap
        self._setup_window()
        self._setup_ui()
        self._setup_shortcuts()
        self._connect_signals()

    def _setup_window(self):
        self.setWindowTitle("SnapEdit — Editor")
        self.setMinimumSize(_MIN_EDITOR_WIDTH, _MIN_EDITOR_HEIGHT)

        # Keep the initial editor size independent of screenshot dimensions.
        w = _FALLBACK_EDITOR_WIDTH
        h = _FALLBACK_EDITOR_HEIGHT
        screen = QApplication.primaryScreen()
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
                font-size: 13px;
                padding: 0 8px;
            }
            QStatusBar QLabel {
                color: %s;
                padding: 0 4px;
            }
        """ % (BASE, BASE, TEXT_SECONDARY, BORDER_SUBTLE, TEXT_SECONDARY))

    def resizeEvent(self, event):
        if hasattr(self, "_hint_label"):
            self._hint_label.setVisible(event.size().width() >= 900)
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
        self._canvas = AnnotationCanvas(self._pixmap)
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

        # Fit after layout
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self._view.fit_in_view_nice)

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

        # Delete
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self).activated.connect(self._canvas.delete_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self).activated.connect(self._canvas.delete_selected)

    def _connect_signals(self):
        self._toolbar.tool_changed.connect(self._canvas.set_tool)
        self._toolbar.color_changed.connect(self._canvas.set_pen_color)
        self._toolbar.stroke_width_changed.connect(self._canvas.set_pen_width)
        self._toolbar.fill_changed.connect(self._canvas.set_fill_enabled)
        self._toolbar.text_color_changed.connect(self._canvas.set_text_color)
        self._toolbar.text_bg_color_changed.connect(self._canvas.set_text_bg_color)
        self._toolbar.text_size_changed.connect(self._canvas.set_text_size)
        self._toolbar.undo_requested.connect(self._canvas.undo)
        self._toolbar.redo_requested.connect(self._canvas.redo)
        self._toolbar.save_file_requested.connect(self._save_file)
        self._toolbar.copy_clipboard_requested.connect(self._copy_clipboard)

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

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

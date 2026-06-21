"""
Main editor window for SnapEdit.
Combines toolbar, canvas, and provides save/export functionality.
"""
import os
from datetime import datetime
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import (
    QPixmap, QKeySequence, QShortcut, QIcon, QColor, QAction
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFileDialog, QApplication, QStatusBar, QLabel
)
from editor.toolbar import Toolbar, ToolType
from editor.canvas import AnnotationCanvas, CanvasView
from settings.config import Config


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
        self.setMinimumSize(800, 600)
        # Size window to fit screenshot but not exceed screen
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            w = min(self._pixmap.width() + 60, screen_rect.width() - 100)
            h = min(self._pixmap.height() + 120, screen_rect.height() - 100)
            self.resize(w, h)
            # Center on screen
            x = (screen_rect.width() - w) // 2 + screen_rect.x()
            y = (screen_rect.height() - h) // 2 + screen_rect.y()
            self.move(x, y)

        self.setStyleSheet("""
            QMainWindow {
                background: #202020;
            }
            QStatusBar {
                background: #202020;
                color: #8080A0;
                border-top: 1px solid #333333;
                font-size: 12px;
                padding: 2px 8px;
            }
        """)

    def resizeEvent(self, event):
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
        self.setStatusBar(self._statusbar)
        self._status_label = QLabel(
            f"Size: {self._pixmap.width()} × {self._pixmap.height()}px  |  "
            "V: Select  |  Ctrl+Scroll / ±: Zoom  Ctrl+0: Fit  |  "
            "Ctrl+Z/Y: Undo/Redo  |  Del: Delete  |  Ctrl+S: Save  Ctrl+C: Copy"
        )
        self._statusbar.addWidget(self._status_label)

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
            self._statusbar.showMessage(f"✅ Saved to: {file_path}", 5000)

    def _copy_clipboard(self):
        """Copy the annotated screenshot to clipboard."""
        pixmap = self._canvas.export_to_pixmap()
        clipboard = QApplication.clipboard()
        clipboard.setPixmap(pixmap)
        self._statusbar.showMessage("📋 Copied to clipboard!", 3000)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

"""
SnapEdit — Lightweight Screenshot Capture & Annotation Tool for Windows 11
Main entry point. Runs in system tray with global hotkey support.
"""
import sys
import os

# Tắt tự động scale DPI của Qt để lấy thông số pixel thực tế (khớp với MSS)
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"

# Ép Windows cho phép ứng dụng đọc DPI thực
import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("snapedit.app.1.0")
except Exception:
    pass

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QFont
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget
)

from settings.config import Config
from hotkey.manager import HotkeyManager
from capture.fullscreen import capture_fullscreen
from capture.region import RegionSelector
from editor.editor_window import EditorWindow
from settings.settings_dialog import SettingsDialog


class SnapEditApp:
    """Main application controller. Lives in system tray."""

    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)
        self._app.setApplicationName("SnapEdit")
        self._app.setStyle("Fusion")

        # Apply dark palette globally
        self._apply_dark_palette()

        self._config = Config()
        self._editor_window = None
        self._region_selector = None

        self._setup_tray()
        self._setup_hotkeys()

    def _apply_dark_palette(self):
        from PyQt6.QtGui import QPalette
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1E1E2E"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#E0E0F0"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#2A2A3C"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#363650"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#2A2A3C"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#E0E0F0"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#E0E0F0"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#2A2A3C"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#E0E0F0"))
        palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#7C5CFC"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.Link, QColor("#7C5CFC"))
        self._app.setPalette(palette)

    def _create_tray_icon(self) -> QIcon:
        """Create a simple tray icon programmatically."""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background circle
        painter.setBrush(QColor("#7C5CFC"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(4, 4, 56, 56, 14, 14)

        # Camera icon shape
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(14, 22, 36, 26, 4, 4)
        painter.drawRect(26, 16, 12, 8)

        # Lens
        painter.setBrush(QColor("#7C5CFC"))
        painter.drawEllipse(24, 26, 16, 16)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(28, 30, 8, 8)

        painter.end()
        return QIcon(pixmap)

    def _setup_tray(self):
        icon = self._create_tray_icon()
        self._app.setWindowIcon(icon)
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(icon)
        self._tray.setToolTip("SnapEdit — Screenshot Capture & Edit")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background: #1E1E2E;
                border: 1px solid #3A3A50;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px;
                color: #E0E0F0;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #7C5CFC;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background: #3A3A50;
                margin: 4px 8px;
            }
        """)

        # Capture actions
        fullscreen_action = QAction("📸  Capture Fullscreen", menu)
        fullscreen_action.triggered.connect(self._capture_fullscreen)
        menu.addAction(fullscreen_action)

        region_action = QAction("✂️  Capture Region", menu)
        region_action.triggered.connect(self._capture_region)
        menu.addAction(region_action)

        menu.addSeparator()

        # Settings
        settings_action = QAction("⚙️  Settings", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        # Exit
        exit_action = QAction("❌  Exit", menu)
        exit_action.triggered.connect(self._quit)
        menu.addAction(exit_action)

        self._tray.setContextMenu(menu)
        # Keep reference to prevent GC
        self._menu = menu
        self._tray.show()

        # Show startup notification
        self._tray.showMessage(
            "SnapEdit is running",
            "The application is running in the system tray.\n"
            f"Fullscreen: {self._config.get('hotkeys.fullscreen', 'Alt+Shift+1')}\n"
            f"Region: {self._config.get('hotkeys.region', 'Alt+Shift+2')}",
            QSystemTrayIcon.MessageIcon.Information,
            3000
        )

    def _setup_hotkeys(self):
        self._hotkey_manager = HotkeyManager(self._config)
        self._hotkey_manager.fullscreen_triggered.connect(self._capture_fullscreen)
        self._hotkey_manager.region_triggered.connect(self._capture_region)
        self._hotkey_manager.start()

    def _capture_fullscreen(self):
        """Capture the full screen and open editor."""
        # Small delay to let menu close / tray hide
        QTimer.singleShot(300, self._do_fullscreen_capture)

    def _do_fullscreen_capture(self):
        pixmap = capture_fullscreen()
        if pixmap and not pixmap.isNull():
            self._open_editor(pixmap)

    def _capture_region(self):
        """Open region selector overlay."""
        QTimer.singleShot(200, self._do_region_capture)

    def _do_region_capture(self):
        self._region_selector = RegionSelector()
        self._region_selector.region_captured.connect(self._on_region_captured)
        self._region_selector.start()

    def _on_region_captured(self, pixmap: QPixmap):
        if self._region_selector:
            self._region_selector.close()
            self._region_selector = None
        if pixmap and not pixmap.isNull():
            self._open_editor(pixmap)

    def _open_editor(self, pixmap: QPixmap):
        """Open the editor window with the captured screenshot."""
        # Close existing editor if open
        if self._editor_window:
            self._editor_window.close()

        self._editor_window = EditorWindow(pixmap, self._config)
        self._editor_window.closed.connect(self._on_editor_closed)
        self._editor_window.show()
        self._editor_window.activateWindow()

    def _on_editor_closed(self):
        self._editor_window = None

    def _open_settings(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(self._config)
        if dialog.exec():
            # Reload hotkeys with new config
            self._config.load()
            self._hotkey_manager.reload(self._config)

    def _quit(self):
        """Clean up and exit."""
        self._hotkey_manager.stop()
        self._tray.hide()
        QApplication.quit()

    def run(self) -> int:
        """Start the application event loop."""
        return self._app.exec()


def main():

    app = SnapEditApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()

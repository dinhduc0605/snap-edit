"""
SnapEdit — Lightweight Screenshot Capture & Annotation Tool for Windows 11
Main entry point. Runs in system tray with global hotkey support.
"""
import sys
import os
from pathlib import Path

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

from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QFont
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu
)

from settings.config import Config
from hotkey.manager import HotkeyManager
from capture.fullscreen import capture_fullscreen
from capture.region import RegionSelector
from capture.timed_region import TimedRegionSelector
from editor.editor_window import EditorWindow
from settings.settings_dialog import SettingsDialog
from theme import (
    ACCENT, BASE, BORDER, HOVER, SURFACE, SURFACE_ALT, TEXT_PRIMARY,
    TYPE_BODY_PT,
)
from windows_integration import SingleInstanceLock, show_already_running_message
from ui_scaling import prepare_ui_fonts, WindowScaler, screen_at_cursor, screen_scale


# Bound retained raw image pixels as well as capture count. This does not
# constrain the active editor or silently downsample screenshots.
_RECENT_MAX_IMAGES = 5
_RECENT_MAX_BYTES = 64 * 1024 * 1024


def pixmap_bytes(pixmap: QPixmap) -> int:
    """Estimate aligned pixel storage without converting/copying the image."""
    return ((pixmap.width() * pixmap.depth() + 31) // 32) * 4 * pixmap.height()


class SnapEditApp:
    """Main application controller. Lives in system tray."""

    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)
        self._app.setApplicationName("SnapEdit")
        self._app.setStyle("Fusion")
        self._app.setFont(QFont("Segoe UI Variable", TYPE_BODY_PT))

        # Apply dark palette globally
        self._apply_dark_palette()

        self._config = Config()
        self._editor_window = None
        self._recent_screenshots = []
        self._region_selector = None
        self._timed_region_selector = None

        # Pay lazy font/style initialization before announcing readiness or
        # accepting capture hotkeys. No desktop image is captured at startup.
        prepare_ui_fonts()
        placeholder = QPixmap(1, 1)
        placeholder.fill(Qt.GlobalColor.transparent)
        self._prepared_editor = EditorWindow(
            placeholder, self._config, self._recent_screenshots,
        )
        self._prepared_editor.ensurePolished()
        self._prepared_editor.grab(QRect(0, 0, self._prepared_editor.width(),
                                        self._prepared_editor._toolbar.sizeHint().height()))
        selector = RegionSelector()
        selector.deleteLater()

        self._setup_tray()
        self._setup_hotkeys()

    def _apply_dark_palette(self):
        from PyQt6.QtGui import QPalette
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(BASE))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_ALT))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Button, QColor(SURFACE))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(BASE))
        palette.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
        self._app.setPalette(palette)

    def _create_tray_icon(self) -> QIcon:
        """Load the bundled app icon, falling back to the generated icon."""
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).resolve().parent

        icon_path = base_path / "assets" / "icon.ico"
        if icon_path.is_file():
            return QIcon(str(icon_path))

        # Fallback for development if the icon asset is unavailable.
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background circle
        painter.setBrush(QColor("#0F6CBD"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(4, 4, 56, 56, 14, 14)

        # Camera icon shape
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(14, 22, 36, 26, 4, 4)
        painter.drawRect(26, 16, 12, 8)

        # Lens
        painter.setBrush(QColor("#0F6CBD"))
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
                background: %s;
                border: 1px solid %s;
                border-radius: 8px;
                padding: 8px;
                font-family: 'Segoe UI Variable', 'Segoe UI';
                font-size: %dpt;
                min-width: 220px;
            }
            QMenu::item {
                padding: 10px 36px 10px 16px;
                color: %s;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: %s;
                color: %s;
            }
            QMenu::separator {
                height: 1px;
                background: %s;
                margin: 6px 8px;
            }
        """ % (
            SURFACE, BORDER, TYPE_BODY_PT, TEXT_PRIMARY,
            HOVER, TEXT_PRIMARY, BORDER,
        ))

        # Capture actions
        fullscreen_action = QAction("Capture full screen", menu)
        fullscreen_action.triggered.connect(self._capture_fullscreen)
        menu.addAction(fullscreen_action)

        region_action = QAction("Capture region", menu)
        region_action.triggered.connect(self._capture_region)
        menu.addAction(region_action)

        timed_region_action = QAction("Timed region capture", menu)
        timed_region_action.triggered.connect(self._capture_timed_region)
        menu.addAction(timed_region_action)

        menu.addSeparator()

        # Settings
        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        # Exit
        exit_action = QAction("Exit SnapEdit", menu)
        exit_action.triggered.connect(self._quit)
        menu.addAction(exit_action)

        self._tray.setContextMenu(menu)
        # Keep reference to prevent GC
        self._menu = menu
        self._menu_scaler = WindowScaler(menu, resize_window=False)
        menu.aboutToShow.connect(
            lambda: self._menu_scaler.apply(screen_scale(screen_at_cursor()), resize=False)
        )
        self._tray.show()

        # Show startup notification
        self._tray.showMessage(
            "SnapEdit is running",
            "The application is running in the system tray.",
            QSystemTrayIcon.MessageIcon.Information,
            3000
        )

    def _setup_hotkeys(self):
        self._hotkey_manager = HotkeyManager(self._config)
        self._hotkey_manager.fullscreen_triggered.connect(self._capture_fullscreen)
        self._hotkey_manager.region_triggered.connect(self._capture_region)
        self._hotkey_manager.timed_region_triggered.connect(
            self._capture_timed_region
        )
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
        if self._region_selector:
            return
        self._region_selector = RegionSelector()
        self._region_selector.region_captured.connect(self._on_region_captured)
        self._region_selector.selection_cancelled.connect(self._on_region_cancelled)
        self._region_selector.start()

    def _on_region_cancelled(self):
        selector = self._region_selector
        self._region_selector = None
        if selector:
            selector.deleteLater()

    def _on_region_captured(self, pixmap: QPixmap):
        if self._region_selector:
            self._region_selector.close()
            self._region_selector.deleteLater()
            self._region_selector = None
        if pixmap and not pixmap.isNull():
            self._open_editor(pixmap)

    def _capture_timed_region(self):
        """Open the timed region selector after the tray menu closes."""
        QTimer.singleShot(200, self._do_timed_region_capture)

    def _do_timed_region_capture(self):
        if self._timed_region_selector:
            self._timed_region_selector.close()
            self._timed_region_selector.deleteLater()
        self._timed_region_selector = TimedRegionSelector()
        self._timed_region_selector.region_captured.connect(
            self._on_timed_region_captured
        )
        self._timed_region_selector.selection_cancelled.connect(
            self._on_timed_region_cancelled
        )
        self._timed_region_selector.start()

    def _on_timed_region_captured(self, pixmap: QPixmap):
        if self._timed_region_selector:
            self._timed_region_selector.deleteLater()
        self._timed_region_selector = None
        if pixmap and not pixmap.isNull():
            self._open_editor(pixmap)

    def _on_timed_region_cancelled(self):
        if self._timed_region_selector:
            self._timed_region_selector.deleteLater()
        self._timed_region_selector = None

    def _remember_capture(self, pixmap: QPixmap):
        size = pixmap_bytes(pixmap)
        # An oversized capture can still be edited/exported at full quality;
        # don't retain it in history or discard useful smaller recent images.
        if pixmap.isNull() or size > _RECENT_MAX_BYTES:
            return
        self._recent_screenshots.insert(0, QPixmap(pixmap))
        total = sum(pixmap_bytes(image) for image in self._recent_screenshots)
        while (len(self._recent_screenshots) > _RECENT_MAX_IMAGES
               or total > _RECENT_MAX_BYTES):
            total -= pixmap_bytes(self._recent_screenshots.pop())

    def _open_editor(self, pixmap: QPixmap, add_to_recent: bool = True):
        """Open the editor window with the captured screenshot."""
        if add_to_recent:
            self._remember_capture(pixmap)

        # Close existing editor if open
        if self._editor_window:
            self._editor_window.close()

        if self._prepared_editor is not None:
            self._editor_window = self._prepared_editor
            self._prepared_editor = None
            self._editor_window.load_capture(pixmap)
        else:
            self._editor_window = EditorWindow(
                pixmap, self._config, self._recent_screenshots,
            )
        self._editor_window.closed.connect(self._on_editor_closed)
        self._editor_window.gallery_image_selected.connect(
            self._open_gallery_image
        )
        self._editor_window.show()
        self._editor_window.activateWindow()

    def _on_editor_closed(self):
        # EditorWindow disposes its buffers and uses WA_DeleteOnClose.
        self._editor_window = None

    def _open_gallery_image(self, pixmap: QPixmap):
        self._open_editor(pixmap, add_to_recent=False)

    def _open_settings(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(self._config)
        try:
            if dialog.exec():
                # Reload hotkeys with new config
                self._config.load()
                self._hotkey_manager.reload(self._config)
                # An unused editor may contain the old drawing defaults.
                if self._prepared_editor is not None:
                    self._prepared_editor.dispose()
                    self._prepared_editor.deleteLater()
                    self._prepared_editor = None
        finally:
            dialog._ui_scaler.dispose()
            dialog.deleteLater()

    def _quit(self):
        """Clean up and exit."""
        if self._timed_region_selector:
            self._timed_region_selector.close()
        if self._region_selector:
            self._region_selector.close()
        if self._editor_window:
            self._editor_window.close()
        if self._prepared_editor:
            self._prepared_editor.dispose()
            self._prepared_editor.deleteLater()
            self._prepared_editor = None
        self._recent_screenshots.clear()
        self._hotkey_manager.stop()
        self._tray.hide()
        QApplication.quit()

    def run(self) -> int:
        """Start the application event loop."""
        return self._app.exec()


def main():
    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire():
        show_already_running_message()
        return

    try:
        app = SnapEditApp()
        exit_code = app.run()
    finally:
        instance_lock.release()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

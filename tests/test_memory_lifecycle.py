"""Ownership/cache regressions. No real desktop, user settings, or clipboard.

Do not rely on gc.collect(): large native buffers must be released at close.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import gc
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import weakref
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import main
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QTimer
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from editor.canvas import TextSettingsPopup, ShapeSettingsPopup
from editor.editor_window import EditorWindow
from editor.gallery_dialog import GalleryDialog
from editor.items.rect_item import RectItem
from editor.items.text_item import TextItem
from settings.config import Config, DEFAULT_CONFIG
from ui_scaling import WindowScaler, prepare_ui_fonts


class MemoryLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        prepare_ui_fonts()

    def setUp(self):
        self.was_gc_enabled = gc.isenabled()
        gc.disable()
        self.config = Config.__new__(Config)
        self.config._data = deepcopy(DEFAULT_CONFIG)
        self.config._data["save_directory"] = "does-not-exist"
        self.controller = main.SnapEditApp.__new__(main.SnapEditApp)
        self.controller._config = self.config
        self.controller._editor_window = None
        self.controller._prepared_editor = None
        self.controller._recent_screenshots = []
        self.windows = []

    def flush(self):
        for _ in range(2):
            self.app.processEvents()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def tearDown(self):
        if self.controller._editor_window:
            self.controller._editor_window.close()
        if self.controller._prepared_editor:
            self.controller._prepared_editor.dispose()
            self.controller._prepared_editor.deleteLater()
        for widget in self.windows:
            if not sip.isdeleted(widget):
                widget.close()
                widget.deleteLater()
        self.controller._recent_screenshots.clear()
        self.flush()
        if self.was_gc_enabled:
            gc.enable()

    @staticmethod
    def image(width=320, height=180, color="#527da9"):
        result = QPixmap(width, height)
        result.fill(QColor(color))
        return result

    def open_editor(self):
        self.controller._open_editor(self.image())
        self.flush()
        return self.controller._editor_window

    def test_closed_editor_scene_scaler_and_wrapper_die_without_gc(self):
        for _ in range(20):
            editor = self.open_editor()
            canvas = editor._canvas
            canvas._add_text(QPointF(20, 20))
            canvas._add_bubble(QPointF(100, 100))
            canvas.undo()  # Also free items no longer attached to the scene.
            refs = [weakref.ref(obj) for obj in (editor, canvas, editor._ui_scaler)]
            refs += [weakref.ref(item) for item in canvas.get_annotation_items()]
            editor._ui_scaler.schedule_refresh()
            editor.close()
            self.assertTrue(editor._pixmap.isNull())
            self.assertEqual(canvas.items(), [])
            self.assertEqual(canvas.undo_stack.count(), 0)
            del editor, canvas
            self.flush()
            self.assertIsNone(self.controller._editor_window)
            self.assertTrue(all(ref() is None for ref in refs))

    def test_scaler_weak_owner_and_cancelled_refresh_after_disposal(self):
        widget = QWidget()
        scaler = WindowScaler(widget)
        ref = weakref.ref(widget)
        scaler.schedule_refresh()
        scaler.dispose()
        scaler.dispose()
        self.assertFalse(scaler._refresh_timer.isActive())
        self.assertEqual(scaler._widgets, [])
        widget.deleteLater()
        del widget
        self.flush()
        self.assertIsNone(ref())
        # Python wrapper might be held by a caller after C++ deletion.
        scaler.refresh()
        scaler.apply(2)

    def test_dialogs_and_popups_do_not_accumulate(self):
        editor = self.open_editor()
        canvas = editor._canvas
        canvas._add_text(QPointF(20, 20))
        text = next(item for item in canvas.items() if isinstance(item, TextItem))
        shape = RectItem(QRectF(0, 0, 40, 40))
        canvas.addItem(shape)
        baseline = len(self.app.allWidgets())
        event = SimpleNamespace(widget=editor._view.viewport, screenPos=lambda: QPoint(10, 10))
        for _ in range(20):
            for popup_type, item in ((TextSettingsPopup, text), (ShapeSettingsPopup, shape)):
                canvas._show_settings_popup(popup_type, item, event)
                ref = weakref.ref(canvas._settings_popup)
                canvas._settings_popup.close()
                self.flush()
                self.assertIsNone(ref())
                self.assertIsNone(canvas._settings_popup)
            with patch.object(GalleryDialog, "exec", return_value=QDialog.DialogCode.Rejected):
                editor._open_gallery()
            self.flush()
            self.assertEqual(len(self.app.allWidgets()), baseline)

    def test_replacing_popup_does_not_clear_new_popup_reference(self):
        editor = self.open_editor()
        canvas = editor._canvas
        canvas._add_text(QPointF(20, 20))
        item = next(item for item in canvas.items() if isinstance(item, TextItem))
        event = SimpleNamespace(widget=editor._view.viewport, screenPos=lambda: QPoint(10, 10))
        canvas._show_settings_popup(TextSettingsPopup, item, event)
        old = weakref.ref(canvas._settings_popup)
        canvas._show_settings_popup(TextSettingsPopup, item, event)
        new = canvas._settings_popup
        self.flush()
        self.assertIsNone(old())
        self.assertIs(canvas._settings_popup, new)
        editor.close()
        self.flush()
        self.assertTrue(sip.isdeleted(new))

    def test_gallery_accept_transfers_shared_image_before_destroying_editor(self):
        editor = self.open_editor()
        old_ref = weakref.ref(editor)
        key = self.controller._recent_screenshots[0].cacheKey()

        def choose_recent(dialog):
            QTimer.singleShot(0, lambda: dialog._select_item(dialog._recent_list.item(0)))
            return QDialog.exec(dialog)

        with patch.object(GalleryDialog, "exec", choose_recent):
            editor._open_gallery()
        del editor
        self.flush()
        self.assertIsNone(old_ref())
        self.assertEqual(self.controller._editor_window._pixmap.cacheKey(), key)
        self.assertEqual(len(self.controller._recent_screenshots), 1)

    def test_gallery_cancel_and_exception_both_dispose(self):
        editor = self.open_editor()
        refs = []

        def fail(dialog):
            refs.append(weakref.ref(dialog))
            raise RuntimeError("test dialog failure")

        with patch.object(GalleryDialog, "exec", fail), self.assertRaises(RuntimeError):
            editor._open_gallery()
        self.flush()
        self.assertIsNone(refs[0]())

    def test_recent_cache_count_bytes_and_newest_order(self):
        history = self.controller._recent_screenshots
        for i in range(8):
            self.controller._remember_capture(self.image(color=QColor(i, 0, 0)))
        self.assertEqual(len(history), 5)
        self.assertEqual(history[0].toImage().pixelColor(0, 0).red(), 7)
        self.assertEqual(history[-1].toImage().pixelColor(0, 0).red(), 3)
        history.clear()
        for i in range(6):
            self.controller._remember_capture(self.image(3840, 2160, QColor(i, 0, 0)))
            self.assertLessEqual(sum(main.pixmap_bytes(image) for image in history), main._RECENT_MAX_BYTES)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].toImage().pixelColor(0, 0).red(), 5)
        self.assertEqual(history[-1].toImage().pixelColor(0, 0).red(), 4)

    def test_oversized_capture_opens_at_full_resolution_without_entering_cache(self):
        self.controller._remember_capture(self.image())
        original_key = self.controller._recent_screenshots[0].cacheKey()
        # A small test budget exercises the same branch without an 8K allocation.
        with patch("main._RECENT_MAX_BYTES", 1024):
            self.controller._open_editor(self.image(640, 360))
        editor = self.controller._editor_window
        self.assertEqual(editor._pixmap.width(), 640)
        self.assertEqual(editor._canvas.export_to_pixmap().size(), editor._pixmap.size())
        self.assertEqual(len(self.controller._recent_screenshots), 1)
        self.assertEqual(self.controller._recent_screenshots[0].cacheKey(), original_key)

    def test_gallery_uses_actual_dpi_thumbnails_and_clears_buffers(self):
        gallery = GalleryDialog([self.image()], "does-not-exist")
        self.windows.append(gallery)
        for scale in (1, 2, 1.5, 1):
            gallery._ui_scaler.apply(scale, resize=False)
            size = gallery._recent_list.iconSize()
            thumbnail = gallery._recent_list.item(0).icon().pixmap(size)
            self.assertEqual(thumbnail.width(), round(148 * scale))
        gallery._select_item(gallery._recent_list.item(0))
        selected = QPixmap(gallery.selected_pixmap)
        gallery.dispose()
        self.assertEqual(gallery._recent_screenshots, [])
        self.assertEqual(gallery._recent_list.count(), 0)
        self.assertTrue(gallery.selected_pixmap.isNull())
        self.assertFalse(selected.isNull())

    def test_gallery_open_folder_button_creates_and_opens_save_directory(self):
        with TemporaryDirectory() as temporary:
            save_directory = Path(temporary) / "saved-images"
            gallery = GalleryDialog([], str(save_directory))
            self.windows.append(gallery)
            with patch(
                "editor.gallery_dialog.QDesktopServices.openUrl", return_value=True
            ) as open_url:
                gallery._open_folder_button.click()

            self.assertTrue(save_directory.is_dir())
            opened_url = open_url.call_args.args[0]
            self.assertEqual(Path(opened_url.toLocalFile()), save_directory.resolve())

    def test_settings_completion_disposes_prepared_editor(self):
        prepared = EditorWindow(self.image(), self.config)
        self.controller._prepared_editor = prepared
        self.controller._hotkey_manager = SimpleNamespace(reload=lambda _: None)
        ref = weakref.ref(prepared)
        del prepared
        with patch("main.SettingsDialog.exec", return_value=QDialog.DialogCode.Accepted), \
             patch.object(self.config, "load"):
            self.controller._open_settings()
        self.flush()
        self.assertIsNone(ref())
        self.assertIsNone(self.controller._prepared_editor)


if __name__ == "__main__":
    unittest.main()

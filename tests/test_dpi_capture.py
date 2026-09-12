"""Regression checks: python -m unittest discover -s tests -v.

Uses synthetic pixels/offscreen Qt, never real desktop pixels or user config.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import main  # Set the same physical-coordinate/DPI policy as the application.
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from capture.region import RegionSelector
from capture.timed_region import TimedRegionSelector
from editor.editor_window import EditorWindow
from editor.canvas import TextSettingsPopup, ShapeSettingsPopup
from editor.toolbar import ToolType
from editor.gallery_dialog import GalleryDialog
from editor.items.arrow_item import ArrowItem
from editor.items.rect_item import RectItem
from editor.items.text_item import TextItem
from settings.config import Config, DEFAULT_CONFIG
from settings.settings_dialog import SettingsDialog
from ui_scaling import prepare_ui_fonts, screen_scale, scaled_stylesheet


class DpiCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setFont(QFont("Segoe UI Variable", 10))
        prepare_ui_fonts()

    def setUp(self):
        self.config = Config.__new__(Config)
        self.config._data = deepcopy(DEFAULT_CONFIG)
        self.pixmap = QPixmap(640, 360)
        self.pixmap.fill(QColor("#357abc"))
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            if not sip.isdeleted(window):
                window.close()
                window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def keep(self, widget):
        self.windows.append(widget)
        return widget

    def editor(self):
        return self.keep(EditorWindow(self.pixmap, self.config))

    def test_dpi_and_stylesheet_units(self):
        for dpi, scale in ((96, 1), (120, 1.25), (144, 1.5), (192, 2), (288, 3)):
            self.assertEqual(screen_scale(SimpleNamespace(logicalDotsPerInch=lambda: dpi)), scale)
        self.assertEqual(scaled_stylesheet("font-size: 12pt; padding: 4px;", 2),
                         "font-size: 32px; padding: 8px;")

    def test_scale_roundtrip_and_actual_icon_size(self):
        editor = self.editor()
        for scale in (1, 1.25, 1.5, 2, 3, 1, 2, 1):
            editor._ui_scaler.apply(scale, resize=False)
            button = editor._toolbar._save_btn
            self.assertEqual(button.size(), QSize(round(44 * scale), round(44 * scale)))
            size = round(24 * scale)
            self.assertEqual(button.iconSize(), QSize(size, size))
            self.assertEqual(button.icon().pixmap(QSize(size, size)).size(), QSize(size, size))
            self.assertEqual(editor._toolbar.layout().contentsMargins().left(), round(12 * scale))
            self.assertEqual(editor._canvas._pen_width, round(5 * scale))
            self.assertEqual(editor._canvas._text_size, round(14 * scale))

    def test_canvas_container_has_scaled_outer_padding(self):
        editor = self.editor()
        margins = editor._canvas_container.layout().contentsMargins()
        self.assertEqual(
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            (16, 16, 16, 16),
        )
        editor._ui_scaler.apply(2, resize=False)
        margins = editor._canvas_container.layout().contentsMargins()
        self.assertEqual(
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            (32, 32, 32, 32),
        )

    def test_monitor_transition_does_not_edit_selected_annotations(self):
        editor = self.editor()
        editor._ui_scaler.apply(2, resize=False)
        canvas = editor._canvas
        canvas._add_text(QPointF(20, 20))
        text = next(item for item in canvas.items() if isinstance(item, TextItem))
        text.setPlainText("DPI")
        text._exit_edit_mode()
        text.setSelected(True)
        original = text.boundingRect()
        editor._ui_scaler.apply(1, resize=False)
        self.assertEqual(text.font_size, 28)
        self.assertEqual(text.boundingRect(), original)
        self.assertEqual(canvas._text_size, 14)
        self.assertEqual(canvas.export_to_pixmap().size(), self.pixmap.size())
        editor._ui_scaler.apply(2, resize=False)
        editor._toolbar._width_spin.setValue(9)
        editor._ui_scaler.apply(1.5, resize=False)
        self.assertEqual(canvas._pen_width, 7)  # 9/2 * 1.5, rounded once
        editor._ui_scaler.apply(2, resize=False)
        self.assertEqual(canvas._pen_width, 9)

    def test_text_tool_focuses_existing_text_instead_of_adding_item(self):
        editor = self.editor()
        editor.show()
        self.app.processEvents()
        canvas = editor._canvas
        canvas._add_text(QPointF(100, 80))
        text = next(item for item in canvas.items() if isinstance(item, TextItem))
        text.setPlainText("Existing text")
        text._exit_edit_mode()
        canvas.set_tool(ToolType.TEXT)
        item_count = len(canvas.get_annotation_items())

        click_pos = editor._view.mapFromScene(
            text.mapToScene(text.boundingRect().center())
        )
        QTest.mouseClick(
            editor._view.viewport(), Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, click_pos,
        )
        self.app.processEvents()

        self.assertEqual(len(canvas.get_annotation_items()), item_count)
        self.assertTrue(text.hasFocus())
        self.assertEqual(
            text.textInteractionFlags(), Qt.TextInteractionFlag.TextEditorInteraction,
        )

    def test_short_arrowhead_is_constrained_to_arrow_length(self):
        arrow = ArrowItem(QPointF(0, 0), QPointF(8, 0), pen_width=20)
        head = arrow._arrowhead_polygon()
        self.assertFalse(head.isEmpty())
        self.assertLessEqual(head.boundingRect().width(), 8)
        self.assertGreaterEqual(head.boundingRect().left(), 0)

        zero_length_arrow = ArrowItem(QPointF(0, 0), QPointF(0, 0))
        self.assertTrue(zero_length_arrow._arrowhead_polygon().isEmpty())

    def test_new_bubbles_scale_but_existing_bubbles_do_not(self):
        canvas = self.editor()._canvas
        canvas.set_annotation_scale(2, 6, 28)
        canvas._add_bubble(QPointF(100, 100))
        bubble = canvas.get_annotation_items()[0]
        self.assertEqual(bubble.scale(), 2)
        self.assertEqual(bubble.pos(), QPointF(68, 68))
        canvas.set_annotation_scale(1, 3, 14)
        self.assertEqual(bubble.scale(), 2)

    def test_prepared_editor_keeps_full_resolution_and_first_frame_fits(self):
        editor = self.editor()
        capture = QPixmap(3840, 2160)
        capture.fill(QColor("#123456"))
        editor.load_capture(capture)
        editor.show()
        self.assertEqual(editor._canvas.sceneRect(), QRect(0, 0, 3840, 2160).toRectF())
        self.assertLess(editor._view.transform().m11(), 1)
        zoom = editor._view.transform().m11()
        viewport = editor._view.viewport().size()
        horizontal_margin = (viewport.width() - capture.width() * zoom) / 2
        vertical_margin = (viewport.height() - capture.height() * zoom) / 2
        self.assertLessEqual(min(horizontal_margin, vertical_margin), 1)
        self.assertEqual(editor._canvas.export_to_pixmap().size(), capture.size())

    def test_small_capture_opens_at_100_percent(self):
        capture = QPixmap(100, 100)
        capture.fill(QColor("#123456"))
        editor = self.keep(EditorWindow(capture, self.config))
        editor.show()
        self.app.processEvents()

        self.assertEqual(editor._view.transform().m11(), 1)
        self.assertEqual(editor._zoom_label.text(), "100%")

    def test_region_release_crops_frozen_undimmed_pixels_without_mss(self):
        selector = self.keep(RegionSelector())
        selector.setGeometry(-640, -100, 640, 360)
        selector._desktop_pixmap = self.pixmap
        selector._origin = QPoint(20, 30)
        selector._selecting = True
        result = []
        selector.region_captured.connect(result.append)
        event = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(119, 79),
                            QPointF(-521, -21), Qt.MouseButton.LeftButton,
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        with patch.object(selector, "_capture_region") as live_capture:
            selector.mouseReleaseEvent(event)
        live_capture.assert_not_called()
        self.assertEqual(result[0].size(), QSize(100, 50))
        self.assertEqual(result[0].toImage().pixelColor(0, 0), QColor("#357abc"))

    def test_live_capture_preserves_negative_physical_coordinates(self):
        selector = self.keep(RegionSelector())
        selector.setGeometry(-3840, -200, 5760, 2160)
        shot = SimpleNamespace(bgra=bytes((0, 0, 255, 255)) * 5000, width=100, height=50)
        with patch("capture.region.mss.mss") as mss:
            mss.return_value.__enter__.return_value.grab.return_value = shot
            result = selector._capture_region(QRect(20, 30, 100, 50))
        mss.return_value.__enter__.return_value.grab.assert_called_once_with(
            {"left": -3820, "top": -170, "width": 100, "height": 50})
        self.assertEqual(result.size(), QSize(100, 50))

    def test_timed_capture_still_grabs_live_after_countdown(self):
        selector = self.keep(TimedRegionSelector())
        selector._selection_rect = QRect(10, 20, 100, 50)
        selector._desktop_pixmap = self.pixmap  # Must NOT use this stale image.
        selector._remaining_seconds = 1
        result = []
        selector.region_captured.connect(result.append)
        with patch.object(selector, "_capture_region", return_value=self.pixmap) as capture:
            selector._countdown_tick()
        capture.assert_called_once_with(QRect(10, 20, 100, 50))
        self.assertEqual(len(result), 1)

    def test_scaled_label_is_cached_and_inside_overlay(self):
        selector = self.keep(RegionSelector())
        selector.resize(3840, 2160)
        selector._set_label_screen(SimpleNamespace(logicalDotsPerInch=lambda: 192))
        metrics = selector._label_metrics
        for rect in (QRect(0, 0, 10, 10), QRect(0, 0, 3840, 2160), QRect(3800, 2100, 40, 60)):
            label = selector._dimension_label_rect(rect)
            self.assertTrue(selector.rect().contains(label))
            self.assertIs(selector._label_metrics, metrics)

    def test_dialogs_and_popups_scale_without_inheriting_scale_twice(self):
        editor = self.editor()
        editor._ui_scaler.apply(2, resize=False)
        widgets = [self.keep(SettingsDialog(self.config)),
                   self.keep(GalleryDialog([self.pixmap], "does-not-exist", editor)),
                   self.keep(TextSettingsPopup(TextItem(), editor)),
                   self.keep(ShapeSettingsPopup(RectItem(QRectF(0, 0, 100, 100)), editor))]
        for widget in widgets:
            for scale in (1, 2, 1.5, 1):
                widget._ui_scaler.apply(scale, resize=False)
                widget.ensurePolished()
                self.assertFalse(widget.grab().isNull())
            self.assertLessEqual(widget.font().pixelSize(), 14)

    def test_app_prepares_editor_before_hotkeys_and_reuses_it_once(self):
        def verify_ready(controller):
            self.assertIsNotNone(controller._prepared_editor)
            self.assertFalse(controller._prepared_editor.isVisible())
        with patch("main.QApplication", return_value=self.app), \
             patch("main.Config", return_value=self.config), \
             patch.object(main.SnapEditApp, "_setup_tray", verify_ready), \
             patch.object(main.SnapEditApp, "_setup_hotkeys", verify_ready):
            controller = main.SnapEditApp()
        prepared = self.keep(controller._prepared_editor)
        controller._open_editor(self.pixmap)
        self.assertIs(controller._editor_window, prepared)
        self.assertIsNone(controller._prepared_editor)
        prepared.close()
        self.assertIsNone(controller._editor_window)
        controller._open_editor(self.pixmap)
        self.keep(controller._editor_window)
        self.assertIsNot(controller._editor_window, prepared)
        self.assertEqual(len(controller._recent_screenshots), 2)


if __name__ == "__main__":
    unittest.main()

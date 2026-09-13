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
from PyQt6.QtWidgets import QApplication, QToolButton
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
from theme import EDITOR_CONTENT_PADDING
from ui_scaling import prepare_ui_fonts, screen_scale, scaled_stylesheet
from ui_widgets import BasicColorDialog, TransparencyPreviewButton


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
            (EDITOR_CONTENT_PADDING,) * 4,
        )
        editor._ui_scaler.apply(2, resize=False)
        margins = editor._canvas_container.layout().contentsMargins()
        self.assertEqual(
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            (EDITOR_CONTENT_PADDING * 2,) * 4,
        )

    def test_text_padding_scales_with_font_size(self):
        item = TextItem(font_size=14)
        initial_padding = item.text_padding
        self.assertAlmostEqual(item.document().documentMargin(), initial_padding)

        item.set_font_size(28)
        self.assertAlmostEqual(item.text_padding, initial_padding * 2)
        self.assertAlmostEqual(item.document().documentMargin(), initial_padding * 2)

    def test_text_background_picker_supports_transparent(self):
        dialog = self.keep(BasicColorDialog(
            QColor("#FFFFFF"), title="Background color", allow_transparent=True
        ))
        transparent = next(
            button for button in dialog.findChildren(QToolButton)
            if button.accessibleName() == "Transparent"
        )
        self.assertEqual(transparent.text(), "")
        self.assertEqual(transparent.width(), transparent.height())
        dialog.show()
        self.app.processEvents()
        black = next(
            button for button in dialog.findChildren(QToolButton)
            if button.accessibleName() == "Black"
        )
        self.assertEqual(transparent.y(), black.y())
        self.assertLess(transparent.x(), black.x())
        transparent.click()
        self.assertTrue(dialog.selected_color.isValid())
        self.assertEqual(dialog.selected_color.alpha(), 0)

        editor = self.editor()
        editor._on_text_bg_color_changed(dialog.selected_color)
        self.assertEqual(self.config._data["text_bg_color"], "#00000000")
        self.assertEqual(editor._canvas._text_bg_color.alpha(), 0)

        popup = self.keep(TextSettingsPopup(
            TextItem(bg_color=QColor(0, 0, 0, 0)), editor
        ))
        preview = popup.findChild(TransparencyPreviewButton)
        self.assertIsNotNone(preview)
        self.assertTrue(preview.is_transparent_preview)

    def test_shift_constrains_new_rect_ellipse_and_line(self):
        canvas = self.editor()._canvas
        start = QPointF(100, 100)

        canvas.set_tool(ToolType.RECT)
        square_end = canvas._constrain_draw_endpoint(start, QPointF(180, 130), True)
        self.assertEqual(abs(square_end.x() - start.x()), abs(square_end.y() - start.y()))

        canvas.set_tool(ToolType.ELLIPSE)
        circle_end = canvas._constrain_draw_endpoint(start, QPointF(125, 190), True)
        self.assertEqual(abs(circle_end.x() - start.x()), abs(circle_end.y() - start.y()))

        canvas.set_tool(ToolType.LINE)
        horizontal_end = canvas._constrain_draw_endpoint(start, QPointF(180, 130), True)
        self.assertEqual(horizontal_end.y(), start.y())
        vertical_end = canvas._constrain_draw_endpoint(start, QPointF(120, 190), True)
        self.assertEqual(vertical_end.x(), start.x())

    def test_annotations_can_extend_past_the_captured_image_and_export_black(self):
        canvas = self.editor()._canvas
        shape = RectItem(QRectF(0, 0, 20, 20))
        canvas.addItem(shape)

        shape.setPos(-40, 10)
        image_rect = canvas.sceneRect()
        bounds = shape.sceneBoundingRect()
        self.assertLess(bounds.left(), image_rect.left())

        exported = canvas.export_to_pixmap()
        self.assertGreater(exported.width(), self.pixmap.width())
        self.assertEqual(
            exported.toImage().pixelColor(0, 0), QColor(Qt.GlobalColor.black)
        )

    def test_shape_picker_updates_the_active_mode_and_toolbar_icon(self):
        toolbar = self.editor()._toolbar
        toolbar._set_shape_tool(ToolType.RECT)

        self.assertEqual(toolbar.current_tool, ToolType.RECT)
        self.assertEqual(toolbar._shape_button.property("iconName"), "rect")
        self.assertTrue(toolbar._shape_button.property("pickerIndicator"))
        self.assertTrue(toolbar._shape_button.isChecked())

    def test_shape_picker_is_compact_and_selects_a_shape(self):
        toolbar = self.editor()._toolbar
        toolbar.show()
        self.app.processEvents()
        toolbar._shape_button.click()
        self.app.processEvents()

        popup = toolbar._shape_picker
        self.assertIsNotNone(popup)
        self.assertTrue(popup.isVisible())
        self.assertLessEqual(popup.width(), 220)
        self.assertLessEqual(popup.height(), 210)

        popup.close()
        self.app.processEvents()
        self.assertEqual(toolbar.current_tool, ToolType.SELECT)
        self.assertTrue(toolbar._tool_buttons[ToolType.SELECT].isChecked())

        toolbar._shape_button.click()
        self.app.processEvents()
        popup = toolbar._shape_picker

        popup._buttons[ToolType.ELLIPSE].click()
        self.app.processEvents()
        self.assertEqual(toolbar.current_tool, ToolType.ELLIPSE)
        self.assertEqual(toolbar._shape_button.property("iconName"), "ellipse")

    def test_shape_can_start_in_the_workspace_outside_the_screenshot(self):
        small_capture = QPixmap(100, 100)
        small_capture.fill(QColor("#357abc"))
        editor = self.keep(EditorWindow(small_capture, self.config))
        editor.show()
        self.app.processEvents()
        editor._toolbar.set_tool(ToolType.LINE)

        image_origin_before = editor._view.mapFromScene(QPointF(0, 0))
        start = editor._view.mapFromScene(QPointF(-20, 20))
        end = editor._view.mapFromScene(QPointF(20, 20))
        self.assertTrue(editor._view.viewport().rect().contains(start))
        QTest.mousePress(editor._view.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(editor._view.viewport(), end)
        QTest.mouseRelease(editor._view.viewport(), Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier, end)
        self.app.processEvents()

        item = editor._canvas.get_annotation_items()[0]
        self.assertLess(item.sceneBoundingRect().left(), 0)
        self.assertEqual(
            editor._view.mapFromScene(QPointF(0, 0)), image_origin_before
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

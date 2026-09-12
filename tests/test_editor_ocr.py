"""Editor OCR overlay behaviour without relying on live Windows OCR."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication

from editor.canvas import AnnotationCanvas
from editor.toolbar import ToolType
from ocr.worker import OcrLayout, OcrWord


class EditorOcrOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.pixmap = QPixmap(320, 180)
        self.pixmap.fill(QColor("#245486"))
        self.canvas = AnnotationCanvas(self.pixmap)
        self.canvas.set_tool(ToolType.OCR)

    def tearDown(self):
        self.canvas.dispose()

    @staticmethod
    def _layout(language="en-US"):
        return OcrLayout(
            language_tag=language,
            text="SnapEdit OCR\nSecond line",
            words=(
                OcrWord("SnapEdit", 20, 20, 72, 20, 0, 0),
                OcrWord("OCR", 100, 20, 34, 20, 0, 1),
                OcrWord("Second", 20, 56, 54, 20, 1, 0),
                OcrWord("line", 82, 56, 32, 20, 1, 1),
            ),
        )

    def test_drag_selection_returns_words_in_reading_order(self):
        self.canvas.show_ocr_layout(self._layout())
        overlay = self.canvas._ocr_overlay

        overlay._set_selection_from_rect(QRectF(15, 15, 125, 30), is_click=False)

        self.assertTrue(self.canvas.has_ocr_selection())
        self.assertEqual(self.canvas.selected_ocr_text(), "SnapEdit OCR")
        self.assertEqual(overlay.selected_word_count, 2)
        self.assertEqual(self.canvas.get_annotation_items(), [])

    def test_all_selected_words_preserve_recognizer_line_breaks(self):
        self.canvas.show_ocr_layout(self._layout())
        overlay = self.canvas._ocr_overlay

        overlay._set_selection_from_rect(QRectF(0, 0, 200, 100), is_click=False)

        self.assertEqual(self.canvas.selected_ocr_text(), "SnapEdit OCR\nSecond line")

    def test_export_omits_transient_highlight_layer(self):
        self.canvas.show_ocr_layout(self._layout())

        exported = self.canvas.export_to_pixmap()

        self.assertEqual(exported.toImage().pixelColor(25, 25), QColor("#245486"))
        self.assertTrue(self.canvas._ocr_overlay.isVisible())

    def test_japanese_selection_normalizes_word_gaps(self):
        layout = OcrLayout(
            language_tag="ja",
            text="全国の中古車が様々",
            words=(
                OcrWord("全国", 10, 10, 20, 16, 0, 0),
                OcrWord("の", 34, 10, 10, 16, 0, 1),
                OcrWord("中古車", 48, 10, 30, 16, 0, 2),
                OcrWord("が", 82, 10, 10, 16, 0, 3),
                OcrWord("様", 96, 10, 10, 16, 0, 4),
                OcrWord("々", 110, 10, 10, 16, 0, 5),
            ),
        )
        self.canvas.show_ocr_layout(layout)
        self.canvas._ocr_overlay._set_selection_from_rect(
            QRectF(94, 5, 31, 30), is_click=False
        )

        self.assertEqual(self.canvas.selected_ocr_text(), "様々")

"""Windows OCR integration using the installed Windows recognizer."""
import io
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest

from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication

from ocr.worker import OcrLayoutWorker, OcrWorker


class OcrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_worker_recognizes_and_returns_text_without_blocking_gui(self):
        image = Image.new("RGBA", (900, 180), "white")
        draw = ImageDraw.Draw(image)
        font_path = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "segoeui.ttf")
        draw.text((25, 25), "SnapEdit OCR 123", fill="black",
                  font=ImageFont.truetype(font_path, 48))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        pixmap = QPixmap.fromImage(QImage.fromData(stream.getvalue()))

        worker = OcrWorker(pixmap)
        output = []
        errors = []
        worker.text_ready.connect(output.append)
        worker.failed.connect(errors.append)
        worker.start()
        while worker.isRunning():
            self.app.processEvents()
        worker.wait()
        self.app.processEvents()

        if errors and "ngôn ngữ OCR" in errors[0]:
            self.skipTest(errors[0])
        self.assertFalse(errors)
        self.assertIn("SnapEdit", output[0])

    def test_worker_uses_japanese_recognizer_when_available(self):
        from winrt.windows.media.ocr import OcrEngine

        if not any(language.language_tag == "ja" for language in OcrEngine.available_recognizer_languages):
            self.skipTest("Japanese OCR language pack is not installed")

        image = Image.new("RGBA", (900, 180), "white")
        draw = ImageDraw.Draw(image)
        font_path = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "NotoSansJP-VF.ttf")
        draw.text((25, 25), "こんにちは 世界", fill="black",
                  font=ImageFont.truetype(font_path, 48))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        pixmap = QPixmap.fromImage(QImage.fromData(stream.getvalue()))

        worker = OcrWorker(pixmap, language="ja")
        output = []
        errors = []
        worker.text_ready.connect(output.append)
        worker.failed.connect(errors.append)
        worker.start()
        while worker.isRunning():
            self.app.processEvents()
        worker.wait()
        self.app.processEvents()

        self.assertFalse(errors)
        self.assertIn("こんにちは", output[0])
        self.assertNotIn("こ ん", output[0])
        self.assertEqual(
            OcrWorker._normalize_japanese_text("中 古 車 【 グ ー ネ ッ ト 】 !"),
            "中古車【グーネット】!",
        )
        self.assertEqual(
            OcrWorker._normalize_japanese_text("全国 の 中古車 が 様 々 な 条件"),
            "全国の中古車が様々な条件",
        )

    def test_layout_worker_returns_word_rectangles_for_editor_selection(self):
        image = Image.new("RGBA", (900, 180), "white")
        draw = ImageDraw.Draw(image)
        font_path = os.path.join(
            os.environ.get("WINDIR", "C:/Windows"), "Fonts", "segoeui.ttf"
        )
        draw.text((25, 25), "SnapEdit OCR 123", fill="black",
                  font=ImageFont.truetype(font_path, 48))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        pixmap = QPixmap.fromImage(QImage.fromData(stream.getvalue()))

        worker = OcrLayoutWorker(pixmap, language="en")
        output = []
        errors = []
        worker.layout_ready.connect(output.append)
        worker.failed.connect(errors.append)
        worker.start()
        while worker.isRunning():
            self.app.processEvents()
        worker.wait()
        self.app.processEvents()

        if errors and "gói OCR tiếng Anh" in errors[0]:
            self.skipTest(errors[0])
        self.assertFalse(errors)
        self.assertIn("SnapEdit", output[0].text)
        self.assertTrue(output[0].words)
        self.assertGreater(output[0].words[0].width, 0)
        self.assertGreater(output[0].words[0].height, 0)

    def test_layout_worker_uses_japanese_variants_for_small_text(self):
        from winrt.windows.media.ocr import OcrEngine

        if not any(language.language_tag == "ja"
                   for language in OcrEngine.available_recognizer_languages):
            self.skipTest("Japanese OCR language pack is not installed")

        image = Image.new("RGBA", (900, 180), "white")
        draw = ImageDraw.Draw(image)
        font_path = os.path.join(
            os.environ.get("WINDIR", "C:/Windows"), "Fonts", "NotoSansJP-VF.ttf"
        )
        draw.text((25, 25), "カード", fill="black",
                  font=ImageFont.truetype(font_path, 32))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        pixmap = QPixmap.fromImage(QImage.fromData(stream.getvalue()))

        worker = OcrLayoutWorker(pixmap, language="ja")
        output = []
        errors = []
        worker.layout_ready.connect(output.append)
        worker.failed.connect(errors.append)
        worker.start()
        while worker.isRunning():
            self.app.processEvents()
        worker.wait()
        self.app.processEvents()

        self.assertFalse(errors)
        self.assertEqual(output[0].text, "カード")
        self.assertTrue(output[0].words)

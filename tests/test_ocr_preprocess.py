"""Unit tests for OCR image candidates and language/result selection."""
import unittest

from PIL import Image

from ocr.preprocess import OcrPreprocessor
from ocr.worker import OcrCandidate, OcrWorker


def rgba_bytes(width: int, height: int, color: str = "white") -> bytes:
    return Image.new("RGBA", (width, height), color).tobytes("raw", "RGBA")


class OcrPreprocessorTests(unittest.TestCase):
    def test_japanese_mode_keeps_source_and_makes_two_safe_variants(self):
        variants = OcrPreprocessor(10_000).prepare(
            180, 48, rgba_bytes(180, 48), japanese_variants=True
        )

        self.assertEqual([item.name for item in variants], [
            "source", "padded", "enhanced",
        ])
        self.assertEqual((variants[0].width, variants[0].height), (180, 48))
        self.assertGreater(variants[1].width, variants[0].width)
        self.assertGreater(variants[1].height, variants[0].height)
        self.assertTrue(all(len(item.bgra_pixels) == item.width * item.height * 4
                            for item in variants))

    def test_regular_mode_does_not_add_extra_ocr_passes(self):
        variants = OcrPreprocessor(10_000).prepare(
            400, 180, rgba_bytes(400, 180), japanese_variants=False
        )
        self.assertEqual([item.name for item in variants], ["source"])

    def test_all_variants_respect_windows_ocr_dimension_limit(self):
        variants = OcrPreprocessor(100).prepare(
            100, 24, rgba_bytes(100, 24), japanese_variants=True
        )
        self.assertTrue(all(max(item.width, item.height) <= 100 for item in variants))

    def test_invalid_pixel_buffer_is_rejected(self):
        with self.assertRaises(ValueError):
            OcrPreprocessor(100).prepare(10, 10, b"bad", japanese_variants=True)


class OcrResultSelectionTests(unittest.TestCase):
    def test_japanese_consensus_beats_a_single_disagreement(self):
        result = OcrWorker._select_result([
            OcrCandidate("ja", "source", "東京駅"),
            OcrCandidate("ja", "padded", "東京駅"),
            OcrCandidate("ja", "enhanced", "東京驛"),
        ], "ja")
        self.assertEqual(result, "東京駅")

    def test_japanese_normalization_happens_before_consensus(self):
        result = OcrWorker._select_result([
            OcrCandidate("ja", "source", "全国 の 中古車 が 様 々"),
            OcrCandidate("ja", "padded", "全国の中古車が様々"),
        ], "ja")
        self.assertEqual(result, "全国の中古車が様々")

    def test_auto_keeps_japanese_result_when_it_contains_script_characters(self):
        result = OcrWorker._select_result([
            OcrCandidate("en-US", "source", "Tokyo station"),
            OcrCandidate("ja", "source", "東京駅"),
        ])
        self.assertEqual(result, "東京駅")

    def test_language_preference_filters_installed_tags(self):
        tags = ["en-US", "ja", "en-US"]
        self.assertEqual(OcrWorker._select_language_tags(tags, "ja-JP"), ["ja"])
        self.assertEqual(OcrWorker._select_language_tags(tags, "en"), ["en-US"])
        self.assertEqual(OcrWorker._select_language_tags(tags, "invalid"), ["en-US", "ja"])

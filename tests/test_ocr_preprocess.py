"""Unit tests for OCR image candidates and language/result selection."""
import unittest
from types import SimpleNamespace

from PIL import Image

from ocr.preprocess import OcrImageVariant, OcrPreprocessor
from ocr.worker import OcrCandidate, OcrLayoutWorker, OcrWorker


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

    def test_japanese_variants_keep_a_mapping_to_original_pixels(self):
        variants = OcrPreprocessor(10_000).prepare(
            180, 48, rgba_bytes(180, 48), japanese_variants=True
        )
        padded = variants[1]

        content_width = padded.width - 2 * padded.source_offset_x
        content_height = padded.height - 2 * padded.source_offset_y
        self.assertAlmostEqual(content_width * padded.source_scale_x, 180)
        self.assertAlmostEqual(content_height * padded.source_scale_y, 48)

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


class OcrLayoutTests(unittest.TestCase):
    def test_layout_maps_downscaled_word_bounds_back_to_source_pixels(self):
        worker = OcrLayoutWorker.__new__(OcrLayoutWorker)
        worker._width = 200
        worker._height = 100
        result = SimpleNamespace(
            text="SnapEdit",
            lines=[SimpleNamespace(
                text="SnapEdit",
                words=[SimpleNamespace(
                    text="SnapEdit",
                    bounding_rect=SimpleNamespace(x=10, y=5, width=30, height=12),
                )],
            )],
        )
        variant = OcrImageVariant(
            "source", 100, 50, b"\0" * (100 * 50 * 4),
            source_scale_x=2.0,
            source_scale_y=2.0,
        )

        layout = worker._layout_from_result(result, "en-US", variant)

        self.assertEqual(layout.text, "SnapEdit")
        self.assertEqual(len(layout.words), 1)
        self.assertEqual(
            (layout.words[0].x, layout.words[0].y,
             layout.words[0].width, layout.words[0].height),
            (20.0, 10.0, 60.0, 24.0),
        )

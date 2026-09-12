"""Tests for the local OCR benchmark metrics, independent of Windows OCR."""
import unittest

from ocr.benchmark import (
    character_error_rate,
    levenshtein_distance,
    make_measurement,
    summarize,
)


class OcrBenchmarkTests(unittest.TestCase):
    def test_levenshtein_and_character_error_rate(self):
        self.assertEqual(levenshtein_distance("東京駅", "東亰駅"), 1)
        self.assertAlmostEqual(character_error_rate("東京駅", "東亰駅"), 1 / 3)

    def test_japanese_measurement_ignores_ocr_word_spacing(self):
        measurement = make_measurement(
            "spacing", "全国の中古車が様々", "全国 の 中古車 が 様 々", 42.0, "ja"
        )
        self.assertEqual(measurement.cer, 0.0)

    def test_summary_reports_mean_accuracy_and_time(self):
        first = make_measurement("one", "ab", "ab", 10.0, "en")
        second = make_measurement("two", "ab", "ac", 30.0, "en")
        self.assertEqual(
            summarize([first, second]),
            {"cases": 2, "mean_cer": 0.25, "mean_elapsed_ms": 20.0},
        )

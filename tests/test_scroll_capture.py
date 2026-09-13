"""Scroll capture matching and disk-backed assembly checks."""
import os
import unittest
from unittest.mock import Mock, patch

import numpy as np

from capture.scroll_stitch import StitchError, StripStore, difference, gray, match_vertical
from capture.scroll_capture import ScrollCaptureWorker
from capture.scroll_native import ScrollTarget
from PyQt6.QtCore import QRect


class ScrollCaptureTests(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(7)

    def pixels(self, height, width=160):
        return self.rng.integers(0, 256, (height, width, 3), dtype=np.uint8)

    def test_vertical_overlap_returns_exact_scroll_distance(self):
        page = self.pixels(500)
        match = match_vertical(page[:220], page[57:277])
        self.assertEqual(match.shift, 57)
        self.assertEqual((match.top, match.bottom), (0, 0))

    def test_fixed_header_and_footer_are_detected(self):
        header, footer, page = self.pixels(18), self.pixels(16), self.pixels(500)
        frame = lambda y: np.concatenate((header, page[y:y + 186], footer))
        match = match_vertical(frame(0), frame(47))
        self.assertEqual(match.shift, 47)
        self.assertEqual((match.top, match.bottom), (18, 16))

    def test_blank_content_is_rejected_as_ambiguous(self):
        blank = np.zeros((220, 160, 3), dtype=np.uint8)
        changed = blank.copy()
        changed[180:] = 40
        with self.assertRaises(StitchError):
            match_vertical(blank, changed)

    def test_sparse_text_movement_is_not_mistaken_for_a_stable_page(self):
        first = np.full((220, 160, 3), 245, dtype=np.uint8)
        second = first.copy()
        for y in (25, 75, 125, 175):
            first[y:y + 2, 25:130:3] = 20
            second[y + 8:y + 10, 25:130:3] = 20
        self.assertGreater(difference(gray(first), gray(second)), 2)

    def test_strip_store_assembles_exact_pixels(self):
        first, second = self.pixels(80), self.pixels(30)
        store = StripStore(160, max_pixels=160 * 200, max_height=200)
        try:
            store.append(first)
            store.append(second)
            with store.assemble() as image:
                actual = np.asarray(image).copy()
            np.testing.assert_array_equal(actual, np.concatenate((first, second)))
        finally:
            store.close()

    def test_strip_store_enforces_output_limit(self):
        store = StripStore(160, max_pixels=160 * 50, max_height=100)
        try:
            with self.assertRaises(StitchError):
                store.append(self.pixels(51))
        finally:
            store.close()

    def test_worker_scrolls_until_stable_and_emits_the_long_image(self):
        page = self.pixels(180, 80)
        frames = [page[0:100], page[30:130], page[60:160]]
        worker = ScrollCaptureWorker(QRect(10, 20, 80, 100))
        target = Mock()
        result = []

        def read_result(path, warning):
            with Image.open(path) as image:
                result.append((np.asarray(image).copy(), warning))
            os.unlink(path)

        from PIL import Image
        worker.completed.connect(read_result)
        with patch("capture.scroll_capture.ScrollTarget", return_value=target), \
                patch("capture.scroll_capture.mss.mss"), \
                patch("capture.scroll_capture.time.sleep"), \
                patch.object(worker, "_grab", return_value=frames[0]), \
                patch.object(worker, "_settled_frame", side_effect=[
                    frames[1], frames[2], frames[2], frames[2],
                ]):
            worker.run()

        self.assertEqual(len(result), 1)
        np.testing.assert_array_equal(result[0][0], page[:160])
        self.assertEqual(result[0][1], "")
        self.assertEqual(target.scroll.call_count, 4)
        target.restore_cursor.assert_called_once()

    def test_scroll_target_locks_and_releases_pointer(self):
        target = ScrollTarget.__new__(ScrollTarget)
        target.api = Mock()
        target.api.ClipCursor.return_value = True
        target.point = (120, 240)
        target._cursor_clipped = False

        target.lock_cursor()
        self.assertTrue(target._cursor_clipped)
        target.release_cursor()
        self.assertFalse(target._cursor_clipped)
        target.api.ClipCursor.assert_called_with(None)


if __name__ == "__main__":
    unittest.main()

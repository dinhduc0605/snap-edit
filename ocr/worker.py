"""Asynchronous Windows OCR worker.

The Windows.Media.Ocr engine uses the recognizer languages installed for the
current Windows user. The GUI thread only prepares the pixel buffer and
receives the final string, so selecting a region stays responsive.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap


def _add_vendor_path() -> None:
    if not getattr(sys, "frozen", False):
        vendor = Path(__file__).resolve().parents[1] / "vendor"
        if str(vendor) not in sys.path:
            sys.path.insert(0, str(vendor))


class OcrWorker(QThread):
    text_ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        # Windows OCR's native 32-bit format is BGRA8; Qt's ARGB32 is BGRA
        # byte order on Windows and avoids an extra channel conversion.
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        self._width = image.width()
        self._height = image.height()
        self._pixels = image.constBits().asstring(image.sizeInBytes())

    def run(self) -> None:
        try:
            text = asyncio.run(self._recognize())
            self.text_ready.emit(text.strip())
        except Exception as exc:
            self.failed.emit(str(exc))

    async def _recognize(self) -> str:
        _add_vendor_path()
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter

        languages = list(OcrEngine.available_recognizer_languages)
        if not languages:
            raise RuntimeError(
                "Windows không có gói ngôn ngữ OCR phù hợp. "
                "Hãy cài Language pack có tính năng OCR trong Windows Settings."
            )

        results = []
        for language in languages:
            engine = OcrEngine.try_create_from_language(
                Language(language.language_tag)
            )
            if engine is None:
                continue
            bitmap = SoftwareBitmap(
                BitmapPixelFormat.BGRA8, self._width, self._height
            )
            writer = DataWriter()
            writer.write_bytes(self._pixels)
            bitmap.copy_from_buffer(writer.detach_buffer())
            result = await engine.recognize_async(bitmap)
            text = (result.text or "").strip()
            if text:
                results.append((language.language_tag, text))

        if not results:
            raise RuntimeError(
                "Không thể khởi tạo Windows OCR. "
                "Hãy kiểm tra lại các Language pack có tính năng OCR."
            )
        return self._select_result(results)

    @staticmethod
    def _select_result(results) -> str:
        """Prefer a result containing non-Latin script characters.

        The profile-language engine can silently choose the first installed
        language. Running each installed recognizer lets Japanese, Chinese,
        and Korean text work even when English is the default Windows language.
        For plain Latin text, preserve the first result (normally en-US).
        """
        scripted = [
            item for item in results
            if any(
                "\u3040" <= char <= "\u30ff"  # Hiragana/Katakana
                or "\u3400" <= char <= "\u9fff"  # CJK ideographs
                or "\uac00" <= char <= "\ud7af"  # Hangul
                for char in item[1]
            )
        ]
        if not scripted:
            language_tag, text = results[0]
        else:
            language_tag, text = max(
            scripted,
            key=lambda item: sum(
                "\u3040" <= char <= "\u30ff"
                or "\u3400" <= char <= "\u9fff"
                or "\uac00" <= char <= "\ud7af"
                for char in item[1]
            ),
            )
        if language_tag.casefold().startswith("ja"):
            return OcrWorker._normalize_japanese_text(text)
        return text

    @staticmethod
    def _normalize_japanese_text(text: str) -> str:
        """Remove OCR word gaps between Japanese glyphs without touching Latin."""
        japanese_punctuation = set(
            "、。！？：；「」『』【】〔〕〈〉《》・〜～…!?;:,()[]{}"
        )

        def is_japanese(char: str) -> bool:
            return (
                "\u3040" <= char <= "\u30ff"  # Hiragana/Katakana
                or "\u3400" <= char <= "\u9fff"  # CJK ideographs
                or "\uac00" <= char <= "\ud7af"  # Hangul, for mixed OCR
                or char in "々〆〇"
            )

        normalized = []
        index = 0
        while index < len(text):
            if text[index] not in " \t":
                normalized.append(text[index])
                index += 1
                continue

            end = index + 1
            while end < len(text) and text[end] in " \t":
                end += 1
            left = normalized[-1] if normalized else ""
            right = text[end] if end < len(text) else ""
            remove_gap = (
                (is_japanese(left) and (is_japanese(right) or right.isdigit()))
                or (left.isdigit() and is_japanese(right))
                or (is_japanese(left) and right in japanese_punctuation)
                or (left in japanese_punctuation and is_japanese(right))
                or (left in japanese_punctuation and right in japanese_punctuation)
            )
            if not remove_gap:
                normalized.extend(text[index:end])
            index = end
        return "".join(normalized)

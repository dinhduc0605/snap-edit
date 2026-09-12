"""Asynchronous Windows OCR worker with conservative Japanese preprocessing.

Windows.Media.Ocr is kept as the only recognition engine, so this feature does
not add a large model or a resident background process. The worker owns the
pixel copy and all image/OCR work, leaving the GUI thread responsive while a
region is recognized.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import sys
from typing import Iterable

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

from ocr.preprocess import OcrImageVariant, OcrPreprocessor


_LANGUAGE_AUTO = "auto"
_SUPPORTED_LANGUAGE_PREFERENCES = {_LANGUAGE_AUTO, "ja", "en"}


def _add_vendor_path() -> None:
    if not getattr(sys, "frozen", False):
        vendor = Path(__file__).resolve().parents[1] / "vendor"
        if str(vendor) not in sys.path:
            sys.path.insert(0, str(vendor))


@dataclass(frozen=True)
class OcrCandidate:
    """Text returned for one language/image-variant attempt."""

    language_tag: str
    variant_name: str
    text: str


@dataclass(frozen=True)
class OcrWord:
    """A recognized word and its rectangle in the original image pixels."""

    text: str
    x: float
    y: float
    width: float
    height: float
    line_index: int
    word_index: int


@dataclass(frozen=True)
class OcrLayout:
    """Recognized text plus word geometry for editor-side text selection."""

    language_tag: str
    text: str
    words: tuple[OcrWord, ...]


class OcrWorker(QThread):
    text_ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        pixmap: QPixmap,
        parent=None,
        *,
        language: str = _LANGUAGE_AUTO,
        preprocess: bool = True,
    ):
        super().__init__(parent)
        # Use explicit RGBA bytes while the pixmap is still on the GUI thread.
        # Pillow converts those bytes into BGRA only for the WinRT bitmap.
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        self._width = image.width()
        self._height = image.height()
        self._rgba_pixels = self._qimage_rgba_bytes(image)
        self._language_preference = self.normalize_language_preference(language)
        self._preprocess = preprocess

    @staticmethod
    def _qimage_rgba_bytes(image: QImage) -> bytes:
        """Copy rows without retaining a GUI-owned QImage buffer."""
        raw = image.constBits().asstring(image.sizeInBytes())
        row_size = image.width() * 4
        stride = image.bytesPerLine()
        if stride == row_size:
            return raw
        return b"".join(
            raw[row * stride: row * stride + row_size]
            for row in range(image.height())
        )

    @staticmethod
    def normalize_language_preference(value: object) -> str:
        """Coerce old/invalid config data to a safe recognition preference."""
        value = str(value or _LANGUAGE_AUTO).strip().casefold()
        if value.startswith("ja"):
            return "ja"
        if value.startswith("en"):
            return "en"
        return value if value in _SUPPORTED_LANGUAGE_PREFERENCES else _LANGUAGE_AUTO

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

        available_tags = [
            language.language_tag
            for language in OcrEngine.available_recognizer_languages
        ]
        if not available_tags:
            raise RuntimeError(
                "Windows không có gói ngôn ngữ OCR phù hợp. "
                "Hãy cài Language pack có tính năng OCR trong Windows Settings."
            )

        language_tags = self._select_language_tags(
            available_tags, self._language_preference
        )
        if not language_tags:
            raise RuntimeError(self._missing_language_message())

        max_dimension = int(
            getattr(OcrEngine, "max_image_dimension", 10_000) or 10_000
        )
        preprocessor = OcrPreprocessor(max_dimension)
        candidates: list[OcrCandidate] = []

        for language_tag in language_tags:
            engine = OcrEngine.try_create_from_language(Language(language_tag))
            if engine is None:
                continue
            try:
                # Extra candidates are opt-in through the Japanese setting.
                # Auto remains as quick as the prior one-pass implementation.
                variants = preprocessor.prepare(
                    self._width,
                    self._height,
                    self._rgba_pixels,
                    japanese_variants=(
                        self._preprocess
                        and self._language_preference == "ja"
                        and language_tag.casefold().startswith("ja")
                    ),
                )
                for variant in variants:
                    text = await self._recognize_variant(
                        engine,
                        variant,
                        BitmapPixelFormat,
                        SoftwareBitmap,
                        DataWriter,
                    )
                    if text:
                        candidates.append(
                            OcrCandidate(language_tag, variant.name, text)
                        )
            finally:
                self._close_winrt_object(engine)

        if not candidates:
            raise RuntimeError(
                "Không thể nhận diện chữ trong vùng đã chọn. "
                "Hãy thử chọn vùng rõ nét hơn."
            )
        return self._select_result(candidates, self._language_preference)

    @staticmethod
    async def _recognize_variant(
        engine,
        variant: OcrImageVariant,
        bitmap_pixel_format,
        software_bitmap_type,
        data_writer_type,
    ) -> str:
        """Recognize one candidate and promptly release its native buffers."""
        bitmap = None
        writer = None
        result = None
        try:
            bitmap = software_bitmap_type(
                bitmap_pixel_format.BGRA8, variant.width, variant.height
            )
            writer = data_writer_type()
            writer.write_bytes(variant.bgra_pixels)
            bitmap.copy_from_buffer(writer.detach_buffer())
            result = await engine.recognize_async(bitmap)
            return (result.text or "").strip()
        finally:
            OcrWorker._close_winrt_object(result)
            OcrWorker._close_winrt_object(writer)
            OcrWorker._close_winrt_object(bitmap)

    @staticmethod
    def _close_winrt_object(value) -> None:
        close = getattr(value, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                # The WinRT wrappers vary slightly by package version; cleanup
                # must never turn a successful OCR result into a failure.
                pass

    @classmethod
    def _select_language_tags(
        cls, available_tags: Iterable[str], preference: str
    ) -> list[str]:
        """Return installed engine tags matching the configured preference."""
        tags = list(dict.fromkeys(str(tag) for tag in available_tags))
        preference = cls.normalize_language_preference(preference)
        if preference == _LANGUAGE_AUTO:
            return tags
        return [tag for tag in tags if tag.casefold().startswith(preference)]

    def _missing_language_message(self) -> str:
        return self.missing_language_message(self._language_preference)

    @staticmethod
    def missing_language_message(language_preference: str) -> str:
        language_name = {"ja": "tiếng Nhật", "en": "tiếng Anh"}.get(
            OcrWorker.normalize_language_preference(language_preference), "đã chọn"
        )
        return (
            f"Windows chưa cài gói OCR {language_name}. "
            "Hãy vào Settings > Time & language > Language & region, "
            "cài language pack và bật tính năng OCR."
        )

    @classmethod
    def _select_result(
        cls,
        results: Iterable[OcrCandidate | tuple[str, str]],
        language_preference: str = _LANGUAGE_AUTO,
    ) -> str:
        """Choose the stable result without assuming an unavailable confidence API.

        Legacy Windows OCR exposes no per-word confidence. For Japanese mode
        we retain the source result and choose the text supported by the most
        similar image variants; exact agreement wins immediately.
        """
        candidates = cls._normalize_candidates(results)
        if not candidates:
            return ""

        preference = cls.normalize_language_preference(language_preference)
        scoped = candidates
        if preference == _LANGUAGE_AUTO:
            scripted = [
                candidate
                for candidate in candidates
                if cls._scripted_character_count(candidate.text)
            ]
            if scripted:
                chosen_tag = max(
                    scripted,
                    key=lambda candidate: cls._scripted_character_count(candidate.text),
                ).language_tag.casefold()
                scoped = [
                    candidate
                    for candidate in candidates
                    if candidate.language_tag.casefold() == chosen_tag
                ]
            else:
                first_tag = candidates[0].language_tag.casefold()
                scoped = [
                    candidate
                    for candidate in candidates
                    if candidate.language_tag.casefold() == first_tag
                ]

        return cls._choose_variant_result(scoped).text

    @classmethod
    def _normalize_candidates(
        cls, results: Iterable[OcrCandidate | tuple[str, str]]
    ) -> list[OcrCandidate]:
        candidates: list[OcrCandidate] = []
        for result in results:
            if isinstance(result, OcrCandidate):
                language_tag, variant_name, text = (
                    result.language_tag,
                    result.variant_name,
                    result.text,
                )
            else:
                language_tag, text = result
                variant_name = "source"
            text = cls._normalize_text_for_language(language_tag, text)
            if text:
                candidates.append(OcrCandidate(language_tag, variant_name, text))
        return candidates

    @classmethod
    def _normalize_text_for_language(cls, language_tag: str, text: object) -> str:
        text = str(text or "").strip()
        if language_tag.casefold().startswith("ja"):
            return cls._normalize_japanese_text(text)
        return text

    @classmethod
    def _choose_variant_result(cls, candidates: list[OcrCandidate]) -> OcrCandidate:
        agreement = Counter(candidate.text for candidate in candidates)
        most_agreed = max(agreement.values())
        if most_agreed > 1:
            agreed_text = next(
                text for text, count in agreement.items() if count == most_agreed
            )
            return next(candidate for candidate in candidates if candidate.text == agreed_text)

        if len(candidates) == 1:
            return candidates[0]

        def score(candidate: OcrCandidate) -> tuple[float, float, int]:
            similarity = sum(
                cls._text_similarity(candidate.text, other.text)
                for other in candidates
                if other is not candidate
            ) / (len(candidates) - 1)
            # Preserve source as a deterministic last tiebreaker. It is the
            # unmodified screenshot and avoids a preprocessing artifact
            # winning when the engine gives no usable confidence signal.
            source_priority = 1 if candidate.variant_name == "source" else 0
            return (similarity, cls._text_quality(candidate.text), source_priority)

        return max(candidates, key=score)

    @staticmethod
    def _text_similarity(left: str, right: str) -> float:
        # Crops are normally short. Cap comparison length so a huge selection
        # cannot make variant selection disproportionately expensive.
        return SequenceMatcher(None, left[:2_048], right[:2_048], autojunk=False).ratio()

    @classmethod
    def _text_quality(cls, text: str) -> float:
        visible = [char for char in text if not char.isspace()]
        if not visible:
            return -10.0
        replacements = sum(char == "\ufffd" for char in visible)
        controls = sum(not char.isprintable() for char in visible)
        scripted_ratio = cls._scripted_character_count(text) / len(visible)
        return min(len(visible), 240) / 240 + scripted_ratio - replacements - controls

    @staticmethod
    def _scripted_character_count(text: str) -> int:
        return sum(
            "\u3040" <= char <= "\u30ff"  # Hiragana/Katakana
            or "\u3400" <= char <= "\u9fff"  # CJK ideographs
            or "\uac00" <= char <= "\ud7af"  # Hangul
            for char in text
        )

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


class OcrLayoutWorker(QThread):
    """Read word rectangles from Windows OCR for selectable editor text.

    Japanese mode uses the same lightweight source/padded/enhanced candidates
    as region OCR. Each candidate records its coordinate transform, so words
    still highlight their true positions on the original screenshot.
    """

    layout_ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        pixmap: QPixmap,
        parent=None,
        *,
        language: str = _LANGUAGE_AUTO,
        preprocess: bool = True,
    ):
        super().__init__(parent)
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        self._width = image.width()
        self._height = image.height()
        self._rgba_pixels = OcrWorker._qimage_rgba_bytes(image)
        self._language_preference = OcrWorker.normalize_language_preference(language)
        self._preprocess = preprocess

    def run(self) -> None:
        try:
            layout = asyncio.run(self._recognize())
            if layout is not None and not self.isInterruptionRequested():
                self.layout_ready.emit(layout)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))

    async def _recognize(self) -> OcrLayout | None:
        _add_vendor_path()
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter

        available_tags = [
            language.language_tag
            for language in OcrEngine.available_recognizer_languages
        ]
        if not available_tags:
            raise RuntimeError(
                "Windows không có gói ngôn ngữ OCR phù hợp. "
                "Hãy cài Language pack có tính năng OCR trong Windows Settings."
            )
        language_tags = OcrWorker._select_language_tags(
            available_tags, self._language_preference
        )
        if not language_tags:
            raise RuntimeError(
                OcrWorker.missing_language_message(self._language_preference)
            )

        max_dimension = int(
            getattr(OcrEngine, "max_image_dimension", 10_000) or 10_000
        )
        preprocessor = OcrPreprocessor(max_dimension)
        layouts: list[OcrLayout] = []
        for language_tag in language_tags:
            if self.isInterruptionRequested():
                return None
            engine = OcrEngine.try_create_from_language(Language(language_tag))
            if engine is None:
                continue
            try:
                variants = preprocessor.prepare(
                    self._width,
                    self._height,
                    self._rgba_pixels,
                    japanese_variants=(
                        self._preprocess
                        and self._language_preference == "ja"
                        and language_tag.casefold().startswith("ja")
                    ),
                )
                for variant in variants:
                    if self.isInterruptionRequested():
                        return None
                    layout = await self._recognize_layout_variant(
                        engine,
                        variant,
                        language_tag,
                        BitmapPixelFormat,
                        SoftwareBitmap,
                        DataWriter,
                    )
                    if layout.text and layout.words:
                        layouts.append(layout)
            finally:
                OcrWorker._close_winrt_object(engine)

        if self.isInterruptionRequested():
            return None
        if not layouts:
            raise RuntimeError(
                "Không thể nhận diện chữ trong ảnh này. "
                "Hãy thử dùng ảnh rõ nét hơn."
            )

        selected_text = OcrWorker._select_result(
            [OcrCandidate(layout.language_tag, "source", layout.text)
             for layout in layouts],
            self._language_preference,
        )
        for layout in layouts:
            if layout.text == selected_text:
                return layout
        return layouts[0]

    async def _recognize_layout_variant(
        self,
        engine,
        variant: OcrImageVariant,
        language_tag: str,
        bitmap_pixel_format,
        software_bitmap_type,
        data_writer_type,
    ) -> OcrLayout:
        bitmap = None
        writer = None
        result = None
        try:
            bitmap = software_bitmap_type(
                bitmap_pixel_format.BGRA8, variant.width, variant.height
            )
            writer = data_writer_type()
            writer.write_bytes(variant.bgra_pixels)
            bitmap.copy_from_buffer(writer.detach_buffer())
            result = await engine.recognize_async(bitmap)
            return self._layout_from_result(result, language_tag, variant)
        finally:
            OcrWorker._close_winrt_object(result)
            OcrWorker._close_winrt_object(writer)
            OcrWorker._close_winrt_object(bitmap)

    def _layout_from_result(
        self, result, language_tag: str, variant: OcrImageVariant
    ) -> OcrLayout:
        """Convert WinRT word rectangles back to original screenshot pixels."""
        words: list[OcrWord] = []
        lines = list(result.lines or [])
        for line_index, line in enumerate(lines):
            for word_index, word in enumerate(line.words or []):
                text = str(word.text or "").strip()
                bounds = word.bounding_rect
                if not text or bounds is None:
                    continue
                left = max(0.0, min(
                    (float(bounds.x) - variant.source_offset_x)
                    * variant.source_scale_x,
                    self._width,
                ))
                top = max(0.0, min(
                    (float(bounds.y) - variant.source_offset_y)
                    * variant.source_scale_y,
                    self._height,
                ))
                right = max(left, min(
                    (float(bounds.x) + float(bounds.width) - variant.source_offset_x)
                    * variant.source_scale_x,
                    self._width,
                ))
                bottom = max(top, min(
                    (float(bounds.y) + float(bounds.height) - variant.source_offset_y)
                    * variant.source_scale_y,
                    self._height,
                ))
                if right <= left or bottom <= top:
                    continue
                words.append(OcrWord(
                    text=text,
                    x=left,
                    y=top,
                    width=right - left,
                    height=bottom - top,
                    line_index=line_index,
                    word_index=word_index,
                ))

        raw_text = str(result.text or "")
        if not raw_text:
            raw_text = "\n".join(str(line.text or "") for line in lines)
        return OcrLayout(
            language_tag=language_tag,
            text=OcrWorker._normalize_text_for_language(language_tag, raw_text),
            words=tuple(words),
        )

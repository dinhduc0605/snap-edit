"""Small, deterministic image variants for Windows OCR.

The Windows OCR API does not expose a preprocessing pipeline.  This module
keeps that work local and dependency-light (Pillow is already required by the
app), while retaining the untouched source image as a safe fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from PIL import Image, ImageFilter, ImageOps, ImageStat


@dataclass(frozen=True)
class OcrImageVariant:
    """One BGRA image plus its mapping back to source-image coordinates.

    A word rectangle ``(x, y)`` returned for this variant maps to the original
    image as ``(x - source_offset_x) * source_scale_x`` (and likewise for
    ``y``). Keeping this alongside the pixels lets the editor use the same
    high-accuracy variants as region OCR without losing highlight positions.
    """

    name: str
    width: int
    height: int
    bgra_pixels: bytes
    source_scale_x: float = 1.0
    source_scale_y: float = 1.0
    source_offset_x: float = 0.0
    source_offset_y: float = 0.0


class OcrPreprocessor:
    """Create conservative OCR candidates for small Japanese text.

    Japanese glyphs often lose their small strokes in a screen crop.  The
    extra candidates add a background-coloured border, enlarge narrow crops,
    and use grayscale contrast plus a mild unsharp mask.  We deliberately do
    not binarize: hard thresholding tends to erase thin kana and anti-aliased
    UI fonts.
    """

    _TARGET_SHORT_EDGE = 420
    _MAX_UPSCALE = 3.0

    def __init__(self, max_image_dimension: int):
        self._max_image_dimension = max(1, int(max_image_dimension))

    def prepare(
        self,
        width: int,
        height: int,
        rgba_pixels: bytes,
        *,
        japanese_variants: bool,
    ) -> list[OcrImageVariant]:
        """Return source plus optional Japanese-oriented image variants.

        ``rgba_pixels`` is intentionally an immutable byte copy made in the
        GUI thread.  Pillow processing then happens only in the OCR worker.
        """
        if width <= 0 or height <= 0:
            raise ValueError("OCR image must have a positive size")
        expected_size = width * height * 4
        if len(rgba_pixels) != expected_size:
            raise ValueError("OCR image buffer has an unexpected size")

        source = Image.frombytes("RGBA", (width, height), rgba_pixels, "raw", "RGBA")
        original = self._fit_to_limit(source)
        variants = [self._to_variant(
            "source",
            original,
            source_scale_x=source.width / original.width,
            source_scale_y=source.height / original.height,
        )]

        if not japanese_variants:
            return variants

        scaled = self._upscale_for_small_text(source)
        prepared = self._add_border(scaled)
        source_scale_x = source.width / scaled.width
        source_scale_y = source.height / scaled.height
        source_offset_x = (prepared.width - scaled.width) / 2
        source_offset_y = (prepared.height - scaled.height) / 2
        variants.append(self._to_variant(
            "padded",
            prepared,
            source_scale_x=source_scale_x,
            source_scale_y=source_scale_y,
            source_offset_x=source_offset_x,
            source_offset_y=source_offset_y,
        ))

        enhanced = self._enhance_for_text(prepared)
        variants.append(self._to_variant(
            "enhanced",
            enhanced,
            source_scale_x=source_scale_x,
            source_scale_y=source_scale_y,
            source_offset_x=source_offset_x,
            source_offset_y=source_offset_y,
        ))
        return variants

    def _fit_to_limit(self, image: Image.Image) -> Image.Image:
        """Downscale only when Windows OCR's maximum dimension requires it."""
        largest_side = max(image.size)
        if largest_side <= self._max_image_dimension:
            return image.copy()
        scale = self._max_image_dimension / largest_side
        return self._resize(image, scale)

    def _upscale_for_small_text(self, image: Image.Image) -> Image.Image:
        """Upscale a thin horizontal/vertical selection without exceeding OCR limits."""
        short_side = max(1, min(image.size))
        desired_scale = min(
            self._MAX_UPSCALE,
            max(1.0, self._TARGET_SHORT_EDGE / short_side),
        )

        # Reserve enough room for a border after the resize.  The approximate
        # 48 pixels matches the largest border (24 px on both sides).
        max_scale = self._max_image_dimension / (max(image.size) + 48)
        scale = min(desired_scale, max_scale)
        if scale <= 0:
            scale = 1.0
        return self._resize(image, scale)

    @staticmethod
    def _resize(image: Image.Image, scale: float) -> Image.Image:
        if abs(scale - 1.0) < 0.001:
            return image.copy()
        width = max(1, round(image.width * scale))
        height = max(1, round(image.height * scale))
        return image.resize((width, height), Image.Resampling.LANCZOS)

    def _add_border(self, image: Image.Image) -> Image.Image:
        """Add a modest border whose colour blends with the crop corners."""
        scale = max(image.size) / max(1, self._max_image_dimension)
        # In the usual case this is 12 px; retain a visible but bounded edge
        # when source images are close to the OCR dimension limit.
        border = max(8, min(24, round(12 + 12 * scale)))
        available = max(0, (self._max_image_dimension - max(image.size)) // 2)
        border = min(border, available)
        if border <= 0:
            return image.copy()
        return ImageOps.expand(image, border=border, fill=self._corner_colour(image))

    @staticmethod
    def _corner_colour(image: Image.Image) -> tuple[int, int, int, int]:
        """Use the median corner colour instead of assuming a white background."""
        width, height = image.size
        points = (
            image.getpixel((0, 0)),
            image.getpixel((width - 1, 0)),
            image.getpixel((0, height - 1)),
            image.getpixel((width - 1, height - 1)),
        )
        return tuple(int(median(pixel[channel] for pixel in points)) for channel in range(4))

    @staticmethod
    def _enhance_for_text(image: Image.Image) -> Image.Image:
        """Improve thin, low-contrast glyph strokes without a hard threshold."""
        grayscale = ImageOps.grayscale(image)
        grayscale = ImageOps.autocontrast(grayscale, cutoff=1)
        # Windows UI can contain light text on a dark surface.  OCR is more
        # reliable with dark glyphs on a light background, so normalize that
        # candidate while retaining the original and padded variants above.
        if ImageStat.Stat(grayscale).mean[0] < 112:
            grayscale = ImageOps.invert(grayscale)
        grayscale = grayscale.filter(
            ImageFilter.UnsharpMask(radius=1.1, percent=125, threshold=2)
        )
        return grayscale.convert("RGBA")

    @staticmethod
    def _to_variant(
        name: str,
        image: Image.Image,
        *,
        source_scale_x: float = 1.0,
        source_scale_y: float = 1.0,
        source_offset_x: float = 0.0,
        source_offset_y: float = 0.0,
    ) -> OcrImageVariant:
        rgba = image.convert("RGBA")
        return OcrImageVariant(
            name=name,
            width=rgba.width,
            height=rgba.height,
            bgra_pixels=rgba.tobytes("raw", "BGRA"),
            source_scale_x=source_scale_x,
            source_scale_y=source_scale_y,
            source_offset_x=source_offset_x,
            source_offset_y=source_offset_y,
        )

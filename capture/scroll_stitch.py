"""Vertical overlap matching and bounded, disk-backed screenshot assembly."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image


MAX_PIXELS = 24_000_000  # ~96 MB RGBA; allow room for editor/export copies.
MAX_HEIGHT = 30_000


class StitchError(ValueError):
    pass


@dataclass(frozen=True)
class Match:
    shift: int
    top: int = 0
    bottom: int = 0


def gray(frame):
    """Build a compact grayscale signature without skipping thin strokes."""
    width = frame.shape[1]
    left, right = width // 20, width - width // 20
    bins = min(96, max(1, right - left))
    edges = np.linspace(left, right, bins + 1).astype(int)
    signature = np.empty((frame.shape[0], bins), dtype=np.float32)
    for index in range(bins):
        strip = frame[:, edges[index]:max(edges[index] + 1, edges[index + 1]), :3]
        signature[:, index] = strip.mean(axis=(1, 2))
    return signature


def difference(a, b):
    """Ignore small animated areas, but never treat a large change as stable."""
    delta = np.abs(a - b)
    broad_change = float(np.quantile(delta, 0.90))
    changed_fraction = float(np.mean(delta > 10))
    # Sparse documents can have text on less than 10% of their pixels. The
    # fraction term catches that movement while ignoring a blinking caret or
    # similarly tiny animation.
    return max(broad_change, changed_fraction * 512)


def _fixed_edges(a, b):
    same = np.mean(np.abs(a - b), axis=1) < 1.5
    texture = np.std(a, axis=1) > 8
    limit = len(a) // 4
    def edge(rows, textured):
        count = 0
        for flag in rows[:limit]:
            if not flag:
                break
            count += 1
        # Do not mistake a blank margin for an independently fixed header.
        return count if count and np.count_nonzero(textured[:count]) >= 4 else 0
    return edge(same, texture), edge(same[::-1], texture[::-1])


def match_vertical(previous, current, margins=None):
    """Find a unique downward displacement; refuse ambiguous/missing overlap."""
    if previous.shape != current.shape:
        raise StitchError("Capture size changed.")
    a, b = gray(previous), gray(current)
    if difference(a, b) < 2:
        return Match(0, *(margins or (0, 0)))
    top, bottom = margins if margins is not None else _fixed_edges(a, b)
    end = len(a) - bottom
    a, b = a[top:end], b[top:end]
    h = len(a)
    if h < 32:
        raise StitchError("Select a taller scrolling region.")
    max_shift = int(h * 0.70)
    stride = max(1, h // 350)

    def score(shift, step):
        aa, bb = a[shift::step], b[:h-shift:step]
        rows = np.std(aa, axis=1) > 6
        if np.count_nonzero(rows) < min(8, max(3, len(aa) // 5)):
            return float("inf")
        error = np.mean(np.abs(aa[rows] - bb[rows]), axis=1)
        # Local animations may spoil a few rows, never most of the overlap.
        return float(np.mean(np.sort(error)[:max(1, int(len(error) * .85))]))

    candidates = [(score(d, stride), d) for d in range(1, max_shift + 1, stride)]
    candidates.sort()
    best_score, best = candidates[0]
    refined = [(score(d, 1), d) for d in range(max(1, best-stride), min(max_shift, best+stride)+1)]
    best_score, best = min(refined)
    if not np.isfinite(best_score) or best_score > 7:
        raise StitchError("Cannot align the next frame. Try a taller region or slower scrolling.")
    rivals = [s for s, d in candidates if abs(d-best) > max(4, stride * 2)]
    if rivals and min(rivals) <= best_score + 1.2:
        raise StitchError("Repeated or blank content makes the overlap ambiguous.")
    return Match(best, top, bottom)


class StripStore:
    """Store each new strip once; assemble only after capture stops."""
    def __init__(self, width, max_pixels=MAX_PIXELS, max_height=MAX_HEIGHT):
        self.width = width
        self.height = 0
        self.max_height = min(max_height, max_pixels // width)
        self._temp = TemporaryDirectory(prefix="snapedit-scroll-")
        self.paths = []

    def append(self, rgb):
        if not len(rgb):
            return
        if rgb.shape[1] != self.width or self.height + len(rgb) > self.max_height:
            raise StitchError("Image size limit reached; keeping the captured portion.")
        path = Path(self._temp.name) / f"{len(self.paths):04d}.png"
        Image.fromarray(np.ascontiguousarray(rgb)).save(path)
        self.paths.append(path)
        self.height += len(rgb)

    def assemble(self):
        image = Image.new("RGB", (self.width, self.height))
        y = 0
        try:
            for path in self.paths:
                with Image.open(path) as strip:
                    image.paste(strip, (0, y))
                    y += strip.height
            return image
        except Exception:
            image.close()
            raise

    def close(self):
        self.paths.clear()
        self._temp.cleanup()

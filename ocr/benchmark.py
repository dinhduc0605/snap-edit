"""Repeatable, local OCR benchmark for Japanese screen crops.

Usage:
    python -m ocr.benchmark path\\to\\japanese_manifest.json

The manifest stays local by default so real screen contents do not need to be
committed.  Each case is run once without preprocessing and once with the
current pipeline, then character error rate (CER) and elapsed time are printed
as JSON for an apples-to-apples comparison.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import fmean
import sys
import time
import unicodedata

from PyQt6.QtCore import QEventLoop
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from ocr.worker import OcrWorker


@dataclass(frozen=True)
class OcrMeasurement:
    name: str
    expected: str
    actual: str
    cer: float
    elapsed_ms: float


def normalize_for_comparison(text: str, language: str) -> str:
    """Apply the same harmless text normalization to expected and actual."""
    normalized = unicodedata.normalize("NFC", str(text or "")).strip()
    if OcrWorker.normalize_language_preference(language) == "ja":
        return OcrWorker._normalize_japanese_text(normalized)
    return normalized


def levenshtein_distance(expected: str, actual: str) -> int:
    """Memory-bounded edit distance for Unicode text."""
    if len(expected) < len(actual):
        expected, actual = actual, expected
    previous = list(range(len(actual) + 1))
    for expected_index, expected_char in enumerate(expected, start=1):
        current = [expected_index]
        for actual_index, actual_char in enumerate(actual, start=1):
            replace_cost = 0 if expected_char == actual_char else 1
            current.append(
                min(
                    current[-1] + 1,
                    previous[actual_index] + 1,
                    previous[actual_index - 1] + replace_cost,
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(expected: str, actual: str) -> float:
    """Return CER; insertions against an empty expected string may exceed 1."""
    return levenshtein_distance(expected, actual) / max(1, len(expected))


def make_measurement(
    name: str,
    expected: str,
    actual: str,
    elapsed_ms: float,
    language: str,
) -> OcrMeasurement:
    expected = normalize_for_comparison(expected, language)
    actual = normalize_for_comparison(actual, language)
    return OcrMeasurement(
        name=name,
        expected=expected,
        actual=actual,
        cer=character_error_rate(expected, actual),
        elapsed_ms=round(elapsed_ms, 1),
    )


def summarize(measurements: list[OcrMeasurement]) -> dict[str, float | int]:
    if not measurements:
        return {"cases": 0, "mean_cer": 0.0, "mean_elapsed_ms": 0.0}
    return {
        "cases": len(measurements),
        "mean_cer": round(fmean(item.cer for item in measurements), 4),
        "mean_elapsed_ms": round(fmean(item.elapsed_ms for item in measurements), 1),
    }


def _recognize_once(
    app: QApplication,
    image_path: Path,
    language: str,
    *,
    preprocess: bool,
) -> tuple[str, float]:
    pixmap = QPixmap(str(image_path))
    if pixmap.isNull():
        raise RuntimeError(f"Cannot load OCR benchmark image: {image_path}")

    output: list[str] = []
    errors: list[str] = []
    loop = QEventLoop()
    worker = OcrWorker(pixmap, language=language, preprocess=preprocess)
    worker.text_ready.connect(output.append)
    worker.failed.connect(errors.append)
    worker.finished.connect(loop.quit)

    started = time.perf_counter()
    worker.start()
    loop.exec()
    elapsed_ms = (time.perf_counter() - started) * 1_000
    worker.wait()
    worker.deleteLater()

    if errors:
        raise RuntimeError(errors[0])
    return (output[0] if output else ""), elapsed_ms


def run_manifest(manifest_path: Path) -> dict:
    """Run baseline/current OCR against the JSON manifest at ``manifest_path``."""
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    language = OcrWorker.normalize_language_preference(
        manifest.get("language", "ja")
    )
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Benchmark manifest needs a non-empty 'cases' list")

    app = QApplication.instance() or QApplication(sys.argv[:1])
    baseline: list[OcrMeasurement] = []
    current: list[OcrMeasurement] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"Benchmark case {index} must be an object")
        try:
            image_name = case["image"]
            expected = case["expected"]
        except KeyError as exc:
            raise ValueError(
                f"Benchmark case {index} is missing {exc.args[0]!r}"
            ) from exc
        name = str(case.get("name", image_name))
        image_path = (manifest_path.parent / image_name).resolve()

        text, elapsed_ms = _recognize_once(
            app, image_path, language, preprocess=False
        )
        baseline.append(
            make_measurement(name, expected, text, elapsed_ms, language)
        )

        text, elapsed_ms = _recognize_once(
            app, image_path, language, preprocess=True
        )
        current.append(
            make_measurement(name, expected, text, elapsed_ms, language)
        )

    return {
        "language": language,
        "baseline": {
            "summary": summarize(baseline),
            "cases": [asdict(item) for item in baseline],
        },
        "current": {
            "summary": summarize(current),
            "cases": [asdict(item) for item in current],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to an OCR JSON manifest")
    args = parser.parse_args()
    print(json.dumps(run_manifest(args.manifest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

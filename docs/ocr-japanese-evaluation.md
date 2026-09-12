# Japanese OCR measurement and tuning

SnapEdit continues to use the Windows OCR language packs already installed on
the PC. It does not download a model or keep another OCR process in memory.

When **Settings → General → Text OCR → Recognition language** is set to
**Japanese**, both region Text OCR and editor Text OCR send three compact
candidates to the Japanese Windows recognizer:

1. The unchanged selected pixels, as a safe fallback.
2. A crop with a background-coloured border and a limited upscale for small
   text.
3. The same crop with grayscale auto-contrast and a mild unsharp mask.

If variants agree, that text wins. If they differ, SnapEdit chooses the most
similar result and retains the untouched crop as the deterministic tiebreaker.
For editor OCR, the word rectangles from enlarged/padded candidates are mapped
back to the original screenshot before highlighting, so stronger recognition
does not shift the selectable text. This is deliberately conservative because
the legacy Windows OCR API exposes no confidence score.

## Establish a local baseline

Do this on the same Windows user account and display scale used for normal
captures.

1. Copy `tests/fixtures/ocr/japanese_manifest.example.json` outside the
   repository, then replace the sample case with 20–50 representative screen
   crops and their exact expected text. Keep sensitive captures local.
2. For each crop, make sure the `image` field is relative to the manifest and
   `expected` is the text a person sees, including intentional line breaks.
3. Run:

   ```powershell
   cd C:\Users\dinhd\Projects\snap-edit
   python -m ocr.benchmark C:\path\to\japanese_manifest.json
   ```

The JSON output reports the old one-pass `baseline` and the new `current`
pipeline, with mean character error rate (`mean_cer`) and elapsed OCR time.
Lower CER is better. Review individual cases as well: a lower average is not
acceptable if a common UI font or dark surface regresses.

## Acceptance targets for this phase

- The Japanese language pack with its OCR feature must be installed in
  Windows; SnapEdit now gives a specific error when it is not.
- Japanese mode should not increase the measured mean CER on the local crop
  set, and should improve the small-text/dark-background cases that motivated
  this work.
- Auto and English still take one image pass per installed recognizer, so the
  regular OCR path keeps the former latency profile.
- No model files, web services, or background OCR daemon are added.

If the benchmark still shows frequent character substitutions after this
phase, the next decision is whether an optional higher-accuracy backend is
worth its disk/RAM/installation cost. That is intentionally outside this
lightweight implementation.

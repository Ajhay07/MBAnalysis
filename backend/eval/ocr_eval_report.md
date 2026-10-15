# OCR Evaluation Report

Measured with REAL (unmocked) local PaddleOCR inference against SYNTHETIC fixtures only (see `ocr_dataset/synthetic/`). No real/manually-annotated engineering drawings exist yet - these numbers say nothing about accuracy on real production drawings.

## Summary by preprocessing configuration

| Configuration | Avg CER | Avg WER | Avg critical-field exact-match | Fixtures |
|---|---|---|---|---|
| deskew_off_clahe_on | 0.1173 | 0.3274 | 0.5833 | 6 |
| deskew_on_clahe_on | 0.5395 | 0.7940 | 0.5278 | 6 |
| deskew_off_clahe_off | 0.1135 | 0.2996 | 0.5833 | 6 |

The repo default is `OCR_PREPROCESS_DESKEW=False, OCR_PREPROCESS_CLAHE=True` (`deskew_off_clahe_on` above), based on a prior empirical finding that the minAreaRect-based deskew estimate can rotate already-straight text and hurt recognition. Compare its row above against `deskew_on_clahe_on` to see whether these new fixtures confirm or contradict that.

## Per-fixture detail

| Config | Fixture | Page | CER | WER | Critical fields hit | Regions | Time (s) |
|---|---|---|---|---|---|---|---|
| deskew_off_clahe_on | fixture_01_titleblock_dimensions | 1 | 0.0324 | 0.0714 | drawing_number=OK, dimension=OK, tolerance=MISS, diameter=MISS | 7 | 3.46 |
| deskew_off_clahe_on | fixture_02_bom_table | 1 | 0.3938 | 0.0000 | part_number=OK, dimension=OK, quantity=OK | 20 | 0.88 |
| deskew_off_clahe_on | fixture_03_small_text_dense | 1 | 0.0805 | 0.6429 | drawing_number=OK, dimension=MISS, tolerance=MISS | 8 | 0.69 |
| deskew_off_clahe_on | fixture_04_multipage | 1 | 0.0000 | 0.0000 | drawing_number=OK | 2 | 0.37 |
| deskew_off_clahe_on | fixture_04_multipage | 2 | 0.0345 | 0.2500 | dimension=OK, diameter=MISS, tolerance=MISS | 3 | 0.59 |
| deskew_off_clahe_on | fixture_05_rotated_text | 1 | 0.1628 | 1.0000 | drawing_number=OK, diameter=MISS, tolerance=MISS | 1 | 0.62 |
| deskew_on_clahe_on | fixture_01_titleblock_dimensions | 1 | 0.0324 | 0.0714 | drawing_number=OK, dimension=OK, tolerance=MISS, diameter=MISS | 7 | 0.72 |
| deskew_on_clahe_on | fixture_02_bom_table | 1 | 0.8108 | 0.8710 | part_number=MISS, dimension=OK, quantity=OK | 11 | 0.6 |
| deskew_on_clahe_on | fixture_03_small_text_dense | 1 | 0.7356 | 0.9048 | drawing_number=OK, dimension=MISS, tolerance=MISS | 8 | 0.59 |
| deskew_on_clahe_on | fixture_04_multipage | 1 | 0.8519 | 1.0000 | drawing_number=OK | 2 | 0.54 |
| deskew_on_clahe_on | fixture_04_multipage | 2 | 0.6437 | 0.9167 | dimension=OK, diameter=MISS, tolerance=MISS | 3 | 0.62 |
| deskew_on_clahe_on | fixture_05_rotated_text | 1 | 0.1628 | 1.0000 | drawing_number=OK, diameter=MISS, tolerance=MISS | 1 | 0.42 |
| deskew_off_clahe_off | fixture_01_titleblock_dimensions | 1 | 0.0324 | 0.0714 | drawing_number=OK, dimension=OK, tolerance=MISS, diameter=MISS | 7 | 0.78 |
| deskew_off_clahe_off | fixture_02_bom_table | 1 | 0.3938 | 0.0000 | part_number=OK, dimension=OK, quantity=OK | 20 | 0.78 |
| deskew_off_clahe_off | fixture_03_small_text_dense | 1 | 0.0805 | 0.6429 | drawing_number=OK, dimension=MISS, tolerance=MISS | 8 | 0.86 |
| deskew_off_clahe_off | fixture_04_multipage | 1 | 0.0000 | 0.0000 | drawing_number=OK | 2 | 0.35 |
| deskew_off_clahe_off | fixture_04_multipage | 2 | 0.0345 | 0.2500 | dimension=OK, diameter=MISS, tolerance=MISS | 3 | 0.5 |
| deskew_off_clahe_off | fixture_05_rotated_text | 1 | 0.1395 | 0.8333 | drawing_number=OK, diameter=MISS, tolerance=MISS | 1 | 0.4 |

## Known failure modes observed

- `fixture_01_titleblock_dimensions` page 1: critical field `tolerance` was NOT recognized exactly (default config). Likely culprits for this field type: ±/decimal-point character dropped or substituted
- `fixture_01_titleblock_dimensions` page 1: critical field `diameter` was NOT recognized exactly (default config). Likely culprits for this field type: diameter symbol (⌀) misread or dropped
- `fixture_03_small_text_dense` page 1: critical field `dimension` was NOT recognized exactly (default config). Likely culprits for this field type: ±/decimal-point character dropped or substituted
- `fixture_03_small_text_dense` page 1: critical field `tolerance` was NOT recognized exactly (default config). Likely culprits for this field type: ±/decimal-point character dropped or substituted
- `fixture_04_multipage` page 2: critical field `diameter` was NOT recognized exactly (default config). Likely culprits for this field type: diameter symbol (⌀) misread or dropped
- `fixture_04_multipage` page 2: critical field `tolerance` was NOT recognized exactly (default config). Likely culprits for this field type: ±/decimal-point character dropped or substituted
- `fixture_05_rotated_text` page 1: critical field `diameter` was NOT recognized exactly (default config). Likely culprits for this field type: diameter symbol (⌀) misread or dropped
- `fixture_05_rotated_text` page 1: critical field `tolerance` was NOT recognized exactly (default config). Likely culprits for this field type: ±/decimal-point character dropped or substituted

Known general risk areas for this OCR stack on engineering drawings (even where not hit by the current fixture set): decimal points dropped/merged into neighboring digits, the diameter symbol (⌀) and plus/minus (±) glyphs are uncommon in most OCR training data and are the most error-prone single characters, and very small (<14pt-equivalent) dense note text has a higher per-character error rate than title-block-sized text.

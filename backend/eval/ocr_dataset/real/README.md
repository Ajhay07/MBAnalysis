# Real-drawing OCR eval fixtures (empty placeholder)

This folder is for **manually-annotated real engineering drawings** (scanned/photographed,
not synthetically generated). None exist yet as of this writing — no real customer or
production drawings have been collected/annotated for OCR evaluation.

When real drawings become available, add them here following the same convention as
`../synthetic/`:

- `<name>.png` or `<name>.pdf` — the drawing image/file.
- `<name>.json` — ground truth: `{"full_text": "...", "critical_fields": {"drawing_number": "...",
  "dimension": "...", "tolerance": "..."}, "notes": "..."}`.

Do **not** mirror synthetic fixtures into this folder and do not label synthetic fixtures as
"real" — `run_ocr_eval.py` reports synthetic and real results separately so accuracy numbers on
generated test images are never confused with accuracy on actual production drawings.

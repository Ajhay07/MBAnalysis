"""OCR evaluation harness: runs the real PaddleOCR adapter against synthetic fixtures and
reports Character Error Rate (CER), Word Error Rate (WER), and exact-match accuracy on
"critical fields" (drawing number / dimension / tolerance / diameter substrings each fixture's
ground-truth JSON designates), across preprocessing configurations (deskew on/off, CLAHE
on/off).

Usage:
    cd backend && python -I eval/run_ocr_eval.py

Writes eval/ocr_eval_report.md. Uses REAL (unmocked) PaddleOCR inference - this is slow
(several seconds per fixture per configuration) because it is doing genuine CPU inference, not
testing against mocks.

IMPORTANT: these numbers are measured ONLY on synthetic, generator-rendered fixtures in
ocr_dataset/synthetic/. They say nothing about accuracy on real engineering drawings (scans,
photographs, CAD-exported PDFs with genuine noise/wear/handwriting) - no such fixtures exist
yet (see ocr_dataset/real/README.md).
"""
from __future__ import annotations

import json
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

HERE = os.path.dirname(os.path.abspath(__file__))
SYNTH_DIR = os.path.join(HERE, "ocr_dataset", "synthetic")
REPORT_PATH = os.path.join(HERE, "ocr_eval_report.md")

CONFIGS = [
    {"name": "deskew_off_clahe_on", "OCR_PREPROCESS_DESKEW": False, "OCR_PREPROCESS_CLAHE": True},
    {"name": "deskew_on_clahe_on", "OCR_PREPROCESS_DESKEW": True, "OCR_PREPROCESS_CLAHE": True},
    {"name": "deskew_off_clahe_off", "OCR_PREPROCESS_DESKEW": False, "OCR_PREPROCESS_CLAHE": False},
]


def _levenshtein(a: list, b: list) -> int:
    """Standard edit distance over a sequence of hashable tokens (chars or words)."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    ref_chars = list(ref)
    if not ref_chars:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref_chars, list(hyp)) / len(ref_chars)


def wer(ref: str, hyp: str) -> float:
    ref_words = ref.split()
    if not ref_words:
        return 0.0 if not hyp.split() else 1.0
    return _levenshtein(ref_words, hyp.split()) / len(ref_words)


def load_fixtures():
    fixtures = []
    for fn in sorted(os.listdir(SYNTH_DIR)):
        if not fn.endswith(".json"):
            continue
        stem = fn[: -len(".json")]
        gt_path = os.path.join(SYNTH_DIR, fn)
        with open(gt_path, "r", encoding="utf-8") as fh:
            gt = json.load(fh)
        for ext in (".png", ".pdf"):
            data_path = os.path.join(SYNTH_DIR, stem + ext)
            if os.path.exists(data_path):
                fixtures.append((stem, data_path, gt))
                break
    return fixtures


def _page_images(path: str):
    """Returns list of (page_number, bgr_image) for a .png or multi-page .pdf fixture."""
    if path.lower().endswith(".pdf"):
        import fitz  # pymupdf
        doc = fitz.open(path)
        pages = []
        try:
            for i in range(doc.page_count):
                pix = doc.load_page(i).get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR) if pix.n == 3 else cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                pages.append((i + 1, bgr))
        finally:
            doc.close()
        return pages
    img = cv2.imread(path)
    return [(1, img)]


def _critical_field_hits(recognized_text: str, critical_fields: dict) -> dict:
    """Exact substring presence (case-insensitive, whitespace-collapsed) check per critical
    field. This is intentionally strict - a single OCR'd char wrong on '45.25mm' fails it,
    which is exactly the point for engineering-drawing numeric accuracy."""
    norm_text = " ".join(recognized_text.split()).lower()
    hits = {}
    for field, value in critical_fields.items():
        norm_value = " ".join(str(value).split()).lower()
        hits[field] = norm_value in norm_text
    return hits


def run():
    from app.config import get_settings
    from app.services import paddle_ocr as pocr_module
    from app.services.paddle_ocr import run_page_ocr

    fixtures = load_fixtures()
    all_results = []  # rows for the report table

    for cfg in CONFIGS:
        for key in ("OCR_PREPROCESS_DESKEW", "OCR_PREPROCESS_CLAHE"):
            os.environ[key] = "true" if cfg[key] else "false"
        get_settings.cache_clear()
        # Force a fresh engine so settings-dependent preprocessing is actually re-applied;
        # the engine itself (model weights) is reused, only preprocessing changes per run.
        for fixture_name, path, gt in fixtures:
            pages_gt = gt.get("pages") or {"1": gt}
            for page_number, image in _page_images(path):
                page_key = str(page_number)
                page_gt = pages_gt.get(page_key) or pages_gt.get("1", {})
                if not page_gt:
                    continue
                t0 = time.time()
                result = run_page_ocr(image, page_number=page_number)
                elapsed = time.time() - t0

                ref_text = page_gt.get("full_text", "")
                hyp_text = result.text
                c = cer(ref_text, hyp_text)
                w = wer(ref_text, hyp_text)
                critical = page_gt.get("critical_fields", {})
                hits = _critical_field_hits(hyp_text, critical)
                exact_match_rate = (sum(hits.values()) / len(hits)) if hits else None

                all_results.append({
                    "config": cfg["name"],
                    "fixture": fixture_name,
                    "page": page_number,
                    "cer": c,
                    "wer": w,
                    "critical_field_hits": hits,
                    "exact_match_rate": exact_match_rate,
                    "num_regions": len(result.regions),
                    "elapsed_s": round(elapsed, 2),
                    "ocr_configured": result.configured,
                    "ocr_error": result.error,
                })
    get_settings.cache_clear()
    write_report(all_results)
    return all_results


def write_report(rows):
    lines = ["# OCR Evaluation Report", "", (
        "Measured with REAL (unmocked) local PaddleOCR inference against SYNTHETIC fixtures "
        "only (see `ocr_dataset/synthetic/`). No real/manually-annotated engineering drawings "
        "exist yet - these numbers say nothing about accuracy on real production drawings."
    ), ""]

    by_config: dict[str, list] = {}
    for r in rows:
        by_config.setdefault(r["config"], []).append(r)

    lines.append("## Summary by preprocessing configuration")
    lines.append("")
    lines.append("| Configuration | Avg CER | Avg WER | Avg critical-field exact-match | Fixtures |")
    lines.append("|---|---|---|---|---|")
    for cfg_name, cfg_rows in by_config.items():
        avg_cer = sum(r["cer"] for r in cfg_rows) / len(cfg_rows)
        avg_wer = sum(r["wer"] for r in cfg_rows) / len(cfg_rows)
        em_rows = [r["exact_match_rate"] for r in cfg_rows if r["exact_match_rate"] is not None]
        avg_em = sum(em_rows) / len(em_rows) if em_rows else float("nan")
        lines.append(f"| {cfg_name} | {avg_cer:.4f} | {avg_wer:.4f} | {avg_em:.4f} | {len(cfg_rows)} |")
    lines.append("")

    lines.append(
        "The repo default is `OCR_PREPROCESS_DESKEW=False, OCR_PREPROCESS_CLAHE=True` "
        "(`deskew_off_clahe_on` above), based on a prior empirical finding that the "
        "minAreaRect-based deskew estimate can rotate already-straight text and hurt "
        "recognition. Compare its row above against `deskew_on_clahe_on` to see whether these "
        "new fixtures confirm or contradict that."
    )
    lines.append("")

    lines.append("## Per-fixture detail")
    lines.append("")
    lines.append("| Config | Fixture | Page | CER | WER | Critical fields hit | Regions | Time (s) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        hits = r["critical_field_hits"]
        hit_str = ", ".join(f"{k}={'OK' if v else 'MISS'}" for k, v in hits.items()) if hits else "n/a"
        lines.append(
            f"| {r['config']} | {r['fixture']} | {r['page']} | {r['cer']:.4f} | {r['wer']:.4f} "
            f"| {hit_str} | {r['num_regions']} | {r['elapsed_s']} |"
        )
    lines.append("")

    lines.append("## Known failure modes observed")
    lines.append("")
    failure_notes = []
    for r in rows:
        if r["config"] != CONFIGS[0]["name"]:
            continue
        for field, ok in r["critical_field_hits"].items():
            if not ok:
                failure_notes.append(
                    f"- `{r['fixture']}` page {r['page']}: critical field `{field}` was NOT "
                    f"recognized exactly (default config). Likely culprits for this field type: "
                    + ("diameter symbol (⌀) misread or dropped" if field == "diameter" else
                       "±/decimal-point character dropped or substituted" if field in ("tolerance", "dimension") else
                       "small/dense text misread")
                )
    if failure_notes:
        lines.extend(failure_notes)
    else:
        lines.append("- No critical-field misses recorded in the default configuration run.")
    lines.append("")
    lines.append(
        "Known general risk areas for this OCR stack on engineering drawings (even where not "
        "hit by the current fixture set): decimal points dropped/merged into neighboring digits, "
        "the diameter symbol (⌀) and plus/minus (±) glyphs are uncommon in most OCR "
        "training data and are the most error-prone single characters, and very small "
        "(<14pt-equivalent) dense note text has a higher per-character error rate than title-"
        "block-sized text."
    )
    lines.append("")

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    results = run()
    for r in results:
        print(r["config"], r["fixture"], "page", r["page"], "CER", round(r["cer"], 4),
              "WER", round(r["wer"], 4), "hits", r["critical_field_hits"])

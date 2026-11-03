"""Thin re-export of the existing OCR engine (app.services.paddle_ocr) under this package's
own extraction/ namespace, per the requested module layout - deliberately NOT a reimplementation.
pdf_extractor.py is the real integration point; import run_page_ocr from here only if you need
raw OCR regions directly (e.g. for a REVIEW_REQUIRED result's source_location context)."""
from __future__ import annotations

from app.services.paddle_ocr import OcrRegion, PageOcrResult, run_page_ocr  # noqa: F401

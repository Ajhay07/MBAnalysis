"""Regression for the real root cause behind every WO-9374-family component defaulting to a
fallback quantity of 1: PaddleOCR's region detection over the rasterized image never found the
BOM table's QTY-column digits at all (confirmed directly against the real drawing's own OCR
regions - no numeric region exists anywhere near the table, even though the SAME page's embedded
PDF text layer reads them correctly). app.providers.deterministic_provider._embedded_text_
numeric_regions supplies exactly those missing digits, straight from the PDF itself, scaled into
the same pixel space the image-OCR regions already use."""
from __future__ import annotations

import fitz
import pytest

from app.providers.deterministic_provider import _embedded_text_numeric_regions
from app.config import get_settings


def _build_pdf(tmp_path, texts: list[tuple[str, float, float]]) -> str:
    doc = fitz.open()
    page = doc.new_page(width=800, height=1000)
    for text, x, y in texts:
        page.insert_text((x, y), text, fontsize=10)
    path = str(tmp_path / "test.pdf")
    doc.save(path)
    doc.close()
    return path


def test_extracts_only_numeric_words_with_scaled_bbox(tmp_path):
    pdf_path = _build_pdf(tmp_path, [
        ("DESCRIPTION", 100, 100),
        ("BELLOWS", 100, 130),
        ("QTY", 300, 100),
        ("2", 300, 130),
        ("16", 300, 160),
    ])
    regions = _embedded_text_numeric_regions(pdf_path, page_number=1)
    texts = {r.text for r in regions}
    assert texts == {"2", "16"}  # DESCRIPTION/BELLOWS/QTY (non-numeric) never included

    zoom = get_settings().PDF_RENDER_DPI / 72.0
    two = next(r for r in regions if r.text == "2")
    # bbox x0 should be the PDF-point x (≈300) scaled by the same zoom factor
    # analysis_pipeline.rasterize_pdf_pages uses to rasterize the page for image OCR.
    x0 = two.bbox[0][0]
    assert x0 == pytest.approx(300 * zoom, abs=5)


def test_returns_empty_list_for_a_page_with_no_numeric_text(tmp_path):
    pdf_path = _build_pdf(tmp_path, [("DESCRIPTION", 100, 100), ("BELLOWS", 100, 130)])
    assert _embedded_text_numeric_regions(pdf_path, page_number=1) == []


def test_returns_empty_list_for_a_bad_path_never_raises():
    assert _embedded_text_numeric_regions("/no/such/file.pdf", page_number=1) == []


def test_returns_empty_list_for_an_out_of_range_page_never_raises(tmp_path):
    pdf_path = _build_pdf(tmp_path, [("16", 100, 100)])
    assert _embedded_text_numeric_regions(pdf_path, page_number=99) == []

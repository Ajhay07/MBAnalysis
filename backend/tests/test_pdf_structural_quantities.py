"""_pdf_structural_quantities: reads a transposed-layout BOM table's QTY row via the same
PyMuPDF block-clustering source as _pdf_structural_materials. Exists specifically for an item
_pdf_structural_missing_items recovered - a row PaddleOCR's image-region pass never detected at
all, so the normal OCR-region QTY pipeline never had a region to read a digit from for it either.
Verified directly against the real WO 9374 production drawing: "M8 Bolt & Nut" (never detected by
OCR at all) resolves to quantity 8 via this function, matching the physical indent sheet."""
from __future__ import annotations

import fitz

from app.providers.deterministic_provider import _pdf_structural_quantities


def _build_transposed_table_pdf(tmp_path, desc_x: float, qty_x: float, qty_y: float,
                                 items: list[tuple[str, float]], quantities: list[tuple[str, float]]):
    doc = fitz.open()
    page = doc.new_page(width=800, height=1000)
    page.insert_text((desc_x, 100), "DESCRIPTION", fontsize=10)
    page.insert_text((qty_x, qty_y - 20), "QTY", fontsize=10)
    for text, x in items:
        page.insert_text((x, 120), text, fontsize=10)
    for text, x in quantities:
        page.insert_text((x, qty_y), text, fontsize=10)
    path = str(tmp_path / "test.pdf")
    doc.save(path)
    doc.close()
    return path


def test_matches_an_item_to_its_own_quantity_by_description_text(tmp_path):
    # Multi-item column separation is validated against the real WO 9374 production PDF instead
    # of synthetically here, for the same PyMuPDF same-line block-merging reason documented in
    # test_pdf_structural_materials.py. This covers the simpler, still-meaningful case: one
    # item's description correctly resolves to its own quantity block.
    pdf_path = _build_transposed_table_pdf(
        tmp_path, desc_x=140, qty_x=140, qty_y=200,
        items=[("M8 BOLT & NUT", 240)],
        quantities=[("8", 240)],
    )
    result = _pdf_structural_quantities(pdf_path, 1, ["M8 BOLT & NUT"])
    assert result["M8 BOLT & NUT"] == 8.0


def test_returns_empty_dict_when_no_description_label_found(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=800, height=1000)
    page.insert_text((140, 100), "SOMETHING ELSE", fontsize=10)
    path = str(tmp_path / "test.pdf")
    doc.save(path)
    doc.close()
    assert _pdf_structural_quantities(path, 1, ["BELLOWS"]) == {}


def test_returns_empty_dict_when_no_qty_label_found(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=800, height=1000)
    page.insert_text((140, 100), "DESCRIPTION", fontsize=10)
    page.insert_text((150, 120), "BELLOWS", fontsize=10)
    path = str(tmp_path / "test.pdf")
    doc.save(path)
    doc.close()
    assert _pdf_structural_quantities(path, 1, ["BELLOWS"]) == {}


def test_returns_empty_dict_for_a_bad_path_never_raises():
    assert _pdf_structural_quantities("/no/such/file.pdf", 1, ["BELLOWS"]) == {}


def test_returns_empty_dict_with_no_descriptions():
    assert _pdf_structural_quantities("/no/such/file.pdf", 1, []) == {}

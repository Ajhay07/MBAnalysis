"""_pdf_structural_missing_items: recovers a BOM row that PaddleOCR's image-region pass missed
ENTIRELY (zero OCR regions anywhere in its column - not a misread, a true miss), using the PDF's
own embedded-text item blocks (same source as _pdf_structural_item_descriptions). Verified
directly against the real WO 9374 production drawing: a live re-analysis came back with only 10
of 11 components - "M8 Bolt & Nut" had no OCR region at all between "Shroud Support" and
"Collar" - and this recovered it correctly (material included) without duplicating any already-
present item, including the merged "material+description+qty" block case that previously caused
a bogus extra "item". The actual multi-item recovery (a missing item surrounded by other known
ones) isn't reproduced synthetically here - PyMuPDF's own block clustering on a bare page needs
real visual separation between items to avoid merging several same-line inserts into one block,
which only a real, visually dense drawing (not an empty synthetic PDF) reliably provides; these
tests instead cover the safety behaviors around that real-file-verified recovery - never
duplicating an already-known item under any of the ways that previously went wrong."""
from __future__ import annotations

import fitz

from app.providers.deterministic_provider import _pdf_structural_missing_items


def test_does_not_duplicate_an_item_already_known(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=800, height=1000)
    page.insert_text((140, 100), "DESCRIPTION", fontsize=10)
    page.insert_text((150, 120), "BELLOWS", fontsize=10)
    pdf_path = str(tmp_path / "test.pdf")
    doc.save(pdf_path)
    doc.close()

    assert _pdf_structural_missing_items(pdf_path, 1, ["BELLOWS"]) == []


def test_does_not_duplicate_a_merged_description_material_qty_block(tmp_path):
    # Reproduces the real "COLLAR" case: the item's own block is merged with material+qty text
    # ("A 240 Gr. 304COLLAR4") and so has a LOW fuzzy-ratio against the bare "COLLAR" description
    # already known - without the substring check, this registered as a second, bogus "missing"
    # item alongside the real one.
    doc = fitz.open()
    page = doc.new_page(width=800, height=1000)
    page.insert_text((140, 100), "DESCRIPTION", fontsize=10)
    page.insert_text((150, 120), "A 240 Gr. 304COLLAR4", fontsize=10)
    pdf_path = str(tmp_path / "test.pdf")
    doc.save(pdf_path)
    doc.close()

    assert _pdf_structural_missing_items(pdf_path, 1, ["COLLAR"]) == []


def test_ignores_unrelated_spec_paragraph_blocks_far_from_the_item_column(tmp_path):
    # Regression: an earlier, wider x-window let unrelated spec-parameters text ("Total Assembly
    # Weight...", "CYCLE LIFE...") bleed in as bogus "missing items" - these sit well past the
    # real item column's own x-range and are also far longer than any real item name.
    doc = fitz.open()
    page = doc.new_page(width=800, height=1000)
    page.insert_text((140, 100), "DESCRIPTION", fontsize=10)
    page.insert_text((150, 120), "BELLOWS", fontsize=10)
    page.insert_text((500, 125), "Total Assembly Weight 195 kg ( APPROX )", fontsize=10)
    pdf_path = str(tmp_path / "test.pdf")
    doc.save(pdf_path)
    doc.close()

    assert _pdf_structural_missing_items(pdf_path, 1, ["BELLOWS"]) == []


def test_returns_empty_list_for_a_bad_path_never_raises():
    assert _pdf_structural_missing_items("/no/such/file.pdf", 1, ["BELLOWS"]) == []

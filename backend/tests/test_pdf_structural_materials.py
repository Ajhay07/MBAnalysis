"""_pdf_structural_materials: material matching via PyMuPDF's own text-block clustering over the
PDF's embedded text layer, used as a more reliable alternative to OCR-region pixel-distance
heuristics for a transposed BOM table's wrapped, multi-line material callouts. Verified directly
against the real WO 9374 production drawing (all 11 components' materials came through
correctly, including the previously-worst case - a merged "material+description+qty" block for
the last item); these tests reproduce that structure with a synthetic PDF."""
from __future__ import annotations

import fitz

from app.providers.deterministic_provider import _pdf_structural_materials


def _build_transposed_table_pdf(tmp_path, desc_x: float, mat_x: float, mat_y: float,
                                 items: list[tuple[str, float]], materials: list[tuple[str, float]]):
    doc = fitz.open()
    page = doc.new_page(width=800, height=1000)
    page.insert_text((desc_x, 100), "DESCRIPTION", fontsize=10)
    page.insert_text((mat_x, mat_y - 20), "MATERIAL", fontsize=10)
    for text, x in items:
        page.insert_text((x, 120), text, fontsize=10)
    for text, x in materials:
        page.insert_text((x, mat_y), text, fontsize=10)
    path = str(tmp_path / "test.pdf")
    doc.save(path)
    doc.close()
    return path


def test_matches_an_item_to_its_own_material_by_description_text(tmp_path):
    # Multi-item column separation (proving two DIFFERENT items each get their own, distinct
    # material) is validated against the real WO 9374 production PDF instead of synthetically
    # here - PyMuPDF's own block-clustering merges two bare text runs on an otherwise-empty
    # synthetic page into one block regardless of x gap (it has no other page content to use as
    # a natural boundary, unlike a real, visually dense drawing), making that specific scenario
    # impractical to reproduce in isolation. This covers the simpler, still-meaningful case: one
    # item's description correctly resolves to its own material block.
    pdf_path = _build_transposed_table_pdf(
        tmp_path, desc_x=140, mat_x=140, mat_y=200,
        items=[("BELLOWS", 150)],
        materials=[("A 240 TYP 304", 150)],
    )
    result = _pdf_structural_materials(pdf_path, 1, [("BELLOWS", "2")])
    assert result["BELLOWS"] == "A 240 TYP 304"


def test_handles_a_merged_description_material_qty_block(tmp_path):
    # Reproduces the real WO 9374 case: PyMuPDF's own clustering merged Collar's material,
    # description and quantity into ONE text run with no spaces - "A 240 Gr. 304COLLAR4".
    doc = fitz.open()
    page = doc.new_page(width=800, height=1000)
    page.insert_text((140, 100), "DESCRIPTION", fontsize=10)
    page.insert_text((140, 180), "MATERIAL", fontsize=10)
    page.insert_text((250, 120), "A 240 Gr. 304COLLAR4", fontsize=10)
    path = str(tmp_path / "test.pdf")
    doc.save(path)
    doc.close()

    result = _pdf_structural_materials(path, 1, [("COLLAR", "4")])
    assert result["COLLAR"] == "A 240 Gr. 304"


def test_does_not_mistake_a_truncated_description_for_a_merged_block(tmp_path):
    # If the component's OWN description was itself truncated upstream (e.g. "& NUT" instead of
    # the full "M8 BOLT & NUT"), the correctly-matched-but-longer item block must not be
    # misread as "description merged with material" - the residual after stripping "& NUT"
    # ("M8 BOLT") contains a digit but isn't a real material pattern, so this must fall through
    # to the ordinary nearest-material-row lookup instead of returning "M8 BOLT" as the material.
    pdf_path = _build_transposed_table_pdf(
        tmp_path, desc_x=140, mat_x=140, mat_y=200,
        items=[("M8 BOLT & NUT", 240)],
        materials=[("IS 1367 CL 6.8 / 6.0", 240)],
    )
    result = _pdf_structural_materials(pdf_path, 1, [("& NUT", "8")])
    assert result["& NUT"] == "IS 1367 CL 6.8 / 6.0"


def test_returns_empty_dict_when_no_description_label_found(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=800, height=1000)
    page.insert_text((140, 100), "SOMETHING ELSE", fontsize=10)
    path = str(tmp_path / "test.pdf")
    doc.save(path)
    doc.close()
    assert _pdf_structural_materials(path, 1, [("BELLOWS", "2")]) == {}


def test_returns_empty_dict_for_a_bad_path_never_raises():
    assert _pdf_structural_materials("/no/such/file.pdf", 1, [("BELLOWS", "2")]) == {}


def test_returns_empty_dict_with_no_items():
    assert _pdf_structural_materials("/no/such/file.pdf", 1, []) == {}

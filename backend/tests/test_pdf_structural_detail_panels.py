"""extract_detail_dimensions_from_pdf_blocks: reads a drawing's own labeled "<NAME> DETAIL"
panels (OD/ID/Thk/L) from PyMuPDF's PDF-text-block clustering, as a more reliable alternative to
image-region OCR for the OD/ID/Thk/L fields PaddleOCR has been unreliable on (confirmed: OD/ID
were already coming through correctly via the existing OCR-region path, but Thk/L were not).

Verified directly against the real WO 9374 production drawing: every one of its 6 named detail
panels came through with the correct OD and, where present, the correct ID/Thk/L too (End Pipe
Thk=10/L=125, Mid Pipe Thk=10/L=150, Sleeve OD=539/ID=509/Thk=1.5/L=150, Shroud OD=683/Thk=15/
L=170, Housing Flange OD=810/ID=559/Thk=25) - a dramatic improvement over the OCR-region path,
which was confirmed to leave Thk/L blank or wrong for most of these same panels.

This drawing family lays its detail panels out in vertical lanes, where a label sits at its own
lane's left edge and its OWN values sit well to its right (offset ~50-150pt) - while an
ADJACENT lane's label can be geometrically CLOSER in raw (x, y) distance than that value's own
label is. Ordinary nearest-centroid matching (as app.services.drawing_detail_extractor's
existing OCR-tuned _assign_to_panels does) was confirmed to misassign values under this layout
(e.g. sending Sleeve's own L=150 to the neighboring Bellow panel) - fixed by the containment-
plus-x-offset assignment these tests cover. The two-lane cross-assignment scenario itself isn't
reproduced synthetically here - PyMuPDF's own block-join merges any two short text runs placed
close enough together on a bare synthetic page to set up that scenario, regardless of the x/y
gap (it has no other page content to use as a natural boundary, unlike a real, visually dense
drawing) - same limitation documented in test_pdf_structural_materials.py; it was verified
directly against the real WO 9374 file instead (see this module's own docstring above)."""
from __future__ import annotations

import fitz

from app.services.drawing_detail_extractor import extract_detail_dimensions_from_pdf_blocks


def _page_blocks(tmp_path, inserts: list[tuple[str, tuple[float, float]]], label_fontsize: float = 10):
    # The label is drawn at a larger fontsize so its own bbox spans real panel height (~55pt,
    # matching a real rotated "<NAME> DETAIL" label's own height) rather than one ordinary
    # text line's ~14pt - giving its values room to sit at distinct y's within its own
    # y-range-plus-margin without PyMuPDF merging them into a single same-line block (a
    # synthetic-PDF-only quirk also documented in test_pdf_structural_materials.py).
    doc = fitz.open()
    page = doc.new_page(width=800, height=1000)
    for i, (text, (x, y)) in enumerate(inserts):
        page.insert_text((x, y), text, fontsize=label_fontsize if i == 0 else 10)
    page_dict = page.get_text("dict")
    doc.close()
    return [b for b in page_dict["blocks"] if b.get("lines")]


def test_reads_od_thk_l_for_one_panel(tmp_path):
    blocks = _page_blocks(tmp_path, [
        ("END PIPE DETAIL", (30, 95)),
        ("OD559", (80, 70)),
        ("10", (100, 90)),
        ("125", (120, 110)),
    ], label_fontsize=40)
    panels = extract_detail_dimensions_from_pdf_blocks(blocks)
    assert len(panels) == 1
    assert panels[0].component_name == "END PIPE"
    assert panels[0].dimensions == {"od": "559", "thk": "10", "l": "125"}


def test_excludes_a_tall_narrow_block_that_reads_like_a_number(tmp_path):
    # A drawing's own vertical grid-reference markers along the page border can, after PyMuPDF's
    # own block-join, read like a plain number ("65") while being unmistakably tall-and-narrow
    # rather than a real inline dimension value's wide-and-short block shape. Built directly as
    # a block dict (rather than via insert_text) since it's the one case that specifically needs
    # an exact, deliberately-tall-and-narrow bbox to exercise the aspect-ratio exclusion.
    blocks = _page_blocks(tmp_path, [
        ("END PIPE DETAIL", (30, 95)),
        ("10", (80, 70)),
    ], label_fontsize=40)
    fake_tall_grid_marker_block = {
        "bbox": (100.0, 60.0, 108.0, 112.0),
        "lines": [
            {"spans": [{"text": "6"}]},
            {"spans": [{"text": "5"}]},
        ],
    }
    blocks.append(fake_tall_grid_marker_block)
    panels = extract_detail_dimensions_from_pdf_blocks(blocks)
    assert panels[0].dimensions.get("thk") == "10"
    assert "65" not in panels[0].raw_tokens
    assert "l" not in panels[0].dimensions


def test_returns_empty_list_with_no_blocks():
    assert extract_detail_dimensions_from_pdf_blocks([]) == []


def test_returns_empty_list_when_no_detail_label_found(tmp_path):
    blocks = _page_blocks(tmp_path, [("SOMETHING ELSE", (30, 95))])
    assert extract_detail_dimensions_from_pdf_blocks(blocks) == []

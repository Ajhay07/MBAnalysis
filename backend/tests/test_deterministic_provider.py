"""Unit tests for app.providers.deterministic_provider.DeterministicProvider - the no-API-key,
no-network, rule-based standard analysis provider. Mocks cv2.imread/run_page_ocr so these are
fast and deterministic (no real OCR engine or image I/O)."""
from __future__ import annotations

import numpy as np
import pytest

from app.providers.deterministic_provider import DeterministicProvider
from app.services.paddle_ocr import OcrRegion, PageOcrResult


def _region(text: str, x: float, y: float, w: float = 60, h: float = 18) -> OcrRegion:
    bbox = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return OcrRegion(text=text, confidence=0.9, bbox=bbox)


def _table_regions() -> list[OcrRegion]:
    header = [
        _region("ITEM NO.", 10, 100), _region("QTY", 90, 100),
        _region("PART NO", 150, 100), _region("DESCRIPTION", 230, 100),
        _region("MATERIAL", 340, 100),
    ]
    row1 = [
        _region("1", 10, 140), _region("16", 90, 140), _region("P-100", 150, 140),
        _region("Bellow", 230, 140), _region("SS316", 340, 140),
    ]
    row2 = [
        _region("2", 10, 170), _region("32", 90, 170), _region("P-101", 150, 170),
        _region("End Pipe", 230, 170), _region("SS316", 340, 170),
    ]
    return header + row1 + row2


SAMPLE_OCR_TEXT = (
    "MB METALLIC BELLOWS PVT LTD\n"
    "REV: B\n"
    "MATERIAL: SS 316L\n"
    "SCALE: 1:2\n"
    "DIA Ø240 R5 M30 TOL ±3\n"
)


def test_operates_with_no_api_key_at_all(monkeypatch):
    """Core requirement: this is the only real provider in the app, and it has no API key
    setting whatsoever - nothing can be missing/absent to block it."""
    provider = DeterministicProvider()
    result = provider.analyze(image_path="does-not-exist.png", ocr_text="", drawing_number="X-1")
    assert result.provider == "deterministic"


def test_title_block_and_materials_parsed_from_ocr_text(monkeypatch):
    monkeypatch.setattr(
        "app.providers.deterministic_provider.cv2.imread", lambda *_a, **_kw: None)
    provider = DeterministicProvider()
    result = provider.analyze(image_path="x.png", ocr_text=SAMPLE_OCR_TEXT, drawing_number="DWG-1")

    assert result.title_block.drawing_number == "DWG-1"
    assert result.title_block.revision == "B"
    assert "SS 316L" in result.title_block.material_spec
    assert result.title_block.scale == "1:2"
    assert "SS 316L" in result.materials or any("SS" in m for m in result.materials)


def test_drawing_quantity_and_nb_size_parsed_from_title_block(monkeypatch):
    """Real MB Metallic Bellows title blocks print "QUANTITY" and "SIZE ( NB )" as a label
    line followed by its value a couple of lines below (see WO-9374-family drawings), not on
    the same line - this is what feeds the indent generator's auto-filled defaults."""
    monkeypatch.setattr(
        "app.providers.deterministic_provider.cv2.imread", lambda *_a, **_kw: None)
    ocr_text = (
        "DESIGN TEMPERATURE\n"
        "65°C\n"
        "QUANTITY\n"
        "08 Nos.\n"
        "MATERIAL CODE\n"
        "101000070101\n"
        "SIZE ( NB )\n"
        "400 mm\n"
        "AXIAL MOVEMENT\n"
        "5 mm\n"
    )
    provider = DeterministicProvider()
    result = provider.analyze(image_path="x.png", ocr_text=ocr_text, drawing_number="DWG-2")
    assert result.title_block.drawing_quantity == 8.0
    assert result.title_block.nb_size_mm == 400.0


def test_missing_quantity_and_nb_fields_stay_none_not_guessed(monkeypatch):
    monkeypatch.setattr(
        "app.providers.deterministic_provider.cv2.imread", lambda *_a, **_kw: None)
    provider = DeterministicProvider()
    result = provider.analyze(image_path="x.png", ocr_text=SAMPLE_OCR_TEXT, drawing_number="DWG-3")
    assert result.title_block.drawing_quantity is None
    assert result.title_block.nb_size_mm is None


def test_wo_number_parsed_from_title_block(monkeypatch):
    """The real WO-9374-family drawings print "WO No. 9374" as a free-standing note - this
    feeds the frontend's auto-filled Generate Indent Sheet form (wo_number), same as
    drawing_quantity/nb_size_mm already do for assembly quantity/required-on."""
    monkeypatch.setattr(
        "app.providers.deterministic_provider.cv2.imread", lambda *_a, **_kw: None)
    ocr_text = "SOME NOTE\nWO No. 9374\nANOTHER NOTE\n"
    provider = DeterministicProvider()
    result = provider.analyze(image_path="x.png", ocr_text=ocr_text, drawing_number="DWG-4")
    assert result.title_block.wo_number == "9374"


def test_wo_number_missing_stays_empty_not_guessed(monkeypatch):
    monkeypatch.setattr(
        "app.providers.deterministic_provider.cv2.imread", lambda *_a, **_kw: None)
    provider = DeterministicProvider()
    result = provider.analyze(image_path="x.png", ocr_text=SAMPLE_OCR_TEXT, drawing_number="DWG-5")
    assert result.title_block.wo_number == ""


def test_dimension_patterns_extracted_from_text(monkeypatch):
    monkeypatch.setattr(
        "app.providers.deterministic_provider.cv2.imread", lambda *_a, **_kw: None)
    provider = DeterministicProvider()
    result = provider.analyze(image_path="x.png", ocr_text=SAMPLE_OCR_TEXT, drawing_number="DWG-1")

    labels = {d.label for d in result.dimensions}
    assert "diameter" in labels
    assert "radius" in labels
    assert "thread" in labels
    assert "tolerance" in labels
    for d in result.dimensions:
        assert d.source_text  # every finding carries its own evidence line


def test_no_bom_table_found_reports_ambiguity_and_empty_components_never_fabricated(monkeypatch):
    monkeypatch.setattr(
        "app.providers.deterministic_provider.cv2.imread", lambda *_a, **_kw: None)
    provider = DeterministicProvider()
    result = provider.analyze(image_path="x.png", ocr_text="no table here", drawing_number="DWG-1")

    assert result.components == []
    assert result.ambiguities  # flagged for human review, not silently empty
    assert any("BOM table" in a.description for a in result.ambiguities)
    assert any("BOM table" in m for m in result.missing_info)


def test_components_extracted_from_real_bom_table_regions(monkeypatch):
    fake_image = np.zeros((10, 10, 3), dtype=np.uint8)
    monkeypatch.setattr(
        "app.providers.deterministic_provider.cv2.imread", lambda *_a, **_kw: fake_image)
    monkeypatch.setattr(
        "app.providers.deterministic_provider.run_page_ocr",
        lambda image, page_number=1: PageOcrResult(page_number=page_number, regions=_table_regions()),
    )
    provider = DeterministicProvider()
    result = provider.analyze(image_path="x.png", ocr_text="", drawing_number="DWG-1")

    assert len(result.components) == 2
    by_part = {c.part_number: c for c in result.components}
    assert by_part["P-100"].description == "Bellow"
    assert by_part["P-100"].quantity == 16
    assert by_part["P-100"].quantity_basis == "explicit_callout"
    assert by_part["P-100"].material == "SS316"
    assert by_part["P-100"].source_text  # evidence always present
    assert by_part["P-101"].quantity == 32


def test_transposed_bom_quantity_comes_from_pdf_embedded_text_not_image_ocr(monkeypatch, tmp_path):
    """End-to-end regression for the real production bug: a WO-9374-style transposed BOM table
    whose image-OCR pass finds DESCRIPTION/MATERIAL/item regions but ZERO quantity digits
    (reproducing the real drawing exactly - confirmed against its actual OCR regions, which had
    no numeric region anywhere near the table) must still end up with the right quantity on each
    component, because pdf_path now supplies those missing digits straight from the PDF's own
    embedded text layer."""
    import fitz
    from app.config import get_settings

    desc_y, mat_y, qty_y = 1800, 2000, 2200
    image_regions = [
        _region("DESCRIPTION", 390, desc_y, w=25, h=110),
        _region("BELLOWS", 413, desc_y, w=25, h=95),
        _region("END PIPE", 445, desc_y, w=25, h=85),
        _region("MATERIAL", 394, mat_y, w=25, h=85),
        _region("A 240 TYP 304", 418, mat_y, w=25, h=120),
        _region("A 516 Gr.70", 450, mat_y, w=25, h=90),
        # The QTY LABEL is readable by image OCR on the real drawing (it's normal-sized text,
        # unlike the small digit values below it) - only the VALUE digits were the ones missing.
        _region("QTY", 396, qty_y, w=25, h=80),
    ]
    fake_image = np.zeros((10, 10, 3), dtype=np.uint8)
    monkeypatch.setattr(
        "app.providers.deterministic_provider.cv2.imread", lambda *_a, **_kw: fake_image)
    monkeypatch.setattr(
        "app.providers.deterministic_provider.run_page_ocr",
        lambda image, page_number=1: PageOcrResult(page_number=page_number, regions=image_regions),
    )

    # The embedded PDF text layer DOES have the QTY values (same as the real drawing's
    # raw_ocr_text, which already proved they're really in the PDF) - positioned, in PDF points,
    # so that after zoom-scaling they land at the same pixel location the image-region fixture
    # above uses for its desc_x/qty_y strip.
    zoom = get_settings().PDF_RENDER_DPI / 72.0
    doc = fitz.open()
    page = doc.new_page(width=1200, height=3000)
    page.insert_text((413 / zoom, (qty_y + 20) / zoom), "2", fontsize=8)
    page.insert_text((445 / zoom, (qty_y + 20) / zoom), "8", fontsize=8)
    pdf_path = str(tmp_path / "wo9374_style.pdf")
    doc.save(pdf_path)
    doc.close()

    provider = DeterministicProvider()
    result = provider.analyze(image_path="x.png", ocr_text="", drawing_number="DWG-9374",
                               pdf_path=pdf_path, page_number=1)

    by_desc = {c.description: c for c in result.components}
    assert by_desc["BELLOWS"].quantity == 2
    assert by_desc["BELLOWS"].quantity_basis == "explicit_callout"
    assert by_desc["END PIPE"].quantity == 8
    assert by_desc["END PIPE"].quantity_basis == "explicit_callout"


def test_never_crashes_when_opencv_is_unavailable(monkeypatch):
    monkeypatch.setattr("app.providers.deterministic_provider.cv2", None)
    provider = DeterministicProvider()
    result = provider.analyze(image_path="x.png", ocr_text=SAMPLE_OCR_TEXT, drawing_number="DWG-1")
    assert result.components == []
    assert result.title_block.revision == "B"  # text-only parsing still works

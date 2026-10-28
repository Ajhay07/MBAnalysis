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


def test_never_crashes_when_opencv_is_unavailable(monkeypatch):
    monkeypatch.setattr("app.providers.deterministic_provider.cv2", None)
    provider = DeterministicProvider()
    result = provider.analyze(image_path="x.png", ocr_text=SAMPLE_OCR_TEXT, drawing_number="DWG-1")
    assert result.components == []
    assert result.title_block.revision == "B"  # text-only parsing still works

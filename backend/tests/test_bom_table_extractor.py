"""Unit tests for app.services.bom_table_extractor, using hand-built OcrRegion fixtures (no
real OCR engine involved - deterministic, fast). Mirrors the fixture style used by
tests/test_reference_bom_service.py."""
from __future__ import annotations

from app.services.bom_table_extractor import extract_bom_table
from app.services.paddle_ocr import OcrRegion


def _region(text: str, x: float, y: float, w: float = 60, h: float = 18) -> OcrRegion:
    bbox = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return OcrRegion(text=text, confidence=0.9, bbox=bbox)


def _simple_table_regions() -> list[OcrRegion]:
    # Header row at y=100.
    header = [
        _region("ITEM NO.", 10, 100),
        _region("QTY", 90, 100),
        _region("PART NO", 150, 100),
        _region("DESCRIPTION", 230, 100),
        _region("MATERIAL", 340, 100),
    ]
    # Body row 1 at y=140.
    row1 = [
        _region("1", 10, 140),
        _region("16", 90, 140),
        _region("P-100", 150, 140),
        _region("Bellow", 230, 140),
        _region("SS316", 340, 140),
    ]
    # Body row 2 at y=170.
    row2 = [
        _region("2", 10, 170),
        _region("32", 90, 170),
        _region("P-101", 150, 170),
        _region("End Pipe", 230, 170),
        _region("SS316", 340, 170),
    ]
    return header + row1 + row2


def test_extracts_header_and_rows_from_well_formed_table():
    table = extract_bom_table(_simple_table_regions())
    assert table is not None
    assert len(table.rows) == 2

    row1 = table.rows[0]
    assert row1.qty == "16"
    assert row1.part_no == "P-100"
    assert row1.description == "Bellow"
    assert row1.material == "SS316"

    row2 = table.rows[1]
    assert row2.qty == "32"
    assert row2.part_no == "P-101"
    assert row2.description == "End Pipe"


def test_returns_none_when_no_header_row_found():
    stray = [_region("Some random title block text", 10, 10), _region("Steel", 10, 40)]
    assert extract_bom_table(stray) is None


def test_returns_none_for_empty_regions():
    assert extract_bom_table([]) is None


def test_scattered_header_token_is_dropped_but_tight_cluster_still_detected():
    # "QTY" shows up far away from the other header-like tokens (e.g. an unrelated dimension
    # callout). It must be excluded from the header row, but the remaining tightly-clustered
    # tokens (still >= MIN_DISTINCT_HEADER_TOKENS) are a legitimate, if narrower, table header -
    # same tightest-cluster behavior as reference_bom_service.detect_reference_bom_table.
    regions = [
        _region("ITEM NO.", 10, 100),
        _region("PART NO", 150, 100),
        _region("DESCRIPTION", 230, 100),
        _region("QTY", 10, 500),  # far below, unrelated - must not end up in header_columns
    ]
    table = extract_bom_table(regions)
    assert table is not None
    assert "qty" not in table.header_columns
    assert set(table.header_columns) == {"item_no", "part_no", "description"}


def test_truly_scattered_headers_below_minimum_cluster_return_none():
    # Only 2 of the header-like tokens end up in any single tight cluster - below
    # MIN_DISTINCT_HEADER_TOKENS, so no table should be detected at all.
    regions = [
        _region("ITEM NO.", 10, 100),
        _region("PART NO", 150, 500),
        _region("DESCRIPTION", 230, 900),
    ]
    assert extract_bom_table(regions) is None


def test_header_only_with_no_body_rows_returns_empty_row_list():
    header_only = [
        _region("ITEM NO.", 10, 100),
        _region("QTY", 90, 100),
        _region("PART NO", 150, 100),
    ]
    table = extract_bom_table(header_only)
    assert table is not None
    assert table.rows == []

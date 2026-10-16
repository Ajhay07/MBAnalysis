"""Unit tests for the reference-BOM-table detection heuristic (app.services.reference_bom_service).
Uses synthetic OcrRegion lists built directly from the text content of the existing OCR-eval
fixtures (backend/eval/ocr_dataset/synthetic) so the test reflects realistic OCR output shape
without requiring the optional paddleocr dependency to be installed."""
from app.services.paddle_ocr import OcrRegion
from app.services.reference_bom_service import compute_discrepancy, detect_reference_bom_table


def _region(text: str, x0: float, y0: float, x1: float, y1: float, confidence: float = 0.95) -> OcrRegion:
    return OcrRegion(text=text, confidence=confidence,
                      bbox=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]])


def _bom_table_regions() -> list[OcrRegion]:
    """Mirrors backend/eval/ocr_dataset/synthetic/fixture_02_bom_table.json's full_text, laid
    out as a real BOM grid would be: one header row, four aligned body rows."""
    header_y = 100
    return [
        _region("BILL OF MATERIALS", 10, 40, 300, 60),
        _region("ITEM", 10, header_y, 60, header_y + 20),
        _region("PART NO", 70, header_y, 180, header_y + 20),
        _region("DESCRIPTION", 190, header_y, 340, header_y + 20),
        _region("QTY", 350, header_y, 400, header_y + 20),
        _region("1", 10, 130, 60, 150),
        _region("BRK-200", 70, 130, 180, 150),
        _region("Mounting Bracket", 190, 130, 340, 150),
        _region("4", 350, 130, 400, 150),
        _region("2", 10, 160, 60, 180),
        _region("SHF-305", 70, 160, 180, 180),
        _region("Drive Shaft 10.0mm", 190, 160, 340, 180),
        _region("1", 350, 160, 400, 180),
        _region("3", 10, 190, 60, 210),
        _region("BRG-6204", 70, 190, 180, 210),
        _region("Ball Bearing 6204-2RS", 190, 190, 340, 210),
        _region("2", 350, 190, 400, 210),
        _region("4", 10, 220, 60, 240),
        _region("SCR-M6X20", 70, 220, 180, 240),
        _region("Hex Screw M6x20", 190, 220, 340, 240),
        _region("8", 350, 220, 400, 240),
    ]


def _no_bom_table_regions() -> list[OcrRegion]:
    """Mirrors fixture_01_titleblock_dimensions.json's full_text: title block + dimension
    callouts, no ITEM/QTY/PART-NO grid anywhere."""
    return [
        _region("DRAWING NO: MB-10045-REV-C", 10, 20, 300, 40),
        _region("TITLE: Pump Housing Bracket", 10, 50, 300, 70),
        _region("REVISION: C   SCALE: 1:2   UNITS: mm", 10, 80, 300, 100),
        _region("BORE DIAMETER: 12.5mm +/-0.1mm TOLERANCE", 10, 110, 340, 130),
        _region("OVERALL LENGTH: 45.25mm", 10, 140, 300, 160),
        _region("WALL THICKNESS: 3.75mm +/-0.05mm", 10, 170, 320, 190),
        _region("MATERIAL: Aluminum 6061-T6", 10, 200, 300, 220),
    ]


def test_detects_clear_bom_table():
    result = detect_reference_bom_table(_bom_table_regions(), page_number=1)
    assert result is not None
    assert result.detected is True
    assert len(result.matched_headers) >= 3
    assert result.row_count_estimate >= 3  # 4 body rows, clustering is approximate
    assert "BRG-6204" in result.raw_text


def test_does_not_detect_table_in_titleblock_only_page():
    result = detect_reference_bom_table(_no_bom_table_regions(), page_number=1)
    assert result is None


def test_does_not_detect_with_empty_regions():
    assert detect_reference_bom_table([], page_number=1) is None


def test_single_scattered_header_token_is_not_enough():
    # Only one lone "MATERIAL" callout from a title block - should never trigger detection.
    regions = [_region("MATERIAL: Aluminum 6061-T6", 10, 200, 300, 220)]
    assert detect_reference_bom_table(regions) is None


def test_compute_discrepancy_flags_count_mismatch_and_unmatched_descriptions():
    report = compute_discrepancy(
        reference_row_count=4,
        candidate_component_count=5,
        reference_text="ITEM PART NO DESCRIPTION QTY\n1 BRK-200 Mounting Bracket 4",
        candidate_descriptions=["Mounting Bracket", "Fastener (qty derived from 6x bolt_hole pattern)"],
        candidate_part_numbers=["BRK-200", "XYZ-999"],
    )
    assert report["count_mismatch"] is True
    assert report["reference_row_count_estimate"] == 4
    assert report["candidate_component_count"] == 5
    assert "Fastener (qty derived from 6x bolt_hole pattern)" in report["candidate_descriptions_not_found_in_reference_text"]
    assert "XYZ-999" in report["candidate_part_numbers_not_found_in_reference_text"]
    assert "Mounting Bracket" not in report["candidate_descriptions_not_found_in_reference_text"]


def test_compute_discrepancy_no_mismatch_when_counts_equal():
    report = compute_discrepancy(
        reference_row_count=4, candidate_component_count=4,
        reference_text="ITEM PART NO DESCRIPTION QTY",
        candidate_descriptions=[], candidate_part_numbers=[],
    )
    assert report["count_mismatch"] is False

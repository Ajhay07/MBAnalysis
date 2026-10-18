from app.models.models import (
    Analysis, Bom, CatalogComponent, Component, Drawing, DrawingStatus, MakeBuy,
)
from app.services.bom_service import generate_bom_from_analysis
from app.services.catalog_matching import match_catalog_component


def _catalog():
    return [
        CatalogComponent(id="cat-1", part_number="6205-2RS", description="Deep Groove Ball Bearing",
                          unit_price=4.25),
        CatalogComponent(id="cat-2", part_number="M6-BOLT", description="Hex Bolt M6x20",
                          unit_price=0.18),
    ]


def test_exact_normalized_part_number_match_wins_outright():
    catalog = _catalog()
    matched, score = match_catalog_component("6205-2rs", "some OCR text", catalog)
    assert matched is not None
    assert matched.id == "cat-1"
    assert score == 1.0


def test_separator_noise_in_ocr_text_still_matches_exactly():
    # OCR frequently mangles separators ('-' vs ' ' vs '_'); normalization should absorb this.
    catalog = _catalog()
    matched, score = match_catalog_component("6205 2RS", "", catalog)
    assert matched is not None and matched.id == "cat-1"
    assert score == 1.0


def test_unrelated_part_number_returns_no_match():
    catalog = _catalog()
    matched, score = match_catalog_component("ZZZ-9999", "totally unrelated widget", catalog)
    assert matched is None
    assert score == 0.0


def test_empty_catalog_returns_no_match():
    matched, score = match_catalog_component("6205-2RS", "Deep Groove Ball Bearing", [])
    assert matched is None
    assert score == 0.0


def test_close_fuzzy_part_number_match_found_but_below_floor_rejected():
    catalog = _catalog()
    # Shares no real structure with either catalog part number - must not be force-matched.
    matched, score = match_catalog_component("XYZ-123", "", catalog)
    assert matched is None


def test_bom_generation_carries_catalog_match_and_seeds_unit_cost(db):
    catalog_item = CatalogComponent(part_number="M6-BOLT", description="Hex Bolt M6x20",
                                     unit_price=0.18)
    db.add(catalog_item)
    db.flush()

    drawing = Drawing(drawing_number="T-CAT", title="Catalog Test", revision="A",
                       file_name="t.png", stored_file_name="t_stored.png", file_type="png",
                       file_size=10, status=DrawingStatus.REVIEWED)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test",
                         title_block={}, dimensions=[], materials=[], overall_confidence=0.9)
    db.add(analysis)
    db.flush()

    matched_component = Component(
        analysis_id=analysis.id, part_number="M6-BOLT", description="Hex Bolt M6x20",
        category="Fastener", quantity=4, material="", make_buy=MakeBuy.BUY,
        confidence=0.95, verification_status="Verified",
        catalog_component_id=catalog_item.id, catalog_match_score=1.0,
    )
    unmatched_component = Component(
        analysis_id=analysis.id, part_number="GB-X-01", description="Unrelated bracket",
        category="Bracket", quantity=1, material="Steel", make_buy=MakeBuy.MAKE,
        confidence=0.9, verification_status="Verified",
    )
    db.add_all([matched_component, unmatched_component])
    db.commit()
    db.refresh(analysis)

    bom = generate_bom_from_analysis(db, analysis)

    matched_line = next(li for li in bom.line_items if li.part_number == "M6-BOLT")
    unmatched_line = next(li for li in bom.line_items if li.part_number == "GB-X-01")

    assert matched_line.catalog_component_id == catalog_item.id
    assert matched_line.unit_cost == 0.18
    assert unmatched_line.catalog_component_id is None
    assert unmatched_line.unit_cost is None

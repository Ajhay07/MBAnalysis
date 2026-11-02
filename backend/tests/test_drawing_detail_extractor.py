"""Synthetic OCR regions shaped like real MB Metallic Bellows drawing DETAIL panels (see
WO-9374's "SLEEVE DETAIL" / "END PIPE DETAIL" / "HOUSING FLANGE DETAIL" panels) - bbox
coordinates are approximate but preserve the real layout: a "<NAME> DETAIL" label with its
dimension tokens scattered within a few hundred pixels below/around it, a different unrelated
panel further down the page, and a label-less "DETAIL-A" weld-section callout that must never
be treated as a component panel.
"""
from app.services.drawing_detail_extractor import extract_detail_dimensions, match_panel_to_description
from app.services.paddle_ocr import OcrRegion


def _r(text, x, y, w=40, h=20, conf=0.9):
    return OcrRegion(text=text, confidence=conf, bbox=[[x, y], [x + w, y], [x + w, y + h], [x, y + h]])


def test_extracts_od_id_thk_l_from_sleeve_panel():
    regions = [
        _r("SLEEVE DETAIL", 100, 500),
        _r("OD", 100, 540),
        _r("539", 140, 540),
        _r("ID", 100, 570),
        _r("509", 140, 570),
        _r("THK", 100, 600),
        _r("1.5", 140, 600),
        _r("L", 100, 630),
        _r("150", 140, 630),
        # unrelated panel far below must not bleed in
        _r("END PIPE DETAIL", 100, 1200),
        _r("559", 140, 1240),
    ]
    panels = extract_detail_dimensions(regions)
    sleeve = next(p for p in panels if p.component_name == "SLEEVE")
    assert sleeve.dimensions["od"] == "539"
    assert sleeve.dimensions["id"] == "509"
    assert sleeve.dimensions["thk"] == "1.5"
    assert sleeve.dimensions["l"] == "150"
    assert sleeve.needs_confirmation is False


def test_bare_detail_letter_callout_is_not_a_component_panel():
    regions = [_r("DETAIL-A", 300, 300), _r("37.5", 320, 330)]
    panels = extract_detail_dimensions(regions)
    assert panels == []


def test_inline_labeled_token_is_parsed():
    regions = [
        _r("HOUSING FLANGE DETAIL", 100, 100),
        _r("OD810", 120, 140),
        _r("OD559", 120, 170),
    ]
    panels = extract_detail_dimensions(regions)
    flange = next(p for p in panels if p.component_name == "HOUSING FLANGE")
    assert flange.dimensions["od"] == "810"


def test_unlabeled_diameter_values_fall_back_to_od_then_id():
    regions = [
        _r("END PIPE DETAIL", 100, 100),
        _r("Ø559", 120, 140),
        _r("125", 120, 170),
    ]
    panels = extract_detail_dimensions(regions)
    end_pipe = next(p for p in panels if p.component_name == "END PIPE")
    assert end_pipe.dimensions["od"] == "559"
    assert end_pipe.dimensions["l"] == "125"


def test_panel_with_no_nearby_numbers_is_flagged_for_confirmation():
    regions = [_r("SHROUD DETAIL", 100, 100)]
    panels = extract_detail_dimensions(regions)
    shroud = panels[0]
    assert shroud.dimensions == {}
    assert shroud.needs_confirmation is True


def test_no_detail_labels_returns_empty_list():
    regions = [_r("BILL OF MATERIAL", 10, 10), _r("DESCRIPTION", 10, 40)]
    assert extract_detail_dimensions(regions) == []


def test_match_panel_to_description_substring_match():
    regions = [
        _r("HOUSING FLANGE DETAIL", 100, 100),
        _r("OD810", 120, 140),
    ]
    panels = extract_detail_dimensions(regions)
    matched = match_panel_to_description("Housing flange", panels)
    assert matched is not None
    assert matched.component_name == "HOUSING FLANGE"
    assert match_panel_to_description("Collar", panels) is None

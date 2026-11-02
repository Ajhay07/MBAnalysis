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
    # Always True regardless of how much was found - this is heuristic pixel-proximity
    # evidence, never treated as a verified reading without a human checking it.
    assert sleeve.needs_confirmation is True


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
    ]
    panels = extract_detail_dimensions(regions)
    end_pipe = next(p for p in panels if p.component_name == "END PIPE")
    assert end_pipe.dimensions["od"] == "559"


def test_unlabeled_plain_number_is_never_guessed_as_thk_or_l():
    # Regression: a bare, unlabeled number near a panel used to be guessed as Thk (small
    # decimal) or L (plain integer) by convention. Reverted - on real drawings the genuine
    # Thk/L values are themselves usually unlabeled too, so this had no real signal to tell a
    # true Thk/L apart from an unrelated nearby number (confirmed wrong on WO-9374's Mid Pipe
    # and Bellow panels). Only OD/ID (from an unambiguous Ø-prefixed token) and explicitly
    # labeled values (an adjacent "L"/"THK" text region, or inline "L150") are ever reported.
    regions = [_r("END PIPE DETAIL", 100, 100), _r("Ø559", 120, 140), _r("125", 120, 170)]
    panels = extract_detail_dimensions(regions)
    end_pipe = next(p for p in panels if p.component_name == "END PIPE")
    assert end_pipe.dimensions == {"od": "559"}


def test_panel_with_no_nearby_numbers_is_flagged_for_confirmation():
    regions = [_r("SHROUD DETAIL", 100, 100)]
    panels = extract_detail_dimensions(regions)
    shroud = panels[0]
    assert shroud.dimensions == {}
    assert shroud.needs_confirmation is True


def test_no_detail_labels_returns_empty_list():
    regions = [_r("BILL OF MATERIAL", 10, 10), _r("DESCRIPTION", 10, 40)]
    assert extract_detail_dimensions(regions) == []


def test_leading_item_number_marker_is_stripped_before_matching():
    # Regression: a real drawing (3I/26160A) prints "[01] BELLOW DETAIL" - the leading "[01] "
    # marker made the whole label fail to match at all (bracket isn't a valid NAME character).
    regions = [_r("[01] BELLOW DETAIL", 100, 100), _r("210", 120, 130)]
    panels = extract_detail_dimensions(regions)
    assert len(panels) == 1
    assert panels[0].component_name == "BELLOW"


def test_roman_numeral_suffix_is_matched_in_full():
    # Regression: "BRACKET DETAIL-II" (a real drawing's second bracket variant) only matched as
    # far as "BRACKET DETAIL-I", leaving a dangling "I" that broke the full-string anchor - the
    # whole label silently failed to match and that panel was never found at all.
    regions = [_r("BRACKET DETAIL-II", 100, 100), _r("50", 120, 130)]
    panels = extract_detail_dimensions(regions)
    assert len(panels) == 1
    assert panels[0].component_name == "BRACKET"


def test_other_bom_component_names_and_header_words_never_leak_into_a_panel():
    # Regression: on a real, densely-laid-out drawing, a panel label's nearby-region window
    # picked up completely unrelated page content purely by pixel proximity - other BOM item
    # names ("LIMIT ROD"), table header words ("DESCRIPTION"), and long general-notes sentences.
    # None of that is ever a genuine dimension and must never be treated as one.
    regions = [
        _r("SLEEVE DETAIL", 100, 100),
        _r("DESCRIPTION", 110, 130),
        _r("LIMIT ROD", 110, 150),
        _r("1. SUITABLE SHIPPING BARS WILL BE PROVIDED, PAINTED IN YELLOW", 110, 170),
        _r("Ø219", 110, 190),
    ]
    panels = extract_detail_dimensions(regions, known_descriptions=["Limit Rod", "Sleeve"])
    sleeve = panels[0]
    assert sleeve.dimensions == {"od": "219"}
    assert "DESCRIPTION" not in sleeve.raw_tokens
    assert "LIMIT ROD" not in sleeve.raw_tokens
    assert not any("SHIPPING BARS" in t for t in sleeve.raw_tokens)


def test_ocr_misread_diameter_symbol_as_zero_is_still_parsed():
    # Regression: PaddleOCR has repeatedly misread the "Ø" diameter glyph as a bare "0" on two
    # separate real drawings (WO-9347: "Ø 219" -> "0 219"; WO-9374: "Ø 559" -> "0 559"). Without
    # this, every such callout silently fell through to the generic dim_N bucket instead of OD/ID.
    regions = [
        _r("HOUSING FLANGE DETAIL", 100, 100),
        _r("0 810", 120, 140),
        _r("0 559", 120, 170),
    ]
    panels = extract_detail_dimensions(regions)
    flange = panels[0]
    assert flange.dimensions["od"] == "810"
    assert flange.dimensions["id"] == "559"


def test_small_leading_zero_value_is_not_misread_as_a_diameter():
    # A real small measurement that happens to start with "0 " (e.g. an OCR split of a decimal
    # like "0 6") must not be swept up by the Ø-misread tolerance, which is deliberately scoped
    # to 2+ digit values (the smallest real OD/ID callout on these drawings is 3 digits).
    regions = [_r("SLEEVE DETAIL", 100, 100), _r("0 6", 120, 140)]
    panels = extract_detail_dimensions(regions)
    assert panels[0].dimensions == {}


def test_notes_fragment_with_a_colon_is_excluded_from_a_panel():
    # Regression: "GENERAL NOTES:-" (and similar label-style fragments like "NOTE :-", "Min
    # DFT: 40 TO 50 MICRON") leaked into a panel's matched tokens on a real drawing purely by
    # page proximity - a genuine dimension callout on these drawings never carries a colon.
    regions = [
        _r("BRACKET DETAIL-I", 100, 100),
        _r("GENERAL NOTES:-", 110, 130),
        _r("028", 110, 150),
    ]
    panels = extract_detail_dimensions(regions)
    bracket = panels[0]
    assert "GENERAL NOTES:-" not in bracket.raw_tokens


def test_material_grade_text_is_excluded_from_a_panel():
    # Regression: material-grade cells ("A 240 TYP 304", "SS 304", "IS 2062 E250 BR") leaked
    # into a panel's matched tokens on a real drawing - these are always a MATERIAL column
    # value, never a component's own dimension, regardless of how close they sit to a label.
    regions = [
        _r("COLLAR DETAIL", 100, 100),
        _r("A 240 TYP 304", 110, 130),
        _r("SS 304", 110, 150),
        _r("IS 2062 E250 BR", 110, 170),
    ]
    panels = extract_detail_dimensions(regions)
    collar = panels[0]
    assert collar.raw_tokens == []


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

"""Regression test for the bug where Thickness and Length were silently dropped whenever a
BOM row's own SIZE cell already had any text (even just an OD reading): the matching detail
panel's structured od/id/thk/l dict was only ever consulted when `dimensions` was still empty,
so a row with a partial/OD-only SIZE cell never picked up Thickness/Length from the panel at
all - see app.providers.deterministic_provider._rows_to_components."""
from app.providers.deterministic_provider import _merge_detail_panels, _rows_to_components
from app.services.bom_table_extractor import BomRow
from app.services.drawing_detail_extractor import DetailPanel


def test_thickness_and_length_merged_in_from_panel_even_when_bom_size_cell_has_text():
    row = BomRow(description="Mid Pipe", qty="1", size="OD 559", confidence=0.8)
    panel = DetailPanel(
        label_text="MID PIPE DETAIL", component_name="MID PIPE",
        dimensions={"od": "559", "thk": "10", "l": "150"}, needs_confirmation=True,
    )
    components = _rows_to_components([row], page_number=1, detail_panels=[panel])

    assert len(components) == 1
    dims = components[0].dimensions
    # The BOM table's own SIZE text is preserved, never overwritten by the panel...
    assert dims["size"] == "OD 559"
    # ...but Thickness/Length (only available from the panel) are now merged in, not dropped.
    assert dims["thk"] == "10"
    assert dims["l"] == "150"
    assert components[0].is_assumption is True  # panel-sourced values still flagged for review


def test_panel_never_overwrites_a_key_the_bom_table_already_supplied():
    row = BomRow(description="Sleeve", qty="1", size="OD 509", confidence=0.8)
    panel = DetailPanel(
        label_text="SLEEVE DETAIL", component_name="SLEEVE",
        dimensions={"od": "539"},  # the auto-extractor's own (less trusted) OD reading
        needs_confirmation=True,
    )
    components = _rows_to_components([row], page_number=1, detail_panels=[panel])
    # "size" (free text, from the BOM table) is untouched - the panel's "od" key is a
    # DIFFERENT dict key, so there's nothing to overwrite here; this just confirms the merge
    # is additive, not a wholesale replacement of what the BOM table already gave.
    assert components[0].dimensions["size"] == "OD 509"
    assert components[0].dimensions["od"] == "539"


def test_no_detail_panel_match_leaves_bom_size_untouched():
    row = BomRow(description="Gasket", qty="1", size="M8", confidence=0.8, raw_text="Gasket M8")
    components = _rows_to_components([row], page_number=1, detail_panels=[])
    assert components[0].dimensions == {"size": "M8"}
    assert components[0].is_assumption is False


def test_shroud_panel_l_is_aliased_to_width_for_the_calc_engine():
    # app.services.calc_engine_service's Bellows/Shroud formula reads a "width" key, never "l" -
    # Shroud's own flat-pattern length is CALCULATED from "od", not read from this panel at all,
    # so a panel-sourced "l" (its own best-effort magnitude guess) needs aliasing to "width" or
    # the calc engine would never see it and would report width as unobtainable even when the
    # panel actually found one. Confirmed necessary on the real WO 9374 Shroud (panel l="170",
    # the real Shroud width per the physical indent sheet).
    row = BomRow(description="Shroud", qty="1", size="", confidence=0.8)
    panel = DetailPanel(
        label_text="SHROUD DETAIL", component_name="SHROUD",
        dimensions={"od": "683", "thk": "2", "l": "170"}, needs_confirmation=True,
    )
    components = _rows_to_components([row], page_number=1, detail_panels=[panel])
    assert components[0].dimensions["width"] == "170"
    assert components[0].dimensions["l"] == "170"  # original key kept, not replaced


def test_width_aliasing_does_not_apply_to_an_ordinary_cylindrical_component():
    row = BomRow(description="Mid Pipe", qty="1", size="", confidence=0.8)
    panel = DetailPanel(
        label_text="MID PIPE DETAIL", component_name="MID PIPE",
        dimensions={"od": "559", "thk": "10", "l": "150"}, needs_confirmation=True,
    )
    components = _rows_to_components([row], page_number=1, detail_panels=[panel])
    assert "width" not in components[0].dimensions


def test_width_aliasing_does_not_apply_to_bellows():
    # Unlike Shroud, Bellows's real width (340mm on the real WO 9374 indent) never appears
    # anywhere in that drawing's own text - confirmed by direct search - so whatever plain
    # number the magnitude-based Thk/L fallback guessed for Bellows's own panel "l" is some
    # OTHER, unrelated callout (e.g. convolution pitch), not a genuine width. Aliasing it would
    # feed the calc engine a wrong width instead of correctly reporting it as unobtainable.
    row = BomRow(description="Bellows", qty="1", size="", confidence=0.8)
    panel = DetailPanel(
        label_text="BELLOW DETAIL", component_name="BELLOW",
        dimensions={"od": "559", "thk": "20", "l": "20"}, needs_confirmation=True,
    )
    components = _rows_to_components([row], page_number=1, detail_panels=[panel])
    assert "width" not in components[0].dimensions


def test_merge_combines_raw_tokens_but_replaces_dimensions():
    # Regression: PyMuPDF's own block-join can merge Bellows's real "1ply x 0.6 mm" ply-
    # thickness callout with an adjacent, unrelated number into one unparseable token on the
    # structural side (confirmed on the real WO 9374 drawing: "20" + "1ply x 0.6 mm" ->
    # "201ply x 0.6 mm") - while the OCR-region pass happened to read that same callout as a
    # separate, clean token. calc_engine_service.parse_bellows_ply_text needs that clean token
    # (it scans a component's raw-token-built assumption_text for it), so raw_tokens must still
    # be combined from both sources even though dimensions themselves are structural-only.
    ocr_panel = DetailPanel(
        label_text="BELLOW DETAIL", component_name="BELLOW",
        dimensions={"od": "539"},  # a less-trusted OCR-pixel reading
        raw_tokens=["1ply x 0.6 mm", "Ø 539"],
    )
    structural_panel = DetailPanel(
        label_text="BELLOW  DETAIL", component_name="BELLOW",
        dimensions={"od": "559", "l": "20"},  # the more-trusted structural reading
        raw_tokens=["201ply x 0.6 mm", "Ø 559"],
    )
    merged = _merge_detail_panels([ocr_panel], [structural_panel])
    assert len(merged) == 1
    assert merged[0].dimensions == {"od": "559", "l": "20"}  # structural wins outright
    assert "1ply x 0.6 mm" in merged[0].raw_tokens  # but the OCR side's clean token survives

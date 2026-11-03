"""Regression test for the bug where Thickness and Length were silently dropped whenever a
BOM row's own SIZE cell already had any text (even just an OD reading): the matching detail
panel's structured od/id/thk/l dict was only ever consulted when `dimensions` was still empty,
so a row with a partial/OD-only SIZE cell never picked up Thickness/Length from the panel at
all - see app.providers.deterministic_provider._rows_to_components."""
from app.providers.deterministic_provider import _rows_to_components
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

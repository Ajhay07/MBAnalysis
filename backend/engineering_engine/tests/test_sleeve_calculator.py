from engineering_engine.calculations import sleeve_calculator
from engineering_engine.validation.dimension_validator import DimensionStatus


def test_sleeve_dimensions_match_wo9374_indent_reference():
    # CORRECTED after review: the indent's own SIZE column gives Sleeve OD as 509, not the
    # 539 the auto-extractor reads off the panel's two concentric circles.
    dims = sleeve_calculator.sleeve_dimensions(od=509, thickness=1.5, length=150)
    assert dims["od"].value == 509
    assert dims["thickness"].value == 1.5
    assert dims["length"].value == 150
    assert all(d.status == DimensionStatus.VERIFIED for d in dims.values())
    assert "mid_pipe_interface_reference" not in dims


def test_mid_pipe_interface_reference_kept_separate_and_flagged():
    # The auto-extracted 539mm value is never folded into `od` - it's its own field, always
    # REVIEW_REQUIRED since its real identity (very likely Mid Pipe's own ID) isn't confirmed.
    dims = sleeve_calculator.sleeve_dimensions(od=509, thickness=1.5, length=150, mid_pipe_interface_reference=539)
    assert dims["od"].value == 509
    assert dims["mid_pipe_interface_reference"].value == 539
    assert dims["od"].value != dims["mid_pipe_interface_reference"].value
    assert dims["mid_pipe_interface_reference"].status == DimensionStatus.REVIEW_REQUIRED
    assert "Mid Pipe" in dims["mid_pipe_interface_reference"].notes


def test_missing_od_reports_missing():
    dims = sleeve_calculator.sleeve_dimensions(od=None, thickness=1.5, length=150)
    assert dims["od"].status == DimensionStatus.MISSING

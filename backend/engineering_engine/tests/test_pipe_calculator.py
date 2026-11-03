from engineering_engine.calculations import pipe_calculator
from engineering_engine.validation.dimension_validator import DimensionStatus


def test_mid_pipe_id_matches_wo9374_reference():
    result = pipe_calculator.calculate_id(od=559, thickness=10, component="Mid Pipe")
    assert result.value == 539
    assert result.status == DimensionStatus.CALCULATED


def test_end_pipe_id_matches_wo9374_reference():
    result = pipe_calculator.calculate_id(od=559, thickness=10, component="End Pipe")
    assert result.value == 539


def test_id_missing_thickness():
    result = pipe_calculator.calculate_id(od=559, thickness=None, component="Mid Pipe")
    assert result.status == DimensionStatus.MISSING
    assert "thickness" in result.notes


def test_pipe_dimensions_full_set_matches_wo9374_mid_pipe_reference():
    dims = pipe_calculator.pipe_dimensions(od=559, thickness=10, length=150, component="Mid Pipe")
    assert dims["od"].value == 559
    assert dims["thickness"].value == 10
    assert dims["length"].value == 150
    assert dims["id"].value == 539
    assert all(d.status in (DimensionStatus.VERIFIED, DimensionStatus.CALCULATED) for d in dims.values())


def test_pipe_dimensions_missing_length_reports_missing_not_zero():
    dims = pipe_calculator.pipe_dimensions(od=559, thickness=10, length=None, component="End Pipe")
    assert dims["length"].status == DimensionStatus.MISSING
    assert dims["length"].value is None

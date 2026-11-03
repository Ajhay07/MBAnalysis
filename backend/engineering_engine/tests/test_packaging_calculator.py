from engineering_engine.calculations import packaging_calculator
from engineering_engine.validation.dimension_validator import DimensionStatus


def test_box_length_adds_250mm_allowance():
    result = packaging_calculator.calculate_box_length(assembly_length=1000)
    assert result.value == 1250
    assert result.status == DimensionStatus.CALCULATED


def test_box_length_missing_assembly_length():
    result = packaging_calculator.calculate_box_length(None)
    assert result.status == DimensionStatus.MISSING


def test_breadth_and_width_never_derived_from_length_formula():
    dims = packaging_calculator.box_breadth_and_width(breadth=33, width=25)
    assert dims["breadth"].value == 33
    assert dims["width"].value == 25
    assert dims["breadth"].status == DimensionStatus.VERIFIED
    assert "not the length allowance formula" in dims["breadth"].notes


def test_breadth_and_width_missing_reports_missing():
    dims = packaging_calculator.box_breadth_and_width(None, None)
    assert dims["breadth"].status == DimensionStatus.MISSING
    assert dims["width"].status == DimensionStatus.MISSING

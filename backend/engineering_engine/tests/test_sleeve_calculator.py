from engineering_engine.calculations import sleeve_calculator
from engineering_engine.validation.dimension_validator import DimensionStatus


def test_sleeve_dimensions_match_wo9374_reference():
    dims = sleeve_calculator.sleeve_dimensions(od=539, blank_diameter=509, thickness=1.5, length=150)
    assert dims["od"].value == 539
    assert dims["blank_diameter"].value == 509
    assert dims["thickness"].value == 1.5
    assert dims["length"].value == 150
    assert all(d.status == DimensionStatus.VERIFIED for d in dims.values())


def test_od_and_blank_diameter_are_never_the_same_field():
    # Spec's explicit warning: don't assume 509mm is the OD without verifying the reference.
    dims = sleeve_calculator.sleeve_dimensions(od=539, blank_diameter=509, thickness=1.5, length=150)
    assert dims["od"].value != dims["blank_diameter"].value
    assert "blank-calculation diameter" in dims["blank_diameter"].notes


def test_missing_blank_diameter_reports_missing():
    dims = sleeve_calculator.sleeve_dimensions(od=539, blank_diameter=None, thickness=1.5, length=150)
    assert dims["blank_diameter"].status == DimensionStatus.MISSING

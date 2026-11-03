from engineering_engine.calculations import shroud_calculator
from engineering_engine.validation.dimension_validator import DimensionStatus


def test_base_circumference_matches_wo9374_reference():
    result = shroud_calculator.calculate_base_circumference(od=683)
    assert result.value == 2144.62  # spec: 683 * 3.14
    assert result.status == DimensionStatus.CALCULATED


def test_base_circumference_missing_od():
    result = shroud_calculator.calculate_base_circumference(od=None)
    assert result.status == DimensionStatus.MISSING


def test_final_length_never_invents_the_unapproved_allowance():
    # Spec: the 2190 (indent) vs 2144.62 (calculated) gap must be flagged, not silently applied.
    base = shroud_calculator.calculate_base_circumference(od=683)
    final = shroud_calculator.calculate_final_length(base.value, reference_indent_length=2190)
    assert final.status == DimensionStatus.REVIEW_REQUIRED
    assert final.value == 2144.62  # reports base length, never 2190 or a reverse-engineered allowance
    assert "45.38" in final.notes


def test_final_length_missing_base_length():
    result = shroud_calculator.calculate_final_length(None)
    assert result.status == DimensionStatus.MISSING

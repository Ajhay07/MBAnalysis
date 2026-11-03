from engineering_engine.calculations import bellows_calculator
from engineering_engine.validation.dimension_validator import DimensionStatus


def test_blank_length_matches_wo9374_reference():
    result = bellows_calculator.calculate_blank_length(od=559)
    assert result.value == 1765  # spec: (559*3.14)+10 = 1765.26 -> rounds to 1765
    assert result.status == DimensionStatus.CALCULATED
    assert result.formula == "(od * 3.14) + 10"


def test_blank_length_missing_od():
    result = bellows_calculator.calculate_blank_length(od=None)
    assert result.status == DimensionStatus.MISSING
    assert result.value is None


def test_sheet_width_missing_pitch_and_depth_never_invents_a_value():
    # Spec explicit requirement: never reverse-engineer q/w from the indent's 340mm reference.
    result = bellows_calculator.calculate_sheet_width(q=None, w=None, n=10)
    assert result.status == DimensionStatus.MISSING
    assert result.value is None
    assert "pitch_q" in result.notes
    assert "depth_w" in result.notes


def test_sheet_width_with_inputs_stays_review_required_pending_convolution_confirmation():
    result = bellows_calculator.calculate_sheet_width(q=50, w=20, n=10)
    assert result.value is not None
    assert result.status == DimensionStatus.REVIEW_REQUIRED


def test_thickness_from_plies_matches_wo9374_reference():
    result = bellows_calculator.calculate_thickness(num_plies=1, ply_thickness_mm=0.6)
    assert result.value == 0.6
    assert result.status == DimensionStatus.VERIFIED  # directly specified, not derived


def test_thickness_missing_inputs():
    result = bellows_calculator.calculate_thickness(None, 0.6)
    assert result.status == DimensionStatus.MISSING


def test_convolution_count_parses_5_plus_5_as_10():
    n, result = bellows_calculator.interpret_convolution_count("- 5+5 NO. OF CONVOLUTES")
    assert n == 10
    assert result.status == DimensionStatus.REVIEW_REQUIRED  # counting convention unconfirmed


def test_convolution_count_missing_text():
    n, result = bellows_calculator.interpret_convolution_count(None)
    assert n is None
    assert result.status == DimensionStatus.MISSING

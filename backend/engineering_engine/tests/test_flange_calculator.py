from engineering_engine.calculations import flange_calculator
from engineering_engine.validation.dimension_validator import DimensionStatus


def test_housing_flange_dimensions_match_wo9374_reference():
    dims = flange_calculator.housing_flange_dimensions(
        od=810, id_=562, thickness=25, pcd=734, hole_diameter=34,
        hole_count_drawing=2, hole_count_indent=2,
    )
    assert dims["od"].value == 810
    assert dims["id"].value == 562
    assert dims["thickness"].value == 25
    assert dims["pcd"].value == 734
    assert dims["hole_diameter"].value == 34
    assert dims["hole_count"].status == DimensionStatus.VERIFIED


def test_housing_flange_hole_count_mismatch_is_flagged_not_resolved():
    dims = flange_calculator.housing_flange_dimensions(
        od=810, id_=562, thickness=25, pcd=734, hole_diameter=34,
        hole_count_drawing=16, hole_count_indent=2,
    )
    assert dims["hole_count"].status == DimensionStatus.REVIEW_REQUIRED
    assert "drawing=16" in str(dims["hole_count"].value)
    assert "indent=2" in str(dims["hole_count"].value)


def test_limit_rod_length_applies_pending_allowance_but_flags_it():
    result = flange_calculator.calculate_limit_rod_length(cad_length=595)
    assert result.value == 610  # 595 + 15
    assert result.status == DimensionStatus.REVIEW_REQUIRED
    assert "pending_approval" in result.notes


def test_limit_rod_missing_cad_length():
    result = flange_calculator.calculate_limit_rod_length(None)
    assert result.status == DimensionStatus.MISSING


def test_collar_from_detail_b_is_verified():
    dims = flange_calculator.collar_dimensions(diameter=20, length=1790, source_detail="Detail B")
    assert dims["diameter"].status == DimensionStatus.VERIFIED
    assert dims["length"].status == DimensionStatus.VERIFIED


def test_collar_not_from_detail_b_is_flagged():
    # Manufacturing instruction: must come from Detail B, never the overall assembly view.
    dims = flange_calculator.collar_dimensions(diameter=20, length=1790, source_detail="Assembly View")
    assert dims["diameter"].status == DimensionStatus.REVIEW_REQUIRED
    assert "Detail B" in dims["diameter"].notes

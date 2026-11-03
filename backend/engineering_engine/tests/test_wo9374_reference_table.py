"""Compares the engine's calculated values against the reference indent table from spec
section 10. These are unit-level checks on the calculators with WO 9374's own known inputs
plugged in directly (no PDF/OCR involved) - exactly what the spec asks for ("Create unit tests
for every formula. Compare calculated values against the reference indent. Flag discrepancies
rather than modifying the expected values to force a match."). Two entries (Shroud's allowance,
M8 Bolt & Nut's quantity) are EXPECTED to show a flagged discrepancy, not a match - asserted
explicitly below rather than silently passing.
"""
from engineering_engine.calculations import (
    bellows_calculator, flange_calculator, packaging_calculator, pipe_calculator, shroud_calculator,
    sleeve_calculator,
)
from engineering_engine.validation.bom_validator import calculate_total_quantity
from engineering_engine.validation.calculation_validator import compare_to_reference
from engineering_engine.validation.dimension_validator import DimensionStatus


def test_bellows_matches_1765_x_340_x_06_except_width_which_stays_missing():
    length = bellows_calculator.calculate_blank_length(od=559)
    thickness = bellows_calculator.calculate_thickness(num_plies=1, ply_thickness_mm=0.6)
    n, _ = bellows_calculator.interpret_convolution_count("5+5 NO. OF CONVOLUTES")
    width = bellows_calculator.calculate_sheet_width(q=None, w=None, n=n)

    assert compare_to_reference(length, 1765).matches
    assert compare_to_reference(thickness, 0.6).matches
    # Width (340mm reference) is NOT independently verifiable without q/w - must stay MISSING,
    # never silently matched by reverse-engineering inputs to hit 340.
    assert width.status == DimensionStatus.MISSING


def test_sleeve_matches_509_x_15_x_150():
    dims = sleeve_calculator.sleeve_dimensions(od=539, blank_diameter=509, thickness=1.5, length=150)
    assert compare_to_reference(dims["blank_diameter"], 509).matches
    assert compare_to_reference(dims["thickness"], 1.5).matches
    assert compare_to_reference(dims["length"], 150).matches


def test_mid_pipe_matches_559_x_10_x_150():
    dims = pipe_calculator.pipe_dimensions(od=559, thickness=10, length=150, component="Mid Pipe")
    assert compare_to_reference(dims["od"], 559).matches
    assert compare_to_reference(dims["thickness"], 10).matches
    assert compare_to_reference(dims["length"], 150).matches
    assert compare_to_reference(dims["id"], 539).matches


def test_end_pipe_matches_559_x_10_x_125():
    dims = pipe_calculator.pipe_dimensions(od=559, thickness=10, length=125, component="End Pipe")
    assert compare_to_reference(dims["od"], 559).matches
    assert compare_to_reference(dims["length"], 125).matches
    assert compare_to_reference(dims["id"], 539).matches


def test_housing_flange_matches_od810_id562_thickness25():
    dims = flange_calculator.housing_flange_dimensions(od=810, id_=562, thickness=25, pcd=734, hole_diameter=34)
    assert compare_to_reference(dims["od"], 810).matches
    assert compare_to_reference(dims["id"], 562).matches
    assert compare_to_reference(dims["thickness"], 25).matches
    assert compare_to_reference(dims["pcd"], 734).matches


def test_shroud_flags_the_allowance_discrepancy_instead_of_matching_2190():
    base = shroud_calculator.calculate_base_circumference(od=683)
    final = shroud_calculator.calculate_final_length(base.value, reference_indent_length=2190)
    # EXPECTED to NOT match 2190 - the allowance is unapproved, so the engine reports the base
    # circumference (2144.62) and flags the gap rather than matching the reference.
    comparison = compare_to_reference(final, 2190)
    assert comparison.matches is False
    assert final.status == DimensionStatus.REVIEW_REQUIRED
    assert comparison.difference == -45.38


def test_wooden_box_length_formula_applied_to_length_only():
    # Reference indent: 33" x 33" x 25" (= 838.2mm x 838.2mm x 635mm). The formula and its
    # 250mm allowance are in millimeters (manufacturing_rules.json) - calculate_box_length
    # always works in mm; converting to/from inches is the caller's job, not the calculator's.
    indent_length_mm = 33 * 25.4
    assembly_length_mm = indent_length_mm - 250  # the un-allowanced package length
    result = packaging_calculator.calculate_box_length(assembly_length=assembly_length_mm)
    assert round(result.value, 1) == round(indent_length_mm, 1)


def test_m8_bolt_and_nut_quantity_flags_32_vs_48_discrepancy():
    result = calculate_total_quantity("M8 Bolt & Nut", quantity_per_assembly=8, number_of_assemblies=4, reference_indent_total=48)
    assert result.calculated_total == 32
    assert result.discrepancy is True

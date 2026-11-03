from engineering_engine.validation.bom_validator import calculate_bom, calculate_total_quantity, reference_only_quantity


def test_total_quantity_is_plain_multiplication():
    result = calculate_total_quantity("Mid Pipe", quantity_per_assembly=1, number_of_assemblies=4)
    assert result.calculated_total == 4
    assert result.discrepancy is False


def test_m8_bolt_and_nut_discrepancy_is_flagged_not_silently_replaced():
    # Spec: CAD BOM says 8/assembly -> 32 total for 4 assemblies, but WO 9374's indent says 48.
    result = calculate_total_quantity("M8 Bolt & Nut", quantity_per_assembly=8, number_of_assemblies=4, reference_indent_total=48)
    assert result.calculated_total == 32
    assert result.reference_indent_total == 48
    assert result.discrepancy is True


def test_calculate_bom_wo9374_reference_table():
    rows = [
        ("Bellows", 2), ("Sleeve", 2), ("Mid Pipe", 1), ("End Pipe", 2), ("Housing Flange", 2),
        ("Limit Rod", 2), ("Nut and Locknut", 16), ("Shroud", 2), ("Shroud Support", 8),
        ("M8 Bolt and Nut", 8), ("Collar", 4),
    ]
    results = calculate_bom(rows, number_of_assemblies=4, reference_totals={"M8 Bolt and Nut": 48})
    totals = {r.component: r.calculated_total for r in results}
    assert totals["Bellows"] == 8
    assert totals["Sleeve"] == 8
    assert totals["Mid Pipe"] == 4
    assert totals["End Pipe"] == 8
    assert totals["Housing Flange"] == 8
    assert totals["Limit Rod"] == 8
    assert totals["Nut and Locknut"] == 64
    assert totals["Shroud"] == 8
    assert totals["Shroud Support"] == 32
    assert totals["M8 Bolt and Nut"] == 32  # calculated, distinct from the indent's 48
    assert totals["Collar"] == 16
    discrepancies = {r.component for r in results if r.discrepancy}
    assert discrepancies == {"M8 Bolt and Nut"}


def test_reference_only_quantity_preserves_indent_qty_with_no_per_assembly_figure():
    # CORRECTED after review: Filler Wire (84 pcs), Electrode (282 pcs), Stiffener (16 Nos.)
    # were previously dropped entirely because the CAD BOM has no per-assembly figure for them.
    result = reference_only_quantity("Filler Wire", 84)
    assert result.reference_indent_total == 84
    assert result.quantity_per_assembly is None
    assert result.calculated_total is None
    assert result.discrepancy is False

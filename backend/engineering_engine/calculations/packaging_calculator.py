"""Wooden Box packaging: length is calculated (assembly length + approved 250mm allowance);
breadth and width come from the approved packaging layout/clearances, a separate source this
module never tries to derive from the same formula.
"""
from __future__ import annotations

from engineering_engine.calculations.rules_loader import load_rules
from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus, missing


def calculate_box_length(assembly_length: float | None, component: str = "Wooden Box") -> DimensionResult:
    """box_length = assembly/package length + 250mm. Approved for length only - see
    manufacturing_rules.json's wooden_box.length_allowance."""
    if assembly_length is None:
        return missing("length", component, "assembly_length input required")
    rule = load_rules()["wooden_box"]["length_allowance"]
    value = assembly_length + rule["allowance_mm"]
    return DimensionResult(
        name="length", value=value, unit="mm", status=DimensionStatus.CALCULATED,
        component=component, extraction_method="calculated",
        formula="assembly_length + allowance_mm", inputs={"assembly_length": assembly_length, "allowance_mm": rule["allowance_mm"]},
    )


def box_breadth_and_width(
    breadth: float | None, width: float | None, component: str = "Wooden Box",
) -> dict[str, DimensionResult]:
    """Both come from the approved packaging layout/clearances - never computed from the
    same 250mm length allowance. VERIFIED when supplied, MISSING otherwise."""
    results: dict[str, DimensionResult] = {}
    for name, value in (("breadth", breadth), ("width", width)):
        if value is None:
            results[name] = missing(name, component, "From approved packaging layout/clearances - not yet supplied")
        else:
            results[name] = DimensionResult(
                name=name, value=value, unit="in", status=DimensionStatus.VERIFIED,
                component=component, extraction_method="manual",
                notes="From approved packaging layout/clearances, not the length allowance formula.",
            )
    return results

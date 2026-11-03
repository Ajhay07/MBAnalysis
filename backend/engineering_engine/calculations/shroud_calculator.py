"""Shroud flat-pattern length: base circumference is an approved formula; the gap between that
and the real indent reference is an UNAPPROVED allowance that must stay flagged, never silently
assumed. See manufacturing_rules.json's shroud.length_allowance for why allowance_mm is null.
"""
from __future__ import annotations

from engineering_engine.calculations.rules_loader import load_rules
from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus, missing


def calculate_base_circumference(od: float | None, component: str = "Shroud") -> DimensionResult:
    """base_length = OD * pi_approx. Approved - this part alone, with no allowance, is a plain
    geometric fact."""
    if od is None:
        return missing("base_length", component, "OD input required")
    rule = load_rules()["shroud"]["circumference_length"]
    value = round(od * rule["pi_approx"], 2)
    return DimensionResult(
        name="base_length", value=value, unit="mm", status=DimensionStatus.CALCULATED,
        component=component, extraction_method="calculated",
        formula=f"od * {rule['pi_approx']}", inputs={"od": od},
    )


def calculate_final_length(
    base_length: float | None, reference_indent_length: float | None = None, component: str = "Shroud",
) -> DimensionResult:
    """final_length = base_length + approved_allowance. allowance_mm is null in
    manufacturing_rules.json (unapproved) - this function NEVER invents one from the gap
    against a reference indent value. It reports the base length, the gap if a reference is
    supplied, and REVIEW_REQUIRED, same as the spec's own worked example (2190 - 2144.62 =
    45.38mm, treated as an allowance requiring verification, not auto-applied)."""
    if base_length is None:
        return missing("length", component, "base_length required (see calculate_base_circumference)")
    rule = load_rules()["shroud"]["length_allowance"]
    if rule["allowance_mm"] is not None:
        value = round(base_length + rule["allowance_mm"], 2)
        return DimensionResult(
            name="length", value=value, unit="mm", status=DimensionStatus.CALCULATED,
            component=component, extraction_method="calculated",
            formula="base_length + allowance_mm", inputs={"base_length": base_length, "allowance_mm": rule["allowance_mm"]},
        )
    notes = (
        f"No approved allowance - allowance_mm is unset in manufacturing_rules.json ({rule['source']}). "
        "Reporting base_length only; the real indent length is a separate, unapproved reference."
    )
    if reference_indent_length is not None:
        gap = round(reference_indent_length - base_length, 2)
        notes += f" Gap vs. supplied reference indent length ({reference_indent_length}mm): {gap}mm."
    return DimensionResult(
        name="length", value=base_length, unit="mm", status=DimensionStatus.REVIEW_REQUIRED,
        component=component, extraction_method="calculated",
        formula="od * pi_approx (allowance not yet approved)",
        inputs={"base_length": base_length, "reference_indent_length": reference_indent_length},
        notes=notes,
    )

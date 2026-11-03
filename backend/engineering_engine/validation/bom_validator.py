"""BOM quantity calculation: total_quantity = quantity_per_assembly * number_of_assemblies -
plain arithmetic, same principle as the main app's own indent_service.py. The one thing this
module adds beyond that multiplication is discrepancy flagging: when a reference indent
quantity is supplied and disagrees with the calculated total, that is reported as its own
result and the reference quantity is NEVER silently overwritten with the calculated one (per
spec: "Flag this discrepancy for human verification. Do not automatically replace the indent
quantity with the calculated BOM quantity.").
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QuantityResult:
    component: str
    quantity_per_assembly: float | None
    number_of_assemblies: float | None
    calculated_total: float | None
    reference_indent_total: float | None = None
    discrepancy: bool = False

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "quantity_per_assembly": self.quantity_per_assembly,
            "number_of_assemblies": self.number_of_assemblies,
            "calculated_total": self.calculated_total,
            "reference_indent_total": self.reference_indent_total,
            "discrepancy": self.discrepancy,
        }


def calculate_total_quantity(
    component: str, quantity_per_assembly: float, number_of_assemblies: float,
    reference_indent_total: float | None = None,
) -> QuantityResult:
    calculated_total = quantity_per_assembly * number_of_assemblies
    discrepancy = reference_indent_total is not None and reference_indent_total != calculated_total
    return QuantityResult(
        component=component,
        quantity_per_assembly=quantity_per_assembly,
        number_of_assemblies=number_of_assemblies,
        calculated_total=calculated_total,
        reference_indent_total=reference_indent_total,
        discrepancy=discrepancy,
    )


def reference_only_quantity(component: str, reference_indent_total: float) -> QuantityResult:
    """For components whose quantity is only ever printed on the indent (e.g. Filler Wire,
    Electrode, Stiffener), with no per-assembly CAD BOM figure to multiply - previously
    dropped entirely (quantity_per_assembly=None meant the whole quantity block was skipped).
    Preserves the reference figure instead of discarding it just because the calculated side
    is unavailable."""
    return QuantityResult(
        component=component, quantity_per_assembly=None, number_of_assemblies=None,
        calculated_total=None, reference_indent_total=reference_indent_total, discrepancy=False,
    )


def calculate_bom(
    rows: list[tuple[str, float]], number_of_assemblies: float,
    reference_totals: dict[str, float] | None = None,
) -> list[QuantityResult]:
    """`rows` is [(component, quantity_per_assembly), ...]; `reference_totals` optionally maps
    component -> the indent's own printed total, for discrepancy checking (e.g. WO 9374's M8
    Bolt & Nut: CAD BOM says 8/assembly * 4 = 32, but the indent prints 48 - both are kept in
    the result rather than one silently winning)."""
    reference_totals = reference_totals or {}
    return [
        calculate_total_quantity(component, qty, number_of_assemblies, reference_totals.get(component))
        for component, qty in rows
    ]

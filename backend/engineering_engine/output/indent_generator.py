"""Assembles per-component DimensionResults + quantity results into the structured JSON shape
from spec section 9. Never computes anything itself - purely a formatting/aggregation layer
over engineering_engine.calculations and engineering_engine.validation.bom_validator.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engineering_engine.validation.bom_validator import QuantityResult
from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus


@dataclass
class ComponentOutput:
    name: str
    material: str = ""
    dimensions: dict[str, DimensionResult] = field(default_factory=dict)
    quantity: QuantityResult | None = None
    missing_inputs: list[str] = field(default_factory=list)
    extra_notes: list[str] = field(default_factory=list)

    def overall_status(self) -> str:
        """A component is only as good as its worst dimension: any MISSING -> MISSING, else
        any REVIEW_REQUIRED -> REVIEW_REQUIRED, else any CALCULATED -> CALCULATED, else
        VERIFIED. Never averages or hides a bad status behind good ones."""
        statuses = {d.status for d in self.dimensions.values()}
        if not statuses:
            return DimensionStatus.MISSING.value
        for s in (DimensionStatus.MISSING, DimensionStatus.REVIEW_REQUIRED, DimensionStatus.CALCULATED):
            if s in statuses:
                return s.value
        return DimensionStatus.VERIFIED.value

    def to_dict(self) -> dict:
        dims = {name: d.value for name, d in self.dimensions.items()}
        calculation = {
            name: {"formula": d.formula, "inputs": d.inputs}
            for name, d in self.dimensions.items() if d.formula
        }
        missing_inputs = sorted(set(self.missing_inputs) | {
            d.name for d in self.dimensions.values() if d.status == DimensionStatus.MISSING
        })
        return {
            "name": self.name,
            "material": self.material,
            "dimensions": dims,
            "dimension_detail": {name: d.to_dict() for name, d in self.dimensions.items()},
            "calculation": calculation or None,
            "quantity_per_assembly": self.quantity.quantity_per_assembly if self.quantity else None,
            "total_quantity": self.quantity.calculated_total if self.quantity else None,
            "reference_indent_quantity": self.quantity.reference_indent_total if self.quantity else None,
            "quantity_discrepancy": self.quantity.discrepancy if self.quantity else False,
            "status": self.overall_status(),
            "missing_inputs": missing_inputs,
            "notes": self.extra_notes or None,
        }


def generate_indent_json(work_order: str, assembly_quantity: float, components: list[ComponentOutput]) -> dict:
    return {
        "work_order": work_order,
        "assembly_quantity": assembly_quantity,
        "components": [c.to_dict() for c in components],
    }

"""Assembles per-component DimensionResults + quantity results into the structured JSON shape
from spec section 9. Never computes anything itself - purely a formatting/aggregation layer
over engineering_engine.calculations and engineering_engine.validation.bom_validator.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engineering_engine.validation.bom_validator import QuantityResult
from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus


# extraction_method values grouped into the four source categories the review asked to
# distinguish (A/B/C/D): cad_vector (native CAD/PDF vector text, not yet implemented - see
# cad_extractor.py), ocr_detail_panel (OCR reading a CAD detail panel - app.services.
# drawing_detail_extractor), calculated (a manufacturing formula), manual (typed in, priority
# #5 of the extraction chain - this engine never pretends a manual value was automated).
_METHOD_CATEGORY = {
    "cad_vector": "cad_extracted",
    "ocr_detail_panel": "ocr_extracted",
    "calculated": "manufacturing_calculated",
    "manual": "manually_supplied",
}


@dataclass
class ComponentOutput:
    name: str
    material: str = ""
    dimensions: dict[str, DimensionResult] = field(default_factory=dict)
    # Reference-indent values for this component, kept SEPARATE from `dimensions` (the engine's
    # own best-available/proposed values) - e.g. Bellows width's indent reference (340mm) next
    # to a MISSING calculated width, or Shroud's indent length (2190mm) next to the calculated
    # base circumference (2144.62mm). Never used to silently fill a gap in `dimensions`.
    reference_dimensions: dict[str, float | str] = field(default_factory=dict)
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
        final_proposed = {name: d.value for name, d in self.dimensions.items()}
        calculation = {
            name: {"formula": d.formula, "inputs": d.inputs}
            for name, d in self.dimensions.items() if d.formula
        }
        missing_inputs = sorted(set(self.missing_inputs) | {
            d.name for d in self.dimensions.values() if d.status == DimensionStatus.MISSING
        })
        # By-source breakdown, grouping dimension_detail's own extraction_method per field -
        # "do not overwrite source dimensions with calculated dimensions": these are read
        # straight off dimension_detail, never derived from/blended with final_proposed.
        by_source: dict[str, dict] = {}
        for name, d in self.dimensions.items():
            if d.value is None:
                continue
            category = _METHOD_CATEGORY.get(d.extraction_method, d.extraction_method or "unknown")
            by_source.setdefault(category, {})[name] = d.value
        return {
            "name": self.name,
            "material": self.material,
            "final_proposed_dimensions": final_proposed,
            "dimensions_by_source": by_source,
            "reference_indent_dimensions": self.reference_dimensions or None,
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

"""Status model for every dimension the engine produces.

Four statuses, matching the spec exactly:
  VERIFIED        - directly extracted from an identifiable CAD dimension/explicit spec and
                     cross-checked (e.g. against the indent reference), no formula involved.
  CALCULATED      - derived from an approved manufacturing formula with all required inputs
                     present. Formula/inputs are retained on the result, never discarded.
  REVIEW_REQUIRED - an inferred value, a discrepancy against a reference, an unapproved or
                     pending-approval allowance, an ambiguous dimension, or uncertain
                     component association. This is the DEFAULT whenever anything is uncertain
                     - never silently upgraded to VERIFIED/CALCULATED to "look complete".
  MISSING         - a required input is unavailable; the engine never substitutes an
                     invented number to fill the gap.

A DimensionResult is the engine's atomic unit of output: one value (or lack of one), with its
full provenance (formula, inputs, source location, extraction method) attached - "every
calculated value must retain its formula, inputs and calculation history" per spec.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DimensionStatus(str, Enum):
    VERIFIED = "VERIFIED"
    CALCULATED = "CALCULATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    MISSING = "MISSING"


@dataclass
class DimensionResult:
    """One dimension's full provenance. `value` is None exactly when status is MISSING -
    that pairing is enforced by `__post_init__`, so a MISSING result can never carry a
    half-filled-in number and a VERIFIED/CALCULATED/REVIEW_REQUIRED one is never silently
    blank."""
    name: str                    # e.g. "length", "thickness", "od", "id", "pcd"
    value: float | str | None
    unit: str
    status: DimensionStatus
    component: str = ""          # e.g. "Bellows", "Mid Pipe"
    detail_view: str = ""        # which CAD detail/view this came from, e.g. "Bellow Detail"
    extraction_method: str = ""  # "cad_vector" | "ocr_detail_panel" | "calculated" | "manual"
    formula: str = ""
    inputs: dict = field(default_factory=dict)
    source_location: str = ""    # free text: page/region/label this was read or derived from
    notes: str = ""

    def __post_init__(self):
        if self.status == DimensionStatus.MISSING and self.value is not None:
            raise ValueError(f"{self.component}.{self.name}: MISSING status must not carry a value")
        if self.status != DimensionStatus.MISSING and self.value is None:
            raise ValueError(f"{self.component}.{self.name}: non-MISSING status must carry a value")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "status": self.status.value,
            "extraction_method": self.extraction_method,
            "formula": self.formula or None,
            "inputs": self.inputs or None,
            "source_location": self.source_location or None,
            "notes": self.notes or None,
        }


def missing(name: str, component: str = "", notes: str = "") -> DimensionResult:
    """Shorthand for the one case every calculator hits often: a required input absent, so
    the dependent dimension can't be produced at all. Never a 0 or an empty string standing
    in for "unknown" - always this explicit MISSING result."""
    return DimensionResult(
        name=name, value=None, unit="", status=DimensionStatus.MISSING,
        component=component, notes=notes,
    )

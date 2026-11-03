"""Cross-checks a calculated DimensionResult against a known reference value (e.g. the WO 9374
indent sheet's own printed numbers) - used by the test suite and by indent_generator.py to
annotate results with how closely a calculation matched the real reference, without ever
changing the calculated value to force a match ("Compare calculated values against the
reference indent. Flag discrepancies rather than modifying the expected values.").
"""
from __future__ import annotations

from dataclasses import dataclass

from engineering_engine.validation.dimension_validator import DimensionResult


@dataclass
class ComparisonResult:
    name: str
    calculated_value: float | str | None
    reference_value: float | str | None
    matches: bool
    difference: float | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name, "calculated_value": self.calculated_value,
            "reference_value": self.reference_value, "matches": self.matches,
            "difference": self.difference,
        }


def compare_to_reference(result: DimensionResult, reference_value: float | str | None, tolerance: float = 0.5) -> ComparisonResult:
    if result.value is None or reference_value is None:
        return ComparisonResult(result.name, result.value, reference_value, matches=False)
    if isinstance(result.value, (int, float)) and isinstance(reference_value, (int, float)):
        diff = round(result.value - reference_value, 3)
        return ComparisonResult(result.name, result.value, reference_value, matches=abs(diff) <= tolerance, difference=diff)
    matches = str(result.value).strip() == str(reference_value).strip()
    return ComparisonResult(result.name, result.value, reference_value, matches=matches)

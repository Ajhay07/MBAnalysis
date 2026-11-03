"""Mid Pipe / End Pipe: OD, Thickness and Length are read directly off the CAD detail (no
formula); ID is the one calculated value, from standard pipe wall geometry. Shared by both
components since MB uses the identical formula for each - the only difference is which
component name/detail view the caller passes in.
"""
from __future__ import annotations

from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus, missing


def calculate_id(od: float | None, thickness: float | None, component: str) -> DimensionResult:
    """ID = OD - (2 * Thickness). No manufacturing allowance unless explicitly specified."""
    if od is None or thickness is None:
        missing_names = [n for n, v in (("od", od), ("thickness", thickness)) if v is None]
        return missing("id", component, f"Required inputs not available: {', '.join(missing_names)}")
    value = od - (2 * thickness)
    return DimensionResult(
        name="id", value=value, unit="mm", status=DimensionStatus.CALCULATED,
        component=component, extraction_method="calculated",
        formula="od - (2 * thickness)", inputs={"od": od, "thickness": thickness},
    )


def pipe_dimensions(
    od: float | None, thickness: float | None, length: float | None, component: str,
    detail_view: str = "", extraction_method: str = "ocr_detail_panel",
    extraction_methods: dict[str, str] | None = None,
) -> dict[str, DimensionResult]:
    """OD/Thickness/Length pass through as VERIFIED when present (read directly off the CAD
    detail, no calculation); MISSING when not. ID is always derived via calculate_id.

    `extraction_methods` optionally overrides the per-field method (e.g.
    {"thickness": "manual"} when thickness came from a reviewer's manual input rather than the
    CAD detail panel OCR), so a mixed-source call (some fields auto-extracted, others typed in)
    never mislabels a manual value as OCR-verified. Falls back to `extraction_method` for any
    field not in the override dict - unchanged behavior for every existing caller."""
    results: dict[str, DimensionResult] = {}
    methods = extraction_methods or {}
    for name, value in (("od", od), ("thickness", thickness), ("length", length)):
        if value is None:
            results[name] = missing(name, component)
        else:
            results[name] = DimensionResult(
                name=name, value=value, unit="mm", status=DimensionStatus.VERIFIED,
                component=component, detail_view=detail_view, extraction_method=methods.get(name, extraction_method),
            )
    results["id"] = calculate_id(od, thickness, component)
    return results

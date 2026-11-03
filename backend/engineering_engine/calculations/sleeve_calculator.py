"""Sleeve: no formula - every dimension comes directly from the supplied indent/sleeve detail.
The one rule enforced here is a data-integrity one, not a calculation: OD, the blank-calculation
diameter (ID on WO 9374's indent, 509mm) and the CAD's own OD (539mm) are kept as DISTINCT
named fields - never collapsed into each other, since conflating "the diameter used for the
manufacturing blank" with "the drawing's OD" is exactly the kind of silent misreading this
engine exists to prevent (per the spec's explicit warning on this component).
"""
from __future__ import annotations

from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus, missing


def sleeve_dimensions(
    od: float | None, blank_diameter: float | None, thickness: float | None, length: float | None,
    component: str = "Sleeve", detail_view: str = "Sleeve Detail",
) -> dict[str, DimensionResult]:
    """`blank_diameter` is the figure actually used for the manufacturing blank calculation
    (509mm on WO 9374 - this is what the indent's SIZE column calls "ID", but it is NOT
    asserted here to be a true bore inner-diameter without the drawing's own dimension
    reference confirming it - it's reported under its own name, separate from `od`)."""
    fields = {"od": od, "blank_diameter": blank_diameter, "thickness": thickness, "length": length}
    results: dict[str, DimensionResult] = {}
    for name, value in fields.items():
        if value is None:
            results[name] = missing(name, component)
        else:
            results[name] = DimensionResult(
                name=name, value=value, unit="mm", status=DimensionStatus.VERIFIED,
                component=component, detail_view=detail_view, extraction_method="ocr_detail_panel",
                notes="" if name != "blank_diameter" else (
                    "This is the indent's own blank-calculation diameter, not confirmed as the "
                    "drawing's true bore ID without checking the dimension reference directly."
                ),
            )
    return results

"""Bellows blank length, sheet width, and thickness - formulas from MB's manufacturing notes.
See engineering_engine/rules/manufacturing_rules.json for the allowance values/approval
status this module reads; nothing here is hardcoded independently of that file.
"""
from __future__ import annotations

from engineering_engine.calculations.rules_loader import load_rules
from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus, missing


def calculate_blank_length(od: float | None, component: str = "Bellows") -> DimensionResult:
    """L = (OD * pi_approx) + allowance_mm. Approved rule - confirmed against WO 9374
    (OD 559 -> 1765.26mm, rounds to the indent's own 1765mm reference)."""
    if od is None:
        return missing("length", component, "OD input required for blank length calculation")
    rule = load_rules()["bellows"]["blank_length"]
    raw = (od * rule["pi_approx"]) + rule["allowance_mm"]
    value = round(raw)
    status = DimensionStatus.CALCULATED if rule["approval_status"] == "approved" else DimensionStatus.REVIEW_REQUIRED
    return DimensionResult(
        name="length", value=value, unit="mm", status=status, component=component,
        extraction_method="calculated",
        formula=f"(od * {rule['pi_approx']}) + {rule['allowance_mm']}",
        inputs={"od": od},
        notes=f"raw={raw:.2f}mm before rounding. {rule['source']}",
    )


def calculate_sheet_width(
    q: float | None, w: float | None, n: int | None, component: str = "Bellows",
) -> DimensionResult:
    """W = ((0.57*q) + (2*w)) * N + 100. q (convolution pitch) and w (convolution depth) are
    routinely NOT reliably extractable from the CAD profile - per the spec, this must never be
    reverse-engineered from the indent's own 340mm reference to force a match. Missing q/w
    always produces MISSING with both names listed, never a guessed width."""
    rule = load_rules()["bellows"]["sheet_width"]
    missing_inputs = [name for name, val in (("pitch_q", q), ("depth_w", w), ("convolution_count_n", n)) if val is None]
    if missing_inputs:
        result = missing("width", component, f"Required inputs not available: {', '.join(missing_inputs)}")
        result.formula = f"(({rule['pitch_factor']} * q) + (2 * w)) * n + {rule['allowance_mm']}"
        result.inputs = {"pitch_q": q, "depth_w": w, "convolution_count_n": n}
        return result
    raw = ((rule["pitch_factor"] * q) + (2 * w)) * n + rule["allowance_mm"]
    return DimensionResult(
        name="width", value=round(raw, 2), unit="mm", status=DimensionStatus.REVIEW_REQUIRED,
        component=component, extraction_method="calculated",
        formula=f"(({rule['pitch_factor']} * q) + (2 * w)) * n + {rule['allowance_mm']}",
        inputs={"pitch_q": q, "depth_w": w, "convolution_count_n": n},
        notes="REVIEW_REQUIRED even with inputs present: convolution_count_interpretation is "
              f"pending_confirmation in manufacturing_rules.json ({rule['source']})",
    )


def calculate_thickness(num_plies: int | None, ply_thickness_mm: float | None, component: str = "Bellows") -> DimensionResult:
    """T = plies * ply_thickness. Directly specified on the CAD detail as one combined callout
    (e.g. "1 ply x 0.6mm") rather than independently derived - VERIFIED, not CALCULATED, once
    both pieces of that single callout are present."""
    if num_plies is None or ply_thickness_mm is None:
        return missing("thickness", component, "num_plies and ply_thickness_mm both required")
    value = round(num_plies * ply_thickness_mm, 3)
    return DimensionResult(
        name="thickness", value=value, unit="mm", status=DimensionStatus.VERIFIED,
        component=component, extraction_method="ocr_detail_panel",
        formula="num_plies * ply_thickness_mm",
        inputs={"num_plies": num_plies, "ply_thickness_mm": ply_thickness_mm},
        notes="Directly specified as a single CAD callout, not independently derived.",
    )


def interpret_convolution_count(cad_text: str | None, component: str = "Bellows") -> tuple[int | None, DimensionResult]:
    """CAD text like "5+5 NO. OF CONVOLUTES" -> provisional N=10. Always REVIEW_REQUIRED per
    manufacturing_rules.json's convolution_count_interpretation (counting convention unconfirmed)."""
    rule = load_rules()["bellows"]["convolution_count_interpretation"]
    if not cad_text:
        return None, missing("convolution_count", component, "No convolution callout found on the Bellow detail")
    import re
    m = re.search(r"(\d+)\s*\+\s*(\d+)", cad_text)
    if not m:
        return None, missing("convolution_count", component, f"Could not parse convolution count from: {cad_text!r}")
    n = int(m.group(1)) + int(m.group(2))
    result = DimensionResult(
        name="convolution_count", value=n, unit="count", status=DimensionStatus.REVIEW_REQUIRED,
        component=component, extraction_method="ocr_detail_panel",
        inputs={"raw_callout": cad_text},
        notes=rule["note"],
    )
    return n, result

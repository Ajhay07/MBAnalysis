"""Builds the WO 9374 material indent using this engine, as the spec's initial validation
dataset. Two input sources, exactly matching the extraction priority chain:
  - OD/ID: pulled from the real CAD PDF via the existing deterministic pipeline
    (engineering_engine.extraction.dimension_parser / pdf_extractor) - this is the one thing
    confirmed reliable this session, backed by the unambiguous Ø marker.
  - Thickness, Length, convolution/pitch/depth, hole counts, packaging dims: NOT reliably
    auto-extractable on this drawing family (confirmed across multiple real test passes this
    session - unlabeled numbers have no signal distinguishing them from unrelated nearby
    text). Supplied here as manual readings (extraction_method="manual", priority #5 in the
    spec's own chain) taken directly off WO 9374's CAD drawing and indent sheet, exactly as a
    human reviewer would enter them - never invented, never reverse-engineered to force a
    formula to match the indent.

Run directly (`python -m engineering_engine.main`) to print the generated JSON; see
engineering_engine/tests/ for the per-formula unit tests and the reference-indent comparison.
"""
from __future__ import annotations

import json
import os

from engineering_engine.calculations import (
    bellows_calculator, flange_calculator, packaging_calculator, pipe_calculator, shroud_calculator,
    sleeve_calculator,
)
from engineering_engine.extraction.dimension_parser import get_component_evidence, parse_numeric
from engineering_engine.output.indent_generator import ComponentOutput, generate_indent_json
from engineering_engine.validation.bom_validator import calculate_total_quantity, reference_only_quantity
from engineering_engine.validation.dimension_validator import DimensionResult, DimensionStatus

WO_9374_PDF = os.path.expanduser(r"~\Downloads\9374.pdf")
ASSEMBLY_QUANTITY = 4

# Manually-read inputs (priority #5 of the extraction chain) - everything the automated
# pipeline cannot reliably get on this drawing family. Each value here is transcribed directly
# from WO 9374's own CAD drawing / indent sheet, not invented.
MANUAL_INPUTS = {
    "BELLOWS": {"num_plies": 1, "ply_thickness_mm": 0.6, "convolution_text": "5+5 NO. OF CONVOLUTES",
                "reference_indent_width": 340, "material": "A 240 TYP 304"},
    # od=509 CORRECTED after review: the indent's own SIZE column gives Sleeve's OD as 509, not
    # the 539 the auto-extractor reads off the Sleeve Detail panel (that 539 is very likely Mid
    # Pipe's own ID printed nearby as a mating reference - see sleeve_calculator.py). 509 is
    # entered manually here (matching the indent) rather than trusted from auto-extraction,
    # since auto-extraction cannot currently tell OD/ID apart from two concentric circles by
    # position alone with any confidence.
    "SLEEVE": {"od": 509, "thickness": 1.5, "length": 150, "material": "A 240 Gr. 304"},
    "MID PIPE": {"thickness": 10, "length": 150, "material": ""},
    "END PIPE": {"thickness": 10, "length": 125, "material": "A 516 Gr.70"},
    "HOUSING FLANGE": {"id": 562, "thickness": 25, "pcd": 734, "hole_diameter": 34,
                        "hole_count_indent": 2, "material": "IS 2062 E250 Gr.BR / A 515/516 Gr. 70"},
    "SHROUD": {"width": 170, "thickness": 2, "reference_indent_length": 2190, "material": "IS 2062 E250 BR"},
    # By explicit instruction: preserve the 595+15=610 calculation (matches the indent) and keep
    # it REVIEW_REQUIRED - WO 9374 has no Limit Rod CAD detail panel, so cad_length=595 is
    # itself derived by subtracting the allowance back out of the indent's own 610 figure, not
    # an independent reading (see calculate_limit_rod_length's cad_length_is_inferred flag,
    # which makes this explicit in the output's notes rather than overclaiming it).
    "LIMIT ROD": {"cad_length": 610 - 15, "cad_length_is_inferred": True, "reference_indent_length": 610,
                  "material": "IS 1367 Cl. 6.8"},
    "NUT & LOCKNUT": {"material": "IS 1367 Cl. 6.0", "thread": "M30"},
    "SHROUD SUPPORT": {"size": "60x60x6 Angle - 40 lg", "material": "IS 2062 E250 BR"},
    "M8 BOLT & NUT": {"size": "M8 x 20 lg", "material": "IS 1367 Cl.6.8/6.0"},
    "COLLAR": {"diameter": 20, "length": 1790, "source_detail": "Detail B", "material": "A 240 TYP 304"},
    "FILLER WIRE": {"size": "ER 309 - Ø2.4 x 1000", "reference_indent_qty": 84},
    "ELECTRODE": {"size": "E 6013 - Ø4 x 450", "reference_indent_qty": 282},
    "STIFFENER": {"size": "40x40x6 Angle - 490 lg", "material": "IS 2062", "reference_indent_qty": 16},
    # assembly_length_mm intentionally NOT supplied: the only source for a "package length" was
    # previously back-derived from the indent's own 33" reference (33*25.4-250), the exact
    # reverse-engineering the spec forbids - CORRECTED after review. No independent assembly/
    # package length is currently extracted anywhere in this pipeline, so the calculated length
    # stays MISSING; the indent's 33x33x25" is kept as reference_indent_dimensions only.
    "WOODEN BOX": {"assembly_length_mm": None, "reference_length_in": 33, "breadth_in": 33, "width_in": 25},
}

# CAD BOM reference (qty per assembly) and the indent's own printed total, for discrepancy
# checking - both transcribed from WO 9374's materials, same "never silently pick one" rule.
BOM_REFERENCE = {
    "BELLOWS": (2, 8), "SLEEVE": (2, 8), "MID PIPE": (1, 4), "END PIPE": (2, 8),
    "HOUSING FLANGE": (2, 8), "LIMIT ROD": (2, 8), "NUT & LOCKNUT": (16, 64),
    "SHROUD": (2, 8), "SHROUD SUPPORT": (8, 32), "M8 BOLT & NUT": (8, 48),  # indent says 48, not 32 - flagged below
    "COLLAR": (4, 16),
}


def _manual_result(name: str, value, component: str, unit: str = "mm", notes: str = "") -> DimensionResult:
    return DimensionResult(
        name=name, value=value, unit=unit, status=DimensionStatus.VERIFIED, component=component,
        extraction_method="manual", notes=notes or "Manually transcribed - not reliably auto-extractable on this drawing family.",
    )


def build_wo9374_components(pdf_path: str = WO_9374_PDF) -> list[ComponentOutput]:
    evidence = {}
    try:
        evidence = get_component_evidence(pdf_path)
    except Exception as exc:  # pragma: no cover - degrades to manual-only, never crashes the build
        print(f"[warn] CAD extraction unavailable ({exc}); proceeding with manual inputs only.")

    def find_evidence(key: str):
        """Exact match first; falls back to substring match either direction, since OCR
        misreads a BOM description (e.g. "SLEEVE" -> "SLEEV", confirmed on the real WO 9374
        extraction) often enough that an exact-key lookup alone silently loses real evidence
        that IS present. Still conservative: requires key or evidence_key be a prefix/substring
        of the other, never a fuzzy/edit-distance match that could pick the wrong component."""
        if key in evidence:
            return evidence[key]
        for ev_key, ev in evidence.items():
            if ev_key in key or key in ev_key:
                return ev
        return None

    def od_for(key: str) -> float | None:
        ev = find_evidence(key)
        if not ev:
            return None
        return parse_numeric(ev.dimensions.get("od"))

    components: list[ComponentOutput] = []

    # --- Bellows ---
    manual = MANUAL_INPUTS["BELLOWS"]
    od = od_for("BELLOWS")
    length_result = bellows_calculator.calculate_blank_length(od)
    thickness_result = bellows_calculator.calculate_thickness(manual["num_plies"], manual["ply_thickness_mm"])
    n, convolution_result = bellows_calculator.interpret_convolution_count(manual["convolution_text"])
    width_result = bellows_calculator.calculate_sheet_width(None, None, n)  # q, w not extractable - stays MISSING
    od_result = (_manual_result("od", od, "Bellows", notes="OD read from the CAD Bellow Detail (Ø marker, auto-extracted).")
                 if od is not None else DimensionResult("od", None, "mm", DimensionStatus.MISSING, "Bellows"))
    components.append(ComponentOutput(
        name="Bellows", material=manual["material"],
        dimensions={"od": od_result, "length": length_result, "width": width_result,
                    "thickness": thickness_result, "convolution_count": convolution_result},
        reference_dimensions={"width": manual["reference_indent_width"]},
        quantity=calculate_total_quantity("Bellows", BOM_REFERENCE["BELLOWS"][0], ASSEMBLY_QUANTITY, BOM_REFERENCE["BELLOWS"][1]),
    ))

    # --- Sleeve ---
    manual = MANUAL_INPUTS["SLEEVE"]
    cad_interface_reference = od_for("SLEEVE")  # the 539mm value auto-extracted from the panel
    sleeve_dims = sleeve_calculator.sleeve_dimensions(
        manual["od"], manual["thickness"], manual["length"],
        mid_pipe_interface_reference=cad_interface_reference, od_source="manual",
    )
    components.append(ComponentOutput(
        name="Sleeve", material=manual["material"], dimensions=sleeve_dims,
        quantity=calculate_total_quantity("Sleeve", BOM_REFERENCE["SLEEVE"][0], ASSEMBLY_QUANTITY, BOM_REFERENCE["SLEEVE"][1]),
    ))

    # --- Mid Pipe / End Pipe ---
    for key, label in (("MID PIPE", "Mid Pipe"), ("END PIPE", "End Pipe")):
        manual = MANUAL_INPUTS[key]
        od = od_for(key)
        dims = pipe_calculator.pipe_dimensions(od, manual["thickness"], manual["length"], label, detail_view=f"{label} Detail")
        components.append(ComponentOutput(
            name=label, material=manual["material"], dimensions=dims,
            quantity=calculate_total_quantity(label, BOM_REFERENCE[key][0], ASSEMBLY_QUANTITY, BOM_REFERENCE[key][1]),
        ))

    # --- Housing Flange ---
    manual = MANUAL_INPUTS["HOUSING FLANGE"]
    od = od_for("HOUSING FLANGE")
    flange_dims = flange_calculator.housing_flange_dimensions(
        od, manual["id"], manual["thickness"], manual["pcd"], manual["hole_diameter"],
        hole_count_drawing=None, hole_count_indent=manual["hole_count_indent"],
    )
    components.append(ComponentOutput(
        name="Housing Flange", material=manual["material"], dimensions=flange_dims,
        quantity=calculate_total_quantity("Housing Flange", BOM_REFERENCE["HOUSING FLANGE"][0], ASSEMBLY_QUANTITY, BOM_REFERENCE["HOUSING FLANGE"][1]),
    ))

    # --- Shroud ---
    manual = MANUAL_INPUTS["SHROUD"]
    od = od_for("SHROUD")
    base_length = shroud_calculator.calculate_base_circumference(od)
    final_length = shroud_calculator.calculate_final_length(
        base_length.value if base_length.value is not None else None, manual["reference_indent_length"],
    )
    components.append(ComponentOutput(
        name="Shroud", material=manual["material"],
        dimensions={
            "base_length": base_length, "length": final_length,
            "width": _manual_result("width", manual["width"], "Shroud"),
            "thickness": _manual_result("thickness", manual["thickness"], "Shroud"),
        },
        reference_dimensions={"length": manual["reference_indent_length"]},
        quantity=calculate_total_quantity("Shroud", BOM_REFERENCE["SHROUD"][0], ASSEMBLY_QUANTITY, BOM_REFERENCE["SHROUD"][1]),
    ))

    # --- Limit Rod ---
    manual = MANUAL_INPUTS["LIMIT ROD"]
    length_result = flange_calculator.calculate_limit_rod_length(
        manual["cad_length"], cad_length_is_inferred=manual["cad_length_is_inferred"],
    )
    components.append(ComponentOutput(
        name="Limit Rod", material=manual["material"], dimensions={"length": length_result},
        reference_dimensions={"length": manual["reference_indent_length"]},
        quantity=calculate_total_quantity("Limit Rod", BOM_REFERENCE["LIMIT ROD"][0], ASSEMBLY_QUANTITY, BOM_REFERENCE["LIMIT ROD"][1]),
    ))

    # --- Collar ---
    manual = MANUAL_INPUTS["COLLAR"]
    collar_dims = flange_calculator.collar_dimensions(manual["diameter"], manual["length"], manual["source_detail"])
    components.append(ComponentOutput(
        name="Collar", material=manual["material"], dimensions=collar_dims,
        quantity=calculate_total_quantity("Collar", BOM_REFERENCE["COLLAR"][0], ASSEMBLY_QUANTITY, BOM_REFERENCE["COLLAR"][1]),
    ))

    # --- Nut & Locknut, Shroud Support, M8 Bolt & Nut, Filler Wire, Electrode, Stiffener ---
    # No calculation formula for these per the spec - specs/quantities come straight from the
    # drawing/BOM, reported as manual VERIFIED pass-throughs.
    for key, label, qty_key in (
        ("NUT & LOCKNUT", "Nut & Locknut", "NUT & LOCKNUT"),
        ("SHROUD SUPPORT", "Shroud Support", "SHROUD SUPPORT"),
        ("M8 BOLT & NUT", "M8 Bolt & Nut", "M8 BOLT & NUT"),
    ):
        manual = MANUAL_INPUTS[key]
        dims = {"size": _manual_result("size", manual.get("size") or manual.get("thread"), label, unit="")}
        components.append(ComponentOutput(
            name=label, material=manual.get("material", ""), dimensions=dims,
            quantity=calculate_total_quantity(label, BOM_REFERENCE[qty_key][0], ASSEMBLY_QUANTITY, BOM_REFERENCE[qty_key][1]),
        ))
    for key, label in (("FILLER WIRE", "Filler Wire"), ("ELECTRODE", "Electrode"), ("STIFFENER", "Stiffener")):
        manual = MANUAL_INPUTS[key]
        dims = {"size": _manual_result("size", manual.get("size"), label, unit="")}
        components.append(ComponentOutput(
            name=label, material=manual.get("material", ""), dimensions=dims,
            # CORRECTED after review: these were previously dropped entirely because the CAD
            # BOM has no per-assembly figure for them - the indent's own quantity is preserved
            # via reference_only_quantity instead of being discarded.
            quantity=reference_only_quantity(label, manual["reference_indent_qty"]),
        ))

    # --- Wooden Box ---
    # CORRECTED after review: assembly_length is no longer back-derived from the indent's own
    # 33" reference (that was reverse-engineering an "input" from the known output). With no
    # independent package-length source currently extracted, the calculated length stays
    # MISSING; the indent's 33x33x25" is reported as reference_dimensions only, never silently
    # substituted as if it were calculated.
    manual = MANUAL_INPUTS["WOODEN BOX"]
    length_result = packaging_calculator.calculate_box_length(manual["assembly_length_mm"])
    bw = packaging_calculator.box_breadth_and_width(manual["breadth_in"], manual["width_in"])
    components.append(ComponentOutput(
        name="Wooden Box", dimensions={"length": length_result, **bw},
        reference_dimensions={"length": manual["reference_length_in"], "breadth": manual["breadth_in"], "width": manual["width_in"]},
        quantity=calculate_total_quantity("Wooden Box", 4, 1, 4),  # 4 Nos. flat, not per-assembly-scaled
    ))

    return components


def main() -> dict:
    components = build_wo9374_components()
    output = generate_indent_json("9374", ASSEMBLY_QUANTITY, components)
    print(json.dumps(output, indent=2, default=str))
    return output


if __name__ == "__main__":
    main()

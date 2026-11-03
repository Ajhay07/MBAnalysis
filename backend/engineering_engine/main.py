"""WO 9374 as a WorkOrderInputs object, run through the GENERALIZED routing pipeline
(engineering_engine.routing.pipeline.process_work_order) - this file no longer contains any
WO-9374-specific branching logic itself; it only supplies data. A new work order is a new
WorkOrderInputs definition (see engineering_engine/fixtures/ for two synthetic examples), not
a code change here or in routing/.

Two input sources, exactly matching the extraction priority chain:
  - OD/ID: pulled from the real CAD PDF via the existing deterministic pipeline
    (engineering_engine.extraction.dimension_parser / pdf_extractor) - the one thing confirmed
    reliable this session, backed by the unambiguous Ø marker. The routing pipeline does this
    automatically from `pdf_path`; nothing in this file calls OCR directly.
  - Thickness, Length, convolution/pitch/depth, hole counts, packaging dims: NOT reliably
    auto-extractable on this drawing family. Supplied as manual readings (priority #5 of the
    extraction chain) taken directly off WO 9374's CAD drawing and indent sheet - never
    invented, never reverse-engineered to force a formula to match the indent (see README.md's
    "Corrections from code review" section for two bugs of exactly that kind, now fixed).

Run directly (`python -m engineering_engine.main`) to print the generated JSON; see
engineering_engine/tests/ for the per-formula unit tests and the reference-indent comparison,
and engineering_engine/tests/test_routing_pipeline.py for the generalized-pipeline tests.
"""
from __future__ import annotations

import json
import os

from engineering_engine.routing.pipeline import process_work_order
from engineering_engine.routing.work_order_inputs import ComponentInput, WorkOrderInputs

WO_9374_PDF = os.path.expanduser(r"~\Downloads\9374.pdf")


def wo_9374_inputs() -> WorkOrderInputs:
    """Everything previously hardcoded as MANUAL_INPUTS/BOM_REFERENCE directly in this file,
    now expressed as data the generalized routing pipeline consumes - no different in kind
    from how a new work order would be defined (see engineering_engine/fixtures/)."""
    return WorkOrderInputs(
        work_order="9374",
        assembly_quantity=4,
        pdf_path=WO_9374_PDF,
        components=[
            ComponentInput(
                description="Bellows", material="A 240 TYP 304",
                manual={"num_plies": 1, "ply_thickness_mm": 0.6, "convolution_text": "5+5 NO. OF CONVOLUTES"},
                reference_dimensions={"width": 340},
                quantity_per_assembly=2, reference_indent_quantity=8,
            ),
            ComponentInput(
                # od=509 CORRECTED after review: the indent's own SIZE column gives Sleeve's OD
                # as 509, not the 539 the auto-extractor reads off the Sleeve Detail panel (very
                # likely Mid Pipe's own ID printed nearby as a mating reference - see
                # calculations/sleeve_calculator.py).
                description="Sleeve", material="A 240 Gr. 304",
                manual={"od": 509, "thickness": 1.5, "length": 150},
                quantity_per_assembly=2, reference_indent_quantity=8,
            ),
            ComponentInput(
                description="Mid Pipe", manual={"thickness": 10, "length": 150},
                quantity_per_assembly=1, reference_indent_quantity=4,
            ),
            ComponentInput(
                description="End Pipe", material="A 516 Gr.70", manual={"thickness": 10, "length": 125},
                quantity_per_assembly=2, reference_indent_quantity=8,
            ),
            ComponentInput(
                description="Housing Flange", material="IS 2062 E250 Gr.BR / A 515/516 Gr. 70",
                manual={"id": 562, "thickness": 25, "pcd": 734, "hole_diameter": 34, "hole_count_indent": 2},
                quantity_per_assembly=2, reference_indent_quantity=8,
            ),
            ComponentInput(
                description="Shroud", material="IS 2062 E250 BR", manual={"width": 170, "thickness": 2},
                reference_dimensions={"length": 2190},
                quantity_per_assembly=2, reference_indent_quantity=8,
            ),
            ComponentInput(
                # By explicit instruction: preserve 595+15=610 (matches the indent) and keep it
                # REVIEW_REQUIRED - WO 9374 has no Limit Rod CAD detail panel, so cad_length=595
                # is itself derived by subtracting the allowance back out of 610, not an
                # independent reading (cad_length_is_inferred documents this in the output).
                description="Limit Rod", material="IS 1367 Cl. 6.8",
                manual={"cad_length": 610 - 15, "cad_length_is_inferred": True},
                reference_dimensions={"length": 610},
                quantity_per_assembly=2, reference_indent_quantity=8,
            ),
            ComponentInput(
                description="Collar", material="A 240 TYP 304",
                manual={"diameter": 20, "length": 1790, "source_detail": "Detail B"},
                quantity_per_assembly=4, reference_indent_quantity=16,
            ),
            ComponentInput(
                description="Nut & Locknut", material="IS 1367 Cl. 6.0", manual={"size": "M30"},
                quantity_per_assembly=16, reference_indent_quantity=64,
            ),
            ComponentInput(
                description="Shroud Support", material="IS 2062 E250 BR", manual={"size": "60x60x6 Angle - 40 lg"},
                quantity_per_assembly=8, reference_indent_quantity=32,
            ),
            ComponentInput(
                # Discrepancy, by design: CAD BOM gives 8/assembly (-> 32 for 4 assemblies),
                # the indent prints 48 - both numbers are preserved, neither silently wins.
                description="M8 Bolt & Nut", material="IS 1367 Cl.6.8/6.0", manual={"size": "M8 x 20 lg"},
                quantity_per_assembly=8, reference_indent_quantity=48,
            ),
            ComponentInput(
                description="Filler Wire", manual={"size": "ER 309 - Ø2.4 x 1000"}, reference_indent_quantity=84,
            ),
            ComponentInput(
                description="Electrode", manual={"size": "E 6013 - Ø4 x 450"}, reference_indent_quantity=282,
            ),
            ComponentInput(
                description="Stiffener", material="IS 2062", manual={"size": "40x40x6 Angle - 490 lg"},
                reference_indent_quantity=16,
            ),
            ComponentInput(
                # assembly_length_mm intentionally omitted: no independent package-length source
                # exists anywhere in this pipeline (see README's "Corrections from code review").
                # The indent's 33x33x25" stays a reference value only, never backward-derived
                # into a fake "input".
                description="Wooden Box", manual={"assembly_length_mm": None, "breadth": 33, "width": 25},
                reference_dimensions={"length": 33, "breadth": 33, "width": 25},
                quantity_per_assembly=1, reference_indent_quantity=4,  # 1 box per assembly * 4 assemblies = 4, matches the indent
            ),
        ],
    )


def main() -> dict:
    output = process_work_order(wo_9374_inputs())
    print(json.dumps(output, indent=2, default=str))
    return output


if __name__ == "__main__":
    main()

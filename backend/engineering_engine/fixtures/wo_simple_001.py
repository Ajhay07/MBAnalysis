"""Synthetic work order: a simpler single-expansion-joint BOM (Bellows/Sleeve/End Pipe/Shroud
only - no Mid Pipe, Housing Flange, Limit Rod or Collar), matching the simpler 4-component
drawing family seen elsewhere in the real sample set this session (e.g. 250.pdf/251.pdf) but
with synthetic numbers, not transcribed from a real drawing. No CAD PDF is supplied (pdf_path=
None) - every dimension here is manual, exercising the "extraction unavailable, degrade
gracefully" path rather than the OCR path WO 9374 exercises.
"""
from __future__ import annotations

from engineering_engine.routing.work_order_inputs import ComponentInput, WorkOrderInputs


def inputs() -> WorkOrderInputs:
    return WorkOrderInputs(
        work_order="SIMPLE-001",
        assembly_quantity=10,
        pdf_path=None,  # no CAD file - exercises the no-extraction-available path
        components=[
            ComponentInput(
                description="Bellows", material="A 240 TYP 304L",
                manual={"num_plies": 2, "ply_thickness_mm": 0.5},  # no OD -> length stays MISSING (no extraction)
                quantity_per_assembly=1, reference_indent_quantity=10,
            ),
            ComponentInput(
                description="Sleeve", material="A 240 Gr. 304L",
                manual={"od": 219, "thickness": 9.5, "length": 175},
                quantity_per_assembly=1, reference_indent_quantity=10,
            ),
            ComponentInput(
                description="End Pipe", material="A 240 Gr. 304L",
                manual={"thickness": 6, "length": 61},  # no OD -> id stays MISSING
                quantity_per_assembly=2, reference_indent_quantity=20,
            ),
            ComponentInput(
                description="Shroud", material="G.I", manual={"width": 170, "thickness": 2},
                reference_dimensions={"length": 1900},  # no OD -> base_length MISSING, final length MISSING too
                quantity_per_assembly=1, reference_indent_quantity=10,
            ),
        ],
    )

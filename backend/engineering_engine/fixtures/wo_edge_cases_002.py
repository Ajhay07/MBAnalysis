"""Synthetic work order built specifically to exercise routing edge cases the spec asks to be
tested: an unknown/unregistered component, a component missing a required parameter, two BOM
rows mapping to the same registered spec (duplicate classification), and a BOM-quantity
discrepancy against a reference indent value. Entirely synthetic - not derived from any real
MB drawing.
"""
from __future__ import annotations

from engineering_engine.routing.work_order_inputs import ComponentInput, WorkOrderInputs


def inputs() -> WorkOrderInputs:
    return WorkOrderInputs(
        work_order="EDGE-002",
        assembly_quantity=2,
        pdf_path=None,
        components=[
            # Missing required parameter: no thickness supplied -> id stays MISSING, not guessed.
            ComponentInput(
                description="Mid Pipe", manual={"length": 100},
                quantity_per_assembly=1, reference_indent_quantity=2,
            ),
            # Unknown component: nothing in the registry matches "Gasket".
            ComponentInput(
                description="Gasket", material="Klingersil C-4400",
                manual={"size": "ID 200 x OD 240 x 3mm"},
                quantity_per_assembly=2, reference_indent_quantity=4,
            ),
            # Duplicate spec match: two distinct BOM rows both classify as BOLTS_AND_NUTS.
            ComponentInput(
                description="M10 Bolt & Nut", manual={"size": "M10 x 25 lg"},
                quantity_per_assembly=8, reference_indent_quantity=16,
            ),
            ComponentInput(
                description="Nut & Locknut", manual={"size": "M20"},
                quantity_per_assembly=4, reference_indent_quantity=8,
            ),
            # BOM quantity discrepancy: calculated 2*2=4, but the (synthetic) reference indent
            # says 6 - must be flagged, never silently resolved either way.
            ComponentInput(
                description="Collar", manual={"diameter": 25, "length": 900, "source_detail": "Detail B"},
                quantity_per_assembly=2, reference_indent_quantity=6,
            ),
            # Unapproved allowance in play: Shroud's final length always stays REVIEW_REQUIRED
            # (manual OD supplied here since this fixture has no CAD PDF to extract one from).
            ComponentInput(
                description="Shroud", manual={"od": 400, "width": 150, "thickness": 3},
                reference_dimensions={"length": 1500},
                quantity_per_assembly=1, reference_indent_quantity=2,
            ),
        ],
    )

"""Per-work-order input data: the component list a work order's indent actually needs, plus
whatever manual readings (priority #5 of the extraction chain), reference indent values, and
BOM quantities go with each one. This is what used to be hardcoded as MANUAL_INPUTS/
BOM_REFERENCE directly in main.py - factored out so a NEW work order is a new WorkOrderInputs
object, not a code change to the routing logic itself.

Nothing here is extracted automatically - by definition, everything in a ComponentInput's
`manual` dict is priority-#5 "manual verification" input. What IS automatic is matching each
ComponentInput to CAD-extracted evidence (OD/ID etc.) by component identity, which the
pipeline does, not this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ComponentInput:
    description: str                              # as it should appear on the indent, e.g. "Bellows"
    material: str = ""
    manual: dict = field(default_factory=dict)     # manual parameter readings, e.g. {"thickness": 10}
    reference_dimensions: dict = field(default_factory=dict)  # indent's own printed values, for comparison only
    quantity_per_assembly: float | None = None     # None when only a flat/reference quantity is known
    reference_indent_quantity: float | None = None
    spec_identifier: str | None = None             # explicit override; None = classify by `description`


@dataclass
class WorkOrderInputs:
    work_order: str
    assembly_quantity: float
    components: list[ComponentInput] = field(default_factory=list)
    pdf_path: str | None = None  # the CAD drawing to extract OD/ID evidence from, if available

"""Deterministic MB Metallic Bellows indent-sheet generation.

Two inputs feed an indent:
  1. The BOM's own top-level line items (already extracted/reviewed components), scaled by
     an explicit assembly_quantity: wt_qty = quantity_per_assembly * assembly_quantity. This
     is plain arithmetic - never AI-estimated - and is covered by the regression test built
     from Work Order 9347's published fixture numbers.
  2. Optional, explicitly-selected IndentRule rows (manufacturing consumables, packaging, ...).
     Rules are never auto-applied against every indent: the caller passes the rule_ids to use
     for *this* generation run, so a rule approved for one product family is never silently
     assumed to apply to an unrelated drawing. A rule with formula=MANUAL_REQUIRED always
     produces a line with wt_qty=None and requires_confirmation=True - the system never
     invents a consumable rate it wasn't given.

Nothing here hardcodes Work Order 9347 (or any other specific work order) - see
tests/test_indent_generation.py for the fixture that proves the arithmetic against that
drawing's published BOM table without the numbers living in this module.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import (
    AuditLog, Bom, BomLineItem, Component, Indent, IndentLine, IndentRule, IndentRuleFormula,
)

# Canonical order for size-string formatting when a component's `dimensions` dict uses these
# keys (OD/ID/Thk/L is the pattern used throughout MB's drawings - see bellow/end-pipe/flange/
# sleeve rows on 9347.pdf). Any other keys are appended afterwards, in insertion order, so a
# differently-shaped dimensions dict still renders instead of being silently dropped.
_SIZE_KEY_ORDER = ["od", "id", "thk", "l", "length", "width", "height", "dia", "pcd", "hole_dia", "noh"]
_SIZE_KEY_LABELS = {
    "od": "OD", "id": "ID", "thk": "Thk", "l": "L", "length": "L", "width": "W", "height": "H",
    "dia": "Dia", "pcd": "PCD", "hole_dia": "Hole Ø", "noh": "No. of Holes",
}


def format_size_text(dimensions: dict | None) -> str:
    """Renders a component's `dimensions` dict as a size string for the SIZE column, e.g.
    {"od": "240", "thk": "6", "l": "61"} -> "OD 240  Thk 6  L 61". Returns "" (not "—") when
    there is nothing to show, so callers can tell "no dimensions recorded" apart from a
    genuine formatted value and flag the former for review instead of printing a placeholder."""
    if not dimensions:
        return ""
    parts: list[str] = []
    seen: set[str] = set()
    for key in _SIZE_KEY_ORDER:
        if key in dimensions and dimensions[key] not in (None, ""):
            label = _SIZE_KEY_LABELS.get(key, key)
            parts.append(f"{label} {dimensions[key]}")
            seen.add(key)
    for key, value in dimensions.items():
        if key not in seen and value not in (None, ""):
            parts.append(f"{key} {value}")
    return "  ".join(parts)


def lines_from_bom(db: Session, bom: Bom, assembly_quantity: float) -> list[dict]:
    """Top-level BOM line items (no parent), scaled by assembly_quantity. A line whose own
    per-assembly quantity is None is still emitted (so nothing silently disappears from the
    indent) but is flagged requires_confirmation=True rather than guessing a quantity."""
    top_level = [li for li in bom.line_items if li.parent_line_item_id is None]
    out: list[dict] = []
    for li in top_level:
        dimensions = None
        if li.component_id:
            component = db.query(Component).get(li.component_id)
            if component:
                dimensions = component.dimensions
        size_text = format_size_text(dimensions)
        wt_qty = None if li.quantity is None else float(li.quantity) * float(assembly_quantity)
        mtl_spec = li.description
        if li.material:
            mtl_spec = f"{li.description}\n{li.material}" if li.description else li.material
        out.append({
            "mtl_spec": mtl_spec,
            "size_text": size_text,
            "wt_qty": wt_qty,
            "unit": "Nos",
            "bom_line_item_id": li.id,
            "indent_rule_id": None,
            "source": "bom_line",
            "requires_confirmation": wt_qty is None,
            "note": "" if wt_qty is not None else "BOM line item has no per-assembly quantity on file.",
        })
    return out


def lines_from_rules(db: Session, rule_ids: list[str], assembly_quantity: float) -> list[dict]:
    """Expands the explicitly-selected IndentRule rows into indent lines. Rules not in
    rule_ids are never applied, however active/relevant they look, so adding a rule to the
    catalog never changes an indent generated without selecting it."""
    if not rule_ids:
        return []
    rules = db.query(IndentRule).filter(IndentRule.id.in_(rule_ids), IndentRule.active.is_(True)).all()
    found = {r.id for r in rules}
    out: list[dict] = []
    for rule in rules:
        if rule.formula == IndentRuleFormula.FIXED_QTY:
            wt_qty = rule.value
            requires_confirmation = rule.value is None
        elif rule.formula == IndentRuleFormula.PER_ASSEMBLY:
            wt_qty = None if rule.value is None else float(rule.value) * float(assembly_quantity)
            requires_confirmation = rule.value is None
        else:  # MANUAL_REQUIRED
            wt_qty = None
            requires_confirmation = True
        out.append({
            "mtl_spec": rule.mtl_spec or rule.name,
            "size_text": rule.size_text or "",
            "wt_qty": wt_qty,
            "unit": rule.unit or "Pcs",
            "bom_line_item_id": None,
            "indent_rule_id": rule.id,
            "source": "rule",
            "requires_confirmation": requires_confirmation,
            "note": "" if not requires_confirmation else
                    f"Approved requirement '{rule.name}' has no quantity rule yet - confirm before issuing.",
        })
    missing = set(rule_ids) - found
    for missing_id in missing:
        out.append({
            "mtl_spec": "(unknown rule)",
            "size_text": "",
            "wt_qty": None,
            "unit": "Pcs",
            "bom_line_item_id": None,
            "indent_rule_id": missing_id,
            "source": "rule",
            "requires_confirmation": True,
            "note": f"Rule id {missing_id} was requested but is missing or inactive.",
        })
    return out


def generate_indent(
    db: Session,
    bom: Bom,
    *,
    assembly_quantity: float,
    wo_number: str = "",
    party_name: str = "",
    required_on: str = "",
    serial_no: str = "",
    indent_date: str = "",
    rule_ids: list[str] | None = None,
    actor: str = "system",
) -> Indent:
    """Creates a new versioned Indent for this BOM (mirrors Bom's own versioning pattern -
    regenerating never overwrites a prior indent, so an already-printed/approved one stays
    intact). Never creates a PurchaseRequisition; that remains a separate, explicitly
    authorized action (see app.routers.procurement)."""
    if assembly_quantity is None or assembly_quantity <= 0:
        raise ValueError("assembly_quantity must be a positive number")

    existing_count = db.query(Indent).filter(Indent.bom_id == bom.id).count()
    indent = Indent(
        bom_id=bom.id,
        drawing_id=bom.drawing_id,
        version=existing_count + 1,
        wo_number=wo_number,
        party_name=party_name,
        required_on=required_on,
        serial_no=serial_no,
        indent_date=indent_date,
        assembly_quantity=assembly_quantity,
        created_by=actor,
    )
    db.add(indent)
    db.flush()

    all_lines = lines_from_bom(db, bom, assembly_quantity) + lines_from_rules(db, rule_ids or [], assembly_quantity)
    for sl_no, line in enumerate(all_lines, start=1):
        db.add(IndentLine(indent_id=indent.id, sl_no=sl_no, **line))

    db.add(AuditLog(
        entity_type="indent", entity_id=indent.id, action="generated",
        details={"bom_id": bom.id, "assembly_quantity": assembly_quantity, "line_count": len(all_lines),
                 "rule_ids": rule_ids or []},
        actor=actor,
    ))
    db.commit()
    db.refresh(indent)
    return indent

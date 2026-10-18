from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import (
    Analysis, Bom, BomLineItem, CatalogComponent, Drawing, DrawingStatus, AuditLog,
)


class CyclicBomReferenceError(ValueError):
    """Raised when a parent_line_item_id assignment would create a cycle."""


def would_create_cycle(db: Session, bom_id: str, item_id: str, new_parent_id: str | None) -> bool:
    """Walks up the parent chain starting at `new_parent_id`; if it ever reaches
    `item_id`, assigning new_parent_id as item_id's parent would create a cycle
    (or make the item its own parent)."""
    if new_parent_id is None:
        return False
    if new_parent_id == item_id:
        return True
    seen: set[str] = set()
    current_id = new_parent_id
    while current_id:
        if current_id in seen:
            # Pre-existing cycle in stored data; treat as a cycle rather than loop forever.
            return True
        seen.add(current_id)
        if current_id == item_id:
            return True
        current = db.query(BomLineItem).filter(
            BomLineItem.id == current_id, BomLineItem.bom_id == bom_id
        ).first()
        if current is None:
            return False
        current_id = current.parent_line_item_id
    return False


def recompute_rollup(db: Session, bom_id: str) -> None:
    """Recomputes total_quantity for every line item in a BOM: qty-per-assembly
    multiplied through the chain of parent qty-per-assembly values. Left null for
    any item whose own quantity or any ancestor's quantity is unknown (None), since
    guessing a multiplier would be worse than flagging it for review."""
    items = db.query(BomLineItem).filter(BomLineItem.bom_id == bom_id).all()
    by_id = {item.id: item for item in items}

    memo: dict[str, float | None] = {}

    def resolve(item_id: str, trail: set[str]) -> float | None:
        if item_id in memo:
            return memo[item_id]
        if item_id in trail:
            memo[item_id] = None  # cycle guard; should not normally happen post-validation
            return None
        item = by_id.get(item_id)
        if item is None or item.quantity is None:
            memo[item_id] = None
            return None
        if not item.parent_line_item_id or item.parent_line_item_id not in by_id:
            total = float(item.quantity)
        else:
            parent_total = resolve(item.parent_line_item_id, trail | {item_id})
            total = None if parent_total is None else float(item.quantity) * parent_total
        memo[item_id] = total
        return total

    for item in items:
        item.total_quantity = resolve(item.id, set())
    db.commit()


def build_bom_tree(db: Session, bom: Bom) -> list[dict]:
    """Returns the BOM's line items as a nested tree (list of top-level nodes,
    each with a `children` list)."""
    items = bom.line_items
    by_parent: dict[str | None, list[BomLineItem]] = {}
    for item in items:
        by_parent.setdefault(item.parent_line_item_id, []).append(item)

    def node(item: BomLineItem, level: int) -> dict:
        return {
            "id": item.id,
            "part_number": item.part_number,
            "description": item.description,
            "category": item.category,
            "quantity": item.quantity,
            "total_quantity": item.total_quantity,
            "material": item.material,
            "make_buy": item.make_buy.value if hasattr(item.make_buy, "value") else item.make_buy,
            "unit_cost": item.unit_cost,
            "parent_line_item_id": item.parent_line_item_id,
            "component_id": item.component_id,
            "level": level,
            "children": [node(child, level + 1) for child in by_parent.get(item.id, [])],
        }

    return [node(item, 0) for item in by_parent.get(None, [])]


def max_tree_depth(nodes: list[dict]) -> int:
    """Depth of the deepest node in a build_bom_tree() result (0 = flat, every node
    top-level/childless). Used by the frontend to decide whether tree view should default on."""
    deepest = 0
    for n in nodes:
        deepest = max(deepest, n.get("level", 0))
        if n.get("children"):
            deepest = max(deepest, max_tree_depth(n["children"]))
    return deepest


def generate_bom_from_analysis(db: Session, analysis: Analysis, actor: str = "system") -> Bom:
    """Builds a new BOM (versioned) from a persisted analysis's components.
    Flat with parent_line_item_id preserved for future multi-level UI."""
    existing_count = db.query(Bom).filter(Bom.analysis_id == analysis.id).count()
    bom = Bom(drawing_id=analysis.drawing_id, analysis_id=analysis.id, version=existing_count + 1,
               status="Draft")
    db.add(bom)
    db.flush()

    id_map: dict[str, str] = {}
    for component in analysis.components:
        # Carry the OCR-to-catalog match (app.services.catalog_matching, applied during the
        # analysis pipeline) over to the BOM line, and seed unit_cost from the catalog price
        # when the pipeline didn't already supply one - never overwrites a real cost.
        unit_cost = None
        if component.catalog_component_id:
            catalog_item = db.query(CatalogComponent).get(component.catalog_component_id)
            if catalog_item:
                unit_cost = catalog_item.unit_price
        line = BomLineItem(
            bom_id=bom.id,
            component_id=component.id,
            part_number=component.part_number,
            description=component.description,
            category=component.category,
            quantity=component.quantity,
            material=component.material,
            make_buy=component.make_buy,
            catalog_component_id=component.catalog_component_id,
            unit_cost=unit_cost,
        )
        db.add(line)
        db.flush()
        id_map[component.id] = line.id

    for component in analysis.components:
        if component.parent_component_id and component.parent_component_id in id_map:
            line = db.query(BomLineItem).filter(
                BomLineItem.component_id == component.id, BomLineItem.bom_id == bom.id
            ).first()
            if line:
                line.parent_line_item_id = id_map[component.parent_component_id]

    drawing = db.query(Drawing).get(analysis.drawing_id)
    if drawing:
        drawing.status = DrawingStatus.BOM_GENERATED

    db.flush()
    recompute_rollup(db, bom.id)

    db.add(AuditLog(entity_type="bom", entity_id=bom.id, action="generated",
                     details={"analysis_id": analysis.id, "line_count": len(analysis.components)},
                     actor=actor))
    db.commit()
    db.refresh(bom)
    return bom

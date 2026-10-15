from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import Analysis, Bom, BomLineItem, Drawing, DrawingStatus, AuditLog


def generate_bom_from_analysis(db: Session, analysis: Analysis) -> Bom:
    """Builds a new BOM (versioned) from a persisted analysis's components.
    Flat with parent_line_item_id preserved for future multi-level UI."""
    existing_count = db.query(Bom).filter(Bom.analysis_id == analysis.id).count()
    bom = Bom(drawing_id=analysis.drawing_id, analysis_id=analysis.id, version=existing_count + 1,
               status="Draft")
    db.add(bom)
    db.flush()

    id_map: dict[str, str] = {}
    for component in analysis.components:
        line = BomLineItem(
            bom_id=bom.id,
            component_id=component.id,
            part_number=component.part_number,
            description=component.description,
            category=component.category,
            quantity=component.quantity,
            material=component.material,
            make_buy=component.make_buy,
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

    db.add(AuditLog(entity_type="bom", entity_id=bom.id, action="generated",
                     details={"analysis_id": analysis.id, "line_count": len(analysis.components)}))
    db.commit()
    db.refresh(bom)
    return bom

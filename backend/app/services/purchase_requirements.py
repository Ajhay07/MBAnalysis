from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import Bom, CatalogComponent, Component


def _availability(stock_quantity: float | None, required_quantity: float) -> str:
    """Stock state for a Buy line against the matched catalog row's on-hand count.
    Unknown (no stock data recorded) is kept distinct from Out of Stock - a catalog row that
    was never given a stock count must never be reported as if it were confirmed empty."""
    if stock_quantity is None:
        return "Unknown"
    if stock_quantity <= 0:
        return "Out of Stock"
    if stock_quantity < required_quantity:
        return "Low Stock"
    return "In Stock"


def build_purchase_requirements(db: Session, bom: Bom) -> dict:
    """Purchase-requirements view of a BOM: every line split into Buy (from suppliers) vs
    Make (in-house), each with quantity, material/grade/spec, and - for Buy lines matched to
    the source catalog (app.services.catalog_matching) - unit price, stock availability, and
    an estimated line cost. Never fabricates a price or stock figure for an unmatched part;
    those fields are simply null, and the summary separately counts how many Buy lines have
    no cost estimate so a reviewer knows the total is a partial figure, not a quote."""
    catalog_by_id = {c.id: c for c in db.query(CatalogComponent).all()}
    # BomLineItem doesn't carry grade/dimensions - pull those from the originating Component
    # (the richer, OCR/vision-extracted record) when the line is still linked to one.
    component_by_id = {
        c.id: c for c in db.query(Component).filter(
            Component.id.in_([li.component_id for li in bom.line_items if li.component_id])
        ).all()
    } if bom.line_items else {}

    buy, make, review = [], [], []
    priced_cost_total = 0.0
    buy_count_missing_price = 0

    for li in bom.line_items:
        component = component_by_id.get(li.component_id)
        catalog_item = catalog_by_id.get(li.catalog_component_id) if li.catalog_component_id else None
        key = (li.make_buy.value if hasattr(li.make_buy, "value") else li.make_buy)

        row = {
            "line_item_id": li.id,
            "part_number": li.part_number,
            "description": li.description,
            "category": li.category,
            "quantity": li.quantity,
            "total_quantity": li.total_quantity,
            "material": li.material,
            "grade": component.grade if component else "",
            "dimensions": component.dimensions if component else {},
            "tolerances": component.tolerances if component else {},
        }

        if key == "Buy":
            unit_price = li.unit_cost if li.unit_cost is not None else (
                catalog_item.unit_price if catalog_item else None)
            quantity_for_cost = li.total_quantity if li.total_quantity is not None else li.quantity
            estimated_cost = unit_price * quantity_for_cost if unit_price is not None else None
            if estimated_cost is not None:
                priced_cost_total += estimated_cost
            else:
                buy_count_missing_price += 1
            row.update({
                "catalog_component_id": li.catalog_component_id,
                "unit_price": unit_price,
                "currency": catalog_item.currency if catalog_item else None,
                "estimated_cost": estimated_cost,
                "stock_quantity": catalog_item.stock_quantity if catalog_item else None,
                "availability": _availability(
                    catalog_item.stock_quantity if catalog_item else None, quantity_for_cost),
                "supplier_id": li.supplier_id,
            })
            buy.append(row)
        elif key == "Make":
            make.append(row)
        else:
            review.append(row)

    return {
        "bom_id": bom.id,
        "buy": buy,
        "make": make,
        "review": review,
        "summary": {
            "buy_item_count": len(buy),
            "make_item_count": len(make),
            "review_item_count": len(review),
            "estimated_total_cost": round(priced_cost_total, 2) if buy else None,
            "buy_items_missing_price": buy_count_missing_price,
            "is_partial_estimate": buy_count_missing_price > 0,
        },
    }

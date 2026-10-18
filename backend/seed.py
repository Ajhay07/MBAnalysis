"""Seeds 3 realistic demo projects (gearbox assembly, shaft+bearing assembly, sheet-metal
bracket) with drawings, analyses, components, BOMs, suppliers and catalog rows.

Run standalone: python seed.py
Or imported and called as seed_demo_data(db) from the /api/demo/load endpoint.
All demo content is clearly flagged is_demo=True / verification_status/notes mention DEMO,
and lives under seed_assets/ as line-drawing SVGs rather than fabricated raster scans.
"""
import os
import shutil

from app.config import get_settings
from app.database import SessionLocal, Base, engine
from app.models.models import (
    Drawing, Analysis, Component, Bom, BomLineItem, Supplier, CatalogComponent,
    DrawingStatus, MakeBuy, AuditLog, InventoryLot,
)
from app.services.catalog_matching import match_catalog_component

# Baseline purchased-part catalog, deliberately keyed to the same part numbers used by the
# seeded BUY components above (6205-2RS, 6005-2Z, M6-BOLT, SH-2002-05) so the demo shows the
# OCR-to-catalog matching feature (app.services.catalog_matching) working out of the box,
# without requiring a real analysis run first.
# stock_quantity is deliberately spread across available/low/out-of-stock/unknown so the
# Purchase Requirements view (app.services.purchase_requirements) shows all four states out
# of the box, rather than everything looking "fine" in the demo.
DEMO_CATALOG = [
    dict(part_number="6205-2RS", description="[DEMO] Deep Groove Ball Bearing", category="Bearing",
         unit_price=4.25, currency="USD", stock_quantity=50),
    dict(part_number="6005-2Z", description="[DEMO] Ball Bearing", category="Bearing",
         unit_price=3.10, currency="USD", stock_quantity=1),  # below the seeded qty=2 -> Low Stock
    dict(part_number="M6-BOLT", description="[DEMO] Hex Bolt M6x20", category="Fastener",
         unit_price=0.18, currency="USD", stock_quantity=500),
    dict(part_number="SH-2002-05", description="[DEMO] Retaining Ring", category="Fastener",
         unit_price=0.65, currency="USD", stock_quantity=0),  # -> Out of Stock
    dict(part_number="TIE-ROD-M16", description="[DEMO] Tie Rod M16", category="Fastener",
         unit_price=2.40, currency="USD", stock_quantity=12),
    dict(part_number="HEX-NUT-M16", description="[DEMO] Hex Nut M16", category="Fastener",
         unit_price=0.22, currency="USD", stock_quantity=4),  # below the seeded qty=8 -> Low Stock
]

# Demo inventory lots, deliberately tied to the seeded gearbox/shaft/bracket BOM line items
# above so the live demo can show a non-trivial availability spread: some AVAILABLE, some
# PARTIAL, some OUT_OF_STOCK, and at least one REVIEW_REQUIRED (via an unmatched/ambiguous item
# or an unverified spec - see GB-1001-10 / Housing, which is Unverified above).
DEMO_INVENTORY_LOTS = [
    # Plenty of stock -> AVAILABLE at the demo production quantities used in tests/UI.
    dict(material_code="6205-2RS", material="", grade="", description="[DEMO] Deep Groove Ball Bearing",
         unit="ea", on_hand_qty="50", reserved_qty="0", quarantined_qty="0", location="Bin A-12"),
    dict(material_code="6005-2Z", material="", grade="", description="[DEMO] Ball Bearing",
         unit="ea", on_hand_qty="40", reserved_qty="0", quarantined_qty="0", location="Bin A-14"),
    dict(material_code="M6-BOLT", material="", grade="", description="[DEMO] Hex Bolt M6x20",
         unit="ea", on_hand_qty="500", reserved_qty="0", quarantined_qty="0", location="Bin C-02"),
    # Steel 4140 for the input shaft - enough for a couple of units but not many -> PARTIAL at
    # higher production quantities.
    dict(material_code=None, material="Steel 4140", grade="Q&T", description="[DEMO] Steel 4140 bar stock",
         unit="ea", on_hand_qty="3", reserved_qty="0", quarantined_qty="0", location="Rack R-3",
         lot_number="L-4140-01"),
    # Steel 8620 for gears - some quarantined (pending incoming inspection), tight supply.
    dict(material_code=None, material="Steel 8620", grade="Carburized", description="[DEMO] Steel 8620 bar stock",
         unit="ea", on_hand_qty="2", reserved_qty="1", quarantined_qty="1", location="Rack R-5",
         lot_number="L-8620-01"),
    # Retaining ring / spring steel: zero stock -> OUT_OF_STOCK.
    dict(material_code="SH-2002-05", material="Spring Steel", grade="", description="[DEMO] Retaining Ring stock",
         unit="ea", on_hand_qty="0", reserved_qty="0", quarantined_qty="0", location="Bin D-01"),
    # No lot at all for the bracket's galvanized steel -> REVIEW_REQUIRED (unmatched), in
    # addition to the Unverified housing component already producing a REVIEW_REQUIRED line.
]

SEED_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_assets")

PROJECTS = [
    {
        "drawing_number": "GB-1001",
        "title": "[DEMO] Gearbox Assembly",
        "revision": "B",
        "asset": "gearbox_assembly.svg",
        "components": [
            dict(part_number="GB-1001-01", description="[DEMO] Input Shaft", category="Shaft",
                 quantity=1, material="Steel 4140", grade="Q&T", make_buy=MakeBuy.MAKE,
                 confidence=0.92, verification_status="Verified",
                 gear_specs={}, dimensions={"length_mm": 300, "diameter_mm": 25}),
            dict(part_number="GB-1001-02", description="[DEMO] Output Gear, 48T", category="Gear",
                 quantity=1, material="Steel 8620", grade="Carburized", make_buy=MakeBuy.MAKE,
                 confidence=0.88, verification_status="Verified",
                 gear_specs={"teeth": 48, "pitch_diameter_mm": 96, "module": 2.0}),
            dict(part_number="GB-1001-03", description="[DEMO] Pinion Gear, 18T", category="Gear",
                 quantity=1, material="Steel 8620", grade="Carburized", make_buy=MakeBuy.MAKE,
                 confidence=0.85, verification_status="Verified",
                 gear_specs={"teeth": 18, "pitch_diameter_mm": 36, "module": 2.0}),
            dict(part_number="6205-2RS", description="[DEMO] Deep Groove Ball Bearing", category="Bearing",
                 quantity=2, material="", grade="", make_buy=MakeBuy.BUY, confidence=0.95,
                 verification_status="Verified", dimensions={}),
            dict(part_number="GB-1001-10", description="[DEMO] Housing, Cast", category="Housing",
                 quantity=1, material="Aluminum A356", grade="T6", make_buy=MakeBuy.MAKE,
                 confidence=0.55, verification_status="Unverified", dimensions={}),
        ],
    },
    {
        "drawing_number": "SH-2002",
        "title": "[DEMO] Shaft & Bearing Assembly",
        "revision": "A",
        "asset": "shaft_bearing_assembly.svg",
        "components": [
            dict(part_number="SH-2002-01", description="[DEMO] Main Shaft", category="Shaft",
                 quantity=1, material="Steel 1045", grade="Normalized", make_buy=MakeBuy.MAKE,
                 confidence=0.9, verification_status="Verified",
                 dimensions={"length_mm": 500, "diameter_mm": 25, "tolerance": "h7"}),
            dict(part_number="6005-2Z", description="[DEMO] Ball Bearing", category="Bearing",
                 quantity=2, material="", grade="", make_buy=MakeBuy.BUY, confidence=0.93,
                 verification_status="Verified"),
            dict(part_number="SH-2002-05", description="[DEMO] Retaining Ring", category="Fastener",
                 quantity=2, material="Spring Steel", grade="", make_buy=MakeBuy.BUY, confidence=0.7,
                 verification_status="Unverified"),
        ],
    },
    {
        "drawing_number": "BR-3003",
        "title": "[DEMO] Sheet Metal Bracket",
        "revision": "C",
        "asset": "sheet_metal_bracket.svg",
        "components": [
            dict(part_number="BR-3003-01", description="[DEMO] Mounting Bracket", category="Bracket",
                 quantity=1, material="Steel, Galvanized", grade="14 GA", make_buy=MakeBuy.MAKE,
                 confidence=0.8, verification_status="Verified",
                 dimensions={"length_mm": 300, "width_mm": 200, "thickness_mm": 2.0}),
            dict(part_number="M6-BOLT", description="[DEMO] Hex Bolt M6x20", category="Fastener",
                 quantity=4, material="", grade="8.8", make_buy=MakeBuy.BUY, confidence=0.97,
                 verification_status="Verified"),
        ],
    },
    {
        "drawing_number": "EX-1005",
        "title": "[DEMO] Bellows Assembly",
        "revision": "A",
        "scale": "1:4",
        "asset": "bellows_assembly.svg",
        "status": DrawingStatus.NEEDS_REVIEW,
        "with_bom": False,
        "components": [
            dict(part_number="BLW-1005-01", description="[DEMO] Bellows Element, 10 convolutions", category="Bellows",
                 quantity=1, material="Stainless Steel 321", grade="ASTM A240", make_buy=MakeBuy.MAKE,
                 confidence=0.82, verification_status="Unverified",
                 dimensions={"length_mm": 452, "od_mm": 230, "convolutions": 10}),
            dict(part_number="FLG-1005-02", description="[DEMO] Flange ASME B16.5 150#", category="Flange",
                 quantity=2, material="Carbon Steel", grade="A105", make_buy=MakeBuy.MAKE,
                 confidence=0.74, verification_status="Unverified", dimensions={"od_mm": 260}),
            dict(part_number="LNR-1005-03", description="[DEMO] Internal Liner", category="Liner",
                 quantity=1, material="Stainless Steel 304", grade="", make_buy=MakeBuy.REVIEW,
                 confidence=0.48, verification_status="Unverified"),
            dict(part_number="TIE-ROD-M16", description="[DEMO] Tie Rod M16", category="Fastener",
                 quantity=4, material="Alloy Steel", grade="B7", make_buy=MakeBuy.BUY,
                 confidence=0.91, verification_status="Unverified"),
            dict(part_number="HEX-NUT-M16", description="[DEMO] Hex Nut M16", category="Fastener",
                 quantity=8, material="", grade="2H", make_buy=MakeBuy.BUY,
                 confidence=0.93, verification_status="Unverified"),
        ],
    },
    {
        "drawing_number": "PL-4001",
        "title": "[DEMO] Pipe Expansion Joint",
        "revision": "B",
        "scale": "1:5",
        "asset": "pipe_expansion_joint.svg",
        "status": DrawingStatus.UPLOADED,
        "components": [],
    },
]


def seed_demo_data(db, actor: str = "system") -> int:
    settings = get_settings()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Baseline suppliers / catalog (no fabricated prices)
    if db.query(Supplier).count() == 0:
        db.add(Supplier(name="[DEMO] McMaster-Carr (placeholder)", contact_name=None,
                         email=None, phone=None, notes="Demo supplier - no real account"))
        db.add(Supplier(name="[DEMO] Local Machine Shop (placeholder)", contact_name=None,
                         email=None, phone=None, notes="Demo supplier - no real account"))
        db.commit()

    existing_parts = {c.part_number for c in db.query(CatalogComponent).all()}
    for row in DEMO_CATALOG:
        if row["part_number"] not in existing_parts:
            db.add(CatalogComponent(**row))
    db.commit()
    catalog = db.query(CatalogComponent).all()

    created = 0
    for proj in PROJECTS:
        existing = db.query(Drawing).filter(Drawing.drawing_number == proj["drawing_number"],
                                             Drawing.is_demo == True).first()  # noqa: E712
        if existing:
            continue

        src_asset = os.path.join(SEED_ASSETS_DIR, proj["asset"])
        stored_name = f"demo_{proj['asset']}"
        dst_asset = os.path.join(os.path.abspath(settings.UPLOAD_DIR), stored_name)
        if os.path.exists(src_asset):
            shutil.copyfile(src_asset, dst_asset)
        size = os.path.getsize(dst_asset) if os.path.exists(dst_asset) else 0

        drawing = Drawing(
            drawing_number=proj["drawing_number"], title=proj["title"], revision=proj["revision"],
            file_name=proj["asset"], stored_file_name=stored_name, file_type="svg", file_size=size,
            units="mm", scale=proj.get("scale", "1:2"), status=proj.get("status", DrawingStatus.REVIEWED),
            is_demo=True,
        )
        db.add(drawing)
        db.flush()

        if proj["components"]:
            analysis = Analysis(
                drawing_id=drawing.id, version=1, provider="demo-seed",
                title_block={"drawing_number": proj["drawing_number"], "title": proj["title"],
                             "revision": proj["revision"], "units": "mm", "scale": proj.get("scale", "1:2"),
                             "material_spec": "See BOM"},
                dimensions=[], materials=sorted({c["material"] for c in proj["components"] if c["material"]}),
                raw_ocr_text="[DEMO] seeded analysis - not derived from OCR",
                overall_confidence=sum(c["confidence"] for c in proj["components"]) / len(proj["components"]),
            )
            db.add(analysis)
            db.flush()

            for c in proj["components"]:
                matched, score = match_catalog_component(c["part_number"], c["description"], catalog)
                db.add(Component(
                    analysis_id=analysis.id, part_number=c["part_number"], description=c["description"],
                    category=c["category"], quantity=c["quantity"], material=c["material"],
                    grade=c["grade"], dimensions=c.get("dimensions", {}), tolerances={},
                    gear_specs=c.get("gear_specs", {}), make_buy=c["make_buy"],
                    confidence=c["confidence"], verification_status=c["verification_status"],
                    source_page=1, source_region={}, source_text="[DEMO] seeded, no source drawing text",
                    catalog_component_id=matched.id if matched else None,
                    catalog_match_score=score if matched else None,
                ))
            db.flush()

            if proj.get("with_bom", True):
                bom = Bom(drawing_id=drawing.id, analysis_id=analysis.id, version=1, status="Draft")
                db.add(bom)
                db.flush()
                for comp in db.query(Component).filter(Component.analysis_id == analysis.id).all():
                    catalog_item = next((c for c in catalog if c.id == comp.catalog_component_id), None)
                    db.add(BomLineItem(
                        bom_id=bom.id, component_id=comp.id, part_number=comp.part_number,
                        description=comp.description, category=comp.category, quantity=comp.quantity,
                        material=comp.material, make_buy=comp.make_buy,
                        catalog_component_id=comp.catalog_component_id,
                        unit_cost=catalog_item.unit_price if catalog_item else None,
                    ))
                db.flush()
                # These seeded BOMs are flat (no parent_line_item_id), but recompute_rollup still needs
                # to run so each line's total_quantity (qty-per-assembly rolled up) is populated rather
                # than left null - inventory availability treats a null total_quantity as "rollup
                # undetermined" (REVIEW_REQUIRED), which would otherwise make every seeded line review-
                # required regardless of actual stock.
                from app.services.bom_service import recompute_rollup
                recompute_rollup(db, bom.id)

        db.add(AuditLog(entity_type="drawing", entity_id=drawing.id, action="demo_seeded", details={},
                         actor=actor))
        created += 1

    if db.query(InventoryLot).filter(InventoryLot.is_demo == True).count() == 0:  # noqa: E712
        for lot in DEMO_INVENTORY_LOTS:
            db.add(InventoryLot(is_demo=True, **lot))
        db.commit()

    db.commit()
    return created


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        n = seed_demo_data(session)
        print(f"Seeded {n} demo project(s).")
    finally:
        session.close()

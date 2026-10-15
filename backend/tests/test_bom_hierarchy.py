from app.models.models import Drawing, Analysis, Bom, BomLineItem, DrawingStatus, MakeBuy, UserRole
from app.services.bom_service import would_create_cycle, recompute_rollup, build_bom_tree


def _make_bom(db):
    drawing = Drawing(drawing_number="H-1", title="Hierarchy Drawing", revision="A",
                       file_name="h.png", stored_file_name="h_stored.png", file_type="png",
                       file_size=10, status=DrawingStatus.REVIEWED)
    db.add(drawing)
    db.flush()
    analysis = Analysis(drawing_id=drawing.id, version=1, provider="test",
                         title_block={}, dimensions=[], materials=[], overall_confidence=0.8)
    db.add(analysis)
    db.flush()
    bom = Bom(drawing_id=drawing.id, analysis_id=analysis.id, version=1, status="Draft")
    db.add(bom)
    db.commit()
    db.refresh(bom)
    return bom


def _line(db, bom, part_number, quantity, parent=None, make_buy=MakeBuy.MAKE):
    li = BomLineItem(bom_id=bom.id, part_number=part_number, description=part_number,
                      category="", quantity=quantity, material="", make_buy=make_buy,
                      parent_line_item_id=parent.id if parent else None)
    db.add(li)
    db.commit()
    db.refresh(li)
    return li


def test_two_level_rollup(db):
    bom = _make_bom(db)
    top = _line(db, bom, "ASSY", 2)
    child = _line(db, bom, "BOLT", 4, parent=top)
    recompute_rollup(db, bom.id)
    db.refresh(top)
    db.refresh(child)
    assert top.total_quantity == 2
    assert child.total_quantity == 8  # 4 per assembly * 2 assemblies


def test_three_level_nested_rollup(db):
    bom = _make_bom(db)
    top = _line(db, bom, "MACHINE", 3)
    sub = _line(db, bom, "GEARBOX", 2, parent=top)
    leaf = _line(db, bom, "GEAR", 5, parent=sub)
    recompute_rollup(db, bom.id)
    db.refresh(leaf)
    db.refresh(sub)
    assert sub.total_quantity == 6       # 2 * 3
    assert leaf.total_quantity == 30     # 5 * 2 * 3


def test_rollup_left_null_when_quantity_unknown(db):
    bom = _make_bom(db)
    top = _line(db, bom, "ASSY", 1)
    top.quantity = None  # simulate an ambiguous/unknown qty-per-assembly after the fact
    db.commit()
    child = _line(db, bom, "PART", 4, parent=top)
    recompute_rollup(db, bom.id)
    db.refresh(top)
    db.refresh(child)
    assert top.total_quantity is None
    assert child.total_quantity is None  # ambiguous multiplier up the chain


def test_would_create_cycle_detects_self_parent(db):
    bom = _make_bom(db)
    a = _line(db, bom, "A", 1)
    assert would_create_cycle(db, bom.id, a.id, a.id) is True


def test_would_create_cycle_detects_indirect_cycle(db):
    bom = _make_bom(db)
    a = _line(db, bom, "A", 1)
    b = _line(db, bom, "B", 1, parent=a)
    c = _line(db, bom, "C", 1, parent=b)
    # Making A's parent = C would close the loop A -> B -> C -> A
    assert would_create_cycle(db, bom.id, a.id, c.id) is True


def test_would_create_cycle_allows_valid_reparenting(db):
    bom = _make_bom(db)
    a = _line(db, bom, "A", 1)
    b = _line(db, bom, "B", 1)
    assert would_create_cycle(db, bom.id, b.id, a.id) is False


def test_update_line_item_rejects_cycle_via_api(client, db, make_user):
    user, password = make_user(role=UserRole.ENGINEER)
    login = client.post("/api/auth/login", json={"email": user.email, "password": password})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    bom = _make_bom(db)
    a = _line(db, bom, "A", 1)
    b = _line(db, bom, "B", 1, parent=a)

    resp = client.patch(f"/api/boms/line-items/{a.id}", json={"parent_line_item_id": b.id},
                         headers=headers)
    assert resp.status_code == 400


def test_tree_endpoint_matches_seeded_hierarchy(client, db, make_user):
    user, password = make_user(role=UserRole.VIEWER)
    login = client.post("/api/auth/login", json={"email": user.email, "password": password})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    bom = _make_bom(db)
    top = _line(db, bom, "TOP", 1)
    mid = _line(db, bom, "MID", 2, parent=top)
    _line(db, bom, "LEAF", 3, parent=mid)
    recompute_rollup(db, bom.id)

    resp = client.get(f"/api/boms/{bom.id}/tree", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 1
    top_node = data["nodes"][0]
    assert top_node["part_number"] == "TOP"
    assert len(top_node["children"]) == 1
    mid_node = top_node["children"][0]
    assert mid_node["part_number"] == "MID"
    assert len(mid_node["children"]) == 1
    assert mid_node["children"][0]["part_number"] == "LEAF"
    assert mid_node["children"][0]["total_quantity"] == 6


def test_export_includes_level_and_parent_columns(db):
    from app.services.export_service import bom_to_dataframe

    bom = _make_bom(db)
    top = _line(db, bom, "TOP", 1)
    child = _line(db, bom, "CHILD", 2, parent=top)
    recompute_rollup(db, bom.id)
    db.refresh(bom)

    df = bom_to_dataframe(bom)
    assert "Level" in df.columns
    assert "Parent Item Number" in df.columns
    top_row = df[df["Part Number"] == "TOP"].iloc[0]
    child_row = df[df["Part Number"] == "CHILD"].iloc[0]
    assert top_row["Level"] == 0
    assert child_row["Level"] == 1
    assert child_row["Parent Item Number"] == "TOP"

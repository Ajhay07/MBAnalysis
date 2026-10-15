"""Auth/authorization coverage: login, token validation, route protection, role gating, and
that the audit trail records the real authenticated actor instead of the "system" default."""
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.models.models import AuditLog, BomLineItem, MakeBuy, UserRole
from app.security import get_jwt_secret


def test_unauthenticated_request_to_protected_endpoint_returns_401(client):
    resp = client.get("/api/dashboard/metrics")
    assert resp.status_code == 401


def test_login_with_wrong_password_returns_401(client, make_user):
    user, password = make_user(role=UserRole.VIEWER)
    resp = client.post("/api/auth/login", json={"email": user.email, "password": "not-the-password"})
    assert resp.status_code == 401


def test_login_with_unknown_email_returns_401(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert resp.status_code == 401


def test_valid_login_returns_usable_token_and_sets_cookie(client, make_user):
    user, password = make_user(role=UserRole.VIEWER)
    resp = client.post("/api/auth/login", json={"email": user.email, "password": password})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert "access_token" in resp.cookies


def test_cookie_from_login_works_on_protected_endpoint(client, make_user):
    user, password = make_user(role=UserRole.VIEWER)
    login = client.post("/api/auth/login", json={"email": user.email, "password": password})
    assert login.status_code == 200

    # Same TestClient instance carries the cookie jar forward automatically.
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == user.email
    assert me.json()["role"] == "viewer"


def test_bearer_token_works_on_protected_endpoint(client, make_user):
    """Token transport also accepts a plain Authorization header, independent of the cookie -
    verified here with a client that never received the login cookie."""
    user, password = make_user(role=UserRole.ENGINEER)
    login = client.post("/api/auth/login", json={"email": user.email, "password": password})
    token = login.json()["access_token"]

    from fastapi.testclient import TestClient
    from app.main import app

    bare_client = TestClient(app)  # fresh cookie jar
    resp = bare_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == user.email


def test_invalid_token_is_rejected(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_expired_token_is_rejected(client, make_user):
    user, _ = make_user(role=UserRole.VIEWER)
    expired_payload = {
        "sub": user.id,
        "role": "viewer",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
    }
    expired_token = jwt.encode(expired_payload, get_jwt_secret(), algorithm="HS256")
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


def test_logout_clears_cookie(client, make_user):
    user, password = make_user(role=UserRole.VIEWER)
    client.post("/api/auth/login", json={"email": user.email, "password": password})
    assert client.get("/api/auth/me").status_code == 200

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_role_gated_action_rejected_for_viewer(client, make_user):
    user, password = make_user(role=UserRole.VIEWER)
    client.post("/api/auth/login", json={"email": user.email, "password": password})

    # Role check runs before the BOM lookup, so a nonexistent id still proves the permission
    # boundary: a viewer gets 403 without ever reaching the "does this BOM exist" logic.
    resp = client.post("/api/boms/does-not-exist/approve")
    assert resp.status_code == 403


def test_role_gated_action_allowed_for_admin_and_engineer(client, make_user):
    for role in (UserRole.ADMIN, UserRole.ENGINEER):
        user, password = make_user(role=role)
        login_client_resp = client.post("/api/auth/login", json={"email": user.email, "password": password})
        assert login_client_resp.status_code == 200

        # Passed the role gate -> reaches the route body -> 404 (no such BOM), not 403.
        resp = client.post("/api/boms/does-not-exist/approve")
        assert resp.status_code == 404, f"role {role} should pass the permission check"


def test_audit_log_records_real_authenticated_actor(client, db, make_user):
    admin, password = make_user(role=UserRole.ADMIN)
    line = BomLineItem(
        bom_id="fake-bom-id-for-test", part_number="X-1", description="Original",
        category="Fastener", quantity=1, material="Steel", make_buy=MakeBuy.MAKE,
    )
    db.add(line)
    db.commit()
    db.refresh(line)

    login = client.post("/api/auth/login", json={"email": admin.email, "password": password})
    assert login.status_code == 200

    resp = client.patch(f"/api/boms/line-items/{line.id}", json={"description": "Updated"})
    assert resp.status_code == 200

    audit = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "bom_line_item", AuditLog.entity_id == line.id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.actor == admin.email
    assert audit.actor != "system"

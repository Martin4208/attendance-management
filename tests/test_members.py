import jwt
import uuid
from datetime import datetime, timedelta, timezone

from app.config import settings
from tests.helpers import create_tenant_user


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_member_can_list_own_tenant_members(client):
    tenant_id, token = create_tenant_user(client, "test@email.com", "string")
    
    # メンバー一覧取得
    res = client.get( f"/tenants/{tenant_id}/members", headers=auth(token) )
    
    assert res.status_code == 200
    members = res.json()
    assert len(members) == 1
    assert members[0]["email"] == "test@email.com"
    assert members[0]["role"] == "owner"
    assert "password_hash" not in members[0]
    
    
def test_list_contains_only_own_tenant_members(client):
    tenant_a, token_a = create_tenant_user(client, "a@example.com", "A社")
    create_tenant_user(client, "b@example.com", "B社")

    res = client.get(f"/tenants/{tenant_a}/members", headers=auth(token_a))

    assert res.status_code == 200
    emails = [m["email"] for m in res.json()]
    assert emails == ["a@example.com"]          # B社のメンバーが混ざらない


def test_cannot_access_other_tenant(client):
    tenant_a, token_a = create_tenant_user(client, "a@example.com", "A社")
    tenant_b, token_b = create_tenant_user(client, "b@example.com", "B社")

    res = client.get(f"/tenants/{tenant_b}/members", headers=auth(token_a))

    assert res.status_code == 403
    assert "b@example.com" not in res.text      # 本文に他社の情報が漏れない


def test_nonexistent_tenant_returns_403(client):
    _, token_a = create_tenant_user(client, "a@example.com", "A社")

    res = client.get(f"/tenants/{uuid.uuid4()}/members", headers=auth(token_a))

    assert res.status_code == 403


def test_other_tenant_and_nonexistent_tenant_look_identical(client):
    _, token_a = create_tenant_user(client, "a@example.com", "A社")
    tenant_b, _ = create_tenant_user(client, "b@example.com", "B社")

    other = client.get(f"/tenants/{tenant_b}/members", headers=auth(token_a))
    missing = client.get(f"/tenants/{uuid.uuid4()}/members", headers=auth(token_a))

    # テナントの存在有無を、応答から推測できない
    assert other.status_code == missing.status_code
    assert other.json() == missing.json()


def test_invalid_tenant_id_returns_422(client):
    _, token = create_tenant_user(client, "a@example.com", "A社")

    res = client.get("/tenants/abc/members", headers=auth(token))

    assert res.status_code == 422


def test_no_token_is_rejected(client):
    tenant_id, _ = create_tenant_user(client, "a@example.com", "A社")

    res = client.get(f"/tenants/{tenant_id}/members")

    assert res.status_code in (401, 403)        # HTTPBearer のバージョンで違う


def test_tampered_token_is_rejected(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{'A' * len(signature)}"   # 署名を差し替える

    res = client.get(f"/tenants/{tenant_id}/members", headers=auth(tampered))

    assert res.status_code == 401


def test_expired_token_is_rejected(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    sub = jwt.decode(token, options={"verify_signature": False})["sub"]
    expired = jwt.encode(
        {"sub": sub, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    res = client.get(f"/tenants/{tenant_id}/members", headers=auth(expired))

    assert res.status_code == 401
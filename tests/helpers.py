from datetime import datetime
import uuid
import jwt

from app.models import Membership


def create_tenant_user(client, email: str, tenant_name: str):
    # サインアップ
    signup = client.post("/auth/signup", json={ "tenant_name": tenant_name, "user_name": "string", "email": email, "password": "password" })
    assert signup.status_code == 201
    tenant_id = signup.json()["tenant_id"]
    
    # ログイン
    login = client.post("/auth/login", json={ "email": email, "password": "password" })
    assert login.status_code == 200
    token = login.json()["access_token"]
    
    return tenant_id, token


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


auth_headers = auth  # 別名


def patch_url(tenant_id, record_id) -> str:
    return f"/tenants/{tenant_id}/attendance/{record_id}"


def iso(dt: datetime) -> str:
    return dt.isoformat()


def to_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


def get_user_id(client, token: str) -> str:
    return jwt.decode(token, options={"verify_signature": False})["sub"]


def make_records(client, tenant_id, token, n):
    """出勤→退勤を n 回繰り返し、作った勤怠の id を古い順で返す。"""
    ids = []
    for _ in range(n):
        res_in = client.post(
            f"/tenants/{tenant_id}/attendance/clock-in", headers=auth(token)
        )
        assert res_in.status_code == 201
        ids.append(res_in.json()["id"])
        res_out = client.post(
            f"/tenants/{tenant_id}/attendance/clock-out", headers=auth(token)
        )
        assert res_out.status_code == 200
    return ids


def add_member(client, db, tenant_id, email, role="member"):
    """別テナントでユーザーを作り、その人を tenant_id の所属として DB に直接追加する。

    メンバー追加 API(Day 6)ができるまでの暫定。(user_id, token) を返す。
    """
    _, token = create_tenant_user(client, email, f"{email} の会社")
    user_id = get_user_id(client, token)
    db.add(
        Membership(
            tenant_id=to_uuid(tenant_id),
            user_id=to_uuid(user_id),
            role=role,
        )
    )
    db.commit()
    return user_id, token
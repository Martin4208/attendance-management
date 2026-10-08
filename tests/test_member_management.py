from sqlalchemy import select, update

from app.models import Plan, Tenant
from tests.helpers import auth, create_tenant_user, get_user_id, to_uuid


def new_user(client, email):
    """別テナントでユーザーを作る。(user_id, token) を返す。"""
    _, token = create_tenant_user(client, email, f"{email} co")
    return get_user_id(client, token), token


def add(client, tenant_id, token, email, role="member"):
    return client.post(
        f"/tenants/{tenant_id}/members",
        json={"email": email, "role": role},
        headers=auth(token),
    )


def change_role(client, tenant_id, token, user_id, role):
    return client.patch(
        f"/tenants/{tenant_id}/members/{user_id}/role",
        json={"role": role},
        headers=auth(token),
    )


def remove(client, tenant_id, token, user_id):
    return client.delete(
        f"/tenants/{tenant_id}/members/{user_id}", headers=auth(token)
    )


def setup_team(client, member_email="m@example.com", admin_email="ad@example.com"):
    """owner / admin / member の 3 人がいるテナントを作る。"""
    tenant_id, owner = create_tenant_user(client, "owner@example.com", "A社")
    owner_id = get_user_id(client, owner)
    admin_id, admin = new_user(client, admin_email)
    member_id, member = new_user(client, member_email)
    assert add(client, tenant_id, owner, admin_email, "admin").status_code == 201
    assert add(client, tenant_id, owner, member_email, "member").status_code == 201
    return {
        "tenant_id": tenant_id,
        "owner": owner, "owner_id": owner_id,
        "admin": admin, "admin_id": admin_id,
        "member": member, "member_id": member_id,
    }


# ---------- 追加 ----------

def test_owner_can_add_member(client):
    tenant_id, owner = create_tenant_user(client, "owner@example.com", "A社")
    uid, utoken = new_user(client, "m@example.com")

    res = add(client, tenant_id, owner, "m@example.com")

    assert res.status_code == 201
    body = res.json()
    assert body["user_id"] == uid
    assert body["role"] == "member"
    assert "password_hash" not in body
    listed = client.get(f"/tenants/{tenant_id}/members", headers=auth(owner)).json()
    assert uid in [m["user_id"] for m in listed]
    # 追加された人が、実際にそのテナントを使える
    clock_in = client.post(
        f"/tenants/{tenant_id}/attendance/clock-in", headers=auth(utoken)
    )
    assert clock_in.status_code == 201


def test_add_is_case_insensitive_for_email(client):
    tenant_id, owner = create_tenant_user(client, "owner@example.com", "A社")
    new_user(client, "m@example.com")

    res = add(client, tenant_id, owner, "M@Example.com")

    assert res.status_code == 201


def test_admin_can_add_member_but_not_admin(client):
    t = setup_team(client)
    new_user(client, "x@example.com")
    new_user(client, "y@example.com")

    ok = add(client, t["tenant_id"], t["admin"], "x@example.com", "member")
    ng = add(client, t["tenant_id"], t["admin"], "y@example.com", "admin")

    assert ok.status_code == 201
    assert ng.status_code == 403


def test_member_cannot_add(client):
    t = setup_team(client)
    new_user(client, "x@example.com")

    res = add(client, t["tenant_id"], t["member"], "x@example.com")

    assert res.status_code == 403


def test_add_unknown_email_returns_404(client):
    tenant_id, owner = create_tenant_user(client, "owner@example.com", "A社")

    res = add(client, tenant_id, owner, "nobody@example.com")

    assert res.status_code == 404


def test_add_twice_returns_409(client):
    tenant_id, owner = create_tenant_user(client, "owner@example.com", "A社")
    new_user(client, "m@example.com")

    first = add(client, tenant_id, owner, "m@example.com")
    second = add(client, tenant_id, owner, "m@example.com")

    assert first.status_code == 201
    assert second.status_code == 409


def test_free_plan_user_limit_returns_403(client):
    tenant_id, owner = create_tenant_user(client, "owner@example.com", "A社")
    # free は 5 人まで。owner を含めて 5 人になるまで追加する
    for i in range(4):
        new_user(client, f"u{i}@example.com")
        assert add(client, tenant_id, owner, f"u{i}@example.com").status_code == 201
    new_user(client, "extra@example.com")

    res = add(client, tenant_id, owner, "extra@example.com")

    assert res.status_code == 403


def test_pro_plan_has_no_user_limit(client, db):
    tenant_id, owner = create_tenant_user(client, "owner@example.com", "A社")
    pro_id = db.execute(select(Plan.id).where(Plan.name == "pro")).scalar_one()
    db.execute(
        update(Tenant).where(Tenant.id == to_uuid(tenant_id)).values(plan_id=pro_id)
    )
    db.commit()
    for i in range(6):
        new_user(client, f"u{i}@example.com")
        assert add(client, tenant_id, owner, f"u{i}@example.com").status_code == 201


def test_removed_member_can_be_added_again_with_new_role(client):
    t = setup_team(client)
    assert remove(client, t["tenant_id"], t["owner"], t["member_id"]).status_code == 204

    res = add(client, t["tenant_id"], t["owner"], "m@example.com", "admin")

    assert res.status_code == 201
    assert res.json()["role"] == "admin"


def test_add_writes_audit_log(client):
    tenant_id, owner = create_tenant_user(client, "owner@example.com", "A社")
    uid, _ = new_user(client, "m@example.com")
    add(client, tenant_id, owner, "m@example.com")

    items = client.get(
        f"/tenants/{tenant_id}/audit-logs", headers=auth(owner)
    ).json()["items"]

    logs = [i for i in items if i["action"] == "member.add"]
    assert len(logs) == 1
    assert logs[0]["target_id"] == uid
    assert logs[0]["before"] is None
    assert "email" not in logs[0]["after"]


# ---------- ロール変更 ----------

def test_owner_can_change_role(client):
    t = setup_team(client)

    res = change_role(client, t["tenant_id"], t["owner"], t["member_id"], "admin")

    assert res.status_code == 200
    assert res.json()["role"] == "admin"


def test_admin_cannot_change_role(client):
    t = setup_team(client)

    res = change_role(client, t["tenant_id"], t["admin"], t["member_id"], "admin")

    assert res.status_code == 403


def test_change_role_unknown_user_returns_404(client):
    import uuid
    tenant_id, owner = create_tenant_user(client, "owner@example.com", "A社")

    res = change_role(client, tenant_id, owner, uuid.uuid4(), "admin")

    assert res.status_code == 404


def test_cannot_demote_last_owner(client):
    tenant_id, owner = create_tenant_user(client, "owner@example.com", "A社")
    owner_id = get_user_id(client, owner)

    res = change_role(client, tenant_id, owner, owner_id, "admin")

    assert res.status_code == 409


def test_can_demote_owner_when_another_owner_exists(client):
    tenant_id, owner = create_tenant_user(client, "owner@example.com", "A社")
    owner_id = get_user_id(client, owner)
    new_user(client, "o2@example.com")
    assert add(client, tenant_id, owner, "o2@example.com", "owner").status_code == 201

    res = change_role(client, tenant_id, owner, owner_id, "admin")

    assert res.status_code == 200


def test_role_change_writes_audit_log(client):
    t = setup_team(client)
    change_role(client, t["tenant_id"], t["owner"], t["member_id"], "admin")

    items = client.get(
        f"/tenants/{t['tenant_id']}/audit-logs", headers=auth(t["owner"])
    ).json()["items"]

    logs = [i for i in items if i["action"] == "member.role_change"]
    assert len(logs) == 1
    assert logs[0]["before"]["role"] == "member"
    assert logs[0]["after"]["role"] == "admin"


# ---------- 削除 ----------

def test_admin_can_remove_member(client):
    t = setup_team(client)

    res = remove(client, t["tenant_id"], t["admin"], t["member_id"])

    assert res.status_code == 204
    listed = client.get(
        f"/tenants/{t['tenant_id']}/members", headers=auth(t["owner"])
    ).json()
    assert t["member_id"] not in [m["user_id"] for m in listed]


def test_removed_member_loses_access(client):
    t = setup_team(client)
    remove(client, t["tenant_id"], t["owner"], t["member_id"])

    res = client.get(
        f"/tenants/{t['tenant_id']}/members", headers=auth(t["member"])
    )

    assert res.status_code == 403


def test_admin_cannot_remove_admin_or_owner(client):
    t = setup_team(client)

    ng_owner = remove(client, t["tenant_id"], t["admin"], t["owner_id"])
    ng_admin = remove(client, t["tenant_id"], t["admin"], t["admin_id"])

    assert ng_owner.status_code == 403
    assert ng_admin.status_code == 403


def test_member_cannot_remove(client):
    t = setup_team(client)

    res = remove(client, t["tenant_id"], t["member"], t["admin_id"])

    assert res.status_code == 403


def test_owner_can_remove_admin(client):
    t = setup_team(client)

    res = remove(client, t["tenant_id"], t["owner"], t["admin_id"])

    assert res.status_code == 204


def test_cannot_remove_last_owner(client):
    t = setup_team(client)

    res = remove(client, t["tenant_id"], t["owner"], t["owner_id"])

    assert res.status_code == 409


def test_can_remove_owner_when_another_owner_exists(client):
    t = setup_team(client)
    assert (
        change_role(client, t["tenant_id"], t["owner"], t["admin_id"], "owner").status_code
        == 200
    )

    res = remove(client, t["tenant_id"], t["owner"], t["owner_id"])

    assert res.status_code == 204


def test_remove_unknown_or_other_tenant_user_returns_404(client):
    import uuid
    t = setup_team(client)
    other_id, _ = new_user(client, "z@example.com")  # このテナントの所属ではない

    unknown = remove(client, t["tenant_id"], t["owner"], uuid.uuid4())
    not_member = remove(client, t["tenant_id"], t["owner"], other_id)

    assert unknown.status_code == 404
    assert not_member.status_code == 404


def test_remove_writes_audit_log(client):
    t = setup_team(client)
    remove(client, t["tenant_id"], t["owner"], t["member_id"])

    items = client.get(
        f"/tenants/{t['tenant_id']}/audit-logs", headers=auth(t["owner"])
    ).json()["items"]

    logs = [i for i in items if i["action"] == "member.remove"]
    assert len(logs) == 1
    assert logs[0]["target_id"] == t["member_id"]
    assert logs[0]["after"] is None
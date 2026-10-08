from datetime import datetime, timedelta, timezone

from tests.helpers import add_member, auth_headers, create_tenant_user, make_records


def logs_url(tenant_id) -> str:
    return f"/tenants/{tenant_id}/audit-logs"


def update_record(client, tenant_id, token, record_id, hours=1):
    new_out = datetime.now(timezone.utc) + timedelta(hours=hours)
    return client.patch(
        f"/tenants/{tenant_id}/attendance/{record_id}",
        json={"clock_out_time": new_out.isoformat()},
        headers=auth_headers(token),
    )


def test_owner_can_view_audit_logs(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    record_id = make_records(client, tenant_id, token, 1)[0]
    assert update_record(client, tenant_id, token, record_id).status_code == 200

    res = client.get(logs_url(tenant_id), headers=auth_headers(token))

    assert res.status_code == 200
    items = res.json()["items"]
    updates = [i for i in items if i["action"] == "attendance.update"]
    assert len(updates) == 1
    assert updates[0]["target_id"] == record_id
    assert updates[0]["before"] is not None
    assert updates[0]["after"] is not None
    assert "tenant_id" not in updates[0]


def test_admin_can_view_audit_logs(client, db):
    tenant_id, _ = create_tenant_user(client, "owner@example.com", "A社")
    _, admin_token = add_member(client, db, tenant_id, "ad@example.com", "admin")

    res = client.get(logs_url(tenant_id), headers=auth_headers(admin_token))

    assert res.status_code == 200


def test_member_cannot_view_audit_logs(client, db):
    tenant_id, _ = create_tenant_user(client, "owner@example.com", "A社")
    _, member_token = add_member(client, db, tenant_id, "m@example.com")

    res = client.get(logs_url(tenant_id), headers=auth_headers(member_token))

    assert res.status_code == 403


def test_cannot_view_other_tenant_audit_logs(client):
    _, token_a = create_tenant_user(client, "a@example.com", "A社")
    tenant_b, _ = create_tenant_user(client, "b@example.com", "B社")

    res = client.get(logs_url(tenant_b), headers=auth_headers(token_a))

    assert res.status_code == 403


def test_audit_logs_contain_only_own_tenant(client):
    tenant_a, token_a = create_tenant_user(client, "a@example.com", "A社")
    tenant_b, token_b = create_tenant_user(client, "b@example.com", "B社")
    record_b = make_records(client, tenant_b, token_b, 1)[0]
    assert update_record(client, tenant_b, token_b, record_b).status_code == 200

    res_a = client.get(logs_url(tenant_a), headers=auth_headers(token_a))
    res_b = client.get(logs_url(tenant_b), headers=auth_headers(token_b))

    assert all(i["target_id"] != record_b for i in res_a.json()["items"])
    assert any(i["target_id"] == record_b for i in res_b.json()["items"])


def test_audit_logs_newest_first(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    record_id = make_records(client, tenant_id, token, 1)[0]
    update_record(client, tenant_id, token, record_id, hours=1)
    update_record(client, tenant_id, token, record_id, hours=2)

    items = client.get(logs_url(tenant_id), headers=auth_headers(token)).json()["items"]

    times = [datetime.fromisoformat(i["created_at"]) for i in items]
    assert times == sorted(times, reverse=True)


def test_audit_logs_pagination_has_no_overlap(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    record_id = make_records(client, tenant_id, token, 1)[0]
    update_record(client, tenant_id, token, record_id, hours=1)
    update_record(client, tenant_id, token, record_id, hours=2)
    # ログは signup の tenant.create と合わせて 3 件以上ある

    all_items = client.get(
        logs_url(tenant_id), params={"limit": 100}, headers=auth_headers(token)
    ).json()["items"]
    total = len(all_items)
    assert total >= 3

    first = client.get(
        logs_url(tenant_id), params={"limit": 2}, headers=auth_headers(token)
    ).json()
    second = client.get(
        logs_url(tenant_id),
        params={"limit": 2, "cursor": first["next_cursor"]},
        headers=auth_headers(token),
    ).json()

    first_ids = [i["id"] for i in first["items"]]
    second_ids = [i["id"] for i in second["items"]]
    assert len(first_ids) == 2
    assert first["next_cursor"] is not None
    assert set(first_ids).isdisjoint(second_ids)
    assert first_ids + second_ids == [i["id"] for i in all_items][: len(first_ids + second_ids)]


def test_audit_logs_invalid_cursor_returns_422(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")

    res = client.get(
        logs_url(tenant_id), params={"cursor": "でたらめ"}, headers=auth_headers(token)
    )

    assert res.status_code == 422
        
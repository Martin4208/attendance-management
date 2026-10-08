from tests.helpers import (
    add_member,
    auth,
    create_tenant_user,
    iso,
    make_records,
    patch_url,
)
import base64
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import AuditLog


def test_member_can_clock_in(client):
    tenant_id, token = create_tenant_user(client, "test@email.com", "string")
    
    res = client.post(f"/tenants/{tenant_id}/attendance/clock-in", headers=auth(token))
    
    assert res.status_code == 201
    body = res.json()
    assert body["id"] is not None
    assert body["clock_in_time"] is not None
    assert body["clock_out_time"] is None
    assert "tenant_id" not in body
    assert "user_id" not in body


def test_double_clock_in_returns_409(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    url = f"/tenants/{tenant_id}/attendance/clock-in"

    first = client.post(url, headers=auth(token))
    second = client.post(url, headers=auth(token))

    assert first.status_code == 201
    assert second.status_code == 409


def test_cannot_clock_in_to_other_tenant(client):
    _, token_a = create_tenant_user(client, "a@example.com", "A社")
    tenant_b, _ = create_tenant_user(client, "b@example.com", "B社")

    res = client.post(f"/tenants/{tenant_b}/attendance/clock-in", headers=auth(token_a))

    assert res.status_code == 403
    
    
def test_member_can_clock_out(client):
    tenant_id, token = create_tenant_user(client, "test@email.com", "string")
    url1 = f"/tenants/{tenant_id}/attendance/clock-in"
    url2 = f"/tenants/{tenant_id}/attendance/clock-out"
    
    first = client.post(url1, headers=auth(token))
    second = client.post(url2, headers=auth(token))
    
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["clock_out_time"] is not None


def test_clock_out_before_clock_in_returns_409(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    url = f"/tenants/{tenant_id}/attendance/clock-out"

    res = client.post(url, headers=auth(token))

    assert res.status_code == 409


def test_double_clock_out_returns_409(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    url1 = f"/tenants/{tenant_id}/attendance/clock-in"
    url2 = f"/tenants/{tenant_id}/attendance/clock-out"

    first = client.post(url1, headers=auth(token))
    second = client.post(url2, headers=auth(token))
    third = client.post(url2, headers=auth(token))

    assert first.status_code == 201
    assert second.status_code == 200
    assert third.status_code == 409
    
    
    
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


def test_list_returns_newest_first(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    ids = make_records(client, tenant_id, token, 3)

    res = client.get(f"/tenants/{tenant_id}/attendance", headers=auth(token))

    assert res.status_code == 200
    body = res.json()
    assert [item["id"] for item in body["items"]] == list(reversed(ids))
    assert body["next_cursor"] is None


def test_list_limit_returns_next_cursor(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    ids = make_records(client, tenant_id, token, 3)

    res = client.get(
        f"/tenants/{tenant_id}/attendance", params={"limit": 2}, headers=auth(token)
    )

    assert res.status_code == 200
    body = res.json()
    assert [item["id"] for item in body["items"]] == list(reversed(ids))[:2]
    assert body["next_cursor"] is not None


def test_list_next_page_has_no_overlap(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    ids = make_records(client, tenant_id, token, 3)
    url = f"/tenants/{tenant_id}/attendance"

    first = client.get(url, params={"limit": 2}, headers=auth(token)).json()
    second = client.get(
        url,
        params={"limit": 2, "cursor": first["next_cursor"]},
        headers=auth(token),
    ).json()

    first_ids = [item["id"] for item in first["items"]]
    second_ids = [item["id"] for item in second["items"]]
    assert second_ids == list(reversed(ids))[2:]
    assert set(first_ids).isdisjoint(second_ids)
    assert second["next_cursor"] is None


def test_list_exact_limit_has_no_next_cursor(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    make_records(client, tenant_id, token, 3)

    res = client.get(
        f"/tenants/{tenant_id}/attendance", params={"limit": 3}, headers=auth(token)
    )

    body = res.json()
    assert len(body["items"]) == 3
    assert body["next_cursor"] is None


def test_list_contains_only_own_records(client):
    tenant_a, token_a = create_tenant_user(client, "a@example.com", "A社")
    tenant_b, token_b = create_tenant_user(client, "b@example.com", "B社")
    ids_a = make_records(client, tenant_a, token_a, 2)
    ids_b = make_records(client, tenant_b, token_b, 1)

    res = client.get(f"/tenants/{tenant_a}/attendance", headers=auth(token_a))

    returned = [item["id"] for item in res.json()["items"]]
    assert sorted(returned) == sorted(ids_a)
    assert ids_b[0] not in returned


def test_list_other_tenant_returns_403(client):
    _, token_a = create_tenant_user(client, "a@example.com", "A社")
    tenant_b, _ = create_tenant_user(client, "b@example.com", "B社")

    res = client.get(f"/tenants/{tenant_b}/attendance", headers=auth(token_a))

    assert res.status_code == 403


def test_list_invalid_cursor_returns_422(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")

    res = client.get(
        f"/tenants/{tenant_id}/attendance",
        params={"cursor": "でたらめ"},
        headers=auth(token),
    )

    assert res.status_code == 422


def test_list_cursor_with_missing_keys_returns_422(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    broken = base64.urlsafe_b64encode(b'{"x": 1}').decode()

    res = client.get(
        f"/tenants/{tenant_id}/attendance",
        params={"cursor": broken},
        headers=auth(token),
    )

    assert res.status_code == 422


def test_list_limit_out_of_range_returns_422(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")

    too_small = client.get(
        f"/tenants/{tenant_id}/attendance", params={"limit": 0}, headers=auth(token)
    )
    too_big = client.get(
        f"/tenants/{tenant_id}/attendance", params={"limit": 101}, headers=auth(token)
    )

    assert too_small.status_code == 422
    assert too_big.status_code == 422
    
    
    
def test_owner_can_update_clock_out(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    record_id = make_records(client, tenant_id, token, 1)[0]
    new_out = datetime.now(timezone.utc) + timedelta(hours=1)

    res = client.patch(
        patch_url(tenant_id, record_id),
        json={"clock_out_time": iso(new_out)},
        headers=auth(token),
    )

    assert res.status_code == 200
    assert res.json()["id"] == record_id
    # 文字列ではなく日時に直して比べる（+00:00 と Z などの書式差を避ける）
    assert datetime.fromisoformat(res.json()["clock_out_time"]) == new_out


def test_update_clock_in_after_clock_out_returns_422(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    record_id = make_records(client, tenant_id, token, 1)[0]
    # 出勤だけを未来にずらすと、今の退勤より後になる（今の行の値と比べる検証）
    new_in = datetime.now(timezone.utc) + timedelta(hours=1)

    res = client.patch(
        patch_url(tenant_id, record_id),
        json={"clock_in_time": iso(new_in)},
        headers=auth(token),
    )

    assert res.status_code == 422


def test_update_clock_out_before_clock_in_returns_422(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    record_id = make_records(client, tenant_id, token, 1)[0]
    new_out = datetime.now(timezone.utc) - timedelta(hours=1)

    res = client.patch(
        patch_url(tenant_id, record_id),
        json={"clock_out_time": iso(new_out)},
        headers=auth(token),
    )

    assert res.status_code == 422


def test_update_clock_out_equal_to_clock_in_returns_422(client):
    # 境界: DB の CHECK は「>」なので、等しい場合も 422 にする（<= の確認）
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    record_id = make_records(client, tenant_id, token, 1)[0]
    listed = client.get(f"/tenants/{tenant_id}/attendance", headers=auth(token))
    clock_in = listed.json()["items"][0]["clock_in_time"]

    res = client.patch(
        patch_url(tenant_id, record_id),
        json={"clock_out_time": clock_in},
        headers=auth(token),
    )

    assert res.status_code == 422


def test_update_with_empty_body_returns_422(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    record_id = make_records(client, tenant_id, token, 1)[0]

    res = client.patch(
        patch_url(tenant_id, record_id), json={}, headers=auth(token)
    )

    assert res.status_code == 422


def test_update_with_naive_datetime_returns_422(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    record_id = make_records(client, tenant_id, token, 1)[0]

    res = client.patch(
        patch_url(tenant_id, record_id),
        json={"clock_out_time": "2099-01-01T18:00:00"},  # タイムゾーン無し
        headers=auth(token),
    )

    assert res.status_code == 422


def test_update_nonexistent_record_returns_404(client):
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")

    res = client.patch(
        patch_url(tenant_id, uuid.uuid4()),
        json={"clock_out_time": iso(datetime.now(timezone.utc))},
        headers=auth(token),
    )

    assert res.status_code == 404


def test_cannot_update_other_tenant_record(client):
    tenant_a, token_a = create_tenant_user(client, "a@example.com", "A社")
    tenant_b, token_b = create_tenant_user(client, "b@example.com", "B社")
    record_b = make_records(client, tenant_b, token_b, 1)[0]
    new_out = datetime.now(timezone.utc) + timedelta(hours=1)

    # A社のURL・A社のトークンで、B社の勤怠の id を指定する
    res = client.patch(
        patch_url(tenant_a, record_b),
        json={"clock_out_time": iso(new_out)},
        headers=auth(token_a),
    )

    assert res.status_code == 404

    # B社の勤怠が変わっていないことも確認する
    listed = client.get(f"/tenants/{tenant_b}/attendance", headers=auth(token_b))
    unchanged = listed.json()["items"][0]["clock_out_time"]
    assert datetime.fromisoformat(unchanged) != new_out


def test_update_writes_audit_log(client, db):  # ← db は仮定した fixture 名
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    record_id = make_records(client, tenant_id, token, 1)[0]
    new_out = datetime.now(timezone.utc) + timedelta(hours=1)

    res = client.patch(
        patch_url(tenant_id, record_id),
        json={"clock_out_time": iso(new_out)},
        headers=auth(token),
    )

    assert res.status_code == 200
    logs = db.execute(
        select(AuditLog).where(AuditLog.action == "attendance.update")
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].target_type == "attendance_record"
    assert logs[0].target_id == record_id
    assert logs[0].before["clock_out_time"] != logs[0].after["clock_out_time"]
    assert "email" not in logs[0].before and "email" not in logs[0].after


def test_failed_update_writes_no_audit_log(client, db):  # ← db は仮定
    tenant_id, token = create_tenant_user(client, "a@example.com", "A社")
    record_id = make_records(client, tenant_id, token, 1)[0]

    res = client.patch(
        patch_url(tenant_id, record_id),
        json={"clock_out_time": iso(datetime.now(timezone.utc) - timedelta(hours=1))},
        headers=auth(token),
    )

    assert res.status_code == 422
    count = db.execute(
        select(AuditLog).where(AuditLog.action == "attendance.update")
    ).scalars().all()
    assert count == []


def test_member_cannot_update_record(client, db):
    tenant_id, owner_token = create_tenant_user(client, "owner@example.com", "A社")
    record_id = make_records(client, tenant_id, owner_token, 1)[0]
    _, member_token = add_member(client, db, tenant_id, "m@example.com", "member")

    res = client.patch(
        patch_url(tenant_id, record_id),
        json={"clock_out_time": iso(datetime.now(timezone.utc) + timedelta(hours=1))},
        headers=auth(member_token),
    )

    assert res.status_code == 403


def test_admin_cannot_update_record(client, db):
    tenant_id, owner_token = create_tenant_user(client, "owner@example.com", "A社")
    record_id = make_records(client, tenant_id, owner_token, 1)[0]
    _, admin_token = add_member(client, db, tenant_id, "ad@example.com", "admin")

    res = client.patch(
        patch_url(tenant_id, record_id),
        json={"clock_out_time": iso(datetime.now(timezone.utc) + timedelta(hours=1))},
        headers=auth(admin_token),
    )

    assert res.status_code == 403
    
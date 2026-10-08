import uuid
from datetime import datetime, timezone

from sqlalchemy import update

from app.models import Membership
from tests.helpers import (
    add_member,
    auth_headers,
    create_tenant_user,
    get_user_id,
    make_records,
    to_uuid,
)


def url(tenant_id, user_id) -> str:
    return f"/tenants/{tenant_id}/members/{user_id}/attendance"


def test_owner_can_view_member_attendance(client, db):
    tenant_id, owner_token = create_tenant_user(client, "owner@example.com", "A社")
    member_id, member_token = add_member(client, db, tenant_id, "m@example.com")
    ids = make_records(client, tenant_id, member_token, 2)

    res = client.get(url(tenant_id, member_id), headers=auth_headers(owner_token))

    assert res.status_code == 200
    assert [i["id"] for i in res.json()["items"]] == list(reversed(ids))


def test_view_contains_only_target_user_records(client, db):
    tenant_id, owner_token = create_tenant_user(client, "owner@example.com", "A社")
    owner_ids = make_records(client, tenant_id, owner_token, 1)
    member_id, member_token = add_member(client, db, tenant_id, "m@example.com")
    member_ids = make_records(client, tenant_id, member_token, 2)

    res = client.get(url(tenant_id, member_id), headers=auth_headers(owner_token))

    returned = [i["id"] for i in res.json()["items"]]
    assert sorted(returned) == sorted(member_ids)
    assert owner_ids[0] not in returned


def test_member_cannot_view_others_attendance(client, db):
    tenant_id, owner_token = create_tenant_user(client, "owner@example.com", "A社")
    owner_id = get_user_id(client, owner_token)
    _, member_token = add_member(client, db, tenant_id, "m@example.com")

    res = client.get(url(tenant_id, owner_id), headers=auth_headers(member_token))

    assert res.status_code == 403


def test_admin_cannot_view_others_attendance(client, db):
    tenant_id, owner_token = create_tenant_user(client, "owner@example.com", "A社")
    member_id, _ = add_member(client, db, tenant_id, "m@example.com")
    _, admin_token = add_member(client, db, tenant_id, "ad@example.com", "admin")

    res = client.get(url(tenant_id, member_id), headers=auth_headers(admin_token))

    assert res.status_code == 403


def test_unknown_user_returns_404(client):
    tenant_id, owner_token = create_tenant_user(client, "owner@example.com", "A社")

    res = client.get(url(tenant_id, uuid.uuid4()), headers=auth_headers(owner_token))

    assert res.status_code == 404


def test_user_of_other_tenant_returns_404(client):
    tenant_a, token_a = create_tenant_user(client, "a@example.com", "A社")
    tenant_b, token_b = create_tenant_user(client, "b@example.com", "B社")
    user_b = get_user_id(client, token_b)
    make_records(client, tenant_b, token_b, 1)

    res = client.get(url(tenant_a, user_b), headers=auth_headers(token_a))

    assert res.status_code == 404


def test_removed_member_returns_404(client, db):
    tenant_id, owner_token = create_tenant_user(client, "owner@example.com", "A社")
    member_id, member_token = add_member(client, db, tenant_id, "m@example.com")
    make_records(client, tenant_id, member_token, 1)
    db.execute(
        update(Membership)
        .where(
            Membership.tenant_id == to_uuid(tenant_id),
            Membership.user_id == to_uuid(member_id),
        )
        .values(deleted_at=datetime.now(timezone.utc))
    )
    db.commit()

    res = client.get(url(tenant_id, member_id), headers=auth_headers(owner_token))

    assert res.status_code == 404


def test_member_attendance_pagination(client, db):
    tenant_id, owner_token = create_tenant_user(client, "owner@example.com", "A社")
    member_id, member_token = add_member(client, db, tenant_id, "m@example.com")
    ids = make_records(client, tenant_id, member_token, 3)

    first = client.get(
        url(tenant_id, member_id), params={"limit": 2}, headers=auth_headers(owner_token)
    ).json()
    second = client.get(
        url(tenant_id, member_id),
        params={"limit": 2, "cursor": first["next_cursor"]},
        headers=auth_headers(owner_token),
    ).json()

    assert [i["id"] for i in first["items"]] == list(reversed(ids))[:2]
    assert [i["id"] for i in second["items"]] == list(reversed(ids))[2:]
    assert second["next_cursor"] is None


def test_invalid_cursor_returns_422(client, db):
    tenant_id, owner_token = create_tenant_user(client, "owner@example.com", "A社")
    member_id, _ = add_member(client, db, tenant_id, "m@example.com")

    res = client.get(
        url(tenant_id, member_id),
        params={"cursor": "でたらめ"},
        headers=auth_headers(owner_token),
    )

    assert res.status_code == 422
    
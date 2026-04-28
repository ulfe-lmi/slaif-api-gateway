import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.schemas.keys import RotatedGatewayKeyResult

from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions


def _rotation_result(
    *,
    old_key_id: uuid.UUID,
    new_key_id: uuid.UUID | None = None,
    plaintext_key: str = "sk-slaif-newpublic.once-only-replacement",
) -> RotatedGatewayKeyResult:
    now = datetime.now(UTC)
    return RotatedGatewayKeyResult(
        old_gateway_key_id=old_key_id,
        new_gateway_key_id=new_key_id or uuid.uuid4(),
        new_plaintext_key=plaintext_key,
        new_public_key_id="newpublic",
        one_time_secret_id=uuid.uuid4(),
        old_status="revoked",
        new_status="active",
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        owner_id=uuid.uuid4(),
    )


def test_unauthenticated_rotate_redirects_to_login() -> None:
    gateway_key_id = uuid.uuid4()
    client = TestClient(_app())

    response = client.post(f"/admin/keys/{gateway_key_id}/rotate", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_rotate_without_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def rotate_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.rotate_gateway_key",
        rotate_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(f"/admin/keys/{uuid.uuid4()}/rotate")

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_rotate_with_invalid_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def rotate_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.rotate_gateway_key",
        rotate_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{uuid.uuid4()}/rotate",
        data={"csrf_token": "wrong", "confirm_rotate": "true", "reason": "rotate"},
    )

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_rotate_requires_confirmation_before_service_call(monkeypatch) -> None:
    called = False
    gateway_key_id = uuid.uuid4()

    async def rotate_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.rotate_gateway_key",
        rotate_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/rotate",
        data={"csrf_token": "dashboard-csrf", "reason": "replace exposed key"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=rotation_confirmation_required"
    assert called is False


def test_rotate_requires_reason_before_service_call(monkeypatch) -> None:
    called = False
    gateway_key_id = uuid.uuid4()

    async def rotate_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.rotate_gateway_key",
        rotate_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/rotate",
        data={"csrf_token": "dashboard-csrf", "confirm_rotate": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=rotation_reason_required"
    assert called is False


def test_rotate_calls_key_service_and_renders_one_time_plaintext(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()
    replacement_key = "sk-slaif-newpublic.once-only-replacement"

    async def rotate_gateway_key(self, payload):
        seen["payload"] = payload
        return _rotation_result(old_key_id=gateway_key_id, plaintext_key=replacement_key)

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.rotate_gateway_key",
        rotate_gateway_key,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/rotate",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_rotate": "true",
            "reason": "replace exposed key",
        },
    )

    assert response.status_code == 200
    assert response.text.count(replacement_key) == 1
    assert "old-plaintext-key-must-not-render" not in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "provider-secret" not in response.text
    assert "session-token" not in response.text
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
    assert response.headers["Pragma"] == "no-cache"
    assert seen["payload"].gateway_key_id == gateway_key_id
    assert seen["payload"].actor_admin_id == admin_user.id
    assert seen["payload"].reason == "replace exposed key"
    assert seen["payload"].revoke_old_key is True


def test_rotate_keep_old_active_passes_revoke_false(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()

    async def rotate_gateway_key(self, payload):
        seen["payload"] = payload
        return _rotation_result(
            old_key_id=gateway_key_id,
            plaintext_key="sk-slaif-newpublic.keep-old-replacement",
        )

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.rotate_gateway_key",
        rotate_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/rotate",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_rotate": "true",
            "keep_old_active": "true",
            "reason": "temporary overlap",
        },
    )

    assert response.status_code == 200
    assert seen["payload"].revoke_old_key is False


def test_no_get_rotate_mutation_route_exists(monkeypatch) -> None:
    gateway_key_id = uuid.uuid4()
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get(f"/admin/keys/{gateway_key_id}/rotate")

    assert response.status_code == 405

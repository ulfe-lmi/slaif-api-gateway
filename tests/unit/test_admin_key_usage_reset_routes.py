import uuid

from fastapi.testclient import TestClient

from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions


def test_unauthenticated_usage_reset_redirects_to_login() -> None:
    gateway_key_id = uuid.uuid4()
    client = TestClient(_app())

    response = client.post(f"/admin/keys/{gateway_key_id}/reset-usage", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_usage_reset_without_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def reset_gateway_key_usage(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.reset_gateway_key_usage",
        reset_gateway_key_usage,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(f"/admin/keys/{uuid.uuid4()}/reset-usage")

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_usage_reset_with_invalid_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def reset_gateway_key_usage(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.reset_gateway_key_usage",
        reset_gateway_key_usage,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{uuid.uuid4()}/reset-usage",
        data={"csrf_token": "wrong", "confirm_reset_usage": "true", "reason": "repair"},
    )

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_usage_reset_requires_reason_before_service_call(monkeypatch) -> None:
    called = False
    gateway_key_id = uuid.uuid4()

    async def reset_gateway_key_usage(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.reset_gateway_key_usage",
        reset_gateway_key_usage,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/reset-usage",
        data={"csrf_token": "dashboard-csrf", "confirm_reset_usage": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=usage_reset_reason_required"
    assert called is False


def test_usage_reset_requires_used_counter_confirmation_before_service_call(monkeypatch) -> None:
    called = False
    gateway_key_id = uuid.uuid4()

    async def reset_gateway_key_usage(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.reset_gateway_key_usage",
        reset_gateway_key_usage,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/reset-usage",
        data={"csrf_token": "dashboard-csrf", "reason": "repair used counters"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/keys/{gateway_key_id}?message=usage_reset_confirmation_required"
    )
    assert called is False


def test_usage_reset_reserved_requires_repair_confirmation_before_service_call(monkeypatch) -> None:
    called = False
    gateway_key_id = uuid.uuid4()

    async def reset_gateway_key_usage(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.reset_gateway_key_usage",
        reset_gateway_key_usage,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/reset-usage",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_reset_usage": "true",
            "reset_reserved": "true",
            "reason": "repair stale reservation",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/keys/{gateway_key_id}?message=reserved_reset_confirmation_required"
    )
    assert called is False


def test_usage_reset_calls_key_service_for_used_counters(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()

    async def reset_gateway_key_usage(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.reset_gateway_key_usage",
        reset_gateway_key_usage,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/reset-usage",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_reset_usage": "true",
            "reason": "clear workshop counters",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=key_usage_reset"
    assert seen["payload"].gateway_key_id == gateway_key_id
    assert seen["payload"].actor_admin_id == admin_user.id
    assert seen["payload"].reason == "clear workshop counters"
    assert seen["payload"].reset_used_counters is True
    assert seen["payload"].reset_reserved_counters is False


def test_usage_reset_calls_key_service_for_reserved_repair(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()

    async def reset_gateway_key_usage(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.reset_gateway_key_usage",
        reset_gateway_key_usage,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/reset-usage",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_reset_usage": "true",
            "reset_reserved": "true",
            "confirm_reset_reserved": "true",
            "reason": "repair stale reservation",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=key_usage_reset"
    assert seen["payload"].gateway_key_id == gateway_key_id
    assert seen["payload"].actor_admin_id == admin_user.id
    assert seen["payload"].reason == "repair stale reservation"
    assert seen["payload"].reset_used_counters is True
    assert seen["payload"].reset_reserved_counters is True


def test_no_get_usage_reset_mutation_route_exists(monkeypatch) -> None:
    gateway_key_id = uuid.uuid4()
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.get(f"/admin/keys/{gateway_key_id}/reset-usage")

    assert response.status_code == 405

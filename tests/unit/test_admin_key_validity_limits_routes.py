import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions


def _gateway_key(**overrides):
    values = {
        "id": uuid.uuid4(),
        "valid_from": datetime.now(UTC) - timedelta(days=1),
        "valid_until": datetime.now(UTC) + timedelta(days=30),
        "cost_limit_eur": Decimal("12.000000000"),
        "token_limit_total": 1200,
        "request_limit_total": 120,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _patch_gateway_key_lookup(monkeypatch, gateway_key) -> None:
    async def get_gateway_key_by_id(self, gateway_key_id):
        return gateway_key

    monkeypatch.setattr(
        "slaif_gateway.db.repositories.keys.GatewayKeysRepository.get_gateway_key_by_id",
        get_gateway_key_by_id,
    )


def test_unauthenticated_validity_update_redirects_to_login() -> None:
    gateway_key_id = uuid.uuid4()
    client = TestClient(_app())

    response = client.post(f"/admin/keys/{gateway_key_id}/validity", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_limits_update_without_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def update_gateway_key_limits(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_limits",
        update_gateway_key_limits,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(f"/admin/keys/{uuid.uuid4()}/limits")

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_validity_update_with_invalid_csrf_fails(monkeypatch) -> None:
    called = False

    async def update_gateway_key_validity(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_validity",
        update_gateway_key_validity,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{uuid.uuid4()}/validity",
        data={"csrf_token": "wrong", "reason": "adjust window"},
    )

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_validity_update_calls_key_service_with_actor_reason_and_datetimes(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()
    current_key = _gateway_key(id=gateway_key_id)
    _patch_gateway_key_lookup(monkeypatch, current_key)

    async def update_gateway_key_validity(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_validity",
        update_gateway_key_validity,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/validity",
        data={
            "csrf_token": "dashboard-csrf",
            "valid_from": "2026-01-01T10:00",
            "valid_until": "2026-02-01T10:00:00Z",
            "reason": "extend workshop",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=key_validity_updated"
    assert seen["payload"].gateway_key_id == gateway_key_id
    assert seen["payload"].actor_admin_id == admin_user.id
    assert seen["payload"].reason == "extend workshop"
    assert seen["payload"].valid_from == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    assert seen["payload"].valid_until == datetime(2026, 2, 1, 10, 0, tzinfo=UTC)


def test_validity_update_preserves_current_valid_until_when_blank(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()
    current_until = datetime(2026, 3, 1, tzinfo=UTC)
    _patch_gateway_key_lookup(monkeypatch, _gateway_key(id=gateway_key_id, valid_until=current_until))

    async def update_gateway_key_validity(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_validity",
        update_gateway_key_validity,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/validity",
        data={
            "csrf_token": "dashboard-csrf",
            "valid_from": "2026-01-01T10:00:00+00:00",
            "valid_until": "",
            "reason": "move start",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert seen["payload"].valid_until == current_until


def test_invalid_datetime_fails_before_service_call(monkeypatch) -> None:
    called = False
    gateway_key_id = uuid.uuid4()

    async def update_gateway_key_validity(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_validity",
        update_gateway_key_validity,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/validity",
        data={"csrf_token": "dashboard-csrf", "valid_until": "not-a-date", "reason": "bad"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=invalid_gateway_key_validity"
    assert called is False


def test_validity_update_missing_key_returns_safe_404(monkeypatch) -> None:
    _patch_gateway_key_lookup(monkeypatch, None)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{uuid.uuid4()}/validity",
        data={
            "csrf_token": "dashboard-csrf",
            "valid_until": "2026-02-01T10:00:00+00:00",
            "reason": "adjust window",
        },
    )

    assert response.status_code == 404
    assert "Gateway key not found." in response.text


def test_limits_update_calls_key_service_with_decimal_ints_and_preserved_values(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()
    _patch_gateway_key_lookup(monkeypatch, _gateway_key(id=gateway_key_id, request_limit_total=120))

    async def update_gateway_key_limits(self, payload):
        seen["payload"] = payload

    async def update_gateway_key_rate_limits(self, payload):
        raise AssertionError("Redis rate-limit service method must not be called")

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_limits",
        update_gateway_key_limits,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_rate_limits",
        update_gateway_key_rate_limits,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/limits",
        data={
            "csrf_token": "dashboard-csrf",
            "cost_limit_eur": "20.500000000",
            "token_limit": "2000",
            "request_limit": "",
            "reason": "raise quota",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{gateway_key_id}?message=key_limits_updated"
    assert seen["payload"].gateway_key_id == gateway_key_id
    assert seen["payload"].actor_admin_id == admin_user.id
    assert seen["payload"].reason == "raise quota"
    assert seen["payload"].cost_limit_eur == Decimal("20.500000000")
    assert seen["payload"].token_limit_total == 2000
    assert seen["payload"].request_limit_total == 120


def test_limits_update_clear_flags_work(monkeypatch) -> None:
    seen = {}
    gateway_key_id = uuid.uuid4()
    _patch_gateway_key_lookup(monkeypatch, _gateway_key(id=gateway_key_id))

    async def update_gateway_key_limits(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_limits",
        update_gateway_key_limits,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{gateway_key_id}/limits",
        data={
            "csrf_token": "dashboard-csrf",
            "clear_cost_limit": "true",
            "clear_token_limit": "true",
            "request_limit": "300",
            "reason": "clear classroom caps",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert seen["payload"].cost_limit_eur is None
    assert seen["payload"].token_limit_total is None
    assert seen["payload"].request_limit_total == 300


def test_limits_update_invalid_values_fail_before_service_call(monkeypatch) -> None:
    called = False

    async def update_gateway_key_limits(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_limits",
        update_gateway_key_limits,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)
    gateway_key_id = uuid.uuid4()

    for field, value in (
        ("cost_limit_eur", "0"),
        ("cost_limit_eur", "-1"),
        ("cost_limit_eur", "not-a-decimal"),
        ("token_limit", "0"),
        ("token_limit", "-1"),
        ("token_limit", "1.5"),
        ("request_limit", "0"),
        ("request_limit", "-1"),
        ("request_limit", "not-an-int"),
    ):
        response = client.post(
            f"/admin/keys/{gateway_key_id}/limits",
            data={"csrf_token": "dashboard-csrf", field: value, "reason": "bad limit"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == (
            f"/admin/keys/{gateway_key_id}?message=invalid_gateway_key_limits"
        )

    assert called is False

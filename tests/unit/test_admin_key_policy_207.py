"""207-a GUI key policy, rate administration, and effective inspection.

Unit coverage for G01 (provider tri-state + advanced version-1
configuration import/export), G02 (existing-key rate editor), and G03
(effective-policy inspection + explain model access), plus the create
form's advanced document mode.

These are source/fake-DB unit tests: the rate-editor composition law and
the tri-state parser are asserted as pure functions, and the routes are
exercised against the unit fake session with repository/service seams
monkeypatched. Persisted PostgreSQL behavior (provider preservation on
disabled providers, rate/usage isolation, configuration export round
trip, and the shared inspection projection) is covered by
``tests/integration/test_admin_key_policy_207_postgres.py``.
"""

import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.schemas.admin_keys import AdminKeyDetail, AdminKeyListRow
from slaif_gateway.schemas.keys import CreatedGatewayKey
from slaif_gateway.services.admin_session_service import AdminSessionContext
from slaif_gateway.services.admin_key_dashboard import AdminKeyNotFoundError
from slaif_gateway.services.key_errors import KeyManagementError
from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions

CANARY = "sk-slaif-canary-" + "0" * 40


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _admin_user() -> AdminUser:
    return AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="argon2-hash",
        role="admin",
        is_active=True,
    )


def _admin_session(admin_user: AdminUser) -> AdminSession:
    session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="sha256:session",
        csrf_token_hash="sha256:csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.admin_user = admin_user
    return session


def _login_with_render(monkeypatch, client: TestClient, key: AdminKeyDetail | None):
    """Login plus detail lookup so error re-renders can paint the page."""
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "dashboard-csrf"

    def verify_session_csrf_token(self, admin_session, csrf_token):
        return csrf_token == "dashboard-csrf"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )
    if key is not None:

        async def get_key_detail(self, gateway_key_id):
            return key

        monkeypatch.setattr(
            "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
            get_key_detail,
        )
    client.cookies.set("slaif_admin_session", "session-plaintext")
    return admin_user


def _detail(*, allowed_providers=None, **overrides) -> AdminKeyDetail:
    values = dict(
        id=uuid.uuid4(),
        public_key_id="public-detail-id",
        key_prefix="sk-slaif-",
        key_hint="sk-slaif-public",
        owner_id=uuid.uuid4(),
        owner_display_name="Safe Owner",
        owner_email="owner@example.org",
        institution_id=None,
        institution_name=None,
        cohort_id=None,
        cohort_name=None,
        status="active",
        computed_display_status="active",
        can_suspend=True,
        can_activate=False,
        can_revoke=True,
        can_rotate=True,
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_until=datetime.now(UTC) + timedelta(days=30),
        cost_limit_eur=Decimal("5.000000000"),
        token_limit_total=1000,
        request_limit_total=100,
        cost_used_eur=Decimal("0"),
        tokens_used_total=0,
        requests_used_total=0,
        cost_reserved_eur=Decimal("0"),
        tokens_reserved_total=0,
        requests_reserved_total=0,
        allowed_models=(),
        allowed_endpoints=(),
        allow_all_models=True,
        allow_all_endpoints=True,
        key_purpose="standard",
        capability_policy_mode="standard",
        calibration_metadata={},
        template_id=None,
        template_revision_id=None,
        allowed_models_summary="All models",
        allowed_endpoints_summary="All endpoints",
        allowed_providers_summary="All enabled providers",
        rate_limit_policy_summary="Default",
        responses_policy=None,
        responses_policy_summary="None",
        chat_streaming_live_burn_policy={},
        chat_streaming_live_burn_policy_summary="off",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    values.update(overrides)
    values["allowed_providers"] = allowed_providers
    row = AdminKeyListRow(**values)
    return AdminKeyDetail(
        **asdict(row),
        revoked_at=None,
        revoked_reason=None,
        created_by_admin_user_id=None,
        last_used_at=None,
        last_quota_reset_at=None,
        quota_reset_count=0,
    )


def _key_row(
    *,
    id=None,
    requests=None,
    tokens=None,
    concurrency=None,
    window=None,
    metadata=None,
):
    return SimpleNamespace(
        id=id or uuid.uuid4(),
        rate_limit_requests_per_minute=requests,
        rate_limit_tokens_per_minute=tokens,
        max_concurrent_requests=concurrency,
        metadata_json=metadata if metadata is not None else {},
    )


def _patch_gateway_key_lookup(monkeypatch, gateway_key):
    async def get_gateway_key_by_id(self, gateway_key_id):
        return gateway_key

    monkeypatch.setattr(
        "slaif_gateway.db.repositories.keys.GatewayKeysRepository.get_gateway_key_by_id",
        get_gateway_key_by_id,
    )


# ---------------------------------------------------------------------------
# G01: provider tri-state parser (pure)
# ---------------------------------------------------------------------------


def test_parse_admin_allowed_providers_tri_state() -> None:
    from slaif_gateway.api.admin import _parse_admin_allowed_providers

    assert (
        _parse_admin_allowed_providers(
            {"allow_all_providers": "true"}, available_provider_values=[]
        )
        is None
    )
    assert (
        _parse_admin_allowed_providers(
            {"provider_deny_all": "true"}, available_provider_values=[]
        )
        == []
    )
    assert (
        _parse_admin_allowed_providers(
            {"allowed_providers": "openai\nOpenRouter"},
            available_provider_values={"openai", "openrouter"},
        )
        == ["openai", "openrouter"]
    )


def test_parse_admin_allowed_providers_both_modes_refused() -> None:
    from slaif_gateway.api.admin import _parse_admin_allowed_providers

    try:
        _parse_admin_allowed_providers(
            {"allow_all_providers": "true", "provider_deny_all": "true"},
            available_provider_values=[],
        )
    except ValueError as exc:
        assert "Select only one provider mode" in str(exc)
    else:
        raise AssertionError("both provider modes must be refused")


def test_parse_admin_allowed_providers_empty_without_mode_fails_closed() -> None:
    from slaif_gateway.api.admin import _parse_admin_allowed_providers

    try:
        _parse_admin_allowed_providers(
            {"allowed_providers": ""}, available_provider_values={"openai"}
        )
    except ValueError as exc:
        assert "empty selection never grants unrestricted access" in str(exc)
    else:
        raise AssertionError("empty selection without a mode must fail closed")


def test_parse_admin_allowed_providers_unknown_slug_refused() -> None:
    from slaif_gateway.api.admin import _parse_admin_allowed_providers

    try:
        _parse_admin_allowed_providers(
            {"allowed_providers": "ghost"},
            available_provider_values={"openai"},
        )
    except ValueError as exc:
        assert "A selected provider is not available" in str(exc)
    else:
        raise AssertionError("unknown provider slug must be refused")


def test_parse_admin_allowed_providers_secret_shaped_slug_refused() -> None:
    from slaif_gateway.api.admin import _parse_admin_allowed_providers

    try:
        _parse_admin_allowed_providers(
            {"allowed_providers": "sk-slaif-" + "0" * 32},
            available_provider_values={"sk-slaif-" + "0" * 32},
        )
    except ValueError as exc:
        assert "not a secret-like value" in str(exc)
    else:
        raise AssertionError("secret-shaped provider value must be refused")


# ---------------------------------------------------------------------------
# G01: tri-state detail prefill (pure)
# ---------------------------------------------------------------------------


def test_default_key_policy_form_tri_state_prefill() -> None:
    from slaif_gateway.api.admin import _default_key_policy_form_for_key

    unrestricted = _default_key_policy_form_for_key(
        SimpleNamespace(allowed_providers=None, allowed_models=(), allowed_endpoints=(), allow_all_models=True, allow_all_endpoints=True)
    )
    assert unrestricted["allow_all_providers"] == "true"
    assert unrestricted["provider_deny_all"] == ""

    deny_all = _default_key_policy_form_for_key(
        SimpleNamespace(allowed_providers=(), allowed_models=(), allowed_endpoints=(), allow_all_models=True, allow_all_endpoints=True)
    )
    assert deny_all["provider_deny_all"] == "true"
    assert deny_all["allow_all_providers"] == ""

    allow_list = _default_key_policy_form_for_key(
        SimpleNamespace(allowed_providers=("openai",), allowed_models=(), allowed_endpoints=(), allow_all_models=True, allow_all_endpoints=True)
    )
    assert allow_list["allow_all_providers"] == ""
    assert allow_list["provider_deny_all"] == ""
    assert allow_list["allowed_providers"] == "openai"


# ---------------------------------------------------------------------------
# G02: rate editor composition law (pure, mirrors the CLI set law)
# ---------------------------------------------------------------------------


def _rate_form(**overrides) -> dict:
    values = {
        "rate_action_requests_per_window": "unchanged",
        "rate_value_requests_per_window": "",
        "rate_action_tokens_per_window": "unchanged",
        "rate_value_tokens_per_window": "",
        "rate_action_concurrency": "unchanged",
        "rate_value_concurrency": "",
        "rate_action_window": "unchanged",
        "rate_value_window": "",
    }
    values.update(overrides)
    return values


def test_compose_rate_policy_set_and_clear() -> None:
    from slaif_gateway.api.admin import _compose_admin_rate_limit_policy

    current = {"requests_per_minute": 60, "window_seconds": 10}
    form = _rate_form(
        rate_action_tokens_per_window="set",
        rate_value_tokens_per_window="1200",
        rate_action_requests_per_window="clear",
    )
    assert _compose_admin_rate_limit_policy(form, current) == {
        "tokens_per_minute": 1200,
        "window_seconds": 10,
    }


def test_compose_rate_policy_one_per_ten_seconds_and_concurrency_one() -> None:
    from slaif_gateway.api.admin import _compose_admin_rate_limit_policy

    form = _rate_form(
        rate_action_requests_per_window="set",
        rate_value_requests_per_window="1",
        rate_action_window="set",
        rate_value_window="10",
    )
    assert _compose_admin_rate_limit_policy(form, {}) == {
        "requests_per_minute": 1,
        "window_seconds": 10,
    }
    form = _rate_form(rate_action_concurrency="set", rate_value_concurrency="1")
    assert _compose_admin_rate_limit_policy(form, {}) == {
        "max_concurrent_requests": 1
    }


def test_compose_rate_policy_zero_refused() -> None:
    from slaif_gateway.api.admin import _compose_admin_rate_limit_policy

    for value in ("0", "-5"):
        form = _rate_form(
            rate_action_requests_per_window="set",
            rate_value_requests_per_window=value,
        )
        try:
            _compose_admin_rate_limit_policy(form, {})
        except ValueError as exc:
            assert "must be a positive whole number" in str(exc)
        else:
            raise AssertionError(f"value {value!r} must be refused")


def test_compose_rate_policy_blank_set_refused() -> None:
    from slaif_gateway.api.admin import _compose_admin_rate_limit_policy

    form = _rate_form(rate_action_window="set", rate_value_window="   ")
    try:
        _compose_admin_rate_limit_policy(form, {})
    except ValueError as exc:
        assert "Enter a positive whole number" in str(exc)
    else:
        raise AssertionError("blank set value must be refused")


def test_compose_rate_policy_unknown_action_refused() -> None:
    from slaif_gateway.api.admin import _compose_admin_rate_limit_policy

    form = _rate_form(rate_action_concurrency="delete")
    try:
        _compose_admin_rate_limit_policy(form, {})
    except ValueError as exc:
        assert "Select a valid action" in str(exc)
    else:
        raise AssertionError("unknown action must be refused")


def test_rate_policy_no_change_detection() -> None:
    from slaif_gateway.api.admin import (
        _admin_rate_limit_policy_no_change,
        _compose_admin_rate_limit_policy,
    )

    current = {"requests_per_minute": 60, "window_seconds": None}
    assert _admin_rate_limit_policy_no_change(
        current, _compose_admin_rate_limit_policy(_rate_form(), current)
    ) is True
    # Setting the SAME stored value is still a no-op.
    same = _rate_form(
        rate_action_requests_per_window="set", rate_value_requests_per_window="60"
    )
    assert _admin_rate_limit_policy_no_change(
        current, _compose_admin_rate_limit_policy(same, current)
    ) is True
    # Clearing a member that is already inherited is a no-op.
    clear_blank = _rate_form(rate_action_window="clear")
    assert _admin_rate_limit_policy_no_change(
        current, _compose_admin_rate_limit_policy(clear_blank, current)
    ) is True
    changed = _rate_form(
        rate_action_requests_per_window="set", rate_value_requests_per_window="120"
    )
    assert _admin_rate_limit_policy_no_change(
        current, _compose_admin_rate_limit_policy(changed, current)
    ) is False
    clear_real = _rate_form(rate_action_requests_per_window="clear")
    assert _admin_rate_limit_policy_no_change(
        current, _compose_admin_rate_limit_policy(clear_real, current)
    ) is False


def test_default_rate_limit_form_prefill() -> None:
    from slaif_gateway.api.admin import _default_admin_rate_limit_form

    form = _default_admin_rate_limit_form({"requests_per_minute": 60, "window_seconds": None})
    assert form["rate_action_requests_per_window"] == "unchanged"
    assert form["rate_value_requests_per_window"] == "60"
    assert form["rate_value_window"] == ""
    for suffix in ("tokens_per_window", "concurrency", "window"):
        assert form[f"rate_action_{suffix}"] == "unchanged"


# ---------------------------------------------------------------------------
# G02: rate editor route
# ---------------------------------------------------------------------------


def test_rate_limits_unauthenticated_redirects_to_login() -> None:
    client = TestClient(_app())
    response = client.post(
        f"/admin/keys/{uuid.uuid4()}/rate-limits", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_rate_limits_invalid_csrf_fails_before_service(monkeypatch) -> None:
    called = False

    async def update_gateway_key_rate_limits(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_rate_limits",
        update_gateway_key_rate_limits,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)
    response = client.post(
        f"/admin/keys/{uuid.uuid4()}/rate-limits",
        data={"csrf_token": "wrong", "reason": "adjust"},
    )
    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_rate_limits_missing_reason_refused(monkeypatch) -> None:
    key_id = uuid.uuid4()
    _patch_gateway_key_lookup(monkeypatch, _key_row(id=key_id))
    client = TestClient(_app())
    _login_with_render(monkeypatch, client, _detail(id=key_id))
    response = client.post(
        f"/admin/keys/{key_id}/rate-limits",
        data={
            "csrf_token": "dashboard-csrf",
            "rate_action_requests_per_window": "set",
            "rate_value_requests_per_window": "1",
        },
    )
    assert response.status_code == 400
    assert "Enter an audit reason before updating operational rate limits." in response.text


def test_rate_limits_no_op_refused(monkeypatch) -> None:
    key_id = uuid.uuid4()
    _patch_gateway_key_lookup(monkeypatch, _key_row(id=key_id))
    called = False

    async def update_gateway_key_rate_limits(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_rate_limits",
        update_gateway_key_rate_limits,
    )
    client = TestClient(_app())
    _login_with_render(monkeypatch, client, _detail(id=key_id))
    response = client.post(
        f"/admin/keys/{key_id}/rate-limits",
        data={"csrf_token": "dashboard-csrf", "reason": "no change attempt"},
    )
    assert response.status_code == 400
    assert "No rate-limit change requested." in response.text
    assert called is False


def test_rate_limits_set_success_payload(monkeypatch) -> None:
    key_id = uuid.uuid4()
    _patch_gateway_key_lookup(monkeypatch, _key_row(id=key_id, requests=60))
    seen = {}

    async def update_gateway_key_rate_limits(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_rate_limits",
        update_gateway_key_rate_limits,
    )
    client = TestClient(_app())
    admin_user = _login_with_render(monkeypatch, client, _detail(id=key_id))
    response = client.post(
        f"/admin/keys/{key_id}/rate-limits",
        data={
            "csrf_token": "dashboard-csrf",
            "rate_action_requests_per_window": "set",
            "rate_value_requests_per_window": "1",
            "rate_action_window": "set",
            "rate_value_window": "10",
            "reason": "one request per ten seconds",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (
        response.headers["location"]
        == f"/admin/keys/{key_id}?message=key_rate_limits_updated"
    )
    payload = seen["payload"]
    assert payload.gateway_key_id == key_id
    assert payload.rate_limit_policy == {"requests_per_minute": 1, "window_seconds": 10}
    assert payload.actor_admin_id == admin_user.id
    assert payload.reason == "one request per ten seconds"


def test_rate_limits_clear_to_inherit_sends_none(monkeypatch) -> None:
    key_id = uuid.uuid4()
    _patch_gateway_key_lookup(
        monkeypatch, _key_row(id=key_id, requests=60, tokens=1200)
    )
    seen = {}

    async def update_gateway_key_rate_limits(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_rate_limits",
        update_gateway_key_rate_limits,
    )
    client = TestClient(_app())
    _login_with_render(monkeypatch, client, _detail(id=key_id))
    response = client.post(
        f"/admin/keys/{key_id}/rate-limits",
        data={
            "csrf_token": "dashboard-csrf",
            "rate_action_requests_per_window": "clear",
            "rate_action_tokens_per_window": "clear",
            "reason": "inherit deployment",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    # Every member cleared: the persisted policy becomes null (inherit).
    assert seen["payload"].rate_limit_policy is None


def test_rate_limits_zero_value_refused_with_fixed_message(monkeypatch) -> None:
    key_id = uuid.uuid4()
    _patch_gateway_key_lookup(monkeypatch, _key_row(id=key_id))
    client = TestClient(_app())
    _login_with_render(monkeypatch, client, _detail(id=key_id))
    response = client.post(
        f"/admin/keys/{key_id}/rate-limits",
        data={
            "csrf_token": "dashboard-csrf",
            "rate_action_concurrency": "set",
            "rate_value_concurrency": "0",
            "reason": "try zero",
        },
    )
    assert response.status_code == 400
    assert "Concurrent requests must be a positive whole number." in response.text


def test_rate_limits_unknown_key_404(monkeypatch) -> None:
    key_id = uuid.uuid4()
    _patch_gateway_key_lookup(monkeypatch, None)

    async def get_key_detail(self, gateway_key_id):
        raise AdminKeyNotFoundError("missing")

    client = TestClient(_app())
    _login_with_render(monkeypatch, client, None)
    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    response = client.post(
        f"/admin/keys/{key_id}/rate-limits",
        data={"csrf_token": "dashboard-csrf", "reason": "adjust"},
    )
    assert response.status_code == 404
    assert "Gateway key not found." in response.text


# ---------------------------------------------------------------------------
# G01: advanced configuration download (route)
# ---------------------------------------------------------------------------


def _export_document():
    return {
        "schema_version": 1,
        "cost_limit_eur": Decimal("2.000000000"),
        "allowed_providers": ["openai"],
        "valid_until": datetime(2027, 1, 1, tzinfo=UTC),
    }


def test_configuration_download_unauthenticated_redirects(monkeypatch) -> None:
    client = TestClient(_app())
    response = client.get(
        f"/admin/keys/{uuid.uuid4()}/configuration.json", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_configuration_download_headers_and_exact_decimals(monkeypatch) -> None:
    key_id = uuid.uuid4()
    detail = _detail(id=key_id)

    async def export_gateway_key_configuration(self, gateway_key_id):
        assert gateway_key_id == key_id
        return _export_document()

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.export_gateway_key_configuration",
        export_gateway_key_configuration,
    )
    client = TestClient(_app())
    _login_with_render(monkeypatch, client, detail)
    response = client.get(f"/admin/keys/{key_id}/configuration.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="slaif-key-configuration-{detail.public_key_id}.json"'
    )
    assert "no-store" in response.headers.get("cache-control", "")
    document = json.loads(response.text)
    # Exact decimal strings: no float, no re-rounding, key-sorted export.
    assert document["cost_limit_eur"] == "2.000000000"
    assert document["allowed_providers"] == ["openai"]
    assert list(document) == sorted(document)


def test_configuration_download_export_error_409(monkeypatch) -> None:
    key_id = uuid.uuid4()

    async def export_gateway_key_configuration(self, gateway_key_id):
        raise KeyManagementError(
            "Stored policy cannot be exported as a configuration document."
        )

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.export_gateway_key_configuration",
        export_gateway_key_configuration,
    )
    client = TestClient(_app())
    _login_with_render(monkeypatch, client, _detail(id=key_id))
    response = client.get(f"/admin/keys/{key_id}/configuration.json")
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# G01: advanced configuration update (route)
# ---------------------------------------------------------------------------


def _config_post(key_id, monkeypatch, document, *, reason="update", confirm="true"):
    client = TestClient(_app())
    _login_with_render(monkeypatch, client, _detail(id=key_id))
    return client.post(
        f"/admin/keys/{key_id}/configuration",
        data={
            "csrf_token": "dashboard-csrf",
            "configuration_json": document,
            "confirm_configuration_update": confirm,
            "reason": reason,
        },
        follow_redirects=False,
    )


def test_configuration_post_missing_reason_refused_without_echo(monkeypatch) -> None:
    key_id = uuid.uuid4()
    document = json.dumps(
        {"schema_version": 1, "note": CANARY, "cost_limit_eur": "5"}
    )
    response = _config_post(key_id, monkeypatch, document, reason="   ")
    assert response.status_code == 400
    assert "Enter an audit reason before updating the advanced key configuration." in response.text
    assert CANARY not in response.text


def test_configuration_post_missing_confirmation_refused_without_echo(monkeypatch) -> None:
    key_id = uuid.uuid4()
    document = json.dumps({"schema_version": 1, "cost_limit_eur": "5", "note": CANARY})
    response = _config_post(key_id, monkeypatch, document, confirm="")
    assert response.status_code == 400
    assert "Confirm the advanced key configuration update before continuing." in response.text
    assert CANARY not in response.text


def test_configuration_post_empty_text_refused(monkeypatch) -> None:
    key_id = uuid.uuid4()
    response = _config_post(key_id, monkeypatch, "   ")
    assert response.status_code == 400
    assert "Enter a valid advanced configuration document." in response.text


def test_configuration_post_malformed_json_refused_without_echo(monkeypatch) -> None:
    key_id = uuid.uuid4()
    response = _config_post(key_id, monkeypatch, "{not json " + CANARY)
    assert response.status_code == 400
    assert "file: File is not valid JSON." in response.text
    assert CANARY not in response.text


def test_configuration_post_duplicate_key_refused(monkeypatch) -> None:
    key_id = uuid.uuid4()
    response = _config_post(
        key_id,
        monkeypatch,
        '{"schema_version": 1, "cost_limit_eur": "1", "cost_limit_eur": "2"}',
    )
    assert response.status_code == 400
    assert "JSON object contains a duplicate key." in response.text


def test_configuration_post_unknown_field_refused(monkeypatch) -> None:
    key_id = uuid.uuid4()
    response = _config_post(
        key_id, monkeypatch, '{"schema_version": 1, "bogus_field": 1}'
    )
    assert response.status_code == 400
    assert "Document contains unsupported fields." in response.text


def test_configuration_post_missing_schema_version_refused(monkeypatch) -> None:
    key_id = uuid.uuid4()
    response = _config_post(key_id, monkeypatch, '{"cost_limit_eur": "1"}')
    assert response.status_code == 400
    assert "schema_version: Field is required." in response.text


def test_configuration_post_empty_object_refused(monkeypatch) -> None:
    key_id = uuid.uuid4()
    response = _config_post(key_id, monkeypatch, '{"schema_version": 1}')
    assert response.status_code == 400
    assert "The configuration document contains no requested changes." in response.text


def test_configuration_post_success_payload(monkeypatch) -> None:
    key_id = uuid.uuid4()
    seen = {}

    async def update_gateway_key_configuration(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_configuration",
        update_gateway_key_configuration,
    )
    document = json.dumps(
        {
            "schema_version": 1,
            "cost_limit_eur": "7.500000000",
            "rate_limit_policy": {"requests_per_minute": 120},
        }
    )
    response = _config_post(key_id, monkeypatch, document, reason="raise limit")
    assert response.status_code == 303
    payload = seen["payload"]
    assert payload.gateway_key_id == key_id
    assert payload.reason == "raise limit"
    assert payload.configuration.cost_limit_eur == Decimal("7.500000000")
    assert payload.configuration.rate_limit_policy == {"requests_per_minute": 120}


def test_configuration_post_service_error_uses_safe_message(monkeypatch) -> None:
    key_id = uuid.uuid4()

    async def update_gateway_key_configuration(self, payload):
        raise KeyManagementError("Bound client module cannot be changed here.")

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_configuration",
        update_gateway_key_configuration,
    )
    document = json.dumps({"schema_version": 1, "responses_policy": None})
    response = _config_post(key_id, monkeypatch, document)
    assert response.status_code == 400
    assert "Bound client module cannot be changed here." in response.text


# ---------------------------------------------------------------------------
# G03: explain route (route)
# ---------------------------------------------------------------------------


def test_explain_route_unauthenticated_redirects() -> None:
    client = TestClient(_app())
    response = client.post(
        f"/admin/keys/{uuid.uuid4()}/explain-route", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_explain_route_renders_shared_report(monkeypatch) -> None:
    key_id = uuid.uuid4()
    _patch_gateway_key_lookup(monkeypatch, _key_row(id=key_id))
    seen = {}

    async def explain_model_route_access(**kwargs):
        seen["kwargs"] = kwargs
        return {
            "note": "Configuration-only view.",
            "verdict": "resolved",
            "message": "Model is allowed on the selected endpoint.",
            "blocker": None,
            "resolution": None,
            "capability_checks": None,
            "allowlist_intersection": None,
            "unevaluated": [],
            "bounds": {
                "route_candidate_bound": 1000,
                "routes_examined": 2,
                "possible_unexamined_routes": False,
            },
        }

    monkeypatch.setattr(
        "slaif_gateway.api.admin.explain_model_route_access",
        explain_model_route_access,
    )
    client = TestClient(_app())
    _login_with_render(monkeypatch, client, _detail(id=key_id))
    response = client.post(
        f"/admin/keys/{key_id}/explain-route",
        data={
            "csrf_token": "dashboard-csrf",
            "endpoint": "/v1/chat/completions",
            "model": "gpt-test-model",
        },
    )
    assert response.status_code == 200
    assert "Configuration-only view." in response.text
    assert "Model is allowed on the selected endpoint." in response.text
    assert "data-explain-report" in response.text
    kwargs = seen["kwargs"]
    assert kwargs["requested_model"] == "gpt-test-model"
    assert kwargs["endpoint"] == "/v1/chat/completions"


def test_explain_route_unavailable_503(monkeypatch) -> None:
    key_id = uuid.uuid4()
    _patch_gateway_key_lookup(monkeypatch, _key_row(id=key_id))

    async def explain_model_route_access(**kwargs):
        raise RuntimeError("read snapshot unavailable")

    monkeypatch.setattr(
        "slaif_gateway.api.admin.explain_model_route_access",
        explain_model_route_access,
    )
    client = TestClient(_app())
    _login_with_render(monkeypatch, client, _detail(id=key_id))
    response = client.post(
        f"/admin/keys/{key_id}/explain-route",
        data={"csrf_token": "dashboard-csrf", "endpoint": "/v1/models", "model": "m"},
    )
    assert response.status_code == 503
    assert "Policy explanation is currently unavailable." in response.text


# ---------------------------------------------------------------------------
# G01: request-policy route tri-state (existing endpoint, new law)
# ---------------------------------------------------------------------------


def _policy_post(key_id, monkeypatch, data, *, row=None, detail_row=None):
    _patch_gateway_key_lookup(monkeypatch, row or _key_row(id=key_id))
    client = TestClient(_app())
    _login_with_render(
        monkeypatch, client, detail_row or _detail(id=key_id)
    )
    base = {
        "csrf_token": "dashboard-csrf",
        "allow_all_models": "true",
        "allow_all_endpoints": "true",
        "reason": "policy change",
    }
    base.update(data)
    return client.post(f"/admin/keys/{key_id}/policy", data=base, follow_redirects=False)


def test_policy_update_both_provider_modes_refused(monkeypatch) -> None:
    key_id = uuid.uuid4()
    response = _policy_post(
        key_id,
        monkeypatch,
        {"allow_all_providers": "true", "provider_deny_all": "true"},
    )
    assert response.status_code == 400
    assert "Select only one provider mode" in response.text


def test_policy_update_empty_selection_without_mode_fails_closed(monkeypatch) -> None:
    key_id = uuid.uuid4()
    response = _policy_post(key_id, monkeypatch, {})
    assert response.status_code == 400
    assert "an empty selection never grants unrestricted access" in response.text


def test_policy_update_deny_all_persists_empty_list(monkeypatch) -> None:
    key_id = uuid.uuid4()
    seen = {}

    async def update_gateway_key_policy(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_policy",
        update_gateway_key_policy,
    )
    response = _policy_post(key_id, monkeypatch, {"provider_deny_all": "true"})
    assert response.status_code == 303
    assert seen["payload"].allowed_providers == []
    assert seen["payload"].update_allowed_providers is True


def test_policy_update_allow_all_persists_null(monkeypatch) -> None:
    key_id = uuid.uuid4()
    seen = {}

    async def update_gateway_key_policy(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_policy",
        update_gateway_key_policy,
    )
    response = _policy_post(key_id, monkeypatch, {"allow_all_providers": "true"})
    assert response.status_code == 303
    assert seen["payload"].allowed_providers is None


def test_policy_update_preserves_disabled_stored_provider(monkeypatch) -> None:
    """A stored slug for a now-disabled provider round-trips unchanged.

    The unit fake DB reports NO enabled providers, so the only way the
    submission validates is through the key's preserved stored list.
    """
    key_id = uuid.uuid4()
    row = _key_row(id=key_id, metadata={"allowed_providers": ["legacy-provider"]})
    seen = {}

    async def update_gateway_key_policy(self, payload):
        seen["payload"] = payload

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_policy",
        update_gateway_key_policy,
    )
    response = _policy_post(
        key_id,
        monkeypatch,
        {"allowed_providers": "legacy-provider"},
        row=row,
    )
    assert response.status_code == 303
    assert seen["payload"].allowed_providers == ["legacy-provider"]


def test_policy_update_unknown_provider_refused(monkeypatch) -> None:
    key_id = uuid.uuid4()
    response = _policy_post(key_id, monkeypatch, {"allowed_providers": "ghost"})
    assert response.status_code == 400
    assert "A selected provider is not available" in response.text


# ---------------------------------------------------------------------------
# G01: create form advanced document mode
# ---------------------------------------------------------------------------


def _create_doc_post(monkeypatch, data, *, detail_row=None):
    client = TestClient(_app())
    _login_with_render(monkeypatch, client, detail_row)
    base = {
        "csrf_token": "dashboard-csrf",
        "owner_id": str(uuid.uuid4()),
        "valid_days": "30",
        "email_delivery_mode": "none",
        "reason": "create key",
        "policy_source": "configuration",
    }
    base.update(data)
    return client.post("/admin/keys/create", data=base)


def test_create_document_mode_missing_document_refused(monkeypatch) -> None:
    response = _create_doc_post(monkeypatch, {})
    assert response.status_code == 400
    assert (
        "Enter a valid advanced configuration document or choose guided fields."
        in response.text
    )


def test_create_document_mode_with_guided_fields_refused(monkeypatch) -> None:
    document = json.dumps({"schema_version": 1, "cost_limit_eur": "5"})
    response = _create_doc_post(
        monkeypatch, {"configuration_json": document, "allowed_models": "gpt-test"}
    )
    assert response.status_code == 400
    assert "Choose one policy source" in response.text


def test_create_document_mode_with_codex_preset_refused(monkeypatch) -> None:
    document = json.dumps({"schema_version": 1, "cost_limit_eur": "5"})
    response = _create_doc_post(
        monkeypatch,
        {
            "configuration_json": document,
            "codex_protocol_pilot": "true",
            "confirm_codex_protocol_pilot": "true",
        },
    )
    assert response.status_code == 400
    assert "Advanced configuration documents cannot be combined" in response.text


def test_create_trusted_calibration_with_deny_all_refused(monkeypatch) -> None:
    response = _create_doc_post(
        monkeypatch,
        {
            "policy_source": "guided",
            "trusted_calibration": "true",
            "confirm_trusted_calibration": "true",
            "provider_deny_all": "true",
        },
    )
    assert response.status_code == 400
    assert "deny-all is not compatible" in response.text


def test_create_document_mode_success_builds_shared_input(monkeypatch) -> None:
    owner_id = uuid.uuid4()
    seen = {}
    key_id = uuid.uuid4()
    now = datetime.now(UTC)

    async def get_owner_by_id(self, owner_id_value):
        assert owner_id_value == owner_id
        return SimpleNamespace(id=owner_id, display_name="Safe Owner")

    monkeypatch.setattr(
        "slaif_gateway.db.repositories.owners.OwnersRepository.get_owner_by_id",
        get_owner_by_id,
    )
    async def create_gateway_key(self, payload):
        seen["payload"] = payload
        return CreatedGatewayKey(
            gateway_key_id=key_id,
            owner_id=owner_id,
            public_key_id="public-new",
            display_prefix="sk-slaif-",
            plaintext_key="sk-slaif-" + "x" * 40,
            one_time_secret_id=uuid.uuid4(),
            valid_from=now,
            valid_until=now + timedelta(days=30),
        )

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.create_gateway_key",
        create_gateway_key,
    )
    document = json.dumps(
        {
            "schema_version": 1,
            "cost_limit_eur": "9.250000000",
            "allowed_models": ["gpt-test-model"],
            "allow_all_endpoints": True,
            "allowed_providers": ["openai"],
        }
    )
    client = TestClient(_app())
    _login_with_render(monkeypatch, client, None)
    response = client.post(
        "/admin/keys/create",
        data={
            "csrf_token": "dashboard-csrf",
            "owner_id": str(owner_id),
            "valid_days": "30",
            "email_delivery_mode": "none",
            "reason": "create key",
            "policy_source": "configuration",
            "configuration_json": document,
        },
        follow_redirects=False,
    )
    # Email mode "none" renders the create-result page (the plaintext key
    # is shown once, to the authenticated operator, on this page only).
    assert response.status_code == 200
    assert "public-new" in response.text
    payload = seen["payload"]
    assert payload.owner_id == owner_id
    assert payload.cost_limit_eur == Decimal("9.250000000")
    assert payload.allowed_models == ["gpt-test-model"]
    assert payload.allow_all_endpoints is True
    assert payload.allowed_providers == ["openai"]
    assert payload.note == "create key"


def test_create_document_mode_error_scrubs_configuration_json(monkeypatch) -> None:
    document = "{not json " + CANARY
    response = _create_doc_post(monkeypatch, {"configuration_json": document})
    assert response.status_code == 400
    assert "file: File is not valid JSON." in response.text
    assert CANARY not in response.text

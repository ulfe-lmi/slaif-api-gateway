import re
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_keys import AdminKeyDetail, AdminKeyListRow
from slaif_gateway.services.calibration_summary_service import (
    CalibrationObservedSummary,
    CalibrationPolicyProposal,
    CalibrationPreviewResult,
)
from slaif_gateway.services.admin_key_dashboard import AdminKeyNotFoundError
from slaif_gateway.services.admin_session_service import AdminSessionContext


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def begin(self):
        return self


class _FakeSessionmaker:
    def __call__(self):
        return _FakeSession()


def _settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://user:secret@localhost:5432/test_db",
        "ADMIN_SESSION_SECRET": "s" * 40,
    }
    values.update(overrides)
    return Settings(**values)


def _app(settings: Settings | None = None):
    app = create_app(settings or _settings())
    app.state.db_sessionmaker = _FakeSessionmaker()
    return app


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


def _row() -> AdminKeyListRow:
    return AdminKeyListRow(
        id=uuid.uuid4(),
        public_key_id="public-test-id",
        key_prefix="sk-slaif-",
        key_hint="sk-slaif-public",
        owner_id=uuid.uuid4(),
        owner_display_name="Ada Lovelace",
        owner_email="ada@example.org",
        institution_id=uuid.uuid4(),
        institution_name="SLAIF University",
        cohort_id=uuid.uuid4(),
        cohort_name="Spring Workshop",
        status="active",
        computed_display_status="active",
        can_suspend=True,
        can_activate=False,
        can_revoke=True,
        can_rotate=True,
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_until=datetime.now(UTC) + timedelta(days=1),
        cost_limit_eur=Decimal("10.000000000"),
        token_limit_total=1000,
        request_limit_total=100,
        cost_used_eur=Decimal("1.000000000"),
        tokens_used_total=10,
        requests_used_total=2,
        cost_reserved_eur=Decimal("0.100000000"),
        tokens_reserved_total=5,
        requests_reserved_total=1,
        allowed_models=("gpt-test",),
        allowed_endpoints=("/v1/chat/completions",),
        allow_all_models=False,
        allow_all_endpoints=False,
        key_purpose="standard",
        capability_policy_mode="standard",
        calibration_metadata={},
        allowed_models_summary="gpt-test",
        allowed_endpoints_summary="/v1/chat/completions",
        allowed_providers_summary="openai",
        rate_limit_policy_summary="30 req/min",
        created_at=datetime.now(UTC) - timedelta(days=2),
        updated_at=datetime.now(UTC) - timedelta(days=1),
    )


def _detail() -> AdminKeyDetail:
    row = _row()
    return AdminKeyDetail(
        **asdict(row),
        revoked_at=None,
        revoked_reason=None,
        created_by_admin_user_id=uuid.uuid4(),
        last_used_at=None,
        last_quota_reset_at=None,
        quota_reset_count=0,
    )


def _trusted_detail() -> AdminKeyDetail:
    row = _row()
    return AdminKeyDetail(
        **{
            **asdict(row),
            "key_purpose": "trusted_calibration",
            "capability_policy_mode": "trusted_calibration_discovery",
            "calibration_metadata": {"created_from": "admin_web"},
        },
        revoked_at=None,
        revoked_reason=None,
        created_by_admin_user_id=uuid.uuid4(),
        last_used_at=None,
        last_quota_reset_at=None,
        quota_reset_count=0,
    )


def _login(monkeypatch, client: TestClient) -> None:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "dashboard-csrf"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    client.cookies.set("slaif_admin_session", "session-plaintext")


def test_admin_keys_redirects_when_unauthenticated() -> None:
    response = TestClient(_app()).get("/admin/keys", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_keys_list_returns_html_and_accepts_filters(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def list_keys(self, **kwargs):
        seen.update(kwargs)
        return [_row()]

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.list_keys",
        list_keys,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)
    cohort_id = uuid.uuid4()

    response = client.get(
        "/admin/keys",
        params={
            "status": "active",
            "owner_email": "ada@example.org",
            "public_key_id": "public-test-id",
            "cohort_id": str(cohort_id),
            "expired": "false",
            "limit": "25",
            "offset": "5",
        },
    )

    assert response.status_code == 200
    assert "Gateway Keys" in response.text
    assert "public-test-id" in response.text
    assert "Ada Lovelace" in response.text
    assert seen["status"] == "active"
    assert seen["owner_email"] == "ada@example.org"
    assert seen["public_key_id"] == "public-test-id"
    assert seen["cohort_id"] == cohort_id
    assert seen["expired"] is False
    assert seen["limit"] == 25
    assert seen["offset"] == 5


def test_admin_keys_list_marks_trusted_calibration(monkeypatch) -> None:
    key = _trusted_detail()

    async def list_keys(self, **kwargs):
        return [key]

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.list_keys",
        list_keys,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get("/admin/keys")

    assert response.status_code == 200
    assert "Trusted calibration" in response.text


def test_admin_key_detail_returns_html(monkeypatch) -> None:
    key = _detail()

    async def get_key_detail(self, gateway_key_id):
        assert gateway_key_id == key.id
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(f"/admin/keys/{key.id}")

    assert response.status_code == 200
    assert "Gateway Key Detail" in response.text
    assert key.public_key_id in response.text
    assert "Plaintext keys" in response.text
    assert "Update Request Policy" in response.text
    assert f'action="/admin/keys/{key.id}/policy"' in response.text
    assert 'name="allowed_models"' in response.text
    assert 'name="allowed_endpoints"' in response.text
    assert 'name="allow_all_models" value="true"' in response.text
    assert 'name="allow_all_endpoints" value="true"' in response.text
    assert "Models must not start with" in response.text


def test_admin_key_detail_shows_trusted_calibration_metadata(monkeypatch) -> None:
    key = _trusted_detail()

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(f"/admin/keys/{key.id}")

    assert response.status_code == 200
    assert "Trusted Calibration Key" in response.text
    assert "trusted_calibration" in response.text
    assert "trusted_calibration_discovery" in response.text
    assert "created_from" in response.text
    assert "admin_web" in response.text
    assert f'href="/admin/keys/{key.id}/calibration"' in response.text


def test_standard_key_detail_does_not_offer_calibration_preview(monkeypatch) -> None:
    key = _detail()

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(f"/admin/keys/{key.id}")

    assert response.status_code == 200
    assert f"/admin/keys/{key.id}/calibration" not in response.text


def test_calibration_form_requires_login() -> None:
    response = TestClient(_app()).get(f"/admin/keys/{uuid.uuid4()}/calibration", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_trusted_calibration_form_renders_preview_controls(monkeypatch) -> None:
    key = _trusted_detail()

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(f"/admin/keys/{key.id}/calibration")

    assert response.status_code == 200
    assert "Calibration Policy Preview" in response.text
    assert "Preview Only" in response.text
    assert f'action="/admin/keys/{key.id}/calibration/preview"' in response.text
    assert 'name="csrf_token" value="dashboard-csrf"' in response.text
    assert 'name="multiplier"' in response.text
    assert "does not mutate gateway key policy" in response.text


def test_standard_key_calibration_form_is_rejected(monkeypatch) -> None:
    key = _detail()

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(f"/admin/keys/{key.id}/calibration")

    assert response.status_code == 400
    assert "trusted calibration keys" in response.text


def test_standard_key_calibration_preview_is_rejected(monkeypatch) -> None:
    key = _detail()

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    async def summarize_calibration_key_usage(self, **kwargs):
        from slaif_gateway.services.calibration_summary_service import CalibrationSummaryError

        raise CalibrationSummaryError("Calibration summaries are available only for trusted calibration keys.")

    monkeypatch.setattr(
        "slaif_gateway.services.calibration_summary_service.CalibrationSummaryService.summarize_calibration_key_usage",
        summarize_calibration_key_usage,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        lambda self, admin_session, csrf_token: csrf_token == "dashboard-csrf",
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{key.id}/calibration/preview",
        data={"csrf_token": "dashboard-csrf", "multiplier": "2"},
    )

    assert response.status_code == 400
    assert "trusted calibration keys" in response.text


def test_calibration_preview_requires_csrf(monkeypatch) -> None:
    key = _trusted_detail()
    called = False

    async def summarize_calibration_key_usage(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.calibration_summary_service.CalibrationSummaryService.summarize_calibration_key_usage",
        summarize_calibration_key_usage,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.post(f"/admin/keys/{key.id}/calibration/preview")

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_calibration_preview_returns_no_cache_safe_result(monkeypatch) -> None:
    key = _trusted_detail()

    async def summarize_calibration_key_usage(self, **kwargs):
        assert kwargs["gateway_key_id"] == key.id
        assert kwargs["multiplier"] == Decimal("2")
        return _calibration_preview(key.id)

    monkeypatch.setattr(
        "slaif_gateway.services.calibration_summary_service.CalibrationSummaryService.summarize_calibration_key_usage",
        summarize_calibration_key_usage,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        lambda self, admin_session, csrf_token: csrf_token == "dashboard-csrf",
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{key.id}/calibration/preview",
        data={"csrf_token": "dashboard-csrf", "multiplier": "2"},
    )

    assert response.status_code == 200
    assert "Strict Policy Proposal Preview" in response.text
    assert "Observed Usage Summary" in response.text
    assert "Strict Participant Policy Proposal" in response.text
    assert "No templates, keys, routes, pricing rows, or gateway key policies were changed" in response.text
    assert "gpt-4.1-mini" in response.text
    assert "no-store" in response.headers["cache-control"]
    assert "sk-provider-secret-placeholder" not in response.text
    assert "Authorization: Bearer" not in response.text
    assert "csrf_token" in response.text
    assert "session_token" not in response.text
    assert "raw request" not in response.text.lower()


def _calibration_preview(gateway_key_id: uuid.UUID) -> CalibrationPreviewResult:
    now = datetime.now(UTC)
    summary = CalibrationObservedSummary(
        gateway_key_id=gateway_key_id,
        public_key_id="public-calibration",
        owner_id=uuid.uuid4(),
        owner_email="ada@example.org",
        owner_display_name="Ada Lovelace",
        institution_id=None,
        institution_name=None,
        cohort_id=None,
        cohort_name=None,
        time_window_start=None,
        time_window_end=None,
        observed_request_count=1,
        observed_endpoints=("/v1/chat/completions",),
        observed_providers=("openai",),
        observed_requested_models=("gpt-4.1-mini",),
        observed_resolved_upstream_models=("gpt-4.1-mini",),
        observed_provider_hosts=("api.openai.com",),
        observed_provider_endpoint_paths=("/v1/chat/completions",),
        observed_hosted_capabilities=(),
        observed_unknown_hosted_capabilities=(),
        observed_denied_capabilities=(),
        total_input_tokens=5,
        total_output_tokens=6,
        total_tokens=11,
        total_reasoning_tokens=None,
        total_cached_tokens=None,
        max_input_tokens_per_request=5,
        max_output_tokens_per_request=6,
        max_total_tokens_per_request=11,
        max_reasoning_tokens_per_request=None,
        max_cached_tokens_per_request=None,
        total_slaif_calculated_cost=Decimal("0.001000000"),
        total_provider_reported_cost=None,
        max_slaif_calculated_cost_per_request=Decimal("0.001000000"),
        max_provider_reported_cost_per_request=None,
        cost_currencies=("EUR",),
        cost_confidence="slaif_calculated",
        warnings=(),
    )
    proposal = CalibrationPolicyProposal(
        proposed_allowed_endpoints=("/v1/chat/completions",),
        proposed_allowed_models=("gpt-4.1-mini",),
        proposed_allowed_providers=("openai",),
        proposed_allowed_hosted_capabilities=(),
        hosted_capabilities_requiring_review=(),
        proposed_request_limit_total=2,
        proposed_token_limit_total=22,
        proposed_input_token_limit_total=10,
        proposed_output_token_limit_total=12,
        proposed_reasoning_token_limit_total=None,
        proposed_cost_limit_eur=Decimal("0.002000000"),
        proposed_max_input_tokens_per_request=10,
        proposed_max_output_tokens_per_request=12,
        proposed_max_total_tokens_per_request=22,
        proposed_max_single_request_cost_eur=Decimal("0.002000000"),
        proposed_rate_limit_policy=None,
        warnings=(),
        assumptions=("Preview only",),
        source_gateway_key_id=gateway_key_id,
        source_time_window_start=now,
        source_time_window_end=now,
        multiplier=Decimal("2"),
    )
    return CalibrationPreviewResult(summary=summary, proposal=proposal, is_empty=False)


def test_admin_key_detail_missing_or_invalid_is_safe(monkeypatch) -> None:
    async def get_key_detail(self, gateway_key_id):
        raise AdminKeyNotFoundError("missing")

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    missing = client.get(f"/admin/keys/{uuid.uuid4()}")
    invalid = client.get("/admin/keys/not-a-uuid")

    assert missing.status_code == 404
    assert invalid.status_code == 404
    assert "Gateway key not found." in missing.text
    assert "Gateway key not found." in invalid.text


def test_admin_keys_templates_do_not_render_sensitive_values(monkeypatch) -> None:
    secret_markers = [
        "plaintext-key-must-not-render",
        "token_hash_must_not_render",
        "encrypted_payload_must_not_render",
        "nonce_must_not_render",
        "sk-provider-secret-placeholder",
        "password_hash_must_not_render",
        "session-plaintext",
    ]
    key = _detail()

    async def list_keys(self, **kwargs):
        return [key]

    async def get_key_detail(self, gateway_key_id):
        return key

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.list_keys",
        list_keys,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    client = TestClient(
        _app(
            _settings(
                OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
                OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
            )
        )
    )
    _login(monkeypatch, client)

    list_response = client.get("/admin/keys")
    detail_response = client.get(f"/admin/keys/{key.id}")
    combined = f"{list_response.text}\n{detail_response.text}"

    assert key.public_key_id in combined
    assert key.key_prefix in combined
    assert key.key_hint in combined
    for marker in secret_markers:
        assert marker not in combined
    assert re.search(r"token_hash|encrypted_payload|nonce|password_hash", combined) is None

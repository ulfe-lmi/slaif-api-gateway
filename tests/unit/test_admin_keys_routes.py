import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_keys import AdminKeyDetail, AdminKeyListRow
from slaif_gateway.schemas.keys import CreatedGatewayKey
from slaif_gateway.services.calibration_summary_service import (
    CalibrationObservedSummary,
    CalibrationPolicyProposal,
    CalibrationPreviewResult,
)
from slaif_gateway.services.admin_key_dashboard import AdminKeyNotFoundError
from slaif_gateway.services.key_errors import InvalidGatewayKeyPolicyError
from slaif_gateway.services.key_policy_validation import GatewayKeyPolicy
from slaif_gateway.services.admin_session_service import AdminSessionContext
from tests.unit.test_admin_key_actions_routes import _login_for_actions


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
        template_id=None,
        template_revision_id=None,
        allowed_models_summary="gpt-test",
        allowed_endpoints_summary="/v1/chat/completions",
        allowed_providers_summary="openai",
        rate_limit_policy_summary="30 req/min",
        responses_policy=None,
        responses_policy_summary="None",
        chat_streaming_live_burn_policy={
            "version": 1,
            "enabled": True,
            "cost_margin_eur": "0.000000000",
            "token_margin": 0,
        },
        chat_streaming_live_burn_policy_summary="Enabled, cost margin EUR 0.000000000, token margin 0",
        created_at=datetime.now(UTC) - timedelta(days=2),
        updated_at=datetime.now(UTC) - timedelta(days=1),
        allowed_providers=("openai",),
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


async def _policy_catalog(request):
    return {
        "provider_choices": [
            SimpleNamespace(
                value="openai",
                display_name="OpenAI",
                kind="openai_compatible",
                label="OpenAI | openai | openai_compatible",
            )
        ],
        "endpoint_choices": [
            SimpleNamespace(
                value="/v1/models",
                label="/v1/models | list visible models",
                description="Catalog listing behaves differently from model-backed generation endpoints.",
                is_model_backed=False,
            ),
            SimpleNamespace(
                value="/v1/chat/completions",
                label="/v1/chat/completions | Chat Completions",
                description="Model-backed endpoint. Explicit models or allow-all-models may be required.",
                is_model_backed=True,
            ),
        ],
        "model_choices": [],
        "model_choices_by_group": {
            "/v1/chat/completions | OpenAI": [
                SimpleNamespace(
                    route_key="openai|/v1/chat/completions|gpt-test|exact|gpt-test-upstream",
                    token="gpt-test",
                    provider="openai",
                    endpoint="/v1/chat/completions",
                    label="gpt-test | openai | /v1/chat/completions | exact | gpt-test-upstream | hidden from /v1/models | streaming",
                    visible_in_models=False,
                    supports_streaming=True,
                )
            ]
        },
        "enabled_provider_values": ("openai",),
    }


async def _validate_admin_request_policy(
    request,
    *,
    allowed_models,
    allowed_endpoints,
    allow_all_models,
    allow_all_endpoints,
):
    return GatewayKeyPolicy(
        allowed_models=list(allowed_models),
        allowed_endpoints=list(allowed_endpoints),
        allow_all_models=allow_all_models,
        allow_all_endpoints=allow_all_endpoints,
    )


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
    monkeypatch.setattr("slaif_gateway.api.admin._load_key_policy_catalog", _policy_catalog)
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(f"/admin/keys/{key.id}")

    assert response.status_code == 200
    assert "Gateway Key Detail" in response.text
    assert key.public_key_id in response.text
    assert "Plaintext keys" in response.text
    assert "Update Request Policy" in response.text
    assert f'action="/admin/keys/{key.id}/policy"' in response.text
    assert 'data-policy-selector-surface' in response.text
    assert "Available enabled providers" in response.text
    assert "Available implemented endpoints" in response.text
    assert "Available route-backed model candidates" in response.text
    assert "Selected allowed providers" in response.text
    assert "The selected list stores requested model tokens, not route IDs." in response.text
    assert 'name="allowed_providers"' in response.text
    assert 'name="allow_all_providers" value="true"' in response.text
    assert 'name="allowed_models"' in response.text
    assert 'name="allowed_endpoints"' in response.text
    assert 'name="allow_all_models" value="true"' in response.text
    assert 'name="allow_all_endpoints" value="true"' in response.text
    assert "hidden from /v1/models" in response.text
    assert "Advanced manual policy strings (fallback)" in response.text


def test_admin_key_policy_update_rejects_model_backed_endpoint_without_models(monkeypatch) -> None:
    key = _detail()

    async def get_key_detail(self, gateway_key_id):
        assert gateway_key_id == key.id
        return key

    async def reject_policy(*args, **kwargs):
        raise InvalidGatewayKeyPolicyError(
            "Select at least one allowed model or allow all models for model-backed endpoints."
        )

    async def update_gateway_key_policy(self, payload):
        raise AssertionError("update_gateway_key_policy should not be called for invalid policy")

    monkeypatch.setattr(
        "slaif_gateway.services.admin_key_dashboard.AdminKeyDashboardService.get_key_detail",
        get_key_detail,
    )
    monkeypatch.setattr("slaif_gateway.api.admin._load_key_policy_catalog", _policy_catalog)
    monkeypatch.setattr(
        "slaif_gateway.api.admin._validate_admin_request_policy",
        reject_policy,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.update_gateway_key_policy",
        update_gateway_key_policy,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{key.id}/policy",
        data={
            "csrf_token": "dashboard-csrf",
            "allowed_providers": "openai",
            "allow_all_providers": "",
            "allowed_endpoints": "/v1/chat/completions",
            "allowed_models": "",
            "reason": "invalid request policy",
        },
    )

    assert response.status_code == 400
    assert "Select at least one allowed model or allow all models for model-backed endpoints." in response.text
    assert 'name="allowed_providers"' in response.text


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


def test_admin_key_detail_shows_template_provenance(monkeypatch) -> None:
    key = AdminKeyDetail(
        **{
            **asdict(_row()),
            "template_id": uuid.uuid4(),
            "template_revision_id": uuid.uuid4(),
        },
        revoked_at=None,
        revoked_reason=None,
        created_by_admin_user_id=uuid.uuid4(),
        last_used_at=None,
        last_quota_reset_at=None,
        quota_reset_count=0,
    )

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
    assert "Template Provenance" in response.text
    assert str(key.template_id) in response.text
    assert str(key.template_revision_id) in response.text
    assert "normal standard gateway key" in response.text


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


def test_calibration_preview_shows_create_template_form(monkeypatch) -> None:
    key = _trusted_detail()

    async def summarize_calibration_key_usage(self, **kwargs):
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
    assert "Create Key Template From This Proposal" in response.text
    assert f'action="/admin/keys/{key.id}/calibration/create-template"' in response.text
    assert 'name="template_name"' in response.text
    assert 'name="confirm_create_template"' in response.text
    assert "does not create participant keys" in response.text


def test_create_template_from_calibration_requires_csrf(monkeypatch) -> None:
    key = _trusted_detail()

    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.post(f"/admin/keys/{key.id}/calibration/create-template")

    assert response.status_code in {400, 403}


def test_create_template_from_calibration_creates_and_redirects(monkeypatch) -> None:
    key = _trusted_detail()
    template_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    audit_id = uuid.uuid4()

    async def summarize_calibration_key_usage(self, **kwargs):
        assert kwargs["gateway_key_id"] == key.id
        assert kwargs["multiplier"] == Decimal("2")
        return _calibration_preview(key.id)

    async def create_from_calibration_proposal(self, **kwargs):
        assert kwargs["name"] == "Workshop template"
        assert kwargs["reason"] == "Reviewed"
        assert kwargs["confirm_create_template"] is True
        return SimpleNamespace(
            template=SimpleNamespace(id=template_id, name="Workshop template"),
            revision=SimpleNamespace(id=revision_id, revision_number=1),
            audit_log=SimpleNamespace(id=audit_id),
        )

    monkeypatch.setattr(
        "slaif_gateway.services.calibration_summary_service.CalibrationSummaryService.summarize_calibration_key_usage",
        summarize_calibration_key_usage,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.key_template_service.KeyTemplateService.create_from_calibration_proposal",
        create_from_calibration_proposal,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        lambda self, admin_session, csrf_token: csrf_token == "dashboard-csrf",
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{key.id}/calibration/create-template",
        data={
            "csrf_token": "dashboard-csrf",
            "multiplier": "2",
            "template_name": "Workshop template",
            "confirm_create_template": "true",
            "reason": "Reviewed",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/templates/{template_id}?message=template_created"


def test_template_pages_require_login() -> None:
    client = TestClient(_app())

    list_response = client.get("/admin/templates", follow_redirects=False)
    detail_response = client.get(f"/admin/templates/{uuid.uuid4()}", follow_redirects=False)

    assert list_response.status_code in {302, 303}
    assert detail_response.status_code in {302, 303}


def test_template_detail_page_shows_safe_metadata(monkeypatch) -> None:
    template_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    revision = SimpleNamespace(
        id=revision_id,
        revision_number=1,
        source_type="calibration_proposal",
        source_calibration_gateway_key_id=uuid.uuid4(),
        source_time_window_start=datetime.now(UTC),
        source_time_window_end=datetime.now(UTC),
        source_multiplier=Decimal("2"),
        created_audit_log_id=uuid.uuid4(),
        allowed_endpoints=["/v1/chat/completions"],
        allowed_models=["gpt-4.1-mini"],
        allowed_providers=["openai"],
        allowed_hosted_capabilities=[],
        hosted_capabilities_requiring_review=["web_search_options"],
        request_limit_total=2,
        token_limit_total=22,
        input_token_limit_total=10,
        output_token_limit_total=12,
        reasoning_token_limit_total=None,
        cost_limit_eur=Decimal("0.002000000"),
        max_total_tokens_per_request=22,
        max_single_request_cost_eur=Decimal("0.002000000"),
        validity_days_default=None,
        email_delivery_mode_default=None,
        template_snapshot={
            "warnings": ["review hosted capabilities"],
            "proposal": {"assumptions": ["safe metadata only"]},
        },
    )
    template = SimpleNamespace(
        id=template_id,
        name="Workshop template",
        description="Reviewed proposal",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        current_revision_id=revision_id,
        revisions=[revision],
    )

    async def get_template_for_admin_detail(self, parsed_template_id):
        assert parsed_template_id == template_id
        return template

    monkeypatch.setattr(
        "slaif_gateway.db.repositories.key_templates.KeyTemplatesRepository.get_template_for_admin_detail",
        get_template_for_admin_detail,
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(f"/admin/templates/{template_id}")

    assert response.status_code == 200
    assert "Workshop template" in response.text
    assert "Single-Key Creation Only" in response.text
    assert "gpt-4.1-mini" in response.text
    assert "web_search_options" in response.text
    assert "Chat Completions streaming live-burn" in response.text
    assert "Chat live-burn: on" in response.text
    assert "prompt text" not in response.text
    assert "sk-live" not in response.text


def test_template_detail_page_shows_create_one_key_form(monkeypatch) -> None:
    template_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    revision = SimpleNamespace(
        id=revision_id,
        revision_number=1,
        source_type="calibration_proposal",
        source_calibration_gateway_key_id=uuid.uuid4(),
        source_time_window_start=None,
        source_time_window_end=None,
        source_multiplier=Decimal("2"),
        created_audit_log_id=uuid.uuid4(),
        allowed_endpoints=["/v1/chat/completions"],
        allowed_models=["gpt-4.1-mini"],
        allowed_providers=["openai"],
        allowed_hosted_capabilities=[],
        hosted_capabilities_requiring_review=[],
        request_limit_total=2,
        token_limit_total=22,
        input_token_limit_total=None,
        output_token_limit_total=None,
        reasoning_token_limit_total=None,
        cost_limit_eur=Decimal("0.002000000"),
        max_input_tokens_per_request=None,
        max_output_tokens_per_request=None,
        max_total_tokens_per_request=None,
        max_single_request_cost_eur=None,
        rate_limit_policy={},
        validity_days_default=7,
        email_delivery_mode_default="none",
        template_snapshot={},
    )
    template = SimpleNamespace(
        id=template_id,
        name="Workshop template",
        description=None,
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        current_revision_id=revision_id,
        revisions=[revision],
    )
    owner = SimpleNamespace(
        id=owner_id,
        display_name="Ada Lovelace",
        email="ada@example.org",
        institution_name=None,
    )

    async def get_template_for_admin_detail(self, parsed_template_id):
        return template

    async def load_options(request):
        return {"owners": [owner], "cohorts": []}

    monkeypatch.setattr(
        "slaif_gateway.db.repositories.key_templates.KeyTemplatesRepository.get_template_for_admin_detail",
        get_template_for_admin_detail,
    )
    monkeypatch.setattr("slaif_gateway.api.admin._load_key_create_form_options_or_empty", load_options)
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.get(f"/admin/templates/{template_id}")

    assert response.status_code == 200
    assert "Create One Key From This Template Revision" in response.text
    assert f'action="/admin/templates/{template_id}/revisions/{revision_id}/create-key"' in response.text
    assert 'name="owner_id"' in response.text
    assert str(owner_id) in response.text
    assert 'name="confirm_create_key_from_template"' in response.text
    assert "Bulk creation from templates is future work" in response.text


def test_create_key_from_template_requires_csrf(monkeypatch) -> None:
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.post(f"/admin/templates/{uuid.uuid4()}/revisions/{uuid.uuid4()}/create-key")

    assert response.status_code in {400, 403}


def test_create_key_from_template_creates_one_key_result(monkeypatch) -> None:
    template_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    gateway_key_id = uuid.uuid4()
    now = datetime.now(UTC)
    revision = SimpleNamespace(
        id=revision_id,
        revision_number=1,
        allowed_models=["gpt-4.1-mini"],
        allowed_endpoints=["/v1/chat/completions"],
        allowed_providers=["openai"],
        allowed_hosted_capabilities=[],
        hosted_capabilities_requiring_review=[],
        request_limit_total=2,
        token_limit_total=22,
        cost_limit_eur=Decimal("0.002000000"),
        rate_limit_policy={},
        validity_days_default=7,
        email_delivery_mode_default="none",
    )
    template = SimpleNamespace(
        id=template_id,
        name="Workshop template",
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
        current_revision_id=revision_id,
        revisions=[revision],
    )
    owner = SimpleNamespace(
        id=owner_id,
        name="Ada",
        surname="Lovelace",
        email="ada@example.org",
    )

    async def load_template(request, parsed_template_id):
        assert parsed_template_id == template_id
        return template

    async def load_options(request):
        return {"owners": [], "cohorts": []}

    class FakeOwners:
        async def get_owner_by_id(self, parsed_owner_id):
            assert parsed_owner_id == owner_id
            return owner

    class FakeCohorts:
        async def get_cohort_by_id(self, parsed_cohort_id):
            return None

    class FakeTemplateService:
        async def create_key_from_revision(self, **kwargs):
            assert kwargs["template_revision_id"] == revision_id
            assert kwargs["owner_id"] == owner_id
            assert kwargs["reason"] == "Reviewed"
            assert kwargs["confirm_create_key_from_template"] is True
            created = CreatedGatewayKey(
                gateway_key_id=gateway_key_id,
                owner_id=owner_id,
                public_key_id="templated",
                display_prefix="sk-slaif-templated",
                plaintext_key="sk-slaif-templated.once-only",
                one_time_secret_id=uuid.uuid4(),
                valid_from=now,
                valid_until=now + timedelta(days=7),
                key_purpose="standard",
                capability_policy_mode="standard",
                template_id=template_id,
                template_revision_id=revision_id,
            )
            return SimpleNamespace(
                created_key=created,
                template=template,
                revision=revision,
                audit_log=SimpleNamespace(id=uuid.uuid4()),
            )

    class FakeEmailDelivery:
        pass

    @asynccontextmanager
    async def fake_runtime(request):
        yield FakeOwners(), FakeCohorts(), FakeTemplateService(), FakeEmailDelivery()

    async def fake_email_delivery(*args, **kwargs):
        return None

    monkeypatch.setattr("slaif_gateway.api.admin._load_template_for_render", load_template)
    monkeypatch.setattr("slaif_gateway.api.admin._load_key_create_form_options_or_empty", load_options)
    monkeypatch.setattr("slaif_gateway.api.admin._admin_template_key_creation_runtime_scope", fake_runtime)
    monkeypatch.setattr(
        "slaif_gateway.api.admin._handle_admin_key_email_delivery_in_transaction",
        fake_email_delivery,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        lambda self, admin_session, csrf_token: csrf_token == "dashboard-csrf",
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.post(
        f"/admin/templates/{template_id}/revisions/{revision_id}/create-key",
        data={
            "csrf_token": "dashboard-csrf",
            "owner_id": str(owner_id),
            "valid_days": "7",
            "email_delivery_mode": "none",
            "confirm_create_key_from_template": "true",
            "reason": "Reviewed",
        },
    )

    assert response.status_code == 200
    assert "Gateway Key Created" in response.text
    assert "sk-slaif-templated.once-only" in response.text
    assert "Created from immutable key template revision" in response.text
    assert "Chat live-burn: on" in response.text
    assert str(template_id) in response.text
    assert str(revision_id) in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text


def test_create_key_from_template_safe_error_for_hosted_review(monkeypatch) -> None:
    template_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    revision = SimpleNamespace(
        id=revision_id,
        revision_number=1,
        source_type="calibration_proposal",
        source_calibration_gateway_key_id=None,
        source_time_window_start=None,
        source_time_window_end=None,
        source_multiplier=None,
        created_audit_log_id=None,
        allowed_endpoints=["/v1/chat/completions"],
        allowed_models=["gpt-4.1-mini"],
        allowed_providers=["openai"],
        allowed_hosted_capabilities=[],
        hosted_capabilities_requiring_review=["web_search_options"],
        request_limit_total=2,
        token_limit_total=22,
        input_token_limit_total=None,
        output_token_limit_total=None,
        reasoning_token_limit_total=None,
        cost_limit_eur=None,
        max_total_tokens_per_request=None,
        max_single_request_cost_eur=None,
        rate_limit_policy={},
        validity_days_default=7,
        email_delivery_mode_default="none",
        template_snapshot={},
    )
    template = SimpleNamespace(
        id=template_id,
        name="Hosted review template",
        description=None,
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        current_revision_id=revision_id,
        revisions=[revision],
    )

    async def load_template(request, parsed_template_id):
        return template

    async def load_options(request):
        return {"owners": [], "cohorts": []}

    @asynccontextmanager
    async def fake_runtime(request):
        class FakeOwners:
            async def get_owner_by_id(self, parsed_owner_id):
                return SimpleNamespace(id=parsed_owner_id)

        class FakeCohorts:
            pass

        class FakeTemplateService:
            async def create_key_from_revision(self, **kwargs):
                from slaif_gateway.services.key_template_service import KeyTemplateError

                raise KeyTemplateError("This template contains hosted capabilities that require review.")

        yield FakeOwners(), FakeCohorts(), FakeTemplateService(), object()

    monkeypatch.setattr("slaif_gateway.api.admin._load_template_for_render", load_template)
    monkeypatch.setattr("slaif_gateway.api.admin._load_key_create_form_options_or_empty", load_options)
    monkeypatch.setattr("slaif_gateway.api.admin._admin_template_key_creation_runtime_scope", fake_runtime)
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        lambda self, admin_session, csrf_token: csrf_token == "dashboard-csrf",
    )
    client = TestClient(_app())
    _login(monkeypatch, client)

    response = client.post(
        f"/admin/templates/{template_id}/revisions/{revision_id}/create-key",
        data={
            "csrf_token": "dashboard-csrf",
            "owner_id": str(uuid.uuid4()),
            "valid_days": "7",
            "confirm_create_key_from_template": "true",
            "reason": "Reviewed",
        },
    )

    assert response.status_code == 400
    assert "hosted capabilities" in response.text
    assert "sk-provider-secret-placeholder" not in response.text
    assert "token_hash" not in response.text


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

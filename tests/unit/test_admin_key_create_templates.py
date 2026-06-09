import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.schemas.keys import CreatedGatewayKey
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    KEY_PURPOSE_TRUSTED_CALIBRATION,
)

from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions
from tests.unit.test_admin_key_create_routes import _cohort, _owner, _patch_options


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_create_form_template_includes_csrf_and_no_secret_fields(monkeypatch) -> None:
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="admin-session-secret-that-must-not-render",
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )
    _patch_options(monkeypatch)
    client = TestClient(_app(settings))
    _login_for_actions(monkeypatch, client)

    async def refresh_csrf_token(self, **kwargs):
        return "rendered-create-csrf"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )

    html = client.get("/admin/keys/create").text

    assert 'method="post" action="/admin/keys/create"' in html
    assert 'name="csrf_token" value="rendered-create-csrf"' in html
    assert 'name="owner_id"' in html
    assert 'data-policy-selector-surface' in html
    assert "Available enabled providers" in html
    assert "Available implemented endpoints" in html
    assert "Available route-backed model candidates" in html
    assert 'name="allowed_providers"' in html
    assert 'name="allow_all_providers" value="true" checked' in html
    assert 'name="allowed_models"' in html
    assert 'name="allowed_endpoints"' in html
    assert "Advanced manual policy strings" in html
    assert "Trusted Calibration Key" in html
    assert 'name="trusted_calibration" value="true"' in html
    assert 'name="confirm_trusted_calibration" value="true"' in html
    assert str(settings.TRUSTED_CALIBRATION_MAX_REQUESTS) in html
    assert str(settings.TRUSTED_CALIBRATION_MAX_VALID_DAYS) in html
    assert "key plaintext is shown once" not in html.lower()
    assert "None - show key once in browser" in html
    assert "Email delivery mode" in html
    assert "Send-now and enqueue suppress browser plaintext display" in html
    assert "Chat Completions streaming live-burn monitoring" in html
    assert 'name="chat_streaming_live_burn_enabled" value="true" checked' in html
    assert 'name="chat_streaming_live_burn_cost_margin_eur" value="0"' in html
    assert 'name="chat_streaming_live_burn_token_margin" value="0"' in html
    assert "Live estimates are provisional, not invoice-grade" in html
    assert "Positive margin stops streams early" in html
    assert "create-chat-streaming-live-burn-fields" in html
    assert "data-streaming-live-burn-surface" in html
    assert 'src="/admin/static/js/policy-selector.js"' in html
    assert 'src="/admin/static/js/streaming-live-burn.js"' in html
    assert "https://cdn" not in html.lower()
    assert "react" not in html.lower()
    assert "vue" not in html.lower()
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert settings.OPENAI_UPSTREAM_API_KEY not in html
    assert settings.OPENROUTER_API_KEY not in html
    assert "password_hash" not in html
    assert "session-token-must-not-render" not in html
    assert "bulk" not in html.lower()
    assert "create-and-email" not in html.lower()


def test_chat_live_burn_static_controls_are_local_and_scoped() -> None:
    policy_js = (
        REPO_ROOT
        / "app"
        / "slaif_gateway"
        / "web"
        / "static"
        / "js"
        / "policy-selector.js"
    ).read_text()
    js = (
        REPO_ROOT
        / "app"
        / "slaif_gateway"
        / "web"
        / "static"
        / "js"
        / "streaming-live-burn.js"
    ).read_text()
    css = (
        REPO_ROOT
        / "app"
        / "slaif_gateway"
        / "web"
        / "static"
        / "css"
        / "admin.css"
    ).read_text()

    assert "data-streaming-live-burn-surface" in js
    assert "data-streaming-live-burn-margin-fields" in js
    assert "input.disabled = !enabled" in js
    assert "cost_limit_eur" not in js
    assert "rate_limit" not in js
    assert "http://" not in js
    assert "https://" not in js
    assert "React" not in js
    assert "Vue" not in js
    assert "data-policy-selector-surface" in policy_js
    assert "data-policy-toggle" in policy_js
    assert "data-policy-manual" in policy_js
    assert "fetch(" not in policy_js
    assert "axios" not in policy_js.lower()
    assert "React" not in policy_js
    assert "Vue" not in policy_js
    assert "https://" not in policy_js
    assert ".live-burn-fields-disabled" in css
    assert ".policy-selector-grid" in css


def test_create_result_template_shows_plaintext_once_without_email_action(monkeypatch) -> None:
    _patch_options(monkeypatch)
    owner_id = uuid.uuid4()
    owner = _owner(owner_id)
    cohort = _cohort()
    plaintext_key = "sk-slaif-newpublic.once-only-created"

    async def get_owner_by_id(self, requested_owner_id):
        return owner

    async def get_cohort_by_id(self, requested_cohort_id):
        return cohort

    async def create_gateway_key(self, payload):
        now = datetime.now(UTC)
        return CreatedGatewayKey(
            gateway_key_id=uuid.uuid4(),
            owner_id=owner_id,
            public_key_id="newpublic",
            display_prefix="sk-slaif-newpublic",
            plaintext_key=plaintext_key,
            one_time_secret_id=uuid.uuid4(),
            valid_from=now,
            valid_until=now + timedelta(days=30),
            rate_limit_policy=None,
        )

    monkeypatch.setattr("slaif_gateway.db.repositories.owners.OwnersRepository.get_owner_by_id", get_owner_by_id)
    monkeypatch.setattr("slaif_gateway.db.repositories.cohorts.CohortsRepository.get_cohort_by_id", get_cohort_by_id)
    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.create_gateway_key",
        create_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data={
            "csrf_token": "dashboard-csrf",
            "owner_id": str(owner_id),
            "cohort_id": str(cohort.id),
            "valid_days": "30",
            "allow_all_models": "true",
            "allow_all_endpoints": "true",
            "reason": "new workshop key",
        },
    )
    html = response.text

    assert response.status_code == 200
    assert html.count(plaintext_key) == 1
    assert "Copy this key now" in html
    assert "rotate the key" in html
    assert "No email delivery row was created" in html
    assert "no Celery task was queued" in html
    assert "Chat streaming live-burn" in html
    assert "Chat live-burn: on" in html
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert "provider key" not in html.lower()
    assert "password_hash" not in html
    assert "session-token" not in html
    assert "one_time_secret" not in html
    assert "email action" not in html.lower()


def test_create_result_template_marks_trusted_calibration_key(monkeypatch) -> None:
    _patch_options(monkeypatch)
    owner_id = uuid.uuid4()
    owner = _owner(owner_id)
    plaintext_key = "sk-slaif-calibration.once-only-created"

    async def get_owner_by_id(self, requested_owner_id):
        return owner

    async def create_gateway_key(self, payload):
        now = datetime.now(UTC)
        return CreatedGatewayKey(
            gateway_key_id=uuid.uuid4(),
            owner_id=owner_id,
            public_key_id="calpublic",
            display_prefix="sk-slaif-calpublic",
            plaintext_key=plaintext_key,
            one_time_secret_id=uuid.uuid4(),
            valid_from=now,
            valid_until=now + timedelta(days=7),
            rate_limit_policy=None,
            key_purpose=KEY_PURPOSE_TRUSTED_CALIBRATION,
            capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
        )

    monkeypatch.setattr("slaif_gateway.db.repositories.owners.OwnersRepository.get_owner_by_id", get_owner_by_id)
    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.create_gateway_key",
        create_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data={
            "csrf_token": "dashboard-csrf",
            "owner_id": str(owner_id),
            "valid_days": "7",
            "request_limit_total": "5",
            "trusted_calibration": "true",
            "confirm_trusted_calibration": "true",
            "reason": "trusted discovery",
        },
    )

    html = response.text
    assert response.status_code == 200
    assert html.count(plaintext_key) == 1
    assert "Trusted calibration key" in html
    assert "broad discovery policy" in html
    assert "trusted_calibration_discovery" in html
    assert "Do not issue to participants" in html

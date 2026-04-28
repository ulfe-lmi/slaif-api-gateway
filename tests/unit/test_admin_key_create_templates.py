import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.schemas.keys import CreatedGatewayKey

from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions
from tests.unit.test_admin_key_create_routes import _cohort, _owner, _patch_options


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
    assert 'name="allowed_models"' in html
    assert 'name="allowed_endpoints"' in html
    assert "key plaintext is shown once" not in html.lower()
    assert "plaintext key is shown once" in html
    assert "does not email the key" in html
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert settings.OPENAI_UPSTREAM_API_KEY not in html
    assert settings.OPENROUTER_API_KEY not in html
    assert "password_hash" not in html
    assert "session-token-must-not-render" not in html
    assert "bulk" not in html.lower()
    assert "create-and-email" not in html.lower()


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
            "reason": "new workshop key",
        },
    )
    html = response.text

    assert response.status_code == 200
    assert html.count(plaintext_key) == 1
    assert "Copy this key now" in html
    assert "rotate the key" in html
    assert "email delivery row" in html
    assert "queue a Celery task" in html
    assert "token_hash" not in html
    assert "encrypted_payload" not in html
    assert "nonce" not in html
    assert "provider key" not in html.lower()
    assert "password_hash" not in html
    assert "session-token" not in html
    assert "one_time_secret" not in html
    assert "email action" not in html.lower()

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import Cohort, Owner
from slaif_gateway.schemas.admin_records import AdminCohortListRow, AdminOwnerListRow
from slaif_gateway.schemas.keys import CreatedGatewayKey
from slaif_gateway.services.email_errors import EmailError
from slaif_gateway.services.key_errors import InvalidGatewayKeyPolicyError
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    KEY_PURPOSE_TRUSTED_CALIBRATION,
)
from slaif_gateway.services.key_policy_validation import GatewayKeyPolicy

from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions


def _owner(owner_id: uuid.UUID | None = None) -> Owner:
    return Owner(
        id=owner_id or uuid.uuid4(),
        name="Ada",
        surname="Lovelace",
        email="ada@example.org",
    )


def _cohort(cohort_id: uuid.UUID | None = None) -> Cohort:
    return Cohort(id=cohort_id or uuid.uuid4(), name="Spring Cohort")


def _created_key(
    *,
    gateway_key_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    plaintext_key: str = "sk-slaif-newpublic.once-only-created",
    key_purpose: str = "standard",
    capability_policy_mode: str = "standard",
) -> CreatedGatewayKey:
    now = datetime.now(UTC)
    return CreatedGatewayKey(
        gateway_key_id=gateway_key_id or uuid.uuid4(),
        owner_id=owner_id or uuid.uuid4(),
        public_key_id="newpublic",
        display_prefix="sk-slaif-newpublic",
        plaintext_key=plaintext_key,
        one_time_secret_id=uuid.uuid4(),
        valid_from=now,
        valid_until=now + timedelta(days=30),
        rate_limit_policy={"requests_per_minute": 60},
        key_purpose=key_purpose,
        capability_policy_mode=capability_policy_mode,
    )


async def _fake_options(request):
    owner_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    cohort_id = uuid.UUID("22222222-2222-4222-8222-222222222222")
    now = datetime.now(UTC)
    return {
        "owners": [
            AdminOwnerListRow(
                id=owner_id,
                name="Ada",
                surname="Lovelace",
                display_name="Ada Lovelace",
                email="ada@example.org",
                institution_id=None,
                institution_name=None,
                is_active=True,
                key_count=0,
                active_key_count=0,
                created_at=now,
                updated_at=now,
            )
        ],
        "cohorts": [
            AdminCohortListRow(
                id=cohort_id,
                name="Spring Cohort",
                description=None,
                starts_at=None,
                ends_at=None,
                owner_count=0,
                key_count=0,
                active_key_count=0,
                created_at=now,
                updated_at=now,
            )
        ],
        "policy_catalog": {
            "provider_choices": [
                SimpleNamespace(
                    value="openai",
                    display_name="OpenAI",
                    kind="openai_compatible",
                    label="OpenAI | openai | openai_compatible",
                ),
                SimpleNamespace(
                    value="openrouter",
                    display_name="OpenRouter",
                    kind="openai_compatible",
                    label="OpenRouter | openrouter | openai_compatible",
                ),
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
            "model_choices": [
                SimpleNamespace(
                    route_key="openai|/v1/chat/completions|gpt-4.1-mini|exact|gpt-4.1-mini",
                    token="gpt-4.1-mini",
                    provider="openai",
                    provider_label="OpenAI",
                    endpoint="/v1/chat/completions",
                    match_type="exact",
                    upstream_model="gpt-4.1-mini",
                    label="gpt-4.1-mini | openai | /v1/chat/completions | exact | gpt-4.1-mini | visible in /v1/models | streaming",
                    group_label="/v1/chat/completions | OpenAI",
                    visible_in_models=True,
                    supports_streaming=True,
                    capability_summary=None,
                ),
                SimpleNamespace(
                    route_key="openrouter|/v1/chat/completions|gpt-4o-*|glob|openrouter/gpt-4o",
                    token="gpt-4o-*",
                    provider="openrouter",
                    provider_label="OpenRouter",
                    endpoint="/v1/chat/completions",
                    match_type="glob",
                    upstream_model="openrouter/gpt-4o",
                    label="gpt-4o-* | openrouter | /v1/chat/completions | glob | openrouter/gpt-4o | hidden from /v1/models | streaming",
                    group_label="/v1/chat/completions | OpenRouter",
                    visible_in_models=False,
                    supports_streaming=True,
                    capability_summary=None,
                ),
            ],
            "model_choices_by_group": {
                "/v1/chat/completions | OpenAI": [
                    SimpleNamespace(
                        route_key="openai|/v1/chat/completions|gpt-4.1-mini|exact|gpt-4.1-mini",
                        token="gpt-4.1-mini",
                        provider="openai",
                        endpoint="/v1/chat/completions",
                        label="gpt-4.1-mini | openai | /v1/chat/completions | exact | gpt-4.1-mini | visible in /v1/models | streaming",
                        visible_in_models=True,
                        supports_streaming=True,
                    )
                ],
                "/v1/chat/completions | OpenRouter": [
                    SimpleNamespace(
                        route_key="openrouter|/v1/chat/completions|gpt-4o-*|glob|openrouter/gpt-4o",
                        token="gpt-4o-*",
                        provider="openrouter",
                        endpoint="/v1/chat/completions",
                        label="gpt-4o-* | openrouter | /v1/chat/completions | glob | openrouter/gpt-4o | hidden from /v1/models | streaming",
                        visible_in_models=False,
                        supports_streaming=True,
                    )
                ],
            },
            "enabled_provider_values": ("openai", "openrouter"),
        },
    }


def _patch_options(monkeypatch) -> None:
    monkeypatch.setattr("slaif_gateway.api.admin._load_key_create_form_options", _fake_options)
    monkeypatch.setattr(
        "slaif_gateway.api.admin._validate_admin_request_policy",
        _validate_admin_request_policy,
    )


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


def test_unauthenticated_create_form_redirects_to_login() -> None:
    client = TestClient(_app())

    response = client.get("/admin/keys/create", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_authenticated_create_form_renders_safe_fields(monkeypatch) -> None:
    _patch_options(monkeypatch)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    async def refresh_csrf_token(self, **kwargs):
        return "rendered-create-csrf"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )

    response = client.get("/admin/keys/create")

    assert response.status_code == 200
    assert 'action="/admin/keys/create"' in response.text
    assert 'name="csrf_token" value="rendered-create-csrf"' in response.text
    assert 'name="owner_id"' in response.text
    assert "Ada Lovelace / ada@example.org" in response.text
    assert 'name="valid_until"' in response.text
    assert 'name="valid_days"' in response.text
    assert 'name="cost_limit_eur"' in response.text
    assert 'data-policy-selector-surface' in response.text
    assert "Available enabled providers" in response.text
    assert "Available implemented endpoints" in response.text
    assert "Available route-backed model candidates" in response.text
    assert "Filtered by the current provider and model-backed endpoint selection when JavaScript is enabled." in response.text
    assert "Catalog-only endpoints and model-backed endpoints are kept separate here on purpose." in response.text
    assert 'name="allow_all_providers" value="true"' in response.text
    assert 'name="allowed_providers"' in response.text
    assert 'name="allowed_models"' in response.text
    assert 'name="allow_all_models" value="true"' in response.text
    assert 'name="allowed_endpoints"' in response.text
    assert 'name="allow_all_endpoints" value="true"' in response.text
    assert 'src="/admin/static/js/policy-selector.js"' in response.text
    assert "Add selected -&gt;" in response.text
    assert "OpenAI | openai | openai_compatible" in response.text
    assert "gpt-4o-* | openrouter | /v1/chat/completions | glob" in response.text
    assert "hidden from /v1/models" in response.text
    assert 'name="rate_limit_requests_per_minute"' in response.text
    assert "Email delivery mode" in response.text
    assert "Send-now and enqueue suppress browser plaintext display" in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "sk-provider-secret-placeholder" not in response.text
    assert "session-token-must-not-render" not in response.text


def test_unauthenticated_create_post_redirects_to_login() -> None:
    client = TestClient(_app())

    response = client.post("/admin/keys/create", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_create_post_without_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.create_gateway_key",
        create_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post("/admin/keys/create")

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_create_post_with_invalid_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.create_gateway_key",
        create_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post("/admin/keys/create", data={"csrf_token": "wrong"})

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_create_requires_owner_before_service_call(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.create_gateway_key",
        create_gateway_key,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data={"csrf_token": "dashboard-csrf", "valid_days": "30", "reason": "workshop"},
    )

    assert response.status_code == 400
    assert "owner_id is required" in response.text
    assert called is False


def test_create_rejects_invalid_owner_uuid_before_service_call(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

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
            "owner_id": "not-a-uuid",
            "valid_days": "30",
            "reason": "workshop",
        },
    )

    assert response.status_code == 400
    assert "owner_id must be a valid UUID" in response.text
    assert called is False


def test_create_rejects_invalid_datetime_before_service_call(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

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
            "owner_id": str(uuid.uuid4()),
            "valid_until": "not-a-date",
            "reason": "workshop",
        },
    )

    assert response.status_code == 400
    assert "Enter a valid key validity window" in response.text
    assert called is False


def test_create_rejects_nonpositive_limits_before_service_call(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

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
            "owner_id": str(uuid.uuid4()),
            "valid_days": "30",
            "cost_limit_eur": "0",
            "reason": "workshop",
        },
    )

    assert response.status_code == 400
    assert "Enter valid positive quota and rate-limit values." in response.text
    assert called is False


def test_create_calls_key_service_and_renders_one_time_plaintext(monkeypatch) -> None:
    _patch_options(monkeypatch)
    owner_id = uuid.uuid4()
    cohort_id = uuid.uuid4()
    owner = _owner(owner_id)
    cohort = _cohort(cohort_id)
    plaintext_key = "sk-slaif-newpublic.once-only-created"
    seen = {}

    async def get_owner_by_id(self, requested_owner_id):
        assert requested_owner_id == owner_id
        return owner

    async def get_cohort_by_id(self, requested_cohort_id):
        assert requested_cohort_id == cohort_id
        return cohort

    async def create_gateway_key(self, payload):
        seen["payload"] = payload
        return _created_key(owner_id=owner_id, plaintext_key=plaintext_key)

    monkeypatch.setattr("slaif_gateway.db.repositories.owners.OwnersRepository.get_owner_by_id", get_owner_by_id)
    monkeypatch.setattr("slaif_gateway.db.repositories.cohorts.CohortsRepository.get_cohort_by_id", get_cohort_by_id)
    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.create_gateway_key",
        create_gateway_key,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data={
            "csrf_token": "dashboard-csrf",
            "owner_id": str(owner_id),
            "cohort_id": str(cohort_id),
            "valid_from": "2026-05-01T09:00:00+00:00",
            "valid_until": "2026-06-01T09:00:00+00:00",
            "cost_limit_eur": "12.50",
            "token_limit_total": "1000",
            "request_limit_total": "100",
            "allowed_providers": "openai",
            "allow_all_providers": "",
            "allowed_models": "gpt-4.1-mini\nopenrouter/model, gpt-4o-mini",
            "allowed_endpoints": "/v1/chat/completions, /v1/models",
            "rate_limit_requests_per_minute": "60",
            "rate_limit_tokens_per_minute": "12000",
            "rate_limit_concurrent_requests": "3",
            "rate_limit_window_seconds": "30",
            "chat_streaming_live_burn_enabled": "true",
            "reason": "new workshop key",
        },
    )

    assert response.status_code == 200
    assert response.text.count(plaintext_key) == 1
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
    assert response.headers["Pragma"] == "no-cache"
    assert response.url.path == "/admin/keys/create"
    assert plaintext_key not in response.headers.get("set-cookie", "")
    assert "Email delivery is pending" not in response.text
    assert "celery_task_id" not in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text
    assert "provider-secret" not in response.text
    assert "session-token" not in response.text

    payload = seen["payload"]
    assert payload.owner_id == owner_id
    assert payload.cohort_id == cohort_id
    assert payload.created_by_admin_id == admin_user.id
    assert payload.note == "new workshop key"
    assert payload.cost_limit_eur == Decimal("12.50")
    assert payload.token_limit_total == 1000
    assert payload.request_limit_total == 100
    assert payload.allowed_providers == ["openai"]
    assert payload.allowed_models == ["gpt-4.1-mini", "openrouter/model", "gpt-4o-mini"]
    assert payload.allowed_endpoints == ["/v1/chat/completions", "/v1/models"]
    assert payload.allow_all_models is False
    assert payload.allow_all_endpoints is False
    assert payload.rate_limit_policy == {
        "requests_per_minute": 60,
        "tokens_per_minute": 12000,
        "max_concurrent_requests": 3,
        "window_seconds": 30,
    }
    assert payload.chat_streaming_live_burn_policy == {
        "version": 1,
        "enabled": True,
        "cost_margin_eur": "0.000000000",
        "token_margin": 0,
    }
    assert payload.key_purpose == "standard"
    assert payload.capability_policy_mode == "standard"


def test_create_selector_round_trips_selected_policy_values_on_validation_error(monkeypatch) -> None:
    _patch_options(monkeypatch)
    owner_id = uuid.uuid4()
    owner = _owner(owner_id)

    async def get_owner_by_id(self, requested_owner_id):
        assert requested_owner_id == owner_id
        return owner

    async def create_gateway_key(self, payload):
        raise InvalidGatewayKeyPolicyError("Select at least one allowed model.")

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
            "valid_days": "30",
            "allowed_providers": "openai",
            "allow_all_providers": "",
            "allowed_endpoints": "/v1/chat/completions",
            "allowed_models": "",
            "reason": "invalid request policy",
        },
    )

    assert response.status_code == 400
    assert "Select at least one allowed model" in response.text
    assert '<option value="openai">OpenAI | openai | openai_compatible</option>' in response.text
    assert '<option value="/v1/chat/completions">/v1/chat/completions | Chat Completions</option>' in response.text


def test_create_rejects_model_backed_endpoint_without_models_before_service(monkeypatch) -> None:
    _patch_options(monkeypatch)
    owner_id = uuid.uuid4()

    async def reject_policy(*args, **kwargs):
        raise InvalidGatewayKeyPolicyError(
            "Select at least one allowed model or allow all models for model-backed endpoints."
        )

    async def create_gateway_key(self, payload):
        raise AssertionError("create_gateway_key should not be called for invalid policy")

    monkeypatch.setattr(
        "slaif_gateway.api.admin._validate_admin_request_policy",
        reject_policy,
    )
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
            "valid_days": "30",
            "allowed_providers": "openai",
            "allow_all_providers": "",
            "allowed_endpoints": "/v1/chat/completions",
            "allowed_models": "",
            "reason": "invalid request policy",
        },
    )

    assert response.status_code == 400
    assert "Select at least one allowed model or allow all models for model-backed endpoints." in response.text


def test_create_unchecked_chat_live_burn_checkbox_disables_policy(monkeypatch) -> None:
    _patch_options(monkeypatch)
    owner_id = uuid.uuid4()
    owner = _owner(owner_id)
    seen = {}

    async def get_owner_by_id(self, requested_owner_id):
        assert requested_owner_id == owner_id
        return owner

    async def create_gateway_key(self, payload):
        seen["payload"] = payload
        return _created_key(owner_id=owner_id)

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
            "valid_days": "30",
            "allow_all_providers": "true",
            "allow_all_models": "true",
            "allow_all_endpoints": "true",
            "reason": "disable live burn",
        },
    )

    assert response.status_code == 200
    assert seen["payload"].chat_streaming_live_burn_policy == {
        "version": 1,
        "enabled": False,
        "cost_margin_eur": "0.000000000",
        "token_margin": 0,
    }


def test_create_trusted_calibration_calls_key_service_and_renders_warning(monkeypatch) -> None:
    _patch_options(monkeypatch)
    owner_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    owner = _owner(owner_id)
    plaintext_key = "sk-slaif-calibration.once-only-created"
    seen = {}

    async def get_owner_by_id(self, requested_owner_id):
        assert requested_owner_id == owner_id
        return owner

    async def create_gateway_key(self, payload):
        seen["payload"] = payload
        return _created_key(
            owner_id=owner_id,
            plaintext_key=plaintext_key,
            key_purpose=KEY_PURPOSE_TRUSTED_CALIBRATION,
            capability_policy_mode=CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
        )

    monkeypatch.setattr("slaif_gateway.db.repositories.owners.OwnersRepository.get_owner_by_id", get_owner_by_id)
    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.create_gateway_key",
        create_gateway_key,
    )
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="s" * 40,
        TRUSTED_CALIBRATION_MAX_REQUESTS=10,
        TRUSTED_CALIBRATION_MAX_VALID_DAYS=7,
    )
    client = TestClient(_app(settings))
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data={
            "csrf_token": "dashboard-csrf",
            "owner_id": str(owner_id),
            "valid_days": "7",
            "request_limit_total": "10",
            "trusted_calibration": "true",
            "confirm_trusted_calibration": "true",
            "reason": "trusted discovery",
        },
    )

    assert response.status_code == 200
    assert response.text.count(plaintext_key) == 1
    assert "Trusted calibration key" in response.text
    assert "Do not issue to participants" in response.text

    payload = seen["payload"]
    assert payload.created_by_admin_id == admin_user.id
    assert payload.key_purpose == KEY_PURPOSE_TRUSTED_CALIBRATION
    assert payload.capability_policy_mode == CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
    assert payload.confirm_trusted_calibration is True
    assert payload.request_limit_total == 10
    assert payload.note == "trusted discovery"
    assert payload.calibration_metadata["created_from"] == "admin_web"


def test_create_trusted_calibration_fails_without_confirmation(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

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
            "owner_id": str(uuid.uuid4()),
            "valid_days": "7",
            "request_limit_total": "5",
            "trusted_calibration": "true",
            "reason": "trusted discovery",
        },
    )

    assert response.status_code == 400
    assert "Confirm trusted calibration mode" in response.text
    assert called is False


def test_create_trusted_calibration_fails_without_request_limit(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

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
            "owner_id": str(uuid.uuid4()),
            "valid_days": "7",
            "trusted_calibration": "true",
            "confirm_trusted_calibration": "true",
            "reason": "trusted discovery",
        },
    )

    assert response.status_code == 400
    assert "Trusted calibration keys require request_limit_total" in response.text
    assert called is False


def test_create_trusted_calibration_fails_when_request_limit_exceeds_max(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.create_gateway_key",
        create_gateway_key,
    )
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="s" * 40,
        TRUSTED_CALIBRATION_MAX_REQUESTS=3,
    )
    client = TestClient(_app(settings))
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data={
            "csrf_token": "dashboard-csrf",
            "owner_id": str(uuid.uuid4()),
            "valid_days": "7",
            "request_limit_total": "4",
            "trusted_calibration": "true",
            "confirm_trusted_calibration": "true",
            "reason": "trusted discovery",
        },
    )

    assert response.status_code == 400
    assert "Trusted calibration request limit exceeds" in response.text
    assert called is False


def test_create_trusted_calibration_fails_when_validity_exceeds_max(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.create_gateway_key",
        create_gateway_key,
    )
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="s" * 40,
        TRUSTED_CALIBRATION_MAX_VALID_DAYS=2,
    )
    client = TestClient(_app(settings))
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data={
            "csrf_token": "dashboard-csrf",
            "owner_id": str(uuid.uuid4()),
            "valid_days": "3",
            "request_limit_total": "2",
            "trusted_calibration": "true",
            "confirm_trusted_calibration": "true",
            "reason": "trusted discovery",
        },
    )

    assert response.status_code == 400
    assert "Trusted calibration validity exceeds" in response.text
    assert called is False


def test_create_trusted_calibration_rejects_unsafe_email_modes(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.key_service.KeyService.create_gateway_key",
        create_gateway_key,
    )
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="s" * 40,
        ENABLE_EMAIL_DELIVERY=True,
        SMTP_HOST="localhost",
        SMTP_FROM="admin@example.org",
    )
    client = TestClient(_app(settings))
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data={
            "csrf_token": "dashboard-csrf",
            "owner_id": str(uuid.uuid4()),
            "valid_days": "7",
            "request_limit_total": "2",
            "trusted_calibration": "true",
            "confirm_trusted_calibration": "true",
            "email_delivery_mode": "send-now",
            "reason": "trusted discovery",
        },
    )

    assert response.status_code == 400
    assert "may only use none or pending email delivery modes" in response.text
    assert called is False


def test_create_rejects_swapped_model_and_endpoint_values_before_service_call(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

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
            "owner_id": str(uuid.uuid4()),
            "valid_days": "30",
            "allowed_models": "/v1/models\n/v1/chat/completions",
            "allowed_endpoints": "gpt-5.2\ngpt-5.1",
            "reason": "new workshop key",
        },
    )

    assert response.status_code == 400
    assert "Allowed endpoints must be API paths such as /v1/models" in response.text
    assert called is False


def test_create_service_failure_logs_diagnostic_context_and_renders_reference(monkeypatch, capsys) -> None:
    _patch_options(monkeypatch)
    owner_id = uuid.uuid4()
    cohort_id = uuid.uuid4()
    admin_bearer = "Bearer admin-session-token-secret"
    csrf_token = "csrf-token-secret"
    fake_plaintext_key = "sk-slaif-newpublic.once-only-created"
    fake_provider_key = "sk-or-provider-secret-abcdef123456"
    fake_encrypted_payload = "encrypted-payload-secret"
    fake_nonce = "nonce-secret"
    owner = _owner(owner_id)
    cohort = _cohort(cohort_id)
    created = _created_key(owner_id=owner_id, plaintext_key=fake_plaintext_key)

    async def get_owner_by_id(self, requested_owner_id):
        return owner if requested_owner_id == owner_id else None

    async def get_cohort_by_id(self, requested_cohort_id):
        return cohort if requested_cohort_id == cohort_id else None

    async def create_gateway_key(self, payload):
        return created

    async def create_pending_key_email_delivery(self, **kwargs):
        raise EmailError(
            "SMTP failure "
            f"Authorization={admin_bearer} csrf_token={csrf_token} session_token=session-token-secret "
            f"plaintext_key={fake_plaintext_key} provider_key={fake_provider_key} "
            f"encrypted_payload={fake_encrypted_payload} nonce={fake_nonce}"
        )

    monkeypatch.setattr("slaif_gateway.db.repositories.owners.OwnersRepository.get_owner_by_id", get_owner_by_id)
    monkeypatch.setattr("slaif_gateway.db.repositories.cohorts.CohortsRepository.get_cohort_by_id", get_cohort_by_id)
    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.create_gateway_key", create_gateway_key)
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.create_pending_key_email_delivery",
        create_pending_key_email_delivery,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client, valid_csrf=csrf_token)

    response = client.post(
        "/admin/keys/create",
        headers={"Authorization": admin_bearer},
        data={
            "csrf_token": csrf_token,
            "owner_id": str(owner_id),
            "cohort_id": str(cohort_id),
            "valid_days": "30",
            "allow_all_models": "true",
            "allow_all_endpoints": "true",
            "email_delivery_mode": "pending",
            "reason": "new workshop key",
        },
    )

    assert response.status_code == 400
    assert "Gateway key creation failed." in response.text
    assert "Reference ID: " in response.text
    diagnostic_id = response.headers["X-SLAIF-Diagnostic-ID"]
    assert diagnostic_id.startswith("gw-")
    assert diagnostic_id in response.text
    assert fake_plaintext_key not in response.text
    assert fake_provider_key not in response.text
    assert "session-token-secret" not in response.text
    assert fake_encrypted_payload not in response.text
    assert fake_nonce not in response.text

    logs = capsys.readouterr().out.strip().splitlines()
    event = json.loads(logs[-1])
    serialized_event = json.dumps(event)
    assert event["event"] == "admin.key_create.failed"
    assert event["level"] == "warning"
    assert event["diagnostic_id"] == diagnostic_id
    assert event["gateway_request_id"] == diagnostic_id
    assert event["admin_id"] == str(admin_user.id)
    assert event["owner_id"] == str(owner_id)
    assert event["cohort_id"] == str(cohort_id)
    assert event["email_delivery_mode"] == "pending"
    assert event["exception_type"] == "EmailError"
    assert event["error_code"] == "email_error"
    assert fake_plaintext_key not in serialized_event
    assert fake_provider_key not in serialized_event
    assert admin_bearer not in serialized_event
    assert csrf_token not in serialized_event
    assert "session-token-secret" not in serialized_event
    assert fake_encrypted_payload not in serialized_event
    assert fake_nonce not in serialized_event

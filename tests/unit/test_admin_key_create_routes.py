import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.db.models import Cohort, Owner
from slaif_gateway.schemas.admin_records import AdminCohortListRow, AdminOwnerListRow
from slaif_gateway.schemas.keys import CreatedGatewayKey

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
    }


def _patch_options(monkeypatch) -> None:
    monkeypatch.setattr("slaif_gateway.api.admin._load_key_create_form_options", _fake_options)


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
    assert 'name="allowed_models"' in response.text
    assert 'name="rate_limit_requests_per_minute"' in response.text
    assert "dashboard workflow does not email the key" in response.text
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
            "allowed_models": "gpt-4.1-mini\nopenrouter/model, gpt-4o-mini",
            "allowed_endpoints": "/v1/chat/completions, /v1/models",
            "rate_limit_requests_per_minute": "60",
            "rate_limit_tokens_per_minute": "12000",
            "rate_limit_concurrent_requests": "3",
            "rate_limit_window_seconds": "30",
            "reason": "new workshop key",
        },
    )

    assert response.status_code == 200
    assert response.text.count(plaintext_key) == 1
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
    assert response.headers["Pragma"] == "no-cache"
    assert response.url.path == "/admin/keys/create"
    assert plaintext_key not in response.headers.get("set-cookie", "")
    assert "email_delivery" not in response.text
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
    assert payload.allowed_models == ["gpt-4.1-mini", "openrouter/model", "gpt-4o-mini"]
    assert payload.allowed_endpoints == ["/v1/chat/completions", "/v1/models"]
    assert payload.rate_limit_policy == {
        "requests_per_minute": 60,
        "tokens_per_minute": 12000,
        "max_concurrent_requests": 3,
        "window_seconds": 30,
    }

import uuid

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.services.email_delivery_service import PendingKeyEmailResult

from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions
from tests.unit.test_admin_key_create_routes import _created_key, _owner, _patch_options


def _email_settings() -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
        ADMIN_SESSION_SECRET="admin-session-secret-that-must-not-render",
        ENABLE_EMAIL_DELIVERY=True,
        SMTP_HOST="localhost",
        SMTP_FROM="noreply@example.org",
        CELERY_BROKER_URL="redis://localhost:6379/15",
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


def _create_data(owner_id: uuid.UUID, **overrides: str) -> dict[str, str]:
    data = {
        "csrf_token": "dashboard-csrf",
        "owner_id": str(owner_id),
        "valid_days": "30",
        "reason": "new workshop key",
    }
    data.update(overrides)
    return data


def _delivery(
    *,
    gateway_key_id: uuid.UUID,
    owner_id: uuid.UUID,
    one_time_secret_id: uuid.UUID,
    status: str = "pending",
) -> PendingKeyEmailResult:
    return PendingKeyEmailResult(
        email_delivery_id=uuid.uuid4(),
        one_time_secret_id=one_time_secret_id,
        gateway_key_id=gateway_key_id,
        owner_id=owner_id,
        recipient_email="ada@example.org",
        status=status,
        provider_message_id="<message@example.org>" if status == "sent" else None,
    )


def test_create_mode_pending_creates_delivery_and_keeps_plaintext_once(monkeypatch) -> None:
    _patch_options(monkeypatch)
    owner_id = uuid.uuid4()
    owner = _owner(owner_id)
    created = _created_key(owner_id=owner_id)
    seen: dict[str, object] = {}

    async def get_owner_by_id(self, requested_owner_id):
        return owner if requested_owner_id == owner_id else None

    async def create_gateway_key(self, payload):
        seen["key_payload"] = payload
        return created

    async def create_pending_key_email_delivery(self, **kwargs):
        seen["delivery_kwargs"] = kwargs
        return _delivery(
            gateway_key_id=created.gateway_key_id,
            owner_id=created.owner_id,
            one_time_secret_id=created.one_time_secret_id,
        )

    monkeypatch.setattr("slaif_gateway.db.repositories.owners.OwnersRepository.get_owner_by_id", get_owner_by_id)
    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.create_gateway_key", create_gateway_key)
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.create_pending_key_email_delivery",
        create_pending_key_email_delivery,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data=_create_data(owner_id, email_delivery_mode="pending"),
    )

    assert response.status_code == 200
    assert response.text.count(created.plaintext_key) == 1
    assert "Email delivery is pending" in response.text
    assert seen["delivery_kwargs"]["gateway_key_id"] == created.gateway_key_id
    assert seen["delivery_kwargs"]["one_time_secret_id"] == created.one_time_secret_id
    assert seen["delivery_kwargs"]["owner_id"] == created.owner_id
    assert seen["delivery_kwargs"]["actor_admin_id"] == admin_user.id
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text


def test_create_mode_send_now_sends_and_suppresses_plaintext(monkeypatch) -> None:
    _patch_options(monkeypatch)
    owner_id = uuid.uuid4()
    owner = _owner(owner_id)
    created = _created_key(owner_id=owner_id)
    seen: dict[str, object] = {}

    async def get_owner_by_id(self, requested_owner_id):
        return owner if requested_owner_id == owner_id else None

    async def create_gateway_key(self, payload):
        return created

    async def create_pending_key_email_delivery(self, **kwargs):
        seen["pending_kwargs"] = kwargs
        return _delivery(
            gateway_key_id=created.gateway_key_id,
            owner_id=created.owner_id,
            one_time_secret_id=created.one_time_secret_id,
        )

    async def send_pending_key_email(self, **kwargs):
        seen["send_kwargs"] = kwargs
        return _delivery(
            gateway_key_id=created.gateway_key_id,
            owner_id=created.owner_id,
            one_time_secret_id=created.one_time_secret_id,
            status="sent",
        )

    monkeypatch.setattr("slaif_gateway.db.repositories.owners.OwnersRepository.get_owner_by_id", get_owner_by_id)
    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.create_gateway_key", create_gateway_key)
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.create_pending_key_email_delivery",
        create_pending_key_email_delivery,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.send_pending_key_email",
        send_pending_key_email,
    )
    client = TestClient(_app(_email_settings()))
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data=_create_data(owner_id, email_delivery_mode="send-now"),
    )

    assert response.status_code == 200
    assert created.plaintext_key not in response.text
    assert "Email delivery is the selected secret channel" in response.text
    assert "sent" in response.text
    assert seen["send_kwargs"]["one_time_secret_id"] == created.one_time_secret_id
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text


def test_create_mode_enqueue_queues_ids_only_and_suppresses_plaintext(monkeypatch) -> None:
    _patch_options(monkeypatch)
    owner_id = uuid.uuid4()
    owner = _owner(owner_id)
    created = _created_key(owner_id=owner_id)
    delivery_id = uuid.uuid4()
    fake_task_calls: list[tuple[object, ...]] = []

    class FakeResult:
        id = "task-123"

    class FakeTask:
        def delay(self, *args):
            fake_task_calls.append(args)
            return FakeResult()

    async def get_owner_by_id(self, requested_owner_id):
        return owner if requested_owner_id == owner_id else None

    async def create_gateway_key(self, payload):
        return created

    async def create_pending_key_email_delivery(self, **kwargs):
        return PendingKeyEmailResult(
            email_delivery_id=delivery_id,
            one_time_secret_id=created.one_time_secret_id,
            gateway_key_id=created.gateway_key_id,
            owner_id=created.owner_id,
            recipient_email="ada@example.org",
            status="pending",
        )

    monkeypatch.setattr("slaif_gateway.db.repositories.owners.OwnersRepository.get_owner_by_id", get_owner_by_id)
    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.create_gateway_key", create_gateway_key)
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.create_pending_key_email_delivery",
        create_pending_key_email_delivery,
    )
    monkeypatch.setattr("slaif_gateway.api.admin.send_pending_key_email_task", FakeTask())
    client = TestClient(_app(_email_settings()))
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data=_create_data(owner_id, email_delivery_mode="enqueue"),
    )

    assert response.status_code == 200
    assert created.plaintext_key not in response.text
    assert "task-123" in response.text
    assert "queued" in response.text
    assert fake_task_calls == [
        (
            str(created.one_time_secret_id),
            str(delivery_id),
            str(admin_user.id),
        )
    ]
    assert "sk-slaif-" not in repr(fake_task_calls)


def test_create_invalid_email_delivery_mode_fails_before_service_call(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.create_gateway_key", create_gateway_key)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data=_create_data(uuid.uuid4(), email_delivery_mode="resend-old-key"),
    )

    assert response.status_code == 400
    assert "Select a valid key email delivery mode" in response.text
    assert called is False


def test_create_send_now_requires_email_enabled_before_service_call(monkeypatch) -> None:
    _patch_options(monkeypatch)
    called = False

    async def create_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.create_gateway_key", create_gateway_key)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        "/admin/keys/create",
        data=_create_data(uuid.uuid4(), email_delivery_mode="send-now"),
    )

    assert response.status_code == 400
    assert "Email delivery must be enabled" in response.text
    assert called is False

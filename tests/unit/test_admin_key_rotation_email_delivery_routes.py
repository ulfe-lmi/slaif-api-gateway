import uuid

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.services.email_delivery_service import PendingKeyEmailResult

from tests.unit.test_admin_key_actions_routes import _app, _login_for_actions
from tests.unit.test_admin_key_rotation_routes import _rotation_result


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


def _rotate_data(**overrides: str) -> dict[str, str]:
    data = {
        "csrf_token": "dashboard-csrf",
        "confirm_rotate": "true",
        "reason": "replace exposed key",
    }
    data.update(overrides)
    return data


def _delivery(
    *,
    rotation,
    status: str = "pending",
) -> PendingKeyEmailResult:
    return PendingKeyEmailResult(
        email_delivery_id=uuid.uuid4(),
        one_time_secret_id=rotation.one_time_secret_id,
        gateway_key_id=rotation.new_gateway_key_id,
        owner_id=rotation.owner_id,
        recipient_email="ada@example.org",
        status=status,
        provider_message_id="<message@example.org>" if status == "sent" else None,
    )


def test_rotate_mode_pending_creates_delivery_and_keeps_replacement_plaintext_once(monkeypatch) -> None:
    old_key_id = uuid.uuid4()
    replacement_key = "sk-slaif-newpublic.once-only-replacement"
    rotation = _rotation_result(old_key_id=old_key_id, plaintext_key=replacement_key)
    seen: dict[str, object] = {}

    async def rotate_gateway_key(self, payload):
        return rotation

    async def create_pending_key_email_delivery(self, **kwargs):
        seen["delivery_kwargs"] = kwargs
        return _delivery(rotation=rotation)

    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.rotate_gateway_key", rotate_gateway_key)
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.create_pending_key_email_delivery",
        create_pending_key_email_delivery,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{old_key_id}/rotate",
        data=_rotate_data(email_delivery_mode="pending"),
    )

    assert response.status_code == 200
    assert response.text.count(replacement_key) == 1
    assert "Email delivery is pending" in response.text
    assert seen["delivery_kwargs"]["gateway_key_id"] == rotation.new_gateway_key_id
    assert seen["delivery_kwargs"]["one_time_secret_id"] == rotation.one_time_secret_id
    assert seen["delivery_kwargs"]["owner_id"] == rotation.owner_id
    assert seen["delivery_kwargs"]["actor_admin_id"] == admin_user.id
    assert "old-plaintext-key-must-not-render" not in response.text


def test_rotate_mode_send_now_sends_and_suppresses_replacement_plaintext(monkeypatch) -> None:
    old_key_id = uuid.uuid4()
    replacement_key = "sk-slaif-newpublic.once-only-replacement"
    rotation = _rotation_result(old_key_id=old_key_id, plaintext_key=replacement_key)
    seen: dict[str, object] = {}

    async def rotate_gateway_key(self, payload):
        seen["payload"] = payload
        return rotation

    async def create_pending_key_email_delivery(self, **kwargs):
        return _delivery(rotation=rotation)

    async def send_pending_key_email(self, **kwargs):
        seen["send_kwargs"] = kwargs
        return _delivery(rotation=rotation, status="sent")

    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.rotate_gateway_key", rotate_gateway_key)
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
        f"/admin/keys/{old_key_id}/rotate",
        data=_rotate_data(email_delivery_mode="send-now"),
    )

    assert response.status_code == 200
    assert replacement_key not in response.text
    assert "Email delivery is the selected secret channel" in response.text
    assert "sent" in response.text
    assert seen["payload"].revoke_old_key is True
    assert seen["send_kwargs"]["one_time_secret_id"] == rotation.one_time_secret_id
    assert "old-plaintext-key-must-not-render" not in response.text
    assert "token_hash" not in response.text
    assert "encrypted_payload" not in response.text
    assert "nonce" not in response.text


def test_rotate_mode_enqueue_queues_ids_only_and_suppresses_plaintext(monkeypatch) -> None:
    old_key_id = uuid.uuid4()
    replacement_key = "sk-slaif-newpublic.once-only-replacement"
    rotation = _rotation_result(old_key_id=old_key_id, plaintext_key=replacement_key)
    delivery_id = uuid.uuid4()
    fake_task_calls: list[tuple[object, ...]] = []

    class FakeResult:
        id = "task-rotation-123"

    class FakeTask:
        def delay(self, *args):
            fake_task_calls.append(args)
            return FakeResult()

    async def rotate_gateway_key(self, payload):
        return rotation

    async def create_pending_key_email_delivery(self, **kwargs):
        return PendingKeyEmailResult(
            email_delivery_id=delivery_id,
            one_time_secret_id=rotation.one_time_secret_id,
            gateway_key_id=rotation.new_gateway_key_id,
            owner_id=rotation.owner_id,
            recipient_email="ada@example.org",
            status="pending",
        )

    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.rotate_gateway_key", rotate_gateway_key)
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.create_pending_key_email_delivery",
        create_pending_key_email_delivery,
    )
    monkeypatch.setattr("slaif_gateway.api.admin.send_pending_key_email_task", FakeTask())
    client = TestClient(_app(_email_settings()))
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{old_key_id}/rotate",
        data=_rotate_data(email_delivery_mode="enqueue"),
    )

    assert response.status_code == 200
    assert replacement_key not in response.text
    assert "queued" in response.text
    assert "task-rotation-123" in response.text
    assert fake_task_calls == [
        (
            str(rotation.one_time_secret_id),
            str(delivery_id),
            str(admin_user.id),
        )
    ]
    assert "sk-slaif-" not in repr(fake_task_calls)


def test_rotate_invalid_email_delivery_mode_fails_before_service_call(monkeypatch) -> None:
    called = False
    old_key_id = uuid.uuid4()

    async def rotate_gateway_key(self, payload):
        nonlocal called
        called = True

    monkeypatch.setattr("slaif_gateway.services.key_service.KeyService.rotate_gateway_key", rotate_gateway_key)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/keys/{old_key_id}/rotate",
        data=_rotate_data(email_delivery_mode="resend-old-key"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/keys/{old_key_id}?message=invalid_email_delivery_mode"
    assert called is False

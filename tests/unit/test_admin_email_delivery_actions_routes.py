import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.services.admin_session_service import AdminSessionContext
from slaif_gateway.services.email_delivery_service import KeyEmailDeliverySendability, PendingKeyEmailResult


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


class _FakeAsyncResult:
    id = "fake-email-task-id"


class _FakeTask:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def delay(self, *args):
        self.calls.append(args)
        return _FakeAsyncResult()


def _settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://user:secret@localhost:5432/test_db",
        "ADMIN_SESSION_SECRET": "s" * 40,
        "ENABLE_EMAIL_DELIVERY": True,
        "SMTP_HOST": "localhost",
        "SMTP_FROM": "noreply@example.org",
        "CELERY_BROKER_URL": "redis://localhost:6379/15",
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


def _login_for_actions(monkeypatch, client: TestClient, *, valid_csrf: str = "dashboard-csrf") -> AdminUser:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    def verify_session_csrf_token(self, admin_session, csrf_token):
        return csrf_token == valid_csrf

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )
    client.cookies.set("slaif_admin_session", "session-plaintext")
    return admin_user


def _sendable(delivery_id: uuid.UUID, secret_id: uuid.UUID) -> KeyEmailDeliverySendability:
    return KeyEmailDeliverySendability(
        email_delivery_id=delivery_id,
        one_time_secret_id=secret_id,
        email_delivery_status="pending",
        one_time_secret_status="present",
        can_send=True,
        blocking_reason=None,
    )


def _blocked(delivery_id: uuid.UUID, secret_id: uuid.UUID, status: str) -> KeyEmailDeliverySendability:
    return KeyEmailDeliverySendability(
        email_delivery_id=delivery_id,
        one_time_secret_id=secret_id,
        email_delivery_status="pending",
        one_time_secret_status=status,
        can_send=False,
        blocking_reason="secret unavailable",
    )


def test_unauthenticated_email_delivery_action_redirects_to_login() -> None:
    client = TestClient(_app())
    response = client.post(f"/admin/email-deliveries/{uuid.uuid4()}/send-now", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_email_delivery_action_without_csrf_fails_before_service_call(monkeypatch) -> None:
    called = False

    async def get_key_email_delivery_sendability(self, email_delivery_id):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        get_key_email_delivery_sendability,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(f"/admin/email-deliveries/{uuid.uuid4()}/send-now")

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_email_delivery_action_with_invalid_csrf_fails(monkeypatch) -> None:
    called = False

    async def get_key_email_delivery_sendability(self, email_delivery_id):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        get_key_email_delivery_sendability,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/email-deliveries/{uuid.uuid4()}/enqueue",
        data={"csrf_token": "wrong", "confirm_enqueue": "true"},
    )

    assert response.status_code == 400
    assert "Invalid CSRF token." in response.text
    assert called is False


def test_send_now_requires_confirmation_before_service_call(monkeypatch) -> None:
    called = False
    delivery_id = uuid.uuid4()

    async def send_pending_key_email(self, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.send_pending_key_email",
        send_pending_key_email,
    )
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/send-now",
        data={"csrf_token": "dashboard-csrf"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/email-deliveries/{delivery_id}?message=email_delivery_send_confirmation_required"
    )
    assert called is False


def test_send_now_calls_email_delivery_service_with_actor_and_ids(monkeypatch) -> None:
    delivery_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    seen: dict[str, object] = {}

    async def get_key_email_delivery_sendability(self, email_delivery_id):
        assert email_delivery_id == delivery_id
        return _sendable(delivery_id, secret_id)

    async def send_pending_key_email(self, **kwargs):
        seen.update(kwargs)
        return PendingKeyEmailResult(
            email_delivery_id=delivery_id,
            one_time_secret_id=secret_id,
            gateway_key_id=uuid.uuid4(),
            owner_id=uuid.uuid4(),
            recipient_email="ada@example.org",
            status="sent",
        )

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        get_key_email_delivery_sendability,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.send_pending_key_email",
        send_pending_key_email,
    )
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/send-now",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_send": "true",
            "reason": "manual retry",
            "plaintext_key": "sk-slaif-public.secret",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/email-deliveries/{delivery_id}?message=email_delivery_sent"
    assert seen == {
        "one_time_secret_id": secret_id,
        "email_delivery_id": delivery_id,
        "actor_admin_id": admin_user.id,
        "reason": "manual retry",
    }


def test_enqueue_requires_confirmation_before_task_call(monkeypatch) -> None:
    delivery_id = uuid.uuid4()
    fake_task = _FakeTask()
    monkeypatch.setattr("slaif_gateway.api.admin.send_pending_key_email_task", fake_task)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/enqueue",
        data={"csrf_token": "dashboard-csrf"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/email-deliveries/{delivery_id}?message=email_delivery_enqueue_confirmation_required"
    )
    assert fake_task.calls == []


def test_enqueue_calls_celery_task_with_ids_only(monkeypatch) -> None:
    delivery_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    fake_task = _FakeTask()

    async def get_key_email_delivery_sendability(self, email_delivery_id):
        assert email_delivery_id == delivery_id
        return _sendable(delivery_id, secret_id)

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        get_key_email_delivery_sendability,
    )
    monkeypatch.setattr("slaif_gateway.api.admin.send_pending_key_email_task", fake_task)
    client = TestClient(_app())
    admin_user = _login_for_actions(monkeypatch, client)

    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/enqueue",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_enqueue": "true",
            "plaintext_key": "sk-slaif-public.secret",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/email-deliveries/{delivery_id}?message=email_delivery_queued"
    assert fake_task.calls == [(str(secret_id), str(delivery_id), str(admin_user.id))]
    assert "sk-slaif-" not in repr(fake_task.calls)
    assert "plaintext" not in repr(fake_task.calls).lower()


def test_expired_or_consumed_secret_prevents_send_and_enqueue(monkeypatch) -> None:
    delivery_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    send_called = False
    fake_task = _FakeTask()

    async def get_key_email_delivery_sendability(self, email_delivery_id):
        return _blocked(email_delivery_id, secret_id, "expired")

    async def send_pending_key_email(self, **kwargs):
        nonlocal send_called
        send_called = True

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        get_key_email_delivery_sendability,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.send_pending_key_email",
        send_pending_key_email,
    )
    monkeypatch.setattr("slaif_gateway.api.admin.send_pending_key_email_task", fake_task)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    send = client.post(
        f"/admin/email-deliveries/{delivery_id}/send-now",
        data={"csrf_token": "dashboard-csrf", "confirm_send": "true"},
        follow_redirects=False,
    )
    enqueue = client.post(
        f"/admin/email-deliveries/{delivery_id}/enqueue",
        data={"csrf_token": "dashboard-csrf", "confirm_enqueue": "true"},
        follow_redirects=False,
    )

    assert send.headers["location"] == f"/admin/email-deliveries/{delivery_id}?message=email_delivery_not_sendable"
    assert enqueue.headers["location"] == f"/admin/email-deliveries/{delivery_id}?message=email_delivery_not_sendable"
    assert send_called is False
    assert fake_task.calls == []


def test_ambiguous_delivery_prevents_send_and_enqueue(monkeypatch) -> None:
    delivery_id = uuid.uuid4()
    secret_id = uuid.uuid4()
    send_called = False
    fake_task = _FakeTask()

    async def get_key_email_delivery_sendability(self, email_delivery_id):
        return KeyEmailDeliverySendability(
            email_delivery_id=email_delivery_id,
            one_time_secret_id=secret_id,
            email_delivery_status="ambiguous",
            one_time_secret_status="present",
            can_send=False,
            blocking_reason="SMTP may have accepted this email; rotate the key.",
        )

    async def send_pending_key_email(self, **kwargs):
        nonlocal send_called
        send_called = True

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        get_key_email_delivery_sendability,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.send_pending_key_email",
        send_pending_key_email,
    )
    monkeypatch.setattr("slaif_gateway.api.admin.send_pending_key_email_task", fake_task)
    client = TestClient(_app())
    _login_for_actions(monkeypatch, client)

    send = client.post(
        f"/admin/email-deliveries/{delivery_id}/send-now",
        data={"csrf_token": "dashboard-csrf", "confirm_send": "true"},
        follow_redirects=False,
    )
    enqueue = client.post(
        f"/admin/email-deliveries/{delivery_id}/enqueue",
        data={"csrf_token": "dashboard-csrf", "confirm_enqueue": "true"},
        follow_redirects=False,
    )

    assert send.headers["location"] == f"/admin/email-deliveries/{delivery_id}?message=email_delivery_not_sendable"
    assert enqueue.headers["location"] == f"/admin/email-deliveries/{delivery_id}?message=email_delivery_not_sendable"
    assert send_called is False
    assert fake_task.calls == []

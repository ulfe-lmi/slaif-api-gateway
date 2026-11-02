import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.services.admin_session_service import AdminSessionContext
from slaif_gateway.services.email_delivery_service import KeyEmailDeliverySendability, PendingKeyEmailResult


class _FakeSession:
    """Read-mostly session fake; supports the 215-a committed audit.

    ``add``/``flush``/``commit`` back the shared
    ``record_enqueue_request_audit`` seam (AuditRepository.add_audit_log
    + session.commit BEFORE broker dispatch); every step is appended to
    the shared ``events`` list so tests can assert the real order.
    """

    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events if events is not None else []
        self.added: list[object] = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def begin(self):
        return self

    def add(self, row: object) -> None:
        self.added.append(row)
        self.events.append("audit-add")

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1
        self.events.append("commit")


class _FakeSessionmaker:
    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events if events is not None else []
        self.sessions: list[_FakeSession] = []

    def __call__(self):
        session = _FakeSession(self.events)
        self.sessions.append(session)
        return session


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


def _app(settings: Settings | None = None, sessionmaker: _FakeSessionmaker | None = None):
    app = create_app(settings or _settings())
    app.state.db_sessionmaker = sessionmaker or _FakeSessionmaker()
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
    send_calls: list[dict[str, object]] = []

    async def get_key_email_delivery_sendability(self, email_delivery_id):
        assert email_delivery_id == delivery_id
        return _sendable(delivery_id, secret_id)

    async def send_pending_key_email(self, **kwargs):
        seen.update(kwargs)
        send_calls.append(dict(kwargs))
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
    assert len(send_calls) == 1

    # 215-a canary: a PROVIDED reason matching an ACTUAL incoming
    # opaque cookie is withheld BEFORE any audit/SMTP - fixed safe
    # feedback, no service call, no new intent.
    client.cookies.set("slaif_opaque_token", "opaque-cookie-secret-215")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/send-now",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_send": "true",
            "reason": "token=opaque-cookie-secret-215",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/email-deliveries/{delivery_id}?message=email_delivery_reason_withheld"
    )
    assert len(send_calls) == 1  # still exactly ONE (the valid one)


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
    events: list[str] = []
    sessionmaker = _FakeSessionmaker(events)

    async def get_key_email_delivery_sendability(self, email_delivery_id):
        assert email_delivery_id == delivery_id
        return _sendable(delivery_id, secret_id)

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        get_key_email_delivery_sendability,
    )
    monkeypatch.setattr("slaif_gateway.api.admin.send_pending_key_email_task", fake_task)
    client = TestClient(_app(sessionmaker=sessionmaker))
    admin_user = _login_for_actions(monkeypatch, client)
    # The broker stub records its own dispatch event so the committed
    # audit order can be asserted against it.
    original_delay = fake_task.delay

    def _delay(*args):
        result = original_delay(*args)
        events.append("task-delay")
        return result

    fake_task.delay = _delay

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

    # 215-a: the ordinary pending enqueue commits the SAME shared
    # requested-intent audit BEFORE broker dispatch (blank reason
    # stays None; retry_failed=False; server actor).
    audits = [
        row
        for session in sessionmaker.sessions
        for row in session.added
        if getattr(row, "action", None) == "email_key_enqueue_requested"
    ]
    assert len(audits) == 1
    audit = audits[0]
    assert audit.entity_type == "email_delivery"
    assert audit.entity_id == delivery_id
    assert audit.admin_user_id == admin_user.id
    assert audit.note is None
    assert audit.new_values["retry_failed"] is False
    assert audit.new_values["intent"] == "enqueue_requested"
    assert audit.new_values["one_time_reference_id"] == str(secret_id)
    add_at = events.index("audit-add")
    delay_at = events.index("task-delay")
    assert add_at < delay_at
    assert "commit" in events[add_at:delay_at]  # committed BEFORE dispatch

    # 215-a canary: a PROVIDED reason matching an ACTUAL incoming
    # opaque cookie is withheld BEFORE any audit/broker - fixed safe
    # feedback, no new intent, no second dispatch. (The auth context
    # still opens its own session; the withheld flow must open NO
    # action session and add NO audit row.)
    sessions_before = len(sessionmaker.sessions)
    client.cookies.set("slaif_opaque_token", "opaque-cookie-secret-215")
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/enqueue",
        data={
            "csrf_token": "dashboard-csrf",
            "confirm_enqueue": "true",
            "reason": "opaque-cookie-secret-215",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/admin/email-deliveries/{delivery_id}?message=email_delivery_reason_withheld"
    )
    assert fake_task.calls == [(str(secret_id), str(delivery_id), str(admin_user.id))]
    canary_sessions = sessionmaker.sessions[sessions_before:]
    # At most the single auth-context session; it carries no audit row
    # and no commit - the intent scope was never entered.
    assert all(len(s.added) == 0 and s.commits == 0 for s in canary_sessions)
    audits_after = [
        row
        for session in sessionmaker.sessions
        for row in session.added
        if getattr(row, "action", None) == "email_key_enqueue_requested"
    ]
    assert len(audits_after) == 1


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

import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.admin_activity import (
    AdminAuditDetail,
    AdminAuditListRow,
    AdminEmailDeliveryDetail,
    AdminEmailDeliveryListRow,
    AdminUsageDetail,
    AdminUsageListRow,
)
from slaif_gateway.services.admin_activity_dashboard import AdminActivityNotFoundError
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


def _usage() -> AdminUsageDetail:
    row = AdminUsageListRow(
        id=uuid.uuid4(),
        request_id="req_usage",
        gateway_key_id=uuid.uuid4(),
        key_public_id="pub_usage",
        owner_id=uuid.uuid4(),
        owner_display_name="Ada Lovelace <ada@example.org>",
        institution_id=uuid.uuid4(),
        cohort_id=uuid.uuid4(),
        endpoint="/v1/chat/completions",
        provider="openai",
        requested_model="gpt-test",
        resolved_model="gpt-test",
        streaming=True,
        success=True,
        accounting_status="finalized",
        http_status=200,
        prompt_tokens=3,
        completion_tokens=5,
        total_tokens=8,
        cached_tokens=1,
        reasoning_tokens=2,
        estimated_cost_eur=Decimal("0.010000000"),
        actual_cost_eur=Decimal("0.008000000"),
        native_currency="EUR",
        latency_ms=123,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    return AdminUsageDetail(
        **asdict(row),
        client_request_id="client_req",
        quota_reservation_id=uuid.uuid4(),
        upstream_request_id="up_req",
        error_type=None,
        error_message=None,
        usage_summary='{"prompt_tokens": 3}',
        response_metadata_summary='{"safe": "ok"}',
    )


def _audit() -> AdminAuditDetail:
    row = AdminAuditListRow(
        id=uuid.uuid4(),
        actor_admin_id=uuid.uuid4(),
        action="key.created",
        target_type="gateway_key",
        target_id=uuid.uuid4(),
        request_id="req_audit",
        ip_address="127.0.0.1",
        user_agent_summary="pytest",
        created_at=datetime.now(UTC),
    )
    return AdminAuditDetail(
        **asdict(row),
        old_values_summary='{"safe": "old"}',
        new_values_summary='{"safe": "new"}',
        note="safe note",
    )


def _email() -> AdminEmailDeliveryDetail:
    row = AdminEmailDeliveryListRow(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        owner_email="ada@example.org",
        gateway_key_id=uuid.uuid4(),
        public_key_id="pub_email",
        one_time_secret_id=uuid.uuid4(),
        status="sent",
        to_email="ada@example.org",
        subject="Gateway key delivery",
        template_name="gateway_key_email",
        sent_at=datetime.now(UTC),
        failed_at=None,
        created_at=datetime.now(UTC),
    )
    return AdminEmailDeliveryDetail(
        **asdict(row),
        provider_message_id="smtp-message-id",
        failure_reason=None,
    )


def test_admin_activity_routes_redirect_when_unauthenticated() -> None:
    client = TestClient(_app())

    for path in ("/admin/usage", "/admin/audit", "/admin/email-deliveries"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


def test_admin_activity_routes_return_html_and_accept_filters(monkeypatch) -> None:
    usage = _usage()
    audit = _audit()
    email = _email()
    seen: dict[str, dict[str, object]] = {}

    async def list_usage(self, **kwargs):
        seen["usage"] = kwargs
        return [usage]

    async def get_usage_detail(self, usage_ledger_id):
        assert usage_ledger_id == usage.id
        return usage

    async def list_audit_logs(self, **kwargs):
        seen["audit"] = kwargs
        return [audit]

    async def get_audit_detail(self, audit_log_id):
        assert audit_log_id == audit.id
        return audit

    async def list_email_deliveries(self, **kwargs):
        seen["email"] = kwargs
        return [email]

    async def get_email_delivery_detail(self, email_delivery_id):
        assert email_delivery_id == email.id
        return email

    monkeypatch.setattr(
        "slaif_gateway.services.admin_activity_dashboard.AdminActivityDashboardService.list_usage",
        list_usage,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_activity_dashboard.AdminActivityDashboardService.get_usage_detail",
        get_usage_detail,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_activity_dashboard.AdminActivityDashboardService.list_audit_logs",
        list_audit_logs,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_activity_dashboard.AdminActivityDashboardService.get_audit_detail",
        get_audit_detail,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_activity_dashboard.AdminActivityDashboardService.list_email_deliveries",
        list_email_deliveries,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_activity_dashboard.AdminActivityDashboardService.get_email_delivery_detail",
        get_email_delivery_detail,
    )

    client = TestClient(_app())
    _login(monkeypatch, client)

    usage_list = client.get(
        "/admin/usage",
        params={
            "provider": "openai",
            "model": "gpt",
            "endpoint": "/v1/chat/completions",
            "status": "finalized",
            "gateway_key_id": str(usage.gateway_key_id),
            "owner_id": str(usage.owner_id),
            "institution_id": str(usage.institution_id),
            "cohort_id": str(usage.cohort_id),
            "request_id": usage.request_id,
            "streaming": "true",
        },
    )
    assert usage_list.status_code == 200
    assert "req_usage" in usage_list.text
    assert seen["usage"]["provider"] == "openai"
    assert seen["usage"]["streaming"] is True

    usage_detail = client.get(f"/admin/usage/{usage.id}")
    assert usage_detail.status_code == 200
    assert "up_req" in usage_detail.text

    audit_list = client.get(
        "/admin/audit",
        params={
            "actor_admin_id": str(audit.actor_admin_id),
            "action": "key",
            "target_type": "gateway_key",
            "target_id": str(audit.target_id),
            "request_id": audit.request_id,
        },
    )
    assert audit_list.status_code == 200
    assert "key.created" in audit_list.text
    assert seen["audit"]["target_id"] == audit.target_id

    audit_detail = client.get(f"/admin/audit/{audit.id}")
    assert audit_detail.status_code == 200
    assert "safe note" in audit_detail.text

    email_list = client.get(
        "/admin/email-deliveries",
        params={
            "status": "sent",
            "owner_email": "ada@example.org",
            "gateway_key_id": str(email.gateway_key_id),
            "one_time_secret_id": str(email.one_time_secret_id),
        },
    )
    assert email_list.status_code == 200
    assert "Gateway key delivery" in email_list.text
    assert seen["email"]["one_time_secret_id"] == email.one_time_secret_id

    email_detail = client.get(f"/admin/email-deliveries/{email.id}")
    assert email_detail.status_code == 200
    assert "smtp-message-id" in email_detail.text


def test_admin_activity_missing_and_invalid_ids_are_safe(monkeypatch) -> None:
    async def missing(self, row_id):
        raise AdminActivityNotFoundError("missing")

    monkeypatch.setattr(
        "slaif_gateway.services.admin_activity_dashboard.AdminActivityDashboardService.get_usage_detail",
        missing,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_activity_dashboard.AdminActivityDashboardService.get_audit_detail",
        missing,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_activity_dashboard.AdminActivityDashboardService.get_email_delivery_detail",
        missing,
    )

    client = TestClient(_app())
    _login(monkeypatch, client)

    for path in (
        "/admin/usage/not-a-uuid",
        f"/admin/usage/{uuid.uuid4()}",
        "/admin/audit/not-a-uuid",
        f"/admin/audit/{uuid.uuid4()}",
        "/admin/email-deliveries/not-a-uuid",
        f"/admin/email-deliveries/{uuid.uuid4()}",
    ):
        response = client.get(path)
        assert response.status_code == 404

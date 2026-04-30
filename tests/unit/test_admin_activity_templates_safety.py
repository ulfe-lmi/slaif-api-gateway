from __future__ import annotations

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


def _app():
    app = create_app(
        Settings(
            APP_ENV="test",
            DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
            ADMIN_SESSION_SECRET="s" * 40,
            OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
            OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
        )
    )
    app.state.db_sessionmaker = _FakeSessionmaker()
    return app


def _login(monkeypatch, client: TestClient) -> None:
    admin_user = AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="argon2-secret-password-hash",
        role="admin",
        is_active=True,
    )
    admin_session = AdminSession(
        id=uuid.uuid4(),
        admin_user_id=admin_user.id,
        session_token_hash="session-token-secret-hash",
        csrf_token_hash="csrf-token-secret-hash",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    admin_session.admin_user = admin_user

    async def validate_admin_session(self, **kwargs):
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    async def refresh_csrf_token(self, **kwargs):
        return "dashboard-csrf-token"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    client.cookies.set("slaif_admin_session", "plaintext-session-token")


def _usage() -> AdminUsageDetail:
    row = AdminUsageListRow(
        id=uuid.uuid4(),
        request_id="req_safe_usage",
        gateway_key_id=uuid.uuid4(),
        key_public_id="pub_safe_usage",
        owner_id=uuid.uuid4(),
        owner_display_name="Ada Lovelace <ada@example.org>",
        institution_id=uuid.uuid4(),
        cohort_id=uuid.uuid4(),
        endpoint="/v1/chat/completions",
        provider="openai",
        requested_model="gpt-safe",
        resolved_model="gpt-safe",
        streaming=False,
        success=True,
        accounting_status="finalized",
        http_status=200,
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
        cached_tokens=0,
        reasoning_tokens=0,
        estimated_cost_eur=Decimal("0.001000000"),
        actual_cost_eur=Decimal("0.001000000"),
        native_currency="EUR",
        latency_ms=20,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    return AdminUsageDetail(
        **asdict(row),
        client_request_id="client_safe",
        quota_reservation_id=uuid.uuid4(),
        upstream_request_id="up_safe",
        error_type=None,
        error_message=None,
        usage_summary='{"safe_counter": 3}',
        response_metadata_summary='{"provider_request": "safe"}',
    )


def _audit() -> AdminAuditDetail:
    row = AdminAuditListRow(
        id=uuid.uuid4(),
        actor_admin_id=uuid.uuid4(),
        action="key.created",
        target_type="gateway_key",
        target_id=uuid.uuid4(),
        request_id="req_safe_audit",
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
        public_key_id="pub_safe_email",
        one_time_secret_id=uuid.uuid4(),
        status="failed",
        to_email="ada@example.org",
        subject="Gateway key delivery",
        template_name="gateway_key_email",
        sent_at=None,
        failed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    return AdminEmailDeliveryDetail(
        **asdict(row),
        provider_message_id=None,
        failure_reason="safe SMTP failure",
        email_delivery_status=row.status,
        one_time_secret_status="present",
        can_send_now=True,
        can_enqueue=True,
        safe_blocking_reason=None,
    )


def test_admin_activity_pages_render_only_safe_metadata(monkeypatch) -> None:
    usage = _usage()
    audit = _audit()
    email = _email()

    async def list_usage(self, **kwargs):
        return [usage]

    async def get_usage_detail(self, usage_ledger_id):
        return usage

    async def list_audit_logs(self, **kwargs):
        return [audit]

    async def get_audit_detail(self, audit_log_id):
        return audit

    async def list_email_deliveries(self, **kwargs):
        return [email]

    async def get_email_delivery_detail(self, email_delivery_id):
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

    pages = [
        client.get("/admin/usage").text,
        client.get(f"/admin/usage/{usage.id}").text,
        client.get("/admin/audit").text,
        client.get(f"/admin/audit/{audit.id}").text,
        client.get("/admin/email-deliveries").text,
        client.get(f"/admin/email-deliveries/{email.id}").text,
    ]
    html = "\n".join(pages)

    assert "req_safe_usage" in html
    assert "key.created" in html
    assert "Gateway key delivery" in html
    assert "pub_safe_email" in html
    assert "/admin/email-deliveries/" in html
    assert "confirm_send" in html
    assert "confirm_enqueue" in html
    assert "one-time secret" in html
    assert "plaintext gateway key will not be shown" in html
    assert "Celery" in html
    assert "/admin/usage/export.csv" in html
    assert "/admin/audit/export.csv" in html
    assert "confirm_export" in html
    assert "Audit reason" in html
    assert "Formula-looking CSV cells are neutralized" in html

    forbidden = [
        "sk-provider-secret-placeholder",
        "sk-or-provider-secret-placeholder",
        "sk-slaif-public.secret",
        "token_hash",
        "encrypted_payload",
        "nonce",
        "password_hash",
        "argon2-secret-password-hash",
        "session-token-secret-hash",
        "plaintext-session-token",
        "prompt text that should not render",
        "completion text that should not render",
        "raw request body",
        "raw response body",
        "email body with key material",
    ]
    for value in forbidden:
        assert value not in html

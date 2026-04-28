import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.db.models import AuditLog, EmailDelivery, GatewayKey, Owner, UsageLedger
from slaif_gateway.schemas import admin_activity
from slaif_gateway.services.admin_activity_dashboard import (
    AdminActivityDashboardService,
    AdminActivityNotFoundError,
)


class _UsageRepo:
    def __init__(self, row: UsageLedger | None = None) -> None:
        self.row = row
        self.seen: dict[str, object] = {}

    async def list_usage_for_admin(self, **kwargs):
        self.seen.update(kwargs)
        return [self.row] if self.row is not None else []

    async def get_usage_for_admin_detail(self, usage_ledger_id):
        return self.row if self.row is not None and usage_ledger_id == self.row.id else None


class _AuditRepo:
    def __init__(self, row: AuditLog | None = None) -> None:
        self.row = row
        self.seen: dict[str, object] = {}

    async def list_audit_logs_for_admin(self, **kwargs):
        self.seen.update(kwargs)
        return [self.row] if self.row is not None else []

    async def get_audit_log_for_admin_detail(self, audit_log_id):
        return self.row if self.row is not None and audit_log_id == self.row.id else None


class _EmailRepo:
    def __init__(self, row: EmailDelivery | None = None) -> None:
        self.row = row
        self.seen: dict[str, object] = {}

    async def list_email_deliveries_for_admin(self, **kwargs):
        self.seen.update(kwargs)
        return [self.row] if self.row is not None else []

    async def get_email_delivery_for_admin_detail(self, email_delivery_id):
        return self.row if self.row is not None and email_delivery_id == self.row.id else None


def _service(
    *,
    usage: UsageLedger | None = None,
    audit: AuditLog | None = None,
    email: EmailDelivery | None = None,
) -> tuple[AdminActivityDashboardService, _UsageRepo, _AuditRepo, _EmailRepo]:
    usage_repo = _UsageRepo(usage)
    audit_repo = _AuditRepo(audit)
    email_repo = _EmailRepo(email)
    return (
        AdminActivityDashboardService(
            usage_ledger_repository=usage_repo,
            audit_repository=audit_repo,
            email_deliveries_repository=email_repo,
        ),
        usage_repo,
        audit_repo,
        email_repo,
    )


def _usage_row() -> UsageLedger:
    owner = Owner(id=uuid.uuid4(), name="Ada", surname="Lovelace", email="ada@example.org")
    key = GatewayKey(id=uuid.uuid4(), public_key_id="pub_usage", key_prefix="sk-slaif-", key_hint="abcd")
    row = UsageLedger(
        id=uuid.uuid4(),
        request_id="req_usage",
        client_request_id="client_req",
        quota_reservation_id=uuid.uuid4(),
        gateway_key_id=key.id,
        owner_id=owner.id,
        institution_id=uuid.uuid4(),
        cohort_id=uuid.uuid4(),
        owner_email_snapshot=owner.email,
        owner_name_snapshot=owner.name,
        owner_surname_snapshot=owner.surname,
        endpoint="/v1/chat/completions",
        provider="openai",
        requested_model="gpt-test",
        resolved_model="gpt-test",
        upstream_request_id="up_req",
        streaming=True,
        success=True,
        accounting_status="finalized",
        http_status=200,
        prompt_tokens=3,
        completion_tokens=5,
        cached_tokens=1,
        reasoning_tokens=2,
        total_tokens=8,
        estimated_cost_eur=Decimal("0.010000000"),
        actual_cost_eur=Decimal("0.008000000"),
        native_currency="EUR",
        usage_raw={"prompt_tokens": 3, "messages": "prompt-content", "api_key": "sk-secret"},
        response_metadata={"safe": "ok", "response_body": "completion-content", "authorization": "Bearer abc"},
        started_at=datetime.now(UTC) - timedelta(seconds=1),
        finished_at=datetime.now(UTC),
        latency_ms=123,
        created_at=datetime.now(UTC),
    )
    row.gateway_key = key
    row.owner = owner
    return row


def _audit_row() -> AuditLog:
    return AuditLog(
        id=uuid.uuid4(),
        admin_user_id=uuid.uuid4(),
        action="key.created",
        entity_type="gateway_key",
        entity_id=uuid.uuid4(),
        old_values={"token_hash": "secret", "safe": "old"},
        new_values={"prompt": "hidden", "safe": "new", "provider_api_key": "sk-secret"},
        ip_address="127.0.0.1",
        user_agent="pytest",
        request_id="req_audit",
        note="Authorization=Bearer abc and safe note",
        created_at=datetime.now(UTC),
    )


def _email_row() -> EmailDelivery:
    owner = Owner(id=uuid.uuid4(), name="Ada", surname="Lovelace", email="ada@example.org")
    key = GatewayKey(id=uuid.uuid4(), public_key_id="pub_email", key_prefix="sk-slaif-", key_hint="wxyz")
    row = EmailDelivery(
        id=uuid.uuid4(),
        owner_id=owner.id,
        gateway_key_id=key.id,
        one_time_secret_id=uuid.uuid4(),
        recipient_email="ada@example.org",
        subject="Gateway key delivery",
        template_name="gateway_key_email",
        status="sent",
        provider_message_id="smtp-message-id",
        error_message=None,
        created_at=datetime.now(UTC),
        sent_at=datetime.now(UTC),
    )
    row.owner = owner
    row.gateway_key = key
    return row


@pytest.mark.asyncio
async def test_activity_service_returns_safe_rows_and_details() -> None:
    usage = _usage_row()
    audit = _audit_row()
    email = _email_row()
    service, _, _, _ = _service(usage=usage, audit=audit, email=email)

    usage_rows = await service.list_usage(provider=" openai ", status="finalized")
    usage_detail = await service.get_usage_detail(usage.id)
    audit_rows = await service.list_audit_logs(action="key")
    audit_detail = await service.get_audit_detail(audit.id)
    email_rows = await service.list_email_deliveries(status="sent")
    email_detail = await service.get_email_delivery_detail(email.id)

    assert usage_rows == [admin_activity.AdminUsageListRow(**asdict(usage_rows[0]))]
    assert usage_detail.key_public_id == "pub_usage"
    assert "prompt-content" not in usage_detail.usage_summary
    assert "completion-content" not in usage_detail.response_metadata_summary
    assert "api_key" not in usage_detail.usage_summary
    assert audit_rows[0].target_type == "gateway_key"
    assert "token_hash" not in audit_detail.old_values_summary
    assert "provider_api_key" not in audit_detail.new_values_summary
    assert "hidden" not in audit_detail.new_values_summary
    assert "Bearer abc" not in (audit_detail.note or "")
    assert email_rows[0].public_key_id == "pub_email"
    assert email_detail.provider_message_id == "smtp-message-id"


@pytest.mark.asyncio
async def test_activity_service_passes_filters_to_repositories() -> None:
    usage = _usage_row()
    audit = _audit_row()
    email = _email_row()
    service, usage_repo, audit_repo, email_repo = _service(usage=usage, audit=audit, email=email)

    await service.list_usage(gateway_key_id=usage.gateway_key_id, request_id="req", streaming=True, limit=7, offset=2)
    await service.list_audit_logs(actor_admin_id=audit.admin_user_id, target_id=audit.entity_id, request_id="req")
    await service.list_email_deliveries(
        owner_email="ada@example.org",
        gateway_key_id=email.gateway_key_id,
        one_time_secret_id=email.one_time_secret_id,
    )

    assert usage_repo.seen["gateway_key_id"] == usage.gateway_key_id
    assert usage_repo.seen["request_id"] == "req"
    assert usage_repo.seen["streaming"] is True
    assert usage_repo.seen["limit"] == 7
    assert usage_repo.seen["offset"] == 2
    assert audit_repo.seen["actor_admin_id"] == audit.admin_user_id
    assert audit_repo.seen["target_id"] == audit.entity_id
    assert email_repo.seen["owner_email"] == "ada@example.org"
    assert email_repo.seen["one_time_secret_id"] == email.one_time_secret_id


@pytest.mark.asyncio
async def test_activity_service_missing_records_raise_safe_error() -> None:
    service, _, _, _ = _service()

    with pytest.raises(AdminActivityNotFoundError):
        await service.get_usage_detail(uuid.uuid4())
    with pytest.raises(AdminActivityNotFoundError):
        await service.get_audit_detail(uuid.uuid4())
    with pytest.raises(AdminActivityNotFoundError):
        await service.get_email_delivery_detail(uuid.uuid4())

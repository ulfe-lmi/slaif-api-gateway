"""Unit evidence for the 202-a read-only email inspection layer."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.schemas.email_inspection import (
    EMAIL_DELIVERY_STATUSES,
    EmailInspectionValidationError,
    normalize_owner_email,
    validate_creation_window,
    validate_delivery_status,
    validate_page,
)
from slaif_gateway.services.email_delivery_service import KeyEmailDeliverySendability
from slaif_gateway.services.email_inspection import EmailInspectionService

NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)


# --- schema validation -------------------------------------------------------


def test_validate_delivery_status_accepts_all_persisted_values() -> None:
    for status in EMAIL_DELIVERY_STATUSES:
        assert validate_delivery_status(status) == status
    assert set(EMAIL_DELIVERY_STATUSES) == {
        "pending",
        "sending",
        "sent",
        "failed",
        "ambiguous",
        "cancelled",
    }


def test_validate_delivery_status_rejects_non_persisted_values() -> None:
    for bad in ("queued", "", "SENT", "sending ", None):  # type: ignore[arg-type]
        with pytest.raises(EmailInspectionValidationError):
            validate_delivery_status(bad)


def test_normalize_owner_email_strip_lower_exact() -> None:
    assert normalize_owner_email("  Ada@Example.ORG ") == "ada@example.org"


def test_normalize_owner_email_rejects_invalid_shapes() -> None:
    for bad in ("", "   ", "no-at-sign", "@x.org", "x.org@", "@@"):
        with pytest.raises(EmailInspectionValidationError):
            normalize_owner_email(bad)


def test_validate_creation_window_rejects_reversed_without_echo() -> None:
    with pytest.raises(EmailInspectionValidationError) as exc:
        validate_creation_window(NOW + timedelta(hours=1), NOW)
    assert "later" in exc.value.safe_message
    assert NOW.isoformat() not in exc.value.safe_message


def test_validate_creation_window_requires_explicit_aware_utc() -> None:
    naive = datetime(2026, 1, 1, tzinfo=None)
    with pytest.raises(EmailInspectionValidationError):
        validate_creation_window(naive, None)
    with pytest.raises(EmailInspectionValidationError):
        validate_creation_window(None, naive)
    assert validate_creation_window(NOW, NOW) == (NOW, NOW)


def test_validate_page_bounds() -> None:
    assert validate_page(1, 0) == (1, 0)
    assert validate_page(100, 1000000) == (100, 1000000)
    for bad in ((0, 0), (101, 0), (50, -1), (50, 1000001)):
        with pytest.raises(EmailInspectionValidationError):
            validate_page(*bad)


# --- fakes -------------------------------------------------------------------


@dataclass
class _Row:
    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    gateway_key_id: uuid.UUID | None = None
    one_time_secret_id: uuid.UUID | None = None
    recipient_email: str = "ada@example.org"
    status: str = "pending"
    created_at: datetime = NOW
    sent_at: datetime | None = None
    failed_at: datetime | None = None


@dataclass
class _AuditRow:
    action: str
    created_at: datetime
    new_values: dict[str, object] | None


class _FakeDeliveryRepo:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []
        self.mutation_calls: list[str] = []

    async def get_email_delivery_by_id(self, delivery_id: uuid.UUID):
        for row in self.rows:
            if row.id == delivery_id:
                return row
        return None

    async def list_email_deliveries_for_inspection(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["delivery_id"] is not None:
            self.rows = [r for r in self.rows if r.id == kwargs["delivery_id"]]
        if kwargs["gateway_key_id"] is not None:
            self.rows = [r for r in self.rows if r.gateway_key_id == kwargs["gateway_key_id"]]
        if kwargs["owner_id"] is not None:
            self.rows = [r for r in self.rows if r.owner_id == kwargs["owner_id"]]
        if kwargs["owner_email_normalized"] is not None:
            self.rows = [
                r
                for r in self.rows
                if r.recipient_email.lower() == kwargs["owner_email_normalized"]
            ]
        if kwargs["status"] is not None:
            self.rows = [r for r in self.rows if r.status == kwargs["status"]]
        if kwargs["created_from"] is not None:
            self.rows = [r for r in self.rows if r.created_at >= kwargs["created_from"]]
        if kwargs["created_until"] is not None:
            self.rows = [r for r in self.rows if r.created_at <= kwargs["created_until"]]
        ordered = sorted(self.rows, key=lambda r: (r.created_at, r.id), reverse=True)
        offset = kwargs["offset"]
        limit = kwargs["limit"]
        return ordered[offset : offset + limit]


class _FakeAuditRepo:
    def __init__(self, row: _AuditRow | None = None) -> None:
        self.row = row
        self.calls: list[uuid.UUID] = []

    async def get_latest_email_error_for_delivery(self, delivery_id: uuid.UUID):
        self.calls.append(delivery_id)
        return self.row


class _Sendability:
    def __init__(self, status: str, can_send: bool, blocking: str | None = None) -> None:
        self.status = status
        self.can_send = can_send
        self.blocking = blocking

    async def __call__(self, delivery_id: uuid.UUID):
        return KeyEmailDeliverySendability(
            email_delivery_id=delivery_id,
            one_time_secret_id=uuid.uuid4(),
            email_delivery_status="pending",
            one_time_secret_status=self.status,
            can_send=self.can_send,
            blocking_reason=self.blocking,
        )


def _service(delivery_repo: _FakeDeliveryRepo, audit_repo: _FakeAuditRepo, sendability: _Sendability):
    return EmailInspectionService(
        email_deliveries_repository=delivery_repo,
        audit_repository=audit_repo,
        sendability_provider=sendability,
    )


# --- list behavior -----------------------------------------------------------


@pytest.mark.asyncio
async def test_list_and_combines_filters_before_paging() -> None:
    key = uuid.uuid4()
    owner = uuid.uuid4()
    rows = [
        _Row(id=uuid.uuid4(), owner_id=owner, gateway_key_id=key, status="pending", created_at=NOW),
        _Row(id=uuid.uuid4(), owner_id=owner, gateway_key_id=key, status="sent", created_at=NOW),
    ]
    repo = _FakeDeliveryRepo(rows)
    service = _service(repo, _FakeAuditRepo(), _Sendability("present", True))

    page = await service.list_deliveries(
        gateway_key_id=key,
        owner_id=owner,
        status="pending",
        limit=50,
        offset=0,
    )

    assert len(page.items) == 1
    assert page.items[0].status == "pending"
    # the repository received ALL filters AND-combined, plus limit+1 fetch
    assert repo.calls[0]["limit"] == 51
    assert repo.calls[0]["gateway_key_id"] == key
    assert repo.calls[0]["owner_id"] == owner
    assert repo.calls[0]["status"] == "pending"
    assert page.has_more is False
    assert page.next_offset is None


@pytest.mark.asyncio
async def test_list_honest_has_more_and_next_offset_at_page_edge() -> None:
    rows = [
        _Row(id=uuid.uuid4(), status="pending", created_at=NOW - timedelta(seconds=i))
        for i in range(51)
    ]
    repo = _FakeDeliveryRepo(rows)
    service = _service(repo, _FakeAuditRepo(), _Sendability("present", True))

    page = await service.list_deliveries(limit=50, offset=0)
    assert len(page.items) == 50
    assert page.has_more is True
    assert page.next_offset == 50

    last = await service.list_deliveries(limit=50, offset=50)
    assert len(last.items) == 1
    assert last.has_more is False
    assert last.next_offset is None


@pytest.mark.asyncio
async def test_list_rejects_unknown_status_via_service_validation() -> None:
    service = _service(_FakeDeliveryRepo([]), _FakeAuditRepo(), _Sendability("present", True))
    with pytest.raises(EmailInspectionValidationError):
        await service.list_deliveries(status="queued")


@pytest.mark.asyncio
async def test_list_items_expose_allowlisted_fields_only() -> None:
    row = _Row(id=uuid.uuid4(), status="failed", failed_at=NOW)
    service = _service(_FakeDeliveryRepo([row]), _FakeAuditRepo(), _Sendability("present", True))
    page = await service.list_deliveries()
    item = page.items[0]
    assert {f for f in item.__dataclass_fields__} == {
        "delivery_id",
        "owner_id",
        "gateway_key_id",
        "one_time_secret_id",
        "recipient_email",
        "status",
        "created_at",
        "sent_at",
        "failed_at",
    }
    # no subject/template/error-prose/provider-message/encrypted fields exist
    assert not hasattr(item, "subject")
    assert not hasattr(item, "error_message")
    assert not hasattr(item, "provider_message_id")
    assert not hasattr(item, "encrypted_payload")


@pytest.mark.asyncio
async def test_list_masks_known_secret_shaped_recipient_and_preserves_normal() -> None:
    # 202-a root canary: a recognized synthetic gateway-key-shaped recipient
    # is masked at the output boundary; normal addresses pass through.
    canary = "sk-slaif-canary202a00"
    rows = [
        _Row(id=uuid.uuid4(), recipient_email=canary),
        _Row(id=uuid.uuid4(), recipient_email="ada@example.org"),
    ]
    service = _service(_FakeDeliveryRepo(rows), _FakeAuditRepo(), _Sendability("present", True))
    page = await service.list_deliveries()
    recipients = {item.recipient_email for item in page.items}
    assert "ada@example.org" in recipients
    assert canary not in recipients


# --- show behavior -----------------------------------------------------------


@pytest.mark.asyncio
async def test_show_missing_delivery_is_distinct_not_found() -> None:
    service = _service(_FakeDeliveryRepo([]), _FakeAuditRepo(), _Sendability("present", True))
    assert await service.show_delivery(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_show_projects_lifecycle_and_known_last_failure() -> None:
    row = _Row(id=uuid.uuid4(), status="sent", sent_at=NOW)
    audit = _AuditRow(
        action="email_key_failed",
        created_at=NOW - timedelta(hours=2),
        new_values={"error_code": "smtp_send_error"},
    )
    service = _service(
        _FakeDeliveryRepo([row]),
        _FakeAuditRepo(audit),
        _Sendability("consumed", False, "The one-time secret was already consumed; lost keys must be rotated."),
    )

    detail = await service.show_delivery(row.id)

    assert detail is not None
    assert detail.item.status == "sent"
    assert detail.secret_lifecycle is not None
    assert detail.secret_lifecycle.status == "consumed"
    assert detail.secret_lifecycle.can_send is False
    assert detail.last_recorded_failure is not None
    assert detail.last_recorded_failure.error_code == "smtp_send_error"
    assert detail.last_recorded_failure.action == "email_key_failed"
    assert detail.last_recorded_failure.provenance == "last recorded audit error"
    # sent row retains a HISTORICAL last-recorded failure; provenance fixed
    assert detail.last_recorded_failure.recorded_at < detail.item.sent_at


@pytest.mark.asyncio
async def test_show_unknown_recorded_error_code_is_unavailable_not_guessed() -> None:
    row = _Row(id=uuid.uuid4(), status="failed", failed_at=NOW)
    audit = _AuditRow(
        action="email_key_ambiguous",
        created_at=NOW,
        new_values={"error_code": "totally_unknown_code"},
    )
    service = _service(
        _FakeDeliveryRepo([row]),
        _FakeAuditRepo(audit),
        _Sendability("present", True),
    )
    detail = await service.show_delivery(row.id)
    assert detail is not None
    assert detail.last_recorded_failure is not None
    assert detail.last_recorded_failure.error_code == "unavailable"
    assert detail.last_recorded_failure.action == "email_key_ambiguous"


@pytest.mark.asyncio
async def test_show_non_dict_audit_metadata_is_unavailable() -> None:
    row = _Row(id=uuid.uuid4(), status="failed", failed_at=NOW)
    audit = _AuditRow(action="email_key_failed", created_at=NOW, new_values=None)
    service = _service(_FakeDeliveryRepo([row]), _FakeAuditRepo(audit), _Sendability("present", True))
    detail = await service.show_delivery(row.id)
    assert detail is not None
    assert detail.last_recorded_failure is not None
    assert detail.last_recorded_failure.error_code == "unavailable"


@pytest.mark.asyncio
async def test_show_no_audit_entry_is_null_not_fabricated() -> None:
    row = _Row(id=uuid.uuid4(), status="pending")
    service = _service(_FakeDeliveryRepo([row]), _FakeAuditRepo(None), _Sendability("present", True))
    detail = await service.show_delivery(row.id)
    assert detail is not None
    assert detail.last_recorded_failure is None


@pytest.mark.asyncio
async def test_show_reuses_exact_delivery_id_for_sendability() -> None:
    row = _Row(id=uuid.uuid4(), status="pending")
    sendability = _Sendability("present", True)

    seen: list[uuid.UUID] = []

    async def spy(delivery_id: uuid.UUID):
        seen.append(delivery_id)
        return await sendability(delivery_id)

    service = EmailInspectionService(
        email_deliveries_repository=_FakeDeliveryRepo([row]),
        audit_repository=_FakeAuditRepo(None),
        sendability_provider=spy,
    )
    await service.show_delivery(row.id)
    assert seen == [row.id]

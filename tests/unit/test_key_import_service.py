from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from slaif_gateway.schemas.keys import CreatedGatewayKey
from slaif_gateway.services.key_import import (
    KeyImportExecutionRow,
    KeyImportExecutionResult,
    KeyImportCohortRef,
    KeyImportOwnerRef,
    KeyImportReadOnlyContext,
    build_key_import_execution_plan,
    enqueue_key_import_email_tasks,
    execute_key_import_plan,
    key_import_execution_error_result,
    key_import_preview_to_dict,
    parse_key_import_csv,
    parse_key_import_json,
    validate_key_import_rows,
)


OWNER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
INSTITUTION_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
COHORT_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
ADMIN_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")


def _context(**overrides) -> KeyImportReadOnlyContext:
    owner = KeyImportOwnerRef(
        id=OWNER_ID,
        email="ada@example.org",
        display_name="Ada Lovelace",
        institution_id=INSTITUTION_ID,
        institution_name="SLAIF",
    )
    values = {
        "owners_by_id": {OWNER_ID: owner},
        "owners_by_email": {owner.email: owner},
        "cohorts_by_id": {COHORT_ID: KeyImportCohortRef(id=COHORT_ID, name="Spring Cohort")},
        "email_delivery_enabled": False,
        "smtp_configured": False,
        "celery_configured": False,
    }
    values.update(overrides)
    return KeyImportReadOnlyContext(**values)


def _valid_row(**overrides) -> dict[str, object]:
    row: dict[str, object] = {
        "owner_id": str(OWNER_ID),
        "valid_days": "30",
        "cost_limit_eur": "10.50",
        "token_limit_total": "100000",
        "request_limit_total": "1000",
        "allowed_models": "gpt-test\nopenrouter/test",
        "allowed_endpoints": "/v1/chat/completions,/v1/models",
        "allowed_providers": "openai,openrouter",
        "rate_limit_requests_per_minute": "60",
        "rate_limit_tokens_per_minute": "12000",
        "rate_limit_concurrent_requests": "4",
        "rate_limit_window_seconds": "30",
        "email_delivery_mode": "none",
        "note": "safe note",
    }
    row.update(overrides)
    return row


def _preview(rows: list[dict[str, object]], *, max_rows: int = 1000, context=None):
    return validate_key_import_rows(
        rows,
        context=context or _context(),
        max_rows=max_rows,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_valid_csv_and_json_parse() -> None:
    csv_rows = parse_key_import_csv("owner_email,valid_days\nada@example.org,30\n")
    json_rows = parse_key_import_json('[{"owner_email":"ada@example.org","valid_days":"30"}]')

    assert csv_rows[0]["owner_email"] == "ada@example.org"
    assert json_rows[0]["valid_days"] == "30"


def test_valid_row_resolves_owner_policy_and_rate_limits() -> None:
    preview = _preview([_valid_row(owner_id="", owner_email="ada@example.org", cohort_id=str(COHORT_ID))])

    row = preview.rows[0]
    assert preview.valid_count == 1
    assert row.owner_id == OWNER_ID
    assert row.owner_email == "ada@example.org"
    assert row.institution_id == INSTITUTION_ID
    assert row.cohort_id == COHORT_ID
    assert row.cost_limit_eur == "10.50"
    assert row.token_limit == 100000
    assert row.request_limit == 1000
    assert row.allowed_models == ("gpt-test", "openrouter/test")
    assert row.allowed_endpoints == ("/v1/chat/completions", "/v1/models")
    assert row.allowed_providers == ("openai", "openrouter")
    assert row.rate_limit_policy == {
        "requests_per_minute": 60,
        "tokens_per_minute": 12000,
        "max_concurrent_requests": 4,
        "window_seconds": 30,
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("unknown", "value", "unknown fields"),
        ("owner_id", str(uuid.uuid4()), "owner_id must reference an existing owner"),
        ("owner_email", "not-an-email", "owner_email must be a valid email address"),
        ("institution_id", str(uuid.uuid4()), "institution_id must match"),
        ("cohort_id", str(uuid.uuid4()), "cohort_id must reference an existing cohort"),
        ("cost_limit_eur", "not-decimal", "cost_limit_eur must be a decimal string"),
        ("cost_limit_eur", "-1", "cost_limit_eur must be positive"),
        ("token_limit_total", "zero", "token_limit must be a positive integer"),
        ("allow_all_models", "maybe", "allow_all_models must be true or false"),
        ("email_delivery_mode", "old-key-resend", "email_delivery_mode must be"),
        ("note", "sk-provider-secret", "note must not contain secret-looking values"),
        ("allowed_models", "Bearer upstream-token", "allowed_models must not contain secret-looking values"),
    ],
)
def test_invalid_rows_are_rejected(field: str, value: str, message: str) -> None:
    preview = _preview([_valid_row(**{field: value})])

    assert preview.invalid_count == 1
    assert message in preview.rows[0].errors[0]


def test_owner_id_and_email_must_match_when_both_supplied() -> None:
    preview = _preview([_valid_row(owner_email="other@example.org")])

    assert preview.invalid_count == 1
    assert "owner_email must match owner_id" in preview.rows[0].errors[0]


def test_missing_owner_email_lookup_is_rejected() -> None:
    preview = _preview([_valid_row(owner_id="", owner_email="missing@example.org")])

    assert preview.invalid_count == 1
    assert "owner_email must reference an existing owner" in preview.rows[0].errors[0]


def test_invalid_validity_window_is_rejected() -> None:
    preview = _preview([_valid_row(valid_days="", valid_until="2025-01-01T00:00:00+00:00")])

    assert preview.invalid_count == 1
    assert "valid_until must be after valid_from" in preview.rows[0].errors[0]


def test_json_numeric_money_and_integer_values_are_rejected() -> None:
    rows = parse_key_import_json(
        '[{"owner_id":"11111111-1111-4111-8111-111111111111",'
        '"valid_days":"30","cost_limit_eur":10.5,"token_limit_total":1000}]'
    )

    preview = _preview(rows)

    assert preview.invalid_count == 1
    assert "cost_limit_eur must be a string" in preview.rows[0].errors[0]


def test_email_delivery_send_now_requires_configuration() -> None:
    preview = _preview([_valid_row(email_delivery_mode="send-now")])

    assert preview.invalid_count == 1
    assert "email delivery must be enabled" in preview.rows[0].errors[0]


def test_email_delivery_modes_validate_when_configured() -> None:
    context = _context(email_delivery_enabled=True, smtp_configured=True, celery_configured=True)

    preview = _preview(
        [_valid_row(email_delivery_mode="send-now"), _valid_row(owner_email="", email_delivery_mode="enqueue")],
        context=context,
    )

    assert preview.valid_count == 2
    assert [row.email_delivery_mode for row in preview.rows] == ["send-now", "enqueue"]


def test_metadata_secret_and_provider_key_values_are_rejected() -> None:
    metadata = _preview([_valid_row(metadata='{"api_key":"sk-provider-secret"}')])
    provider_key = _preview([_valid_row(label="sk-or-provider-secret")])

    assert metadata.invalid_count == 1
    assert "metadata must not contain secret-looking values" in metadata.rows[0].errors[0]
    assert provider_key.invalid_count == 1
    assert "label must not contain secret-looking values" in provider_key.rows[0].errors[0]


def test_max_rows_enforced() -> None:
    with pytest.raises(ValueError, match="at most 1 rows"):
        _preview([_valid_row(), _valid_row(owner_email="")], max_rows=1)


def test_duplicate_owner_rows_are_classified_without_blocking_preview() -> None:
    preview = _preview([_valid_row(), _valid_row(owner_email="")])

    assert preview.valid_count == 2
    assert preview.duplicate_owner_count == 2
    assert [row.classification for row in preview.rows] == ["duplicate", "duplicate"]


def test_preview_dict_does_not_include_raw_content_or_secret_fields() -> None:
    preview = _preview([_valid_row(note="<script>alert(1)</script>")])
    payload = key_import_preview_to_dict(preview)

    assert payload["rows"][0]["owner_email"] == "ada@example.org"
    assert "owner_email,valid_days" not in str(payload)
    assert "token_hash" not in str(payload)
    assert "encrypted_payload" not in str(payload)
    assert "nonce" not in str(payload)
    assert "password_hash" not in str(payload)
    assert "sk-slaif-plaintext.secret" not in str(payload)


def test_execution_plan_requires_confirmation_reason_and_valid_rows() -> None:
    preview = _preview([_valid_row(allowed_providers="")])

    with pytest.raises(ValueError, match="Confirm bulk key import"):
        build_key_import_execution_plan(
            preview,
            actor_admin_id=ADMIN_ID,
            reason="bulk import",
            confirm_import=False,
            confirm_plaintext_display=True,
        )
    with pytest.raises(ValueError, match="audit reason"):
        build_key_import_execution_plan(
            preview,
            actor_admin_id=ADMIN_ID,
            reason=" ",
            confirm_import=True,
            confirm_plaintext_display=True,
        )
    with pytest.raises(ValueError, match="one-time plaintext display"):
        build_key_import_execution_plan(
            preview,
            actor_admin_id=ADMIN_ID,
            reason="bulk import",
            confirm_import=True,
            confirm_plaintext_display=False,
        )

    invalid = _preview([_valid_row(owner_id=str(uuid.uuid4()))])
    with pytest.raises(ValueError, match="All rows must validate"):
        build_key_import_execution_plan(
            invalid,
            actor_admin_id=ADMIN_ID,
            reason="bulk import",
            confirm_import=True,
            confirm_plaintext_display=True,
        )


def test_execution_plan_rejects_send_now_and_provider_policy() -> None:
    configured = _context(email_delivery_enabled=True, smtp_configured=True, celery_configured=True)
    send_now = _preview([_valid_row(email_delivery_mode="send-now", allowed_providers="")], context=configured)
    provider_policy = _preview([_valid_row()], context=configured)

    with pytest.raises(ValueError, match="send-now email delivery is not implemented"):
        build_key_import_execution_plan(
            send_now,
            actor_admin_id=ADMIN_ID,
            reason="bulk import",
            confirm_import=True,
            confirm_plaintext_display=True,
        )
    with pytest.raises(ValueError, match="allowed_providers"):
        build_key_import_execution_plan(
            provider_policy,
            actor_admin_id=ADMIN_ID,
            reason="bulk import",
            confirm_import=True,
            confirm_plaintext_display=True,
        )


def test_execution_plan_builds_for_supported_modes() -> None:
    context = _context(email_delivery_enabled=True, celery_configured=True)
    preview = _preview(
        [
            _valid_row(allowed_providers="", email_delivery_mode="pending"),
            _valid_row(allowed_providers="", email_delivery_mode="enqueue"),
        ],
        context=context,
    )

    plan = build_key_import_execution_plan(
        preview,
        actor_admin_id=ADMIN_ID,
        reason="bulk import",
        confirm_import=True,
        confirm_plaintext_display=True,
    )

    assert plan.total_rows == 2
    assert plan.reason == "bulk import"
    assert plan.plaintext_display_required is True


class _FakeKeyService:
    def __init__(self) -> None:
        self.payloads = []

    async def create_gateway_key(self, payload):
        self.payloads.append(payload)
        return CreatedGatewayKey(
            gateway_key_id=uuid.UUID("55555555-5555-4555-8555-555555555555"),
            owner_id=payload.owner_id,
            public_key_id="pub_bulk",
            display_prefix="sk-slaif-pub_bulk",
            plaintext_key="sk-slaif-pub_bulk.plaintext-secret",
            one_time_secret_id=uuid.UUID("66666666-6666-4666-8666-666666666666"),
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            rate_limit_policy=payload.rate_limit_policy,
        )


class _FakeEmailDeliveryService:
    def __init__(self) -> None:
        self.calls = []

    async def create_pending_key_email_delivery(self, **kwargs):
        self.calls.append(kwargs)

        class _Result:
            email_delivery_id = uuid.UUID("77777777-7777-4777-8777-777777777777")
            status = "pending"

        return _Result()


@pytest.mark.asyncio
async def test_execute_key_import_plan_calls_key_service_and_returns_plaintext_once() -> None:
    preview = _preview([_valid_row(allowed_providers="", email_delivery_mode="pending")])
    plan = build_key_import_execution_plan(
        preview,
        actor_admin_id=ADMIN_ID,
        reason="bulk import",
        confirm_import=True,
        confirm_plaintext_display=True,
    )
    key_service = _FakeKeyService()
    email_service = _FakeEmailDeliveryService()

    result = await execute_key_import_plan(
        plan,
        key_service=key_service,  # type: ignore[arg-type]
        email_delivery_service=email_service,  # type: ignore[arg-type]
    )

    assert result.created_count == 1
    assert result.plaintext_display_count == 1
    assert result.pending_email_delivery_count == 1
    assert result.rows[0].plaintext_key == "sk-slaif-pub_bulk.plaintext-secret"
    assert result.rows[0].email_delivery_id == uuid.UUID("77777777-7777-4777-8777-777777777777")
    assert key_service.payloads[0].owner_id == OWNER_ID
    assert key_service.payloads[0].cost_limit_eur == Decimal("10.50")
    assert email_service.calls[0]["one_time_secret_id"] == uuid.UUID("66666666-6666-4666-8666-666666666666")


@pytest.mark.asyncio
async def test_execute_key_import_plan_suppresses_plaintext_for_enqueue() -> None:
    context = _context(email_delivery_enabled=True, celery_configured=True)
    preview = _preview([_valid_row(allowed_providers="", email_delivery_mode="enqueue")], context=context)
    plan = build_key_import_execution_plan(
        preview,
        actor_admin_id=ADMIN_ID,
        reason="bulk import",
        confirm_import=True,
        confirm_plaintext_display=False,
    )
    key_service = _FakeKeyService()
    email_service = _FakeEmailDeliveryService()

    result = await execute_key_import_plan(
        plan,
        key_service=key_service,  # type: ignore[arg-type]
        email_delivery_service=email_service,  # type: ignore[arg-type]
    )

    assert result.created_count == 1
    assert result.plaintext_display_count == 0
    assert result.rows[0].plaintext_key is None
    assert result.rows[0].email_delivery_id == uuid.UUID("77777777-7777-4777-8777-777777777777")
    assert result.rows[0].enqueue_status == "pending"


def test_enqueue_key_import_email_tasks_uses_ids_only() -> None:
    queued: list[dict[str, object]] = []
    delivery_id = uuid.UUID("77777777-7777-4777-8777-777777777777")
    secret_id = uuid.UUID("66666666-6666-4666-8666-666666666666")
    base = KeyImportExecutionResult(
        total_rows=1,
        created_count=1,
        invalid_count=0,
        rows=(
            KeyImportExecutionRow(
                row_number=1,
                action="created",
                one_time_secret_id=secret_id,
                email_delivery_id=delivery_id,
                email_delivery_mode="enqueue",
                enqueue_status="pending",
                plaintext_key=None,
            ),
        ),
    )

    def enqueue_func(**kwargs):
        queued.append(kwargs)
        return "task-123"

    result = enqueue_key_import_email_tasks(
        base,
        actor_admin_id=ADMIN_ID,
        enqueue_func=enqueue_func,
    )

    assert queued == [
        {
            "one_time_secret_id": secret_id,
            "email_delivery_id": delivery_id,
            "actor_admin_id": ADMIN_ID,
        }
    ]
    assert "plaintext" not in str(queued).lower()
    assert result.rows[0].enqueue_status == "queued"
    assert result.rows[0].email_delivery_status == "queued"
    assert result.rows[0].celery_task_id == "task-123"
    assert result.rows[0].plaintext_key is None
    assert result.queued_email_delivery_count == 1


def test_enqueue_key_import_email_tasks_handles_failure_safely() -> None:
    base = KeyImportExecutionResult(
        total_rows=1,
        created_count=1,
        invalid_count=0,
        rows=(
            KeyImportExecutionRow(
                row_number=1,
                action="created",
                one_time_secret_id=uuid.UUID("66666666-6666-4666-8666-666666666666"),
                email_delivery_id=uuid.UUID("77777777-7777-4777-8777-777777777777"),
                email_delivery_mode="enqueue",
                enqueue_status="pending",
                plaintext_key=None,
            ),
        ),
    )

    def enqueue_func(**kwargs):
        raise RuntimeError("broker contains sk-slaif-secret")

    result = enqueue_key_import_email_tasks(base, actor_admin_id=ADMIN_ID, enqueue_func=enqueue_func)

    assert result.rows[0].enqueue_status == "failed"
    assert "pending" in (result.rows[0].enqueue_error or "")
    assert "sk-slaif" not in (result.rows[0].enqueue_error or "")
    assert result.rows[0].plaintext_key is None

def test_execution_error_result_does_not_include_raw_content() -> None:
    result = key_import_execution_error_result("safe error")

    assert isinstance(result, KeyImportExecutionResult)
    assert result.invalid_count == 1
    assert "owner_email,valid_days" not in str(result)
    assert "token_hash" not in str(result)
    assert "encrypted_payload" not in str(result)

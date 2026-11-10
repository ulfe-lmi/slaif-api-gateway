"""216-a G14 reviewed accounting-recovery operations: focused proofs.

Pure-in-memory proofs for the new shared seams (no DB, no provider):

- the bounded accounting review intent: 500-CHARACTER Unicode reason law
  (original validated value preserved), 200-target bound, sealed hold
  no-charge choice, tamper/actor/session/purpose/expiry refusals, and the
  worst-case canonical-JSON bound;
- the relevant-source fingerprints (expired / provider-completed / hold)
  bind the reviewed relationships and recovery markers - and keep the
  gateway key's running balances OUT;
- the reviewed-target selection law (1..200, unique, exact);
- the batch apply bridge: fresh canonical row locks, ascending DISTINCT
  fresh key prelocks BEFORE any source check or settlement, changed-row
  whole-batch refusal (Core is never called), safe already-resolved
  no-ops, and the shared mutually-exclusive hold intent law (explicit
  no-charge confirmation, never inferred);
- the ASGI guards: disabled-dashboard 404, valid-auth/CSRF canaries to
  the intended guards, fixed safe refusals (selection/reason/alias/
  no-charge/conflict/superadmin/confirm), committed/refused/unconfirmed
  outcomes, and credential canaries absent from rendered HTML.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from slaif_gateway.api import admin_accounting_operations as ops
from slaif_gateway.api.admin_review_intent import (
    ACCOUNTING_REVIEW_MAX_TARGETS,
    AdminReviewIntentError,
    build_accounting_review_token,
    verify_accounting_review_token,
)
from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.schemas.external_tool_hold import ExternalToolHoldAction
from slaif_gateway.services.admin_accounting_operations import (
    ACTION_EXPIRED,
    ACTION_HOLD_FINALIZE,
    ACTION_HOLD_RELEASE,
    ACTION_PROVIDER_COMPLETED,
    PREVIEW_ELIGIBLE,
    AccountingOperationResult,
    AccountingReviewTarget,
    AccountingSelectionError,
    AccountingSourceChangedError,
    AdminAccountingOperationsService,
    fingerprint_expired_reservation,
    fingerprint_hold,
    fingerprint_provider_completed,
)
from slaif_gateway.schemas.external_tool_hold import ExternalToolHoldReconciliationInput
from slaif_gateway.services.reconciliation_errors import (
    ProviderCompletedRecoveryAlreadyReconciledError,
)
from slaif_gateway.services.admin_session_service import AdminSessionContext

SECRET_SHAPED = "sk-slaif-abcdef0123456789abcdef0123456789abcdef01"
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def _target_id() -> str:
    return str(uuid.uuid4())


def _fp() -> str:
    return uuid.uuid4().hex * 2  # 64-hex reviewed-source fingerprint shape


def _doc(
    action: str = ACTION_EXPIRED,
    targets: list[dict[str, str]] | None = None,
    assertions: dict[str, Any] | None = None,
    reason: str = "ops reconciliation",
    confirm_no_charge: bool | None = None,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "action": action,
        "targets": targets if targets is not None else [{"id": _target_id(), "fingerprint": _fp()}],
        "assertions": assertions,
        "reason": reason,
        "nonce": uuid.uuid4().hex,
    }
    if confirm_no_charge is not None:
        document["confirm_no_charge"] = confirm_no_charge
    return document


# ---------------------------------------------------------------------------
# Review-intent accounting purpose: 500-char Unicode reason law + seals
# ---------------------------------------------------------------------------


def test_accounting_review_reason_is_500_unicode_chars_not_bytes() -> None:
    # 500 astral code points = 2000 UTF-8 bytes: the law is CHARACTERS, not
    # bytes, so this is accepted and the original value is preserved verbatim.
    reason = "\U0001F600" * 500
    assert len(reason) == 500
    assert len(reason.encode("utf-8")) > 500
    admin_user_id = uuid.uuid4()
    admin_session_id = uuid.uuid4()
    token = build_accounting_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=admin_user_id,
        admin_session_id=admin_session_id,
        review_document=_doc(reason=reason),
    )
    document = verify_accounting_review_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=admin_user_id,
        admin_session_id=admin_session_id,
    )
    assert document["reason"] == reason


def test_accounting_review_roundtrip_preserves_reason_and_200_targets() -> None:
    admin_user_id = uuid.uuid4()
    admin_session_id = uuid.uuid4()
    targets = [{"id": _target_id(), "fingerprint": _fp()} for _ in range(200)]
    reason = "  ops " + "\U0001F600" * 493 + " "  # 500 chars, surrounding whitespace
    assert len(reason) == 500
    document = _doc(targets=targets, reason=reason)
    token = build_accounting_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=admin_user_id,
        admin_session_id=admin_session_id,
        review_document=document,
    )
    verified = verify_accounting_review_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=admin_user_id,
        admin_session_id=admin_session_id,
    )
    assert verified["reason"] == reason  # original validated value preserved
    assert verified["targets"] == targets


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(reason=""),
        lambda d: d.update(reason="   "),
        lambda d: d.update(reason="r" * 501),
        lambda d: d.update(reason="\U0001F600" * 501),
        lambda d: d.update(targets=[]),
        lambda d: d.update(targets=d["targets"] * 2 if False else d["targets"][:1] + d["targets"][:1]),
        lambda d: d.update(targets=[{"id": _target_id(), "fingerprint": _fp()} for _ in range(201)]),
        lambda d: d.update(targets=[{"id": "not-a-uuid", "fingerprint": _fp()}]),
        lambda d: d.update(targets=[{"id": _target_id(), "fingerprint": "zz" * 32}]),
        lambda d: d.update(assertions={"actual_cost_eur": "1", "actual_total_tokens": 1, "success": True}),
        lambda d: d.update(nonce="x" * 32),
        lambda d: d.update(extra_key=1),
        lambda d: d.pop("reason"),
    ],
)
def test_accounting_review_refuses_invalid_documents(mutate) -> None:
    document = _doc()
    mutate(document)
    with pytest.raises(AdminReviewIntentError):
        build_accounting_review_token(
            admin_session_secret="s" * 40,
            admin_user_id=uuid.uuid4(),
            admin_session_id=uuid.uuid4(),
            review_document=document,
        )


def test_accounting_review_worst_case_bound_fits_and_roundtrips() -> None:
    # 200 targets + a full 500-char astral Unicode reason: the documented
    # worst case must still fit the finite canonical-JSON envelope.
    document = _doc(
        targets=[{"id": _target_id(), "fingerprint": _fp()} for _ in range(ACCOUNTING_REVIEW_MAX_TARGETS)],
        reason="\U0001F600" * 500,
    )
    token = build_accounting_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=uuid.uuid4(),
        admin_session_id=uuid.uuid4(),
        review_document=document,
    )
    assert token


def test_accounting_review_overbound_token_refused() -> None:
    with pytest.raises(AdminReviewIntentError):
        verify_accounting_review_token(
            admin_session_secret="s" * 40,
            token="a" * 1_000_000,
            admin_user_id=uuid.uuid4(),
            admin_session_id=uuid.uuid4(),
        )


def test_accounting_review_refuses_wrong_actor_session_purpose_and_expiry() -> None:
    admin_user_id = uuid.uuid4()
    admin_session_id = uuid.uuid4()
    secret = "s" * 40
    token = build_accounting_review_token(
        admin_session_secret=secret,
        admin_user_id=admin_user_id,
        admin_session_id=admin_session_id,
        review_document=_doc(),
        now=NOW,
    )
    with pytest.raises(AdminReviewIntentError):
        verify_accounting_review_token(
            admin_session_secret=secret,
            token=token,
            admin_user_id=uuid.uuid4(),
            admin_session_id=admin_session_id,
        )
    with pytest.raises(AdminReviewIntentError):
        verify_accounting_review_token(
            admin_session_secret=secret,
            token=token,
            admin_user_id=admin_user_id,
            admin_session_id=uuid.uuid4(),
        )
    with pytest.raises(AdminReviewIntentError):
        verify_accounting_review_token(
            admin_session_secret="t" * 40,
            token=token,
            admin_user_id=admin_user_id,
            admin_session_id=admin_session_id,
        )
    # expired (15-minute bound, now past expiry)
    with pytest.raises(AdminReviewIntentError):
        verify_accounting_review_token(
            admin_session_secret=secret,
            token=token,
            admin_user_id=admin_user_id,
            admin_session_id=admin_session_id,
            now=NOW + timedelta(minutes=16),
        )
    # wrong purpose: an SMTP-test token is never an accounting seal
    from slaif_gateway.api.admin_review_intent import build_smtp_test_review_token

    from slaif_gateway.services.email_admin_operations import prepare_smtp_test_facts

    facts = prepare_smtp_test_facts(
        recipient="ops@example.invalid", subject="s", body="b", nonce=uuid.uuid4().hex
    )
    other = build_smtp_test_review_token(
        admin_session_secret=secret,
        admin_user_id=admin_user_id,
        admin_session_id=admin_session_id,
        review_document=facts.as_review_document(),
        now=NOW,
    )
    with pytest.raises(AdminReviewIntentError):
        verify_accounting_review_token(
            admin_session_secret=secret,
            token=other,
            admin_user_id=admin_user_id,
            admin_session_id=admin_session_id,
            now=NOW,
        )


def test_accounting_review_seals_hold_nocharge_choice() -> None:
    admin_user_id = uuid.uuid4()
    admin_session_id = uuid.uuid4()
    # release must seal True
    release = _doc(
        action=ACTION_HOLD_RELEASE,
        confirm_no_charge=True,
    )
    token = build_accounting_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=admin_user_id,
        admin_session_id=admin_session_id,
        review_document=release,
    )
    verified = verify_accounting_review_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=admin_user_id,
        admin_session_id=admin_session_id,
    )
    assert verified["confirm_no_charge"] is True
    assert verified["assertions"] is None

    # finalize must seal False + the three assertions
    finalize = _doc(
        action=ACTION_HOLD_FINALIZE,
        assertions={
            "actual_cost_eur": "1.25",
            "actual_total_tokens": 42,
            "success": True,
        },
        confirm_no_charge=False,
    )
    token = build_accounting_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=admin_user_id,
        admin_session_id=admin_session_id,
        review_document=finalize,
    )
    verified = verify_accounting_review_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=admin_user_id,
        admin_session_id=admin_session_id,
    )
    assert verified["confirm_no_charge"] is False

    # conflicting branches refuse: release with False, finalize with True,
    # release with assertions, hold with multiple targets, non-hold with the key.
    for bad in (
        _doc(action=ACTION_HOLD_RELEASE, confirm_no_charge=False),
        _doc(action=ACTION_HOLD_FINALIZE, confirm_no_charge=True),
        _doc(
            action=ACTION_HOLD_RELEASE,
            confirm_no_charge=True,
            assertions={"actual_cost_eur": "1", "actual_total_tokens": 1, "success": True},
        ),
        _doc(
            action=ACTION_HOLD_RELEASE,
            targets=[{"id": _target_id(), "fingerprint": _fp()} for _ in range(2)],
            confirm_no_charge=True,
        ),
        _doc(action=ACTION_EXPIRED, confirm_no_charge=True),
        _doc(action=ACTION_HOLD_RELEASE),  # missing sealed choice
    ):
        with pytest.raises(AdminReviewIntentError):
            build_accounting_review_token(
                admin_session_secret="s" * 40,
                admin_user_id=admin_user_id,
                admin_session_id=admin_session_id,
                review_document=bad,
            )


def test_accounting_review_tamper_refused() -> None:
    admin_user_id = uuid.uuid4()
    admin_session_id = uuid.uuid4()
    secret = "s" * 40
    document = _doc(
        action=ACTION_HOLD_FINALIZE,
        assertions={"actual_cost_eur": "1.00", "actual_total_tokens": 10, "success": True},
        confirm_no_charge=False,
    )
    token = build_accounting_review_token(
        admin_session_secret=secret,
        admin_user_id=admin_user_id,
        admin_session_id=admin_session_id,
        review_document=document,
    )
    body, _, digest = token.rpartition(".")
    # flip one character inside the sealed payload
    flipped = ("A" if body[50] != "A" else "B") + body[51:] + "." + digest
    with pytest.raises(AdminReviewIntentError):
        verify_accounting_review_token(
            admin_session_secret=secret,
            token=flipped,
            admin_user_id=admin_user_id,
            admin_session_id=admin_session_id,
        )


# ---------------------------------------------------------------------------
# Fingerprints: bind relationships/markers, exclude key running balances
# ---------------------------------------------------------------------------


def _fake_reservation(**overrides: Any) -> Any:
    base = dict(
        id=uuid.uuid4(),
        gateway_key_id=uuid.uuid4(),
        request_id="req-probe",
        status="pending",
        reserved_cost_eur=Decimal("1.50"),
        reserved_tokens=100,
        reserved_requests=1,
        quota_mode="ordinary",
        expires_at=NOW - timedelta(hours=1),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _fake_ledger(**overrides: Any) -> Any:
    base = dict(
        id=uuid.uuid4(),
        accounting_status="failed",
        actual_cost_eur=Decimal("0.75"),
        total_tokens=50,
        prompt_tokens=20,
        completion_tokens=30,
        success=None,
        quota_reservation_id=uuid.uuid4(),
        gateway_key_id=uuid.uuid4(),
        request_id="req-probe",
        response_metadata={"needs_reconciliation": True, "recovery_state": "provider_completed_finalization_failed"},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_expired_fingerprint_binds_relationships() -> None:
    base = _fake_reservation()
    base_fp = fingerprint_expired_reservation(base)
    for field, value in (
        ("gateway_key_id", uuid.uuid4()),
        ("request_id", "req-other"),
        ("status", "finalized"),
        ("reserved_cost_eur", Decimal("2.00")),
        ("reserved_tokens", 200),
        ("reserved_requests", 2),
        ("quota_mode", "external_tool_fenced"),
        ("expires_at", NOW),
    ):
        changed = fingerprint_expired_reservation(_fake_reservation(id=base.id, **{field: value}))
        assert changed != base_fp, field
    # same row -> same fingerprint
    assert fingerprint_expired_reservation(_fake_reservation(**{k: v for k, v in base.__dict__.items()})) == base_fp


def test_provider_fingerprint_binds_markers_and_linked_reservation() -> None:
    reservation = _fake_reservation()
    ledger = _fake_ledger(quota_reservation_id=reservation.id)
    base_fp = fingerprint_provider_completed(ledger, reservation)
    # recovery metadata markers
    for marker in (
        {"needs_reconciliation": False, "recovery_state": "provider_completed_finalization_failed"},
        {"needs_reconciliation": True, "recovery_state": "provider_completed_reconciled"},
    ):
        changed = fingerprint_provider_completed(
            _fake_ledger(quota_reservation_id=reservation.id, response_metadata=marker), reservation
        )
        assert changed != base_fp, marker
    # linked reservation facts
    for field, value in (
        ("status", "finalized"),
        ("reserved_cost_eur", Decimal("9.00")),
        ("reserved_tokens", 999),
        ("gateway_key_id", uuid.uuid4()),
        ("request_id", "req-other"),
    ):
        changed = fingerprint_provider_completed(ledger, _fake_reservation(id=reservation.id, **{field: value}))
        assert changed != base_fp, field
    # ledger facts
    for field, value in (
        ("accounting_status", "finalized"),
        ("actual_cost_eur", Decimal("1.00")),
        ("total_tokens", 100),
    ):
        changed = fingerprint_provider_completed(_fake_ledger(quota_reservation_id=reservation.id, **{field: value}), reservation)
        assert changed != base_fp, field


def test_hold_fingerprint_binds_reservation_ledger_and_fence() -> None:
    reservation = _fake_reservation(quota_mode="external_tool_fenced")
    ledger = _fake_ledger(accounting_status="estimated", success=None)
    key = SimpleNamespace(external_tool_fence_state="held")
    base_fp = fingerprint_hold(reservation, ledger, key)
    assert (
        fingerprint_hold(reservation, ledger, SimpleNamespace(external_tool_fence_state="none"))
        != base_fp
    )
    assert (
        fingerprint_hold(_fake_reservation(id=reservation.id, status="finalized"), ledger, key) != base_fp
    )
    assert (
        fingerprint_hold(reservation, _fake_ledger(id=ledger.id, accounting_status="finalized"), key)
        != base_fp
    )


# ---------------------------------------------------------------------------
# Selection law
# ---------------------------------------------------------------------------


def test_selection_bounds() -> None:
    good = [AccountingReviewTarget(id=uuid.uuid4(), fingerprint=_fp()) for _ in range(200)]
    AdminAccountingOperationsService  # noqa: B018 - symbol under test exists
    from slaif_gateway.services.admin_accounting_operations import _validate_selection

    _validate_selection(good)
    with pytest.raises(AccountingSelectionError):
        _validate_selection([])
    with pytest.raises(AccountingSelectionError):
        _validate_selection(good + [AccountingReviewTarget(id=uuid.uuid4(), fingerprint=_fp())])
    dup = [AccountingReviewTarget(id=uuid.uuid4(), fingerprint=_fp())]
    with pytest.raises(AccountingSelectionError):
        _validate_selection(dup * 2)


def test_exception_safe_message_base_contract() -> None:
    # Regression: a read-only safe_message property on the new subclass
    # used to make ReconciliationError.__init__ raise AttributeError (every
    # refusal path -> 500).
    exc = AccountingSourceChangedError()
    assert exc.safe_message
    assert exc.error_code == "accounting_source_changed"
    assert exc.status_code == 409
    sel = AccountingSelectionError()
    assert sel.error_code == "accounting_selection_invalid"
    assert sel.status_code == 400


# ---------------------------------------------------------------------------
# Batch apply bridge with fake repositories/services
# ---------------------------------------------------------------------------


class _FakeQuota:
    def __init__(self, rows: list[Any] | None = None, missing: bool = False) -> None:
        self.rows = rows or []
        self.missing = missing
        self.lock_order: list[str] = []

    async def get_reservations_by_ids_for_update(self, ids: list[uuid.UUID]) -> list[Any]:
        self.lock_order.append(f"reservations:{sorted(str(i) for i in ids)}")
        if self.missing:
            return list(self.rows[:-1])
        return list(self.rows)


class _FakeUsage:
    def __init__(self, ledgers: list[Any] | None = None, linked: list[Any] | None = None) -> None:
        self.ledgers = ledgers or []
        self.linked = linked or []
        self.lock_order: list[str] = []

    async def get_usage_records_by_ids_for_update(self, ids: list[uuid.UUID]) -> list[Any]:
        self.lock_order.append(f"ledgers:{sorted(str(i) for i in ids)}")
        return list(self.ledgers)

    async def get_usage_records_by_reservation_id(self, reservation_id: uuid.UUID) -> list[Any]:
        self.lock_order.append(f"linked-read:{reservation_id}")
        return list(self.linked)


class _FakeKeys:
    def __init__(self, keys: dict[uuid.UUID, Any] | None = None) -> None:
        self.keys = keys or {}
        self.lock_order: list[str] = []

    async def get_gateway_key_for_update(self, key_id: uuid.UUID):
        self.lock_order.append(f"key:{key_id}")
        return self.keys.get(key_id)


class _FakeReservationService:
    def __init__(self, raise_code: str | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.raise_code = raise_code

    async def reconcile_expired_pending_reservation(self, reservation_id, *, now=None, dry_run=False, actor_admin_id=None, reason=None):
        self.calls.append(
            {"id": reservation_id, "dry_run": dry_run, "actor_admin_id": actor_admin_id, "reason": reason}
        )
        return SimpleNamespace(
            new_status="expired",
            released_cost_eur=Decimal("1"),
            released_tokens=1,
            released_requests=1,
        )

    async def reconcile_provider_completed_recovery(
        self, *, usage_ledger_id=None, reservation_id=None, dry_run=True, actor_admin_id=None, reason=None, now=None
    ):
        self.calls.append({"id": usage_ledger_id, "dry_run": dry_run, "reason": reason})
        if self.raise_code == "already":
            raise ProviderCompletedRecoveryAlreadyReconciledError()
        return SimpleNamespace(new_accounting_status="finalized", used_cost_eur=Decimal("1"), used_tokens=1)


class _FakeHoldService:
    def __init__(self, idempotent: bool = False) -> None:
        self.calls: list[ExternalToolHoldReconciliationInput] = []
        self.idempotent = idempotent

    async def reconcile(self, request: ExternalToolHoldReconciliationInput):
        self.calls.append(request)
        return SimpleNamespace(
            reservation_id=request.reservation_id,
            usage_ledger_id=uuid.uuid4(),
            action=request.action.value,
            executed=request.execute,
            fence_state="none",
            reservation_status="finalized",
            accounting_status="finalized",
            actual_cost_eur=request.actual_cost_eur,
            actual_total_tokens=request.actual_total_tokens,
            success=request.success,
            idempotent=self.idempotent,
        )


def _service(
    *,
    quota: _FakeQuota | None = None,
    usage: _FakeUsage | None = None,
    keys: _FakeKeys | None = None,
    reservation: _FakeReservationService | None = None,
    hold: _FakeHoldService | None = None,
) -> AdminAccountingOperationsService:
    return AdminAccountingOperationsService(
        reservation_service=reservation or _FakeReservationService(),
        hold_service=hold or _FakeHoldService(),
        fence_service=SimpleNamespace(),
        quota_reservations_repository=quota or _FakeQuota(),
        usage_ledger_repository=usage or _FakeUsage(),
        keys_repository=keys or _FakeKeys(),
    )


def test_apply_expired_settles_and_key_prelock_order() -> None:
    key_b = uuid.uuid4()
    key_a = uuid.uuid4()
    while key_a >= key_b:
        key_a = uuid.uuid4()
    row_a = _fake_reservation(gateway_key_id=key_a)
    row_b = _fake_reservation(gateway_key_id=key_b)
    rows = [row_b, row_a]  # ascending id order for the fake
    rows.sort(key=lambda r: str(r.id))
    quota = _FakeQuota(rows=rows)
    keys = _FakeKeys({key_a: SimpleNamespace(), key_b: SimpleNamespace()})
    reservation = _FakeReservationService()
    service = _service(quota=quota, keys=keys, reservation=reservation)

    targets = [
        AccountingReviewTarget(id=row_b.id, fingerprint=fingerprint_expired_reservation(row_b)),
        AccountingReviewTarget(id=row_a.id, fingerprint=fingerprint_expired_reservation(row_a)),
    ]
    result = asyncio_run(service.apply_expired(targets=targets, actor_admin_id=uuid.uuid4(), reason="r"))
    assert result.committed and result.settled_count == 2
    # key locks: ascending key UUID, both AFTER all row locks, BEFORE Core
    key_positions = [i for i, entry in enumerate(quota.lock_order + keys.lock_order) if entry.startswith("key:")]
    assert key_positions, "keys were not prelocked"
    key_entries = [e for e in keys.lock_order]
    assert key_entries == [f"key:{key_a}", f"key:{key_b}"]
    assert len(reservation.calls) == 2
    assert all(call["reason"] == "r" for call in reservation.calls)


def test_apply_expired_changed_row_refuses_whole_batch_without_core() -> None:
    # 216 bridge regression: a 2-row batch where ONE row's relevant source
    # facts changed must refuse/rollback the WHOLE selection; Core is never
    # called for ANY row (no settled1/already1 mix).
    row_a = _fake_reservation()
    row_b = _fake_reservation()
    rows = sorted([row_a, row_b], key=lambda r: str(r.id))
    quota = _FakeQuota(rows=rows)
    keys = _FakeKeys({r.gateway_key_id: SimpleNamespace() for r in rows})
    reservation = _FakeReservationService()
    service = _service(quota=quota, keys=keys, reservation=reservation)

    # row_b's live status changed after the preview (fingerprint drift)
    row_b.status = "finalized"
    targets = [
        AccountingReviewTarget(id=rows[0].id, fingerprint=fingerprint_expired_reservation(rows[0])),
        AccountingReviewTarget(id=rows[1].id, fingerprint="0" * 64),  # stale
    ]
    with pytest.raises(AccountingSourceChangedError):
        asyncio_run(
            service.apply_expired(targets=targets, actor_admin_id=uuid.uuid4(), reason="r")
        )
    assert reservation.calls == []  # Core never called for any row


def test_apply_expired_unchanged_terminal_is_already_resolved() -> None:
    row = _fake_reservation(status="expired")
    quota = _FakeQuota(rows=[row])
    keys = _FakeKeys({row.gateway_key_id: SimpleNamespace()})
    reservation = _FakeReservationService()
    service = _service(quota=quota, keys=keys, reservation=reservation)
    result = asyncio_run(
        service.apply_expired(
            targets=[AccountingReviewTarget(id=row.id, fingerprint=fingerprint_expired_reservation(row))],
            actor_admin_id=uuid.uuid4(),
            reason="r",
        )
    )
    assert result.already_resolved_count == 1 and result.settled_count == 0
    assert reservation.calls == []


def test_apply_expired_missing_row_or_key_refuses() -> None:
    row = _fake_reservation()
    quota = _FakeQuota(rows=[row], missing=True)
    service = _service(quota=quota, keys=_FakeKeys({row.gateway_key_id: SimpleNamespace()}))
    with pytest.raises(AccountingSourceChangedError):
        asyncio_run(
            service.apply_expired(
                targets=[AccountingReviewTarget(id=row.id, fingerprint=fingerprint_expired_reservation(row))],
                actor_admin_id=uuid.uuid4(),
                reason="r",
            )
        )
    keys = _FakeKeys({})  # key vanished
    quota2 = _FakeQuota(rows=[row])
    service2 = _service(quota=quota2, keys=keys)
    with pytest.raises(AccountingSourceChangedError):
        asyncio_run(
            service2.apply_expired(
                targets=[AccountingReviewTarget(id=row.id, fingerprint=fingerprint_expired_reservation(row))],
                actor_admin_id=uuid.uuid4(),
                reason="r",
            )
        )


def test_apply_provider_completed_order_and_outcomes() -> None:
    reservation = _fake_reservation()
    ledger = _fake_ledger(quota_reservation_id=reservation.id, gateway_key_id=reservation.gateway_key_id)
    usage = _FakeUsage(ledgers=[ledger])
    quota = _FakeQuota(rows=[reservation])
    keys = _FakeKeys({reservation.gateway_key_id: SimpleNamespace()})
    core = _FakeReservationService()
    service = _service(quota=quota, usage=usage, keys=keys, reservation=core)
    target = AccountingReviewTarget(id=ledger.id, fingerprint=fingerprint_provider_completed(ledger, reservation))
    result = asyncio_run(
        service.apply_provider_completed(targets=[target], actor_admin_id=uuid.uuid4(), reason="r")
    )
    assert result.settled_count == 1
    # lock order: ledgers, then reservations, then keys (all before Core)
    assert usage.lock_order[0].startswith("ledgers:")
    assert quota.lock_order[0].startswith("reservations:")
    assert keys.lock_order[0].startswith("key:")
    assert len(core.calls) == 1 and core.calls[0]["dry_run"] is False


def test_apply_provider_completed_changed_source_refuses_before_core() -> None:
    reservation = _fake_reservation()
    ledger = _fake_ledger(quota_reservation_id=reservation.id, gateway_key_id=reservation.gateway_key_id)
    core = _FakeReservationService()
    service = _service(
        quota=_FakeQuota(rows=[reservation]),
        usage=_FakeUsage(ledgers=[ledger]),
        keys=_FakeKeys({reservation.gateway_key_id: SimpleNamespace()}),
        reservation=core,
    )
    target = AccountingReviewTarget(id=ledger.id, fingerprint="f" * 64)  # drifted
    with pytest.raises(AccountingSourceChangedError):
        asyncio_run(service.apply_provider_completed(targets=[target], actor_admin_id=uuid.uuid4(), reason="r"))
    assert core.calls == []


def test_apply_provider_completed_already_finalized_is_already_resolved() -> None:
    reservation = _fake_reservation(status="finalized")
    ledger = _fake_ledger(
        quota_reservation_id=reservation.id,
        gateway_key_id=reservation.gateway_key_id,
        accounting_status="finalized",
        response_metadata={"needs_reconciliation": False, "recovery_state": "provider_completed_reconciled"},
    )
    core = _FakeReservationService()
    service = _service(
        quota=_FakeQuota(rows=[reservation]),
        usage=_FakeUsage(ledgers=[ledger]),
        keys=_FakeKeys({reservation.gateway_key_id: SimpleNamespace()}),
        reservation=core,
    )
    target = AccountingReviewTarget(id=ledger.id, fingerprint=fingerprint_provider_completed(ledger, reservation))
    result = asyncio_run(service.apply_provider_completed(targets=[target], actor_admin_id=uuid.uuid4(), reason="r"))
    assert result.already_resolved_count == 1 and result.settled_count == 0
    assert core.calls == []


def test_apply_hold_lock_order_and_intent_law() -> None:
    reservation = _fake_reservation(quota_mode="external_tool_fenced")
    ledger = _fake_ledger(id=uuid.uuid4(), accounting_status="estimated", success=None)
    key_id = reservation.gateway_key_id
    usage = _FakeUsage(ledgers=[ledger], linked=[ledger])
    quota = _FakeQuota(rows=[reservation])
    keys = _FakeKeys({key_id: SimpleNamespace(external_tool_fence_state="held")})
    hold = _FakeHoldService()
    service = _service(quota=quota, usage=usage, keys=keys, hold=hold)
    target = AccountingReviewTarget(id=reservation.id, fingerprint=fingerprint_hold(reservation, ledger, SimpleNamespace(external_tool_fence_state="held")))

    # release requires the explicit sealed confirmation and no actual fields
    with pytest.raises(AccountingSelectionError):
        asyncio_run(
            service.apply_hold(
                target=target,
                action=ExternalToolHoldAction.RELEASE_NO_CHARGE,
                actual_cost_eur=None,
                actual_total_tokens=None,
                success=None,
                confirm_no_charge=False,
                actor_admin_id=uuid.uuid4(),
                reason="r",
            )
        )
    with pytest.raises(AccountingSelectionError):
        asyncio_run(
            service.apply_hold(
                target=target,
                action=ExternalToolHoldAction.RELEASE_NO_CHARGE,
                actual_cost_eur=Decimal("1"),
                actual_total_tokens=None,
                success=None,
                confirm_no_charge=True,
                actor_admin_id=uuid.uuid4(),
                reason="r",
            )
        )
    with pytest.raises(AccountingSelectionError):
        asyncio_run(
            service.apply_hold(
                target=target,
                action=ExternalToolHoldAction.FINALIZE_ACTUAL,
                actual_cost_eur=Decimal("1"),
                actual_total_tokens=5,
                success=True,
                confirm_no_charge=True,
                actor_admin_id=uuid.uuid4(),
                reason="r",
            )
        )
    with pytest.raises(AccountingSelectionError):
        asyncio_run(
            service.apply_hold(
                target=target,
                action=ExternalToolHoldAction.FINALIZE_ACTUAL,
                actual_cost_eur=None,
                actual_total_tokens=None,
                success=None,
                confirm_no_charge=False,
                actor_admin_id=uuid.uuid4(),
                reason="r",
            )
        )
    assert hold.calls == []

    # valid release: locks ledger -> reservation -> key, Core sees the sealed choice
    result = asyncio_run(
        service.apply_hold(
            target=target,
            action=ExternalToolHoldAction.RELEASE_NO_CHARGE,
            actual_cost_eur=None,
            actual_total_tokens=None,
            success=None,
            confirm_no_charge=True,
            actor_admin_id=uuid.uuid4(),
            reason="r",
        )
    )
    assert result.settled_count == 1
    assert hold.calls[0].confirm_no_charge is True
    assert usage.lock_order[0].startswith("linked-read:")
    assert usage.lock_order[1].startswith("ledgers:")
    assert quota.lock_order[0].startswith("reservations:")
    assert keys.lock_order[0].startswith("key:")

    # drifted source: refused BEFORE Core
    hold2 = _FakeHoldService()
    service2 = _service(
        quota=_FakeQuota(rows=[_fake_reservation(id=reservation.id, quota_mode="external_tool_fenced", status="finalized")]),
        usage=_FakeUsage(ledgers=[ledger], linked=[ledger]),
        keys=_FakeKeys({key_id: SimpleNamespace(external_tool_fence_state="held")}),
        hold=hold2,
    )
    with pytest.raises(AccountingSourceChangedError):
        asyncio_run(
            service2.apply_hold(
                target=target,
                action=ExternalToolHoldAction.RELEASE_NO_CHARGE,
                actual_cost_eur=None,
                actual_total_tokens=None,
                success=None,
                confirm_no_charge=True,
                actor_admin_id=uuid.uuid4(),
                reason="r",
            )
        )
    assert hold2.calls == []

    # vanished locked ledger: the plain pre-read still sees the linked row,
    # but the fresh locked read returns [] -> safe refusal BEFORE indexing,
    # before the reservation lock, and with no Core call.
    hold3 = _FakeHoldService()
    quota3 = _FakeQuota(rows=[reservation])
    service3 = _service(
        quota=quota3,
        usage=_FakeUsage(ledgers=[], linked=[ledger]),
        keys=_FakeKeys({key_id: SimpleNamespace(external_tool_fence_state="held")}),
        hold=hold3,
    )
    with pytest.raises(AccountingSourceChangedError):
        asyncio_run(
            service3.apply_hold(
                target=target,
                action=ExternalToolHoldAction.RELEASE_NO_CHARGE,
                actual_cost_eur=None,
                actual_total_tokens=None,
                success=None,
                confirm_no_charge=True,
                actor_admin_id=uuid.uuid4(),
                reason="r",
            )
        )
    assert hold3.calls == []
    assert quota3.lock_order == []


def test_apply_hold_idempotent_maps_already_resolved() -> None:
    reservation = _fake_reservation(quota_mode="external_tool_fenced")
    ledger = _fake_ledger(accounting_status="estimated", success=None)
    key_id = reservation.gateway_key_id
    hold = _FakeHoldService(idempotent=True)
    service = _service(
        quota=_FakeQuota(rows=[reservation]),
        usage=_FakeUsage(ledgers=[ledger], linked=[ledger]),
        keys=_FakeKeys({key_id: SimpleNamespace(external_tool_fence_state="held")}),
        hold=hold,
    )
    target = AccountingReviewTarget(
        id=reservation.id, fingerprint=fingerprint_hold(reservation, ledger, SimpleNamespace(external_tool_fence_state="held"))
    )
    result = asyncio_run(
        service.apply_hold(
            target=target,
            action=ExternalToolHoldAction.RELEASE_NO_CHARGE,
            actual_cost_eur=None,
            actual_total_tokens=None,
            success=None,
            confirm_no_charge=True,
            actor_admin_id=uuid.uuid4(),
            reason="r",
        )
    )
    assert result.already_resolved_count == 1 and result.settled_count == 0


def asyncio_run(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# ASGI guards: canaries must reach the intended guards; fixed safe refusals
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, owner: "_FakeSessionmaker") -> None:
        self._owner = owner
        # The apply route builds its service on the MUTATION session; the
        # commit-ack fault must fire on that transaction's commit only (the
        # auth read scope commits cleanly, as it does natively).
        self.mutating = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def begin(self):
        return _FakeBegin(self, self._owner)


class _FakeBegin:
    """One transaction: the commit-ack fault is a ONE-SHOT flag.

    Only the MUTATION transaction (the session the apply route built its
    service on) loses its commit acknowledgement when
    ``fail_next_commit`` was armed before the POST - and only after its
    apply already ran. Read scopes (e.g. admin-session validation) always
    commit cleanly, matching native behavior.
    """

    def __init__(self, session: "_FakeSession", owner: "_FakeSessionmaker") -> None:
        self._session = session
        self._owner = owner

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None and self._owner.fail_next_commit and self._session.mutating:
            self._owner.fail_next_commit = False
            raise RuntimeError("commit ack lost (fixture)")
        return None


class _FakeSessionmaker:
    def __init__(self) -> None:
        self.fail_next_commit = False

    def __call__(self):
        return _FakeSession(self)


def _asgi_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://user:secret@localhost:5432/test_db",
        "ADMIN_SESSION_SECRET": "s" * 40,
        "GATEWAY_KEY_PREFIX": "sk-slaif-",
        "GATEWAY_KEY_ACCEPTED_PREFIXES": "sk-slaif-",
        "ENABLE_ADMIN_DASHBOARD": True,
    }
    values.update(overrides)
    return Settings(**values)


def _asgi_app(settings: Settings | None = None) -> Any:
    app = create_app(settings or _asgi_settings())
    app.state.db_sessionmaker = _FakeSessionmaker()
    return app


def _admin_user(role: str = "superadmin") -> AdminUser:
    return AdminUser(
        id=uuid.uuid4(),
        email="admin-216@example.org",
        display_name="216 Admin",
        password_hash="argon2-hash",
        role=role,
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


def _login(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    *,
    role: str = "superadmin",
    valid_csrf: str = "csrf-216",
) -> tuple[AdminUser, AdminSession]:
    admin_user = _admin_user(role)
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs: Any) -> AdminSessionContext:
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    def verify_session_csrf_token(self, admin_session_row: Any, csrf_token: str) -> bool:
        return csrf_token == valid_csrf

    async def refresh_csrf_token(self, *, admin_session_id):
        return "page-csrf-216"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    client.cookies.set("slaif_admin_session", "session-plaintext")
    return admin_user, admin_session


class _FakeAccountingService:
    """Canned read/preview/apply results (no DB)."""

    def __init__(self) -> None:
        self.key = uuid.uuid4()
        self.reservation = SimpleNamespace(
            id=uuid.uuid4(),
            gateway_key_id=self.key,
            request_id="req-" + "a" * 24,
            status="pending",
            reserved_cost_eur=Decimal("1.50"),
            reserved_tokens=3_000_000,
            reserved_requests=1,
            expires_at=NOW,
            created_at=NOW,
            requires_external_tool_review=False,
        )
        self.ledger = SimpleNamespace(
            id=uuid.uuid4(),
            usage_ledger_id=None,  # filled below (candidate-shaped projection)
            reservation_id=self.reservation.id,
            gateway_key_id=self.key,
            request_id="req-" + "a" * 24,
            provider="probe-provider",
            requested_model="probe-model",
            resolved_model=None,
            endpoint="chat/completions",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            estimated_cost_eur=Decimal("0.1"),
            actual_cost_eur=Decimal("0.12"),
            created_at=NOW,
            recovery_state="provider_completed_finalization_failed",
        )
        self.ledger.usage_ledger_id = self.ledger.id
        self.hold = SimpleNamespace(
            gateway_key_id=self.key,
            reservation_id=self.reservation.id,
            usage_ledger_id=self.ledger.id,
            request_id="req-" + "b" * 24,
            fence_state="held",
            accounting_status="estimated",
            reason_code="missing_final_usage",
            evidence_quality="partial_estimate",
            held_at=NOW,
            created_at=NOW,
            expires_at=None,
            provider="probe-provider",
            endpoint="chat/completions",
            requested_model="probe-model",
            reserved_cost_eur=Decimal("2"),
            reserved_tokens=4_000_000,
            reserved_requests=1,
            partial_total_tokens=None,
            estimated_cost_eur=None,
        )
        self.fence = SimpleNamespace(
            gateway_key_id=self.key,
            fence_state="held",
            reservation_id=self.reservation.id,
            request_id="req-" + "c" * 24,
            acquired_at=NOW,
            expires_at=None,
        )
        self.preview_calls: list[str] = []
        self.apply_calls: list[str] = []
        self.apply_outcome: str = "committed"

    async def list_expired_candidates(self, *, limit: int = 100):
        return [self.reservation]

    async def list_fence_candidates(self, *, limit: int = 100):
        return [self.fence]

    async def list_hold_candidates(self, *, limit: int = 100):
        return [self.hold]

    async def list_provider_completed_candidates(self, *, limit: int = 100, provider=None, model=None, gateway_key_id=None):
        return [self.ledger]

    async def preview_expired(self, reservation_ids, *, now=None):
        self.preview_calls.append("expired")
        return [
            SimpleNamespace(
                id=i,
                fingerprint=_fp(),
                proposal=PREVIEW_ELIGIBLE,
                safe_detail="would_release",
                action_label="Release the reserved amounts",
                observed={"status": "pending", "quota_mode": "token", "expires_at": "2026-11-01T00:00:00+00:00"},
                proposed={},
                observed_tokens=3_000_000,
                observed_requests=2,
                observed_cost_eur="12.5",
                proposed_tokens=3_000_000,
                proposed_requests=2,
                proposed_cost_eur="12.5",
            )
            for i in reservation_ids
        ]

    async def preview_provider_completed(self, usage_ledger_ids, *, now=None):
        self.preview_calls.append("provider_completed")
        return [
            SimpleNamespace(
                id=i,
                fingerprint=_fp(),
                proposal=PREVIEW_ELIGIBLE,
                safe_detail="would_finalize",
                action_label="Finalize from stored evidence",
                observed={"accounting_status": "estimated", "provider": "probe-provider"},
                proposed={},
                observed_tokens=30,
                observed_requests=None,
                observed_cost_eur="0.01",
                proposed_tokens=30,
                proposed_requests=None,
                proposed_cost_eur="0.01",
            )
            for i in usage_ledger_ids
        ]

    async def preview_hold(self, reservation_id, *, action, actual_cost_eur, actual_total_tokens, success, confirm_no_charge):
        self.preview_calls.append("hold")
        return SimpleNamespace(
            id=reservation_id,
            fingerprint=_fp(),
            proposal=PREVIEW_ELIGIBLE,
            safe_detail="would_reconcile",
            action_label="Hold reconcile",
            observed={"fence_state": "held", "accounting_status": "estimated"},
            proposed={"proposed_success": success} if success is not None else {},
            observed_tokens=100,
            observed_requests=1,
            observed_cost_eur="0.02",
            proposed_tokens=actual_total_tokens,
            proposed_requests=None,
            proposed_cost_eur=str(actual_cost_eur) if actual_cost_eur is not None else None,
        )

    async def apply_expired(self, *, targets, actor_admin_id, reason, now=None):
        self.apply_calls.append("expired")
        if self.apply_outcome == "refused":
            raise AccountingSourceChangedError()
        return AccountingOperationResult(
            action=ACTION_EXPIRED,
            target_count=len(targets),
            settled_count=len(targets),
            already_resolved_count=0,
            committed=True,
            unconfirmed=False,
            outcomes=tuple(
                SimpleNamespace(id=t.id, status="settled", safe_detail="released") for t in targets
            ),
        )

    async def apply_provider_completed(self, *, targets, actor_admin_id, reason, now=None):
        self.apply_calls.append("provider_completed")
        if self.apply_outcome == "refused":
            raise AccountingSourceChangedError()
        return AccountingOperationResult(
            action=ACTION_PROVIDER_COMPLETED,
            target_count=len(targets),
            settled_count=len(targets),
            already_resolved_count=0,
            committed=True,
            unconfirmed=False,
            outcomes=tuple(
                SimpleNamespace(id=t.id, status="settled", safe_detail="finalized") for t in targets
            ),
        )

    async def apply_hold(self, *, target, action, actual_cost_eur, actual_total_tokens, success, confirm_no_charge, actor_admin_id, reason):
        self.apply_calls.append("hold")
        if self.apply_outcome == "refused":
            raise AccountingSourceChangedError()
        return AccountingOperationResult(
            action=action.value,
            target_count=1,
            settled_count=1,
            already_resolved_count=0,
            committed=True,
            unconfirmed=False,
            outcomes=(SimpleNamespace(id=target.id, status="settled", safe_detail="reconciled"),),
        )


def test_dashboard_disabled_refuses_all_accounting_routes(monkeypatch) -> None:
    app = _asgi_app(_asgi_settings(ENABLE_ADMIN_DASHBOARD=False))
    with TestClient(app) as client:
        for path in (
            "/admin/accounting-operations/",
            "/admin/accounting-operations/expired-reservations",
            "/admin/accounting-operations/external-tool-fences",
            "/admin/accounting-operations/external-tool-holds",
            "/admin/accounting-operations/provider-completed-recovery",
        ):
            assert client.get(path).status_code == 404
        assert (
            client.post("/admin/accounting-operations/expired-reservations/preview", data={}).status_code == 404
        )


def test_accounting_views_render_and_guard(monkeypatch) -> None:
    app = _asgi_app()
    fake = _FakeAccountingService()
    monkeypatch.setattr(ops, "_build_service", lambda session: fake)
    monkeypatch.setattr(ops, "load_choices", _fake_load_choices)
    with TestClient(app) as client:
        _login(monkeypatch, client)
        for path, marker in (
            ("/admin/accounting-operations/", "Accounting Operations"),
            ("/admin/accounting-operations/expired-reservations", "Expired pending reservations"),
            ("/admin/accounting-operations/external-tool-fences", "Read-only view"),
            ("/admin/accounting-operations/external-tool-holds", "External-tool accounting holds"),
            ("/admin/accounting-operations/provider-completed-recovery", "Provider-completed"),
        ):
            response = client.get(path)
            assert response.status_code == 200, path
            assert marker in response.text
        # beyond-cap exact-selection pickers are present
        expired = client.get("/admin/accounting-operations/expired-reservations").text
        assert 'name="exact_reservation_id"' in expired
        provider = client.get("/admin/accounting-operations/provider-completed-recovery").text
        assert 'name="exact_ledger_id"' in provider
        holds = client.get("/admin/accounting-operations/external-tool-holds").text
        assert 'name="exact_reservation_id"' in holds and 'name="confirm_no_charge"' in holds


async def _fake_load_choices(session, kind, **kwargs):
    return []


def test_expired_preview_reason_and_selection_negatives(monkeypatch) -> None:
    app = _asgi_app()
    fake = _FakeAccountingService()
    monkeypatch.setattr(ops, "_build_service", lambda session: fake)
    monkeypatch.setattr(ops, "load_choices", _fake_load_choices)
    with TestClient(app) as client:
        _login(monkeypatch, client)
        rid = str(fake.reservation.id)
        base = {"csrf_token": "csrf-216", "target_id": rid}
        # no selection
        assert client.post("/admin/accounting-operations/expired-reservations/preview", data={"csrf_token": "csrf-216"}).status_code == 400
        # blank reason
        response = client.post("/admin/accounting-operations/expired-reservations/preview", data={**base, "reason": "  "})
        assert response.status_code == 400
        assert "reason" in response.text
        # 501-char Unicode reason
        response = client.post(
            "/admin/accounting-operations/expired-reservations/preview",
            data={**base, "reason": "\U0001F600" * 501},
        )
        assert response.status_code == 400
        # known incoming authentication alias in the reason
        response = client.post("/admin/accounting-operations/expired-reservations/preview", data={**base, "reason": SECRET_SHAPED})
        assert response.status_code == 400
        # valid preview signs the review (200 + token field)
        response = client.post("/admin/accounting-operations/expired-reservations/preview", data={**base, "reason": "ops"})
        assert response.status_code == 200
        assert 'name="review_token"' in response.text
        # 216 review display: separately sortable token/request/cost columns
        # with raw sort keys, plain labels, and a plain intended action; the
        # dry-run status is a CURRENT fact (observed), never a proposed
        # post-apply state, and no raw underscore field names render.
        assert "Tokens (observed)" in response.text
        assert "Requests (observed)" in response.text
        assert "Tokens (if applied)" in response.text
        assert "Intended action" in response.text
        assert "Release the reserved amounts" in response.text
        assert 'data-sort-value="3000000"' in response.text
        assert 'data-sort-value="12.5"' in response.text
        assert "3M" in response.text
        assert "reserved_cost_eur" not in response.text
        assert "new_status" not in response.text
        # 201 targets -> fixed selection refusal
        items = [(("target_id", str(uuid.uuid4())),) for _ in range(201)]
        response = client.post(
            "/admin/accounting-operations/expired-reservations/preview",
            data=[item for group in items for item in group],
        )
        assert response.status_code == 400


def test_hold_preview_intent_negatives(monkeypatch) -> None:
    app = _asgi_app()
    fake = _FakeAccountingService()
    monkeypatch.setattr(ops, "_build_service", lambda session: fake)
    monkeypatch.setattr(ops, "load_choices", _fake_load_choices)
    with TestClient(app) as client:
        _login(monkeypatch, client)
        rid = str(fake.reservation.id)
        base = {
            "csrf_token": "csrf-216",
            "reservation_id": rid,
            "hold_action": "release-no-charge",
            "reason": "ops",
        }
        # release without the explicit no-charge confirmation
        response = client.post("/admin/accounting-operations/external-tool-holds/preview", data=base)
        assert response.status_code == 400
        # release WITH cost fields -> conflicting branch
        response = client.post(
            "/admin/accounting-operations/external-tool-holds/preview",
            data={**base, "confirm_no_charge": "1", "actual_cost_eur": "1.00"},
        )
        assert response.status_code == 400
        # finalize WITH the no-charge checkbox -> conflicting branch
        response = client.post(
            "/admin/accounting-operations/external-tool-holds/preview",
            data={
                "csrf_token": "csrf-216",
                "reservation_id": rid,
                "hold_action": "finalize-actual",
                "actual_cost_eur": "1.00",
                "actual_total_tokens": "10",
                "outcome": "success",
                "confirm_no_charge": "1",
                "reason": "ops",
            },
        )
        assert response.status_code == 400
        # finalize missing the explicit outcome
        response = client.post(
            "/admin/accounting-operations/external-tool-holds/preview",
            data={
                "csrf_token": "csrf-216",
                "reservation_id": rid,
                "hold_action": "finalize-actual",
                "actual_cost_eur": "1.00",
                "actual_total_tokens": "10",
                "reason": "ops",
            },
        )
        assert response.status_code == 400
        # known numeric bearer alias carried into a manual assertion
        response = client.post(
            "/admin/accounting-operations/external-tool-holds/preview",
            data={
                "csrf_token": "csrf-216",
                "reservation_id": rid,
                "hold_action": "finalize-actual",
                "actual_cost_eur": "1.00",
                "actual_total_tokens": SECRET_SHAPED,
                "outcome": "success",
                "reason": "ops",
            },
        )
        assert response.status_code == 400
        assert SECRET_SHAPED not in response.text
        # radio AND exact-record at once -> conflict
        response = client.post(
            "/admin/accounting-operations/external-tool-holds/preview",
            data={**base, "confirm_no_charge": "1", "exact_reservation_id": rid},
        )
        assert response.status_code == 400
        # valid release preview signs the review
        response = client.post(
            "/admin/accounting-operations/external-tool-holds/preview",
            data={**base, "confirm_no_charge": "1"},
        )
        assert response.status_code == 200
        assert 'name="review_token"' in response.text
        # hold review display: sortable observed columns + plain intended
        # action; the dry-run reservation/accounting statuses remain observed
        # current facts (never a "new" state).
        assert "Tokens (observed)" in response.text
        assert "Intended action" in response.text
        assert "Hold reconcile" in response.text
        assert "new_accounting_status" not in response.text
        assert "new_reservation_status" not in response.text
        assert SECRET_SHAPED not in response.text


def test_apply_role_and_seal_guards(monkeypatch) -> None:
    app = _asgi_app()
    fake = _FakeAccountingService()
    monkeypatch.setattr(ops, "_build_service", lambda session: fake)
    monkeypatch.setattr(ops, "load_choices", _fake_load_choices)
    with TestClient(app) as client:
        # non-superadmin: valid auth/CSRF still refused (403)
        admin_user, admin_session = _login(monkeypatch, client, role="admin")
        response = client.post(
            "/admin/accounting-operations/expired-reservations/apply",
            data={"csrf_token": "csrf-216", "review_token": "x", "confirm_apply": "1"},
        )
        assert response.status_code == 403
        # superadmin with a garbage seal
        admin_user, admin_session = _login(monkeypatch, client, role="superadmin")
        response = client.post(
            "/admin/accounting-operations/expired-reservations/apply",
            data={"csrf_token": "csrf-216", "review_token": "garbage", "confirm_apply": "1"},
        )
        assert response.status_code == 400
        # wrong family: an expired seal on the hold apply route
        settings = _asgi_settings()
        target_id = str(uuid.uuid4())
        document = {
            "action": ACTION_EXPIRED,
            "targets": [{"id": target_id, "fingerprint": _fp()}],
            "assertions": None,
            "reason": "ops",
            "nonce": uuid.uuid4().hex,
        }
        token = build_accounting_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=admin_user.id,
            admin_session_id=admin_session.id,
            review_document=document,
        )
        response = client.post(
            "/admin/accounting-operations/external-tool-holds/apply",
            data={"csrf_token": "csrf-216", "review_token": token, "confirm_apply": "1"},
        )
        assert response.status_code == 400
        # missing confirmation: re-render with the fixed confirm error, no apply
        response = client.post(
            "/admin/accounting-operations/expired-reservations/apply",
            data={"csrf_token": "csrf-216", "review_token": token},
        )
        assert response.status_code == 200
        assert "confirm" in response.text.lower()
        assert fake.apply_calls == []


def test_apply_committed_refused_unconfirmed_outcomes(monkeypatch) -> None:
    app = _asgi_app()
    fake = _FakeAccountingService()
    monkeypatch.setattr(ops, "_build_service", lambda session: fake)
    monkeypatch.setattr(ops, "load_choices", _fake_load_choices)
    with TestClient(app) as client:
        # The TestClient lifespan startup replaces the pre-startup fake
        # sessionmaker with a real idle one; the unit transaction-fault hooks
        # require the fake, so it is reinstalled AFTER lifespan startup
        # (production lifespan/session code is unchanged).
        fake_sessionmaker = _FakeSessionmaker()
        app.state.db_sessionmaker = fake_sessionmaker
        assert isinstance(app.state.db_sessionmaker, _FakeSessionmaker)
        admin_user, admin_session = _login(monkeypatch, client, role="superadmin")
        settings = _asgi_settings()
        target_id = str(uuid.uuid4())
        document = {
            "action": ACTION_EXPIRED,
            "targets": [{"id": target_id, "fingerprint": _fp()}],
            "assertions": None,
            "reason": "ops",
            "nonce": uuid.uuid4().hex,
        }
        token = build_accounting_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=admin_user.id,
            admin_session_id=admin_session.id,
            review_document=document,
        )
        # committed
        response = client.post(
            "/admin/accounting-operations/expired-reservations/apply",
            data={"csrf_token": "csrf-216", "review_token": token, "confirm_apply": "1"},
        )
        assert response.status_code == 200
        assert "settled" in response.text
        assert fake.apply_calls == ["expired"]
        # refused (source changed at the seam)
        fake.apply_outcome = "refused"
        token2 = build_accounting_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=admin_user.id,
            admin_session_id=admin_session.id,
            review_document={**document, "nonce": uuid.uuid4().hex},
        )
        response = client.post(
            "/admin/accounting-operations/expired-reservations/apply",
            data={"csrf_token": "csrf-216", "review_token": token2, "confirm_apply": "1"},
        )
        assert response.status_code == 200
        assert "refused" in response.text or "refused" in response.text.lower()
        # unconfirmed (commit acknowledgement lost AFTER mutation)
        fake.apply_outcome = "committed"
        # Arm the ONE-SHOT commit-ack fault on the unit sessionmaker: only
        # the mutation transaction (marked by the apply-route service build)
        # loses its acknowledgement, after the apply already ran; the auth
        # read scope commits cleanly, matching native behavior.
        def _armed_build_service(session):
            session.mutating = True
            return fake

        monkeypatch.setattr(ops, "_build_service", _armed_build_service)
        fake_sessionmaker.fail_next_commit = True
        token3 = build_accounting_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=admin_user.id,
            admin_session_id=admin_session.id,
            review_document={**document, "nonce": uuid.uuid4().hex},
        )
        response = client.post(
            "/admin/accounting-operations/expired-reservations/apply",
            data={"csrf_token": "csrf-216", "review_token": token3, "confirm_apply": "1"},
        )
        assert response.status_code == 200
        # The unconfirmed message is honest: lost commit acknowledgement,
        # explicitly NOT a rollback guarantee.
        assert "commit acknowledgement" in response.text
        assert "NOT a rollback" in response.text
        # The one-shot fault fired exactly once, at the mutation commit.
        assert fake_sessionmaker.fail_next_commit is False


def test_apply_sealed_alias_reason_refused_before_render(monkeypatch) -> None:
    app = _asgi_app()
    fake = _FakeAccountingService()
    monkeypatch.setattr(ops, "_build_service", lambda session: fake)
    monkeypatch.setattr(ops, "load_choices", _fake_load_choices)
    with TestClient(app) as client:
        admin_user, admin_session = _login(monkeypatch, client, role="superadmin")
        settings = _asgi_settings()
        document = {
            "action": ACTION_EXPIRED,
            "targets": [{"id": str(uuid.uuid4()), "fingerprint": _fp()}],
            "assertions": None,
            "reason": f"rotated {SECRET_SHAPED} for ops",
            "nonce": uuid.uuid4().hex,
        }
        # a seal with an alias-shaped reason is itself buildable (the builder
        # does not know request aliases); the APPLY guard must refuse it.
        token = build_accounting_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=admin_user.id,
            admin_session_id=admin_session.id,
            review_document=document,
        )
        response = client.post(
            "/admin/accounting-operations/expired-reservations/apply",
            data={"csrf_token": "csrf-216", "review_token": token, "confirm_apply": "1"},
        )
        assert response.status_code == 400
        assert SECRET_SHAPED not in response.text
        assert fake.apply_calls == []


# ---------------------------------------------------------------------------
# Shared record-choice seam: credential-shaped model tokens are withheld
# (216-a provider-view picker leak fix; initial render AND AJAX hydration)
# ---------------------------------------------------------------------------


class _ModelChoiceStubSession:
    """Stub async session: every grouped model source returns the same
    (model, latest) rows (the ``model`` branch de-duplicates by token)."""

    def __init__(self, rows: list[tuple[Any, Any]]) -> None:
        self._rows = list(rows)

    async def execute(self, _stmt: Any) -> Any:
        rows = self._rows

        class _Result:
            def all(self) -> list[tuple[Any, Any]]:
                return rows

        return _Result()


def test_model_choice_seam_withholds_credential_tokens() -> None:
    from slaif_gateway.services.admin_record_choices import load_choices

    session = _ModelChoiceStubSession(
        [
            (SECRET_SHAPED, None),
            ("model-hold-216", None),
            ("gpt-4o", None),
            (None, None),  # NULL models never become choices
        ]
    )
    choices = asyncio_run(
        load_choices(session, "model", accepted_prefixes=("sk-slaif-",))
    )
    labels = [c.label for c in choices]
    # Ordinary model tokens remain selectable (the guard is not a blanket
    # mask of the picker)...
    assert "model-hold-216" in labels
    assert "gpt-4o" in labels
    # ...while the credential-shaped token is withheld entirely: a masked
    # placeholder never becomes a selectable identity.
    assert SECRET_SHAPED not in labels
    assert SECRET_SHAPED not in [c.id for c in choices]


def test_model_choice_seam_withholds_selected_hydration_too() -> None:
    from slaif_gateway.services.admin_record_choices import load_choices

    # The plain-value selected re-hydration path (a selected value outside
    # the initial batch) must NOT re-insert a withheld credential-shaped
    # token, while an ORDINARY older value still hydrates (positive
    # control: the guard is bounded to secret-shaped model tokens).
    session = _ModelChoiceStubSession([("gpt-4o", None)])
    choices = asyncio_run(
        load_choices(
            session,
            "model",
            selected=(SECRET_SHAPED, "older-model-216"),
            accepted_prefixes=("sk-slaif-",),
        )
    )
    labels = [c.label for c in choices]
    assert SECRET_SHAPED not in labels
    assert SECRET_SHAPED not in [c.id for c in choices]
    assert "older-model-216" in labels  # ordinary older value hydrates
    assert "gpt-4o" in labels  # ordinary in-batch token preserved

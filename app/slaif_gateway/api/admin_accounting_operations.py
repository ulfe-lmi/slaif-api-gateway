"""Reviewed accounting-recovery router (216-a: G14).

Bounded admin GUI surfaces under ``/admin/accounting-operations`` that reuse
the shared Core reconciliation services (see :mod:`slaif_gateway.services.
admin_accounting_operations`). Four read-only candidate views and four
reviewed recovery action families:

- expired pending reservations (reconcile one or a bounded selection);
- external-tool accounting holds (finalize-actual or release-no-charge,
  single target with explicit operator assertions);
- provider-completed finalization-failed (reconcile one or a bounded
  selection, stored authoritative evidence only);
- unresolved external-tool fences (read-only inspection - NO action).

The browser supplies NO authority: the actor and session come from the admin
session, execution requires the authenticated user's existing superadmin
role (checked on the server), the reviewed targets/assertions come from the
signed accounting review token, and every apply re-verifies the seal, then
re-loads the exact selected rows under canonical locks and re-checks the
relevant source facts before mutation in one transaction. Preview calls set
``dry_run=True`` / ``execute=False`` and write nothing. No secrets, provider
content, or raw exception text reaches HTML, logs, audits, or downloads.
"""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from fastapi import APIRouter, Request
from starlette.responses import HTMLResponse, Response

from slaif_gateway.api.admin import (
    _admin_action_context,
    _admin_error_page,
    _admin_not_found,
    _admin_page_context,
    _admin_status_message,
    _is_checked,
    _settings,
    templates,
)
from slaif_gateway.api.admin_review_intent import (
    ACCOUNTING_REVIEW_MAX_TARGETS,
    AdminReviewIntentError,
    build_accounting_review_token,
    verify_accounting_review_token,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.quota import QuotaReservationsRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services.admin_record_choices import load_choices
from slaif_gateway.utils.redaction import redact_text
from slaif_gateway.schemas.external_tool_hold import ExternalToolHoldAction
from slaif_gateway.services.admin_accounting_operations import (
    ACTION_EXPIRED,
    ACTION_HOLD_FINALIZE,
    ACTION_HOLD_RELEASE,
    ACTION_PROVIDER_COMPLETED,
    PREVIEW_REFUSED,
    AccountingOperationError,
    AccountingOperationResult,
    AccountingReviewTarget,
    AdminAccountingOperationsService,
)
from slaif_gateway.services.external_tool_fence import (
    ExternalToolFenceError,
    ExternalToolFenceService,
)
from slaif_gateway.services.external_tool_hold import ExternalToolAccountingHoldService
from slaif_gateway.services.reconciliation_errors import ReconciliationError
from slaif_gateway.services.request_diagnostics import is_known_incoming_secret_alias
from slaif_gateway.services.reservation_reconciliation import ReservationReconciliationService

router = APIRouter(prefix="/admin", include_in_schema=False)
logger = structlog.get_logger(__name__)

_BASE = "/admin/accounting-operations"

# Candidate views are bounded projections (no offset contract): a short or
# empty page never proves database completeness.
_VIEW_LIMIT = 200

# Fixed safe refusal vocabulary (finite codes, never echo raw input).
_ERROR_SELECTION = "accounting_selection_required"
_ERROR_REASON = "accounting_reason_required"
_ERROR_REASON_LONG = "accounting_reason_too_long"
_ERROR_REASON_WITHHELD = "accounting_reason_withheld"
_ERROR_SUPERADMIN = "accounting_superuser_required"
_ERROR_CONFIRM = "accounting_confirm_required"
_ERROR_INVALID = "accounting_invalid"
_ERROR_FAMILY = "accounting_review_family_mismatch"
_ERROR_FILTER = "accounting_filter_invalid"
_ERROR_NOCHARGE = "accounting_nocharge_confirmation_required"
_ERROR_CONFLICT = "accounting_assertions_conflict"
_ERROR_ALIAS = "accounting_value_withheld"
_ERROR_MULTISELECT = "accounting_selection_conflict"

_ERROR_MESSAGES = {
    _ERROR_SELECTION: "Select at least one reviewed row (at most 200) with valid identifiers before previewing.",
    _ERROR_REASON: "A nonblank audit reason is required.",
    _ERROR_REASON_LONG: "The audit reason must be at most 500 characters.",
    _ERROR_REASON_WITHHELD: "The audit reason matches a known incoming authentication value and cannot be used. Choose a different reason.",
    _ERROR_SUPERADMIN: "Applying accounting recovery requires the existing superadmin role. Inspection remains available to all signed-in admins.",
    _ERROR_CONFIRM: "Confirm the reviewed accounting operation before applying.",
    _ERROR_INVALID: "One of the reviewed values is invalid. Check the form and preview again.",
    _ERROR_FAMILY: "This reviewed operation cannot be applied here. Open the matching preview again.",
    _ERROR_FILTER: "A list filter is invalid (the key filter must be a UUID). Clear it and try again.",
    _ERROR_NOCHARGE: "Release with no charge requires its explicit no-charge confirmation checkbox.",
    _ERROR_CONFLICT: "The hold action and its assertions conflict: release with no charge accepts NO cost/token/outcome values, and finalize with actuals accepts NO no-charge confirmation. Adjust the form and preview again.",
    _ERROR_ALIAS: "A reviewed value matches a known incoming authentication value and cannot be used. Preview again without it.",
    _ERROR_MULTISELECT: "Choose the row one way only: either the candidate-row picker or the exact known-record field - not both at once.",
}

_ACTION_LABELS = {
    ACTION_EXPIRED: "Expired pending reservations",
    ACTION_PROVIDER_COMPLETED: "Provider-completed finalization failures",
    ACTION_HOLD_FINALIZE: "Hold finalize with operator actuals",
    ACTION_HOLD_RELEASE: "Hold release with no charge",
}

# Plain labels for the remaining preview metadata (review "details" cell).
_PREVIEW_DETAIL_LABELS = {
    "status": "Status",
    "quota_mode": "Quota mode",
    "expires_at": "Expires (UTC)",
    "accounting_status": "Accounting status",
    "provider": "Provider",
    "fence_state": "Fence state",
    "proposed_success": "Provider outcome",
}


@dataclass(frozen=True, slots=True)
class _ReviewPreviewRow:
    """Display-ready preview row: raw numerics plus readable details.

    Numeric readouts keep exact machine units (the template adds the
    human-facing M/number forms and the raw ``data-sort-value`` keys);
    missing evidence stays ``None`` (rendered as an em dash, never zero).
    ``details`` are the remaining current/proposed metadata with plain
    labels, redacted before render.
    """

    id: str
    proposal: str
    safe_detail: str
    action_label: str
    observed_tokens: int | None
    observed_requests: int | None
    observed_cost_eur: str | None
    proposed_tokens: int | None
    proposed_requests: int | None
    proposed_cost_eur: str | None
    details: tuple[tuple[str, str], ...]


def _preview_detail_value(value: Any) -> str:
    if value is None:
        return "—"
    if value is True:
        return "success"
    if value is False:
        return "failure"
    return str(value)

_REFUSED_MESSAGES = {
    "accounting_selection_invalid": "The reviewed accounting selection is invalid. Preview the selection again.",
    "accounting_source_changed": "A reviewed row changed after the preview, so the WHOLE operation was refused and nothing changed. Preview the selection again.",
    "accounting_operation_error": "The accounting recovery operation failed and nothing changed. Check the row state and preview again.",
    "reservation_not_pending": "A reviewed reservation is no longer pending. Nothing was changed.",
    "reservation_not_expired": "A reviewed reservation is no longer expired. Nothing was changed.",
    "stale_reservation_not_found": "A reviewed reservation is no longer present. Nothing was changed.",
    "reconciliation_invariant_error": "A reviewed row no longer satisfies the reconciliation invariants. Nothing was changed.",
    "provider_completed_recovery_already_reconciled": "A reviewed row was already reconciled. Nothing was changed again and no duplicate effect occurred.",
    "provider_completed_recovery_not_found": "A reviewed provider-completed row is no longer present. Nothing was changed.",
    "provider_completed_recovery_metadata_missing": "A reviewed row is missing authoritative stored evidence. Nothing was changed.",
    "provider_completed_recovery_not_repairable": "A reviewed row can no longer be safely repaired. Nothing was changed.",
    "provider_completed_recovery_invariant_error": "A reviewed row no longer satisfies the recovery invariants. Nothing was changed.",
    "external_tool_accounting_hold_error": "The reviewed hold can no longer be reconciled. Nothing was changed.",
    "invalid_external_tool_accounting_hold": "The reviewed hold assertions are no longer valid. Nothing was changed.",
    "external_tool_accounting_hold_invariant_error": "The reviewed hold no longer satisfies the hold invariants. Nothing was changed.",
    "external_tool_accounting_reconciliation_conflict": "The reviewed hold conflicts with its stored reconciliation facts. Nothing was changed.",
}
_DEFAULT_REFUSED_MESSAGE = (
    "The accounting recovery operation was refused and nothing changed. Check the row state and preview again."
)
_UNCONFIRMED_MESSAGE = (
    "The commit acknowledgement for the accounting operation was lost. This is NOT a rollback "
    "guarantee: verify the row state and the audit log before acting again. Do not re-apply "
    "blindly; a safe already-resolved outcome is possible."
)

_NONNEGATIVE_INT_RE = re.compile(r"^[0-9]+$")

# 216-a exact known-record selection bounds (the reviewed-operation
# ceiling; the generic list-filter cap stays 20 and is not reused):
# raw submitted members (repeats/blanks/newline fallback) and canonical
# unique UUIDs both cap at the 200 reviewed targets; a 201st unique
# target refuses predictably. Per-member length is a conservative
# anti-flood bound far above a UUID's 36 canonical characters.
_MAX_EXACT_SUBMITTED_VALUES = ACCOUNTING_REVIEW_MAX_TARGETS
_MAX_EXACT_MEMBER_LENGTH = 128


def _known_alias(request: Request, value: str | None) -> bool:
    if not value:
        return False
    return is_known_incoming_secret_alias(
        value,
        scope=request.scope,
        accepted_prefixes=_settings(request).get_gateway_key_accepted_prefixes(),
    )


def _error_page(request: Request, *, status_code: int, code: str) -> Response:
    return _admin_error_page(request, status_code=status_code, message=_ERROR_MESSAGES[code])


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if value is None or not value.strip():
        return None
    try:
        return uuid.UUID(value.strip())
    except ValueError:
        return None


def _selected_target_ids(form: Any) -> list[uuid.UUID]:
    """Parse the repeated ``target_id`` checkbox values.

    Returns the checked ids (possibly empty); a malformed member raises
    ValueError (fixed safe refusal at the caller).
    """
    ids: list[uuid.UUID] = []
    for raw in form.getlist("target_id"):
        parsed = _parse_uuid(str(raw or ""))
        if parsed is None:
            raise ValueError("target_id")
        ids.append(parsed)
    return ids


def _exact_selection_ids(
    request: Request, form: Any, field: str
) -> tuple[list[uuid.UUID], str | None]:
    """Bounded exact known-record selection (record-choice control).

    Returns ``(ids, error_code)``; ids may be empty (field unused). The
    raw members are alias-guarded BEFORE parsing: manual input is
    untrusted content and never reaches the seal.

    The bounds are the reviewed-operation ceiling, NOT the generic
    list-filter cap: at most 200 raw submitted members (repeated widget
    values, blanks and the newline no-JS fallback all count) and at most
    200 canonical unique UUIDs (case/hyphenation de-duplicated,
    first-seen order). A 201st unique target refuses predictably. The
    unrelated global list-filter limit (20) is untouched.
    """
    raw_values = form.getlist(field)
    if not raw_values:
        return [], None
    if any(_known_alias(request, str(value)) for value in raw_values):
        return [], _ERROR_ALIAS
    members: list[str] = []
    submitted = 0
    for raw in raw_values:
        # ``maxsplit`` keeps a single oversized newline flood bounded:
        # the excess remainder stays one part and the count rejects.
        for part in str(raw if raw is not None else "").split(
            "\n", _MAX_EXACT_SUBMITTED_VALUES
        ):
            submitted += 1
            if submitted > _MAX_EXACT_SUBMITTED_VALUES:
                return [], _ERROR_SELECTION
            member = part.strip()
            if not member:
                continue
            if len(member) > _MAX_EXACT_MEMBER_LENGTH:
                return [], _ERROR_SELECTION
            members.append(member)
    parsed: list[uuid.UUID] = []
    seen: set[str] = set()
    for member in members:
        try:
            parsed_value = uuid.UUID(member)
        except ValueError:
            return [], _ERROR_SELECTION
        canonical = str(parsed_value)
        if canonical in seen:
            continue
        if len(seen) >= ACCOUNTING_REVIEW_MAX_TARGETS:
            return [], _ERROR_SELECTION
        seen.add(canonical)
        parsed.append(parsed_value)
    return parsed, None


def _parse_nonnegative_int(value: str) -> int | None:
    if not _NONNEGATIVE_INT_RE.fullmatch(value.strip()):
        return None
    parsed = int(value.strip())
    return parsed if parsed >= 0 else None


def _parse_finite_nonnegative_decimal(value: str) -> Decimal | None:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError, ArithmeticError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _validate_reason(request: Request, reason: str) -> str | None:
    """Return a fixed safe error code, or None when the reason is acceptable."""
    if not reason.strip():
        return _ERROR_REASON
    if len(reason) > 500:
        return _ERROR_REASON_LONG
    if _known_alias(request, reason):
        return _ERROR_REASON_WITHHELD
    return None


def _build_service(session) -> AdminAccountingOperationsService:
    keys_repo = GatewayKeysRepository(session)
    quota_repo = QuotaReservationsRepository(session)
    usage_repo = UsageLedgerRepository(session)
    audit_repo = AuditRepository(session)
    fence_service = ExternalToolFenceService(
        gateway_keys_repository=keys_repo,
        quota_reservations_repository=quota_repo,
        usage_ledger_repository=usage_repo,
        audit_repository=audit_repo,
    )
    reservation_service = ReservationReconciliationService(
        gateway_keys_repository=keys_repo,
        quota_reservations_repository=quota_repo,
        usage_ledger_repository=usage_repo,
        audit_repository=audit_repo,
    )
    hold_service = ExternalToolAccountingHoldService(
        gateway_keys_repository=keys_repo,
        quota_reservations_repository=quota_repo,
        usage_ledger_repository=usage_repo,
        audit_repository=audit_repo,
        fence_service=fence_service,
    )
    return AdminAccountingOperationsService(
        reservation_service=reservation_service,
        hold_service=hold_service,
        fence_service=fence_service,
        quota_reservations_repository=quota_repo,
        usage_ledger_repository=usage_repo,
        keys_repository=keys_repo,
    )


def _apply_url_for(action: str | None) -> str:
    """The sealed family's apply URL (the template never builds it itself)."""
    if action == ACTION_EXPIRED:
        return f"{_BASE}/expired-reservations/apply"
    if action == ACTION_PROVIDER_COMPLETED:
        return f"{_BASE}/provider-completed-recovery/apply"
    if action in (ACTION_HOLD_FINALIZE, ACTION_HOLD_RELEASE):
        return f"{_BASE}/external-tool-holds/apply"
    return f"{_BASE}"


def _render(
    request: Request,
    *,
    template: str,
    admin,
    csrf_token: str,
    **context,
) -> Response:
    context.setdefault("admin_status_message", _admin_status_message(request))
    context.setdefault("base_path", _BASE)
    context.setdefault("apply_url", _apply_url_for(context.get("action")))
    return templates.TemplateResponse(
        request,
        template,
        {
            "admin": admin,
            "csrf_token": csrf_token,
            **context,
        },
    )


def _sanitize_previews(previews: Any, accepted_prefixes: tuple[str, ...]) -> Any:
    """Display-only redaction of preview metadata (existing pure helper).

    Free-text candidate facts (provider/model/endpoint) can carry
    secret-SHAPED values: the SAME pure text redactor used by the
    accounting audit path masks them before HTML, links, and sort
    attributes. Fingerprints and Core freshness checks keep the raw
    model attributes (this never touches them), and missing numeric
    evidence stays missing (never zero).

    Numeric readouts (tokens/requests/cost) keep their exact machine
    values for the separately sortable review columns; only the
    remaining metadata dict values are redacted and mapped to plain
    labels. Dry-run statuses are current facts (they arrive in
    ``observed``) and are never re-labelled as proposed state.
    """
    if not previews:
        return previews
    rows: list[_ReviewPreviewRow] = []
    for preview in previews:
        details: list[tuple[str, str]] = []
        for source in (preview.observed or {}, preview.proposed or {}):
            for key, value in source.items():
                if isinstance(value, str):
                    value = redact_text(value, accepted_prefixes)
                details.append(
                    (_PREVIEW_DETAIL_LABELS.get(key, key), _preview_detail_value(value))
                )
        rows.append(
            _ReviewPreviewRow(
                id=str(preview.id),
                proposal=preview.proposal,
                safe_detail=preview.safe_detail,
                action_label=preview.action_label,
                observed_tokens=preview.observed_tokens,
                observed_requests=preview.observed_requests,
                observed_cost_eur=preview.observed_cost_eur,
                proposed_tokens=preview.proposed_tokens,
                proposed_requests=preview.proposed_requests,
                proposed_cost_eur=preview.proposed_cost_eur,
                details=tuple(details),
            )
        )
    return rows


def _render_review(
    request: Request,
    *,
    action_context,
    csrf_token: str,
    action: str,
    reason: str,
    previews: Any,
    assertions: dict[str, Any] | None,
    confirm_no_charge: bool | None = None,
) -> Response:
    """Render the shared review stage from one preview result set.

    Refused rows keep their safe per-row outcome and REFUSE the whole review
    (no seal is issued): the operator must adjust the selection and preview
    again. Only a selection where every row is eligible or already resolved
    is signed.
    """
    review_token: str | None = None
    error: str | None = None
    if previews is not None and any(p.proposal == PREVIEW_REFUSED for p in previews):
        error = (
            "One or more selected rows cannot be reviewed right now (see each row's outcome). "
            "Deselect them, preview again, and apply only the rows that remain eligible or "
            "already resolved."
        )
    elif previews is not None:
        try:
            review_token = build_accounting_review_token(
                admin_session_secret=_settings(request).ADMIN_SESSION_SECRET,
                admin_user_id=action_context.admin_user.id,
                admin_session_id=action_context.admin_session.id,
                review_document=_review_document(
                    action,
                    previews,
                    assertions,
                    reason,
                    confirm_no_charge,
                ),
            )
        except AdminReviewIntentError as exc:
            review_token = None
            error = exc.message
    return _render(
        request,
        template="accounting_operations/review.html",
        admin=action_context.admin_user,
        csrf_token=csrf_token,
        action=action,
        action_label=_ACTION_LABELS.get(action, "Accounting recovery"),
        reason=reason,
        previews=_sanitize_previews(
            previews, _settings(request).get_gateway_key_accepted_prefixes()
        ),
        assertions=assertions,
        hold_action=action if action in (ACTION_HOLD_FINALIZE, ACTION_HOLD_RELEASE) else None,
        doc_targets=None,
        confirm_no_charge=confirm_no_charge,
        review_token=review_token,
        error=error,
        result=None,
        max_targets=ACCOUNTING_REVIEW_MAX_TARGETS,
    )


def _review_document(
    action: str,
    previews: Any,
    assertions: dict[str, Any] | None,
    reason: str,
    confirm_no_charge: bool | None,
) -> dict[str, Any]:
    """One strict closed review document (see the review-intent validator).

    For hold actions the explicit operator no-charge choice is sealed:
    release True, finalize False - never inferred from the selected mode.
    """
    document: dict[str, Any] = {
        "action": action,
        "targets": [
            {"id": str(preview.id), "fingerprint": preview.fingerprint} for preview in previews
        ],
        "assertions": assertions,
        "reason": reason,
        "nonce": secrets.token_hex(16),
    }
    if action in (ACTION_HOLD_FINALIZE, ACTION_HOLD_RELEASE):
        document["confirm_no_charge"] = confirm_no_charge is True
    return document


async def _apply_in_transaction(
    request: Request,
    *,
    apply_coro_factory,
) -> tuple[str, AccountingOperationResult | None, str | None]:
    """Run one reviewed apply inside a single transaction.

    Returns ``(state, result, error_code)`` where state is ``committed``,
    ``refused`` (safe rollback; the whole selected batch was not applied),
    or ``unconfirmed`` (a commit acknowledgement could not be confirmed -
    never a rollback promise).
    """
    session_factory = get_sessionmaker_from_app(request)
    mutation_done = False
    try:
        async with session_factory() as session:
            async with session.begin():
                service = _build_service(session)
                result = await apply_coro_factory(service)
                mutation_done = True
        return ("committed", result, None)
    except (ReconciliationError, ExternalToolFenceError) as exc:
        # AccountingOperationError is a ReconciliationError subclass; the
        # fence error family is the one hold-reconcile sibling that does
        # NOT inherit from ReconciliationError and must still refuse
        # safely (never a 500).
        if mutation_done:
            return ("unconfirmed", None, "unconfirmed")
        code = getattr(exc, "error_code", None) or "accounting_operation_error"
        return ("refused", None, str(code))
    except Exception:  # noqa: BLE001 - fail closed on an unexpected fault
        if mutation_done:
            logger.warning("admin_accounting_apply_unconfirmed", error_type="commit_ack")
            return ("unconfirmed", None, "unconfirmed")
        raise


async def _apply_route(
    request: Request,
    *,
    expected_actions: frozenset[str],
    form: Any,
) -> Response:
    """Shared verified-seal apply pipeline (see module docstring)."""
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    csrf_token = str(form.get("csrf_token") or "")
    review_token = str(form.get("review_token") or "")
    confirm_apply = str(form.get("confirm_apply") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    # Execution privilege: the authenticated user's EXISTING superadmin
    # role, checked on the server (inspection needs no special role).
    if action_context.admin_user.role != "superadmin":
        return _error_page(request, status_code=403, code=_ERROR_SUPERADMIN)

    try:
        document = verify_accounting_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            token=review_token,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
        )
    except AdminReviewIntentError as exc:
        return _admin_error_page(request, status_code=400, message=exc.message)

    action = str(document["action"])
    if action not in expected_actions:
        return _error_page(request, status_code=400, code=_ERROR_FAMILY)
    reason = str(document["reason"])

    # The sealed reason is displayed/audited content: keep the known
    # incoming authentication alias guard BEFORE any render, audit, or
    # mutation.
    if _known_alias(request, reason):
        return _error_page(request, status_code=400, code=_ERROR_REASON_WITHHELD)

    # Canonical signed values (targets + sealed assertions) are re-guarded
    # AFTER verify and BEFORE render/audit/mutation: the request's known
    # aliases can change between review and apply.
    assertions = document.get("assertions")
    canonical_values: list[str] = [str(target["id"]) for target in document["targets"]]
    if assertions is not None:
        canonical_values.extend(
            (
                str(assertions.get("actual_cost_eur")),
                str(assertions.get("actual_total_tokens")),
                str(assertions.get("success")),
            )
        )
    if any(_known_alias(request, value) for value in canonical_values):
        return _error_page(request, status_code=400, code=_ERROR_ALIAS)

    doc_targets = [str(target["id"]) for target in document["targets"]]
    if not _is_checked(confirm_apply):
        return _render(
            request,
            template="accounting_operations/review.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            action=action,
            action_label=_ACTION_LABELS.get(action, "Accounting recovery"),
            reason=reason,
            previews=None,
            assertions=document.get("assertions"),
            hold_action=action if action in (ACTION_HOLD_FINALIZE, ACTION_HOLD_RELEASE) else None,
            doc_targets=doc_targets,
            confirm_no_charge=document.get("confirm_no_charge"),
            review_token=review_token,
            error=_ERROR_MESSAGES[_ERROR_CONFIRM],
            result=None,
            max_targets=ACCOUNTING_REVIEW_MAX_TARGETS,
        )

    targets = [
        AccountingReviewTarget(
            id=uuid.UUID(str(target["id"])),
            fingerprint=str(target["fingerprint"]),
        )
        for target in document["targets"]
    ]
    actor_admin_id = action_context.admin_user.id

    if action == ACTION_EXPIRED:
        apply_coro = lambda service: service.apply_expired(  # noqa: E731 - single use
            targets=targets, actor_admin_id=actor_admin_id, reason=reason
        )
    elif action == ACTION_PROVIDER_COMPLETED:
        apply_coro = lambda service: service.apply_provider_completed(  # noqa: E731 - single use
            targets=targets, actor_admin_id=actor_admin_id, reason=reason
        )
    else:
        hold_action = (
            ExternalToolHoldAction.FINALIZE_ACTUAL
            if action == ACTION_HOLD_FINALIZE
            else ExternalToolHoldAction.RELEASE_NO_CHARGE
        )
        # The sealed no-charge choice (release True / finalize False) is
        # re-checked at the bridge and again by the shared Core validator
        # before execution.
        confirm_no_charge = bool(document["confirm_no_charge"])
        if action == ACTION_HOLD_FINALIZE:
            # Assertions are strict-typed by the seal validator: finite
            # non-negative Decimal cost, non-negative integer tokens,
            # explicit boolean outcome.
            actual_cost_eur = Decimal(str(assertions["actual_cost_eur"]))
            actual_total_tokens = int(assertions["actual_total_tokens"])
            success = bool(assertions["success"])
        else:
            actual_cost_eur, actual_total_tokens, success = None, None, None

        def apply_coro(service):  # noqa: E306 - single use
            return service.apply_hold(
                target=targets[0],
                action=hold_action,
                actual_cost_eur=actual_cost_eur,
                actual_total_tokens=actual_total_tokens,
                success=success,
                confirm_no_charge=confirm_no_charge,
                actor_admin_id=actor_admin_id,
                reason=reason,
            )

    state, result, error_code = await _apply_in_transaction(
        request, apply_coro_factory=apply_coro
    )

    if state == "committed":
        assert result is not None
        settled = result.settled_count
        already = result.already_resolved_count
        if settled and already:
            message = (
                f"Committed: {settled} row(s) settled; {already} row(s) were already "
                "resolved and left unchanged (no duplicate effect)."
            )
        elif settled:
            message = (
                f"Committed: {settled} row(s) settled with your audited reason. "
                "The changes were committed together."
            )
        else:
            message = (
                "Committed: every reviewed row was already resolved when applied. "
                "Nothing was changed again and no duplicate effect occurred."
            )
        result_context: dict[str, Any] = {
            "state": state,
            "message": message,
            "outcomes": [
                {"id": str(o.id), "status": o.status, "detail": o.safe_detail}
                for o in result.outcomes
            ],
        }
    else:
        refused_message = (
            _UNCONFIRMED_MESSAGE
            if state == "unconfirmed"
            else _REFUSED_MESSAGES.get(error_code or "", _DEFAULT_REFUSED_MESSAGE)
        )
        result_context = {"state": state, "message": refused_message, "outcomes": []}

    return _render(
        request,
        template="accounting_operations/review.html",
        admin=action_context.admin_user,
        csrf_token=csrf_token,
        action=action,
        action_label=_ACTION_LABELS.get(action, "Accounting recovery"),
        reason=reason,
        previews=None,
        assertions=document.get("assertions"),
        hold_action=action if action in (ACTION_HOLD_FINALIZE, ACTION_HOLD_RELEASE) else None,
        doc_targets=doc_targets,
        confirm_no_charge=document.get("confirm_no_charge"),
        review_token=None,
        error=None,
        result=result_context,
        max_targets=ACCOUNTING_REVIEW_MAX_TARGETS,
    )


# ---------------------------------------------------------------------------
# Index / navigation
# ---------------------------------------------------------------------------


@router.get("/accounting-operations/", response_class=HTMLResponse)
async def accounting_operations_index(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    return _render(
        request,
        template="accounting_operations/index.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
    )


# ---------------------------------------------------------------------------
# Read-only candidate views
# ---------------------------------------------------------------------------


@router.get("/accounting-operations/expired-reservations", response_class=HTMLResponse)
async def view_expired_reservations(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            rows = await _build_service(session).list_expired_candidates(limit=_VIEW_LIMIT)
            reservation_options = await load_choices(session, "quota_reservation")
    return _render(
        request,
        template="accounting_operations/expired_reservations.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        rows=rows,
        reservation_options=reservation_options,
        max_targets=ACCOUNTING_REVIEW_MAX_TARGETS,
        view_limit=_VIEW_LIMIT,
    )


@router.get("/accounting-operations/external-tool-fences", response_class=HTMLResponse)
async def view_external_tool_fences(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            rows = await _build_service(session).list_fence_candidates(limit=_VIEW_LIMIT)
    return _render(
        request,
        template="accounting_operations/fences.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        rows=rows,
        view_limit=_VIEW_LIMIT,
    )


@router.get("/accounting-operations/external-tool-holds", response_class=HTMLResponse)
async def view_external_tool_holds(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            rows = await _build_service(session).list_hold_candidates(limit=_VIEW_LIMIT)
            reservation_options = await load_choices(session, "quota_reservation")
    return _render(
        request,
        template="accounting_operations/holds.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        rows=rows,
        reservation_options=reservation_options,
        view_limit=_VIEW_LIMIT,
        hold_actions=[
            (ExternalToolHoldAction.FINALIZE_ACTUAL.value, "Finalize with actuals"),
            (ExternalToolHoldAction.RELEASE_NO_CHARGE.value, "Release with no charge"),
        ],
    )


@router.get("/accounting-operations/provider-completed-recovery", response_class=HTMLResponse)
async def view_provider_completed_recovery(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    raw_key = str(request.query_params.get("gateway_key_id") or "").strip()
    provider = str(request.query_params.get("provider") or "").strip() or None
    model = str(request.query_params.get("model") or "").strip() or None
    key_id: uuid.UUID | None = None
    if raw_key:
        key_id = _parse_uuid(raw_key)
        if key_id is None:
            return _error_page(request, status_code=400, code=_ERROR_FILTER)
    # The narrowing filters are rendered/echoed: refuse known incoming
    # authentication aliases BEFORE any render.
    if any(_known_alias(request, value) for value in (raw_key, provider or "", model or "")):
        return _error_page(request, status_code=400, code=_ERROR_FILTER)

    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            rows = await _build_service(session).list_provider_completed_candidates(
                limit=_VIEW_LIMIT,
                provider=provider,
                model=model,
                gateway_key_id=key_id,
            )
            key_options = await load_choices(session, "key")
            provider_options = await load_choices(session, "provider")
            model_options = await load_choices(
                session,
                "model",
                # 216-a: withhold credential-shaped model tokens from the
                # selectable model identities (shared seam, same guard as
                # the record-choices AJAX hydration).
                accepted_prefixes=settings.get_gateway_key_accepted_prefixes(),
            )
            ledger_options = await load_choices(session, "usage_ledger")
    # Presentation-safe rows: the existing pure text redactor masks
    # secret-shaped free-text candidate facts (provider/model/endpoint)
    # before HTML/links/sort attributes; ids and numeric evidence keep
    # their exact values (missing stays missing, never zero).
    accepted = settings.get_gateway_key_accepted_prefixes()
    display_rows = [
        {
            "usage_ledger_id": row.usage_ledger_id,
            "reservation_id": row.reservation_id,
            "gateway_key_id": row.gateway_key_id,
            "provider": redact_text(str(row.provider or ""), accepted),
            "model": (
                redact_text(str(row.requested_model or row.resolved_model or ""), accepted)
                or "n/a"
            ),
            "endpoint": redact_text(str(row.endpoint or ""), accepted),
            "total_tokens": row.total_tokens,
            "actual_cost_eur": row.actual_cost_eur,
            "created_at": row.created_at,
        }
        for row in rows
    ]
    return _render(
        request,
        template="accounting_operations/provider_completed.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        rows=display_rows,
        key_options=key_options,
        provider_options=provider_options,
        model_options=model_options,
        ledger_options=ledger_options,
        max_targets=ACCOUNTING_REVIEW_MAX_TARGETS,
        view_limit=_VIEW_LIMIT,
        filters={"gateway_key_id": raw_key, "provider": provider or "", "model": model or ""},
    )


# ---------------------------------------------------------------------------
# Preview (dry_run=True / execute=False; writes nothing) + review seal
# ---------------------------------------------------------------------------


@router.post("/accounting-operations/expired-reservations/preview", response_class=HTMLResponse)
async def preview_expired_reservations(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    try:
        checked_ids = _selected_target_ids(form)
    except ValueError:
        return _error_page(request, status_code=400, code=_ERROR_SELECTION)
    exact_ids, exact_error = _exact_selection_ids(request, form, "exact_reservation_id")
    if exact_error is not None:
        return _error_page(request, status_code=400, code=exact_error)
    target_ids = list(dict.fromkeys([*checked_ids, *exact_ids]))
    if not target_ids:
        return _error_page(request, status_code=400, code=_ERROR_SELECTION)
    reason = str(form.get("reason") or "")
    reason_error = _validate_reason(request, reason)
    if reason_error is not None:
        return _error_page(request, status_code=400, code=reason_error)

    session_factory = get_sessionmaker_from_app(request)
    try:
        async with session_factory() as session:
            async with session.begin():
                service = _build_service(session)
                previews = await service.preview_expired(target_ids)
    except AccountingOperationError:
        # Bounded selection law (empty/oversized/duplicate) at the service
        # seam: fixed safe refusal, never a 500.
        return _error_page(request, status_code=400, code=_ERROR_SELECTION)
    return _render_review(
        request,
        action_context=action_context,
        csrf_token=csrf_token,
        action=ACTION_EXPIRED,
        reason=reason,
        previews=previews,
        assertions=None,
    )


@router.post("/accounting-operations/provider-completed-recovery/preview", response_class=HTMLResponse)
async def preview_provider_completed_recovery(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    try:
        checked_ids = _selected_target_ids(form)
    except ValueError:
        return _error_page(request, status_code=400, code=_ERROR_SELECTION)
    exact_ids, exact_error = _exact_selection_ids(request, form, "exact_ledger_id")
    if exact_error is not None:
        return _error_page(request, status_code=400, code=exact_error)
    target_ids = list(dict.fromkeys([*checked_ids, *exact_ids]))
    if not target_ids:
        return _error_page(request, status_code=400, code=_ERROR_SELECTION)
    reason = str(form.get("reason") or "")
    reason_error = _validate_reason(request, reason)
    if reason_error is not None:
        return _error_page(request, status_code=400, code=reason_error)

    session_factory = get_sessionmaker_from_app(request)
    try:
        async with session_factory() as session:
            async with session.begin():
                service = _build_service(session)
                previews = await service.preview_provider_completed(target_ids)
    except AccountingOperationError:
        # Bounded selection law (empty/oversized/duplicate) at the service
        # seam: fixed safe refusal, never a 500.
        return _error_page(request, status_code=400, code=_ERROR_SELECTION)
    return _render_review(
        request,
        action_context=action_context,
        csrf_token=csrf_token,
        action=ACTION_PROVIDER_COMPLETED,
        reason=reason,
        previews=previews,
        assertions=None,
    )


@router.post("/accounting-operations/external-tool-holds/preview", response_class=HTMLResponse)
async def preview_external_tool_hold(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    radio_id = _parse_uuid(str(form.get("reservation_id") or ""))
    exact_ids, exact_error = _exact_selection_ids(request, form, "exact_reservation_id")
    if exact_error is not None:
        return _error_page(request, status_code=400, code=exact_error)
    if radio_id is not None and exact_ids:
        return _error_page(request, status_code=400, code=_ERROR_MULTISELECT)
    if radio_id is None:
        if not exact_ids:
            return _error_page(request, status_code=400, code=_ERROR_SELECTION)
        if len(exact_ids) > 1:
            return _error_page(request, status_code=400, code=_ERROR_MULTISELECT)
        radio_id = exact_ids[0]
    reservation_id = radio_id
    try:
        hold_action = ExternalToolHoldAction(str(form.get("hold_action") or ""))
    except ValueError:
        return _error_page(request, status_code=400, code=_ERROR_INVALID)
    reason = str(form.get("reason") or "")
    reason_error = _validate_reason(request, reason)
    if reason_error is not None:
        return _error_page(request, status_code=400, code=reason_error)

    # The no-charge choice is an explicit operator decision (checkbox),
    # never inferred from the selected mode; conflicting branches refuse
    # BEFORE any preview read (the shared Core law is re-enforced at the
    # service and again at execution).
    confirm_no_charge = _is_checked(str(form.get("confirm_no_charge") or ""))
    raw_cost = str(form.get("actual_cost_eur") or "").strip()
    raw_tokens = str(form.get("actual_total_tokens") or "").strip()
    outcome = str(form.get("outcome") or "")
    # Manual assertion fields are untrusted content: the existing pure
    # alias helper refuses known incoming authentication values BEFORE
    # parsing or sealing (a numeric bearer-shaped value is a secret even
    # when it canonicalizes into a token count).
    if any(_known_alias(request, value) for value in (raw_cost, raw_tokens, outcome)):
        return _error_page(request, status_code=400, code=_ERROR_ALIAS)
    assertions: dict[str, Any] | None = None
    actual_cost_eur: Decimal | None = None
    actual_total_tokens: int | None = None
    success: bool | None = None
    if hold_action is ExternalToolHoldAction.FINALIZE_ACTUAL:
        if confirm_no_charge:
            return _error_page(request, status_code=400, code=_ERROR_CONFLICT)
        actual_cost_eur = (
            _parse_finite_nonnegative_decimal(raw_cost) if raw_cost else None
        )
        actual_total_tokens = _parse_nonnegative_int(raw_tokens) if raw_tokens else None
        if outcome == "success":
            success = True
        elif outcome == "failure":
            success = False
        else:
            success = None
        if actual_cost_eur is None or actual_total_tokens is None or success is None:
            return _error_page(request, status_code=400, code=_ERROR_INVALID)
        assertions = {
            "actual_cost_eur": str(actual_cost_eur),
            "actual_total_tokens": actual_total_tokens,
            "success": success,
        }
    else:  # RELEASE_NO_CHARGE
        if not confirm_no_charge:
            return _error_page(request, status_code=400, code=_ERROR_NOCHARGE)
        if raw_cost or raw_tokens or outcome:
            return _error_page(request, status_code=400, code=_ERROR_CONFLICT)

    session_factory = get_sessionmaker_from_app(request)
    try:
        async with session_factory() as session:
            async with session.begin():
                service = _build_service(session)
                preview = await service.preview_hold(
                    reservation_id,
                    action=hold_action,
                    actual_cost_eur=actual_cost_eur,
                    actual_total_tokens=actual_total_tokens,
                    success=success,
                    confirm_no_charge=confirm_no_charge,
                )
    except AccountingOperationError:
        # Shared intent law at the service seam (defense in depth behind
        # the form-level checks): fixed safe refusal, never a 500.
        return _error_page(request, status_code=400, code=_ERROR_INVALID)
    action = (
        ACTION_HOLD_FINALIZE
        if hold_action is ExternalToolHoldAction.FINALIZE_ACTUAL
        else ACTION_HOLD_RELEASE
    )
    return _render_review(
        request,
        action_context=action_context,
        csrf_token=csrf_token,
        action=action,
        reason=reason,
        previews=[preview],
        assertions=assertions,
        confirm_no_charge=confirm_no_charge,
    )


# ---------------------------------------------------------------------------
# Apply (sealed review + superadmin + explicit confirmation)
# ---------------------------------------------------------------------------


@router.post("/accounting-operations/expired-reservations/apply", response_class=HTMLResponse)
async def apply_expired_reservations(request: Request) -> Response:
    form = await request.form()
    return await _apply_route(request, expected_actions=frozenset({ACTION_EXPIRED}), form=form)


@router.post("/accounting-operations/provider-completed-recovery/apply", response_class=HTMLResponse)
async def apply_provider_completed_recovery(request: Request) -> Response:
    form = await request.form()
    return await _apply_route(
        request, expected_actions=frozenset({ACTION_PROVIDER_COMPLETED}), form=form
    )


@router.post("/accounting-operations/external-tool-holds/apply", response_class=HTMLResponse)
async def apply_external_tool_hold(request: Request) -> Response:
    form = await request.form()
    return await _apply_route(
        request,
        expected_actions=frozenset({ACTION_HOLD_FINALIZE, ACTION_HOLD_RELEASE}),
        form=form,
    )

"""Privileged administrator account management router (218-a: G17).

Bounded admin GUI surfaces under ``/admin/accounts`` for the routine
post-bootstrap account administration that the offline CLI already
provides:

- list administrator accounts (bounded, navigation-preserving list,
  safe metadata only - never hashes, session tokens, or secrets);
- create one account (ordinary admin by default; EVERY creation
  requires its explicit confirmation, and the privileged superadmin
  choice additionally requires the explicit privileged-role
  acknowledgement plus a bounded audit reason);
- reset one existing account's password (server-derived fixed UUID
  target bound to the form, exact matching new password/confirmation,
  explicit confirmation and reason, and DELIBERATE revocation of ALL
  of the target's existing sessions in the same transaction as the
  hash change and the actor/target/reason audit).

Authority law: every view and action first passes the existing
dashboard-off gate, then the existing admin session + CSRF validation
(``_admin_page_context`` / ``_admin_action_context`` one-way reuse from
:mod:`slaif_gateway.api.admin`), and then the SERVER-side check that the
authenticated admin's PERSISTED role is the existing ``superadmin``.
Hiding the navigation link is deliberately NOT sufficient. The browser
supplies no role, no actor identity, and no bootstrap path; the actor
is always the session admin. First-superadmin creation and break-glass
access remain CLI/offline only.

Secret law: password bytes are preserved EXACTLY (never trimmed or
normalized), bounded only by the shared nonempty hashing law plus a
documented finite GUI resource cap, and are never re-displayed,
logged, audited, or returned; only Argon2id hashes persist. Raw
persisted free-text fields (email, display name, reason) are refused
without echo when they equal a known incoming authentication value,
and the reset audit User-Agent passes through the existing pure alias
masker before persistence. DB/audit fault paths answer fixed
secret-free outcomes and never log raw exceptions, SQL text, or
hashes.

The shared :class:`slaif_gateway.services.admin_service.AdminService`
performs the actual account work for GUI and CLI alike (no duplicated
password/account SQL in routes).
"""

from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import APIRouter, Form, Query, Request
from sqlalchemy.exc import IntegrityError
from starlette.responses import HTMLResponse, RedirectResponse, Response

from slaif_gateway.api.admin import (
    _admin_action_context,
    _admin_error_page,
    _admin_list_pagination,
    _admin_not_found,
    _admin_page_context,
    _admin_status_message,
    _clear_session_cookie,
    _client_host,
    _is_checked,
    _settings,
    templates,
)
from slaif_gateway.api.admin_email_operations import _safe_audit_user_agent
from slaif_gateway.db.repositories.admin_sessions import AdminSessionsRepository
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services.admin_session_service import AdminSessionContext
from slaif_gateway.services.admin_service import AdminService
from slaif_gateway.services.record_errors import (
    DuplicateRecordError,
    RecordNotFoundError,
)
from slaif_gateway.services.request_diagnostics import is_known_incoming_secret_alias
from slaif_gateway.utils.passwords import hash_admin_password

router = APIRouter(prefix="/admin", include_in_schema=False)
logger = structlog.get_logger(__name__)

_BASE = "/admin/accounts"

# Bounded input law (validated BEFORE the expensive Argon2id hash).
# The GUI keeps the shared nonempty password law (no new minimum) plus
# one documented finite resource cap so a hostile form cannot drive
# unbounded Argon2id work.
_EMAIL_MAX_LENGTH = 320
_DISPLAY_NAME_MAX_LENGTH = 200
_PASSWORD_MAX_LENGTH = 128
_REASON_MAX_LENGTH = 500
_EMAIL_PATTERN = re.compile(r"[^@\s]{1,64}@[^@\s]+\.[^@\s]+")

# Fixed safe refusal vocabulary (finite codes, never echo raw input).
_ERROR_SUPERADMIN = "accounts_superuser_required"
_ERROR_TARGET = "accounts_target_invalid"
_ERROR_TARGET_MISMATCH = "accounts_target_mismatch"
_ERROR_TARGET_MISSING = "accounts_target_not_found"
_ERROR_EMAIL = "accounts_email_invalid"
_ERROR_DISPLAY_NAME = "accounts_display_name_invalid"
_ERROR_PASSWORD = "accounts_password_invalid"
_ERROR_PASSWORD_MISMATCH = "accounts_password_mismatch"
_ERROR_CONFIRM = "accounts_confirm_required"
_ERROR_REASON = "accounts_reason_required"
_ERROR_REASON_LONG = "accounts_reason_too_long"
_ERROR_REASON_WITHHELD = "accounts_reason_withheld"
_ERROR_ALIAS = "accounts_value_withheld"

_ERROR_MESSAGES: dict[str, str] = {
    _ERROR_SUPERADMIN: (
        "Administrator account management requires the existing superadmin "
        "role. Sign in as a superadmin to manage accounts."
    ),
    _ERROR_TARGET: (
        "Select an administrator account from the accounts list to reset "
        "its password."
    ),
    _ERROR_TARGET_MISMATCH: (
        "This reset form no longer matches the displayed account. Return "
        "to the accounts list and select the account again."
    ),
    _ERROR_TARGET_MISSING: "The selected administrator account no longer exists.",
    _ERROR_EMAIL: (
        "Enter a valid email address: a local part, one '@', and a domain "
        f"with a dot (at most {_EMAIL_MAX_LENGTH} characters total)."
    ),
    _ERROR_DISPLAY_NAME: (
        "Enter a display name (at least 1 and at most "
        f"{_DISPLAY_NAME_MAX_LENGTH} characters after trimming)."
    ),
    _ERROR_PASSWORD: (
        f"The new password must be nonempty and at most {_PASSWORD_MAX_LENGTH} "
        "characters."
    ),
    _ERROR_PASSWORD_MISMATCH: (
        "The new password and its confirmation do not match exactly. "
        "Neither value is stored, displayed, or logged."
    ),
    _ERROR_CONFIRM: (
        "Confirm the account change before submitting: every account "
        "creation requires its explicit confirmation, and a superadmin "
        "account additionally requires the privileged-role confirmation; "
        "a password reset requires its explicit confirmation."
    ),
    _ERROR_REASON: "A nonblank audit reason is required.",
    _ERROR_REASON_LONG: (
        f"The audit reason must be at most {_REASON_MAX_LENGTH} characters."
    ),
    _ERROR_REASON_WITHHELD: (
        "The audit reason matches a known incoming authentication value "
        "and cannot be used. Choose a different reason."
    ),
    _ERROR_ALIAS: (
        "A field value matches a known incoming authentication value and "
        "cannot be used. Change that field and try again."
    ),
}

_MSG_DUPLICATE = (
    "An administrator account with this email already exists. The "
    "submission was rejected without changes."
)
# Honest outcome-UNCONFIRMED law: a pre-commit fault rolls back
# atomically (proven natively), but a generic commit/connection fault
# cannot establish that, so these fixed outcomes never promise a
# rollback. The operator verifies the account/audit state before
# retrying; there is no durable receipt or automatic retry.
_MSG_CREATE_FAILED = (
    "Account creation could not be confirmed. Verify the account list "
    "(or the audit log) to see whether the account exists before "
    "retrying, so it is not created twice. If the problem persists, "
    "contact your operator."
)
_MSG_RESET_FAILED = (
    "The password reset could not be confirmed. Verify the account's "
    "current state (a sign-in attempt with the new password, or the "
    "audit log) before retrying. If the problem persists, contact "
    "your operator."
)
_MSG_TARGET_LOOKUP_FAILED = (
    "The administrator account could not be loaded. No reset was "
    "attempted. Try again; if it persists, contact your operator."
)


@asynccontextmanager
async def _admin_accounts_service_scope(request: Request) -> AsyncIterator[AdminService]:
    """One transaction-bound shared AdminService (same session/transaction)."""
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield AdminService(
                admin_users_repository=AdminUsersRepository(session),
                audit_repository=AuditRepository(session),
                admin_sessions_repository=AdminSessionsRepository(session),
            )


def _superadmin_gate(
    request: Request, context: AdminSessionContext
) -> Response | None:
    """SERVER-side persisted-role gate (hiding links is insufficient)."""
    if context.admin_user.role == "superadmin":
        return None
    return _admin_error_page(
        request, status_code=403, message=_ERROR_MESSAGES[_ERROR_SUPERADMIN]
    )


def _parse_target_uuid(value: str | None) -> uuid.UUID | None:
    if value is None or not value.strip():
        return None
    try:
        return uuid.UUID(value.strip())
    except ValueError:
        return None


def _validate_password_pair(password: str, confirmation: str) -> str | None:
    """Bounds on the EXACT password bytes (never trimmed or normalized).

    The shared hashing law is nonempty; the GUI adds only the finite
    resource cap. Password strength is recommended through the field
    help, not enforced as a new policy.
    """
    if not password or len(password) > _PASSWORD_MAX_LENGTH:
        return _ERROR_PASSWORD
    if password != confirmation:
        return _ERROR_PASSWORD_MISMATCH
    return None


def _validate_reason(request: Request, reason: str) -> str | None:
    if not reason.strip():
        return _ERROR_REASON
    if len(reason) > _REASON_MAX_LENGTH:
        return _ERROR_REASON_LONG
    if is_known_incoming_secret_alias(
        reason,
        scope=request.scope,
        accepted_prefixes=_settings(request).get_gateway_key_accepted_prefixes(),
    ):
        return _ERROR_REASON_WITHHELD
    return None


def _validate_free_text_alias(request: Request, value: str) -> str | None:
    """Refuse (no echo) a RAW free-text field that equals a known
    incoming authentication value, before normalization, persistence,
    or redisplay."""
    if value and is_known_incoming_secret_alias(
        value,
        scope=request.scope,
        accepted_prefixes=_settings(request).get_gateway_key_accepted_prefixes(),
    ):
        return _ERROR_ALIAS
    return None


def _render(
    request: Request,
    *,
    template: str,
    context: AdminSessionContext,
    csrf_token: str,
    form_error: str | None,
    status_code: int = 200,
    **extra: object,
) -> Response:
    return templates.TemplateResponse(
        request,
        template,
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "admin_status_message": _admin_status_message(request),
            "form_error": form_error,
            **extra,
        },
        status_code=status_code,
    )


async def _email_exists_now(request: Request, email: str) -> bool:
    """Re-check ONE email against committed state after a raced commit.

    Fail closed: any lookup fault means the duplicate condition is NOT
    established, so the caller keeps the honest generic failure outcome.
    """
    try:
        async with _admin_accounts_service_scope(request) as service:
            await service.get_admin_user(email)
        return True
    except RecordNotFoundError:
        return False
    except Exception:  # noqa: BLE001 - fail closed, secret-free
        return False


@router.get("/accounts", response_class=HTMLResponse)
async def list_admin_accounts(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    gate = _superadmin_gate(request, context)
    if gate is not None:
        return gate

    async with _admin_accounts_service_scope(request) as service:
        # 218-a cap+1: a full page alone is NOT has_more; older accounts
        # stay reachable through the preserved navigation.
        fetched = await service.list_admin_users(limit=limit + 1, offset=offset)

    rows = fetched[:limit]
    page_state = _admin_list_pagination(
        request,
        base_path=_BASE,
        limit=limit,
        offset=offset,
        fetched_count=len(fetched),
        filter_pairs=[],
    )
    if isinstance(page_state, Response):
        return page_state

    return _render(
        request,
        template="admin_accounts/list.html",
        context=context,
        csrf_token=csrf_token,
        form_error=None,
        accounts=rows,
        **page_state,
        rows_shown=len(rows),
        list_aria="Administrator accounts",
        filters={"limit": limit, "offset": offset},
    )


@router.get("/accounts/create", response_class=HTMLResponse)
async def create_admin_account_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    gate = _superadmin_gate(request, context)
    if gate is not None:
        return gate

    return _render(
        request,
        template="admin_accounts/create.html",
        context=context,
        csrf_token=csrf_token,
        form_error=None,
        form={},
    )


@router.post("/accounts/create", response_class=HTMLResponse)
async def create_admin_account(
    request: Request,
    email: str = Form(""),
    display_name: str = Form(""),
    password: str = Form(""),
    password_confirmation: str = Form(""),
    role: str = Form("admin"),
    confirm_create: str = Form(""),
    confirm_superadmin: str = Form(""),
    reason: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    # Fresh authorization + CSRF on the mutating request.
    context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(context, Response):
        return context
    gate = _superadmin_gate(request, context)
    if gate is not None:
        return gate

    # Bounded validation BEFORE the expensive Argon2id hash. The
    # submitted CSRF token is still the stored (valid) one, so a
    # validation re-render may keep it (the action context does not
    # rotate it); password/confirmation are NEVER re-displayed.
    normalized_email = email.strip().lower()
    display_name_trimmed = display_name.strip()

    error_code: str | None = None
    if role not in {"admin", "superadmin"}:
        error_code = _ERROR_CONFIRM
    elif not _is_checked(confirm_create):
        error_code = _ERROR_CONFIRM
    elif (
        not normalized_email
        or len(normalized_email) > _EMAIL_MAX_LENGTH
        or _EMAIL_PATTERN.fullmatch(normalized_email) is None
    ):
        error_code = _ERROR_EMAIL
    else:
        # Raw persisted free text is refused (no echo) when it equals a
        # known incoming authentication value - checked BEFORE any
        # normalization, persistence, or redisplay.
        alias_error = (
            _validate_free_text_alias(request, email)
            or _validate_free_text_alias(request, display_name)
        )
        if alias_error is not None:
            error_code = alias_error
        elif not (1 <= len(display_name_trimmed) <= _DISPLAY_NAME_MAX_LENGTH):
            error_code = _ERROR_DISPLAY_NAME
        else:
            password_error = _validate_password_pair(password, password_confirmation)
            if password_error is not None:
                error_code = password_error
            else:
                reason_error = _validate_reason(request, reason)
                if reason_error is not None:
                    error_code = reason_error
                elif role == "superadmin" and not _is_checked(confirm_superadmin):
                    error_code = _ERROR_CONFIRM

    if error_code is not None:
        # Preserve only the non-secret, already-received operator
        # fields for actionable recovery - and never a value that was
        # refused as a known incoming authentication value (no echo),
        # and never the password fields.
        return _render(
            request,
            template="admin_accounts/create.html",
            context=context,
            csrf_token=csrf_token,
            form_error=_ERROR_MESSAGES[error_code],
            status_code=400,
            form={
                "email": (
                    normalized_email
                    if _validate_free_text_alias(request, email) is None
                    else ""
                ),
                "display_name": (
                    display_name_trimmed
                    if _validate_free_text_alias(request, display_name) is None
                    else ""
                ),
                "role": role if role in {"admin", "superadmin"} else "admin",
                "reason": (
                    reason if _validate_reason(request, reason) is None else ""
                ),
            },
        )

    password_hash = hash_admin_password(password)
    # Fixed secret-free outcome law: only the KNOWN duplicate-email
    # condition may claim "already exists"; every other DB/audit fault
    # gets the honest fixed failure outcome, and no raw exception, SQL
    # text, or hash is ever logged or rendered.
    outcome: str
    try:
        async with _admin_accounts_service_scope(request) as service:
            await service.create_admin_user(
                email=normalized_email,
                display_name=display_name_trimmed,
                password_hash=password_hash,
                is_superadmin=(role == "superadmin"),
                actor_admin_id=context.admin_user.id,
                reason=reason,
            )
        outcome = "created"
    except DuplicateRecordError:
        outcome = "duplicate"
    except IntegrityError:
        # Concurrent duplicate submission raced the unique email
        # constraint at commit time: re-check the committed state to
        # decide WHICH fixed outcome is honest.
        outcome = (
            "duplicate"
            if await _email_exists_now(request, normalized_email)
            else "failed"
        )
    except Exception:  # noqa: BLE001 - fixed secret-free outcome
        logger.warning("admin_account_create_failed", code="creation_failed")
        outcome = "failed"

    if outcome == "created":
        return RedirectResponse(f"{_BASE}?message=admin_account_created", status_code=303)
    if outcome == "duplicate":
        return _admin_error_page(request, status_code=409, message=_MSG_DUPLICATE)
    return _admin_error_page(request, status_code=500, message=_MSG_CREATE_FAILED)


@router.get("/accounts/reset", response_class=HTMLResponse)
async def reset_admin_account_form(
    request: Request, admin_id: str | None = Query(None)
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    gate = _superadmin_gate(request, context)
    if gate is not None:
        return gate

    target_id = _parse_target_uuid(admin_id)
    if target_id is None:
        return _admin_error_page(
            request, status_code=400, message=_ERROR_MESSAGES[_ERROR_TARGET]
        )

    try:
        async with _admin_accounts_service_scope(request) as service:
            # Server-derived identity (name/email/role/state) - the
            # browser never supplies the account it will see.
            target = await service.get_admin_user(str(target_id))
    except RecordNotFoundError:
        return _admin_error_page(
            request, status_code=404, message=_ERROR_MESSAGES[_ERROR_TARGET_MISSING]
        )
    except Exception:  # noqa: BLE001 - fixed secret-free outcome
        # Read-only lookup fault: NO reset was attempted (the lookup
        # precedes any mutation scope), so this wording is exact.
        return _admin_error_page(request, status_code=500, message=_MSG_TARGET_LOOKUP_FAILED)

    return _render(
        request,
        template="admin_accounts/reset.html",
        context=context,
        csrf_token=csrf_token,
        form_error=None,
        target=target,
        is_self_reset=(target.id == context.admin_user.id),
        admin_id=str(target.id),
        form={},
    )


@router.post("/accounts/reset", response_class=HTMLResponse)
async def reset_admin_account_password(
    request: Request,
    admin_id: str = Form(""),
    password: str = Form(""),
    password_confirmation: str = Form(""),
    confirm_reset: str = Form(""),
    reason: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    # Fresh authorization + CSRF on the mutating request.
    context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(context, Response):
        return context
    gate = _superadmin_gate(request, context)
    if gate is not None:
        return gate

    # The reset form is BOUND to the displayed fixed canonical target:
    # the form action URL carries the target, and the hidden field must
    # agree; any conflict is refused (no signing/custody framework).
    url_target_id = _parse_target_uuid(request.query_params.get("admin_id"))
    hidden_target_id = _parse_target_uuid(admin_id)
    if url_target_id is None:
        return _admin_error_page(
            request, status_code=400, message=_ERROR_MESSAGES[_ERROR_TARGET]
        )
    if hidden_target_id is None or hidden_target_id != url_target_id:
        return _admin_error_page(
            request, status_code=400, message=_ERROR_MESSAGES[_ERROR_TARGET_MISMATCH]
        )
    target_id = url_target_id

    try:
        async with _admin_accounts_service_scope(request) as service:
            # Server-refetched target identity (validation recovery also
            # re-renders from this fresh read, never from the browser).
            target = await service.get_admin_user(str(target_id))
    except RecordNotFoundError:
        return _admin_error_page(
            request, status_code=404, message=_ERROR_MESSAGES[_ERROR_TARGET_MISSING]
        )
    except Exception:  # noqa: BLE001 - fixed secret-free outcome
        # Read-only lookup fault: NO reset was attempted (the lookup
        # precedes any mutation scope), so this wording is exact.
        return _admin_error_page(request, status_code=500, message=_MSG_TARGET_LOOKUP_FAILED)

    # Bounded validation BEFORE the expensive Argon2id hash.
    error_code: str | None = None
    if not _is_checked(confirm_reset):
        error_code = _ERROR_CONFIRM
    else:
        password_error = _validate_password_pair(password, password_confirmation)
        if password_error is not None:
            error_code = password_error
        else:
            reason_error = _validate_reason(request, reason)
            if reason_error is not None:
                error_code = reason_error

    is_self_reset = target.id == context.admin_user.id
    if error_code is not None:
        return _render(
            request,
            template="admin_accounts/reset.html",
            context=context,
            csrf_token=csrf_token,
            form_error=_ERROR_MESSAGES[error_code],
            status_code=400,
            target=target,
            is_self_reset=is_self_reset,
            admin_id=str(target.id),
            # Same no-echo preservation law as create: a refused
            # reason is never re-displayed.
            form={
                "reason": (
                    reason if _validate_reason(request, reason) is None else ""
                )
            },
        )

    password_hash = hash_admin_password(password)
    # Fixed secret-free outcome law (same as create): one transaction,
    # all-or-nothing; faults never leak raw exception/SQL/hash text and
    # never claim a success they did not commit.
    outcome: str
    try:
        async with _admin_accounts_service_scope(request) as service:
            # Shared transaction: target row lock, new hash, revocation
            # of ALL of the target's existing sessions, and the
            # actor/target/reason audit - one commit, all-or-nothing.
            await service.reset_admin_password(
                admin_user_id_or_email=str(target.id),
                password_hash=password_hash,
                actor_admin_id=context.admin_user.id,
                reason=reason,
                ip_address=_client_host(request),
                user_agent=_safe_audit_user_agent(request, request.headers.get("user-agent")),
            )
        outcome = "reset"
    except RecordNotFoundError:
        # The target vanished between the identity lookup and the
        # locked reset: fixed safe outcome.
        outcome = "missing"
    except Exception:  # noqa: BLE001 - fixed secret-free outcome
        logger.warning("admin_account_reset_failed", code="reset_failed")
        outcome = "failed"

    if outcome == "missing":
        return _admin_error_page(
            request, status_code=404, message=_ERROR_MESSAGES[_ERROR_TARGET_MISSING]
        )
    if outcome == "failed":
        return _admin_error_page(request, status_code=500, message=_MSG_RESET_FAILED)

    if is_self_reset:
        # The shared reset deliberately revoked the actor's own session;
        # return a secret-free outcome and clear the (now revoked)
        # cookie.
        response = RedirectResponse(
            "/admin/login?message=admin_password_reset_self", status_code=303
        )
        _clear_session_cookie(response, settings)
        return response

    return RedirectResponse(f"{_BASE}?message=admin_password_reset", status_code=303)

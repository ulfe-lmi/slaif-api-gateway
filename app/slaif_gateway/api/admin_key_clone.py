"""Reviewed standard-key cloning for the admin GUI (208-a / G04).

Select -> review -> confirm -> inspect result/recover, reusing the
already-qualified :class:`~slaif_gateway.services.key_clone_service.KeyCloneService`.
This purpose-bound router keeps the clone workflow out of the admin monolith
while reusing its existing helpers (one-way import: ``admin.py`` never
imports this module).

Workflow and invariants:

- ``GET  /admin/keys/{id}/clone``          guided form; the CORE determines
  supported/unsupported state via a read-only eligibility probe.
- ``POST /admin/keys/{id}/clone/review``   calls ``build_plan`` (no mutation,
  no policy audit), then binds the complete strict plan document, the
  delivery choice, the signed-in admin/session, and a bounded expiry into a
  signed review-intent token.
- ``POST /admin/keys/{id}/clone/apply``    verifies/rebinds/strict-reparses
  the token, checks source match + confirmation + bounded reason, then
  executes the SAME reviewed plan (never a regenerated operation UUID) in
  the caller-owned transaction. Dispatch happens only AFTER commit; a
  post-commit channel failure is a "created with delivery failure" outcome
  with stable IDs - never a request for a second clone.
- ``GET  /admin/keys/{id}/clone/receipts`` authenticated, READ-ONLY outcome
  recovery by source+operation identity (works after review expiry or a
  lost response); it never creates a clone and assumes nothing on not-found.

The one-time plaintext is displayed at most once, only through the selected
one-time channel (none/pending), on a no-store result page. It never appears
in URLs, hidden review state, errors, audit rows, logs, or already-applied
outcomes.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse

from slaif_gateway.api.admin import (
    _admin_action_context,
    _admin_bounded_reason,
    _admin_diagnostic_id,
    _admin_email_delivery_action_scope,
    _admin_error_page,
    _admin_key_dashboard_service_scope,
    _admin_not_found,
    _admin_page_context,
    _admin_redact_key_form_value,
    _admin_redact_key_form_values,
    _choice_selected_labels,
    _enqueue_admin_pending_key_email,
    _is_checked,
    _load_admin_record_choices_safe,
    _log_admin_action_failure,
    _parse_admin_datetime,
    _parse_admin_email_delivery_mode,
    _parse_gateway_key_id,
    _parse_optional_admin_uuid,
    _parse_required_admin_uuid,
    _set_no_store_headers,
    _settings,
    _validate_admin_email_delivery_preconditions,
    templates,
)
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    build_review_intent_token,
    verify_review_intent_token,
)
from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.schemas.key_clone import (
    MAX_VALIDITY_DURATION_SECONDS,
    VALIDITY_ABSOLUTE,
    VALIDITY_COPY_SOURCE_EXPIRY,
    VALIDITY_DURATION_FROM_NOW,
    parse_clone_plan_document,
)
from slaif_gateway.services.admin_key_dashboard import AdminKeyNotFoundError
from slaif_gateway.services.email_delivery_service import (
    EmailDeliveryService,
    PendingKeyEmailResult,
)
from slaif_gateway.services.email_errors import EmailError
from slaif_gateway.services.email_service import EmailService
from slaif_gateway.services.key_clone_service import (
    KeyCloneReceiptProjection,
    KeyCloneService,
)
from slaif_gateway.services.key_errors import GatewayKeyNotFoundError, KeyManagementError
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.services.streaming_live_burn_surface import (
    CHAT_STREAMING_LIVE_BURN_SURFACE,
    streaming_live_burn_surface_policy_summary,
)
from slaif_gateway.web.formatting import (
    format_number,
    format_rate_limit_policy,
    format_tokens_m,
)

router = APIRouter(prefix="/admin", include_in_schema=False)

# Readable labels for the one-time delivery channel (bound at review).
_DELIVERY_MODE_LABELS: dict[str, str] = {
    "none": "None - show the new key once in the browser",
    "pending": "Pending - create a delivery row and show the key once",
    "send-now": "Send now - email is the delivery channel (key not shown in the browser)",
    "enqueue": "Enqueue - Celery email delivery (key not shown in the browser)",
}

# Fixed safe display reasons for the form-page core eligibility probe.
_ELIGIBILITY_MESSAGES: dict[str, str] = {
    "key_clone_source_ineligible": (
        "The core reports this source key is not eligible for cloning right "
        "now: a standard purpose and capability mode, active status, "
        "current (unexpired) validity, and no fence are all required."
    ),
    "key_clone_unsupported_source_policy": (
        "The source key's Responses-streaming live-burn policy cannot be "
        "represented by standard key creation; cloning is refused and the "
        "source policy is never reset."
    ),
    "key_clone_source_secret_shape": (
        "The source key's configured policy contains a recognized secret "
        "shape; cloning is refused and the policy is never altered."
    ),
}
_ELIGIBILITY_FALLBACK_MESSAGE = (
    "This source key is not supported for cloning. The source policy is "
    "never reset or weakened to force eligibility."
)

_DURATION_UNITS: dict[str, int] = {
    "seconds": 1,
    "minutes": 60,
    "hours": 3600,
    "days": 86400,
}


def _default_clone_form() -> dict[str, str]:
    return {
        "target_owner_id": "",
        "target_cohort_id": "",
        "validity_mode": VALIDITY_COPY_SOURCE_EXPIRY,
        "duration_value": "",
        "duration_unit": "hours",
        "valid_from": "",
        "valid_until": "",
        "email_delivery_mode": "none",
    }


@asynccontextmanager
async def _admin_key_clone_runtime_scope(
    request: Request,
) -> AsyncIterator[tuple[Settings, KeyCloneService]]:
    """Caller-owned transaction runtime for the clone operation.

    Mirrors the qualified CLI clone runtime: the service is flush-only and
    the surrounding transaction commits the target key, one-time secret,
    pending delivery, clone receipt, and audit atomically - or rolls ALL of
    them back on a late failure.
    """
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            settings = _settings(request)
            keys_repository = GatewayKeysRepository(session)
            one_time_secrets_repository = OneTimeSecretsRepository(session)
            audit_repository = AuditRepository(session)
            key_service = KeyService(
                settings=settings,
                gateway_keys_repository=keys_repository,
                one_time_secrets_repository=one_time_secrets_repository,
                audit_repository=audit_repository,
                model_routes_repository=ModelRoutesRepository(session),
            )
            email_delivery_service = EmailDeliveryService(
                settings=settings,
                one_time_secrets_repository=one_time_secrets_repository,
                email_deliveries_repository=EmailDeliveriesRepository(session),
                gateway_keys_repository=keys_repository,
                owners_repository=OwnersRepository(session),
                audit_repository=audit_repository,
                email_service=EmailService(settings),
                session=session,
            )
            clone_service = KeyCloneService(
                settings=settings,
                key_service=key_service,
                gateway_keys_repository=keys_repository,
                owners_repository=OwnersRepository(session),
                cohorts_repository=CohortsRepository(session),
                email_delivery_service=email_delivery_service,
                audit_repository=audit_repository,
            )
            yield settings, clone_service


async def _probe_clone_eligibility(
    request: Request, source_id: uuid.UUID, owner_id: uuid.UUID
) -> dict[str, object]:
    """Read-only core eligibility probe for the form page.

    Runs the CORE ``build_plan`` once against the source's own owner
    (copy-source-expiry, no cohort): every source-side eligibility rule
    (standard purpose/mode, active, validity, fence, supported canonical
    policy, no recognized secret shapes) is decided by the existing service
    - this is not a GUI policy engine. The call mutates nothing and writes
    no audit row; the result is only a supported/unsupported display state.
    """
    try:
        async with _admin_key_clone_runtime_scope(request) as (_settings_obj, clone_service):
            await clone_service.build_plan(
                source_gateway_key_id=source_id,
                target_owner_id=owner_id,
                target_cohort_id=None,
                validity_mode=VALIDITY_COPY_SOURCE_EXPIRY,
            )
    except GatewayKeyNotFoundError:
        return {"eligible": False, "message": _ELIGIBILITY_FALLBACK_MESSAGE}
    except KeyManagementError as exc:
        return {
            "eligible": False,
            "message": _ELIGIBILITY_MESSAGES.get(exc.error_code, _ELIGIBILITY_FALLBACK_MESSAGE),
        }
    except Exception:  # noqa: BLE001 - display state only; review is authoritative
        return {
            "eligible": False,
            "message": (
                "Eligibility could not be pre-checked; submitting the review "
                "reports the exact core reason."
            ),
        }
    return {
        "eligible": True,
        "message": (
            "The core currently reports this source as cloneable (standard "
            "key, active, within validity, unfenced, supported policy)."
        ),
    }


def _parse_clone_validity_form(
    form: dict[str, str],
) -> dict[str, Any]:
    """Parse the guided validity fields into strict build_plan arguments.

    Enforces the single-mode law with fixed safe errors (never echoing the
    submitted values): exactly one mode's fields may be non-blank, durations
    are positive whole numbers of the selected unit converted to exact
    seconds bounded by the service maximum, and absolute windows are valid
    UTC datetimes with the end after the start.
    """
    mode = (form.get("validity_mode") or "").strip().lower()
    if mode not in {
        VALIDITY_COPY_SOURCE_EXPIRY,
        VALIDITY_DURATION_FROM_NOW,
        VALIDITY_ABSOLUTE,
    }:
        raise ValueError("Select a supported validity mode.")

    duration_raw = (form.get("duration_value") or "").strip()
    unit_raw = (form.get("duration_unit") or "").strip().lower()
    valid_from_raw = (form.get("valid_from") or "").strip()
    valid_until_raw = (form.get("valid_until") or "").strip()

    out: dict[str, Any] = {
        "validity_mode": mode,
        "validity_duration_seconds": None,
        "validity_from": None,
        "validity_until": None,
    }
    if mode == VALIDITY_DURATION_FROM_NOW:
        if not duration_raw:
            raise ValueError("Enter a positive duration for duration-from-now.")
        if unit_raw not in _DURATION_UNITS:
            raise ValueError("Select a supported duration unit.")
        try:
            amount = int(duration_raw, 10)
        except ValueError:
            raise ValueError("Duration must be a positive whole number.") from None
        if amount <= 0:
            raise ValueError("Duration must be positive.")
        seconds = amount * _DURATION_UNITS[unit_raw]
        if seconds > MAX_VALIDITY_DURATION_SECONDS:
            raise ValueError(
                f"Duration exceeds the bounded maximum ({MAX_VALIDITY_DURATION_SECONDS} seconds)."
            )
        out["validity_duration_seconds"] = seconds
        if valid_from_raw or valid_until_raw:
            raise ValueError("Absolute dates are only used for the absolute mode.")
    elif mode == VALIDITY_ABSOLUTE:
        if duration_raw:
            raise ValueError("A duration is only used for the duration-from-now mode.")
        if not valid_from_raw or not valid_until_raw:
            raise ValueError("Enter both absolute start and end times (UTC).")
        try:
            valid_from = _parse_admin_datetime(valid_from_raw)
            valid_until = _parse_admin_datetime(valid_until_raw)
        except ValueError:
            raise ValueError("Enter valid UTC dates and times (YYYY-MM-DD HH:MM).") from None
        if valid_from is None or valid_until is None:
            raise ValueError("Enter both absolute start and end times (UTC).")
        if valid_until <= valid_from:
            raise ValueError("The absolute end time must be after the start time.")
        out["validity_from"] = valid_from.isoformat()
        out["validity_until"] = valid_until.isoformat()
    else:  # copy-source-expiry
        if duration_raw or valid_from_raw or valid_until_raw:
            raise ValueError(
                "Copy-source-expiry uses the source's current expiry; leave the "
                "other validity fields blank."
            )
    return out


def _clone_form_response(
    request: Request,
    *,
    admin: object,
    csrf_token: str,
    key: object,
    form: dict[str, str],
    settings: Settings,
    error: str | None,
    diagnostic_id: str | None = None,
    status_code: int = 200,
    eligibility: dict[str, object] | None = None,
    choices: dict[str, Any] | None = None,
) -> Response:
    redacted_form = _admin_redact_key_form_values(form, settings)
    return templates.TemplateResponse(
        request,
        "keys/clone_form.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "key": key,
            "form": redacted_form,
            "choice_labels": _choice_selected_labels(
                choices or {},
                (
                    ("target_owner_id", redacted_form.get("target_owner_id")),
                    ("target_cohort_id", redacted_form.get("target_cohort_id")),
                ),
            ),
            "choices": choices or {},
            "eligibility": eligibility
            or {"eligible": False, "message": _ELIGIBILITY_FALLBACK_MESSAGE},
            "delivery_mode_labels": _DELIVERY_MODE_LABELS,
            "max_duration_seconds": MAX_VALIDITY_DURATION_SECONDS,
            "error": error,
            "diagnostic_id": diagnostic_id,
        },
        status_code=status_code,
    )


@router.get("/keys/{gateway_key_id}/clone", response_class=HTMLResponse)
async def clone_key_form(request: Request, gateway_key_id: str) -> Response:
    """Guided clone form: source identity + core eligibility + target selection."""
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    source_id = _parse_gateway_key_id(gateway_key_id)
    if source_id is None:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_key_dashboard_service_scope(request) as service:
            key = await service.get_key_detail(source_id)
    except AdminKeyNotFoundError:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")

    eligibility = await _probe_clone_eligibility(request, source_id, key.owner_id)
    choices = await _load_admin_record_choices_safe(
        request,
        (
            ("owner_id", "owner", None),
            ("cohort_id", "cohort", None),
        ),
    )
    return _clone_form_response(
        request,
        admin=context.admin_user,
        csrf_token=csrf_token,
        key=key,
        form=_default_clone_form(),
        settings=settings,
        error=None,
        eligibility=eligibility,
        choices=choices,
    )


@router.post("/keys/{gateway_key_id}/clone/review", response_class=HTMLResponse)
async def clone_key_review(
    request: Request,
    gateway_key_id: str,
    csrf_token: str = Form(""),
    target_owner_id: str = Form(""),
    target_cohort_id: str = Form(""),
    validity_mode: str = Form(VALIDITY_COPY_SOURCE_EXPIRY),
    duration_value: str = Form(""),
    duration_unit: str = Form("hours"),
    valid_from: str = Form(""),
    valid_until: str = Form(""),
    email_delivery_mode: str = Form("none"),
) -> Response:
    """Core build_plan + signed review state (non-mutating, no policy audit)."""
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    source_id = _parse_gateway_key_id(gateway_key_id)
    if source_id is None:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = {
        "target_owner_id": target_owner_id,
        "target_cohort_id": target_cohort_id,
        "validity_mode": validity_mode,
        "duration_value": duration_value,
        "duration_unit": duration_unit,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "email_delivery_mode": email_delivery_mode,
    }

    async def _rerender(error: str, *, status_code: int = 400) -> Response:
        key = await _load_key_detail_or_none(request, source_id)
        if key is None:
            # The source vanished before the form could be re-rendered:
            # controlled 404, never a form over an absent key.
            return _admin_error_page(
                request, status_code=404, message="Gateway key not found."
            )
        choices = await _load_admin_record_choices_safe(
            request,
            (
                ("owner_id", "owner", form.get("target_owner_id")),
                ("cohort_id", "cohort", form.get("target_cohort_id")),
            ),
        )
        return _clone_form_response(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            key=key,
            form=form,
            settings=settings,
            error=error,
            diagnostic_id=_admin_diagnostic_id(request),
            status_code=status_code,
            choices=choices,
        )

    # Fixed safe input validation BEFORE any service call.
    try:
        owner_uuid = _parse_required_admin_uuid(
            form.get("target_owner_id"), field_name="target_owner_id"
        )
        cohort_uuid = _parse_optional_admin_uuid(
            form.get("target_cohort_id"), field_name="target_cohort_id"
        )
        validity = _parse_clone_validity_form(form)
        delivery_mode = _parse_admin_email_delivery_mode(form.get("email_delivery_mode"))
        _validate_admin_email_delivery_preconditions(settings, delivery_mode)
    except (KeyManagementError, ValueError) as exc:
        return await _rerender(_admin_redact_key_form_value(str(exc), settings))

    # The CORE builds the strict non-secret plan (no mutation, no audit).
    try:
        async with _admin_key_clone_runtime_scope(request) as (_settings_obj, clone_service):
            document = await clone_service.build_plan(
                source_gateway_key_id=source_id,
                target_owner_id=owner_uuid,
                target_cohort_id=cohort_uuid,
                validity_mode=validity["validity_mode"],
                validity_duration_seconds=validity["validity_duration_seconds"],
                validity_from=validity["validity_from"],
                validity_until=validity["validity_until"],
            )
    except GatewayKeyNotFoundError:
        # The source vanished between page load and submit: a controlled 404,
        # never a form re-render over an absent key.
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")
    except (KeyManagementError, EmailError, ValueError) as exc:
        message = exc.safe_message if isinstance(exc, KeyManagementError) else str(exc)
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=owner_uuid,
            cohort_id=cohort_uuid,
            email_delivery_mode=delivery_mode,
        )
        return await _rerender(_admin_redact_key_form_value(message, settings))

    token = build_review_intent_token(
        admin_session_secret=settings.ADMIN_SESSION_SECRET,
        admin_user_id=action_context.admin_user.id,
        admin_session_id=action_context.admin_session.id,
        plan_document=document,
        delivery_mode=delivery_mode,
    )

    key = await _load_key_detail_or_none(request, source_id)
    choices = await _load_admin_record_choices_safe(
        request,
        (
            ("owner_id", "owner", str(owner_uuid)),
            ("cohort_id", "cohort", str(cohort_uuid) if cohort_uuid else None),
        ),
    )
    response = templates.TemplateResponse(
        request,
        "keys/clone_review.html",
        {
            "admin": action_context.admin_user,
            "csrf_token": csrf_token,
            "key": key,
            "source_id": source_id,
            "source_public_key_id": document["source_public_key_id"],
            "plan": document,
            "policy": document["policy"],
            "policy_summary": _clone_policy_summary(document["policy"]),
            "owner_id": owner_uuid,
            "cohort_id": cohort_uuid,
            "choice_labels": _choice_selected_labels(
                choices,
                (
                    ("owner_id", str(owner_uuid)),
                    ("cohort_id", str(cohort_uuid) if cohort_uuid else None),
                ),
            ),
            "delivery_mode": delivery_mode,
            "delivery_mode_label": _DELIVERY_MODE_LABELS[delivery_mode],
            "clone_review_intent": token,
            "max_duration_seconds": MAX_VALIDITY_DURATION_SECONDS,
            "error": None,
        },
    )
    return response


async def _load_key_detail_or_none(request: Request, source_id: uuid.UUID) -> object:
    try:
        async with _admin_key_dashboard_service_scope(request) as service:
            return await service.get_key_detail(source_id)
    except (AdminKeyNotFoundError, AttributeError, RuntimeError):
        return None


def _clone_rate_limit_line(rate_policy: object) -> str | None:
    """Window-aware readout for the reviewed rate-limit policy.

    The runtime meters these counts in the configured ``window_seconds``
    bucket (one minute when the window is omitted), so a non-minute
    window is labeled by its window instead of "per minute". Minute and
    omitted windows keep the existing shared per-minute grammar; the raw
    policy stays exact in the optional JSON detail.
    """
    if not isinstance(rate_policy, dict) or not rate_policy:
        return None
    window = rate_policy.get("window_seconds")
    if window in (None, 60):
        return format_rate_limit_policy(rate_policy)
    parts: list[str] = []
    requests = rate_policy.get("requests_per_minute")
    if requests is not None and format_number(requests) is not None:
        parts.append(f"{format_number(requests)} requests")
    tokens = rate_policy.get("tokens_per_minute")
    if tokens is not None and format_tokens_m(tokens) is not None:
        parts.append(f"{format_tokens_m(tokens)}M tokens")
    if not parts:
        # Only the window/concurrency parts are set: the shared grammar
        # already carries no per-minute claim.
        return format_rate_limit_policy(rate_policy)
    window_text = format_number(window)
    qualifier = (
        f"per {window_text}s window" if window_text else "per configured window"
    )
    line = ", ".join(parts) + " " + qualifier
    concurrency = rate_policy.get("max_concurrent_requests")
    if concurrency is not None and format_number(concurrency) is not None:
        line += f", max {format_number(concurrency)} concurrent"
    return line


def _clone_policy_summary(policy: dict[str, Any]) -> dict[str, Any]:
    """Readable, non-secret rows for the reviewed canonical policy document.

    Limit/lazy/live-burn values stay in their native (exact) form so the
    template renders them with the shared ``num``/``tokm``/``ratepolicy``/
    ``policysum`` readout filters; the live-burn line reuses the existing
    service summary helper and the rate line keeps the window the runtime
    meters in. No policy logic is added - this only projects fields the
    canonical document already carries.
    """
    providers = policy.get("allowed_providers")
    if providers is None and policy.get("allow_all_providers") is None:
        providers_text = "Unrestricted (all enabled providers)"
    elif providers is None or policy.get("allow_all_providers"):
        providers_text = "Unrestricted (all enabled providers)"
    elif providers == []:
        providers_text = "Deny all providers"
    else:
        providers_text = f"Allow-list: {', '.join(providers)}"

    models = policy.get("allowed_models")
    if models is None and policy.get("allow_all_models") is None:
        models_text = "Default (route-backed models for the allowed providers)"
    elif models is None or policy.get("allow_all_models"):
        models_text = "All route-backed models"
    elif models == []:
        models_text = "Deny all models"
    else:
        models_text = f"Allow-list: {', '.join(models)}"

    endpoints = policy.get("allowed_endpoints")
    if endpoints is None and policy.get("allow_all_endpoints") is None:
        endpoints_text = "Default (implemented endpoints)"
    elif endpoints is None or policy.get("allow_all_endpoints"):
        endpoints_text = "All implemented endpoints"
    elif endpoints == []:
        endpoints_text = "Deny all endpoints"
    else:
        endpoints_text = f"Allow-list: {', '.join(endpoints)}"

    live_burn_raw = policy.get("chat_streaming_live_burn_policy")
    return {
        "allowed_providers": providers_text,
        "allowed_models": models_text,
        "allowed_endpoints": endpoints_text,
        "cost_limit_eur": policy.get("cost_limit_eur"),
        "token_limit_total": policy.get("token_limit_total"),
        "request_limit_total": policy.get("request_limit_total"),
        "rate_limit_policy": policy.get("rate_limit_policy"),
        "rate_limit_line": _clone_rate_limit_line(policy.get("rate_limit_policy")),
        "lazy_throttling_policy": policy.get("lazy_throttling_policy"),
        "chat_streaming_live_burn_summary": (
            streaming_live_burn_surface_policy_summary(
                CHAT_STREAMING_LIVE_BURN_SURFACE, live_burn_raw
            )
            if live_burn_raw is not None
            else None
        ),
        "external_tool_policy": policy.get("external_tool_policy"),
        "responses_policy": policy.get("responses_policy"),
        "confirm_external_tool_fenced": policy.get("confirm_external_tool_fenced"),
    }


@router.post("/keys/{gateway_key_id}/clone/apply", response_class=HTMLResponse)
async def clone_key_apply(
    request: Request,
    gateway_key_id: str,
    csrf_token: str = Form(""),
    clone_review_intent: str = Form(""),
    confirm_apply: str = Form(""),
    confirm_external_tool_fenced: str = Form(""),
    reason: str = Form(""),
) -> Response:
    """Verify/rebind/strict-reparse the review state, then execute it.

    The delivery channel comes ONLY from the verified token: a mutable
    apply field can never turn a reviewed mail operation into plaintext
    display or vice versa.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    source_id = _parse_gateway_key_id(gateway_key_id)
    if source_id is None:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    def _safe_400(message: str) -> Response:
        return _admin_error_page(
            request,
            status_code=400,
            message=_admin_redact_key_form_value(message, settings),
        )

    # Everything below runs BEFORE any mutation.
    try:
        plan_document, delivery_mode = verify_review_intent_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            token=clone_review_intent,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
        )
        plan = parse_clone_plan_document(plan_document)
        if plan.source_gateway_key_id != str(source_id):
            raise ValueError(
                "The reviewed plan belongs to a different source key; review "
                "it again from that key."
            )
        if not _is_checked(confirm_apply):
            raise ValueError("Confirm the reviewed clone plan before applying it.")
        cleaned_reason, reason_error = _admin_bounded_reason(reason)
        if reason_error is not None:
            raise ValueError(reason_error)
        if cleaned_reason is None:
            raise ValueError("Enter an audit reason before applying the clone.")
        cleaned_reason = _admin_redact_key_form_value(cleaned_reason, settings)
        _validate_admin_email_delivery_preconditions(settings, delivery_mode)
        confirm_fenced = _is_checked(confirm_external_tool_fenced)
        if plan.requires_fenced_confirmation and not confirm_fenced:
            raise ValueError(
                "Provide the fresh fenced external-tool confirmation before applying."
            )
    except (AdminReviewIntentError, ValueError) as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _safe_400(exc.message if isinstance(exc, AdminReviewIntentError) else str(exc))

    # Execute the SAME reviewed plan in the caller-owned transaction.
    try:
        async with _admin_key_clone_runtime_scope(request) as (_settings_obj, clone_service):
            result = await clone_service.execute_plan(
                plan=plan,
                reason=cleaned_reason,
                actor_admin_id=action_context.admin_user.id,
                confirm_external_tool_fenced=confirm_fenced,
                create_email_delivery=delivery_mode != "none",
            )
    except (KeyManagementError, EmailError, ValueError) as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=uuid.UUID(plan.target_owner_id),
            cohort_id=(
                uuid.UUID(plan.target_cohort_id) if plan.target_cohort_id else None
            ),
            email_delivery_mode=delivery_mode,
        )
        message = exc.safe_message if isinstance(exc, KeyManagementError) else str(exc)
        return _safe_400(message)

    # Post-commit dispatch only (the clone is already committed; a channel
    # failure here is a recovery outcome, never a request for a second clone).
    delivery_result: PendingKeyEmailResult | None = None
    celery_task_id: str | None = None
    post_commit_failure: str | None = None
    if (
        result.status == "created"
        and delivery_mode in {"send-now", "enqueue"}
        and result.one_time_secret_id
        and result.email_delivery_id
    ):
        if delivery_mode == "send-now":
            try:
                async with _admin_email_delivery_action_scope(request) as email_delivery_service:
                    delivery_result = await email_delivery_service.send_pending_key_email(
                        one_time_secret_id=uuid.UUID(result.one_time_secret_id),
                        email_delivery_id=uuid.UUID(result.email_delivery_id),
                        actor_admin_id=action_context.admin_user.id,
                        reason=cleaned_reason,
                    )
            except EmailError as exc:
                _log_admin_action_failure(
                    request,
                    exc=exc,
                    admin_id=action_context.admin_user.id,
                    owner_id=uuid.UUID(plan.target_owner_id),
                    cohort_id=(
                        uuid.UUID(plan.target_cohort_id) if plan.target_cohort_id else None
                    ),
                    email_delivery_mode=delivery_mode,
                )
                post_commit_failure = "email_delivery_failed"
        else:  # enqueue
            try:
                celery_task_id = _enqueue_admin_pending_key_email(
                    one_time_secret_id=uuid.UUID(result.one_time_secret_id),
                    email_delivery_id=uuid.UUID(result.email_delivery_id),
                    actor_admin_id=action_context.admin_user.id,
                )
                delivery_result = PendingKeyEmailResult(
                    email_delivery_id=uuid.UUID(result.email_delivery_id),
                    one_time_secret_id=uuid.UUID(result.one_time_secret_id),
                    gateway_key_id=uuid.UUID(result.target_gateway_key_id),
                    owner_id=uuid.UUID(plan.target_owner_id),
                    recipient_email=None,
                    status="queued",
                )
            except Exception as exc:  # noqa: BLE001 - committed; safe recovery only
                _log_admin_action_failure(
                    request,
                    exc=exc,
                    admin_id=action_context.admin_user.id,
                    owner_id=uuid.UUID(plan.target_owner_id),
                    cohort_id=(
                        uuid.UUID(plan.target_cohort_id) if plan.target_cohort_id else None
                    ),
                    email_delivery_mode=delivery_mode,
                    level="error",
                )
                post_commit_failure = "celery_enqueue_failed"

    show_plaintext = (
        result.status == "created"
        and delivery_mode in {"none", "pending"}
        and result.plaintext_key is not None
    )
    response = templates.TemplateResponse(
        request,
        "keys/clone_result.html",
        {
            "admin": action_context.admin_user,
            "result": result,
            "source_id": source_id,
            "source_public_key_id": plan.source_public_key_id,
            "target_owner_id": plan.target_owner_id,
            "target_cohort_id": plan.target_cohort_id,
            "delivery_mode": delivery_mode,
            "delivery_mode_label": _DELIVERY_MODE_LABELS[delivery_mode],
            "show_plaintext": show_plaintext,
            # In-process only: rendered at most once on this no-store page.
            "plaintext_key": result.plaintext_key if show_plaintext else None,
            "delivery": delivery_result,
            "celery_task_id": celery_task_id,
            "post_commit_failure": post_commit_failure,
        },
    )
    _set_no_store_headers(response)
    return response


@router.get("/keys/{gateway_key_id}/clone/receipts", response_class=HTMLResponse)
async def clone_key_recovery(
    request: Request,
    gateway_key_id: str,
    operation: str = "",
) -> Response:
    """Authenticated READ-ONLY outcome recovery (works after review expiry).

    Recovers by canonical source+operation identity through the narrowly
    allowlisted receipt projection: created (exactly one target) versus
    not-found/unknown (nothing assumed). It never creates a clone, never
    locks, and never redisplay plaintext; delivery retry always points at
    the existing one-time sendability flow.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    source_id = _parse_gateway_key_id(gateway_key_id)
    if source_id is None:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_key_dashboard_service_scope(request) as service:
            key = await service.get_key_detail(source_id)
    except AdminKeyNotFoundError:
        return _admin_error_page(request, status_code=404, message="Gateway key not found.")

    operation_uuid: uuid.UUID | None = None
    operation_error: str | None = None
    projection: KeyCloneReceiptProjection | None = None
    projection_error: str | None = None
    # Redact recognized credential-shaped values before redisplay/logging;
    # ordinary (e.g. misspelled) UUID input is preserved for correction and
    # still fails with the useful fixed UUID error.
    operation_value = _admin_redact_key_form_value(operation.strip(), settings)
    if operation_value:
        try:
            operation_uuid = uuid.UUID(operation_value)
        except ValueError:
            operation_error = (
                "Enter the operation UUID shown on the clone result page "
                "(32 hexadecimal digits with hyphens)."
            )
    if operation_uuid is not None:
        try:
            async with _admin_key_clone_runtime_scope(request) as (_settings_obj, clone_service):
                projection = await clone_service.find_clone_receipt(
                    source_gateway_key_id=source_id,
                    operation_uuid=operation_uuid,
                )
        except GatewayKeyNotFoundError:
            return _admin_error_page(request, status_code=404, message="Gateway key not found.")
        except KeyManagementError as exc:
            projection_error = exc.safe_message

    response = templates.TemplateResponse(
        request,
        "keys/clone_recovery.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "key": key,
            "operation": operation_value,
            "operation_uuid": str(operation_uuid) if operation_uuid else None,
            "operation_error": operation_error,
            "projection": projection,
            "projection_error": projection_error,
        },
    )
    return response

"""Focused admin email-operation router (215-a: G12).

Bounded admin GUI surfaces that reuse the shared application seams:

- explicit retry-failed intent for an EXISTING failed delivery: a
  distinct action with a required nonblank bounded (1024 UTF-8 bytes)
  reason, the shared current-Core preflight, the attributable
  enqueue-REQUEST intent audit committed BEFORE broker dispatch, and a
  broker failure that is reported requested-but-unconfirmed (never a
  fabricated queued/sent state);
- the bounded SMTP test through the EXISTING ``EmailService`` primitive:
  a two-stage signed review intent (purpose-bound, actor/session-bound,
  15-minute expiry), a one-use claim plus per-actor 3/60s budget on
  existing PostgreSQL row locks and audit facts, an outer 30s per-attempt
  deadline, and finite safe outcomes (accepted / unconfirmed / failed /
  unavailable) that never echo provider prose.

The browser supplies NO authority: the actor and session come from the
admin session, the reviewed facts come from the signed token, and every
action re-resolves the exact delivery/secret binding and current
eligibility on the server before sending or enqueuing. The Celery task
payload stays exactly the existing three UUID arguments.
"""

from __future__ import annotations

import secrets
import uuid

import structlog
from fastapi import APIRouter, Form, Request
from starlette.responses import HTMLResponse, Response

from slaif_gateway.api.admin import (
    _admin_action_context,
    _admin_error_page,
    _admin_not_found,
    _admin_page_context,
    _admin_request_id,
    _admin_status_message,
    _client_host,
    _enqueue_admin_pending_key_email,
    _is_checked,
    _redirect_to_admin_email_delivery,
    _settings,
    _validate_admin_email_delivery_preconditions,
    templates,
)
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    build_smtp_test_review_token,
    verify_smtp_test_review_token,
)
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services.email_admin_operations import (
    SMTP_TEST_BUDGET_ATTEMPTS,
    SMTP_TEST_BUDGET_WINDOW_SECONDS,
    SMTP_TEST_DEFAULT_BODY,
    SMTP_TEST_DEFAULT_SUBJECT,
    EmailAdminOperationError,
    SmtpTestBudgetExceededError,
    SmtpTestFacts,
    SmtpTestIntentAlreadyClaimedError,
    claim_smtp_test_attempt,
    prepare_smtp_test_facts,
    record_enqueue_request_audit,
    record_smtp_test_result,
    run_smtp_test_with_deadline,
    smtp_test_outer_deadline,
    validate_retry_reason,
)
from slaif_gateway.services.email_delivery_service import (
    EmailDeliveryService,
    EmailError,
)
from slaif_gateway.services.email_service import EmailService
from slaif_gateway.services.request_diagnostics import (
    build_client_id_masker,
    is_known_incoming_secret_alias,
)

router = APIRouter(prefix="/admin", include_in_schema=False)

_RETRY_MODE_SEND_NOW = "send-now"
_RETRY_MODE_ENQUEUE = "enqueue"

# Fixed safe reason-error mapping (finite codes, never echoed input).
_RETRY_REASON_MESSAGES = {
    "blank": "email_delivery_retry_reason_required",
    "too_long": "email_delivery_retry_reason_too_long",
    "known_secret": "email_delivery_retry_reason_withheld",
}


def _smtp_test_ready(settings) -> bool:
    """ENABLE_EMAIL_DELIVERY + SMTP host/from readiness (no send)."""
    return bool(
        settings.ENABLE_EMAIL_DELIVERY
        and settings.SMTP_HOST
        and settings.SMTP_FROM
    )


def _smtp_test_readiness(settings) -> dict[str, object]:
    return {
        "enabled": bool(settings.ENABLE_EMAIL_DELIVERY),
        "configured": bool(settings.SMTP_HOST and settings.SMTP_FROM),
        "available": _smtp_test_ready(settings),
    }


def _known_alias(request: Request, value: str | None) -> bool:
    if not value:
        return False
    return is_known_incoming_secret_alias(
        value,
        scope=request.scope,
        accepted_prefixes=_settings(request).get_gateway_key_accepted_prefixes(),
    )

logger = structlog.get_logger(__name__)


def _safe_audit_user_agent(request: Request, user_agent: str | None) -> str | None:
    """Mask known incoming auth aliases out of the UA before persistence.

    ``AuditRepository.add_audit_log`` stores the top-level
    ``user_agent`` RAW (the global metadata sanitizer does not touch
    it), so the new SMTP-test audit context first passes the UA
    through the SAME pure single-pass alias masker the request
    capture writer uses (fixed [REDACTED] token for embedded
    incoming credential values).  Incomplete discovery is fail
    closed: the whole value is withheld.  The global sanitizer is
    unchanged.
    """
    if not user_agent:
        return user_agent
    try:
        masker, complete = build_client_id_masker(
            request.scope,
            accepted_prefixes=_settings(request).get_gateway_key_accepted_prefixes(),
        )
    except Exception:  # noqa: BLE001 - fail closed on a masker fault
        return "[withheld]"
    if not complete:
        return "[withheld]"
    if masker is None:
        # No known incoming aliases discovered: the value is safe.
        return user_agent
    try:
        masked = masker(user_agent.encode("utf-8"))
    except Exception:  # noqa: BLE001 - fail closed on a masker fault
        return "[withheld]"
    if masked == user_agent.encode("utf-8"):
        return user_agent
    # SAME input encoding for the decode: the masked bytes are the
    # original UTF-8 with ASCII [REDACTED] substitutions, so the
    # nonsecret Unicode metadata round-trips uncorrupted.  A decode
    # fault is fail-closed (withhold the whole value).
    try:
        return masked.decode("utf-8")
    except UnicodeDecodeError:
        return "[withheld]"


@router.post(
    "/email-deliveries/{email_delivery_id}/retry-failed",
    response_class=HTMLResponse,
)
async def retry_admin_email_delivery_failed(
    request: Request,
    email_delivery_id: str,
    csrf_token: str = Form(""),
    retry_mode: str = Form(_RETRY_MODE_SEND_NOW),
    reason: str | None = Form(None),
    confirm_retry: str | None = Form(None),
) -> Response:
    """Explicit retry of ONE existing FAILED delivery (distinct intent).

    Server-side law: the exact delivery must still exist, must still be
    FAILED, and must be eligible under the shared current-Core
    preflight at action time (a failed-only flag on a now-pending row or
    a now-mismatched binding refuses). A nonblank bounded reason is
    required and audited with the server actor; for enqueue the
    requested intent is committed BEFORE broker dispatch and a broker
    failure is reported requested-but-unconfirmed.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    try:
        parsed_email_delivery_id = uuid.UUID(email_delivery_id)
    except ValueError:
        return _admin_error_page(request, status_code=404, message="Email delivery row not found.")

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    if confirm_retry != "true":
        return _redirect_to_admin_email_delivery(
            parsed_email_delivery_id,
            message="email_delivery_retry_confirmation_required",
        )

    mode = (retry_mode or "").strip()
    if mode not in {_RETRY_MODE_SEND_NOW, _RETRY_MODE_ENQUEUE}:
        return _redirect_to_admin_email_delivery(
            parsed_email_delivery_id,
            message="email_delivery_retry_mode_required",
        )

    try:
        _validate_admin_email_delivery_preconditions(settings, mode)
    except ValueError:
        return _redirect_to_admin_email_delivery(
            parsed_email_delivery_id,
            message="email_delivery_configuration_required",
        )

    # Shared nonblank / 1024-UTF-8-bytes / known-secret-safe reason law.
    try:
        validated_reason = validate_retry_reason(reason)
    except EmailAdminOperationError as exc:
        return _redirect_to_admin_email_delivery(
            parsed_email_delivery_id,
            message=_RETRY_REASON_MESSAGES.get(
                exc.code, "email_delivery_retry_reason_withheld"
            ),
        )
    if _known_alias(request, validated_reason):
        return _redirect_to_admin_email_delivery(
            parsed_email_delivery_id,
            message="email_delivery_retry_reason_withheld",
        )

    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        service = EmailDeliveryService(
            settings=settings,
            one_time_secrets_repository=OneTimeSecretsRepository(session),
            email_deliveries_repository=EmailDeliveriesRepository(session),
            gateway_keys_repository=GatewayKeysRepository(session),
            owners_repository=OwnersRepository(session),
            audit_repository=AuditRepository(session),
            email_service=EmailService(settings),
            session=session,
        )
        try:
            # Shared current-Core preflight: exact row, exact secret
            # binding, same-secret history, current lifecycle.
            sendability = await service.get_key_email_delivery_sendability(
                parsed_email_delivery_id
            )
            if sendability.email_delivery_status != "failed":
                # 215-a: a failed-only flag on a now-pending (or any
                # other non-failed) row refuses with a TRUTHFUL
                # not-failed/not-applicable message (the FAILED-only
                # wording is reserved for the genuine failed-row
                # redirects); the ordinary pending flows remain the
                # send-now/enqueue actions. No dispatch happens.
                return _redirect_to_admin_email_delivery(
                    parsed_email_delivery_id,
                    message="email_delivery_retry_not_applicable",
                )
            if not sendability.can_send or sendability.one_time_secret_id is None:
                return _redirect_to_admin_email_delivery(
                    parsed_email_delivery_id,
                    message="email_delivery_not_sendable",
                )
            one_time_secret_id = sendability.one_time_secret_id

            if mode == _RETRY_MODE_SEND_NOW:
                result = await service.send_pending_key_email(
                    one_time_secret_id=one_time_secret_id,
                    email_delivery_id=parsed_email_delivery_id,
                    actor_admin_id=action_context.admin_user.id,
                    reason=validated_reason,
                )
                if result.status == "sent":
                    message = "email_delivery_sent"
                elif result.status == "ambiguous":
                    message = "email_delivery_ambiguous"
                else:
                    message = "email_delivery_send_failed"
                return _redirect_to_admin_email_delivery(
                    parsed_email_delivery_id, message=message
                )

            # Enqueue: persist the requested intent (server actor,
            # server reason, explicit retry intent) and COMMIT before
            # broker dispatch. The worker keeps its independent atomic
            # claim/consume/history law; the payload stays exactly the
            # existing three UUIDs.
            try:
                await record_enqueue_request_audit(
                    session=session,
                    one_time_secret_id=one_time_secret_id,
                    email_delivery_id=parsed_email_delivery_id,
                    actor_admin_id=action_context.admin_user.id,
                    reason=validated_reason,
                    retry_failed=True,
                )
            except Exception as exc:  # noqa: BLE001 - safe fixed recovery
                # The requested intent is NOT confirmed durable: a
                # recording failure must prevent broker dispatch entirely
                # (no intent to attribute, no queued/sent promise).
                logger.warning(
                    "admin_email_retry_enqueue_record_failed",
                    email_delivery_id=str(parsed_email_delivery_id),
                    error_type=type(exc).__name__,
                )
                return _redirect_to_admin_email_delivery(
                    parsed_email_delivery_id,
                    message="email_delivery_enqueue_recording_unconfirmed",
                )
            try:
                _enqueue_admin_pending_key_email(
                    one_time_secret_id=one_time_secret_id,
                    email_delivery_id=parsed_email_delivery_id,
                    actor_admin_id=action_context.admin_user.id,
                )
            except Exception:  # noqa: BLE001 - honest requested-but-unconfirmed
                # The intent audit is already durable (requested intent);
                # a broker failure/lost ack is never queued/sent success.
                return _redirect_to_admin_email_delivery(
                    parsed_email_delivery_id,
                    message="email_delivery_enqueue_unconfirmed",
                )
            return _redirect_to_admin_email_delivery(
                parsed_email_delivery_id, message="email_delivery_queued"
            )
        except ValueError:
            return _redirect_to_admin_email_delivery(
                parsed_email_delivery_id,
                message="email_delivery_configuration_required",
            )
        except EmailError:
            return _redirect_to_admin_email_delivery(
                parsed_email_delivery_id,
                message="email_delivery_send_failed",
            )


@router.get("/email-operations/smtp-test", response_class=HTMLResponse)
async def admin_smtp_test_form(request: Request) -> Response:
    """Bounded SMTP test form (one validated recipient, useful help)."""
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return templates.TemplateResponse(
        request,
        "email_operations/smtp_test.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "admin_status_message": _admin_status_message(request),
            "readiness": _smtp_test_readiness(settings),
            "default_subject": SMTP_TEST_DEFAULT_SUBJECT,
            "default_body": SMTP_TEST_DEFAULT_BODY,
            "budget_attempts": SMTP_TEST_BUDGET_ATTEMPTS,
            "budget_window_seconds": SMTP_TEST_BUDGET_WINDOW_SECONDS,
        },
    )


def _render_smtp_test_review(
    request: Request,
    *,
    action_context,
    csrf_token: str,
    facts: SmtpTestFacts | None,
    review_token: str | None,
    result: object | None,
    error: str | None,
    result_recorded: bool = True,
) -> Response:
    """Render the reviewed SMTP test confirmation/outcome page."""
    return templates.TemplateResponse(
        request,
        "email_operations/smtp_test_review.html",
        {
            "admin": action_context.admin_user,
            "csrf_token": csrf_token,
            "admin_status_message": _admin_status_message(request),
            "facts": facts,
            "review_token": review_token,
            "result": result,
            "error": error,
            "result_recorded": result_recorded,
            "budget_attempts": SMTP_TEST_BUDGET_ATTEMPTS,
            "budget_window_seconds": SMTP_TEST_BUDGET_WINDOW_SECONDS,
            "outer_deadline_seconds": smtp_test_outer_deadline(_settings(request)),
        },
    )


@router.post("/email-operations/smtp-test/review", response_class=HTMLResponse)
async def admin_smtp_test_review(request: Request) -> Response:
    """Validate the test fields and bind the signed one-use review intent.

    Nothing is sent here: this stage prepares the reviewed facts, checks
    configuration readiness, refuses known incoming authentication
    aliases, and signs the actor/session/expiry-bound review token that
    the apply stage verifies.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    if not _smtp_test_ready(settings):
        return _admin_error_page(
            request,
            status_code=400,
            message="Email delivery is disabled or SMTP configuration is incomplete; the test cannot be prepared.",
        )

    recipient = str(form.get("recipient") or "")
    subject = str(form.get("subject") or "")
    body = str(form.get("body") or "")

    try:
        facts = prepare_smtp_test_facts(
            recipient=recipient or None,
            subject=subject or None,
            body=body or None,
            nonce=secrets.token_hex(16),
        )
    except EmailAdminOperationError as exc:
        return _admin_error_page(request, status_code=400, message=exc.safe_message)

    # The reviewed facts are displayed content: a known incoming
    # authentication alias is refused BEFORE signing or rendering
    # (never echoed).
    if any(_known_alias(request, value) for value in (facts.recipient, facts.subject, facts.body)):
        return _admin_error_page(
            request,
            status_code=400,
            message="A reviewed value matches a known incoming authentication value and cannot be used. Prepare the test again.",
        )

    try:
        token = build_smtp_test_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
            review_document=facts.as_review_document(),
        )
    except AdminReviewIntentError as exc:
        return _admin_error_page(request, status_code=400, message=exc.message)

    return _render_smtp_test_review(
        request,
        action_context=action_context,
        csrf_token=csrf_token,
        facts=facts,
        review_token=token,
        result=None,
        error=None,
    )


@router.get("/email-operations/smtp-test/apply", response_class=HTMLResponse)
async def admin_smtp_test_apply_recovery(request: Request) -> Response:
    """Safe NO-SEND recovery surface for a reload/bookmark of the
    POST-only apply URL: a fixed notice and a link back to the new-test
    page.  It never resends, never re-claims, and carries no live
    one-use token (existing page-context pattern; no new surface)."""
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return templates.TemplateResponse(
        request,
        "email_operations/smtp_test_review.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "admin_status_message": _admin_status_message(request),
            "facts": None,
            "review_token": None,
            "result": None,
            "error": None,
            "result_recorded": True,
            "recovery": True,
            "budget_attempts": SMTP_TEST_BUDGET_ATTEMPTS,
            "budget_window_seconds": SMTP_TEST_BUDGET_WINDOW_SECONDS,
            "outer_deadline_seconds": smtp_test_outer_deadline(settings),
        },
    )


@router.post("/email-operations/smtp-test/apply", response_class=HTMLResponse)
async def admin_smtp_test_apply(request: Request) -> Response:
    """Verify the signed review, claim one-use, then attempt SMTP bounded.

    The token is reviewed data, never authority: posted recipient/
    subject/body overrides confer nothing (the signed facts are the
    only content). The one-use claim is recorded durably BEFORE the
    external SMTP call (atomic across API workers on the existing
    actor-row lock + audit facts); a lost result after the claim is
    unconfirmed, never permission to send again. The per-actor budget
    counts attempted and unconfirmed sends honestly.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    review_token = str(form.get("review_token") or "")
    confirm_send_test = str(form.get("confirm_send_test") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    try:
        document = verify_smtp_test_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            token=review_token,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
        )
        facts = SmtpTestFacts(
            recipient=str(document["recipient"]),
            subject=str(document["subject"]),
            body=str(document["body"]),
            nonce=str(document["nonce"]),
        )
    except AdminReviewIntentError as exc:
        return _admin_error_page(request, status_code=400, message=exc.message)

    # The signed facts are displayed content: a known incoming
    # authentication alias is refused IMMEDIATELY after verify/parse,
    # BEFORE any render or claim (missing-confirm and readiness refusals
    # no longer echo the reviewed facts before this guard).
    if any(_known_alias(request, value) for value in (facts.recipient, facts.subject, facts.body)):
        return _admin_error_page(
            request,
            status_code=400,
            message="The reviewed SMTP test can no longer be applied: a reviewed value matches a known incoming authentication value. Prepare the test again.",
        )

    if not _is_checked(confirm_send_test):
        return _render_smtp_test_review(
            request,
            action_context=action_context,
            csrf_token=csrf_token,
            facts=facts,
            review_token=review_token,
            result=None,
            error="Confirm the reviewed SMTP test before sending.",
        )

    if not _smtp_test_ready(settings):
        return _render_smtp_test_review(
            request,
            action_context=action_context,
            csrf_token=csrf_token,
            facts=facts,
            review_token=review_token,
            result=None,
            error="Email delivery is disabled or SMTP configuration is incomplete; the test cannot be attempted.",
        )

    session_factory = get_sessionmaker_from_app(request)
    ip_address = _client_host(request)
    # AuditRepository stores the top-level user_agent/request_id RAW;
    # mask known incoming authentication aliases BEFORE persistence
    # (global sanitizer unchanged).
    user_agent = _safe_audit_user_agent(request, request.headers.get("user-agent"))
    request_id = _safe_audit_user_agent(request, _admin_request_id(request))

    # 1) one-use claim (committed BEFORE the external SMTP call).  If
    # claim durability cannot be confirmed, the attempt is NEVER
    # dispatched: a fixed safe unconfirmed recovery, no retry token, no
    # raw exception/prose.
    try:
        async with session_factory() as session:
            await claim_smtp_test_attempt(
                session=session,
                admin_users_repository=AdminUsersRepository(session),
                audit_repository=AuditRepository(session),
                actor_admin_id=action_context.admin_user.id,
                intent_nonce=facts.nonce,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
    except SmtpTestIntentAlreadyClaimedError as exc:
        return _render_smtp_test_review(
            request,
            action_context=action_context,
            csrf_token=csrf_token,
            facts=facts,
            review_token=None,
            result=None,
            error=exc.safe_message,
        )
    except SmtpTestBudgetExceededError as exc:
        return _render_smtp_test_review(
            request,
            action_context=action_context,
            csrf_token=csrf_token,
            facts=facts,
            review_token=None,
            result=None,
            error=exc.safe_message,
        )
    except Exception as exc:  # noqa: BLE001 - safe fixed recovery
        # Claim durability unconfirmed (commit/DB fault): never dispatch.
        logger.warning(
            "admin_smtp_test_claim_unconfirmed",
            actor_admin_id=str(action_context.admin_user.id),
            error_type=type(exc).__name__,
        )
        return _render_smtp_test_review(
            request,
            action_context=action_context,
            csrf_token=csrf_token,
            facts=facts,
            review_token=None,
            result=None,
            error=(
                "The test attempt recording could not be confirmed "
                "before sending; no email was sent and no retry was "
                "scheduled. Prepare the test again."
            ),
        )

    # 2) bounded SMTP attempt through the existing primitive.
    outcome = await run_smtp_test_with_deadline(
        settings=settings,
        email_service=EmailService(settings),
        recipient=facts.recipient,
        subject=facts.subject,
        body=facts.body,
    )

    # 3) durable finite result.  The claim/budget stay consumed
    # regardless: if the RESULT recording fails after the attempt, the
    # page keeps the truthful outcome (an accepted send is still shown
    # accepted) plus a record-unconfirmed note - never a rollback or
    # no-message promise.
    result_recorded = True
    try:
        async with session_factory() as session:
            await record_smtp_test_result(
                session=session,
                audit_repository=AuditRepository(session),
                actor_admin_id=action_context.admin_user.id,
                intent_nonce=facts.nonce,
                outcome=outcome,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
    except Exception as exc:  # noqa: BLE001 - safe fixed recovery
        result_recorded = False
        logger.warning(
            "admin_smtp_test_result_unrecorded",
            actor_admin_id=str(action_context.admin_user.id),
            outcome=outcome.result,
            error_type=type(exc).__name__,
        )

    return _render_smtp_test_review(
        request,
        action_context=action_context,
        csrf_token=csrf_token,
        facts=facts,
        review_token=None,
        result=outcome,
        error=None,
        result_recorded=result_recorded,
    )

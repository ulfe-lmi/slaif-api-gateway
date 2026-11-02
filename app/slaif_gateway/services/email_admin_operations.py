"""Shared admin-operation seams for GUI email delivery actions (215-a).

This module is the single application-level home for the operations the
CLI ``email send-pending-key`` command and the admin GUI must behave
identically for:

- the bounded nonblank known-secret-safe retry reason law (1024 UTF-8
  BYTES, not characters);
- the operator enqueue-REQUEST intent audit (committed BEFORE broker
  dispatch, referencing the one-time secret under the SAFE field name
  ``one_time_reference_id``);
- the bounded SMTP test field law and the one-use, per-actor-budgeted
  SMTP test orchestration for the admin GUI.

The web layer imports ONLY this module and existing services - never
``cli``. The CLI keeps its stable public/testing surface by delegating
to the same seams with unchanged ordering, metadata, and defaults.
Nothing here decrypts, renders, or sends key material; the Celery task
payload stays exactly the existing three UUID arguments.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from email import errors as _email_errors
from email.headerregistry import Address as _Address
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.services.email_errors import (
    EmailDeliveryDisabledError,
    SmtpConfigurationError,
    SmtpSendError,
)
from slaif_gateway.services.email_service import EmailService
from slaif_gateway.services.provider_route_configuration import (
    contains_known_secret_shape,
)

# Consistent with the existing operator audit-reason bound
# (services/openai_compatible_setup.py: 1024 UTF-8 bytes).
RETRY_REASON_MAX_BYTES = 1024

# Bounded GUI SMTP test field bounds (explicit GUI resource bounds; the
# CLI test defaults are unchanged).
SMTP_TEST_RECIPIENT_MAX_CHARS = 254  # RFC 5321 mailbox maximum
SMTP_TEST_SUBJECT_MAX_BYTES = 255
SMTP_TEST_BODY_MAX_BYTES = 4096

# Outer per-attempt deadline for one GUI SMTP test. SMTP_TIMEOUT_SECONDS
# currently accepts any positive number (per socket operation), so the
# per-actor budget alone cannot bound a hung test; the outer deadline is
# min(30s, configured SMTP timeout) and is applied around the EXISTING
# EmailService.send_email primitive (no new transport).
SMTP_TEST_OUTER_DEADLINE_SECONDS = 30.0

# Per-actor GUI test-attempt budget: 3 attempts per 60 seconds.
# Attempted and unconfirmed sends count honestly (a lost result after a
# claimed attempt is unconfirmed, not free).
SMTP_TEST_BUDGET_ATTEMPTS = 3
SMTP_TEST_BUDGET_WINDOW_SECONDS = 60

# Harmless defaults; contain no gateway key or secret material. The
# CLI test keeps its own defaults (cli/email.py).
SMTP_TEST_DEFAULT_SUBJECT = "SLAIF API Gateway test email"
SMTP_TEST_DEFAULT_BODY = "SLAIF API Gateway SMTP test email."

# Finite audit vocabulary for the GUI SMTP test intent records.
SMTP_TEST_CLAIM_ACTION = "email_smtp_test_claimed"
SMTP_TEST_RESULT_ACTION = "email_smtp_test_resulted"
SMTP_TEST_ENTITY_TYPE = "email_smtp_test"

_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")

# One complete bare mailbox: no display names, no groups/lists, no quoted
# local parts, no port/angle syntax. Anything containing one of these
# characters is refused BEFORE parsing so the stdlib parser can never be
# asked to reinterpret the value into a DIFFERENT address (e.g.
# ``first:second@example.invalid`` parses to display-name + a second
# address, and ``user@example.invalid:25`` parses to an empty address).
_RECIPIENT_FORBIDDEN_CHARS = frozenset(
    (',', ';', '<', '>', ':', '\\', '"', ' ', '\t', '\r', '\n', '\x00')
)


class EmailAdminOperationError(ValueError):
    """Fixed safe validation failure for shared email admin operations.

    ``code`` is a finite machine-readable vocabulary; ``safe_message``
    names the field and bound only and never echoes supplied values.
    """

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class SmtpTestIntentAlreadyClaimedError(EmailAdminOperationError):
    """The exact reviewed SMTP test intent was already used (one-use)."""


class SmtpTestBudgetExceededError(EmailAdminOperationError):
    """The per-actor 3-attempts-per-60-seconds budget is exhausted."""


@dataclass(frozen=True, slots=True)
class SmtpTestFacts:
    """The exact reviewed SMTP test content (defaults already applied)."""

    recipient: str
    subject: str
    body: str
    nonce: str

    def as_review_document(self) -> dict[str, str]:
        return {
            "recipient": self.recipient,
            "subject": self.subject,
            "body": self.body,
            "nonce": self.nonce,
        }


@dataclass(frozen=True, slots=True)
class SmtpTestOutcome:
    """Fixed safe SMTP test outcome label (never raw provider prose)."""

    result: str  # "accepted" | "unconfirmed" | "failed" | "unavailable"


def validate_retry_reason(reason: str | None) -> str:
    """Shared nonblank/byte-bound/known-secret-safe retry reason law.

    Returns the ORIGINAL value unchanged (the valid reason is preserved
    consistently with the audited value). The bound is UTF-8 BYTES: a
    multibyte reason may be far shorter in characters and still valid,
    and a 1025-byte multibyte reason is refused, not silently trimmed.
    """
    if reason is None or not reason.strip():
        raise EmailAdminOperationError(
            "blank", "The audit reason must be nonblank."
        )
    if len(reason.encode("utf-8")) > RETRY_REASON_MAX_BYTES:
        raise EmailAdminOperationError(
            "too_long",
            "The audit reason is too long. Keep it to at most "
            f"{RETRY_REASON_MAX_BYTES} UTF-8 bytes.",
        )
    if contains_known_secret_shape(reason):
        raise EmailAdminOperationError(
            "known_secret",
            "The audit reason was withheld: it matches a recognized "
            "credential pattern.",
        )
    return reason


def validate_smtp_test_recipient(value: str | None) -> str:
    """Validate ONE complete bare mailbox; return EXACTLY what is sent.

    The returned string is the canonical recipient: it is shown in the
    review, signed into the review token, and set as the SMTP ``To``
    header verbatim - the standard-library addr-spec grammar must
    round-trip it to itself (``email.headerregistry.Address``), so the
    displayed/signed recipient is exactly what ``EmailService.send_email``
    sends.  CR/LF/NUL are rejected on the RAW value BEFORE any
    strip/default; groups, display names, quoted local parts, and
    trailing syntax (``addr:25``) are refused up front; a value a list
    parser would reinterpret (``first:second@example.invalid``), a
    missing domain (``localonly``), a missing local part
    (``@example.invalid``), or an empty label (``a@example..invalid``)
    can never pass.
    """
    if value is None:
        raise EmailAdminOperationError(
            "recipient_missing", "The test recipient is required."
        )
    if any(ch in value for ch in ("\r", "\n", "\x00")):
        raise EmailAdminOperationError(
            "recipient_invalid", "The test recipient is not a single email address."
        )
    recipient = value.strip()
    if not recipient:
        raise EmailAdminOperationError(
            "recipient_missing", "The test recipient is required."
        )
    if any(ch in recipient for ch in _RECIPIENT_FORBIDDEN_CHARS):
        raise EmailAdminOperationError(
            "recipient_invalid", "The test recipient is not a single email address."
        )
    if len(recipient) > SMTP_TEST_RECIPIENT_MAX_CHARS:
        raise EmailAdminOperationError(
            "recipient_invalid",
            f"The test recipient exceeds {SMTP_TEST_RECIPIENT_MAX_CHARS} characters.",
        )
    # One complete mailbox via the standard-library grammar (addr-spec:
    # a LIST parser like getaddresses is NOT a mailbox validator - it
    # reinterprets display names and silently drops trailing syntax).
    # Syntax failures are fixed safe refusals, never echoed.
    try:
        parsed = _Address(addr_spec=recipient)
    except (ValueError, TypeError, _email_errors.HeaderParseError):
        raise EmailAdminOperationError(
            "recipient_invalid", "The test recipient is not a single email address."
        ) from None
    if not parsed.username or not parsed.domain:
        raise EmailAdminOperationError(
            "recipient_invalid", "The test recipient is not a single email address."
        )
    # Canonical target consistency: the EXACT validated string is what
    # the review shows, what is signed, and what EmailService sends.
    if str(parsed) != recipient:
        raise EmailAdminOperationError(
            "recipient_invalid", "The test recipient is not a single email address."
        )
    if contains_known_secret_shape(recipient):
        raise EmailAdminOperationError(
            "recipient_withheld",
            "The test recipient was withheld: it matches a recognized "
            "credential pattern.",
        )
    return recipient


def validate_smtp_test_subject(value: str | None) -> str:
    """Bounded test subject: at most 255 UTF-8 bytes, no CR/LF/NUL.

    CR/LF/NUL are rejected on the RAW value BEFORE any strip/default: a
    CRLF-only subject is refused, never silently replaced by the default.
    """
    if value is None:
        return SMTP_TEST_DEFAULT_SUBJECT
    if any(ch in value for ch in ("\r", "\n", "\x00")):
        raise EmailAdminOperationError(
            "subject_invalid", "The test subject must not contain line breaks."
        )
    if not value.strip():
        return SMTP_TEST_DEFAULT_SUBJECT
    subject = value.strip()
    if len(subject.encode("utf-8")) > SMTP_TEST_SUBJECT_MAX_BYTES:
        raise EmailAdminOperationError(
            "subject_too_long",
            f"The test subject exceeds {SMTP_TEST_SUBJECT_MAX_BYTES} UTF-8 bytes.",
        )
    if contains_known_secret_shape(subject):
        raise EmailAdminOperationError(
            "subject_withheld",
            "The test subject was withheld: it matches a recognized "
            "credential pattern.",
        )
    return subject


def validate_smtp_test_body(value: str | None) -> str:
    """Bounded plain-text test body: at most 4096 UTF-8 bytes, no NUL.

    NUL is rejected on the RAW value BEFORE the blank/default path (a
    NUL-only body is refused, never silently replaced by the default).
    """
    if value is None:
        return SMTP_TEST_DEFAULT_BODY
    if "\x00" in value:
        raise EmailAdminOperationError(
            "body_invalid", "The test body must not contain NUL characters."
        )
    if not value.strip():
        return SMTP_TEST_DEFAULT_BODY
    body = value
    if len(body.encode("utf-8")) > SMTP_TEST_BODY_MAX_BYTES:
        raise EmailAdminOperationError(
            "body_too_long",
            f"The test body exceeds {SMTP_TEST_BODY_MAX_BYTES} UTF-8 bytes.",
        )
    if contains_known_secret_shape(body):
        raise EmailAdminOperationError(
            "body_withheld",
            "The test body was withheld: it matches a recognized "
            "credential pattern.",
        )
    return body


def prepare_smtp_test_facts(
    *,
    recipient: str | None,
    subject: str | None,
    body: str | None,
    nonce: str,
) -> SmtpTestFacts:
    """Validate all test fields and apply safe defaults in one seam.

    ``nonce`` is the one-use reviewed-intent identity (32 hex chars,
    generated by the caller); it is a random opaque token, never message
    content, and it is what the one-use claim and budget guard on.
    """
    if not _NONCE_RE.fullmatch(nonce):
        raise EmailAdminOperationError(
            "nonce_invalid", "The reviewed test intent is missing or invalid."
        )
    return SmtpTestFacts(
        recipient=validate_smtp_test_recipient(recipient),
        subject=validate_smtp_test_subject(subject),
        body=validate_smtp_test_body(body),
        nonce=nonce,
    )


async def record_enqueue_request_audit(
    *,
    session: AsyncSession,
    one_time_secret_id: uuid.UUID,
    email_delivery_id: uuid.UUID | None,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
    retry_failed: bool,
) -> None:
    """Bounded safe operator enqueue-REQUEST intent audit; commit BEFORE dispatch.

    Shared by the CLI and the GUI (the web layer never imports CLI).
    The one-time secret is referenced under the SAFE field name
    ``one_time_reference_id`` (strictly the already-parsed UUID string):
    the durable metadata sanitizer intentionally drops secret-bearing
    key names such as ``one_time_secret_id`` from every audit record,
    and this event must not relax that global boundary. The reference
    keeps the intent attributable for no-ID enqueues (entity_id NULL).
    """
    await AuditRepository(session).add_audit_log(
        action="email_key_enqueue_requested",
        entity_type="email_delivery",
        entity_id=email_delivery_id,
        admin_user_id=actor_admin_id,
        note=reason,
        new_values={
            "one_time_reference_id": str(one_time_secret_id),
            "email_delivery_id": str(email_delivery_id) if email_delivery_id else None,
            "actor_admin_id": str(actor_admin_id) if actor_admin_id else None,
            "intent": "enqueue_requested",
            "retry_failed": retry_failed,
        },
    )
    await session.commit()


class AdminUserLockRepository(Protocol):
    """Directly necessary existing-row lock seam for the SMTP test guard."""

    async def get_admin_user_for_update(self, admin_user_id: uuid.UUID) -> object: ...


def _intent_entity_id(intent_nonce: str) -> uuid.UUID:
    """Map the one-use intent nonce to its durable nonsecret identity.

    The 32-hex nonce is exactly a UUID, and ``AuditLog.entity_id`` is a
    bound column - NOT sanitized metadata - so the durable claim/result
    identity survives the global metadata sanitizer untouched (a key
    named like a nonce would be masked to ``***`` in ``new_values``).
    The nonce string itself never reaches audit metadata: the identity
    is bound as action + entity_type + entity_id + actor.
    """
    return uuid.UUID(hex=intent_nonce)


async def claim_smtp_test_attempt(
    *,
    session: AsyncSession,
    admin_users_repository: AdminUserLockRepository,
    audit_repository: object,
    actor_admin_id: uuid.UUID,
    intent_nonce: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    """Record the one-use SMTP test claim durably BEFORE any SMTP call.

    Atomic across the deployed API workers: the actor row is locked
    (existing PostgreSQL row lock) for the whole check-insert-commit, so
    two concurrent claims by the same actor serialize and the second
    sees the committed claim. The claim is committed before the caller
    may attempt SMTP; a lost result after the claim is unconfirmed,
    never permission to send again. No new table, outbox, job system,
    or Redis dependency.
    """
    actor = await admin_users_repository.get_admin_user_for_update(actor_admin_id)
    if actor is None:
        raise SmtpTestIntentAlreadyClaimedError(
            "already_claimed",
            "The reviewed test intent can no longer be used for this admin.",
        )
    existing = await audit_repository.get_smtp_test_claim(
        admin_user_id=actor_admin_id, intent_nonce=intent_nonce
    )
    if existing is not None:
        raise SmtpTestIntentAlreadyClaimedError(
            "already_claimed",
            "This reviewed test intent was already used. Submit a new test "
            "if another attempt is needed.",
        )
    since = datetime.now(UTC) - timedelta(seconds=SMTP_TEST_BUDGET_WINDOW_SECONDS)
    attempts = await audit_repository.count_recent_smtp_test_attempts(
        admin_user_id=actor_admin_id, since=since
    )
    if attempts >= SMTP_TEST_BUDGET_ATTEMPTS:
        raise SmtpTestBudgetExceededError(
            "cooldown",
            f"Test email cooldown active: at most {SMTP_TEST_BUDGET_ATTEMPTS} "
            f"attempts per {SMTP_TEST_BUDGET_WINDOW_SECONDS} seconds per admin. "
            "Wait, then submit a new test.",
        )
    await audit_repository.add_audit_log(
        action=SMTP_TEST_CLAIM_ACTION,
        entity_type=SMTP_TEST_ENTITY_TYPE,
        entity_id=_intent_entity_id(intent_nonce),
        admin_user_id=actor_admin_id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        new_values={"result": "claimed"},
    )
    await session.commit()


async def record_smtp_test_result(
    *,
    session: AsyncSession,
    audit_repository: object,
    actor_admin_id: uuid.UUID,
    intent_nonce: str,
    outcome: SmtpTestOutcome,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    """Append the finite test result (fixed vocabulary; no provider prose).

    Same intent identity (entity_id) as the claim, so the result links
    to the exact one-use attempt.
    """
    await audit_repository.add_audit_log(
        action=SMTP_TEST_RESULT_ACTION,
        entity_type=SMTP_TEST_ENTITY_TYPE,
        entity_id=_intent_entity_id(intent_nonce),
        admin_user_id=actor_admin_id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        new_values={"result": outcome.result},
    )
    await session.commit()


def smtp_test_outer_deadline(settings: Settings) -> float:
    """Outer per-attempt deadline: min(30s, configured SMTP timeout).

    SMTP_TIMEOUT_SECONDS is validated positive by Settings; when it is
    shorter than the 30s cap it bounds the test sooner (a legitimate
    multi-operation SMTP transaction with a very short per-operation
    timeout may then be reported UNCONFIRMED instead of silently
    exceeding the operator's configured bound - the claim and budget
    stay consumed and nothing auto-retries).
    """
    return min(SMTP_TEST_OUTER_DEADLINE_SECONDS, float(settings.SMTP_TIMEOUT_SECONDS))


def _smtp_explicit_refusal(cause: BaseException | None) -> bool:
    """True only when the client error EXPLICITLY shows no SMTP acceptance.

    Connect/Helo/authentication/MAIL-FROM/RCPT-TO refusals and an
    explicit server data refusal all occur with a definite server
    response (or no connection at all) BEFORE the message can have been
    accepted.  Any other client failure has an UNKNOWN stage (the
    primitive wraps every send fault in one SmtpSendError) and must be
    reported UNCONFIRMED - never as a definitive non-acceptance.
    """
    if cause is None:
        return False
    try:
        from aiosmtplib import errors as smtp_errors
    except ImportError:  # stage unknown -> unconfirmed
        return False
    explicit = (
        smtp_errors.SMTPConnectError,  # covers connect response/timeout variants
        smtp_errors.SMTPHeloError,
        smtp_errors.SMTPAuthenticationError,
        smtp_errors.SMTPSenderRefused,
        smtp_errors.SMTPRecipientRefused,
        smtp_errors.SMTPRecipientsRefused,
        smtp_errors.SMTPDataError,
    )
    return isinstance(cause, explicit)


async def run_smtp_test_with_deadline(
    *,
    settings: Settings,
    email_service: EmailService,
    recipient: str,
    subject: str,
    body: str,
) -> SmtpTestOutcome:
    """Send one reviewed test through the existing primitive, bounded.

    Outcomes are the finite safe vocabulary; the primitive's raw-ish
    provider_status/message_id are NOT surfaced to the browser.
    ``failed`` is reserved for EXPLICIT pre-dispatch refusals; a
    stage-unknown client failure after dispatch is ``unconfirmed`` (SMTP
    may have accepted). The one-use claim and budget stay consumed in
    every non-accepted outcome; nothing auto-retries.
    """
    try:
        await asyncio.wait_for(
            email_service.send_email(to=recipient, subject=subject, text_body=body),
            timeout=smtp_test_outer_deadline(settings),
        )
    except asyncio.TimeoutError:
        # A timeout after dispatch can mean SMTP accepted: unconfirmed.
        return SmtpTestOutcome(result="unconfirmed")
    except (EmailDeliveryDisabledError, SmtpConfigurationError):
        return SmtpTestOutcome(result="unavailable")
    except SmtpSendError as exc:
        if _smtp_explicit_refusal(exc.__cause__):
            return SmtpTestOutcome(result="failed")
        return SmtpTestOutcome(result="unconfirmed")
    return SmtpTestOutcome(result="accepted")

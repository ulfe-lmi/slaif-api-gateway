"""215-a G12 shared email admin operations: focused validator/intent/ASGI proofs.

Pure-in-memory proofs for the shared seams (no SMTP, no DB):

- the bounded retry-reason law (UTF-8 BYTES, not characters) with the
  exact multibyte boundary;
- ONE complete bare mailbox recipient validation (the stdlib list
  parser is not a mailbox validator: display names, missing local
  parts/domains, empty labels, and trailing syntax are all refused and
  the canonical round-trip is proven);
- raw CR/LF/NUL refusals BEFORE strip/default (a CRLF-only subject is
  never silently replaced by the default);
- the JSON-escape-budgeted signed review intent (a valid 4096-byte
  multiline/escaped body round-trips exactly; overbound fields are
  still refused);
- the one-use claim + per-actor budget at the repository seam;
- the finite SMTP outcome mapping (explicit pre-dispatch refusals are
  failed; every stage-unknown client failure is unconfirmed);
- focused valid-auth/CSRF canaries through the GUI routes, including
  the pre-dispatch claim fault (no SMTP call), the post-accept result
  fault (accepted stays shown, record unconfirmed), and the enqueue
  recording fault (no broker dispatch).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiosmtplib import errors as smtp_errors
from fastapi.testclient import TestClient

from slaif_gateway.api import admin_email_operations
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    build_smtp_test_review_token,
    verify_smtp_test_review_token,
)
from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.main import create_app
from slaif_gateway.services.admin_session_service import AdminSessionContext
from slaif_gateway.services.email_admin_operations import (
    RETRY_REASON_MAX_BYTES,
    SMTP_TEST_BUDGET_ATTEMPTS,
    SMTP_TEST_DEFAULT_BODY,
    SMTP_TEST_DEFAULT_SUBJECT,
    SMTP_TEST_OUTER_DEADLINE_SECONDS,
    SMTP_TEST_RECIPIENT_MAX_CHARS,
    SMTP_TEST_SUBJECT_MAX_BYTES,
    EmailAdminOperationError,
    SmtpTestBudgetExceededError,
    SmtpTestFacts,
    SmtpTestIntentAlreadyClaimedError,
    SmtpTestOutcome,
    claim_smtp_test_attempt,
    prepare_smtp_test_facts,
    record_enqueue_request_audit,
    record_smtp_test_result,
    run_smtp_test_with_deadline,
    smtp_test_outer_deadline,
    validate_retry_reason,
    validate_smtp_test_body,
    validate_smtp_test_recipient,
    validate_smtp_test_subject,
)
from slaif_gateway.services.email_delivery_service import (
    KeyEmailDeliverySendability,
    PendingKeyEmailResult,
)
from slaif_gateway.services.email_errors import (
    EmailDeliveryDisabledError,
    SmtpConfigurationError,
    SmtpSendError,
)

SECRET_SHAPED = "sk-slaif-abcdef0123456789abcdef0123456789abcdef01"


# ---------------------------------------------------------------------------
# Retry reason law (UTF-8 bytes, not characters)
# ---------------------------------------------------------------------------


def test_retry_reason_requires_nonblank() -> None:
    for value in (None, "", "   ", "\t\n"):
        with pytest.raises(EmailAdminOperationError) as exc:
            validate_retry_reason(value)
        assert exc.value.code == "blank"


def test_retry_reason_byte_bound_is_utf8_not_chars() -> None:
    # 1024 ASCII bytes: accepted, original preserved verbatim.
    ascii_1024 = "r" * RETRY_REASON_MAX_BYTES
    assert validate_retry_reason(ascii_1024) == ascii_1024
    # 1025 ASCII bytes: refused (not silently trimmed).
    with pytest.raises(EmailAdminOperationError) as exc:
        validate_retry_reason("r" * (RETRY_REASON_MAX_BYTES + 1))
    assert exc.value.code == "too_long"
    # Multibyte boundary: "é" is 2 UTF-8 bytes.  512 chars = exactly
    # 1024 bytes (accepted); 513 chars = 1026 bytes (refused) even
    # though it is far shorter than 1024 characters.
    assert len(("é" * 512).encode("utf-8")) == RETRY_REASON_MAX_BYTES
    assert validate_retry_reason("é" * 512) == "é" * 512
    with pytest.raises(EmailAdminOperationError) as exc:
        validate_retry_reason("é" * 513)
    assert exc.value.code == "too_long"


def test_retry_reason_refuses_known_secret_shape() -> None:
    with pytest.raises(EmailAdminOperationError) as exc:
        validate_retry_reason(f"rotated {SECRET_SHAPED} for ops")
    assert exc.value.code == "known_secret"


# ---------------------------------------------------------------------------
# Recipient: ONE complete bare mailbox (canonical target consistency)
# ---------------------------------------------------------------------------


def test_recipient_accepts_one_complete_mailbox_verbatim() -> None:
    for value in (
        "ops@example.invalid",
        "first.last+tag@sub.example.invalid",
        "a_b-c%d@ex-ample.invalid",
    ):
        assert validate_smtp_test_recipient(value) == value


def test_recipient_refuses_list_parser_reinterpretations() -> None:
    # getaddresses would send these to a DIFFERENT address:
    for value in (
        "first:second@example.invalid",  # display name + second address
        "user@example.invalid:25",  # trailing port syntax
        "a@b.invalid, c@d.invalid",  # address list
        "group:a@b.invalid;",  # group syntax
        '"quoted"@example.invalid',  # quoted local part
        "<user@example.invalid>",  # angle syntax
        "user@exa\\mple.invalid",  # backslash escape
    ):
        with pytest.raises(EmailAdminOperationError):
            validate_smtp_test_recipient(value)


def test_recipient_refuses_incomplete_mailboxes() -> None:
    for value in (
        "localonly",  # no domain
        "@example.invalid",  # no local part
        "a@example..invalid",  # empty domain label
        "a@.invalid",  # empty first label
        "a b@example.invalid",  # bare space
        "a\tb@example.invalid",  # bare tab
    ):
        with pytest.raises(EmailAdminOperationError):
            validate_smtp_test_recipient(value)


def test_recipient_refuses_missing_and_blank() -> None:
    with pytest.raises(EmailAdminOperationError) as exc_none:
        validate_smtp_test_recipient(None)
    assert exc_none.value.code == "recipient_missing"
    with pytest.raises(EmailAdminOperationError) as exc_blank:
        validate_smtp_test_recipient("   ")
    assert exc_blank.value.code == "recipient_missing"


def test_recipient_refuses_raw_control_bytes_before_strip() -> None:
    for value in ("ops@example.invalid\r", "ops@ex\nample.invalid", "a\x00b@example.invalid"):
        with pytest.raises(EmailAdminOperationError):
            validate_smtp_test_recipient(value)


def test_recipient_refuses_oversized_and_secret_shapes() -> None:
    oversized = "a" * (SMTP_TEST_RECIPIENT_MAX_CHARS - 14) + "@example.invalid"
    assert len(oversized) > SMTP_TEST_RECIPIENT_MAX_CHARS
    with pytest.raises(EmailAdminOperationError):
        validate_smtp_test_recipient(oversized)
    with pytest.raises(EmailAdminOperationError) as exc:
        validate_smtp_test_recipient("sk-slaif-abcdef@example.invalid")
    assert exc.value.code == "recipient_withheld"


# ---------------------------------------------------------------------------
# Subject / body: raw control refusals BEFORE strip/default, byte bounds
# ---------------------------------------------------------------------------


def test_subject_defaults_and_bounds() -> None:
    assert validate_smtp_test_subject(None) == SMTP_TEST_DEFAULT_SUBJECT
    assert validate_smtp_test_subject("   ") == SMTP_TEST_DEFAULT_SUBJECT
    assert validate_smtp_test_subject("Ops note") == "Ops note"
    # 255 UTF-8 bytes ok; 256 refused.
    ok = "s" * SMTP_TEST_SUBJECT_MAX_BYTES
    assert validate_smtp_test_subject(ok) == ok
    with pytest.raises(EmailAdminOperationError):
        validate_smtp_test_subject("s" * (SMTP_TEST_SUBJECT_MAX_BYTES + 1))
    # Multibyte: 127 "é" = 254 bytes ok; 128 = 256 refused.
    assert validate_smtp_test_subject("é" * 127) == "é" * 127
    with pytest.raises(EmailAdminOperationError):
        validate_smtp_test_subject("é" * 128)


def test_subject_refuses_cr_lf_nul_before_default() -> None:
    # A CRLF-only subject is refused, never silently replaced by the
    # safe default (raw check BEFORE strip/default).
    with pytest.raises(EmailAdminOperationError):
        validate_smtp_test_subject("\r\n")
    with pytest.raises(EmailAdminOperationError):
        validate_smtp_test_subject("ok\r")
    with pytest.raises(EmailAdminOperationError):
        validate_smtp_test_subject("nul\x00subject")


def test_body_defaults_and_bounds() -> None:
    assert validate_smtp_test_body(None) == SMTP_TEST_DEFAULT_BODY
    assert validate_smtp_test_body("  ") == SMTP_TEST_DEFAULT_BODY
    ok = "b" * 4096
    assert validate_smtp_test_body(ok) == ok
    with pytest.raises(EmailAdminOperationError):
        validate_smtp_test_body("b" * 4097)
    # Multibyte boundary: 1365 "é" = 2730 bytes ok; 2048 "é" = 4096
    # bytes ok; 2049 = 4098 refused.
    assert validate_smtp_test_body("é" * 2048) == "é" * 2048
    with pytest.raises(EmailAdminOperationError):
        validate_smtp_test_body("é" * 2049)
    # CR/LF are legal inside the plain-text body (line breaks allowed).
    assert validate_smtp_test_body("line one\r\nline two") == "line one\r\nline two"


def test_body_refuses_nul_before_default() -> None:
    # A NUL-only body is refused, never replaced by the default.
    with pytest.raises(EmailAdminOperationError):
        validate_smtp_test_body("\x00")
    with pytest.raises(EmailAdminOperationError):
        validate_smtp_test_body("body\x00text")


# ---------------------------------------------------------------------------
# prepare_smtp_test_facts + signed review intent (JSON-escape budget)
# ---------------------------------------------------------------------------


def _facts(recipient: str | None, subject: str | None, body: str | None, nonce: str = "ab" * 16) -> SmtpTestFacts:
    return prepare_smtp_test_facts(
        recipient=recipient,
        subject=subject,
        body=body,
        nonce=nonce,
    )


def test_prepare_facts_rejects_bad_nonce_and_applies_defaults() -> None:
    with pytest.raises(EmailAdminOperationError) as exc:
        _facts("ops@example.invalid", None, None, nonce="not-a-nonce")
    assert exc.value.code == "nonce_invalid"
    facts = _facts("ops@example.invalid", None, None)
    assert facts.subject == SMTP_TEST_DEFAULT_SUBJECT
    assert facts.body == SMTP_TEST_DEFAULT_BODY


def _admin_pair() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4()


def test_review_token_roundtrips_valid_4096_multiline_escaped_body() -> None:
    # The ROOT size repro: 4096 UTF-8 bytes of "x\\n" is a VALID body,
    # and its JSON-escaped canonical form (6274 bytes) must fit the
    # escape-budgeted envelope - build -> verify exact round-trip.
    uid, sid = _admin_pair()
    body = "x\n" * 2048
    assert len(body.encode("utf-8")) == 4096
    facts = _facts("ops@example.invalid", None, body)
    token = build_smtp_test_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=uid,
        admin_session_id=sid,
        review_document=facts.as_review_document(),
    )
    doc = verify_smtp_test_review_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=uid,
        admin_session_id=sid,
    )
    assert doc == {
        "recipient": "ops@example.invalid",
        "subject": SMTP_TEST_DEFAULT_SUBJECT,
        "body": body,
        "nonce": "ab" * 16,
    }


def test_review_token_worst_case_control_body_roundtrip() -> None:
    # Every BMP code point escapes to 6 bytes in the canonical
    # serializer: the envelope budget must still hold for the worst
    # legal body.
    uid, sid = _admin_pair()
    body = "\x07" * 4096
    facts = _facts("ops@example.invalid", None, body)
    token = build_smtp_test_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=uid,
        admin_session_id=sid,
        review_document=facts.as_review_document(),
    )
    doc = verify_smtp_test_review_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=uid,
        admin_session_id=sid,
    )
    assert doc["body"] == body


def test_review_token_worst_case_astral_unicode_roundtrip() -> None:
    # Astral-plane code points escape to a 12-byte SURROGATE PAIR (not
    # 6): the recipient is char-bounded, so its per-code-point worst
    # case is 12 bytes.  This pure accepted-facts repro - 173-char
    # emoji-labeled recipient + U+0001 x255 subject + U+0001 x4096 body
    # (canonical JSON 28121 bytes) - must round-trip EXACTLY under the
    # derived envelope, without narrowing any valid field.
    emoji = "\U0001F600" * 40
    recipient = "x@" + (emoji + ".") * 3 + emoji + ".invalid"
    assert len(recipient) == 173
    assert len(recipient) <= 254
    subject = "\u0001" * 255
    body = "\u0001" * 4096
    assert len(subject.encode("utf-8")) == 255
    assert len(body.encode("utf-8")) == 4096
    uid, sid = _admin_pair()
    facts = _facts(recipient, subject, body)
    token = build_smtp_test_review_token(
        admin_session_secret="s" * 40,
        admin_user_id=uid,
        admin_session_id=sid,
        review_document=facts.as_review_document(),
    )
    doc = verify_smtp_test_review_token(
        admin_session_secret="s" * 40,
        token=token,
        admin_user_id=uid,
        admin_session_id=sid,
    )
    assert doc["recipient"] == recipient
    assert doc["subject"] == subject
    assert doc["body"] == body


def test_review_token_refuses_overbound_field() -> None:
    # Existing overbound refusal: the field law still refuses before
    # any signing work (no trimming, no loosening).
    uid, sid = _admin_pair()
    doc = {
        "recipient": "ops@example.invalid",
        "subject": "s" * (SMTP_TEST_SUBJECT_MAX_BYTES + 1),
        "body": "b",
        "nonce": "cd" * 16,
    }
    with pytest.raises(AdminReviewIntentError):
        build_smtp_test_review_token(
            admin_session_secret="s" * 40,
            admin_user_id=uid,
            admin_session_id=sid,
            review_document=doc,
        )


def test_review_token_tamper_actor_session_purpose_expired() -> None:
    uid, sid = _admin_pair()
    facts = _facts("ops@example.invalid", None, None)
    secret = "s" * 40
    token = build_smtp_test_review_token(
        admin_session_secret=secret,
        admin_user_id=uid,
        admin_session_id=sid,
        review_document=facts.as_review_document(),
        ttl_seconds=60,
    )
    # Tampered payload -> invalid (digest mismatch).
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    with pytest.raises(AdminReviewIntentError):
        verify_smtp_test_review_token(
            admin_session_secret=secret, token=tampered, admin_user_id=uid, admin_session_id=sid
        )
    # Wrong actor / session -> not authentic.
    for bad_uid, bad_sid in ((uuid.uuid4(), sid), (uid, uuid.uuid4())):
        with pytest.raises(AdminReviewIntentError):
            verify_smtp_test_review_token(
                admin_session_secret=secret,
                token=token,
                admin_user_id=bad_uid,
                admin_session_id=bad_sid,
            )
    # A different-purpose token (clone-style outer envelope is refused
    # by purpose/actor checks); expired token -> expired.
    expired = build_smtp_test_review_token(
        admin_session_secret=secret,
        admin_user_id=uid,
        admin_session_id=sid,
        review_document=facts.as_review_document(),
        ttl_seconds=-1,
    )
    with pytest.raises(AdminReviewIntentError) as exc:
        verify_smtp_test_review_token(
            admin_session_secret=secret,
            token=expired,
            admin_user_id=uid,
            admin_session_id=sid,
        )
    assert "expired" in exc.value.message


# ---------------------------------------------------------------------------
# One-use claim + budget at the repository seam (fakes)
# ---------------------------------------------------------------------------


class _FakeClaimAuditRepo:
    def __init__(self, *, existing: Any = None, attempts: int = 0) -> None:
        self.existing = existing
        self.attempts = attempts
        self.claims: list[dict[str, Any]] = []
        self.fail: Exception | None = None

    async def get_smtp_test_claim(self, *, admin_user_id, intent_nonce):
        return self.existing

    async def count_recent_smtp_test_attempts(self, *, admin_user_id, since):
        return self.attempts

    async def add_audit_log(self, **kwargs: Any):
        if self.fail is not None:
            raise self.fail
        self.claims.append(kwargs)


class _FakeLockRepo:
    def __init__(self, actor: Any = object()) -> None:
        self.actor = actor

    async def get_admin_user_for_update(self, admin_user_id):
        return self.actor


class _FakeCommitSession:
    def __init__(self) -> None:
        self.committed = False
        self.added: list[Any] = []

    async def commit(self) -> None:
        self.committed = True

    async def flush(self) -> None:
        return None

    def add(self, row: Any) -> None:
        self.added.append(row)


@pytest.mark.asyncio
async def test_claim_records_bound_identity_and_commits() -> None:
    repo = _FakeClaimAuditRepo()
    session = _FakeCommitSession()
    nonce = "0123456789abcdef0123456789abcdef"
    actor = uuid.uuid4()
    await claim_smtp_test_attempt(
        session=session,
        admin_users_repository=_FakeLockRepo(),
        audit_repository=repo,
        actor_admin_id=actor,
        intent_nonce=nonce,
        ip_address="127.0.0.1",
        user_agent="unit-agent",
        request_id="req-215",
    )
    assert session.committed is True
    claim = repo.claims[0]
    assert claim["action"] == "email_smtp_test_claimed"
    assert claim["entity_type"] == "email_smtp_test"
    # The nonce itself never reaches metadata: the durable identity is
    # the bound entity_id column (UUID(hex=nonce)).
    assert claim["entity_id"] == uuid.UUID(hex=nonce)
    assert claim["admin_user_id"] == actor
    assert claim["new_values"] == {"result": "claimed"}
    assert "intent_nonce" not in claim["new_values"]


@pytest.mark.asyncio
async def test_claim_refuses_duplicate_and_budget() -> None:
    actor = uuid.uuid4()
    nonce = "11" * 16
    dup = _FakeClaimAuditRepo(existing=object())
    with pytest.raises(SmtpTestIntentAlreadyClaimedError):
        await claim_smtp_test_attempt(
            session=_FakeCommitSession(),
            admin_users_repository=_FakeLockRepo(),
            audit_repository=dup,
            actor_admin_id=actor,
            intent_nonce=nonce,
        )
    over = _FakeClaimAuditRepo(attempts=SMTP_TEST_BUDGET_ATTEMPTS)
    with pytest.raises(SmtpTestBudgetExceededError):
        await claim_smtp_test_attempt(
            session=_FakeCommitSession(),
            admin_users_repository=_FakeLockRepo(),
            audit_repository=over,
            actor_admin_id=actor,
            intent_nonce="22" * 16,
        )
    missing_actor = _FakeClaimAuditRepo()
    with pytest.raises(SmtpTestIntentAlreadyClaimedError):
        await claim_smtp_test_attempt(
            session=_FakeCommitSession(),
            admin_users_repository=_FakeLockRepo(actor=None),
            audit_repository=missing_actor,
            actor_admin_id=actor,
            intent_nonce="33" * 16,
        )


@pytest.mark.asyncio
async def test_result_records_same_bound_identity() -> None:
    repo = _FakeClaimAuditRepo()
    nonce = "abcd" * 8
    await record_smtp_test_result(
        session=_FakeCommitSession(),
        audit_repository=repo,
        actor_admin_id=uuid.uuid4(),
        intent_nonce=nonce,
        outcome=SmtpTestOutcome(result="accepted"),
        user_agent="unit-agent",
    )
    row = repo.claims[0]
    assert row["action"] == "email_smtp_test_resulted"
    assert row["entity_type"] == "email_smtp_test"
    assert row["entity_id"] == uuid.UUID(hex=nonce)
    assert row["new_values"] == {"result": "accepted"}


# ---------------------------------------------------------------------------
# Shared enqueue-request intent audit (fake repository)
# ---------------------------------------------------------------------------


class _FakeEnqueueAuditRepo:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def add_audit_log(self, **kwargs: Any):
        self.rows.append(kwargs)


@pytest.mark.asyncio
async def test_enqueue_request_audit_binds_safe_identity_and_commits() -> None:
    # The shared seam uses the REAL AuditRepository on the (fake)
    # session, so this also proves the row survives the global
    # metadata sanitizer untouched.
    session = _FakeCommitSession()
    secret_id, delivery_id, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await record_enqueue_request_audit(
        session=session,
        one_time_secret_id=secret_id,
        email_delivery_id=delivery_id,
        actor_admin_id=actor,
        reason="operator retry",
        retry_failed=True,
    )
    assert session.committed is True
    assert len(session.added) == 1
    row = session.added[0]
    assert row.action == "email_key_enqueue_requested"
    assert row.entity_type == "email_delivery"
    assert row.entity_id == delivery_id
    assert row.admin_user_id == actor
    assert row.note == "operator retry"
    # The secret is referenced under the SAFE field name only (the
    # global sanitizer drops one_time_secret_id from metadata).
    assert row.new_values["one_time_reference_id"] == str(secret_id)
    assert row.new_values["email_delivery_id"] == str(delivery_id)
    assert row.new_values["actor_admin_id"] == str(actor)
    assert row.new_values["intent"] == "enqueue_requested"
    assert row.new_values["retry_failed"] is True
    assert "one_time_secret_id" not in row.new_values


# ---------------------------------------------------------------------------
# Finite SMTP outcome mapping (fake EmailService; cause hierarchy)
# ---------------------------------------------------------------------------


class _FakeEmailService:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    async def send_email(self, *, to: str, subject: str, text_body: str, html_body: str | None = None):
        self.calls.append({"to": to, "subject": subject, "text_body": text_body})
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _smtp_send_error(cause: BaseException | None) -> SmtpSendError:
    """Wrap a cause exactly as the real primitive does (raise ... from)."""
    err = SmtpSendError("wrapped")
    err.__cause__ = cause
    return err


def _settings_for_smtp(smtp_timeout: float | None = None) -> Settings:
    values: dict[str, Any] = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://user:secret@localhost:5432/test_db",
        "ADMIN_SESSION_SECRET": "s" * 40,
        "ENABLE_EMAIL_DELIVERY": True,
        "SMTP_HOST": "localhost",
        "SMTP_FROM": "noreply@example.org",
    }
    if smtp_timeout is not None:
        values["SMTP_TIMEOUT_SECONDS"] = smtp_timeout
    return Settings(**values)


@pytest.mark.asyncio
async def test_smtp_outcome_accepted_and_canonical_recipient() -> None:
    svc = _FakeEmailService(object())
    outcome = await run_smtp_test_with_deadline(
        settings=_settings_for_smtp(),
        email_service=svc,  # type: ignore[arg-type]
        recipient="ops@example.invalid",
        subject="s",
        body="b",
    )
    assert outcome.result == "accepted"
    # The canonical validated recipient is EXACTLY what is sent.
    assert svc.calls[0]["to"] == "ops@example.invalid"


@pytest.mark.asyncio
async def test_smtp_outcome_disabled_and_config_are_unavailable() -> None:
    for exc in (EmailDeliveryDisabledError("off"), SmtpConfigurationError("no host")):
        outcome = await run_smtp_test_with_deadline(
            settings=_settings_for_smtp(),
            email_service=_FakeEmailService(exc),  # type: ignore[arg-type]
            recipient="ops@example.invalid",
            subject="s",
            body="b",
        )
        assert outcome.result == "unavailable"


@pytest.mark.asyncio
async def test_smtp_outcome_timeout_is_unconfirmed() -> None:
    async def hang(**_kwargs: Any) -> None:
        await __import__("asyncio").sleep(3600)

    class _HangService:
        async def send_email(self, **kwargs: Any) -> None:
            await hang(**kwargs)

    outcome = await run_smtp_test_with_deadline(
        settings=Settings(
            APP_ENV="test",
            DATABASE_URL="postgresql+asyncpg://user:secret@localhost:5432/test_db",
            ADMIN_SESSION_SECRET="s" * 40,
            ENABLE_EMAIL_DELIVERY=True,
            SMTP_HOST="localhost",
            SMTP_FROM="noreply@example.org",
            SMTP_TIMEOUT_SECONDS=0.05,
        ),
        email_service=_HangService(),  # type: ignore[arg-type]
        recipient="ops@example.invalid",
        subject="s",
        body="b",
    )
    assert outcome.result == "unconfirmed"


@pytest.mark.asyncio
async def test_smtp_outcome_explicit_refusals_are_failed() -> None:
    # Connect-timeout IS an explicit connect-family refusal (no
    # connection was made), as are helo/auth/MAIL-FROM/RCPT-TO/data
    # refusals with a definite server response.
    for cause in (
        smtp_errors.SMTPConnectError(b"421 no"),
        smtp_errors.SMTPConnectTimeoutError("timeout"),
        smtp_errors.SMTPHeloError(500, b"no"),
        smtp_errors.SMTPAuthenticationError(535, b"no"),
        smtp_errors.SMTPSenderRefused(550, b"no", "from@example.invalid"),
        smtp_errors.SMTPRecipientRefused(550, b"no", "to@example.invalid"),
        smtp_errors.SMTPRecipientsRefused({"a@b.c": (550, b"no")}),
        smtp_errors.SMTPDataError(554, b"no"),
    ):
        outcome = await run_smtp_test_with_deadline(
            settings=_settings_for_smtp(),
            email_service=_FakeEmailService(_smtp_send_error(cause)),  # type: ignore[arg-type]
            recipient="ops@example.invalid",
            subject="s",
            body="b",
        )
        assert outcome.result == "failed", type(cause)


@pytest.mark.asyncio
async def test_smtp_outcome_stage_unknown_failures_are_unconfirmed() -> None:
    # Read-timeout/disconnect and any other wrapped fault do NOT
    # imply no SMTP acceptance.
    for cause in (
        smtp_errors.SMTPServerDisconnected("gone"),
        smtp_errors.SMTPResponseException(554, b"ambiguous"),
        OSError("network reset"),
        RuntimeError("unknown"),
        None,
    ):
        outcome = await run_smtp_test_with_deadline(
            settings=_settings_for_smtp(),
            email_service=_FakeEmailService(_smtp_send_error(cause)),  # type: ignore[arg-type]
            recipient="ops@example.invalid",
            subject="s",
            body="b",
        )
        assert outcome.result == "unconfirmed", repr(cause)


def test_smtp_outer_deadline_respects_shorter_configured_timeout() -> None:
    # 30s cap when the configured SMTP timeout is longer...
    assert smtp_test_outer_deadline(_settings_for_smtp(smtp_timeout=60)) == SMTP_TEST_OUTER_DEADLINE_SECONDS
    # ...and the configured bound when it is shorter.
    assert smtp_test_outer_deadline(_settings_for_smtp(smtp_timeout=5)) == 5.0


# ---------------------------------------------------------------------------
# ASGI canaries: valid auth/CSRF must reach the intended validators
# ---------------------------------------------------------------------------


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


def _asgi_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://user:secret@localhost:5432/test_db",
        "ADMIN_SESSION_SECRET": "s" * 40,
        "GATEWAY_KEY_PREFIX": "sk-slaif-",
        "GATEWAY_KEY_ACCEPTED_PREFIXES": "sk-slaif-",
        "ENABLE_EMAIL_DELIVERY": True,
        "SMTP_HOST": "localhost",
        "SMTP_FROM": "noreply@example.org",
        "CELERY_BROKER_URL": "redis://localhost:6379/15",
    }
    values.update(overrides)
    return Settings(**values)


def _asgi_app(settings: Settings | None = None) -> Any:
    app = create_app(settings or _asgi_settings())
    app.state.db_sessionmaker = _FakeSessionmaker()
    return app


def _admin_user() -> AdminUser:
    return AdminUser(
        id=uuid.uuid4(),
        email="admin@example.org",
        display_name="Admin User",
        password_hash="argon2-hash",
        role="admin",
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


def _login(monkeypatch: pytest.MonkeyPatch, client: TestClient, *, valid_csrf: str = "csrf-215") -> AdminUser:
    admin_user = _admin_user()
    admin_session = _admin_session(admin_user)

    async def validate_admin_session(self, **kwargs: Any) -> AdminSessionContext:
        return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)

    def verify_session_csrf_token(self, admin_session_row: Any, csrf_token: str) -> bool:
        return csrf_token == valid_csrf

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.validate_admin_session",
        validate_admin_session,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.verify_session_csrf_token",
        verify_session_csrf_token,
    )

    async def refresh_csrf_token(self, *, admin_session_id):
        return "page-csrf-215"

    monkeypatch.setattr(
        "slaif_gateway.services.admin_session_service.AdminSessionService.refresh_csrf_token",
        refresh_csrf_token,
    )
    client.cookies.set("slaif_admin_session", "session-plaintext")
    return admin_user


def _sendability(delivery_id: uuid.UUID, secret_id: uuid.UUID, *, status: str = "pending") -> KeyEmailDeliverySendability:
    return KeyEmailDeliverySendability(
        email_delivery_id=delivery_id,
        one_time_secret_id=secret_id,
        email_delivery_status=status,
        one_time_secret_status="present" if status in {"pending", "failed"} else status,
        can_send=status in {"pending", "failed"},
        blocking_reason=None if status in {"pending", "failed"} else "blocked",
    )


# ---- retry-failed ----------------------------------------------------------


def test_retry_failed_requires_confirmation_before_validation(monkeypatch) -> None:
    calls: list[str] = []

    async def sendability(self, email_delivery_id):
        calls.append("sendability")

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        sendability,
    )
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    delivery_id = uuid.uuid4()
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={"csrf_token": "csrf-215", "retry_mode": "send-now", "reason": "retry"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_retry_confirmation_required")
    assert calls == []


def test_retry_failed_valid_canary_reaches_send_with_actor_and_reason(monkeypatch) -> None:
    delivery_id, secret_id = uuid.uuid4(), uuid.uuid4()
    seen: dict[str, Any] = {}

    async def sendability(self, email_delivery_id):
        assert email_delivery_id == delivery_id
        return _sendability(delivery_id, secret_id, status="failed")

    async def send_pending_key_email(self, **kwargs: Any) -> PendingKeyEmailResult:
        seen.update(kwargs)
        return PendingKeyEmailResult(
            email_delivery_id=delivery_id,
            one_time_secret_id=secret_id,
            gateway_key_id=None,
            owner_id=None,
            recipient_email=None,
            status="sent",
        )

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        sendability,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.send_pending_key_email",
        send_pending_key_email,
    )
    client = TestClient(_asgi_app())
    admin_user = _login(monkeypatch, client)
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": "csrf-215",
            "retry_mode": "send-now",
            "reason": "operator retry 215",
            "confirm_retry": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_sent")
    assert seen == {
        "one_time_secret_id": secret_id,
        "email_delivery_id": delivery_id,
        "actor_admin_id": admin_user.id,
        "reason": "operator retry 215",
    }


def test_retry_failed_now_pending_row_refuses(monkeypatch) -> None:
    delivery_id, secret_id = uuid.uuid4(), uuid.uuid4()

    async def sendability(self, email_delivery_id):
        return _sendability(delivery_id, secret_id, status="pending")

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        sendability,
    )
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": "csrf-215",
            "retry_mode": "send-now",
            "reason": "retry",
            "confirm_retry": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    # Truthful not-failed copy: the row is pending, so the FAILED-only
    # retry-required message must not claim it is failed.
    assert response.headers["location"].endswith("message=email_delivery_retry_not_applicable")


def test_retry_failed_normal_send_on_now_failed_row_refuses(monkeypatch) -> None:
    # The ORDINARY send action on a now-failed row refuses (215-a).
    delivery_id, secret_id = uuid.uuid4(), uuid.uuid4()
    sent = False

    async def sendability(self, email_delivery_id):
        return _sendability(delivery_id, secret_id, status="failed")

    async def send_pending_key_email(self, **kwargs: Any) -> PendingKeyEmailResult:
        nonlocal sent
        sent = True

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        sendability,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.send_pending_key_email",
        send_pending_key_email,
    )
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/send-now",
        data={"csrf_token": "csrf-215", "confirm_send": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_retry_required")
    assert sent is False


def test_retry_failed_reason_negatives_are_fixed_safe(monkeypatch) -> None:
    delivery_id, secret_id = uuid.uuid4(), uuid.uuid4()

    async def sendability(self, email_delivery_id):
        return _sendability(delivery_id, secret_id, status="failed")

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        sendability,
    )
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    base = f"/admin/email-deliveries/{delivery_id}/retry-failed"
    data = {"csrf_token": "csrf-215", "retry_mode": "send-now", "confirm_retry": "true"}

    # blank
    response = client.post(base, data={**data, "reason": "  "}, follow_redirects=False)
    assert response.headers["location"].endswith("message=email_delivery_retry_reason_required")
    # 1025 ASCII bytes
    response = client.post(base, data={**data, "reason": "r" * 1025}, follow_redirects=False)
    assert response.headers["location"].endswith("message=email_delivery_retry_reason_too_long")
    # multibyte 513 "é" = 1026 bytes
    response = client.post(base, data={**data, "reason": "é" * 513}, follow_redirects=False)
    assert response.headers["location"].endswith("message=email_delivery_retry_reason_too_long")
    # known credential pattern
    response = client.post(base, data={**data, "reason": SECRET_SHAPED}, follow_redirects=False)
    assert response.headers["location"].endswith("message=email_delivery_retry_reason_withheld")
    # bad mode
    response = client.post(base, data={**data, "reason": "ok", "retry_mode": "bogus"}, follow_redirects=False)
    assert response.headers["location"].endswith("message=email_delivery_retry_mode_required")


def test_retry_failed_known_incoming_alias_reason_refused(monkeypatch) -> None:
    # The posted reason matching the request's OWN Authorization bearer
    # value is refused as a known incoming auth alias.
    delivery_id, secret_id = uuid.uuid4(), uuid.uuid4()

    async def sendability(self, email_delivery_id):
        return _sendability(delivery_id, secret_id, status="failed")

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        sendability,
    )
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": "csrf-215",
            "retry_mode": "send-now",
            "reason": "the token sk-slaif-abcdef0123456789abcdef0123456789abcdef01 was rotated",
            "confirm_retry": "true",
        },
        headers={"authorization": "Bearer sk-slaif-abcdef0123456789abcdef0123456789abcdef01"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_retry_reason_withheld")


class _FakeEnqueueBroker:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.fail: Exception | None = None

    def __call__(self, *, one_time_secret_id, email_delivery_id, actor_admin_id):
        if self.fail is not None:
            raise self.fail
        self.calls.append(
            (str(one_time_secret_id), str(email_delivery_id), str(actor_admin_id) if actor_admin_id else None)
        )
        return "fake-task-id"


def test_retry_failed_enqueue_commits_intent_before_broker(monkeypatch) -> None:
    delivery_id, secret_id = uuid.uuid4(), uuid.uuid4()
    order: list[str] = []
    broker = _FakeEnqueueBroker()

    async def sendability(self, email_delivery_id):
        return _sendability(delivery_id, secret_id, status="failed")

    async def audit(**kwargs: Any) -> None:
        order.append("audit")

    def enqueue(**kwargs: Any) -> str:
        order.append("broker")
        return broker(**kwargs)

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        sendability,
    )
    monkeypatch.setattr(admin_email_operations, "record_enqueue_request_audit", audit)
    monkeypatch.setattr(admin_email_operations, "_enqueue_admin_pending_key_email", enqueue)
    client = TestClient(_asgi_app())
    admin_user = _login(monkeypatch, client)
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": "csrf-215",
            "retry_mode": "enqueue",
            "reason": "operator enqueue retry",
            "confirm_retry": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_queued")
    # Intent committed BEFORE broker dispatch; payload EXACTLY the
    # existing three UUID string args (server actor, not posted).
    assert order == ["audit", "broker"]
    assert broker.calls == [(str(secret_id), str(delivery_id), str(admin_user.id))]


def test_retry_failed_enqueue_broker_failure_is_unconfirmed(monkeypatch) -> None:
    delivery_id, secret_id = uuid.uuid4(), uuid.uuid4()
    broker = _FakeEnqueueBroker()
    broker.fail = RuntimeError("broker down")

    async def sendability(self, email_delivery_id):
        return _sendability(delivery_id, secret_id, status="failed")

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        sendability,
    )
    monkeypatch.setattr(
        admin_email_operations, "record_enqueue_request_audit",
        lambda **kwargs: _never(**kwargs),
    )
    monkeypatch.setattr(admin_email_operations, "_enqueue_admin_pending_key_email", broker)
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": "csrf-215",
            "retry_mode": "enqueue",
            "reason": "operator enqueue retry",
            "confirm_retry": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_enqueue_unconfirmed")
    # No queued/sent success is fabricated; the message is fixed safe.
    assert "broker down" not in response.text


def test_retry_failed_enqueue_recording_failure_prevents_broker(monkeypatch) -> None:
    # A recording failure must prevent broker dispatch entirely and
    # return the safe recording-unconfirmed (never queued).
    delivery_id, secret_id = uuid.uuid4(), uuid.uuid4()
    broker = _FakeEnqueueBroker()

    async def sendability(self, email_delivery_id):
        return _sendability(delivery_id, secret_id, status="failed")

    async def audit_raises(**kwargs: Any) -> None:
        raise RuntimeError("db commit fault")

    monkeypatch.setattr(
        "slaif_gateway.services.email_delivery_service.EmailDeliveryService.get_key_email_delivery_sendability",
        sendability,
    )
    monkeypatch.setattr(admin_email_operations, "record_enqueue_request_audit", audit_raises)
    monkeypatch.setattr(admin_email_operations, "_enqueue_admin_pending_key_email", broker)
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    response = client.post(
        f"/admin/email-deliveries/{delivery_id}/retry-failed",
        data={
            "csrf_token": "csrf-215",
            "retry_mode": "enqueue",
            "reason": "operator enqueue retry",
            "confirm_retry": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("message=email_delivery_enqueue_recording_unconfirmed")
    assert broker.calls == []
    assert "db commit fault" not in response.text


async def _never(**kwargs: Any) -> None:
    return None


# ---- SMTP test: form / review / apply --------------------------------------


def test_smtp_test_form_renders_readiness_for_valid_admin(monkeypatch) -> None:
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    response = client.get("/admin/email-operations/smtp-test")
    assert response.status_code == 200
    assert "SMTP Test" in response.text
    assert "at most 3 test attempts per 60 seconds" in response.text
    assert SMTP_TEST_DEFAULT_SUBJECT in response.text


def test_smtp_test_form_shows_unavailable_when_disabled(monkeypatch) -> None:
    client = TestClient(_asgi_app(_asgi_settings(ENABLE_EMAIL_DELIVERY=False)))
    _login(monkeypatch, client)
    response = client.get("/admin/email-operations/smtp-test")
    assert response.status_code == 200
    assert "Email delivery is disabled" in response.text


def test_smtp_test_review_refuses_invalid_recipient_fixed_safe(monkeypatch) -> None:
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    # getaddresses would reinterpret this; the mailbox law refuses.
    response = client.post(
        "/admin/email-operations/smtp-test/review",
        data={"csrf_token": "csrf-215", "recipient": "first:second@example.invalid"},
    )
    assert response.status_code == 400
    assert "not a single email address" in response.text
    # No list-parser fallback and no echoed parse artifact.
    assert "second@example.invalid" not in response.text


def test_smtp_test_review_refuses_known_alias_before_render(monkeypatch) -> None:
    # A subject embedding the request's own (opaque) bearer value is
    # refused BEFORE signing/rendering and never echoed.  (The
    # sk-slaif- credential SHAPE is refused earlier by the field law;
    # this proves the separate known-incoming-auth alias boundary.)
    bearer = "opaque-secret-token-215abcdef0123456789abcdef01"
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    response = client.post(
        "/admin/email-operations/smtp-test/review",
        data={
            "csrf_token": "csrf-215",
            "recipient": "ops-215@example.invalid",
            "subject": f"token {bearer} here",
        },
        headers={"authorization": f"Bearer {bearer}"},
    )
    assert response.status_code == 400
    assert "known incoming authentication value" in response.text
    assert bearer not in response.text


def test_smtp_test_review_signs_and_returns_one_use_token(monkeypatch) -> None:
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    response = client.post(
        "/admin/email-operations/smtp-test/review",
        data={"csrf_token": "csrf-215", "recipient": "ops@example.invalid"},
    )
    assert response.status_code == 200
    assert 'name="review_token"' in response.text
    assert 'name="confirm_send_test"' in response.text
    assert "ops@example.invalid" in response.text


class _FakeClaim:
    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = fail

    async def __call__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.fail is not None:
            raise self.fail


class _FakeResult:
    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = fail

    async def __call__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.fail is not None:
            raise self.fail


class _FakeOutcomeRunner:
    def __init__(self, outcome: SmtpTestOutcome) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> SmtpTestOutcome:
        self.calls.append(kwargs)
        return self.outcome


def _signed_apply_data(monkeypatch: pytest.MonkeyPatch, client: TestClient, **overrides: Any) -> dict[str, str]:
    """Prepare a real signed review intent and return the apply form data."""
    response = client.post(
        "/admin/email-operations/smtp-test/review",
        data={"csrf_token": "csrf-215", "recipient": "ops@example.invalid", **{k: v for k, v in overrides.items() if k in ("subject", "body")}},
    )
    assert response.status_code == 200
    token = response.text.split('name="review_token" value="', 1)[1].split('"', 1)[0]
    return {"csrf_token": "csrf-215", "review_token": token, "confirm_send_test": "true"}


def test_smtp_test_apply_happy_path_one_message_and_recorded(monkeypatch) -> None:
    claim, result, runner = _FakeClaim(), _FakeResult(), _FakeOutcomeRunner(SmtpTestOutcome(result="accepted"))
    monkeypatch.setattr(admin_email_operations, "claim_smtp_test_attempt", claim)
    monkeypatch.setattr(admin_email_operations, "record_smtp_test_result", result)
    monkeypatch.setattr(admin_email_operations, "run_smtp_test_with_deadline", runner)
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    data = _signed_apply_data(monkeypatch, client)
    response = client.post("/admin/email-operations/smtp-test/apply", data=data)
    assert response.status_code == 200
    assert "accepted by the configured SMTP service" in response.text
    # One claimed, one attempted, one recorded; the one-use token is
    # consumed (no confirm form re-rendered).
    assert len(claim.calls) == 1
    assert len(runner.calls) == 1
    assert len(result.calls) == 1
    assert result.calls[0]["outcome"] == runner.outcome
    assert 'name="review_token"' not in response.text
    assert "Result recording UNCONFIRMED" not in response.text


def test_smtp_test_apply_claim_fault_dispatches_nothing(monkeypatch) -> None:
    # Pre-dispatch claim durability failure: fixed safe unconfirmed,
    # no SMTP call, no raw exception prose, no retry token.
    claim = _FakeClaim(fail=RuntimeError("commit fault"))
    result = _FakeResult()
    runner = _FakeOutcomeRunner(SmtpTestOutcome(result="accepted"))
    monkeypatch.setattr(admin_email_operations, "claim_smtp_test_attempt", claim)
    monkeypatch.setattr(admin_email_operations, "record_smtp_test_result", result)
    monkeypatch.setattr(admin_email_operations, "run_smtp_test_with_deadline", runner)
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    data = _signed_apply_data(monkeypatch, client)
    response = client.post("/admin/email-operations/smtp-test/apply", data=data)
    assert response.status_code == 200
    assert "recording could not be confirmed before sending" in response.text
    assert runner.calls == []  # NO SMTP call
    assert result.calls == []
    assert "commit fault" not in response.text
    assert 'name="review_token"' not in response.text


def test_smtp_test_apply_result_fault_keeps_truthful_outcome(monkeypatch) -> None:
    # Post-accept result recording failure: the claim/budget stay
    # consumed, the acceptance stays truthfully shown, and the page
    # says the RECORD is unconfirmed (never a rollback/no-message
    # promise).
    claim = _FakeClaim()
    result = _FakeResult(fail=RuntimeError("result commit fault"))
    runner = _FakeOutcomeRunner(SmtpTestOutcome(result="accepted"))
    monkeypatch.setattr(admin_email_operations, "claim_smtp_test_attempt", claim)
    monkeypatch.setattr(admin_email_operations, "record_smtp_test_result", result)
    monkeypatch.setattr(admin_email_operations, "run_smtp_test_with_deadline", runner)
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    data = _signed_apply_data(monkeypatch, client)
    response = client.post("/admin/email-operations/smtp-test/apply", data=data)
    assert response.status_code == 200
    assert "accepted by the configured SMTP service" in response.text
    assert "Result recording UNCONFIRMED" in response.text
    assert len(claim.calls) == 1
    assert len(runner.calls) == 1  # exactly one message attempted
    assert "result commit fault" not in response.text


def test_smtp_test_apply_duplicate_claim_and_budget_refusals(monkeypatch) -> None:
    runner = _FakeOutcomeRunner(SmtpTestOutcome(result="accepted"))
    for error, marker in (
        (SmtpTestIntentAlreadyClaimedError("already_claimed", "This reviewed test intent was already used. Submit a new test if another attempt is needed."), "already used"),
        (SmtpTestBudgetExceededError("cooldown", "Test email cooldown active."), "cooldown"),
    ):
        claim = _FakeClaim(fail=error)
        monkeypatch.setattr(admin_email_operations, "claim_smtp_test_attempt", claim)
        monkeypatch.setattr(admin_email_operations, "record_smtp_test_result", _FakeResult())
        monkeypatch.setattr(admin_email_operations, "run_smtp_test_with_deadline", runner)
        client = TestClient(_asgi_app())
        _login(monkeypatch, client)
        data = _signed_apply_data(monkeypatch, client)
        response = client.post("/admin/email-operations/smtp-test/apply", data=data)
        assert response.status_code == 200
        assert marker in response.text
    assert runner.calls == []  # refused before any SMTP call


def test_smtp_test_apply_alias_guard_fires_before_confirm_render(monkeypatch) -> None:
    # ROOT ordering: a known-alias signed fact is refused IMMEDIATELY
    # after verify/parse - even when confirm is missing - so no render
    # echoes the facts before the guard and no claim is attempted.
    bearer = "opaque-secret-token-215abcdef0123456789abcdef01"
    claim = _FakeClaim()
    monkeypatch.setattr(admin_email_operations, "claim_smtp_test_attempt", claim)
    monkeypatch.setattr(admin_email_operations, "record_smtp_test_result", _FakeResult())
    monkeypatch.setattr(admin_email_operations, "run_smtp_test_with_deadline", _FakeOutcomeRunner(SmtpTestOutcome(result="accepted")))
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    review = client.post(
        "/admin/email-operations/smtp-test/review",
        data={
            "csrf_token": "csrf-215",
            "recipient": "ops-215@example.invalid",
            "subject": f"token {bearer} here",
        },
    )
    assert review.status_code == 200  # no incoming auth header on THIS request: signed
    token = review.text.split('name="review_token" value="', 1)[1].split('"', 1)[0]
    response = client.post(
        "/admin/email-operations/smtp-test/apply",
        data={"csrf_token": "csrf-215", "review_token": token},  # confirm MISSING
        headers={"authorization": f"Bearer {bearer}"},  # bearer present on THIS request
    )
    assert response.status_code == 400
    assert "known incoming authentication value" in response.text
    assert "Confirm the reviewed SMTP test before sending." not in response.text
    assert bearer not in response.text
    assert claim.calls == []


def test_smtp_test_apply_refuses_tampered_and_unknown_tokens(monkeypatch) -> None:
    claim = _FakeClaim()
    monkeypatch.setattr(admin_email_operations, "claim_smtp_test_attempt", claim)
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    data = _signed_apply_data(monkeypatch, client)
    # Tampered token -> 400 fixed safe (digest mismatch).
    response = client.post(
        "/admin/email-operations/smtp-test/apply",
        data={**data, "review_token": data["review_token"][:-4] + "aaaa"},
    )
    assert response.status_code == 400
    # Unknown token -> 400 fixed safe.
    response3 = client.post(
        "/admin/email-operations/smtp-test/apply",
        data={**data, "review_token": "aaaa.bbbb"},
    )
    assert response3.status_code == 400
    assert claim.calls == []  # refused before any claim


def test_smtp_test_apply_masks_incoming_alias_from_persisted_ua(monkeypatch) -> None:
    # AuditRepository stores the top-level user_agent RAW; the new SMTP
    # audit context must mask known incoming auth aliases first.
    bearer = "sk-slaif-abcdef0123456789abcdef0123456789abcdef01"
    claim = _FakeClaim()
    result = _FakeResult()
    monkeypatch.setattr(admin_email_operations, "claim_smtp_test_attempt", claim)
    monkeypatch.setattr(admin_email_operations, "record_smtp_test_result", result)
    monkeypatch.setattr(admin_email_operations, "run_smtp_test_with_deadline", _FakeOutcomeRunner(SmtpTestOutcome(result="accepted")))
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    data = _signed_apply_data(monkeypatch, client)
    # Unicode prefix + embedded incoming alias: the mask must remove
    # the alias while PRESERVING the unaffected Unicode metadata.
    # Raw-bytes header: httpx refuses non-ASCII str headers, but HTTP
    # headers are latin-1-decoded server-side, so the app sees the
    # non-Latin1 metadata "ops-agent-Ã¼bung" (raw bytes C3 BC).  The
    # mask must preserve that metadata EXACTLY (same-input-encoding
    # round-trip) and substitute only the known alias.
    raw_ua = b"ops-agent-\xc3\xbcbung/" + bearer.encode("ascii")
    received_ua = raw_ua.decode("latin-1")
    expected_masked = received_ua[: len(received_ua) - len(bearer)] + "[REDACTED]"
    response = client.post(
        "/admin/email-operations/smtp-test/apply",
        data=data,
        headers={
            "user-agent": raw_ua,
            "authorization": f"Bearer {bearer}",
        },
    )
    assert response.status_code == 200
    assert len(claim.calls) == 1
    ua_claim = str(claim.calls[0].get("user_agent"))
    ua_result = str(result.calls[0].get("user_agent"))
    # The alias is masked before persistence in BOTH audit contexts...
    assert bearer not in ua_claim
    assert bearer not in ua_result
    assert "[REDACTED]" in ua_claim
    # ...and the clean (nonsecret) metadata is byte-identical to what
    # the server received, uncorrupted (no re-encoding drift).
    assert ua_claim == expected_masked
    assert ua_result == expected_masked


def test_smtp_test_apply_keeps_clean_ua(monkeypatch) -> None:
    claim = _FakeClaim()
    result = _FakeResult()
    monkeypatch.setattr(admin_email_operations, "claim_smtp_test_attempt", claim)
    monkeypatch.setattr(admin_email_operations, "record_smtp_test_result", result)
    monkeypatch.setattr(admin_email_operations, "run_smtp_test_with_deadline", _FakeOutcomeRunner(SmtpTestOutcome(result="accepted")))
    client = TestClient(_asgi_app())
    _login(monkeypatch, client)
    data = _signed_apply_data(monkeypatch, client)
    response = client.post(
        "/admin/email-operations/smtp-test/apply",
        data=data,
        headers={"user-agent": "clean-agent/1.0"},
    )
    assert response.status_code == 200
    assert claim.calls[0].get("user_agent") == "clean-agent/1.0"
    assert result.calls[0].get("user_agent") == "clean-agent/1.0"

"""Purpose-bound admin review-intent state for the key-clone workflow (208-a).

The clone review binds the COMPLETE strict clone-plan document (including
its stable operation UUID), the reviewed delivery selection, the current
admin user and session, and a bounded expiry under an HMAC-SHA256 keyed with
the existing administrator session secret (``ADMIN_SESSION_SECRET``). The
token is reviewed data, not authority:

- it is never stored server-side and never persisted;
- apply verifies the digest in constant time, rebinds the signed-in actor
  and session, checks the bounded expiry, and re-parses the embedded plan
  through the strict version-1 clone schema BEFORE any mutation;
- tampering, wrong actor/session, expiry, and malformed input all fail with
  fixed safe messages that never echo the token.

No new persistence, secret deployment setting, workflow platform, or crypto
design is introduced: the existing administrator session secret is the only
key material, and standard :mod:`hmac`/HMAC-SHA256 is the only primitive.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from slaif_gateway.schemas.key_clone import (
    MAX_CLONE_PLAN_FILE_BYTES,
    parse_clone_plan_document,
)
from slaif_gateway.schemas.key_batch import (
    KEY_BATCH_PLAN_MAX_BYTES,
    parse_key_batch_plan,
    )
from slaif_gateway.schemas.provider_route_configuration import (
    ROUTE_PLAN_FILE_MAX_BYTES,
    parse_route_update_plan_document,
    )
from slaif_gateway.schemas.key_configuration import (
    MAX_KEY_CONFIGURATION_REASON_LENGTH,
)
from slaif_gateway.schemas.codex_replay_maintenance import (
    REPLAY_PLAN_MAX_BYTES,
    parse_replay_extend_plan_document,
    )
from slaif_gateway.services.pricing_rule_service import (
    PRICING_DISABLE_PLAN_MAX_BYTES,
    parse_pricing_disable_plan_document,
)
from slaif_gateway.services.email_admin_operations import (
    SMTP_TEST_BODY_MAX_BYTES,
    SMTP_TEST_RECIPIENT_MAX_CHARS,
    SMTP_TEST_SUBJECT_MAX_BYTES,
    validate_smtp_test_body,
    validate_smtp_test_recipient,
    validate_smtp_test_subject,
)
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE_ID,
)
from slaif_gateway.services.external_tool_policy_contract import (
    ExternalToolOperatorCeilings,
)

REVIEW_INTENT_PURPOSE = "admin.key-clone.review.v1"
# 209-a: separate batch purpose (a clone token is never valid for a batch
# apply and vice versa); same HMAC pattern, same 15-minute bound.
REVIEW_INTENT_BATCH_PURPOSE = "admin.key-batch.review.v1"
# 210-a: separate reviewed route-configuration purpose (a route token is
# never valid for a clone or batch apply and vice versa); same HMAC
# pattern, same 15-minute bound.
REVIEW_INTENT_ROUTE_PURPOSE = "admin.route-configuration.review.v1"
# 212-a: separate reviewed Codex-compatibility migration purpose (a
# compatibility token is never valid for a clone/batch/route apply and
# vice versa); same HMAC pattern, same 15-minute bound.
REVIEW_INTENT_COMPATIBILITY_PURPOSE = "admin.codex-compatibility.review.v1"
# 213-a: separate reviewed replay-maintenance purpose (a replay token is
# never valid for a clone/batch/route/compatibility apply and vice
# versa); same HMAC pattern, same 15-minute bound.
REVIEW_INTENT_REPLAY_PURPOSE = "admin.replay-maintenance.review.v1"
REVIEW_INTENT_TTL_SECONDS = 15 * 60

# Bounded wrapper for the 128 KiB core plan: base64url expansion (4/3) of
# the canonical payload (plan document + identity + expiry) plus the digest
# and separator. This is documented encoding overhead, not a second policy
# cap; the decoded plan itself is bounded by the core schema on re-parse.
MAX_REVIEW_INTENT_TOKEN_CHARS = (MAX_CLONE_PLAN_FILE_BYTES * 4) // 3 + 4096

# Bounded wrapper for the 8 MiB core batch plan: base64url expansion (4/3)
# of the canonical payload plus the digest and separator (documented
# encoding overhead, not a second policy cap). The decoded plan is bounded
# by the core schema on re-parse; the shipped Nginx templates carry a
# 16m allowance for the batch locations (largest envelope
# 11,184,812 base64url chars = 10.67 MiB + the other small form fields).
MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS = (KEY_BATCH_PLAN_MAX_BYTES * 4) // 3 + 4096

# Bounded wrapper for the 128 KiB core route plan: base64url expansion
# (4/3) plus digest and separator (documented encoding overhead, not a
# second policy cap). The decoded plan is bounded by the core schema on
# re-parse; the largest envelope stays far below the default admin
# per-field transport bound, so no proxy allowance is needed.
MAX_REVIEW_INTENT_ROUTE_TOKEN_CHARS = (ROUTE_PLAN_FILE_MAX_BYTES * 4) // 3 + 4096

# 212-a: the reviewed compatibility migration document is ONE finite
# migration (operation, key UUID, exact source, selector, resolved target
# tuple, bounded reason) - 8 KiB of canonical payload is ample, and the
# bounded wrapper is the documented 4/3 base64url expansion plus the
# digest and separator (encoding overhead, not a second policy cap).
COMPATIBILITY_REVIEW_PLAN_MAX_BYTES = 8 * 1024
MAX_REVIEW_INTENT_COMPATIBILITY_TOKEN_CHARS = (
    COMPATIBILITY_REVIEW_PLAN_MAX_BYTES * 4
) // 3 + 4096

# 213-a: the strict replay extend plan is bounded by REPLAY_PLAN_MAX_BYTES
# (32 KiB) in its rendered form, whose canonical JSON is never larger; the
# review wrapper adds ONE bounded nonblank Unicode reason plus the
# identity/expiry envelope.  The canonical serializer uses ensure_ascii,
# so a 512-character astral-Unicode reason can consume 6,144 escaped
# bytes; the fixed +8192 wrapper allowance budgets that maximum plus the
# identity/expiry keys before any signing/base64 work.  The token cap is
# the derived 4/3 base64url expansion plus the digest and separator
# (documented encoding overhead, not a second policy cap).
REPLAY_REVIEW_PLAN_MAX_BYTES = REPLAY_PLAN_MAX_BYTES + 8192
MAX_REVIEW_INTENT_REPLAY_TOKEN_CHARS = (
    REPLAY_REVIEW_PLAN_MAX_BYTES * 4
) // 3 + 4096

_CLONE_DELIVERY_MODES = frozenset({"none", "pending", "send-now", "enqueue"})

_INVALID_MESSAGE = "The clone review state is missing or invalid."
_NOT_AUTHENTIC_MESSAGE = "The clone review state is not valid for this signed-in admin."
_EXPIRED_MESSAGE = "The clone review has expired. Review the clone plan again."
_TOO_LARGE_MESSAGE = "The clone plan exceeds the bounded review size."
_BATCH_INVALID_MESSAGE = "The key batch review state is missing or invalid."
_BATCH_NOT_AUTHENTIC_MESSAGE = (
    "The key batch review state is not valid for this signed-in admin."
)
_BATCH_EXPIRED_MESSAGE = (
    "The key batch review has expired. Review the batch plan again."
)
_BATCH_TOO_LARGE_MESSAGE = "The key batch plan exceeds the bounded review size."
_ROUTE_INVALID_MESSAGE = "The route configuration review state is missing or invalid."
_ROUTE_NOT_AUTHENTIC_MESSAGE = (
    "The route configuration review state is not valid for this signed-in admin."
)
_ROUTE_EXPIRED_MESSAGE = (
    "The route configuration review has expired. Review the route plan again."
)
_ROUTE_TOO_LARGE_MESSAGE = (
    "The route configuration plan exceeds the bounded review size."
)
_COMPAT_INVALID_MESSAGE = (
    "The compatibility review state is missing or invalid."
)
_COMPAT_NOT_AUTHENTIC_MESSAGE = (
    "The compatibility review state is not valid for this signed-in admin."
)
_COMPAT_EXPIRED_MESSAGE = (
    "The compatibility review has expired. Review the migration again."
)
_COMPAT_TOO_LARGE_MESSAGE = (
    "The compatibility migration exceeds the bounded review size."
)
_REPLAY_INVALID_MESSAGE = (
    "The replay maintenance review state is missing or invalid."
)
_REPLAY_NOT_AUTHENTIC_MESSAGE = (
    "The replay maintenance review state is not valid for this signed-in admin."
)
_REPLAY_EXPIRED_MESSAGE = (
    "The replay maintenance review has expired. Preview the scope again."
)
_REPLAY_TOO_LARGE_MESSAGE = (
    "The replay maintenance review plan exceeds the bounded review size."
)

# The digest half is exactly 64 lowercase hex characters; anything else is a
# malformed format and is refused BEFORE digest comparison (compare_digest
# raises on non-ASCII strings, so format must be proven first).
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class AdminReviewIntentError(ValueError):
    """Safe fixed-message review-intent failure (never echoes the token)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _strict_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _value in pairs:
        if not isinstance(key, str) or key in seen:
            raise ValueError("duplicate or non-string JSON key")
        seen.add(key)
    return dict(pairs)


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(admin_session_secret: str, payload: bytes) -> str:
    return hmac.new(
        admin_session_secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()


def build_review_intent_token(
    *,
    admin_session_secret: str,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    plan_document: dict[str, Any],
    delivery_mode: str,
    ttl_seconds: int = REVIEW_INTENT_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Bind one reviewed clone plan + delivery choice to actor/session/expiry.

    ``plan_document`` is the exact strict version-1 document produced by
    ``KeyCloneService.build_plan`` (re-parsed here so a caller can never bind
    a non-conformant plan); the returned token is bounded by
    :data:`MAX_REVIEW_INTENT_TOKEN_CHARS`.
    """
    if delivery_mode not in _CLONE_DELIVERY_MODES:
        raise AdminReviewIntentError(_INVALID_MESSAGE)
    parse_clone_plan_document(plan_document)
    # Builder-side decoded-plan bound: the embedded plan must fit the core
    # 128 KiB plan-file budget in canonical bytes (the strict document
    # parser alone does not enforce a byte limit). The documented base64url
    # expansion (4/3) plus wrapper overhead keeps every core-supported plan
    # inside :data:`MAX_REVIEW_INTENT_TOKEN_CHARS`.
    if len(_canonical_json(plan_document)) > MAX_CLONE_PLAN_FILE_BYTES:
        raise AdminReviewIntentError(_TOO_LARGE_MESSAGE)
    issued = now or datetime.now(UTC)
    payload = {
        "purpose": REVIEW_INTENT_PURPOSE,
        "admin_user_id": str(admin_user_id),
        "admin_session_id": str(admin_session_id),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
        "delivery_mode": delivery_mode,
        "plan": plan_document,
    }
    encoded = _canonical_json(payload)
    token = (
        base64.urlsafe_b64encode(encoded).decode("ascii")
        + "."
        + _digest(admin_session_secret, encoded)
    )
    if len(token) > MAX_REVIEW_INTENT_TOKEN_CHARS:
        raise AdminReviewIntentError(_TOO_LARGE_MESSAGE)
    return token


def verify_review_intent_token(
    *,
    admin_session_secret: str,
    token: str | None,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    now: datetime | None = None,
) -> tuple[dict[str, Any], str]:
    """Verify, rebind, and strict-reparse one review-intent token.

    Returns ``(plan_document, delivery_mode)``. Every failure path raises
    :class:`AdminReviewIntentError` with a fixed safe message; the token
    bytes never appear in an exception, log, or rendered error.
    """
    if (
        not isinstance(token, str)
        or not token
        or len(token) > MAX_REVIEW_INTENT_TOKEN_CHARS
    ):
        raise AdminReviewIntentError(_INVALID_MESSAGE)
    body, separator, digest = token.rpartition(".")
    if (
        not separator
        or not body
        or not digest
        or not _DIGEST_RE.match(digest)
    ):
        raise AdminReviewIntentError(_INVALID_MESSAGE)
    try:
        encoded = base64.urlsafe_b64decode(body.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        raise AdminReviewIntentError(_INVALID_MESSAGE) from None
    if not hmac.compare_digest(_digest(admin_session_secret, encoded), digest):
        raise AdminReviewIntentError(_NOT_AUTHENTIC_MESSAGE)
    try:
        payload = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_strict_pairs_hook
        )
    except (UnicodeDecodeError, ValueError):
        raise AdminReviewIntentError(_INVALID_MESSAGE) from None
    if not isinstance(payload, dict):
        raise AdminReviewIntentError(_INVALID_MESSAGE)
    if payload.get("purpose") != REVIEW_INTENT_PURPOSE:
        raise AdminReviewIntentError(_NOT_AUTHENTIC_MESSAGE)
    if (
        payload.get("admin_user_id") != str(admin_user_id)
        or payload.get("admin_session_id") != str(admin_session_id)
    ):
        raise AdminReviewIntentError(_NOT_AUTHENTIC_MESSAGE)
    expires_raw = payload.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except (TypeError, ValueError):
        raise AdminReviewIntentError(_INVALID_MESSAGE) from None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (now or datetime.now(UTC)) >= expires_at:
        raise AdminReviewIntentError(_EXPIRED_MESSAGE)
    plan_document = payload.get("plan")
    if not isinstance(plan_document, dict):
        raise AdminReviewIntentError(_INVALID_MESSAGE)
    try:
        parse_clone_plan_document(plan_document)
    except Exception:
        raise AdminReviewIntentError(_INVALID_MESSAGE) from None
    delivery_mode = payload.get("delivery_mode")
    if delivery_mode not in _CLONE_DELIVERY_MODES:
        raise AdminReviewIntentError(_INVALID_MESSAGE)
    return plan_document, delivery_mode


def build_batch_review_token(
    *,
    admin_session_secret: str,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    plan_document: dict[str, Any],
    ttl_seconds: int = REVIEW_INTENT_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Bind one reviewed key-batch plan to actor/session/expiry (209-a).

    ``plan_document`` is the EXACT strict version-1 batch plan document
    produced by ``render_key_batch_plan`` (re-parsed here so a caller can
    never bind a non-conformant plan). The token is reviewed data, not
    authority; it is bounded by
    :data:`MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS` (the core 8 MiB plan bound
    plus documented base64url/wrapper overhead).
    """
    parse_key_batch_plan(plan_document)
    # Builder-side decoded-plan bound: the embedded plan must fit the core
    # 8 MiB plan budget in canonical bytes (the strict document parser
    # alone does not enforce a byte limit).
    if len(_canonical_json(plan_document)) > KEY_BATCH_PLAN_MAX_BYTES:
        raise AdminReviewIntentError(_BATCH_TOO_LARGE_MESSAGE)
    issued = now or datetime.now(UTC)
    payload = {
        "purpose": REVIEW_INTENT_BATCH_PURPOSE,
        "admin_user_id": str(admin_user_id),
        "admin_session_id": str(admin_session_id),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
        "plan": plan_document,
    }
    encoded = _canonical_json(payload)
    token = (
        base64.urlsafe_b64encode(encoded).decode("ascii")
        + "."
        + _digest(admin_session_secret, encoded)
    )
    if len(token) > MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS:
        raise AdminReviewIntentError(_BATCH_TOO_LARGE_MESSAGE)
    return token


def verify_batch_review_token(
    *,
    admin_session_secret: str,
    token: str | None,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify, rebind, and strict-reparse one batch review-intent token.

    Returns the exact strict version-1 batch plan document. Every failure
    path raises :class:`AdminReviewIntentError` with a fixed safe message;
    the token bytes never appear in an exception, log, or rendered error.
    A clone-purpose token is refused (different signed purpose).
    """
    if (
        not isinstance(token, str)
        or not token
        or len(token) > MAX_REVIEW_INTENT_BATCH_TOKEN_CHARS
    ):
        raise AdminReviewIntentError(_BATCH_INVALID_MESSAGE)
    body, separator, digest = token.rpartition(".")
    if (
        not separator
        or not body
        or not digest
        or not _DIGEST_RE.match(digest)
    ):
        raise AdminReviewIntentError(_BATCH_INVALID_MESSAGE)
    try:
        encoded = base64.urlsafe_b64decode(body.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        raise AdminReviewIntentError(_BATCH_INVALID_MESSAGE) from None
    if not hmac.compare_digest(_digest(admin_session_secret, encoded), digest):
        raise AdminReviewIntentError(_BATCH_NOT_AUTHENTIC_MESSAGE)
    try:
        payload = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_strict_pairs_hook
        )
    except (UnicodeDecodeError, ValueError):
        raise AdminReviewIntentError(_BATCH_INVALID_MESSAGE) from None
    if not isinstance(payload, dict):
        raise AdminReviewIntentError(_BATCH_INVALID_MESSAGE)
    if payload.get("purpose") != REVIEW_INTENT_BATCH_PURPOSE:
        raise AdminReviewIntentError(_BATCH_NOT_AUTHENTIC_MESSAGE)
    if (
        payload.get("admin_user_id") != str(admin_user_id)
        or payload.get("admin_session_id") != str(admin_session_id)
    ):
        raise AdminReviewIntentError(_BATCH_NOT_AUTHENTIC_MESSAGE)
    expires_raw = payload.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except (TypeError, ValueError):
        raise AdminReviewIntentError(_BATCH_INVALID_MESSAGE) from None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (now or datetime.now(UTC)) >= expires_at:
        raise AdminReviewIntentError(_BATCH_EXPIRED_MESSAGE)
    plan_document = payload.get("plan")
    if not isinstance(plan_document, dict):
        raise AdminReviewIntentError(_BATCH_INVALID_MESSAGE)
    try:
        parse_key_batch_plan(plan_document)
    except Exception:
        raise AdminReviewIntentError(_BATCH_INVALID_MESSAGE) from None
    return plan_document


def build_route_review_token(
    *,
    admin_session_secret: str,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    plan_document: dict[str, Any],
    route_target: str,
    external_tool_ceilings: ExternalToolOperatorCeilings,
    profile_dir: str,
    ttl_seconds: int = REVIEW_INTENT_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Bind one reviewed route-configuration plan to actor/session/expiry (210-a).

    ``plan_document`` is the EXACT strict version-1 route plan document
    rendered by ``render_route_update_plan`` (strictly re-parsed here -
    including the 128 KiB canonical byte bound the document parser alone
    does not enforce - so a caller can never bind a non-conformant plan).
    The exact reviewed route target is signed separately: a valid token
    for one route is never valid for a different route URL, regardless of
    signature. The token is reviewed data, not authority; it is bounded
    by :data:`MAX_REVIEW_INTENT_ROUTE_TOKEN_CHARS`.
    """
    try:
        plan = parse_route_update_plan_document(
            plan_document,
            external_tool_ceilings=external_tool_ceilings,
            profile_dir=profile_dir,
        )
    except Exception as exc:
        raise AdminReviewIntentError(_ROUTE_INVALID_MESSAGE) from exc
    if plan.route_id != str(route_target).strip():
        raise AdminReviewIntentError(_ROUTE_INVALID_MESSAGE)
    # Builder-side decoded-plan bound: the embedded plan must fit the core
    # 128 KiB plan budget in canonical bytes (the strict document parser
    # alone does not enforce a byte limit).
    if len(_canonical_json(plan_document)) > ROUTE_PLAN_FILE_MAX_BYTES:
        raise AdminReviewIntentError(_ROUTE_TOO_LARGE_MESSAGE)
    issued = now or datetime.now(UTC)
    payload = {
        "purpose": REVIEW_INTENT_ROUTE_PURPOSE,
        "admin_user_id": str(admin_user_id),
        "admin_session_id": str(admin_session_id),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
        "route_target": str(route_target).strip(),
        "plan": plan_document,
    }
    encoded = _canonical_json(payload)
    token = (
        base64.urlsafe_b64encode(encoded).decode("ascii")
        + "."
        + _digest(admin_session_secret, encoded)
    )
    if len(token) > MAX_REVIEW_INTENT_ROUTE_TOKEN_CHARS:
        raise AdminReviewIntentError(_ROUTE_TOO_LARGE_MESSAGE)
    return token


def verify_route_review_token(
    *,
    admin_session_secret: str,
    token: str | None,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    route_target: str,
    external_tool_ceilings: ExternalToolOperatorCeilings,
    profile_dir: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify, rebind, and strict-reparse one route review-intent token.

    Returns the exact strict version-1 route plan document. Every failure
    path raises :class:`AdminReviewIntentError` with a fixed safe message;
    the token bytes never appear in an exception, log, or rendered error.
    The signed route target must equal ``route_target`` (the apply URL),
    so a valid token for one route can never apply to a different route.
    A clone/batch-purpose token is refused (different signed purpose).
    """
    if (
        not isinstance(token, str)
        or not token
        or len(token) > MAX_REVIEW_INTENT_ROUTE_TOKEN_CHARS
    ):
        raise AdminReviewIntentError(_ROUTE_INVALID_MESSAGE)
    body, separator, digest = token.rpartition(".")
    if (
        not separator
        or not body
        or not digest
        or not _DIGEST_RE.match(digest)
    ):
        raise AdminReviewIntentError(_ROUTE_INVALID_MESSAGE)
    try:
        encoded = base64.urlsafe_b64decode(body.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        raise AdminReviewIntentError(_ROUTE_INVALID_MESSAGE) from None
    if not hmac.compare_digest(_digest(admin_session_secret, encoded), digest):
        raise AdminReviewIntentError(_ROUTE_NOT_AUTHENTIC_MESSAGE)
    try:
        payload = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_strict_pairs_hook
        )
    except (UnicodeDecodeError, ValueError):
        raise AdminReviewIntentError(_ROUTE_INVALID_MESSAGE) from None
    if not isinstance(payload, dict):
        raise AdminReviewIntentError(_ROUTE_INVALID_MESSAGE)
    if payload.get("purpose") != REVIEW_INTENT_ROUTE_PURPOSE:
        raise AdminReviewIntentError(_ROUTE_NOT_AUTHENTIC_MESSAGE)
    if (
        payload.get("admin_user_id") != str(admin_user_id)
        or payload.get("admin_session_id") != str(admin_session_id)
    ):
        raise AdminReviewIntentError(_ROUTE_NOT_AUTHENTIC_MESSAGE)
    expires_raw = payload.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except (TypeError, ValueError):
        raise AdminReviewIntentError(_ROUTE_INVALID_MESSAGE) from None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (now or datetime.now(UTC)) >= expires_at:
        raise AdminReviewIntentError(_ROUTE_EXPIRED_MESSAGE)
    if payload.get("route_target") != str(route_target).strip():
        raise AdminReviewIntentError(_ROUTE_NOT_AUTHENTIC_MESSAGE)
    plan_document = payload.get("plan")
    if not isinstance(plan_document, dict):
        raise AdminReviewIntentError(_ROUTE_INVALID_MESSAGE)
    # Decoded canonical-plan bound (mirrors the builder): the 128 KiB
    # core plan budget applies to the plan itself, not to the base64url
    # wrapper slack; the document parser alone does not enforce bytes.
    if len(_canonical_json(plan_document)) > ROUTE_PLAN_FILE_MAX_BYTES:
        raise AdminReviewIntentError(_ROUTE_TOO_LARGE_MESSAGE)
    try:
        plan = parse_route_update_plan_document(
            plan_document,
            external_tool_ceilings=external_tool_ceilings,
            profile_dir=profile_dir,
        )
    except Exception:
        raise AdminReviewIntentError(_ROUTE_INVALID_MESSAGE) from None
    if plan.route_id != str(route_target).strip():
        raise AdminReviewIntentError(_ROUTE_NOT_AUTHENTIC_MESSAGE)
    return plan_document




# ---------------------------------------------------------------------------
# 212-a: reviewed Codex-compatibility migration (ONE finite migration)
# ---------------------------------------------------------------------------
#
# The envelope is strict and closed: exact outer keys, exact per-operation
# document keys, string types proven BEFORE any set membership, fullmatch
# hex/version patterns, and the exact frozen selector/tuple/edge law DERIVED
# from the shared Core read-only helpers (no duplicated edge logic).  The
# shared Core migration functions remain the sole operation authority and
# re-validate everything - including the ORIGINAL reason string - at both
# the review (dry-run) and apply calls.

from slaif_gateway.services.codex_module_upgrade import (  # noqa: E402
    CODEX_0149_V4_CLIENT_MODULE,
    UPGRADE_TARGET_CLIENT_MODULES,
    legal_module_operations,
)

_COMPAT_OPERATIONS = frozenset(
    {"module_upgrade", "module_rollback", "profile_migrate"}
)
_COMPAT_MODULE_SELECTORS = frozenset({"0149-v4", "0149-v5", "0162-v1", "0162-v2"})
_COMPAT_PROFILE_TARGETS = frozenset({"active", "0162-v1", "0162-v2"})
# The core migration law (8-200 printable ASCII with non-whitespace
# content) mirrored for envelope strictness only; the shared Core
# validator is still the sole authority and re-validates the ORIGINAL
# string (leading/trailing spaces included; nothing is trimmed) at the
# review and apply calls.
_COMPAT_REASON_RE = re.compile(r"^[\x20-\x7E]{8,200}$")
_COMPAT_VERSION_RE = re.compile(r"^[1-9][0-9]{0,8}$")
_COMPAT_TUPLE_FIELDS = frozenset({"id", "version", "fixture_sha256"})
_COMPAT_PAYLOAD_KEYS = frozenset(
    {"purpose", "admin_user_id", "admin_session_id", "expires_at", "review"}
)
_COMPAT_MODULE_KEYS = frozenset(
    {
        "operation",
        "gateway_key_id",
        "expected_source",
        "target",
        "reason",
        "source_tuple",
        "target_tuple",
    }
)
_COMPAT_PROFILE_KEYS = frozenset(
    {
        "operation",
        "gateway_key_id",
        "from_version",
        "from_digest",
        "target",
        "reason",
        "source_tuple",
        "target_tuple",
    }
)
# Core operation spelling for the read-only legal-fact helper.
_CORE_OPERATION_NAMES = {"module_upgrade": "upgrade", "module_rollback": "rollback"}


def _frozen_tuple_for_selector(selector: str):
    if selector == "0149-v4":
        return CODEX_0149_V4_CLIENT_MODULE
    return UPGRADE_TARGET_CLIENT_MODULES.get(selector)


def _strict_compat_tuple(value: object, *, expected_id: str | None = None) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != _COMPAT_TUPLE_FIELDS
        or not all(
            isinstance(value.get(field), str) and value.get(field)
            for field in _COMPAT_TUPLE_FIELDS
        )
        or (expected_id is not None and value["id"] != expected_id)
        or _COMPAT_VERSION_RE.fullmatch(value["version"]) is None
        or _DIGEST_RE.fullmatch(value["fixture_sha256"]) is None
    ):
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)


def _strict_compatibility_review_document(document: object) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
    operation = document.get("operation")
    if not isinstance(operation, str) or operation not in _COMPAT_OPERATIONS:
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
    required = (
        _COMPAT_MODULE_KEYS
        if operation in ("module_upgrade", "module_rollback")
        else _COMPAT_PROFILE_KEYS
    )
    if set(document) != required:
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
    key_id = document.get("gateway_key_id")
    if not isinstance(key_id, str):
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
    try:
        uuid.UUID(key_id)
    except (ValueError, TypeError):
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE) from None
    reason = document.get("reason")
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or _COMPAT_REASON_RE.fullmatch(reason) is None
    ):
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
    if operation in ("module_upgrade", "module_rollback"):
        source = document.get("expected_source")
        target = document.get("target")
        if (
            not isinstance(source, str)
            or source not in _COMPAT_MODULE_SELECTORS
            or not isinstance(target, str)
            or target not in _COMPAT_MODULE_SELECTORS
        ):
            raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
        # The exact frozen selector/tuple/edge law from the shared Core
        # read-only helpers: the (operation, source, target) pairing must
        # be one of the Core's legal transitions for the frozen source
        # tuple, and both bound tuples must be the exact frozen tuples.
        source_frozen = _frozen_tuple_for_selector(source)
        target_frozen = _frozen_tuple_for_selector(target)
        if source_frozen is None or target_frozen is None:
            raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
        core_pairs = legal_module_operations(source_frozen)
        if (_CORE_OPERATION_NAMES[operation], target) not in core_pairs:
            raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
        _strict_compat_tuple(document.get("source_tuple"))
        _strict_compat_tuple(document.get("target_tuple"))
        if (
            {k: document["source_tuple"][k] for k in _COMPAT_TUPLE_FIELDS}
            != {k: source_frozen[k] for k in _COMPAT_TUPLE_FIELDS}
            or {k: document["target_tuple"][k] for k in _COMPAT_TUPLE_FIELDS}
            != {k: target_frozen[k] for k in _COMPAT_TUPLE_FIELDS}
        ):
            raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
    else:
        from_version = document.get("from_version")
        from_digest = document.get("from_digest")
        target = document.get("target")
        if (
            not isinstance(from_version, str)
            or _COMPAT_VERSION_RE.fullmatch(from_version) is None
            or not isinstance(from_digest, str)
            or _DIGEST_RE.fullmatch(from_digest) is None
            or not isinstance(target, str)
            or target not in _COMPAT_PROFILE_TARGETS
        ):
            raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
        # The profile migration is 0162-family only; the bound source is
        # the exact (version, digest) pin, and a frozen target binds its
        # exact frozen tuple.  The "active" exact tuple is intentionally
        # NOT frozen here: it is bound at review and re-checked against
        # the apply worker's actual registry by the shared apply guard.
        _strict_compat_tuple(
            document.get("source_tuple"), expected_id=CODEX_0162_CLIENT_MODULE_ID
        )
        _strict_compat_tuple(
            document.get("target_tuple"), expected_id=CODEX_0162_CLIENT_MODULE_ID
        )
        if (
            document["source_tuple"]["version"] != from_version
            or document["source_tuple"]["fixture_sha256"] != from_digest
        ):
            raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
        if target != "active":
            target_frozen = UPGRADE_TARGET_CLIENT_MODULES.get(target)
            if target_frozen is None:
                raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
            if (
                {k: document["target_tuple"][k] for k in _COMPAT_TUPLE_FIELDS}
                != {k: target_frozen[k] for k in _COMPAT_TUPLE_FIELDS}
            ):
                raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
    return document


def build_compatibility_review_token(
    *,
    admin_session_secret: str,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    review_document: dict[str, Any],
    ttl_seconds: int = REVIEW_INTENT_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Bind one reviewed Codex-compatibility migration to actor/session/expiry.

    ``review_document`` is the strict finite document validated by
    :func:`_strict_compatibility_review_document` BEFORE canonical
    serialization; the token is bounded by
    :data:`MAX_REVIEW_INTENT_COMPATIBILITY_TOKEN_CHARS`.
    """
    _strict_compatibility_review_document(review_document)
    if len(_canonical_json(review_document)) > COMPATIBILITY_REVIEW_PLAN_MAX_BYTES:
        raise AdminReviewIntentError(_COMPAT_TOO_LARGE_MESSAGE)
    issued = now or datetime.now(UTC)
    payload = {
        "purpose": REVIEW_INTENT_COMPATIBILITY_PURPOSE,
        "admin_user_id": str(admin_user_id),
        "admin_session_id": str(admin_session_id),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
        "review": review_document,
    }
    encoded = _canonical_json(payload)
    token = (
        base64.urlsafe_b64encode(encoded).decode("ascii")
        + "."
        + _digest(admin_session_secret, encoded)
    )
    if len(token) > MAX_REVIEW_INTENT_COMPATIBILITY_TOKEN_CHARS:
        raise AdminReviewIntentError(_COMPAT_TOO_LARGE_MESSAGE)
    return token


def verify_compatibility_review_token(
    *,
    admin_session_secret: str,
    token: str | None,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify, rebind, and strict-reparse one compatibility review token.

    Returns the strict finite review document.  The outer payload is
    CLOSED: exactly the identity/expiry keys plus ``review`` - unknown
    outer keys are refused.  A clone/batch/route token is refused
    (different signed purpose).  Every failure path raises
    :class:`AdminReviewIntentError` with a fixed safe message; the token
    bytes never appear in an exception, log, or rendered error.
    """
    if (
        not isinstance(token, str)
        or not token
        or len(token) > MAX_REVIEW_INTENT_COMPATIBILITY_TOKEN_CHARS
    ):
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
    body, separator, digest = token.rpartition(".")
    if (
        not separator
        or not body
        or not digest
        or not _DIGEST_RE.fullmatch(digest)
    ):
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
    try:
        encoded = base64.urlsafe_b64decode(body.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE) from None
    if not hmac.compare_digest(_digest(admin_session_secret, encoded), digest):
        raise AdminReviewIntentError(_COMPAT_NOT_AUTHENTIC_MESSAGE)
    try:
        payload = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_strict_pairs_hook
        )
    except (UnicodeDecodeError, ValueError):
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE) from None
    if not isinstance(payload, dict) or set(payload) != _COMPAT_PAYLOAD_KEYS:
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE)
    if payload.get("purpose") != REVIEW_INTENT_COMPATIBILITY_PURPOSE:
        raise AdminReviewIntentError(_COMPAT_NOT_AUTHENTIC_MESSAGE)
    if (
        payload.get("admin_user_id") != str(admin_user_id)
        or payload.get("admin_session_id") != str(admin_session_id)
    ):
        raise AdminReviewIntentError(_COMPAT_NOT_AUTHENTIC_MESSAGE)
    expires_raw = payload.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except (TypeError, ValueError):
        raise AdminReviewIntentError(_COMPAT_INVALID_MESSAGE) from None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (now or datetime.now(UTC)) >= expires_at:
        raise AdminReviewIntentError(_COMPAT_EXPIRED_MESSAGE)
    review = payload.get("review")
    # Strict re-validation BEFORE canonical serialization: malformed
    # values yield the fixed safe error, never a serialization fault.
    document = _strict_compatibility_review_document(review)
    if len(_canonical_json(document)) > COMPATIBILITY_REVIEW_PLAN_MAX_BYTES:
        raise AdminReviewIntentError(_COMPAT_TOO_LARGE_MESSAGE)
    return document

# ---------------------------------------------------------------------------
# 213-a: reviewed replay maintenance (strict extend plan + safe reason)
# ---------------------------------------------------------------------------

_REPLAY_REVIEW_KEYS = frozenset({"plan", "reason"})


def _strict_replay_review_document(document: object) -> dict[str, Any]:
    """Closed strict document: the COMPLETE strict extend plan + reason.

    The plan dict must pass the shared strict plan schema (known fields,
    types, ceilings, fingerprints, and the exact round-trip gate); the
    reason follows the normal GUI convention: bounded nonblank Unicode
    (at most MAX_KEY_CONFIGURATION_REASON_LENGTH characters).  The
    string is NEVER trimmed here or in the Core - the reviewed string is
    preserved through apply, where the shared service re-validates
    nonblank content and credential shapes on the ORIGINAL string.
    Every failure is the fixed safe message; no plan value or reason is
    echoed.
    """
    if not isinstance(document, dict) or set(document) != _REPLAY_REVIEW_KEYS:
        raise AdminReviewIntentError(_REPLAY_INVALID_MESSAGE)
    reason = document.get("reason")
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > MAX_KEY_CONFIGURATION_REASON_LENGTH
    ):
        raise AdminReviewIntentError(_REPLAY_INVALID_MESSAGE)
    plan_document = document.get("plan")
    if not isinstance(plan_document, dict):
        raise AdminReviewIntentError(_REPLAY_INVALID_MESSAGE)
    try:
        parse_replay_extend_plan_document(plan_document)
    except Exception:  # noqa: BLE001 - fixed safe vocabulary, never the plan
        raise AdminReviewIntentError(_REPLAY_INVALID_MESSAGE) from None
    return document


def build_replay_review_token(
    *,
    admin_session_secret: str,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    review_document: dict[str, Any],
    ttl_seconds: int = REVIEW_INTENT_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Bind one reviewed replay extension to actor/session/expiry.

    ``review_document`` is the strict finite document validated by
    :func:`_strict_replay_review_document` BEFORE canonical
    serialization; the plan envelope and the token length are both
    bounded before any signing work returns.
    """
    _strict_replay_review_document(review_document)
    if len(_canonical_json(review_document)) > REPLAY_REVIEW_PLAN_MAX_BYTES:
        raise AdminReviewIntentError(_REPLAY_TOO_LARGE_MESSAGE)
    issued = now or datetime.now(UTC)
    payload = {
        "purpose": REVIEW_INTENT_REPLAY_PURPOSE,
        "admin_user_id": str(admin_user_id),
        "admin_session_id": str(admin_session_id),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
        "review": review_document,
    }
    encoded = _canonical_json(payload)
    token = (
        base64.urlsafe_b64encode(encoded).decode("ascii")
        + "."
        + _digest(admin_session_secret, encoded)
    )
    if len(token) > MAX_REVIEW_INTENT_REPLAY_TOKEN_CHARS:
        raise AdminReviewIntentError(_REPLAY_TOO_LARGE_MESSAGE)
    return token


def verify_replay_review_token(
    *,
    admin_session_secret: str,
    token: str | None,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify, rebind, and strict-reparse one replay review token.

    Returns the strict finite review document.  The outer payload is
    CLOSED: exactly the identity/expiry keys plus ``review`` - unknown
    outer keys are refused.  A clone/batch/route/compatibility token is
    refused (different signed purpose).  Every failure path raises
    :class:`AdminReviewIntentError` with a fixed safe message; the token
    bytes never appear in an exception, log, or rendered error.
    """
    if (
        not isinstance(token, str)
        or not token
        or len(token) > MAX_REVIEW_INTENT_REPLAY_TOKEN_CHARS
    ):
        raise AdminReviewIntentError(_REPLAY_INVALID_MESSAGE)
    body, separator, digest = token.rpartition(".")
    if (
        not separator
        or not body
        or not digest
        or not _DIGEST_RE.fullmatch(digest)
    ):
        raise AdminReviewIntentError(_REPLAY_INVALID_MESSAGE)
    try:
        encoded = base64.urlsafe_b64decode(body.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        raise AdminReviewIntentError(_REPLAY_INVALID_MESSAGE) from None
    if not hmac.compare_digest(_digest(admin_session_secret, encoded), digest):
        raise AdminReviewIntentError(_REPLAY_NOT_AUTHENTIC_MESSAGE)
    try:
        payload = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_strict_pairs_hook
        )
    except (UnicodeDecodeError, ValueError):
        raise AdminReviewIntentError(_REPLAY_INVALID_MESSAGE) from None
    if not isinstance(payload, dict) or set(payload) != _COMPAT_PAYLOAD_KEYS:
        raise AdminReviewIntentError(_REPLAY_INVALID_MESSAGE)
    if payload.get("purpose") != REVIEW_INTENT_REPLAY_PURPOSE:
        raise AdminReviewIntentError(_REPLAY_NOT_AUTHENTIC_MESSAGE)
    if (
        payload.get("admin_user_id") != str(admin_user_id)
        or payload.get("admin_session_id") != str(admin_session_id)
    ):
        raise AdminReviewIntentError(_REPLAY_NOT_AUTHENTIC_MESSAGE)
    expires_raw = payload.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except (TypeError, ValueError):
        raise AdminReviewIntentError(_REPLAY_INVALID_MESSAGE) from None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (now or datetime.now(UTC)) >= expires_at:
        raise AdminReviewIntentError(_REPLAY_EXPIRED_MESSAGE)
    review = payload.get("review")
    # Strict re-validation BEFORE canonical serialization: malformed
    # plan values or an edited count yield the fixed safe error, never
    # a serialization fault.
    document = _strict_replay_review_document(review)
    if len(_canonical_json(document)) > REPLAY_REVIEW_PLAN_MAX_BYTES:
        raise AdminReviewIntentError(_REPLAY_TOO_LARGE_MESSAGE)
    return document
# 214-a: separate reviewed pricing-disable purpose (a pricing token is
# never valid for a clone/batch/route/compatibility/replay apply and vice
# versa); same HMAC pattern, same 15-minute bound.
REVIEW_INTENT_PRICING_PURPOSE = "admin.pricing-disable.review.v1"

# 214-a: the compact signed pricing plan is bounded by
# PRICING_DISABLE_PLAN_MAX_BYTES (128 KiB) in canonical form; the review
# wrapper adds ONE bounded nonblank Unicode reason plus the
# identity/expiry envelope.  The canonical serializer uses ensure_ascii,
# so a 512-character astral-Unicode reason can consume 6,144 escaped
# bytes; the fixed +8192 wrapper allowance budgets that maximum plus the
# identity/expiry keys before any signing/base64 work.  The token cap is
# the derived 4/3 base64url expansion plus the digest and separator
# (documented encoding overhead, not a second policy cap).
PRICING_REVIEW_PLAN_MAX_BYTES = PRICING_DISABLE_PLAN_MAX_BYTES + 8192
MAX_REVIEW_INTENT_PRICING_TOKEN_CHARS = (
    PRICING_REVIEW_PLAN_MAX_BYTES * 4
) // 3 + 4096

_PRICING_INVALID_MESSAGE = (
    "The pricing disable review state is missing or invalid."
)
_PRICING_NOT_AUTHENTIC_MESSAGE = (
    "The pricing disable review state is not valid for this signed-in admin."
)
_PRICING_EXPIRED_MESSAGE = (
    "The pricing disable review has expired. Preview the scope again."
)
_PRICING_TOO_LARGE_MESSAGE = (
    "The pricing disable review plan exceeds the bounded review size."
)

_PRICING_REVIEW_KEYS = frozenset({"plan", "reason"})


def _strict_pricing_review_document(document: object) -> dict[str, Any]:
    """Closed strict document: the COMPLETE compact pricing plan + reason.

    The plan dict must pass the shared strict compact plan schema (known
    fields, the bounded row count, unique {id, fingerprint} rows); the
    reason follows the normal GUI convention: bounded nonblank Unicode
    (at most MAX_KEY_CONFIGURATION_REASON_LENGTH characters).  The
    string is NEVER trimmed here or in the Core - the reviewed string is
    preserved through apply, where the GUI re-checks it against this
    request's known incoming aliases.  Every failure is the fixed safe
    message; no plan value or reason is echoed.
    """
    if not isinstance(document, dict) or set(document) != _PRICING_REVIEW_KEYS:
        raise AdminReviewIntentError(_PRICING_INVALID_MESSAGE)
    reason = document.get("reason")
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > MAX_KEY_CONFIGURATION_REASON_LENGTH
    ):
        raise AdminReviewIntentError(_PRICING_INVALID_MESSAGE)
    plan_document = document.get("plan")
    if not isinstance(plan_document, dict):
        raise AdminReviewIntentError(_PRICING_INVALID_MESSAGE)
    try:
        parse_pricing_disable_plan_document(plan_document)
    except Exception:  # noqa: BLE001 - fixed safe vocabulary, never the plan
        raise AdminReviewIntentError(_PRICING_INVALID_MESSAGE) from None
    # The PLAN ITSELF is bounded by its own 128 KiB cap, separately from
    # the +8192 reason/wrapper envelope cap checked by the caller: a
    # conformant-but-oversized plan is refused here, on both the build
    # and the strict re-parse verify path.
    if len(_canonical_json(plan_document)) > PRICING_DISABLE_PLAN_MAX_BYTES:
        raise AdminReviewIntentError(_PRICING_TOO_LARGE_MESSAGE)
    return document


def build_pricing_review_token(
    *,
    admin_session_secret: str,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    review_document: dict[str, Any],
    ttl_seconds: int = REVIEW_INTENT_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Bind one reviewed pricing-disable plan to actor/session/expiry.

    ``review_document`` is the strict finite document validated by
    :func:`_strict_pricing_review_document` BEFORE canonical
    serialization; the plan envelope and the token length are both
    bounded before any signing work returns.
    """
    _strict_pricing_review_document(review_document)
    if len(_canonical_json(review_document)) > PRICING_REVIEW_PLAN_MAX_BYTES:
        raise AdminReviewIntentError(_PRICING_TOO_LARGE_MESSAGE)
    issued = now or datetime.now(UTC)
    payload = {
        "purpose": REVIEW_INTENT_PRICING_PURPOSE,
        "admin_user_id": str(admin_user_id),
        "admin_session_id": str(admin_session_id),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
        "review": review_document,
    }
    encoded = _canonical_json(payload)
    token = (
        base64.urlsafe_b64encode(encoded).decode("ascii")
        + "."
        + _digest(admin_session_secret, encoded)
    )
    if len(token) > MAX_REVIEW_INTENT_PRICING_TOKEN_CHARS:
        raise AdminReviewIntentError(_PRICING_TOO_LARGE_MESSAGE)
    return token


def verify_pricing_review_token(
    *,
    admin_session_secret: str,
    token: str | None,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify, rebind, and strict-reparse one pricing review token.

    Returns the strict finite review document.  The outer payload is
    CLOSED: exactly the identity/expiry keys plus ``review`` - unknown
    outer keys are refused.  A clone/batch/route/compatibility/replay
    token is refused (different signed purpose).  Every failure path
    raises :class:`AdminReviewIntentError` with a fixed safe message; the
    token bytes never appear in an exception, log, or rendered error.
    """
    if (
        not isinstance(token, str)
        or not token
        or len(token) > MAX_REVIEW_INTENT_PRICING_TOKEN_CHARS
    ):
        raise AdminReviewIntentError(_PRICING_INVALID_MESSAGE)
    body, separator, digest = token.rpartition(".")
    if (
        not separator
        or not body
        or not digest
        or not _DIGEST_RE.fullmatch(digest)
    ):
        raise AdminReviewIntentError(_PRICING_INVALID_MESSAGE)
    try:
        encoded = base64.urlsafe_b64decode(body.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        raise AdminReviewIntentError(_PRICING_INVALID_MESSAGE) from None
    if not hmac.compare_digest(_digest(admin_session_secret, encoded), digest):
        raise AdminReviewIntentError(_PRICING_NOT_AUTHENTIC_MESSAGE)
    try:
        payload = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_strict_pairs_hook
        )
    except (UnicodeDecodeError, ValueError):
        raise AdminReviewIntentError(_PRICING_INVALID_MESSAGE) from None
    if not isinstance(payload, dict) or set(payload) != _COMPAT_PAYLOAD_KEYS:
        raise AdminReviewIntentError(_PRICING_INVALID_MESSAGE)
    if payload.get("purpose") != REVIEW_INTENT_PRICING_PURPOSE:
        raise AdminReviewIntentError(_PRICING_NOT_AUTHENTIC_MESSAGE)
    if (
        payload.get("admin_user_id") != str(admin_user_id)
        or payload.get("admin_session_id") != str(admin_session_id)
    ):
        raise AdminReviewIntentError(_PRICING_NOT_AUTHENTIC_MESSAGE)
    expires_raw = payload.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except (TypeError, ValueError):
        raise AdminReviewIntentError(_PRICING_INVALID_MESSAGE) from None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (now or datetime.now(UTC)) >= expires_at:
        raise AdminReviewIntentError(_PRICING_EXPIRED_MESSAGE)
    review = payload.get("review")
    # Strict re-validation BEFORE canonical serialization: malformed
    # plan values or an edited count yield the fixed safe error, never
    # a serialization fault.
    document = _strict_pricing_review_document(review)
    if len(_canonical_json(document)) > PRICING_REVIEW_PLAN_MAX_BYTES:
        raise AdminReviewIntentError(_PRICING_TOO_LARGE_MESSAGE)
    return document

# 215-a: separate bounded SMTP-test intent purpose (a test token is never
# valid for a clone/batch/route/compatibility/replay/pricing apply and
# vice versa); same HMAC pattern, same 15-minute bound.  The strict closed
# document is exactly the reviewed recipient/subject/body plus the one-use
# intent nonce - no transport overrides, no address lists, no gateway key
# material.
REVIEW_INTENT_SMTP_TEST_PURPOSE = "admin.smtp-test.review.v1"

# 215-a: the signed SMTP test document is bounded by its own field caps
# (recipient 254 CHARS, subject 255 UTF-8 BYTES, body 4096 UTF-8 BYTES,
# 32-hex nonce).  JSON ESCAPING is budgeted separately from the raw
# field caps: the canonical serializer is ensure_ascii, so a fully
# multiline/escaped/Unicode body expands before signing.  Per code point
# the worst case is a SURROGATE-PAIR escape of 12 bytes (astral plane,
# e.g. emoji: 4 UTF-8 bytes -> ``\\ud83d\\ude00``); a BMP code point
# costs at most 6 (``\\uXXXX``).  The recipient is char-bounded, so its
# per-code-point worst case (12) applies directly; a byte-bounded field
# of N bytes holds at most N code points, and a 1-byte code point is
# the per-BYTE worst case (6 bytes escaped), so 6 x N bounds it.  The
# escaped document size is therefore finite WITHOUT trimming the body
# or loosening field validation.
_JSON_ESCAPE_WORST_CASE_ASTRAL = 12
_JSON_ESCAPE_WORST_CASE_PER_BYTE = 6
# Exact fixed canonical-JSON overhead of the closed document
# ``{"body":"...","nonce":"...","recipient":"...","subject":"..."}``:
# 2 braces + 3 commas + 4 colons + 16 quotes + key lengths
# (4+5+9+7=25) = 50 bytes.
_SMTP_TEST_DOCUMENT_FIXED_OVERHEAD = 50
SMTP_TEST_REVIEW_ENVELOPE_MAX_BYTES = (
    SMTP_TEST_RECIPIENT_MAX_CHARS * _JSON_ESCAPE_WORST_CASE_ASTRAL
    + (SMTP_TEST_SUBJECT_MAX_BYTES + SMTP_TEST_BODY_MAX_BYTES)
    * _JSON_ESCAPE_WORST_CASE_PER_BYTE
    + 32  # the 32-hex nonce (never escaped)
    + _SMTP_TEST_DOCUMENT_FIXED_OVERHEAD
)

# The signed payload wraps the review document in the closed
# purpose/actor/session/expiry envelope: 2 braces + 4 commas + 5 colons
# + 10 key quotes + key lengths (16+13+10+7+6=52) + 8 value quotes +
# two 36-char UUID values + the 25-char purpose + a 33-char ISO-8601
# expiry = 211 bytes exact overhead.
SMTP_TEST_REVIEW_PAYLOAD_MAX_BYTES = (
    SMTP_TEST_REVIEW_ENVELOPE_MAX_BYTES + 211
)

# Derived base64url token cap: 4*ceil(payloadBytes/3) expansion of the
# bounded payload plus the separator and the 64-hex digest (documented
# encoding overhead, not a second policy cap).  The ceiling matters: a
# floor undercounts the base64 length by up to 2 characters.
MAX_REVIEW_INTENT_SMTP_TEST_TOKEN_CHARS = (
    4 * ((SMTP_TEST_REVIEW_PAYLOAD_MAX_BYTES + 2) // 3) + 1 + 64
)

_SMTP_TEST_INVALID_MESSAGE = (
    "The SMTP test review state is missing or invalid."
)
_SMTP_TEST_NOT_AUTHENTIC_MESSAGE = (
    "The SMTP test review state is not valid for this signed-in admin."
)
_SMTP_TEST_EXPIRED_MESSAGE = (
    "The SMTP test review has expired. Prepare the test again."
)
_SMTP_TEST_TOO_LARGE_MESSAGE = (
    "The SMTP test review exceeds the bounded review size."
)

_SMTP_TEST_REVIEW_KEYS = frozenset({"recipient", "subject", "body", "nonce"})
_SMTP_TEST_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")


def _strict_smtp_test_review_document(document: object) -> dict[str, Any]:
    """Closed strict document: exactly recipient/subject/body/nonce.

    Every field passes the SAME shared bounded law the CLI-style
    validation uses (finite caps, no CR/LF in the subject, no lists or
    transport overrides in the recipient, no known credential shapes).
    The body is the EXACT text that will be sent (safe defaults already
    applied by the caller before signing).  Every failure is the fixed
    safe message; no field value is echoed.
    """
    if not isinstance(document, dict) or set(document) != _SMTP_TEST_REVIEW_KEYS:
        raise AdminReviewIntentError(_SMTP_TEST_INVALID_MESSAGE)
    for value in document.values():
        if not isinstance(value, str):
            raise AdminReviewIntentError(_SMTP_TEST_INVALID_MESSAGE)
    try:
        validate_smtp_test_recipient(document["recipient"])
        validate_smtp_test_subject(document["subject"])
        validate_smtp_test_body(document["body"])
    except Exception:  # noqa: BLE001 - fixed safe vocabulary, never the field
        raise AdminReviewIntentError(_SMTP_TEST_INVALID_MESSAGE) from None
    if not _SMTP_TEST_NONCE_RE.fullmatch(document["nonce"]):
        raise AdminReviewIntentError(_SMTP_TEST_INVALID_MESSAGE)
    return document


def build_smtp_test_review_token(
    *,
    admin_session_secret: str,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    review_document: dict[str, Any],
    ttl_seconds: int = REVIEW_INTENT_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Bind one reviewed SMTP test intent to actor/session/expiry.

    ``review_document`` is the strict finite document validated by
    :func:`_strict_smtp_test_review_document` BEFORE canonical
    serialization; the document envelope and the token length are both
    bounded before any signing work returns.
    """
    _strict_smtp_test_review_document(review_document)
    if len(_canonical_json(review_document)) > SMTP_TEST_REVIEW_ENVELOPE_MAX_BYTES:
        raise AdminReviewIntentError(_SMTP_TEST_TOO_LARGE_MESSAGE)
    issued = now or datetime.now(UTC)
    payload = {
        "purpose": REVIEW_INTENT_SMTP_TEST_PURPOSE,
        "admin_user_id": str(admin_user_id),
        "admin_session_id": str(admin_session_id),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
        "review": review_document,
    }
    encoded = _canonical_json(payload)
    token = (
        base64.urlsafe_b64encode(encoded).decode("ascii")
        + "."
        + _digest(admin_session_secret, encoded)
    )
    if len(token) > MAX_REVIEW_INTENT_SMTP_TEST_TOKEN_CHARS:
        raise AdminReviewIntentError(_SMTP_TEST_TOO_LARGE_MESSAGE)
    return token


def verify_smtp_test_review_token(
    *,
    admin_session_secret: str,
    token: str | None,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify, rebind, and strict-reparse one SMTP test review token.

    Returns the strict finite review document.  The outer payload is
    CLOSED: exactly the identity/expiry keys plus ``review`` - unknown
    outer keys are refused.  A clone/batch/route/compatibility/replay/
    pricing token is refused (different signed purpose).  Every failure
    path raises :class:`AdminReviewIntentError` with a fixed safe
    message; the token bytes never appear in an exception, log, or
    rendered error.
    """
    if (
        not isinstance(token, str)
        or not token
        or len(token) > MAX_REVIEW_INTENT_SMTP_TEST_TOKEN_CHARS
    ):
        raise AdminReviewIntentError(_SMTP_TEST_INVALID_MESSAGE)
    body, separator, digest = token.rpartition(".")
    if (
        not separator
        or not body
        or not digest
        or not _DIGEST_RE.fullmatch(digest)
    ):
        raise AdminReviewIntentError(_SMTP_TEST_INVALID_MESSAGE)
    try:
        encoded = base64.urlsafe_b64decode(body.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        raise AdminReviewIntentError(_SMTP_TEST_INVALID_MESSAGE) from None
    if not hmac.compare_digest(_digest(admin_session_secret, encoded), digest):
        raise AdminReviewIntentError(_SMTP_TEST_NOT_AUTHENTIC_MESSAGE)
    try:
        payload = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_strict_pairs_hook
        )
    except (UnicodeDecodeError, ValueError):
        raise AdminReviewIntentError(_SMTP_TEST_INVALID_MESSAGE) from None
    if not isinstance(payload, dict) or set(payload) != _COMPAT_PAYLOAD_KEYS:
        raise AdminReviewIntentError(_SMTP_TEST_INVALID_MESSAGE)
    if payload.get("purpose") != REVIEW_INTENT_SMTP_TEST_PURPOSE:
        raise AdminReviewIntentError(_SMTP_TEST_NOT_AUTHENTIC_MESSAGE)
    if (
        payload.get("admin_user_id") != str(admin_user_id)
        or payload.get("admin_session_id") != str(admin_session_id)
    ):
        raise AdminReviewIntentError(_SMTP_TEST_NOT_AUTHENTIC_MESSAGE)
    expires_raw = payload.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except (TypeError, ValueError):
        raise AdminReviewIntentError(_SMTP_TEST_INVALID_MESSAGE) from None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (now or datetime.now(UTC)) >= expires_at:
        raise AdminReviewIntentError(_SMTP_TEST_EXPIRED_MESSAGE)
    review = payload.get("review")
    # Strict re-validation BEFORE canonical serialization: a tampered or
    # edited field yields the fixed safe error, never a serialization
    # fault.
    document = _strict_smtp_test_review_document(review)
    if len(_canonical_json(document)) > SMTP_TEST_REVIEW_ENVELOPE_MAX_BYTES:
        raise AdminReviewIntentError(_SMTP_TEST_TOO_LARGE_MESSAGE)
    return document


# ---------------------------------------------------------------------------
# 216-a: bounded reviewed accounting-operations recovery purpose.
#
# A new, separate purpose: an expired / provider-completed / hold recovery
# token is never valid for a clone / batch / route / compatibility / replay /
# pricing / smtp-test apply, and vice versa. Same HMAC-SHA256 +
# administrator-session-secret pattern and the same 15-minute bound as the
# other purposes. The CLOSED document carries exactly ONE action family, the
# exact reviewed target ids (<= 200) plus a per-target relevant-source
# evidence fingerprint, the validated manual hold assertions (finalize-actual
# only), the bounded safe reason, and a one-use nonce. The token is reviewed
# data, never authority: apply re-verifies in constant time, rebinds the
# signed-in actor and session, checks the bound, and the server re-checks
# every target under canonical locks before mutation.
# ---------------------------------------------------------------------------

REVIEW_INTENT_ACCOUNTING_PURPOSE = "admin.accounting-operations.review.v1"

# The four reviewed recovery action families (the fence view has no action).
ACCOUNTING_REVIEW_ACTIONS = frozenset(
    {"expired", "provider_completed", "hold_finalize_actual", "hold_release_no_charge"}
)
# 216-a: the GUI reviewed-selection ceiling (deliberate; the CLI positive
# limits are unchanged). One action family per operation.
ACCOUNTING_REVIEW_MAX_TARGETS = 200

_ACCOUNTING_REVIEW_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
_ACCOUNTING_REVIEW_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_ACCOUNTING_REVIEW_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

_ACCOUNTING_TARGET_KEYS = frozenset({"id", "fingerprint"})
_ACCOUNTING_ASSERTIONS_KEYS = frozenset({"actual_cost_eur", "actual_total_tokens", "success"})
_ACCOUNTING_REVIEW_KEYS = frozenset({"action", "targets", "assertions", "reason", "nonce"})
# 216-a: the explicit operator no-charge choice is sealed for hold actions:
# release MUST carry True, finalize MUST carry False. It is an operator
# decision, never inferred from the selected mode.
_ACCOUNTING_REVIEW_HOLD_KEYS = _ACCOUNTING_REVIEW_KEYS | frozenset({"confirm_no_charge"})

# 216-a: the reviewed recovery reason preserves the existing Core contract -
# a nonblank bounded reason of at most 500 CHARACTERS (Unicode code points,
# not bytes) whose original validated value is preserved and audited. This
# deliberately does NOT inherit the older Codex-compatibility ASCII 8..200
# policy or the SMTP-test byte limit.
_ACCOUNTING_REVIEW_REASON_MAX_CHARS = 500
# Worst-case canonical-JSON expansion of one code point is an astral-plane
# surrogate-pair escape (12 bytes), so a full 500-character Unicode reason
# can expand to at most 500 * 12 bytes before signing. This finite
# worst-case canonical-JSON byte budget for the CLOSED document is used only
# as a backstop (the strict parser enforces the real bounds): 200 targets x
# 126 bytes (36-char id + 64-hex fingerprint, never escaped) plus list
# separators; the 500-char Unicode reason; bounded manual assertions
# (finalize-actual only); a 32-hex nonce; fixed key / structure overhead.
# (The sealed hold no-charge key adds at most ~25 bytes and stays inside
# that fixed overhead margin: hold documents are single-target.)
_ACCOUNTING_REVIEW_DOC_MAX_BYTES = (
    ACCOUNTING_REVIEW_MAX_TARGETS * 126
    + (ACCOUNTING_REVIEW_MAX_TARGETS - 1)
    + 2  # the targets list brackets
    + _ACCOUNTING_REVIEW_REASON_MAX_CHARS * 12  # worst-case Unicode reason
    + 160  # bounded manual assertions (finalize-actual only)
    + 32  # nonce
    + 200  # fixed key / structure overhead
)
# The signed payload wraps the document in the closed
# purpose/actor/session/expiry envelope (same 211-byte exact overhead the
# other review envelopes use).
ACCOUNTING_REVIEW_PAYLOAD_MAX_BYTES = _ACCOUNTING_REVIEW_DOC_MAX_BYTES + 211
# base64url 4/3 expansion of the bounded payload + separator + 64-hex digest
# (documented encoding overhead, not a second policy cap).
MAX_REVIEW_INTENT_ACCOUNTING_TOKEN_CHARS = (
    4 * ((ACCOUNTING_REVIEW_PAYLOAD_MAX_BYTES + 2) // 3) + 1 + 64
)

_ACCOUNTING_INVALID_MESSAGE = (
    "The accounting recovery review state is missing or invalid."
)
_ACCOUNTING_NOT_AUTHENTIC_MESSAGE = (
    "The accounting recovery review state is not valid for this signed-in admin."
)
_ACCOUNTING_EXPIRED_MESSAGE = (
    "The accounting recovery review has expired. Preview the selection again."
)
_ACCOUNTING_TOO_LARGE_MESSAGE = (
    "The accounting recovery review exceeds the bounded review size."
)


def _parse_accounting_decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError, ArithmeticError):
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE) from None
    if not parsed.is_finite() or parsed < 0:
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    return parsed


def _strict_accounting_review_document(document: object) -> dict[str, Any]:
    """Closed strict document: action/targets/assertions/reason/nonce (+ the
    sealed hold no-charge choice).

    Every target carries a 36-char reviewed id and a 64-hex relevant-source
    evidence fingerprint; one action family per operation; at most 200
    targets; hold actions are single-target. Manual hold assertions are
    bounded and typed (finite non-negative cost, non-negative integer tokens,
    explicit boolean outcome) and appear ONLY for finalize-actual; the sealed
    no-charge choice appears ONLY for hold actions (release True, finalize
    False). Every failure is the fixed safe message; no field value is
    echoed.
    """
    if not isinstance(document, dict):
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    action = document.get("action")
    if action not in ACCOUNTING_REVIEW_ACTIONS:
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    allowed_keys = (
        _ACCOUNTING_REVIEW_HOLD_KEYS
        if action in ("hold_finalize_actual", "hold_release_no_charge")
        else _ACCOUNTING_REVIEW_KEYS
    )
    if set(document) != allowed_keys:
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    if action in ("hold_finalize_actual", "hold_release_no_charge"):
        if document["confirm_no_charge"] is not (action == "hold_release_no_charge"):
            raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    targets = document.get("targets")
    if not isinstance(targets, list) or not 1 <= len(targets) <= ACCOUNTING_REVIEW_MAX_TARGETS:
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, dict) or set(target) != _ACCOUNTING_TARGET_KEYS:
            raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
        target_id = target.get("id")
        fingerprint = target.get("fingerprint")
        if not isinstance(target_id, str) or not _ACCOUNTING_REVIEW_UUID_RE.fullmatch(target_id):
            raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
        if not isinstance(fingerprint, str) or not _ACCOUNTING_REVIEW_HEX_RE.fullmatch(fingerprint):
            raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
        if target_id.lower() in seen:
            raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
        seen.add(target_id.lower())
    if action in ("hold_finalize_actual", "hold_release_no_charge") and len(targets) != 1:
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    assertions = document.get("assertions")
    if action == "hold_finalize_actual":
        if not isinstance(assertions, dict) or set(assertions) != _ACCOUNTING_ASSERTIONS_KEYS:
            raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
        cost_raw = assertions.get("actual_cost_eur")
        tokens = assertions.get("actual_total_tokens")
        success = assertions.get("success")
        if not isinstance(cost_raw, str):
            raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
        _parse_accounting_decimal(cost_raw)
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
            raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
        if not isinstance(success, bool):
            raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    elif assertions is not None:
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    reason = document.get("reason")
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > _ACCOUNTING_REVIEW_REASON_MAX_CHARS
    ):
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    nonce = document.get("nonce")
    if not isinstance(nonce, str) or not _ACCOUNTING_REVIEW_NONCE_RE.fullmatch(nonce):
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    return document


def build_accounting_review_token(
    *,
    admin_session_secret: str,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    review_document: dict[str, Any],
    ttl_seconds: int = REVIEW_INTENT_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Bind one reviewed accounting recovery intent to actor/session/expiry.

    ``review_document`` is the strict closed document validated BEFORE
    canonical serialization; both the document envelope and the token length
    are bounded before any signing work returns.
    """
    _strict_accounting_review_document(review_document)
    if len(_canonical_json(review_document)) > _ACCOUNTING_REVIEW_DOC_MAX_BYTES:
        raise AdminReviewIntentError(_ACCOUNTING_TOO_LARGE_MESSAGE)
    issued = now or datetime.now(UTC)
    payload = {
        "purpose": REVIEW_INTENT_ACCOUNTING_PURPOSE,
        "admin_user_id": str(admin_user_id),
        "admin_session_id": str(admin_session_id),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
        "review": review_document,
    }
    encoded = _canonical_json(payload)
    token = (
        base64.urlsafe_b64encode(encoded).decode("ascii")
        + "."
        + _digest(admin_session_secret, encoded)
    )
    if len(token) > MAX_REVIEW_INTENT_ACCOUNTING_TOKEN_CHARS:
        raise AdminReviewIntentError(_ACCOUNTING_TOO_LARGE_MESSAGE)
    return token


def verify_accounting_review_token(
    *,
    admin_session_secret: str,
    token: str | None,
    admin_user_id: uuid.UUID,
    admin_session_id: uuid.UUID,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify, rebind, and strict-reparse one accounting recovery token.

    Returns the strict closed review document. The outer payload is CLOSED:
    exactly the identity/expiry keys plus ``review``. A token for any other
    purpose is refused (different signed purpose). Every failure path raises
    :class:`AdminReviewIntentError` with a fixed safe message; the token
    bytes never appear in an exception, log, or rendered error.
    """
    if (
        not isinstance(token, str)
        or not token
        or len(token) > MAX_REVIEW_INTENT_ACCOUNTING_TOKEN_CHARS
    ):
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    body, separator, digest = token.rpartition(".")
    if not separator or not body or not digest or not _DIGEST_RE.fullmatch(digest):
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    try:
        encoded = base64.urlsafe_b64decode(body.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError):
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE) from None
    if not hmac.compare_digest(_digest(admin_session_secret, encoded), digest):
        raise AdminReviewIntentError(_ACCOUNTING_NOT_AUTHENTIC_MESSAGE)
    try:
        payload = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_strict_pairs_hook
        )
    except (UnicodeDecodeError, ValueError):
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE) from None
    if not isinstance(payload, dict) or set(payload) != _COMPAT_PAYLOAD_KEYS:
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE)
    if payload.get("purpose") != REVIEW_INTENT_ACCOUNTING_PURPOSE:
        raise AdminReviewIntentError(_ACCOUNTING_NOT_AUTHENTIC_MESSAGE)
    if (
        payload.get("admin_user_id") != str(admin_user_id)
        or payload.get("admin_session_id") != str(admin_session_id)
    ):
        raise AdminReviewIntentError(_ACCOUNTING_NOT_AUTHENTIC_MESSAGE)
    expires_raw = payload.get("expires_at")
    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except (TypeError, ValueError):
        raise AdminReviewIntentError(_ACCOUNTING_INVALID_MESSAGE) from None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (now or datetime.now(UTC)) >= expires_at:
        raise AdminReviewIntentError(_ACCOUNTING_EXPIRED_MESSAGE)
    # Strict re-validation BEFORE canonical serialization: a tampered or
    # edited field yields the fixed safe error, never a serialization fault.
    document = _strict_accounting_review_document(payload.get("review"))
    if len(_canonical_json(document)) > _ACCOUNTING_REVIEW_DOC_MAX_BYTES:
        raise AdminReviewIntentError(_ACCOUNTING_TOO_LARGE_MESSAGE)
    return document

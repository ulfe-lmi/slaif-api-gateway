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

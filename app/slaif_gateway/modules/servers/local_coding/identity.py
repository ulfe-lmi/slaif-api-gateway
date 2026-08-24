"""Gateway-owned opaque Local Coding identity derivation and v1 signing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import secrets
from collections.abc import Mapping
from dataclasses import dataclass

from slaif_gateway.modules.servers.local_coding.contract import LocalCodingRouteContract

_SESSION_KEYS = ("session_id", "thread_id", "turn_id", "root_turn_id")
_OPAQUE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")


def _bounded_identity_input(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise ValueError(f"Local Coding {label} is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"Local Coding {label} is invalid")
    return value


@dataclass(frozen=True, slots=True)
class LocalCodingRequestIdentity:
    principal: str
    session: str
    repository: str
    route: str
    identity_mode: str


def _opaque_hmac(secret: bytes, domain: str, *values: str) -> str:
    message = "\n".join((domain, *values)).encode("utf-8")
    digest = hmac.new(secret, message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def derive_request_identity(
    *,
    owner_id: object,
    identity_hints: Mapping[str, str],
    repository_scope: str | None,
    route: LocalCodingRouteContract,
    derivation_secret: bytes | None,
) -> LocalCodingRequestIdentity | None:
    if route.identity_mode == "static":
        return None
    if derivation_secret is None:
        raise ValueError("Local Coding identity derivation secret is unavailable")
    repository_scope = _bounded_identity_input(repository_scope, "repository binding")
    session_values = [
        _bounded_identity_input(identity_hints[key], "session hint")
        for key in _SESSION_KEYS
        if identity_hints.get(key)
    ]
    if not session_values or len(set(session_values)) != 1:
        raise ValueError("Local Coding session context is unavailable or ambiguous")
    owner_truth = _bounded_identity_input(str(owner_id), "owner truth")
    principal = _opaque_hmac(derivation_secret, "slaif-local-coding:principal:v1", owner_truth)
    session = _opaque_hmac(
        derivation_secret,
        "slaif-local-coding:session:v1",
        principal,
        session_values[0],
    )
    repository = _opaque_hmac(
        derivation_secret,
        "slaif-local-coding:repository:v1",
        principal,
        repository_scope,
    )
    return LocalCodingRequestIdentity(
        principal=principal,
        session=session,
        repository=repository,
        route=route.route_name,
        identity_mode=route.identity_mode,
    )


def canonical_identity_bytes(
    *,
    method: str,
    path: str,
    raw_query: bytes,
    body: bytes,
    identity: LocalCodingRequestIdentity,
    timestamp: str,
    nonce: str,
) -> bytes:
    fields = (
        "slaif-local-coding-identity-v1",
        method,
        path,
        hashlib.sha256(raw_query).hexdigest(),
        hashlib.sha256(body).hexdigest(),
        identity.principal,
        identity.session,
        identity.repository,
        identity.route,
        timestamp,
        nonce,
    )
    return "\n".join(fields).encode("utf-8")


def expected_signature(*, secret: bytes, canonical: bytes) -> str:
    return "v1=" + hmac.new(secret, canonical, hashlib.sha256).hexdigest()


def make_nonce(*, minimum: int, maximum: int) -> str:
    nonce = base64.urlsafe_b64encode(secrets.token_bytes(maximum)).decode("ascii").rstrip("=")
    if len(nonce) < minimum:
        raise ValueError("Local Coding nonce generation failed")
    return nonce[:maximum]


def sign_identity(
    *,
    signing_secret: bytes,
    identity: LocalCodingRequestIdentity,
    body: bytes,
    route: LocalCodingRouteContract,
    timestamp: str,
    nonce: str,
) -> dict[str, str]:
    if not math.isfinite(float(timestamp)) or not timestamp.isdigit():
        raise ValueError("Local Coding timestamp is invalid")
    if identity.route != route.route_name:
        raise ValueError("Local Coding identity route does not match route contract")
    if not route.nonce_min_length <= len(nonce) <= route.nonce_max_length:
        raise ValueError("Local Coding nonce is outside route bounds")
    if not nonce or any(character not in _OPAQUE for character in nonce):
        raise ValueError("Local Coding nonce is invalid")
    canonical = canonical_identity_bytes(
        method="POST",
        path="/v1/responses",
        raw_query=b"",
        body=body,
        identity=identity,
        timestamp=timestamp,
        nonce=nonce,
    )
    signature = expected_signature(secret=signing_secret, canonical=canonical)
    headers = {
        "X-SLAIF-Identity-Version": "v1",
        "X-SLAIF-Principal": identity.principal,
        "X-SLAIF-Session": identity.session,
        "X-SLAIF-Repository": identity.repository,
        "X-SLAIF-Route": identity.route,
        "X-SLAIF-Timestamp": timestamp,
        "X-SLAIF-Nonce": nonce,
        "X-SLAIF-Signature": signature,
    }
    if identity.identity_mode != "signed_identity_v1":
        raise ValueError("Local Coding identity mode is not signed")
    return headers

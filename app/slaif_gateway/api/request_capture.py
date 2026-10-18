"""Pure-ASGI observer for the operator-controlled request-capture facility.

This is the ASGI "tee" that observes incoming client requests at the receive
boundary (before JSON/model parsing, module normalization, or request policy)
and, only when a finite, armed capture session matches, publishes a bounded,
masked artifact through the shared file store.

Design (objective 191, R2/R3/R4/R7):

* Default-OFF passthrough: when nothing is armed the only per-request cost is a
  bounded manifest read; no body buffering, no DB access.
* A pure ASGI middleware (no ``BaseHTTPMiddleware``/``request.body`` rewrite):
  the original ``receive``/``send`` messages are forwarded unchanged, so
  bytes, streaming, disconnect, and error behavior are preserved.
* Claim is taken before the body is tee'd; a matching, not-yet-exhausted
  session gates all body buffering, so normal requests never buffer.
* A bounded body buffer (>= 10 MiB by default) preserves the original bytes up
  to the budget. The *total* number of received bytes is tracked separately
  from the captured prefix so ``observed`` reflects the real stream size even
  when the stored prefix is truncated; completeness and the specific
  ``incomplete_reason`` are explicit markers (``not_consumed`` / ``body_limit``
  / ``client_disconnected`` / ``buffer_failure``). A truncated prefix that ends
  on a near-full copy of a known secret is masked, never written almost
  complete.
* The verified key UUID is obtained by a **read-only** auth probe (isolated,
  closed DB session) only while a session is active and an Authorization
  header is present; probe errors never alter the request response or
  admission, and a UUID-filtered session is never consumed by a mismatch.
* Masking uses the content-preserving redactor; known auth values are masked in
  every request-derived stored string (method, local rejection params) as well
  as the raw path/query/headers/body. On any masking/store failure the capture
  is skipped safely and the app is never re-run.
* If the app raises, the observer finalizes (writing a safe artifact with the
  original exception class only, never its message or traceback) and re-raises
  the *exact* original exception object; the app is always called exactly once.
* The artifact is correlated to the response by the server-generated
  ``X-SLAIF-Diagnostic-ID`` (``gw-...``); the precise local rejection reason is
  read from the shared per-request scope state (reliable across the
  BaseHTTPMiddleware child tasks used by RequestId/Metrics).
* No raw request content is written; the caller passes already-masked bytes to
  the store. No response body/stream is captured.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from slaif_gateway.config import Settings
from slaif_gateway.services.request_capture import (
    CAPTURE_REJECTION_STATE_KEY,
    CaptureStore,
    CaptureStoreError,
    build_capture_facility,
    get_scope_capture_provenance,
    get_scope_capture_rejection,
)
from slaif_gateway.utils.capture_redaction import (
    CaptureRedactionError,
    build_capture_masker,
    collect_incoming_secrets,
    redact_capture_request,
)

__all__ = [
    "CAPTURE_REJECTION_STATE_KEY",
    "RequestCaptureMiddleware",
    "build_capture_facility",
    "install_request_capture",
]

logger = logging.getLogger("slaif_gateway.request_capture")

# The diagnostic ID is the server-generated ``gw-<uuid4>`` correlation key.
_DIAGNOSTIC_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_DIAGNOSTIC_HEADER = b"x-slaif-diagnostic-id"
# Bound the serialized local rejection reason so a stray oversized context
# cannot inflate an artifact.
_MAX_REJECTION_BYTES = 8192
# Fixed, content-free replacement token used for non-recognized secrets so the
# method / rejection masking is consistent with the redactor.
_FULLY_REDACTED = b"[REDACTED]"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _b64(data: bytes) -> str:
    return base64.b64encode(bytes(data)).decode("ascii")


def _dumps(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sanitize_rejection(value: Any) -> dict[str, Any] | None:
    """Return a bounded, JSON-safe view of the recorded rejection reason.

    The policy records a structured, content-free reason. This bounds the
    serialized size and drops any non-serializable content defensively; it
    never introduces raw request content.
    """
    if not isinstance(value, dict) or not value:
        return None
    try:
        blob = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    except (TypeError, ValueError):
        return None
    if len(blob) > _MAX_REJECTION_BYTES:
        return {"reason": "rejection_too_large"}
    return value


# -- wiring --------------------------------------------------------------


def install_request_capture(app: Any, settings: Settings) -> CaptureStore | None:
    """Wire the capture middleware into ``app`` if the facility is enabled.

    Returns the built store (for diagnostics) or ``None`` when disabled/invalid.
    Adds the observer as the outermost HTTP middleware so it can read the
    server-generated diagnostic ID that RequestIdMiddleware sets.
    """
    store = build_capture_facility(settings)
    if store is None:
        return None
    try:
        accepted = settings.get_gateway_key_accepted_prefixes()
    except Exception:  # noqa: BLE001 - fall back to the single default prefix
        accepted = (settings.GATEWAY_KEY_PREFIX,)
    app.add_middleware(
        RequestCaptureMiddleware,
        store=store,
        body_budget_bytes=store.config.body_budget_bytes,
        accepted_prefixes=accepted,
    )
    app.state.capture_store = store
    return store


# -- masking helpers for request-derived metadata -------------------------


def _secret_pairs(
    secrets: Sequence[tuple[bytes, str | None]],
) -> list[tuple[bytes, bytes]]:
    """Build ``(secret, replacement)`` pairs matching the redactor's scheme."""
    pairs: list[tuple[bytes, bytes]] = []
    for secret, hint in secrets:
        if not isinstance(secret, (bytes, bytearray)) or not secret:
            continue
        replacement = hint.encode("utf-8") if hint is not None else _FULLY_REDACTED
        pairs.append((bytes(secret), replacement))
    return pairs


def _mask_text(text: str, masker: Callable[[bytes], bytes] | None) -> str:
    """Apply the byte masker to one request-derived string value.

    A surrogatepass round-trip handles values containing lone surrogates
    without raising, while the (ASCII) known secrets are still masked. On the
    unexpected event masking cannot be applied, the value is replaced by a
    fixed content-free marker; the original value is NEVER returned unmasked.
    """
    if not isinstance(text, str) or not text:
        return text
    if masker is None:
        return text
    try:
        masked = masker(text.encode("utf-8", "surrogatepass"))
        return masked.decode("utf-8", "surrogatepass")
    except Exception:  # noqa: BLE001 - fail safe: never leak the original
        return _FULLY_REDACTED.decode("ascii")


def _mask_structure(value: Any, masker: Callable[[bytes], bytes] | None) -> Any:
    """Recursively mask every string *value* in a structured rejection dict.

    Field names, and non-string values (ints/bools/None), are left untouched so
    the structured rejection shape is preserved; only values that may repeat a
    known auth secret are masked.
    """
    if masker is None:
        return value
    if isinstance(value, str):
        return _mask_text(value, masker)
    if isinstance(value, Mapping):
        return {key: _mask_structure(item, masker) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mask_structure(item, masker) for item in value]
    return value


# -- bounded request/response observation -----------------------------------


class _BodyBuffer:
    """Bounded, order-preserving capture of the raw request body bytes.

    Tracks the *total* number of received bytes separately from the captured
    prefix (capped at the budget) so the observed size always reflects the real
    stream even when the stored prefix is truncated or the budget is zero.
    """

    def __init__(self, budget: int) -> None:
        self._budget = max(0, int(budget))
        self._chunks: list[bytes] = []
        self._captured = 0
        self.total_received = 0
        self.complete = False
        self.buffer_failed = False

    @property
    def truncated(self) -> bool:
        return self.total_received > self._budget

    def ingest(self, chunk: bytes, more_body: bool) -> None:
        if self.buffer_failed:
            return
        try:
            chunk = bytes(chunk)
        except (TypeError, ValueError):
            self.buffer_failed = True
            return
        self.total_received += len(chunk)
        if self._budget > 0 and self._captured < self._budget:
            room = self._budget - self._captured
            take = chunk if len(chunk) <= room else chunk[:room]
            if take:
                self._chunks.append(take)
                self._captured += len(take)
        if not more_body:
            self.complete = True

    def body_bytes(self) -> bytes:
        return b"".join(self._chunks)

    @property
    def observed_bytes(self) -> int:
        return self.total_received

    @property
    def buffered_bytes(self) -> int:
        return self._captured

    @property
    def body_complete(self) -> bool:
        return self.complete and not self.truncated


class _ResponseState:
    def __init__(self) -> None:
        self.status: int | None = None
        self.headers: list[tuple[bytes, bytes]] = []
        self.disconnected = False


class _Claimed:
    __slots__ = ("session_id", "endpoint", "verified_key_uuid")

    def __init__(self, session_id: str, endpoint: str, verified_key_uuid: str | None) -> None:
        self.session_id = session_id
        self.endpoint = endpoint
        self.verified_key_uuid = verified_key_uuid


def _incomplete_reason(buffer: _BodyBuffer, response: _ResponseState) -> str | None:
    """Return the explicit reason a captured body is incomplete, else ``None``."""
    if buffer.body_complete:
        return None
    if buffer.buffer_failed:
        return "buffer_failure"
    if buffer.total_received == 0:
        return "not_consumed"
    if buffer.truncated:
        return "body_limit"
    if response.disconnected:
        return "client_disconnected"
    return "not_consumed"


# -- header helpers ----------------------------------------------------------


def _headers_from_scope(scope: dict[str, Any]) -> list[tuple[str, bytes]]:
    raw = scope.get("headers", []) or []
    out: list[tuple[str, bytes]] = []
    for item in raw:
        try:
            name, value = item
        except (TypeError, ValueError):
            continue
        out.append((bytes(name).decode("latin-1"), bytes(value)))
    return out


def _first_header(headers: list[tuple[str, bytes]], name: str) -> str | None:
    needle = name.lower().encode("latin-1")
    for item in headers:
        if item[0].encode("latin-1", "ignore").lower() == needle:
            return item[1].decode("latin-1")
    return None


def _has_authorization(headers: list[tuple[str, bytes]]) -> bool:
    return any(h[0].lower() == "authorization" for h in headers)


def _diagnostic_id(scope: dict[str, Any], headers: list[tuple[bytes, bytes]]) -> str | None:
    state = scope.get("state")
    if isinstance(state, dict):
        gid = state.get("gateway_request_id")
        if isinstance(gid, str) and _DIAGNOSTIC_ID_RE.fullmatch(gid):
            return gid
    for name, value in headers or []:
        if name.lower() == _DIAGNOSTIC_HEADER:
            try:
                gid = value.decode("ascii")
            except UnicodeDecodeError:
                continue
            if _DIAGNOSTIC_ID_RE.fullmatch(gid):
                return gid
    return None


# -- middleware --------------------------------------------------------------


class RequestCaptureMiddleware:
    """Outermost pure-ASGI capture observer (default-OFF passthrough)."""

    def __init__(
        self,
        app: Awaitable,
        *,
        store: CaptureStore,
        body_budget_bytes: int,
        accepted_prefixes: tuple[str, ...] | list[str],
    ) -> None:
        self.app = app
        self._store = store
        self._config = store.config
        self._body_budget = max(0, int(body_budget_bytes))
        self._accepted_prefixes = tuple(accepted_prefixes)

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        claimed = await self._try_claim(scope)
        if claimed is None:
            # Default-OFF / no matching active session: unchanged passthrough.
            await self.app(scope, receive, send)
            return
        await self._run_captured(scope, receive, send, claimed)

    # -- claim (before body tee) --------------------------------------------

    async def _try_claim(self, scope: dict[str, Any]) -> _Claimed | None:
        try:
            endpoint = scope.get("path", "")
            if not isinstance(endpoint, str) or not endpoint.startswith("/"):
                return None
            summary = self._store.peek(endpoint=endpoint)
            if summary is None:
                return None
            headers = _headers_from_scope(scope)
            verified_uuid = None
            if _has_authorization(headers):
                verified_uuid = await self._probe_verified_key(scope, headers)
            session = self._store.claim(
                endpoint=endpoint,
                key_uuid=verified_uuid,
                reserve_bytes=self._store.reservation_bytes(),
            )
            if session is None:
                return None
            return _Claimed(session.session_id, session.endpoint, verified_uuid)
        except CaptureStoreError:
            return None
        except Exception:  # noqa: BLE001 - never affect the app
            return None

    # -- read-only verified-key probe (bounded, isolated) -------------------

    async def _probe_verified_key(
        self, scope: dict[str, Any], headers: list[tuple[str, bytes]]
    ) -> str | None:
        try:
            app = scope.get("app")
            state = getattr(app, "state", None)
            settings = getattr(state, "settings", None)
            sessionmaker = getattr(state, "db_sessionmaker", None)
            if settings is None or sessionmaker is None:
                return None
            authorization = _first_header(headers, "authorization")
            if not authorization:
                return None
            from slaif_gateway.db.repositories.keys import GatewayKeysRepository
            from slaif_gateway.services.auth_service import GatewayAuthService

            session = sessionmaker()
            try:
                repository = GatewayKeysRepository(session)
                service = GatewayAuthService(
                    settings=settings, gateway_keys_repository=repository
                )
                result = await service.authenticate_authorization_header(authorization)
                return str(result.gateway_key_id)
            finally:
                await session.close()
        except Exception:  # noqa: BLE001 - probe errors never alter the request
            return None

    # -- captured run (bounded body tee + artifact publication) -------------

    async def _run_captured(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
        claimed: _Claimed,
    ) -> None:
        buffer = _BodyBuffer(self._body_budget)
        response = _ResponseState()

        async def tee_receive() -> dict[str, Any]:
            message = await receive()
            mtype = message.get("type")
            if mtype == "http.request":
                buffer.ingest(
                    message.get("body", b""), bool(message.get("more_body", False))
                )
            elif mtype == "http.disconnect":
                response.disconnected = True
            return message

        async def tee_send(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                response.status = message.get("status")
                response.headers = list(message.get("headers", []) or [])
            await send(message)

        try:
            await self.app(scope, tee_receive, tee_send)
        except BaseException as exc:
            # Finalize (write a safe artifact) then re-raise the EXACT original
            # exception; the app is never re-run and capture cannot affect it.
            try:
                self._finalize(scope, claimed, buffer, response, exception=exc)
            except BaseException:  # noqa: BLE001 - never mask the original error
                pass
            raise
        self._finalize(scope, claimed, buffer, response)

    def _finalize(
        self,
        scope: dict[str, Any],
        claimed: _Claimed,
        buffer: _BodyBuffer,
        response: _ResponseState,
        exception: BaseException | None = None,
    ) -> None:
        try:
            request_id = _diagnostic_id(scope, response.headers)
            if request_id is None:
                return

            # Preserve the ORIGINAL percent-encoded path when the server gave
            # us ``raw_path``; fall back to encoding the decoded path.
            raw_path = scope.get("raw_path")
            if isinstance(raw_path, (bytes, bytearray)):
                path_bytes = bytes(raw_path)
            else:
                path = scope.get("path", "")
                path_bytes = (
                    path.encode("utf-8", "surrogateescape")
                    if isinstance(path, str)
                    else bytes(path)
                )

            query = scope.get("query_string", b"")
            query_bytes = (
                query.encode("utf-8", "surrogateescape")
                if isinstance(query, str)
                else bytes(query)
            )
            headers = _headers_from_scope(scope)
            body = buffer.body_bytes()
            body_complete = buffer.body_complete

            # Incomplete captures are NOT persisted: a truncated / disconnected
            # / unconsumed body prefix can carry a near-complete credential in a
            # raw, percent-encoded, or JSON-escaped form that whole-secret
            # masking cannot recover.  For an incomplete capture we therefore
            # store NO body bytes (path/query/headers remain fully masked) and
            # record the observed/buffered/stored counts plus a stable note.
            # Complete bodies are retained fully except explicit auth
            # substitutions.  Request bytes are always forwarded unchanged.
            body_for_redaction = body if body_complete else b""

            # Discover the incoming secrets once and mask every request-derived
            # stored value (raw path/query/headers plus method and the local
            # rejection params) with the same, consistent replacements.
            secrets, _notes, _hint = collect_incoming_secrets(
                query=query_bytes,
                headers=headers,
                body=body,
                accepted_prefixes=self._accepted_prefixes,
            )
            pairs = _secret_pairs(secrets)
            try:
                masked = redact_capture_request(
                    path=path_bytes,
                    query=query_bytes,
                    headers=headers,
                    body=body_for_redaction,
                    accepted_prefixes=self._accepted_prefixes,
                    body_complete=body_complete,
                )
            except CaptureRedactionError:
                return  # masking failed: skip capture safely
            masker = build_capture_masker(pairs) if pairs else None

            method = scope.get("method")
            if isinstance(method, str) and masker is not None:
                method = _mask_text(method, masker)

            rejection = _sanitize_rejection(get_scope_capture_rejection(scope))
            if rejection is not None and masker is not None:
                rejection = _mask_structure(rejection, masker)

            incomplete_reason = _incomplete_reason(buffer, response)
            declared = _declared_content_length(headers)

            # Provenance: prefer the normal-auth verified key (authoritative);
            # otherwise the read-only capture probe's verified key.  Selected
            # client-module identity is best-effort.  All content-free.
            provenance = get_scope_capture_provenance(scope) or {}
            normal_uuid = provenance.get("verified_key_uuid")
            if isinstance(normal_uuid, str) and normal_uuid:
                final_key_uuid = normal_uuid
                key_provenance = (
                    provenance.get("auth_provenance") or "normal_auth"
                )
            elif claimed.verified_key_uuid:
                final_key_uuid = claimed.verified_key_uuid
                key_provenance = "read_only_capture_probe"
            else:
                final_key_uuid = None
                key_provenance = None
            module_id = (
                provenance.get("module_id")
                if isinstance(provenance.get("module_id"), str)
                else None
            )
            module_version = (
                provenance.get("module_version")
                if isinstance(provenance.get("module_version"), str)
                else None
            )
            module_fixture_sha256 = (
                provenance.get("module_fixture_sha256")
                if isinstance(provenance.get("module_fixture_sha256"), str)
                else None
            )

            capture_doc = {
                "schema_version": 1,
                "request_id": request_id,
                "method": method,
                "path": _b64(masked.path),
                "query": _b64(masked.query),
                "headers": [[name, _b64(value)] for name, value in masked.headers],
                "body": _b64(masked.body),
                "body_complete": bool(masked.body_complete),
                "incomplete_reason": incomplete_reason,
                "body_omitted_for_secret_safety": not body_complete,
                "body_bytes_observed": buffer.observed_bytes,
                "body_bytes_buffered": buffer.buffered_bytes,
                "body_bytes_stored": len(masked.body),
                "body_bytes_declared": declared,
                "body_truncated": bool(buffer.truncated),
                "body_disconnected": bool(response.disconnected),
                "secrets_masked": int(masked.secrets_masked),
            }
            record_doc = {
                "schema_version": 1,
                "request_id": request_id,
                "captured_at": _utc_now_iso(),
                "endpoint": claimed.endpoint,
                "verified_key_uuid": final_key_uuid,
                "verified_key_provenance": key_provenance,
                "module_id": module_id,
                "module_version": module_version,
                "module_fixture_sha256": module_fixture_sha256,
                "recognized_hint": masked.recognized_hint,
                "status_code": response.status,
                "app_raised": exception is not None,
                "exception_class": type(exception).__name__ if exception is not None else None,
                "body_complete": bool(masked.body_complete),
                "incomplete_reason": incomplete_reason,
                "rejection": rejection,
                "deployed_revision": self._config.deployed_revision,
                "revision_provenance": self._config.revision_provenance,
                "app_version": self._config.app_version,
            }
            self._store.write_artifact(
                session_id=claimed.session_id,
                request_id=request_id,
                capture=_dumps(capture_doc),
                record=_dumps(record_doc),
            )
        except CaptureStoreError:
            return
        except Exception:  # noqa: BLE001 - capture must never affect the app
            return


def _declared_content_length(headers: list[tuple[str, bytes]]) -> int | None:
    value = _first_header(headers, "content-length")
    if value is None:
        return None
    try:
        parsed = int(value.strip())
    except (ValueError, AttributeError):
        return None
    return parsed if parsed >= 0 else None

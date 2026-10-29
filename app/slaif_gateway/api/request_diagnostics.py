"""Pure-ASGI observer for the content-free request-failure diagnostics.

Design (work order 201-a):

* Default-OFF: installed only when ``REQUEST_DIAGNOSTICS_ENABLED`` is true at
  startup; otherwise the app is untouched (zero per-request cost).
* Pure ASGI middleware (no ``BaseHTTPMiddleware``): the original
  ``receive``/``send`` messages are forwarded unchanged, so bytes,
  streaming, disconnect, and error behavior are preserved exactly.
* Terminal-outcome observation only: the response status is read from the
  ``http.response.start`` message, and a diagnostic is recorded at most
  ONCE after the final HTTP/stream outcome.  No response/request body is
  parsed or buffered to derive diagnostics.
* One observer write after the terminal outcome, with pure best-effort fact
  hooks at the existing decisions (stream boundaries, route-limit
  rejections, the shared local-error classifier, normal-auth provenance).
* A successful request never produces a record; HTTP 200 alone never
  produces a success diagnostic for a failed stream (the stream-failure
  hooks mark the scope, the observer records ``stream_failure`` with the
  actual HTTP status).
* ``asyncio.CancelledError`` is NEVER suppressed: cancellation facts are
  recorded best-effort and the exact cancellation is re-raised.
* A failed insert, timeout, unavailable schema/database, capacity
  contention, or cleanup error never changes the original HTTP/SSE result,
  admission, accounting, or cancellation (the shared service is bounded and
  best-effort; the observer additionally guards every step).
* Only ``/v1`` failure paths are observed; the admin surface is untouched.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from slaif_gateway.config import Settings
from slaif_gateway.services.request_capture import (
    get_scope_capture_provenance,
    get_scope_capture_rejection,
)
from slaif_gateway.services.request_diagnostics import (
    RequestDiagnosticsService,
    build_client_id_masker,
    get_scope_diagnostics,
)

__all__ = [
    "DiagnosticsObserverMiddleware",
    "install_request_diagnostics",
]

# Explicit, known keys contributed by the narrow observation hooks.
_HOOK_FACT_KEYS = (
    "source",
    "reason_code",
    "error_code",
    "error_param",
    "positions",
    "counts",
    "limits",
    "route_id",
    "route_pattern",
    "deployment_revision",
    "estimated_input_tokens",
    "output_allowance_tokens",
    "context_window_tokens",
    "replay_error_code",
)


def _project_rejection_facts(rejection: object) -> dict[str, Any]:
    """Project ONLY safe typed fields from the shared classifier map.

    Never copies ``error_message``, the classifier ``field`` free-form
    value, validation ``loc`` strings, error types, or decoder text.  The
    genuine integer ``observed`` count IS preserved, under its own finite
    counts key, alongside ``count``/``limit``.  The shared service
    re-validates every projected value against its finite vocabularies
    before anything is stored.
    """
    if not isinstance(rejection, Mapping) or not rejection:
        return {}
    out: dict[str, Any] = {}
    for key in ("source", "reason_code", "error_code"):
        value = rejection.get(key)
        if isinstance(value, str) and value:
            out[key] = value
    for key in ("error_param", "param"):
        value = rejection.get(key)
        if isinstance(value, str) and value:
            out.setdefault("error_param", value)
            break
    status = rejection.get("status_code")
    if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
        out.setdefault("http_status", status)
    positions: dict[str, int] = {}
    for key in ("namespace_index", "tool_index"):
        value = rejection.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            positions[key] = value
    errors = rejection.get("errors")
    if isinstance(errors, (list, tuple)) and errors and isinstance(errors[0], Mapping):
        first = errors[0]
        for key in ("line", "column", "pos"):
            value = first.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                positions.setdefault(key, value)
    if positions:
        out["positions"] = positions
    counts: dict[str, int] = {}
    for key in ("count", "limit", "observed"):
        value = rejection.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            counts[key] = value
    if counts:
        out["counts"] = counts
    return out


class DiagnosticsObserverMiddleware:
    """One terminal, content-free, best-effort diagnostics observer."""

    def __init__(
        self,
        app: Callable[..., Any],
        *,
        settings: Settings,
        accepted_prefixes: tuple[str, ...],
    ) -> None:
        self.app = app
        self._settings = settings
        self._accepted_prefixes = tuple(accepted_prefixes)

    async def __call__(
        self, scope: dict[str, Any], receive: Any, send: Any
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path")
        if not isinstance(path, str) or not path.startswith("/v1"):
            await self.app(scope, receive, send)
            return
        observed: dict[str, Any] = {"status": None, "response_started": False}

        async def wrapped_send(message: dict[str, Any]) -> None:
            try:
                mtype = message.get("type")
                if mtype == "http.response.start":
                    observed["status"] = message.get("status")
                    observed["response_started"] = True
                elif mtype in ("http.response.body", "http.response.pathsend"):
                    observed["response_started"] = True
            except Exception:  # noqa: BLE001 - observation never affects the request
                pass
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except BaseException as exc:  # noqa: BLE001 - must re-raise EXACTLY
            await self._observe(scope, observed, exc)
            raise
        await self._observe(scope, observed, None)

    # -- terminal observation -------------------------------------------

    async def _observe(
        self, scope: dict[str, Any], observed: dict[str, Any], app_exc: BaseException | None
    ) -> None:
        """Record at most one terminal diagnostic; never raise (except an
        in-flight cancellation, which is re-raised, never suppressed)."""
        try:
            outcome = self._decide_outcome(scope, observed, app_exc)
            if outcome is None:
                return
            service = self._build_service(scope)
            if service is None:
                return
            facts = self._assemble_facts(scope, observed, outcome, app_exc)
            if facts is None:
                return
            masker, complete = build_client_id_masker(
                scope, accepted_prefixes=self._accepted_prefixes
            )
            await service.record_failure(
                facts,
                client_id_masker=masker,
                client_id_mask_complete=complete,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - observability must never affect the request
            pass

    @staticmethod
    def _decide_outcome(
        scope: dict[str, Any], observed: dict[str, Any], app_exc: BaseException | None
    ) -> str | None:
        status = observed["status"]
        if app_exc is None:
            if isinstance(status, int) and status >= 400:
                return "http_rejection"
            facts = get_scope_diagnostics(scope)
            hook = facts.get("stream_outcome") if isinstance(facts, Mapping) else None
            if hook in ("stream_failure", "cancelled"):
                return hook
            return None
        if isinstance(app_exc, asyncio.CancelledError):
            return "cancelled"
        # A response was already started (e.g. HTTP 200 headers for a
        # streaming response) before the stream broke: a stream failure.
        if isinstance(status, int) and status < 400:
            return "stream_failure"
        # No response was observed: the request failed before a response
        # was produced (the server error middleware answers 500 outside
        # this middleware).
        return "http_rejection"

    def _build_service(self, scope: dict[str, Any]) -> RequestDiagnosticsService | None:
        app = scope.get("app")
        state = getattr(app, "state", None)
        session_factory = getattr(state, "db_sessionmaker", None)
        if session_factory is None:
            return None
        return RequestDiagnosticsService(
            settings=self._settings, session_factory=session_factory
        )

    def _assemble_facts(
        self,
        scope: dict[str, Any],
        observed: dict[str, Any],
        outcome: str,
        app_exc: BaseException | None,
    ) -> dict[str, Any] | None:
        state = scope.get("state")
        gateway_request_id = state.get("gateway_request_id") if isinstance(state, Mapping) else None
        if not isinstance(gateway_request_id, str) or not gateway_request_id:
            return None  # no server diagnostic ID: cannot correlate honestly
        client_request_id = (
            state.get("request_id") if isinstance(state, Mapping) else None
        )
        facts: dict[str, Any] = {
            "gateway_request_id": gateway_request_id,
            "client_request_id": client_request_id,
            "method": scope.get("method"),
            "occurred_at": datetime.now(UTC),
            "stream_outcome": outcome,
        }
        status = observed["status"]
        wire_status = (
            status if isinstance(status, int) and 100 <= status <= 599 else None
        )
        route = scope.get("route")
        route_path = getattr(route, "path", None)
        if isinstance(route_path, str) and route_path:
            # Static matched route template only (never a raw path).
            facts["endpoint_template"] = route_path
        facts.update(_project_rejection_facts(get_scope_capture_rejection(scope)))
        # The actually-observed ASGI wire status wins over the classifier's
        # status hint; the hint only fills in when no status was observed.
        if wire_status is not None:
            facts["http_status"] = wire_status
        provenance = get_scope_capture_provenance(scope)
        if (
            isinstance(provenance, Mapping)
            and provenance.get("auth_provenance") == "normal_auth"
        ):
            # Normal successful authentication ONLY; a read-only
            # capture-probe provenance must never supply identity.
            facts["gateway_key_id"] = provenance.get("verified_key_uuid")
        hook_facts = get_scope_diagnostics(scope)
        if isinstance(hook_facts, Mapping):
            for key in _HOOK_FACT_KEYS:
                value = hook_facts.get(key)
                if value is not None:
                    facts[key] = value
        if app_exc is not None and not facts.get("error_code"):
            code = getattr(app_exc, "code", None) or getattr(app_exc, "error_code", None)
            if isinstance(code, str) and code:
                facts["error_code"] = code
        revision = getattr(self._settings, "REQUEST_CAPTURE_DEPLOYED_REVISION", "")
        if isinstance(revision, str) and revision:
            facts.setdefault("deployment_revision", revision)
        return facts


def install_request_diagnostics(app: Any, settings: Settings) -> None:
    """Wire the default-OFF diagnostics observer into ``app``.

    Adds the observer INSIDE ``RequestIdMiddleware`` (so the server
    diagnostic and client request IDs exist on the scope state) and inside
    the capture observer (which stays outermost).  No-op when recording is
    disabled at startup; changing the setting requires restarting the API
    workers.
    """
    if not bool(getattr(settings, "REQUEST_DIAGNOSTICS_ENABLED", False)):
        return
    try:
        accepted = settings.get_gateway_key_accepted_prefixes()
    except Exception:  # noqa: BLE001 - fall back to the single default prefix
        accepted = (settings.GATEWAY_KEY_PREFIX,)
    app.add_middleware(
        DiagnosticsObserverMiddleware,
        settings=settings,
        accepted_prefixes=tuple(accepted),
    )

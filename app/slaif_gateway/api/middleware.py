"""HTTP middleware for request IDs and low-cardinality metrics."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from slaif_gateway.config import Settings
from slaif_gateway.logging import bind_request_id, clear_log_context
from slaif_gateway.metrics import observe_http_request
from slaif_gateway.services.request_diagnostics import build_client_id_masker

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
SLAIF_DIAGNOSTIC_ID_HEADER = "X-SLAIF-Diagnostic-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a safe request ID to request state, logs, and response headers."""

    def __init__(self, app, *, settings: Settings) -> None:
        super().__init__(app)
        self._header_name = settings.REQUEST_ID_HEADER
        self._settings = settings

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _safe_request_id(request.headers.get(self._header_name))
        gateway_request_id = f"gw-{uuid.uuid4()}"
        request.state.request_id = request_id
        request.state.gateway_request_id = gateway_request_id
        bind_request_id(self._log_safe_request_id(request, request_id), gateway_request_id)
        try:
            response = await call_next(request)
        finally:
            clear_log_context()
        response.headers[self._header_name] = request_id
        response.headers[SLAIF_DIAGNOSTIC_ID_HEADER] = gateway_request_id
        return response

    def _log_safe_request_id(self, request: Request, request_id: str) -> str | None:
        """Alias-mask the client request ID for the LOG binding only.

        A client may copy an incoming credential value (cookie, X-API-Key,
        proxy Bearer, ...) into the request-ID header.  ``redact_text``
        masks known secret SHAPES only, so an opaque aliased credential
        would otherwise reach structured logs verbatim.  The pure alias
        masker is built from this request's headers/query (no body); the
        masked value is bound for logging only.  When secret discovery is
        incomplete the client ID is omitted from the log binding entirely
        (fail closed).  The wire response header and request state keep
        the original value for correlation, and no auth/admission decision
        is affected.
        """
        try:
            accepted = self._settings.get_gateway_key_accepted_prefixes()
        except Exception:  # noqa: BLE001 - fall back to the single default prefix
            accepted = (self._settings.GATEWAY_KEY_PREFIX,)
        try:
            masker, complete = build_client_id_masker(
                request.scope, accepted_prefixes=tuple(accepted)
            )
            if not complete:
                return None  # discovery incomplete: fail closed, omit binding
            if masker is None:
                return request_id  # no incoming secrets to alias
            masked = masker(request_id.encode("latin-1", "replace")).decode(
                "latin-1", "replace"
            )
        except Exception:  # noqa: BLE001 - observability must never affect the request
            return None  # any fault in masking: omit the binding, never 500
        return masked if masked != request_id else request_id


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record basic HTTP request count and duration metrics."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            observe_http_request(
                method=request.method,
                endpoint=_endpoint_label(request),
                status_code=500,
                duration_seconds=time.perf_counter() - start,
            )
            raise

        observe_http_request(
            method=request.method,
            endpoint=_endpoint_label(request),
            status_code=response.status_code,
            duration_seconds=time.perf_counter() - start,
        )
        return response


def _safe_request_id(value: str | None) -> str:
    if value and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return f"req-{uuid.uuid4()}"


def _endpoint_label(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path
    return request.url.path if request.url.path in {"/healthz", "/readyz", "/metrics"} else "unmatched"

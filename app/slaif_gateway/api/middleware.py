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

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a safe request ID to request state, logs, and response headers."""

    def __init__(self, app, *, settings: Settings) -> None:
        super().__init__(app)
        self._header_name = settings.REQUEST_ID_HEADER

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _safe_request_id(request.headers.get(self._header_name))
        request.state.request_id = request_id
        request.state.gateway_request_id = f"gw-{uuid.uuid4()}"
        bind_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            clear_log_context()
        response.headers[self._header_name] = request_id
        return response


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

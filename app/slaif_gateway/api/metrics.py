"""Prometheus metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

from slaif_gateway.config import Settings
from slaif_gateway.metrics import prometheus_content_type, prometheus_response_body

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    settings: Settings | None = getattr(request.app.state, "settings", None)
    if settings is None or not settings.ENABLE_METRICS:
        return Response(status_code=404)

    if settings.metrics_require_auth() and not _client_ip_allowed(request, settings):
        return PlainTextResponse("metrics access denied\n", status_code=403)

    return Response(
        content=prometheus_response_body(),
        media_type=prometheus_content_type(),
    )


def _client_ip_allowed(request: Request, settings: Settings) -> bool:
    allowed_ips = set(settings.get_metrics_allowed_ips())
    if not allowed_ips:
        return False
    client = request.client
    return client is not None and client.host in allowed_ips

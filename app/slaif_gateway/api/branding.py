"""Fixed public operator-branding asset routes (187-a).

These routes serve the five fixed branding slots before login, so existing
Nginx ``/admin`` proxy rules work unchanged. Route paths are registered fixed
literals — never request-selected file names, paths, or listing. Each
endpoint is total: it serves the currently valid override bytes, or the
packaged fallback (empty stylesheet for the CSS slot, the packaged logo for
image slots), so a page never references a broken subresource even when a
file disappears between render and request.

The branding directory value is read from this application instance's
``request.app.state.settings`` on every request; requesting an asset grants
no authentication rights and performs no session or state writes.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import Response

from slaif_gateway.web.branding import (
    STYLE_CSS,
    fallback_asset,
    resolve_slot,
)

router = APIRouter(prefix="/admin/branding", include_in_schema=False)

_RESPONSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Content-Type-Options": "nosniff",
}


def _branding_dir(request: Request) -> str | None:
    value = getattr(request.app.state.settings, "SLAIF_BRANDING_DIR", None)
    return value if isinstance(value, str) else None


def _serve(request: Request, slot: str) -> Response:
    resolved = resolve_slot(slot, _branding_dir(request))
    if resolved is not None:
        return Response(
            resolved.data,
            headers={**_RESPONSE_HEADERS, "Content-Type": resolved.content_type},
        )
    data, content_type = fallback_asset(slot)
    return Response(
        data,
        headers={**_RESPONSE_HEADERS, "Content-Type": content_type},
    )


@router.get("/style.css")
def branding_style_css(request: Request) -> Response:
    return _serve(request, STYLE_CSS)


@router.get("/logo")
def branding_logo(request: Request) -> Response:
    return _serve(request, "logo")


@router.get("/logo-compact")
def branding_logo_compact(request: Request) -> Response:
    return _serve(request, "logo-compact")


@router.get("/favicon")
def branding_favicon(request: Request) -> Response:
    return _serve(request, "favicon")


@router.get("/hero")
def branding_hero(request: Request) -> Response:
    return _serve(request, "hero")

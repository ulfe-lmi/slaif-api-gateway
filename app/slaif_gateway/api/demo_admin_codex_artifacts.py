"""Demo-host inert Codex profile reference attachments (224-w).

The standalone demo process admits the exact one finite artifact
family over the visitor's verified per-login SELECT-only copy:

* ``GET /admin/routes/{uuid}/codex-profile/base``
* ``GET /admin/routes/{uuid}/codex-profile/profile``
* ``GET /admin/routes/{uuid}/codex-profile/catalog``

The central demo gate admits ONLY these exact shapes (one finite
artifact vocabulary, not arbitrary names) and keeps every unsafe
method the pre-body quiet 204 cut.

Read law: ONE request-local SELECT-only transaction on the gate-bound
engine with the independent ``current_database()`` /
``transaction_read_only`` recheck; the route must exist in THIS copy
and be eligible under the SAME pure copy-bound qualification
inspection the normal route detail uses (``CodexQualificationService``
over the request-local copy session - copied route/provider/pricing
facts only), else a safe 404.

The demo host cannot forward ``/v1``, so the normal live
``PUBLIC_BASE_URL`` is NEVER used to emit a runnable profile. For an
eligible copied route the SAME pure renderer over the FINITE packaged
profile data is called with the reserved non-routable placeholder URL
``https://api.slaif.invalid/v1``: the three attachments are clearly
labeled INERT references (``.reference`` filenames), contain no
bearer, no real source host, no provider credential, and point to no
usable endpoint. Every response - including fixed refusals - is
private no-store and nosniff. A failed render (unknown/unsupported
profile id) is a safe 404.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import (
    ProviderConfigsRepository,
)
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services.codex_qualification import (
    CodexQualificationService,
    render_codex_profile,
)

router = APIRouter(include_in_schema=False)

# The reserved non-routable placeholder accepted by the SAME gateway
# base-URL validator the normal renderer uses (no real source host is
# ever read from the demo process settings).
_DEMO_INERT_BASE_URL = "https://api.slaif.invalid/v1"

_SAFE_NOT_FOUND = "Not Found"
_SAFE_UNAVAILABLE = (
    "The Codex profile artifact is unavailable for this demo session."
)


def _not_found() -> Response:
    return HTMLResponse(
        _SAFE_NOT_FOUND, status_code=404, headers={"Cache-Control": "private, no-store"}
    )


def _unavailable() -> Response:
    return HTMLResponse(
        _SAFE_UNAVAILABLE, status_code=503, headers={"Cache-Control": "private, no-store"}
    )


def _no_query(request: Request) -> bool:
    return not request.query_params.multi_items()


def _inert_filename(name: str) -> str:
    """Insert the ``.reference`` inert marker before the final
    extension (no extension: append it)."""
    if "." not in name.rsplit("/", 1)[-1]:
        return name + ".reference"
    stem, dot, ext = name.rpartition(".")
    return f"{stem}.reference.{ext}"


def _artifact_response(body: bytes, media_type: str, filename: str) -> Response:
    response = Response(body, media_type=media_type)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = (
        "private, no-store, no-cache, must-revalidate"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


async def _copy_recheck(session: Any, target_db: str) -> bool:
    current = await session.scalar(text("SELECT current_database()"))
    read_only = await session.scalar(text("SHOW transaction_read_only"))
    return current == target_db and read_only == "on"


@router.get("/admin/routes/{route_id}/codex-profile/{artifact_name}")
async def demo_codex_profile_artifact(
    request: Request, route_id: str, artifact_name: str
) -> Response:
    """224-w: the ONE finite inert reference attachment family for a
    copied eligible route (base / profile / catalog where present)."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or not _no_query(request):
        return _not_found()
    if artifact_name not in ("base", "profile", "catalog"):
        return _not_found()
    try:
        parsed_route_id = _uuid.UUID(route_id)
    except ValueError:
        return _not_found()

    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _unavailable()
    profile_id: str | None = None
    try:
        async with session_factory() as session, session.begin():
            if not await _copy_recheck(session, demo.target_db):
                return _unavailable()
            route = await ModelRoutesRepository(session).get_model_route_by_id(
                parsed_route_id
            )
            if route is None:
                return _not_found()
            # Copied-fact eligibility: the SAME pure, copy-bound
            # qualification inspection the normal route detail uses
            # (bounded SELECTs on this session's copy only).
            results = await CodexQualificationService(
                provider_configs_repository=ProviderConfigsRepository(session),
                model_routes_repository=ModelRoutesRepository(session),
                pricing_rules_repository=PricingRulesRepository(session),
                fx_rates_repository=FxRatesRepository(session),
            ).inspect()
            for result in results:
                if result.route_id == parsed_route_id:
                    if result.ready and result.profile_id:
                        profile_id = result.profile_id
                    break
    except Exception:  # noqa: BLE001 - unavailable, never ambient
        return _unavailable()
    if profile_id is None:
        return _not_found()

    try:
        artifacts = render_codex_profile(_DEMO_INERT_BASE_URL, profile_id)
    except ValueError:
        return _not_found()

    if artifact_name == "base":
        return _artifact_response(
            artifacts.base_config_toml.encode("utf-8"),
            "text/plain",
            _inert_filename("codex-provider.config.toml"),
        )
    if artifact_name == "profile":
        return _artifact_response(
            artifacts.profile_config_toml.encode("utf-8"),
            "text/plain",
            _inert_filename(f"{artifacts.profile}.config.toml"),
        )
    if artifacts.model_catalog_json is None:
        return _not_found()
    return _artifact_response(
        artifacts.model_catalog_json.encode("utf-8"),
        "application/json",
        _inert_filename(artifacts.model_catalog_target),
    )

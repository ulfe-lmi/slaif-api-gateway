"""Demo-host key JSON attachments (224-w).

The standalone demo process admits the exact two attachment GETs over
the visitor's verified per-login SELECT-only copy:

* ``GET /admin/keys/{uuid}/calibration/summary.json`` with the bounded
  positive query law (``start_at`` / ``end_at`` / ``multiplier``);
* ``GET /admin/keys/{uuid}/configuration.json`` (query-free).

The central demo gate admits ONLY these exact shapes and keeps every
unsafe method the pre-body quiet 204 cut.

Read law: ONE request-local SELECT-only transaction on the gate-bound
engine with the independent ``current_database()`` /
``transaction_read_only`` recheck.

The calibration summary is produced by the PROVEN read-only normal
service, bound to the request-local copy session (the key must exist
in THIS copy, fixed 404 otherwise; no ambient ``get_settings()``
read): the SAME strict input validation
(``_parse_admin_datetime`` / ``_parse_required_admin_decimal``) as
the normal download (the normal selector's default multiplier 3
applies when the parameter is absent), recalculated over the FROZEN
copied usage rows (copied-data recalculation, never live current
usage).

The configuration download is SAFELY UNAVAILABLE in this demo
(224-x): the 222/224-r sanitizer maps ``gateway_keys.metadata`` to
KR, retaining only the projected clone receipt and DISCARDING the
ordinary policy metadata (allowed providers, Responses, throttling,
streaming-burn and external-tool policies). Rendering the normal
version-1 document on the stripped copy plus the demo process's
neutral settings would fabricate defaults or wrong operator ceilings
for a nondefault source key, so the exact GET performs NO copy read
and returns a fixed safe 503 with NO JSON - no source fallback, no
raw metadata passthrough, no default guessing. A later same-PR order
may implement a verified policy projection.

Whole-output refusal: when ANY nested canonical string of the
serialized artifact is a known incoming authentication alias or
recognized complete credential material (the same pure request-aware
classifier as the normal calibration export), the WHOLE output is
refused with a fixed safe error - no partial secret substitution, no
echo of the refused value. A finite 1 MiB output ceiling refuses
oversize output explicitly (never truncated). Both attachments are
private no-store/no-cache and nosniff with the attachment disposition.
Corrupt or unavailable copy binding is the fixed safe 503.
"""

from __future__ import annotations

import json
import uuid as _uuid
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from slaif_gateway.api.admin import (
    _admin_configuration_json_default,
    _calibration_payload_has_known_secret_alias,
    _parse_admin_datetime,
    _parse_required_admin_decimal,
)
from slaif_gateway.api.admin_compatibility import _is_known_alias
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.usage_profiles import UsageProfilesRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services.calibration_summary_service import (
    CalibrationSummaryError,
    CalibrationSummaryService,
)

router = APIRouter(include_in_schema=False)

# 219-b finite local ceiling (1 MiB), preserved for BOTH demo
# attachments (never truncate and label it complete).
_MAX_ATTACHMENT_BYTES = 1024 * 1024

_SAFE_NOT_FOUND = "Not Found"
_SAFE_UNAVAILABLE = (
    "The key download is unavailable for this demo session."
)
_SAFE_REFUSAL = (
    "The download was refused: it contains a value matching a known "
    "incoming authentication value. Review the affected record before "
    "exporting."
)
_SAFE_INPUT_REFUSAL = "The download input was invalid."
_SAFE_OVERSIZED = (
    "The download exceeds the 1 MiB export limit."
)


_ATTACHMENT_REFUSAL_HEADERS = {
    # The order's wire law for EVERY attachment response (success and
    # refusal): private no-store (the central gate normalizes every
    # admitted dynamic response to exactly this one header) plus
    # nosniff.
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}


def _not_found() -> Response:
    return HTMLResponse(_SAFE_NOT_FOUND, status_code=404,
                        headers=dict(_ATTACHMENT_REFUSAL_HEADERS))


def _unavailable() -> Response:
    return HTMLResponse(_SAFE_UNAVAILABLE, status_code=503,
                        headers=dict(_ATTACHMENT_REFUSAL_HEADERS))


def _refusal(message: str, status_code: int) -> Response:
    return HTMLResponse(
        message,
        status_code=status_code,
        headers=dict(_ATTACHMENT_REFUSAL_HEADERS),
    )


def _attachment_headers(response: Response, filename: str) -> None:
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = (
        "private, no-store, no-cache, must-revalidate"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"


def _no_query(request: Request) -> bool:
    return not request.query_params.multi_items()


async def _copy_recheck(session: Any, target_db: str) -> bool:
    current = await session.scalar(text("SELECT current_database()"))
    read_only = await session.scalar(text("SHOW transaction_read_only"))
    return current == target_db and read_only == "on"


def _accepted_prefixes(request: Request) -> tuple[str, ...]:
    """The demo app's FIXED neutral accepted-prefix tuple (never the
    ambient process settings)."""
    settings = request.app.state.settings
    return tuple(settings.get_gateway_key_accepted_prefixes())


@router.get("/admin/keys/{key_id}/calibration/summary.json")
async def demo_key_calibration_summary(
    request: Request, key_id: str
) -> Response:
    """224-w: the bounded calibration summary over FROZEN copied
    usage (copied-data recalculation), same service and strict input
    validation as the normal download, whole-output alias refusal,
    1 MiB ceiling, private no-store nosniff attachment."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _not_found()
    try:
        parsed_key_id = _uuid.UUID(key_id)
    except ValueError:
        return _not_found()
    if _is_known_alias(request, key_id):
        return _refusal(_SAFE_REFUSAL, 400)
    # The gate already enforced the bounded positive query law; read
    # the (admitted) values for the strict normal parsers.
    params = request.query_params
    start_at = params.get("start_at") or ""
    end_at = params.get("end_at") or ""
    # The normal selector's DEFAULT multiplier 3 applies when the
    # parameter is ABSENT (an explicit empty value is refused by the
    # gate law; the branch below is defense in depth).
    _multiplier_raw = params.get("multiplier")
    if _multiplier_raw is None:
        multiplier = "3"
    elif _multiplier_raw == "":
        return _refusal(_SAFE_INPUT_REFUSAL, 400)
    else:
        multiplier = _multiplier_raw

    # Strict normal input validation BEFORE any copy query.
    try:
        parsed_start_at = _parse_admin_datetime(start_at)
        parsed_end_at = _parse_admin_datetime(end_at)
        parsed_multiplier = _parse_required_admin_decimal(
            multiplier, field_name="multiplier"
        )
    except (CalibrationSummaryError, ValueError):
        return _refusal(_SAFE_INPUT_REFUSAL, 400)

    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _unavailable()
    payload: dict[str, Any] | None = None
    try:
        async with session_factory() as session, session.begin():
            if not await _copy_recheck(session, demo.target_db):
                return _unavailable()
            key = await GatewayKeysRepository(session).get_gateway_key_by_id(
                parsed_key_id
            )
            if key is None:
                return _not_found()
            # The PROVEN read-only service, bound to THIS request-local
            # copy session (no second session, no settings dependency).
            service = CalibrationSummaryService(
                gateway_keys_repository=GatewayKeysRepository(session),
                usage_profiles_repository=UsageProfilesRepository(session),
            )
            result = await service.summarize_calibration_key_usage(
                gateway_key_id=parsed_key_id,
                start_at=parsed_start_at,
                end_at=parsed_end_at,
                multiplier=parsed_multiplier,
            )
            payload = asdict(result)
    except (CalibrationSummaryError, ValueError):
        return _refusal(_SAFE_INPUT_REFUSAL, 400)
    except Exception:  # noqa: BLE001 - unavailable, never ambient
        return _unavailable()

    # Whole-output refusal (no partial substitution, no echo).
    if _calibration_payload_has_known_secret_alias(
        payload, scope=request.scope, accepted_prefixes=_accepted_prefixes(request)
    ):
        return _refusal(_SAFE_REFUSAL, 400)

    content = (
        json.dumps(
            payload, indent=2, sort_keys=True,
            default=_admin_configuration_json_default,
        )
        + "\n"
    )
    if len(content.encode("utf-8")) > _MAX_ATTACHMENT_BYTES:
        return _refusal(_SAFE_OVERSIZED, 400)
    response = Response(content=content, media_type="application/json")
    _attachment_headers(
        response, f"slaif-calibration-summary-{parsed_key_id}.json"
    )
    return response


@router.get("/admin/keys/{key_id}/configuration.json")
async def demo_key_configuration(request: Request, key_id: str) -> Response:
    """224-x: SAFELY UNAVAILABLE - fixed safe 503, NO JSON.

    The 222/224-r sanitizer maps ``gateway_keys.metadata`` to KR,
    discarding the ordinary policy metadata (allowed providers,
    Responses, throttling, streaming-burn and external-tool
    policies); the normal version-1 renderer on the stripped copy
    plus the demo process's neutral settings would fabricate
    defaults or wrong operator ceilings for a nondefault source
    key. Until a separately verified policy projection exists, this
    exact GET performs NO copy read and returns the fixed safe 503
    with no JSON, no source fallback, no raw metadata passthrough
    and no default guessing. The basic shape laws (demo state,
    query-free, canonical UUID, path-identity alias refusal before
    any binding) are unchanged; every response carries the
    attachment refusal headers (private no-store + nosniff).
    """
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _not_found()
    if not _no_query(request):
        return _not_found()
    try:
        _uuid.UUID(key_id)
    except ValueError:
        return _not_found()
    if _is_known_alias(request, key_id):
        return _refusal(_SAFE_REFUSAL, 400)
    return _unavailable()

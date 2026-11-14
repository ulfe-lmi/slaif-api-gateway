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
``transaction_read_only`` recheck; the key must exist in THIS copy
(fixed 404 otherwise). Both documents are produced by the PROVEN
read-only normal rendering services, bound to the request-local copy
session and the demo app's fixed neutral settings (no ambient
``get_settings()`` read):

* configuration: the SAME allowlisted strict version-1 document the
  CLI renders for the exact copied key (``render_key_configuration_
  document``; no key material, provider credential, raw metadata,
  replay token, source ID or copy locator);
* calibration: the SAME service and the SAME strict input validation
  (``_parse_admin_datetime`` / ``_parse_required_admin_decimal``) as
  the normal download, recalculated over the FROZEN copied usage rows
  (copied-data recalculation, never live current usage).

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
from slaif_gateway.services.key_service import (
    KeyConfigurationExportError,
    KeyService,
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


def _not_found() -> Response:
    return HTMLResponse(
        _SAFE_NOT_FOUND, status_code=404, headers={"Cache-Control": "private, no-store"}
    )


def _unavailable() -> Response:
    return HTMLResponse(
        _SAFE_UNAVAILABLE, status_code=503, headers={"Cache-Control": "private, no-store"}
    )


def _refusal(message: str, status_code: int) -> Response:
    return HTMLResponse(
        message,
        status_code=status_code,
        headers={"Cache-Control": "private, no-store"},
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
    multiplier = params.get("multiplier") or ""

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
    """224-w: the allowlisted strict version-1 configuration document
    for the EXACT copied key (same canonical render as the normal
    export), whole-output alias refusal, 1 MiB ceiling, private
    no-store nosniff attachment."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _not_found()
    if not _no_query(request):
        return _not_found()
    try:
        parsed_key_id = _uuid.UUID(key_id)
    except ValueError:
        return _not_found()
    if _is_known_alias(request, key_id):
        return _refusal(_SAFE_REFUSAL, 400)

    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _unavailable()
    document: dict[str, Any] | None = None
    try:
        async with session_factory() as session, session.begin():
            if not await _copy_recheck(session, demo.target_db):
                return _unavailable()
            key = await GatewayKeysRepository(session).get_gateway_key_by_id(
                parsed_key_id
            )
            if key is None:
                return _not_found()
            # The PROVEN pure read-only renderer on the SAME copied
            # key state (the demo app's fixed neutral settings; the
            # render path never touches the unused service seams).
            service = KeyService(
                settings=request.app.state.settings,
                gateway_keys_repository=GatewayKeysRepository(session),
                one_time_secrets_repository=None,
                audit_repository=None,
            )
            document = service.render_key_configuration_document(key)
    except (KeyConfigurationExportError, ValueError):
        # Malformed/unsupported stored policy in the copy: one fixed
        # safe refusal, never an ambient fallback, no echo.
        return _refusal(_SAFE_UNAVAILABLE, 503)
    except Exception:  # noqa: BLE001 - unavailable, never ambient
        return _unavailable()

    if _calibration_payload_has_known_secret_alias(
        document, scope=request.scope, accepted_prefixes=_accepted_prefixes(request)
    ):
        return _refusal(_SAFE_REFUSAL, 400)

    content = (
        json.dumps(
            document, indent=2, sort_keys=True,
            default=_admin_configuration_json_default,
        )
        + "\n"
    )
    if len(content.encode("utf-8")) > _MAX_ATTACHMENT_BYTES:
        return _refusal(_SAFE_OVERSIZED, 400)
    response = Response(content=content, media_type="application/json")
    _attachment_headers(
        response, f"slaif-key-configuration-{key.public_key_id}.json"
    )
    return response

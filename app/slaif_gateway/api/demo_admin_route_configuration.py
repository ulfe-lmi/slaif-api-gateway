"""Demo-host read-only route configuration form (224-w).

The standalone demo process admits the exact one GET shape over the
visitor's verified per-login SELECT-only copy:

* ``GET /admin/routes/{uuid}/configuration`` (query-free).

The central demo gate admits ONLY this exact shape and keeps every
unsafe method - including the normal plan/apply POSTs - the pre-body
quiet 204 cut.

Read law: ONE request-local SELECT-only transaction on the gate-bound
engine with the independent ``current_database()`` /
``transaction_read_only`` recheck. The route and the four
database-backed choice families (provider, requested model, upstream
model, endpoint) are loaded from THIS copy with the same bounded
read-only choice law as the normal form (``load_choices`` on the
request-local copy session). The optional operator completion choices
come ONLY from the 223-verified sanitized
``profiles/completion-choices.json`` display leaf - metadata first
(kind/size/digest/actual-length), the bounded body re-asserting every
condition as bound parameters, exact length + SHA256, and the typed
verifier law; there is NO live ``COMPLETION_SERVICE_PROFILE_DIR`` or
operator-directory fallback in the demo process: the operator
directory is source state, and reading it (or the demo process's own
copy of the setting) would be an ambient read. An absent leaf means
the source deployment recorded no operator completion profiles, and
the picker then shows the FINITE PACKAGED defaults - the same
package-only bundled profile data the normal form offers when the
operator directory is absent (an honest finite list, never an empty
picker labeled "package defaults"); a corrupt leaf is the fixed safe
503. No provider network or source file read. Captured choice IDs
and the copied selected ID that match a known incoming
authentication alias are withheld (no echo, no link, the same pure
request-aware classifier as the other demo surfaces). The existing
form, field hints and visible action controls are kept with a
persistent frozen/no-op cue.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid as _uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from slaif_gateway.api.admin import templates
from slaif_gateway.api.admin_provider_route_configuration import (
    _CHAT_FLAG_FIELDS,
    _CODEX_LEAF_FIELDS,
    _MEDIA_LEAF_FIELDS,
    _RESPONSES_FLAG_FIELDS,
    _default_route_config_form,
)
from slaif_gateway.api.admin import (
    _admin_redact_key_form_values,
    _choice_selected_labels,
)
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services import demo_snapshot_files as dsf
from slaif_gateway.services.admin_record_choices import (
    RecordChoice,
    load_choices,
)
from slaif_gateway.services.request_diagnostics import (
    is_known_incoming_secret_alias,
)

router = APIRouter(include_in_schema=False)

# The 223 capture's completion-choices leaf (metadata-first law).
_COMPLETION_CHOICES_NAME = "profiles/completion-choices.json"
_MAX_COMPLETION_CHOICES_BYTES = dsf._COMPLETION_PROFILE_MAX_BYTES
_MAX_COMPLETION_CHOICES_COUNT = dsf._COMPLETION_PROFILE_MAX_COUNT
_MAX_CAPTURE_AT = 253_402_300_800.0
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")

_SAFE_NOT_FOUND = "Not Found"
_SAFE_UNAVAILABLE = (
    "The route configuration page is unavailable for this demo session."
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


async def _copy_recheck(session: Any, target_db: str) -> bool:
    current = await session.scalar(text("SELECT current_database()"))
    read_only = await session.scalar(text("SHOW transaction_read_only"))
    return current == target_db and read_only == "on"


async def _completion_choices_from_leaf(
    session: Any,
) -> tuple[list[RecordChoice], bool]:
    """The sanitized operator completion choices, or the unconfigured
    state. ``(choices, unconfigured)``; raises on a corrupt configured
    leaf (the caller returns the fixed safe 503)."""
    meta = (
        await session.execute(
            text(
                "SELECT kind, byte_count, sha256, captured_at, "
                "octet_length(body) AS actual_bytes "
                "FROM demo_display.leaves "
                "WHERE logical_name = :name"
            ),
            {"name": _COMPLETION_CHOICES_NAME},
        )
    ).first()
    if meta is None:
        # Absent leaf: the source deployment recorded no operator
        # completion profiles (the 223 capture emits the leaf only for
        # a configured directory).
        return [], True
    kind, byte_count, stored_sha, captured_at, actual_bytes = meta
    if (
        kind != dsf.KIND_COMPLETION_CHOICES
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or not 0 <= byte_count <= _MAX_COMPLETION_CHOICES_BYTES
        or not isinstance(stored_sha, str)
        or _SHA256_HEX.fullmatch(stored_sha) is None
        or isinstance(actual_bytes, bool)
        or not isinstance(actual_bytes, int)
        or not 0 <= actual_bytes <= _MAX_COMPLETION_CHOICES_BYTES
        or actual_bytes != byte_count
        or isinstance(captured_at, bool)
        or not isinstance(captured_at, (int, float))
        or not math.isfinite(float(captured_at))
        or not 0 <= float(captured_at) < _MAX_CAPTURE_AT
    ):
        raise ValueError("corrupt completion choices leaf")
    body_row = (
        await session.execute(
            text(
                "SELECT body FROM demo_display.leaves "
                "WHERE logical_name = :name "
                "AND octet_length(body) <= :cap "
                "AND byte_count = :size "
                "AND sha256 = :digest "
                "AND kind = :kind"
            ),
            {
                "name": _COMPLETION_CHOICES_NAME,
                "cap": _MAX_COMPLETION_CHOICES_BYTES,
                "size": byte_count,
                "digest": stored_sha,
                "kind": dsf.KIND_COMPLETION_CHOICES,
            },
        )
    ).first()
    if body_row is None:
        raise ValueError("corrupt completion choices leaf")
    body = bytes(body_row[0])
    if len(body) != byte_count or (
        hashlib.sha256(body).hexdigest() != stored_sha
    ):
        raise ValueError("corrupt completion choices leaf")
    dsf._verify_json_policy(dsf.KIND_COMPLETION_CHOICES, body)
    document = json.loads(body.decode("utf-8"))
    profiles = document["profiles"]
    if (
        not isinstance(profiles, list)
        or len(profiles) > _MAX_COMPLETION_CHOICES_COUNT
    ):
        raise ValueError("corrupt completion choices leaf")
    return [
        RecordChoice(id=str(p), label=str(p), sub="sanitized capture")
        for p in profiles
    ], False


@router.get("/admin/routes/{route_id}/configuration", response_class=HTMLResponse)
async def demo_route_configuration_form(
    request: Request, route_id: str
) -> Response:
    """224-w: the demo route configuration form (query-free,
    gate-admitted): copied route + copy-backed choices, completion
    choices only from the sanitized leaf, persistent frozen/no-op
    cue, no provider network or source file read."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or not _no_query(request):
        return _not_found()
    try:
        parsed_route_id = _uuid.UUID(route_id)
    except ValueError:
        return _not_found()

    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return _unavailable()
    try:
        async with session_factory() as session, session.begin():
            if not await _copy_recheck(session, demo.target_db):
                return _unavailable()
            route = await ModelRoutesRepository(session).get_model_route_by_id(
                parsed_route_id
            )
            if route is None:
                return _not_found()
            form = _default_route_config_form(route)
            settings = request.app.state.settings
            accepted = tuple(settings.get_gateway_key_accepted_prefixes())
            choices: dict[str, list[RecordChoice]] = {}
            for field_name, kind in (
                ("provider", "provider"),
                ("requested_model", "model"),
                ("upstream_model", "model"),
                ("endpoint", "endpoint"),
            ):
                choices[field_name] = await load_choices(
                    session,
                    kind,
                    selected=(form.get(field_name),)
                    if form.get(field_name)
                    else (),
                    accepted_prefixes=accepted,
                )
            completion, unconfigured = await _completion_choices_from_leaf(
                session
            )
            if unconfigured:
                # 224-x: the source recorded no operator completion
                # profiles. Show the FINITE PACKAGED defaults - the
                # same package-only bundled profile data the normal
                # form offers when the operator directory is absent.
                # The demo process's OWN settings are never consulted
                # (profile_dir is pinned to the bundled package
                # data), and the honest empty state (a package with
                # no bundled profiles) is rendered as no choices.
                completion = list(
                    await load_choices(
                        session,
                        "completion_profile",
                        selected=(),
                        profile_dir="",
                    )
                )
            # Hydrate the copied selected completion id (it was
            # sanitizer-remapped, so it is a closed fictional id).
            selected_completion = form.get("completion_profile") or None
            if selected_completion and selected_completion not in [
                c.id for c in completion
            ]:
                completion = [
                    RecordChoice(
                        id=selected_completion,
                        label=selected_completion,
                        sub="sanitized capture",
                    )
                ] + completion
            choices["completion_profile"] = completion
    except ValueError:
        # A corrupt CONFIGURED completion leaf is one fixed safe 503.
        return _unavailable()
    except Exception:  # noqa: BLE001 - unavailable, never ambient
        return _unavailable()

    # 224-x: output-side known-incoming-alias withholding for the
    # captured completion-profile choice IDs (and their labels) and
    # the copied selected ID: a captured ID equal to a known incoming
    # authentication alias must not be echoed or linked (the same
    # pure request-aware classifier as the other demo surfaces; the
    # demo app's fixed neutral prefix tuple, never ambient settings;
    # fail closed on a classifier error or an unusable tuple).
    try:
        _alias_prefixes = tuple(
            request.app.state.settings.get_gateway_key_accepted_prefixes()
        )
        if not all(isinstance(x, str) for x in _alias_prefixes):
            _alias_prefixes = None
    except Exception:
        _alias_prefixes = None

    def _is_alias(value: object) -> bool:
        if not isinstance(value, str) or not value:
            return False
        if _alias_prefixes is None:
            return True  # fail closed: the classifier cannot be proven safe
        try:
            return is_known_incoming_secret_alias(
                value, scope=request.scope, accepted_prefixes=_alias_prefixes
            )
        except Exception:  # noqa: BLE001 - fail closed, no echo
            return True

    # 224-y review cleanup: the local was reassigned but never read;
    # the withholding effect is the form mutation below (behavior
    # unchanged).
    _completion_selected = form.get("completion_profile") or None
    if _completion_selected is not None and _is_alias(_completion_selected):
        form["completion_profile"] = ""  # no pre-selected withheld value
    choices["completion_profile"] = [
        c
        for c in choices["completion_profile"]
        if not _is_alias(c.id) and not _is_alias(c.label)
    ]

    choice_labels = _choice_selected_labels(
        choices,
        (
            ("provider", form.get("provider")),
            ("requested_model", form.get("requested_model")),
            ("upstream_model", form.get("upstream_model")),
            ("endpoint", form.get("endpoint")),
            ("completion_profile", form.get("completion_profile")),
        ),
    )
    response = templates.TemplateResponse(
        request,
        "routes/configuration_form.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "route_id": str(parsed_route_id),
            "route": route,
            "form": _admin_redact_key_form_values(form, settings),
            "choices": choices,
            "choice_labels": choice_labels,
            "error": None,
            "codex_leaf_fields": _CODEX_LEAF_FIELDS,
            "media_leaf_fields": _MEDIA_LEAF_FIELDS,
            "chat_flag_fields": _CHAT_FLAG_FIELDS,
            "responses_flag_fields": _RESPONSES_FLAG_FIELDS,
            "demo_admin": True,
            "demo_completion_unconfigured": unconfigured,
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response

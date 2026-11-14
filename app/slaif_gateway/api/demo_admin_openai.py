"""Objective 224-y: demo-only OpenAI-assisted read pages.

A small, purpose-built router mounted by ``create_demo_app`` ONLY,
and BEFORE the core admin router, so the three EXACT query-free GET
shapes ``/admin/openai-assisted``, ``/admin/openai-assisted/pricing``
and ``/admin/openai-assisted/routes`` are served by these handlers
in the demo process while the normal live-Settings handlers are
never reached for those paths there. Every proposal POST and every
unsafe method stays the central gate's pre-body quiet 204 cut
(never dispatched, never parsed, never generated).

The pages render the established styled index and forms with
working navigation and COPIED model/currency choices (the bounded
existing ``load_choices`` on the gate's SAME request-local
verified SELECT-only copy, one read-only transaction with the
independent ``current_database()`` / ``transaction_read_only``
recheck). Only the fixed official public source URL constants and
the finite packaged reference defaults are displayed. The 223
process-configuration leaf is numeric-only and does NOT record the
source proposal model, so the default model is labeled a packaged
reference and the source setting is stated as not captured. The
demo template branches replace every normal "this calls OpenAI",
discovery-key-in-use, generated-success or runnable-proposal claim
with truthful frozen/no-call/no-op wording while keeping the
inputs and hints ergonomic. Choices (and nothing else) come from
the copy; known incoming auth aliases are withheld from them. No
live/source ``OPENAI_ASSISTED_CATALOG_MODEL``, discovery key or
environment, ambient settings, provider discovery call, prompt or
result generation ever occurs; the normal admin HTML and behavior
remain byte-identical.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from sqlalchemy import text

from slaif_gateway.api.admin import templates
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services.admin_record_choices import (
    RecordChoice,
    load_choices,
)
from slaif_gateway.services.openai_assisted_catalog import (
    DEFAULT_OPENAI_ASSISTED_MODEL,
    DEFAULT_OPENAI_MODELS_SOURCE_URL,
    DEFAULT_OPENAI_PRICING_SOURCE_URL,
    OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR,
)
from slaif_gateway.services.request_diagnostics import (
    is_known_incoming_secret_alias,
)

router = APIRouter(prefix="/admin/openai-assisted", include_in_schema=False)

_SAFE_UNAVAILABLE = (
    "The OpenAI assisted proposal pages are unavailable for this demo session."
)

# The fixed official public source URL constants (never a live
# discovery or environment read).
_PRICING_SOURCE_URLS = (
    DEFAULT_OPENAI_PRICING_SOURCE_URL,
    DEFAULT_OPENAI_MODELS_SOURCE_URL,
)
_ROUTE_SOURCE_URLS = (DEFAULT_OPENAI_MODELS_SOURCE_URL,)

# Finite packaged reference defaults (the normal form defaults with
# the source proposal-model setting replaced by the packaged
# reference; the 223 process leaf does not capture that setting).
_PRICING_FORM = {
    "source_url": DEFAULT_OPENAI_PRICING_SOURCE_URL,
    "models_source_url": DEFAULT_OPENAI_MODELS_SOURCE_URL,
    "proposal_model": DEFAULT_OPENAI_ASSISTED_MODEL,
    "currency": "USD",
    "endpoint_scope": "chat_completions",
    "include_models": "",
    "exclude_models": "",
    "max_web_calls": "3",
}
_ROUTE_FORM = {
    "source_url": DEFAULT_OPENAI_MODELS_SOURCE_URL,
    "proposal_model": DEFAULT_OPENAI_ASSISTED_MODEL,
    "endpoint_scope": "chat_completions",
    "include_models": "",
    "exclude_models": "",
}


def _unavailable() -> HTMLResponse:
    return HTMLResponse(
        content=(
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<title>SLAIF demo</title></head><body><p>"
            + _SAFE_UNAVAILABLE
            + "</p></body></html>"
        ),
        status_code=503,
        headers={"Cache-Control": "private, no-store"},
    )


def _alias_prefixes(request: Request) -> tuple[str, ...] | None:
    """The demo app's fixed neutral prefix tuple (never ambient)."""
    try:
        prefixes = tuple(
            request.app.state.settings.get_gateway_key_accepted_prefixes()
        )
        if all(isinstance(x, str) for x in prefixes):
            return prefixes
    except Exception:
        pass
    return None


async def _copy_choices(
    request: Request,
    demo: Any,
    kinds: tuple[tuple[str, str], ...],
    prefixes: tuple[str, ...],
) -> dict[str, list[RecordChoice]] | None:
    """Bounded ``load_choices`` on the request-local verified
    SELECT-only copy, one read-only transaction with the
    independent recheck; known incoming auth aliases withheld from
    every choice. ``kinds`` is the closed (field, kind) selector
    list. Any failure is a fixed safe 503 (never an ambient read).
    """
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return None
    out: dict[str, list[RecordChoice]] = {}
    try:
        async with session_factory() as session, session.begin():
            current = await session.scalar(text("SELECT current_database()"))
            read_only = await session.scalar(text("SHOW transaction_read_only"))
            if current != demo.target_db or read_only != "on":
                return None
            for field, kind in kinds:
                choices = await load_choices(
                    session,
                    kind,
                    selected=(),
                    accepted_prefixes=prefixes,
                )
                out[field] = [
                    c
                    for c in choices
                    if not is_known_incoming_secret_alias(
                        c.id, scope=request.scope, accepted_prefixes=prefixes
                    )
                    and not is_known_incoming_secret_alias(
                        c.label, scope=request.scope, accepted_prefixes=prefixes
                    )
                ]
    except Exception:
        # Driver, connection or statement failure: one fixed safe
        # refusal. Cancellation is a BaseException and is not
        # swallowed.
        return None
    return out


def _choice_labels(
    choices: dict[str, list[RecordChoice]], selected: tuple[tuple[str, str], ...]
) -> dict[str, str]:
    labels: dict[str, str] = {}
    for field, value in selected:
        if not value:
            continue
        for c in choices.get(field, ()):  # type: ignore[union-attr]
            if c.id == value:
                labels[field] = c.label
                break
        else:
            labels[field] = value
    return labels


@router.get("", response_class=HTMLResponse)
async def demo_openai_assisted_index(request: Request) -> HTMLResponse:
    """224-y: the demo OpenAI-assisted index (query-free)."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _unavailable()
    response = templates.TemplateResponse(
        request,
        "openai_assisted/index.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "warning": None,
            "source_urls": _PRICING_SOURCE_URLS,
            "route_source_urls": _ROUTE_SOURCE_URLS,
            "api_key_env_var": OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR,
            "proposal_model": DEFAULT_OPENAI_ASSISTED_MODEL,
            "demo_admin": True,
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get("/pricing", response_class=HTMLResponse)
async def demo_openai_assisted_pricing_form(request: Request) -> HTMLResponse:
    """224-y: the demo pricing-proposal form (query-free, no-op)."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _unavailable()
    prefixes = _alias_prefixes(request)
    if prefixes is None:
        return _unavailable()
    choices = await _copy_choices(
        request,
        demo,
        (
            ("proposal_model", "model"),
            ("currency", "currency"),
            ("model", "model"),
        ),
        prefixes,
    )
    if choices is None:
        return _unavailable()
    response = templates.TemplateResponse(
        request,
        "openai_assisted/pricing.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "form": dict(_PRICING_FORM),
            "choices": choices,
            "choice_labels": _choice_labels(
                choices,
                (
                    ("proposal_model", _PRICING_FORM["proposal_model"]),
                    ("currency", _PRICING_FORM["currency"]),
                ),
            ),
            "error": None,
            "diagnostic_id": None,
            "warning": None,
            "api_key_env_var": OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR,
            "source_urls": _PRICING_SOURCE_URLS,
            "demo_admin": True,
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get("/routes", response_class=HTMLResponse)
async def demo_openai_assisted_routes_form(request: Request) -> HTMLResponse:
    """224-y: the demo route-proposal form (query-free, no-op)."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None:
        return _unavailable()
    prefixes = _alias_prefixes(request)
    if prefixes is None:
        return _unavailable()
    choices = await _copy_choices(
        request,
        demo,
        (
            ("proposal_model", "model"),
            ("model", "model"),
        ),
        prefixes,
    )
    if choices is None:
        return _unavailable()
    response = templates.TemplateResponse(
        request,
        "openai_assisted/routes.html",
        {
            "admin": demo.session_context.admin_user,
            "csrf_token": demo.csrf_token,
            "form": dict(_ROUTE_FORM),
            "choices": choices,
            "choice_labels": _choice_labels(
                choices, (("proposal_model", _ROUTE_FORM["proposal_model"]),)
            ),
            "error": None,
            "diagnostic_id": None,
            "warning": None,
            "api_key_env_var": OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR,
            "source_urls": _ROUTE_SOURCE_URLS,
            "demo_admin": True,
        },
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response

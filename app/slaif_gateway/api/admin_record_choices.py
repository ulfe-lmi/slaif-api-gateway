"""Authenticated record-choice lookup for the admin console (192-a).

GET /admin/record-choices?kind=<allowlisted>&q=<bounded>
    [&selected=<id>]{&selected=<id2>}...        # repeatable (multi filters)
    [&provider=<dep>]{&provider=<dep2>}...    # repeatable scope (policy search)
    [&endpoint=<path>]{&endpoint=<path2>}...   # repeatable scope (policy_model)
    [&target_type=<type>]{&target_type=<type2>}]...  # repeatable audit scope

The ``provider``/``endpoint`` parameters are REPEATABLE scopes for the
policy catalog searches: absent = unscoped, present but blank
(``provider=``) = explicitly empty scope (no choices), present with
values = bounded IN scope. A single value keeps the legacy dependent-
picker behavior exactly.

``selected`` and ``target_type`` are repeatable with EXPLICIT bounds
(195-a): at most 100 values per parameter and at most 1024 characters
per value — excess is a predictable 400, never a silent truncation
(the old 8-value cap is gone).

- Requires a valid admin session under the same authentication law as the
  admin pages; unauthenticated clients get the standard 303 login
  redirect, so no option data is ever exposed publicly or cacheably
  (no-store).
- The lookup is strictly non-mutating: the session is validated with
  ``touch=False`` (no ``last_seen_at`` update) and NO new CSRF token is
  issued, so a dropdown search never invalidates the already-rendered
  form's CSRF token and never writes session rows. The handler performs
  no other writes either (no audit, no quota, no accounting).
- ``kind`` must be one of the fixed allowlisted option kinds; anything else
  is a 400 with an OpenAI-shaped JSON error body (no table/column/SQL is
  ever driven by client input).
- ``q`` is length-bounded; at most 100 choices are returned per request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from slaif_gateway.api.admin import (
    _admin_service_scope,
    _clear_session_cookie,
    _settings,
)
from slaif_gateway.services.admin_record_choices import (
    CHOICE_LIMIT,
    QUERY_MAX_LENGTH,
    UnknownChoiceKindError,
    load_choices,
)
from slaif_gateway.services.admin_session_service import (
    AdminSessionContext,
    AdminSessionError,
)
from slaif_gateway.utils.admin_list_filters import MAX_LIST_FILTER_VALUE_LENGTH
from slaif_gateway.db.session import get_sessionmaker_from_app

router = APIRouter(prefix="/admin", include_in_schema=False)

_KINDS: frozenset[str] = frozenset(
    {
        "owner",
        "owner_email",
        "institution",
        "institution_name",
        "cohort",
        "cohort_name",
        "key",
        "key_public_id",
        "provider",
        "model",
        "policy_model",
        "policy_provider",
        "endpoint",
        "currency",
        "fx_source",
        "audit_action",
        "audit_target_type",
        "audit_target",
        "audit_actor",
        "request_id",
        "email_delivery_status",
        "one_time_secret",
        "email_delivery",
        "tool_destination",
        "completion_profile",
    }
)


def _bad_request(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
        content={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "code": "record_choices_bad_request",
            }
        },
    )


# Bounded explicit scope limit: a legitimate multi-selection (up to 100
# providers/endpoints) must never be silently subset. Each value stays
# length-bounded to QUERY_MAX_LENGTH; excess is a predictable client
# error, not a partial scope.
SCOPE_MAX_VALUES = 100

# Repeatable ``selected``/``target_type`` value limit (195-a): a
# legitimate multi-filter selection must never be silently truncated to
# a subset. Each value stays length-bounded to the shared conservative
# per-value bound; excess is a predictable client error, not a partial
# selection (the legacy 8-value cap is gone).
SELECTED_MAX_VALUES = 100


class ScopeParamError(ValueError):
    """More scope values than SCOPE_MAX_VALUES were submitted."""


class SelectedParamError(ValueError):
    """A repeatable id-list parameter violates its documented bounds."""


def _scope_param(values: list[str]) -> tuple[str, ...] | None:
    """Normalize a repeatable scope query parameter.

    Absent (empty list) = no scope. Present with only blank values
    (``provider=``) = EXPLICITLY empty scope (the service returns no
    choices, mirroring the policy selector's client-side filters).
    Present with values = bounded ``IN`` scope (at most SCOPE_MAX_VALUES
    values, each truncated to QUERY_MAX_LENGTH). Submitting more than
    the cap raises ScopeParamError (the handler answers 400) — a valid
    selection is never silently truncated.
    """
    if not values:
        return None
    if len(values) > SCOPE_MAX_VALUES:
        raise ScopeParamError(f"at most {SCOPE_MAX_VALUES} scope values")
    cleaned = tuple(value.strip()[:QUERY_MAX_LENGTH] for value in values)
    return tuple(value for value in cleaned if value)


def _bounded_id_values(values: list[str], *, param: str) -> tuple[str, ...] | None:
    """Normalize a repeatable id-list query parameter (195-a).

    Absent (empty list) = no values. Values are stripped, blank members
    dropped, and de-duplicated preserving first-seen order. Bounds are
    enforced BEFORE any use — a predictable client error, never a silent
    truncation:
    * at most :data:`SELECTED_MAX_VALUES` submitted values;
    * at most :data:`MAX_LIST_FILTER_VALUE_LENGTH` characters per value
      (the same conservative bound the list filters use).
    Messages derive only from the FIXED parameter name and the limits;
    they never echo the submitted values.
    """
    if not values:
        return None
    if len(values) > SELECTED_MAX_VALUES:
        raise SelectedParamError(
            f"{param}: at most {SELECTED_MAX_VALUES} values are accepted."
        )
    for value in values:
        if len(value.strip()) > MAX_LIST_FILTER_VALUE_LENGTH:
            raise SelectedParamError(
                f"{param}: values are limited to "
                f"{MAX_LIST_FILTER_VALUE_LENGTH} characters."
            )
    deduped = tuple(
        dict.fromkeys(value.strip() for value in values if value and value.strip())
    )
    if len(deduped) > SELECTED_MAX_VALUES:
        raise SelectedParamError(
            f"{param}: at most {SELECTED_MAX_VALUES} values are accepted."
        )
    return deduped or None

async def _admin_lookup_context(
    request: Request,
) -> AdminSessionContext | Response:
    """Validate the admin session for a non-mutating lookup.

    Same authentication law as the admin pages, but without side effects:
    ``touch=False`` (no ``last_seen_at`` update) and no CSRF token
    refresh, so repeated dropdown searches never invalidate the
    already-rendered form's CSRF token and never mutate session rows.
    Invalid sessions receive the same 303 login redirect as the pages.
    """
    settings = _settings(request)
    session_token = request.cookies.get(settings.ADMIN_SESSION_COOKIE_NAME)
    if not session_token:
        return RedirectResponse("/admin/login", status_code=303)

    try:
        async with _admin_service_scope(request) as service:
            return await service.validate_admin_session(
                session_token=session_token,
                touch=False,
            )
    except (AdminSessionError, RuntimeError):
        response = RedirectResponse("/admin/login", status_code=303)
        _clear_session_cookie(response, settings)
        return response


@router.get("/record-choices")
async def list_record_choices(
    request: Request,
    kind: Annotated[str, Query(min_length=1, max_length=64)],
    q: Annotated[str | None, Query(max_length=QUERY_MAX_LENGTH)] = None,
    selected: Annotated[list[str], Query()] = [],
    provider: Annotated[list[str], Query(max_length=QUERY_MAX_LENGTH)] = [],
    endpoint: Annotated[list[str], Query(max_length=QUERY_MAX_LENGTH)] = [],
    target_type: Annotated[list[str], Query()] = [],
) -> JSONResponse:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _bad_request("Admin dashboard is disabled.")

    lookup_context = await _admin_lookup_context(request)
    if isinstance(lookup_context, Response):
        return lookup_context  # 303 redirect to login

    if kind not in _KINDS:
        return _bad_request("Unknown record-choices kind.")

    q_value = q.strip() if q and q.strip() else None
    try:
        selected_ids = _bounded_id_values(selected, param="selected")
        target_type_values = _bounded_id_values(target_type, param="target_type")
    except SelectedParamError:
        # Fixed safe message derived only from the constant bounds; the
        # exception text never reaches the client (CodeQL #15).
        return _bad_request(
            f"At most {SELECTED_MAX_VALUES} values of at most "
            f"{MAX_LIST_FILTER_VALUE_LENGTH} characters are accepted "
            "per selected list."
        )
    try:
        provider_values = _scope_param(provider)
        endpoint_values = _scope_param(endpoint)
    except ScopeParamError:
        # Fixed safe message derived only from the constant cap: the
        # exception text never reaches the client (CodeQL #15).
        return _bad_request(
            f"At most {SCOPE_MAX_VALUES} scope values are accepted per parameter."
        )

    session_factory = get_sessionmaker_from_app(request)
    try:
        async with session_factory() as session:
            async with session.begin():
                choices = await load_choices(
                    session,
                    kind,
                    q=q_value,
                    # No selected values = the EMPTY SEQUENCE (the
                    # producer/consumer boundary contract for all kinds);
                    # never None — the service iterates it.
                    selected=selected_ids or (),
                    provider=provider_values,
                    endpoints=endpoint_values,
                    target_type=target_type_values,
                    profile_dir=settings.COMPLETION_SERVICE_PROFILE_DIR,
                )
    except UnknownChoiceKindError:
        return _bad_request("Unknown record-choices kind.")

    return JSONResponse(
        status_code=200,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
        content={
            "kind": kind,
            "q": q_value or "",
            "limit": CHOICE_LIMIT,
            "choices": [{"id": c.id, "label": c.label, "sub": c.sub} for c in choices],
        },
    )

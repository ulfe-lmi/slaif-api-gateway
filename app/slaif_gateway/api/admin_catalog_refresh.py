"""Admin GUI: catalog proposals and the sealed catalog-refresh workflow
(217-a / G15).

Bounded operator workflows on the EXISTING admin shell:

- setup/status for the operator-owned catalog custody (default OFF;
  missing/unsafe configuration renders useful authenticated help and
  dispatches NOTHING - no network, no jobs, no mutation);
- provider-catalog PROPOSALS (proposal-only generation, bridged to the
  existing import previews without automatic import);
- COLLECT (bootstrap versus refresh, live-DB or uploaded exported
  baseline, bounded research choice) and supplied-bundle REVIEW through
  the shared application composition;
- sealed run review/status/verify with the SAME authenticated canonical
  plan rendered safely (never arbitrary inline artifact HTML), verified
  attachment downloads, and explicit read-only cleanup;
- the reviewed APPLY: one closed session-bound review intent, fresh
  existing-superadmin gate per request, and the Core one-transaction
  apply under the SAME held authenticated run context. Apply is a
  synchronous web-layer composition - never a queued read-only job.

The web router never imports the worker module or module-level
celery_app/settings at import time: broker dispatch happens through a
lazy import inside the send handlers only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from typing import Any
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, Request
from starlette.formparsers import MultiPartParser
from starlette.responses import HTMLResponse, Response

from slaif_gateway.api.admin import (
    _admin_action_context,
    _admin_attachment_context,
    _admin_error_page,
    _admin_not_found,
    _admin_page_context,
    _admin_status_message,
    _is_checked,
    _set_no_store_headers,
    _settings,
    templates,
)
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    build_catalog_refresh_review_token,
    verify_catalog_refresh_review_token,
)
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services import admin_catalog_refresh as custody
from slaif_gateway.services.admin_catalog_refresh import (
    CustodyCapacityError,
    CustodyJobError,
    AdminCatalogRefreshError,
    inspect_custody_setup,
)
from slaif_gateway.services.admin_record_choices import load_choices
from slaif_gateway.services.catalog_refresh import execution_identity
from slaif_gateway.services.catalog_refresh.apply import apply_reviewed_run, apply_status
from slaif_gateway.services.catalog_refresh.errors import CatalogRefreshBlockedError
from slaif_gateway.services.catalog_refresh.filesystem import (
    CatalogRefreshSealError,
    load_seal_key_bytes,
)
from slaif_gateway.services.catalog_refresh.sealing import CONTENT_FILES
from slaif_gateway.services.provider_catalog_proposal import (
    OPENROUTER_PACKAGE_ORDER,
    SUPPORTED_ENDPOINT_SCOPES,
)
from slaif_gateway.services.request_diagnostics import is_known_incoming_secret_alias

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", include_in_schema=False)

_BASE = "/admin/operations/catalog"
# Finite multipart ENVELOPE allowance for the canonical review upload:
# the exact per-file caps (8 MiB bundle + 32 MiB baseline) PLUS a
# finite form/overhead headroom so the supported simultaneous maximum
# files are accepted under the scoped nginx 48m allowance. Each
# original per-file cap is re-enforced at the file (never widened).
_REVIEW_UPLOAD_HEADROOM_BYTES = 1 * 1024 * 1024
_REVIEW_UPLOAD_CAP = (
    8 * 1024 * 1024 + 32 * 1024 * 1024 + _REVIEW_UPLOAD_HEADROOM_BYTES
)
_COLLECT_UPLOAD_CAP = 34 * 1024 * 1024
# Bounded review views (no offset contract: a short page never proves
# custody completeness).
_VIEW_LIMIT = 100
# Finite finite-form vocabularies (closed, server-enforced again).
# The endpoint-scope vocabulary is the EXISTING proposal service's supported
# set - the GUI never advertises a scope the generator cannot honor. A
# stable display order plus a drift assertion keep the two in lockstep.
_PROVIDERS = ("openai", "openrouter")
_PROPOSAL_SCOPES = ("openai", "openrouter", "all")
_JOB_ID_RE = re.compile(r"[0-9a-f]{32}")
_CURRENCIES = ("USD", "EUR", "GBP", "CHF")
_ENDPOINT_SCOPES = ("chat_completions", "responses")
assert set(_ENDPOINT_SCOPES) == set(SUPPORTED_ENDPOINT_SCOPES)
# 217-a: apply-preview token TTL (the shared closed intent bound).
_APPLY_TTL_SECONDS = 900


# --- shared guards ---------------------------------------------------------


def _known_alias(request: Request, value: str | None) -> bool:
    if not value:
        return False
    return is_known_incoming_secret_alias(
        value,
        scope=request.scope,
        accepted_prefixes=_settings(request).get_gateway_key_accepted_prefixes(),
    )


def _require_dashboard(request: Request) -> Response | None:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)
    return None


async def _page(request: Request):
    """Authenticated admin page context (or the auth refusal response)."""
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context
    return context, csrf_token


def _render(request: Request, *, template: str, context: Any, csrf_token: str, **kwargs: Any) -> Response:
    return templates.TemplateResponse(
        request,
        template,
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "base_path": _BASE,
            "admin_status_message": _admin_status_message(request),
            **kwargs,
        },
    )


def _dispatch_job(settings: Any, job_id: str) -> tuple[bool, str]:
    """Broker dispatch with an HONEST confirmation: broker admission is
    not completion and not live-worker proof. The confirmed/unconfirmed
    fact is persisted on the existing job metadata (survives refresh);
    a failed dispatch is reported as such and the operator can cancel
    the job to release its slot, then re-queue."""
    try:
        from slaif_gateway.workers.tasks_catalog_refresh import (  # lazy: no eager broker import
            catalog_refresh_execute_job,
        )
    except Exception as exc:  # noqa: BLE001 - safe refusal, never crash the page
        dispatched, note = False, f"worker module unavailable: {type(exc).__name__}"
    else:
        try:
            catalog_refresh_execute_job.delay(job_id)
            dispatched, note = (
                True,
                "queued (broker acknowledged; a running worker is not yet proven)",
            )
        except Exception as exc:  # noqa: BLE001 - honest unconfirmed state
            dispatched, note = False, f"broker dispatch unconfirmed: {type(exc).__name__}"
    try:
        custody.note_dispatch(settings, job_id, dispatched=dispatched, detail=note)
    except Exception:  # noqa: BLE001 - persistence failure never hides the honest note
        pass
    return dispatched, note

class _UploadTooLarge(Exception):
    """Bounded upload refusal (hard cap exceeded before completion)."""


class _UploadMalformed(Exception):
    """Multipart body failed strict bounded parsing."""


class _BoundedForm:
    """Bounded multipart form projection that PRESERVES repeated keys.

    A native ``<select multiple>`` (or the record-chip controls) submits
    the SAME key once per selected value; a plain dict would keep only
    the last. ``get`` keeps single-field semantics (last value), and
    ``getlist`` returns every value in submission order."""

    def __init__(self, pairs: list[tuple[str, str]]) -> None:
        self._pairs = list(pairs)
        self._by_name: dict[str, list[str]] = {}
        for key, value in self._pairs:
            self._by_name.setdefault(key, []).append(value)

    def get(self, key: str, default: str | None = None) -> str | None:
        values = self._by_name.get(key)
        return values[-1] if values else default

    def getlist(self, key: str) -> list[str]:
        return list(self._by_name.get(key, []))

    def keys(self) -> list[str]:
        return list(self._by_name)

    def __iter__(self) -> Any:
        return iter(self._by_name)

    def __len__(self) -> int:
        return len(self._by_name)


async def _bounded_multipart(
    request: Request, *, cap_bytes: int, max_files: int, max_fields: int
) -> tuple[_BoundedForm, dict[str, bytes]]:
    """Stream one multipart body with a HARD total byte cap (refused
    before unbounded allocation), bounded file/field counts, and a
    finite envelope cap (per-file caps are re-enforced by the caller).
    Returns (form, files-as-bytes). The parser-owned spooled file parts
    are closed on EVERY exit path (success, size, malformed): direct
    MultiPartParser ownership does not attach them to request._form."""

    class _CapExceeded(Exception):
        pass

    async def _capped_stream():
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > cap_bytes:
                raise _CapExceeded()
            yield chunk

    parser = MultiPartParser(
        request.headers,
        _capped_stream(),
        max_files=max_files,
        max_fields=max_fields,
        max_part_size=cap_bytes,
    )
    items = None
    try:
        items = await parser.parse()
    except _CapExceeded:
        raise _UploadTooLarge() from None
    except Exception as exc:  # noqa: BLE001 - strict bounded refusal
        raise _UploadMalformed(str(type(exc).__name__)) from None
    pairs: list[tuple[str, str]] = []
    files: dict[str, bytes] = {}
    try:
        for key, value in items.multi_items():
            if hasattr(value, "read"):
                # Parser-owned spooled part: read it bounded, then the close
                # pass below releases the spool on every path. An UNSELECTED
                # <input type=file> still submits the native no-file sentinel
                # File(filename="", size=0): ignore ONLY that sentinel so an
                # optional file field does not look like a supplied empty
                # document. A NAMED zero-byte file is preserved for strict
                # validation/refusal downstream.
                filename = getattr(value, "filename", "") or ""
                data = await value.read(cap_bytes + 1)
                if not filename and len(data) == 0:
                    continue
                if len(data) > cap_bytes:
                    raise _UploadTooLarge()
                files[key] = data
            else:
                pairs.append((key, str(value)))
    finally:
        for _key, value in items.multi_items():
            if hasattr(value, "read"):
                try:
                    await value.close()
                except Exception:  # noqa: BLE001 - best-effort release
                    pass
    return _BoundedForm(pairs), files


def _secret_form_refusal(request: Request, values: Any) -> bool:
    """True when ANY bounded form value IS or EMBEDS a known incoming
    authentication value or a credential-shaped identifier (the same
    pure fail-closed guards the apply-reason check uses). Refusal happens
    BEFORE any custody persistence - secret-bearing input is refused,
    never rewritten or re-signed."""
    for value in values:
        if _known_alias(request, value):
            return True
    return False


def _secret_upload_refusal(request: Request, content: bytes) -> bool:
    """True when bounded upload bytes contain a known incoming opaque
    authentication value OR a credential-shaped identifier - the same
    pure guard family the form-value check uses (known incoming secret
    masker plus the credential-shaped redact_text discovery). Fail
    closed when discovery is incomplete."""
    from slaif_gateway.services.request_diagnostics import build_client_id_masker
    from slaif_gateway.utils.redaction import redact_text

    try:
        masker, complete = build_client_id_masker(
            request.scope,
            accepted_prefixes=_settings(request).get_gateway_key_accepted_prefixes(),
        )
    except Exception:  # noqa: BLE001 - fail closed
        return True
    if not complete:
        return True
    prefixes = _settings(request).get_gateway_key_accepted_prefixes()
    try:
        text = content.decode("utf-8", errors="replace")
        if redact_text(text, prefixes) != text:
            return True
    except Exception:  # noqa: BLE001 - fail closed
        return True
    if masker is None:
        return False
    try:
        return masker(content) != content
    except Exception:  # noqa: BLE001 - fail closed
        return True


def _research_available(settings: Any) -> bool:
    """Lazy worker import: the FULL existing isolated-runner research
    configuration must be verified safe at use; otherwise the GUI shows
    research honestly unavailable (never a partial configuration)."""
    try:
        from slaif_gateway.workers import tasks_catalog_refresh as _worker

        return _worker._research_config_from_settings(settings) is not None
    except Exception:  # noqa: BLE001 - fail closed
        return False


def _parse_provider_choices(values: Any) -> list[str]:
    """Closed supported-provider set from REPEATED form keys (a native
    ``<select multiple>`` submits one key per selection). De-duplicated,
    sorted; unsupported values are dropped (the empty result is the
    handler's refusal)."""
    return sorted({
        value.strip()
        for value in values
        if value.strip() in _PROVIDERS
    })


def _parse_model_choices(value: Any) -> list[str] | None:
    """Explicit KNOWN-model choices from ONE form value: comma- or
    newline-separated (the record-choice multi control serializes
    newlines; typed fallbacks use commas). Blank = all eligible (empty
    list). An OVERSIZED explicit selection (>200) is refused (None),
    never silently truncated."""
    models: list[str] = []
    for chunk in str(value or "").replace(",", "\n").splitlines():
        cleaned = chunk.strip()
        if cleaned and cleaned not in models:
            models.append(cleaned)
    if len(models) > 200:
        return None
    return models


def _setup_context(request: Request, context: Any, csrf_token: str) -> dict[str, Any]:
    """Setup + custody usage + bounded job/run projections for one page."""
    settings = _settings(request)
    setup = inspect_custody_setup(settings)
    jobs: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    if setup.state == "ready":
        from slaif_gateway.services.admin_catalog_refresh import (
            _custody_usage,  # same-process inspection, no lock needed for display
            list_jobs,
            list_runs,
        )

        jobs = list_jobs(settings, limit=_VIEW_LIMIT)
        runs = list_runs(settings, limit=_VIEW_LIMIT)
        artifacts, records, active, total_bytes, reserved, slots = _custody_usage(setup.root)
        usage = {
            "artifacts": artifacts,
            "records": records,
            "active": active,
            "total_bytes": total_bytes,
            "reserved_bytes": reserved,
            "max_total_bytes": settings.CATALOG_REFRESH_MAX_TOTAL_BYTES,
            "max_retained_runs": settings.CATALOG_REFRESH_MAX_RETAINED_RUNS,
            "max_active_jobs": settings.CATALOG_REFRESH_MAX_ACTIVE_JOBS,
            "read_only_timeout_seconds": settings.CATALOG_REFRESH_READ_ONLY_TIMEOUT_SECONDS,
        }
    research_available = _research_available(settings)
    live_db_available = bool((settings.DATABASE_URL or "").strip())
    return {
        "setup": setup,
        "jobs": jobs,
        "runs": runs,
        "usage": usage,
        "research_available": research_available,
        "live_db_available": live_db_available,
        "content_files": sorted(CONTENT_FILES),
    }


def _last_job(jobs: list[dict[str, Any]], family: str) -> dict[str, Any] | None:
    for job in jobs:
        if job.get("family") == family:
            return job
    return None


def _last_job_packages(settings: Any, job: dict[str, Any] | None) -> list[str]:
    """Generated package presets for the bound proposal job (closed
    known-preset enumeration through the held custody handles; empty
    until the job is ready/warnings)."""
    if job is None or job.get("status") not in ("ready", "warnings"):
        return []
    try:
        return custody.list_proposal_packages(settings, str(job["job_id"]))
    except (CustodyJobError, AdminCatalogRefreshError):
        return []


def _bound_job(settings: Any, job_id: Any, family: str) -> dict[str, Any] | None:
    """Read the EXACT server-created job id back from custody.

    POST acknowledgements bind to the id ``create_job`` returned, never
    to "the newest job of this family": with MAX_ACTIVE_JOBS > 1 a
    concurrent request could otherwise be reported as this one's result.
    Unknown ids and foreign families resolve to None (nothing is
    substituted).
    """
    if not isinstance(job_id, str) or not _JOB_ID_RE.fullmatch(job_id):
        return None
    try:
        job = custody.get_job(settings, job_id)
    except (CustodyJobError, AdminCatalogRefreshError):
        return None
    if job is None or job.get("family") != family:
        return None
    return job


_JOB_REFUSAL_MESSAGE = (
    "The requested job id is unknown, was already cleaned up, or belongs to "
    "a different job family. No job is shown for it; open the page without "
    "the job parameter to see the newest job of this family."
)


def _resolve_bound_view(
    request: Request, settings: Any, family: str, jobs: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, str | None]:
    """Split ABSENT vs EXPLICIT ``?job=`` refresh navigation.

    - ABSENT (or empty) param -> ``("latest", None, None)``: the caller
      may show the newest job of the family, explicitly as the
      latest-global view.
    - EXPLICIT param -> ``("bound", job, None)`` for the exact well-formed
      closed custody id of this family, otherwise ``("refused", None,
      message)``: an unknown, deleted, invalid, or foreign-family id is
      NEVER substituted by the newest job (that would repeat the
      wrong-result bug after cleanup or malformed navigation).
    """
    raw = request.query_params.get("job")
    if raw is None or not raw.strip():
        return _last_job(jobs, family), None
    job = _bound_job(settings, raw, family)
    if job is not None:
        return job, None
    return None, _JOB_REFUSAL_MESSAGE


# --- workspace index --------------------------------------------------------


@router.get("/operations/catalog/", response_class=HTMLResponse)
async def catalog_index(request: Request) -> Response:
    page = await _page(request)
    if isinstance(page, Response):
        return page
    context, csrf_token = page
    extra = _setup_context(request, context, csrf_token)
    return _render(
        request,
        template="catalog_refresh/index.html",
        context=context,
        csrf_token=csrf_token,
        **extra,
    )


# --- proposals ---------------------------------------------------------------


@router.get("/operations/catalog/proposals", response_class=HTMLResponse)
async def catalog_proposals(request: Request) -> Response:
    page = await _page(request)
    if isinstance(page, Response):
        return page
    context, csrf_token = page
    settings = _settings(request)
    # 217-a: the include/exclude model filters reuse the catalog_upstream
    # record choice (latest ~100 upstream ids + older search + manual entry).
    model_options: list[Any] = []
    session_factory = get_sessionmaker_from_app(request)
    try:
        async with session_factory() as session:
            model_options = await load_choices(
                session,
                "catalog_upstream",
                selected=(),
                accepted_prefixes=settings.get_gateway_key_accepted_prefixes(),
            )
    except Exception:  # noqa: BLE001 - the page still works without choices
        model_options = []
    extra = _setup_context(request, context, csrf_token)
    # 217-a: exact ?job= refresh binding; an explicit but unknown,
    # deleted, invalid, or foreign-family id is refused, never replaced
    # by the newest job (the absent param keeps the latest-global view).
    last_job, job_refusal = _resolve_bound_view(request, settings, "proposal", extra["jobs"])
    extra.update(
        {
            "providers": _PROVIDERS,
            "endpoint_scopes": _ENDPOINT_SCOPES,
            "currencies": _CURRENCIES,
            "model_options": model_options,
            "package_presets": OPENROUTER_PACKAGE_ORDER,
            "last_job": last_job,
            "last_job_packages": _last_job_packages(settings, last_job),
            "last_job_provider_scope": (
                custody.job_provider_scope(settings, str(last_job["job_id"]))
                if last_job is not None
                else None
            ),
            "job_refusal": job_refusal,
            "errors": {},
        }
    )
    return _render(
        request,
        template="catalog_refresh/proposals.html",
        context=context,
        csrf_token=csrf_token,
        **extra,
    )


def _proposal_params(form: Any) -> tuple[dict[str, Any], str | None]:
    """Closed finite parameter capture (server re-enforces every bound).
    List-valued choices (endpoint scope, source method, packages) are read
    through getlist so repeated form keys are preserved; oversized EXPLICIT
    selections are refused rather than silently truncated."""
    scope = str(form.get("provider_scope") or "openai")
    if scope not in ("openai", "openrouter", "all"):
        return {}, "provider_scope"
    try:
        max_models = int(str(form.get("max_models") or "500"))
    except ValueError:
        return {}, "max_models"
    if not 1 <= max_models <= 500:
        return {}, "max_models"
    try:
        fetch_details_limit = int(str(form.get("fetch_details_limit") or "50"))
    except ValueError:
        return {}, "fetch_details_limit"
    if not 0 <= fetch_details_limit <= 200:
        return {}, "fetch_details_limit"
    try:
        max_web_calls = int(str(form.get("max_web_calls") or "3"))
    except ValueError:
        return {}, "max_web_calls"
    if not 0 <= max_web_calls <= 10:
        return {}, "max_web_calls"
    currency = str(form.get("currency") or "USD")
    if currency not in _CURRENCIES:
        return {}, "currency"
    endpoint_scopes = [
        value
        for value in (str(s).strip() for s in form.getlist("endpoint_scope"))
        if value in _ENDPOINT_SCOPES
    ]
    if not endpoint_scopes:
        return {}, "endpoint_scope"
    # source methods: closed set; repeated checkbox keys preserved via getlist
    source_methods = [
        value
        for value in (str(s).strip() for s in form.getlist("source_method"))
        if value in ("docs", "api", "assisted")
    ]
    if not source_methods:
        return {}, "source_method"
    # assisted is OpenAI-only: OpenRouter always uses docs + the models API
    # (selection cannot remove either) and the generator raises for
    # OpenRouter+assisted - refuse the unsupported combination BEFORE any
    # dispatch/network rather than a post-fetch failure.
    if "assisted" in source_methods and scope in ("openrouter", "all"):
        return {}, "source_method"
    # the OpenAI API / assisted seams require the existing deployment secret;
    # refuse early (a useful setup state) instead of a post-fetch
    # internal_error when it is not configured.
    if scope in ("openai", "all") and (
        "api" in source_methods or "assisted" in source_methods
    ):
        if not (os.getenv("OPENAI_ADMIN_DISCOVERY_API_KEY") or "").strip():
            return {}, "source_method"
    # explicit model selections: refuse oversized rather than truncate
    # 217-a: the include/exclude filters are the catalog_upstream record
    # choice (multi). Reuse the shared comma-/newline-aware parser so the
    # record-choice newline serialization and the legacy typed comma
    # fallback both parse identically; an OVERSIZED explicit selection
    # (>200) is still refused, never truncated.
    include_models = _parse_model_choices(form.get("include_models"))
    if include_models is None:
        return {}, "include_models"
    exclude_models = _parse_model_choices(form.get("exclude_models"))
    if exclude_models is None:
        return {}, "exclude_models"
    # packages: closed preset set via repeated checkbox keys
    package_names = [
        value
        for value in (str(p).strip() for p in form.getlist("package_name"))
        if value in OPENROUTER_PACKAGE_ORDER
    ]
    if scope == "openai" and (package_names or _is_checked(str(form.get("all_packages")))):
        return {}, "package_names"
    params: dict[str, Any] = {
        "provider_scope": scope,
        "endpoint_scopes": endpoint_scopes,
        "currency": currency,
        "max_models": max_models,
        "fetch_details_limit": fetch_details_limit,
        "max_web_calls": max_web_calls,
        "source_methods": source_methods,
        "save_source_snapshots": _is_checked(str(form.get("save_source_snapshots"))),
        "include_models": include_models,
        "exclude_models": exclude_models,
        "include_api_models": _is_checked(str(form.get("include_api_models"))),
        "acknowledge_assisted_proposal_risk": _is_checked(
            str(form.get("acknowledge_assisted_proposal_risk"))
        ),
        "allow_zero_prices": _is_checked(str(form.get("allow_zero_prices"))),
        "paired_ready_only": _is_checked(str(form.get("paired_ready_only"))),
        "ordinary_chat_only": _is_checked(str(form.get("ordinary_chat_only"))),
        "include_deprecated": _is_checked(str(form.get("include_deprecated"))),
        "include_ambiguous_capabilities": _is_checked(
            str(form.get("include_ambiguous_capabilities"))
        ),
        "all_packages": _is_checked(str(form.get("all_packages"))),
        "package_names": package_names,
    }
    return params, None


@router.post("/operations/catalog/proposals/generate", response_class=HTMLResponse)
async def catalog_proposals_generate(request: Request) -> Response:
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    form = await request.form()
    action = await _admin_action_context(request, csrf_token=str(form.get("csrf_token") or ""))
    if isinstance(action, Response):
        return action
    settings = _settings(request)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready":
        return _render_setup_refusal(request, action, str(form.get("csrf_token") or ""))
    params, field_error = _proposal_params(form)
    if field_error:
        return _render(
            request,
            template="catalog_refresh/proposals.html",
            context=action,
            csrf_token=str(form.get("csrf_token") or ""),
            **_setup_context(request, action, str(form.get("csrf_token") or "")),
            providers=_PROVIDERS,
            endpoint_scopes=_ENDPOINT_SCOPES,
            currencies=_CURRENCIES,
            model_options=None,
            package_presets=OPENROUTER_PACKAGE_ORDER,
            last_job=None,
            errors={"field": field_error, "message": (
                "OpenRouter packages require OpenRouter or both providers; leave packages unselected for OpenAI-only."
                if field_error == "package_names" else "One or more bounded proposal fields are invalid."
            )},
        )
    # Secret-persistence guard BEFORE the job record (which persists the
    # raw params) is written: every bounded value is checked with the
    # existing pure known-incoming-secret / credential-shaped guards.
    param_values: list[str] = []
    for value in params.values():
        if isinstance(value, list):
            param_values.extend(str(item) for item in value)
        elif isinstance(value, str):
            param_values.append(value)
    if _secret_form_refusal(request, param_values):
        return _render(
            request,
            template="catalog_refresh/proposals.html",
            context=action,
            csrf_token=str(form.get("csrf_token") or ""),
            **_setup_context(request, action, str(form.get("csrf_token") or "")),
            providers=_PROVIDERS,
            endpoint_scopes=_ENDPOINT_SCOPES,
            currencies=_CURRENCIES,
            model_options=None,
            package_presets=OPENROUTER_PACKAGE_ORDER,
            last_job=None,
            errors={"field": "secret", "message": "A proposal field matches a known incoming authentication value; it was refused and no job was created."},
        )
    try:
        job_id = custody.create_job(settings, "proposal", params)
    except (CustodyCapacityError, CustodyJobError, AdminCatalogRefreshError) as exc:
        return _render(
            request,
            template="catalog_refresh/proposals.html",
            context=action,
            csrf_token=str(form.get("csrf_token") or ""),
            **_setup_context(request, action, str(form.get("csrf_token") or "")),
            providers=_PROVIDERS,
            endpoint_scopes=_ENDPOINT_SCOPES,
            currencies=_CURRENCIES,
            model_options=None,
            package_presets=OPENROUTER_PACKAGE_ORDER,
            last_job=None,
            errors={"field": "capacity", "message": getattr(exc, "detail", None) or exc.code},
        )
    dispatched, dispatch_note = _dispatch_job(settings, job_id)
    # 217-a: bind the acknowledgement to the EXACT created job id (the
    # provider scope is the validated in-memory form value).
    bound_job = _bound_job(settings, job_id, "proposal")
    extra = _setup_context(request, action, str(form.get("csrf_token") or ""))
    extra.update(
        {
            "providers": _PROVIDERS,
            "endpoint_scopes": _ENDPOINT_SCOPES,
            "currencies": _CURRENCIES,
            "model_options": None,
            "package_presets": OPENROUTER_PACKAGE_ORDER,
            "last_job": bound_job,
            "last_job_packages": _last_job_packages(settings, bound_job),
            "last_job_provider_scope": params["provider_scope"],
            "dispatched": dispatched,
            "dispatch_note": dispatch_note,
            "errors": {},
        }
    )
    return _render(
        request,
        template="catalog_refresh/proposals.html",
        context=action,
        csrf_token=str(form.get("csrf_token") or ""),
        **extra,
    )


def _render_setup_refusal(request: Request, context: Any, csrf_token: str) -> Response:
    settings = _settings(request)
    setup = inspect_custody_setup(settings)
    return _render(
        request,
        template="catalog_refresh/index.html",
        context=context,
        csrf_token=csrf_token,
        setup=setup,
        jobs=[],
        runs=[],
        usage={},
        research_available=False,
        live_db_available=False,
        content_files=sorted(CONTENT_FILES),
        setup_refusal="Catalog actions are unavailable: complete the setup steps below first.",
    )


# --- collect -----------------------------------------------------------------


@router.get("/operations/catalog/collect", response_class=HTMLResponse)
async def catalog_collect(request: Request) -> Response:
    page = await _page(request)
    if isinstance(page, Response):
        return page
    context, csrf_token = page
    settings = _settings(request)
    model_options: list[Any] = []
    session_factory = get_sessionmaker_from_app(request)
    try:
        async with session_factory() as session:
            model_options = await load_choices(
                session,
                # 217-a: the collector consumes LITERAL upstream model ids,
                # so the dropdown projects the catalog upstream identities
                # (routes/pricing), not the alias-unioning shared model kind.
                "catalog_upstream",
                selected=(),
                accepted_prefixes=settings.get_gateway_key_accepted_prefixes(),
            )
    except Exception:  # noqa: BLE001 - the page still works without choices
        model_options = []
    extra = _setup_context(request, context, csrf_token)
    last_job, job_refusal = _resolve_bound_view(request, settings, "collect", extra["jobs"])
    extra.update(
        {
            "providers": _PROVIDERS,
            "model_options": model_options,
            "last_job": last_job,
            "job_refusal": job_refusal,
            "errors": {},
        }
    )
    return _render(
        request,
        template="catalog_refresh/collect.html",
        context=context,
        csrf_token=csrf_token,
        **extra,
    )


@router.post("/operations/catalog/collect/submit", response_class=HTMLResponse)
async def catalog_collect_submit(request: Request) -> Response:
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    settings = _settings(request)
    # Session authentication BEFORE any multipart parse or file I/O
    # (the established NONROTATING read-auth context): a missing,
    # invalid, or revoked session is refused without consuming the
    # upload stream. Fresh CSRF validation (the action context below)
    # still gates every job/custody/dispatch effect.
    read_auth = await _admin_attachment_context(request, touch=False)
    if isinstance(read_auth, Response):
        _set_no_store_headers(read_auth)
        return read_auth
    upload_error: str | None = None
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        try:
            form_fields, files = await _bounded_multipart(
                request,
                cap_bytes=_COLLECT_UPLOAD_CAP,
                max_files=1,
                max_fields=32,
            )
        except _UploadTooLarge:
            form_fields, files = _BoundedForm([]), {}
            upload_error = "size"
        except _UploadMalformed:
            form_fields, files = _BoundedForm([]), {}
            upload_error = "malformed"
    else:
        # starlette FormData already preserves repeated keys (getlist).
        form_fields = await request.form()
        files = {}
    action = await _admin_action_context(
        request, csrf_token=str(form_fields.get("csrf_token") or "")
    )
    if isinstance(action, Response):
        return action
    csrf = str(form_fields.get("csrf_token") or "")
    setup = inspect_custody_setup(settings)
    if setup.state != "ready":
        return _render_setup_refusal(request, action, csrf)

    if upload_error == "size":
        return _render_collect_error(request, action, csrf, "The uploaded baseline exceeds its 32 MiB bound.", "size")
    if upload_error == "malformed":
        return _render_collect_error(request, action, csrf, "The upload could not be strictly parsed within its bounds.", "malformed")

    mode = str(form_fields.get("mode") or "")
    if mode not in ("bootstrap", "refresh"):
        return _render_collect_error(request, action, csrf, "Choose exactly one: bootstrap (empty catalog) or refresh (existing catalog).", "mode")
    # Repeated ``providers=`` keys (native select multiple) preserved via
    # getlist; closed supported set, selection order de-duplicated.
    providers = _parse_provider_choices(form_fields.getlist("providers"))
    if not providers:
        return _render_collect_error(request, action, csrf, "Select at least one supported provider (openai, openrouter).", "providers")
    # Explicit KNOWN-model choices: comma- or newline-separated (the
    # record-choice multi control serializes newlines). Blank = all
    # eligible. An OVERSIZED explicit selection is refused, never
    # silently truncated.
    models = _parse_model_choices(form_fields.get("models"))
    if models is None:
        return _render_collect_error(request, action, csrf, "At most 200 explicit model choices may be selected; refine the selection (blank = all eligible).", "models")
    research = _is_checked(form_fields.get("research"))
    if research and not _research_available(settings):
        return _render_collect_error(request, action, csrf, "Assisted research is not fully configured on this deployment; leave it unchecked (deterministic collect) or configure the operator research runner.", "research")

    baseline_upload = files.get("baseline")
    if baseline_upload is not None and mode != "refresh":
        return _render_collect_error(request, action, csrf, "A baseline upload only applies to refresh.", "baseline")
    staged_baseline: bytes | None = None
    if baseline_upload is not None:
        from slaif_gateway.services.catalog_refresh.baseline import MAX_BASELINE_BYTES

        if len(baseline_upload) > MAX_BASELINE_BYTES:
            return _render_collect_error(request, action, csrf, "The uploaded baseline exceeds its 32 MiB bound.", "size")
        staged_baseline = baseline_upload

    # Secret-persistence guard BEFORE any custody write: every bounded
    # form value and the uploaded bytes are checked with the existing
    # pure known-incoming-secret / credential-shaped guards.
    form_values = [str(form_fields.get(key) or "") for key in form_fields]
    if _secret_form_refusal(request, form_values):
        return _render_collect_error(request, action, csrf, "A form value matches a known incoming authentication value; it was refused and nothing was stored.", "secret")
    if staged_baseline is not None and _secret_upload_refusal(request, staged_baseline):
        return _render_collect_error(request, action, csrf, "The uploaded baseline contains a known incoming authentication value or credential-shaped content; it was refused and nothing was stored.", "secret")

    # The generated upload name is committed in the job record at
    # admission (NEW-ONLY); the write itself is O_EXCL under the custody
    # lock after admission.
    baseline_name: str | None = None
    if staged_baseline is not None:
        baseline_name = f"baseline-{uuid.uuid4().hex}"
    params: dict[str, Any] = {
        "mode": mode,
        "providers": providers,
        "models": models,
        "research": research,
        "baseline_upload": baseline_name,
    }
    try:
        job_id = custody.create_job(settings, "collect", params)
    except (CustodyCapacityError, CustodyJobError, AdminCatalogRefreshError) as exc:
        return _render_collect_error(request, action, csrf, getattr(exc, "detail", None) or exc.code, "capacity")
    if staged_baseline is not None and baseline_name is not None:
        try:
            custody.store_upload(settings, job_id, "baseline", staged_baseline, name=baseline_name)
        except (CustodyCapacityError, CustodyJobError, AdminCatalogRefreshError) as exc:
            # The job was admitted but the upload did not fit: record the
            # refusal terminally (never leave a silently broken queued job).
            custody.finish_job(settings, job_id, "failed", error_code=getattr(exc, "code", None) or "upload_failed")
            return _render_collect_error(request, action, csrf, getattr(exc, "detail", None) or "the upload could not be stored", "capacity")
    dispatched, dispatch_note = _dispatch_job(settings, job_id)
    extra = _setup_context(request, action, csrf)
    extra.update(
        {
            "providers": _PROVIDERS,
            "model_options": [],
            "last_job": _bound_job(settings, job_id, "collect"),
            "dispatched": dispatched,
            "dispatch_note": dispatch_note,
            "errors": {},
        }
    )
    return _render(
        request,
        template="catalog_refresh/collect.html",
        context=action,
        csrf_token=csrf,
        **extra,
    )


def _render_collect_error(
    request: Request, context: Any, csrf_token: str, message: str, field: str
) -> Response:
    settings = _settings(request)
    jobs = custody.list_jobs(settings, limit=_VIEW_LIMIT) if inspect_custody_setup(settings).state == "ready" else []
    return _render(
        request,
        template="catalog_refresh/collect.html",
        context=context,
        csrf_token=csrf_token,
        **_setup_context(request, context, csrf_token),
        providers=_PROVIDERS,
        model_options=[],
        last_job=_last_job(jobs, "collect"),
        dispatched=None,
        dispatch_note=None,
        errors={"field": field, "message": message},
    )


# --- review supplied bundle ---------------------------------------------------


@router.get("/operations/catalog/review", response_class=HTMLResponse)
async def catalog_review(request: Request) -> Response:
    page = await _page(request)
    if isinstance(page, Response):
        return page
    context, csrf_token = page
    settings = _settings(request)
    extra = _setup_context(request, context, csrf_token)
    last_job, job_refusal = _resolve_bound_view(request, settings, "review_supplied", extra["jobs"])
    extra.update(
        {
            "last_job": last_job,
            "job_refusal": job_refusal,
            "errors": {},
        }
    )
    return _render(
        request,
        template="catalog_refresh/review.html",
        context=context,
        csrf_token=csrf_token,
        **extra,
    )


@router.post("/operations/catalog/review/submit", response_class=HTMLResponse)
async def catalog_review_submit(request: Request) -> Response:
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    settings = _settings(request)
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        page = await _page(request)
        if isinstance(page, Response):
            return page
        context, csrf = page
        extra = _setup_context(request, context, csrf)
        return _render(
            request,
            template="catalog_refresh/review.html",
            context=context,
            csrf_token=csrf,
            **extra,
            last_job=_last_job(extra["jobs"], "review_supplied"),
            errors={"field": "form", "message": "A bundle upload is required for a supplied-bundle review."},
        )
    # Session authentication BEFORE any multipart parse or file I/O
    # (the established NONROTATING read-auth context): a missing,
    # invalid, or revoked session is refused without consuming the
    # upload stream. Fresh CSRF validation (the action context below)
    # still gates every job/custody/dispatch effect.
    read_auth = await _admin_attachment_context(request, touch=False)
    if isinstance(read_auth, Response):
        _set_no_store_headers(read_auth)
        return read_auth
    upload_error: str | None = None
    try:
        form_fields, files = await _bounded_multipart(
            request, cap_bytes=_REVIEW_UPLOAD_CAP, max_files=2, max_fields=16
        )
    except _UploadTooLarge:
        form_fields, files = _BoundedForm([]), {}
        upload_error = "size"
    except _UploadMalformed:
        form_fields, files = _BoundedForm([]), {}
        upload_error = "malformed"
    action = await _admin_action_context(
        request, csrf_token=str(form_fields.get("csrf_token") or "")
    )
    if isinstance(action, Response):
        return action
    csrf = str(form_fields.get("csrf_token") or "")
    setup = inspect_custody_setup(settings)
    if setup.state != "ready":
        return _render_setup_refusal(request, action, csrf)
    if upload_error == "size":
        return _render_review_error(request, action, csrf, "The combined upload exceeds its bounded allowance (8 MiB bundle + 32 MiB baseline plus finite form overhead).", "size")
    if upload_error == "malformed":
        return _render_review_error(request, action, csrf, "The upload could not be strictly parsed within its bounds.", "malformed")
    bundle_upload = files.get("bundle")
    if bundle_upload is None:
        return _render_review_error(request, action, csrf, "The sealed bundle upload is required.", "bundle")
    from slaif_gateway.services.catalog_refresh.baseline import MAX_BASELINE_BYTES
    from slaif_gateway.services.catalog_refresh.bundle import MAX_BUNDLE_BYTES

    if len(bundle_upload) > MAX_BUNDLE_BYTES:
        return _render_review_error(request, action, csrf, "The bundle exceeds its 8 MiB bound.", "size")
    bundle_bytes = bundle_upload
    baseline_bytes: bytes | None = None
    if "baseline" in files:
        if len(files["baseline"]) > MAX_BASELINE_BYTES:
            return _render_review_error(request, action, csrf, "The baseline exceeds its 32 MiB bound.", "size")
        baseline_bytes = files["baseline"]
    first_install = _is_checked(form_fields.get("first_install"))
    # Secret-persistence guard BEFORE any custody write: the bounded
    # form values and BOTH uploaded artifacts are checked with the
    # existing pure known-incoming-secret / credential-shaped guards.
    form_values = [str(form_fields.get(key) or "") for key in form_fields]
    if _secret_form_refusal(request, form_values):
        return _render_review_error(request, action, csrf, "A form value matches a known incoming authentication value; it was refused and nothing was stored.", "secret")
    if _secret_upload_refusal(request, bundle_bytes) or (
        baseline_bytes is not None and _secret_upload_refusal(request, baseline_bytes)
    ):
        return _render_review_error(request, action, csrf, "An uploaded artifact contains a known incoming authentication value or credential-shaped content; it was refused and nothing was stored.", "secret")
    bundle_name = f"bundle-{uuid.uuid4().hex}"
    baseline_name = f"baseline-{uuid.uuid4().hex}" if baseline_bytes is not None else None
    params: dict[str, Any] = {
        "bundle_name": bundle_name,
        "baseline_name": baseline_name,
        "first_install": first_install,
    }
    try:
        job_id = custody.create_job(settings, "review_supplied", params)
        custody.store_upload(settings, job_id, "bundle", bundle_bytes, name=bundle_name)
        if baseline_bytes is not None and baseline_name is not None:
            custody.store_upload(settings, job_id, "baseline", baseline_bytes, name=baseline_name)
    except (CustodyCapacityError, CustodyJobError, AdminCatalogRefreshError) as exc:
        try:
            custody.finish_job(settings, job_id, "failed", error_code=getattr(exc, "code", None) or "upload_failed")
        except CustodyJobError:
            pass
        return _render_review_error(request, action, csrf, getattr(exc, "detail", None) or "the upload could not be stored", "capacity")
    dispatched, dispatch_note = _dispatch_job(settings, job_id)
    extra = _setup_context(request, action, csrf)
    extra.update(
        {
            "last_job": _bound_job(settings, job_id, "review_supplied"),
            "dispatched": dispatched,
            "dispatch_note": dispatch_note,
            "errors": {},
        }
    )
    return _render(
        request,
        template="catalog_refresh/review.html",
        context=action,
        csrf_token=csrf,
        **extra,
    )


def _render_review_error(
    request: Request, context: Any, csrf_token: str, message: str, field: str
) -> Response:
    settings = _settings(request)
    jobs = custody.list_jobs(settings, limit=_VIEW_LIMIT) if inspect_custody_setup(settings).state == "ready" else []
    return _render(
        request,
        template="catalog_refresh/review.html",
        context=context,
        csrf_token=csrf_token,
        **_setup_context(request, context, csrf_token),
        last_job=_last_job(jobs, "review_supplied"),
        dispatched=None,
        dispatch_note=None,
        errors={"field": field, "message": message},
    )


# --- export baseline ------------------------------------------------------------


@router.get("/operations/catalog/export-baseline", response_class=HTMLResponse)
async def catalog_export_page(request: Request) -> Response:
    page = await _page(request)
    if isinstance(page, Response):
        return page
    context, csrf_token = page
    settings = _settings(request)
    extra = _setup_context(request, context, csrf_token)
    last_job, job_refusal = _resolve_bound_view(request, settings, "export_baseline", extra["jobs"])
    extra.update(
        {
            "last_job": last_job,
            "job_refusal": job_refusal,
            "errors": {},
        }
    )
    return _render(
        request,
        template="catalog_refresh/export.html",
        context=context,
        csrf_token=csrf_token,
        **extra,
    )


@router.post("/operations/catalog/export-baseline/submit", response_class=HTMLResponse)
async def catalog_export_submit(request: Request) -> Response:
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    form = await request.form()
    csrf = str(form.get("csrf_token") or "")
    action = await _admin_action_context(request, csrf_token=csrf)
    if isinstance(action, Response):
        return action
    settings = _settings(request)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready":
        return _render_setup_refusal(request, action, csrf)
    try:
        job_id = custody.create_job(settings, "export_baseline", {})
    except (CustodyCapacityError, CustodyJobError, AdminCatalogRefreshError) as exc:
        settings2 = _settings(request)
        jobs = custody.list_jobs(settings2, limit=_VIEW_LIMIT)
        return _render(
            request,
            template="catalog_refresh/export.html",
            context=action,
            csrf_token=csrf,
            **_setup_context(request, action, csrf),
            last_job=_last_job(jobs, "export_baseline"),
            errors={"field": "capacity", "message": getattr(exc, "detail", None) or exc.code},
        )
    dispatched, dispatch_note = _dispatch_job(settings, job_id)
    extra = _setup_context(request, action, csrf)
    extra.update(
        {
            "last_job": _bound_job(settings, job_id, "export_baseline"),
            "dispatched": dispatched,
            "dispatch_note": dispatch_note,
            "errors": {},
        }
    )
    return _render(
        request,
        template="catalog_refresh/export.html",
        context=action,
        csrf_token=csrf,
        **extra,
    )


# --- sealed run review / status / verify --------------------------------------


def _run_detail_context(settings, run_id: str) -> dict[str, Any]:
    """Safe bounded projection of the SAME authenticated canonical plan
    (sealed validation report + receipt + execution context). Every
    value is sealed bytes rendered with autoescaping; bounded view sizes
    never imply a complete inventory."""
    capture, handle = custody.load_run_capture(settings, run_id)
    try:
        report = capture.report
        validation_doc = json.loads(capture.content["validation.json"])
        apply_plan = dict(validation_doc.get("apply_plan") or {})
        # Baseline facts are derived from the PARSED CANONICAL baseline
        # document (``capture.baseline``) - never from the display
        # validation section (which carries a different, partial shape).
        # A bootstrap/first-install run made NO SQL observation: its
        # target is the explicit configured target (honestly labeled),
        # the version is unknown, the row set is empty, and the sealed
        # first-install baseline bytes are the content identity.
        baseline_mode = str(getattr(capture.bundle.baseline, "mode", "") or "")
        baseline_doc = capture.baseline
        if baseline_doc is not None:
            baseline = {
                "mode": baseline_mode or "db_snapshot",
                "target_database": str(baseline_doc.target.database),
                "target_host": str(baseline_doc.target.server_host),
                "target_port": int(baseline_doc.target.server_port),
                "postgres_version": str(baseline_doc.target.postgres_version),
                "sql_checked": True,
                "target_origin": "sql_observed",
                "content_sha256": str(baseline_doc.content_sha256),
                "exported_at": baseline_doc.exported_at.isoformat()
                if baseline_doc.exported_at is not None
                else None,
            }
            row_counts = {
                "providers": int(baseline_doc.counts.providers),
                "routes": int(baseline_doc.counts.routes),
                "pricing_rules": int(baseline_doc.counts.pricing_rules),
                "fx_rates": int(baseline_doc.counts.fx_rates),
            }
        else:
            configured = _configured_target_facts(settings)
            baseline = {
                "mode": baseline_mode or "first_install",
                "target_database": configured[0] if configured else None,
                "target_host": configured[1] if configured else None,
                "target_port": configured[2] if configured else None,
                "postgres_version": "unknown (not SQL-observed)",
                "sql_checked": False,
                "target_origin": (
                    "configured (NOT SQL-observed)" if configured else "unknown"
                ),
                "content_sha256": hashlib.sha256(
                    capture.content.get("catalog-baseline.json", b"")
                ).hexdigest(),
                "exported_at": None,
            }
            row_counts: dict[str, int] = {}
        execution_context = capture.execution_context
        current_identity = execution_identity.measure_code_identity()
        original_identity = str(
            getattr(execution_context.generator, "code_revision", "") or ""
        )
        original_tool = str(getattr(execution_context.generator, "tool", "") or "")
        warning_rows = [
            {
                "severity": w.severity,
                "code": w.code,
                "provider": w.provider,
                "model": w.model,
                "detail": w.detail,
            }
            for w in list(report.warnings)[:100]
        ]
        source_rows = []
        for source in list(report.sources)[:50]:
            if isinstance(source, dict):
                source_rows.append(
                    {
                        "url": str(source.get("url") or "")[:256],
                        "retrieved_at": str(source.get("retrieved_at") or ""),
                        "content_hash": str(source.get("content_hash") or "")[:16],
                        "provider": str(source.get("provider") or ""),
                    }
                )
        # Bounded safe projection of the SAME sealed apply plan for the run
        # page. Only stable string facts are surfaced; the full plan bytes
        # remain in the verified catalog-refresh.json download.
        plan_operations_list = apply_plan.get("operations") or []

        def _first_present(op: dict[str, Any], keys: tuple[str, ...]) -> str:
            for key in keys:
                value = op.get(key)
                if value not in (None, ""):
                    return str(value)
            return "—"

        plan_op_rows: list[dict[str, str]] = []
        for op in list(plan_operations_list)[:200]:
            if not isinstance(op, dict):
                continue
            scope = _first_present(op, ("upstream_model", "endpoint"))
            if scope == "—":
                base = op.get("base_currency")
                quote = op.get("quote_currency")
                if base and quote:
                    scope = f"{base}/{quote}"
            plan_op_rows.append(
                {
                    "type": str(op.get("type") or ""),
                    "provider": _first_present(op, ("provider",)),
                    "subject": _first_present(
                        op,
                        (
                            "requested_model",
                            "model",
                            "source_pair",
                            "display_name",
                        ),
                    ),
                    "scope": scope,
                }
            )
        return {
            "run_id": run_id,
            "state": report.state,
            "state_reason": report.state_reason,
            "generated_at": report.generated_at,
            "policy_version": report.policy_version,
            "counts": dict(report.counts),
            "per_provider": {k: dict(v) for k, v in dict(report.per_provider).items()},
            "baseline": baseline,
            "row_counts": row_counts,
            "warnings": warning_rows,
            "warning_codes": [w["code"] for w in warning_rows if w["code"]],
            "sources": source_rows,
            "dispositions": [
                {
                    "provider": d.provider,
                    "model": d.model,
                    "disposition": d.disposition,
                    "detail": d.detail,
                }
                for d in list(report.dispositions)[:200]
            ],
            "price_comparisons": [
                {
                    "provider": p.provider,
                    "model": p.model,
                    "dimension": p.dimension,
                    "old": p.old,
                    "new": p.new,
                    "currency_old": p.currency_old,
                    "currency_new": p.currency_new,
                    "percent_change": p.percent_change,
                    "state": p.state,
                    # Actual unit of the sealed price value: token dimensions
                    # are per 1,000,000 tokens; the request dimension is per
                    # request. The value/currency are sealed and never altered.
                    "unit": _price_dimension_unit(p.dimension),
                }
                for p in list(report.price_comparisons)[:200]
            ],
            "apply_plan_present": bool(apply_plan.get("operations")),
            "plan_sha256": str(apply_plan.get("plan_sha256") or ""),
            "plan_operations": len(apply_plan.get("operations") or []),
            "plan_op_rows": plan_op_rows,
            "bundle_sha256": str(capture.receipt.get("semantic_bundle_sha256") or ""),
            "receipt_hmac_sha256": str(capture.receipt.get("hmac_sha256") or ""),
            "acquisition": str(getattr(execution_context, "acquisition", "")),
            "original_generator_identity": original_identity,
            "original_generator_tool": original_tool,
            "current_verifier_identity": current_identity,
            "identity_match": bool(
                original_identity and current_identity == original_identity
            ),
            "generator_versions": dict(
                getattr(execution_context, "generator_versions", {}) or {}
            ),
            "artifacts": sorted(
                (
                    {"name": name, "bytes": len(bytes_)}
                    for name, bytes_ in capture.content.items()
                ),
                key=lambda item: item["name"],
            ),
        }
    finally:
        handle.close()


@router.get("/operations/catalog/runs/{run_id}/", response_class=HTMLResponse)
async def catalog_run_detail(request: Request, run_id: str) -> Response:
    page = await _page(request)
    if isinstance(page, Response):
        return page
    context, csrf_token = page
    settings = _settings(request)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready":
        return _render_setup_refusal(request, context, csrf_token)
    try:
        detail = _run_detail_context(settings, run_id)
    except (CustodyJobError, AdminCatalogRefreshError, CatalogRefreshSealError, ValueError):
        return _admin_error_page(
            request, status_code=404, message="Unknown or unreadable sealed run."
        )
    except Exception:  # noqa: BLE001 - safe refusal, no raw error text
        return _admin_error_page(
            request, status_code=500, message="The sealed run could not be reviewed safely."
        )
    jobs = custody.list_jobs(settings, limit=_VIEW_LIMIT)
    related_job = next(
        (j for j in jobs if j.get("run_id") == detail["run_id"]), None
    )
    return _render(
        request,
        template="catalog_refresh/run.html",
        context=context,
        csrf_token=csrf_token,
        **_setup_context(request, context, csrf_token),
        detail=detail,
        related_job=related_job,
        is_superadmin=context.admin_user.role == "superadmin",
    )


@router.post("/operations/catalog/runs/{run_id}/verify", response_class=HTMLResponse)
async def catalog_run_verify(request: Request, run_id: str) -> Response:
    """Explicit read-only verification (seal, digests, semantic replay)
    under the held handle; truthful original-vs-current identity.
    Success is ``VerifyResult.valid`` - independent of the READY policy
    state, which is reported separately."""
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    form = await request.form()
    csrf = str(form.get("csrf_token") or "")
    action = await _admin_action_context(request, csrf_token=csrf)
    if isinstance(action, Response):
        return action
    settings = _settings(request)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready":
        return _render_setup_refusal(request, action, csrf)
    try:
        from slaif_gateway.services.catalog_refresh.application import verify_run_dir

        run_handle = custody.open_run_handle(settings, run_id)
        try:
            verify_result = verify_run_dir(
                run_dir=setup.root / "runs" / custody._assert_run_id(run_id),
                seal_key_path=setup.seal_key,
                run_handle=run_handle,
            )
        finally:
            run_handle.close()
        detail = _run_detail_context(settings, run_id)
    except (CustodyJobError, AdminCatalogRefreshError, CatalogRefreshSealError, ValueError):
        return _admin_error_page(
            request, status_code=404, message="Unknown or unreadable sealed run."
        )
    except Exception:  # noqa: BLE001 - safe refusal
        return _admin_error_page(
            request, status_code=500, message="Verification could not be completed safely."
        )
    return _render(
        request,
        template="catalog_refresh/run.html",
        context=action,
        csrf_token=csrf,
        **_setup_context(request, action, csrf),
        detail=detail,
        related_job=None,
        is_superadmin=action.admin_user.role == "superadmin",
        verified_state=getattr(verify_result, "state", None),
        verified_ok=bool(getattr(verify_result, "valid", False)),
    )


_ARTIFACT_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json",
    ".tsv": "text/tab-separated-values; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}


def _attachment(name: str, content: bytes) -> Response:
    suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    return Response(
        content,
        media_type=_ARTIFACT_CONTENT_TYPES.get(suffix, "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/operations/catalog/runs/{run_id}/artifact/{name}")
async def catalog_run_artifact(request: Request, run_id: str, name: str) -> Response:
    """Verified sealed artifact download.

    NON-ROTATING authenticated read context: the origin page (and its
    still-displayed form token) remains valid after the download, so a
    signed review form can still be submitted afterwards."""
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    context = await _admin_attachment_context(request, touch=False)
    if isinstance(context, Response):
        _set_no_store_headers(context)
        return context
    settings = _settings(request)
    try:
        content = custody.read_run_artifact(settings, run_id, name)
    except (CustodyJobError, AdminCatalogRefreshError, CatalogRefreshSealError):
        content = None
    if content is None:
        return _admin_error_page(
            request, status_code=404, message="Unknown or unreadable sealed artifact."
        )
    response = _attachment(name, content)
    _set_no_store_headers(response)
    return response


@router.get("/operations/catalog/jobs/{job_id}/artifact/{name}")
async def catalog_job_artifact(request: Request, job_id: str, name: str) -> Response:
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    context = await _admin_attachment_context(request, touch=False)
    if isinstance(context, Response):
        _set_no_store_headers(context)
        return context
    settings = _settings(request)
    try:
        content = custody.read_job_artifact(settings, job_id, name)
    except (CustodyJobError, AdminCatalogRefreshError):
        content = None
    if content is None:
        # GENERATED proposal artifacts live under proposals/<job_id>/
        # (the same verified bounded read; closed name set).
        try:
            content = custody.read_proposal_artifact(settings, job_id, name)
        except (CustodyJobError, AdminCatalogRefreshError):
            content = None
    if content is None:
        return _admin_error_page(
            request, status_code=404, message="Unknown or unreadable job artifact."
        )
    response = _attachment(name, content)
    _set_no_store_headers(response)
    return response


# --- proposal-to-import-preview bridge (NO automatic import) -------------------


_PROPOSAL_IMPORT_KINDS = {
    "routes": "routes-proposal.tsv",
    "pricing": "pricing-proposal.tsv",
}


async def _render_proposal_import_preview(
    request: Request,
    action: Any,
    csrf: str,
    *,
    artifact_name: str,
    text: str,
    source_label: str,
) -> Response:
    """Render one bounded generated TSV through the EXISTING route/pricing
    import-preview surface (NO import execution - the preview page's own
    explicitly confirmed execute action remains the only import path)."""
    settings = _settings(request)
    kind = "routes" if artifact_name == "routes-proposal.tsv" else "pricing"
    try:
        if kind == "routes":
            from slaif_gateway.api.admin import (
                _build_route_import_preview,
                _parse_route_import_rows_for_format,
                detect_route_import_format,
            )

            detected = detect_route_import_format(
                filename=artifact_name, requested_format="auto", text=text
            )
            raw_rows = _parse_route_import_rows_for_format(text, import_format=detected)
            preview = await _build_route_import_preview(
                request, raw_rows, max_rows=settings.ROUTE_IMPORT_MAX_ROWS
            )
            return templates.TemplateResponse(
                request,
                "routes/import_preview.html",
                {
                    "admin": action.admin_user,
                    "csrf_token": csrf,
                    "preview": preview,
                    "import_format": detected,
                    "source_label": source_label,
                    "max_rows": settings.ROUTE_IMPORT_MAX_ROWS,
                    "max_bytes": settings.ROUTE_IMPORT_MAX_BYTES,
                },
            )
        from slaif_gateway.api.admin import (
            _classify_pricing_import_preview,
            _parse_pricing_import_rows_for_format,
            detect_pricing_import_format,
            validate_pricing_import_rows,
        )

        detected = detect_pricing_import_format(
            filename=artifact_name, requested_format="auto", text=text
        )
        raw_rows = _parse_pricing_import_rows_for_format(text, import_format=detected)
        preview = validate_pricing_import_rows(
            raw_rows, max_rows=settings.PRICING_IMPORT_MAX_ROWS
        )
        preview = await _classify_pricing_import_preview(request, preview)
        return templates.TemplateResponse(
            request,
            "pricing/import_preview.html",
            {
                "admin": action.admin_user,
                "csrf_token": csrf,
                "preview": preview,
                "import_format": detected,
                "source_label": source_label,
                "max_rows": settings.PRICING_IMPORT_MAX_ROWS,
                "max_bytes": settings.PRICING_IMPORT_MAX_BYTES,
            },
        )
    except ValueError as exc:
        return _admin_error_page(
            request, status_code=400, message=str(exc) or "refused"
        )


@router.post(
    "/operations/catalog/jobs/{job_id}/import-preview/{kind}",
    response_class=HTMLResponse,
)
async def catalog_job_import_preview(
    request: Request, job_id: str, kind: str
) -> Response:
    """Bridge ONE generated proposal TSV to the EXISTING import preview.

    The bounded generated TSV is read from operator custody and rendered
    through the existing route/pricing import-preview surface. There is
    deliberately NO import execution here - the preview page's own
    existing (explicitly confirmed) execute action remains the only way
    to import, and it is not invoked by this bridge."""
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    form = await request.form()
    csrf = str(form.get("csrf_token") or "")
    action = await _admin_action_context(request, csrf_token=csrf)
    if isinstance(action, Response):
        return action
    artifact_name = _PROPOSAL_IMPORT_KINDS.get(kind)
    if artifact_name is None:
        return _admin_error_page(request, status_code=400, message="Unknown import kind.")
    settings = _settings(request)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready":
        return _render_setup_refusal(request, action, csrf)
    try:
        content = custody.read_proposal_artifact(settings, job_id, artifact_name)
    except (CustodyJobError, AdminCatalogRefreshError):
        content = None
    if content is None:
        return _admin_error_page(
            request,
            status_code=404,
            message="That job has no readable generated TSV artifact.",
        )
    text = content.decode("utf-8", errors="replace")
    source_label = f"catalog proposal job {job_id[:12]}"
    return await _render_proposal_import_preview(
        request,
        action,
        csrf,
        artifact_name=artifact_name,
        text=text,
        source_label=source_label,
    )


@router.get("/operations/catalog/jobs/{job_id}/package/{preset}/{name}")
async def catalog_job_package_artifact(
    request: Request, job_id: str, preset: str, name: str
) -> Response:
    """Generated package file download (closed preset + closed file set).

    NON-ROTATING authenticated read context, same bounded custody read as
    the root artifacts. Proposals are UNSEALED outputs: the import
    preview/review remains the strict gate."""
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    context = await _admin_attachment_context(request, touch=False)
    if isinstance(context, Response):
        _set_no_store_headers(context)
        return context
    settings = _settings(request)
    try:
        content = custody.read_proposal_package_artifact(
            settings, job_id, preset, name
        )
    except (CustodyJobError, AdminCatalogRefreshError):
        content = None
    if content is None:
        return _admin_error_page(
            request,
            status_code=404,
            message="Unknown or unreadable generated package file.",
        )
    response = _attachment(name, content)
    _set_no_store_headers(response)
    return response


@router.post(
    "/operations/catalog/jobs/{job_id}/package/{preset}/import-preview/{kind}",
    response_class=HTMLResponse,
)
async def catalog_job_package_import_preview(
    request: Request, job_id: str, preset: str, kind: str
) -> Response:
    """Bridge ONE generated PACKAGE TSV to the EXISTING import preview
    (same no-automatic-import boundary as the root bridge)."""
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    form = await request.form()
    csrf = str(form.get("csrf_token") or "")
    action = await _admin_action_context(request, csrf_token=csrf)
    if isinstance(action, Response):
        return action
    artifact_name = _PROPOSAL_IMPORT_KINDS.get(kind)
    if artifact_name is None:
        return _admin_error_page(request, status_code=400, message="Unknown import kind.")
    settings = _settings(request)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready":
        return _render_setup_refusal(request, action, csrf)
    try:
        content = custody.read_proposal_package_artifact(
            settings, job_id, preset, artifact_name
        )
    except (CustodyJobError, AdminCatalogRefreshError):
        content = None
    if content is None:
        return _admin_error_page(
            request,
            status_code=404,
            message="That job has no readable generated package TSV.",
        )
    source_label = f"catalog proposal job {job_id[:12]} package {preset}"
    return await _render_proposal_import_preview(
        request,
        action,
        csrf,
        artifact_name=artifact_name,
        text=content.decode("utf-8", errors="replace"),
        source_label=source_label,
    )


# --- job lifecycle (cancel / cleanup) ------------------------------------------


def _render_job_action(request, context, csrf_token, message: str, *, is_error: bool):
    settings = _settings(request)
    jobs = custody.list_jobs(settings, limit=_VIEW_LIMIT)
    return _render(
        request,
        template="catalog_refresh/index.html",
        context=context,
        csrf_token=csrf_token,
        **_setup_context(request, context, csrf_token),
        jobs=jobs,
        action_message=message,
        action_is_error=is_error,
    )


@router.post("/operations/catalog/jobs/{job_id}/cancel", response_class=HTMLResponse)
async def catalog_job_cancel(request: Request, job_id: str) -> Response:
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    form = await request.form()
    csrf = str(form.get("csrf_token") or "")
    action = await _admin_action_context(request, csrf_token=csrf)
    if isinstance(action, Response):
        return action
    settings = _settings(request)
    try:
        accepted = custody.request_cancel(settings, job_id)
    except (CustodyJobError, AdminCatalogRefreshError) as exc:
        return _render_job_action(request, action, csrf, getattr(exc, "detail", None) or "Unknown job.", is_error=True)
    message = (
        "Cancellation requested: read-only checkpoints until a terminal fact is known."
        if accepted
        else "The job is already terminal; nothing to cancel."
    )
    return _render_job_action(request, action, csrf, message, is_error=not accepted)


@router.post("/operations/catalog/jobs/{job_id}/remove", response_class=HTMLResponse)
async def catalog_job_remove(request: Request, job_id: str) -> Response:
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    form = await request.form()
    csrf = str(form.get("csrf_token") or "")
    action = await _admin_action_context(request, csrf_token=csrf)
    if isinstance(action, Response):
        return action
    if action.admin_user.role != "superadmin":
        return _admin_error_page(
            request,
            status_code=403,
            message="Cleaning up custody records requires the existing superadmin role.",
        )
    settings = _settings(request)
    try:
        custody.remove_terminal_job(settings, job_id)
    except (CustodyJobError, AdminCatalogRefreshError) as exc:
        return _render_job_action(request, action, csrf, getattr(exc, "detail", None) or "The finished job could not be removed.", is_error=True)
    return _render_job_action(request, action, csrf, "The finished job record was removed from custody.", is_error=False)


@router.post("/operations/catalog/runs/{run_id}/remove", response_class=HTMLResponse)
async def catalog_run_remove(request: Request, run_id: str) -> Response:
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    form = await request.form()
    csrf = str(form.get("csrf_token") or "")
    action = await _admin_action_context(request, csrf_token=csrf)
    if isinstance(action, Response):
        return action
    if action.admin_user.role != "superadmin":
        return _admin_error_page(
            request,
            status_code=403,
            message="Cleaning up sealed runs requires the existing superadmin role.",
        )
    settings = _settings(request)
    try:
        custody.remove_terminal_run(settings, run_id)
    except (CustodyJobError, AdminCatalogRefreshError) as exc:
        return _render_job_action(request, action, csrf, getattr(exc, "detail", None) or "The sealed run could not be removed.", is_error=True)
    return _render_job_action(request, action, csrf, "The sealed run was removed from custody (identity-checked).", is_error=False)


# --- reviewed apply (synchronous, web-layer, fresh superadmin) ------------------


def _price_dimension_unit(dimension: Any) -> str:
    """The actual unit of a sealed pricing value for its dimension.

    Token dimensions are priced per 1,000,000 tokens; the request dimension
    is priced per request. The sealed value/currency are never altered - this
    only states the unit the operator already priced it in.
    """
    dim = str(dimension or "")
    if dim == "request":
        return "per request"
    if dim:
        return f"per 1,000,000 {dim} tokens"
    return "per unit"


def _configured_target_facts(settings: Any) -> tuple[str, str, int] | None:
    """Identity of the EXPLICIT deployment-configured apply target.

    Parsed configuration only - NO SQL observation: (database, host,
    port) with the same identity semantics the Core baseline export
    uses (hostname default, port 5432 default, path database). None
    when not configured or not naming a database."""
    url = (settings.DATABASE_URL or "").strip()
    if not url:
        return None
    try:
        parsed = urlparse(url)
        database = (parsed.path or "").lstrip("/")
        if not parsed.scheme or not database:
            return None
        return database, (parsed.hostname or "localhost"), (parsed.port or 5432)
    except ValueError:
        return None


def _sealed_warning_codes(capture: Any) -> list[str]:
    """The exact sealed warning-code vocabulary of ONE authenticated run."""
    return sorted({w.code for w in capture.report.warnings if w.code})


def _sealed_apply_facts(
    capture: Any, settings: Any
) -> tuple[dict[str, Any] | None, str | None]:
    """Binding facts derived from ONE authenticated capture (the SAME
    held bytes Core apply consumes) plus the explicit configured target.

    Baseline facts come from the PARSED CANONICAL baseline document
    (``capture.baseline``), never from the display validation section.
    A first-install/bootstrap run made NO SQL observation: its target
    facts are the explicit configured target, the version is an honest
    unknown marker, the row set is empty, and the sealed first-install
    baseline bytes are the content identity. No SQL fact is ever
    invented. Returns (facts, None) or (None, safe message)."""
    if capture.result.state not in ("READY", "READY_WITH_WARNINGS"):
        return None, (
            f"the sealed review state is {capture.result.state}; "
            "only READY or READY_WITH_WARNINGS runs can be applied"
        )
    validation_doc = json.loads(capture.content["validation.json"])
    apply_plan = validation_doc.get("apply_plan") or {}
    if not apply_plan.get("operations") or not apply_plan.get("plan_sha256"):
        return None, "the sealed run carries no executable apply plan"
    bundle_sha = str(capture.receipt.get("semantic_bundle_sha256") or "")
    if not bundle_sha:
        return None, "the sealed run receipt carries no bundle digest"
    baseline = capture.baseline
    if baseline is not None:
        target_database = str(baseline.target.database)
        target_host = str(baseline.target.server_host)
        target_port = int(baseline.target.server_port)
        postgres_version = str(baseline.target.postgres_version)
        row_counts = {
            "providers": int(baseline.counts.providers),
            "routes": int(baseline.counts.routes),
            "pricing_rules": int(baseline.counts.pricing_rules),
            "fx_rates": int(baseline.counts.fx_rates),
        }
        baseline_sha = str(baseline.content_sha256)
    else:
        target = _configured_target_facts(settings)
        if target is None:
            return None, (
                "bootstrap (first-install) apply signs the EXPLICIT "
                "configured target: DATABASE_URL must be configured and "
                "name a database before a review can be signed"
            )
        target_database, target_host, target_port = target
        postgres_version = "unknown"
        row_counts = {}
        baseline_sha = hashlib.sha256(
            capture.content["catalog-baseline.json"]
        ).hexdigest()
    return (
        {
            "bundle_sha256": bundle_sha,
            "plan_sha256": str(apply_plan.get("plan_sha256") or ""),
            "target_database": target_database,
            "target_host": target_host,
            "target_port": target_port,
            "postgres_version": postgres_version,
            "baseline_content_sha256": baseline_sha,
            "row_counts": row_counts,
        },
        None,
    )


def _reason_refusal(request: Request, reason: str) -> str | None:
    """Closed validation for the operator's signed audit reason."""
    if not reason or not reason.strip():
        return "A nonblank audit reason (at most 500 characters) is required."
    if len(reason.strip()) > 500:
        return "A nonblank audit reason (at most 500 characters) is required."
    if _known_alias(request, reason):
        return (
            "The audit reason matches a known incoming authentication "
            "value and cannot be used. Choose a different reason."
        )
    return None


def _apply_review_document(
    settings, run_id: str, *, reason: str, ack_codes: list[str]
) -> tuple[tuple[dict[str, Any], list[str]] | None, str | None]:
    """Build the strict closed review document from the SEALED run facts
    plus the operator's SELECTED intent (reason + the exact sealed
    warning acknowledgements), all validated BEFORE anything is signed.
    Returns ((document, warning_codes), None) or (None, safe message)."""
    capture, handle = custody.load_run_capture(settings, run_id)
    try:
        facts, refusal = _sealed_apply_facts(capture, settings)
        if facts is None:
            return None, refusal or "the sealed run cannot be reviewed safely"
        warning_codes = _sealed_warning_codes(capture)
        selected = sorted(set(ack_codes))
        if selected != warning_codes:
            detail = "acknowledge exactly the sealed warning codes"
            missing = [code for code in warning_codes if code not in selected]
            extra = [code for code in selected if code not in warning_codes]
            if missing:
                detail += f"; not acknowledged yet: {', '.join(missing)}"
            if extra:
                detail += f"; outside the sealed set: {', '.join(extra)}"
            return None, detail
        document = {
            "run_id": run_id,
            **facts,
            "ack_warning_codes": warning_codes,
            "reason": reason,
            "nonce": uuid.uuid4().hex,
        }
        return (document, warning_codes), None
    finally:
        handle.close()


@router.post("/operations/catalog/runs/{run_id}/apply-preview", response_class=HTMLResponse)
async def catalog_apply_preview(request: Request, run_id: str) -> Response:
    """Two-step reviewed apply.

    Step 1 (no reason submitted): the sealed facts and the exact sealed
    warning vocabulary are shown; the operator selects the audit reason
    and acknowledgements. Step 2 (reason + acknowledgements submitted):
    the choices are validated against the sealed facts BEFORE signing,
    sealed into the closed session-bound document, and the final review
    page displays the signed choices. The signed values are the ONLY
    apply inputs - the final form carries no editable reason/ack."""
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    form = await request.form()
    csrf = str(form.get("csrf_token") or "")
    action = await _admin_action_context(request, csrf_token=csrf)
    if isinstance(action, Response):
        return action
    if action.admin_user.role != "superadmin":
        return _admin_error_page(
            request,
            status_code=403,
            message="Reviewing an apply requires the existing superadmin role. Inspection remains available to all signed-in admins.",
        )
    settings = _settings(request)
    reason = str(form.get("reason") or "").strip()
    ack_codes = [
        code.strip()
        for code in (str(value).strip() for value in form.getlist("ack_warning_code"))
        if code.strip()
    ]
    try:
        detail = _run_detail_context(settings, run_id)
    except (CustodyJobError, AdminCatalogRefreshError, CatalogRefreshSealError, ValueError, KeyError):
        return _admin_error_page(
            request, status_code=404, message="Unknown or unreadable sealed run."
        )
    sealed: dict[str, Any] = {}
    warning_codes: list[str] = []
    review_token = ""
    signed_reason = ""
    signed_acks: list[str] = []
    if reason:
        reason_problem = _reason_refusal(request, reason)
        if reason_problem:
            return _admin_error_page(request, status_code=400, message=reason_problem)
        try:
            built, refusal = _apply_review_document(
                settings, run_id, reason=reason, ack_codes=ack_codes
            )
        except (CustodyJobError, AdminCatalogRefreshError, CatalogRefreshSealError, ValueError, KeyError):
            return _admin_error_page(
                request, status_code=404, message="Unknown or unreadable sealed run."
            )
        except Exception:  # noqa: BLE001 - safe refusal
            return _admin_error_page(
                request, status_code=500, message="The apply review could not be prepared safely."
            )
        if built is None:
            return _admin_error_page(request, status_code=400, message=refusal or "refused")
        document, warning_codes = built
        sealed = dict(document)
        signed_reason = reason
        signed_acks = list(warning_codes)
        try:
            review_token = build_catalog_refresh_review_token(
                admin_session_secret=settings.ADMIN_SESSION_SECRET,
                admin_user_id=action.admin_user.id,
                admin_session_id=action.admin_session.id,
                review_document=document,
                ttl_seconds=_APPLY_TTL_SECONDS,
            )
        except AdminReviewIntentError as exc:
            return _admin_error_page(request, status_code=400, message=exc.message)
    else:
        # Step 1: sealed facts + exact acknowledgement vocabulary.
        capture, handle = custody.load_run_capture(settings, run_id)
        try:
            facts, refusal = _sealed_apply_facts(capture, settings)
            if facts is not None:
                sealed = dict(facts)
                warning_codes = _sealed_warning_codes(capture)
        finally:
            handle.close()
        if refusal is not None:
            return _admin_error_page(request, status_code=400, message=refusal)
    return _render(
        request,
        template="catalog_refresh/apply_review.html",
        context=action,
        csrf_token=csrf,
        **_setup_context(request, action, csrf),
        detail=detail,
        sealed=sealed,
        warning_codes=warning_codes,
        review_token=review_token,
        signed_reason=signed_reason,
        signed_acks=signed_acks,
        ttl_seconds=_APPLY_TTL_SECONDS,
        apply_result=None,
    )


@router.post("/operations/catalog/runs/{run_id}/apply", response_class=HTMLResponse)
async def catalog_apply(request: Request, run_id: str) -> Response:
    """The final reviewed apply.

    ONLY the signed closed document is an input: the review token plus
    the explicit confirmation checkbox. No unsigned reason/ack override
    exists. The signed facts are re-checked field-by-field against the
    CURRENT authenticated capture and the explicit configured target,
    on the SAME held run context the Core apply consumes - no re-open
    sits between the binding check and the Core call."""
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    form = await request.form()
    csrf = str(form.get("csrf_token") or "")
    review_token = str(form.get("review_token") or "")
    action = await _admin_action_context(request, csrf_token=csrf)
    if isinstance(action, Response):
        return action
    if action.admin_user.role != "superadmin":
        return _admin_error_page(
            request,
            status_code=403,
            message="Applying a catalog refresh requires the existing superadmin role. Inspection remains available to all signed-in admins.",
        )
    if not _is_checked(form.get("confirm_apply")):
        return _admin_error_page(
            request,
            status_code=400,
            message="The explicit confirmation checkbox is required for the reviewed apply.",
        )
    settings = _settings(request)
    try:
        document = verify_catalog_refresh_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            token=review_token,
            admin_user_id=action.admin_user.id,
            admin_session_id=action.admin_session.id,
        )
    except AdminReviewIntentError as exc:
        return _admin_error_page(request, status_code=400, message=exc.message)
    if document.get("run_id") != run_id:
        return _admin_error_page(
            request, status_code=400, message="The review state does not bind to this run."
        )
    reason = str(document.get("reason") or "")
    for canonical_value in (reason, str(document.get("target_database") or "")):
        if _known_alias(request, canonical_value):
            return _admin_error_page(
                request, status_code=400, message="A signed canonical value matches a known incoming authentication value; the apply was refused."
            )
    database_url = (settings.DATABASE_URL or "").strip()
    if not database_url:
        return _admin_error_page(
            request,
            status_code=400,
            message="DATABASE_URL is not configured on this deployment; the reviewed apply needs the deployment database.",
        )
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None or setup.seal_key is None:
        return _render_setup_refusal(request, action, csrf)
    detail = None
    try:
        detail = _run_detail_context(settings, run_id)
    except (CustodyJobError, AdminCatalogRefreshError, CatalogRefreshSealError, ValueError, KeyError):
        detail = None
    try:
        capture, run_handle = custody.load_run_capture(settings, run_id)
        try:
            current, refusal = _sealed_apply_facts(capture, settings)
            if current is None:
                return _admin_error_page(
                    request,
                    status_code=400,
                    message=refusal or "The sealed run changed since the review was signed; preview again.",
                )
            stale = (
                str(document.get("bundle_sha256") or "") != current["bundle_sha256"]
                or str(document.get("plan_sha256") or "") != current["plan_sha256"]
                or str(document.get("target_database") or "") != current["target_database"]
                or str(document.get("target_host") or "") != current["target_host"]
                or int(document.get("target_port") or -1) != int(current["target_port"])
                or str(document.get("postgres_version") or "") != current["postgres_version"]
                or str(document.get("baseline_content_sha256") or "") != current["baseline_content_sha256"]
                or dict(document.get("row_counts") or {}) != dict(current["row_counts"])
                or sorted(document.get("ack_warning_codes") or []) != _sealed_warning_codes(capture)
            )
            if stale:
                return _admin_error_page(
                    request,
                    status_code=400,
                    message="The sealed run or its binding facts changed since the review was signed; preview again.",
                )
            configured = _configured_target_facts(settings)
            if (
                configured is None
                or configured[0] != str(document.get("target_database") or "")
                or configured[1] != str(document.get("target_host") or "")
                or configured[2] != int(document.get("target_port") or -1)
            ):
                return _admin_error_page(
                    request,
                    status_code=400,
                    message="The configured deployment target no longer matches the signed review target; the apply was refused (no SQL executed).",
                )
            seal_key = load_seal_key_bytes(setup.seal_key)
            result = await apply_reviewed_run(
                run_dir=setup.root / "runs" / run_id,
                seal_key=seal_key,
                database_url=database_url,
                reason=reason,
                actor=str(action.admin_user.email or action.admin_user.display_name),
                admin_id=action.admin_user.id,
                ack_warnings=tuple(document.get("ack_warning_codes") or []),
                run_handle=run_handle,
            )
        finally:
            run_handle.close()
    except CatalogRefreshBlockedError as exc:
        return _render_apply_refusal(
            request, action, csrf, run_id, detail,
            getattr(exc, "code", None) or "blocked",
        )
    except (CustodyJobError, AdminCatalogRefreshError, CatalogRefreshSealError, ValueError):
        return _admin_error_page(
            request, status_code=404, message="Unknown or unreadable sealed run."
        )
    except Exception:  # noqa: BLE001 - unconfirmed, never a success claim
        logger.warning(
            "catalog apply finished unconfirmed",
            run_id=run_id,
            error_class="unexpected",
        )
        return _render_apply_unconfirmed(
            request, action, csrf, run_id, detail,
        )
    return _render(
        request,
        template="catalog_refresh/apply_result.html",
        context=action,
        csrf_token=csrf,
        **_setup_context(request, action, csrf),
        detail=detail,
        apply_status_value=(
            "already_committed (the committed repeat returned the original result)"
            if result.status == "already_committed"
            else "committed"
        ),
        apply_run_id=result.run_id,
        apply_bundle_sha256=result.bundle_sha256,
        apply_effective_at=result.effective_at,
        apply_counts=result.counts,
        apply_records=None,
        apply_unconfirmed=False,
    )


def _render_apply_refusal(
    request: Request, context: Any, csrf_token: str, run_id: str, detail, code: str
) -> Response:
    return _render(
        request,
        template="catalog_refresh/apply_result.html",
        context=context,
        csrf_token=csrf_token,
        **_setup_context(request, context, csrf_token),
        detail=detail,
        apply_status_value=f"refused ({code})",
        apply_run_id=run_id,
        apply_bundle_sha256=None,
        apply_effective_at=None,
        apply_counts=None,
        apply_records=None,
        apply_unconfirmed=False,
    )


def _render_apply_unconfirmed(
    request: Request, context: Any, csrf_token: str, run_id: str, detail
) -> Response:
    return _render(
        request,
        template="catalog_refresh/apply_result.html",
        context=context,
        csrf_token=csrf_token,
        **_setup_context(request, context, csrf_token),
        detail=detail,
        apply_status_value=(
            "UNCONFIRMED: the outcome is not known. Use the status action below; "
            "never assume applied or rolled back."
        ),
        apply_run_id=run_id,
        apply_bundle_sha256=None,
        apply_effective_at=None,
        apply_counts=None,
        apply_records=None,
        apply_unconfirmed=True,
    )


@router.get("/operations/catalog/runs/{run_id}/apply-status", response_class=HTMLResponse)
async def catalog_apply_status(request: Request, run_id: str) -> Response:
    """Authoritative committed-status read on the same held context: an
    unconfirmed apply is resolved here (committed or still unknown).

    NON-ROTATING authenticated read context (the stored form token is
    left untouched): while the operator polls, the signed review page's
    still-displayed form token must remain valid, so the apply on that
    same page can still be submitted. This page's status action is a
    plain GET and consumes no form token."""
    not_found = _require_dashboard(request)
    if not_found is not None:
        return not_found
    context = await _admin_attachment_context(request, touch=False)
    if isinstance(context, Response):
        return context
    settings = _settings(request)
    setup = inspect_custody_setup(settings)
    if setup.state != "ready" or setup.root is None or setup.seal_key is None:
        return _render_setup_refusal(request, context, "")
    database_url = (settings.DATABASE_URL or "").strip()
    detail = None
    status_value = None
    status = None
    records: list[dict[str, Any]] = []
    try:
        detail = _run_detail_context(settings, run_id)
        if database_url:
            seal_key = load_seal_key_bytes(setup.seal_key)
            run_handle = custody.open_run_handle(settings, run_id)
            try:
                status = await apply_status(
                    run_dir=setup.root / "runs" / run_id,
                    seal_key=seal_key,
                    database_url=database_url,
                    run_handle=run_handle,
                )
            finally:
                run_handle.close()
            records = list(status.records)
            status_value = (
                "committed (authoritative application record found)"
                if status.committed
                else "not committed in the authoritative record (unknown outcome remains unknown - no rollback promised)"
            )
        else:
            status_value = "DATABASE_URL is not configured; the authoritative record cannot be read."
    except (CustodyJobError, AdminCatalogRefreshError, CatalogRefreshSealError, ValueError):
        return _admin_error_page(
            request, status_code=404, message="Unknown or unreadable sealed run."
        )
    except Exception:  # noqa: BLE001 - safe refusal
        status_value = "The authoritative record could not be read; the outcome remains unconfirmed."
    committed = bool(status is not None and status.committed)
    return _render(
        request,
        template="catalog_refresh/apply_result.html",
        context=context,
        csrf_token="",
        **_setup_context(request, context, ""),
        detail=detail,
        apply_status_value=status_value or "unknown",
        apply_run_id=run_id,
        apply_bundle_sha256=(status.bundle_sha256 if status is not None else None),
        apply_effective_at=None,
        apply_counts=None,
        # Render the ACTUAL authoritative records (never collapsed to a
        # run-id-only view); the unconfirmed warning shows only when there
        # is NO authoritative committed evidence.
        apply_records=(records if committed else None),
        apply_unconfirmed=not committed,
    )

"""214-a: admin GUI reports and reviewed catalog tools (G11/G13/G18).

Delivers the GUI reporting and catalog-operations surface:

* **G11** — grouped usage summary (seven CLI-parity dimensions) and the
  Chat streaming live-burn aggregate, both over a bounded ledger source
  (GUI ceiling 10,000 rows, fetched cap+1 and REFUSED when overbound -
  never a silent prefix), plus a safe strict-JSON usage export through
  the shared ``UsageExportRow`` allowlist with session-derived actor,
  CSRF/confirmation/reason and the existing safe audit convention.
* **G18** — the reviewed matching-model pricing disable: exact
  provider/model/optional-endpoint scope preview (SQL-filtered enabled
  rows, bounded at 1000, overbound scope refused), a compact signed plan
  (identity + stable source fingerprint per row, 128 KiB cap) bound to
  the signed-in actor/session through the existing review-intent
  primitives, then a separate confirmation/apply in ONE caller
  transaction where the shared service re-checks fresh post-lock
  source facts and matching membership before disabling only the exact
  reviewed rows (late audit failure rolls everything back; the honest
  repeat is a no-op, never a second disable).
* **G18 FX** — effective FX lookup for an explicit base/quote pair at
  UTC now through the existing ``FxRateService.latest_fx_rate`` helper,
  with an honest missing state.

The controllers only bind scope, confirmation, and identity; the shared
services (``UsageReportService``, ``PricingRuleService``,
``FxRateService``) remain the sole authority for grouping, accounting
provenance, locking, staleness law, and rate resolution.  One-way helper
reuse from ``admin.py`` (admin.py does not import this router).
"""

from __future__ import annotations

import json
import re
from dataclasses import is_dataclass
from decimal import Decimal
import uuid as uuid_module
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Form, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.api.admin import (
    _admin_action_context,
    _admin_not_found,
    _admin_page_context,
    _client_host,
    _clean_admin_reason,
    _is_checked,
    _load_admin_record_choices,
    _log_admin_action_failure,
    _parse_admin_datetime,
    _parse_admin_export_limit,
    _parse_provider_slug,
    _parse_pricing_text,
    _parse_route_endpoint,
    _settings,
    templates,
)
from slaif_gateway.api.admin_review_intent import (
    AdminReviewIntentError,
    build_pricing_review_token,
    verify_pricing_review_token,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.schemas.key_configuration import (
    MAX_KEY_CONFIGURATION_REASON_LENGTH,
)
from slaif_gateway.schemas.usage import UsageReportFilters
from slaif_gateway.services.admin_export_service import _safe_filter_metadata
from slaif_gateway.services.fx_rate_service import FxRateService
from slaif_gateway.services.pricing_rule_service import (
    PricingDisableNoMatchError,
    PricingDisablePlan,
    PricingDisableScopeError,
    PricingDisableStaleError,
    PricingRuleService,
    parse_pricing_disable_plan_document,
    render_pricing_disable_plan,
)
from slaif_gateway.services.record_errors import RecordNotFoundError
from slaif_gateway.services.request_diagnostics import is_known_incoming_secret_alias
from slaif_gateway.services.usage_report_service import (
    GROUP_BY_VALUES,
    UsageReportService,
    UsageReportSourceBoundError,
    validate_group_by,
)
from slaif_gateway.utils.admin_pagination import (
    MAX_ADMIN_PAGE_LIMIT,
    build_navigation_url,
    build_page,
    page_params,
)
from slaif_gateway.web.formatting import format_number

router = APIRouter(prefix="/admin/reports", include_in_schema=False)

# 214-a GUI source ceiling: the bounded number of ledger rows one report
# view may aggregate.  The service fetches at most ceiling+1 rows through
# the EXISTING repository query and the overbound scope is REFUSED with
# narrowing help - a report never summarizes a silent prefix.  The CLI
# keeps its unbounded default (max_source_rows=None) unchanged.
GUI_USAGE_REPORT_SOURCE_MAX_ROWS = 10_000

# Finite display vocabulary (same seven CLI dimensions).
GROUP_BY_OPTIONS = tuple(sorted(GROUP_BY_VALUES))


def _currency_code(value: str | None, field_name: str) -> str | None:
    """3-letter currency code or None (blank); ValueError on bad shape."""
    if value is None or not value.strip():
        return None
    normalized = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", normalized):
        raise ValueError(f"{field_name} must be a 3-letter currency code.")
    return normalized


@asynccontextmanager
async def _report_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Caller-owned transaction scope for one report operation."""
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield session


def _accepted_prefixes(request: Request) -> tuple[str, ...]:
    return _settings(request).get_gateway_key_accepted_prefixes()


def _is_known_alias(request: Request, value: object) -> bool:
    """True when a display/submitted value is a known incoming
    authentication alias (pure fail-closed discovery; never echoes)."""
    return is_known_incoming_secret_alias(
        value, scope=request.scope, accepted_prefixes=_accepted_prefixes(request)
    )


def _walk_strings(value: object) -> object:
    """Recursively yield the string leaves of one closed review document."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_strings(item)


def _review_doc_has_alias(request: Request, document: object) -> bool:
    return any(_is_known_alias(request, item) for item in _walk_strings(document))


def _parse_report_uuid(value: str | None, field_name: str) -> uuid_module.UUID | None:
    if value is None or not value.strip():
        return None
    try:
        return uuid_module.UUID(value.strip())
    except ValueError:
        raise ValueError(f"{field_name} must be a UUID.") from None


def _parse_report_filters(
    *,
    provider: str | None,
    model: str | None,
    owner_id: str | None,
    cohort_id: str | None,
    gateway_key_id: str | None,
    start_at: datetime | None,
    end_at: datetime | None,
) -> UsageReportFilters:
    """One CLI-parity single-value report scope (inclusive UTC window).

    The shared report filters are single-value by design (the CLI
    summary/export contract); the ledger list's richer OR-within/
    AND-across multi-filter contract is a DIFFERENT scope and is not
    pretended to be identical here.
    """
    if start_at is not None and end_at is not None and end_at < start_at:
        raise ValueError("end_at must be greater than or equal to start_at.")
    return UsageReportFilters(
        start_at=start_at,
        end_at=end_at,
        provider=(provider.strip() or None) if provider is not None else None,
        model=(model.strip() or None) if model is not None else None,
        owner_id=_parse_report_uuid(owner_id, "owner_id"),
        cohort_id=_parse_report_uuid(cohort_id, "cohort_id"),
        gateway_key_id=_parse_report_uuid(gateway_key_id, "gateway_key_id"),
    )


def _report_filter_metadata(
    filters: UsageReportFilters,
) -> dict[str, object]:
    return _safe_filter_metadata(
        {
            "provider": filters.provider,
            "model": filters.model,
            "owner_id": filters.owner_id,
            "cohort_id": filters.cohort_id,
            "gateway_key_id": filters.gateway_key_id,
            "start_at": filters.start_at,
            "end_at": filters.end_at,
        }
    )


def _cost_status(known: int, total: int) -> str:
    """Per-group cost availability label (complete/partial/none).

    Display-only counts follow the established comma-grouped
    convention (read-only readouts; never a sort key, form value, or
    machine export).
    """
    known_text = format_number(known)
    total_text = format_number(total)
    if total <= 0:
        return "No rows"
    if known == total:
        return f"Complete ({known_text} of {total_text} rows known)"
    if known == 0:
        return f"No cost data (0 of {total_text} rows known)"
    return f"Partial ({known_text} of {total_text} rows known)"


def _safe_display(request: Request, value: object) -> str:
    """One display string with known-incoming-alias withholding."""
    text = str(value) if value is not None else ""
    if not text:
        return "—"
    if _is_known_alias(request, text):
        return "Withheld: matches a known credential value"
    return text


def _refuse_alias_scope(request: Request) -> Response:
    return _report_error(
        request,
        400,
        "The report scope cannot be shown: it matches a known incoming authentication value.",
    )


def _cost_money_display(known: int, total: int, value: Decimal) -> dict[str, object]:
    """Money display law (214-a review):

    - all rows missing  -> numeric is NOT rendered (unavailable, never 0);
    - all rows known     -> exact sum (a genuine known zero stays zero);
    - partially known    -> exact sum over the known rows, explicitly
      labelled incomplete (never a final actual cost).
    """
    if total <= 0:
        return {"available": False, "value": None, "label": "no rows"}
    if known == 0:
        return {"available": False, "value": None, "label": "unavailable"}
    if known < total:
        return {
            "available": True,
            "value": value,
            "label": "incomplete (partial; missing rows excluded)",
        }
    return {"available": True, "value": value, "label": ""}


def _json_default(value: object) -> object:
    """Typed JSON serializer for the safe export DTO (non-CLI utility).

    Exact raw machine units: Decimal as its EXACT string (never float),
    UUID as its canonical string, datetime as ISO-8601.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid_module.UUID):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _summary_group_display(
    request: Request, rows, availability
) -> list[dict[str, object]]:
    """Display-safe per-group rows: existing UsageSummaryRow facts plus
    the cost availability evidence (never a second money sum)."""
    display: list[dict[str, object]] = []
    for row, avail in zip(rows, availability):
        estimated = _cost_money_display(
            avail.estimated_cost_known_count,
            avail.row_count,
            row.estimated_cost_eur,
        )
        actual = _cost_money_display(
            avail.actual_cost_known_count, avail.row_count, row.actual_cost_eur
        )
        display.append(
            {
                # Label is a display fact: known incoming alias withheld.
                "label": _safe_display(
                    request, row.grouping_label or row.grouping_key
                ),
                "grouping_key": row.grouping_key,
                "request_count": row.request_count,
                "success_count": row.success_count,
                "failure_count": row.failure_count,
                "total_tokens": row.total_tokens,
                "cached_tokens": row.cached_tokens,
                "reasoning_tokens": row.reasoning_tokens,
                "estimated_cost": estimated,
                "actual_cost": actual,
                # Provider-native reported cost has NO currency
                # compatibility evidence: counts/explicit unavailable
                # only - a cross-currency sum is never displayed as
                # meaningful money.
                "provider_reported_status": _cost_status(
                    avail.provider_reported_cost_known_count, avail.row_count
                ),
                "provider_reported_shown": (
                    avail.provider_reported_cost_known_count > 0
                ),
                # Compact cell shows "k/n known" / "unavailable"; the exact
                # status string stays in the cell title (evidence access).
                "provider_reported_known": avail.provider_reported_cost_known_count,
                "provider_reported_total": avail.row_count,
                "first_seen_at": row.first_seen_at,
                "last_seen_at": row.last_seen_at,
            }
        )
    return display


# 214-a: fixed allowlisted recovery destinations for report-owned error
# pages.  Only these fixed report/form URLs may be offered as a direct
# no-JS recovery link; no raw query, token, secret, or free-form
# destination is ever echoed (the global admin error framework is
# deliberately NOT touched).
_REPORT_RECOVERY_DESTINATIONS = frozenset(
    {
        "/admin/reports/",
        "/admin/reports/live-burn",
        "/admin/reports/export",
        "/admin/reports/pricing-disable",
        "/admin/pricing",
    }
)


def _report_error(
    request: Request,
    status_code: int,
    message: str,
    *,
    recovery_href: str | None = None,
    recovery_label: str | None = None,
) -> Response:
    """Report-owned error surface with an optional direct safe recovery
    link to a fixed allowlisted report/form destination (no-JS recovery
    flow).  The destination must be one of the fixed allowlisted URLs;
    anything else falls back to the plain report error page (still with
    the generic "Go to admin" link), so no raw query/token/secret is ever
    emitted and no global error framework is introduced."""
    if recovery_href is not None and recovery_href not in _REPORT_RECOVERY_DESTINATIONS:
        recovery_href = None
        recovery_label = None
    return templates.TemplateResponse(
        request,
        "reports/error.html",
        {
            "error_status": status_code,
            "error_status_text": {
                400: "Bad request",
                404: "Not found",
                503: "Service unavailable",
            }.get(status_code, "Error"),
            "error_message": message,
            "recovery_href": recovery_href,
            "recovery_label": recovery_label or "Back to the report",
        },
        status_code=status_code,
    )


def _refuse_alias_scope(
    request: Request, recovery_href: str | None = None
) -> Response:
    return _report_error(
        request,
        400,
        "The report scope cannot be shown: it matches a known incoming authentication value.",
        recovery_href=recovery_href,
    )


# ----------------------------------------------------------------------
# G11: grouped usage summary report
# ----------------------------------------------------------------------


def _nav_filter_alias_refusal(
    request: Request, filter_pairs: list[tuple[str, str]]
) -> Response | None:
    """214-a: refuse accepted filter values matching a known incoming
    authentication alias BEFORE any navigation URL embeds them (the
    paged-list equivalent in admin.py runs the same check inside
    ``_admin_list_pagination``)."""
    for _name, value in filter_pairs:
        if _is_known_alias(request, value):
            return _refuse_alias_scope(request, "/admin/reports/")
    return None


def _report_filter_form_pairs(
    *,
    provider: str | None,
    model: str | None,
    owner_id: str | None,
    cohort_id: str | None,
    gateway_key_id: str | None,
    start_at: datetime | None,
    end_at: datetime | None,
    extra: list[tuple[str, str]] | None = None,
) -> list[tuple[str, str]]:
    """Allowlisted accepted report-filter pairs for one navigation URL
    (single-value CLI-parity scope; blank values omitted)."""
    pairs: list[tuple[str, str]] = list(extra or [])
    for name, value in (
        ("provider", provider),
        ("model", model),
        ("owner_id", owner_id),
        ("cohort_id", cohort_id),
        ("gateway_key_id", gateway_key_id),
    ):
        if value and value.strip():
            pairs.append((name, value.strip()))
    if start_at is not None:
        pairs.append(("start_at", start_at.isoformat()))
    if end_at is not None:
        pairs.append(("end_at", end_at.isoformat()))
    return pairs


@router.get("/", response_class=HTMLResponse)
async def usage_summary_report(
    request: Request,
    group_by: str = Query("provider_model"),
    provider: str | None = Query(None),
    model: str | None = Query(None),
    owner_id: str | None = Query(None),
    cohort_id: str | None = Query(None),
    gateway_key_id: str | None = Query(None),
    start_at: str | None = Query(None),
    end_at: str | None = Query(None),
    limit: int = Query(50, ge=1, le=MAX_ADMIN_PAGE_LIMIT),
    offset: int = Query(0, ge=0),
) -> Response:
    """Grouped usage summary over the bounded accepted source set.

    Groups are paged in-memory over the COMPLETE accepted group set
    (the service runs with ``limit=None`` here): the page
    limit/offset never bound the source evidence, and the stable
    grouping_key final tie-break keeps the paged order deterministic.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    # Report times use the existing aware-UTC parsing/normalization
    # BEFORE any comparison (naive input is normalized to UTC; mixed
    # naive/aware comparisons are never reached).
    try:
        parsed_start_at = _parse_admin_datetime(start_at)
        parsed_end_at = _parse_admin_datetime(end_at)
        filters = _parse_report_filters(
            provider=provider,
            model=model,
            owner_id=owner_id,
            cohort_id=cohort_id,
            gateway_key_id=gateway_key_id,
            start_at=parsed_start_at,
            end_at=parsed_end_at,
        )
        normalized_group_by = validate_group_by(group_by)
    except ValueError as exc:
        return _report_error(request, 400, str(exc), recovery_href="/admin/reports/")

    # Submitted scope values are echoed/displayed facts: a known
    # incoming authentication alias is refused BEFORE any service call
    # or rendering (fixed no-echo message).
    for value in (provider, model, owner_id, cohort_id, gateway_key_id, start_at, end_at):
        if value and _is_known_alias(request, value):
            return _refuse_alias_scope(request, "/admin/reports/")

    # Form facts for the report page: the accepted submitted scope is
    # prefilled so an overbound refusal can be recovered WITHIN the page
    # (a narrowing filter) without editing URLs.
    filters_view = {
        "provider": provider or "",
        "model": model or "",
        "owner_id": owner_id or "",
        "cohort_id": cohort_id or "",
        "gateway_key_id": gateway_key_id or "",
        "start_at": parsed_start_at.isoformat() if parsed_start_at is not None else "",
        "end_at": parsed_end_at.isoformat() if parsed_end_at is not None else "",
        "limit": limit,
        "offset": offset,
    }
    choices = await _load_admin_record_choices(
        request,
        (
            ("provider", "provider", provider or None),
            ("model", "model", model or None),
            ("owner_id", "owner", owner_id or None),
            ("cohort_id", "cohort", cohort_id or None),
            ("gateway_key_id", "key", gateway_key_id or None),
        ),
    )

    try:
        async with _report_session(request) as session:
            service = UsageReportService(
                usage_ledger_repository=UsageLedgerRepository(session)
            )
            report = await service.summarize_usage_report(
                filters=filters,
                group_by=normalized_group_by,
                limit=None,
                max_source_rows=GUI_USAGE_REPORT_SOURCE_MAX_ROWS,
            )
    except UsageReportSourceBoundError as exc:
        # The cap/refusal is unchanged; the recovery is the EXISTING
        # report/filter form rendered with the bound error: no results,
        # no group rows, and no completeness or count claims.
        return templates.TemplateResponse(
            request,
            "reports/usage_summary.html",
            {
                "admin": context.admin_user,
                "csrf_token": csrf_token,
                "bound_error": str(exc),
                "groups": [],
                "group_by": normalized_group_by,
                "group_by_options": GROUP_BY_OPTIONS,
                "source_bound": GUI_USAGE_REPORT_SOURCE_MAX_ROWS,
                "total_groups": 0,
                "page": build_page(page_size=limit, offset=offset, row_count=0),
                "prev_url": "",
                "next_url": "",
                "rows_shown": 0,
                "list_aria": "Usage summary groups",
                "filters": filters_view,
                "choices": choices,
            },
            status_code=400,
        )

    # In-memory cap+1 pagination over the COMPLETE accepted groups:
    # a full page alone is NOT has_more (an overflow group was fetched).
    window = list(report.rows[offset : offset + limit + 1])
    page = build_page(page_size=limit, offset=offset, row_count=len(window))
    page_rows = window[:limit]
    page_availability = list(report.availability[offset : offset + limit + 1])[:limit]
    filter_pairs = _report_filter_form_pairs(
        provider=provider,
        model=model,
        owner_id=owner_id,
        cohort_id=cohort_id,
        gateway_key_id=gateway_key_id,
        start_at=parsed_start_at,
        end_at=parsed_end_at,
        extra=[("group_by", normalized_group_by)],
    )
    if (refusal := _nav_filter_alias_refusal(request, filter_pairs)) is not None:
        return refusal
    prev_url = (
        build_navigation_url(
            "/admin/reports/", page_params(limit=limit, offset=page.prev_offset, filters=filter_pairs)
        )
        if page.can_prev
        else ""
    )
    next_url = (
        build_navigation_url(
            "/admin/reports/", page_params(limit=limit, offset=page.next_offset, filters=filter_pairs)
        )
        if page.has_more
        else ""
    )

    return templates.TemplateResponse(
        request,
        "reports/usage_summary.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "report": report,
            "groups": _summary_group_display(request, page_rows, page_availability),
            "group_by": normalized_group_by,
            "group_by_options": GROUP_BY_OPTIONS,
            "source_bound": GUI_USAGE_REPORT_SOURCE_MAX_ROWS,
            "total_groups": len(report.rows),
            "page": page,
            "prev_url": prev_url,
            "next_url": next_url,
            "rows_shown": len(page_rows),
            "list_aria": "Usage summary groups",
            "filters": filters_view,
            "choices": choices,
        },
    )


# ----------------------------------------------------------------------
# G11: Chat streaming live-burn report
# ----------------------------------------------------------------------


@router.get("/live-burn", response_class=HTMLResponse)
async def usage_live_burn_report(
    request: Request,
    provider: str | None = Query(None),
    model: str | None = Query(None),
    owner_id: str | None = Query(None),
    cohort_id: str | None = Query(None),
    gateway_key_id: str | None = Query(None),
    start_at: str | None = Query(None),
    end_at: str | None = Query(None),
) -> Response:
    """Chat streaming live-burn provenance over the bounded source set."""
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        parsed_start_at = _parse_admin_datetime(start_at)
        parsed_end_at = _parse_admin_datetime(end_at)
        filters = _parse_report_filters(
            provider=provider,
            model=model,
            owner_id=owner_id,
            cohort_id=cohort_id,
            gateway_key_id=gateway_key_id,
            start_at=parsed_start_at,
            end_at=parsed_end_at,
        )
    except ValueError as exc:
        return _report_error(request, 400, str(exc), recovery_href="/admin/reports/live-burn")

    # Submitted scope values are echoed/displayed facts: a known
    # incoming authentication alias is refused BEFORE any service call
    # or rendering (fixed no-echo message).
    for value in (provider, model, owner_id, cohort_id, gateway_key_id, start_at, end_at):
        if value and _is_known_alias(request, value):
            return _refuse_alias_scope(request, "/admin/reports/live-burn")

    # Form facts for the report page: the accepted submitted scope is
    # prefilled so an overbound refusal can be recovered WITHIN the page
    # (a narrowing filter) without editing URLs.
    filters_view = {
        "provider": provider or "",
        "model": model or "",
        "owner_id": owner_id or "",
        "cohort_id": cohort_id or "",
        "gateway_key_id": gateway_key_id or "",
        "start_at": parsed_start_at.isoformat() if parsed_start_at is not None else "",
        "end_at": parsed_end_at.isoformat() if parsed_end_at is not None else "",
    }
    choices = await _load_admin_record_choices(
        request,
        (
            ("provider", "provider", provider or None),
            ("model", "model", model or None),
            ("owner_id", "owner", owner_id or None),
            ("cohort_id", "cohort", cohort_id or None),
            ("gateway_key_id", "key", gateway_key_id or None),
        ),
    )

    try:
        async with _report_session(request) as session:
            service = UsageReportService(
                usage_ledger_repository=UsageLedgerRepository(session)
            )
            aggregate = await service.summarize_chat_live_burn(
                filters=filters,
                max_source_rows=GUI_USAGE_REPORT_SOURCE_MAX_ROWS,
            )
    except UsageReportSourceBoundError as exc:
        # The cap/refusal is unchanged; the recovery is the EXISTING
        # report/filter form rendered with the bound error: no aggregates,
        # no result rows, and no completeness or count claims.
        return templates.TemplateResponse(
            request,
            "reports/usage_live_burn.html",
            {
                "admin": context.admin_user,
                "csrf_token": csrf_token,
                "bound_error": str(exc),
                "aggregate": None,
                "source_bound": GUI_USAGE_REPORT_SOURCE_MAX_ROWS,
                "filters": filters_view,
                "choices": choices,
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "reports/usage_live_burn.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "aggregate": aggregate,
            "source_bound": GUI_USAGE_REPORT_SOURCE_MAX_ROWS,
            "filters": filters_view,
            "choices": choices,
        },
    )


# ----------------------------------------------------------------------
# G11: safe strict-JSON usage export
# ----------------------------------------------------------------------


@router.get("/export", response_class=HTMLResponse)
async def usage_export_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    choices = await _load_admin_record_choices(
        request,
        (
            ("provider", "provider", None),
            ("model", "model", None),
            ("owner_id", "owner", None),
            ("cohort_id", "cohort", None),
            ("gateway_key_id", "key", None),
        ),
    )

    return templates.TemplateResponse(
        request,
        "reports/usage_export.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "export_max_rows": settings.ADMIN_USAGE_EXPORT_MAX_ROWS,
            "reason_max_length": MAX_KEY_CONFIGURATION_REASON_LENGTH,
            "choices": choices,
            "filters": {
                "provider": "",
                "model": "",
                "owner_id": "",
                "cohort_id": "",
                "gateway_key_id": "",
                "start_at": "",
                "end_at": "",
            },
        },
    )


@router.post("/export")
async def usage_export_json(
    request: Request,
    csrf_token: str = Form(""),
    confirm_export: str | None = Form(None),
    reason: str | None = Form(None),
    provider: str | None = Form(None),
    model: str | None = Form(None),
    owner_id: str | None = Form(None),
    cohort_id: str | None = Form(None),
    gateway_key_id: str | None = Form(None),
    start_at: str | None = Form(None),
    end_at: str | None = Form(None),
    limit: str | None = Form(None),
) -> Response:
    """Confirmed strict-JSON usage export (private no-store attachment).

    The shared ``UsageExportRow`` allowlist is the ONLY exported shape
    (exact raw machine units, nullable costs).  The configured ceiling
    is fetched cap+1 and an overbound scope is REFUSED with the exact
    counts - the export never emits a silent partial and never claims
    first-page data is complete.  Submitted scope/reason, every
    serialized DTO leaf, and the audit metadata are known-alias guarded
    before output or persistence (fixed no-echo refusal).
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context
    if not _is_checked(confirm_export):
        return _report_error(
            request,
            400,
            "Confirm the JSON export before continuing.",
            recovery_href="/admin/reports/export",
        )
    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _report_error(
            request,
            400,
            "Enter an audit reason before exporting usage rows.",
            recovery_href="/admin/reports/export",
        )
    if len(cleaned_reason) > MAX_KEY_CONFIGURATION_REASON_LENGTH:
        return _report_error(
            request,
            400,
            "Audit reason is too long. Keep it to at most "
            f"{MAX_KEY_CONFIGURATION_REASON_LENGTH} characters.",
            recovery_href="/admin/reports/export",
        )

    try:
        parsed_start_at = _parse_admin_datetime(start_at)
        parsed_end_at = _parse_admin_datetime(end_at)
        filters = _parse_report_filters(
            provider=provider,
            model=model,
            owner_id=owner_id,
            cohort_id=cohort_id,
            gateway_key_id=gateway_key_id,
            start_at=parsed_start_at,
            end_at=parsed_end_at,
        )
        parsed_limit = _parse_admin_export_limit(
            limit,
            default=settings.ADMIN_USAGE_EXPORT_MAX_ROWS,
            maximum=settings.ADMIN_USAGE_EXPORT_MAX_ROWS,
        )
    except ValueError as exc:
        return _report_error(request, 400, str(exc), recovery_href="/admin/reports/export")

    # Submitted scope/reason are persisted and echoed facts: a known
    # incoming authentication alias is refused BEFORE any output or
    # persistence (fixed no-echo message, never signed or re-displayed).
    for value in (provider, model, owner_id, cohort_id, gateway_key_id, start_at, end_at):
        if value and _is_known_alias(request, value):
            return _refuse_alias_scope(request, "/admin/reports/export")
    if _is_known_alias(request, reason):
        return _report_error(
            request,
            400,
            "Reason withheld: it matches a known incoming authentication value.",
            recovery_href="/admin/reports/export",
        )

    async with _report_session(request) as session:
        usage_repository = UsageLedgerRepository(session)
        audit_repository = AuditRepository(session)
        service = UsageReportService(usage_ledger_repository=usage_repository)
        # cap+1 through the existing bounded query: exactly cap+1 fetched
        # rows prove an overbound scope without a racing count.
        rows = await service.export_usage(filters=filters, limit=parsed_limit + 1)
        if len(rows) > parsed_limit:
            return _report_error(
                request,
                400,
                (
                    "The export scope matches "
                    f"{parsed_limit + 1} or more ledger rows; the configured "
                    f"export ceiling is {parsed_limit} rows. Narrow the scope "
                    "with a time window, provider, model, key, owner, or "
                    "cohort filter. No partial export was produced."
                ),
                recovery_href="/admin/reports/export",
            )
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "scope": {
                "filters": _report_filter_metadata(filters),
                "limit": parsed_limit,
                "row_count": len(rows),
            },
            "rows": [asdict(row) for row in rows],
        }
        # Every serialized DTO leaf is alias-guarded BEFORE output or
        # persistence: one withheld leaf refuses the whole export
        # (fail-closed, fixed no-echo message).
        if any(_is_known_alias(request, leaf) for leaf in _walk_strings(payload)):
            return _report_error(
                request,
                400,
                "The export cannot be produced: a value in the matching rows matches a known incoming authentication value. Narrow the scope.",
                recovery_href="/admin/reports/export",
            )
        content = json.dumps(
            payload,
            allow_nan=False,
            sort_keys=True,
            default=_json_default,
        ).encode("utf-8")
        await audit_repository.add_audit_log(
            admin_user_id=action_context.admin_user.id,
            action="admin_usage_export_json",
            entity_type="usage_ledger_export",
            old_values=None,
            new_values={
                "row_count": len(rows),
                "limit": parsed_limit,
                "filters": _report_filter_metadata(filters),
            },
            ip_address=_client_host(request),
            user_agent=request.headers.get("user-agent"),
            request_id=request.headers.get(settings.REQUEST_ID_HEADER),
            note=cleaned_reason,
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"usage-export-{timestamp}.json"
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


# ----------------------------------------------------------------------
# G18: reviewed matching-model pricing disable
# ----------------------------------------------------------------------


@router.get("/pricing-disable", response_class=HTMLResponse)
async def pricing_disable_form(request: Request) -> Response:
    """Entry form for the reviewed matching-model pricing disable."""
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    choices = await _load_admin_record_choices(request, (("provider", "provider", None), ("model", "model", None), ("endpoint", "endpoint", None)))

    return templates.TemplateResponse(
        request,
        "reports/pricing_disable.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "choices": choices,
            "max_reviewed_rows": 1000,
            "reason_max_length": MAX_KEY_CONFIGURATION_REASON_LENGTH,
            "filters": {"provider": "", "model": "", "endpoint": "", "reason": ""},
            "error": None,
        },
    )


def _plan_display_context(request: Request, plan: PricingDisablePlan) -> dict[str, object]:
    """Safe preview display facts (never signed; fingerprint alone binds).

    The display rows are NOT part of the compact signed plan, so every
    displayed scope/row fact passes the known-incoming-alias withholding
    HERE (the signed-document walk covers only the compact plan + reason).
    """
    return {
        "provider": _safe_display(request, plan.provider),
        "model": _safe_display(request, plan.model),
        "endpoint": (
            _safe_display(request, plan.endpoint) if plan.endpoint else "(all endpoints)"
        ),
        "row_count": plan.row_count,
        "display_rows": [
            {
                "pricing_rule_id": str(row.pricing_rule_id),
                "provider": _safe_display(request, row.provider),
                "model": _safe_display(request, row.upstream_model),
                "endpoint": _safe_display(request, row.endpoint),
                "currency": row.currency,
                "valid_from": row.valid_from,
                "valid_until": row.valid_until,
                "input_price_per_1m": row.input_price_per_1m,
                "cached_input_price_per_1m": row.cached_input_price_per_1m,
                "output_price_per_1m": row.output_price_per_1m,
                "reasoning_price_per_1m": row.reasoning_price_per_1m,
                "request_price": row.request_price,
            }
            for row in plan.display_rows
        ],
        "row_ids": [str(row.pricing_rule_id) for row in plan.rows],
    }


@router.post("/pricing-disable/preview", response_class=HTMLResponse)
async def pricing_disable_preview(request: Request) -> Response:
    """Deliberate preview: shared-service preview (read-only), strict
    compact plan rendering, and signing bound to the signed-in
    actor/session with the 15-minute review-intent bound.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    provider_raw = str(form.get("provider") or "")
    model_raw = str(form.get("model") or "")
    endpoint_raw = str(form.get("endpoint") or "")
    reason = str(form.get("reason") or "")

    try:
        provider_slug = _parse_provider_slug(provider_raw)
        model_text = _parse_pricing_text(model_raw, field_name="Model")
        endpoint_value: str | None = None
        if endpoint_raw.strip():
            endpoint_value = _parse_route_endpoint(endpoint_raw)
    except ValueError as exc:
        return _report_error(request, 400, str(exc), recovery_href="/admin/reports/pricing-disable")

    # The scope identifiers are displayed facts: a known incoming
    # authentication alias is refused BEFORE the service call, signing,
    # or rendering (never echoed).
    for value in (provider_slug, model_text, endpoint_value):
        if value and _is_known_alias(request, value):
            return _report_error(
                request,
                400,
                "The pricing disable scope cannot be previewed: it matches a known incoming authentication value.",
                recovery_href="/admin/reports/pricing-disable",
            )

    # Normal GUI reason convention (the replay-maintenance pattern):
    # nonblank, bounded, NEVER trimmed (the original string is the
    # reviewed string), alias-guarded before signing.
    if not reason.strip():
        return _report_error(
            request,
            400,
            "Enter a nonblank audit reason for the reviewed pricing disable.",
            recovery_href="/admin/reports/pricing-disable",
        )
    if len(reason) > MAX_KEY_CONFIGURATION_REASON_LENGTH:
        return _report_error(
            request,
            400,
            "Audit reason is too long. Keep it to at most "
            f"{MAX_KEY_CONFIGURATION_REASON_LENGTH} characters.",
            recovery_href="/admin/reports/pricing-disable",
        )
    if _is_known_alias(request, reason):
        return _report_error(
            request,
            400,
            "Reason withheld: it matches a known incoming authentication value.",
            recovery_href="/admin/reports/pricing-disable",
        )

    try:
        async with _report_session(request) as session:
            service = PricingRuleService(
                pricing_rules_repository=PricingRulesRepository(session),
                audit_repository=AuditRepository(session),
            )
            plan = await service.preview_disable_model(
                provider=provider_slug,
                model=model_text,
                endpoint=endpoint_value,
            )
    except PricingDisableNoMatchError as exc:
        return _report_error(request, 400, str(exc), recovery_href="/admin/reports/pricing-disable")
    except PricingDisableScopeError as exc:
        return _report_error(request, 400, str(exc), recovery_href="/admin/reports/pricing-disable")

    # Strict compact plan document (closed keys, unique ids, bounded
    # row count, fingerprint format, 128 KiB canonical cap) - rendered
    # BEFORE any signing.
    plan_document = render_pricing_disable_plan(plan)
    review_document: dict[str, object] = {"plan": plan_document, "reason": reason}
    if _review_doc_has_alias(request, review_document):
        return _report_error(
            request,
            400,
            "The reviewed pricing facts can no longer be shown: they match a known incoming authentication value. Preview the scope again.",
            recovery_href="/admin/reports/pricing-disable",
        )
    try:
        token = build_pricing_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
            review_document=review_document,
        )
    except AdminReviewIntentError as exc:
        return _report_error(request, 400, exc.message, recovery_href="/admin/reports/pricing-disable")

    return templates.TemplateResponse(
        request,
        "reports/pricing_disable_review.html",
        {
            "admin": action_context.admin_user,
            "csrf_token": csrf_token,
            "plan_context": _plan_display_context(request, plan),
            "reason": reason,
            "review_token": token,
            "result": None,
        },
    )


@router.post("/pricing-disable/apply", response_class=HTMLResponse)
async def pricing_disable_apply(request: Request) -> Response:
    """Verify the signed review, then apply in ONE caller transaction.

    The token is reviewed data, never authority: posted plan/count/
    reason/actor overrides confer no authority.  The signed facts are
    re-checked against THIS request's known incoming aliases before any
    service call; the shared service re-validates fresh post-lock
    source state and matching membership under its locks, so stale or
    drifted scope is refused with zero writes, a late audit failure
    rolls all changes back, and the honest repeat is a no-op (never a
    second disable or invented receipt).
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    form = await request.form()
    csrf_token = str(form.get("csrf_token") or "")
    review_token = str(form.get("review_token") or "")
    confirm_apply = str(form.get("confirm_apply") or "")
    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    try:
        document = verify_pricing_review_token(
            admin_session_secret=settings.ADMIN_SESSION_SECRET,
            token=review_token,
            admin_user_id=action_context.admin_user.id,
            admin_session_id=action_context.admin_session.id,
        )
    except AdminReviewIntentError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _report_error(request, 400, exc.message, recovery_href="/admin/reports/pricing-disable")

    try:
        plan = parse_pricing_disable_plan_document(document["plan"])
        reason = str(document["reason"])
    except (KeyError, TypeError, ValueError):
        return _report_error(
            request,
            400,
            "The pricing disable review state is missing or invalid.",
            recovery_href="/admin/reports/pricing-disable",
        )

    if not _is_checked(confirm_apply):
        return _report_error(
            request,
            400,
            "Confirm the reviewed pricing disable before applying it.",
            recovery_href="/admin/reports/pricing-disable",
        )

    if _review_doc_has_alias(request, document):
        return _report_error(
            request,
            400,
            "The reviewed pricing disable can no longer be applied: a reviewed value matches a known incoming authentication value. Preview the scope again.",
            recovery_href="/admin/reports/pricing-disable",
        )

    result = None
    try:
        async with _report_session(request) as session:
            service = PricingRuleService(
                pricing_rules_repository=PricingRulesRepository(session),
                audit_repository=AuditRepository(session),
            )
            result = await service.apply_disable_model_reviewed(
                plan=plan,
                actor_admin_id=action_context.admin_user.id,
                reason=reason,
            )
    except PricingDisableStaleError as exc:
        _log_admin_action_failure(
            request,
            exc=exc,
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _report_error(
            request,
            400,
            f"{exc} Preview the scope again to review the current state.",
            recovery_href="/admin/reports/pricing-disable",
        )
    except Exception:  # noqa: BLE001 - outcome may be unconfirmed; fixed safe fallback
        _log_admin_action_failure(
            request,
            exc=Exception("pricing disable apply failed"),
            admin_id=action_context.admin_user.id,
            owner_id=None,
            cohort_id=None,
            email_delivery_mode=None,
        )
        return _report_error(
            request,
            400,
            "The pricing disable outcome is UNCONFIRMED. Check the pricing rule state and the audit log before retrying; a lost commit acknowledgement cannot prove a rollback.",
            recovery_href="/admin/pricing",
            recovery_label="Check the pricing rules",
        )

    return templates.TemplateResponse(
        request,
        "reports/pricing_disable_review.html",
        {
            "admin": action_context.admin_user,
            "csrf_token": csrf_token,
            "plan_context": _plan_display_context(request, plan),
            "reason": reason,
            "review_token": None,
            "result": {
                "disabled_count": result.disabled_count,
                "already_disabled": result.already_disabled,
            },
        },
    )


# ----------------------------------------------------------------------
# G18: effective FX lookup (UTC now, exact shared helper)
# ----------------------------------------------------------------------


@router.get("/fx-lookup", response_class=HTMLResponse)
async def fx_rate_lookup(
    request: Request,
    base_currency: str = Query(""),
    quote_currency: str = Query(""),
) -> Response:
    """Effective FX rate for one explicit base/quote pair at UTC now.

    Resolution uses the EXISTING ``FxRateService.latest_fx_rate`` helper
    unchanged; a missing pair is an honest missing state, never an
    inferred or same-currency rate.
    """
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found(request)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        base = _currency_code(base_currency, "Base currency")
        quote = _currency_code(quote_currency, "Quote currency")
    except ValueError as exc:
        return _report_error(request, 400, str(exc), recovery_href="/admin/reports/fx-lookup")
    if base is not None and base == quote:
        return _report_error(
            request,
            400,
            "Base and quote currency must differ.",
            recovery_href="/admin/reports/fx-lookup",
        )

    if base is not None and quote is not None and (
        _is_known_alias(request, base) or _is_known_alias(request, quote)
    ):
        return _refuse_alias_scope(request, "/admin/reports/fx-lookup")

    lookup: dict[str, object] | None = None
    if base is not None and quote is not None:
        try:
            async with _report_session(request) as session:
                service = FxRateService(
                    fx_rates_repository=FxRatesRepository(session),
                    audit_repository=AuditRepository(session),
                )
                rate = await service.latest_fx_rate(
                    base_currency=base, quote_currency=quote
                )
            # The rate's source is a display fact not covered by any
            # signed document: known-incoming-alias withheld.
            lookup = {
                "base_currency": rate.base_currency,
                "quote_currency": rate.quote_currency,
                "rate": rate.rate,
                "source": (
                    _safe_display(request, rate.source)
                    if rate.source is not None
                    else None
                ),
                "valid_from": rate.valid_from,
                "valid_until": rate.valid_until,
            }
        except RecordNotFoundError:
            lookup = {
                "base_currency": base,
                "quote_currency": quote,
                "missing": True,
            }

    choices = await _load_admin_record_choices(
        request,
        (("base_currency", "currency", base), ("quote_currency", "currency", quote)),
    )

    return templates.TemplateResponse(
        request,
        "reports/fx_lookup.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "lookup": lookup,
            "filters": {
                "base_currency": base or "",
                "quote_currency": quote or "",
            },
            "choices": choices,
        },
    )

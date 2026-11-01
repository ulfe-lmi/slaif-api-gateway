"""Read-only usage ledger reporting service."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Final

from slaif_gateway.db.models import UsageLedger
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.usage import (
    UsageExportRow,
    UsageGroupCostAvailability,
    UsageReportFilters,
    UsageSummaryReport,
    UsageSummaryRow,
)
from slaif_gateway.services.chat_live_burn_telemetry import (
    ChatLiveBurnAggregate,
    aggregate_chat_live_burn_usage,
    parse_chat_live_burn_usage_detail,
)

GROUP_BY_VALUES: Final[set[str]] = {"provider", "model", "provider_model", "owner", "cohort", "key", "day"}


class UsageReportSourceBoundError(ValueError):
    """The accepted report source bound is exceeded by the matching scope.

    214-a: the GUI reporting surface loads matching ledger rows through
    the existing repository query with an OPTIONAL service bound
    (``max_source_rows``) and fetches at most bound+1 rows.  When more
    rows match, the scope is REFUSED with this error instead of being
    silently summarized as a prefix or raced against a separate count.
    The message is fixed and safe (no row values); narrowing help names
    the supported single-value filters only.
    """

    def __init__(self, *, matched_rows: int, source_bound: int) -> None:
        self.matched_rows = matched_rows
        self.source_bound = source_bound
        super().__init__(
            "The usage report scope matches more ledger rows than the "
            f"bounded source limit of {source_bound}. "
            "Narrow the scope with the inclusive UTC start/end time window, "
            "provider, model, owner, cohort, or gateway key filters before "
            "reporting."
        )


class UsageReportService:
    """Generate safe summaries and exports from usage ledger rows.

    The service is read-only: it does not create sessions, commit transactions,
    call providers, or contact external services.
    """

    def __init__(self, *, usage_ledger_repository: UsageLedgerRepository) -> None:
        self._usage = usage_ledger_repository

    async def summarize_usage(
        self,
        *,
        filters: UsageReportFilters | None = None,
        group_by: str = "provider_model",
        limit: int | None = 100,
        max_source_rows: int | None = None,
    ) -> list[UsageSummaryRow]:
        normalized_group_by = _normalize_group_by(group_by)
        rows = await self._usage.list_usage_records(
            **_filters_kwargs(filters),
            limit=(max_source_rows + 1) if max_source_rows is not None else None,
            ascending=True,
        )
        if max_source_rows is not None and len(rows) > max_source_rows:
            raise UsageReportSourceBoundError(
                matched_rows=len(rows), source_bound=max_source_rows
            )
        summaries = _aggregate_rows(rows, group_by=normalized_group_by)
        summaries.sort(key=lambda row: (row.request_count, _timestamp(row.last_seen_at)), reverse=True)
        if limit is not None:
            summaries = summaries[:limit]
        return summaries

    async def summarize_usage_report(
        self,
        *,
        filters: UsageReportFilters | None = None,
        group_by: str = "provider_model",
        limit: int | None = 100,
        max_source_rows: int | None = None,
    ) -> UsageSummaryReport:
        """214-a additive bounded reporting result for the GUI.

        Same bounded source rows, same canonical grouping, and same
        display sort law as :meth:`summarize_usage`; additionally returns
        the per-group cost availability evidence over the COMPLETE
        accepted bounded source set (never only the displayed page of
        groups).  The existing :meth:`summarize_usage` return shape and
        the CLI JSON field set are unchanged.
        """
        normalized_group_by = _normalize_group_by(group_by)
        rows = await self._usage.list_usage_records(
            **_filters_kwargs(filters),
            limit=(max_source_rows + 1) if max_source_rows is not None else None,
            ascending=True,
        )
        if max_source_rows is not None and len(rows) > max_source_rows:
            raise UsageReportSourceBoundError(
                matched_rows=len(rows), source_bound=max_source_rows
            )
        summaries = _aggregate_rows(rows, group_by=normalized_group_by)
        # 214-a: the new GUI result is fully deterministic - the grouping
        # key is unique per group, so it is a stable FINAL tie-break for
        # this result only (the CLI summarize_usage sort contract is
        # unchanged).
        summaries.sort(
            key=lambda row: (
                row.request_count,
                _timestamp(row.last_seen_at),
                row.grouping_key,
            ),
            reverse=True,
        )
        availability_all = _aggregate_cost_availability(rows, group_by=normalized_group_by)
        truncated = limit is not None and len(summaries) > limit
        display = summaries if limit is None else summaries[:limit]
        availability = tuple(availability_all[row.grouping_key] for row in display)
        return UsageSummaryReport(
            group_by=normalized_group_by,
            filters=filters or UsageReportFilters(),
            source_row_count=len(rows),
            rows=tuple(display),
            availability=availability,
            truncated_groups=truncated,
        )

    async def export_usage(
        self,
        *,
        filters: UsageReportFilters | None = None,
        limit: int | None = None,
    ) -> list[UsageExportRow]:
        rows = await self._usage.list_usage_records(
            **_filters_kwargs(filters),
            limit=limit,
            ascending=True,
        )
        return [_to_export_row(row) for row in rows]

    async def summarize_chat_live_burn(
        self,
        *,
        filters: UsageReportFilters | None = None,
        max_source_rows: int | None = None,
    ) -> ChatLiveBurnAggregate:
        rows = await self._usage.list_usage_records(
            **_filters_kwargs(filters),
            limit=(max_source_rows + 1) if max_source_rows is not None else None,
            ascending=True,
        )
        if max_source_rows is not None and len(rows) > max_source_rows:
            raise UsageReportSourceBoundError(
                matched_rows=len(rows), source_bound=max_source_rows
            )
        details = [
            parse_chat_live_burn_usage_detail(
                endpoint=row.endpoint,
                streaming=row.streaming,
                response_metadata=row.response_metadata,
            )
            for row in rows
        ]
        return aggregate_chat_live_burn_usage(details)


def validate_group_by(group_by: str) -> str:
    """Validate and normalize a usage summary group name."""
    return _normalize_group_by(group_by)


def _normalize_group_by(group_by: str) -> str:
    normalized = group_by.strip().lower()
    if normalized not in GROUP_BY_VALUES:
        allowed = ", ".join(sorted(GROUP_BY_VALUES))
        raise ValueError(f"--group-by must be one of: {allowed}")
    return normalized


def _filters_kwargs(filters: UsageReportFilters | None) -> dict[str, object]:
    selected = filters or UsageReportFilters()
    return {
        "start_at": selected.start_at,
        "end_at": selected.end_at,
        "provider": _clean_optional(selected.provider),
        "model": _clean_optional(selected.model),
        "owner_id": selected.owner_id,
        "cohort_id": selected.cohort_id,
        "gateway_key_id": selected.gateway_key_id,
    }


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _aggregate_rows(rows: Iterable[UsageLedger], *, group_by: str) -> list[UsageSummaryRow]:
    grouped: dict[str, UsageSummaryRow] = {}
    for row in rows:
        key, label = _group_key_and_label(row, group_by=group_by)
        current = grouped.get(key)
        provider_reported_cost = _provider_reported_cost(row)
        if current is None:
            grouped[key] = UsageSummaryRow(
                grouping_key=key,
                grouping_label=label,
                request_count=1,
                success_count=1 if row.success is True else 0,
                failure_count=1 if row.success is False else 0,
                prompt_tokens=int(row.prompt_tokens or 0),
                completion_tokens=int(row.completion_tokens or 0),
                total_tokens=int(row.total_tokens or 0),
                cached_tokens=int(row.cached_tokens or 0),
                reasoning_tokens=int(row.reasoning_tokens or 0),
                estimated_cost_eur=_decimal_or_zero(row.estimated_cost_eur),
                actual_cost_eur=_decimal_or_zero(row.actual_cost_eur),
                provider_reported_cost=provider_reported_cost,
                first_seen_at=row.created_at,
                last_seen_at=row.created_at,
            )
            continue

        grouped[key] = replace(
            current,
            request_count=current.request_count + 1,
            success_count=current.success_count + (1 if row.success is True else 0),
            failure_count=current.failure_count + (1 if row.success is False else 0),
            prompt_tokens=current.prompt_tokens + int(row.prompt_tokens or 0),
            completion_tokens=current.completion_tokens + int(row.completion_tokens or 0),
            total_tokens=current.total_tokens + int(row.total_tokens or 0),
            cached_tokens=current.cached_tokens + int(row.cached_tokens or 0),
            reasoning_tokens=current.reasoning_tokens + int(row.reasoning_tokens or 0),
            estimated_cost_eur=current.estimated_cost_eur + _decimal_or_zero(row.estimated_cost_eur),
            actual_cost_eur=current.actual_cost_eur + _decimal_or_zero(row.actual_cost_eur),
            provider_reported_cost=_sum_optional_decimals(current.provider_reported_cost, provider_reported_cost),
            first_seen_at=_min_datetime(current.first_seen_at, row.created_at),
            last_seen_at=_max_datetime(current.last_seen_at, row.created_at),
        )
    return list(grouped.values())


def _group_key_and_label(row: UsageLedger, *, group_by: str) -> tuple[str, str | None]:
    model = row.resolved_model or row.requested_model or "unknown"
    if group_by == "provider":
        return row.provider, row.provider
    if group_by == "model":
        return model, model
    if group_by == "provider_model":
        key = f"{row.provider}:{model}"
        return key, f"{row.provider} / {model}"
    if group_by == "owner":
        key = str(row.owner_id) if row.owner_id is not None else "unknown"
        label = _owner_label(row)
        return key, label
    if group_by == "cohort":
        key = str(row.cohort_id) if row.cohort_id is not None else "unknown"
        return key, row.cohort_name_snapshot or key
    if group_by == "key":
        key = str(row.gateway_key_id)
        return key, key
    if group_by == "day":
        key = row.created_at.date().isoformat()
        return key, key
    raise ValueError(f"Unsupported group_by value: {group_by}")


def _owner_label(row: UsageLedger) -> str:
    parts = [row.owner_name_snapshot, row.owner_surname_snapshot]
    label = " ".join(part for part in parts if part)
    if row.owner_email_snapshot:
        return f"{label} <{row.owner_email_snapshot}>" if label else str(row.owner_email_snapshot)
    return label or (str(row.owner_id) if row.owner_id is not None else "unknown")


def _aggregate_cost_availability(
    rows: Iterable[UsageLedger], *, group_by: str
) -> dict[str, UsageGroupCostAvailability]:
    """Per-group known/missing cost evidence over the same rows/grouping.

    214-a: grouped monetary sums coerce missing values to zero, so the
    rendered total alone cannot prove every row carried a known cost.
    This projection reuses the SAME rows and the SAME canonical
    grouping law (no companion query, no money recomputation) and only
    counts known versus missing per group.
    """
    grouped: dict[str, UsageGroupCostAvailability] = {}
    for row in rows:
        key, label = _group_key_and_label(row, group_by=group_by)
        current = grouped.get(key)
        estimated_known = row.estimated_cost_eur is not None
        actual_known = row.actual_cost_eur is not None
        provider_reported_known = _provider_reported_cost(row) is not None
        if current is None:
            grouped[key] = UsageGroupCostAvailability(
                grouping_key=key,
                grouping_label=label,
                row_count=1,
                estimated_cost_known_count=1 if estimated_known else 0,
                estimated_cost_missing_count=0 if estimated_known else 1,
                actual_cost_known_count=1 if actual_known else 0,
                actual_cost_missing_count=0 if actual_known else 1,
                provider_reported_cost_known_count=1 if provider_reported_known else 0,
                provider_reported_cost_missing_count=0 if provider_reported_known else 1,
            )
            continue
        grouped[key] = replace(
            current,
            row_count=current.row_count + 1,
            estimated_cost_known_count=current.estimated_cost_known_count + (1 if estimated_known else 0),
            estimated_cost_missing_count=current.estimated_cost_missing_count + (0 if estimated_known else 1),
            actual_cost_known_count=current.actual_cost_known_count + (1 if actual_known else 0),
            actual_cost_missing_count=current.actual_cost_missing_count + (0 if actual_known else 1),
            provider_reported_cost_known_count=(
                current.provider_reported_cost_known_count + (1 if provider_reported_known else 0)
            ),
            provider_reported_cost_missing_count=(
                current.provider_reported_cost_missing_count + (0 if provider_reported_known else 1)
            ),
        )
    return grouped


def _provider_reported_cost(row: UsageLedger) -> Decimal | None:
    metadata = row.response_metadata or {}
    for key in ("provider_reported_cost", "provider_reported_cost_native"):
        value = metadata.get(key)
        if value is None:
            continue
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    return None


def _decimal_or_zero(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal("0")


def _sum_optional_decimals(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None:
        return right
    if right is None:
        return left
    return left + right


def _min_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _max_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _timestamp(value: datetime | None) -> float:
    return value.timestamp() if value is not None else 0


def _to_export_row(row: UsageLedger) -> UsageExportRow:
    chat_live_burn = parse_chat_live_burn_usage_detail(
        endpoint=row.endpoint,
        streaming=row.streaming,
        response_metadata=row.response_metadata,
    )
    return UsageExportRow(
        created_at=row.created_at,
        request_id=row.request_id,
        gateway_key_id=row.gateway_key_id,
        owner_id=row.owner_id,
        cohort_id=row.cohort_id,
        provider=row.provider,
        requested_model=row.requested_model,
        resolved_model=row.resolved_model,
        endpoint=row.endpoint,
        streaming=row.streaming,
        success=row.success,
        accounting_status=row.accounting_status,
        prompt_tokens=int(row.prompt_tokens or 0),
        completion_tokens=int(row.completion_tokens or 0),
        total_tokens=int(row.total_tokens or 0),
        cached_tokens=int(row.cached_tokens or 0),
        reasoning_tokens=int(row.reasoning_tokens or 0),
        estimated_cost_eur=row.estimated_cost_eur,
        actual_cost_eur=row.actual_cost_eur,
        native_currency=row.native_currency,
        upstream_request_id=row.upstream_request_id,
        chat_live_burn_triggered=chat_live_burn.triggered if chat_live_burn is not None else False,
        chat_live_burn_stop_reason=chat_live_burn.stop_reason if chat_live_burn is not None else None,
        chat_live_burn_estimated_tokens_at_stop=(
            chat_live_burn.estimated_tokens_at_stop if chat_live_burn is not None else None
        ),
        chat_live_burn_estimated_cost_eur_at_stop=(
            chat_live_burn.estimated_cost_eur_at_stop if chat_live_burn is not None else None
        ),
        chat_live_burn_cost_margin_eur=chat_live_burn.cost_margin_eur if chat_live_burn is not None else None,
        chat_live_burn_token_margin=chat_live_burn.token_margin if chat_live_burn is not None else None,
        chat_live_burn_final_provider_usage_available=(
            chat_live_burn.final_provider_usage_available if chat_live_burn is not None else None
        ),
    )

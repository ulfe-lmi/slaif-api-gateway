"""Typer commands for safe usage ledger reports."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from io import StringIO
from pathlib import Path
from typing import Annotated

import typer

from slaif_gateway.cli.common import (
    cli_db_session,
    emit_json,
    handle_cli_error,
    json_default,
    parse_datetime,
    parse_uuid,
    require_positive_limit,
    run_async,
)
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.schemas.usage import UsageExportRow, UsageReportFilters, UsageSummaryRow
from slaif_gateway.services.usage_report_service import UsageReportService, validate_group_by

app = typer.Typer(help="Inspect and export usage ledger reports")

_EXPORT_COLUMNS = [
    "created_at",
    "request_id",
    "gateway_key_id",
    "owner_id",
    "cohort_id",
    "provider",
    "requested_model",
    "resolved_model",
    "endpoint",
    "streaming",
    "success",
    "accounting_status",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "estimated_cost_eur",
    "actual_cost_eur",
    "native_currency",
    "upstream_request_id",
]


def _service(session) -> UsageReportService:
    return UsageReportService(usage_ledger_repository=UsageLedgerRepository(session))


async def _summarize_usage(
    *,
    filters: UsageReportFilters,
    group_by: str,
    limit: int,
) -> list[UsageSummaryRow]:
    async with cli_db_session() as (_, session):
        return await _service(session).summarize_usage(
            filters=filters,
            group_by=group_by,
            limit=limit,
        )


async def _export_usage(
    *,
    filters: UsageReportFilters,
    limit: int | None,
) -> list[UsageExportRow]:
    async with cli_db_session() as (_, session):
        return await _service(session).export_usage(filters=filters, limit=limit)


@app.callback()
def usage() -> None:
    """Inspect and export usage ledger reports."""


@app.command("summarize")
def summarize(
    start_at: Annotated[str | None, typer.Option("--start-at", help="Inclusive ISO created_at lower bound")] = None,
    end_at: Annotated[str | None, typer.Option("--end-at", help="Inclusive ISO created_at upper bound")] = None,
    provider: Annotated[str | None, typer.Option("--provider", help="Provider filter")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Requested or resolved model filter")] = None,
    owner_id: Annotated[str | None, typer.Option("--owner-id", help="Owner UUID filter")] = None,
    cohort_id: Annotated[str | None, typer.Option("--cohort-id", help="Cohort UUID filter")] = None,
    key_id: Annotated[str | None, typer.Option("--key-id", help="Gateway key UUID filter")] = None,
    group_by: Annotated[str, typer.Option("--group-by", help="provider, model, provider_model, owner, cohort, key, day")] = "provider_model",
    limit: Annotated[int, typer.Option("--limit", help="Maximum summary rows to return")] = 100,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Summarize usage ledger counts, tokens, and costs."""
    try:
        require_positive_limit(limit)
        normalized_group_by = validate_group_by(group_by)
        filters = _parse_filters(
            start_at=start_at,
            end_at=end_at,
            provider=provider,
            model=model,
            owner_id=owner_id,
            cohort_id=cohort_id,
            key_id=key_id,
        )
        rows = run_async(_summarize_usage(filters=filters, group_by=normalized_group_by, limit=limit))
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=json_output)
        return

    payload = [_row_dict(row) for row in rows]
    if json_output:
        emit_json({"usage_summary": payload})
        return
    _emit_summary_table(rows)


@app.command("export")
def export(
    start_at: Annotated[str | None, typer.Option("--start-at", help="Inclusive ISO created_at lower bound")] = None,
    end_at: Annotated[str | None, typer.Option("--end-at", help="Inclusive ISO created_at upper bound")] = None,
    provider: Annotated[str | None, typer.Option("--provider", help="Provider filter")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Requested or resolved model filter")] = None,
    owner_id: Annotated[str | None, typer.Option("--owner-id", help="Owner UUID filter")] = None,
    cohort_id: Annotated[str | None, typer.Option("--cohort-id", help="Cohort UUID filter")] = None,
    key_id: Annotated[str | None, typer.Option("--key-id", help="Gateway key UUID filter")] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Maximum records to export")] = None,
    output_format: Annotated[str, typer.Option("--format", help="csv or json")] = "csv",
    output: Annotated[Path | None, typer.Option("--output", help="Write export to this file")] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing output file")] = False,
) -> None:
    """Export safe usage ledger rows as CSV or JSON."""
    try:
        if limit is not None:
            require_positive_limit(limit)
        normalized_format = _normalize_format(output_format)
        filters = _parse_filters(
            start_at=start_at,
            end_at=end_at,
            provider=provider,
            model=model,
            owner_id=owner_id,
            cohort_id=cohort_id,
            key_id=key_id,
        )
        rows = run_async(_export_usage(filters=filters, limit=limit))
        rendered = _render_export(rows, output_format=normalized_format)
        _write_or_echo(rendered, output=output, force=force)
    except Exception as exc:  # noqa: BLE001
        handle_cli_error(exc, json_output=False)


def _parse_filters(
    *,
    start_at: str | None,
    end_at: str | None,
    provider: str | None,
    model: str | None,
    owner_id: str | None,
    cohort_id: str | None,
    key_id: str | None,
) -> UsageReportFilters:
    parsed_start = parse_datetime(start_at, field_name="start_at")
    parsed_end = parse_datetime(end_at, field_name="end_at")
    if parsed_start is not None and parsed_end is not None and parsed_end < parsed_start:
        raise typer.BadParameter("end_at must be greater than or equal to start_at")
    return UsageReportFilters(
        start_at=parsed_start,
        end_at=parsed_end,
        provider=provider,
        model=model,
        owner_id=parse_uuid(owner_id, field_name="owner_id") if owner_id else None,
        cohort_id=parse_uuid(cohort_id, field_name="cohort_id") if cohort_id else None,
        gateway_key_id=parse_uuid(key_id, field_name="key_id") if key_id else None,
    )


def _normalize_format(output_format: str) -> str:
    normalized = output_format.strip().lower()
    if normalized not in {"csv", "json"}:
        raise typer.BadParameter("--format must be csv or json")
    return normalized


def _row_dict(row: UsageSummaryRow | UsageExportRow) -> dict[str, object]:
    return asdict(row)


def _emit_summary_table(rows: list[UsageSummaryRow]) -> None:
    if not rows:
        typer.echo("No usage records found.")
        return
    typer.echo(
        "grouping_key\tgrouping_label\trequest_count\tsuccess_count\tfailure_count\t"
        "prompt_tokens\tcompletion_tokens\ttotal_tokens\testimated_cost_eur\tactual_cost_eur"
    )
    for row in rows:
        typer.echo(
            "\t".join(
                (
                    row.grouping_key,
                    row.grouping_label or "",
                    str(row.request_count),
                    str(row.success_count),
                    str(row.failure_count),
                    str(row.prompt_tokens),
                    str(row.completion_tokens),
                    str(row.total_tokens),
                    str(row.estimated_cost_eur),
                    str(row.actual_cost_eur),
                )
            )
        )


def _render_export(rows: list[UsageExportRow], *, output_format: str) -> str:
    payload = [_row_dict(row) for row in rows]
    if output_format == "json":
        return json.dumps(payload, default=json_default, sort_keys=True) + "\n"

    handle = StringIO()
    writer = csv.DictWriter(handle, fieldnames=_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in payload:
        writer.writerow({column: _csv_value(row.get(column)) for column in _EXPORT_COLUMNS})
    return handle.getvalue()


def _csv_value(value: object) -> object:
    if value is None:
        return ""
    return json_default(value) if not isinstance(value, (str, int, bool)) else value


def _write_or_echo(content: str, *, output: Path | None, force: bool) -> None:
    if output is None:
        typer.echo(content, nl=False)
        return
    if output.exists() and not force:
        raise ValueError("Output file already exists. Use --force to overwrite it.")
    output.write_text(content, encoding="utf-8")
    typer.echo(f"Wrote {output}")

"""Safe metadata-only audit, finance, project, and SIEM export builders."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True, slots=True)
class ExportColumn:
    name: str


FINANCE_COLUMNS = (
    ExportColumn("timestamp"), ExportColumn("organization_id"), ExportColumn("team_id"),
    ExportColumn("project_id"), ExportColumn("owner_id"), ExportColumn("gateway_key_id"),
    ExportColumn("provider"), ExportColumn("model"), ExportColumn("input_tokens"),
    ExportColumn("output_tokens"), ExportColumn("cost_eur"),
)
SECURITY_COLUMNS = (
    ExportColumn("timestamp"), ExportColumn("event_type"), ExportColumn("admin_user_id"),
    ExportColumn("entity_type"), ExportColumn("entity_id"),
)
PROJECT_COLUMNS = (
    ExportColumn("timestamp"), ExportColumn("project_id"), ExportColumn("provider"),
    ExportColumn("model"), ExportColumn("tool_name"), ExportColumn("tokens"),
)
SIEM_JSON_COLUMNS = (
    ExportColumn("timestamp"), ExportColumn("event_type"), ExportColumn("subject_type"),
    ExportColumn("subject_id"), ExportColumn("outcome"),
)


def _safe_cell(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _row_values(columns: tuple[ExportColumn, ...], row: Mapping[str, object]) -> list[object]:
    return [_safe_cell(row.get(column.name)) for column in columns]


def to_csv(columns: tuple[ExportColumn, ...], rows: Iterable[Mapping[str, object]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([column.name for column in columns])
    for row in rows:
        writer.writerow(_row_values(columns, row))
    return output.getvalue()


def to_json(rows: Iterable[Mapping[str, object]]) -> str:
    return json.dumps(list(rows), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def to_cef(rows: Iterable[Mapping[str, object]]) -> str:
    lines: list[str] = []
    for row in rows:
        timestamp = _timestamp_text(row.get("timestamp"))
        event = _safe_token(row.get("event_type"), "unknown")
        subject = _safe_token(row.get("subject_id"), "unknown")
        outcome = _safe_token(row.get("outcome"), "unknown")
        lines.append(
            f"CEF:0|SLAIF|Gateway|1.0|{event}|{subject}|5|outcome={outcome} rt={timestamp}"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def anonymize_owner_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Replace direct owner identifiers with stable pseudonymous markers."""
    mapping: dict[object, str] = {}
    result: list[dict[str, object]] = []
    for row in rows:
        copied = dict(row)
        owner = copied.get("owner_id")
        if owner is not None:
            marker = mapping.setdefault(owner, f"owner-{len(mapping) + 1}")
            copied["owner_id"] = marker
        result.append(copied)
    return result


def _safe_token(value: object, fallback: str) -> str:
    text = str(value) if value is not None else fallback
    return text.replace("|", "\\|").replace("=", "\\=").replace("\n", " ").replace("\r", " ") or fallback


def _timestamp_text(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "unknown")

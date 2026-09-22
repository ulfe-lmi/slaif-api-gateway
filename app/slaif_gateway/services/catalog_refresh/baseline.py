"""Read-only consistent PostgreSQL baseline export and baseline loading.

The export is an allowlisted metadata snapshot: provider configuration
metadata, model routes, pricing rules, and FX rates with validity windows.
It is deliberately not an ORM dump or a settings dump: secrets, credentials,
users, sessions, request content, free-form notes, and unrelated data are
never exported. Provider secret environment variable *names* may be retained
(names only); provider/source URLs are sanitized (credentials and query
tokens stripped).

The unkeyed SHA-256 content digest over the canonical rows is an *integrity
check* on the document bytes: it detects later modification, but it is NOT
"self-authenticating", NOT authentication, and NOT proof that the baseline
is current or that SQL was executed at any particular time. The
``sql_checked`` flag records that SQL was executed *when this document was
exported* (a historical capture fact); a review that consumes the document
from a file must state that separately.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse, urlunparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from slaif_gateway.schemas.catalog_refresh import (
    BaselineCounts,
    BaselineDocument,
    BaselineFxRow,
    BaselinePricingRow,
    BaselineProviderRow,
    BaselineRouteRow,
    BaselineTarget,
    validate_strict_capabilities,
)
from slaif_gateway.services.catalog_refresh.errors import (
    CatalogRefreshBlockedError,
)

MAX_BASELINE_BYTES = 32 * 1024 * 1024

_PG_VERSION_PATTERN = re.compile(r"^\d+(\.\d+){0,2}")


def _normalize_pg_version(raw: str) -> str:
    """Reduce SHOW server_version output (e.g. '16.15 (Ubuntu ...)') to '16.15'."""
    match = _PG_VERSION_PATTERN.match(raw.strip())
    if match is None:
        raise CatalogRefreshBlockedError(
            "baseline_export_failed", "unrecognized PostgreSQL server_version"
        )
    return match.group(0)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key {key!r}")
        seen.add(key)
        result[key] = value
    return result


def _reject_non_finite(token: str) -> Any:
    raise ValueError(f"non-finite JSON value {token!r}")


def load_baseline(raw: bytes) -> BaselineDocument:
    """Parse and validate an exported baseline document."""
    from pydantic import ValidationError

    if len(raw) > MAX_BASELINE_BYTES:
        raise CatalogRefreshBlockedError(
            "baseline_too_large", "baseline exceeds the 32 MiB bound"
        )
    try:
        text_payload = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CatalogRefreshBlockedError(
            "baseline_not_utf8", "baseline is not valid UTF-8"
        ) from exc
    try:
        payload = json.loads(
            text_payload,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise CatalogRefreshBlockedError("baseline_invalid_json", str(exc)) from exc
    try:
        document = BaselineDocument.model_validate(payload)
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(loc) for loc in error.get('loc', ()))}: {error.get('msg', 'invalid')}"
            for error in exc.errors()[:8]
        )
        raise CatalogRefreshBlockedError(
            "baseline_schema_invalid", errors[:4000]
        ) from exc
    recomputed = hashlib.sha256(
        canonical_baseline_content(document)
    ).hexdigest()
    if recomputed != document.content_sha256:
        raise CatalogRefreshBlockedError(
            "baseline_digest_mismatch",
            "baseline content digest does not match the document content",
        )
    return document


def canonical_baseline_content(baseline: BaselineDocument) -> bytes:
    """Stable content digest input: target identity + rows, never exported_at."""
    payload = {
        "target": baseline.target.model_dump(mode="json"),
        "counts": baseline.counts.model_dump(mode="json"),
        "providers": [row.model_dump(mode="json") for row in baseline.providers],
        "routes": [row.model_dump(mode="json") for row in baseline.routes],
        "pricing": [row.model_dump(mode="json") for row in baseline.pricing],
        "fx": [row.model_dump(mode="json") for row in baseline.fx],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _strict_capabilities(value: Any, *, row_id: str) -> dict[str, bool]:
    """Validate route capabilities to a strict allowlisted shape.

    A non-conforming value fails the export with a safe, explicit issue
    (row identity only — never the offending value) instead of being
    silently truncated.
    """
    try:
        return validate_strict_capabilities(dict(value) if value else {}, field="capabilities")
    except ValueError as exc:
        raise CatalogRefreshBlockedError(
            "baseline_capability_malformed",
            f"route row {row_id} carries a non-conforming capabilities value: {exc}",
        ) from exc


def _sanitize_export_url(value: str | None, *, field: str, row_id: str) -> str | None:
    """Sanitize a provider/source URL for export.

    Only http(s) URLs with a host are retained. Userinfo (credentials) and
    query/fragment (tokens) are stripped; the environment-variable name of a
    provider secret is handled separately and never derived from the URL.
    """
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise CatalogRefreshBlockedError(
            "baseline_url_malformed",
            f"{field} on row {row_id} is not a safe http(s) URL",
        )
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    sanitized = urlunparse((parsed.scheme, netloc, parsed.path or "", "", "", ""))
    return sanitized


def _target_parts_from_url(database_url: str) -> tuple[str, int, str, str]:
    """Return (host, port, database, engine_url) keeping credentials out of scope."""
    parsed = urlparse(database_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    database = (parsed.path or "/").lstrip("/")
    if not database:
        raise CatalogRefreshBlockedError(
            "baseline_target_invalid", "database URL must name a database"
        )
    engine_url = database_url
    if engine_url.startswith("postgresql://"):
        engine_url = engine_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif engine_url.startswith("postgres://"):
        engine_url = engine_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if not engine_url.startswith("postgresql+asyncpg://"):
        raise CatalogRefreshBlockedError(
            "baseline_target_invalid", "database URL must use the postgres/asyncpg scheme"
        )
    return host, port, database, engine_url


async def export_baseline(
    database_url: str, *, now: datetime, page_size: int = 500
) -> BaselineDocument:
    """Read-only consistent export in one REPEATABLE READ transaction.

    Raises CatalogRefreshBlockedError on connection failure or consistency
    mismatch — a connection failure must never become an empty bootstrap.
    """
    if page_size <= 0 or page_size > 5000:
        raise CatalogRefreshBlockedError("baseline_page_invalid", "page_size must be in 1..5000")
    server_host, server_port, database, engine_url = _target_parts_from_url(database_url)
    engine: AsyncEngine = create_async_engine(
        engine_url, isolation_level="REPEATABLE READ", pool_pre_ping=True
    )
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                server_version = _normalize_pg_version(
                    str(
                        (
                            await connection.execute(text("SHOW server_version"))
                        ).scalar_one()
                    )
                )
                counts = {
                    name: (
                        await connection.execute(text(f"SELECT COUNT(*) FROM {name}"))
                    ).scalar_one()
                    for name in ("provider_configs", "model_routes", "pricing_rules", "fx_rates")
                }
                providers = await _page_rows(
                    connection,
                    "provider_configs",
                    "id",
                    (
                        "id, provider, display_name, kind, base_url, api_key_env_var, "
                        "enabled, timeout_seconds, max_retries, created_at, updated_at"
                    ),
                    counts["provider_configs"],
                    page_size,
                )
                routes = await _page_rows(
                    connection,
                    "model_routes",
                    "id",
                    (
                        "id, requested_model, match_type, endpoint, provider, upstream_model, "
                        "priority, enabled, visible_in_models, supports_streaming, capabilities, "
                        "created_at, updated_at"
                    ),
                    counts["model_routes"],
                    page_size,
                )
                pricing = await _page_rows(
                    connection,
                    "pricing_rules",
                    "id",
                    (
                        "id, provider, upstream_model, endpoint, currency, input_price_per_1m, "
                        "cached_input_price_per_1m, output_price_per_1m, reasoning_price_per_1m, "
                        "request_price, valid_from, valid_until, enabled, "
                        "source_url, created_at, updated_at"
                    ),
                    counts["pricing_rules"],
                    page_size,
                )
                fx = await _page_rows(
                    connection,
                    "fx_rates",
                    "id",
                    "id, base_currency, quote_currency, rate, valid_from, valid_until, source, created_at",
                    counts["fx_rates"],
                    page_size,
                )
    except CatalogRefreshBlockedError:
        raise
    except Exception as exc:  # noqa: BLE001 - connection/schema failures must stay safe
        raise CatalogRefreshBlockedError(
            "baseline_export_failed", f"read-only export failed: {type(exc).__name__}"
        ) from exc
    finally:
        await engine.dispose()

    provider_rows = tuple(
        BaselineProviderRow(
            id=str(row["id"]),
            provider=row["provider"],
            display_name=row["display_name"],
            kind=row["kind"],
            base_url=_sanitize_export_url(row["base_url"], field="base_url", row_id=str(row["id"])),
            api_key_env_var=row["api_key_env_var"],
            enabled=bool(row["enabled"]),
            timeout_seconds=int(row["timeout_seconds"]),
            max_retries=int(row["max_retries"]),
            created_at=_aware(row["created_at"]),
            updated_at=_aware(row["updated_at"]),
        )
        for row in providers
    )
    route_rows = tuple(
        BaselineRouteRow(
            id=str(row["id"]),
            requested_model=row["requested_model"],
            match_type=row["match_type"],
            endpoint=row["endpoint"],
            provider=row["provider"],
            upstream_model=row["upstream_model"],
            priority=int(row["priority"]),
            enabled=bool(row["enabled"]),
            visible_in_models=bool(row["visible_in_models"]),
            supports_streaming=bool(row["supports_streaming"]),
            capabilities=_strict_capabilities(row["capabilities"], row_id=str(row["id"])),
            created_at=_aware(row["created_at"]),
            updated_at=_aware(row["updated_at"]),
        )
        for row in routes
    )
    pricing_rows = tuple(
        BaselinePricingRow(
            id=str(row["id"]),
            provider=row["provider"],
            upstream_model=row["upstream_model"],
            endpoint=row["endpoint"],
            currency=row["currency"],
            input_price_per_1m=None if row["input_price_per_1m"] is None else str(row["input_price_per_1m"]),
            cached_input_price_per_1m=None if row["cached_input_price_per_1m"] is None else str(row["cached_input_price_per_1m"]),
            output_price_per_1m=None if row["output_price_per_1m"] is None else str(row["output_price_per_1m"]),
            reasoning_price_per_1m=None if row["reasoning_price_per_1m"] is None else str(row["reasoning_price_per_1m"]),
            request_price=None if row["request_price"] is None else str(row["request_price"]),
            valid_from=_aware(row["valid_from"]),
            valid_until=None if row["valid_until"] is None else _aware(row["valid_until"]),
            enabled=bool(row["enabled"]),
            source_url=_sanitize_export_url(row["source_url"], field="source_url", row_id=str(row["id"])),
            created_at=_aware(row["created_at"]),
            updated_at=_aware(row["updated_at"]),
        )
        for row in pricing
    )
    fx_rows = tuple(
        BaselineFxRow(
            id=str(row["id"]),
            base_currency=row["base_currency"],
            quote_currency=row["quote_currency"],
            rate=str(row["rate"]),
            valid_from=_aware(row["valid_from"]),
            valid_until=None if row["valid_until"] is None else _aware(row["valid_until"]),
            source=_sanitize_export_url(row["source"], field="source", row_id=str(row["id"])),
            created_at=_aware(row["created_at"]),
        )
        for row in fx
    )
    baseline = BaselineDocument(
        schema_version="1",
        exported_at=now.astimezone(UTC),
        target=BaselineTarget(
            server_host=server_host,
            server_port=server_port,
            database=database,
            postgres_version=server_version,
        ),
        sql_checked=True,
        counts=BaselineCounts(
            providers=len(provider_rows),
            routes=len(route_rows),
            pricing_rules=len(pricing_rows),
            fx_rates=len(fx_rows),
        ),
        content_sha256="0" * 64,
        providers=provider_rows,
        routes=route_rows,
        pricing=pricing_rows,
        fx=fx_rows,
    )
    digest = hashlib.sha256(
        canonical_baseline_content(
            baseline.model_copy(update={"content_sha256": "0" * 64})
        )
    ).hexdigest()
    return baseline.model_copy(update={"content_sha256": digest})


async def _page_rows(
    connection: Any,
    table: str,
    id_column: str,
    columns: str,
    expected_count: int,
    page_size: int,
) -> list[Any]:
    """Keyset pagination; refuses silent truncation by cross-checking counts."""
    rows: list[Any] = []
    last_id = "00000000-0000-0000-0000-000000000000"
    while True:
        statement = text(
            f"SELECT {columns} FROM {table} WHERE {id_column} > :last_id "
            f"ORDER BY {id_column} LIMIT :page_size"
        )
        batch = [
            dict(row._mapping)
            for row in (
                await connection.execute(
                    statement, {"last_id": last_id, "page_size": page_size}
                )
            ).all()
        ]
        rows.extend(batch)
        if len(batch) < page_size:
            break
        last_id = str(batch[-1][id_column])
    if len(rows) != expected_count:
        raise CatalogRefreshBlockedError(
            "baseline_consistency_mismatch",
            f"{table}: expected {expected_count} rows, exported {len(rows)}",
        )
    return rows


def _aware(value: Any) -> datetime:
    if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
        return value.replace(tzinfo=UTC)
    return value

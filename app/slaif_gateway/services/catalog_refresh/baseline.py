"""Read-only consistent PostgreSQL baseline export and baseline loading.

The export is an allowlisted metadata snapshot: provider configuration
metadata, model routes, pricing rules, and FX rates with validity windows.
It is deliberately not an ORM dump or a settings dump: secrets, credentials,
users, sessions, request content, free-form notes, and unrelated data are
never exported. Provider secret environment variable *names* may be retained
(names only); provider/source URLs are sanitized (credentials and query
tokens stripped).

Route capabilities are projected to the recognized runtime contract
(endpoint-family boolean blocks, the typed Codex limits/compaction
contracts, and the typed external-tools policy) with bounded allowlists,
preserving nested structure and effective meaning; anything unrepresentable
is flagged on the row with a fingerprint of the raw map as a safe opaque
comparison identity, never silently discarded as unchanged. Pricing
metadata is projected to the typed allowlisted monetary fields the runtime
consumes (audio output pricing, Codex cache-write/long-context accounting,
selected hosted fee); unrepresentable monetary metadata flags the row. FX
source values are either sanitized URLs or safe normalized legacy labels;
free-form text is not carried.

The unkeyed SHA-256 content digest over the canonical rows is an *integrity
check* on the document bytes: it detects later modification, but it is NOT
"self-authenticating", NOT authentication, and NOT proof that the baseline
is current or that SQL was executed at any particular time. The
``sql_checked`` flag records that SQL was executed *when this document was
exported* (a historical capture fact); a review that consumes the document
from a file must state that separately.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse, urlunparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from slaif_gateway.schemas.catalog_refresh import (
    CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY,
    CODEX_LIMITS_KEY,
    BaselineCounts,
    BaselineDocument,
    BaselineFxRow,
    BaselinePricingRow,
    BaselineProviderRow,
    BaselineRouteRow,
    BaselineTarget,
    _CAPABILITY_BOOL_BLOCKS,
    parse_decimal_text,
    parse_codex_compaction_compatible_route_ids,
    parse_codex_route_limits,
    parse_route_external_tool_policy,
    DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
)
from slaif_gateway.services.catalog_refresh.errors import (
    CatalogRefreshBlockedError,
    safe_schema_error_text,
)
from slaif_gateway.utils.redaction import redact_text

MAX_BASELINE_BYTES = 32 * 1024 * 1024
_FX_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

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
            # Constant message: the (untrusted) key name is never echoed.
            raise ValueError("duplicate JSON key")
        seen.add(key)
        result[key] = value
    return result


def _reject_non_finite(_token: str) -> Any:
    raise ValueError("non-finite JSON value")


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
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise CatalogRefreshBlockedError("baseline_invalid_json", str(exc)) from exc
    try:
        document = BaselineDocument.model_validate(payload)
    except ValidationError as exc:
        # Pydantic locations/messages may carry untrusted input;
        # render a bounded, safe form (see safe_schema_error_text).
        raise CatalogRefreshBlockedError(
            "baseline_schema_invalid", safe_schema_error_text(exc)
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


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def project_route_capabilities(raw: Any) -> tuple[dict[str, Any], bool]:
    """Project a runtime capabilities map to the canonical baseline shape.

    Returns (canonical, unrepresented). Recognized endpoint-family blocks are
    projected strictly with bounded allowlists (known fields, exact types,
    contract-parsed Codex limits/compaction IDs/external tools); anything
    unrepresentable is dropped from the public document and flagged instead
    of being silently claimed unchanged.
    """
    canonical: dict[str, Any] = {}
    unrepresented = False
    if raw is None:
        return canonical, False
    if not isinstance(raw, Mapping):
        return canonical, True
    for key, value in raw.items():
        if key in _CAPABILITY_BOOL_BLOCKS and isinstance(value, Mapping):
            block: dict[str, bool] = {}
            for inner_key, inner in value.items():
                if (
                    isinstance(inner_key, str)
                    and inner_key in _CAPABILITY_BOOL_BLOCKS[key]
                    and isinstance(inner, bool)
                ):
                    block[inner_key] = inner
            if len(block) != len(value):
                unrepresented = True
            else:
                canonical[key] = dict(sorted(block.items()))
        elif key == CODEX_LIMITS_KEY:
            try:
                parse_codex_route_limits({CODEX_LIMITS_KEY: value})
            except Exception:  # noqa: BLE001 - contract parser raises typed errors
                unrepresented = True
            else:
                canonical[key] = {k: value[k] for k in sorted(value)}
        elif key == CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY:
            try:
                ids = parse_codex_compaction_compatible_route_ids(
                    {CODEX_COMPACTION_COMPATIBLE_ROUTE_IDS_KEY: value}
                )
            except Exception:  # noqa: BLE001
                unrepresented = True
            else:
                canonical[key] = sorted(str(route_id) for route_id in ids)
        elif key == "external_tools":
            result = parse_route_external_tool_policy(
                value, ceilings=DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
            )
            if result.valid and result.policy is not None:
                canonical["external_tools"] = result.policy.to_metadata()
            else:
                unrepresented = True
        else:
            unrepresented = True
    return canonical, unrepresented


def capabilities_fingerprint(raw: Any) -> str:
    """Safe opaque comparison identity of a raw capabilities map."""
    return hashlib.sha256(_canonical_json_bytes(raw if raw is not None else {})).hexdigest()


def classify_fx_source(value: str | None) -> tuple[str | None, str | None]:
    """Classify an FX source value into (sanitized_url, safe_label).

    Actual http(s) URLs are sanitized (credentials/query/fragment stripped).
    Safe legacy labels (bounded lowercase alnum/._-, not secret-looking) are
    normalized and retained as typed labels. Anything else is free-form text
    and is not carried into the public document.
    """
    if value is None:
        return None, None
    text = value.strip()
    if not text:
        return None, None
    parsed = urlparse(text)
    if parsed.scheme in ("http", "https") and parsed.hostname:
        return _sanitize_export_url(text, field="fx.source", row_id="<fx>"), None
    label = text.lower()
    if not _FX_LABEL_PATTERN.fullmatch(label):
        return None, None
    if label.startswith(
        ("sk-", "sk_", "sk-or-", "bearer ", "authorization ", "password", "secret", "api_key", "apikey")
    ):
        return None, None
    if redact_text(label) != label:
        return None, None
    return None, label


_METADATA_AUDIO_KEY = "audio_output_price_per_1m"
_METADATA_CODEX_KEY = "codex_accounting"
_METADATA_EXTERNAL_TOOL_KEY = "external_tool_pricing"
_EXTERNAL_TOOL_PRICE_KEY = "openai_web_search_call_price_native"
_EXTERNAL_TOOL_SOURCE = "openai_published_per_call"
_CODEX_LONG_FIELDS = (
    "long_context_threshold_tokens",
    "long_context_input_multiplier",
    "long_context_output_multiplier",
)
_CODEX_CACHE_FIELDS = ("cache_write_input_price_per_1m", "cache_write_input_multiplier")
_METADATA_ALLOWLIST = frozenset(
    {_METADATA_AUDIO_KEY, _METADATA_CODEX_KEY, _METADATA_EXTERNAL_TOOL_KEY}
)


def _project_codex_accounting(raw: Any) -> dict[str, Any] | None:
    """Strict typed projection of the runtime codex_accounting contract."""
    if not isinstance(raw, Mapping):
        return None
    fields = {str(key) for key in raw}
    cache_fields = fields.intersection(_CODEX_CACHE_FIELDS)
    expected = set(_CODEX_LONG_FIELDS) | cache_fields
    # Mirror the runtime contract exactly: EXACTLY ONE cache-write field
    # (price or multiplier) plus the full long-context set, nothing else.
    # A long-context-only mapping is not a valid runtime row.
    if len(cache_fields) != 1 or fields != expected:
        return None
    threshold = raw.get("long_context_threshold_tokens")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold <= 0:
        return None
    projected: dict[str, Any] = {"long_context_threshold_tokens": threshold}
    for name in ("long_context_input_multiplier", "long_context_output_multiplier"):
        value = raw.get(name)
        if not isinstance(value, str):
            return None
        try:
            normalized = parse_decimal_text(value, field=f"pricing.{name}", non_negative=True)
        except ValueError:
            return None
        if Decimal(normalized) <= 0:
            return None
        projected[name] = normalized
    for name in _CODEX_CACHE_FIELDS:
        if name not in raw:
            continue
        value = raw[name]
        if not isinstance(value, str):
            return None
        try:
            projected[name] = parse_decimal_text(value, field=f"pricing.{name}", non_negative=True)
        except ValueError:
            return None
    return projected


def _project_external_tool(raw: Any) -> dict[str, Any] | None:
    """Strict typed projection of the selected hosted-fee contract."""
    if not isinstance(raw, Mapping) or set(raw) != {_EXTERNAL_TOOL_PRICE_KEY, "source"}:
        return None
    if raw.get("source") != _EXTERNAL_TOOL_SOURCE:
        return None
    price = raw.get(_EXTERNAL_TOOL_PRICE_KEY)
    if isinstance(price, bool) or isinstance(price, float) or not isinstance(price, (str, int)):
        return None
    try:
        normalized = parse_decimal_text(
            str(price) if isinstance(price, int) else price,
            field="pricing.external_tool_price_per_call",
            non_negative=True,
        )
    except ValueError:
        return None
    return {"external_tool_price_per_call": normalized, "external_tool_source": _EXTERNAL_TOOL_SOURCE}


def project_pricing_metadata(metadata: Any) -> dict[str, Any]:
    """Project pricing_metadata to the typed allowlisted monetary fields.

    Returns the BaselinePricingRow monetary metadata fields plus
    "unrepresented": True when the metadata carries keys or values outside
    the recognized monetary contract. Free-form values are never carried
    into the public document.
    """
    result: dict[str, Any] = {
        "audio_output_price_per_1m": None,
        "cache_write_input_price_per_1m": None,
        "cache_write_input_multiplier": None,
        "long_context_threshold_tokens": None,
        "long_context_input_multiplier": None,
        "long_context_output_multiplier": None,
        "external_tool_price_per_call": None,
        "external_tool_source": None,
        "unrepresented": False,
    }
    if metadata is None:
        return result
    if not isinstance(metadata, Mapping):
        result["unrepresented"] = True
        return result
    for key in metadata:
        if key not in _METADATA_ALLOWLIST:
            result["unrepresented"] = True
    value = metadata.get(_METADATA_AUDIO_KEY)
    if value is not None:
        if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int)):
            result["unrepresented"] = True
        else:
            try:
                result["audio_output_price_per_1m"] = parse_decimal_text(
                    str(value) if isinstance(value, int) else value,
                    field="pricing.audio_output_price_per_1m",
                    non_negative=True,
                )
            except ValueError:
                result["unrepresented"] = True
    codex = metadata.get(_METADATA_CODEX_KEY)
    if codex is not None:
        projected = _project_codex_accounting(codex)
        if projected is None:
            result["unrepresented"] = True
        else:
            result.update(projected)
    tool = metadata.get(_METADATA_EXTERNAL_TOOL_KEY)
    if tool is not None:
        projected = _project_external_tool(tool)
        if projected is None:
            result["unrepresented"] = True
        else:
            result.update(projected)
    return result


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


def _classify_fx_source_export(value: str | None, *, row_id: str) -> tuple[str | None, str | None]:
    fx_source, fx_label = classify_fx_source(value)
    if fx_source is None and fx_label is None and value is not None and value.strip():
        # Free-form text is not carried; the row identity is named, never the value.
        raise CatalogRefreshBlockedError(
            "baseline_fx_source_unsafe",
            f"fx row {row_id} carries a source value that is neither a safe URL nor a safe label; it is not exported",
        )
    return fx_source, fx_label


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
                        "request_price, pricing_metadata, valid_from, valid_until, enabled, "
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
            capabilities=project_route_capabilities(row["capabilities"])[0],
            capabilities_unrepresented=project_route_capabilities(row["capabilities"])[1],
            capabilities_fingerprint=capabilities_fingerprint(row["capabilities"]),
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
            **{
                key: value
                for key, value in project_pricing_metadata(row["pricing_metadata"]).items()
                if key != "unrepresented"
            },
            pricing_metadata_unrepresented=bool(
                project_pricing_metadata(row["pricing_metadata"])["unrepresented"]
            ),
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
            source=_classify_fx_source_export(row["source"], row_id=str(row["id"]))[0],
            source_label=_classify_fx_source_export(row["source"], row_id=str(row["id"]))[1],
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

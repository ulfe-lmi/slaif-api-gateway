"""Admin-only OpenAI-assisted catalog proposal generation."""

from __future__ import annotations

import csv
import fnmatch
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse

import httpx

from slaif_gateway.services.hosted_tool_policy import is_search_specific_chat_completion_model
from slaif_gateway.services.model_route_service import normalize_endpoint
from slaif_gateway.utils.redaction import redact_text

DEFAULT_OPENAI_PRICING_SOURCE_URL = "https://platform.openai.com/docs/pricing"
DEFAULT_OPENAI_MODELS_SOURCE_URL = "https://platform.openai.com/docs/models/compare"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_ADMIN_DISCOVERY_API_KEY_ENV_VAR = "OPENAI_ADMIN_DISCOVERY_API_KEY"
DEFAULT_OPENAI_ASSISTED_MODEL = "gpt-5.5"
OFFICIAL_OPENAI_SOURCE_DOMAINS = (
    "developers.openai.com",
    "platform.openai.com",
    "openai.com",
)
PROPOSAL_WARNING = (
    "LLM-assisted proposal only. Review before import. "
    "This does not mutate SLAIF metadata."
)

_CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"
_DISALLOWED_ROUTE_ENDPOINTS = {"/v1/responses", "/v1/completions"}
_DISALLOWED_ROUTE_CATEGORIES = {
    "responses_only",
    "responses-only",
    "responses only",
    "embeddings_only",
    "embeddings-only",
    "embeddings only",
    "embedding_only",
    "embedding-only",
    "embedding only",
    "image_only",
    "image-only",
    "image only",
    "audio_only",
    "audio-only",
    "audio only",
    "moderation_only",
    "moderation-only",
    "moderation only",
    "realtime_only",
    "realtime-only",
    "realtime only",
    "batch_only",
    "batch-only",
    "batch only",
}

_PRICING_TSV_FIELDS = (
    "provider",
    "model",
    "endpoint",
    "currency",
    "input_price_per_1m",
    "cached_input_price_per_1m",
    "output_price_per_1m",
    "reasoning_price_per_1m",
    "request_price",
    "valid_from",
    "source_url",
    "source_retrieved_at",
    "pricing_metadata",
    "notes",
)

_ROUTE_TSV_FIELDS = (
    "requested_model",
    "match_type",
    "endpoint",
    "provider",
    "upstream_model",
    "priority",
    "enabled",
    "visible_in_models",
    "supports_streaming",
    "capabilities",
    "notes",
)


@dataclass(frozen=True, slots=True)
class OpenAIAssistedProposalResult:
    """Safe result summary for one generated proposal file."""

    output_path: Path
    proposal_type: str
    row_count: int
    warnings: tuple[str, ...]
    source_urls: tuple[str, ...]
    next_steps: tuple[str, ...] = (
        "inspect TSV",
        "run pricing/routes import preview",
        "execute import only with confirmation and audit reason",
    )


@dataclass(frozen=True, slots=True)
class OpenAIAssistedProposalTextResult:
    """Safe proposal text returned to admin UI without writing local metadata."""

    proposal_type: str
    tsv_text: str
    row_count: int
    warnings: tuple[str, ...]
    source_urls: tuple[str, ...]
    next_steps: tuple[str, ...] = (
        "inspect TSV",
        "run pricing/routes import preview",
        "execute import only with confirmation and audit reason",
    )


async def generate_openai_pricing_proposal(
    *,
    output_path: Path,
    source_url: str,
    models_source_url: str,
    api_key_env_var: str,
    proposal_model: str,
    currency: str,
    endpoint: str,
    include_models: Sequence[str],
    exclude_models: Sequence[str],
    max_web_calls: int,
    overwrite: bool,
    http_client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
) -> OpenAIAssistedProposalResult:
    """Generate a reviewed pricing TSV proposal file without touching local metadata."""
    _validate_output_path(output_path, overwrite=overwrite)
    text_result = await generate_openai_pricing_proposal_text(
        source_url=source_url,
        models_source_url=models_source_url,
        api_key_env_var=api_key_env_var,
        proposal_model=proposal_model,
        currency=currency,
        endpoint=endpoint,
        include_models=include_models,
        exclude_models=exclude_models,
        max_web_calls=max_web_calls,
        http_client=http_client,
        now=now,
    )
    _write_proposal_file(output_path, text_result.tsv_text, overwrite=overwrite)
    return OpenAIAssistedProposalResult(
        output_path=output_path,
        proposal_type=text_result.proposal_type,
        row_count=text_result.row_count,
        warnings=text_result.warnings,
        source_urls=text_result.source_urls,
        next_steps=text_result.next_steps,
    )


async def generate_openai_pricing_proposal_text(
    *,
    source_url: str,
    models_source_url: str,
    api_key_env_var: str,
    proposal_model: str,
    currency: str,
    endpoint: str,
    include_models: Sequence[str],
    exclude_models: Sequence[str],
    max_web_calls: int,
    http_client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
) -> OpenAIAssistedProposalTextResult:
    """Generate a reviewed pricing TSV proposal text without touching local metadata."""
    _validate_official_source_url(source_url)
    _validate_official_source_url(models_source_url)
    normalized_currency = _normalize_currency(currency)
    normalized_endpoint = normalize_endpoint(endpoint)
    if normalized_endpoint in _DISALLOWED_ROUTE_ENDPOINTS:
        raise ValueError("pricing proposals cannot target /v1/responses or /v1/completions")
    if normalized_endpoint != _CHAT_COMPLETIONS_ENDPOINT:
        raise ValueError("only OpenAI Chat Completions pricing proposals are supported")
    _require_positive_max_web_calls(max_web_calls)

    payload = await _call_openai_for_json(
        api_key_env_var=api_key_env_var,
        proposal_model=proposal_model,
        prompt=_pricing_prompt(
            source_url=source_url,
            models_source_url=models_source_url,
            currency=normalized_currency,
            endpoint=normalized_endpoint,
            include_models=include_models,
            exclude_models=exclude_models,
            max_web_calls=max_web_calls,
        ),
        schema=_pricing_response_schema(),
        http_client=http_client,
    )
    retrieved_at = _proposal_timestamp(now)
    rows, warnings, source_urls = _pricing_rows_from_payload(
        payload,
        proposal_model=proposal_model,
        currency=normalized_currency,
        endpoint=normalized_endpoint,
        include_models=include_models,
        exclude_models=exclude_models,
        retrieved_at=retrieved_at,
    )
    if not rows:
        raise ValueError("OpenAI pricing proposal contained no importable rows")

    text = _render_tsv(_PRICING_TSV_FIELDS, rows)
    return OpenAIAssistedProposalTextResult(
        proposal_type="pricing",
        tsv_text=text,
        row_count=len(rows),
        warnings=tuple(warnings),
        source_urls=tuple(source_urls),
    )


async def generate_openai_route_proposal(
    *,
    output_path: Path,
    source_url: str,
    api_key_env_var: str,
    proposal_model: str,
    include_models: Sequence[str],
    exclude_models: Sequence[str],
    implemented_endpoints_only: bool,
    overwrite: bool,
    http_client: httpx.AsyncClient | None = None,
) -> OpenAIAssistedProposalResult:
    """Generate a reviewed route TSV proposal file without touching local metadata."""
    _validate_output_path(output_path, overwrite=overwrite)
    text_result = await generate_openai_route_proposal_text(
        source_url=source_url,
        api_key_env_var=api_key_env_var,
        proposal_model=proposal_model,
        include_models=include_models,
        exclude_models=exclude_models,
        implemented_endpoints_only=implemented_endpoints_only,
        http_client=http_client,
    )
    _write_proposal_file(output_path, text_result.tsv_text, overwrite=overwrite)
    return OpenAIAssistedProposalResult(
        output_path=output_path,
        proposal_type=text_result.proposal_type,
        row_count=text_result.row_count,
        warnings=text_result.warnings,
        source_urls=text_result.source_urls,
        next_steps=text_result.next_steps,
    )


async def generate_openai_route_proposal_text(
    *,
    source_url: str,
    api_key_env_var: str,
    proposal_model: str,
    include_models: Sequence[str],
    exclude_models: Sequence[str],
    implemented_endpoints_only: bool,
    http_client: httpx.AsyncClient | None = None,
) -> OpenAIAssistedProposalTextResult:
    """Generate a reviewed route TSV proposal text without touching local metadata."""
    _validate_official_source_url(source_url)

    payload = await _call_openai_for_json(
        api_key_env_var=api_key_env_var,
        proposal_model=proposal_model,
        prompt=_route_prompt(
            source_url=source_url,
            include_models=include_models,
            exclude_models=exclude_models,
            implemented_endpoints_only=implemented_endpoints_only,
        ),
        schema=_route_response_schema(),
        http_client=http_client,
    )
    rows, warnings, source_urls = _route_rows_from_payload(
        payload,
        include_models=include_models,
        exclude_models=exclude_models,
        implemented_endpoints_only=implemented_endpoints_only,
    )
    if not rows:
        raise ValueError("OpenAI route proposal contained no importable rows")

    text = _render_tsv(_ROUTE_TSV_FIELDS, rows)
    return OpenAIAssistedProposalTextResult(
        proposal_type="route",
        tsv_text=text,
        row_count=len(rows),
        warnings=tuple(warnings),
        source_urls=tuple(source_urls),
    )


async def _call_openai_for_json(
    *,
    api_key_env_var: str,
    proposal_model: str,
    prompt: str,
    schema: dict[str, object],
    http_client: httpx.AsyncClient | None,
) -> dict[str, object]:
    if api_key_env_var == "OPENAI_API_KEY":
        raise ValueError("OPENAI_API_KEY is reserved for client gateway keys")
    api_key = os.getenv(api_key_env_var)
    if not api_key or not api_key.strip():
        raise ValueError(f"{api_key_env_var} is not configured")
    if _looks_like_secret(api_key_env_var):
        raise ValueError("--api-key-env-var must be a safe environment variable name")
    if not proposal_model.strip():
        raise ValueError("--model cannot be empty")

    request_payload = {
        "model": proposal_model.strip(),
        "store": False,
        "include": ["web_search_call.action.sources"],
        "tools": [
            {
                "type": "web_search",
                "search_context_size": "low",
                "filters": {"allowed_domains": list(OFFICIAL_OPENAI_SOURCE_DOMAINS)},
            }
        ],
        "tool_choice": "auto",
        "input": [
            {
                "role": "developer",
                "content": (
                    "Return strict JSON matching the supplied schema. Cite official "
                    "OpenAI source URLs for every row. Do not include secrets, raw "
                    "webpage text, prompts, completions, or chain-of-thought."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema["name"],
                "strict": True,
                "schema": schema["schema"],
            }
        },
    }

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=60.0)
    try:
        response = await client.post(
            OPENAI_RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
            json=request_payload,
        )
        if response.status_code >= 400:
            raise ValueError(f"OpenAI proposal request failed with status {response.status_code}")
        try:
            response_payload = response.json()
        except json.JSONDecodeError as exc:
            raise ValueError("OpenAI proposal response was not JSON") from exc
    finally:
        if owns_client:
            await client.aclose()

    text = _extract_response_text(response_payload)
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("OpenAI proposal JSON could not be parsed") from exc
    if not isinstance(loaded, dict):
        raise ValueError("OpenAI proposal JSON must be an object")
    return dict(loaded)


def _extract_response_text(payload: Mapping[str, object]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    pieces: list[str] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                    pieces.append(str(part["text"]))
    text = "".join(pieces).strip()
    if not text:
        raise ValueError("OpenAI proposal response did not include output text")
    return text


def _pricing_rows_from_payload(
    payload: Mapping[str, object],
    *,
    proposal_model: str,
    currency: str,
    endpoint: str,
    include_models: Sequence[str],
    exclude_models: Sequence[str],
    retrieved_at: str,
) -> tuple[list[dict[str, str]], list[str], list[str]]:
    raw_rows = _required_rows(payload)
    warnings = _safe_warnings(payload)
    source_urls: set[str] = set()
    rows: list[dict[str, str]] = []
    for index, raw_row in enumerate(raw_rows, start=1):
        model = _required_safe_text(raw_row.get("model"), field_name="model", row_number=index)
        if not _model_allowed(model, include_models=include_models, exclude_models=exclude_models):
            warnings.append(f"row {index} skipped by include/exclude model filters: {model}")
            continue
        provider = _required_safe_text(raw_row.get("provider"), field_name="provider", row_number=index)
        if provider != "openai":
            raise ValueError(f"pricing row {index} provider must be openai")
        row_endpoint = normalize_endpoint(
            _required_safe_text(raw_row.get("endpoint"), field_name="endpoint", row_number=index)
        )
        if row_endpoint != endpoint:
            raise ValueError(f"pricing row {index} endpoint must be {endpoint}")
        row_currency = _normalize_currency(
            _required_safe_text(raw_row.get("currency"), field_name="currency", row_number=index)
        )
        if row_currency != currency:
            raise ValueError(f"pricing row {index} currency must be {currency}")
        row_source_urls = _required_source_urls(raw_row.get("source_urls"), row_number=index)
        source_url = _required_source_url(raw_row.get("source_url"), row_number=index)
        if source_url not in row_source_urls:
            row_source_urls.insert(0, source_url)
        source_urls.update(row_source_urls)
        confidence = _confidence(raw_row.get("confidence"), row_number=index)
        metadata = {
            "source_type": "openai_llm_assisted",
            "operator_review_required": True,
            "proposal_model": proposal_model,
            "source_urls": row_source_urls,
            "source_retrieved_at": retrieved_at,
            "confidence": confidence,
        }
        rows.append(
            {
                "provider": "openai",
                "model": model,
                "endpoint": "chat.completions",
                "currency": currency,
                "input_price_per_1m": _required_decimal_text(
                    raw_row.get("input_price_per_1m"),
                    field_name="input_price_per_1m",
                    row_number=index,
                ),
                "cached_input_price_per_1m": _optional_decimal_text(
                    raw_row.get("cached_input_price_per_1m"),
                    field_name="cached_input_price_per_1m",
                    row_number=index,
                ),
                "output_price_per_1m": _required_decimal_text(
                    raw_row.get("output_price_per_1m"),
                    field_name="output_price_per_1m",
                    row_number=index,
                ),
                "reasoning_price_per_1m": _optional_decimal_text(
                    raw_row.get("reasoning_price_per_1m"),
                    field_name="reasoning_price_per_1m",
                    row_number=index,
                ),
                "request_price": _optional_decimal_text(
                    raw_row.get("request_price"),
                    field_name="request_price",
                    row_number=index,
                ),
                "valid_from": _required_safe_text(
                    raw_row.get("valid_from"),
                    field_name="valid_from",
                    row_number=index,
                ),
                "source_url": source_url,
                "source_retrieved_at": retrieved_at,
                "pricing_metadata": _metadata_json(metadata),
                "notes": (
                    "Admin-reviewed local accounting assumption from OpenAI-assisted "
                    "proposal; not invoice-grade truth."
                ),
            }
        )
    return rows, warnings, sorted(source_urls)


def _route_rows_from_payload(
    payload: Mapping[str, object],
    *,
    include_models: Sequence[str],
    exclude_models: Sequence[str],
    implemented_endpoints_only: bool,
) -> tuple[list[dict[str, str]], list[str], list[str]]:
    raw_rows = _required_rows(payload)
    warnings = _safe_warnings(payload)
    source_urls: set[str] = set()
    rows: list[dict[str, str]] = []
    for index, raw_row in enumerate(raw_rows, start=1):
        requested_model = _required_safe_text(
            raw_row.get("requested_model"),
            field_name="requested_model",
            row_number=index,
        )
        if not _model_allowed(
            requested_model,
            include_models=include_models,
            exclude_models=exclude_models,
        ):
            warnings.append(f"row {index} skipped by include/exclude model filters: {requested_model}")
            continue
        category = _optional_safe_text(raw_row.get("model_category"), field_name="model_category", row_number=index)
        if is_search_specific_chat_completion_model(requested_model):
            warnings.append(
                "row "
                f"{index} omitted search-specific model requiring future hosted_web_search policy: "
                f"{requested_model}"
            )
            continue
        if _is_disallowed_route_category(requested_model, category):
            warnings.append(f"row {index} omitted unsupported model category: {requested_model}")
            continue
        endpoint = normalize_endpoint(
            _required_safe_text(raw_row.get("endpoint"), field_name="endpoint", row_number=index)
        )
        if endpoint in _DISALLOWED_ROUTE_ENDPOINTS:
            warnings.append(f"row {index} omitted unsupported gateway endpoint: {endpoint}")
            continue
        if endpoint != _CHAT_COMPLETIONS_ENDPOINT:
            if implemented_endpoints_only:
                warnings.append(f"row {index} omitted non-implemented endpoint: {endpoint}")
                continue
            raise ValueError(f"route row {index} endpoint must be chat.completions")
        supported_endpoints = _source_text_list(raw_row.get("supported_endpoints"), field_name="supported_endpoints")
        normalized_supported = {normalize_endpoint(item) for item in supported_endpoints}
        if implemented_endpoints_only and _CHAT_COMPLETIONS_ENDPOINT not in normalized_supported:
            warnings.append(f"row {index} omitted ambiguous Chat Completions compatibility: {requested_model}")
            continue
        row_source_urls = _required_source_urls(raw_row.get("source_urls"), row_number=index)
        source_urls.update(row_source_urls)
        confidence = _confidence(raw_row.get("confidence"), row_number=index)
        capabilities = {
            "source_type": "openai_llm_assisted",
            "source_urls": row_source_urls,
            "endpoint_compatibility": "v1/chat/completions",
            "confidence": confidence,
        }
        upstream_model = (
            _optional_safe_text(raw_row.get("upstream_model"), field_name="upstream_model", row_number=index)
            or requested_model
        )
        rows.append(
            {
                "requested_model": requested_model,
                "match_type": "exact",
                "endpoint": "chat.completions",
                "provider": "openai",
                "upstream_model": upstream_model,
                "priority": "100",
                "enabled": "true",
                "visible_in_models": "true",
                "supports_streaming": "true"
                if _required_bool(raw_row.get("supports_streaming"), field_name="supports_streaming", row_number=index)
                else "false",
                "capabilities": _metadata_json(capabilities),
                "notes": (
                    "Endpoint compatibility is proposed from official OpenAI docs "
                    "and requires admin review."
                ),
            }
        )
    return rows, warnings, sorted(source_urls)


def _required_rows(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    unknown = set(payload) - {"rows", "warnings"}
    if unknown:
        raise ValueError(f"OpenAI proposal JSON had unexpected top-level fields: {', '.join(sorted(unknown))}")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("OpenAI proposal JSON must include rows")
    result: list[Mapping[str, object]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"OpenAI proposal row {index} must be an object")
        result.append(row)
    return result


def _safe_warnings(payload: Mapping[str, object]) -> list[str]:
    warnings = payload.get("warnings", [])
    if warnings is None:
        return []
    if not isinstance(warnings, list):
        raise ValueError("OpenAI proposal warnings must be a list")
    result: list[str] = []
    for warning in warnings:
        if not isinstance(warning, str):
            raise ValueError("OpenAI proposal warnings must be strings")
        cleaned = warning.strip()
        if cleaned and _looks_like_secret(cleaned):
            raise ValueError("OpenAI proposal warnings must not contain secret-looking values")
        if cleaned:
            result.append(cleaned)
    return result


def _pricing_prompt(
    *,
    source_url: str,
    models_source_url: str,
    currency: str,
    endpoint: str,
    include_models: Sequence[str],
    exclude_models: Sequence[str],
    max_web_calls: int,
) -> str:
    return "\n".join(
        (
            "Generate OpenAI Chat Completions pricing proposal rows for SLAIF.",
            f"Use only official OpenAI sources: {source_url} and {models_source_url}.",
            f"Use at most {max_web_calls} web search calls.",
            f"Endpoint must be {endpoint}; do not emit /v1/responses or /v1/completions rows.",
            f"Currency must be {currency}. Prices must be decimal strings per 1M tokens.",
            "Include only models with official Chat Completions compatibility.",
            f"Include model filters: {list(include_models) or 'none'}.",
            f"Exclude model filters: {list(exclude_models) or 'none'}.",
            "Each row must cite source_url and source_urls from official OpenAI domains.",
        )
    )


def _route_prompt(
    *,
    source_url: str,
    include_models: Sequence[str],
    exclude_models: Sequence[str],
    implemented_endpoints_only: bool,
) -> str:
    endpoint_policy = (
        "Emit only /v1/chat/completions-compatible models."
        if implemented_endpoints_only
        else "Evaluate endpoint compatibility, but still omit unsupported gateway endpoints."
    )
    return "\n".join(
        (
            "Generate OpenAI Chat Completions route proposal rows for SLAIF.",
            f"Use only official OpenAI model documentation: {source_url}.",
            endpoint_policy,
            "Do not emit Responses-only, embeddings-only, image-only, audio-only, "
            "moderation-only, realtime-only, batch-only, /v1/responses, or /v1/completions rows.",
            f"Include model filters: {list(include_models) or 'none'}.",
            f"Exclude model filters: {list(exclude_models) or 'none'}.",
            "Each row must cite source_urls from official OpenAI domains.",
        )
    )


def _pricing_response_schema() -> dict[str, object]:
    row = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "provider": {"type": "string"},
            "model": {"type": "string"},
            "endpoint": {"type": "string"},
            "currency": {"type": "string"},
            "input_price_per_1m": {"type": "string"},
            "cached_input_price_per_1m": {"type": ["string", "null"]},
            "output_price_per_1m": {"type": "string"},
            "reasoning_price_per_1m": {"type": ["string", "null"]},
            "request_price": {"type": ["string", "null"]},
            "valid_from": {"type": "string"},
            "source_url": {"type": "string"},
            "source_urls": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": ["number", "string"]},
        },
        "required": [
            "provider",
            "model",
            "endpoint",
            "currency",
            "input_price_per_1m",
            "cached_input_price_per_1m",
            "output_price_per_1m",
            "reasoning_price_per_1m",
            "request_price",
            "valid_from",
            "source_url",
            "source_urls",
            "confidence",
        ],
    }
    return _response_schema("openai_pricing_proposal", row)


def _route_response_schema() -> dict[str, object]:
    row = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "requested_model": {"type": "string"},
            "model_category": {"type": "string"},
            "endpoint": {"type": "string"},
            "upstream_model": {"type": ["string", "null"]},
            "supports_streaming": {"type": "boolean"},
            "supported_endpoints": {"type": "array", "items": {"type": "string"}},
            "source_urls": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": ["number", "string"]},
        },
        "required": [
            "requested_model",
            "model_category",
            "endpoint",
            "upstream_model",
            "supports_streaming",
            "supported_endpoints",
            "source_urls",
            "confidence",
        ],
    }
    return _response_schema("openai_route_proposal", row)


def _response_schema(name: str, row_schema: dict[str, object]) -> dict[str, object]:
    return {
        "name": name,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "rows": {"type": "array", "items": row_schema},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["rows", "warnings"],
        },
    }


def _validate_output_path(path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ValueError("output file already exists; pass --overwrite to replace it")
    if path.exists() and not path.is_file():
        raise ValueError("output path exists and is not a file")
    if not path.parent.exists():
        raise ValueError("output directory does not exist")


def _write_proposal_file(path: Path, text: str, *, overwrite: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_TRUNC if overwrite else os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise ValueError("output file already exists; pass --overwrite to replace it") from exc
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except OSError as exc:
        raise ValueError("could not write proposal file") from exc


def _render_tsv(fields: Sequence[str], rows: Sequence[Mapping[str, str]]) -> str:
    handle = StringIO()
    writer = csv.DictWriter(handle, fieldnames=list(fields), delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row))
    return handle.getvalue()


def _required_safe_text(value: object, *, field_name: str, row_number: int) -> str:
    text = _optional_safe_text(value, field_name=field_name, row_number=row_number)
    if text is None:
        raise ValueError(f"row {row_number} field {field_name} is required")
    return text


def _optional_safe_text(value: object, *, field_name: str, row_number: int) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"row {row_number} field {field_name} must be a string")
    cleaned = value.strip()
    if not cleaned:
        return None
    if _looks_like_secret(cleaned):
        raise ValueError(f"row {row_number} field {field_name} must not contain secret-looking values")
    return cleaned


def _required_decimal_text(value: object, *, field_name: str, row_number: int) -> str:
    parsed = _optional_decimal_text(value, field_name=field_name, row_number=row_number)
    if parsed == "":
        raise ValueError(f"row {row_number} field {field_name} is required")
    return parsed


def _optional_decimal_text(value: object, *, field_name: str, row_number: int) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise ValueError(f"row {row_number} field {field_name} must be a decimal string")
    normalized = value.strip()
    if not normalized:
        return ""
    try:
        parsed = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"row {row_number} field {field_name} must be a decimal string") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"row {row_number} field {field_name} must be non-negative")
    return str(parsed)


def _required_bool(value: object, *, field_name: str, row_number: int) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"row {row_number} field {field_name} must be boolean")


def _required_source_url(value: object, *, row_number: int) -> str:
    source_url = _required_safe_text(value, field_name="source_url", row_number=row_number)
    _validate_official_source_url(source_url)
    return source_url


def _required_source_urls(value: object, *, row_number: int) -> list[str]:
    urls = _source_text_list(value, field_name="source_urls")
    if not urls:
        raise ValueError(f"row {row_number} source_urls must not be empty")
    for source_url in urls:
        _validate_official_source_url(source_url)
    return urls


def _source_text_list(value: object, *, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain only non-empty strings")
        cleaned = item.strip()
        if _looks_like_secret(cleaned):
            raise ValueError(f"{field_name} must not contain secret-looking values")
        result.append(cleaned)
    return result


def _validate_official_source_url(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("source URLs must be absolute https URLs")
    if parsed.username or parsed.password:
        raise ValueError("source URLs must not contain credentials")
    host = parsed.hostname or ""
    if not any(host == domain or host.endswith(f".{domain}") for domain in OFFICIAL_OPENAI_SOURCE_DOMAINS):
        raise ValueError("source URLs must use official OpenAI domains")


def _confidence(value: object, *, row_number: int) -> str:
    if isinstance(value, int | float | str):
        try:
            parsed = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"row {row_number} confidence must be a decimal") from exc
        if not parsed.is_finite() or parsed < 0 or parsed > 1:
            raise ValueError(f"row {row_number} confidence must be between 0 and 1")
        return str(parsed)
    raise ValueError(f"row {row_number} confidence must be numeric")


def _metadata_json(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"))


def _normalize_currency(value: str) -> str:
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("currency must be a 3-letter code")
    return normalized


def _proposal_timestamp(now: datetime | None) -> str:
    timestamp = now or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    timestamp = timestamp.astimezone(UTC).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")


def _model_allowed(
    model: str,
    *,
    include_models: Sequence[str],
    exclude_models: Sequence[str],
) -> bool:
    if include_models and not any(fnmatch.fnmatchcase(model, pattern) for pattern in include_models):
        return False
    return not any(fnmatch.fnmatchcase(model, pattern) for pattern in exclude_models)


def _is_disallowed_route_category(model: str, category: str | None) -> bool:
    normalized_category = (category or "").strip().lower()
    if normalized_category in _DISALLOWED_ROUTE_CATEGORIES:
        return True
    normalized_model = model.lower()
    return normalized_model.startswith(
        (
            "text-embedding-",
            "gpt-image-",
            "chatgpt-image-",
            "omni-moderation",
            "text-moderation",
            "gpt-realtime",
            "tts-",
            "whisper",
            "sora-",
        )
    ) or "realtime" in normalized_model


def _require_positive_max_web_calls(value: int) -> None:
    if value <= 0:
        raise ValueError("--max-web-calls must be positive")


def _looks_like_secret(value: str) -> bool:
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered.startswith(("bearer ", "sk-", "sk_", "sk-or-")):
        return True
    return redact_text(stripped) != stripped

"""Safe usage profile persistence for future calibration workflows."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from slaif_gateway.db.models import UsageLedger, UsageProfile
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.db.repositories.usage_profiles import UsageProfilesRepository
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.utils.redaction import is_sensitive_key, redact_text
from slaif_gateway.utils.sanitization import REDACTED_VALUE, sanitize_metadata_mapping

_CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"
_CHAT_COMPLETIONS_PROVIDER_PATH = "/chat/completions"
_SAFE_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_COST_SOURCES = {"provider_reported", "slaif_calculated", "mixed", "unknown"}


@dataclass(frozen=True, slots=True)
class UsageProfileToolMetadata:
    """Safe tool metadata extracted from accepted Chat Completions request fields."""

    tool_call_counts: dict[str, int] = field(default_factory=dict)
    function_tool_names: list[str] = field(default_factory=list)


class UsageProfileService:
    """Create safe usage profile rows from finalized usage ledger records."""

    def __init__(
        self,
        *,
        usage_ledger_repository: UsageLedgerRepository,
        usage_profiles_repository: UsageProfilesRepository,
    ) -> None:
        self._usage_ledger_repository = usage_ledger_repository
        self._usage_profiles_repository = usage_profiles_repository

    async def record_from_usage_ledger(
        self,
        usage_ledger_id,
        *,
        route: RouteResolutionResult | None = None,
        provider_endpoint_path: str | None = _CHAT_COMPLETIONS_PROVIDER_PATH,
        tool_metadata: UsageProfileToolMetadata | None = None,
        profile_metadata: Mapping[str, Any] | None = None,
    ) -> UsageProfile | None:
        """Create a profile row for a finalized Chat Completions ledger row.

        Returns ``None`` when the ledger is absent, not finalized, or not a
        successful Chat Completions row. Callers should treat the profile as
        advisory metadata and keep quota/accounting finalization authoritative.
        """
        existing = await self._usage_profiles_repository.get_by_usage_ledger_id(usage_ledger_id)
        if existing is not None:
            return existing

        ledger = await self._usage_ledger_repository.get_usage_record_by_id(usage_ledger_id)
        if ledger is None or not _is_profile_eligible(ledger):
            return None

        provider_host, provider_path = _provider_location(
            route=route,
            fallback_path=provider_endpoint_path,
        )
        response_metadata = _safe_mapping(getattr(ledger, "response_metadata", None))
        provider_reported_cost, provider_reported_currency = _provider_reported_cost(response_metadata)
        slaif_calculated_cost = _decimal_or_none(getattr(ledger, "actual_cost_eur", None))
        cost_source = _cost_source(
            provider_reported_cost=provider_reported_cost,
            slaif_calculated_cost=slaif_calculated_cost,
        )
        metadata = _safe_profile_metadata(
            {
                "profile_version": 1,
                "source": "chat_completions_accounting_finalization",
                "cost_source": cost_source,
                "provider_reported_currency": provider_reported_currency,
                **dict(profile_metadata or {}),
            }
        )
        tools = tool_metadata or UsageProfileToolMetadata()

        return await self._usage_profiles_repository.create_usage_profile(
            usage_ledger_id=ledger.id,
            gateway_key_id=ledger.gateway_key_id,
            owner_id=ledger.owner_id,
            institution_id=ledger.institution_id,
            cohort_id=ledger.cohort_id,
            endpoint_path=ledger.endpoint,
            provider=ledger.provider,
            requested_model=ledger.requested_model,
            resolved_upstream_model=ledger.resolved_model,
            provider_host=provider_host,
            provider_endpoint_path=provider_path,
            input_tokens=int(ledger.input_tokens or ledger.prompt_tokens or 0),
            output_tokens=int(ledger.output_tokens or ledger.completion_tokens or 0),
            total_tokens=int(ledger.total_tokens or 0),
            reasoning_tokens=_nullable_count(getattr(ledger, "reasoning_tokens", None)),
            cached_tokens=_nullable_count(getattr(ledger, "cached_tokens", None)),
            tool_call_counts=dict(tools.tool_call_counts),
            function_tool_names=list(tools.function_tool_names),
            provider_reported_cost=provider_reported_cost,
            slaif_calculated_cost=slaif_calculated_cost,
            cost_currency="EUR" if slaif_calculated_cost is not None else provider_reported_currency,
            cost_source=cost_source,
            gateway_request_id=ledger.request_id,
            profile_metadata=metadata,
        )


def build_chat_completion_tool_metadata(body: Mapping[str, Any] | None) -> UsageProfileToolMetadata:
    """Extract safe counts and function names from accepted request metadata."""
    if body is None:
        return UsageProfileToolMetadata()
    counts: dict[str, int] = {}
    names: set[str] = set()

    tools = body.get("tools")
    if isinstance(tools, Sequence) and not isinstance(tools, str | bytes):
        for tool in tools:
            if not isinstance(tool, Mapping):
                continue
            tool_type = tool.get("type")
            if not isinstance(tool_type, str):
                tool_type = "unknown"
            tool_type = _safe_tool_count_key(tool_type)
            counts[tool_type] = counts.get(tool_type, 0) + 1
            if tool_type == "function":
                name = _function_name_from_tool(tool)
                if name is not None:
                    names.add(name)

    legacy_functions = body.get("functions")
    if isinstance(legacy_functions, Sequence) and not isinstance(legacy_functions, str | bytes):
        for function in legacy_functions:
            if not isinstance(function, Mapping):
                continue
            counts["function"] = counts.get("function", 0) + 1
            name = _safe_function_name(function.get("name"))
            if name is not None:
                names.add(name)

    return UsageProfileToolMetadata(
        tool_call_counts=dict(sorted(counts.items())),
        function_tool_names=sorted(names),
    )


def _is_profile_eligible(ledger: UsageLedger) -> bool:
    return (
        ledger.success is True
        and ledger.accounting_status == "finalized"
        and ledger.endpoint == _CHAT_COMPLETIONS_ENDPOINT
        and int(ledger.total_tokens or 0) >= 0
    )


def _provider_location(
    *,
    route: RouteResolutionResult | None,
    fallback_path: str | None,
) -> tuple[str | None, str | None]:
    base_url = route.provider_base_url if route is not None else None
    host, path = sanitize_provider_url_parts(base_url)
    endpoint_path = sanitize_provider_path(fallback_path) or _CHAT_COMPLETIONS_PROVIDER_PATH
    if path and path != "/":
        endpoint_path = sanitize_provider_path(f"{path.rstrip('/')}/{endpoint_path.lstrip('/')}")
    return host, endpoint_path


def sanitize_provider_url_parts(value: str | None) -> tuple[str | None, str | None]:
    """Return sanitized provider host and path, excluding query/fragment/userinfo."""
    if not value:
        return None, None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None, None
    host = parsed.hostname.lower() if parsed.hostname else None
    if host is not None and parsed.port is not None:
        host = f"{host}:{parsed.port}"
    path = sanitize_provider_path(parsed.path)
    return host, path


def sanitize_provider_path(value: str | None) -> str | None:
    if not value:
        return None
    path = urlsplit(value).path if "?" in value or "#" in value else value
    path = path.strip()
    if not path:
        return "/"
    if not path.startswith("/"):
        path = f"/{path}"
    redacted = redact_text(path)
    if redacted != path or "authorization" in path.lower() or "bearer" in path.lower():
        return None
    return redacted[:256]


def _provider_reported_cost(metadata: Mapping[str, Any]) -> tuple[Decimal | None, str | None]:
    value = metadata.get("provider_reported_cost_native")
    currency = metadata.get("provider_reported_currency")
    return _decimal_or_none(value), str(currency).upper() if isinstance(currency, str) and currency else None


def _cost_source(
    *,
    provider_reported_cost: Decimal | None,
    slaif_calculated_cost: Decimal | None,
) -> str:
    if provider_reported_cost is not None and slaif_calculated_cost is not None:
        return "mixed"
    if provider_reported_cost is not None:
        return "provider_reported"
    if slaif_calculated_cost is not None:
        return "slaif_calculated"
    return "unknown"


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if number < 0:
        return None
    return number


def _nullable_count(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0:
        return None
    return value


def _safe_profile_metadata(metadata: Mapping[str, Any]) -> dict[str, object]:
    sanitized = sanitize_metadata_mapping(metadata, drop_content_keys=True)
    cleaned = _drop_redacted_values(sanitized)
    return cleaned if isinstance(cleaned, dict) else {}


def _drop_redacted_values(value: object) -> object | None:
    if value in (None, REDACTED_VALUE):
        return None
    if isinstance(value, dict):
        cleaned: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or is_sensitive_key(key):
                continue
            child = _drop_redacted_values(item)
            if child is not None:
                cleaned[key] = child
        return cleaned
    if isinstance(value, list):
        return [item for item in (_drop_redacted_values(item) for item in value) if item is not None]
    return value


def _safe_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return sanitize_metadata_mapping(value, drop_content_keys=True)


def _function_name_from_tool(tool: Mapping[str, Any]) -> str | None:
    function = tool.get("function")
    if not isinstance(function, Mapping):
        return None
    return _safe_function_name(function.get("name"))


def _safe_function_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not _SAFE_TOOL_NAME_RE.fullmatch(stripped):
        return None
    if redact_text(stripped) != stripped:
        return None
    if is_sensitive_key(stripped):
        return None
    return stripped


def _safe_tool_count_key(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if not _SAFE_TOOL_NAME_RE.fullmatch(normalized):
        return "unknown"
    if is_sensitive_key(normalized) or redact_text(normalized) != normalized:
        return "unknown"
    return normalized


def validate_cost_source(value: str) -> str:
    """Validate cost source values for tests and future callers."""
    if value not in _COST_SOURCES:
        raise ValueError("Unsupported usage profile cost source")
    return value

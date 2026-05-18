"""Bootstrap workflow for curated OpenAI Completions catalog metadata."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from importlib import resources
from pathlib import Path
from typing import Literal

from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.chat_completion_route_capabilities import (
    ensure_default_chat_completion_capabilities,
)
from slaif_gateway.services.model_route_service import normalize_endpoint
from slaif_gateway.services.pricing_rule_service import PricingRuleService
from slaif_gateway.services.provider_config_service import ProviderConfigService

OPENAI_PROVIDER = "openai"
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
OPENAI_CHAT_COMPLETIONS_CATALOG = "openai_chat_completions_models.json"
PLACEHOLDER_PRICING_NOTE = (
    "Placeholder pricing for smoke tests only; not real pricing and not for production use."
)
REQUIRED_PRICING_COLUMNS = frozenset(
    {
        "provider",
        "model",
        "endpoint",
        "currency",
        "input_price_per_1m",
        "output_price_per_1m",
    }
)

PricingMode = Literal["require-file", "placeholder"]
BootstrapStatus = Literal["created", "exists", "conflict", "missing", "not_implemented"]


@dataclass(frozen=True, slots=True)
class OpenAICompletionsCatalogEntry:
    """One curated model entry for a supported OpenAI Completions endpoint."""

    model_id: str
    upstream_model: str
    endpoint: str
    visible_in_models: bool
    supports_streaming: bool
    legacy_model: bool
    notes: str
    source_note: str

    @property
    def normalized_endpoint(self) -> str:
        return normalize_endpoint(self.endpoint)


@dataclass(frozen=True, slots=True)
class BootstrapRowStatus:
    """Safe row-level status for bootstrap output."""

    status: BootstrapStatus
    model_id: str | None = None
    endpoint: str | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class OpenAICompletionsBootstrapResult:
    """Aggregate result for the OpenAI Completions catalog bootstrap."""

    dry_run: bool
    provider: BootstrapRowStatus
    chat_routes: tuple[BootstrapRowStatus, ...]
    completions_routes: tuple[BootstrapRowStatus, ...]
    pricing: tuple[BootstrapRowStatus, ...]
    selected_models: tuple[str, ...]
    placeholder_pricing: bool

    @property
    def has_blockers(self) -> bool:
        statuses = [self.provider, *self.chat_routes, *self.completions_routes, *self.pricing]
        return any(row.status in {"conflict", "missing"} for row in statuses)


@dataclass(frozen=True, slots=True)
class _PricingInput:
    provider: str
    model: str
    endpoint: str
    currency: str
    input_price_per_1m: Decimal
    output_price_per_1m: Decimal
    notes: str | None = None


def load_openai_chat_completions_catalog(
    *,
    include_legacy_models: bool,
) -> tuple[OpenAICompletionsCatalogEntry, ...]:
    """Load curated OpenAI Chat Completions model metadata from package resources."""
    text = resources.files("slaif_gateway.resources").joinpath(
        OPENAI_CHAT_COMPLETIONS_CATALOG
    ).read_text(encoding="utf-8")
    loaded = json.loads(text)
    if not isinstance(loaded, list):
        raise ValueError("OpenAI Chat Completions catalog must be a list")
    entries = tuple(_catalog_entry(row) for row in loaded)
    selected = [entry for entry in entries if include_legacy_models or not entry.legacy_model]
    return tuple(selected)


def load_pricing_file(path: Path, *, currency: str) -> dict[tuple[str, str, str], _PricingInput]:
    """Read operator-controlled pricing CSV without fetching remote pricing."""
    if not path.exists() or not path.is_file():
        raise ValueError("--pricing-file is required and must point to an existing CSV file")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or ())
        missing = REQUIRED_PRICING_COLUMNS - fieldnames
        if missing:
            fields = ", ".join(sorted(missing))
            raise ValueError(f"Pricing CSV is missing required columns: {fields}")
        rows = list(reader)

    normalized_currency = _normalize_currency(currency)
    result: dict[tuple[str, str, str], _PricingInput] = {}
    for index, row in enumerate(rows, start=2):
        provider = _required_csv_text(row.get("provider"), row_number=index, field_name="provider")
        model = _required_csv_text(row.get("model"), row_number=index, field_name="model")
        endpoint = normalize_endpoint(
            _required_csv_text(row.get("endpoint"), row_number=index, field_name="endpoint")
        )
        row_currency = _normalize_currency(
            _required_csv_text(row.get("currency"), row_number=index, field_name="currency")
        )
        if row_currency != normalized_currency:
            raise ValueError(
                f"Pricing CSV row {index} currency {row_currency} does not match --currency "
                f"{normalized_currency}"
            )
        notes = _optional_csv_text(row.get("notes"), row_number=index, field_name="notes")
        if notes is not None and _looks_like_secret(notes):
            raise ValueError(f"Pricing CSV row {index} notes must not contain secret-looking values")
        key = (provider, model, endpoint)
        if key in result:
            raise ValueError(
                f"Pricing CSV contains duplicate provider/model/endpoint row for {provider} "
                f"{model} {endpoint}"
            )
        result[key] = _PricingInput(
            provider=provider,
            model=model,
            endpoint=endpoint,
            currency=row_currency,
            input_price_per_1m=_required_decimal(
                row.get("input_price_per_1m"),
                row_number=index,
                field_name="input_price_per_1m",
            ),
            output_price_per_1m=_required_decimal(
                row.get("output_price_per_1m"),
                row_number=index,
                field_name="output_price_per_1m",
            ),
            notes=notes,
        )
    return result


async def bootstrap_openai_completions_catalog(
    *,
    provider_configs_repository: ProviderConfigsRepository,
    model_routes_repository: ModelRoutesRepository,
    pricing_rules_repository: PricingRulesRepository,
    audit_repository: AuditRepository,
    api_key_env_var: str,
    currency: str,
    pricing_mode: PricingMode,
    pricing_file_rows: Mapping[tuple[str, str, str], _PricingInput],
    include_legacy_completions: bool,
    include_legacy_models: bool,
    dry_run: bool,
) -> OpenAICompletionsBootstrapResult:
    """Plan or apply local provider, route, and pricing rows for OpenAI chat models."""
    if include_legacy_completions:
        return OpenAICompletionsBootstrapResult(
            dry_run=dry_run,
            provider=BootstrapRowStatus(status="not_implemented", message="not evaluated"),
            chat_routes=(),
            completions_routes=(
                BootstrapRowStatus(
                    status="not_implemented",
                    endpoint="/v1/completions",
                    message="/v1/completions legacy endpoint is not implemented",
                ),
            ),
            pricing=(),
            selected_models=(),
            placeholder_pricing=pricing_mode == "placeholder",
        )

    entries = load_openai_chat_completions_catalog(include_legacy_models=include_legacy_models)
    normalized_currency = _normalize_currency(currency)
    provider_status = await _provider_status(
        provider_configs_repository=provider_configs_repository,
        api_key_env_var=api_key_env_var,
    )
    route_statuses = await _route_statuses(
        model_routes_repository=model_routes_repository,
        entries=entries,
    )
    pricing_statuses = await _pricing_statuses(
        pricing_rules_repository=pricing_rules_repository,
        entries=entries,
        currency=normalized_currency,
        pricing_mode=pricing_mode,
        pricing_file_rows=pricing_file_rows,
    )
    result = OpenAICompletionsBootstrapResult(
        dry_run=dry_run,
        provider=provider_status,
        chat_routes=tuple(route_statuses),
        completions_routes=(
            BootstrapRowStatus(
                status="not_implemented",
                endpoint="/v1/completions",
                message="/v1/completions legacy endpoint is not implemented",
            ),
        ),
        pricing=tuple(pricing_statuses),
        selected_models=tuple(entry.model_id for entry in entries),
        placeholder_pricing=pricing_mode == "placeholder",
    )
    if dry_run or result.has_blockers:
        return result

    provider_service = ProviderConfigService(
        provider_configs_repository=provider_configs_repository,
        audit_repository=audit_repository,
    )
    route_service = _RouteCreationService(model_routes_repository, audit_repository)
    pricing_service = PricingRuleService(
        pricing_rules_repository=pricing_rules_repository,
        audit_repository=audit_repository,
    )
    if provider_status.status == "created":
        await provider_service.create_provider_config(
            provider=OPENAI_PROVIDER,
            display_name="OpenAI",
            base_url=OPENAI_DEFAULT_BASE_URL,
            api_key_env_var=api_key_env_var,
            enabled=True,
            notes="Created by openai-completions-catalog bootstrap.",
            reason="OpenAI Completions catalog bootstrap",
        )
    for entry, status in zip(entries, route_statuses, strict=True):
        if status.status != "created":
            continue
        await route_service.create_entry(entry)
    now = datetime.now(UTC)
    for entry, status in zip(entries, pricing_statuses, strict=True):
        if status.status != "created":
            continue
        pricing_input = _pricing_for_entry(
            entry=entry,
            currency=normalized_currency,
            pricing_mode=pricing_mode,
            pricing_file_rows=pricing_file_rows,
        )
        metadata = {"source": "operator_file", "bootstrap": "openai-completions-catalog"}
        notes = pricing_input.notes or "Imported by openai-completions-catalog bootstrap."
        if pricing_mode == "placeholder":
            metadata = {
                "source": "placeholder",
                "placeholder": True,
                "bootstrap": "openai-completions-catalog",
            }
            notes = PLACEHOLDER_PRICING_NOTE
        await pricing_service.create_pricing_rule(
            provider=OPENAI_PROVIDER,
            model=entry.upstream_model,
            endpoint=entry.normalized_endpoint,
            currency=normalized_currency,
            input_price_per_1m=pricing_input.input_price_per_1m,
            output_price_per_1m=pricing_input.output_price_per_1m,
            cached_input_price_per_1m=None,
            reasoning_price_per_1m=None,
            request_price=None,
            pricing_metadata=metadata,
            valid_from=now,
            valid_until=None,
            source_url=None,
            notes=notes,
            enabled=True,
            reason="OpenAI Completions catalog bootstrap",
        )
    return result


class _RouteCreationService:
    def __init__(
        self,
        model_routes_repository: ModelRoutesRepository,
        audit_repository: AuditRepository,
    ) -> None:
        from slaif_gateway.services.model_route_service import ModelRouteService

        self._service = ModelRouteService(
            model_routes_repository=model_routes_repository,
            audit_repository=audit_repository,
        )

    async def create_entry(self, entry: OpenAICompletionsCatalogEntry) -> None:
        await self._service.create_model_route(
            requested_model=entry.model_id,
            match_type="exact",
            provider=OPENAI_PROVIDER,
            upstream_model=entry.upstream_model,
            priority=100,
            visible_in_models=entry.visible_in_models,
            enabled=True,
            notes=entry.notes,
            endpoint=entry.normalized_endpoint,
            supports_streaming=entry.supports_streaming,
            capabilities=ensure_default_chat_completion_capabilities(
                {
                    "catalog": "openai-completions",
                    "endpoint": entry.endpoint,
                    "source_note": entry.source_note,
                },
                supports_streaming=entry.supports_streaming,
                endpoint=entry.normalized_endpoint,
            ),
            reason="OpenAI Completions catalog bootstrap",
        )


async def _provider_status(
    *,
    provider_configs_repository: ProviderConfigsRepository,
    api_key_env_var: str,
) -> BootstrapRowStatus:
    normalized_env_var = _required_text(api_key_env_var, "API key environment variable")
    if _looks_like_secret(normalized_env_var):
        return BootstrapRowStatus(
            status="conflict",
            message="api key option must be an environment variable name, not a secret value",
        )
    existing = await provider_configs_repository.get_provider_config_by_provider(OPENAI_PROVIDER)
    if existing is None:
        return BootstrapRowStatus(status="created", message="provider will be created")
    if (
        existing.api_key_env_var == normalized_env_var
        and existing.enabled is True
        and existing.base_url == OPENAI_DEFAULT_BASE_URL
    ):
        return BootstrapRowStatus(status="exists", message="provider already exists")
    return BootstrapRowStatus(
        status="conflict",
        message="existing openai provider config differs or is disabled",
    )


async def _route_statuses(
    *,
    model_routes_repository: ModelRoutesRepository,
    entries: Sequence[OpenAICompletionsCatalogEntry],
) -> list[BootstrapRowStatus]:
    statuses: list[BootstrapRowStatus] = []
    for entry in entries:
        existing = await model_routes_repository.list_model_routes(
            endpoint=entry.normalized_endpoint,
            limit=10000,
        )
        matching = [row for row in existing if row.requested_model == entry.model_id]
        if any(_route_matches_catalog(row, entry) for row in matching):
            statuses.append(
                BootstrapRowStatus(
                    status="exists",
                    model_id=entry.model_id,
                    endpoint=entry.normalized_endpoint,
                    message="route already exists",
                )
            )
        elif matching:
            statuses.append(
                BootstrapRowStatus(
                    status="conflict",
                    model_id=entry.model_id,
                    endpoint=entry.normalized_endpoint,
                    message="existing route for model/endpoint differs",
                )
            )
        else:
            statuses.append(
                BootstrapRowStatus(
                    status="created",
                    model_id=entry.model_id,
                    endpoint=entry.normalized_endpoint,
                    message="route will be created",
                )
            )
    return statuses


async def _pricing_statuses(
    *,
    pricing_rules_repository: PricingRulesRepository,
    entries: Sequence[OpenAICompletionsCatalogEntry],
    currency: str,
    pricing_mode: PricingMode,
    pricing_file_rows: Mapping[tuple[str, str, str], _PricingInput],
) -> list[BootstrapRowStatus]:
    statuses: list[BootstrapRowStatus] = []
    for entry in entries:
        pricing_input = _pricing_for_entry(
            entry=entry,
            currency=currency,
            pricing_mode=pricing_mode,
            pricing_file_rows=pricing_file_rows,
        )
        if pricing_input is None:
            statuses.append(
                BootstrapRowStatus(
                    status="missing",
                    model_id=entry.model_id,
                    endpoint=entry.normalized_endpoint,
                    message="pricing file is missing required model/endpoint row",
                )
            )
            continue
        existing = await pricing_rules_repository.list_pricing_rules(
            provider=OPENAI_PROVIDER,
            upstream_model=entry.upstream_model,
            endpoint=entry.normalized_endpoint,
            limit=100,
        )
        enabled_existing = [row for row in existing if row.enabled]
        if any(_pricing_matches(row, pricing_input) for row in enabled_existing):
            statuses.append(
                BootstrapRowStatus(
                    status="exists",
                    model_id=entry.model_id,
                    endpoint=entry.normalized_endpoint,
                    message="pricing already exists",
                )
            )
        elif enabled_existing:
            statuses.append(
                BootstrapRowStatus(
                    status="conflict",
                    model_id=entry.model_id,
                    endpoint=entry.normalized_endpoint,
                    message="enabled pricing rule for model/endpoint differs",
                )
            )
        else:
            statuses.append(
                BootstrapRowStatus(
                    status="created",
                    model_id=entry.model_id,
                    endpoint=entry.normalized_endpoint,
                    message="pricing will be created",
                )
            )
    return statuses


def _pricing_for_entry(
    *,
    entry: OpenAICompletionsCatalogEntry,
    currency: str,
    pricing_mode: PricingMode,
    pricing_file_rows: Mapping[tuple[str, str, str], _PricingInput],
) -> _PricingInput | None:
    if pricing_mode == "placeholder":
        return _PricingInput(
            provider=OPENAI_PROVIDER,
            model=entry.upstream_model,
            endpoint=entry.normalized_endpoint,
            currency=currency,
            input_price_per_1m=Decimal("0"),
            output_price_per_1m=Decimal("0"),
            notes=PLACEHOLDER_PRICING_NOTE,
        )
    return pricing_file_rows.get((OPENAI_PROVIDER, entry.upstream_model, entry.normalized_endpoint))


def _catalog_entry(row: object) -> OpenAICompletionsCatalogEntry:
    if not isinstance(row, dict):
        raise ValueError("OpenAI Chat Completions catalog entries must be objects")
    endpoint = _required_mapping_text(row, "endpoint")
    if endpoint != "chat.completions":
        raise ValueError("OpenAI Chat Completions catalog can only contain chat.completions entries")
    model_id = _required_mapping_text(row, "model_id")
    if _is_non_completions_model_id(model_id):
        raise ValueError(f"Non-Completions model is not allowed in catalog: {model_id}")
    return OpenAICompletionsCatalogEntry(
        model_id=model_id,
        upstream_model=_required_mapping_text(row, "upstream_model"),
        endpoint=endpoint,
        visible_in_models=bool(row.get("visible_in_models")),
        supports_streaming=bool(row.get("supports_streaming")),
        legacy_model=bool(row.get("legacy_model")),
        notes=_required_mapping_text(row, "notes"),
        source_note=_required_mapping_text(row, "source_note"),
    )


def _route_matches_catalog(row: object, entry: OpenAICompletionsCatalogEntry) -> bool:
    return (
        getattr(row, "requested_model", None) == entry.model_id
        and getattr(row, "match_type", None) == "exact"
        and getattr(row, "endpoint", None) == entry.normalized_endpoint
        and getattr(row, "provider", None) == OPENAI_PROVIDER
        and getattr(row, "upstream_model", None) == entry.upstream_model
        and getattr(row, "enabled", None) is True
        and getattr(row, "visible_in_models", None) == entry.visible_in_models
        and getattr(row, "supports_streaming", None) == entry.supports_streaming
    )


def _pricing_matches(row: object, pricing_input: _PricingInput) -> bool:
    return (
        getattr(row, "provider", None) == pricing_input.provider
        and getattr(row, "upstream_model", None) == pricing_input.model
        and getattr(row, "endpoint", None) == pricing_input.endpoint
        and getattr(row, "currency", None) == pricing_input.currency
        and getattr(row, "input_price_per_1m", None) == pricing_input.input_price_per_1m
        and getattr(row, "output_price_per_1m", None) == pricing_input.output_price_per_1m
    )


def _required_mapping_text(row: Mapping[str, object], field_name: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"OpenAI Chat Completions catalog entry missing {field_name}")
    return value.strip()


def _required_csv_text(value: object, *, row_number: int, field_name: str) -> str:
    if value is None:
        raise ValueError(f"Pricing CSV row {row_number} is missing {field_name}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"Pricing CSV row {row_number} field {field_name} cannot be empty")
    return text


def _optional_csv_text(value: object, *, row_number: int, field_name: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "\n" in text or "\r" in text:
        raise ValueError(f"Pricing CSV row {row_number} field {field_name} must be one line")
    return text


def _required_decimal(value: object, *, row_number: int, field_name: str) -> Decimal:
    text = _required_csv_text(value, row_number=row_number, field_name=field_name)
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"Pricing CSV row {row_number} field {field_name} must be a decimal value"
        ) from exc
    if parsed < 0:
        raise ValueError(f"Pricing CSV row {row_number} field {field_name} must be non-negative")
    return parsed


def _required_text(value: str, label: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    return text


def _normalize_currency(value: str) -> str:
    currency = _required_text(value, "Currency").upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("--currency must be a 3-letter code")
    return currency


def _looks_like_secret(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith(("sk-", "sk_", "sk-or-")) or "bearer " in lowered


def _is_non_completions_model_id(model_id: str) -> bool:
    lowered = model_id.lower()
    markers = (
        "embedding",
        "moderation",
        "tts",
        "transcribe",
        "whisper",
        "image",
        "dall-e",
        "realtime",
        "audio",
        "sora",
    )
    return any(marker in lowered for marker in markers)

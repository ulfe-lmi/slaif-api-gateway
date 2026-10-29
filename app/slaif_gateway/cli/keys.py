"""Typer commands for service-backed gateway key management."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

import typer

from slaif_gateway.cli.common import CliError, parse_int_option, write_secret_file
from slaif_gateway.cli.key_policy_files import (
    PROVIDER_ABSENT,
    build_configuration_from_explicit_flags,
    policy_source_callback,
    policy_sources,
    read_policy_file,
    provider_flags_value,
    validate_policy_file_conflicts,
    was_explicit,
)
from slaif_gateway.config import Settings, get_settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.key_templates import KeyTemplatesRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.session import get_sessionmaker
from slaif_gateway.modules.clients.codex_0162 import bootstrap_codex_compatibility_profile
from slaif_gateway.modules.codex_profile_data import CodexProfileDataError
from slaif_gateway.schemas.keys import (
    ActivateGatewayKeyInput,
    CreateGatewayKeyInput,
    CreatedGatewayKey,
    GatewayKeyManagementResult,
    ResetGatewayKeyUsageInput,
    RevokeGatewayKeyInput,
    RotateGatewayKeyInput,
    RotatedGatewayKeyResult,
    SuspendGatewayKeyInput,
    UpdateGatewayKeyChatStreamingLiveBurnInput,
    UpdateGatewayKeyConfigurationInput,
    UpdateGatewayKeyLazyThrottlingInput,
    UpdateGatewayKeyExternalToolPolicyInput,
    UpdateGatewayKeyLimitsInput,
    UpdateGatewayKeyPolicyInput,
    UpdateGatewayKeyRateLimitsInput,
    UpdateGatewayKeyValidityInput,
)
from slaif_gateway.schemas.key_clone import (
    MAX_CLONE_PLAN_FILE_BYTES,
    VALIDITY_ABSOLUTE,
    VALIDITY_COPY_SOURCE_EXPIRY,
    VALIDITY_DURATION_FROM_NOW,
    KeyClonePlan,
    KeyClonePlanError,
    parse_clone_plan_file,
)
from slaif_gateway.services.chat_streaming_live_burn import (
    ChatStreamingLiveBurnPolicyError,
    chat_streaming_live_burn_policy_from_metadata,
    default_chat_streaming_live_burn_policy,
    normalize_chat_streaming_live_burn_policy,
)
from slaif_gateway.services.email_delivery_service import (
    EmailDeliveryService,
    PendingKeyEmailResult,
)
from slaif_gateway.services.email_errors import EmailError
from slaif_gateway.services.email_service import EmailService
from slaif_gateway.services.external_tool_policy_contract import (
    STRICT_BOUNDED,
    parse_key_external_tool_policy,
    strict_key_policy,
)
from slaif_gateway.services.key_errors import GatewayKeyNotFoundError, KeyManagementError
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
    KEY_PURPOSE_TRUSTED_CALIBRATION,
)
from slaif_gateway.services.key_policy_configuration import (
    build_create_gateway_key_input,
)
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.services.key_clone_service import (
    KeyCloneResult,
    KeyCloneService,
)
from slaif_gateway.services.key_policy_inspection import (
    KeyPolicyInspectionContext,
    build_key_policy_inspection,
    explain_model_route_access,
    safe_calibration_metadata_projection,
    safe_freeform_reason_projection,
    safe_provider_policy_projection,
    safe_responses_policy_projection,
)
from slaif_gateway.services.key_template_service import (
    KeyFromTemplateCreationResult,
    KeyTemplateError,
    KeyTemplateService,
)
from slaif_gateway.services.streaming_live_burn_surface import (
    CHAT_STREAMING_LIVE_BURN_SURFACE,
    streaming_live_burn_surface_policy_from_cli_options,
)
from slaif_gateway.cli.email import _PendingKeyEmailTaskSeam
from slaif_gateway.utils.crypto import is_plausible_gateway_key

app = typer.Typer(help="Manage gateway keys")
policy_app = typer.Typer(help="Show or update gateway-key request policy")

# 204-b: the workers task module is NOT imported at CLI module import;
# the deferred-call seam (defined in cli/email.py) keeps this module
# attribute name for the existing test mocks and resolves the fixed
# task only when the enqueue call actually runs.
send_pending_key_email_task = _PendingKeyEmailTaskSeam()

external_tools_app = typer.Typer(help="Show or update deny-by-default external-tool policy")
app.add_typer(policy_app, name="policy")
app.add_typer(external_tools_app, name="external-tools")
# 203-a: reviewed key-configuration batches (plan/apply sub-group).
from slaif_gateway.cli.key_batch import app as key_batch_app  # noqa: E402

app.add_typer(key_batch_app, name="batch")

# Documented page bound for `keys list` (bounded, complete pagination).
MAX_KEY_LIST_LIMIT = 200


class CliKeyError(Exception):
    """Safe CLI-facing key command error."""


class CliDatabaseConfigError(CliKeyError):
    """Raised when CLI database settings are missing or invalid."""


class EmailDeliveryMode(str, Enum):
    """Explicit key email-delivery mode for create/rotate commands."""

    none = "none"
    pending = "pending"
    send_now = "send-now"
    enqueue = "enqueue"


def _bootstrap_codex_profile(settings: Settings) -> None:
    """Bootstrap the configured Codex profile before R4 pin authoring.

    Idempotent for same-config initialization; an invalid configured file
    fails closed with a fixed safe message instead of falling back to the
    packaged default.
    """
    try:
        bootstrap_codex_compatibility_profile(settings.CODEX_COMPATIBILITY_PROFILE_FILE)
    except CodexProfileDataError as exc:
        raise CliKeyError(exc.safe_message) from exc


@dataclass(frozen=True, slots=True)
class KeyEmailDeliveryCliResult:
    """Safe combined metadata for key creation/rotation and optional delivery."""

    key_result: CreatedGatewayKey | RotatedGatewayKeyResult
    delivery_result: PendingKeyEmailResult | None = None
    celery_task_id: str | None = None


@asynccontextmanager
async def _key_runtime() -> AsyncIterator[tuple[Settings, GatewayKeysRepository, KeyService]]:
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError(
            "DATABASE_URL is not configured. Set DATABASE_URL and try again."
        )
    _bootstrap_codex_profile(settings)

    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise CliDatabaseConfigError(str(exc)) from exc

    async with session_factory() as session:
        async with session.begin():
            keys_repository = GatewayKeysRepository(session)
            service = KeyService(
                settings=settings,
                gateway_keys_repository=keys_repository,
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
                model_routes_repository=ModelRoutesRepository(session),
            )
            yield settings, keys_repository, service


@asynccontextmanager
async def _key_email_runtime() -> AsyncIterator[tuple[Settings, KeyService, EmailDeliveryService]]:
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError(
            "DATABASE_URL is not configured. Set DATABASE_URL and try again."
        )
    _bootstrap_codex_profile(settings)

    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise CliDatabaseConfigError(str(exc)) from exc

    async with session_factory() as session:
        async with session.begin():
            keys_repository = GatewayKeysRepository(session)
            one_time_secrets_repository = OneTimeSecretsRepository(session)
            audit_repository = AuditRepository(session)
            key_service = KeyService(
                settings=settings,
                gateway_keys_repository=keys_repository,
                one_time_secrets_repository=one_time_secrets_repository,
                audit_repository=audit_repository,
                model_routes_repository=ModelRoutesRepository(session),
            )
            email_delivery_service = EmailDeliveryService(
                settings=settings,
                one_time_secrets_repository=one_time_secrets_repository,
                email_deliveries_repository=EmailDeliveriesRepository(session),
                gateway_keys_repository=keys_repository,
                owners_repository=OwnersRepository(session),
                audit_repository=audit_repository,
                email_service=EmailService(settings),
            )
            yield settings, key_service, email_delivery_service


@asynccontextmanager
async def _template_key_runtime() -> AsyncIterator[
    tuple[Settings, KeyTemplateService, EmailDeliveryService]
]:
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError(
            "DATABASE_URL is not configured. Set DATABASE_URL and try again."
        )

    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise CliDatabaseConfigError(str(exc)) from exc

    async with session_factory() as session:
        async with session.begin():
            keys_repository = GatewayKeysRepository(session)
            one_time_secrets_repository = OneTimeSecretsRepository(session)
            owners_repository = OwnersRepository(session)
            audit_repository = AuditRepository(session)
            key_service = KeyService(
                settings=settings,
                gateway_keys_repository=keys_repository,
                one_time_secrets_repository=one_time_secrets_repository,
                audit_repository=audit_repository,
                model_routes_repository=ModelRoutesRepository(session),
            )
            email_delivery_service = EmailDeliveryService(
                settings=settings,
                one_time_secrets_repository=one_time_secrets_repository,
                email_deliveries_repository=EmailDeliveriesRepository(session),
                gateway_keys_repository=keys_repository,
                owners_repository=owners_repository,
                audit_repository=audit_repository,
                email_service=EmailService(settings),
            )
            yield (
                settings,
                KeyTemplateService(
                    key_templates_repository=KeyTemplatesRepository(session),
                    audit_repository=audit_repository,
                    key_service=key_service,
                    external_tool_ceilings=(settings.get_external_tool_operator_ceilings()),
                ),
                email_delivery_service,
            )


@asynccontextmanager
async def _policy_inspection_runtime() -> AsyncIterator[
    tuple[Settings, GatewayKeysRepository, KeyPolicyInspectionContext]
]:
    """Read-only runtime for effective-policy inspection and route explanation.

    Opens one session (a read snapshot) and exposes only the repositories the
    inspection service needs. It never constructs a ``KeyService`` and issues
    no writes: the inspection layer is configuration-only by construction.
    """
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError(
            "DATABASE_URL is not configured. Set DATABASE_URL and try again."
        )
    _bootstrap_codex_profile(settings)

    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise CliDatabaseConfigError(str(exc)) from exc

    async with session_factory() as session:
        async with session.begin():
            inspection_context = KeyPolicyInspectionContext(
                model_routes=ModelRoutesRepository(session),
                provider_configs=ProviderConfigsRepository(session),
            )
            yield settings, GatewayKeysRepository(session), inspection_context


@asynccontextmanager
async def _key_clone_runtime() -> AsyncIterator[tuple[Settings, KeyCloneService]]:
    """Caller-owned transaction runtime for the clone plan/execute operation.

    The clone service is flush-only. The surrounding session transaction
    commits the target key, one-time secret, pending delivery, clone
    receipt, and audit rows atomically - or rolls ALL of them back on a
    late failure.
    """
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError(
            "DATABASE_URL is not configured. Set DATABASE_URL and try again."
        )
    _bootstrap_codex_profile(settings)

    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise CliDatabaseConfigError(str(exc)) from exc

    async with session_factory() as session:
        async with session.begin():
            keys_repository = GatewayKeysRepository(session)
            one_time_secrets_repository = OneTimeSecretsRepository(session)
            audit_repository = AuditRepository(session)
            key_service = KeyService(
                settings=settings,
                gateway_keys_repository=keys_repository,
                one_time_secrets_repository=one_time_secrets_repository,
                audit_repository=audit_repository,
                model_routes_repository=ModelRoutesRepository(session),
            )
            email_delivery_service = EmailDeliveryService(
                settings=settings,
                one_time_secrets_repository=one_time_secrets_repository,
                email_deliveries_repository=EmailDeliveriesRepository(session),
                gateway_keys_repository=keys_repository,
                owners_repository=OwnersRepository(session),
                audit_repository=audit_repository,
                email_service=EmailService(settings),
            )
            clone_service = KeyCloneService(
                settings=settings,
                key_service=key_service,
                gateway_keys_repository=keys_repository,
                owners_repository=OwnersRepository(session),
                cohorts_repository=CohortsRepository(session),
                email_delivery_service=email_delivery_service,
                audit_repository=audit_repository,
            )
            yield settings, clone_service


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


def _parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{field_name} must be a valid UUID") from exc


def _parse_datetime(value: str | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise typer.BadParameter(f"{field_name} cannot be empty")
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise typer.BadParameter(f"{field_name} must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_decimal(value: str | None, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise typer.BadParameter(f"{field_name} must be a decimal value") from exc
    return parsed


def _parse_required_decimal(value: str, *, field_name: str) -> Decimal:
    parsed = _parse_decimal(value, field_name=field_name)
    if parsed is None:
        raise typer.BadParameter(f"{field_name} is required")
    return parsed


def _validate_positive_int(value: int | None, *, option_name: str) -> int | None:
    if value is not None and value <= 0:
        raise typer.BadParameter(f"{option_name} must be positive")
    return value


def _rate_limit_policy_from_options(
    *,
    requests_per_minute: int | None = None,
    tokens_per_minute: int | None = None,
    concurrent_requests: int | None = None,
    window_seconds: int | None = None,
) -> dict[str, int] | None:
    policy: dict[str, int] = {}
    if requests_per_minute is not None:
        policy["requests_per_minute"] = (
            _validate_positive_int(
                requests_per_minute,
                option_name="--rate-limit-requests-per-minute",
            )
            or requests_per_minute
        )
    if tokens_per_minute is not None:
        policy["tokens_per_minute"] = (
            _validate_positive_int(
                tokens_per_minute,
                option_name="--rate-limit-tokens-per-minute",
            )
            or tokens_per_minute
        )
    if concurrent_requests is not None:
        policy["max_concurrent_requests"] = (
            _validate_positive_int(
                concurrent_requests,
                option_name="--rate-limit-concurrent-requests",
            )
            or concurrent_requests
        )
    if window_seconds is not None:
        policy["window_seconds"] = (
            _validate_positive_int(
                window_seconds,
                option_name="--rate-limit-window-seconds",
            )
            or window_seconds
        )
    return policy or None


def _chat_streaming_live_burn_policy_from_options(
    *,
    enabled: bool,
    cost_margin_eur: str | None,
    token_margin: int | None,
) -> dict[str, object]:
    try:
        return streaming_live_burn_surface_policy_from_cli_options(
            CHAT_STREAMING_LIVE_BURN_SURFACE,
            enabled=enabled,
            cost_margin_eur=cost_margin_eur,
            token_margin=token_margin,
            max_abs_cost_margin_eur=Decimal("1000000"),
            max_abs_token_margin=1000000000,
        ).to_metadata()
    except ChatStreamingLiveBurnPolicyError as exc:
        raise typer.BadParameter(str(exc), param_hint=exc.param) from exc


def _external_tool_policy_from_options(
    *,
    mode: str,
    capabilities: Sequence[str] | None,
    destination_ids: Sequence[str] | None,
    max_calls: int,
    acknowledge_single_request_overrun: bool,
) -> dict[str, object]:
    if max_calls < 0:
        raise typer.BadParameter("--external-tool-max-calls must be non-negative")
    return {
        "version": 1,
        "mode": mode.strip(),
        "allowed_capabilities": list(capabilities or []),
        "allowed_destination_ids": list(destination_ids or []),
        "max_provider_tool_calls_per_request": max_calls,
        "single_request_overrun_acknowledged": acknowledge_single_request_overrun,
    }


def _valid_until_from_options(
    *,
    valid_from: datetime | None,
    valid_until: str | None,
    valid_days: int | None,
) -> datetime:
    if valid_until is not None and valid_days is not None:
        raise typer.BadParameter("Use either --valid-until or --valid-days, not both")
    if valid_until is None and valid_days is None:
        raise typer.BadParameter("Provide --valid-until or --valid-days")
    if valid_days is not None:
        if valid_days <= 0:
            raise typer.BadParameter("--valid-days must be positive")
        return (valid_from or datetime.now(UTC)) + timedelta(days=valid_days)
    parsed = _parse_datetime(valid_until, field_name="valid_until")
    if parsed is None:
        raise typer.BadParameter("valid_until is required")
    return parsed


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _emit_json(payload: dict[str, object]) -> None:
    typer.echo(json.dumps(payload, default=_json_default, sort_keys=True))


def _safe_gateway_key_dict(gateway_key: GatewayKey) -> dict[str, object]:
    provider_policy = _provider_policy_from_gateway_key(gateway_key)
    return {
        "id": gateway_key.id,
        "public_key_id": gateway_key.public_key_id,
        "key_prefix": gateway_key.key_prefix,
        "key_hint": gateway_key.key_hint,
        "owner_id": gateway_key.owner_id,
        "cohort_id": gateway_key.cohort_id,
        "status": gateway_key.status,
        "valid_from": gateway_key.valid_from,
        "valid_until": gateway_key.valid_until,
        "cost_limit_eur": gateway_key.cost_limit_eur,
        "token_limit_total": gateway_key.token_limit_total,
        "request_limit_total": gateway_key.request_limit_total,
        "cost_used_eur": gateway_key.cost_used_eur,
        "tokens_used_total": gateway_key.tokens_used_total,
        "requests_used_total": gateway_key.requests_used_total,
        "cost_reserved_eur": gateway_key.cost_reserved_eur,
        "tokens_reserved_total": gateway_key.tokens_reserved_total,
        "requests_reserved_total": gateway_key.requests_reserved_total,
        "created_at": gateway_key.created_at,
        "updated_at": gateway_key.updated_at,
        "revoked_at": gateway_key.revoked_at,
        "revoked_reason": safe_freeform_reason_projection(
            gateway_key.revoked_reason
        ),
        "allowed_models": list(gateway_key.allowed_models or []),
        "allowed_endpoints": list(gateway_key.allowed_endpoints or []),
        "allow_all_models": gateway_key.allow_all_models,
        "allow_all_endpoints": gateway_key.allow_all_endpoints,
        "key_purpose": getattr(gateway_key, "key_purpose", "standard"),
        "capability_policy_mode": getattr(gateway_key, "capability_policy_mode", "standard"),
        "calibration_metadata": safe_calibration_metadata_projection(
            getattr(gateway_key, "calibration_metadata", {}) or {}
        ),
        "template_id": getattr(gateway_key, "template_id", None),
        "template_revision_id": getattr(gateway_key, "template_revision_id", None),
        "allowed_providers": provider_policy["allowed_providers"],
        "allow_all_providers": provider_policy["allow_all_providers"],
        "allowed_providers_state": provider_policy["state"],
        "rate_limit_policy": _rate_limit_policy_from_gateway_key(gateway_key),
        "responses_policy": _responses_policy_from_gateway_key(gateway_key),
        "chat_streaming_live_burn_policy": _chat_streaming_live_burn_policy_from_gateway_key(
            gateway_key
        ),
        "external_tool_policy": _external_tool_policy_from_gateway_key(gateway_key),
    }


def _rate_limit_policy_from_gateway_key(gateway_key: GatewayKey) -> dict[str, int] | None:
    policy: dict[str, int] = {}
    requests_per_minute = getattr(gateway_key, "rate_limit_requests_per_minute", None)
    tokens_per_minute = getattr(gateway_key, "rate_limit_tokens_per_minute", None)
    max_concurrent_requests = getattr(gateway_key, "max_concurrent_requests", None)
    if requests_per_minute is not None:
        policy["requests_per_minute"] = requests_per_minute
    if tokens_per_minute is not None:
        policy["tokens_per_minute"] = tokens_per_minute
    if max_concurrent_requests is not None:
        policy["max_concurrent_requests"] = max_concurrent_requests
    metadata_policy = None
    metadata_json = getattr(gateway_key, "metadata_json", None)
    if isinstance(metadata_json, dict):
        metadata_policy = metadata_json.get("rate_limit_policy")
    if isinstance(metadata_policy, dict):
        window_seconds = metadata_policy.get("window_seconds")
        if isinstance(window_seconds, int) and not isinstance(window_seconds, bool):
            policy["window_seconds"] = window_seconds
    return policy or None


def _provider_policy_from_gateway_key(gateway_key: GatewayKey) -> dict[str, object]:
    """SAFE explicit provider state shared with the inspection report.

    Preserves the legitimate ``None`` (unrestricted) versus ``[]`` (deny-all)
    distinction; malformed stored members project to the fixed ``invalid``
    marker instead of being stringified or echoed.
    """
    return safe_provider_policy_projection(getattr(gateway_key, "metadata_json", None))


def _responses_policy_from_gateway_key(gateway_key: GatewayKey) -> dict[str, object] | None:
    """Project the stored Responses policy as safe display data.

    Uses the strict shared 196 authoring validator: a valid block projects to
    its canonical members only; unknown, malformed, or stale blocks project
    to the fixed ``invalid`` marker. No private or unsupported stored value
    is ever copied into CLI output.
    """
    metadata_json = getattr(gateway_key, "metadata_json", None)
    if not isinstance(metadata_json, dict):
        return None
    return safe_responses_policy_projection(metadata_json.get("responses_policy"))


def _chat_streaming_live_burn_policy_from_gateway_key(gateway_key: GatewayKey) -> dict[str, object]:
    metadata_json = getattr(gateway_key, "metadata_json", None)
    try:
        return chat_streaming_live_burn_policy_from_metadata(
            metadata_json if isinstance(metadata_json, dict) else {},
            max_abs_cost_margin_eur=Decimal("1000000"),
            max_abs_token_margin=1000000000,
        ).to_metadata()
    except ChatStreamingLiveBurnPolicyError:
        return default_chat_streaming_live_burn_policy().to_metadata()


def _external_tool_policy_from_gateway_key(gateway_key: GatewayKey) -> dict[str, object]:
    metadata = getattr(gateway_key, "metadata_json", None)
    raw_policy = metadata.get("external_tool_policy") if isinstance(metadata, dict) else None
    parsed = parse_key_external_tool_policy(
        raw_policy,
        ceilings=get_settings().get_external_tool_operator_ceilings(),
    )
    policy = parsed.policy if parsed.valid and parsed.policy is not None else strict_key_policy()
    return policy.to_metadata()


def _management_result_dict(result: GatewayKeyManagementResult) -> dict[str, object]:
    return {
        "gateway_key_id": result.gateway_key_id,
        "public_key_id": result.public_key_id,
        "status": result.status,
        "updated_at": result.updated_at,
        "valid_from": result.valid_from,
        "valid_until": result.valid_until,
        "cost_limit_eur": result.cost_limit_eur,
        "token_limit_total": result.token_limit_total,
        "request_limit_total": result.request_limit_total,
        "cost_used_eur": result.cost_used_eur,
        "tokens_used_total": result.tokens_used_total,
        "requests_used_total": result.requests_used_total,
        "cost_reserved_eur": result.cost_reserved_eur,
        "tokens_reserved_total": result.tokens_reserved_total,
        "requests_reserved_total": result.requests_reserved_total,
        "last_quota_reset_at": result.last_quota_reset_at,
        "quota_reset_count": result.quota_reset_count,
        "rate_limit_policy": result.rate_limit_policy,
        "lazy_throttling_policy": result.lazy_throttling_policy,
        "allowed_models": result.allowed_models,
        "allowed_endpoints": result.allowed_endpoints,
        "allow_all_models": result.allow_all_models,
        "allow_all_endpoints": result.allow_all_endpoints,
        "key_purpose": result.key_purpose,
        "capability_policy_mode": result.capability_policy_mode,
        "chat_streaming_live_burn_policy": result.chat_streaming_live_burn_policy,
        "external_tool_policy": result.external_tool_policy,
        "template_id": getattr(result, "template_id", None),
        "template_revision_id": getattr(result, "template_revision_id", None),
    }


def _created_key_dict(
    result: CreatedGatewayKey, *, include_plaintext: bool = True
) -> dict[str, object]:
    payload: dict[str, object] = {
        "gateway_key_id": result.gateway_key_id,
        "owner_id": result.owner_id,
        "public_key_id": result.public_key_id,
        "display_prefix": result.display_prefix,
        "one_time_secret_id": result.one_time_secret_id,
        "valid_from": result.valid_from,
        "valid_until": result.valid_until,
        "rate_limit_policy": result.rate_limit_policy,
        "chat_streaming_live_burn_policy": result.chat_streaming_live_burn_policy,
        "key_purpose": result.key_purpose,
        "capability_policy_mode": result.capability_policy_mode,
        "external_tool_policy": result.external_tool_policy,
    }
    if include_plaintext:
        payload["plaintext_key"] = result.plaintext_key
    return payload


def _read_bounded_plan_file(path: Path) -> bytes:
    """Read at most ``MAX_CLONE_PLAN_FILE_BYTES + 1`` bytes of a plan file.

    Bounding the read (instead of loading the whole file) keeps an oversized
    file from being fully read before the size limit is enforced. Errors are
    fixed and safe; they never echo the path or file contents.
    """
    cap = MAX_CLONE_PLAN_FILE_BYTES
    try:
        with path.open("rb") as fh:
            data = fh.read(cap + 1)
    except OSError as exc:
        raise typer.BadParameter("Clone plan file is missing or unreadable.") from exc
    if len(data) > cap:
        raise typer.BadParameter("Clone plan file exceeds the bounded size.")
    return data


def _write_clone_plan_file(path: Path, document: dict[str, object]) -> None:
    """Write a reviewed NON-secret plan to a new 0600 file (no overwrite)."""
    text = json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"
    data = text.encode("utf-8")
    if len(data) > MAX_CLONE_PLAN_FILE_BYTES:
        raise CliKeyError("Clone plan exceeds the bounded file size.")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise typer.BadParameter("Clone plan file already exists.") from exc
    except OSError as exc:
        raise CliKeyError("Could not create clone plan file.") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
    except OSError as exc:
        raise CliKeyError("Could not write clone plan file.") from exc


def _clone_result_dict(
    result: KeyCloneResult, *, include_plaintext: bool = False
) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": result.status,
        "operation_uuid": result.operation_uuid,
        "source_gateway_key_id": result.source_gateway_key_id,
        "source_fingerprint": result.source_fingerprint,
        "requires_fenced_confirmation": result.requires_fenced_confirmation,
        "target_gateway_key_id": result.target_gateway_key_id,
        "target_public_key_id": result.target_public_key_id,
        "one_time_secret_id": result.one_time_secret_id,
        "email_delivery_id": result.email_delivery_id,
        "valid_from": result.valid_from,
        "valid_until": result.valid_until,
    }
    if include_plaintext and result.plaintext_key is not None:
        payload["plaintext_key"] = result.plaintext_key
    return payload


def _delivery_result_dict(result: PendingKeyEmailResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "email_delivery_id": result.email_delivery_id,
        "one_time_secret_id": result.one_time_secret_id,
        "status": result.status,
    }
    if result.gateway_key_id is not None:
        payload["gateway_key_id"] = result.gateway_key_id
    if result.owner_id is not None:
        payload["owner_id"] = result.owner_id
    if result.recipient_email is not None:
        payload["recipient_email"] = result.recipient_email
    if result.provider_message_id is not None:
        payload["provider_message_id"] = result.provider_message_id
    if result.error_code is not None:
        payload["error_code"] = result.error_code
    if result.error_message is not None:
        payload["error_message"] = result.error_message
    return payload


def _append_email_delivery_payload(
    payload: dict[str, object],
    *,
    delivery_result: PendingKeyEmailResult | None,
    celery_task_id: str | None = None,
) -> dict[str, object]:
    if delivery_result is not None:
        payload["email_delivery"] = _delivery_result_dict(delivery_result)
        payload["email_delivery_id"] = delivery_result.email_delivery_id
        payload["email_delivery_status"] = delivery_result.status
        if delivery_result.recipient_email is not None:
            payload["email_delivery_recipient"] = delivery_result.recipient_email
    if celery_task_id is not None:
        payload["celery_task_id"] = celery_task_id
    return payload


def _exit_if_email_delivery_failed(delivery_result: PendingKeyEmailResult | None) -> None:
    if delivery_result is not None and delivery_result.status == "failed":
        raise typer.Exit(code=1)


def _rotated_key_dict(
    result: RotatedGatewayKeyResult, *, include_plaintext: bool = True
) -> dict[str, object]:
    payload: dict[str, object] = {
        "old_gateway_key_id": result.old_gateway_key_id,
        "new_gateway_key_id": result.new_gateway_key_id,
        "new_public_key_id": result.new_public_key_id,
        "one_time_secret_id": result.one_time_secret_id,
        "old_status": result.old_status,
        "new_status": result.new_status,
        "valid_from": result.valid_from,
        "valid_until": result.valid_until,
        "owner_id": result.owner_id,
    }
    if include_plaintext:
        payload["new_plaintext_key"] = result.new_plaintext_key
    return payload


def _echo_kv(payload: dict[str, object]) -> None:
    for key, value in payload.items():
        if isinstance(value, datetime):
            display = value.isoformat()
        elif isinstance(value, Decimal):
            display = str(value)
        elif value is None:
            display = ""
        else:
            display = str(value)
        typer.echo(f"{key}: {display}")


def _handle_cli_error(exc: Exception, *, json_output: bool = False) -> None:
    if isinstance(exc, KeyManagementError):
        message = exc.safe_message
        code = exc.error_code
    elif isinstance(exc, KeyTemplateError):
        message = str(exc)
        code = "key_template_error"
    elif isinstance(exc, EmailError):
        message = exc.safe_message
        code = exc.error_code
    elif isinstance(exc, CliDatabaseConfigError):
        message = str(exc)
        code = "database_not_configured"
    elif isinstance(exc, CliError | CliKeyError):
        message = str(exc)
        code = "cli_error"
    elif isinstance(exc, typer.BadParameter):
        message = str(exc)
        code = "invalid_parameter"
    else:
        message = "Command failed"
        code = "command_failed"

    if json_output:
        _emit_json({"error": {"code": code, "message": message}})
    else:
        typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _validate_secret_output_options(
    *,
    json_output: bool,
    show_plaintext: bool,
    secret_output_file: Path | None,
    email_delivery_mode: EmailDeliveryMode = EmailDeliveryMode.none,
) -> None:
    if show_plaintext and secret_output_file is not None:
        raise typer.BadParameter("Use either --show-plaintext or --secret-output-file, not both")
    if email_delivery_mode in {EmailDeliveryMode.send_now, EmailDeliveryMode.enqueue}:
        if show_plaintext:
            raise typer.BadParameter(
                "--show-plaintext cannot be combined with email-delivery send-now/enqueue"
            )
        if secret_output_file is not None:
            raise typer.BadParameter(
                "--secret-output-file cannot be combined with email-delivery send-now/enqueue"
            )
        return
    if json_output and not show_plaintext and secret_output_file is None:
        raise typer.BadParameter(
            "JSON output does not include plaintext keys by default; use --show-plaintext "
            "or --secret-output-file PATH"
        )
    if secret_output_file is not None and secret_output_file.exists():
        raise typer.BadParameter(f"Secret output file already exists: {secret_output_file}")


def _require_explicit_key_handling_for_typed_surface(
    *,
    typed_surface: bool,
    show_plaintext: bool,
    secret_output_file: Path | None,
    email_delivery_mode: EmailDeliveryMode,
) -> None:
    """Reject typed key-policy creation without an explicit key channel.

    New typed surfaces (a policy file or explicit provider parity flags)
    must not inherit the legacy implicit one-time plaintext print. An
    explicit choice - --show-plaintext, a new 0600 --secret-output-file,
    or an explicit --email-delivery mode - is required before any creation
    happens. Legacy flag-free creation keeps its documented pre-existing
    default behavior.
    """
    if not typed_surface:
        return
    if (
        show_plaintext
        or secret_output_file is not None
        or email_delivery_mode is not EmailDeliveryMode.none
    ):
        return
    raise typer.BadParameter(
        "Typed key-policy creation requires an explicit one-time key choice "
        "before creation: --show-plaintext, --secret-output-file PATH, or "
        "--email-delivery pending/send-now/enqueue. Only legacy flag-free "
        "creation prints the one-time plaintext key by default."
    )


def _warn_plaintext_display() -> None:
    typer.secho(
        "Warning: plaintext key is shown once. Store it now; it cannot be recovered later.",
        fg=typer.colors.YELLOW,
        err=True,
    )


def _warn_secret_file(path: Path) -> None:
    typer.secho(
        f"Warning: plaintext key written once to {path} with 0600 permissions. "
        "Store it securely; it cannot be recovered later.",
        fg=typer.colors.YELLOW,
        err=True,
    )


def _warn_email_delivery_channel(mode: EmailDeliveryMode) -> None:
    if mode == EmailDeliveryMode.pending:
        typer.secho(
            "Warning: email delivery is pending; send it with "
            "slaif-gateway email send-pending-key.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    elif mode == EmailDeliveryMode.send_now:
        typer.secho(
            "Warning: plaintext key is not printed because email delivery is the selected "
            "secret output channel. Lost keys cannot be resent; rotate instead.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    elif mode == EmailDeliveryMode.enqueue:
        typer.secho(
            "Warning: plaintext key is not printed because queued email delivery is the selected "
            "secret output channel. Delivery depends on worker availability; lost keys cannot be "
            "resent, rotate instead.",
            fg=typer.colors.YELLOW,
            err=True,
        )


def _warn_trusted_calibration_key() -> None:
    typer.secho(
        "Trusted calibration key: broad discovery policy, small request limit, short validity. "
        "Do not issue to participants.",
        fg=typer.colors.YELLOW,
        err=True,
    )


def _warn_reserved_counter_reset() -> None:
    typer.secho(
        "Warning: resetting reserved counters is an admin repair action and does not delete ledger rows.",
        fg=typer.colors.YELLOW,
        err=True,
    )


async def _create_gateway_key(payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
    async with _key_runtime() as (_, _, service):
        return await service.create_gateway_key(payload)


async def _create_gateway_key_with_email_delivery(
    payload: CreateGatewayKeyInput,
    *,
    email_delivery_mode: EmailDeliveryMode,
) -> KeyEmailDeliveryCliResult:
    async with _key_email_runtime() as (settings, key_service, email_delivery_service):
        _validate_email_delivery_preconditions(settings, email_delivery_mode)
        key_result = await key_service.create_gateway_key(payload)
        delivery_result = await _create_pending_delivery_for_created_key(
            email_delivery_service,
            key_result=key_result,
            actor_admin_id=payload.created_by_admin_id,
            reason=payload.note,
        )

    if email_delivery_mode == EmailDeliveryMode.send_now:
        delivery_result = await _send_pending_key_email_now(
            one_time_secret_id=key_result.one_time_secret_id,
            email_delivery_id=delivery_result.email_delivery_id,
            actor_admin_id=payload.created_by_admin_id,
            reason=payload.note,
        )
    celery_task_id = (
        _enqueue_pending_key_email(
            one_time_secret_id=key_result.one_time_secret_id,
            email_delivery_id=delivery_result.email_delivery_id,
            actor_admin_id=payload.created_by_admin_id,
        )
        if email_delivery_mode == EmailDeliveryMode.enqueue
        else None
    )
    if email_delivery_mode == EmailDeliveryMode.enqueue:
        delivery_result = PendingKeyEmailResult(
            email_delivery_id=delivery_result.email_delivery_id,
            one_time_secret_id=delivery_result.one_time_secret_id,
            gateway_key_id=delivery_result.gateway_key_id,
            owner_id=delivery_result.owner_id,
            recipient_email=delivery_result.recipient_email,
            status="queued",
        )
    return KeyEmailDeliveryCliResult(
        key_result=key_result,
        delivery_result=delivery_result,
        celery_task_id=celery_task_id,
    )


async def _create_key_from_template(
    *,
    template_revision_id: uuid.UUID,
    owner_id: uuid.UUID,
    cohort_id: uuid.UUID | None,
    valid_from: datetime | None,
    valid_until: datetime | None,
    valid_days: int | None,
    email_delivery_mode: EmailDeliveryMode,
    actor_admin_id: uuid.UUID | None,
    reason: str,
    confirm_create_key_from_template: bool,
) -> tuple[KeyFromTemplateCreationResult, PendingKeyEmailResult | None, str | None]:
    async with _template_key_runtime() as (settings, template_service, email_delivery_service):
        _validate_email_delivery_preconditions(settings, email_delivery_mode)
        result = await template_service.create_key_from_revision(
            template_revision_id=template_revision_id,
            owner_id=owner_id,
            cohort_id=cohort_id,
            actor_admin_id=actor_admin_id,
            reason=reason,
            confirm_create_key_from_template=confirm_create_key_from_template,
            valid_from=valid_from,
            valid_until=valid_until,
            valid_days=valid_days,
        )
        delivery_result = (
            await _create_pending_delivery_for_created_key(
                email_delivery_service,
                key_result=result.created_key,
                actor_admin_id=actor_admin_id,
                reason=reason,
            )
            if email_delivery_mode != EmailDeliveryMode.none
            else None
        )

    if email_delivery_mode == EmailDeliveryMode.send_now and delivery_result is not None:
        delivery_result = await _send_pending_key_email_now(
            one_time_secret_id=result.created_key.one_time_secret_id,
            email_delivery_id=delivery_result.email_delivery_id,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )
    celery_task_id = None
    if email_delivery_mode == EmailDeliveryMode.enqueue and delivery_result is not None:
        celery_task_id = _enqueue_pending_key_email(
            one_time_secret_id=result.created_key.one_time_secret_id,
            email_delivery_id=delivery_result.email_delivery_id,
            actor_admin_id=actor_admin_id,
        )
        delivery_result = PendingKeyEmailResult(
            email_delivery_id=delivery_result.email_delivery_id,
            one_time_secret_id=delivery_result.one_time_secret_id,
            gateway_key_id=delivery_result.gateway_key_id,
            owner_id=delivery_result.owner_id,
            recipient_email=delivery_result.recipient_email,
            status="queued",
        )
    return result, delivery_result, celery_task_id


async def _create_pending_delivery_for_created_key(
    service: EmailDeliveryService,
    *,
    key_result: CreatedGatewayKey,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
) -> PendingKeyEmailResult:
    return await service.create_pending_key_email_delivery(
        gateway_key_id=key_result.gateway_key_id,
        one_time_secret_id=key_result.one_time_secret_id,
        owner_id=key_result.owner_id,
        actor_admin_id=actor_admin_id,
        reason=reason,
    )


async def _list_gateway_keys(
    *,
    owner_id: uuid.UUID | None,
    owner_email: str | None,
    cohort_id: uuid.UUID | None,
    status: str | None,
    limit: int,
    offset: int,
) -> list[GatewayKey]:
    if owner_email is not None:
        owner_id = await _resolve_owner_id(owner_email, expected_owner_id=owner_id)
    async with _key_runtime() as (_, keys_repository, _):
        return await keys_repository.list_gateway_keys(
            owner_id=owner_id,
            cohort_id=cohort_id,
            status=status,
            limit=limit,
            offset=offset,
        )


async def _resolve_owner_id(
    owner_email: str, *, expected_owner_id: uuid.UUID | None
) -> uuid.UUID:
    """Exact owner-email lookup (never substring matching); fixed safe errors."""
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError(
            "DATABASE_URL is not configured. Set DATABASE_URL and try again."
        )
    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise CliDatabaseConfigError(str(exc)) from exc
    async with session_factory() as session:
        async with session.begin():
            owner = await OwnersRepository(session).get_owner_by_email(owner_email)
    if owner is None:
        raise CliKeyError("No owner exists for the provided email.")
    if expected_owner_id is not None and owner.id != expected_owner_id:
        raise CliKeyError(
            "The provided owner email does not match the owner UUID."
        )
    return owner.id


async def _show_gateway_key(gateway_key_id: uuid.UUID) -> GatewayKey:
    async with _key_runtime() as (_, keys_repository, _):
        gateway_key = await keys_repository.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            raise GatewayKeyNotFoundError()
        return gateway_key


# Fixed, no-echo refusal for credential-shaped lookup references.
_FULL_KEY_LOOKUP_REFUSAL = (
    "Full key material cannot be used for lookup. "
    "Use the key UUID or its public key ID."
)


async def _resolve_gateway_key_reference(
    settings: Settings,
    keys_repository: GatewayKeysRepository,
    reference: str,
) -> GatewayKey:
    """Resolve a SAFE key reference: UUID or exact public key ID.

    Full bearer-shaped key material is refused with a fixed safe message and
    never echoed; there is no identity lookup from token hash/HMAC/plaintext.
    Credential-shaped references (whitespace, secret separators, header
    prefixes, or any accepted key prefix) are refused BEFORE any database
    query.
    """
    trimmed = reference.strip()
    if not trimmed:
        raise GatewayKeyNotFoundError()
    if is_plausible_gateway_key(
        trimmed, settings.get_gateway_key_accepted_prefixes()
    ):
        raise CliKeyError(_FULL_KEY_LOOKUP_REFUSAL)
    if _is_credential_shaped_reference(
        trimmed, settings.get_gateway_key_accepted_prefixes()
    ):
        raise CliKeyError(_FULL_KEY_LOOKUP_REFUSAL)
    try:
        key_id = uuid.UUID(trimmed)
    except ValueError:
        key_id = None
    if key_id is not None:
        gateway_key = await keys_repository.get_gateway_key_by_id(key_id)
        if gateway_key is not None:
            return gateway_key
    gateway_key = await keys_repository.get_gateway_key_by_public_key_id(trimmed)
    if gateway_key is None:
        raise GatewayKeyNotFoundError()
    return gateway_key


def _is_credential_shaped_reference(
    trimmed: str, accepted_prefixes: tuple[str, ...]
) -> bool:
    """Fixed-shape refusal for references that cannot be a safe UUID/public ID.

    Safe references never contain whitespace, a secret separator (``.``), a
    ``Bearer`` header prefix, or any accepted gateway key prefix.
    """
    if any(ch.isspace() for ch in trimmed):
        return True
    if "." in trimmed:
        return True
    if re.match(r"^bearer[\s:]", trimmed, re.IGNORECASE):
        return True
    return any(trimmed.startswith(prefix) for prefix in accepted_prefixes)


async def _show_gateway_key_by_reference(reference: str) -> GatewayKey:
    async with _key_runtime() as (settings, keys_repository, _):
        return await _resolve_gateway_key_reference(
            settings, keys_repository, reference
        )


async def _update_lazy_throttling(
    *,
    gateway_key_id: uuid.UUID,
    policy: dict[str, object] | None,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, keys_repository, service):
        gateway_key = await keys_repository.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            raise GatewayKeyNotFoundError()
        payload = UpdateGatewayKeyLazyThrottlingInput(
            gateway_key_id=gateway_key_id,
            lazy_throttling_policy=policy,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )
        return await service.update_gateway_key_lazy_throttling(payload)


async def _effective_policy_report(gateway_key_id: uuid.UUID) -> dict[str, object]:
    async with _policy_inspection_runtime() as (settings, keys_repository, _):
        gateway_key = await keys_repository.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            raise GatewayKeyNotFoundError()
        return build_key_policy_inspection(gateway_key=gateway_key, settings=settings)


async def _explain_model_route(
    *,
    gateway_key_id: uuid.UUID,
    model: str,
    endpoint: str,
) -> dict[str, object]:
    async with _policy_inspection_runtime() as (settings, keys_repository, context):
        gateway_key = await keys_repository.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            raise GatewayKeyNotFoundError()
        return await explain_model_route_access(
            gateway_key=gateway_key,
            settings=settings,
            requested_model=model,
            endpoint=endpoint,
            context=context,
        )


async def _suspend_gateway_key(payload: SuspendGatewayKeyInput) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, _, service):
        return await service.suspend_gateway_key(payload)


async def _activate_gateway_key(payload: ActivateGatewayKeyInput) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, _, service):
        return await service.activate_gateway_key(payload)


async def _revoke_gateway_key(payload: RevokeGatewayKeyInput) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, _, service):
        return await service.revoke_gateway_key(payload)


async def _update_validity(payload: UpdateGatewayKeyValidityInput) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, _, service):
        return await service.update_gateway_key_validity(payload)


async def _update_limits(
    *,
    gateway_key_id: uuid.UUID,
    cost_limit_eur: Decimal | None,
    token_limit_total: int | None,
    request_limit_total: int | None,
    clear_cost_limit: bool,
    clear_token_limit: bool,
    clear_request_limit: bool,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, keys_repository, service):
        gateway_key = await keys_repository.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            raise GatewayKeyNotFoundError()
        payload = UpdateGatewayKeyLimitsInput(
            gateway_key_id=gateway_key_id,
            cost_limit_eur=(
                None
                if clear_cost_limit
                else cost_limit_eur
                if cost_limit_eur is not None
                else gateway_key.cost_limit_eur
            ),
            token_limit_total=(
                None
                if clear_token_limit
                else token_limit_total
                if token_limit_total is not None
                else gateway_key.token_limit_total
            ),
            request_limit_total=(
                None
                if clear_request_limit
                else request_limit_total
                if request_limit_total is not None
                else gateway_key.request_limit_total
            ),
            actor_admin_id=actor_admin_id,
            reason=reason,
        )
        return await service.update_gateway_key_limits(payload)


async def _update_rate_limits(
    *,
    gateway_key_id: uuid.UUID,
    requests_per_minute: int | None,
    tokens_per_minute: int | None,
    concurrent_requests: int | None,
    window_seconds: int | None,
    clear_requests: bool,
    clear_tokens: bool,
    clear_concurrency: bool,
    clear_window: bool,
    clear_all: bool,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, keys_repository, service):
        gateway_key = await keys_repository.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            raise GatewayKeyNotFoundError()

        existing_policy = _rate_limit_policy_from_gateway_key(gateway_key) or {}
        if clear_all:
            rate_limit_policy: dict[str, int | None] = {}
        else:
            rate_limit_policy = dict(existing_policy)
            if clear_requests:
                rate_limit_policy.pop("requests_per_minute", None)
            elif requests_per_minute is not None:
                rate_limit_policy["requests_per_minute"] = requests_per_minute

            if clear_tokens:
                rate_limit_policy.pop("tokens_per_minute", None)
            elif tokens_per_minute is not None:
                rate_limit_policy["tokens_per_minute"] = tokens_per_minute

            if clear_concurrency:
                rate_limit_policy.pop("max_concurrent_requests", None)
            elif concurrent_requests is not None:
                rate_limit_policy["max_concurrent_requests"] = concurrent_requests

            if clear_window:
                rate_limit_policy.pop("window_seconds", None)
            elif window_seconds is not None:
                rate_limit_policy["window_seconds"] = window_seconds

        return await service.update_gateway_key_rate_limits(
            UpdateGatewayKeyRateLimitsInput(
                gateway_key_id=gateway_key_id,
                rate_limit_policy=rate_limit_policy or None,
                actor_admin_id=actor_admin_id,
                reason=reason,
            )
        )


async def _update_chat_streaming_live_burn(
    payload: UpdateGatewayKeyChatStreamingLiveBurnInput,
) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, _, service):
        return await service.update_gateway_key_chat_streaming_live_burn(payload)


async def _update_policy(payload: UpdateGatewayKeyPolicyInput) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, _, service):
        return await service.update_gateway_key_policy(payload)


async def _update_configuration(
    payload: UpdateGatewayKeyConfigurationInput,
) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, _, service):
        return await service.update_gateway_key_configuration(payload)


async def _export_configuration(gateway_key_id: uuid.UUID) -> dict[str, object]:
    async with _key_runtime() as (_, _, service):
        return await service.export_gateway_key_configuration(gateway_key_id)


async def _update_external_tool_policy(
    payload: UpdateGatewayKeyExternalToolPolicyInput,
) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, _, service):
        return await service.update_gateway_key_external_tool_policy(payload)


async def _reset_usage(payload: ResetGatewayKeyUsageInput) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, _, service):
        return await service.reset_gateway_key_usage(payload)


async def _rotate_gateway_key(payload: RotateGatewayKeyInput) -> RotatedGatewayKeyResult:
    async with _key_runtime() as (_, _, service):
        return await service.rotate_gateway_key(payload)


async def _rotate_gateway_key_with_email_delivery(
    payload: RotateGatewayKeyInput,
    *,
    email_delivery_mode: EmailDeliveryMode,
) -> KeyEmailDeliveryCliResult:
    async with _key_email_runtime() as (settings, key_service, email_delivery_service):
        _validate_email_delivery_preconditions(settings, email_delivery_mode)
        key_result = await key_service.rotate_gateway_key(payload)
        delivery_result = await _create_pending_delivery_for_rotated_key(
            email_delivery_service,
            key_result=key_result,
            actor_admin_id=payload.actor_admin_id,
            reason=payload.reason,
        )

    if email_delivery_mode == EmailDeliveryMode.send_now:
        delivery_result = await _send_pending_key_email_now(
            one_time_secret_id=key_result.one_time_secret_id,
            email_delivery_id=delivery_result.email_delivery_id,
            actor_admin_id=payload.actor_admin_id,
            reason=payload.reason,
        )
    celery_task_id = (
        _enqueue_pending_key_email(
            one_time_secret_id=key_result.one_time_secret_id,
            email_delivery_id=delivery_result.email_delivery_id,
            actor_admin_id=payload.actor_admin_id,
        )
        if email_delivery_mode == EmailDeliveryMode.enqueue
        else None
    )
    if email_delivery_mode == EmailDeliveryMode.enqueue:
        delivery_result = PendingKeyEmailResult(
            email_delivery_id=delivery_result.email_delivery_id,
            one_time_secret_id=delivery_result.one_time_secret_id,
            gateway_key_id=delivery_result.gateway_key_id,
            owner_id=delivery_result.owner_id,
            recipient_email=delivery_result.recipient_email,
            status="queued",
        )
    return KeyEmailDeliveryCliResult(
        key_result=key_result,
        delivery_result=delivery_result,
        celery_task_id=celery_task_id,
    )


async def _create_pending_delivery_for_rotated_key(
    service: EmailDeliveryService,
    *,
    key_result: RotatedGatewayKeyResult,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
) -> PendingKeyEmailResult:
    if key_result.owner_id is None:
        raise CliKeyError("Rotated key result did not include owner metadata for email delivery")
    return await service.create_pending_key_email_delivery(
        gateway_key_id=key_result.new_gateway_key_id,
        one_time_secret_id=key_result.one_time_secret_id,
        owner_id=key_result.owner_id,
        actor_admin_id=actor_admin_id,
        reason=reason,
    )


async def _send_pending_key_email_now(
    *,
    one_time_secret_id: uuid.UUID,
    email_delivery_id: uuid.UUID,
    actor_admin_id: uuid.UUID | None,
    reason: str | None,
) -> PendingKeyEmailResult:
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError(
            "DATABASE_URL is not configured. Set DATABASE_URL and try again."
        )
    try:
        session_factory = get_sessionmaker(settings)
    except RuntimeError as exc:
        raise CliDatabaseConfigError(str(exc)) from exc

    async with session_factory() as session:
        email_delivery_service = EmailDeliveryService(
            settings=settings,
            one_time_secrets_repository=OneTimeSecretsRepository(session),
            email_deliveries_repository=EmailDeliveriesRepository(session),
            gateway_keys_repository=GatewayKeysRepository(session),
            owners_repository=OwnersRepository(session),
            audit_repository=AuditRepository(session),
            email_service=EmailService(settings),
            session=session,
        )
        return await email_delivery_service.send_pending_key_email(
            one_time_secret_id=one_time_secret_id,
            email_delivery_id=email_delivery_id,
            actor_admin_id=actor_admin_id,
            reason=reason,
        )


def _enqueue_pending_key_email(
    *,
    one_time_secret_id: uuid.UUID,
    email_delivery_id: uuid.UUID,
    actor_admin_id: uuid.UUID | None,
) -> str:
    async_result = send_pending_key_email_task.delay(
        str(one_time_secret_id),
        str(email_delivery_id),
        str(actor_admin_id) if actor_admin_id else None,
    )
    return str(async_result.id)


def _validate_email_delivery_preconditions(
    settings: Settings,
    email_delivery_mode: EmailDeliveryMode,
) -> None:
    if email_delivery_mode == EmailDeliveryMode.pending:
        return
    if email_delivery_mode == EmailDeliveryMode.send_now:
        if not settings.ENABLE_EMAIL_DELIVERY:
            raise CliKeyError("ENABLE_EMAIL_DELIVERY must be true for email-delivery=send-now")
        return
    if email_delivery_mode == EmailDeliveryMode.enqueue:
        if not settings.ENABLE_EMAIL_DELIVERY:
            raise CliKeyError("ENABLE_EMAIL_DELIVERY must be true for email-delivery=enqueue")
        if not settings.get_celery_broker_url():
            raise CliKeyError(
                "CELERY_BROKER_URL or REDIS_URL is required for email-delivery=enqueue"
            )


async def _build_clone_plan_document(
    *,
    source_gateway_key_id: uuid.UUID,
    target_owner_id: uuid.UUID,
    target_cohort_id: uuid.UUID | None,
    validity_mode: str,
    validity_duration_seconds: int | None,
    validity_from: str | None,
    validity_until: str | None,
) -> dict[str, object]:
    """Read-only clone plan build: no mutation, no audit row."""
    async with _key_clone_runtime() as (_, clone_service):
        return await clone_service.build_plan(
            source_gateway_key_id=source_gateway_key_id,
            target_owner_id=target_owner_id,
            target_cohort_id=target_cohort_id,
            validity_mode=validity_mode,
            validity_duration_seconds=validity_duration_seconds,
            validity_from=validity_from,
            validity_until=validity_until,
        )


async def _execute_clone_plan(
    plan: KeyClonePlan,
    *,
    reason: str,
    actor_admin_id: uuid.UUID | None,
    confirm_external_tool_fenced: bool,
    email_delivery_mode: EmailDeliveryMode,
) -> KeyCloneResult:
    """Execute one reviewed plan inside the caller-owned transaction."""
    async with _key_clone_runtime() as (settings, clone_service):
        _validate_email_delivery_preconditions(settings, email_delivery_mode)
        return await clone_service.execute_plan(
            plan=plan,
            reason=reason,
            actor_admin_id=actor_admin_id,
            confirm_external_tool_fenced=confirm_external_tool_fenced,
            create_email_delivery=email_delivery_mode is not EmailDeliveryMode.none,
        )


@app.callback()
def keys() -> None:
    """Manage gateway keys."""


@app.command("create")
def create(
    ctx: typer.Context,
    owner_id: Annotated[str, typer.Option("--owner-id", help="Owner UUID")],
    cohort_id: Annotated[str | None, typer.Option("--cohort-id", help="Cohort UUID")] = None,
    valid_from: Annotated[
        str | None,
        typer.Option("--valid-from", help="ISO datetime; defaults to now"),
    ] = None,
    valid_until: Annotated[
        str | None,
        typer.Option("--valid-until", help="ISO datetime"),
    ] = None,
    valid_days: Annotated[
        int | None,
        typer.Option("--valid-days", help="Validity duration in days"),
    ] = None,
    cost_limit_eur: Annotated[
        str | None,
        typer.Option(
            "--cost-limit-eur",
            help="Cost limit in EUR",
            callback=policy_source_callback,
        ),
    ] = None,
    token_limit_total: Annotated[
        int | None,
        typer.Option(
            "--token-limit-total",
            help="Total token limit",
            callback=policy_source_callback,
        ),
    ] = None,
    request_limit_total: Annotated[
        int | None,
        typer.Option(
            "--request-limit-total",
            help="Total request limit",
            callback=policy_source_callback,
        ),
    ] = None,
    allowed_models: Annotated[
        list[str] | None,
        typer.Option(
            "--allowed-model",
            help="Allowed model; repeatable",
            callback=policy_source_callback,
        ),
    ] = None,
    allowed_endpoints: Annotated[
        list[str] | None,
        typer.Option(
            "--allowed-endpoint",
            help="Allowed endpoint; repeatable",
            callback=policy_source_callback,
        ),
    ] = None,
    allow_all_models: Annotated[
        bool,
        typer.Option(
            "--allow-all-models/--no-allow-all-models",
            help="Allow all route-backed models",
            callback=policy_source_callback,
        ),
    ] = False,
    allow_all_endpoints: Annotated[
        bool,
        typer.Option(
            "--allow-all-endpoints/--no-allow-all-endpoints",
            help="Allow all implemented endpoints",
            callback=policy_source_callback,
        ),
    ] = False,
    allowed_providers: Annotated[
        list[str] | None,
        typer.Option(
            "--allowed-provider",
            help="Allowed upstream provider; repeatable",
            callback=policy_source_callback,
        ),
    ] = None,
    provider_all: Annotated[
        bool,
        typer.Option(
            "--provider-all",
            help="Unrestricted provider access (no provider allow-list)",
            callback=policy_source_callback,
        ),
    ] = False,
    provider_none: Annotated[
        bool,
        typer.Option(
            "--provider-none",
            help="Deny all providers (empty provider allow-list)",
            callback=policy_source_callback,
        ),
    ] = False,
    policy_file: Annotated[
        Path | None,
        typer.Option(
            "--policy-file",
            help="Versioned key-configuration policy file (only policy source)",
            callback=policy_source_callback,
        ),
    ] = None,
    rate_limit_requests_per_minute: Annotated[
        int | None,
        typer.Option(
            "--rate-limit-requests-per-minute",
            help="Redis operational request limit per key per window",
            callback=policy_source_callback,
        ),
    ] = None,
    rate_limit_tokens_per_minute: Annotated[
        int | None,
        typer.Option(
            "--rate-limit-tokens-per-minute",
            help="Redis operational estimated-token limit per key per window",
            callback=policy_source_callback,
        ),
    ] = None,
    rate_limit_concurrent_requests: Annotated[
        int | None,
        typer.Option(
            "--rate-limit-concurrent-requests",
            help="Redis operational concurrent request limit per key",
            callback=policy_source_callback,
        ),
    ] = None,
    rate_limit_window_seconds: Annotated[
        int | None,
        typer.Option(
            "--rate-limit-window-seconds",
            help="Redis operational rate-limit window in seconds",
            callback=policy_source_callback,
        ),
    ] = None,
    chat_streaming_live_burn_enabled: Annotated[
        bool,
        typer.Option(
            "--chat-streaming-live-burn-enabled/--no-chat-streaming-live-burn",
            help=(
                "Enable Chat Completions streaming live-burn monitoring for "
                "/v1/chat/completions stream=true"
            ),
            callback=policy_source_callback,
        ),
    ] = True,
    chat_streaming_live_burn_cost_margin_eur: Annotated[
        str | None,
        typer.Option(
            "--chat-streaming-live-burn-cost-margin-eur",
            help=(
                "Chat streaming live-burn cost margin in EUR; positive stops early, "
                "zero stops near the boundary, negative allows bounded overrun"
            ),
            callback=policy_source_callback,
        ),
    ] = None,
    chat_streaming_live_burn_token_margin: Annotated[
        int | None,
        typer.Option(
            "--chat-streaming-live-burn-token-margin",
            help=(
                "Chat streaming live-burn output token margin; positive stops early, "
                "zero stops near the boundary, negative allows bounded overrun"
            ),
            callback=policy_source_callback,
        ),
    ] = None,
    external_tool_mode: Annotated[
        str,
        typer.Option(
            "--external-tool-mode",
            help=(
                "strict_bounded or external_tool_fenced; runtime supports only exact "
                "OpenAI Responses web_search with matching key/route policy"
            ),
            callback=policy_source_callback,
        ),
    ] = STRICT_BOUNDED,
    external_tool_capabilities: Annotated[
        list[str] | None,
        typer.Option(
            "--external-tool-capability",
            help="Reviewed external capability ID; repeatable",
            callback=policy_source_callback,
        ),
    ] = None,
    external_tool_destination_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--external-tool-destination-id",
            help="Reviewed opaque connector:/remote_mcp: destination ID; repeatable",
            callback=policy_source_callback,
        ),
    ] = None,
    external_tool_max_calls: Annotated[
        int,
        typer.Option(
            "--external-tool-max-calls",
            help="Positive future provider-tool call cap; zero for strict mode",
            callback=policy_source_callback,
        ),
    ] = 0,
    acknowledge_single_request_overrun: Annotated[
        bool,
        typer.Option(
            "--acknowledge-single-request-overrun",
            help="Acknowledge the fenced single-request overrun and hold behavior",
            callback=policy_source_callback,
        ),
    ] = False,
    confirm_external_tool_fenced: Annotated[
        bool,
        typer.Option(
            "--confirm-external-tool-fenced",
            "--confirm",
            help="Second confirmation required for fenced future policy",
            callback=policy_source_callback,
        ),
    ] = False,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit note")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
    show_plaintext: Annotated[
        bool,
        typer.Option("--show-plaintext", help="Include the one-time plaintext key in JSON output"),
    ] = False,
    secret_output_file: Annotated[
        Path | None,
        typer.Option(
            "--secret-output-file", help="Write the one-time plaintext key to a new 0600 file"
        ),
    ] = None,
    email_delivery: Annotated[
        EmailDeliveryMode,
        typer.Option(
            "--email-delivery",
            help="Key email delivery mode: none, pending, send-now, or enqueue",
        ),
    ] = EmailDeliveryMode.none,
    trusted_calibration: Annotated[
        bool,
        typer.Option(
            "--trusted-calibration/--standard",
            help="Create a trusted organizer calibration key with broad discovery policy",
            callback=policy_source_callback,
        ),
    ] = False,
    confirm_trusted_calibration: Annotated[
        bool,
        typer.Option(
            "--confirm-trusted-calibration",
            help="Required acknowledgement for trusted calibration keys",
            callback=policy_source_callback,
        ),
    ] = False,
) -> None:
    """Create a gateway key and print the plaintext key once.

    Chat streaming live-burn applies only to /v1/chat/completions stream=true.
    Chat streaming live-burn flags:
    --chat-streaming-live-burn-enabled / --no-chat-streaming-live-burn,
    --chat-streaming-live-burn-cost-margin-eur, and
    --chat-streaming-live-burn-token-margin.

    Provider flags: --allowed-provider (repeatable), --provider-all, and
    --provider-none are mutually exclusive. --policy-file makes a versioned
    key-configuration file the only source of policy configuration; it may
    only be combined with identity, validity, reason, actor, output, and
    delivery flags.

    Typed policy surfaces require an explicit one-time key choice before
    creation: with --policy-file or any explicit provider flag, one of
    --show-plaintext, --secret-output-file PATH, or --email-delivery
    pending/send-now/enqueue is required. Legacy flag-free creation keeps
    its pre-existing default of printing the one-time plaintext key once.
    """
    try:
        _validate_secret_output_options(
            json_output=json_output,
            show_plaintext=show_plaintext,
            secret_output_file=secret_output_file,
            email_delivery_mode=email_delivery,
        )
        if trusted_calibration and email_delivery not in {
            EmailDeliveryMode.none,
            EmailDeliveryMode.pending,
        }:
            raise typer.BadParameter(
                "Trusted calibration keys support only --email-delivery none or pending."
            )
        if trusted_calibration and not confirm_trusted_calibration:
            raise typer.BadParameter(
                "Trusted calibration keys require --confirm-trusted-calibration."
            )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    parsed_valid_from = _parse_datetime(valid_from, field_name="valid_from") or datetime.now(UTC)
    sources = policy_sources(ctx)
    try:
        if was_explicit(sources, "policy_file"):
            # A policy file may carry an exact client-module pin. Every CLI
            # process starts with only the packaged registry, so the
            # configured Codex profile must be bootstrapped BEFORE the
            # authoring validator compares pins - not after the DB runtime
            # opens. A misconfigured profile file fails closed with a fixed
            # safe message (no packaged fallback).
            _bootstrap_codex_profile(get_settings())
            validate_policy_file_conflicts(sources)
            _require_explicit_key_handling_for_typed_surface(
                typed_surface=True,
                show_plaintext=show_plaintext,
                secret_output_file=secret_output_file,
                email_delivery_mode=email_delivery,
            )
            configuration = read_policy_file(policy_file)
            # Explicit confirmation control may accompany the file: the
            # file's own field wins when present, otherwise the explicit
            # CLI flag supplies the acknowledgement.
            if (
                was_explicit(sources, "confirm_external_tool_fenced")
                and confirm_external_tool_fenced
                and not configuration.has("confirm_external_tool_fenced")
            ):
                configuration.confirm_external_tool_fenced = True
            payload = build_create_gateway_key_input(
                config=configuration,
                owner_id=_parse_uuid(owner_id, field_name="owner_id"),
                cohort_id=_parse_uuid(cohort_id, field_name="cohort_id")
                if cohort_id
                else None,
                valid_from=parsed_valid_from,
                valid_until=_valid_until_from_options(
                    valid_from=parsed_valid_from,
                    valid_until=valid_until,
                    valid_days=valid_days,
                ),
                created_by_admin_id=(
                    _parse_uuid(actor_admin_id, field_name="actor_admin_id")
                    if actor_admin_id
                    else None
                ),
                note=reason,
            )
        else:
            key_purpose = KEY_PURPOSE_TRUSTED_CALIBRATION if trusted_calibration else "standard"
            capability_policy_mode = (
                CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
                if trusted_calibration
                else "standard"
            )
            provider_value = provider_flags_value(
                sources,
                allowed_providers=allowed_providers,
                provider_all=provider_all,
                provider_none=provider_none,
            )
            # Legacy flag-free creation keeps its pre-existing default; only
            # an explicit provider parity choice is a new typed surface.
            if provider_value is not PROVIDER_ABSENT:
                _require_explicit_key_handling_for_typed_surface(
                    typed_surface=True,
                    show_plaintext=show_plaintext,
                    secret_output_file=secret_output_file,
                    email_delivery_mode=email_delivery,
                )
            payload = CreateGatewayKeyInput(
                owner_id=_parse_uuid(owner_id, field_name="owner_id"),
                cohort_id=_parse_uuid(cohort_id, field_name="cohort_id")
                if cohort_id
                else None,
                valid_from=parsed_valid_from,
                valid_until=_valid_until_from_options(
                    valid_from=parsed_valid_from,
                    valid_until=valid_until,
                    valid_days=valid_days,
                ),
                cost_limit_eur=_parse_decimal(cost_limit_eur, field_name="cost_limit_eur"),
                token_limit_total=token_limit_total,
                request_limit_total=request_limit_total,
                allowed_models=list(allowed_models or []),
                allowed_endpoints=list(allowed_endpoints or []),
                allow_all_models=allow_all_models,
                allow_all_endpoints=allow_all_endpoints,
                key_purpose=key_purpose,
                capability_policy_mode=capability_policy_mode,
                calibration_metadata={"creation_channel": "cli"}
                if trusted_calibration
                else {},
                confirm_trusted_calibration=confirm_trusted_calibration,
                rate_limit_policy=_rate_limit_policy_from_options(
                    requests_per_minute=rate_limit_requests_per_minute,
                    tokens_per_minute=rate_limit_tokens_per_minute,
                    concurrent_requests=rate_limit_concurrent_requests,
                    window_seconds=rate_limit_window_seconds,
                ),
                chat_streaming_live_burn_policy=_chat_streaming_live_burn_policy_from_options(
                    enabled=chat_streaming_live_burn_enabled,
                    cost_margin_eur=chat_streaming_live_burn_cost_margin_eur,
                    token_margin=chat_streaming_live_burn_token_margin,
                ),
                external_tool_policy=_external_tool_policy_from_options(
                    mode=external_tool_mode,
                    capabilities=external_tool_capabilities,
                    destination_ids=external_tool_destination_ids,
                    max_calls=external_tool_max_calls,
                    acknowledge_single_request_overrun=acknowledge_single_request_overrun,
                ),
                confirm_external_tool_fenced=confirm_external_tool_fenced,
                created_by_admin_id=(
                    _parse_uuid(actor_admin_id, field_name="actor_admin_id")
                    if actor_admin_id
                    else None
                ),
                note=reason,
                allowed_providers=None
                if provider_value is PROVIDER_ABSENT
                else provider_value,
            )
    except typer.BadParameter:
        raise
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return
    try:
        if email_delivery == EmailDeliveryMode.none:
            cli_result = KeyEmailDeliveryCliResult(
                key_result=_run_async(_create_gateway_key(payload))
            )
        else:
            cli_result = _run_async(
                _create_gateway_key_with_email_delivery(
                    payload,
                    email_delivery_mode=email_delivery,
                )
            )
        result = cli_result.key_result
        if not isinstance(result, CreatedGatewayKey):
            raise CliKeyError("Unexpected key creation result")
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    if email_delivery in {EmailDeliveryMode.send_now, EmailDeliveryMode.enqueue}:
        _warn_email_delivery_channel(email_delivery)
    elif secret_output_file is not None:
        try:
            write_secret_file(secret_output_file, result.plaintext_key)
        except Exception as exc:  # noqa: BLE001
            _handle_cli_error(exc, json_output=json_output)
            return
        _warn_secret_file(secret_output_file)
    elif show_plaintext or not json_output:
        _warn_plaintext_display()
    if trusted_calibration:
        _warn_trusted_calibration_key()
    if email_delivery == EmailDeliveryMode.pending:
        _warn_email_delivery_channel(email_delivery)

    include_plaintext = (
        email_delivery not in {EmailDeliveryMode.send_now, EmailDeliveryMode.enqueue}
        and secret_output_file is None
        and (show_plaintext or not json_output)
    )
    payload_dict = _created_key_dict(result, include_plaintext=include_plaintext)
    payload_dict = _append_email_delivery_payload(
        payload_dict,
        delivery_result=cli_result.delivery_result,
        celery_task_id=cli_result.celery_task_id,
    )
    if json_output:
        _emit_json(payload_dict)
        _exit_if_email_delivery_failed(cli_result.delivery_result)
        return

    _echo_kv(payload_dict)
    _exit_if_email_delivery_failed(cli_result.delivery_result)


@app.command("clone")
def clone(
    dry_run: Annotated[
        Path | None,
        typer.Option(
            "--dry-run",
            help="Write the reviewed non-secret clone plan to this NEW 0600 path",
        ),
    ] = None,
    execute: Annotated[
        Path | None,
        typer.Option(
            "--execute",
            help="Execute this exact previously reviewed clone plan file",
        ),
    ] = None,
    source_key_id: Annotated[
        str | None,
        typer.Option("--source-key-id", help="Source gateway key UUID (dry-run only)"),
    ] = None,
    target_owner_id: Annotated[
        str | None,
        typer.Option("--target-owner-id", help="Target owner UUID (dry-run only)"),
    ] = None,
    target_cohort_id: Annotated[
        str | None,
        typer.Option(
            "--target-cohort-id", help="Existing target cohort UUID (dry-run only)"
        ),
    ] = None,
    validity_mode: Annotated[
        str | None,
        typer.Option(
            "--validity-mode",
            help=(
                "copy-source-expiry, duration-from-now, or absolute (dry-run only)"
            ),
        ),
    ] = None,
    validity_duration_seconds: Annotated[
        str | None,
        typer.Option(
            "--validity-duration-seconds",
            help="Positive whole seconds for duration-from-now (dry-run only)",
        ),
    ] = None,
    valid_from: Annotated[
        str | None,
        typer.Option(
            "--valid-from", help="ISO datetime for absolute mode (dry-run only)"
        ),
    ] = None,
    valid_until: Annotated[
        str | None,
        typer.Option(
            "--valid-until", help="ISO datetime for absolute mode (dry-run only)"
        ),
    ] = None,
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Audit note (required for execute)"),
    ] = None,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    confirm_external_tool_fenced: Annotated[
        bool,
        typer.Option(
            "--confirm-external-tool-fenced",
            help=(
                "Fresh fenced external-tool confirmation (execute only; never "
                "copied from the source)"
            ),
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
    show_plaintext: Annotated[
        bool,
        typer.Option(
            "--show-plaintext",
            help="Include the one-time plaintext key in output (execute only)",
        ),
    ] = False,
    secret_output_file: Annotated[
        Path | None,
        typer.Option(
            "--secret-output-file",
            help="Write the one-time plaintext key to a new 0600 file (execute only)",
        ),
    ] = None,
    email_delivery: Annotated[
        EmailDeliveryMode,
        typer.Option(
            "--email-delivery",
            help="Key email delivery mode: pending, send-now, or enqueue (execute only)",
        ),
    ] = EmailDeliveryMode.none,
) -> None:
    """Clone a standard key from a reviewed canonical policy plan.

    Two-step operation:

    1. ``--dry-run PATH`` writes a strict NON-secret plan file (new 0600 file,
       never overwrites) for the live source key: canonical configured policy,
       source fingerprint, stable operation UUID, explicit target validity
       mode, and confirmation requirements. Dry-run mutates nothing and
       writes no audit row.
    2. ``--execute PATH`` executes that exact plan file. It requires --reason
       and EXACTLY ONE explicit one-time key channel: --show-plaintext,
       --secret-output-file PATH, or --email-delivery pending/send-now/enqueue.

    The target starts as an independent active standard key: configured
    policy totals are copied, never source usage, remaining balance, replay
    rows, holds, or template membership. Re-running the same executed plan
    returns the already-applied target and never creates a new key, secret,
    or delivery; a changed plan is refused. The one-time plaintext key cannot
    be recovered after first output: use ``slaif-gateway email
    send-pending-key`` for a still-unconsumed pending delivery, otherwise
    rotate the key.
    """
    try:
        validity_duration_seconds = parse_int_option(
            validity_duration_seconds, field_name="--validity-duration-seconds"
        )
        if (dry_run is None) == (execute is None):
            raise typer.BadParameter(
                "Use exactly one of --dry-run PATH or --execute PATH."
            )
        if dry_run is not None:
            if source_key_id is None:
                raise typer.BadParameter("--source-key-id is required for --dry-run")
            if target_owner_id is None:
                raise typer.BadParameter("--target-owner-id is required for --dry-run")
            if validity_mode is None:
                raise typer.BadParameter("--validity-mode is required for --dry-run")
            if validity_mode not in {
                VALIDITY_COPY_SOURCE_EXPIRY,
                VALIDITY_DURATION_FROM_NOW,
                VALIDITY_ABSOLUTE,
            }:
                raise typer.BadParameter(
                    "--validity-mode must be copy-source-expiry, duration-from-now, "
                    "or absolute"
                )
            if validity_mode == VALIDITY_DURATION_FROM_NOW:
                if validity_duration_seconds is None or validity_duration_seconds <= 0:
                    raise typer.BadParameter(
                        "--validity-duration-seconds must be positive for "
                        "duration-from-now"
                    )
                if valid_from is not None or valid_until is not None:
                    raise typer.BadParameter(
                        "--valid-from/--valid-until are only valid for absolute mode"
                    )
            elif validity_mode == VALIDITY_ABSOLUTE:
                if not valid_from or not valid_until:
                    raise typer.BadParameter(
                        "--valid-from and --valid-until are required for absolute mode"
                    )
                if validity_duration_seconds is not None:
                    raise typer.BadParameter(
                        "--validity-duration-seconds is only valid for "
                        "duration-from-now"
                    )
            else:
                if (
                    validity_duration_seconds is not None
                    or valid_from is not None
                    or valid_until is not None
                ):
                    raise typer.BadParameter(
                        "copy-source-expiry accepts no duration or absolute validity values"
                    )
            # R4: refuse execute-only channel/confirmation options on dry-run.
            # --reason and --actor-admin-id are shared: accepted here, but the
            # audit note and actor apply only during execute (dry-run writes no
            # audit row).
            if show_plaintext:
                raise typer.BadParameter(
                    "--show-plaintext is execute-only; it cannot be used with --dry-run."
                )
            if secret_output_file is not None:
                raise typer.BadParameter(
                    "--secret-output-file is execute-only; it cannot be used with --dry-run."
                )
            if email_delivery is not EmailDeliveryMode.none:
                raise typer.BadParameter(
                    "--email-delivery is execute-only; it cannot be used with --dry-run."
                )
            if confirm_external_tool_fenced:
                raise typer.BadParameter(
                    "--confirm-external-tool-fenced is execute-only; it cannot be used with --dry-run."
                )
        else:
            # R4: refuse dry-run-only source/target/validity flags on execute;
            # the reviewed plan file is the sole source of those values.
            if (
                source_key_id is not None
                or target_owner_id is not None
                or target_cohort_id is not None
                or validity_mode is not None
                or validity_duration_seconds is not None
                or valid_from is not None
                or valid_until is not None
            ):
                raise typer.BadParameter(
                    "Clone execute reads source/target/validity from the plan "
                    "file; do not pass --source-key-id, --target-owner-id, "
                    "--target-cohort-id, or --validity-* with --execute."
                )
            if not reason or not reason.strip():
                raise typer.BadParameter("--reason is required for --execute")
            channels = sum(
                (
                    show_plaintext,
                    secret_output_file is not None,
                    email_delivery is not EmailDeliveryMode.none,
                )
            )
            if channels != 1:
                raise typer.BadParameter(
                    "Clone execution requires exactly one explicit one-time key "
                    "channel: --show-plaintext, --secret-output-file PATH, or "
                    "--email-delivery pending/send-now/enqueue."
                )
            if show_plaintext and secret_output_file is not None:
                raise typer.BadParameter(
                    "Use either --show-plaintext or --secret-output-file, not both"
                )
        actor = (
            _parse_uuid(actor_admin_id, field_name="actor_admin_id")
            if actor_admin_id
            else None
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    try:
        if dry_run is not None:
            document = _run_async(
                _build_clone_plan_document(
                    source_gateway_key_id=_parse_uuid(
                        source_key_id, field_name="source_key_id"
                    ),
                    target_owner_id=_parse_uuid(
                        target_owner_id, field_name="target_owner_id"
                    ),
                    target_cohort_id=(
                        _parse_uuid(target_cohort_id, field_name="target_cohort_id")
                        if target_cohort_id
                        else None
                    ),
                    validity_mode=validity_mode,
                    validity_duration_seconds=validity_duration_seconds,
                    validity_from=valid_from,
                    validity_until=valid_until,
                )
            )
            _write_clone_plan_file(dry_run, document)
            if json_output:
                # The emitted document is byte-identical in content to the
                # plan file: it re-parses with the same strict schema.
                _emit_json(document)
            else:
                typer.secho(
                    f"Clone plan written to {dry_run} (new 0600 file, never "
                    "overwritten). Review it, then execute with:\n"
                    f"  slaif-gateway keys clone --execute {dry_run} --reason NOTE "
                    "<--show-plaintext | --secret-output-file PATH | --email-delivery MODE>",
                    err=True,
                )
                _echo_kv(
                    {
                        "status": "planned",
                        "plan_file": str(dry_run),
                        "operation_uuid": document["operation_uuid"],
                        "source_gateway_key_id": document["source_gateway_key_id"],
                        "source_public_key_id": document["source_public_key_id"],
                        "source_fingerprint": document["source_fingerprint"],
                        "target_owner_id": document["target_owner_id"],
                        "target_cohort_id": document["target_cohort_id"],
                        "validity_mode": document["validity"]["mode"],
                        "requires_fenced_confirmation": document[
                            "requires_fenced_confirmation"
                        ],
                    }
                )
        else:
            plan_data = _read_bounded_plan_file(Path(execute))  # type: ignore[union-attr]
            plan = parse_clone_plan_file(plan_data)
            result = _run_async(
                _execute_clone_plan(
                    plan,
                    reason=reason,
                    actor_admin_id=actor,
                    confirm_external_tool_fenced=confirm_external_tool_fenced,
                    email_delivery_mode=email_delivery,
                )
            )

            delivery_result: PendingKeyEmailResult | None = None
            celery_task_id: str | None = None
            post_commit_failed = False

            if result.status == "created":
                if secret_output_file is not None:
                    try:
                        write_secret_file(secret_output_file, result.plaintext_key)
                    except Exception:  # noqa: BLE001
                        post_commit_failed = True
                    else:
                        _warn_secret_file(secret_output_file)
                elif email_delivery is EmailDeliveryMode.send_now:
                    _warn_email_delivery_channel(email_delivery)
                    try:
                        delivery_result = _run_async(
                            _send_pending_key_email_now(
                                one_time_secret_id=uuid.UUID(result.one_time_secret_id),
                                email_delivery_id=uuid.UUID(result.email_delivery_id),
                                actor_admin_id=actor,
                                reason=reason,
                            )
                        )
                    except Exception:  # noqa: BLE001 - committed; safe recovery only
                        post_commit_failed = True
                elif email_delivery is EmailDeliveryMode.enqueue:
                    _warn_email_delivery_channel(email_delivery)
                    try:
                        celery_task_id = _enqueue_pending_key_email(
                            one_time_secret_id=uuid.UUID(result.one_time_secret_id),
                            email_delivery_id=uuid.UUID(result.email_delivery_id),
                            actor_admin_id=actor,
                        )
                    except Exception:  # noqa: BLE001
                        post_commit_failed = True
                    else:
                        delivery_result = PendingKeyEmailResult(
                            email_delivery_id=uuid.UUID(result.email_delivery_id),
                            one_time_secret_id=uuid.UUID(result.one_time_secret_id),
                            gateway_key_id=uuid.UUID(result.target_gateway_key_id),
                            owner_id=uuid.UUID(plan.target_owner_id),
                            recipient_email=None,
                            status="queued",
                        )
                elif email_delivery is EmailDeliveryMode.pending:
                    _warn_email_delivery_channel(email_delivery)
                elif show_plaintext:
                    _warn_plaintext_display()
            elif result.status == "already-applied":
                typer.secho(
                    "This clone operation already completed: the recorded target is "
                    "returned. No new key, secret, or delivery was created, and the "
                    "one-time plaintext is unrecoverable. Use `slaif-gateway email "
                    "send-pending-key` for a still-unconsumed pending delivery, or "
                    "rotate the key.",
                    fg=typer.colors.YELLOW,
                    err=True,
                )

            payload = _clone_result_dict(
                result,
                include_plaintext=(show_plaintext and result.status == "created"),
            )
            payload = _append_email_delivery_payload(
                payload,
                delivery_result=delivery_result,
                celery_task_id=celery_task_id,
            )
            if post_commit_failed:
                payload["recovery"] = {
                    "plaintext_recoverable": False,
                    "target_gateway_key_id": result.target_gateway_key_id,
                    "one_time_secret_id": result.one_time_secret_id,
                    "email_delivery_id": result.email_delivery_id,
                    "guidance": (
                        "The clone committed, but the selected output channel failed "
                        "after commit. The one-time plaintext cannot be recovered. "
                        "Use `slaif-gateway email send-pending-key "
                        f"--one-time-secret-id {result.one_time_secret_id}` for a "
                        "still-unconsumed pending delivery, or rotate the key."
                    ),
                }
            if json_output:
                _emit_json(payload)
            else:
                _echo_kv(payload)
            if post_commit_failed:
                raise typer.Exit(code=1)
            _exit_if_email_delivery_failed(delivery_result)
        return
    except KeyClonePlanError as exc:
        _handle_cli_error(CliKeyError(str(exc)), json_output=json_output)
        return
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return


@app.command("create-from-template")
def create_from_template(
    template_revision_id: Annotated[
        str,
        typer.Option("--template-revision-id", help="Immutable key template revision UUID"),
    ],
    owner_id: Annotated[str, typer.Option("--owner-id", help="Owner UUID")],
    cohort_id: Annotated[str | None, typer.Option("--cohort-id", help="Cohort UUID")] = None,
    valid_from: Annotated[
        str | None,
        typer.Option("--valid-from", help="ISO datetime; defaults to now"),
    ] = None,
    valid_until: Annotated[
        str | None,
        typer.Option("--valid-until", help="ISO datetime override"),
    ] = None,
    valid_days: Annotated[
        int | None,
        typer.Option("--valid-days", help="Validity duration override in days"),
    ] = None,
    email_delivery: Annotated[
        EmailDeliveryMode,
        typer.Option(
            "--email-delivery",
            help="Key email delivery mode: none, pending, send-now, or enqueue",
        ),
    ] = EmailDeliveryMode.none,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str, typer.Option("--reason", help="Required audit reason")] = "",
    confirm_create_key_from_template: Annotated[
        bool,
        typer.Option(
            "--confirm-create-key-from-template",
            help="Confirm single key creation from the selected immutable template revision",
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
    show_plaintext: Annotated[
        bool,
        typer.Option("--show-plaintext", help="Include the one-time plaintext key in JSON output"),
    ] = False,
    secret_output_file: Annotated[
        Path | None,
        typer.Option(
            "--secret-output-file", help="Write the one-time plaintext key to a new 0600 file"
        ),
    ] = None,
) -> None:
    """Create one normal gateway key from an immutable key template revision."""
    try:
        _validate_secret_output_options(
            json_output=json_output,
            show_plaintext=show_plaintext,
            secret_output_file=secret_output_file,
            email_delivery_mode=email_delivery,
        )
        if not confirm_create_key_from_template:
            raise typer.BadParameter(
                "Confirm key creation from template with --confirm-create-key-from-template."
            )
        if not reason.strip():
            raise typer.BadParameter("--reason is required for key creation from template.")
        result, delivery_result, celery_task_id = _run_async(
            _create_key_from_template(
                template_revision_id=_parse_uuid(
                    template_revision_id,
                    field_name="template_revision_id",
                ),
                owner_id=_parse_uuid(owner_id, field_name="owner_id"),
                cohort_id=_parse_uuid(cohort_id, field_name="cohort_id") if cohort_id else None,
                valid_from=_parse_datetime(valid_from, field_name="valid_from"),
                valid_until=_parse_datetime(valid_until, field_name="valid_until"),
                valid_days=valid_days,
                email_delivery_mode=email_delivery,
                actor_admin_id=(
                    _parse_uuid(actor_admin_id, field_name="actor_admin_id")
                    if actor_admin_id
                    else None
                ),
                reason=reason,
                confirm_create_key_from_template=confirm_create_key_from_template,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    created = result.created_key
    if email_delivery in {EmailDeliveryMode.send_now, EmailDeliveryMode.enqueue}:
        _warn_email_delivery_channel(email_delivery)
    elif secret_output_file is not None:
        try:
            write_secret_file(secret_output_file, created.plaintext_key)
        except Exception as exc:  # noqa: BLE001
            _handle_cli_error(exc, json_output=json_output)
            return
        _warn_secret_file(secret_output_file)
    elif show_plaintext or not json_output:
        _warn_plaintext_display()
    if email_delivery == EmailDeliveryMode.pending:
        _warn_email_delivery_channel(email_delivery)

    include_plaintext = (
        email_delivery not in {EmailDeliveryMode.send_now, EmailDeliveryMode.enqueue}
        and secret_output_file is None
        and (show_plaintext or not json_output)
    )
    payload_dict = _created_key_dict(created, include_plaintext=include_plaintext)
    payload_dict.update(
        {
            "template_id": result.template.id,
            "template_revision_id": result.revision.id,
            "template_revision_number": result.revision.revision_number,
            "message": (
                "One standard gateway key created from the selected template revision. "
                "No templates, revisions, or existing keys were changed."
            ),
        }
    )
    payload_dict = _append_email_delivery_payload(
        payload_dict,
        delivery_result=delivery_result,
        celery_task_id=celery_task_id,
    )
    if json_output:
        _emit_json(payload_dict)
        _exit_if_email_delivery_failed(delivery_result)
        return

    _echo_kv(payload_dict)
    _exit_if_email_delivery_failed(delivery_result)


@app.command("list")
def list_keys(
    owner_id: Annotated[str | None, typer.Option("--owner-id", help="Owner UUID")] = None,
    owner_email: Annotated[
        str | None,
        typer.Option("--owner-email", help="Exact owner email (no substring match)"),
    ] = None,
    cohort_id: Annotated[str | None, typer.Option("--cohort-id", help="Cohort UUID")] = None,
    status: Annotated[str | None, typer.Option("--status", help="Key status")] = None,
    limit: Annotated[str, typer.Option("--limit", help="Maximum rows to return")] = "50",
    offset: Annotated[
        str,
        typer.Option("--offset", help="Rows to skip for bounded complete pagination"),
    ] = "0",
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List gateway keys using safe metadata only."""
    limit = parse_int_option(limit, field_name="--limit")
    offset = parse_int_option(offset, field_name="--offset")
    if limit <= 0:
        raise typer.BadParameter("--limit must be positive")
    if limit > MAX_KEY_LIST_LIMIT:
        raise typer.BadParameter(f"--limit must be at most {MAX_KEY_LIST_LIMIT}")
    if offset < 0:
        raise typer.BadParameter("--offset must be non-negative")
    if owner_id is not None and owner_email is not None:
        raise typer.BadParameter("Use either --owner-id or --owner-email, not both")
    try:
        rows = _run_async(
            _list_gateway_keys(
                owner_id=_parse_uuid(owner_id, field_name="owner_id") if owner_id else None,
                owner_email=owner_email,
                cohort_id=_parse_uuid(cohort_id, field_name="cohort_id") if cohort_id else None,
                status=status,
                # Bounded lookahead: fetch one extra row so the true end of
                # the result set is known and has_more is never a guess.
                limit=limit + 1,
                offset=offset,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    has_more = len(rows) > limit
    rows = rows[:limit]
    safe_rows = [_safe_gateway_key_dict(row) for row in rows]
    next_offset = offset + len(safe_rows) if has_more else None
    if json_output:
        _emit_json(
            {
                "keys": safe_rows,
                "paging": {
                    "limit": limit,
                    "offset": offset,
                    "returned": len(safe_rows),
                    "has_more": has_more,
                    "next_offset": next_offset,
                },
            }
        )
        return

    if not safe_rows:
        typer.echo("No gateway keys found.")
        return
    for index, row in enumerate(safe_rows):
        if index:
            typer.echo("")
        _echo_kv(row)
    if has_more:
        typer.echo(
            f"More rows may follow; continue with --offset {next_offset}."
        )


@app.command("show")
def show(
    gateway_key_id: Annotated[
        str,
        typer.Argument(help="Gateway key UUID or exact public key ID"),
    ],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show safe metadata for one gateway key (UUID or public key ID).

    Full bearer-shaped key material is refused with a fixed safe error;
    no bearer is required or accepted to find a key.
    """
    try:
        gateway_key = _run_async(_show_gateway_key_by_reference(gateway_key_id))
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    safe_row = _safe_gateway_key_dict(gateway_key)
    if json_output:
        _emit_json(safe_row)
        return
    _echo_kv(safe_row)


@policy_app.command("show")
def policy_show(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show endpoint/model request policy for one gateway key."""
    try:
        gateway_key = _run_async(
            _show_gateway_key(_parse_uuid(gateway_key_id, field_name="gateway_key_id"))
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    provider_policy = _provider_policy_from_gateway_key(gateway_key)
    payload = {
        "gateway_key_id": gateway_key.id,
        "public_key_id": gateway_key.public_key_id,
        "allowed_models": list(gateway_key.allowed_models or []),
        "allowed_endpoints": list(gateway_key.allowed_endpoints or []),
        "allow_all_models": gateway_key.allow_all_models,
        "allow_all_endpoints": gateway_key.allow_all_endpoints,
        "allowed_providers": provider_policy["allowed_providers"],
        "allow_all_providers": provider_policy["allow_all_providers"],
        "allowed_providers_state": provider_policy["state"],
    }
    if json_output:
        _emit_json(payload)
        return
    _echo_kv(payload)


def _echo_nested_kv(payload: dict[str, object], *, indent: int = 0) -> None:
    """Render a nested safe report as indented key/value text."""
    prefix = "  " * indent
    for key, value in payload.items():
        if isinstance(value, dict):
            typer.echo(f"{prefix}{key}:")
            _echo_nested_kv(value, indent=indent + 1)
            continue
        if isinstance(value, list):
            simple = all(
                item is None or isinstance(item, (str, int, float, bool))
                for item in value
            )
            if simple:
                typer.echo(
                    f"{prefix}{key}: {json.dumps(value, default=_json_default, sort_keys=True)}"
                )
                continue
            typer.echo(f"{prefix}{key}:")
            for item in value:
                typer.echo(
                    f"{prefix}  - {json.dumps(item, default=_json_default, sort_keys=True)}"
                )
            continue
        if isinstance(value, datetime):
            display = value.isoformat()
        elif isinstance(value, Decimal):
            display = str(value)
        elif value is None:
            display = ""
        else:
            display = str(value)
        typer.echo(f"{prefix}{key}: {display}")


@policy_app.command("effective")
def policy_effective(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show the key's effective policy (configuration-only, not authentication).

    Renders configured versus effective values with their source (key,
    deployment, default, or none), safe lifetime quotas, allow-lists,
    Responses/Codex module identity, and Redis configuration. A null per-key
    rate is inherited (deployment value), never unlimited; a null lifetime
    quota is unlimited.
    """
    try:
        report = _run_async(
            _effective_policy_report(
                _parse_uuid(gateway_key_id, field_name="gateway_key_id")
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    if json_output:
        _emit_json(report)
        return
    _echo_nested_kv(report)


@policy_app.command("explain-route")
def policy_explain_route(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    model: Annotated[
        str,
        typer.Option("--model", help="Requested model name"),
    ],
    endpoint: Annotated[
        str,
        typer.Option(
            "--endpoint",
            help="Endpoint path or stable ID (default /v1/chat/completions)",
        ),
    ] = "/v1/chat/completions",
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Explain which configuration grants or blocks model access.

    Configuration-only: it names the grant/route/provider/known-capability
    that allows or prevents access without issuing inference, reserving
    quota, or contacting a provider. The runtime 1000-route candidate bound
    is preserved and disclosed.
    """
    if not model or not model.strip():
        raise typer.BadParameter("--model is required")
    try:
        report = _run_async(
            _explain_model_route(
                gateway_key_id=_parse_uuid(gateway_key_id, field_name="gateway_key_id"),
                model=model.strip(),
                endpoint=endpoint,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    if json_output:
        _emit_json(report)
        return
    _echo_nested_kv(report)


@policy_app.command("update")
def policy_update(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    ctx: typer.Context,
    allowed_models: Annotated[
        list[str] | None,
        typer.Option(
            "--allowed-model",
            help="Allowed model ID; repeatable",
            callback=policy_source_callback,
        ),
    ] = None,
    allowed_endpoints: Annotated[
        list[str] | None,
        typer.Option(
            "--allowed-endpoint",
            help="Allowed /v1 endpoint path; repeatable",
            callback=policy_source_callback,
        ),
    ] = None,
    allow_all_models: Annotated[
        bool,
        typer.Option(
            "--allow-all-models/--no-allow-all-models",
            help="Allow all route-backed models",
            callback=policy_source_callback,
        ),
    ] = False,
    allow_all_endpoints: Annotated[
        bool,
        typer.Option(
            "--allow-all-endpoints/--no-allow-all-endpoints",
            help="Allow all implemented endpoints",
            callback=policy_source_callback,
        ),
    ] = False,
    allowed_providers: Annotated[
        list[str] | None,
        typer.Option(
            "--allowed-provider",
            help="Allowed upstream provider; repeatable",
            callback=policy_source_callback,
        ),
    ] = None,
    provider_all: Annotated[
        bool,
        typer.Option(
            "--provider-all",
            help="Unrestricted provider access (no provider allow-list)",
            callback=policy_source_callback,
        ),
    ] = False,
    provider_none: Annotated[
        bool,
        typer.Option(
            "--provider-none",
            help="Deny all providers (empty provider allow-list)",
            callback=policy_source_callback,
        ),
    ] = False,
    policy_file: Annotated[
        Path | None,
        typer.Option(
            "--policy-file",
            help="Versioned key-configuration policy file (only policy source)",
            callback=policy_source_callback,
        ),
    ] = None,
    confirm_external_tool_fenced: Annotated[
        bool,
        typer.Option(
            "--confirm-external-tool-fenced",
            help="Explicit acknowledgement for a fenced external-tool policy",
            callback=policy_source_callback,
        ),
    ] = False,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Required audit reason")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Update endpoint/model request policy for one gateway key.

    Omitted policy flags preserve the current values; an explicit flag
    changes exactly that member. Use --policy-file for a full typed
    configuration.
    """
    try:
        sources = policy_sources(ctx)
        if was_explicit(sources, "policy_file"):
            # Same pre-authoring bootstrap as create: a file may carry an
            # exact client-module pin, and every CLI process starts with
            # only the packaged registry. A misconfigured profile file
            # fails closed with a fixed safe message (no packaged fallback).
            _bootstrap_codex_profile(get_settings())
            validate_policy_file_conflicts(sources)
            configuration = read_policy_file(policy_file)
            # Explicit confirmation control may accompany the file: the
            # file's own field wins when present, otherwise the explicit
            # CLI flag supplies the acknowledgement.
            if (
                was_explicit(sources, "confirm_external_tool_fenced")
                and confirm_external_tool_fenced
                and not configuration.has("confirm_external_tool_fenced")
            ):
                configuration.confirm_external_tool_fenced = True
        else:
            configuration = build_configuration_from_explicit_flags(
                sources,
                allowed_models=allowed_models,
                allowed_endpoints=allowed_endpoints,
                allow_all_models=allow_all_models,
                allow_all_endpoints=allow_all_endpoints,
            )
            provider_value = provider_flags_value(
                sources,
                allowed_providers=allowed_providers,
                provider_all=provider_all,
                provider_none=provider_none,
            )
            if provider_value is not PROVIDER_ABSENT:
                configuration.allowed_providers = provider_value
            if (
                was_explicit(sources, "confirm_external_tool_fenced")
                and confirm_external_tool_fenced
            ):
                configuration.confirm_external_tool_fenced = True
        if configuration.is_empty():
            raise typer.BadParameter(
                "No requested policy change: provide at least one explicit "
                "policy flag or --policy-file."
            )
        result = _run_async(
            _update_configuration(
                UpdateGatewayKeyConfigurationInput(
                    gateway_key_id=_parse_uuid(gateway_key_id, field_name="gateway_key_id"),
                    configuration=configuration,
                    actor_admin_id=(
                        _parse_uuid(actor_admin_id, field_name="actor_admin_id")
                        if actor_admin_id
                        else None
                    ),
                    reason=reason,
                )
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    safe_result = _management_result_dict(result)
    if json_output:
        _emit_json(safe_result)
        return
    _echo_kv(safe_result)


@policy_app.command("export")
def policy_export(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
) -> None:
    """Export the key's administtered policy as a version-1 configuration document."""
    try:
        document = _run_async(
            _export_configuration(_parse_uuid(gateway_key_id, field_name="gateway_key_id"))
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc)
        return
    _emit_json(document)

@external_tools_app.command("show")
def external_tools_show(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show canonical safe external-tool policy and its bounded runtime scope."""
    try:
        gateway_key = _run_async(
            _show_gateway_key(_parse_uuid(gateway_key_id, field_name="gateway_key_id"))
        )
        payload = {
            "gateway_key_id": gateway_key.id,
            "public_key_id": gateway_key.public_key_id,
            "external_tool_policy": _external_tool_policy_from_gateway_key(gateway_key),
            "runtime_status": "denied_pending_objectives_014_016",
        }
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return
    if json_output:
        _emit_json(payload)
        return
    _echo_kv(payload)


@external_tools_app.command("update")
def external_tools_update(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    mode: Annotated[
        str,
        typer.Option("--mode", help="strict_bounded or external_tool_fenced"),
    ] = STRICT_BOUNDED,
    capabilities: Annotated[
        list[str] | None,
        typer.Option("--capability", help="Reviewed external capability ID; repeatable"),
    ] = None,
    destination_ids: Annotated[
        list[str] | None,
        typer.Option("--destination-id", help="Reviewed opaque destination ID; repeatable"),
    ] = None,
    max_calls: Annotated[
        int,
        typer.Option("--max-calls", help="Positive provider-tool call cap; zero for strict"),
    ] = 0,
    acknowledge_single_request_overrun: Annotated[
        bool,
        typer.Option(
            "--acknowledge-single-request-overrun",
            help="Acknowledge future one-request overrun and final-cost hold behavior",
        ),
    ] = False,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Required second confirmation for fenced mode"),
    ] = False,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str, typer.Option("--reason", help="Required audit reason")] = "",
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Replace audited external-tool policy; only exact fenced web search can run."""
    try:
        result = _run_async(
            _update_external_tool_policy(
                UpdateGatewayKeyExternalToolPolicyInput(
                    gateway_key_id=_parse_uuid(
                        gateway_key_id,
                        field_name="gateway_key_id",
                    ),
                    external_tool_policy=_external_tool_policy_from_options(
                        mode=mode,
                        capabilities=capabilities,
                        destination_ids=destination_ids,
                        max_calls=max_calls,
                        acknowledge_single_request_overrun=(acknowledge_single_request_overrun),
                    ),
                    confirm_external_tool_fenced=confirm,
                    actor_admin_id=(
                        _parse_uuid(actor_admin_id, field_name="actor_admin_id")
                        if actor_admin_id
                        else None
                    ),
                    reason=reason,
                )
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return
    payload = _management_result_dict(result)
    payload["runtime_status"] = "denied_pending_objectives_014_016"
    if json_output:
        _emit_json(payload)
        return
    _echo_kv(payload)


def _status_command_common(
    *,
    command: str,
    gateway_key_id: str,
    actor_admin_id: str | None,
    reason: str | None,
    json_output: bool,
) -> None:
    parsed_id = _parse_uuid(gateway_key_id, field_name="gateway_key_id")
    parsed_actor = (
        _parse_uuid(actor_admin_id, field_name="actor_admin_id") if actor_admin_id else None
    )
    if command == "suspend":
        coro = _suspend_gateway_key(
            SuspendGatewayKeyInput(parsed_id, actor_admin_id=parsed_actor, reason=reason)
        )
    elif command == "activate":
        coro = _activate_gateway_key(
            ActivateGatewayKeyInput(parsed_id, actor_admin_id=parsed_actor, reason=reason)
        )
    else:
        coro = _revoke_gateway_key(
            RevokeGatewayKeyInput(parsed_id, actor_admin_id=parsed_actor, reason=reason)
        )

    try:
        result = _run_async(coro)
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    safe_result = _management_result_dict(result)
    if json_output:
        _emit_json(safe_result)
        return
    _echo_kv(safe_result)


@app.command("suspend")
def suspend(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Suspend an active gateway key."""
    _status_command_common(
        command="suspend",
        gateway_key_id=gateway_key_id,
        actor_admin_id=actor_admin_id,
        reason=reason,
        json_output=json_output,
    )


@app.command("activate")
def activate(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Activate a suspended gateway key."""
    _status_command_common(
        command="activate",
        gateway_key_id=gateway_key_id,
        actor_admin_id=actor_admin_id,
        reason=reason,
        json_output=json_output,
    )


@app.command("revoke")
def revoke(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Revoke an active or suspended gateway key."""
    if not reason and not json_output:
        typer.secho(
            "Warning: --reason is recommended for revocation audit logs.", fg=typer.colors.YELLOW
        )
    _status_command_common(
        command="revoke",
        gateway_key_id=gateway_key_id,
        actor_admin_id=actor_admin_id,
        reason=reason,
        json_output=json_output,
    )


@app.command("extend")
def extend(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    valid_until: Annotated[
        str | None,
        typer.Option("--valid-until", help="New ISO valid-until datetime"),
    ] = None,
    valid_days: Annotated[
        int | None,
        typer.Option("--valid-days", help="Set valid-until to now plus this many days"),
    ] = None,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Update a gateway key validity end time."""
    payload = UpdateGatewayKeyValidityInput(
        gateway_key_id=_parse_uuid(gateway_key_id, field_name="gateway_key_id"),
        valid_until=_valid_until_from_options(
            valid_from=None,
            valid_until=valid_until,
            valid_days=valid_days,
        ),
        actor_admin_id=_parse_uuid(actor_admin_id, field_name="actor_admin_id")
        if actor_admin_id
        else None,
        reason=reason,
    )
    try:
        result = _run_async(_update_validity(payload))
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    safe_result = _management_result_dict(result)
    if json_output:
        _emit_json(safe_result)
        return
    _echo_kv(safe_result)


@app.command("set-limits")
def set_limits(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    cost_limit_eur: Annotated[
        str | None,
        typer.Option("--cost-limit-eur", help="Cost limit in EUR"),
    ] = None,
    token_limit_total: Annotated[
        int | None,
        typer.Option("--token-limit-total", help="Total token limit"),
    ] = None,
    request_limit_total: Annotated[
        int | None,
        typer.Option("--request-limit-total", help="Total request limit"),
    ] = None,
    clear_cost_limit: Annotated[
        bool,
        typer.Option("--clear-cost-limit", help="Clear cost limit"),
    ] = False,
    clear_token_limit: Annotated[
        bool,
        typer.Option("--clear-token-limit", help="Clear token limit"),
    ] = False,
    clear_request_limit: Annotated[
        bool,
        typer.Option("--clear-request-limit", help="Clear request limit"),
    ] = False,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Set or clear gateway key limits."""
    if clear_cost_limit and cost_limit_eur is not None:
        raise typer.BadParameter("Use either --cost-limit-eur or --clear-cost-limit")
    if clear_token_limit and token_limit_total is not None:
        raise typer.BadParameter("Use either --token-limit-total or --clear-token-limit")
    if clear_request_limit and request_limit_total is not None:
        raise typer.BadParameter("Use either --request-limit-total or --clear-request-limit")
    if token_limit_total is not None and token_limit_total <= 0:
        raise typer.BadParameter("--token-limit-total must be positive")
    if request_limit_total is not None and request_limit_total <= 0:
        raise typer.BadParameter("--request-limit-total must be positive")

    try:
        result = _run_async(
            _update_limits(
                gateway_key_id=_parse_uuid(gateway_key_id, field_name="gateway_key_id"),
                cost_limit_eur=_parse_decimal(cost_limit_eur, field_name="cost_limit_eur"),
                token_limit_total=token_limit_total,
                request_limit_total=request_limit_total,
                clear_cost_limit=clear_cost_limit,
                clear_token_limit=clear_token_limit,
                clear_request_limit=clear_request_limit,
                actor_admin_id=_parse_uuid(actor_admin_id, field_name="actor_admin_id")
                if actor_admin_id
                else None,
                reason=reason,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    safe_result = _management_result_dict(result)
    if json_output:
        _emit_json(safe_result)
        return
    _echo_kv(safe_result)


@app.command("set-rate-limits")
def set_rate_limits(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    requests_per_minute: Annotated[
        int | None,
        typer.Option("--requests-per-minute", help="Redis request limit per key per window"),
    ] = None,
    tokens_per_minute: Annotated[
        int | None,
        typer.Option("--tokens-per-minute", help="Redis estimated-token limit per key per window"),
    ] = None,
    concurrent_requests: Annotated[
        int | None,
        typer.Option("--concurrent-requests", help="Redis concurrent request limit per key"),
    ] = None,
    window_seconds: Annotated[
        int | None,
        typer.Option("--window-seconds", help="Redis rate-limit window in seconds"),
    ] = None,
    clear_requests: Annotated[
        bool,
        typer.Option("--clear-requests", help="Clear per-key request rate limit"),
    ] = False,
    clear_tokens: Annotated[
        bool,
        typer.Option("--clear-tokens", help="Clear per-key estimated-token rate limit"),
    ] = False,
    clear_concurrency: Annotated[
        bool,
        typer.Option("--clear-concurrency", help="Clear per-key concurrency limit"),
    ] = False,
    clear_window: Annotated[
        bool,
        typer.Option("--clear-window", help="Clear per-key rate-limit window override"),
    ] = False,
    clear_all: Annotated[
        bool,
        typer.Option("--clear-all", help="Clear all per-key Redis rate-limit settings"),
    ] = False,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Set or clear Redis-backed operational rate limits for a gateway key."""
    if clear_all and any(
        (
            requests_per_minute is not None,
            tokens_per_minute is not None,
            concurrent_requests is not None,
            window_seconds is not None,
            clear_requests,
            clear_tokens,
            clear_concurrency,
            clear_window,
        )
    ):
        raise typer.BadParameter("--clear-all cannot be combined with other rate-limit options")
    if clear_requests and requests_per_minute is not None:
        raise typer.BadParameter("Use either --requests-per-minute or --clear-requests")
    if clear_tokens and tokens_per_minute is not None:
        raise typer.BadParameter("Use either --tokens-per-minute or --clear-tokens")
    if clear_concurrency and concurrent_requests is not None:
        raise typer.BadParameter("Use either --concurrent-requests or --clear-concurrency")
    if clear_window and window_seconds is not None:
        raise typer.BadParameter("Use either --window-seconds or --clear-window")
    if not any(
        (
            requests_per_minute is not None,
            tokens_per_minute is not None,
            concurrent_requests is not None,
            window_seconds is not None,
            clear_requests,
            clear_tokens,
            clear_concurrency,
            clear_window,
            clear_all,
        )
    ):
        raise typer.BadParameter("Provide at least one rate-limit option")

    _validate_positive_int(requests_per_minute, option_name="--requests-per-minute")
    _validate_positive_int(tokens_per_minute, option_name="--tokens-per-minute")
    _validate_positive_int(concurrent_requests, option_name="--concurrent-requests")
    _validate_positive_int(window_seconds, option_name="--window-seconds")

    try:
        result = _run_async(
            _update_rate_limits(
                gateway_key_id=_parse_uuid(gateway_key_id, field_name="gateway_key_id"),
                requests_per_minute=requests_per_minute,
                tokens_per_minute=tokens_per_minute,
                concurrent_requests=concurrent_requests,
                window_seconds=window_seconds,
                clear_requests=clear_requests,
                clear_tokens=clear_tokens,
                clear_concurrency=clear_concurrency,
                clear_window=clear_window,
                clear_all=clear_all,
                actor_admin_id=_parse_uuid(actor_admin_id, field_name="actor_admin_id")
                if actor_admin_id
                else None,
                reason=reason,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    safe_result = _management_result_dict(result)
    if json_output:
        _emit_json(safe_result)
        return
    _echo_kv(safe_result)


@app.command("set-lazy-throttling")
def set_lazy_throttling(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="wait or reject"),
    ] = None,
    max_wait_seconds: Annotated[
        str | None,
        typer.Option(
            "--max-wait-seconds",
            help=(
                "Positive whole seconds to wait, for --mode wait only "
                "(within the installation ceiling)"
            ),
        ),
    ] = None,
    max_waiting_requests: Annotated[
        str | None,
        typer.Option(
            "--max-waiting-requests",
            help=(
                "Positive whole waiting bound, for --mode wait only "
                "(within the installation ceiling)"
            ),
        ),
    ] = None,
    clear: Annotated[
        bool,
        typer.Option(
            "--clear",
            help="Clear the stored policy (default immediate rejection)",
        ),
    ] = False,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Required audit reason")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Set or clear the key's bounded lazy (waiting) throttling policy.

    Semantics:
    - ``--mode wait`` requires BOTH positive ``--max-wait-seconds`` and
      ``--max-waiting-requests`` within the installation ceilings; the shared
      KeyService validator remains the authority and is re-applied in the
      same caller-owned transaction.
    - ``--mode reject`` removes the stored override (default immediate
      rejection). It cannot be combined with waiting bounds: the shared
      KeyService canonicalizes a reject policy to "no stored override", so
      any supplied bounds would be silently discarded; the CLI refuses them
      before any mutation. Use ``--mode wait`` for waiting bounds.
    - ``--clear`` removes the stored policy (default immediate rejection).
    - Plain reject and clear are distinct verbs with the SAME stored outcome
      (no stored override / immediate rejection); neither accepts waiting
      bounds, and they cannot be combined with each other.

    Waiting never relaxes hard quota, auth, security, or pricing, and changing
    it touches only the key's lazy metadata, ``updated_at``, and one audit row.
    """
    max_wait_seconds = parse_int_option(max_wait_seconds, field_name="--max-wait-seconds")
    max_waiting_requests = parse_int_option(
        max_waiting_requests, field_name="--max-waiting-requests"
    )
    if clear and (
        mode is not None or max_wait_seconds is not None or max_waiting_requests is not None
    ):
        raise typer.BadParameter(
            "--clear cannot be combined with --mode or waiting bounds"
        )
    if mode is None and not clear:
        raise typer.BadParameter("Provide --mode wait, --mode reject, or --clear")
    if mode is not None and mode not in ("wait", "reject"):
        raise typer.BadParameter("--mode must be wait or reject")
    if mode == "reject" and (
        max_wait_seconds is not None or max_waiting_requests is not None
    ):
        raise typer.BadParameter(
            "--mode reject cannot be combined with --max-wait-seconds or "
            "--max-waiting-requests; use --mode wait for waiting bounds"
        )
    if mode == "wait" and (
        max_wait_seconds is None or max_waiting_requests is None
    ):
        raise typer.BadParameter(
            "--mode wait requires both --max-wait-seconds and --max-waiting-requests"
        )
    _validate_positive_int(max_wait_seconds, option_name="--max-wait-seconds")
    _validate_positive_int(
        max_waiting_requests, option_name="--max-waiting-requests"
    )
    if not reason or not reason.strip():
        raise typer.BadParameter("--reason is required")

    # Operator ceilings (installation values) gate bounds up front. The shared
    # service re-validates in the write path and remains the authority.
    if max_wait_seconds is not None or max_waiting_requests is not None:
        settings = get_settings()
        if (
            max_wait_seconds is not None
            and max_wait_seconds > settings.LAZY_THROTTLING_MAX_WAIT_SECONDS
        ):
            raise typer.BadParameter(
                "--max-wait-seconds exceeds the operator ceiling for this installation"
            )
        if (
            max_waiting_requests is not None
            and max_waiting_requests
            > settings.LAZY_THROTTLING_MAX_WAITING_PER_KEY
        ):
            raise typer.BadParameter(
                "--max-waiting-requests exceeds the operator ceiling for this installation"
            )

    policy: dict[str, object] | None
    if mode == "wait":
        policy = {
            "mode": "wait",
            "max_wait_seconds": max_wait_seconds,
            "max_waiting_requests": max_waiting_requests,
        }
    else:
        # reject and clear both remove/normalize to the canonical reject policy.
        policy = None

    try:
        result = _run_async(
            _update_lazy_throttling(
                gateway_key_id=_parse_uuid(gateway_key_id, field_name="gateway_key_id"),
                policy=policy,
                actor_admin_id=_parse_uuid(actor_admin_id, field_name="actor_admin_id")
                if actor_admin_id
                else None,
                reason=reason,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    safe_result = _management_result_dict(result)
    if json_output:
        _emit_json(safe_result)
        return
    _echo_kv(safe_result)


@app.command("set-chat-streaming-live-burn")
def set_chat_streaming_live_burn(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    enabled: Annotated[
        bool | None,
        typer.Option(
            "--enabled/--disabled",
            help=(
                "Enable or disable Chat Completions streaming live-burn monitoring "
                "for /v1/chat/completions stream=true"
            ),
        ),
    ] = None,
    cost_margin_eur: Annotated[
        str | None,
        typer.Option(
            "--cost-margin-eur",
            help=(
                "Cost margin in EUR; positive stops early, zero stops near the boundary, "
                "negative allows bounded overrun"
            ),
        ),
    ] = None,
    token_margin: Annotated[
        int | None,
        typer.Option(
            "--token-margin",
            help=(
                "Output token margin; positive stops early, zero stops near the boundary, "
                "negative allows bounded overrun"
            ),
        ),
    ] = None,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Required audit reason")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Set Chat Completions streaming live-burn policy for a gateway key.

    Applies only to /v1/chat/completions stream=true. Positive margins stop
    early, zero margins stop near the boundary, and negative margins allow
    bounded estimated overrun.
    """
    if enabled is None and cost_margin_eur is None and token_margin is None:
        raise typer.BadParameter("Provide --enabled/--disabled or at least one margin option")
    if not reason or not reason.strip():
        raise typer.BadParameter("--reason is required")

    try:
        gateway_key = _run_async(
            _show_gateway_key(_parse_uuid(gateway_key_id, field_name="gateway_key_id"))
        )
        existing = _chat_streaming_live_burn_policy_from_gateway_key(gateway_key)
        policy = normalize_chat_streaming_live_burn_policy(
            {
                "version": 1,
                "enabled": existing["enabled"] if enabled is None else enabled,
                "cost_margin_eur": (
                    existing["cost_margin_eur"]
                    if cost_margin_eur is None
                    else _parse_required_decimal(
                        cost_margin_eur,
                        field_name="cost_margin_eur",
                    )
                ),
                "token_margin": existing["token_margin"] if token_margin is None else token_margin,
            },
            max_abs_cost_margin_eur=Decimal("1000000"),
            max_abs_token_margin=1000000000,
        )
        result = _run_async(
            _update_chat_streaming_live_burn(
                UpdateGatewayKeyChatStreamingLiveBurnInput(
                    gateway_key_id=gateway_key.id,
                    chat_streaming_live_burn_policy=policy.to_metadata(),
                    actor_admin_id=(
                        _parse_uuid(actor_admin_id, field_name="actor_admin_id")
                        if actor_admin_id
                        else None
                    ),
                    reason=reason,
                )
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    safe_result = _management_result_dict(result)
    if json_output:
        _emit_json(safe_result)
        return
    _echo_kv(safe_result)


@app.command("reset-usage")
def reset_usage(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    reset_used: Annotated[
        bool,
        typer.Option("--reset-used/--no-reset-used", help="Reset used counters"),
    ] = True,
    reset_reserved: Annotated[
        bool,
        typer.Option("--reset-reserved", help="Reset reserved counters as an admin repair"),
    ] = False,
    confirm_reset_reserved: Annotated[
        bool,
        typer.Option(
            "--confirm-reset-reserved",
            help="Confirm reserved-counter repair reset",
        ),
    ] = False,
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Reset gateway key usage counters without deleting usage ledger rows."""
    if reset_reserved:
        _warn_reserved_counter_reset()
        if not confirm_reset_reserved:
            _handle_cli_error(
                CliKeyError("Use --confirm-reset-reserved with --reset-reserved"),
                json_output=json_output,
            )
            return
    payload = ResetGatewayKeyUsageInput(
        gateway_key_id=_parse_uuid(gateway_key_id, field_name="gateway_key_id"),
        reset_used_counters=reset_used,
        reset_reserved_counters=reset_reserved,
        actor_admin_id=_parse_uuid(actor_admin_id, field_name="actor_admin_id")
        if actor_admin_id
        else None,
        reason=reason,
    )
    try:
        result = _run_async(_reset_usage(payload))
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    safe_result = _management_result_dict(result)
    if json_output:
        _emit_json(safe_result)
        return
    _echo_kv(safe_result)


@app.command("rotate")
def rotate(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    actor_admin_id: Annotated[
        str | None,
        typer.Option("--actor-admin-id", help="Acting admin UUID"),
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason", help="Audit reason")] = None,
    revoke_old: Annotated[
        bool,
        typer.Option("--revoke-old/--keep-old-active", help="Revoke old key after rotation"),
    ] = True,
    valid_until: Annotated[
        str | None,
        typer.Option("--valid-until", help="Replacement ISO valid-until datetime"),
    ] = None,
    valid_days: Annotated[
        int | None,
        typer.Option("--valid-days", help="Replacement valid-until as now plus days"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
    show_plaintext: Annotated[
        bool,
        typer.Option(
            "--show-plaintext", help="Include the replacement plaintext key in JSON output"
        ),
    ] = False,
    secret_output_file: Annotated[
        Path | None,
        typer.Option(
            "--secret-output-file",
            help="Write the replacement plaintext key to a new 0600 file",
        ),
    ] = None,
    email_delivery: Annotated[
        EmailDeliveryMode,
        typer.Option(
            "--email-delivery",
            help="Replacement key email delivery mode: none, pending, send-now, or enqueue",
        ),
    ] = EmailDeliveryMode.none,
) -> None:
    """Rotate a gateway key and print the replacement plaintext key once."""
    try:
        _validate_secret_output_options(
            json_output=json_output,
            show_plaintext=show_plaintext,
            secret_output_file=secret_output_file,
            email_delivery_mode=email_delivery,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    new_valid_until = (
        _valid_until_from_options(valid_from=None, valid_until=valid_until, valid_days=valid_days)
        if valid_until is not None or valid_days is not None
        else None
    )
    payload = RotateGatewayKeyInput(
        gateway_key_id=_parse_uuid(gateway_key_id, field_name="gateway_key_id"),
        actor_admin_id=_parse_uuid(actor_admin_id, field_name="actor_admin_id")
        if actor_admin_id
        else None,
        reason=reason,
        revoke_old_key=revoke_old,
        new_valid_until=new_valid_until,
    )
    try:
        if email_delivery == EmailDeliveryMode.none:
            cli_result = KeyEmailDeliveryCliResult(
                key_result=_run_async(_rotate_gateway_key(payload))
            )
        else:
            cli_result = _run_async(
                _rotate_gateway_key_with_email_delivery(
                    payload,
                    email_delivery_mode=email_delivery,
                )
            )
        result = cli_result.key_result
        if not isinstance(result, RotatedGatewayKeyResult):
            raise CliKeyError("Unexpected key rotation result")
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    if email_delivery in {EmailDeliveryMode.send_now, EmailDeliveryMode.enqueue}:
        _warn_email_delivery_channel(email_delivery)
    elif secret_output_file is not None:
        try:
            write_secret_file(secret_output_file, result.new_plaintext_key)
        except Exception as exc:  # noqa: BLE001
            _handle_cli_error(exc, json_output=json_output)
            return
        _warn_secret_file(secret_output_file)
    elif show_plaintext or not json_output:
        _warn_plaintext_display()
    if email_delivery == EmailDeliveryMode.pending:
        _warn_email_delivery_channel(email_delivery)

    include_plaintext = (
        email_delivery not in {EmailDeliveryMode.send_now, EmailDeliveryMode.enqueue}
        and secret_output_file is None
        and (show_plaintext or not json_output)
    )
    payload_dict = _rotated_key_dict(result, include_plaintext=include_plaintext)
    payload_dict = _append_email_delivery_payload(
        payload_dict,
        delivery_result=cli_result.delivery_result,
        celery_task_id=cli_result.celery_task_id,
    )
    if json_output:
        _emit_json(payload_dict)
        _exit_if_email_delivery_failed(cli_result.delivery_result)
        return

    _echo_kv(payload_dict)
    _exit_if_email_delivery_failed(cli_result.delivery_result)


def _safe_output_has_no_secrets(output: str, forbidden_terms: Sequence[str]) -> bool:
    """Test helper to keep CLI safety checks readable."""
    lowered = output.lower()
    return not any(term.lower() in lowered for term in forbidden_terms)

"""Typer commands for service-backed gateway key management."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any

import typer

from slaif_gateway.cli.common import CliError, write_secret_file
from slaif_gateway.config import Settings, get_settings
from slaif_gateway.db.models import GatewayKey
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.session import get_sessionmaker
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
    UpdateGatewayKeyLimitsInput,
    UpdateGatewayKeyRateLimitsInput,
    UpdateGatewayKeyValidityInput,
)
from slaif_gateway.services.key_errors import GatewayKeyNotFoundError, KeyManagementError
from slaif_gateway.services.key_service import KeyService

app = typer.Typer(help="Manage gateway keys")


class CliKeyError(Exception):
    """Safe CLI-facing key command error."""


class CliDatabaseConfigError(CliKeyError):
    """Raised when CLI database settings are missing or invalid."""


@asynccontextmanager
async def _key_runtime() -> AsyncIterator[tuple[Settings, GatewayKeysRepository, KeyService]]:
    settings = get_settings()
    if not settings.DATABASE_URL:
        raise CliDatabaseConfigError("DATABASE_URL is not configured. Set DATABASE_URL and try again.")

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
            )
            yield settings, keys_repository, service


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
        policy["requests_per_minute"] = _validate_positive_int(
            requests_per_minute,
            option_name="--rate-limit-requests-per-minute",
        ) or requests_per_minute
    if tokens_per_minute is not None:
        policy["tokens_per_minute"] = _validate_positive_int(
            tokens_per_minute,
            option_name="--rate-limit-tokens-per-minute",
        ) or tokens_per_minute
    if concurrent_requests is not None:
        policy["max_concurrent_requests"] = _validate_positive_int(
            concurrent_requests,
            option_name="--rate-limit-concurrent-requests",
        ) or concurrent_requests
    if window_seconds is not None:
        policy["window_seconds"] = _validate_positive_int(
            window_seconds,
            option_name="--rate-limit-window-seconds",
        ) or window_seconds
    return policy or None


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
        "revoked_reason": gateway_key.revoked_reason,
        "rate_limit_policy": _rate_limit_policy_from_gateway_key(gateway_key),
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
    }


def _created_key_dict(result: CreatedGatewayKey, *, include_plaintext: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        "gateway_key_id": result.gateway_key_id,
        "owner_id": result.owner_id,
        "public_key_id": result.public_key_id,
        "display_prefix": result.display_prefix,
        "one_time_secret_id": result.one_time_secret_id,
        "valid_from": result.valid_from,
        "valid_until": result.valid_until,
        "rate_limit_policy": result.rate_limit_policy,
    }
    if include_plaintext:
        payload["plaintext_key"] = result.plaintext_key
    return payload


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
) -> None:
    if show_plaintext and secret_output_file is not None:
        raise typer.BadParameter("Use either --show-plaintext or --secret-output-file, not both")
    if json_output and not show_plaintext and secret_output_file is None:
        raise typer.BadParameter(
            "JSON output does not include plaintext keys by default; use --show-plaintext "
            "or --secret-output-file PATH"
        )
    if secret_output_file is not None and secret_output_file.exists():
        raise typer.BadParameter(f"Secret output file already exists: {secret_output_file}")


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


def _warn_reserved_counter_reset() -> None:
    typer.secho(
        "Warning: resetting reserved counters is an admin repair action and does not delete ledger rows.",
        fg=typer.colors.YELLOW,
        err=True,
    )


async def _create_gateway_key(payload: CreateGatewayKeyInput) -> CreatedGatewayKey:
    async with _key_runtime() as (_, _, service):
        return await service.create_gateway_key(payload)


async def _list_gateway_keys(
    *,
    owner_id: uuid.UUID | None,
    cohort_id: uuid.UUID | None,
    status: str | None,
    limit: int,
) -> list[GatewayKey]:
    async with _key_runtime() as (_, keys_repository, _):
        return await keys_repository.list_gateway_keys(
            owner_id=owner_id,
            cohort_id=cohort_id,
            status=status,
            limit=limit,
        )


async def _show_gateway_key(gateway_key_id: uuid.UUID) -> GatewayKey:
    async with _key_runtime() as (_, keys_repository, _):
        gateway_key = await keys_repository.get_gateway_key_by_id(gateway_key_id)
        if gateway_key is None:
            raise GatewayKeyNotFoundError()
        return gateway_key


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


async def _reset_usage(payload: ResetGatewayKeyUsageInput) -> GatewayKeyManagementResult:
    async with _key_runtime() as (_, _, service):
        return await service.reset_gateway_key_usage(payload)


async def _rotate_gateway_key(payload: RotateGatewayKeyInput) -> RotatedGatewayKeyResult:
    async with _key_runtime() as (_, _, service):
        return await service.rotate_gateway_key(payload)


@app.callback()
def keys() -> None:
    """Manage gateway keys."""


@app.command("create")
def create(
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
    allowed_models: Annotated[
        list[str] | None,
        typer.Option("--allowed-model", help="Allowed model; repeatable"),
    ] = None,
    allowed_endpoints: Annotated[
        list[str] | None,
        typer.Option("--allowed-endpoint", help="Allowed endpoint; repeatable"),
    ] = None,
    rate_limit_requests_per_minute: Annotated[
        int | None,
        typer.Option(
            "--rate-limit-requests-per-minute",
            help="Redis operational request limit per key per window",
        ),
    ] = None,
    rate_limit_tokens_per_minute: Annotated[
        int | None,
        typer.Option(
            "--rate-limit-tokens-per-minute",
            help="Redis operational estimated-token limit per key per window",
        ),
    ] = None,
    rate_limit_concurrent_requests: Annotated[
        int | None,
        typer.Option(
            "--rate-limit-concurrent-requests",
            help="Redis operational concurrent request limit per key",
        ),
    ] = None,
    rate_limit_window_seconds: Annotated[
        int | None,
        typer.Option(
            "--rate-limit-window-seconds",
            help="Redis operational rate-limit window in seconds",
        ),
    ] = None,
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
        typer.Option("--secret-output-file", help="Write the one-time plaintext key to a new 0600 file"),
    ] = None,
) -> None:
    """Create a gateway key and print the plaintext key once."""
    try:
        _validate_secret_output_options(
            json_output=json_output,
            show_plaintext=show_plaintext,
            secret_output_file=secret_output_file,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    parsed_valid_from = _parse_datetime(valid_from, field_name="valid_from") or datetime.now(UTC)
    payload = CreateGatewayKeyInput(
        owner_id=_parse_uuid(owner_id, field_name="owner_id"),
        cohort_id=_parse_uuid(cohort_id, field_name="cohort_id") if cohort_id else None,
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
        rate_limit_policy=_rate_limit_policy_from_options(
            requests_per_minute=rate_limit_requests_per_minute,
            tokens_per_minute=rate_limit_tokens_per_minute,
            concurrent_requests=rate_limit_concurrent_requests,
            window_seconds=rate_limit_window_seconds,
        ),
        created_by_admin_id=(
            _parse_uuid(actor_admin_id, field_name="actor_admin_id") if actor_admin_id else None
        ),
        note=reason,
    )
    try:
        result = _run_async(_create_gateway_key(payload))
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    if secret_output_file is not None:
        try:
            write_secret_file(secret_output_file, result.plaintext_key)
        except Exception as exc:  # noqa: BLE001
            _handle_cli_error(exc, json_output=json_output)
            return
        _warn_secret_file(secret_output_file)
    elif show_plaintext or not json_output:
        _warn_plaintext_display()

    include_plaintext = secret_output_file is None and (show_plaintext or not json_output)
    payload_dict = _created_key_dict(result, include_plaintext=include_plaintext)
    if json_output:
        _emit_json(payload_dict)
        return

    _echo_kv(payload_dict)


@app.command("list")
def list_keys(
    owner_id: Annotated[str | None, typer.Option("--owner-id", help="Owner UUID")] = None,
    cohort_id: Annotated[str | None, typer.Option("--cohort-id", help="Cohort UUID")] = None,
    status: Annotated[str | None, typer.Option("--status", help="Key status")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return")] = 50,
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """List gateway keys using safe metadata only."""
    if limit <= 0:
        raise typer.BadParameter("--limit must be positive")
    try:
        rows = _run_async(
            _list_gateway_keys(
                owner_id=_parse_uuid(owner_id, field_name="owner_id") if owner_id else None,
                cohort_id=_parse_uuid(cohort_id, field_name="cohort_id") if cohort_id else None,
                status=status,
                limit=limit,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    safe_rows = [_safe_gateway_key_dict(row) for row in rows]
    if json_output:
        _emit_json({"keys": safe_rows})
        return

    if not safe_rows:
        typer.echo("No gateway keys found.")
        return
    for index, row in enumerate(safe_rows):
        if index:
            typer.echo("")
        _echo_kv(row)


@app.command("show")
def show(
    gateway_key_id: Annotated[str, typer.Argument(help="Gateway key UUID")],
    json_output: Annotated[bool, typer.Option("--json", help="Output JSON")] = False,
) -> None:
    """Show safe metadata for one gateway key."""
    try:
        gateway_key = _run_async(
            _show_gateway_key(_parse_uuid(gateway_key_id, field_name="gateway_key_id"))
        )
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    safe_row = _safe_gateway_key_dict(gateway_key)
    if json_output:
        _emit_json(safe_row)
        return
    _echo_kv(safe_row)


def _status_command_common(
    *,
    command: str,
    gateway_key_id: str,
    actor_admin_id: str | None,
    reason: str | None,
    json_output: bool,
) -> None:
    parsed_id = _parse_uuid(gateway_key_id, field_name="gateway_key_id")
    parsed_actor = _parse_uuid(actor_admin_id, field_name="actor_admin_id") if actor_admin_id else None
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
        typer.secho("Warning: --reason is recommended for revocation audit logs.", fg=typer.colors.YELLOW)
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
        typer.Option("--show-plaintext", help="Include the replacement plaintext key in JSON output"),
    ] = False,
    secret_output_file: Annotated[
        Path | None,
        typer.Option(
            "--secret-output-file",
            help="Write the replacement plaintext key to a new 0600 file",
        ),
    ] = None,
) -> None:
    """Rotate a gateway key and print the replacement plaintext key once."""
    try:
        _validate_secret_output_options(
            json_output=json_output,
            show_plaintext=show_plaintext,
            secret_output_file=secret_output_file,
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
        result = _run_async(_rotate_gateway_key(payload))
    except Exception as exc:  # noqa: BLE001
        _handle_cli_error(exc, json_output=json_output)
        return

    if secret_output_file is not None:
        try:
            write_secret_file(secret_output_file, result.new_plaintext_key)
        except Exception as exc:  # noqa: BLE001
            _handle_cli_error(exc, json_output=json_output)
            return
        _warn_secret_file(secret_output_file)
    elif show_plaintext or not json_output:
        _warn_plaintext_display()

    include_plaintext = secret_output_file is None and (show_plaintext or not json_output)
    payload_dict = _rotated_key_dict(result, include_plaintext=include_plaintext)
    if json_output:
        _emit_json(payload_dict)
        return

    _echo_kv(payload_dict)


def _safe_output_has_no_secrets(output: str, forbidden_terms: Sequence[str]) -> bool:
    """Test helper to keep CLI safety checks readable."""
    lowered = output.lower()
    return not any(term.lower() in lowered for term in forbidden_terms)

#!/usr/bin/env python3
"""Bounded hermetic/live gate for the unregistered Qwen vision candidate."""

from __future__ import annotations

import hashlib
import getpass
import io
import ipaddress
import json
import os
import subprocess
import sys
import tempfile
import shutil
import socket
import uuid
import base64
import struct
import threading
import zlib
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

import slaif_gateway.services.codex_profile_registry as registry
import slaif_gateway.services.codex_qualification as qualification

BASE_URL_ENV = "SLAIF_QWEN38_VISION_BASE_URL"
API_KEY_ENV = "SLAIF_QWEN38_VISION_API_KEY"
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests/fixtures/codex/0.148.0/qwen3.8-27b-vision-api-key-responses.json"
ALLOWED_FIXTURE_TYPES = frozenset(
    {
        "phase", "request", "response.created", "response.output_item.added",
        "response.function_call_arguments.delta",
        "response.custom_tool_call_input.delta", "response.output_item.done",
        "response.completed", "response.output_text.delta", "tool", "function",
        "stream", "sse", "catalog", "replacement", "route", "provider", "gateway",
        "upstream", "credential_boundary", "substituted", "final", "completed",
        "accounting", "ledger", "reservation", "responses", "codex_0_148", "initial",
        "continuation", "item", "call", "call_id", "function_call", "message",
        "auth_substitution", "header_sanitization", "model_rewrite", "loopback",
        "codex_request_envelope", "codex_client_tools", "codex_streaming_tool_events",
        "text_only", "no_search", "no_parallel", "finalized", "success", "EUR",
        "image_input", "single_image", "no_remote_image",
    }
)
LIVE_CONCURRENCY_LIMIT = 1
MAX_KEY_BYTES = 512
CODEX_BINARY = Path("/usr/bin/codex")
CODEX_VERSION = "0.148.0"
POSTGRES_BIN = Path("/usr/lib/postgresql/16/bin")


class SequentialLiveGuard:
    """Reject overlapping live orchestration in-process and across threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owner: int | None = None

    @contextmanager
    def acquire(self):
        identity = threading.get_ident()
        with self._lock:
            if self._owner is not None:
                raise VerificationError("live_execution_must_be_sequential")
            self._owner = identity
        try:
            yield
        finally:
            with self._lock:
                self._owner = None


LIVE_GUARD = SequentialLiveGuard()


def synthetic_png_data_url(*, width: int = 32, height: int = 32) -> str:
    """Build one tiny deterministic inline PNG without reading user content."""

    if width < 1 or height < 1 or width > 512 or height > 512:
        raise VerificationError("Synthetic image dimensions are outside the bounded range.")
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(((x * 7 + y * 3) % 256, (x * 11 + y * 5) % 256, 128))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return len(data).to_bytes(4, "big") + kind + data + (
            zlib.crc32(kind + data) & 0xFFFFFFFF
        ).to_bytes(4, "big")

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def build_private_postgres_commands(*, data_directory: Path, port: int, database: str) -> tuple[tuple[str, ...], ...]:
    """Return the bounded unprivileged PostgreSQL command sequence."""

    initdb = POSTGRES_BIN / "initdb"
    pg_ctl = POSTGRES_BIN / "pg_ctl"
    createdb = POSTGRES_BIN / "createdb"
    log_path = data_directory.parent / "postgres.log"
    socket_directory = data_directory.parent / "socket"
    return (
        (str(initdb), "-D", str(data_directory), "--auth=trust", "--no-locale", "--encoding=UTF8"),
        (
            str(pg_ctl), "-D", str(data_directory), "-l", str(log_path), "-w", "-t", "20", "start",
            "-o", f"-h 127.0.0.1 -p {port} -k {socket_directory}",
        ),
        (str(createdb), "-h", "127.0.0.1", "-p", str(port), database),
    )


@contextmanager
def private_postgres(*, database_url: str | None = None):
    """Yield one validated disposable DB, self-provisioning only a private cluster."""

    try:
        import verify_codex_gateway_e2e as gateway
    except ModuleNotFoundError:
        from scripts import verify_codex_gateway_e2e as gateway
    if database_url is not None:
        yield gateway.validate_test_database_url(database_url)
        return
    root = Path(tempfile.mkdtemp(prefix="slaif-qwen38-postgres-")).resolve()
    data_directory = root / "data"
    port = _free_loopback_port()
    database = f"qwen38_test_{os.getpid()}_{port}"
    process_started = False
    try:
        (root / "socket").mkdir(mode=0o700)
        commands = build_private_postgres_commands(
            data_directory=data_directory, port=port, database=database
        )
        if any(not Path(command[0]).is_file() for command in commands):
            raise VerificationError("postgres_dependency_unavailable")
        for index, command in enumerate(commands):
            try:
                result = subprocess.run(
                    command,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise VerificationError("postgres_start_failed") from exc
            if result.returncode != 0:
                raise VerificationError("postgres_start_failed")
            process_started = process_started or index == 1
        target = gateway.validate_test_database_url(
            f"postgresql+asyncpg://{getpass.getuser()}@127.0.0.1:{port}/{database}"
        )
        yield target
    finally:
        if process_started:
            pg_ctl = POSTGRES_BIN / "pg_ctl"
            subprocess.run(
                (str(pg_ctl), "-D", str(data_directory), "-w", "-t", "20", "stop", "-m", "fast"),
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        shutil.rmtree(root)


class VerificationError(RuntimeError):
    """A fixed, non-reflecting verifier failure."""


def validate_target_url(value: str) -> str:
    """Accept only a canonical numeric private/loopback/link-local ``/v1`` URL."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise VerificationError("LAN target URL is invalid.")
    if any(ord(char) < 33 or ord(char) == 127 for char in value) or any(
        char in value for char in ("%", "\\")
    ):
        raise VerificationError("LAN target URL is invalid.")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise VerificationError("LAN target URL is invalid.")
    if parsed.query or parsed.fragment or parsed.path != "/v1":
        raise VerificationError("LAN target URL is invalid.")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
    except (ValueError, TypeError) as exc:
        raise VerificationError("LAN target URL must use a private numeric address.") from exc
    if port is not None and not 1 <= port <= 65535:
        raise VerificationError("LAN target URL port is invalid.")
    if not (address.is_private or address.is_loopback or address.is_link_local):
        raise VerificationError("LAN target URL is outside the private boundary.")
    return value


def validate_environment(environment: Mapping[str, str]) -> str:
    base = environment.get(BASE_URL_ENV)
    key = environment.get(API_KEY_ENV)
    if not base and not key:
        return "live_target_absent"
    if not base or not key:
        raise VerificationError("LAN target configuration must provide both variables.")
    validate_target_url(base)
    if (
        not isinstance(key, str)
        or not key
        or len(key.encode("utf-8")) > MAX_KEY_BYTES
        or any(ord(char) < 33 or ord(char) == 127 for char in key)
    ):
        raise VerificationError("LAN target credential is invalid.")
    return "live_target_present"


def parse_arguments(arguments: Sequence[str]) -> None:
    if arguments:
        raise VerificationError("Verifier accepts no arguments.")


def verify_candidate_codex_version(binary: Path = CODEX_BINARY) -> str:
    """Verify the candidate's exact raw version independently of 0.147 capture code."""

    try:
        result = subprocess.run(
            [str(binary), "--version"],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError("codex_version_check_failed") from exc
    if len(result.stdout) > 128 or result.stderr or result.returncode != 0:
        raise VerificationError("codex_version_check_failed")
    try:
        raw = result.stdout.decode("ascii")
    except UnicodeDecodeError as exc:
        raise VerificationError("codex_version_check_failed") from exc
    if raw != f"codex-cli {CODEX_VERSION}\n":
        raise VerificationError("codex_version_mismatch")
    return CODEX_VERSION


def build_observed_fixture(*, facts, actions, runtime, accounting) -> dict[str, object]:
    """Project observed request/SSE/accounting facts into structural evidence only."""

    event_sequence: list[dict[str, object]] = []
    request_phases: list[dict[str, object]] = []
    relationships: list[dict[str, object]] = []
    event_index = 0
    for request_index, (fact, action) in enumerate(zip(facts, actions, strict=True)):
        phase = "initial" if request_index == 0 else "continuation"
        request_phases.append({
            "field_type": "request", "phase": phase, "index": request_index,
            "event_count": len(action.payload), "taxonomy_id": "codex_0_148", "enabled": True,
        })
        for event in action.payload:
            item = event.get("item") if isinstance(event, Mapping) else None
            item_type = item.get("type") if isinstance(item, Mapping) else None
            event_record: dict[str, object] = {
                "event_type": str(event["type"]), "index": event_index,
                "phase": phase, "field_type": "sse",
            }
            if isinstance(item_type, str):
                event_record["tool_type"] = item_type
            if isinstance(item, Mapping) and isinstance(item.get("id"), str):
                event_record["id"] = item["id"]
                if item_type == "function_call":
                    relationships.extend(
                        (
                            {"field_type": "function_call", "id": item["id"], "relation": "item"},
                            {"field_type": "function_call", "id": item.get("call_id", "call"), "relation": "call_id"},
                        )
                    )
            event_sequence.append(event_record)
            event_index += 1
    usage_rows = []
    for row, cost in zip(accounting.usage, accounting.ledger_actual_costs_eur, strict=True):
        input_tokens, cached_tokens, output_tokens, reasoning_tokens, total_tokens = row
        usage_rows.append({
            "field_type": "ledger", "status": "finalized", "enabled": True,
            "input_tokens": input_tokens, "cached_tokens": cached_tokens,
            "output_tokens": output_tokens, "reasoning_tokens": reasoning_tokens,
            "total_tokens": total_tokens,
            "cost_nano_eur": int(cost * 1_000_000_000) if cost is not None else 0,
        })
    return {
        "event_type": "phase", "count": len(facts), "enabled": True,
        "event_sequence": event_sequence,
        "request_facts": {
            "field_type": "request", "count": len(facts), "enabled": True,
            "phases": request_phases, "relationships": relationships,
        },
        "catalog_facts": {
            "field_type": "catalog", "count": 1, "enabled": True,
            "catalog_source": "replacement", "taxonomy_id": "codex_0_148",
            "no_search": {"field_type": "no_search", "enabled": True},
            "no_parallel": {"field_type": "no_parallel", "enabled": True},
        },
        "route_facts": {
            "field_type": "route", "count": 3, "enabled": True, "endpoint": "responses",
            "provider_kind": "openai_compatible", "model_rewrite": "public_to_upstream",
            "gates": [
                {"field_type": "route", "gate": gate, "enabled": True}
                for gate in runtime.required_route_gates
            ],
        },
        "credential_facts": {
            "field_type": "credential_boundary", "count": 2, "enabled": True,
            "facts": [
                {"field_type": "auth_substitution", "enabled": all(f.authorization_replaced for f in facts)},
                {"field_type": "header_sanitization", "enabled": all(f.headers_sanitized for f in facts)},
            ],
        },
        "accounting_facts": {
            "field_type": "accounting", "count": len(usage_rows), "enabled": True,
            "requests_used": accounting.requests_used, "tokens_used": accounting.tokens_used,
            "cost_nano_eur": int(accounting.cost_used_eur * 1_000_000_000),
            "reservations": [
                {"field_type": "reservation", "status": status, "enabled": True}
                for status in accounting.reservation_statuses
            ],
            "ledgers": usage_rows,
        },
    }


def sanitize_captured_fixture(value: object) -> dict[str, object]:
    return registry.sanitize_codex_fixture(value, allowed_types=ALLOWED_FIXTURE_TYPES)


def fixture_digest(value: Mapping[str, object]) -> str:
    without_digest = {key: item for key, item in value.items() if key != "digest"}
    canonical = json.dumps(without_digest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def write_captured_fixture(value: Mapping[str, object]) -> str:
    sanitized = sanitize_captured_fixture(value)
    FIXTURE_PATH.write_text(
        json.dumps(sanitized, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()


def _candidate_runtime_modules():
    try:
        import verify_codex_gateway_e2e as gateway
    except ModuleNotFoundError:
        from scripts import verify_codex_gateway_e2e as gateway
    return gateway, registry, qualification


@contextmanager
def _candidate_runtime_registry():
    gateway, registry, qualification = _candidate_runtime_modules()
    runtime = replace(registry.QWEN38_VISION_CODEX_CANDIDATE, mocked_qualification=True)
    profiles = MappingProxyType(
        {registry.OPENAI_CODEX_PROFILE.profile_id: registry.OPENAI_CODEX_PROFILE, runtime.profile_id: runtime}
    )
    old = (
        registry.CODEX_PROFILE_REGISTRY,
        qualification.CODEX_PROFILE_REGISTRY,
        qualification.CODEX_MODEL,
        qualification.CODEX_PROFILE_ID,
        qualification.CODEX_CLI_VERSION,
        qualification.CODEX_FIXTURE_SHA256,
        gateway.CODEX_MODEL,
    )
    registry.CODEX_PROFILE_REGISTRY = profiles
    qualification.CODEX_PROFILE_REGISTRY = profiles
    qualification.CODEX_MODEL = runtime.public_model
    qualification.CODEX_PROFILE_ID = runtime.profile_id
    qualification.CODEX_CLI_VERSION = runtime.cli_version
    qualification.CODEX_FIXTURE_SHA256 = runtime.fixture_sha256
    gateway.CODEX_MODEL = runtime.public_model
    try:
        yield gateway, runtime
    finally:
        (
            registry.CODEX_PROFILE_REGISTRY,
            qualification.CODEX_PROFILE_REGISTRY,
            qualification.CODEX_MODEL,
            qualification.CODEX_PROFILE_ID,
            qualification.CODEX_CLI_VERSION,
            qualification.CODEX_FIXTURE_SHA256,
            gateway.CODEX_MODEL,
        ) = old


async def _seed_candidate_gateway(
    *, gateway, database_url: str, provider_base_url: str, provider_env: str,
    settings, runtime, zero_pricing: bool = False
):
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal
    from slaif_gateway.db.repositories.audit import AuditRepository
    from slaif_gateway.db.repositories.cohorts import CohortsRepository
    from slaif_gateway.db.repositories.institutions import InstitutionsRepository
    from slaif_gateway.db.repositories.keys import GatewayKeysRepository
    from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
    from slaif_gateway.db.repositories.owners import OwnersRepository
    from slaif_gateway.db.repositories.pricing import PricingRulesRepository
    from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
    from slaif_gateway.db.repositories.routing import ModelRoutesRepository
    from slaif_gateway.schemas.keys import CreateGatewayKeyInput
    from slaif_gateway.services.key_service import KeyService
    from slaif_gateway.services.responses_route_capabilities import default_responses_capabilities
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex[:12]
    try:
        async with sessions() as session:
            institution = await InstitutionsRepository(session).create_institution(
                name=f"Reserved Qwen verifier {suffix}", country="SI", notes="Disposable local verifier"
            )
            owner = await OwnersRepository(session).create_owner(
                name="Reserved", surname="Verifier", email=f"qwen-{suffix}@example.invalid",
                institution_id=institution.id, notes="Disposable local verifier"
            )
            cohort = await CohortsRepository(session).create_cohort(
                name=f"qwen-{suffix}", description="Disposable local verifier cohort",
                starts_at=now - timedelta(minutes=5), ends_at=now + timedelta(hours=2)
            )
            provider_name = "openai_compatible"
            await ProviderConfigsRepository(session).create_provider_config(
                provider=provider_name, display_name="Qwen numeric loopback verifier",
                base_url=provider_base_url, api_key_env_var=provider_env,
                enabled=True, timeout_seconds=30, max_retries=0, notes="Bounded candidate verifier provider"
            )
            responses = default_responses_capabilities()
            responses.update({
                "text": True, "stateless": True, "streaming": True,
                "codex_request_envelope": True, "codex_client_tools": True,
                "codex_streaming_tool_events": True,
                "image_input": True,
            })
            route_caps = {
                "responses": responses,
                "codex_limits": {
                    "context_window_tokens": runtime.context_window_tokens,
                    "default_max_output_tokens": runtime.default_max_output_tokens,
                    "max_output_tokens": runtime.max_output_tokens,
                },
                "codex_profile": {
                    "version": runtime.metadata_version,
                    "profile_id": runtime.profile_id,
                    "fixture_sha256": runtime.fixture_sha256,
                },
            }
            routes = ModelRoutesRepository(session)
            route = await routes.create_model_route(
                requested_model=runtime.public_model, provider=provider_name,
                upstream_model=runtime.upstream_model, match_type="exact",
                endpoint="/v1/responses", priority=1, enabled=True,
                visible_in_models=True, supports_streaming=True, capabilities={},
                notes="Disposable Qwen candidate route"
            )
            await routes.update_model_route_metadata(route.id, capabilities=route_caps)
            pricing = PricingRulesRepository(session)
            input_price = Decimal("0") if zero_pricing else Decimal("1")
            cached_input_price = Decimal("0")
            output_price = Decimal("0") if zero_pricing else Decimal("2")
            reasoning_price = Decimal("0") if zero_pricing else Decimal("2")
            await pricing.create_pricing_rule(
                provider=provider_name, upstream_model=runtime.upstream_model, endpoint="/v1/responses",
                valid_from=now - timedelta(minutes=5), currency="EUR",
                input_price_per_1m=input_price, cached_input_price_per_1m=cached_input_price,
                output_price_per_1m=output_price, reasoning_price_per_1m=reasoning_price,
                request_price=Decimal("0"), pricing_metadata={
                    "codex_accounting": {
                        "long_context_threshold_tokens": 272_000,
                        "long_context_input_multiplier": "2",
                        "long_context_output_multiplier": "1.5",
                        "cache_write_input_multiplier": "1.25",
                    }
                }, notes="Disposable local pricing"
            )
            service = KeyService(
                settings=settings, gateway_keys_repository=GatewayKeysRepository(session),
                one_time_secrets_repository=OneTimeSecretsRepository(session), audit_repository=AuditRepository(session),
                model_routes_repository=routes,
            )
            key = await service.create_gateway_key(CreateGatewayKeyInput(
                owner_id=owner.id, cohort_id=cohort.id, valid_from=now - timedelta(minutes=1),
                valid_until=now + timedelta(hours=1), cost_limit_eur=Decimal("20"),
                token_limit_total=100_000, request_limit_total=4,
                allowed_models=[runtime.public_model], allowed_endpoints=["/v1/models", "/v1/responses"],
                allowed_providers=[provider_name],
                responses_policy={
                    "version": 1,
                    "codex_client_tool_taxonomy": "codex_0_148",
                    "allowed_capabilities": [
                        "codex_request_envelope", "codex_client_tools",
                        "codex_streaming_tool_events", "image_input",
                    ],
                    "allowed_local_tool_types": list(runtime.local_tools),
                },
                rate_limit_policy={"requests_per_minute": 100, "tokens_per_minute": 100_000,
                                   "max_concurrent_requests": 1, "window_seconds": 60},
                note="Disposable Qwen candidate verifier key",
            ))
            await session.commit()
            return key
    finally:
        await engine.dispose()


async def _inspect_candidate_route(*, database_url: str, runtime, provider: str):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
    from slaif_gateway.db.repositories.pricing import PricingRulesRepository
    from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
    from slaif_gateway.db.repositories.routing import ModelRoutesRepository
    engine = create_async_engine(database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            result = await qualification.CodexQualificationService(
                provider_configs_repository=ProviderConfigsRepository(session),
                model_routes_repository=ModelRoutesRepository(session),
                pricing_rules_repository=PricingRulesRepository(session),
                fx_rates_repository=FxRatesRepository(session),
                profile_registry=MappingProxyType({runtime.profile_id: runtime}),
            ).ready_responses_profile(provider=provider, qualification_profile=runtime.profile_id)
            return result
    finally:
        await engine.dispose()


def _accounting_proved(accounting, *, pending: int, exact_hermetic: bool) -> bool:
    """Check fixed hermetic facts or bounded zero-price live facts."""

    common = (
        pending == 0,
        accounting.requests_used == 2,
        accounting.requests_reserved == 0,
        accounting.tokens_reserved == 0,
        accounting.cost_reserved_eur == Decimal("0"),
        accounting.reservation_statuses == ("finalized", "finalized"),
        accounting.ledger_statuses == ("finalized", "finalized"),
        accounting.ledger_successes == (True, True),
        accounting.ledger_error_types == (None, None),
        accounting.ledger_http_statuses == (200, 200),
        accounting.ledger_native_currencies == ("EUR", "EUR"),
        len(accounting.usage) == 2,
        len(accounting.ledger_actual_costs_eur) == 2,
        sum(accounting.ledger_actual_costs_eur, Decimal("0")) == accounting.cost_used_eur,
    )
    if not all(common):
        return False
    if exact_hermetic:
        return (
            accounting.tokens_used == 4
            and accounting.cost_used_eur == Decimal("0.000006000")
            and accounting.usage == ((1, 0, 1, 0, 2), (1, 0, 1, 0, 2))
            and accounting.ledger_actual_costs_eur == (Decimal("0.000003000"), Decimal("0.000003000"))
        )
    if accounting.cost_used_eur != Decimal("0") or accounting.tokens_used <= 0:
        return False
    if any(cost != Decimal("0") for cost in accounting.ledger_actual_costs_eur):
        return False
    if any(
        input_tokens <= 0
        or output_tokens <= 0
        or total_tokens <= 0
        or total_tokens < input_tokens + output_tokens + reasoning_tokens
        for input_tokens, _cached_tokens, output_tokens, reasoning_tokens, total_tokens in accounting.usage
    ):
        return False
    return accounting.tokens_used == sum(row[-1] for row in accounting.usage)


def _candidate_actions(gateway, *, workspace: Path, upstream_model: str):
    tool_source = json.dumps({
        "cmd": "python -c \"from pathlib import Path; Path('qwen38-vision-marker.txt').write_text('SLAIF_QWEN38_FILE_OK\\\\n')\"",
        "workdir": str(workspace),
        "yield_time_ms": 1000,
    }, sort_keys=True, separators=(",", ":"))
    tool_events = [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "type": "function_call", "id": "qwen_vision_tool_item", "status": "in_progress",
                "call_id": "qwen_vision_tool_call", "name": "exec_command", "arguments": "",
            },
        },
        {
            "type": "response.function_call_arguments.delta", "output_index": 0,
            "item_id": "qwen_vision_tool_item", "delta": tool_source,
        },
        {
            "type": "response.output_item.done", "output_index": 0,
            "item": {
                "type": "function_call", "id": "qwen_vision_tool_item", "status": "completed",
                "call_id": "qwen_vision_tool_call", "name": "exec_command", "arguments": tool_source,
            },
        },
    ]
    first = (
        {"type": "response.created", "response": {"id": "resp_qwen_vision_one"}},
        *tool_events,
        {"type": "response.completed", "response": {"id": "resp_qwen_vision_one", "status": "completed", "usage": gateway._usage(1)}},
    )
    second = gateway._completed_events("resp_qwen_vision_two", "qwen_vision_message", "SLAIF_QWEN38_CODEX_OK")
    return tuple(
        gateway.MockAction("/v1/responses", "sse", events, expected_model=upstream_model)
        for events in (first, second)
    )


def _vision_codex_command(
    *,
    profile_name: str,
    workspace: Path,
    image_path: Path,
) -> list[str]:
    """Construct exactly one bounded single-image Codex invocation."""

    if not image_path.is_file():
        raise VerificationError("Synthetic image was not created.")
    return [
        "/usr/bin/codex", "--ask-for-approval", "never", "--profile", profile_name,
        "exec", "--ephemeral", "--ignore-rules", "--json", "--skip-git-repo-check",
        "--sandbox", "workspace-write", "--cd", str(workspace),
        "-c", "check_for_update_on_startup=false",
        "-c", 'model_reasoning_effort="low"',
        "-c", 'model_verbosity="low"',
        "-c", f"model_providers.{profile_name}.request_max_retries=0",
        "-c", f"model_providers.{profile_name}.stream_max_retries=0",
        "-i", str(image_path),
        "--",
        "Use the attached image only as the bounded visual context. Satisfy the local function tool turn and return the final marker.",
    ]

def _run_real_hermetic_phase() -> Mapping[str, object]:
    """Provision a private DB, then run one real Codex/gateway/provider phase."""

    with private_postgres(database_url=os.environ.get("TEST_DATABASE_URL")) as target:
        return _run_real_hermetic_for_target(target)


def _run_real_hermetic_for_target(
    target,
    *,
    provider_base_url: str | None = None,
    provider_key: str | None = None,
    provider_mock=None,
) -> Mapping[str, object]:
    """Run Codex through SLAIF, using either the bounded loopback or configured provider."""

    with _candidate_runtime_registry() as (gateway, runtime):
        version = verify_candidate_codex_version()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            gateway.migrate_database(target)
        if provider_base_url is None:
            mock = provider_mock or gateway.ScriptedOpenAIMock()
        else:
            mock = provider_mock
        loopback_provider = provider_base_url is None or provider_mock is not None
        owns_mock = provider_mock is None
        if owns_mock and mock is not None:
            mock.start()
        provider_url = (
            f"http://127.0.0.1:{mock.port}/v1" if loopback_provider else provider_base_url
        )
        provider_env = (
            "SLAIF_QWEN38_VISION_UPSTREAM_KEY"
            if provider_base_url is None
            else "SLAIF_QWEN38_VISION_LIVE_PROVIDER_KEY"
        )
        configured_provider_key = (
            gateway.DUMMY_UPSTREAM_KEY if provider_base_url is None else provider_key
        )
        if not isinstance(provider_url, str) or not isinstance(configured_provider_key, str):
            raise VerificationError("provider_configuration_failed")
        old_key = os.environ.get(provider_env)
        os.environ[provider_env] = configured_provider_key
        try:
            with gateway.private_redis() as (redis_url, _redis_process):
                settings = gateway._gateway_settings(target.url, redis_url)
                key = __import__("asyncio").run(_seed_candidate_gateway(
                    gateway=gateway,
                    database_url=target.url,
                    provider_base_url=provider_url,
                    provider_env=provider_env,
                    settings=settings, runtime=runtime,
                    zero_pricing=provider_base_url is not None,
                ))
                ready_route = __import__("asyncio").run(
                    _inspect_candidate_route(
                        database_url=target.url, runtime=runtime, provider="openai_compatible"
                    )
                )
                if not ready_route.ready or tuple(runtime.local_tools) != ("function",):
                    raise VerificationError("qualification_inspection_failed")
                with gateway.gateway_server(settings) as (gateway_port, gateway_peers):
                    root = Path(tempfile.mkdtemp(prefix="slaif-qwen38-codex-"))
                    try:
                        home = root / "codex-home"
                        work = root / "workspace"
                        home.mkdir(mode=0o700)
                        work.mkdir(mode=0o700)
                        artifacts = qualification.render_codex_profile_artifacts(
                            f"http://127.0.0.1:{gateway_port}/v1", runtime, legacy_default=False
                        )
                        (home / "config.toml").write_text(artifacts.base_config_toml, encoding="utf-8")
                        (home / f"{runtime.profile_name}.config.toml").write_text(artifacts.profile_config_toml, encoding="utf-8")
                        (home / runtime.model_catalog_target).write_text(runtime.model_catalog_artifact + "\n", encoding="utf-8")
                        for path in (home / "config.toml", home / f"{runtime.profile_name}.config.toml", home / runtime.model_catalog_target):
                            path.chmod(0o600)
                        actions = _candidate_actions(
                            gateway, workspace=work, upstream_model=runtime.upstream_model
                        )
                        if loopback_provider:
                            mock.queue(actions)
                        image_path = work / "slaif-vision-fixture.png"
                        import base64 as _base64
                        image_path.write_bytes(_base64.b64decode(
                            synthetic_png_data_url().partition(",")[2]
                        ))
                        command = _vision_codex_command(
                            profile_name=runtime.profile_name,
                            workspace=work,
                            image_path=image_path,
                        )
                        environment = gateway._profile_environment(home, key.plaintext_key)
                        environment.update({"CODEX_HOME": str(home), "OPENAI_API_KEY": key.plaintext_key,
                                            "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"})
                        result = subprocess.run(command, check=False, capture_output=True, env=environment, timeout=120)
                        if result.returncode != 0:
                            raise VerificationError(
                                "codex_process_failed:"
                                + result.stderr.decode("utf-8", "replace")[ -400:]
                                .replace("\n", "|").replace("\r", "")
                                + ":"
                                + result.stdout.decode("utf-8", "replace")[-400:]
                                .replace("\n", "|").replace("\r", "")
                            )
                        facts = mock.facts_since(0, 2) if loopback_provider else ()
                        marker = work / "qwen38-vision-marker.txt"
                        if (
                            result.returncode != 0
                            or not gateway._codex_completed(result)
                            or not gateway._codex_final_marker_seen(result, marker="SLAIF_QWEN38_CODEX_OK")
                            or not marker.is_file()
                            or marker.read_text(encoding="utf-8") != "SLAIF_QWEN38_FILE_OK\n"
                        ):
                            raise VerificationError(
                                "codex_phase_failed:"
                                + result.stdout.decode("utf-8", "replace")[-1200:].replace("\n", "|")
                                + ":marker="
                                + str(marker.is_file())
                            )
                        if loopback_provider and not all(
                            fact.authorization_replaced and fact.headers_sanitized and fact.model_matched
                            for fact in facts
                        ):
                            raise VerificationError("boundary_proof_failed")
                        accounting = __import__("asyncio").run(gateway.load_accounting(target.url, key.gateway_key_id))
                        pending = __import__("asyncio").run(gateway.outstanding_reservations(target.url))
                        if not _accounting_proved(
                            accounting, pending=pending, exact_hermetic=provider_base_url is None
                        ):
                            raise VerificationError("accounting_proof_failed")
                        if loopback_provider:
                            image_parts = [
                                part
                                for fact in facts
                                for item in fact.input_items
                                for part in (
                                    item.get("content", [])
                                    if isinstance(item.get("content"), list) else []
                                )
                                if isinstance(part, dict) and part.get("type") == "input_image"
                            ]
                            if len(image_parts) < 1 or len({str(part.get("image_url")) for part in image_parts}) > 1 or any(
                                isinstance(part.get("image_url"), str)
                                and part["image_url"].startswith(("http://", "https://"))
                                for part in image_parts
                            ):
                                raise VerificationError("single_inline_image_boundary_failed")
                        sentinels = [
                            key.plaintext_key, configured_provider_key,
                            "SLAIF_QWEN38_CODEX_OK", "SLAIF_QWEN38_FILE_OK",
                        ]
                        if __import__("asyncio").run(gateway.sentinels_persisted(target.url, sentinels)):
                            raise VerificationError("privacy_proof_failed")
                        if provider_base_url is not None:
                            return {
                                "codex_version": version, "request_count": accounting.requests_used,
                                "event_count": sum(len(action.payload) for action in actions),
                                "accounting_proved": True, "privacy_proved": True,
                                "real_provider_called": provider_base_url is not None,
                                "loopback_only": gateway_peers.loopback_only,
                            }
                        event_count = sum(len(action.payload) for action in actions)
                        fixture = build_observed_fixture(
                            facts=facts, actions=actions, runtime=runtime, accounting=accounting
                        )
                        digest = write_captured_fixture(fixture)
                        return {
                            "codex_version": version, "request_count": len(facts), "event_count": event_count,
                            "fixture_digest": digest, "accounting_proved": True, "privacy_proved": True,
                            "real_provider_called": provider_base_url is not None,
                            "loopback_only": gateway_peers.loopback_only and mock.loopback_only,
                        }
                    finally:
                        import shutil
                        shutil.rmtree(root, ignore_errors=True)
        finally:
            if owns_mock and mock is not None:
                mock.stop()
            if old_key is None:
                os.environ.pop(provider_env, None)
            else:
                os.environ[provider_env] = old_key


def run_hermetic_phase(*, runner: Callable[[], Mapping[str, object]] | None = None) -> Mapping[str, object]:
    """Run the bounded phase; the callable seam is for pure failure tests."""

    if runner is not None:
        result = runner()
        if not isinstance(result, Mapping):
            raise VerificationError("Hermetic runner returned an invalid result.")
        return result
    return _run_real_hermetic_phase()


def run_live_phase(
    *,
    base_url: str,
    api_key: str,
    runner: Callable[[str, str], Mapping[str, object]] | None = None,
) -> Mapping[str, object]:
    """Run the separately authorized LAN target phase; no loopback fallback exists."""

    validate_target_url(base_url)
    if not api_key:
        raise VerificationError("Live target credential is invalid.")
    if runner is None:
        runner = _run_live_target
    with LIVE_GUARD.acquire():
        result = runner(base_url, api_key)
    if not isinstance(result, Mapping) or result.get("real_provider_called") is not True:
        raise VerificationError("Live target call was not observed.")
    return result


def run_local_live_plumbing_phase() -> Mapping[str, object]:
    """Exercise the live branch against a separately configured numeric-loopback target."""

    gateway, _, _ = _candidate_runtime_modules()
    mock = gateway.ScriptedOpenAIMock()
    mock.start()
    try:
        with private_postgres(database_url=os.environ.get("TEST_DATABASE_URL")) as target:
            return _run_real_hermetic_for_target(
                target,
                provider_base_url=f"http://127.0.0.1:{mock.port}/v1",
                provider_key=gateway.DUMMY_UPSTREAM_KEY,
                provider_mock=mock,
            )
    finally:
        mock.stop()


def _run_live_target(base_url: str, api_key: str) -> Mapping[str, object]:
    """Run Codex -> disposable SLAIF -> configured private provider target."""

    with private_postgres(database_url=os.environ.get("TEST_DATABASE_URL")) as target:
        return _run_real_hermetic_for_target(
            target, provider_base_url=base_url, provider_key=api_key
        )


def _safe_summary(
    *, live_state: str, phase: Mapping[str, object], real_provider_called: bool = False
) -> tuple[str, ...]:
    required = ("codex_version", "request_count", "event_count", "accounting_proved", "privacy_proved")
    if any(key not in phase for key in required):
        raise VerificationError("Hermetic result was incomplete.")
    if phase["accounting_proved"] is not True or phase["privacy_proved"] is not True:
        raise VerificationError("Hermetic proof was incomplete.")
    return (
        "RESULT=OK",
        f"LIVE_TARGET_PRESENT={str(live_state == 'live_target_present').lower()}",
        f"REAL_PROVIDER_CALLED={str(real_provider_called).lower()}",
        "CANDIDATE_REGISTERED=false",
        "LIVE_QUALIFIED=false",
        "HERMETIC_PHASE=true",
        "ACCOUNTING_PROVED=true",
        "PRIVACY_PROVED=true",
    )


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        parse_arguments(sys.argv[1:] if arguments is None else arguments)
        live_state = validate_environment(os.environ)
        if live_state == "live_target_absent":
            try:
                phase = run_hermetic_phase()
            except VerificationError:
                print(
                    "RESULT=LIVE_TARGET_ABSENT\nLIVE_TARGET_PRESENT=false\n"
                    "REAL_PROVIDER_CALLED=false\nHERMETIC_PHASE=blocked"
                )
                return 0
            print(
                "RESULT=LIVE_TARGET_ABSENT\nLIVE_TARGET_PRESENT=false\n"
                "REAL_PROVIDER_CALLED=false\nHERMETIC_PHASE=true\n"
                f"ACCOUNTING_PROVED={str(phase.get('accounting_proved') is True).lower()}\n"
                f"PRIVACY_PROVED={str(phase.get('privacy_proved') is True).lower()}\n"
                "LIVE_QUALIFIED=false"
            )
            return 0
        phase = run_hermetic_phase()
        live_phase = run_live_phase(
            base_url=os.environ[BASE_URL_ENV], api_key=os.environ[API_KEY_ENV]
        )
        lines = _safe_summary(
            live_state=live_state,
            phase=phase,
            real_provider_called=live_phase["real_provider_called"] is True,
        )
        lines = (*lines, "LIVE_EVIDENCE_PASSED=true")
    except Exception:
        present = bool(os.environ.get(BASE_URL_ENV) or os.environ.get(API_KEY_ENV))
        print(
            "RESULT=FAIL\nLIVE_TARGET_PRESENT="
            + str(present).lower()
            + "\nREAL_PROVIDER_CALLED=false\nLIVE_QUALIFIED=false"
        )
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

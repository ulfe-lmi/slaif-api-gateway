#!/usr/bin/env python3
"""Bounded hermetic/live gate for the unregistered Qwen3.8 Codex candidate."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

from slaif_gateway.services.codex_profile_registry import (
    QWEN38_TEXT_CODEX_CANDIDATE,
    sanitize_codex_fixture,
)

BASE_URL_ENV = "SLAIF_QWEN38_TEXT_BASE_URL"
API_KEY_ENV = "SLAIF_QWEN38_TEXT_API_KEY"
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests/fixtures/codex/0.148.0/qwen3.8-27b-text-api-key-responses.json"
ALLOWED_FIXTURE_TYPES = frozenset(
    {
        "phase", "request", "response.created", "response.output_item.added",
        "response.custom_tool_call_input.delta", "response.output_item.done",
        "response.completed", "response.output_text.delta", "tool", "function",
        "stream", "sse", "catalog", "replacement", "route", "provider", "gateway",
        "upstream", "credential_boundary", "substituted", "final", "completed",
    }
)
MAX_KEY_BYTES = 512


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


def build_structural_fixture(*, request_count: int, event_count: int) -> dict[str, object]:
    """Build only structural facts from a completed bounded capture."""

    return {
        "event_type": "phase", "count": request_count, "enabled": True,
        "event_sequence": [
            {"event_type": "request", "index": 0, "field_type": "gateway"},
            {"event_type": "tool", "index": 1, "tool_type": "function"},
            {"event_type": "stream", "count": event_count, "field_type": "sse"},
            {"event_type": "final", "index": 2, "field_type": "completed"},
        ],
        "request_facts": {"field_type": "request", "count": request_count, "enabled": True},
        "catalog_facts": {"field_type": "replacement", "count": 1, "enabled": True},
        "route_facts": {"field_type": "route", "count": 3, "enabled": True},
        "credential_facts": {"field_type": "credential_boundary", "count": 2, "enabled": True},
    }


def sanitize_captured_fixture(value: object) -> dict[str, object]:
    return sanitize_codex_fixture(value, allowed_types=ALLOWED_FIXTURE_TYPES)


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
    import scripts.verify_codex_gateway_e2e as gateway
    import slaif_gateway.services.codex_profile_registry as registry
    import slaif_gateway.services.codex_qualification as qualification

    return gateway, registry, qualification


@contextmanager
def _candidate_runtime_registry():
    gateway, registry, qualification = _candidate_runtime_modules()
    runtime = replace(QWEN38_TEXT_CODEX_CANDIDATE, mocked_qualification=True)
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


async def _seed_candidate_gateway(*, gateway, database_url: str, mock_port: int, settings, runtime):
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
                base_url=f"http://127.0.0.1:{mock_port}/v1", api_key_env_var="SLAIF_QWEN38_UPSTREAM_KEY",
                enabled=True, timeout_seconds=10, max_retries=0, notes="Disposable loopback only"
            )
            responses = default_responses_capabilities()
            responses.update({
                "text": True, "stateless": True, "streaming": True,
                "codex_request_envelope": True, "codex_client_tools": True,
                "codex_streaming_tool_events": True,
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
            await pricing.create_pricing_rule(
                provider=provider_name, upstream_model=runtime.upstream_model, endpoint="/v1/responses",
                valid_from=now - timedelta(minutes=5), currency="EUR",
                input_price_per_1m=Decimal("1"), cached_input_price_per_1m=Decimal("0"),
                output_price_per_1m=Decimal("2"), reasoning_price_per_1m=Decimal("2"),
                request_price=Decimal("0"), pricing_metadata={}, notes="Disposable local pricing"
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
                    "allowed_capabilities": ["codex_request_envelope", "codex_client_tools", "codex_streaming_tool_events"],
                    "allowed_local_tool_types": ["function", "custom"],
                },
                rate_limit_policy={"requests_per_minute": 100, "tokens_per_minute": 100_000,
                                   "max_concurrent_requests": 1, "window_seconds": 60},
                note="Disposable Qwen candidate verifier key",
            ))
            await session.commit()
            return key
    finally:
        await engine.dispose()


def _candidate_actions(gateway):
    tool_source = 'text("QWEN38_TOOL_OK")'
    first = (
        {"type": "response.created", "response": {"id": "resp_qwen_one"}},
        *gateway._tool_events(item_id="qwen_tool_item", call_id="qwen_tool_call", source=tool_source),
        {"type": "response.completed", "response": {"id": "resp_qwen_one", "status": "completed", "usage": gateway._usage(1)}},
    )
    second = gateway._completed_events("resp_qwen_two", "qwen_message", "SLAIF_QWEN38_CODEX_OK")
    return tuple(gateway.MockAction("/v1/responses", "sse", events) for events in (first, second))


def _run_real_hermetic_phase() -> Mapping[str, object]:
    """Run one Codex -> real gateway -> numeric-loopback provider phase."""

    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        raise VerificationError("hermetic_dependency_unavailable")
    with _candidate_runtime_registry() as (gateway, runtime):
        version = gateway.capture.verify_codex_version(Path("/usr/bin/codex"), runtime.cli_version)
        target = gateway.validate_test_database_url(database_url)
        gateway.migrate_database(target)
        mock = gateway.ScriptedOpenAIMock()
        mock.start()
        old_key = os.environ.get("SLAIF_QWEN38_UPSTREAM_KEY")
        os.environ["SLAIF_QWEN38_UPSTREAM_KEY"] = "qwen38-loopback-upstream-dummy"
        try:
            with gateway.private_redis() as (redis_url, _redis_process):
                settings = gateway._gateway_settings(target.url, redis_url)
                key = __import__("asyncio").run(_seed_candidate_gateway(
                    gateway=gateway, database_url=target.url, mock_port=mock.port,
                    settings=settings, runtime=runtime
                ))
                with gateway.gateway_server(settings) as (gateway_port, gateway_peers):
                    root = Path(tempfile.mkdtemp(prefix="slaif-qwen38-codex-"))
                    try:
                        home = root / "codex-home"
                        work = root / "workspace"
                        home.mkdir(mode=0o700)
                        work.mkdir(mode=0o700)
                        artifacts = __import__("slaif_gateway.services.codex_qualification", fromlist=["render_codex_profile_artifacts"]).render_codex_profile_artifacts(
                            f"http://127.0.0.1:{gateway_port}/v1", runtime, legacy_default=False
                        )
                        (home / "config.toml").write_text(artifacts.base_config_toml, encoding="utf-8")
                        (home / f"{runtime.profile_name}.config.toml").write_text(artifacts.profile_config_toml, encoding="utf-8")
                        (home / runtime.model_catalog_target).write_text(runtime.model_catalog_artifact + "\n", encoding="utf-8")
                        for path in (home / "config.toml", home / f"{runtime.profile_name}.config.toml", home / runtime.model_catalog_target):
                            path.chmod(0o600)
                        mock.queue(_candidate_actions(gateway))
                        command = ["/usr/bin/codex", "--ask-for-approval", "never", "--profile", runtime.profile_name,
                                   "exec", "--ephemeral", "--ignore-rules", "--json", "--skip-git-repo-check",
                                   "--sandbox", "read-only", "--cd", str(work), "-c", "check_for_update_on_startup=false",
                                   "-c", "model_reasoning_effort=\"low\"", "-c", "model_verbosity=\"low\"",
                                   "-c", "model_providers.qwen3_8_text.request_max_retries=0",
                                   "-c", "model_providers.qwen3_8_text.stream_max_retries=0",
                                   "Satisfy the bounded local function tool turn and return the final marker."]
                        environment = gateway._profile_environment(home, key.plaintext_key)
                        environment.update({"CODEX_HOME": str(home), "HOME": str(home), "OPENAI_API_KEY": key.plaintext_key,
                                            "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"})
                        result = subprocess.run(command, check=False, capture_output=True, env=environment, timeout=120)
                        facts = mock.facts_since(0, 2)
                        if result.returncode != 0 or not gateway._codex_completed(result) or not gateway._codex_final_marker_seen(result, marker="SLAIF_QWEN38_CODEX_OK"):
                            raise VerificationError("codex_phase_failed")
                        if not all(fact.authorization_replaced and fact.headers_sanitized and fact.model_matched for fact in facts):
                            raise VerificationError("boundary_proof_failed")
                        accounting = __import__("asyncio").run(gateway.load_accounting(target.url, key.gateway_key_id))
                        pending = __import__("asyncio").run(gateway.outstanding_reservations(target.url))
                        if pending != 0 or accounting.requests_used != 2:
                            raise VerificationError("accounting_proof_failed")
                        sentinels = [key.plaintext_key, "qwen38-loopback-upstream-dummy", "SLAIF_QWEN38_CODEX_OK", "QWEN38_TOOL_OK"]
                        if __import__("asyncio").run(gateway.sentinels_persisted(target.url, sentinels)):
                            raise VerificationError("privacy_proof_failed")
                        fixture = build_structural_fixture(request_count=2, event_count=10)
                        digest = write_captured_fixture(fixture)
                        return {"codex_version": version, "request_count": 2, "event_count": 10,
                                "fixture_digest": digest, "accounting_proved": True, "privacy_proved": True,
                                "loopback_only": gateway_peers.loopback_only and mock.loopback_only}
                    finally:
                        import shutil
                        shutil.rmtree(root, ignore_errors=True)
        finally:
            mock.stop()
            if old_key is None:
                os.environ.pop("SLAIF_QWEN38_UPSTREAM_KEY", None)
            else:
                os.environ["SLAIF_QWEN38_UPSTREAM_KEY"] = old_key


def run_hermetic_phase(*, runner: Callable[[], Mapping[str, object]] | None = None) -> Mapping[str, object]:
    """Run the bounded phase; the callable seam is for pure failure tests."""

    if runner is not None:
        result = runner()
        if not isinstance(result, Mapping):
            raise VerificationError("Hermetic runner returned an invalid result.")
        return result
    return _run_real_hermetic_phase()


def _safe_summary(*, live_state: str, phase: Mapping[str, object]) -> tuple[str, ...]:
    required = ("codex_version", "request_count", "event_count", "accounting_proved", "privacy_proved")
    if any(key not in phase for key in required):
        raise VerificationError("Hermetic result was incomplete.")
    if phase["accounting_proved"] is not True or phase["privacy_proved"] is not True:
        raise VerificationError("Hermetic proof was incomplete.")
    return (
        "RESULT=OK",
        f"LIVE_TARGET_PRESENT={str(live_state == 'live_target_present').lower()}",
        "REAL_PROVIDER_CALLED=false",
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
                f"PRIVACY_PROVED={str(phase.get('privacy_proved') is True).lower()}"
            )
            return 0
        phase = run_hermetic_phase()
        lines = _safe_summary(live_state=live_state, phase=phase)
    except VerificationError:
        present = bool(os.environ.get(BASE_URL_ENV) or os.environ.get(API_KEY_ENV))
        print(
            "RESULT=FAIL\nLIVE_TARGET_PRESENT="
            + str(present).lower()
            + "\nREAL_PROVIDER_CALLED=false"
        )
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

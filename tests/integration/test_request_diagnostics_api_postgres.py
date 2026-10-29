"""Real app + real owned-PostgreSQL-16 evidence for objective 201 (API layer).

Drives the ACTUAL FastAPI application (create_app, real middleware stack
including the diagnostics observer) against a real disposable PostgreSQL 16
database.  The upstream provider is a respx MOCK (no real upstream contact,
no Redis, no normal-email, no real SMTP).  Each test owns its own gateway key
so per-key accounting-state oracles are exact.

Proves: a pre-auth 401 records without any key identity and without ledger or
reservation rows; an unsupported-function-tool capability denial records the
ACTUALLY RESOLVED route identity (route UUID + configured pattern noted at the
trusted resolution boundary) with the public error code, and the public
response and per-key accounting state are byte/row-identical whether
recording is disabled, enabled, or the diagnostics writer is failing; and an
unsupported stream event after HTTP 200 records ``stream_failure`` with the
actual wire status while the client-visible stream and the finalized
accounting state are unchanged across recording modes.

Additionally proves (all correlated by each response's own
``X-SLAIF-Diagnostic-ID``): an endpoint denial records the key identity with
NO route facts; a Codex context-window rejection records the actually
resolved route identity plus the actual decision numbers (estimate,
context, configured ceilings); a Codex encrypted-replay request authorizes
against a REAL persisted reference (positive 200) and is then denied with
the honest opaque code once ONLY that reference is expired, with no
accounting change; the real CLI retrieves the recorded failure by the
returned diagnostic ID against the owned database; a truly slow awaited
capacity-lock write exercises the write timeout boundary without changing
the public response; and content-free canaries (a secret aliased into
``X-Request-ID``, an unknown fact field, and a raw model wildcard suffix)
never reach the stored row, the CLI output, or the logs, while the wire
request ID is preserved.

The diagnostics write timeout is raised to the maximum allowed 1000ms so cold
first-connection statement preparation stays inside the write budget (the
production default remains 100ms).  Ownership discipline mirrors the 199/200
owned fixtures: unique owner label, loopback-bound, tmpfs-backed PostgreSQL
16, identity inspected BEFORE readiness/migration, cleanup removes ONLY the
exact created container ID.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import contextlib
import io
import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from slaif_gateway.api.middleware import SLAIF_DIAGNOSTIC_ID_HEADER
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif201a"

_STATE: dict[str, Any] = {}

MODEL = "diag-model-201"
PROVIDER = "openai"
BASE_URL = "https://api.openai.com/v1"
RESPONSES_ENDPOINT = "/v1/responses"
MODEL_CODEX = "diag-codex-model-201"
MODEL_REPLAY = "diag-replay-model-201"

TEST_HMAC_SECRET = "test-hmac-secret-for-diagnostics-api-12345"
TEST_ADMIN_SECRET = "test-admin-secret-for-diagnostics-api-12345"
_ENV_VARS = (
    "DATABASE_URL",
    "APP_ENV",
    "GATEWAY_KEY_PREFIX",
    "GATEWAY_KEY_ACCEPTED_PREFIXES",
    "ACTIVE_HMAC_KEY_VERSION",
    "TOKEN_HMAC_SECRET_V1",
    "TOKEN_HMAC_SECRET_V2",
    "ADMIN_SESSION_SECRET",
    "ONE_TIME_SECRET_ENCRYPTION_KEY",
    "OPENAI_UPSTREAM_API_KEY",
    "OPENROUTER_API_KEY",
    "REQUEST_DIAGNOSTICS_ENABLED",
    "REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS",
    "REQUEST_CAPTURE_ENABLED",
)


# --- owned PostgreSQL 16 fixture (mirrors 199/200 ownership discipline) ------


def _inspect_owned(container, owner: str, container_port: int) -> int:
    container.reload()
    attrs = container.attrs
    labels = attrs["Config"].get("Labels") or {}
    assert labels.get(f"{_OWNER_PREFIX}.owner") == owner, "owned container label mismatch"
    host_config = attrs["HostConfig"] or {}
    tmpfs = host_config.get("Tmpfs") or {}
    assert "/var/lib/postgresql/data" in tmpfs, "owned PG tmpfs missing"
    configured = (host_config.get("PortBindings") or {}).get(f"{container_port}/tcp") or []
    assert configured and all(b.get("HostIp") == "127.0.0.1" for b in configured), (
        f"owned container must bind loopback, got: {configured}"
    )
    network_ports = (attrs["NetworkSettings"] or {}).get("Ports") or {}
    bound = network_ports.get(f"{container_port}/tcp") or []
    assert bound and all(b.get("HostIp") == "127.0.0.1" for b in bound), (
        f"owned container must publish on loopback, got: {bound}"
    )
    port = bound[0]["HostPort"]
    assert port, "owned container port binding missing"
    return int(port)


def _remove_owned(client, container, owner: str) -> str:
    import docker

    try:
        c = client.containers.get(container.id)
    except docker.errors.NotFound:
        return f"already_absent:{container.id[:12]}"
    c.reload()
    c_labels = c.attrs["Config"].get("Labels") or {}
    assert c_labels.get(f"{_OWNER_PREFIX}.owner") == owner, (
        "refusing to remove a container whose owner label changed"
    )
    c.stop(timeout=10)
    c.remove(force=True)
    return f"removed:{container.id[:12]}"


@pytest.fixture(scope="module")
def owned_pg_url() -> Iterator[str]:
    """One NEW owned, labeled, loopback-bound, tmpfs-backed PostgreSQL 16."""
    import docker

    client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
    container = None
    owner = f"{_OWNER_PREFIX}-{uuid.uuid4().hex}"
    try:
        container = client.containers.run(
            "postgres:16",
            environment={
                "POSTGRES_USER": "test",
                "POSTGRES_PASSWORD": "test",
                "POSTGRES_DB": "test",
            },
            ports={5432: ("127.0.0.1", None)},
            labels={f"{_OWNER_PREFIX}.owner": owner},
            tmpfs={"/var/lib/postgresql/data": "rw"},
            detach=True,
        )
        _STATE["pg_container"] = container.id
        _STATE["pg_owner"] = owner
        port = _inspect_owned(container, owner, 5432)

        async def _wait_ready() -> None:
            import asyncpg

            deadline = time.monotonic() + 90
            last: object = None
            while time.monotonic() < deadline:
                try:
                    conn = await asyncpg.connect(
                        f"postgresql://test:test@127.0.0.1:{port}/test", timeout=3
                    )
                    await conn.close()
                    return
                except Exception as exc:  # noqa: BLE001 - startup retry
                    last = exc
                    await asyncio.sleep(0.5)
            raise AssertionError(f"owned PG did not become ready: {last!r}")

        asyncio.run(_wait_ready())
        url = f"postgresql+asyncpg://test:test@127.0.0.1:{port}/test"
        run_alembic_upgrade_head(url)
        _STATE["pg_source"] = "owned"
        yield url
    finally:
        if container is not None:
            _STATE["pg_cleanup"] = _remove_owned(client, container, owner)


@pytest.fixture(scope="module")
def runtime_env(owned_pg_url: str) -> Iterator[str]:
    """DATABASE_URL is ONLY the exact owned fictional database."""
    saved = {name: os.environ.get(name) for name in _ENV_VARS}
    os.environ["DATABASE_URL"] = owned_pg_url
    os.environ["APP_ENV"] = "test"
    os.environ["GATEWAY_KEY_PREFIX"] = "sk-slaif-"
    os.environ["GATEWAY_KEY_ACCEPTED_PREFIXES"] = "sk-slaif-"
    os.environ["ACTIVE_HMAC_KEY_VERSION"] = "1"
    os.environ["TOKEN_HMAC_SECRET_V1"] = TEST_HMAC_SECRET
    os.environ.pop("TOKEN_HMAC_SECRET_V2", None)
    os.environ["ADMIN_SESSION_SECRET"] = TEST_ADMIN_SECRET
    from slaif_gateway.utils.secrets import generate_secret_key

    os.environ["ONE_TIME_SECRET_ENCRYPTION_KEY"] = generate_secret_key()
    os.environ["OPENAI_UPSTREAM_API_KEY"] = "fake-openai-upstream-key"
    os.environ["OPENROUTER_API_KEY"] = "fake-openrouter-upstream-key"
    os.environ["REQUEST_DIAGNOSTICS_ENABLED"] = "false"
    os.environ["REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS"] = "1000"
    # The full-body content canaries require the operator request-capture
    # channel to be deterministic OFF (unarmed) for the whole module,
    # independent of any ambient environment.
    os.environ["REQUEST_CAPTURE_ENABLED"] = "false"
    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    try:
        yield owned_pg_url
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        from slaif_gateway.config import get_settings as _gs

        _gs.cache_clear()


@pytest.fixture(autouse=True)
def provider_egress_guard():
    """Fail closed on ANY provider egress without an explicit mock.

    201-a forbids real upstream contact.  TestClient traffic is local ASGI;
    every provider HTTP call the gateway makes must be registered on this
    router by the test, otherwise respx raises before any network access.
    """
    with respx.mock(assert_all_mocked=True) as router:
        yield router


# --- world ---------------------------------------------------------------------


async def _setup_world(url: str) -> dict[str, Any]:
    from slaif_gateway.db.models import ModelRoute
    from sqlalchemy import delete

    from slaif_gateway.db.repositories.cohorts import CohortsRepository
    from slaif_gateway.db.repositories.institutions import InstitutionsRepository
    from slaif_gateway.db.repositories.owners import OwnersRepository
    from slaif_gateway.db.repositories.pricing import PricingRulesRepository
    from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
    from slaif_gateway.db.repositories.routing import ModelRoutesRepository

    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)
    unique = uuid.uuid4().hex
    now = datetime.now(UTC)
    async with factory() as session:
        await session.execute(
            delete(ModelRoute).where(
                ModelRoute.requested_model == MODEL, ModelRoute.provider == PROVIDER
            )
        )
        institutions = InstitutionsRepository(session)
        owners = OwnersRepository(session)
        cohorts = CohortsRepository(session)
        providers = ProviderConfigsRepository(session)
        routes = ModelRoutesRepository(session)
        pricing = PricingRulesRepository(session)
        institution = await institutions.create_institution(
            name=f"SLAIF Diag Institute {unique}", country="SI"
        )
        owner = await owners.create_owner(
            name="Diag", surname="Owner", email=f"diag-{unique}@example.test",
            institution_id=institution.id,
        )
        cohort = await cohorts.create_cohort(
            name=f"diag-{unique}", starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
        )
        provider_config = await providers.get_provider_config_by_provider(PROVIDER)
        if provider_config is None:
            await providers.create_provider_config(
                provider=PROVIDER,
                display_name="OpenAI (diagnostics test)",
                base_url=BASE_URL,
                api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                notes="diagnostics test provider config without secrets",
            )
        route = await routes.create_model_route(
            requested_model=MODEL,
            provider=PROVIDER,
            upstream_model=MODEL,
            match_type="exact",
            endpoint=RESPONSES_ENDPOINT,
            priority=1,
            visible_in_models=True,
            supports_streaming=True,
            capabilities={
                "responses": {
                    "text": True,
                    "stateless": True,
                    "streaming": True,
                    "tools": False,
                    "function_tools": False,
                    "custom_tools": False,
                }
            },
            notes="diagnostics test route",
        )
        await pricing.create_pricing_rule(
            provider=PROVIDER,
            upstream_model=MODEL,
            endpoint=RESPONSES_ENDPOINT,
            valid_from=now - timedelta(days=1),
            currency="EUR",
            input_price_per_1m=Decimal("1.000000000"),
            output_price_per_1m=Decimal("1.000000000"),
            request_price=Decimal("0.000000000"),
            notes="diagnostics test pricing",
        )
        await session.commit()
        return {"owner_id": owner.id, "cohort_id": cohort.id, "route_id": route.id}


def _make_key(
    url: str,
    world: dict[str, Any],
    *,
    model: str = MODEL,
    responses_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One gateway key scoped to the test model + responses endpoint."""
    from slaif_gateway.config import Settings
    from slaif_gateway.db.repositories.audit import AuditRepository
    from slaif_gateway.db.repositories.keys import GatewayKeysRepository
    from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
    from slaif_gateway.schemas.keys import CreateGatewayKeyInput
    from slaif_gateway.services.key_service import KeyService

    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)

    async def _go() -> dict[str, Any]:
        now = datetime.now(UTC)
        async with factory() as session:
            service = KeyService(
                settings=Settings(),
                gateway_keys_repository=GatewayKeysRepository(session),
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
            )
            created = await service.create_gateway_key(
                CreateGatewayKeyInput(
                    owner_id=world["owner_id"],
                    cohort_id=world["cohort_id"],
                    valid_from=now - timedelta(minutes=5),
                    valid_until=now + timedelta(days=1),
                    cost_limit_eur=Decimal("10.000000000"),
                    token_limit_total=100_000,
                    request_limit_total=100,
                    allowed_models=[model],
                    allowed_endpoints=[RESPONSES_ENDPOINT],
                    key_purpose="standard",
                    capability_policy_mode="standard",
                    calibration_metadata={},
                    confirm_trusted_calibration=False,
                    responses_policy=responses_policy,
                    note="diagnostics test key",
                )
            )
            await session.commit()
            return {
                "plaintext_key": created.plaintext_key,
                "key_id": created.gateway_key_id,
                "public_key_id": created.public_key_id,
            }

    return asyncio.run(_go())


async def _setup_codex_route(url: str, model: str, *, with_limits: bool) -> dict[str, Any]:
    """One additional exact-match model route carrying Codex capabilities.

    ``with_limits`` adds the client-tools/streaming-tool-events grants plus
    the exact numeric ``codex_limits`` contract required when the key holds
    the complete extended-limits gate set.
    """
    from decimal import Decimal
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from slaif_gateway.db.models import ModelRoute
    from slaif_gateway.db.repositories.pricing import PricingRulesRepository
    from slaif_gateway.db.repositories.routing import ModelRoutesRepository

    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)
    now = datetime.now(UTC)
    block: dict[str, object] = {
        "text": True,
        "stateless": True,
        "codex_request_envelope": True,
        "codex_encrypted_reasoning_replay": True,
    }
    if with_limits:
        block.update({"codex_client_tools": True, "codex_streaming_tool_events": True})
    capabilities: dict[str, object] = {"responses": block}
    if with_limits:
        # exact field set; default <= max < context (enforced at parse time)
        capabilities["codex_limits"] = {
            "context_window_tokens": 400,
            "default_max_output_tokens": 64,
            "max_output_tokens": 256,
        }
    async with factory() as session:
        await session.execute(delete(ModelRoute).where(ModelRoute.requested_model == model))
        routes = ModelRoutesRepository(session)
        pricing = PricingRulesRepository(session)
        route = await routes.create_model_route(
            requested_model=model,
            provider=PROVIDER,
            upstream_model=model,
            match_type="exact",
            endpoint=RESPONSES_ENDPOINT,
            priority=1,
            visible_in_models=True,
            supports_streaming=True,
            capabilities=capabilities,
            notes="diagnostics codex test route",
        )
        await pricing.create_pricing_rule(
            provider=PROVIDER,
            upstream_model=model,
            endpoint=RESPONSES_ENDPOINT,
            valid_from=now - timedelta(days=1),
            currency="EUR",
            input_price_per_1m=Decimal("1.000000000"),
            cached_input_price_per_1m=Decimal("0.250000000"),
            output_price_per_1m=Decimal("1.000000000"),
            reasoning_price_per_1m=Decimal("2.000000000"),
            request_price=Decimal("0.000000000"),
            # the EXISTING Codex accounting contract (complete, as required
            # by codex_limits_applied requests): long-context tier plus one
            # explicit cache-write price, as strict decimal strings.
            pricing_metadata={
                "codex_accounting": {
                    "long_context_threshold_tokens": 272000,
                    "long_context_input_multiplier": "1.5",
                    "long_context_output_multiplier": "1.5",
                    "cache_write_input_price_per_1m": "1.250000000",
                }
            },
            notes="diagnostics codex test pricing",
        )
        await session.commit()
        return {"route_id": route.id}


# --- state oracles ----------------------------------------------------------------


def _key_state(url: str, key_id: Any) -> dict[str, Any]:
    from slaif_gateway.db.models import GatewayKey, QuotaReservation, UsageLedger

    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)

    async def _go() -> dict[str, Any]:
        async with factory() as session:
            key = await session.get(GatewayKey, key_id)
            ledger = (
                await session.execute(
                    select(UsageLedger).where(UsageLedger.gateway_key_id == key_id)
                )
            ).scalars().all()
            reservations = (
                await session.execute(
                    select(QuotaReservation).where(QuotaReservation.gateway_key_id == key_id)
                )
            ).scalars().all()
            return {
                "cost_used_eur": key.cost_used_eur,
                "tokens_used_total": key.tokens_used_total,
                "requests_used_total": key.requests_used_total,
                "cost_reserved_eur": key.cost_reserved_eur,
                "tokens_reserved_total": key.tokens_reserved_total,
                "requests_reserved_total": key.requests_reserved_total,
                "ledger_rows": len(ledger),
                "ledger_states": sorted(
                    (r.accounting_status, r.success) for r in ledger
                ),
                "reservation_states": sorted(r.status for r in reservations),
            }

    return asyncio.run(_go())


def _diagnostic_rows(url: str, *, limit: int = 200) -> list[dict[str, Any]]:
    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)

    async def _go() -> list[dict[str, Any]]:
        async with factory() as session:
            result = await session.execute(
                text(
                    "SELECT gateway_request_id, client_request_id, "
                    "client_id_unavailable_reason, method, endpoint_template, "
                    "http_status, stream_outcome, source, reason_code, error_code, "
                    "gateway_key_id, route_id, route_pattern, counts, limits, "
                    "estimated_input_tokens, context_window_tokens "
                    "FROM request_diagnostics ORDER BY recorded_at DESC, id DESC "
                    f"LIMIT {int(limit)}"
                )
            )
            return [dict(row._mapping) for row in result.all()]

    return asyncio.run(_go())


_DIAGNOSTIC_ROW_COLUMNS = (
    "SELECT gateway_request_id, client_request_id, "
    "client_id_unavailable_reason, method, endpoint_template, "
    "http_status, stream_outcome, source, reason_code, error_code, "
    "gateway_key_id, route_id, route_pattern, counts, limits, "
    "estimated_input_tokens, output_allowance_tokens, context_window_tokens "
)


def _diagnostic_row_by_id(url: str, gateway_request_id: str) -> dict[str, Any] | None:
    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)

    async def _go() -> dict[str, Any] | None:
        async with factory() as session:
            result = await session.execute(
                text(
                    _DIAGNOSTIC_ROW_COLUMNS
                    + "FROM request_diagnostics WHERE gateway_request_id = :gid"
                ),
                {"gid": gateway_request_id},
            )
            row = result.first()
            return dict(row._mapping) if row is not None else None

    return asyncio.run(_go())


def _diagnostic_row_full(url: str, gateway_request_id: str) -> dict[str, Any] | None:
    """EVERY stored column for one diagnostic ID (content-free canary scan)."""
    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)

    async def _go() -> dict[str, Any] | None:
        async with factory() as session:
            result = await session.execute(
                text(
                    "SELECT * FROM request_diagnostics WHERE gateway_request_id = :gid"
                ),
                {"gid": gateway_request_id},
            )
            row = result.first()
            return dict(row._mapping) if row is not None else None

    return asyncio.run(_go())


def _diagnostic_row_count(url: str) -> int:
    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)

    async def _go() -> int:
        async with factory() as session:
            return (
                await session.execute(text("SELECT count(*) FROM request_diagnostics"))
            ).scalar_one()

    return asyncio.run(_go())


def _build_app(diagnostics_enabled: bool) -> Any:
    os.environ["REQUEST_DIAGNOSTICS_ENABLED"] = "true" if diagnostics_enabled else "false"
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app

    get_settings.cache_clear()
    return create_app(get_settings())


def _function_tool_body() -> dict[str, Any]:
    return {
        "model": MODEL,
        "input": "bounded",
        "tools": [
            {
                "type": "function",
                "name": "lookup",
                "description": "lookup thing",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
    }


# --- tests ---------------------------------------------------------------------------


def test_preauth_401_recorded_without_key_identity_or_ledger(
    owned_pg_url: str, runtime_env: str
) -> None:
    world = asyncio.run(_setup_world(owned_pg_url))
    key = _make_key(owned_pg_url, world)
    app = _build_app(diagnostics_enabled=True)
    with TestClient(app) as client:
        response = client.post(
            RESPONSES_ENDPOINT,
            json={"model": MODEL, "input": "bounded"},
            headers={"Authorization": "Bearer sk-slaif-" + "0" * 40},
        )
    assert response.status_code == 401
    diag_id = response.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
    assert diag_id
    newest = _diagnostic_row_by_id(owned_pg_url, diag_id)
    assert newest is not None
    assert newest["stream_outcome"] == "http_rejection"
    assert newest["http_status"] == 401
    # pre-auth: NO key identity, and the authenticated-key column is empty
    assert newest["gateway_key_id"] is None
    state = _key_state(owned_pg_url, key["key_id"])
    assert state["ledger_rows"] == 0
    assert state["reservation_states"] == []


def test_capability_denial_records_resolved_route_facts_and_state_unchanged(
    owned_pg_url: str, runtime_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from slaif_gateway.db.repositories.request_diagnostics import (
        RequestDiagnosticsRepository,
    )

    world = asyncio.run(_setup_world(owned_pg_url))
    key = _make_key(owned_pg_url, world)

    async def _failing_insert(self: Any, record: Any) -> None:
        raise RuntimeError("synthetic diagnostics writer failure")

    payloads: list[dict[str, Any]] = []
    status_codes: list[int] = []
    states: list[dict[str, Any]] = []
    recorded: list[dict[str, Any] | None] = []

    for mode in ("disabled", "enabled", "failing_writer"):
        if mode == "failing_writer":
            monkeypatch.setattr(
                RequestDiagnosticsRepository, "insert_row", _failing_insert
            )
        app = _build_app(diagnostics_enabled=mode != "disabled")
        with TestClient(app) as client:
            response = client.post(
                RESPONSES_ENDPOINT,
                json=_function_tool_body(),
                headers={"Authorization": f"Bearer {key['plaintext_key']}"},
            )
        assert 400 <= response.status_code < 500
        payloads.append(response.json())
        status_codes.append(response.status_code)
        states.append(_key_state(owned_pg_url, key["key_id"]))
        # correlate THIS response by its own diagnostic ID header
        diag_id = response.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
        assert diag_id
        recorded.append(_diagnostic_row_by_id(owned_pg_url, diag_id))
        if mode == "failing_writer":
            monkeypatch.undo()

    # the public OpenAI-shaped error is identical in all three modes
    assert payloads[0] == payloads[1] == payloads[2]
    public_code = payloads[0]["error"]["code"]
    assert public_code == "responses_function_tool_capability_not_supported"
    # the per-key accounting state is unchanged (and identical) in all modes
    assert states[0] == states[1] == states[2]
    assert states[0]["ledger_rows"] == 0
    assert states[0]["reservation_states"] == []

    # exactly one row exists, and only for the enabled mode's diagnostic ID
    assert recorded[0] is None
    assert recorded[2] is None
    # enabled: the ACTUALLY RESOLVED route identity is recorded (noted at the
    # trusted resolution boundary, before capability enforcement)
    rec = recorded[1]
    assert rec is not None
    assert str(rec["route_id"]) == str(world["route_id"])
    assert rec["route_pattern"] == MODEL
    assert rec["error_code"] == public_code
    assert rec["stream_outcome"] == "http_rejection"
    assert rec["http_status"] == status_codes[1]
    # provenance: normal auth succeeded, so the key UUID is present
    assert str(rec["gateway_key_id"]) == str(key["key_id"])


def test_stream_failure_after_200_recorded_and_state_consistent(
    owned_pg_url: str,
    runtime_env: str,
    monkeypatch: pytest.MonkeyPatch,
    provider_egress_guard: Any,
) -> None:
    from slaif_gateway.db.repositories.request_diagnostics import (
        RequestDiagnosticsRepository,
    )

    world = asyncio.run(_setup_world(owned_pg_url))
    key = _make_key(owned_pg_url, world)

    sse = (
        'data: {"type":"response.created","response":{"id":"resp-diag-201",'
        '"status":"in_progress"}}\n\n'
        'data: {"type":"response.not_a_supported_event"}\n\n'
        "data: [DONE]\n\n"
    )

    async def _failing_insert(self: Any, record: Any) -> None:
        raise RuntimeError("synthetic diagnostics writer failure")

    bodies: list[str] = []
    deltas: list[dict[str, Any]] = []
    recorded: list[dict[str, Any] | None] = []

    for mode in ("disabled", "enabled", "failing_writer"):
        if mode == "failing_writer":
            monkeypatch.setattr(
                RequestDiagnosticsRepository, "insert_row", _failing_insert
            )
        app = _build_app(diagnostics_enabled=mode != "disabled")
        state_before = _key_state(owned_pg_url, key["key_id"])
        sse_route = provider_egress_guard.post(f"{BASE_URL}/responses").mock(
            return_value=httpx.Response(
                200,
                content=sse.encode(),
                headers={"content-type": "text/event-stream"},
            )
        )
        with TestClient(app) as client:
            with client.stream(
                "POST",
                RESPONSES_ENDPOINT,
                json={"model": MODEL, "input": "bounded", "stream": True},
                headers={"Authorization": f"Bearer {key['plaintext_key']}"},
            ) as response:
                streamed = "".join(response.iter_text())
                assert response.status_code == 200
                diag_id = response.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
                assert diag_id
        assert sse_route.called
        bodies.append(streamed)
        recorded.append(_diagnostic_row_by_id(owned_pg_url, diag_id))
        state_after = _key_state(owned_pg_url, key["key_id"])
        before_set = list(state_before["ledger_states"])
        after_set = list(state_after["ledger_states"])
        added_ledger: list[tuple[Any, Any]] = []
        for item in after_set:
            if item in before_set:
                before_set.remove(item)
            else:
                added_ledger.append(item)
        before_res = list(state_before["reservation_states"])
        after_res = list(state_after["reservation_states"])
        added_reservations: list[str] = []
        for item in after_res:
            if item in before_res:
                before_res.remove(item)
            else:
                added_reservations.append(item)
        deltas.append(
            {
                "ledger_rows": state_after["ledger_rows"] - state_before["ledger_rows"],
                "added_ledger": sorted(added_ledger),
                "added_reservations": sorted(added_reservations),
                "cost_used_delta": state_after["cost_used_eur"] - state_before["cost_used_eur"],
                "tokens_used_delta": state_after["tokens_used_total"] - state_before["tokens_used_total"],
                "requests_used_delta": state_after["requests_used_total"] - state_before["requests_used_total"],
            }
        )
        if mode == "failing_writer":
            monkeypatch.undo()

    # every mode's client-visible stream carries the same failure code once
    for body in bodies:
        assert body.count("responses_stream_event_not_supported") == 1
    # the per-run accounting DELTA is identical in all three modes
    assert deltas[0] == deltas[1] == deltas[2]
    # the interruption finalizes one failed ledger row + one released
    # reservation per run, identically, regardless of recording mode
    assert deltas[0]["ledger_rows"] == 1
    assert deltas[0]["added_ledger"] == [("failed", False)]
    assert deltas[0]["added_reservations"] == ["released"]
    # only the enabled mode records; stream_failure keeps the actual wire status
    assert recorded[0] is None
    assert recorded[2] is None
    rec = recorded[1]
    assert rec is not None
    assert rec["stream_outcome"] == "stream_failure"
    assert rec["http_status"] == 200
    assert rec["source"] == "responses_stream_failure"
    assert rec["error_code"] == "responses_stream_event_not_supported"
    assert rec["route_pattern"] == MODEL


# --- T4: endpoint denial -------------------------------------------------------


def test_endpoint_denial_records_key_identity_and_no_route_facts(
    owned_pg_url: str, runtime_env: str
) -> None:
    world = asyncio.run(_setup_world(owned_pg_url))
    key = _make_key(owned_pg_url, world)
    app = _build_app(diagnostics_enabled=True)
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": MODEL, "messages": [{"role": "user", "content": "bounded"}]},
            headers={"Authorization": f"Bearer {key['plaintext_key']}"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "endpoint_not_allowed"
    diag_id = response.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
    assert diag_id
    rec = _diagnostic_row_by_id(owned_pg_url, diag_id)
    assert rec is not None
    assert rec["error_code"] == "endpoint_not_allowed"
    assert rec["http_status"] == 403
    assert rec["stream_outcome"] == "http_rejection"
    assert rec["endpoint_template"] == "/v1/chat/completions"
    # endpoint policy rejects BEFORE any route resolution: no route facts
    assert rec["route_id"] is None
    assert rec["route_pattern"] is None
    # normal auth provenance supplies the key identity
    assert str(rec["gateway_key_id"]) == str(key["key_id"])
    state = _key_state(owned_pg_url, key["key_id"])
    assert state["ledger_rows"] == 0
    assert state["reservation_states"] == []


# --- T5: Codex context-window rejection facts ---------------------------------


def test_codex_context_rejection_records_route_and_decision_facts(
    owned_pg_url: str, runtime_env: str
) -> None:
    world = asyncio.run(_setup_world(owned_pg_url))
    codex_world = asyncio.run(_setup_codex_route(owned_pg_url, MODEL_CODEX, with_limits=True))
    key = _make_key(
        owned_pg_url,
        world,
        model=MODEL_CODEX,
        # the pinned historical 0147 tuple: the exact five Codex gates plus
        # the full local tool set resolves the qualified Codex client module
        # (with a real policy spec) and the reviewed OpenAI server pair.
        responses_policy={
            "version": 1,
            "allowed_capabilities": [
                "codex_request_envelope",
                "codex_client_tools",
                "codex_streaming_tool_events",
                "codex_encrypted_reasoning_replay",
                "codex_compaction",
            ],
            "allowed_local_tool_types": ["function", "custom"],
        },
    )
    app = _build_app(diagnostics_enabled=True)
    # prompt_cache_key makes this a Codex envelope request; the long input
    # pushes estimated_input + the route default output past the 400-token
    # context window.
    body = {"model": MODEL_CODEX, "input": "x" * 3000, "prompt_cache_key": "diag-c5"}
    with TestClient(app) as client:
        response = client.post(
            RESPONSES_ENDPOINT,
            json=body,
            headers={"Authorization": f"Bearer {key['plaintext_key']}"},
        )
    assert response.status_code == 400
    public_code = response.json()["error"]["code"]
    assert public_code == "responses_codex_context_window_exceeded"
    diag_id = response.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
    assert diag_id
    rec = _diagnostic_row_by_id(owned_pg_url, diag_id)
    assert rec is not None
    assert rec["error_code"] == public_code
    assert rec["http_status"] == 400
    assert rec["stream_outcome"] == "http_rejection"
    assert rec["endpoint_template"] == RESPONSES_ENDPOINT
    # the ACTUALLY RESOLVED route identity (trusted resolution boundary)
    assert str(rec["route_id"]) == str(codex_world["route_id"])
    assert rec["route_pattern"] == MODEL_CODEX
    # actual decision numbers and configured ceilings (not classifier hints)
    assert rec["source"] == "responses_route_limits"
    assert rec["context_window_tokens"] == 400
    assert rec["estimated_input_tokens"] is not None
    assert rec["estimated_input_tokens"] > 336  # the amount that broke the window
    assert rec["limits"] == {
        "max_output_tokens": 256,
        "max_input_tokens": 1050000,
        "context_window_tokens": 400,
    }
    # route default output was the allowance used in the decision
    assert rec["output_allowance_tokens"] == 64
    # provenance: normal auth succeeded
    assert str(rec["gateway_key_id"]) == str(key["key_id"])
    # the rejection happens before any quota side effect
    state = _key_state(owned_pg_url, key["key_id"])
    assert state["ledger_rows"] == 0
    assert state["reservation_states"] == []


# --- T6: real replay reference: authorize then expire (API level) -------------


def test_replay_reference_authorizes_then_expired_denial_recorded(
    owned_pg_url: str,
    runtime_env: str,
    provider_egress_guard: Any,
) -> None:
    from slaif_gateway.config import get_settings
    from slaif_gateway.db.repositories.codex_replay import (
        CodexReplayReferencesRepository,
    )
    from slaif_gateway.db.repositories.usage import UsageLedgerRepository
    from slaif_gateway.services.codex_replay_service import CodexReplayService

    world = asyncio.run(_setup_world(owned_pg_url))
    # with_limits=True: the complete Codex gate set below makes the
    # extended-limits path active, so the route must carry the exact numeric
    # codex_limits contract as well.
    replay_world = asyncio.run(_setup_codex_route(owned_pg_url, MODEL_REPLAY, with_limits=True))
    key = _make_key(
        owned_pg_url,
        world,
        model=MODEL_REPLAY,
        # the pinned historical 0147 tuple (same as the context test): the
        # qualified Codex client module validates the encrypted-replay input
        # item and pairs with the reviewed OpenAI server module.
        responses_policy={
            "version": 1,
            "allowed_capabilities": [
                "codex_request_envelope",
                "codex_client_tools",
                "codex_streaming_tool_events",
                "codex_encrypted_reasoning_replay",
                "codex_compaction",
            ],
            "allowed_local_tool_types": ["function", "custom"],
        },
    )
    item_id = f"rs-diag201-{uuid.uuid4().hex}"

    @dataclass(frozen=True, slots=True, repr=False)
    class _ReplayCandidate:
        item_kind: str
        item_id: str | None
        call_id: str | None = None
        tool_namespace: str | None = None
        tool_name: str | None = None

    async def _seed_reference() -> tuple[datetime, datetime]:
        factory = async_sessionmaker(create_async_engine(owned_pg_url, future=True), expire_on_commit=False)
        # Deterministic chronology: seed the finalized ledger and the
        # genuine reference at now-60s (inside this key's valid_from of
        # now-5min) with the LONG default (one-year) lifetime.
        seed_now = datetime.now(UTC) - timedelta(seconds=60)
        source_request_id = f"req-diag201-{uuid.uuid4().hex}"
        async with factory() as session:
            usage = UsageLedgerRepository(session)
            ledger = await usage.create_success_record(
                request_id=source_request_id,
                gateway_key_id=key["key_id"],
                owner_id=world["owner_id"],
                cohort_id=world["cohort_id"],
                endpoint=RESPONSES_ENDPOINT,
                provider=PROVIDER,
                started_at=seed_now,
                finished_at=seed_now,
                requested_model=MODEL_REPLAY,
                resolved_model=MODEL_REPLAY,
                streaming=False,
            )
            replay = CodexReplayService(
                repository=CodexReplayReferencesRepository(session),
                settings=get_settings(),
            )
            persisted = await replay.persist_validated_references(
                candidates=(
                    _ReplayCandidate(
                        item_kind="reasoning",
                        item_id=item_id,
                        call_id=None,
                        tool_namespace=None,
                        tool_name=None,
                    ),
                ),
                gateway_key_id=key["key_id"],
                usage_ledger_id=ledger.id,
                source_request_id=source_request_id,
                provider=PROVIDER,
                route_id=replay_world["route_id"],
                upstream_model=MODEL_REPLAY,
                now=seed_now,
            )
            assert persisted == 1
            await session.commit()
            result = await session.execute(
                text(
                    "SELECT created_at, expires_at FROM codex_replay_references "
                    "WHERE gateway_key_id = :kid"
                ),
                {"kid": key["key_id"]},
            )
            row = result.one()
            return row[0], row[1]

    created_at, expires_at = asyncio.run(_seed_reference())

    body = {
        "model": MODEL_REPLAY,
        "input": [
            {"type": "reasoning", "id": item_id, "encrypted_content": "enc-diag201"}
        ],
    }
    provider_response = httpx.Response(
        200,
        json={
            "id": "resp-diag201-t6",
            "object": "response",
            "status": "completed",
            "model": MODEL_REPLAY,
            "output": [],
            "usage": {"input_tokens": 6, "output_tokens": 8, "total_tokens": 14},
            "store": False,
        },
        headers={"content-type": "application/json"},
    )

    app = _build_app(diagnostics_enabled=True)
    state_before = _key_state(owned_pg_url, key["key_id"])
    assert state_before["ledger_rows"] == 1  # the seeded finalized ledger only
    # long initial lifetime: exactly the default TTL past the back-dated
    # creation, so the reference is still active at the current moment
    assert (expires_at - created_at) == timedelta(
        seconds=get_settings().CODEX_REPLAY_REFERENCE_TTL_SECONDS
    )
    assert expires_at > datetime.now(UTC)  # the reference is still active

    # POSITIVE CONTROL: the persisted reference authorizes the real API
    # replay (the provider call is the explicit mock on the egress guard)
    replay_route = provider_egress_guard.post(f"{BASE_URL}/responses").mock(
        return_value=provider_response
    )
    with TestClient(app) as client:
        ok = client.post(
            RESPONSES_ENDPOINT,
            json=body,
            headers={"Authorization": f"Bearer {key['plaintext_key']}"},
        )
    assert ok.status_code == 200, ok.text
    assert replay_route.called
    ok_diag = ok.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
    assert ok_diag
    # a successful 200 never records
    assert _diagnostic_row_by_id(owned_pg_url, ok_diag) is None
    state_after_ok = _key_state(owned_pg_url, key["key_id"])
    assert state_after_ok["ledger_rows"] == state_before["ledger_rows"] + 1

    # Deterministic expiry: set ONLY this controlled reference's expiry to
    # created_at + 30s -- AFTER creation (the row's expires_at > created_at
    # invariant is preserved) and already ~30s BEFORE the API's current
    # time, so the reference is expired without any sleep or race.
    async def _expire_reference() -> int:
        factory = async_sessionmaker(
            create_async_engine(owned_pg_url, future=True), expire_on_commit=False
        )
        async with factory() as session:
            result = await session.execute(
                text(
                    "UPDATE codex_replay_references "
                    "SET expires_at = created_at + interval '30 seconds' "
                    "WHERE gateway_key_id = :kid AND created_at = :created"
                ),
                {"kid": key["key_id"], "created": created_at},
            )
            await session.commit()
            return result.rowcount

    assert asyncio.run(_expire_reference()) == 1

    async def _stored_expiry() -> datetime:
        factory = async_sessionmaker(
            create_async_engine(owned_pg_url, future=True), expire_on_commit=False
        )
        async with factory() as session:
            result = await session.execute(
                text(
                    "SELECT expires_at FROM codex_replay_references "
                    "WHERE gateway_key_id = :kid AND created_at = :created"
                ),
                {"kid": key["key_id"], "created": created_at},
            )
            return result.scalar_one()

    # stored chronology preserved (still after creation) while the expiry is
    # already in the past relative to the API's current time
    expired_at = asyncio.run(_stored_expiry())
    assert created_at < expired_at < datetime.now(UTC)

    # the same request now fails closed with the honest opaque replay code
    with TestClient(app) as client:
        denied = client.post(
            RESPONSES_ENDPOINT,
            json=body,
            headers={"Authorization": f"Bearer {key['plaintext_key']}"},
        )
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "responses_codex_replay_reference_not_found"
    diag_id = denied.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
    assert diag_id
    rec = _diagnostic_row_by_id(owned_pg_url, diag_id)
    assert rec is not None
    assert rec["error_code"] == "responses_codex_replay_reference_not_found"
    assert rec["http_status"] == 404
    assert rec["stream_outcome"] == "http_rejection"
    # replay verification precedes route resolution: no route facts
    assert rec["route_id"] is None
    assert rec["route_pattern"] is None
    assert str(rec["gateway_key_id"]) == str(key["key_id"])
    # the denied replay changed NO accounting state
    assert _key_state(owned_pg_url, key["key_id"]) == state_after_ok


# --- T7: real CLI lookup against the owned database ---------------------------


def test_cli_lookup_retrieves_recorded_failure_by_diagnostic_id(
    owned_pg_url: str, runtime_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app as cli_app
    from slaif_gateway.config import get_settings

    world = asyncio.run(_setup_world(owned_pg_url))
    key = _make_key(owned_pg_url, world)
    app = _build_app(diagnostics_enabled=True)
    with TestClient(app) as client:
        response = client.post(
            RESPONSES_ENDPOINT,
            json=_function_tool_body(),
            headers={"Authorization": f"Bearer {key['plaintext_key']}"},
        )
    assert 400 <= response.status_code < 500
    diag_id = response.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
    assert diag_id
    expected_code = response.json()["error"]["code"]

    # the CLI reads settings from the environment (the exact owned URL)
    monkeypatch.setenv("DATABASE_URL", owned_pg_url)
    monkeypatch.setenv("REQUEST_DIAGNOSTICS_ENABLED", "true")
    get_settings.cache_clear()
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        ["diagnostics", "request", "show", "--request-id", diag_id, "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["outcome"] == "found"
    record = payload["record"]
    assert record["gateway_request_id"] == diag_id
    assert record["error_code"] == expected_code
    assert record["gateway_key_id"] == str(key["key_id"])

    # gateway namespace resolves the same row
    result = runner.invoke(
        cli_app,
        ["diagnostics", "request", "show", "--request-id", diag_id,
         "--namespace", "gateway", "--json"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["outcome"] == "found"

    # an absent ID is an honest not_found (exit 0, typed outcome)
    result = runner.invoke(
        cli_app,
        ["diagnostics", "request", "show", "--request-id", "gw-not-present-201", "--json"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["outcome"] == "not_found"

    # the human status line reflects the real retained count
    retained = _diagnostic_row_count(owned_pg_url)
    result = runner.invoke(cli_app, ["diagnostics", "status"])
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("recording enabled;")
    assert f"{retained} retained record(s)" in result.stdout


# --- T8: truly slow awaited write hits the timeout boundary --------------------


def test_slow_capacity_lock_write_times_out_without_changing_response(
    owned_pg_url: str, runtime_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from slaif_gateway.db.repositories.request_diagnostics import (
        RequestDiagnosticsRepository,
    )

    world = asyncio.run(_setup_world(owned_pg_url))
    key = _make_key(owned_pg_url, world)
    headers = {"Authorization": f"Bearer {key['plaintext_key']}"}

    # baseline with recording disabled
    baseline = _build_app(diagnostics_enabled=False)
    with TestClient(baseline) as client:
        base_response = client.post(RESPONSES_ENDPOINT, json=_function_tool_body(), headers=headers)
    assert 400 <= base_response.status_code < 500
    base_diag = base_response.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
    assert base_diag
    assert _diagnostic_row_by_id(owned_pg_url, base_diag) is None

    # NOW a truly slow awaited write: the capacity-lock acquisition itself
    # sleeps 300ms inside the real _record path, far beyond the 10ms budget.
    async def _slow_lock(self: Any) -> bool:
        await asyncio.sleep(0.3)
        return True

    monkeypatch.setenv("REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS", "10")
    monkeypatch.setattr(RequestDiagnosticsRepository, "try_acquire_capacity_lock", _slow_lock)
    enabled = _build_app(diagnostics_enabled=True)
    try:
        with TestClient(enabled) as client:
            slow_response = client.post(RESPONSES_ENDPOINT, json=_function_tool_body(), headers=headers)
    finally:
        monkeypatch.undo()

    # the public response is UNCHANGED by the timed-out observer write
    assert slow_response.status_code == base_response.status_code
    assert slow_response.json() == base_response.json()
    slow_diag = slow_response.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
    assert slow_diag
    assert slow_diag != base_diag
    # the timed-out write stored nothing
    assert _diagnostic_row_by_id(owned_pg_url, slow_diag) is None


# --- T9: content-free canaries (row + CLI + logs) ------------------------------


def test_secret_alias_request_id_never_stored_logged_or_echoed_by_cli(
    owned_pg_url: str, runtime_env: str
) -> None:
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app as cli_app
    from slaif_gateway.config import get_settings

    world = asyncio.run(_setup_world(owned_pg_url))
    key = _make_key(owned_pg_url, world)
    # the PLAINTEXT gateway key aliased into the client request-ID header:
    # a known incoming-secret shape, not a neutral client ID
    alias_id = key["plaintext_key"]
    app = _build_app(diagnostics_enabled=True)
    log_buffer = io.StringIO()
    with contextlib.redirect_stdout(log_buffer):
        with TestClient(app) as client:
            response = client.post(
                RESPONSES_ENDPOINT,
                json=_function_tool_body(),
                headers={
                    "Authorization": f"Bearer {alias_id}",
                    "X-Request-ID": alias_id,
                },
            )
    assert 400 <= response.status_code < 500
    # the WIRE request ID is preserved for correlation (unchanged by design)
    assert response.headers.get("X-Request-ID") == alias_id
    diag_id = response.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
    assert diag_id

    row = _diagnostic_row_full(owned_pg_url, diag_id)
    assert row is not None
    assert row["client_request_id"] is None
    assert row["client_id_unavailable_reason"] == "secret_alias"
    # the raw secret is absent from EVERY stored column
    assert alias_id not in repr(row)
    # ...and absent from the structured logs captured for the request
    assert alias_id not in log_buffer.getvalue()

    # ...and absent from the CLI JSON output for the same record
    get_settings.cache_clear()
    result = CliRunner().invoke(
        cli_app,
        ["diagnostics", "request", "show", "--request-id", diag_id, "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["outcome"] == "found"
    assert payload["record"]["client_request_id"] is None
    assert payload["record"]["client_id_unavailable_reason"] == "secret_alias"
    assert alias_id not in result.stdout


def test_unknown_fact_field_dropped_and_model_suffix_never_stored(
    owned_pg_url: str, runtime_env: str
) -> None:
    from slaif_gateway.config import Settings
    from slaif_gateway.services.request_diagnostics import (
        DiagnosticsWriteOutcome,
        RequestDiagnosticsService,
    )

    world = asyncio.run(_setup_world(owned_pg_url))
    key = _make_key(owned_pg_url, world)

    # 1) an unknown fact field name is a bounded drop (DROPPED_INVALID), no
    # row.  Recording is enabled EXPLICITLY on this service's settings (the
    # module environment starts disabled; no reliance on prior tests).
    factory = async_sessionmaker(create_async_engine(owned_pg_url, future=True), expire_on_commit=False)
    service = RequestDiagnosticsService(
        settings=Settings(
            _env_file=None,
            APP_ENV="test",
            DATABASE_URL=owned_pg_url,
            REQUEST_DIAGNOSTICS_ENABLED=True,
            REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS=1000,
        ),
        session_factory=factory,
    )

    async def _reject_unknown() -> DiagnosticsWriteOutcome:
        facts = {
            "gateway_request_id": f"gw-{uuid.uuid4()}",
            "method": "POST",
            "endpoint_template": RESPONSES_ENDPOINT,
            "occurred_at": datetime.now(UTC),
            "stream_outcome": "http_rejection",
            "http_status": 400,
            "bogus_unknown_field": "must-never-store",
        }
        return await service.record_failure(facts)

    before = _diagnostic_row_count(owned_pg_url)
    outcome = asyncio.run(_reject_unknown())
    assert outcome is DiagnosticsWriteOutcome.DROPPED_INVALID
    assert _diagnostic_row_count(owned_pg_url) == before

    # 2) a raw model wildcard suffix is denied and never reaches the row
    suffix_model = "canary-model-suffix-xyz"
    app = _build_app(diagnostics_enabled=True)
    with TestClient(app) as client:
        response = client.post(
            RESPONSES_ENDPOINT,
            json={"model": suffix_model, "input": "bounded"},
            headers={"Authorization": f"Bearer {key['plaintext_key']}"},
        )
    assert 400 <= response.status_code < 500
    diag_id = response.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
    assert diag_id
    row = _diagnostic_row_full(owned_pg_url, diag_id)
    assert row is not None
    assert suffix_model not in repr(row)
    assert row["endpoint_template"] == RESPONSES_ENDPOINT
    # no route matched the unknown model: no route facts
    assert row["route_id"] is None
    assert row["route_pattern"] is None
    assert str(row["gateway_key_id"]) == str(key["key_id"])
    assert row["error_code"] in (
        "model_not_found",
        "model_not_allowed_for_key",
    )
    state = _key_state(owned_pg_url, key["key_id"])
    assert state["ledger_rows"] == 0
    assert state["reservation_states"] == []


async def _setup_wild_route(url: str, pattern: str) -> dict[str, Any]:
    """One configured PREFIX route: its static pattern is the only identity
    that may ever reach storage (never a client-requested suffix)."""
    from decimal import Decimal
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from slaif_gateway.db.models import ModelRoute
    from slaif_gateway.db.repositories.pricing import PricingRulesRepository
    from slaif_gateway.db.repositories.routing import ModelRoutesRepository

    factory = async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        await session.execute(delete(ModelRoute).where(ModelRoute.requested_model == pattern))
        routes = ModelRoutesRepository(session)
        pricing = PricingRulesRepository(session)
        route = await routes.create_model_route(
            requested_model=pattern,
            provider=PROVIDER,
            upstream_model=pattern,  # static configured upstream identity
            match_type="prefix",
            endpoint=RESPONSES_ENDPOINT,
            priority=1,
            visible_in_models=True,
            supports_streaming=True,
            capabilities={
                "responses": {
                    "text": True,
                    "stateless": True,
                    "streaming": True,
                    "tools": False,
                    "function_tools": False,
                    "custom_tools": False,
                }
            },
            notes="diagnostics wildcard test route",
        )
        await pricing.create_pricing_rule(
            provider=PROVIDER,
            upstream_model=pattern,
            endpoint=RESPONSES_ENDPOINT,
            valid_from=now - timedelta(days=1),
            currency="EUR",
            input_price_per_1m=Decimal("1.000000000"),
            output_price_per_1m=Decimal("1.000000000"),
            request_price=Decimal("0.000000000"),
            notes="diagnostics wildcard test pricing",
        )
        await session.commit()
        return {"route_id": route.id}


# --- T9c: real API content-free canaries (stored row + CLI + logs) ------------


def test_real_api_content_canaries_never_stored(
    owned_pg_url: str,
    runtime_env: str,
    provider_egress_guard: Any,
) -> None:
    from typer.testing import CliRunner

    from slaif_gateway.cli.main import app as cli_app
    from slaif_gateway.config import get_settings

    world = asyncio.run(_setup_world(owned_pg_url))
    wild_base = "diag-wild-201-"
    wild_suffix = f"priv-{uuid.uuid4().hex[:10]}"
    wild_model = wild_base + wild_suffix
    wild_world = asyncio.run(_setup_wild_route(owned_pg_url, wild_base))

    key = _make_key(owned_pg_url, world)
    wild_key = _make_key(owned_pg_url, world, model=wild_model)
    app = _build_app(diagnostics_enabled=True)
    get_settings.cache_clear()
    runner = CliRunner()
    log_buffer = io.StringIO()

    def _assert_canaries_absent(diag_id: str, *canaries: str) -> None:
        # EVERY stored column of the record for this exact diagnostic ID
        row = _diagnostic_row_full(owned_pg_url, diag_id)
        assert row is not None
        row_repr = repr(row)
        for canary in canaries:
            assert canary not in row_repr
        # the CLI JSON output for the same record
        result = runner.invoke(
            cli_app,
            ["diagnostics", "request", "show", "--request-id", diag_id, "--json"],
        )
        assert result.exit_code == 0, result.output
        for canary in canaries:
            assert canary not in result.stdout
        # the structured logs captured so far for this test
        logs = log_buffer.getvalue()
        for canary in canaries:
            assert canary not in logs

    with contextlib.redirect_stdout(log_buffer):
        with TestClient(app) as client:
            # (1) VALID prompt/instructions + tool description and schema
            # content, rejected by the CAPABILITY policy of the resolved
            # route: none of it may be stored, logged, or CLI-echoed.
            prompt_canary = f"prompt-canary-{uuid.uuid4().hex}"
            tool_desc_canary = f"tool-desc-canary-{uuid.uuid4().hex}"
            schema_prop_canary = f"schema-prop-{uuid.uuid4().hex[:12]}"
            r1 = client.post(
                RESPONSES_ENDPOINT,
                json={
                    "model": MODEL,
                    "input": prompt_canary,
                    "instructions": prompt_canary,
                    "tools": [
                        {
                            "type": "function",
                            "name": "lookup",
                            "description": tool_desc_canary,
                            "parameters": {
                                "type": "object",
                                "properties": {schema_prop_canary: {"type": "string"}},
                            },
                        }
                    ],
                },
                headers={"Authorization": f"Bearer {key['plaintext_key']}"},
            )
            assert 400 <= r1.status_code < 500
            assert (
                r1.json()["error"]["code"]
                == "responses_function_tool_capability_not_supported"
            )
            r1_diag = r1.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
            rec1 = _diagnostic_row_by_id(owned_pg_url, r1_diag)
            assert rec1 is not None
            assert str(rec1["route_id"]) == str(world["route_id"])
            assert rec1["route_pattern"] == MODEL
            _assert_canaries_absent(
                r1_diag, prompt_canary, tool_desc_canary, schema_prop_canary
            )

            # (2) a real UNKNOWN request field name (and its value)
            unknown_field = f"zzz_unknown_{uuid.uuid4().hex[:12]}"
            unknown_value = f"unknown-field-value-{uuid.uuid4().hex}"
            r2 = client.post(
                RESPONSES_ENDPOINT,
                json={
                    "model": MODEL,
                    "input": "bounded",
                    unknown_field: unknown_value,
                },
                headers={"Authorization": f"Bearer {key['plaintext_key']}"},
            )
            assert 400 <= r2.status_code < 500
            _assert_canaries_absent(
                r2.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER), unknown_field, unknown_value
            )

            # (2b) MALFORMED JSON body: decoder context stays content-free
            malformed_canary = f"malformed-json-{uuid.uuid4().hex}"
            r3 = client.post(
                RESPONSES_ENDPOINT,
                content=f'{{"model": "{MODEL}", "input": "{malformed_canary}"',
                headers={
                    "Authorization": f"Bearer {key['plaintext_key']}",
                    "content-type": "application/json",
                },
            )
            assert r3.status_code in (400, 422)
            _assert_canaries_absent(
                r3.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER), malformed_canary
            )

            # (3) a MATCHED configured prefix route with a private requested
            # suffix: only the static configured pattern and route UUID are
            # recorded, never the suffix.
            wild_body = dict(_function_tool_body())
            wild_body["model"] = wild_model
            r4 = client.post(
                RESPONSES_ENDPOINT,
                json=wild_body,
                headers={"Authorization": f"Bearer {wild_key['plaintext_key']}"},
            )
            assert 400 <= r4.status_code < 500
            assert (
                r4.json()["error"]["code"]
                == "responses_function_tool_capability_not_supported"
            )
            r4_diag = r4.headers.get(SLAIF_DIAGNOSTIC_ID_HEADER)
            rec4 = _diagnostic_row_by_id(owned_pg_url, r4_diag)
            assert rec4 is not None
            assert str(rec4["route_id"]) == str(wild_world["route_id"])
            assert rec4["route_pattern"] == wild_base
            _assert_canaries_absent(r4_diag, wild_model, wild_suffix)

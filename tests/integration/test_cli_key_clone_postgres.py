"""Real owned-PostgreSQL evidence for objective 198's `keys clone` surface.

Covers exact canonical configuration equality (None/[] providers, nullable
rates, unlimited quotas), independent target material/usage/replay, unchanged
source rows, caller-transaction rollback on a forced LATE clone audit
failure, concurrent same-plan execution from TWO separate processes proving
READ-COMMITTED receipt deduplication, and exact retry after a simulated
post-commit mail failure. No provider HTTP, no Redis, no real upstream
contact, no real SMTP delivery (send-now is pointed at a refused local port).

Ownership discipline mirrors the 184/185/197 owned fixtures: unique owner
label, loopback-bound, tmpfs-backed PostgreSQL 16, identity inspected BEFORE
readiness/migration, cleanup removes ONLY the exact created container ID.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.config import get_settings
from slaif_gateway.db.models import (
    AuditLog,
    CodexReplayReference,
    EmailDelivery,
    GatewayKey,
    OneTimeSecret,
    UsageLedger,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.schemas.key_clone import parse_clone_plan_document
from slaif_gateway.services.email_delivery_service import EmailDeliveryService
from slaif_gateway.services.email_service import EmailService
from slaif_gateway.services.key_clone_service import (
    KeyCloneService,
    KeyCloneUnsupportedIsolationError,
)
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif198a"

_STATE: dict[str, str] = {}

_CLI_ENV_VARS = (
    "DATABASE_URL",
    "APP_ENV",
    "GATEWAY_KEY_PREFIX",
    "GATEWAY_KEY_ACCEPTED_PREFIXES",
    "ACTIVE_HMAC_KEY_VERSION",
    "TOKEN_HMAC_SECRET_V1",
    "ADMIN_SESSION_SECRET",
    "ONE_TIME_SECRET_ENCRYPTION_KEY",
    "OPENAI_UPSTREAM_API_KEY",
    "OPENROUTER_API_KEY",
    "ENABLE_EMAIL_DELIVERY",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_FROM",
)

TEST_HMAC_SECRET = "test-hmac-secret-for-cli-key-clone-12345"
TEST_ADMIN_SECRET = "test-admin-secret-for-cli-key-clone-12345"
OPENAI_BASE_URL = "https://canary-openai.example.invalid/v1"

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "app"

_CHILD_SCRIPT = r"""
import json
import sys

from typer.testing import CliRunner

from slaif_gateway.cli.main import app

result = CliRunner().invoke(app, sys.argv[1:])
print(
    json.dumps(
        {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
)
"""


# --- owned PostgreSQL 16 fixture ---------------------------------------------


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
        _STATE["pg_container"] = container.id  # type: ignore[attr-defined]
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


# --- environment / session helpers --------------------------------------------


@pytest.fixture(scope="module")
def cli_env(owned_pg_url: str) -> str:
    """DATABASE_URL is ONLY the exact owned fictional database."""
    saved = {name: os.environ.get(name) for name in _CLI_ENV_VARS}
    os.environ["DATABASE_URL"] = owned_pg_url
    os.environ["APP_ENV"] = "test"
    os.environ["GATEWAY_KEY_PREFIX"] = "sk-slaif-"
    os.environ["GATEWAY_KEY_ACCEPTED_PREFIXES"] = "sk-slaif-"
    os.environ["ACTIVE_HMAC_KEY_VERSION"] = "1"
    os.environ["TOKEN_HMAC_SECRET_V1"] = TEST_HMAC_SECRET
    os.environ["ADMIN_SESSION_SECRET"] = TEST_ADMIN_SECRET
    os.environ["ONE_TIME_SECRET_ENCRYPTION_KEY"] = generate_secret_key()
    os.environ["OPENAI_UPSTREAM_API_KEY"] = "fake-openai-upstream-key"
    os.environ["OPENROUTER_API_KEY"] = "fake-openrouter-upstream-key"
    os.environ.pop("ENABLE_EMAIL_DELIVERY", None)
    os.environ.pop("SMTP_HOST", None)
    os.environ.pop("SMTP_PORT", None)
    os.environ.pop("SMTP_FROM", None)
    get_settings.cache_clear()
    try:
        yield owned_pg_url
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()


def _session_factory(url: str):
    return async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)


@pytest.fixture(scope="module")
def route_fixtures(cli_env: str) -> str:
    """Provider + enabled model routes required by `keys create` validation."""
    url = cli_env

    async def setup():
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                providers = ProviderConfigsRepository(session)
                routes = ModelRoutesRepository(session)
                provider = await providers.get_provider_config_by_provider("openai")
                if provider is None:
                    await providers.create_provider_config(
                        provider="openai",
                        display_name="OpenAI",
                        base_url=OPENAI_BASE_URL,
                        api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                    )
                existing = {
                    r.requested_model
                    for r in await routes.list_model_routes(provider="openai")
                }
                for requested, upstream in (
                    ("gpt-test-mini", "up-mini"),
                    ("gpt-test-tiny", "up-tiny"),
                ):
                    if requested not in existing:
                        await routes.create_model_route(
                            requested_model=requested,
                            provider="openai",
                            upstream_model=upstream,
                        )

    _run(setup())
    return url


def _run(coro):
    return asyncio.run(coro)


@dataclass(frozen=True)
class OwnerContext:
    institution_id: uuid.UUID
    cohort_id: uuid.UUID
    owner_id: uuid.UUID
    owner_email: str


async def _create_owner_context(url: str, tag: str) -> OwnerContext:
    session_factory = _session_factory(url)
    unique = f"{tag}-{uuid.uuid4().hex[:16]}"
    now = datetime.now(UTC)
    async with session_factory() as session:
        async with session.begin():
            institutions = InstitutionsRepository(session)
            cohorts = CohortsRepository(session)
            owners = OwnersRepository(session)
            institution = await institutions.create_institution(
                name=f"SLAIF 198 {unique}", country="SI", notes="198 integration data"
            )
            cohort = await cohorts.create_cohort(
                name=unique,
                description="198 integration cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=30),
            )
            owner = await owners.create_owner(
                name="Clone",
                surname="Test",
                email=f"{unique}@example.invalid",
                institution_id=institution.id,
            )
            return OwnerContext(
                institution_id=institution.id,
                cohort_id=cohort.id,
                owner_id=owner.id,
                owner_email=owner.email,
            )


def _column_attr(column_name: str) -> str:
    # The JSONB column is named "metadata" in the table but maps to the
    # "metadata_json" Python attribute on the model.
    return "metadata_json" if column_name == "metadata" else column_name


def _cli(runner: CliRunner, *args: str):
    return runner.invoke(app, list(args))


def _create_key_cli(
    runner: CliRunner,
    *extra: str,
    owner_id: uuid.UUID,
    cohort_id: uuid.UUID,
    secret_path: Path,
    reason: str,
) -> dict[str, object]:
    now = datetime.now(UTC)
    valid_until = (now + timedelta(days=30)).isoformat()
    result = _cli(
        runner,
        "keys",
        "create",
        "--owner-id",
        str(owner_id),
        "--cohort-id",
        str(cohort_id),
        "--valid-until",
        valid_until,
        "--reason",
        reason,
        "--secret-output-file",
        str(secret_path),
        "--json",
        *extra,
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


async def _plant_usage_evidence(url: str, key_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Finalized usage + replay reference rows on the SOURCE key only."""
    session_factory = _session_factory(url)
    unique = uuid.uuid4().hex
    now = datetime.now(UTC)
    async with session_factory() as session:
        async with session.begin():
            routes = ModelRoutesRepository(session)
            existing = {
                r.requested_model
                for r in await routes.list_model_routes(provider="openai")
            }
            if "gpt-test-mini" not in existing:
                await routes.create_model_route(
                    requested_model="gpt-test-mini",
                    provider="openai",
                    upstream_model="up-mini",
                )
            routes_openai = [
                r
                for r in await routes.list_model_routes(provider="openai")
                if r.requested_model == "gpt-test-mini"
            ]
            route = routes_openai[0]
            ledger = UsageLedger(
                request_id=f"req-{unique}",
                gateway_key_id=key_id,
                endpoint="/v1/chat/completions",
                http_method="POST",
                provider="openai",
                requested_model="gpt-test-mini",
                resolved_model="gpt-test-mini",
                streaming=False,
                success=True,
                accounting_status="finalized",
                http_status=200,
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
                actual_cost_eur=Decimal("0.000000010"),
                native_currency="EUR",
                usage_raw={},
                response_metadata={},
                started_at=now - timedelta(seconds=60),
                finished_at=now - timedelta(seconds=30),
            )
            session.add(ledger)
            await session.flush()
            replay = CodexReplayReference(
                gateway_key_id=key_id,
                usage_ledger_id=ledger.id,
                source_request_id=f"req-{unique}",
                provider="openai",
                route_id=route.id,
                upstream_model="up-mini",
                item_kind="reasoning",
                item_id_hmac=unique.ljust(64, "0"),
                hmac_key_version=1,
                created_at=now - timedelta(seconds=30),
                expires_at=now + timedelta(hours=23),
            )
            session.add(replay)
            await session.flush()
            return ledger.id, replay.id


async def _state_snapshot(url: str, key_id: uuid.UUID) -> dict[str, object]:
    """Full relevant state snapshot: table counts plus every source-key column."""
    factory = _session_factory(url)
    async with factory() as session:
        counts: dict[str, int] = {}
        for table, name in (
            (AuditLog, "audit"),
            (UsageLedger, "ledger"),
            (OneTimeSecret, "one_time_secrets"),
            (EmailDelivery, "email_deliveries"),
            (CodexReplayReference, "replay_references"),
            (GatewayKey, "gateway_keys"),
        ):
            counts[name] = (
                await session.execute(select(func.count()).select_from(table))
            ).scalar_one()
        key_row = await session.get(GatewayKey, key_id)
        return {
            "counts": counts,
            "key_columns": {
                c.key: getattr(key_row, _column_attr(c.key))
                for c in key_row.__table__.columns
            },
        }


async def _count_where(url: str, table, where) -> int:
    factory = _session_factory(url)
    async with factory() as session:
        return (await session.execute(select(func.count()).select_from(table).where(where))).scalar_one()


async def _get_key(url: str, key_id: uuid.UUID) -> dict[str, object]:
    factory = _session_factory(url)
    async with factory() as session:
        row = await session.get(GatewayKey, key_id)
        return {c.key: getattr(row, _column_attr(c.key)) for c in row.__table__.columns}


# --- A1: exact canonical equality, independence, unchanged source -------------


def test_clone_student_source_exact_canonical_equality_and_independence(
    cli_env: str, route_fixtures: str, tmp_path: Path
) -> None:
    url = cli_env
    runner = CliRunner()
    source_ctx = _run(_create_owner_context(url, "src"))
    target_ctx = _run(_create_owner_context(url, "dst"))

    source = _create_key_cli(
        runner,
        "--allowed-model",
        "gpt-test-mini",
        "--allowed-model",
        "gpt-test-tiny",
        "--allowed-endpoint",
        "/v1/chat/completions",
        "--token-limit-total",
        "500000",
        owner_id=source_ctx.owner_id,
        cohort_id=source_ctx.cohort_id,
        secret_path=tmp_path / "src-a.secret",
        reason="198 student source",
    )
    source_id = uuid.UUID(source["gateway_key_id"])

    # Finalized usage + replay evidence on the source ONLY.
    ledger_id, replay_id = _run(_plant_usage_evidence(url, source_id))

    before = _run(_state_snapshot(url, source_id))

    # --- dry-run: plan file, no mutation, no audit ---
    plan_path = tmp_path / "student-plan.json"
    dry = _cli(
        runner,
        "keys",
        "clone",
        "--dry-run",
        str(plan_path),
        "--source-key-id",
        str(source_id),
        "--target-owner-id",
        str(target_ctx.owner_id),
        "--target-cohort-id",
        str(target_ctx.cohort_id),
        "--validity-mode",
        "copy-source-expiry",
        "--json",
    )
    assert dry.exit_code == 0, dry.output
    assert plan_path.exists()
    assert stat.S_IMODE(os.stat(plan_path).st_mode) == 0o600
    plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan_doc["target_owner_id"] == str(target_ctx.owner_id)
    assert plan_doc["target_cohort_id"] == str(target_ctx.cohort_id)
    # Canonical policy: providers ABSENT (unrestricted), cost unlimited,
    # request limit nullable, rate members nullable.
    policy = plan_doc["policy"]
    # Creation persists an explicit null provider policy = unrestricted.
    assert policy["allowed_providers"] is None
    assert policy["cost_limit_eur"] is None
    assert policy["request_limit_total"] is None
    assert policy["token_limit_total"] == 500000

    after_dry = _run(_state_snapshot(url, source_id))
    assert after_dry == before, "dry-run must not mutate anything"

    # --- execute ---
    exec_result = _cli(
        runner,
        "keys",
        "clone",
        "--execute",
        str(plan_path),
        "--reason",
        "198 student clone",
        "--email-delivery",
        "pending",
        "--json",
    )
    assert exec_result.exit_code == 0, exec_result.output
    payload = json.loads(exec_result.stdout)
    assert payload["status"] == "created"
    assert "plaintext_key" not in payload
    target_id = uuid.UUID(payload["target_gateway_key_id"])
    ots_id = uuid.UUID(payload["one_time_secret_id"])
    delivery_id = uuid.UUID(payload["email_delivery_id"])

    # --- exact canonical configuration equality ---
    src_export = _cli(runner, "keys", "policy", "export", str(source_id))
    tgt_export = _cli(runner, "keys", "policy", "export", str(target_id))
    assert src_export.exit_code == 0 and tgt_export.exit_code == 0
    assert json.loads(tgt_export.stdout) == json.loads(src_export.stdout)

    # --- independent material / state / ownership ---
    source_cols = before["key_columns"]
    target_cols = _run(_get_key(url, target_id))
    assert target_cols["id"] != source_cols["id"]
    assert target_cols["public_key_id"] != source_cols["public_key_id"]
    assert target_cols["token_hash"] != source_cols["token_hash"]
    assert target_cols["hmac_key_version"] == 1
    assert target_cols["owner_id"] == target_ctx.owner_id
    assert target_cols["cohort_id"] == target_ctx.cohort_id
    assert target_cols["status"] == "active"
    assert target_cols["cost_used_eur"] == 0
    assert target_cols["tokens_used_total"] == 0
    assert target_cols["requests_used_total"] == 0
    assert target_cols["key_purpose"] == "standard"
    assert target_cols["capability_policy_mode"] == "standard"
    # copy-source-expiry: window starts at execution, ends at source expiry.
    assert target_cols["valid_until"] == source_cols["valid_until"]
    assert target_cols["valid_from"] >= source_cols["valid_from"]
    # Template membership is NOT copied (source has none; target must not gain any).
    assert target_cols["template_id"] is None
    assert target_cols["template_revision_id"] is None

    # One-time secret + pending delivery rows exist for the target.
    assert (
        _run(_count_where(url, OneTimeSecret, OneTimeSecret.gateway_key_id == target_id)) == 1
    )
    assert _run(_count_where(url, OneTimeSecret, OneTimeSecret.id == ots_id)) == 1

    async def _delivery_row():
        async with _session_factory(url)() as session:
            return await session.get(EmailDelivery, delivery_id)

    delivery_row = _run(_delivery_row())
    assert delivery_row is not None
    assert delivery_row.gateway_key_id == target_id
    assert delivery_row.status == "pending"

    # No replay/ledger rows were copied to the target.
    assert (
        _run(
            _count_where(url, CodexReplayReference, CodexReplayReference.gateway_key_id == target_id)
        )
        == 0
    )
    assert (
        _run(_count_where(url, UsageLedger, UsageLedger.gateway_key_id == target_id)) == 0
    )

    # Receipt on the target: bounded safe data only.
    receipt = target_cols["metadata"].get("clone_receipt")
    assert receipt is not None
    assert receipt["source_gateway_key_id"] == str(source_id)
    assert receipt["target_gateway_key_id"] == str(target_id)
    assert receipt["source_fingerprint"] == plan_doc["source_fingerprint"]
    assert receipt["validity_mode"] == "copy-source-expiry"
    joined = json.dumps(receipt)
    assert "sk-slaif-" not in joined
    assert "once-only" not in joined

    # Clone audit: exactly one, safe values only.
    async def _clone_audit():
        async with _session_factory(url)() as session:
            row = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "gateway_key_cloned",
                        AuditLog.entity_id == target_id,
                    )
                )
            ).scalars().all()
            return row

    clone_audits = _run(_clone_audit())
    assert len(clone_audits) == 1
    audit_blob = json.dumps(clone_audits[0].new_values, default=str)
    assert f"sk-slaif-{target_cols['key_prefix']}" not in audit_blob
    secret_file_text = (tmp_path / "src-a.secret").read_text(encoding="utf-8")
    assert secret_file_text.strip() not in audit_blob

    # Source completely unchanged (every column) and its evidence intact.
    after = _run(_state_snapshot(url, source_id))
    assert after["key_columns"] == before["key_columns"]
    assert (
        _run(
            _count_where(
                url, CodexReplayReference, CodexReplayReference.id == replay_id
            )
        )
        == 1
    )
    assert _run(_count_where(url, UsageLedger, UsageLedger.id == ledger_id)) == 1


# --- A2: deny-all providers + configured rates, retry, tamper -----------------


def test_clone_beta_source_rates_denyall_retry_and_tamper(
    cli_env: str, route_fixtures: str, tmp_path: Path
) -> None:
    url = cli_env
    runner = CliRunner()
    source_ctx = _run(_create_owner_context(url, "srcb"))
    target_ctx = _run(_create_owner_context(url, "dstb"))

    source = _create_key_cli(
        runner,
        "--allowed-model",
        "gpt-test-mini",
        "--allowed-endpoint",
        "/v1/chat/completions",
        "--allowed-endpoint",
        "/v1/responses",
        "--provider-none",
        "--cost-limit-eur",
        "50",
        "--token-limit-total",
        "250000",
        "--request-limit-total",
        "1000",
        "--rate-limit-requests-per-minute",
        "30",
        "--rate-limit-tokens-per-minute",
        "5000",
        "--rate-limit-window-seconds",
        "60",
        owner_id=source_ctx.owner_id,
        cohort_id=source_ctx.cohort_id,
        secret_path=tmp_path / "src-b.secret",
        reason="198 beta source",
    )
    source_id = uuid.UUID(source["gateway_key_id"])
    before = _run(_state_snapshot(url, source_id))

    plan_path = tmp_path / "beta-plan.json"
    dry = _cli(
        runner,
        "keys",
        "clone",
        "--dry-run",
        str(plan_path),
        "--source-key-id",
        str(source_id),
        "--target-owner-id",
        str(target_ctx.owner_id),
        "--validity-mode",
        "duration-from-now",
        "--validity-duration-seconds",
        "3600",
        "--json",
    )
    assert dry.exit_code == 0, dry.output
    plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan_doc["policy"]["allowed_providers"] == []
    assert plan_doc["policy"]["rate_limit_policy"] == {
        "requests_per_minute": 30,
        "tokens_per_minute": 5000,
        "window_seconds": 60,
    }

    secret_path = tmp_path / "clone-b.secret"
    executed = _cli(
        runner,
        "keys",
        "clone",
        "--execute",
        str(plan_path),
        "--reason",
        "198 beta clone",
        "--secret-output-file",
        str(secret_path),
        "--json",
    )
    assert executed.exit_code == 0, executed.output
    payload = json.loads(executed.stdout)
    assert payload["status"] == "created"
    target_id = uuid.UUID(payload["target_gateway_key_id"])
    assert secret_path.exists()
    assert stat.S_IMODE(os.stat(secret_path).st_mode) == 0o600
    assert "plaintext_key" not in payload
    assert secret_path.read_text(encoding="utf-8").strip() not in executed.stdout

    # Exact canonical equality including deny-all providers + configured rates.
    src_export = _cli(runner, "keys", "policy", "export", str(source_id))
    tgt_export = _cli(runner, "keys", "policy", "export", str(target_id))
    assert json.loads(tgt_export.stdout) == json.loads(src_export.stdout)

    # Exact repeat: already-applied, no new key/secret/plaintext.
    keys_before = _run(_count_where(url, GatewayKey, GatewayKey.id.is_not(None)))
    repeated = _cli(
        runner,
        "keys",
        "clone",
        "--execute",
        str(plan_path),
        "--reason",
        "198 beta clone retry",
        "--show-plaintext",
        "--json",
    )
    assert repeated.exit_code == 0, repeated.output
    repeated_payload = json.loads(repeated.stdout)
    assert repeated_payload["status"] == "already-applied"
    assert repeated_payload["target_gateway_key_id"] == str(target_id)
    assert "plaintext_key" not in repeated_payload
    assert (
        secret_path.read_text(encoding="utf-8").strip() not in repeated.stdout
    )
    keys_after = _run(_count_where(url, GatewayKey, GatewayKey.id.is_not(None)))
    assert keys_after == keys_before

    # Changed plan with the same operation UUID is refused.
    tampered = dict(plan_doc)
    tampered["validity"] = {
        "mode": "duration-from-now",
        "duration_seconds": 7200,
    }
    tamper_path = tmp_path / "beta-plan-tampered.json"
    tamper_path.write_text(json.dumps(tampered, indent=2) + "\n", encoding="utf-8")
    tampered_run = _cli(
        runner,
        "keys",
        "clone",
        "--execute",
        str(tamper_path),
        "--reason",
        "198 beta tamper",
        "--show-plaintext",
        "--json",
    )
    assert tampered_run.exit_code == 1
    assert "key_clone_plan_mismatch" in tampered_run.stdout

    # Unknown-field and oversized plan files are rejected before any DB write.
    unknown = dict(plan_doc)
    unknown["bogus_field"] = 1
    unknown_path = tmp_path / "beta-plan-unknown.json"
    unknown_path.write_text(json.dumps(unknown), encoding="utf-8")
    unknown_run = _cli(
        runner,
        "keys",
        "clone",
        "--execute",
        str(unknown_path),
        "--reason",
        "x",
        "--show-plaintext",
    )
    assert unknown_run.exit_code == 1
    assert "unsupported fields" in unknown_run.stderr

    oversized_path = tmp_path / "beta-plan-oversized.json"
    oversized_path.write_bytes(b"{" + b'"pad": "' + b"A" * 200_000 + b'"\n}')
    oversized_run = _cli(
        runner,
        "keys",
        "clone",
        "--execute",
        str(oversized_path),
        "--reason",
        "x",
        "--show-plaintext",
    )
    assert oversized_run.exit_code == 1
    # R4: the bounded reader rejects with a fixed safe message (no byte count,
    # path, or body echo) BEFORE any database use.
    assert "exceeds the bounded size" in oversized_run.stderr

    # Source unchanged.
    after = _run(_state_snapshot(url, source_id))
    assert after["key_columns"] == before["key_columns"]


# --- A3: forced LATE clone-audit failure rolls back the whole transaction -----


def test_clone_late_audit_failure_rolls_back(
    cli_env: str, route_fixtures: str, tmp_path: Path, monkeypatch
) -> None:
    url = cli_env
    runner = CliRunner()
    source_ctx = _run(_create_owner_context(url, "srcr"))
    target_ctx = _run(_create_owner_context(url, "dstr"))

    source = _create_key_cli(
        runner,
        "--allowed-model",
        "gpt-test-mini",
        "--allowed-endpoint",
        "/v1/chat/completions",
        owner_id=source_ctx.owner_id,
        cohort_id=source_ctx.cohort_id,
        secret_path=tmp_path / "src-r.secret",
        reason="198 rollback source",
    )
    source_id = uuid.UUID(source["gateway_key_id"])

    plan_path = tmp_path / "rollback-plan.json"
    dry = _cli(
        runner,
        "keys",
        "clone",
        "--dry-run",
        str(plan_path),
        "--source-key-id",
        str(source_id),
        "--target-owner-id",
        str(target_ctx.owner_id),
        "--validity-mode",
        "copy-source-expiry",
    )
    assert dry.exit_code == 0, dry.output
    plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))
    operation_uuid = plan_doc["operation_uuid"]

    before = _run(_state_snapshot(url, source_id))

    hook: dict[str, bool] = {"called": False, "saw_receipt": False, "saw_ots": False}
    original = AuditRepository.add_audit_log

    async def failing_add_audit_log(self, *, action: str, **kwargs: object):
        if action == "gateway_key_cloned":
            # SAME transaction: the new target key + receipt + one-time secret
            # must all already be visible before the forced LATE failure.
            target_id = kwargs.get("entity_id")
            row = await self._session.get(GatewayKey, target_id)  # type: ignore[arg-type]
            receipt = (row.metadata_json or {}).get("clone_receipt") or {}
            hook["saw_receipt"] = (
                receipt.get("operation_uuid") == operation_uuid
                and receipt.get("source_gateway_key_id") == str(source_id)
            )
            ots_id = (kwargs.get("new_values") or {}).get("one_time_secret_id")
            ots = (
                await self._session.execute(
                    select(OneTimeSecret).where(OneTimeSecret.id == ots_id)  # type: ignore[arg-type]
                )
            ).scalar_one_or_none()
            hook["saw_ots"] = ots is not None
            hook["called"] = True
            raise RuntimeError("forced late clone audit failure (198 test)")
        return await original(self, action=action, **kwargs)  # type: ignore[call-arg]

    monkeypatch.setattr(AuditRepository, "add_audit_log", failing_add_audit_log)

    failed = _cli(
        runner,
        "keys",
        "clone",
        "--execute",
        str(plan_path),
        "--reason",
        "198 must roll back",
        "--email-delivery",
        "pending",
        "--json",
    )
    assert failed.exit_code == 1, failed.output
    assert hook["called"], "audit hook was not reached; failure was not LATE"
    assert hook["saw_receipt"], "receipt not visible in the same transaction"
    assert hook["saw_ots"], "one-time secret not visible in the same transaction"

    after = _run(_state_snapshot(url, source_id))
    assert after == before, "caller transaction must roll back ALL new rows"
    receipts = _run(
        _count_where(
            url,
            GatewayKey,
            GatewayKey.metadata_json.op("@>")(
                {"clone_receipt": {"operation_uuid": operation_uuid}}
            ),
        )
    )
    assert receipts == 0, "no partial receipt may persist"


# --- A4: two separate processes, same plan, READ COMMITTED dedup ---------------


def test_clone_concurrent_same_plan_two_processes_one_applied(
    cli_env: str, route_fixtures: str, tmp_path: Path
) -> None:
    url = cli_env
    runner = CliRunner()
    source_ctx = _run(_create_owner_context(url, "srcc"))
    target_ctx = _run(_create_owner_context(url, "dstc"))

    source = _create_key_cli(
        runner,
        "--allowed-model",
        "gpt-test-mini",
        "--allowed-endpoint",
        "/v1/chat/completions",
        "--token-limit-total",
        "100000",
        owner_id=source_ctx.owner_id,
        cohort_id=source_ctx.cohort_id,
        secret_path=tmp_path / "src-c.secret",
        reason="198 concurrency source",
    )
    source_id = uuid.UUID(source["gateway_key_id"])

    plan_path = tmp_path / "concurrent-plan.json"
    dry = _cli(
        runner,
        "keys",
        "clone",
        "--dry-run",
        str(plan_path),
        "--source-key-id",
        str(source_id),
        "--target-owner-id",
        str(target_ctx.owner_id),
        "--target-cohort-id",
        str(target_ctx.cohort_id),
        "--validity-mode",
        "copy-source-expiry",
    )
    assert dry.exit_code == 0, dry.output
    plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))
    operation_uuid = plan_doc["operation_uuid"]

    # Supported isolation boundary: the engine default is READ COMMITTED.
    async def _isolation():
        factory = _session_factory(url)
        async with factory() as session:
            return (await session.execute(select(func.current_setting("transaction_isolation")))).scalar_one()

    assert _run(_isolation()) == "read committed"

    base = [
        "keys",
        "clone",
        "--execute",
        str(plan_path),
        "--reason",
        "198 concurrent clone",
    ]
    # Pending delivery (not a plaintext/file channel): exactly ONE pending
    # delivery must exist for the operation after the concurrent race.
    args_a = base + ["--email-delivery", "pending", "--json"]
    args_b = base + ["--email-delivery", "pending", "--json"]

    env = {**os.environ, "PYTHONPATH": str(APP_DIR)}

    pa = subprocess.Popen(
        [sys.executable, "-c", _CHILD_SCRIPT, *args_a],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    pb = subprocess.Popen(
        [sys.executable, "-c", _CHILD_SCRIPT, *args_b],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out_a, err_a = pa.communicate(timeout=300)
    out_b, err_b = pb.communicate(timeout=300)
    assert pa.returncode == 0, err_a[-2000:]
    assert pb.returncode == 0, err_b[-2000:]
    result_a = json.loads(out_a.strip().splitlines()[-1])
    result_b = json.loads(out_b.strip().splitlines()[-1])

    statuses = sorted(
        [
            json.loads(result_a["stdout"])["status"],
            json.loads(result_b["stdout"])["status"],
        ]
    )
    assert statuses == ["already-applied", "created"]

    target_ids = {
        json.loads(result_a["stdout"])["target_gateway_key_id"],
        json.loads(result_b["stdout"])["target_gateway_key_id"],
    }
    assert len(target_ids) == 1
    target_id = uuid.UUID(target_ids.pop())

    # Exactly ONE target key, one one-time secret, one clone receipt, one
    # clone audit for this operation.
    assert (
        _run(_count_where(url, OneTimeSecret, OneTimeSecret.gateway_key_id == target_id)) == 1
    )
    receipt_count = _run(
        _count_where(
            url,
            GatewayKey,
            GatewayKey.metadata_json.op("@>")(
                {"clone_receipt": {"operation_uuid": operation_uuid}}
            ),
        )
    )
    assert receipt_count == 1
    clone_audits = _run(
        _count_where(
            url,
            AuditLog,
            (AuditLog.action == "gateway_key_cloned") & (AuditLog.entity_id == target_id),
        )
    )
    assert clone_audits == 1

    # Exactly ONE pending delivery for the operation: only the created process
    # made one; the already-applied repeat did not.
    assert (
        _run(
            _count_where(url, EmailDelivery, EmailDelivery.gateway_key_id == target_id)
        )
        == 1
    )
    for blob in (result_a["stdout"], result_b["stdout"]):
        assert "plaintext_key" not in blob


# --- A5: exact retry after simulated post-commit mail failure ------------------


def test_clone_retry_after_postcommit_mail_failure(
    cli_env: str, route_fixtures: str, tmp_path: Path
) -> None:
    url = cli_env
    runner = CliRunner()
    source_ctx = _run(_create_owner_context(url, "srcm"))
    target_ctx = _run(_create_owner_context(url, "dstm"))

    source = _create_key_cli(
        runner,
        "--allowed-model",
        "gpt-test-mini",
        "--allowed-endpoint",
        "/v1/chat/completions",
        owner_id=source_ctx.owner_id,
        cohort_id=source_ctx.cohort_id,
        secret_path=tmp_path / "src-m.secret",
        reason="198 mail-fail source",
    )
    source_id = uuid.UUID(source["gateway_key_id"])

    plan_path = tmp_path / "mailfail-plan.json"
    dry = _cli(
        runner,
        "keys",
        "clone",
        "--dry-run",
        str(plan_path),
        "--source-key-id",
        str(source_id),
        "--target-owner-id",
        str(target_ctx.owner_id),
        "--validity-mode",
        "copy-source-expiry",
    )
    assert dry.exit_code == 0, dry.output
    plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))
    operation_uuid = plan_doc["operation_uuid"]

    # Point send-now at a refused local port: the commit succeeds, the mail
    # fails AFTER commit, and the CLI must exit nonzero with safe IDs only.
    saved = {
        name: os.environ.get(name)
        for name in ("ENABLE_EMAIL_DELIVERY", "SMTP_HOST", "SMTP_PORT", "SMTP_FROM")
    }
    os.environ["ENABLE_EMAIL_DELIVERY"] = "true"
    os.environ["SMTP_HOST"] = "127.0.0.1"
    os.environ["SMTP_PORT"] = "1"
    os.environ["SMTP_FROM"] = "clone-fail@example.invalid"
    get_settings.cache_clear()
    try:
        failed = _cli(
            runner,
            "keys",
            "clone",
            "--execute",
            str(plan_path),
            "--reason",
            "198 mail failure clone",
            "--email-delivery",
            "send-now",
            "--json",
        )
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()

    assert failed.exit_code == 1, failed.output
    payload = json.loads(failed.stdout)
    assert payload["status"] == "created"
    assert payload["email_delivery_status"] == "failed"
    assert "plaintext_key" not in payload
    target_id = uuid.UUID(payload["target_gateway_key_id"])

    # The key committed despite the mail failure; the receipt identifies it.
    target_cols = _run(_get_key(url, target_id))
    assert target_cols["status"] == "active"
    receipt = target_cols["metadata"].get("clone_receipt")
    assert receipt is not None
    assert receipt["operation_uuid"] == operation_uuid

    # Exact retry: already-applied, no second key, no plaintext, no auto-resend.
    keys_before = _run(_count_where(url, GatewayKey, GatewayKey.id.is_not(None)))
    repeated = _cli(
        runner,
        "keys",
        "clone",
        "--execute",
        str(plan_path),
        "--reason",
        "198 mail failure retry",
        "--show-plaintext",
        "--json",
    )
    assert repeated.exit_code == 0, repeated.output
    repeated_payload = json.loads(repeated.stdout)
    assert repeated_payload["status"] == "already-applied"
    assert repeated_payload["target_gateway_key_id"] == str(target_id)
    assert "plaintext_key" not in repeated_payload
    keys_after = _run(_count_where(url, GatewayKey, GatewayKey.id.is_not(None)))
    assert keys_after == keys_before


# --- 198-b: REPEATABLE READ refusal (real owned PG) ----------------------------


def test_clone_repeatableread_isolation_refused_no_rows(
    cli_env: str, route_fixtures: str, tmp_path: Path
) -> None:
    url = cli_env
    runner = CliRunner()
    source_ctx = _run(_create_owner_context(url, "srcr"))
    target_ctx = _run(_create_owner_context(url, "dstr"))

    source = _create_key_cli(
        runner,
        "--allowed-model", "gpt-test-mini",
        "--allowed-endpoint", "/v1/chat/completions",
        owner_id=source_ctx.owner_id,
        cohort_id=source_ctx.cohort_id,
        secret_path=tmp_path / "src-rr.secret",
        reason="198 rr source",
    )
    source_id = uuid.UUID(source["gateway_key_id"])

    plan_path = tmp_path / "rr-plan.json"
    dry = _cli(
        runner, "keys", "clone", "--dry-run", str(plan_path),
        "--source-key-id", str(source_id),
        "--target-owner-id", str(target_ctx.owner_id),
        "--validity-mode", "copy-source-expiry",
    )
    assert dry.exit_code == 0, dry.output
    plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))
    operation_uuid = plan_doc["operation_uuid"]

    before = _run(_state_snapshot(url, source_id))

    async def run_at_rr() -> str:
        settings = get_settings()
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                )
                observed = (
                    await session.execute(
                        select(func.current_setting("transaction_isolation"))
                    )
                ).scalar_one()
                keys_repo = GatewayKeysRepository(session)
                audit_repo = AuditRepository(session)
                key_service = KeyService(
                    settings=settings,
                    gateway_keys_repository=keys_repo,
                    one_time_secrets_repository=OneTimeSecretsRepository(session),
                    audit_repository=audit_repo,
                    model_routes_repository=ModelRoutesRepository(session),
                )
                email_service = EmailDeliveryService(
                    settings=settings,
                    one_time_secrets_repository=OneTimeSecretsRepository(session),
                    email_deliveries_repository=EmailDeliveriesRepository(session),
                    gateway_keys_repository=keys_repo,
                    owners_repository=OwnersRepository(session),
                    audit_repository=audit_repo,
                    email_service=EmailService(settings),
                )
                clone_service = KeyCloneService(
                    settings=settings,
                    key_service=key_service,
                    gateway_keys_repository=keys_repo,
                    owners_repository=OwnersRepository(session),
                    cohorts_repository=CohortsRepository(session),
                    email_delivery_service=email_service,
                    audit_repository=audit_repo,
                )
                try:
                    await clone_service.execute_plan(
                        plan=parse_clone_plan_document(plan_doc),
                        reason="198 rr refusal",
                        actor_admin_id=None,
                        confirm_external_tool_fenced=False,
                        create_email_delivery=True,
                    )
                except KeyCloneUnsupportedIsolationError:
                    await session.rollback()
                    return observed
                raise AssertionError("REPEATABLE READ isolation was not refused")

    observed = _run(run_at_rr())
    assert observed == "repeatable read"

    after = _run(_state_snapshot(url, source_id))
    assert after == before, "RR refusal must leave no new rows or audits"
    receipts = _run(
        _count_where(
            url, GatewayKey,
            GatewayKey.metadata_json.op("@>")(
                {"clone_receipt": {"operation_uuid": operation_uuid}}
            ),
        )
    )
    assert receipts == 0, "no receipt may persist after an RR refusal"


# --- 198-b: two NEW plans from one source -> two independent keys -------------


def test_clone_two_new_plans_from_one_source_create_two_keys(
    cli_env: str, route_fixtures: str, tmp_path: Path
) -> None:
    url = cli_env
    runner = CliRunner()
    source_ctx = _run(_create_owner_context(url, "srct"))
    target_ctx = _run(_create_owner_context(url, "dstt"))

    source = _create_key_cli(
        runner,
        "--allowed-model", "gpt-test-mini",
        "--allowed-endpoint", "/v1/chat/completions",
        owner_id=source_ctx.owner_id,
        cohort_id=source_ctx.cohort_id,
        secret_path=tmp_path / "src-t.secret",
        reason="198 two-plan source",
    )
    source_id = uuid.UUID(source["gateway_key_id"])

    # Two DISTINCT plans (distinct operation UUIDs) from the SAME source, both
    # targeting the SAME existing cohort: each is a legitimate new operation
    # and must create its own independent equivalent key (no source-only dedup).
    plan_paths = []
    for i in (1, 2):
        p = tmp_path / f"two-plan-{i}.json"
        dry = _cli(
            runner, "keys", "clone", "--dry-run", str(p),
            "--source-key-id", str(source_id),
            "--target-owner-id", str(target_ctx.owner_id),
            "--target-cohort-id", str(target_ctx.cohort_id),
            "--validity-mode", "copy-source-expiry",
        )
        assert dry.exit_code == 0, dry.output
        plan_paths.append(p)

    results = []
    for i, p in enumerate(plan_paths):
        result = _cli(
            runner, "keys", "clone", "--execute", str(p),
            "--reason", f"198 two-plan {i + 1}",
            "--show-plaintext", "--json",
        )
        assert result.exit_code == 0, result.output
        results.append(json.loads(result.stdout))

    ops = {r["operation_uuid"] for r in results}
    targets = {r["target_gateway_key_id"] for r in results}
    assert len(ops) == 2, "two distinct operations"
    assert len(targets) == 2, "two independent target keys"
    assert all(r["status"] == "created" for r in results)
    assert all(r["target_public_key_id"] != "pub-source" for r in results)

    # Both targets are independent, active, in the SAME existing cohort, with
    # distinct token material.
    cols_a = _run(_get_key(url, uuid.UUID(results[0]["target_gateway_key_id"])))
    cols_b = _run(_get_key(url, uuid.UUID(results[1]["target_gateway_key_id"])))
    for cols in (cols_a, cols_b):
        assert cols["status"] == "active"
        assert cols["cohort_id"] == target_ctx.cohort_id
    assert cols_a["token_hash"] != cols_b["token_hash"]

"""Real owned-PostgreSQL evidence for objective 197's CLI surfaces.

Covers the bounded wait/reject/reset setter with caller-transaction rollback
on a forced LATE audit failure, effective-policy parity against the REAL
GatewayAuthService (test-owned 0600 one-time secret file), safe lookup and
bounded complete pagination with tied timestamps, configuration-only route
explanation with real route/provider fixtures, and read-only no-mutation
snapshots. No provider HTTP, no Redis, no real upstream contact.

Ownership discipline mirrors the 184/185 owned fixtures: unique owner label,
loopback-bound, tmpfs-backed PostgreSQL 16, identity inspected BEFORE
readiness/migration, cleanup removes ONLY the exact created container ID.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.config import get_settings
from slaif_gateway.db.models import (
    AuditLog,
    GatewayKey,
    OneTimeSecret,
    QuotaReservation,
    UsageLedger,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.services.auth_service import GatewayAuthService
from slaif_gateway.services.rate_limit_policy import (
    build_rate_limit_policy,
    effective_lazy_throttling_policy,
)
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif197a"

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
)

TEST_HMAC_SECRET = "test-hmac-secret-for-cli-effective-policy-12345"
TEST_ADMIN_SECRET = "test-admin-secret-for-cli-effective-policy-12345"
OPENAI_BASE_URL = "https://canary-openai.example.invalid/v1"
OPENROUTER_BASE_URL = "https://canary-openrouter.example.invalid/v1"
CANARY = "PRIVATE_UNSUPPORTED_METADATA_197"


# --- owned PostgreSQL 16 fixture ---------------------------------------------


def _inspect_owned(container, owner: str, container_port: int) -> int:
    """Reload and verify the EXACT created identity; return the bound port."""
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


def _run(coro):
    return asyncio.run(coro)


async def _plant_private_metadata(url: str, key_id: uuid.UUID) -> None:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            row = await session.get(GatewayKey, key_id)
            metadata = dict(row.metadata_json or {})
            metadata["private_note_197"] = CANARY
            row.metadata_json = metadata


async def _state_snapshot(url: str, key_id: uuid.UUID) -> dict[str, object]:
    """Full relevant state snapshot: table counts plus every key column."""
    factory = _session_factory(url)
    async with factory() as session:
        counts: dict[str, int] = {}
        for table, name in (
            (AuditLog, "audit"),
            (UsageLedger, "ledger"),
            (QuotaReservation, "reservations"),
            (OneTimeSecret, "one_time_secrets"),
        ):
            counts[name] = (
                await session.execute(select(func.count()).select_from(table))
            ).scalar_one()
        key_row = await session.get(GatewayKey, key_id)
        return {
            "counts": counts,
            "key_columns": {
                c.key: getattr(key_row, c.key) for c in key_row.__table__.columns
            },
        }


@dataclass(frozen=True)
class OwnerContext:
    institution_id: uuid.UUID
    cohort_id: uuid.UUID
    owner_id: uuid.UUID
    owner_email: str


async def _create_owner_context(url: str) -> OwnerContext:
    session_factory = _session_factory(url)
    unique = f"eff-{uuid.uuid4().hex[:16]}"
    now = datetime.now(UTC)
    async with session_factory() as session:
        async with session.begin():
            institutions = InstitutionsRepository(session)
            cohorts = CohortsRepository(session)
            owners = OwnersRepository(session)
            institution = await institutions.create_institution(
                name=f"SLAIF 197 {unique}", country="SI", notes="197 integration data"
            )
            cohort = await cohorts.create_cohort(
                name=unique,
                description="197 integration cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=30),
            )
            owner = await owners.create_owner(
                name="Eff",
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


def _cli(runner: CliRunner, *args: str):
    return runner.invoke(app, list(args))


# --- A2: bounded wait/reject/reset --------------------------------------------


def test_lazy_wait_set_inspect_clear_and_isolation(
    cli_env: str, route_fixtures: str, tmp_path: Path
) -> None:
    url = cli_env
    runner = CliRunner()

    async def setup():
        context = await _create_owner_context(url)
        return context

    context = _run(setup())

    created = _cli(
        runner,
        "keys",
        "create",
        "--owner-id",
        str(context.owner_id),
        "--valid-days",
        "30",
        "--allowed-model",
        "gpt-test-mini",
        "--allowed-endpoint",
        "/v1/chat/completions",
        "--reason",
        "197 integration create",
        "--secret-output-file",
        str(tmp_path / "wait.secret"),
        "--json",
    )
    assert created.exit_code == 0, created.output
    payload = json.loads(created.stdout)
    key_id = uuid.UUID(payload["gateway_key_id"])

    rates = _cli(
        runner,
        "keys",
        "set-rate-limits",
        str(key_id),
        "--requests-per-minute",
        "1",
        "--window-seconds",
        "10",
        "--concurrent-requests",
        "1",
        "--reason",
        "one request per ten seconds",
    )
    assert rates.exit_code == 0, rates.output

    wait = _cli(
        runner,
        "keys",
        "set-lazy-throttling",
        str(key_id),
        "--mode",
        "wait",
        "--max-wait-seconds",
        "30",
        "--max-waiting-requests",
        "2",
        "--reason",
        "bounded wait for batch runs",
        "--json",
    )
    assert wait.exit_code == 0, wait.output
    wait_body = json.loads(wait.output)
    assert wait_body["lazy_throttling_policy"] == {
        "mode": "wait",
        "max_wait_seconds": 30,
        "max_waiting_requests": 2,
    }

    effective = _cli(runner, "keys", "policy", "effective", str(key_id), "--json")
    assert effective.exit_code == 0, effective.output
    body = json.loads(effective.output)
    assert body["rate_limits"]["requests_per_window"] == {
        "configured": 1,
        "effective": 1,
        "source": "key",
    }
    assert body["rate_limits"]["window_seconds"] == {
        "configured": 10,
        "effective": 10,
        "source": "key",
    }
    assert body["rate_limits"]["count_semantics"] == "counts per selected window"
    lazy = body["lazy_throttling"]
    assert lazy["stored_state"] == "wait-configured"
    assert lazy["mode"] == "wait"
    assert lazy["max_wait_seconds"] == 30
    assert lazy["max_waiting_requests"] == 2
    assert lazy["source"] == "key"

    # Snapshot: only waiting metadata + updated_at + one audit may change.
    async def snapshot():
        factory = _session_factory(url)
        async with factory() as session:
            row = await session.get(GatewayKey, key_id)
            audit_count = (
                await session.execute(
                    select(func.count()).select_from(AuditLog).where(
                        AuditLog.entity_id == key_id
                    )
                )
            ).scalar_one()
            ledger = (
                await session.execute(
                    select(func.count()).select_from(UsageLedger).where(
                        UsageLedger.gateway_key_id == key_id
                    )
                )
            ).scalar_one()
            reservations = (
                await session.execute(
                    select(func.count()).select_from(QuotaReservation).where(
                        QuotaReservation.gateway_key_id == key_id
                    )
                )
            ).scalar_one()
            return {
                "columns": {
                    c.key: getattr(row, c.key) for c in row.__table__.columns
                },
                "metadata": dict(row.metadata_json or {}),
                "audit_count": audit_count,
                "ledger_count": ledger,
                "reservation_count": reservations,
            }

    before = _run(snapshot())
    metadata_before = dict(before["metadata"])
    metadata_before.pop("lazy_throttling_policy", None)

    clear = _cli(
        runner,
        "keys",
        "set-lazy-throttling",
        str(key_id),
        "--clear",
        "--reason",
        "stop waiting",
        "--json",
    )
    assert clear.exit_code == 0, clear.output
    assert json.loads(clear.output)["lazy_throttling_policy"] is None

    after = _run(snapshot())
    before_columns = dict(before["columns"])
    after_columns = dict(after["columns"])
    for field in (
        "token_hash",
        "status",
        "valid_from",
        "valid_until",
        "cost_limit_eur",
        "token_limit_total",
        "request_limit_total",
        "cost_used_eur",
        "tokens_used_total",
        "requests_used_total",
        "cost_reserved_eur",
        "tokens_reserved_total",
        "requests_reserved_total",
        "rate_limit_requests_per_minute",
        "rate_limit_tokens_per_minute",
        "max_concurrent_requests",
    ):
        assert before_columns[field] == after_columns[field], field
    assert after_columns["updated_at"] >= before_columns["updated_at"]
    assert after["metadata"].pop("lazy_throttling_policy", "absent") == "absent"
    assert after["metadata"] == metadata_before
    assert after["audit_count"] == before["audit_count"] + 1
    assert after["ledger_count"] == before["ledger_count"]
    assert after["reservation_count"] == before["reservation_count"]

    # Out-of-range wait fails with NO change and NO extra audit.
    over = _cli(
        runner,
        "keys",
        "set-lazy-throttling",
        str(key_id),
        "--mode",
        "wait",
        "--max-wait-seconds",
        "999999",
        "--max-waiting-requests",
        "2",
        "--reason",
        "excessive wait must be refused",
    )
    assert over.exit_code == 2
    assert "operator ceiling" in over.output
    final = _run(snapshot())
    assert final["audit_count"] == after["audit_count"]
    assert final["columns"]["updated_at"] == after_columns["updated_at"]

    # Toggle back to wait, then reject stores the canonical (cleared) policy.
    wait2 = _cli(
        runner,
        "keys",
        "set-lazy-throttling",
        str(key_id),
        "--mode",
        "wait",
        "--max-wait-seconds",
        "10",
        "--max-waiting-requests",
        "1",
        "--reason",
        "retry wait",
        "--json",
    )
    assert wait2.exit_code == 0, wait2.output
    reject = _cli(
        runner,
        "keys",
        "set-lazy-throttling",
        str(key_id),
        "--mode",
        "reject",
        "--reason",
        "reject again",
        "--json",
    )
    assert reject.exit_code == 0, reject.output
    assert json.loads(reject.output)["lazy_throttling_policy"] is None
    effective2 = _cli(runner, "keys", "policy", "effective", str(key_id), "--json")
    assert json.loads(effective2.output)["lazy_throttling"]["stored_state"] == "absent"


def test_lazy_late_audit_failure_rolls_back(
    cli_env: str, route_fixtures: str, monkeypatch, tmp_path: Path
) -> None:
    url = cli_env
    runner = CliRunner()
    context = _run(_create_owner_context(url))

    created = _cli(
        runner,
        "keys",
        "create",
        "--owner-id",
        str(context.owner_id),
        "--valid-days",
        "30",
        "--allowed-model",
        "gpt-test-mini",
        "--allowed-endpoint",
        "/v1/chat/completions",
        "--reason",
        "197 rollback create",
        "--secret-output-file",
        str(tmp_path / "rollback.secret"),
        "--json",
    )
    assert created.exit_code == 0, created.output
    key_id = uuid.UUID(json.loads(created.stdout)["gateway_key_id"])

    hook: dict[str, bool] = {"called": False, "saw_update": False}
    original = AuditRepository.add_audit_log

    async def failing_add_audit_log(self, *, action: str, **kwargs: object):
        if action == "update_key_lazy_throttling":
            # SAME transaction: the metadata update must already be visible
            # before the forced late audit failure.
            row = await self._session.get(GatewayKey, key_id)
            stored = (row.metadata_json or {}).get("lazy_throttling_policy")
            hook["saw_update"] = bool(
                isinstance(stored, dict) and stored.get("mode") == "wait"
            )
            hook["called"] = True
            raise RuntimeError("forced late audit failure (197 test)")
        return await original(self, action=action, **kwargs)  # type: ignore[call-arg]

    monkeypatch.setattr(AuditRepository, "add_audit_log", failing_add_audit_log)

    async def snapshot_metadata():
        factory = _session_factory(url)
        async with factory() as session:
            row = await session.get(GatewayKey, key_id)
            audit_count = (
                await session.execute(
                    select(func.count()).select_from(AuditLog).where(
                        AuditLog.entity_id == key_id,
                        AuditLog.action == "update_key_lazy_throttling",
                    )
                )
            ).scalar_one()
            return dict(row.metadata_json or {}), audit_count

    before_meta, before_audit = _run(snapshot_metadata())

    failed = _cli(
        runner,
        "keys",
        "set-lazy-throttling",
        str(key_id),
        "--mode",
        "wait",
        "--max-wait-seconds",
        "15",
        "--max-waiting-requests",
        "1",
        "--reason",
        "must roll back",
    )
    assert failed.exit_code == 1

    assert hook["called"], "audit hook was not reached; failure was not LATE"
    assert hook["saw_update"], "metadata update not visible in the same transaction"

    after_meta, after_audit = _run(snapshot_metadata())
    assert after_meta == before_meta  # caller transaction rolled back
    assert after_audit == 0  # no partial audit row persisted


# --- A2: effective policy parity against the REAL GatewayAuthService ----------


def test_effective_policy_parity_with_real_auth(
    cli_env: str, route_fixtures: str, tmp_path: Path
) -> None:
    url = cli_env
    runner = CliRunner()
    context = _run(_create_owner_context(url))
    secret_file = tmp_path / "new-key.secret"

    created = _cli(
        runner,
        "keys",
        "create",
        "--owner-id",
        str(context.owner_id),
        "--valid-days",
        "30",
        "--allowed-model",
        "gpt-test-mini",
        "--allowed-endpoint",
        "/v1/chat/completions",
        "--secret-output-file",
        str(secret_file),
        "--reason",
        "197 parity create",
        "--json",
    )
    assert created.exit_code == 0, created.output
    payload = json.loads(created.stdout)
    key_id = uuid.UUID(payload["gateway_key_id"])
    assert "plaintext_key" not in payload

    # Test-owned 0600 one-time secret file.
    mode = stat.S_IMODE(secret_file.stat().st_mode)
    assert mode == 0o600, oct(mode)
    plaintext = secret_file.read_text().strip()
    assert plaintext.startswith("sk-slaif-")

    _cli(
        runner,
        "keys",
        "set-rate-limits",
        str(key_id),
        "--requests-per-minute",
        "2",
        "--window-seconds",
        "30",
        "--reason",
        "parity rates",
    )
    _cli(
        runner,
        "keys",
        "set-lazy-throttling",
        str(key_id),
        "--mode",
        "wait",
        "--max-wait-seconds",
        "20",
        "--max-waiting-requests",
        "3",
        "--reason",
        "parity wait",
    )

    settings = get_settings()

    async def real_auth():
        factory = _session_factory(url)
        async with factory() as session:
            auth_service = GatewayAuthService(
                settings=settings,
                gateway_keys_repository=GatewayKeysRepository(session),
            )
            return await auth_service.authenticate_authorization_header(
                f"Bearer {plaintext}"
            )

    authenticated = _run(real_auth())
    assert authenticated.gateway_key_id == key_id
    real_policy = build_rate_limit_policy(
        authenticated_key=authenticated, settings=settings
    )
    real_lazy = effective_lazy_throttling_policy(
        authenticated_key=authenticated, settings=settings
    )

    effective = _cli(runner, "keys", "policy", "effective", str(key_id), "--json")
    assert effective.exit_code == 0, effective.output
    body = json.loads(effective.output)

    assert body["rate_limits"]["requests_per_window"]["effective"] == (
        real_policy.requests_per_minute
    )
    assert body["rate_limits"]["requests_per_window"]["source"] == "key"
    assert body["rate_limits"]["window_seconds"]["effective"] == real_policy.window_seconds
    assert body["rate_limits"]["window_seconds"]["source"] == "key"
    lazy = body["lazy_throttling"]
    assert lazy["mode"] == real_lazy.mode
    assert lazy["max_wait_seconds"] == real_lazy.max_wait_seconds
    assert lazy["max_waiting_requests"] == real_lazy.max_waiting_requests
    assert body["allowlists"]["allow_all_models"] == authenticated.allow_all_models
    assert body["allowlists"]["allowed_models"] == list(authenticated.allowed_models)
    assert (
        body["allowlists"]["allow_all_endpoints"] == authenticated.allow_all_endpoints
    )
    assert (
        body["allowlists"]["allowed_endpoints"] == list(authenticated.allowed_endpoints)
    )
    if authenticated.allowed_providers is None:
        assert body["allowlists"]["state"] == "unrestricted"
    else:
        assert body["allowlists"]["allowed_providers"] == list(
            authenticated.allowed_providers
        )
    # Configuration view must not read as authentication success.
    assert body["scope"] == "configuration-only"
    assert body["key"]["status_note"] is None


# --- A3: safe lookup and bounded complete pagination ----------------------------


def test_lookup_and_paging_with_tied_timestamps(cli_env: str) -> None:
    url = cli_env
    runner = CliRunner()
    context = _run(_create_owner_context(url))

    async def create_rows_tied():
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                keys = GatewayKeysRepository(session)
                base = datetime.now(UTC) - timedelta(hours=1)
                ids = []
                for index in range(5):
                    row = await keys.create_gateway_key_record(
                        public_key_id=f"pub197{index}{'x' * 30}",
                        token_hash=f"hash197-{uuid.uuid4().hex}",
                        owner_id=context.owner_id,
                        cohort_id=context.cohort_id,
                        valid_from=base,
                        valid_until=base + timedelta(days=30),
                        status="active",
                    )
                    ids.append(row.id)
                await session.execute(
                    sa_update(GatewayKey)
                    .where(GatewayKey.id.in_(ids[:2]))
                    .values(created_at=base)
                )
                return ids

    _run(create_rows_tied())

    seen: list[str] = []
    offset = 0
    pages = 0
    while True:
        result = _cli(
            runner,
            "keys",
            "list",
            "--owner-email",
            context.owner_email,
            "--limit",
            "2",
            "--offset",
            str(offset),
            "--json",
        )
        assert result.exit_code == 0, result.output
        body = json.loads(result.output)
        paging = body["paging"]
        for key in body["keys"]:
            seen.append(key["public_key_id"])
            assert key["owner_id"] == str(context.owner_id)
        pages += 1
        if not paging["has_more"]:
            assert paging["next_offset"] is None
            break
        offset = paging["next_offset"]
        assert pages <= 10, "pagination did not terminate"

    assert len(seen) == 5
    assert len(set(seen)) == 5, "duplicate or lost rows across pages"
    assert pages == 3  # 2 + 2 + 1 with two tied timestamps


def test_lookup_exact_public_id_bearer_refusal_and_unknown_email(cli_env: str) -> None:
    url = cli_env
    runner = CliRunner()
    context = _run(_create_owner_context(url))

    async def create_one():
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                keys = GatewayKeysRepository(session)
                now = datetime.now(UTC)
                row = await keys.create_gateway_key_record(
                    public_key_id=f"publookup{'y' * 33}",
                    token_hash=f"hashlookup-{uuid.uuid4().hex}",
                    owner_id=context.owner_id,
                    cohort_id=context.cohort_id,
                    valid_from=now,
                    valid_until=now + timedelta(days=30),
                    status="active",
                )
                return row.public_key_id

    public_key_id = _run(create_one())

    by_public = _cli(runner, "keys", "show", public_key_id, "--json")
    assert by_public.exit_code == 0, by_public.output
    assert json.loads(by_public.output)["public_key_id"] == public_key_id

    bearer = f"sk-slaif-{public_key_id}." + "B" * 43
    refused = _cli(runner, "keys", "show", bearer, "--json")
    assert refused.exit_code == 1
    assert "Full key material cannot be used for lookup" in refused.output
    assert bearer not in refused.output
    assert bearer not in refused.stderr

    unknown = _cli(runner, "keys", "list", "--owner-email", "nobody-197@example.invalid", "--json")
    assert unknown.exit_code == 1
    assert "No owner exists for the provided email" in unknown.output
    assert "nobody-197@example.invalid" not in unknown.output


def test_cohort_status_filter_before_limit(cli_env: str) -> None:
    url = cli_env
    runner = CliRunner()
    context = _run(_create_owner_context(url))

    async def setup():
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                cohorts = CohortsRepository(session)
                keys = GatewayKeysRepository(session)
                now = datetime.now(UTC)
                second_cohort = await cohorts.create_cohort(
                    name=f"second-{uuid.uuid4().hex[:12]}",
                    description="197 second cohort",
                    starts_at=now,
                    ends_at=now + timedelta(days=5),
                )
                for index in range(3):
                    await keys.create_gateway_key_record(
                        public_key_id=f"pubfiltA{index}{'z' * 31}",
                        token_hash=f"hashfiltA-{uuid.uuid4().hex}",
                        owner_id=context.owner_id,
                        cohort_id=context.cohort_id,
                        valid_from=now,
                        valid_until=now + timedelta(days=30),
                        status="active",
                    )
                await keys.create_gateway_key_record(
                    public_key_id=f"pubfiltB0{'z' * 32}",
                    token_hash=f"hashfiltB-{uuid.uuid4().hex}",
                    owner_id=context.owner_id,
                    cohort_id=second_cohort.id,
                    valid_from=now,
                    valid_until=now + timedelta(days=30),
                    status="suspended",
                )
                return second_cohort.id

    second_cohort_id = _run(setup())

    only_cohort = _cli(
        runner,
        "keys",
        "list",
        "--owner-email",
        context.owner_email,
        "--cohort-id",
        str(context.cohort_id),
        "--limit",
        "2",
        "--json",
    )
    assert only_cohort.exit_code == 0, only_cohort.output
    body = json.loads(only_cohort.output)
    assert len(body["keys"]) == 2
    assert body["paging"]["has_more"] is True
    for key in body["keys"]:
        assert key["cohort_id"] == str(context.cohort_id)

    other_cohort = _cli(
        runner,
        "keys",
        "list",
        "--owner-email",
        context.owner_email,
        "--cohort-id",
        str(second_cohort_id),
        "--status",
        "suspended",
        "--json",
    )
    body2 = json.loads(other_cohort.output)
    assert len(body2["keys"]) == 1
    assert body2["keys"][0]["status"] == "suspended"


# --- A3: configuration-only route explanation with real fixtures ----------------


@pytest.fixture(scope="module")
def route_fixtures(cli_env: str) -> str:
    """Real repository route/provider fixtures for explanation cases."""
    url = cli_env

    async def setup():
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                providers = ProviderConfigsRepository(session)
                routes = ModelRoutesRepository(session)
                await providers.create_provider_config(
                    provider="openai",
                    display_name="OpenAI",
                    base_url=OPENAI_BASE_URL,
                    api_key_env_var="OPENAI_UPSTREAM_API_KEY",
                )
                await providers.create_provider_config(
                    provider="openrouter",
                    display_name="OpenRouter",
                    base_url=OPENROUTER_BASE_URL,
                    api_key_env_var="OPENROUTER_API_KEY",
                )
                await routes.create_model_route(
                    requested_model="exa-model-a", provider="openai", upstream_model="up-a"
                )
                await routes.create_model_route(
                    requested_model="exa-model-b",
                    provider="openai",
                    upstream_model="up-b",
                    enabled=False,
                )
                await routes.create_model_route(
                    requested_model="exa-model-c",
                    provider="openai",
                    upstream_model="up-c",
                    enabled=False,
                )
                await routes.create_model_route(
                    requested_model="exa-ambig",
                    provider="openai",
                    upstream_model="up-ambig",
                    priority=100,
                )
                await routes.create_model_route(
                    requested_model="exa-ambig",
                    provider="openrouter",
                    upstream_model="up-ambig-2",
                    priority=100,
                )
                await routes.create_model_route(
                    requested_model="exa-notext",
                    provider="openai",
                    upstream_model="up-notext",
                    capabilities={
                        "chat_completions": {"chat_text": False}
                    },
                )
                # Base route so CLI key creation with --allowed-model
                # gpt-test-mini passes the enabled-route validation.
                await routes.create_model_route(
                    requested_model="gpt-test-mini",
                    provider="openai",
                    upstream_model="gpt-test-mini",
                )
        return url

    return _run(setup())


def test_explain_required_example_and_blockers(
    cli_env: str, route_fixtures: str, tmp_path: Path
) -> None:
    url = cli_env
    runner = CliRunner()
    context = _run(_create_owner_context(url))

    # Repository-created on purpose: the required example allows models
    # whose Chat routes are DISABLED (exa-model-b/c), which the CLI create
    # validation (enabled-route requirement) would refuse to author.
    async def create_main_key():
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                keys = GatewayKeysRepository(session)
                now = datetime.now(UTC)
                return await keys.create_gateway_key_record(
                    public_key_id=f"pubexplain{'w' * 32}",
                    token_hash=f"hashexplain-{uuid.uuid4().hex}",
                    owner_id=context.owner_id,
                    cohort_id=context.cohort_id,
                    valid_from=now,
                    valid_until=now + timedelta(days=30),
                    status="active",
                    allowed_models=["exa-model-a", "exa-model-b", "exa-model-c"],
                    allowed_endpoints=["/v1/chat/completions"],
                )

    key_id = str(_run(create_main_key()).id)

    resolved = _cli(
        runner,
        "keys",
        "policy",
        "explain-route",
        key_id,
        "--model",
        "exa-model-a",
        "--endpoint",
        "/v1/chat/completions",
        "--json",
    )
    assert resolved.exit_code == 0, resolved.output
    body = json.loads(resolved.output)
    assert body["verdict"] == "resolved"
    assert body["resolution"]["provider"] == "openai"
    intersection = body["allowlist_intersection"]
    # Required example: three allowed models, only one with an enabled Chat route.
    assert intersection["allowed_models"] == [
        "exa-model-a",
        "exa-model-b",
        "exa-model-c",
    ]
    assert intersection["allowed_models_with_candidate_route"] == ["exa-model-a"]
    assert body["capability_checks"]["base_request_supported"] is True
    # No provider configuration references leak.
    assert OPENAI_BASE_URL not in resolved.output
    assert "api_key_env_var" not in resolved.output
    assert "fake-openai-upstream-key" not in resolved.output

    disabled = _cli(
        runner,
        "keys",
        "policy",
        "explain-route",
        key_id,
        "--model",
        "exa-model-b",
        "--json",
    )
    assert json.loads(disabled.output)["blocker"] == "model-route-disabled"

    # exa-ambig is NOT in this key's allow-list, so the key grant check
    # blocks it before any route ranking; the resolver's own ambiguity error
    # is unreachable here because distinct routes always differ on the
    # deterministic route-ID tiebreaker.
    not_allowed = _cli(
        runner,
        "keys",
        "policy",
        "explain-route",
        key_id,
        "--model",
        "exa-ambig",
        "--json",
    )
    assert json.loads(not_allowed.output)["blocker"] == "model-not-allowed-for-key"

    # A separate key that is allowed for the capability-restricted route so
    # the BASE-request capability check is what blocks it.
    notext_created = _cli(
        runner,
        "keys",
        "create",
        "--owner-id",
        str(context.owner_id),
        "--valid-days",
        "30",
        "--allowed-model",
        "exa-notext",
        "--allowed-endpoint",
        "/v1/chat/completions",
        "--reason",
        "197 explain capability create",
        "--secret-output-file",
        str(tmp_path / "explain-notext.secret"),
        "--json",
    )
    assert notext_created.exit_code == 0, notext_created.output
    notext_key_id = str(json.loads(notext_created.stdout)["gateway_key_id"])

    notext = _cli(
        runner,
        "keys",
        "policy",
        "explain-route",
        notext_key_id,
        "--model",
        "exa-notext",
        "--json",
    )
    notext_body = json.loads(notext.output)
    assert notext_body["blocker"] == "route-capability-not-supported"
    assert (
        notext_body["capability_checks"]["capability_error_code"]
        == "chat_capability_not_supported"
    )

    # /v1/models is separately-authorized discovery, never auto-granted.
    discovery = _cli(
        runner,
        "keys",
        "policy",
        "explain-route",
        key_id,
        "--model",
        "exa-model-a",
        "--endpoint",
        "/v1/models",
        "--json",
    )
    discovery_body = json.loads(discovery.output)
    assert discovery_body["verdict"] == "discovery-separately-authorized"
    assert discovery_body["endpoint_allowed"] is False
    assert discovery_body["blocker"] == "endpoint-not-allowed"


def test_explain_provider_and_key_state_blockers(
    cli_env: str, route_fixtures: str
) -> None:
    url = cli_env
    runner = CliRunner()
    context = _run(_create_owner_context(url))

    async def setup_keys():
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                keys = GatewayKeysRepository(session)
                now = datetime.now(UTC)
                # Provider deny-all key.
                deny_all = await keys.create_gateway_key_record(
                    public_key_id=f"pubdenyall{'q' * 32}",
                    token_hash=f"hashdenyall-{uuid.uuid4().hex}",
                    owner_id=context.owner_id,
                    cohort_id=context.cohort_id,
                    valid_from=now,
                    valid_until=now + timedelta(days=30),
                    status="active",
                    allowed_models=["exa-model-a"],
                    allowed_endpoints=["/v1/chat/completions"],
                    metadata_json={"allowed_providers": []},
                )
                # Suspended key.
                suspended = await keys.create_gateway_key_record(
                    public_key_id=f"pubsuspended{'q' * 29}",
                    token_hash=f"hashsuspended-{uuid.uuid4().hex}",
                    owner_id=context.owner_id,
                    cohort_id=context.cohort_id,
                    valid_from=now,
                    valid_until=now + timedelta(days=30),
                    status="suspended",
                    allowed_models=["exa-model-a"],
                    allowed_endpoints=["/v1/chat/completions"],
                )
                # Expired key.
                expired = await keys.create_gateway_key_record(
                    public_key_id=f"pubexpired{'q' * 30}",
                    token_hash=f"hashexpired-{uuid.uuid4().hex}",
                    owner_id=context.owner_id,
                    cohort_id=context.cohort_id,
                    valid_from=now - timedelta(days=3),
                    valid_until=now - timedelta(days=1),
                    status="active",
                    allowed_models=["exa-model-a"],
                    allowed_endpoints=["/v1/chat/completions"],
                )
                # Fenced key (active external-tool fence with real reservation).
                fenced = await keys.create_gateway_key_record(
                    public_key_id=f"pubfenced{'q' * 31}",
                    token_hash=f"hashfenced-{uuid.uuid4().hex}",
                    owner_id=context.owner_id,
                    cohort_id=context.cohort_id,
                    valid_from=now,
                    valid_until=now + timedelta(days=30),
                    status="active",
                    allowed_models=["exa-model-a"],
                    allowed_endpoints=["/v1/chat/completions"],
                )
                reservation = QuotaReservation(
                    gateway_key_id=fenced.id,
                    request_id=f"req-fence-197-{uuid.uuid4().hex}",
                    endpoint="/v1/chat/completions",
                    requested_model="exa-model-a",
                    expires_at=now + timedelta(minutes=5),
                )
                session.add(reservation)
                await session.flush()
                fenced.external_tool_fence_state = "active"
                fenced.external_tool_fence_reservation_id = reservation.id
                fenced.external_tool_fence_request_id = reservation.request_id
                fenced.external_tool_fence_acquired_at = now
                fenced.external_tool_fence_expires_at = now + timedelta(minutes=5)
                return deny_all.id, suspended.id, expired.id, fenced.id

    deny_all_id, suspended_id, expired_id, fenced_id = _run(setup_keys())

    deny = _cli(
        runner,
        "keys",
        "policy",
        "explain-route",
        str(deny_all_id),
        "--model",
        "exa-model-a",
        "--json",
    )
    deny_body = json.loads(deny.output)
    assert deny_body["blocker"] == "provider-not-allowed-for-key"
    assert deny_body["allowlist_intersection"]["allowed_models_with_candidate_route"] == []

    suspended_report = _cli(
        runner,
        "keys",
        "policy",
        "explain-route",
        str(suspended_id),
        "--model",
        "exa-model-a",
        "--json",
    )
    assert json.loads(suspended_report.output)["blocker"] == "key-suspended"

    expired_report = _cli(
        runner,
        "keys",
        "policy",
        "explain-route",
        str(expired_id),
        "--model",
        "exa-model-a",
        "--json",
    )
    expired_body = json.loads(expired_report.output)
    assert expired_body["blocker"] == "key-expired"
    assert expired_body["resolution"] is None
    assert expired_body["key_state"]["usable_for_requests"] is False

    fenced_report = _cli(
        runner,
        "keys",
        "policy",
        "explain-route",
        str(fenced_id),
        "--model",
        "exa-model-a",
        "--json",
    )
    assert (
        json.loads(fenced_report.output)["blocker"]
        == "key-external-tool-fence-active"
    )


def test_readonly_inspection_changes_nothing(
    cli_env: str, route_fixtures: str, tmp_path: Path
) -> None:
    url = cli_env
    runner = CliRunner()
    context = _run(_create_owner_context(url))

    created = _cli(
        runner,
        "keys",
        "create",
        "--owner-id",
        str(context.owner_id),
        "--valid-days",
        "30",
        "--allowed-model",
        "exa-model-a",
        "--allowed-endpoint",
        "/v1/chat/completions",
        "--reason",
        "197 readonly create",
        "--secret-output-file",
        str(tmp_path / "readonly.secret"),
        "--json",
    )
    assert created.exit_code == 0, created.output
    payload = json.loads(created.stdout)
    key_id = uuid.UUID(payload["gateway_key_id"])
    public_key_id = payload["public_key_id"]

    _run(_plant_private_metadata(url, key_id))
    before = _run(_state_snapshot(url, key_id))

    outputs: list[str] = []
    for args in (
        ("keys", "policy", "effective", str(key_id), "--json"),
        (
            "keys",
            "policy",
            "explain-route",
            str(key_id),
            "--model",
            "exa-model-a",
            "--json",
        ),
        ("keys", "show", str(key_id), "--json"),
        ("keys", "list", "--owner-email", context.owner_email, "--limit", "5", "--json"),
    ):
        result = _cli(runner, *args)
        assert result.exit_code == 0, result.output
        outputs.append(result.output)

    after = _run(_state_snapshot(url, key_id))
    assert after["counts"] == before["counts"]
    assert after["key_columns"] == before["key_columns"]

    for output in outputs:
        assert CANARY not in output
        assert TEST_HMAC_SECRET not in output
        # A full bearer (prefix + FULL public id + secret) must never appear;
        # the configured prefix and the 8-char display hint are safe metadata.
        assert f"sk-slaif-{public_key_id}" not in output
        assert OPENAI_BASE_URL not in output
        assert "fake-openai-upstream-key" not in output

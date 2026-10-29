"""Real CLI + real service + real owned-PostgreSQL-16 evidence for 203-a.

Drives the ACTUAL CLI entrypoint (Typer app, real repositories/SQL) and
the ACTUAL shared KeyBatchService/KeyService against one real disposable
PostgreSQL 16 database. No provider, SMTP, or broker contact of any kind:
no provider credentials are configured for any forwarding decision, no
email is sent, and no Celery task is enqueued.

Proves:
- the mandatory 37-key cohort: ``plan`` is a READ ONLY preview that
  identifies the EXACT eligible UUID set (37 active; suspended/revoked
  members are never selected and a cohort selection reports an empty
  ``excluded_by_status`` per contract, while the suspended/revoked control
  rows are proven unchanged), with zero writes, zero audits, and zero
  material/state change; ``apply`` runs the EXISTING per-key
  ``update_key_configuration`` law in ONE caller-owned transaction with
  exact per-key audits (reason/actor, old/new request limits), preserves
  revoked/suspended/unrelated/other-cohort keys and all usage/reservation
  state, and a whole-set repeat is ``already_at_target`` with zero
  writes and zero new audits;
- explicit UUID selection with mixed statuses (``excluded_by_status``),
  duplicate refusal, missing-ID whole-request refusal (count only, no ID
  echo), and separate ``--status`` inclusion;
- a >100-eligible cohort (selection/preview not truncated at 100) and a
  >1000 cohort refused (cap+1 overflow) before any artifact or write;
- stale member add/removal, config drift, and status drift: whole-batch
  refusal with zero writes and zero audits; plus a controlled real-PG
  lock-wait concurrency case where a competitor commits a NEW eligible
  cohort member while the apply is blocked on a LATER selected-key row
  lock (the causal wait is observed via pg_stat_activity with
  pg_stat_clear_snapshot; the post-last-lock membership re-resolution
  refuses the whole batch);
- a late injected audit failure at a LATER key rolls back ALL keys and
  ALL provisional audits (no partial commit);
- usage-only counter movement between preview and apply never stales the
  repeat and is preserved;
- the real-PG money-target normalization: an ordinary integer EUR target
  renders/applies at the exact Numeric(18,9) representation
  ("2" -> "2.000000000"), a 9-decimal input round-trips, and a
  10-decimal target is refused at the projection boundary;
- the fenced external-tool target: a SAVED plan confirmation is NOT
  authority - apply without the fresh explicit flag refuses before any
  write/audit, the fresh flag applies with one per-key audit, and
  repeated decisions retain the current guard;
- edited-plan fingerprint coherence: an edited advertised before (with
  the derived diff) and a coherently edited policy+after+diff carrying a
  stale post digest are both refused on first apply AND repeat with zero
  writes;
- CLI canaries: a credential shape in the policy file, in the plan
  artifact pathname, and in the audit reason are all refused with fixed
  safe errors, never echoed in stdout/stderr, with no artifact and no
  writes.

Ownership discipline mirrors the 198/199/200/202 owned fixtures: unique
owner label, loopback-bound, tmpfs-backed PostgreSQL 16, identity
inspected BEFORE readiness/migration, cleanup removes ONLY the exact
created container ID.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import time
import uuid
from collections.abc import Iterator
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
    AdminUser,
    AuditLog,
    Cohort,
    GatewayKey,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.schemas.key_batch import (
    KeyBatchStaleError,
    parse_key_batch_plan_file,
)
from slaif_gateway.services.key_batch_service import KeyBatchService
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif203a"

_ENV_VARS = (
    "DATABASE_URL",
    "APP_ENV",
    "GATEWAY_KEY_PREFIX",
    "GATEWAY_KEY_ACCEPTED_PREFIXES",
    "ACTIVE_HMAC_KEY_VERSION",
    "TOKEN_HMAC_SECRET_V1",
    "ADMIN_SESSION_SECRET",
    "ONE_TIME_SECRET_ENCRYPTION_KEY",
    "ENABLE_EMAIL_DELIVERY",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_FROM",
    "CELERY_BROKER_URL",
    "OPENAI_UPSTREAM_API_KEY",
    "OPENROUTER_API_KEY",
)

TEST_HMAC_SECRET = "test-hmac-secret-for-cli-key-batches-203a"
TEST_ADMIN_SECRET = "test-admin-secret-for-cli-key-batches-203a"

CANARY = "sk-slaif-canary203a00000000000"
# Recognized provider-key shape the finite redaction patterns match in any
# surrounding context (plan-artifact pathname canary).
PATH_CANARY = "sk-proj-canary203a000000000000"

POLICY_333 = {"schema_version": 1, "request_limit_total": 333}
POLICY_2000 = {"schema_version": 1, "request_limit_total": 2000}
FENCED_POLICY = {
    "schema_version": 1,
    "request_limit_total": 500,
    "token_limit_total": 100_000,
    "cost_limit_eur": "10.000000000",
    "external_tool_policy": {
        "version": 1,
        "mode": "external_tool_fenced",
        "allowed_capabilities": ["provider_web_search"],
        "allowed_destination_ids": [],
        "max_provider_tool_calls_per_request": 1,
        "single_request_overrun_acknowledged": True,
    },
    "confirm_external_tool_fenced": True,
}

_runner = CliRunner()
_S: dict[str, object] = {}

# Module-scoped plan artifact directory: the reviewed 37-key plan must
# SURVIVE across the plan/apply/repeat/canary tests (function-scoped
# tmp_path is deleted between tests and would make later tests depend on
# pytest retention luck).


@pytest.fixture(scope="module")
def plan_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("key-batch-203a-plans")


# --- owned PostgreSQL 16 fixture (198/199/200/202 ownership discipline) ----


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
    owner = f"{_OWNER_PREFIX}-owner-{uuid.uuid4().hex}"
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
        yield url
    finally:
        if container is not None:
            _remove_owned(client, container, owner)


@pytest.fixture(scope="module")
def cli_env(owned_pg_url: str) -> str:
    """DATABASE_URL is ONLY the exact owned fictional database."""
    saved = {name: os.environ.get(name) for name in _ENV_VARS}
    os.environ["DATABASE_URL"] = owned_pg_url
    os.environ["APP_ENV"] = "test"
    os.environ["GATEWAY_KEY_PREFIX"] = "sk-slaif-"
    os.environ["GATEWAY_KEY_ACCEPTED_PREFIXES"] = "sk-slaif-"
    os.environ["ACTIVE_HMAC_KEY_VERSION"] = "1"
    os.environ["TOKEN_HMAC_SECRET_V1"] = TEST_HMAC_SECRET
    os.environ["ADMIN_SESSION_SECRET"] = TEST_ADMIN_SECRET
    os.environ["ONE_TIME_SECRET_ENCRYPTION_KEY"] = generate_secret_key()
    os.environ["ENABLE_EMAIL_DELIVERY"] = "false"
    os.environ.pop("SMTP_HOST", None)
    os.environ.pop("SMTP_PORT", None)
    os.environ.pop("SMTP_FROM", None)
    os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/15"
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


# --- helpers -----------------------------------------------------------------


def _session_factory(url: str):
    return async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)


def _run(coro):
    return asyncio.run(coro)


def _create_key_cli(
    url: str, owner_id: uuid.UUID, *, cohort_id: uuid.UUID | None, request_limit: int = 100
) -> uuid.UUID:
    """Create ONE key through the ACTUAL CLI entrypoint (real SQL)."""
    args = [
        "keys",
        "create",
        "--owner-id",
        str(owner_id),
        "--valid-from",
        "2026-06-01T00:00:00+00:00",
        "--valid-until",
        "2027-06-01T00:00:00+00:00",
        "--reason",
        "203a integration seed",
        "--allow-all-models",
        "--allow-all-endpoints",
        "--request-limit-total",
        str(request_limit),
        "--json",
        "--show-plaintext",
    ]
    if cohort_id is not None:
        args += ["--cohort-id", str(cohort_id)]
    result = _runner.invoke(app, args)
    # Failure channel is the CLI's fixed-shape safe JSON error (key
    # material is never echoed there); the plaintext key on the success
    # channel is parsed, never printed.
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    return uuid.UUID(payload["gateway_key_id"])


async def _insert_owner(url: str) -> uuid.UUID:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            owner = await OwnersRepository(session).create_owner(
                name="Batch",
                surname="Owner",
                email=f"batch-{uuid.uuid4().hex}@example.org",
            )
            return owner.id


async def _insert_cohort(url: str, name: str) -> uuid.UUID:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            cohort = Cohort(id=uuid.uuid4(), name=name, description="203a fixture")
            session.add(cohort)
            await session.flush()
            return cohort.id


async def _insert_admin(url: str) -> uuid.UUID:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            admin = AdminUser(
                id=uuid.uuid4(),
                email=f"admin-{uuid.uuid4().hex}@example.org",
                display_name="Batch Admin",
                password_hash="203a-synthetic-never-used-for-auth",
                role="admin",
            )
            session.add(admin)
            await session.flush()
            return admin.id


async def _insert_keys(
    url: str,
    count: int,
    *,
    cohort_id: uuid.UUID | None,
    owner_id: uuid.UUID,
    request_limit: int = 100,
    status: str = "active",
) -> list[uuid.UUID]:
    """Bulk fixture data (direct SQL seed, not a product mutation)."""
    factory = _session_factory(url)
    ids = [uuid.uuid4() for _ in range(count)]
    now = datetime.now(UTC)
    async with factory() as session:
        async with session.begin():
            for kid in ids:
                session.add(
                    GatewayKey(
                        id=kid,
                        public_key_id=f"pk203a-{kid.hex}",
                        token_hash=f"h{kid.hex}",
                        owner_id=owner_id,
                        cohort_id=cohort_id,
                        status=status,
                        valid_from=now - timedelta(days=1),
                        valid_until=now + timedelta(days=90),
                        request_limit_total=request_limit,
                    )
                )
            await session.flush()
    return ids


async def _key_states(url: str, key_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple]:
    factory = _session_factory(url)
    async with factory() as session:
        rows = (
            await session.execute(
                select(GatewayKey).where(GatewayKey.id.in_(key_ids))
            )
        ).scalars().all()
    return {
        r.id: (
            r.request_limit_total,
            r.cost_limit_eur,
            r.token_limit_total,
            r.status,
            r.token_hash,
            r.public_key_id,
            r.valid_from,
            r.valid_until,
            r.cost_used_eur,
            r.tokens_used_total,
            r.requests_used_total,
            r.cost_reserved_eur,
            r.tokens_reserved_total,
            r.requests_reserved_total,
            json.dumps(r.metadata_json, sort_keys=True),
        )
        for r in rows
    }


async def _config_audits(url: str, key_ids: list[uuid.UUID] | None = None) -> list[AuditLog]:
    factory = _session_factory(url)
    async with factory() as session:
        stmt = select(AuditLog).where(AuditLog.action == "update_key_configuration")
        if key_ids is not None:
            stmt = stmt.where(AuditLog.entity_id.in_(key_ids))
        stmt = stmt.order_by(AuditLog.created_at, AuditLog.id)
        rows = (await session.execute(stmt)).scalars().all()
        return list(rows)


def _plan_file(tmp_path, name: str, policy: dict) -> object:
    p = tmp_path / name
    p.write_text(json.dumps(policy))
    return p


def _plan_cli(policy_path, plan_path, selection_args) -> object:
    return _runner.invoke(
        app,
        [
            "keys", "batch", "plan", *selection_args,
            "--policy-file", str(policy_path),
            "--plan-file", str(plan_path), "--json",
        ],
    )


def _apply_cli(plan_path, reason, extra: tuple = ()) -> object:
    return _runner.invoke(
        app,
        [
            "keys", "batch", "apply", "--plan-file", str(plan_path),
            "--reason", reason, *extra, "--json",
        ],
    )


# --- seeding (once per module) ------------------------------------------------


def _seed_all(url: str) -> None:
    """Seed the module fixtures.

    The ACTUAL CLI entrypoint (Typer) runs its async command inside its
    OWN event loop, so every CLI phase executes OUTSIDE any running
    loop: short ``_run`` transactions alternate with synchronous CLI
    calls and no ``asyncio.run`` is ever nested in a running loop.
    """
    owner_id = _run(_insert_owner(url))
    admin_id = _run(_insert_admin(url))
    cohorts = {
        name: _run(_insert_cohort(url, f"203a-{name}-{uuid.uuid4().hex[:8]}"))
        for name in (
            "main", "unrelated", "tail", "overflow", "stale", "conc",
            "rollback", "usage", "money", "fenced", "edited", "sel",
        )
    }

    # The MANDATORY 37-key cohort through the ACTUAL CLI, plus one
    # suspended and one revoked control member.
    main_ids = [
        _create_key_cli(url, owner_id, cohort_id=cohorts["main"])
        for _ in range(37)
    ]
    suspended_id = _create_key_cli(url, owner_id, cohort_id=cohorts["main"])
    revoked_id = _create_key_cli(url, owner_id, cohort_id=cohorts["main"])
    for result in (
        _runner.invoke(app, ["keys", "suspend", str(suspended_id),
                             "--reason", "203a control", "--json"]),
        _runner.invoke(app, ["keys", "revoke", str(revoked_id),
                             "--reason", "203a control", "--json"]),
    ):
        assert result.exit_code == 0, result.output

    unrelated_ids = _run(_insert_keys(
        url, 101, cohort_id=cohorts["unrelated"], owner_id=owner_id
    ))
    tail_ids = _run(_insert_keys(
        url, 105, cohort_id=cohorts["tail"], owner_id=owner_id
    ))
    overflow_ids = _run(_insert_keys(
        url, 1001, cohort_id=cohorts["overflow"], owner_id=owner_id
    ))
    stale_ids = _run(_insert_keys(
        url, 3, cohort_id=cohorts["stale"], owner_id=owner_id
    ))
    conc_ids = _run(_insert_keys(
        url, 2, cohort_id=cohorts["conc"], owner_id=owner_id
    ))
    rollback_ids = _run(_insert_keys(
        url, 3, cohort_id=cohorts["rollback"], owner_id=owner_id
    ))
    usage_ids = _run(_insert_keys(
        url, 2, cohort_id=cohorts["usage"], owner_id=owner_id
    ))
    sel_ids = _run(_insert_keys(
        url, 2, cohort_id=cohorts["sel"], owner_id=owner_id
    ))
    sel_suspended = _run(_insert_keys(
        url, 1, cohort_id=cohorts["sel"], owner_id=owner_id, status="suspended"
    ))
    money_id = _create_key_cli(url, owner_id, cohort_id=cohorts["money"])
    fenced_id = _create_key_cli(url, owner_id, cohort_id=cohorts["fenced"])
    edited_id = _create_key_cli(url, owner_id, cohort_id=cohorts["edited"])

    _S.update(
        owner_id=owner_id,
        admin_id=admin_id,
        main_ids=main_ids,
        main_suspended_id=suspended_id,
        main_revoked_id=revoked_id,
        unrelated_ids=unrelated_ids,
        tail_ids=tail_ids,
        overflow_ids=overflow_ids,
        stale_ids=stale_ids,
        conc_ids=conc_ids,
        rollback_ids=rollback_ids,
        usage_ids=usage_ids,
        sel_ids=sel_ids,
        sel_suspended_id=sel_suspended[0],
        money_id=money_id,
        fenced_id=fenced_id,
        edited_id=edited_id,
        cohorts=cohorts,
    )


@pytest.fixture(scope="module", autouse=True)
def seeded(cli_env: str) -> dict[str, object]:
    _seed_all(cli_env)
    return _S


# --- A: the mandatory 37-key cohort (plan read-only, apply, repeat) ----------


def test_plan_37_key_cohort_is_read_only_exact_preview(plan_dir, cli_env: str):
    url = cli_env
    main_ids: list[uuid.UUID] = _S["main_ids"]
    cohorts: dict[str, uuid.UUID] = _S["cohorts"]
    suspended_id: uuid.UUID = _S["main_suspended_id"]
    revoked_id: uuid.UUID = _S["main_revoked_id"]

    all_main = main_ids + [suspended_id, revoked_id]
    before_states = _run(_key_states(url, list(all_main)))
    before_audits = len(_run(_config_audits(url)))

    policy_path = _plan_file(plan_dir, "policy37.json", POLICY_333)
    plan_path = plan_dir / "plan37.json"
    res = _plan_cli(policy_path, plan_path, ["--cohort-id", str(cohorts["main"])])
    assert res.exit_code == 0, (res.output, res.stderr)
    payload = json.loads(res.output)
    plan = payload["plan"]

    # EXACT eligible UUID set (37 active), never the suspended/revoked.
    assert plan["selected_count"] == 37
    assert sorted(plan["key_ids"]) == sorted(str(k) for k in main_ids)
    # Cohort selection contract: non-active members are simply not
    # selected, and excluded_by_status is EMPTY (the cohort preview does
    # not enumerate excluded rows); the suspended/revoked control members
    # are proven never selected above and untouched below.
    assert plan["excluded_by_status"] == []
    assert plan["changed_count"] == 37 and plan["unchanged_count"] == 0
    # Exact canonical per-key patch/diff for EVERY selected key.
    for entry in plan["keys"]:
        assert entry["before"]["request_limit_total"] == 100
        assert entry["after"]["request_limit_total"] == 333
        assert entry["changes"] == [
            {"field": "request_limit_total", "before": 100, "after": 333}
        ]

    # READ ONLY: zero writes, zero audits, zero material/state change.
    after_states = _run(_key_states(url, list(all_main)))
    assert after_states == before_states
    assert len(_run(_config_audits(url))) == before_audits
    # The written plan file is a strict, parseable artifact at 0600.
    assert plan_path.exists()
    assert stat.S_IMODE(os.stat(plan_path).st_mode) == 0o600
    parsed = parse_key_batch_plan_file(plan_path)
    assert parsed.selected_count == 37
    _S["plan37_path"] = plan_path


def test_apply_37_key_cohort_one_transaction_audits_preservation_repeat(tmp_path, cli_env: str):
    url = cli_env
    main_ids: list[uuid.UUID] = _S["main_ids"]
    cohorts: dict[str, uuid.UUID] = _S["cohorts"]
    admin_id: uuid.UUID = _S["admin_id"]
    unrelated_ids: list[uuid.UUID] = _S["unrelated_ids"]
    tail_ids: list[uuid.UUID] = _S["tail_ids"]

    suspended_id: uuid.UUID = _S["main_suspended_id"]
    revoked_id: uuid.UUID = _S["main_revoked_id"]
    all_main = main_ids + [suspended_id, revoked_id]
    # ONE exact scope for every preservation comparison: the 37 selected
    # keys plus the suspended/revoked control members, the unrelated
    # cohort, and the >100 tail cohort.
    controls_before = _run(_key_states(url, list(all_main)))
    unrelated_before = _run(_key_states(url, list(unrelated_ids)))
    tail_before = _run(_key_states(url, list(tail_ids)))

    reason = "203a 37-key reviewed batch"
    res = _apply_cli(
        _S["plan37_path"], reason, ("--actor-admin-id", str(admin_id))
    )
    assert res.exit_code == 0, (res.output, res.stderr)
    payload = json.loads(res.output)
    assert payload["status"] == "applied"
    assert payload["selected_count"] == 37 and payload["changed_count"] == 37

    # Persisted canonical configuration for every selected key.
    factory = _session_factory(url)

    async def _check():
        async with factory() as session:
            rows = (
                await session.execute(
                    select(GatewayKey).where(GatewayKey.id.in_(main_ids))
                )
            ).scalars().all()
            return {r.id: (r.request_limit_total, r.status, r.cost_limit_eur) for r in rows}

    states = _run(_check())
    for kid in main_ids:
        assert states[kid][0] == 333 and states[kid][1] == "active"

    # EXACT per-key audits: one per key, exact reason/actor, old/new values.
    audits = _run(_config_audits(url, list(main_ids)))
    assert len(audits) == 37
    audited = {a.entity_id for a in audits}
    assert audited == set(main_ids)
    for audit in audits:
        assert audit.note == reason
        assert audit.admin_user_id == admin_id
        assert audit.old_values["request_limit_total"] == 100
        assert audit.new_values["request_limit_total"] == 333

    # Preservation: revoked/suspended controls, unrelated cohort, tail
    # cohort, and every other cohort untouched; usage/reservation state
    # (fresh keys: all zeros) preserved.
    after_all = _run(_key_states(url, list(all_main + unrelated_ids + tail_ids)))
    for kid in unrelated_ids:
        assert after_all[kid] == unrelated_before[kid]
    for kid in tail_ids:
        assert after_all[kid] == tail_before[kid]
    for kid in main_ids:
        state = after_all[kid]
        assert (state[8], state[9], state[10], state[11], state[12], state[13]) == (
            Decimal("0"), 0, 0, Decimal("0"), 0, 0
        ), "usage/reservation counters must be untouched"
    suspended_state = after_all[suspended_id]
    revoked_state = after_all[revoked_id]
    assert suspended_state == controls_before[suspended_id]
    assert revoked_state == controls_before[revoked_id]
    assert suspended_state[3] == "suspended" and suspended_state[0] == 100
    assert revoked_state[3] == "revoked" and revoked_state[0] == 100

    # No all-key scope: the 1001-key overflow cohort is untouched.
    factory2 = _session_factory(url)

    async def _overflow_max():
        async with factory2() as session:
            return (
                await session.execute(
                    select(func.max(GatewayKey.request_limit_total)).where(
                        GatewayKey.cohort_id == cohorts["overflow"]
                    )
                )
            ).scalar_one()

    assert _run(_overflow_max()) == 100

    # Whole-set repeat: explicit no-write, no-new-audit state equality
    # over the SAME exact scope (the 37 selected keys).
    main_after_apply = _run(_key_states(url, list(main_ids)))
    before_repeat = len(_run(_config_audits(url, list(main_ids))))
    res = _apply_cli(_S["plan37_path"], "203a 37-key repeat")
    assert res.exit_code == 0, (res.output, res.stderr)
    payload = json.loads(res.output)
    assert payload["status"] == "already_at_target"
    assert payload["changed_count"] == 0 and payload["unchanged_count"] == 37
    assert len(_run(_config_audits(url, list(main_ids)))) == before_repeat
    assert _run(_key_states(url, list(main_ids))) == main_after_apply


# --- A: explicit selection semantics -----------------------------------------


def test_explicit_key_selection_mixed_statuses_duplicates_missing(tmp_path, cli_env: str):
    url = cli_env
    sel_ids: list[uuid.UUID] = _S["sel_ids"]
    sel_suspended: uuid.UUID = _S["sel_suspended_id"]
    before = _run(_key_states(url, list(sel_ids + [sel_suspended])))

    policy_path = _plan_file(tmp_path, "policy-sel.json", POLICY_333)
    plan_path = tmp_path / "plan-sel.json"
    res = _plan_cli(
        policy_path, plan_path,
        ["--key-id", str(sel_ids[0]), "--key-id", str(sel_ids[1]),
         "--key-id", str(sel_suspended)],
    )
    assert res.exit_code == 0, (res.output, res.stderr)
    plan = json.loads(res.output)["plan"]
    assert sorted(plan["key_ids"]) == sorted(str(k) for k in sel_ids)
    assert plan["excluded_by_status"] == [
        {"key_id": str(sel_suspended), "status": "suspended"}
    ]
    res = _apply_cli(plan_path, "203a explicit selection")
    assert res.exit_code == 0, (res.output, res.stderr)
    assert json.loads(res.output)["changed_count"] == 2
    after = _run(_key_states(url, list(sel_ids + [sel_suspended])))
    assert after[sel_ids[0]][0] == 333 and after[sel_ids[1]][0] == 333
    assert after[sel_suspended] == before[sel_suspended], "excluded key untouched"

    # Duplicate key IDs: refused before any effect.
    res = _plan_cli(
        policy_path, tmp_path / "plan-dup.json",
        ["--key-id", str(sel_ids[0]), "--key-id", str(sel_ids[0])],
    )
    assert res.exit_code == 1
    assert "duplicate" in json.loads(res.output)["error"]["message"].lower()
    assert not (tmp_path / "plan-dup.json").exists()

    # Missing key IDs: the WHOLE request fails; count only, no ID echo.
    missing = uuid.uuid4()
    res = _plan_cli(
        policy_path, tmp_path / "plan-missing.json",
        ["--key-id", str(sel_ids[0]), "--key-id", str(missing)],
    )
    assert res.exit_code == 1
    error = json.loads(res.output)["error"]
    assert error["code"] == "key_batch_key_not_found"
    assert str(missing) not in res.output
    assert not (tmp_path / "plan-missing.json").exists()

    # Separate status inclusion: the suspended member is selectable.
    res = _plan_cli(
        policy_path, tmp_path / "plan-sus.json",
        ["--key-id", str(sel_suspended), "--status", "suspended"],
    )
    assert res.exit_code == 0, (res.output, res.stderr)
    plan = json.loads(res.output)["plan"]
    assert plan["key_ids"] == [str(sel_suspended)]
    assert plan["excluded_by_status"] == []
    # Refusals never wrote.
    final = _run(_key_states(url, list(sel_ids + [sel_suspended])))
    assert final == after


# --- A: >100 eligible (no truncation) and cap+1 overflow ---------------------


def test_cohort_over_100_eligible_is_not_truncated(tmp_path, cli_env: str):
    tail_ids: list[uuid.UUID] = _S["tail_ids"]
    cohorts: dict[str, uuid.UUID] = _S["cohorts"]
    policy_path = _plan_file(tmp_path, "policy-tail.json", POLICY_333)
    res = _plan_cli(
        policy_path, tmp_path / "plan-tail.json", ["--cohort-id", str(cohorts["tail"])]
    )
    assert res.exit_code == 0, (res.output, res.stderr)
    plan = json.loads(res.output)["plan"]
    # ALL 105 eligible keys selected - the legacy first-100 tail cannot be
    # silently dropped by a page-bounded selection.
    assert plan["selected_count"] == 105
    assert set(plan["key_ids"]) == {str(k) for k in tail_ids}


def test_cohort_overflow_beyond_cap_refused_before_artifact(tmp_path, cli_env: str):
    url = cli_env
    cohorts: dict[str, uuid.UUID] = _S["cohorts"]
    overflow_ids: list[uuid.UUID] = _S["overflow_ids"]
    before = _run(_key_states(url, list(overflow_ids[:5])))
    before_audits = len(_run(_config_audits(url)))
    policy_path = _plan_file(tmp_path, "policy-ovf.json", POLICY_333)
    plan_path = tmp_path / "plan-ovf.json"
    res = _plan_cli(policy_path, plan_path, ["--cohort-id", str(cohorts["overflow"])])
    assert res.exit_code == 1, res.output
    error = json.loads(res.output)["error"]
    assert error["code"] == "key_batch_selection_overflow"
    # Refused BEFORE any artifact, write, or audit.
    assert not plan_path.exists()
    assert _run(_key_states(url, list(overflow_ids[:5]))) == before
    assert len(_run(_config_audits(url))) == before_audits


# --- C: stale membership / drift refusals (zero writes) -----------------------


def test_stale_membership_and_drift_refusals_zero_writes(tmp_path, cli_env: str):
    url = cli_env
    stale_ids: list[uuid.UUID] = _S["stale_ids"]
    cohorts: dict[str, uuid.UUID] = _S["cohorts"]
    owner_id: uuid.UUID = _S["owner_id"]
    policy_path = _plan_file(tmp_path, "policy-stale.json", POLICY_333)
    st1, st2, st3 = stale_ids

    # Fresh engine per caller transaction: an asyncpg pool connection is
    # bound to the loop that created it, and each _run() is a NEW loop.
    async def _drift_setup(kind: str, extra_id: uuid.UUID | None = None):
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                if kind == "add":
                    assert extra_id is not None
                    session.add(
                        GatewayKey(
                            id=extra_id,
                            public_key_id=f"pk203a-{extra_id.hex}",
                            token_hash=f"h{extra_id.hex}",
                            owner_id=owner_id,
                            cohort_id=cohorts["stale"],
                            status="active",
                            valid_from=datetime.now(UTC) - timedelta(days=1),
                            valid_until=datetime.now(UTC) + timedelta(days=90),
                            request_limit_total=100,
                        )
                    )
                elif kind == "remove":
                    await session.execute(
                        text(
                            "UPDATE gateway_keys SET cohort_id = NULL "
                            "WHERE id = :k"
                        ),
                        {"k": st3},
                    )
                elif kind == "config":
                    await session.execute(
                        text(
                            "UPDATE gateway_keys SET request_limit_total = 555 "
                            "WHERE id = :k"
                        ),
                        {"k": st2},
                    )
                elif kind == "status":
                    await session.execute(
                        text(
                            "UPDATE gateway_keys SET status = 'suspended' "
                            "WHERE id = :k"
                        ),
                        {"k": st1},
                    )
                await session.flush()

    async def _drift_reset(kind: str, extra_id: uuid.UUID | None = None):
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                if kind == "add":
                    await session.execute(
                        text("DELETE FROM gateway_keys WHERE id = :k"), {"k": extra_id}
                    )
                elif kind == "remove":
                    await session.execute(
                        text(
                            "UPDATE gateway_keys SET cohort_id = :c WHERE id = :k"
                        ),
                        {"c": cohorts["stale"], "k": st3},
                    )
                elif kind == "config":
                    await session.execute(
                        text(
                            "UPDATE gateway_keys SET request_limit_total = 100 "
                            "WHERE id = :k"
                        ),
                        {"k": st2},
                    )
                elif kind == "status":
                    await session.execute(
                        text(
                            "UPDATE gateway_keys SET status = 'active' WHERE id = :k"
                        ),
                        {"k": st1},
                    )
                await session.flush()

    baseline = _run(_key_states(url, list(stale_ids)))
    for index, kind in enumerate(("add", "remove", "config", "status")):
        extra_id = uuid.uuid4() if kind == "add" else None
        res = _plan_cli(
            policy_path, tmp_path / f"plan-stale-{index}.json",
            ["--cohort-id", str(cohorts["stale"])],
        )
        assert res.exit_code == 0, (res.output, res.stderr)
        if kind == "add":
            # The newcomer joins AFTER the review (committed now).
            _run(_drift_setup(kind, extra_id))
        else:
            _run(_drift_setup(kind))
        res = _apply_cli(tmp_path / f"plan-stale-{index}.json", f"203a stale {kind}")
        assert res.exit_code == 1, (res.output, res.stderr)
        error = json.loads(res.output)["error"]
        assert error["code"] == "key_batch_stale", (kind, error)
        # ZERO writes (no key moved to the target) and ZERO audits.
        mid_states = _run(_key_states(url, list(stale_ids)))
        for kid in stale_ids:
            assert mid_states[kid][0] != 333, f"refusal {kind} must never write"
        assert len(_run(_config_audits(url, list(stale_ids)))) == 0
        _run(_drift_reset(kind, extra_id))
    assert len(_run(_config_audits(url, list(stale_ids)))) == 0
    final = _run(_key_states(url, list(stale_ids)))
    for kid in stale_ids:
        assert final[kid][0] == 100, "refusals must never write"
        assert final[kid] == baseline[kid]


# --- C: controlled real-PG lock wait (competitor cohort join) -----------------


def test_controlled_pg_lock_wait_cohort_join_refused(cli_env: str):
    url = cli_env
    conc_ids: list[uuid.UUID] = _S["conc_ids"]
    cohorts: dict[str, uuid.UUID] = _S["cohorts"]
    owner_id: uuid.UUID = _S["owner_id"]
    k1, k2 = sorted(conc_ids)
    new_member = uuid.uuid4()
    observed = {"wait_seen": False}

    factory = _session_factory(url)

    async def _observer(holder_pid: int, waiter_pid: int) -> None:
        # Fresh autocommit observer: the holder's own cached snapshot CANNOT
        # see waiters, so clear the statistics snapshot before each poll.
        async with factory() as session:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                await session.execute(text("SELECT pg_stat_clear_snapshot()"))
                row = (
                    await session.execute(
                        text(
                            "SELECT 1 FROM pg_stat_activity "
                            "WHERE pid = :waiter "
                            "AND wait_event_type = 'Lock' "
                            "AND :holder = ANY(pg_blocking_pids(pid))"
                        ),
                        {"waiter": waiter_pid, "holder": holder_pid},
                    )
                ).first()
                if row is not None:
                    observed["wait_seen"] = True
                    return
                await asyncio.sleep(0.2)

    async def _scenario():
        # Plan BEFORE the competitor exists: exactly k1, k2.
        plan = None
        settings = get_settings()

        async def _make_plan():
            async with factory() as session:
                async with session.begin():
                    keys_repo = GatewayKeysRepository(session)
                    key_service = KeyService(
                        settings=settings,
                        gateway_keys_repository=keys_repo,
                        one_time_secrets_repository=OneTimeSecretsRepository(session),
                        audit_repository=AuditRepository(session),
                    )
                    batch_service = KeyBatchService(
                        gateway_keys_repository=keys_repo,
                        cohorts_repository=CohortsRepository(session),
                        key_service=key_service,
                    )
                    from slaif_gateway.schemas.key_configuration import (
                        parse_key_configuration,
                    )

                    return await batch_service.plan(
                        cohort_id=cohorts["conc"],
                        key_ids=(),
                        statuses=["active"],
                        policy=parse_key_configuration(POLICY_333),
                    )

        plan = await _make_plan()
        assert [uuid.UUID(k) for k in plan.key_ids] == [k1, k2]

        # Competitor session B: lock the LATER selected key (k2), then (after
        # the observer proves A is blocked on B) commit a NEW eligible cohort
        # member in the SAME transaction.
        b_pid: list[int] = []
        b_release = asyncio.Event()

        async def _competitor():
            async with factory() as session:
                async with session.begin():
                    await session.execute(
                        text("SELECT id FROM gateway_keys WHERE id = :k FOR UPDATE"),
                        {"k": k2},
                    )
                    b_pid.append(
                        (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                    )
                    session.add(
                        GatewayKey(
                            id=new_member,
                            public_key_id=f"pk203a-{new_member.hex}",
                            token_hash=f"h{new_member.hex}",
                            owner_id=owner_id,
                            cohort_id=cohorts["conc"],
                            status="active",
                            valid_from=datetime.now(UTC) - timedelta(days=1),
                            valid_until=datetime.now(UTC) + timedelta(days=90),
                            request_limit_total=100,
                        )
                    )
                    await session.flush()
                    await b_release.wait()
            # COMMIT on exit: releases the k2 row lock AND makes the new
            # member visible to the applier's post-last-lock re-resolution.

        # Applier session A: the shared service under a caller-owned
        # transaction; it locks k1, then blocks on B's held k2 lock.
        a_pid: list[int] = []
        outcome: list[str] = []

        async def _applier():
            async with factory() as session:
                async with session.begin():
                    keys_repo = GatewayKeysRepository(session)
                    key_service = KeyService(
                        settings=settings,
                        gateway_keys_repository=keys_repo,
                        one_time_secrets_repository=OneTimeSecretsRepository(session),
                        audit_repository=AuditRepository(session),
                    )
                    batch_service = KeyBatchService(
                        gateway_keys_repository=keys_repo,
                        cohorts_repository=CohortsRepository(session),
                        key_service=key_service,
                    )
                    a_pid.append(
                        (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                    )
                    try:
                        result = await batch_service.apply(
                            plan=plan, reason="203a concurrency"
                        )
                        outcome.append(result.status)
                    except KeyBatchStaleError:
                        outcome.append("stale")
            # ROLLBACK on exit (nothing was written, but the law is honored).

        competitor_task = asyncio.create_task(_competitor())

        # Competitor readiness barrier: the competitor must DEMONSTRABLY
        # OWN the later selected-key (k2) lock (its FOR UPDATE is flushed
        # and its pid recorded) BEFORE the applier is even started, so the
        # causal holder/waiter relation cannot be inverted.
        deadline = time.monotonic() + 60
        while not b_pid and time.monotonic() < deadline:
            assert not competitor_task.done(), "competitor failed to acquire k2"
            await asyncio.sleep(0.05)
        assert b_pid, "competitor did not acquire the k2 lock"

        applier_task = asyncio.create_task(_applier())
        deadline = time.monotonic() + 60
        while not a_pid and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        assert a_pid, "applier did not start"

        observer_task = asyncio.create_task(_observer(b_pid[0], a_pid[0]))
        # Let the observer confirm the CAUSAL wait, then release the lock.
        while not observed["wait_seen"]:
            assert not observer_task.done(), "observer gave up before seeing the wait"
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.2)
        b_release.set()
        await applier_task
        await competitor_task
        # JOIN the observer (it returns right after recording the wait)
        # instead of cancelling a live watcher.
        await observer_task
        return outcome[0]

    assert _run(_scenario()) == "stale"
    assert observed["wait_seen"], "the causal lock wait was never observed"
    # The refusal is total: both selected keys untouched, zero audits; the
    # competitor's own committed member is the only change (its own write).
    states = _run(_key_states(url, [k1, k2]))
    assert states[k1][0] == 100 and states[k2][0] == 100
    assert len(_run(_config_audits(url, [k1, k2]))) == 0
    factory2 = _session_factory(url)

    async def _member_visible():
        async with factory2() as session:
            return (
                await session.execute(
                    text(
                        "SELECT 1 FROM gateway_keys WHERE id = :k AND cohort_id = :c"
                    ),
                    {"k": new_member, "c": cohorts["conc"]},
                )
            ).first() is not None

    assert _run(_member_visible())


# --- D: late audit failure rolls back ALL ------------------------------------


class _BoomAuditRepository(AuditRepository):
    """Controlled fault injection: raises on the Nth audit write only."""

    def __init__(self, session, *, boom_at: int) -> None:
        super().__init__(session)
        self.boom_at = boom_at
        self.calls = 0

    async def add_audit_log(self, **kwargs) -> None:  # type: ignore[override]
        self.calls += 1
        if self.calls == self.boom_at:
            raise RuntimeError("injected late audit failure (203a test)")
        return await super().add_audit_log(**kwargs)


def test_late_audit_failure_rolls_back_all_keys_and_audits(cli_env: str):
    url = cli_env
    rollback_ids: list[uuid.UUID] = _S["rollback_ids"]
    cohorts: dict[str, uuid.UUID] = _S["cohorts"]
    settings = get_settings()
    factory = _session_factory(url)

    captured: dict[str, object] = {}

    async def _scenario():
        from slaif_gateway.schemas.key_configuration import parse_key_configuration

        async with factory() as session:
            async with session.begin():
                keys_repo = GatewayKeysRepository(session)
                boom_repo = _BoomAuditRepository(session, boom_at=3)
                captured["boom_repo"] = boom_repo
                key_service = KeyService(
                    settings=settings,
                    gateway_keys_repository=keys_repo,
                    one_time_secrets_repository=OneTimeSecretsRepository(session),
                    audit_repository=boom_repo,
                )
                batch_service = KeyBatchService(
                    gateway_keys_repository=keys_repo,
                    cohorts_repository=CohortsRepository(session),
                    key_service=key_service,
                )
                plan = await batch_service.plan(
                    cohort_id=cohorts["rollback"],
                    key_ids=(),
                    statuses=["active"],
                    policy=parse_key_configuration(POLICY_333),
                )
                assert len(plan.key_ids) == 3
                # The injected LATE audit failure must CROSS the caller
                # transaction context (propagated, never swallowed inside
                # it) so the begin-context exit ROLLS BACK every key write
                # and every provisional audit (flushed, never committed).
                await batch_service.apply(plan=plan, reason="203a rollback")

    raised: RuntimeError | None = None
    try:
        _run(_scenario())
    except RuntimeError as exc:
        raised = exc
    assert raised is not None and "injected late audit failure" in str(raised), (
        "the controlled late audit failure must propagate out of the "
        "caller transaction (no partial success is allowed)"
    )
    boom_repo = captured["boom_repo"]
    # The failure was LATE: two keys were fully written+audited inside
    # the transaction before the third key's audit raised.
    assert boom_repo.calls == 3

    # Fresh sessions: the transaction ROLLBACK undid ALL key writes and
    # ALL provisional audits (no partial commit).
    states = _run(_key_states(url, list(rollback_ids)))
    for kid in rollback_ids:
        assert states[kid][0] == 100, "no partial commit is allowed"
    assert len(_run(_config_audits(url, list(rollback_ids)))) == 0, (
        "provisional (flushed) audits must roll back with the transaction"
    )


# --- D: usage-only movement never stales --------------------------------------


def test_usage_only_movement_does_not_stale_repeat(cli_env: str):
    url = cli_env
    usage_ids: list[uuid.UUID] = _S["usage_ids"]
    cohorts: dict[str, uuid.UUID] = _S["cohorts"]
    settings = get_settings()

    async def _make_batch_service(session):
        keys_repo = GatewayKeysRepository(session)
        key_service = KeyService(
            settings=settings,
            gateway_keys_repository=keys_repo,
            one_time_secrets_repository=OneTimeSecretsRepository(session),
            audit_repository=AuditRepository(session),
        )
        return KeyBatchService(
            gateway_keys_repository=keys_repo,
            cohorts_repository=CohortsRepository(session),
            key_service=key_service,
        )

    async def _preview():
        from slaif_gateway.schemas.key_configuration import parse_key_configuration

        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                batch_service = await _make_batch_service(session)
                return await batch_service.plan(
                    cohort_id=cohorts["usage"],
                    key_ids=(),
                    statuses=["active"],
                    policy=parse_key_configuration(POLICY_333),
                )

    plan = _run(_preview())

    # Synthetic fixture injection (order D): committed usage-only counter
    # movement BETWEEN the preview and the FIRST configuration write,
    # standing in for a concurrent request flow the batch must neither
    # stale on nor disturb.
    async def _move_usage(cost: str, tokens: int, requests: int):
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                for kid in usage_ids:
                    await session.execute(
                        text(
                            "UPDATE gateway_keys SET cost_used_eur = :c, "
                            "tokens_used_total = :t, requests_used_total = :r "
                            "WHERE id = :k"
                        ),
                        {"k": kid, "c": cost, "t": tokens, "r": requests},
                    )
                await session.flush()

    _run(_move_usage("1.250000000", 11, 7))

    async def _first_apply():
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                batch_service = await _make_batch_service(session)
                return await batch_service.apply(
                    plan=plan, reason="203a usage first"
                )

    first = _run(_first_apply())
    assert first.status == "applied"
    # The PRE-first-write movement is preserved by the actual write.
    async def _usage():
        factory1 = _session_factory(url)
        async with factory1() as session:
            rows = (
                await session.execute(
                    select(GatewayKey).where(GatewayKey.id.in_(usage_ids))
                )
            ).scalars().all()
            return {
                r.id: (
                    r.cost_used_eur,
                    r.tokens_used_total,
                    r.requests_used_total,
                    r.request_limit_total,
                )
                for r in rows
            }

    usage_after_first = _run(_usage())
    for kid in usage_ids:
        assert usage_after_first[kid] == (Decimal("1.250000000"), 11, 7, 333)
    audits_after_first = len(_run(_config_audits(url, list(usage_ids))))
    assert audits_after_first == len(usage_ids)

    # A second synthetic movement between the first write and the repeat.
    _run(_move_usage("2.500000000", 22, 14))

    async def _repeat():
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                batch_service = await _make_batch_service(session)
                return await batch_service.apply(
                    plan=plan, reason="203a usage repeat"
                )

    repeat = _run(_repeat())
    assert repeat.status == "already_at_target"
    # No NEW audits; usage counters preserved exactly; target applied.
    assert len(_run(_config_audits(url, list(usage_ids)))) == audits_after_first
    usage = _run(_usage())
    for kid in usage_ids:
        assert usage[kid] == (Decimal("2.500000000"), 22, 14, 333)


# --- item 5/7: real-PG money target normalization + first/repeat --------------


def test_money_integer_target_pg_apply_repeat(tmp_path, cli_env: str):
    url = cli_env
    money_id: uuid.UUID = _S["money_id"]

    policy_path = _plan_file(tmp_path, "policy-money.json", {"schema_version": 1, "cost_limit_eur": 2})
    plan_path = tmp_path / "plan-money.json"
    res = _plan_cli(policy_path, plan_path, ["--key-id", str(money_id)])
    assert res.exit_code == 0, (res.output, res.stderr)
    plan = json.loads(res.output)["plan"]
    # The projected target renders the EXACT Numeric(18,9) representation.
    assert plan["keys"][0]["after"]["cost_limit_eur"] == "2.000000000"

    res = _apply_cli(plan_path, "203a money batch")
    assert res.exit_code == 0, (res.output, res.stderr)
    assert json.loads(res.output)["status"] == "applied"

    factory = _session_factory(url)

    async def _stored():
        async with factory() as session:
            value = (
                await session.execute(
                    text("SELECT cost_limit_eur, cost_limit_eur::text FROM gateway_keys WHERE id = :k"),
                    {"k": money_id},
                )
            ).one()
            return value[0], value[1]

    stored, stored_text = _run(_stored())
    assert stored == Decimal("2.000000000")
    assert stored_text == "2.000000000"

    # Repeat on the SAME saved plan: explicit already-at-target, no writes.
    before = len(_run(_config_audits(url, [money_id])))
    res = _apply_cli(plan_path, "203a money repeat")
    assert res.exit_code == 0, (res.output, res.stderr)
    assert json.loads(res.output)["status"] == "already_at_target"
    assert len(_run(_config_audits(url, [money_id]))) == before

    # Ten decimals cannot be honestly projected: refused at plan time, no
    # artifact, no writes.
    bad_policy = _plan_file(tmp_path, "policy-money-bad.json", {"schema_version": 1, "cost_limit_eur": "1.1234567891"})
    res = _plan_cli(bad_policy, tmp_path / "plan-money-bad.json", ["--key-id", str(money_id)])
    assert res.exit_code == 1
    error = json.loads(res.output)["error"]
    assert "9-decimal" in error["message"]
    assert not (tmp_path / "plan-money-bad.json").exists()


# --- item 8: fenced target requires the FRESH apply confirmation --------------


def test_fenced_target_requires_fresh_confirmation_cli(tmp_path, cli_env: str):
    url = cli_env
    fenced_id: uuid.UUID = _S["fenced_id"]
    policy_path = _plan_file(tmp_path, "policy-fenced.json", FENCED_POLICY)
    plan_path = tmp_path / "plan-fenced.json"
    res = _plan_cli(policy_path, plan_path, ["--key-id", str(fenced_id)])
    assert res.exit_code == 0, (res.output, res.stderr)
    plan = json.loads(res.output)["plan"]
    # The preview input is recorded INFORMATIONALLY in the saved plan.
    assert plan["policy"]["confirm_external_tool_fenced"] is True
    assert plan["keys"][0]["after"]["external_tool_policy"]["mode"] == "external_tool_fenced"

    async def _metadata():
        factory = _session_factory(url)
        async with factory() as session:
            row = await session.get(GatewayKey, fenced_id)
            return dict(row.metadata_json or {})

    # SAVED true + NO fresh flag: refused BEFORE any write/audit.
    res = _apply_cli(plan_path, "203a fenced without fresh flag")
    assert res.exit_code == 1, (res.output, res.stderr)
    error = json.loads(res.output)["error"]
    assert error["code"] == "invalid_gateway_key_policy"
    assert "confirm" in error["message"].lower()
    assert len(_run(_config_audits(url, [fenced_id]))) == 0
    assert "external_tool_policy" not in _run(_metadata()), "no write before refusal"

    # FRESH explicit flag + reason: applies with ONE per-key audit.
    res = _apply_cli(plan_path, "203a fenced with fresh flag", ("--confirm-external-tool-fenced",))
    assert res.exit_code == 0, (res.output, res.stderr)
    assert json.loads(res.output)["status"] == "applied"
    audits = _run(_config_audits(url, [fenced_id]))
    assert len(audits) == 1
    assert _run(_metadata())["external_tool_policy"]["mode"] == "external_tool_fenced"

    # Repeated decisions retain the CURRENT guard: no fresh flag -> refuse;
    # fresh flag -> explicit already-at-target with zero new audits.
    res = _apply_cli(plan_path, "203a fenced repeat without flag")
    assert res.exit_code == 1, (res.output, res.stderr)
    assert len(_run(_config_audits(url, [fenced_id]))) == 1
    res = _apply_cli(plan_path, "203a fenced repeat with flag", ("--confirm-external-tool-fenced",))
    assert res.exit_code == 0, (res.output, res.stderr)
    assert json.loads(res.output)["status"] == "already_at_target"
    assert len(_run(_config_audits(url, [fenced_id]))) == 1


# --- item 9: edited-plan fingerprint coherence (real flow) --------------------


def test_edited_plan_fingerprints_refused_pg(tmp_path, cli_env: str):
    url = cli_env
    edited_id: uuid.UUID = _S["edited_id"]
    policy_path = _plan_file(tmp_path, "policy-edited.json", POLICY_2000)
    plan_path = tmp_path / "plan-edited.json"
    res = _plan_cli(policy_path, plan_path, ["--key-id", str(edited_id)])
    assert res.exit_code == 0, (res.output, res.stderr)

    document = json.loads(plan_path.read_text())
    for key in document["keys"]:
        key["before"]["request_limit_total"] = 777
        for change in key["changes"]:
            if change["field"] == "request_limit_total":
                change["before"] = 777
    edited_path = tmp_path / "plan-edited-bad.json"
    edited_path.write_text(json.dumps(document, sort_keys=True))

    # (a) first apply with the edited advertised before: refused, no writes.
    res = _apply_cli(edited_path, "203a edited before first")
    assert res.exit_code == 1, (res.output, res.stderr)
    assert json.loads(res.output)["error"]["code"] == "key_batch_stale"
    assert _run(_key_states(url, [edited_id]))[edited_id][0] == 100

    # Control: the unedited plan applies.
    res = _apply_cli(plan_path, "203a edited control")
    assert res.exit_code == 0, (res.output, res.stderr)
    assert json.loads(res.output)["status"] == "applied"
    assert _run(_key_states(url, [edited_id]))[edited_id][0] == 2000

    # (b) the SAME edited before on the repeat: refused, state preserved.
    res = _apply_cli(edited_path, "203a edited before repeat")
    assert res.exit_code == 1, (res.output, res.stderr)
    assert json.loads(res.output)["error"]["code"] == "key_batch_stale"
    assert _run(_key_states(url, [edited_id]))[edited_id][0] == 2000

    # (c) coherently edited policy+after+diff with the STALE post digest
    # (recorded against the reviewed 2000 target): refused in this
    # applied-2000 state, the 9000 target is NEVER written. The
    # FIRST-apply variant of the same coherent edit is the durable unit
    # regression
    # test_apply_coherent_edit_stale_post_fingerprint_refused_on_first.
    document9k = json.loads(plan_path.read_text())
    for key in document9k["keys"]:
        key["after"]["request_limit_total"] = 9000
        for change in key["changes"]:
            if change["field"] == "request_limit_total":
                change["after"] = 9000
    document9k["policy"]["request_limit_total"] = 9000
    edited9k_path = tmp_path / "plan-edited-9k.json"
    edited9k_path.write_text(json.dumps(document9k, sort_keys=True))
    res = _apply_cli(edited9k_path, "203a coherent 9k edit")
    assert res.exit_code == 1, (res.output, res.stderr)
    assert json.loads(res.output)["error"]["code"] == "key_batch_stale"
    assert _run(_key_states(url, [edited_id]))[edited_id][0] == 2000
    assert len(_run(_config_audits(url, [edited_id]))) == 1


# --- B/E: CLI canaries never echoed (real flow) --------------------------------


def test_cli_canaries_no_echo_policy_path_reason(tmp_path, cli_env: str):
    url = cli_env
    edited_id: uuid.UUID = _S["edited_id"]
    main_ids: list[uuid.UUID] = _S["main_ids"]
    owner_id: uuid.UUID = _S["owner_id"]
    main_audits_before = len(_run(_config_audits(url, list(main_ids))))

    # (1) credential shape in the POLICY FILE content: refused at the writer
    # boundary, never echoed, no artifact.
    canary_policy = _plan_file(
        tmp_path, "policy-canary.json",
        {"schema_version": 1, "allowed_models": [CANARY]},
    )
    res = _plan_cli(canary_policy, tmp_path / "plan-canary.json", ["--key-id", str(edited_id)])
    assert res.exit_code == 1, (res.output, res.stderr)
    assert CANARY not in res.output and CANARY not in res.stderr
    assert not (tmp_path / "plan-canary.json").exists()

    # (2) credential shape in the PLAN ARTIFACT PATHNAME: refused before any
    # write or output, never echoed in either mode.
    normal_policy = _plan_file(tmp_path, "policy-normal.json", POLICY_2000)
    for extra in ([], ["--json"]):
        res = _runner.invoke(
            app,
            [
                "keys", "batch", "plan", "--key-id", str(edited_id),
                "--policy-file", str(normal_policy),
                "--plan-file", str(tmp_path / f"{PATH_CANARY}.json"),
                *extra,
            ],
        )
        assert res.exit_code == 1, (res.output, res.stderr)
        assert PATH_CANARY not in res.output and PATH_CANARY not in res.stderr
        if extra:
            assert json.loads(res.output)["error"]["code"] == "invalid_parameter"
        assert not (tmp_path / f"{PATH_CANARY}.json").exists()

    # (3) credential shape in the AUDIT REASON: refused before any effect,
    # never echoed, no writes, no audits.
    res = _apply_cli(_S["plan37_path"], f"rotate {CANARY} now")
    assert res.exit_code == 1, (res.output, res.stderr)
    assert CANARY not in res.output and CANARY not in res.stderr
    assert json.loads(res.output)["error"]["code"] == "key_batch_reason"

    # (4) credential shape in a SELECTED key's RETAINED current
    # configuration: shared route/model validation would otherwise
    # reflect the configured value into its error; the new shared batch
    # boundary refuses it BEFORE projection, with a fixed safe error,
    # no artifact, and no writes.
    stored_canary_id = uuid.uuid4()

    async def _seed_stored_canary():
        factory = _session_factory(url)
        async with factory() as session:
            async with session.begin():
                session.add(
                    GatewayKey(
                        id=stored_canary_id,
                        public_key_id=f"pk203a-{stored_canary_id.hex}",
                        token_hash=f"h{stored_canary_id.hex}",
                        owner_id=owner_id,
                        status="active",
                        valid_from=datetime.now(UTC) - timedelta(days=1),
                        valid_until=datetime.now(UTC) + timedelta(days=90),
                        request_limit_total=100,
                        allow_all_models=False,
                        allowed_models=[CANARY],
                    )
                )
                await session.flush()

    _run(_seed_stored_canary())
    stored_policy = _plan_file(tmp_path, "policy-stored.json", POLICY_2000)
    res = _plan_cli(
        stored_policy, tmp_path / "plan-stored.json", ["--key-id", str(stored_canary_id)]
    )
    assert res.exit_code == 1, (res.output, res.stderr)
    assert CANARY not in res.output and CANARY not in res.stderr
    assert json.loads(res.output)["error"]["code"] == "key_batch_policy"
    assert not (tmp_path / "plan-stored.json").exists()
    # The retained canary row is untouched (no configuration write).
    factory_sc = _session_factory(url)

    async def _stored_unchanged():
        async with factory_sc() as session:
            return (
                await session.execute(
                    select(GatewayKey).where(GatewayKey.id == stored_canary_id)
                )
            ).scalar_one()

    stored_row = _run(_stored_unchanged())
    assert stored_row.request_limit_total == 100
    assert stored_row.allowed_models == [CANARY]

    # The 37-key cohort remains exactly at the applied state and the
    # refused reason/canaries added no audits.
    factory = _session_factory(url)

    async def _all_333():
        async with factory() as session:
            return (
                await session.execute(
                    text(
                        "SELECT count(*) FROM gateway_keys "
                        "WHERE request_limit_total = 333 AND cohort_id = :c"
                    ),
                    {"c": _S["cohorts"]["main"]},
                )
            ).scalar_one()

    assert _run(_all_333()) == 37
    assert len(_run(_config_audits(url, list(main_ids)))) == main_audits_before

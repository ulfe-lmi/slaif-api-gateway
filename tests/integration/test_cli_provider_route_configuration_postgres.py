"""Real owned-PostgreSQL evidence for objective 199-a provider/route CLI.

Proves the two fictional module providers (distinct origins/env-name
references/profiles/timeouts, 0 retries) prepared DISABLED through the real
CLI and explicitly enabled afterwards; provider partial updates preserving
omitted fields (including zero retries) with one audit and a row lock;
routes add with a strict capabilities file (disabled preparation default);
the reviewed two-step route plan (dry-run renders, execute applies exactly
once, repeated apply is refused stale, competing changes invalidate the
plan); nested media/headroom preservation vs explicit full replacement;
wrong profile/kind/upstream/selector refusal; file canaries and oversize
refusals; no dry-run writes or audits; a forced LATE audit failure with the
updated row visible first in the SAME transaction and full rollback proof;
and real competing-update serialization with the preserve-omitted law.
199-c continues the SAME module: the explicit clear-note oracle restored
(real old -> null in one audited operation, late-audit rollback of clear
plus sibling), creation-surface known-shape refusals, and complete pure
module/transport parity (unknown module refused, implicit legacy binding
accepted, unsupported streaming refused) against real owned PostgreSQL.

No provider HTTP, no Redis, no real upstream contact, no real SMTP.
Ownership discipline mirrors the 198 owned fixture: unique owner label,
loopback-bound, tmpfs-backed PostgreSQL 16, identity inspected BEFORE
readiness/migration, cleanup removes ONLY the exact created container ID.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import stat
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.config import get_settings
from slaif_gateway.db.models import (
    AuditLog,
    CodexReplayReference,
    ModelRoute,
    ProviderConfig,
    UsageLedger,
)
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.schemas.provider_route_configuration import (
    parse_route_update_plan_file,
)
from slaif_gateway.services.provider_route_configuration import (
    execute_route_update_plan,
    partial_update_provider_config,
    preview_route_update_for_route,
    ProviderRouteStaleError,
)
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif199a"

_STATE: dict[str, Any] = {}

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

TEST_HMAC_SECRET = "test-hmac-secret-for-cli-provider-route-12345"
TEST_ADMIN_SECRET = "test-admin-secret-for-cli-provider-route-12345"

RUNNER = CliRunner()


def _cli(*args: str) -> Any:
    return RUNNER.invoke(app, list(args))


# 199-b R5: renderer-stable terminal env (set in cli_env) +
# ANSI/whitespace-independent assertion helper (project pattern).
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_TERM_VARS = ("COLUMNS", "NO_COLOR")


def _plain(text: str) -> str:
    return " ".join(_ANSI_RE.sub("", text).split())


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
    saved_term = {name: os.environ.get(name) for name in _TERM_VARS}
    os.environ["COLUMNS"] = "220"
    os.environ["NO_COLOR"] = "1"
    try:
        yield owned_pg_url
    finally:
        for name, value in saved_term.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()


def _session_factory(url: str):
    return async_sessionmaker(create_async_engine(url, future=True), expire_on_commit=False)


# --- module setup: two fictional module providers + routes + references -------


ZAP_CAPS = {
    "schema_version": 1,
    "capabilities": {
        "chat_completions": {
            "chat_text": True,
            "chat_streaming": False,
            "chat_function_tools": True,
        },
        "codex_limits": {
            "context_window_tokens": 1050000,
            "default_max_output_tokens": 32768,
            "max_output_tokens": 128000,
        },
        "media_input_estimation": {
            "version": 1,
            "image_tokens": 1024,
            "video_tokens": 2048,
            "video_frames": 8,
        },
        "completion_service": {"version": 1, "profile": "zap-it-v1"},
    },
}

FACIAL_CAPS = {
    "schema_version": 1,
    "capabilities": {
        "chat_completions": {"chat_text": True, "chat_streaming": False},
        "completion_service": {"version": 1, "profile": "facial-scoring-v1"},
    },
}


@pytest.fixture(scope="module")
def world(cli_env: str, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Prepare providers/routes/pricing/keys through the REAL CLI + repos."""
    url = cli_env
    tmp = tmp_path_factory.mktemp("slaif199a")
    zap_caps_file = tmp / "zap-caps.json"
    zap_caps_file.write_text(json.dumps(ZAP_CAPS), encoding="utf-8")
    facial_caps_file = tmp / "facial-caps.json"
    facial_caps_file.write_text(json.dumps(FACIAL_CAPS), encoding="utf-8")

    state: dict[str, Any] = {"tmp": tmp}

    # 1. Two fictional module providers, DISABLED preparation (CLI default).
    for slug, origin, env_ref, timeout, display in (
        ("svc-a", "https://svc-a.example/api", "SVC_A_KEY", 30, "Svc A"),
        ("svc-b", "https://svc-b.example/api", "SVC_B_KEY", 180, "Svc B"),
    ):
        result = _cli(
            "providers", "add",
            "--provider", slug,
            "--display-name", display,
            "--kind", "module",
            "--base-url", origin,
            "--api-key-env-var", env_ref,
            "--timeout-seconds", str(timeout),
            "--max-retries", "0",
            "--reason", "fictional module preparation",
            "--json",
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["enabled"] is False, "199 default: creation stays DISABLED"
        assert payload["max_retries"] == 0
        assert payload["timeout_seconds"] == timeout
        assert payload["api_key_env_var"] == env_ref
        state[slug] = payload["id"]

    # Third provider: openai_compatible (for kind-mismatch refusal).
    result = _cli(
        "providers", "add",
        "--provider", "svc-c",
        "--kind", "openai_compatible",
        "--base-url", "https://svc-c.example/v1",
        "--api-key-env-var", "SVC_C_KEY",
        "--reason", "compatible provider",
        "--json",
    )
    assert result.exit_code == 0, result.stderr
    state["svc-c"] = json.loads(result.stdout)["id"]

    # 2. Pricing rows through the EXISTING pricing command.
    for provider, model in (("svc-a", "zap-it-1"), ("svc-b", "facial-manipulation-scoring")):
        result = _cli(
            "pricing", "add",
            "--provider", provider,
            "--model", model,
            "--input-price-per-1m", "0.01",
            "--output-price-per-1m", "0.03",
            "--json",
        )
        assert result.exit_code == 0, result.stderr

    # 3. Routes through the real CLI (capabilities-file preparation => disabled).
    result = _cli(
        "routes", "add",
        "--requested-model", "zap-it-1",
        "--match-type", "exact",
        "--provider", "svc-a",
        "--upstream-model", "zap-it-1",
        "--no-streaming",
        "--capabilities-file", str(zap_caps_file),
        "--priority", "100",
        "--reason", "two-service workflow route",
        "--json",
    )
    assert result.exit_code == 0, result.stderr
    state["route_a"] = json.loads(result.stdout)["id"]

    result = _cli(
        "routes", "add",
        "--requested-model", "facial-manipulation-scoring",
        "--match-type", "exact",
        "--provider", "svc-b",
        "--upstream-model", "facial-manipulation-scoring",
        "--no-streaming",
        "--capabilities-file", str(facial_caps_file),
        "--priority", "100",
        "--reason", "two-service workflow route",
        "--json",
    )
    assert result.exit_code == 0, result.stderr
    state["route_b"] = json.loads(result.stdout)["id"]

    # Flag-free route on the compatible provider (historical enabled default).
    result = _cli(
        "routes", "add",
        "--requested-model", "plain-model",
        "--match-type", "exact",
        "--provider", "svc-c",
        "--upstream-model", "plain-model",
        "--priority", "50",
        "--json",
    )
    assert result.exit_code == 0, result.stderr
    state["route_c"] = json.loads(result.stdout)["id"]
    state["route_c_enabled_default"] = json.loads(result.stdout)["enabled"] is True

    # 4. Explicit activation of the two-service workflow (separate commands).
    assert _cli("providers", "enable", "svc-a", "--json").exit_code == 0
    assert _cli("routes", "enable", state["route_a"], "--json").exit_code == 0

    # 5. Plant synthetic key + ledger + replay references on route A.
    state.update(asyncio.run(_plant_references(url, state["route_a"])))
    _STATE.update(state)
    return _STATE


async def _plant_references(url: str, route_a_id: str) -> dict[str, Any]:
    factory = _session_factory(url)
    state: dict[str, Any] = {}
    async with factory() as session:
        async with session.begin():
            owners = OwnersRepository(session)
            owner = await owners.create_owner(
                name="Fiction", surname="Operator", email="fiction.operator@example.invalid"
            )
            keys = GatewayKeysRepository(session)
            key = await keys.create_gateway_key_record(
                public_key_id="pk_fiction_199a",
                token_hash="0" * 64,
                owner_id=owner.id,
                valid_from=datetime.now(UTC),
                valid_until=datetime.now(UTC).replace(year=2030),
                allowed_models=["zap-it-1"],
            )
            ledger = UsageLedger(
                request_id="req-199a-1",
                gateway_key_id=key.id,
                owner_id=owner.id,
                endpoint="/v1/chat/completions",
                provider="svc-a",
                requested_model="zap-it-1",
                resolved_model="zap-it-1",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
            session.add(ledger)
            await session.flush()
            replay = CodexReplayReference(
                gateway_key_id=key.id,
                usage_ledger_id=ledger.id,
                source_request_id="req-199a-1",
                provider="svc-a",
                route_id=uuid.UUID(route_a_id),
                upstream_model="zap-it-1",
                item_kind="reasoning",
                item_id_hmac="a" * 64,
                hmac_key_version=1,
                expires_at=datetime.now(UTC).replace(year=2030),
            )
            session.add(replay)
            await session.flush()
            state["owner_id"] = owner.id
            state["key_id"] = key.id
            state["ledger_id"] = ledger.id
            state["replay_id"] = replay.id
    return state


# --- helpers ------------------------------------------------------------------


async def _route(url: str, route_id: str) -> Any:
    factory = _session_factory(url)
    async with factory() as session:
        row = await ModelRoutesRepository(session).get_model_route_by_id(uuid.UUID(route_id))
        assert row is not None
        return {
            "id": str(row.id),
            "requested_model": row.requested_model,
            "match_type": row.match_type,
            "endpoint": row.endpoint,
            "provider": row.provider,
            "upstream_model": row.upstream_model,
            "priority": row.priority,
            "enabled": row.enabled,
            "visible_in_models": row.visible_in_models,
            "supports_streaming": row.supports_streaming,
            "capabilities": json.loads(json.dumps(row.capabilities, default=str)),
            "notes": row.notes,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


async def _provider(url: str, identifier: str) -> Any:
    factory = _session_factory(url)
    async with factory() as session:
        row = await ProviderConfigsRepository(session).get_provider_config_for_update(identifier)
        assert row is not None
        return {
            "id": str(row.id),
            "provider": row.provider,
            "display_name": row.display_name,
            "kind": row.kind,
            "base_url": row.base_url,
            "api_key_env_var": row.api_key_env_var,
            "enabled": row.enabled,
            "timeout_seconds": row.timeout_seconds,
            "max_retries": row.max_retries,
            "notes": row.notes,
            "created_at": row.created_at,
        }


async def _provider_audits(url: str, identifier: str) -> list[dict[str, Any]]:
    factory = _session_factory(url)
    async with factory() as session:
        row = await ProviderConfigsRepository(session).get_provider_config_by_provider(
            identifier
        )
        assert row is not None
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "provider_config_updated",
                        AuditLog.entity_id == row.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "old_values": dict(r.old_values or {}),
                "new_values": dict(r.new_values or {}),
                "note": r.note,
            }
            for r in rows
        ]


async def _audit_counts(url: str) -> dict[str, int]:
    factory = _session_factory(url)
    async with factory() as session:
        rows = (
            await session.execute(select(AuditLog.action))
        ).all()
        counts: dict[str, int] = {}
        for (action,) in rows:
            counts[action] = counts.get(action, 0) + 1
        return counts


# --- tests ----------------------------------------------------------------------


def test_fictional_module_providers_prepared_disabled(world, cli_env) -> None:
    for slug in ("svc-a", "svc-b"):
        result = _cli("providers", "show", slug, "--json")
        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["kind"] == "module"
        assert payload["max_retries"] == 0
        assert "fake-openai-upstream-key" not in result.stdout
        assert "SVC_A_KEY=" not in result.stdout
    a, b = asyncio.run(_provider(cli_env, "svc-a")), asyncio.run(_provider(cli_env, "svc-b"))
    assert a["base_url"] == "https://svc-a.example/api"
    assert b["base_url"] == "https://svc-b.example/api"
    assert a["api_key_env_var"] == "SVC_A_KEY"
    assert b["api_key_env_var"] == "SVC_B_KEY"
    assert a["timeout_seconds"] == 30 and b["timeout_seconds"] == 180


def test_route_a_capabilities_file_stored_exact(world, cli_env) -> None:
    row = asyncio.run(_route(cli_env, world["route_a"]))
    assert row["enabled"] is True  # explicitly enabled in setup
    assert row["capabilities"] == ZAP_CAPS["capabilities"]
    assert world["route_c_enabled_default"] is True  # historical flag-free default


def test_provider_partial_update_preserves_omitted(world, cli_env) -> None:
    before_a = asyncio.run(_provider(cli_env, "svc-a"))
    before_b = asyncio.run(_provider(cli_env, "svc-b"))
    result = _cli(
        "providers", "update", "svc-a", "--reason", "reviewed timeout change",
        "--timeout-seconds", "60", "--max-retries", "1", "--json",
    )
    assert result.exit_code == 0, result.stderr
    after_a = asyncio.run(_provider(cli_env, "svc-a"))
    after_b = asyncio.run(_provider(cli_env, "svc-b"))
    assert after_a["timeout_seconds"] == 60
    assert after_a["max_retries"] == 1
    for field in ("id", "provider", "display_name", "kind", "base_url",
                  "api_key_env_var", "enabled", "created_at", "notes"):
        assert after_a[field] == before_a[field], field
    assert after_b == before_b  # unrelated provider untouched


def test_provider_explicit_zero_retries_preserved(world, cli_env) -> None:
    result = _cli(
        "providers", "update", "svc-a", "--reason", "reviewed retry change",
        "--max-retries", "0", "--json",
    )
    assert result.exit_code == 0, result.stderr
    after = asyncio.run(_provider(cli_env, "svc-a"))
    assert after["max_retries"] == 0
    assert after["timeout_seconds"] == 60  # omitted field preserved


def test_provider_notes_replace_and_clear(world, cli_env) -> None:
    result = _cli(
        "providers", "update", "svc-a", "--reason", "add notes",
        "--notes", "reviewed note", "--json",
    )
    assert result.exit_code == 0, result.stderr
    assert asyncio.run(_provider(cli_env, "svc-a"))["notes"] == "reviewed note"

    # 199-c: the EXPLICIT clear intent stores NULL within the shared
    # audited operation (no direct pre-write): the audited OLD value is
    # the REAL prior value and the NEW value is the real null.
    before = asyncio.run(_provider(cli_env, "svc-a"))
    assert before["notes"] == "reviewed note"
    counts = asyncio.run(_audit_counts(cli_env))
    result = _cli(
        "providers", "update", "svc-a", "--reason", "clear notes",
        "--clear-notes", "--json",
    )
    assert result.exit_code == 0, result.stderr
    after = asyncio.run(_provider(cli_env, "svc-a"))
    assert after["notes"] is None  # the advertised clear actually clears
    for field in ("id", "provider", "display_name", "kind", "base_url",
                  "api_key_env_var", "enabled", "timeout_seconds",
                  "max_retries", "created_at"):
        assert after[field] == before[field], field  # no sibling change
    counts_after = asyncio.run(_audit_counts(cli_env))
    assert counts_after.get("provider_config_updated", 0) == (
        counts.get("provider_config_updated", 0) + 1
    )  # exactly one audit, no direct prewrite
    audits = asyncio.run(_provider_audits(cli_env, "svc-a"))
    clear_audit = [a for a in audits if a["note"] == "clear notes"]
    assert len(clear_audit) == 1
    assert clear_audit[0]["old_values"]["notes"] == "reviewed note"  # REAL old
    assert clear_audit[0]["new_values"]["notes"] is None  # real new null


def test_provider_update_conflict_refused(world, cli_env) -> None:
    before = asyncio.run(_provider(cli_env, "svc-a"))
    result = _cli(
        "providers", "update", "svc-a", "--reason", "x",
        "--notes", "x", "--clear-notes",
    )
    assert result.exit_code != 0
    assert "--notes or --clear-notes" in _plain(result.stderr)
    assert asyncio.run(_provider(cli_env, "svc-a")) == before


def test_route_plan_apply_ceiling_preserves_siblings(world, cli_env) -> None:
    route_a = world["route_a"]
    before = asyncio.run(_route(cli_env, route_a))
    plan_path = world["tmp"] / "ceiling-plan.json"
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(plan_path),
        "--codex-max-output-tokens", "400000", "--json",
    )
    assert result.exit_code == 0, result.stderr
    assert plan_path.exists()
    assert stat.S_IMODE(plan_path.stat().st_mode) == 0o600
    plan = parse_route_update_plan_file(plan_path.read_bytes())
    assert plan.capabilities_mode == "partial"
    assert plan.capability_patch.codex_limits == {"max_output_tokens": 400000}
    assert plan.enabled is True
    preview = plan.preview or {}
    assert "Configuration review only" in preview["note"]
    assert "unknown" in preview["note"]

    result = _cli(
        "routes", "update", route_a, "--execute", str(plan_path),
        "--reason", "reviewed ceiling 400000", "--json",
    )
    assert result.exit_code == 0, result.stderr
    after = asyncio.run(_route(cli_env, route_a))
    # Stable identity + unchanged siblings
    assert after["id"] == before["id"]
    assert after["created_at"] == before["created_at"]
    assert after["priority"] == before["priority"]
    assert after["requested_model"] == before["requested_model"]
    assert after["provider"] == before["provider"]
    caps = after["capabilities"]
    assert caps["codex_limits"] == {
        "context_window_tokens": 1050000,
        "default_max_output_tokens": 32768,
        "max_output_tokens": 400000,
    }
    assert caps["media_input_estimation"] == ZAP_CAPS["capabilities"]["media_input_estimation"]
    assert caps["chat_completions"] == ZAP_CAPS["capabilities"]["chat_completions"]
    assert caps["completion_service"] == {"version": 1, "profile": "zap-it-v1"}
    world["ceiling_plan"] = plan_path
    world["ceiling_after"] = after

    # One audited mutation
    counts = asyncio.run(_audit_counts(cli_env))
    assert counts.get("model_route_updated", 0) >= 1


def test_repeated_apply_refused_stale(world, cli_env) -> None:
    route_a = world["route_a"]
    before = asyncio.run(_route(cli_env, route_a))
    counts = asyncio.run(_audit_counts(cli_env))
    result = _cli(
        "routes", "update", route_a, "--execute", str(world["ceiling_plan"]),
        "--reason", "repeat", "--json",
    )
    assert result.exit_code != 0
    # --json renders the safe error on stdout, not stderr.
    error = json.loads(result.stdout)["error"]
    assert "no longer matches" in error["message"]
    after = asyncio.run(_route(cli_env, route_a))
    assert after == before  # zero writes
    assert asyncio.run(_audit_counts(cli_env)) == counts  # zero audits


def test_nested_media_update_preserves_siblings(world, cli_env) -> None:
    route_a = world["route_a"]
    plan_path = world["tmp"] / "media-plan.json"
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(plan_path),
        "--media-video-frames", "16", "--json",
    )
    assert result.exit_code == 0, result.stderr
    result = _cli(
        "routes", "update", route_a, "--execute", str(plan_path),
        "--reason", "reviewed media frames", "--json",
    )
    assert result.exit_code == 0, result.stderr
    after = asyncio.run(_route(cli_env, route_a))
    media = after["capabilities"]["media_input_estimation"]
    assert media == {"version": 1, "image_tokens": 1024, "video_tokens": 2048, "video_frames": 16}
    # codex headroom from the earlier plan is preserved
    assert after["capabilities"]["codex_limits"]["max_output_tokens"] == 400000
    assert after["capabilities"]["completion_service"] == {"version": 1, "profile": "zap-it-v1"}


def test_full_replacement_is_distinct(world, cli_env) -> None:
    route_a = world["route_a"]
    new_caps = world["tmp"] / "replacement-caps.json"
    # 199-c: a module-kind provider must keep resolving after the
    # replacement, so the completion selector stays in the document.
    replacement = {
        "schema_version": 1,
        "capabilities": {
            "chat_completions": {"chat_text": True, "chat_streaming": False},
            "media_input_estimation": {"version": 1, "image_tokens": 512},
            "completion_service": {"version": 1, "profile": "zap-it-v1"},
        },
    }
    new_caps.write_text(json.dumps(replacement), encoding="utf-8")
    plan_path = world["tmp"] / "replacement-plan.json"
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(plan_path),
        "--capabilities-file", str(new_caps), "--json",
    )
    assert result.exit_code == 0, result.stderr
    plan = parse_route_update_plan_file(plan_path.read_bytes())
    assert plan.capabilities_mode == "full-replacement"
    result = _cli(
        "routes", "update", route_a, "--execute", str(plan_path),
        "--reason", "reviewed full replacement", "--json",
    )
    assert result.exit_code == 0, result.stderr
    after = asyncio.run(_route(cli_env, route_a))
    assert after["capabilities"] == replacement["capabilities"]
    assert "codex_limits" not in after["capabilities"]  # unrelated group gone
    assert after["capabilities"]["completion_service"] == (
        {"version": 1, "profile": "zap-it-v1"}
    )  # provider still resolves


def test_wrong_profile_kind_upstream_denied(world, cli_env) -> None:
    route_a, route_c = world["route_a"], world["route_c"]
    counts = asyncio.run(_audit_counts(cli_env))

    # Profile whose public model differs from the route requested model.
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(world["tmp"] / "wrong-profile"),
        "--completion-service-profile", "facial-scoring-v1",
    )
    assert result.exit_code != 0
    assert not (world["tmp"] / "wrong-profile").exists()

    # Kind mismatch: openai_compatible provider cannot select a module profile.
    result = _cli(
        "routes", "update", route_c, "--dry-run", str(world["tmp"] / "wrong-kind"),
        "--completion-service-profile", "zap-it-v1",
    )
    assert result.exit_code != 0
    assert not (world["tmp"] / "wrong-kind").exists()

    # Upstream model mismatch with a matching profile.
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(world["tmp"] / "wrong-upstream"),
        "--completion-service-profile", "zap-it-v1", "--upstream-model", "other-model",
    )
    assert result.exit_code != 0
    assert not (world["tmp"] / "wrong-upstream").exists()

    assert asyncio.run(_audit_counts(cli_env)) == counts  # no writes/audits
    # Route C unchanged
    row_c = asyncio.run(_route(cli_env, route_c))
    assert row_c["requested_model"] == "plain-model"


def test_invalid_numerics_and_media_bounds_refused(world, cli_env) -> None:
    route_a = world["route_a"]
    # context below configured output breaks the strict codex relationship.
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(world["tmp"] / "bad-codex"),
        "--codex-context-window-tokens", "10",
    )
    assert result.exit_code != 0
    assert "codex_limits" in result.stderr
    # media frames above the engine ceiling.
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(world["tmp"] / "bad-media"),
        "--media-video-frames", "33",
    )
    assert result.exit_code != 0
    # zero media tokens.
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(world["tmp"] / "bad-media0"),
        "--media-image-tokens", "0",
    )
    assert result.exit_code != 0


def test_file_canaries_and_oversize_refused(world, cli_env) -> None:
    route_a = world["route_a"]
    secret_file = world["tmp"] / "secret-caps.json"
    secret_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "capabilities": {
                    "chat_completions": {"chat_text": True},
                    "codex_compaction_compatible_route_ids": [
                        "Authorization: Bearer abcdef1234567890"
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(world["tmp"] / "p1"),
        "--capabilities-file", str(secret_file),
    )
    assert result.exit_code != 0
    assert "secret shape" in result.stderr
    assert str(secret_file) not in result.stderr
    assert "Bearer abcdef1234567890" not in result.stderr

    big_file = world["tmp"] / "big-caps.json"
    big_file.write_text(
        '{"schema_version": 1, "capabilities": {"chat_completions": {"chat_text": true}}'
        + ", \"pad\": \"" + "x" * 70000 + '"}',
        encoding="utf-8",
    )
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(world["tmp"] / "p2"),
        "--capabilities-file", str(big_file),
    )
    assert result.exit_code != 0
    assert "bounded size" in result.stderr


def test_dry_run_performs_no_writes_or_audits(world, cli_env) -> None:
    route_a = world["route_a"]
    before = asyncio.run(_route(cli_env, route_a))
    counts = asyncio.run(_audit_counts(cli_env))
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(world["tmp"] / "readonly-plan"),
        "--priority", "77", "--json",
    )
    assert result.exit_code == 0
    after = asyncio.run(_route(cli_env, route_a))
    assert after == before
    assert asyncio.run(_audit_counts(cli_env)) == counts


def test_omitted_vs_clear_vs_false_semantics(world, cli_env) -> None:
    route_c = world["route_c"]
    base = asyncio.run(_route(cli_env, route_c))

    # omitted notes => preserved
    plan_path = world["tmp"] / "omit-notes.json"
    result = _cli(
        "routes", "update", route_c, "--dry-run", str(plan_path),
        "--priority", "60", "--json",
    )
    assert result.exit_code == 0
    result = _cli(
        "routes", "update", route_c, "--execute", str(plan_path),
        "--reason", "reviewed priority", "--json",
    )
    assert result.exit_code == 0
    row = asyncio.run(_route(cli_env, route_c))
    assert row["priority"] == 60
    assert row["notes"] == base["notes"]

    # clear notes => NULL
    plan_path = world["tmp"] / "clear-notes.json"
    result = _cli(
        "routes", "update", route_c, "--dry-run", str(plan_path),
        "--notes", "temporary note", "--json",
    )
    assert result.exit_code == 0
    plan = parse_route_update_plan_file(plan_path.read_bytes())
    assert plan.notes == "temporary note"
    # explicit false forms
    plan_path2 = world["tmp"] / "false-flags.json"
    result = _cli(
        "routes", "update", route_c, "--dry-run", str(plan_path2),
        "--hidden", "--no-streaming", "--json",
    )
    assert result.exit_code == 0
    plan2 = parse_route_update_plan_file(plan_path2.read_bytes())
    assert plan2.visible_in_models is False
    assert plan2.supports_streaming is False
    result = _cli(
        "routes", "update", route_c, "--execute", str(plan_path2),
        "--reason", "reviewed false flags", "--json",
    )
    assert result.exit_code == 0
    row = asyncio.run(_route(cli_env, route_c))
    assert row["visible_in_models"] is False
    assert row["supports_streaming"] is False
    assert row["notes"] == base["notes"]  # clear never requested


def test_forced_late_audit_failure_rolls_back(world, cli_env, monkeypatch) -> None:
    route_a = world["route_a"]
    before = asyncio.run(_route(cli_env, route_a))
    counts = asyncio.run(_audit_counts(cli_env))
    route_uuid = uuid.UUID(route_a)
    observed: dict[str, Any] = {}

    original = AuditRepository.add_audit_log
    forced = {"raised": False}

    async def hook(self, *args: Any, **kwargs: Any) -> Any:
        if (
            not forced["raised"]
            and kwargs.get("action") == "model_route_updated"
            and kwargs.get("entity_id") == route_uuid
        ):
            # The updated row must be visible in the SAME transaction before
            # the LATE audit failure.
            row = await ModelRoutesRepository(self._session).get_model_route_by_id(route_uuid)
            assert row is not None
            assert row.priority == 55, "updated row not visible in the same transaction"
            observed["visible"] = row.priority
            forced["raised"] = True
            raise RuntimeError("forced late audit failure")
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(AuditRepository, "add_audit_log", hook)
    result = _cli(
        "routes", "update", route_a, "--dry-run", str(world["tmp"] / "late-audit-plan"),
        "--priority", "55", "--json",
    )
    assert result.exit_code == 0
    result = _cli(
        "routes", "update", route_a, "--execute", str(world["tmp"] / "late-audit-plan"),
        "--reason", "reviewed late audit probe", "--json",
    )
    assert result.exit_code != 0
    assert observed.get("visible") == 55

    after = asyncio.run(_route(cli_env, route_a))
    assert after == before  # full rollback, no partial state
    assert asyncio.run(_audit_counts(cli_env)) == counts  # no orphan audit
    # The plan is still stale-free for a retry: re-executing succeeds now.
    result = _cli(
        "routes", "update", route_a, "--execute", str(world["tmp"] / "late-audit-plan"),
        "--reason", "reviewed retry after rollback", "--json",
    )
    assert result.exit_code == 0, result.output
    final = asyncio.run(_route(cli_env, route_a))
    assert final["priority"] == 55
    world["route_a_priority_after_late_audit"] = 55


def test_competing_route_change_invalidates_plan(world, cli_env) -> None:
    """B previews while A holds the route lock; A commits; B's execute is stale."""
    route_a = world["route_a"]
    route_uuid = uuid.UUID(route_a)

    async def scenario() -> dict[str, Any]:
        factory = _session_factory(cli_env)
        notes: dict[str, Any] = {}
        async with factory() as session_a:
            txn_a = await session_a.begin()
            routes_a = ModelRoutesRepository(session_a)
            held = await routes_a.get_model_route_for_update(route_uuid)
            assert held is not None
            async with factory() as session_b:
                plan = await preview_route_update_for_route(
                    session_b, str(route_uuid), priority=77
                )
                if session_b.in_transaction():
                    await session_b.rollback()
            async with factory() as session_b:
                execute_task = asyncio.create_task(
                    execute_route_update_plan(session_b, plan, reason="late")
                )
                await asyncio.sleep(0.75)
                notes["b_blocked"] = not execute_task.done()
                await routes_a.update_model_route_metadata(route_uuid, priority=66)
                await txn_a.commit()
                with pytest.raises(ProviderRouteStaleError):
                    await asyncio.wait_for(execute_task, timeout=30)
            # B's session saw the stale refusal; roll back its (empty) tx.
            if session_b.in_transaction():
                await session_b.rollback()
            # Use a FRESH session for the execute (mirrors the CLI: separate
            # invocation, no pre-lock identity-map snapshot).
        return notes

    notes = asyncio.run(scenario())
    assert notes["b_blocked"] is True  # B genuinely waited on A's row lock
    row = asyncio.run(_route(cli_env, route_a))
    assert row["priority"] == 66  # A's change, B's proposed 77 never applied


def test_competing_provider_update_preserve_omitted(world, cli_env) -> None:
    """B's partial provider update blocks on A's lock; A commits; B preserves A's value."""
    url = cli_env

    async def scenario() -> Any:
        factory = _session_factory(url)
        async with factory() as session_a:
            txn_a = await session_a.begin()
            providers_a = ProviderConfigsRepository(session_a)
            held = await providers_a.get_provider_config_for_update("svc-b")
            assert held is not None
            async with factory() as session_b:
                update_task = asyncio.create_task(
                    partial_update_provider_config(
                        session_b, "svc-b", display_name="Svc B tuned", reason="b partial"
                    )
                )
                await asyncio.sleep(0.75)
                blocked = not update_task.done()
                await providers_a.update_provider_metadata(held.id, timeout_seconds=111)
                await txn_a.commit()
                row_b = await asyncio.wait_for(update_task, timeout=30)
                await session_b.commit()
                return {"blocked": blocked, "row": row_b}

    result = asyncio.run(scenario())
    assert result["blocked"] is True
    after = asyncio.run(_provider(url, "svc-b"))
    assert after["display_name"] == "Svc B tuned"
    assert after["timeout_seconds"] == 111  # A's committed value preserved
    assert after["max_retries"] == 0


def test_planted_references_preserved(world, cli_env) -> None:
    url = cli_env

    async def scenario() -> dict[str, Any]:
        factory = _session_factory(url)
        notes: dict[str, Any] = {}
        async with factory() as session:
            key = await GatewayKeysRepository(session).get_gateway_key_by_public_key_id(
                "pk_fiction_199a"
            )
            assert key is not None
            notes["key"] = key.id
            replay_rows = (
                await session.execute(
                    select(CodexReplayReference).where(
                        CodexReplayReference.route_id == uuid.UUID(world["route_a"])
                    )
                )
            ).scalars().all()
            notes["replay"] = list(replay_rows)
            ledger_rows = (
                await session.execute(
                    select(UsageLedger).where(UsageLedger.id == world["ledger_id"])
                )
            ).scalars().all()
            notes["ledger"] = list(ledger_rows)
        return notes

    notes = asyncio.run(scenario())
    assert notes["key"] == world["key_id"]
    assert len(notes["replay"]) == 1
    assert notes["replay"][0].id == world["replay_id"]
    assert len(notes["ledger"]) == 1


# --- 199-b focused PG evidence --------------------------------------------------

CANARY_199B = "sk-proj-abcdef1234567890abcdef1234567890"


def test_provider_notes_audit_old_real_value(world, cli_env) -> None:
    """R1: successive real updates audit the REAL prior notes value."""
    result = _cli(
        "providers", "update", "svc-b", "--reason", "audit probe one",
        "--notes", "audit probe one", "--json",
    )
    assert result.exit_code == 0, result.stderr
    result = _cli(
        "providers", "update", "svc-b", "--reason", "audit probe two",
        "--notes", "audit probe two", "--json",
    )
    assert result.exit_code == 0, result.stderr
    audits = asyncio.run(_provider_audits(cli_env, "svc-b"))
    second = [a for a in audits if a["new_values"].get("notes") == "audit probe two"]
    assert len(second) == 1
    assert second[0]["old_values"].get("notes") == "audit probe one"
    assert second[0]["note"] == "audit probe two"


def test_route_provider_switch_context_stale(world, cli_env) -> None:
    """R2: a provider switch binds destination identity + context; drift is stale."""
    for slug, origin, env_ref in (
        ("svc-d", "https://svc-d.example/v1", "SVC_D_KEY"),
        ("svc-e", "https://svc-e.example/v1", "SVC_E_KEY"),
    ):
        result = _cli(
            "providers", "add",
            "--provider", slug, "--kind", "openai_compatible",
            "--base-url", origin, "--api-key-env-var", env_ref,
            "--max-retries", "0",
            "--reason", "provider switch fixture", "--json",
        )
        assert result.exit_code == 0, result.stderr

    result = _cli(
        "routes", "add",
        "--requested-model", "switch-model", "--match-type", "exact",
        "--provider", "svc-d", "--priority", "40",
        "--reason", "provider switch route", "--json",
    )
    assert result.exit_code == 0, result.stderr
    route_id = json.loads(result.stdout)["id"]
    twin = _cli(
        "routes", "add",
        "--requested-model", "switch-model", "--match-type", "exact",
        "--provider", "svc-d", "--priority", "40",
        "--reason", "provider switch twin route", "--json",
    )
    assert twin.exit_code == 0, twin.stderr
    twin_id = json.loads(twin.stdout)["id"]

    # Review a switch to svc-e: the plan BINDS the destination provider.
    plan_path = world["tmp"] / "switch-plan.json"
    result = _cli(
        "routes", "update", route_id, "--dry-run", str(plan_path),
        "--provider", "svc-e", "--json",
    )
    assert result.exit_code == 0, result.stderr
    plan = parse_route_update_plan_file(plan_path.read_bytes())
    assert plan.route_id == route_id
    assert plan.provider == "svc-e"
    preview = plan.preview or {}
    assert preview["current_configuration"]["provider"] == "svc-d"
    assert preview["proposed_configuration"]["provider"] == "svc-e"

    # Drift the destination context: the reviewed plan must go stale.
    result = _cli(
        "providers", "update", "svc-e", "--reason", "context drift",
        "--timeout-seconds", "99", "--json",
    )
    assert result.exit_code == 0, result.stderr
    before = asyncio.run(_route(cli_env, route_id))
    counts = asyncio.run(_audit_counts(cli_env))
    result = _cli(
        "routes", "update", route_id, "--execute", str(plan_path),
        "--reason", "apply switch", "--json",
    )
    assert result.exit_code != 0
    assert "provider context" in json.loads(result.stdout)["error"]["message"]
    assert asyncio.run(_route(cli_env, route_id)) == before  # zero writes
    assert asyncio.run(_audit_counts(cli_env)) == counts  # zero audits

    # A FRESH review of the same switch applies exactly once.
    plan2_path = world["tmp"] / "switch-plan2.json"
    result = _cli(
        "routes", "update", route_id, "--dry-run", str(plan2_path),
        "--provider", "svc-e", "--json",
    )
    assert result.exit_code == 0, result.stderr
    result = _cli(
        "routes", "update", route_id, "--execute", str(plan2_path),
        "--reason", "apply switch after fresh review", "--json",
    )
    assert result.exit_code == 0, result.stderr
    assert asyncio.run(_route(cli_env, route_id))["provider"] == "svc-e"
    assert asyncio.run(_route(cli_env, twin_id))["provider"] == "svc-d"

    # The route argument binds to the reviewed plan: a plan tampered to
    # target the twin route is refused stale with zero writes.
    plan3_path = world["tmp"] / "switch-plan3.json"
    result = _cli("routes", "update", route_id, "--dry-run", str(plan3_path), "--json")
    assert result.exit_code == 0, result.stderr
    document = json.loads(plan3_path.read_text(encoding="utf-8"))
    tampered_path = world["tmp"] / "switch-plan3-tampered.json"
    tampered = dict(document)
    tampered["route_id"] = twin_id
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    before_twin = asyncio.run(_route(cli_env, twin_id))
    counts = asyncio.run(_audit_counts(cli_env))
    result = _cli(
        "routes", "update", twin_id, "--execute", str(tampered_path),
        "--reason", "tampered target", "--json",
    )
    assert result.exit_code != 0
    assert "no longer matches" in json.loads(result.stdout)["error"]["message"]
    assert asyncio.run(_route(cli_env, twin_id)) == before_twin  # zero writes
    assert asyncio.run(_audit_counts(cli_env)) == counts  # zero audits

    # A deleted destination provider makes the reviewed plan stale too.
    async def drop_svc_e() -> None:
        factory = _session_factory(cli_env)
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    delete(ProviderConfig).where(ProviderConfig.provider == "svc-e")
                )

    asyncio.run(drop_svc_e())
    before = asyncio.run(_route(cli_env, route_id))
    counts = asyncio.run(_audit_counts(cli_env))
    result = _cli(
        "routes", "update", route_id, "--execute", str(plan3_path),
        "--reason", "destination gone", "--json",
    )
    assert result.exit_code != 0
    assert "destination provider" in json.loads(result.stdout)["error"]["message"]
    assert asyncio.run(_route(cli_env, route_id)) == before  # zero writes
    assert asyncio.run(_audit_counts(cli_env)) == counts  # zero audits


def test_lowered_external_tool_ceiling_denied(world, cli_env) -> None:
    """R3: route policy caps are checked against ACTUAL installation ceilings."""
    route_a = world["route_a"]

    def caps_doc(cap: int) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "capabilities": {
                "chat_completions": {"chat_text": True, "chat_streaming": False},
                "media_input_estimation": {"version": 1, "image_tokens": 512},
                "completion_service": {"version": 1, "profile": "zap-it-v1"},
                "external_tools": {
                    "version": 1,
                    "supported_capabilities": ["provider_web_search"],
                    "approved_destination_ids": [],
                    "max_provider_tool_calls_per_request": cap,
                    "call_limit_enforced": True,
                    "final_usage_required": True,
                    "final_cost_required": True,
                },
            },
        }

    saved = os.environ.get("EXTERNAL_TOOL_MAX_PROVIDER_TOOL_CALLS_PER_REQUEST")
    try:
        os.environ["EXTERNAL_TOOL_MAX_PROVIDER_TOOL_CALLS_PER_REQUEST"] = "1"
        get_settings.cache_clear()

        high = world["tmp"] / "caps-cap2.json"
        high.write_text(json.dumps(caps_doc(2)), encoding="utf-8")
        result = _cli(
            "routes", "update", route_a,
            "--dry-run", str(world["tmp"] / "cap2-plan"),
            "--capabilities-file", str(high),
        )
        assert result.exit_code != 0
        assert "external_tools" in _plain(result.stderr)
        assert not (world["tmp"] / "cap2-plan").exists()

        low = world["tmp"] / "caps-cap1.json"
        low.write_text(json.dumps(caps_doc(1)), encoding="utf-8")
        plan_path = world["tmp"] / "cap1-plan.json"
        result = _cli(
            "routes", "update", route_a, "--dry-run", str(plan_path),
            "--capabilities-file", str(low), "--json",
        )
        assert result.exit_code == 0, result.stderr
        result = _cli(
            "routes", "update", route_a, "--execute", str(plan_path),
            "--reason", "reviewed external tool cap one", "--json",
        )
        assert result.exit_code == 0, result.stderr
        after = asyncio.run(_route(cli_env, route_a))
        assert (
            after["capabilities"]["external_tools"]["max_provider_tool_calls_per_request"]
            == 1
        )
    finally:
        if saved is None:
            os.environ.pop("EXTERNAL_TOOL_MAX_PROVIDER_TOOL_CALLS_PER_REQUEST", None)
        else:
            os.environ["EXTERNAL_TOOL_MAX_PROVIDER_TOOL_CALLS_PER_REQUEST"] = saved
        get_settings.cache_clear()


def test_configured_profile_directory(world, cli_env) -> None:
    """R3: completion profiles resolve from the CONFIGURED operator directory."""
    from pathlib import Path

    from slaif_gateway.modules.servers.completion_service.profiles import load_profile

    route_a = world["route_a"]
    profile_dir = world["tmp"] / "profiles-199b"
    profile_dir.mkdir()
    bundled = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "app/slaif_gateway/modules/servers/completion_service/profiles/zap-it-v1.json"
        ).read_text(encoding="utf-8")
    )
    profile = dict(bundled)
    profile["profile_id"] = "custom-it-v1"
    profile["api_key_env_var"] = "CUSTOM_IT_API_KEY"
    profile["result_schema_version"] = "custom-it.public.v1"
    profile_path = profile_dir / "custom-it-v1.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    os.chmod(profile_path, 0o600)  # the operator directory enforces 0600
    saved = os.environ.get("COMPLETION_SERVICE_PROFILE_DIR")
    try:
        os.environ["COMPLETION_SERVICE_PROFILE_DIR"] = str(profile_dir)
        get_settings.cache_clear()

        plan_path = world["tmp"] / "profile-plan.json"
        result = _cli(
            "routes", "update", route_a, "--dry-run", str(plan_path),
            "--completion-service-profile", "custom-it-v1", "--json",
        )
        assert result.exit_code == 0, result.stderr

        # With an operator directory configured, the bundled directory is not
        # visible: a bundled-only profile is refused.
        result = _cli(
            "routes", "update", route_a,
            "--dry-run", str(world["tmp"] / "bundled-refused"),
            "--completion-service-profile", "zap-it-v1",
        )
        assert result.exit_code != 0
        assert "completion_service" in _plain(result.stderr)
        assert not (world["tmp"] / "bundled-refused").exists()

        result = _cli(
            "routes", "update", route_a,
            "--dry-run", str(world["tmp"] / "unknown-refused"),
            "--completion-service-profile", "unknown-it-v9",
        )
        assert result.exit_code != 0
        assert "completion_service" in _plain(result.stderr)

        result = _cli(
            "routes", "update", route_a, "--execute", str(plan_path),
            "--reason", "reviewed configured profile", "--json",
        )
        assert result.exit_code == 0, result.stderr
        assert "CUSTOM_IT_API_KEY" not in result.stdout  # no credential resolution
        after = asyncio.run(_route(cli_env, route_a))
        assert after["capabilities"]["completion_service"] == {
            "version": 1,
            "profile": "custom-it-v1",
        }
    finally:
        if saved is None:
            os.environ.pop("COMPLETION_SERVICE_PROFILE_DIR", None)
        else:
            os.environ["COMPLETION_SERVICE_PROFILE_DIR"] = saved
        get_settings.cache_clear()
        load_profile.cache_clear()


def test_known_secret_refusals(world, cli_env) -> None:
    """R1: known credential shapes are refused pre-mutation and redacted on reads."""
    canary = CANARY_199B
    provider_a = asyncio.run(_provider(cli_env, "svc-a"))
    counts = asyncio.run(_audit_counts(cli_env))

    result = _cli(
        "providers", "update", "svc-a", "--reason", "secret probe notes",
        "--notes", canary,
    )
    assert result.exit_code != 0
    assert "credential patterns" in _plain(result.stderr)
    assert canary not in result.stdout
    assert canary not in result.stderr
    assert asyncio.run(_provider(cli_env, "svc-a")) == provider_a  # zero writes
    assert asyncio.run(_audit_counts(cli_env)) == counts  # zero audits

    result = _cli(
        "providers", "update", "svc-a", "--reason", "secret probe name",
        "--display-name", canary,
    )
    assert result.exit_code != 0
    assert "credential patterns" in _plain(result.stderr)
    assert canary not in result.stdout
    assert canary not in result.stderr
    assert asyncio.run(_provider(cli_env, "svc-a")) == provider_a  # zero writes

    result = _cli(
        "routes", "add",
        "--requested-model", "secret-model-199b", "--match-type", "exact",
        "--provider", "svc-a", "--notes", canary,
    )
    assert result.exit_code != 0
    assert "credential patterns" in _plain(result.stderr)
    assert canary not in result.stdout
    assert canary not in result.stderr

    async def count_secret_routes() -> int:
        factory = _session_factory(cli_env)
        async with factory() as session:
            rows = (
                await session.execute(
                    select(ModelRoute).where(
                        ModelRoute.requested_model == "secret-model-199b"
                    )
                )
            ).scalars().all()
            return len(rows)

    assert asyncio.run(count_secret_routes()) == 0  # no row, no audit
    assert asyncio.run(_audit_counts(cli_env)) == counts

    # A LEGACY stored value (planted directly, pre-guard) is redacted on read.
    async def plant_legacy() -> None:
        factory = _session_factory(cli_env)
        async with factory() as session:
            async with session.begin():
                row = await ProviderConfigsRepository(session).get_provider_config_by_provider(
                    "svc-b"
                )
                assert row is not None
                row.notes = f"legacy {canary}"
                await session.flush()

    asyncio.run(plant_legacy())
    result = _cli("providers", "show", "svc-b", "--json")
    assert result.exit_code == 0, result.stderr
    assert canary not in result.stdout
    assert "***" in result.stdout

# --- 199-c focused PG evidence ----------------------------------------------------


def _create_facial_bound_provider() -> None:
    """Create the implicitly-bound legacy module provider (once, real CLI)."""
    result = _cli(
        "providers", "add",
        "--provider", "facial_scoring",
        "--display-name", "Facial Scoring (legacy bound)",
        "--kind", "module",
        "--base-url", "https://facial-scoring.example/api",
        "--api-key-env-var", "FACIAL_SCORING_API_KEY",
        "--max-retries", "0",
        "--reason", "legacy-bound module preparation",
        "--json",
    )
    assert result.exit_code == 0, result.stderr


async def _count_provider_rows(url: str) -> int:
    factory = _session_factory(url)
    async with factory() as session:
        return len((await session.execute(select(ProviderConfig))).scalars().all())


async def _count_routes_by_model(url: str, model: str) -> int:
    factory = _session_factory(url)
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(ModelRoute).where(ModelRoute.requested_model == model)
                )
            )
            .scalars()
            .all()
        )
        return len(rows)


def test_provider_create_known_secret_shape_refused(world, cli_env) -> None:
    """C2: recognized credential shapes are refused BEFORE creation writes."""
    canary = CANARY_199B
    before_rows = asyncio.run(_count_provider_rows(cli_env))
    counts = asyncio.run(_audit_counts(cli_env))

    result = _cli(
        "providers", "add",
        "--provider", "svc-g",
        "--api-key-env-var", "SVC_G_KEY",
        "--base-url", "https://svc-g.example/v1",
        "--notes", canary,
        "--reason", "creation probe",
    )
    assert result.exit_code != 0
    assert "credential patterns" in _plain(result.stderr)
    assert canary not in result.stdout
    assert canary not in result.stderr
    assert asyncio.run(_count_provider_rows(cli_env)) == before_rows  # zero rows
    assert asyncio.run(_audit_counts(cli_env)) == counts  # zero audits

    # ordinary text and safe env-variable NAMES stay literal on creation
    result = _cli(
        "providers", "add",
        "--provider", "svc-g",
        "--api-key-env-var", "SVC_G_KEY",
        "--display-name", "Svc G (reviewed)",
        "--base-url", "https://svc-g.example/v1",
        "--notes", "uses SVC_G_KEY; reviewed note",
        "--reason", "ordinary creation",
        "--json",
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["enabled"] is False  # creation stays DISABLED
    stored = asyncio.run(_provider(cli_env, "svc-g"))
    assert stored["notes"] == "uses SVC_G_KEY; reviewed note"
    assert stored["display_name"] == "Svc G (reviewed)"


def test_provider_late_audit_failure_rolls_back_clear_and_sibling(
    world, cli_env, monkeypatch
) -> None:
    """C1: a LATE provider audit failure rolls back clear AND sibling."""
    result = _cli(
        "providers", "update", "svc-a", "--reason", "re-add notes",
        "--notes", "rollback probe", "--json",
    )
    assert result.exit_code == 0, result.stderr
    before = asyncio.run(_provider(cli_env, "svc-a"))
    assert before["notes"] == "rollback probe"
    counts = asyncio.run(_audit_counts(cli_env))
    provider_uuid = uuid.UUID(before["id"])
    observed: dict[str, Any] = {}
    forced = {"raised": False}

    original = AuditRepository.add_audit_log

    async def hook(self, *args: Any, **kwargs: Any) -> Any:
        if (
            not forced["raised"]
            and kwargs.get("action") == "provider_config_updated"
            and kwargs.get("entity_id") == provider_uuid
        ):
            # The cleared row must be visible in the SAME transaction
            # before the LATE audit failure.
            row = await ProviderConfigsRepository(
                self._session
            ).get_provider_config_by_id(provider_uuid)
            assert row is not None
            assert (
                row.notes is None and row.timeout_seconds == 75
            ), "updated row not visible in the same transaction"
            observed["visible"] = (row.notes, row.timeout_seconds)
            forced["raised"] = True
            raise RuntimeError("forced late provider audit failure")
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(AuditRepository, "add_audit_log", hook)
    result = _cli(
        "providers", "update", "svc-a", "--reason", "clear + timeout probe",
        "--clear-notes", "--timeout-seconds", "75", "--json",
    )
    assert result.exit_code != 0
    assert observed.get("visible") == (None, 75)

    after = asyncio.run(_provider(cli_env, "svc-a"))
    assert after == before  # full rollback: clear AND sibling preserved
    assert asyncio.run(_audit_counts(cli_env)) == counts  # no orphan audit

    # The retry now succeeds and audits the REAL prior value -> null.
    result = _cli(
        "providers", "update", "svc-a", "--reason", "clear + timeout retry",
        "--clear-notes", "--timeout-seconds", "75", "--json",
    )
    assert result.exit_code == 0, result.stderr
    final = asyncio.run(_provider(cli_env, "svc-a"))
    assert final["notes"] is None
    assert final["timeout_seconds"] == 75
    audits = asyncio.run(_provider_audits(cli_env, "svc-a"))
    retry_audit = [a for a in audits if a["note"] == "clear + timeout retry"]
    assert len(retry_audit) == 1
    assert retry_audit[0]["old_values"]["notes"] == "rollback probe"
    assert retry_audit[0]["new_values"]["notes"] is None


def test_unknown_module_route_create_refused(world, cli_env) -> None:
    """C3: an unregistered module provider cannot back a NEW route."""
    result = _cli(
        "providers", "add",
        "--provider", "ghost-mod",
        "--kind", "module",
        "--base-url", "https://ghost.example/api",
        "--api-key-env-var", "GHOST_KEY",
        "--max-retries", "0",
        "--reason", "unregistered module preparation",
        "--json",
    )
    assert result.exit_code == 0, result.stderr
    counts = asyncio.run(_audit_counts(cli_env))
    result = _cli(
        "routes", "add",
        "--requested-model", "ghost-model-199c",
        "--match-type", "exact",
        "--provider", "ghost-mod",
        "--priority", "30",
        "--reason", "unsupported module route",
    )
    assert result.exit_code != 0
    assert "supported server module" in _plain(result.stderr)
    assert asyncio.run(_count_routes_by_model(cli_env, "ghost-model-199c")) == 0
    assert asyncio.run(_audit_counts(cli_env)) == counts  # no writes/audits


def test_legacy_bound_route_create_valid_and_wrong_model_refused(world, cli_env) -> None:
    """C3: the implicit legacy binding resolves on real PG create."""
    _create_facial_bound_provider()
    counts = asyncio.run(_audit_counts(cli_env))

    # negative first: wrong requested model for the bound profile
    result = _cli(
        "routes", "add",
        "--requested-model", "wrong-model-199c",
        "--match-type", "exact",
        "--provider", "facial_scoring",
        "--upstream-model", "wrong-model-199c",
        "--no-streaming",
        "--priority", "30",
        "--reason", "bound profile wrong model",
    )
    assert result.exit_code != 0
    assert "profile public model" in _plain(result.stderr)
    assert asyncio.run(_count_routes_by_model(cli_env, "wrong-model-199c")) == 0
    assert asyncio.run(_audit_counts(cli_env)) == counts  # no writes/audits

    # positive: the SAME bundled profile directory the runtime uses
    result = _cli(
        "routes", "add",
        "--requested-model", "facial-manipulation-scoring",
        "--match-type", "exact",
        "--provider", "facial_scoring",
        "--upstream-model", "facial-manipulation-scoring",
        "--no-streaming",
        "--priority", "30",
        "--reason", "legacy-bound route preparation",
        "--json",
    )
    assert result.exit_code == 0, result.stderr
    route_id = json.loads(result.stdout)["id"]
    row = asyncio.run(_route(cli_env, route_id))
    assert row["supports_streaming"] is False
    assert row["capabilities"]["chat_completions"]["chat_streaming"] is False
    assert "completion_service" not in row["capabilities"]  # no fabricated selector
    world["route_facial"] = route_id


def test_legacy_bound_streaming_refused_on_create(world, cli_env) -> None:
    """C3: advertised streaming (route flag + default chat block) is refused."""
    counts = asyncio.run(_audit_counts(cli_env))
    result = _cli(
        "routes", "add",
        "--requested-model", "facial-manipulation-scoring",
        "--match-type", "exact",
        "--provider", "facial_scoring",
        "--upstream-model", "facial-manipulation-scoring",
        "--priority", "33",
        "--reason", "streaming on a completion route",
    )
    assert result.exit_code != 0
    assert "streaming" in _plain(result.stderr)
    assert asyncio.run(_audit_counts(cli_env)) == counts  # no writes/audits


def test_explicit_selector_streaming_refused_on_update(world, cli_env) -> None:
    """C3: an explicit-selector route cannot advertise streaming either."""
    route_b = world["route_b"]
    counts = asyncio.run(_audit_counts(cli_env))
    before = asyncio.run(_route(cli_env, route_b))
    result = _cli(
        "routes", "update", route_b, "--dry-run", str(world["tmp"] / "streaming-plan"),
        "--streaming",
    )
    assert result.exit_code != 0
    assert "streaming" in _plain(result.stderr)
    assert not (world["tmp"] / "streaming-plan").exists()
    assert asyncio.run(_route(cli_env, route_b)) == before  # zero writes
    assert asyncio.run(_audit_counts(cli_env)) == counts  # zero audits


def test_legacy_bound_operator_directory_resolution(world, cli_env) -> None:
    """C3: implicit bindings honor the SAME configured operator directory."""
    from pathlib import Path

    from slaif_gateway.modules.servers.completion_service.profiles import load_profile

    bundled_path = (
        Path(__file__).resolve().parents[2]
        / "app/slaif_gateway/modules/servers/completion_service/profiles/facial-scoring-v1.json"
    )
    saved = os.environ.get("COMPLETION_SERVICE_PROFILE_DIR")
    try:
        # case 1: operator directory WITH the bound profile file -> implicit OK
        profile_dir = world["tmp"] / "profiles-199c-bound"
        profile_dir.mkdir()
        target = profile_dir / "facial-scoring-v1.json"
        target.write_text(bundled_path.read_text(encoding="utf-8"), encoding="utf-8")
        os.chmod(target, 0o600)  # operator directories enforce 0600
        os.environ["COMPLETION_SERVICE_PROFILE_DIR"] = str(profile_dir)
        get_settings.cache_clear()
        result = _cli(
            "routes", "add",
            "--requested-model", "facial-manipulation-scoring",
            "--match-type", "exact",
            "--provider", "facial_scoring",
            "--upstream-model", "facial-manipulation-scoring",
            "--no-streaming",
            "--priority", "31",
            "--reason", "legacy-bound operator-dir route",
            "--json",
        )
        assert result.exit_code == 0, result.stderr
        route_id = json.loads(result.stdout)["id"]
        row = asyncio.run(_route(cli_env, route_id))
        assert row["capabilities"]["chat_completions"]["chat_streaming"] is False
        assert "completion_service" not in row["capabilities"]

        # case 2: operator directory WITHOUT the bound profile -> refused
        counts = asyncio.run(_audit_counts(cli_env))
        empty_dir = world["tmp"] / "profiles-199c-empty"
        empty_dir.mkdir()
        os.environ["COMPLETION_SERVICE_PROFILE_DIR"] = str(empty_dir)
        get_settings.cache_clear()
        result = _cli(
            "routes", "add",
            "--requested-model", "facial-manipulation-scoring",
            "--match-type", "exact",
            "--provider", "facial_scoring",
            "--upstream-model", "facial-manipulation-scoring",
            "--no-streaming",
            "--priority", "32",
            "--reason", "bound profile unavailable",
        )
        assert result.exit_code != 0
        assert "valid available profile selector" in _plain(result.stderr)
        assert asyncio.run(_audit_counts(cli_env)) == counts  # no writes/audits
    finally:
        if saved is None:
            os.environ.pop("COMPLETION_SERVICE_PROFILE_DIR", None)
        else:
            os.environ["COMPLETION_SERVICE_PROFILE_DIR"] = saved
        get_settings.cache_clear()
        load_profile.cache_clear()

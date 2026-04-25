"""PostgreSQL-backed integration tests for the ``slaif-gateway keys`` CLI."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.db.models import AuditLog, GatewayKey, OneTimeSecret, UsageLedger
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.utils.crypto import parse_gateway_key_public_id
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.db_test_utils import run_alembic_upgrade_head

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for CLI key PostgreSQL integration tests",
)

TEST_HMAC_SECRET = "test-hmac-secret-for-cli-key-integration-123456"
TEST_ADMIN_SECRET = "test-admin-secret-for-cli-key-integration-123456"
SAFE_MARKERS = (
    "token_hash",
    "encrypted_payload",
    "nonce",
)


@dataclass(frozen=True, slots=True)
class OwnerContext:
    institution_id: uuid.UUID
    cohort_id: uuid.UUID
    owner_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class CreatedCliKey:
    gateway_key_id: uuid.UUID
    owner_id: uuid.UUID
    cohort_id: uuid.UUID
    public_key_id: str
    plaintext_key: str
    output: str


@pytest.fixture(scope="session")
def cli_postgres_url() -> str:
    database_url = os.environ["TEST_DATABASE_URL"]
    run_alembic_upgrade_head(database_url)
    return database_url


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, cli_postgres_url: str) -> str:
    monkeypatch.setenv("DATABASE_URL", cli_postgres_url)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("GATEWAY_KEY_PREFIX", "sk-slaif-")
    monkeypatch.setenv("GATEWAY_KEY_ACCEPTED_PREFIXES", "sk-slaif-")
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", TEST_HMAC_SECRET)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", TEST_ADMIN_SECRET)
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", generate_secret_key())
    monkeypatch.setenv("OPENAI_UPSTREAM_API_KEY", "fake-openai-upstream-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-openrouter-upstream-key")

    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    return cli_postgres_url


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _run(coro):
    return asyncio.run(coro)


def _unique_label(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


async def _create_owner_context(database_url: str) -> OwnerContext:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unique = _unique_label("cli-keys")
    now = datetime.now(UTC)

    try:
        async with session_factory() as session:
            institutions = InstitutionsRepository(session)
            cohorts = CohortsRepository(session)
            owners = OwnersRepository(session)

            institution = await institutions.create_institution(
                name=f"SLAIF CLI Integration {unique}",
                country="SI",
                notes="CLI key integration test data",
            )
            cohort = await cohorts.create_cohort(
                name=unique,
                description="CLI key integration cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=30),
            )
            owner = await owners.create_owner(
                name="CLI",
                surname="Integration",
                email=f"{unique}@example.org",
                institution_id=institution.id,
                notes="CLI key integration owner",
            )
            await session.commit()
            return OwnerContext(
                institution_id=institution.id,
                cohort_id=cohort.id,
                owner_id=owner.id,
            )
    finally:
        await engine.dispose()


def _create_key_via_cli(
    runner: CliRunner,
    database_url: str,
    *,
    json_output: bool = False,
) -> CreatedCliKey:
    context = _run(_create_owner_context(database_url))
    args = [
        "keys",
        "create",
        "--owner-id",
        str(context.owner_id),
        "--cohort-id",
        str(context.cohort_id),
        "--valid-days",
        "30",
        "--cost-limit-eur",
        "12.500000000",
        "--token-limit-total",
        "1000",
        "--request-limit-total",
        "25",
        "--allowed-model",
        "gpt-test-mini",
        "--allowed-endpoint",
        "/v1/chat/completions",
        "--reason",
        "integration create",
    ]
    if json_output:
        args.append("--json")

    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    payload = _parse_create_output(result.stdout, json_output=json_output)
    return CreatedCliKey(
        gateway_key_id=uuid.UUID(payload["gateway_key_id"]),
        owner_id=context.owner_id,
        cohort_id=context.cohort_id,
        public_key_id=payload["public_key_id"],
        plaintext_key=payload["plaintext_key"],
        output=result.stdout,
    )


def _parse_create_output(output: str, *, json_output: bool = False) -> dict[str, str]:
    if json_output:
        payload = json.loads(output)
        return {
            "gateway_key_id": payload["gateway_key_id"],
            "public_key_id": payload["public_key_id"],
            "plaintext_key": payload["plaintext_key"],
        }

    parsed: dict[str, str] = {}
    for line in output.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            parsed[key] = value
    return parsed


def _parse_rotate_output(output: str, *, json_output: bool = False) -> dict[str, str]:
    if json_output:
        payload = json.loads(output)
        return {
            "old_gateway_key_id": payload["old_gateway_key_id"],
            "new_gateway_key_id": payload["new_gateway_key_id"],
            "new_plaintext_key": payload["new_plaintext_key"],
            "new_public_key_id": payload["new_public_key_id"],
        }

    parsed: dict[str, str] = {}
    for line in output.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            parsed[key] = value
    return parsed


def _assert_safe_output(output: str, *allowed_plaintext_keys: str) -> None:
    lowered = output.lower()
    for marker in SAFE_MARKERS:
        assert marker not in lowered
    for plaintext_key in allowed_plaintext_keys:
        assert output.count(plaintext_key) == 1


async def _get_key(database_url: str, gateway_key_id: uuid.UUID) -> GatewayKey:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            gateway_key = await session.get(GatewayKey, gateway_key_id)
            assert gateway_key is not None
            return gateway_key
    finally:
        await engine.dispose()


async def _one_time_secret_for_key(database_url: str, gateway_key_id: uuid.UUID) -> OneTimeSecret:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(OneTimeSecret)
                    .where(OneTimeSecret.gateway_key_id == gateway_key_id)
                    .order_by(OneTimeSecret.created_at.desc())
                    .limit(1)
                )
            ).scalar_one()
            return row
    finally:
        await engine.dispose()


async def _audit_count(
    database_url: str,
    *,
    gateway_key_id: uuid.UUID,
    action: str | None = None,
) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            statement = select(func.count()).select_from(AuditLog).where(
                AuditLog.entity_type == "gateway_key",
                AuditLog.entity_id == gateway_key_id,
            )
            if action is not None:
                statement = statement.where(AuditLog.action == action)
            return int((await session.execute(statement)).scalar_one())
    finally:
        await engine.dispose()


async def _audit_payload_text(database_url: str, gateway_key_id: uuid.UUID) -> str:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "gateway_key",
                        AuditLog.entity_id == gateway_key_id,
                    )
                )
            ).scalars()
            return json.dumps(
                [
                    {
                        "action": row.action,
                        "old_values": row.old_values,
                        "new_values": row.new_values,
                        "note": row.note,
                    }
                    for row in rows
                ],
                default=str,
                sort_keys=True,
            )
    finally:
        await engine.dispose()


async def _prime_usage_counters(database_url: str, gateway_key_id: uuid.UUID) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    try:
        async with session_factory() as session:
            gateway_key = await session.get(GatewayKey, gateway_key_id)
            assert gateway_key is not None
            gateway_key.cost_used_eur = Decimal("2.000000000")
            gateway_key.tokens_used_total = 111
            gateway_key.requests_used_total = 3
            gateway_key.cost_reserved_eur = Decimal("1.000000000")
            gateway_key.tokens_reserved_total = 22
            gateway_key.requests_reserved_total = 2
            session.add(
                UsageLedger(
                    request_id=f"cli-key-reset-{uuid.uuid4().hex}",
                    gateway_key_id=gateway_key_id,
                    owner_id=gateway_key.owner_id,
                    cohort_id=gateway_key.cohort_id,
                    endpoint="/v1/chat/completions",
                    provider="openai",
                    requested_model="gpt-test-mini",
                    resolved_model="gpt-test-mini",
                    success=True,
                    accounting_status="finalized",
                    http_status=200,
                    prompt_tokens=5,
                    completion_tokens=6,
                    input_tokens=5,
                    output_tokens=6,
                    total_tokens=11,
                    started_at=now,
                    finished_at=now,
                )
            )
            await session.commit()

            count_statement = select(func.count()).select_from(UsageLedger).where(
                UsageLedger.gateway_key_id == gateway_key_id
            )
            return int((await session.execute(count_statement)).scalar_one())
    finally:
        await engine.dispose()


async def _usage_ledger_count(database_url: str, gateway_key_id: uuid.UUID) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            statement = select(func.count()).select_from(UsageLedger).where(
                UsageLedger.gateway_key_id == gateway_key_id
            )
            return int((await session.execute(statement)).scalar_one())
    finally:
        await engine.dispose()


def test_keys_create_persists_hmac_one_time_secret_and_audit(
    runner: CliRunner,
    cli_env: str,
) -> None:
    created = _create_key_via_cli(runner, cli_env)

    assert created.plaintext_key.startswith("sk-slaif-")
    assert created.output.count(created.plaintext_key) == 1
    assert "shown once" in created.output
    _assert_safe_output(created.output, created.plaintext_key)

    public_key_id = parse_gateway_key_public_id(created.plaintext_key, ("sk-slaif-",))
    assert public_key_id == created.public_key_id

    gateway_key = _run(_get_key(cli_env, created.gateway_key_id))
    assert gateway_key.public_key_id == created.public_key_id
    assert gateway_key.token_hash
    assert not gateway_key.token_hash.startswith("sk-")
    assert gateway_key.token_hash != created.plaintext_key
    assert created.plaintext_key not in gateway_key.token_hash
    assert created.plaintext_key not in (gateway_key.key_hint or "")

    one_time_secret = _run(_one_time_secret_for_key(cli_env, created.gateway_key_id))
    assert one_time_secret.encrypted_payload
    assert one_time_secret.nonce
    assert created.plaintext_key not in one_time_secret.encrypted_payload
    assert created.plaintext_key not in one_time_secret.nonce
    assert one_time_secret.purpose == "gateway_key_email"
    assert _run(_audit_count(cli_env, gateway_key_id=created.gateway_key_id, action="gateway_key_created")) == 1

    audit_payload = _run(_audit_payload_text(cli_env, created.gateway_key_id))
    assert created.plaintext_key not in audit_payload
    assert gateway_key.token_hash not in audit_payload
    assert one_time_secret.encrypted_payload not in audit_payload
    assert one_time_secret.nonce not in audit_payload


def test_keys_create_json_outputs_plaintext_once_and_safe_metadata(
    runner: CliRunner,
    cli_env: str,
) -> None:
    created = _create_key_via_cli(runner, cli_env, json_output=True)

    payload = json.loads(created.output)
    assert payload["plaintext_key"] == created.plaintext_key
    assert created.output.count(created.plaintext_key) == 1
    assert payload["public_key_id"] == created.public_key_id
    _assert_safe_output(created.output, created.plaintext_key)


def test_keys_list_and_show_emit_safe_metadata(
    runner: CliRunner,
    cli_env: str,
) -> None:
    created = _create_key_via_cli(runner, cli_env)

    list_result = runner.invoke(
        app,
        [
            "keys",
            "list",
            "--owner-id",
            str(created.owner_id),
            "--cohort-id",
            str(created.cohort_id),
            "--status",
            "active",
            "--limit",
            "100",
            "--json",
        ],
    )
    show_result = runner.invoke(app, ["keys", "show", str(created.gateway_key_id), "--json"])

    assert list_result.exit_code == 0, list_result.output
    assert show_result.exit_code == 0, show_result.output
    assert created.public_key_id in list_result.stdout
    assert created.public_key_id in show_result.stdout
    for output in (list_result.stdout, show_result.stdout):
        _assert_safe_output(output)
        assert created.plaintext_key not in output


def test_keys_status_transitions_mutate_database_and_write_audit(
    runner: CliRunner,
    cli_env: str,
) -> None:
    created = _create_key_via_cli(runner, cli_env)

    suspend_result = runner.invoke(
        app,
        ["keys", "suspend", str(created.gateway_key_id), "--reason", "integration suspend"],
    )
    assert suspend_result.exit_code == 0, suspend_result.output
    assert _run(_get_key(cli_env, created.gateway_key_id)).status == "suspended"

    activate_result = runner.invoke(
        app,
        ["keys", "activate", str(created.gateway_key_id), "--reason", "integration activate"],
    )
    assert activate_result.exit_code == 0, activate_result.output
    assert _run(_get_key(cli_env, created.gateway_key_id)).status == "active"

    revoke_result = runner.invoke(
        app,
        ["keys", "revoke", str(created.gateway_key_id), "--reason", "integration revoke"],
    )
    assert revoke_result.exit_code == 0, revoke_result.output
    revoked_key = _run(_get_key(cli_env, created.gateway_key_id))
    assert revoked_key.status == "revoked"
    assert revoked_key.revoked_at is not None
    assert revoked_key.revoked_reason == "integration revoke"

    for output in (suspend_result.stdout, activate_result.stdout, revoke_result.stdout):
        _assert_safe_output(output)
        assert created.plaintext_key not in output

    assert _run(_audit_count(cli_env, gateway_key_id=created.gateway_key_id, action="suspend_key")) == 1
    assert _run(_audit_count(cli_env, gateway_key_id=created.gateway_key_id, action="activate_key")) == 1
    assert _run(_audit_count(cli_env, gateway_key_id=created.gateway_key_id, action="revoke_key")) == 1

    failed_activate = runner.invoke(app, ["keys", "activate", str(created.gateway_key_id)])
    assert failed_activate.exit_code != 0
    assert "already revoked" in failed_activate.stderr
    _assert_safe_output(failed_activate.stderr)
    assert created.plaintext_key not in failed_activate.stderr


def test_keys_extend_set_limits_and_reset_usage_persist_changes(
    runner: CliRunner,
    cli_env: str,
) -> None:
    created = _create_key_via_cli(runner, cli_env)
    original_key = _run(_get_key(cli_env, created.gateway_key_id))
    new_valid_until = (original_key.valid_until + timedelta(days=7)).isoformat()

    extend_result = runner.invoke(
        app,
        [
            "keys",
            "extend",
            str(created.gateway_key_id),
            "--valid-until",
            new_valid_until,
            "--reason",
            "integration extend",
        ],
    )
    assert extend_result.exit_code == 0, extend_result.output
    assert _run(_get_key(cli_env, created.gateway_key_id)).valid_until == datetime.fromisoformat(
        new_valid_until
    )

    set_limits_result = runner.invoke(
        app,
        [
            "keys",
            "set-limits",
            str(created.gateway_key_id),
            "--cost-limit-eur",
            "1.250000000",
            "--token-limit-total",
            "250",
            "--request-limit-total",
            "5",
            "--reason",
            "integration limits",
        ],
    )
    assert set_limits_result.exit_code == 0, set_limits_result.output
    limited_key = _run(_get_key(cli_env, created.gateway_key_id))
    assert limited_key.cost_limit_eur == Decimal("1.250000000")
    assert limited_key.token_limit_total == 250
    assert limited_key.request_limit_total == 5

    ledger_count_before = _run(_prime_usage_counters(cli_env, created.gateway_key_id))
    reset_used_result = runner.invoke(
        app,
        ["keys", "reset-usage", str(created.gateway_key_id), "--reason", "integration reset used"],
    )
    assert reset_used_result.exit_code == 0, reset_used_result.output
    reset_used_key = _run(_get_key(cli_env, created.gateway_key_id))
    assert reset_used_key.cost_used_eur == Decimal("0E-9")
    assert reset_used_key.tokens_used_total == 0
    assert reset_used_key.requests_used_total == 0
    assert reset_used_key.cost_reserved_eur == Decimal("1.000000000")
    assert reset_used_key.tokens_reserved_total == 22
    assert reset_used_key.requests_reserved_total == 2
    assert _run(_usage_ledger_count(cli_env, created.gateway_key_id)) == ledger_count_before

    reset_reserved_result = runner.invoke(
        app,
        [
            "keys",
            "reset-usage",
            str(created.gateway_key_id),
            "--reset-reserved",
            "--reason",
            "integration reset reserved",
        ],
    )
    assert reset_reserved_result.exit_code == 0, reset_reserved_result.output
    assert "admin repair action" in reset_reserved_result.stdout
    reset_reserved_key = _run(_get_key(cli_env, created.gateway_key_id))
    assert reset_reserved_key.cost_reserved_eur == Decimal("0E-9")
    assert reset_reserved_key.tokens_reserved_total == 0
    assert reset_reserved_key.requests_reserved_total == 0
    assert _run(_usage_ledger_count(cli_env, created.gateway_key_id)) == ledger_count_before

    for output in (
        extend_result.stdout,
        set_limits_result.stdout,
        reset_used_result.stdout,
        reset_reserved_result.stdout,
    ):
        _assert_safe_output(output)
        assert created.plaintext_key not in output

    assert _run(_audit_count(cli_env, gateway_key_id=created.gateway_key_id, action="extend_key")) == 1
    assert _run(_audit_count(cli_env, gateway_key_id=created.gateway_key_id, action="update_key_limits")) == 1
    assert _run(_audit_count(cli_env, gateway_key_id=created.gateway_key_id, action="reset_quota")) == 2


def test_keys_rotate_revokes_old_key_and_stores_replacement_safely(
    runner: CliRunner,
    cli_env: str,
) -> None:
    created = _create_key_via_cli(runner, cli_env)

    rotate_result = runner.invoke(
        app,
        ["keys", "rotate", str(created.gateway_key_id), "--reason", "integration rotate"],
    )

    assert rotate_result.exit_code == 0, rotate_result.output
    assert "shown once" in rotate_result.stdout
    rotated = _parse_rotate_output(rotate_result.stdout)
    replacement_key = rotated["new_plaintext_key"]
    replacement_key_id = uuid.UUID(rotated["new_gateway_key_id"])
    assert replacement_key.startswith("sk-slaif-")
    _assert_safe_output(rotate_result.stdout, replacement_key)
    assert created.plaintext_key not in rotate_result.stdout

    old_key = _run(_get_key(cli_env, created.gateway_key_id))
    new_key = _run(_get_key(cli_env, replacement_key_id))
    assert old_key.status == "revoked"
    assert old_key.revoked_reason == "integration rotate"
    assert new_key.status == "active"
    assert new_key.public_key_id == rotated["new_public_key_id"]
    assert new_key.token_hash
    assert not new_key.token_hash.startswith("sk-")
    assert replacement_key not in new_key.token_hash
    assert replacement_key not in (new_key.key_hint or "")

    one_time_secret = _run(_one_time_secret_for_key(cli_env, replacement_key_id))
    assert one_time_secret.purpose == "gateway_key_rotation_email"
    assert replacement_key not in one_time_secret.encrypted_payload
    assert replacement_key not in one_time_secret.nonce

    assert _run(_audit_count(cli_env, gateway_key_id=created.gateway_key_id, action="rotate_key")) == 1
    assert (
        _run(
            _audit_count(
                cli_env,
                gateway_key_id=replacement_key_id,
                action="gateway_key_rotation_created",
            )
        )
        == 1
    )


def test_keys_rotate_keep_old_active_preserves_old_status(
    runner: CliRunner,
    cli_env: str,
) -> None:
    created = _create_key_via_cli(runner, cli_env)

    rotate_result = runner.invoke(
        app,
        [
            "keys",
            "rotate",
            str(created.gateway_key_id),
            "--keep-old-active",
            "--reason",
            "integration keep old",
            "--json",
        ],
    )

    assert rotate_result.exit_code == 0, rotate_result.output
    rotated = _parse_rotate_output(rotate_result.stdout, json_output=True)
    replacement_key = rotated["new_plaintext_key"]
    replacement_key_id = uuid.UUID(rotated["new_gateway_key_id"])
    _assert_safe_output(rotate_result.stdout, replacement_key)
    assert _run(_get_key(cli_env, created.gateway_key_id)).status == "active"
    assert _run(_get_key(cli_env, replacement_key_id)).status == "active"
    assert _run(_audit_count(cli_env, gateway_key_id=created.gateway_key_id, action="rotate_key")) == 1


def test_keys_cli_failure_cases_are_nonzero_and_safe(
    runner: CliRunner,
    cli_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _create_key_via_cli(runner, cli_env)

    invalid_uuid = runner.invoke(app, ["keys", "show", "not-a-uuid"])
    assert invalid_uuid.exit_code != 0
    _assert_safe_output(invalid_uuid.output)

    negative_limit = runner.invoke(
        app,
        ["keys", "set-limits", str(created.gateway_key_id), "--token-limit-total", "-1"],
    )
    assert negative_limit.exit_code != 0
    _assert_safe_output(negative_limit.output)
    assert created.plaintext_key not in negative_limit.output

    revoke_result = runner.invoke(
        app,
        ["keys", "revoke", str(created.gateway_key_id), "--reason", "failure setup revoke"],
    )
    assert revoke_result.exit_code == 0, revoke_result.output
    revoked_activate = runner.invoke(app, ["keys", "activate", str(created.gateway_key_id)])
    assert revoked_activate.exit_code != 0
    assert "already revoked" in revoked_activate.stderr
    _assert_safe_output(revoked_activate.stderr)
    assert created.plaintext_key not in revoked_activate.stderr

    monkeypatch.delenv("DATABASE_URL", raising=False)
    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    missing_database = runner.invoke(app, ["keys", "list"])
    assert missing_database.exit_code == 1
    assert "DATABASE_URL is not configured" in missing_database.stderr
    _assert_safe_output(missing_database.stderr)

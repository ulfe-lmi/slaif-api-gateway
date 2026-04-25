"""PostgreSQL-backed integration tests for bootstrap-record CLI commands."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.db.models import AdminUser, AuditLog, Cohort, GatewayKey, Institution, OneTimeSecret, Owner
from slaif_gateway.utils.passwords import verify_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.db_test_utils import run_alembic_upgrade_head

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for bootstrap CLI PostgreSQL integration tests",
)

TEST_HMAC_SECRET = "test-hmac-secret-for-bootstrap-cli-integration-123456"
TEST_ADMIN_SECRET = "test-admin-secret-for-bootstrap-cli-integration-123456"
TEST_OPENAI_KEY = "fake-openai-upstream-key"
TEST_OPENROUTER_KEY = "fake-openrouter-upstream-key"
FORBIDDEN_OUTPUT_MARKERS = (
    "password_hash",
    "token_hash",
    "encrypted_payload",
    "nonce",
    TEST_OPENAI_KEY,
    TEST_OPENROUTER_KEY,
)


@dataclass(frozen=True, slots=True)
class BootstrapRecords:
    admin_id: uuid.UUID
    institution_id: uuid.UUID
    cohort_id: uuid.UUID
    owner_id: uuid.UUID


@pytest.fixture(scope="session")
def cli_bootstrap_postgres_url() -> str:
    database_url = os.environ["TEST_DATABASE_URL"]
    run_alembic_upgrade_head(database_url)
    return database_url


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, cli_bootstrap_postgres_url: str) -> str:
    monkeypatch.setenv("DATABASE_URL", cli_bootstrap_postgres_url)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("GATEWAY_KEY_PREFIX", "sk-slaif-")
    monkeypatch.setenv("GATEWAY_KEY_ACCEPTED_PREFIXES", "sk-slaif-")
    monkeypatch.setenv("ACTIVE_HMAC_KEY_VERSION", "1")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", TEST_HMAC_SECRET)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", TEST_ADMIN_SECRET)
    monkeypatch.setenv("ONE_TIME_SECRET_ENCRYPTION_KEY", generate_secret_key())
    monkeypatch.setenv("OPENAI_UPSTREAM_API_KEY", TEST_OPENAI_KEY)
    monkeypatch.setenv("OPENROUTER_API_KEY", TEST_OPENROUTER_KEY)

    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    return cli_bootstrap_postgres_url


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _run(coro):
    return asyncio.run(coro)


def _unique_label(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _load_json(output: str) -> dict[str, object]:
    return json.loads(output)


def _assert_safe_output(output: str, *allowed_plaintext_keys: str) -> None:
    lowered = output.lower()
    for marker in FORBIDDEN_OUTPUT_MARKERS:
        assert marker.lower() not in lowered
    for plaintext_key in allowed_plaintext_keys:
        assert output.count(plaintext_key) == 1


async def _get_row(database_url: str, model, row_id: uuid.UUID):
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            row = await session.get(model, row_id)
            assert row is not None
            return row
    finally:
        await engine.dispose()


async def _get_admin_by_email(database_url: str, email: str) -> AdminUser:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            row = (
                await session.execute(select(AdminUser).where(AdminUser.email == email.lower()))
            ).scalar_one()
            return row
    finally:
        await engine.dispose()


async def _get_owner_by_email(database_url: str, email: str) -> Owner:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            row = (await session.execute(select(Owner).where(Owner.email == email.lower()))).scalar_one()
            return row
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
    entity_type: str,
    entity_id: uuid.UUID,
    action: str | None = None,
) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            statement = select(func.count()).select_from(AuditLog).where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            if action is not None:
                statement = statement.where(AuditLog.action == action)
            return int((await session.execute(statement)).scalar_one())
    finally:
        await engine.dispose()


def _create_institution(runner: CliRunner, *, name: str) -> uuid.UUID:
    result = runner.invoke(
        app,
        [
            "institutions",
            "create",
            "--name",
            name,
            "--country",
            "SI",
            "--notes",
            "bootstrap CLI integration",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    _assert_safe_output(result.stdout)
    return uuid.UUID(str(_load_json(result.stdout)["id"]))


def _create_cohort(runner: CliRunner, *, name: str) -> uuid.UUID:
    starts_at = datetime.now(UTC).replace(microsecond=0)
    ends_at = starts_at + timedelta(days=14)
    result = runner.invoke(
        app,
        [
            "cohorts",
            "create",
            "--name",
            name,
            "--description",
            "bootstrap CLI integration",
            "--starts-at",
            starts_at.isoformat(),
            "--ends-at",
            ends_at.isoformat(),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    _assert_safe_output(result.stdout)
    return uuid.UUID(str(_load_json(result.stdout)["id"]))


def _create_owner(
    runner: CliRunner,
    *,
    name: str,
    surname: str,
    email: str,
    institution_id: uuid.UUID,
) -> uuid.UUID:
    result = runner.invoke(
        app,
        [
            "owners",
            "create",
            "--name",
            name,
            "--surname",
            surname,
            "--email",
            email,
            "--institution-id",
            str(institution_id),
            "--notes",
            "bootstrap CLI integration",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    _assert_safe_output(result.stdout)
    return uuid.UUID(str(_load_json(result.stdout)["id"]))


def _create_bootstrap_records(runner: CliRunner) -> BootstrapRecords:
    unique = _unique_label("bootstrap-flow")
    admin_password = f"{unique}-admin-password"
    admin_email = f"{unique}-admin@example.org"
    admin_result = runner.invoke(
        app,
        [
            "admin",
            "create",
            "--email",
            admin_email,
            "--display-name",
            "Bootstrap Flow Admin",
            "--password",
            admin_password,
            "--json",
        ],
    )
    assert admin_result.exit_code == 0, admin_result.output
    _assert_safe_output(admin_result.stdout)
    assert admin_password not in admin_result.stdout

    institution_id = _create_institution(runner, name=f"SLAIF Bootstrap {unique}")
    cohort_id = _create_cohort(runner, name=f"SLAIF Workshop {unique}")
    owner_id = _create_owner(
        runner,
        name="Bootstrap",
        surname="Owner",
        email=f"{unique}-owner@example.org",
        institution_id=institution_id,
    )

    return BootstrapRecords(
        admin_id=uuid.UUID(str(_load_json(admin_result.stdout)["id"])),
        institution_id=institution_id,
        cohort_id=cohort_id,
        owner_id=owner_id,
    )


def test_admin_cli_create_reset_and_list_persist_safe_password_data(
    runner: CliRunner,
    cli_env: str,
) -> None:
    unique = _unique_label("admin-cli")
    email = f"{unique}@example.org"
    password = f"{unique}-initial-password"

    create_result = runner.invoke(
        app,
        [
            "admin",
            "create",
            "--email",
            email.upper(),
            "--display-name",
            "Integration Admin",
            "--password",
            password,
            "--superadmin",
            "--json",
        ],
    )

    assert create_result.exit_code == 0, create_result.output
    _assert_safe_output(create_result.stdout)
    assert password not in create_result.stdout
    payload = _load_json(create_result.stdout)
    admin_id = uuid.UUID(str(payload["id"]))
    assert payload["email"] == email
    assert payload["display_name"] == "Integration Admin"
    assert payload["is_superadmin"] is True

    admin_user = _run(_get_row(cli_env, AdminUser, admin_id))
    assert admin_user.email == email
    assert admin_user.display_name == "Integration Admin"
    assert admin_user.role == "superadmin"
    assert admin_user.password_hash.startswith("$argon2id$")
    assert admin_user.password_hash != password
    assert verify_admin_password(password, admin_user.password_hash)
    assert _run(
        _audit_count(
            cli_env,
            entity_type="admin_user",
            entity_id=admin_id,
            action="admin_user_created",
        )
    ) == 1

    stdin_email = f"{unique}-stdin@example.org"
    stdin_password = f"{unique}-stdin-password"
    stdin_result = runner.invoke(
        app,
        [
            "admin",
            "create",
            "--email",
            stdin_email,
            "--display-name",
            "Stdin Admin",
            "--password-stdin",
            "--json",
        ],
        input=f"{stdin_password}\n",
    )
    assert stdin_result.exit_code == 0, stdin_result.output
    _assert_safe_output(stdin_result.stdout)
    assert stdin_password not in stdin_result.stdout
    stdin_admin = _run(_get_admin_by_email(cli_env, stdin_email))
    assert verify_admin_password(stdin_password, stdin_admin.password_hash)

    new_password = f"{unique}-new-password"
    reset_result = runner.invoke(
        app,
        ["admin", "reset-password", email, "--password-stdin", "--json"],
        input=f"{new_password}\n",
    )
    assert reset_result.exit_code == 0, reset_result.output
    _assert_safe_output(reset_result.stdout)
    assert new_password not in reset_result.stdout
    reset_admin = _run(_get_row(cli_env, AdminUser, admin_id))
    assert reset_admin.password_hash != admin_user.password_hash
    assert verify_admin_password(new_password, reset_admin.password_hash)
    assert not verify_admin_password(password, reset_admin.password_hash)
    assert _run(
        _audit_count(
            cli_env,
            entity_type="admin_user",
            entity_id=admin_id,
            action="admin_user_password_reset",
        )
    ) == 1

    list_result = runner.invoke(app, ["admin", "list", "--limit", "100", "--json"])
    assert list_result.exit_code == 0, list_result.output
    _assert_safe_output(list_result.stdout)
    assert email in list_result.stdout
    assert password not in list_result.stdout
    assert new_password not in list_result.stdout


def test_institution_cli_create_list_show_and_duplicate_error(
    runner: CliRunner,
    cli_env: str,
) -> None:
    unique = _unique_label("institution-cli")
    institution_name = f"SLAIF Integration {unique}"
    institution_id = _create_institution(runner, name=institution_name)

    institution = _run(_get_row(cli_env, Institution, institution_id))
    assert institution.name == institution_name
    assert institution.country == "SI"
    assert _run(
        _audit_count(
            cli_env,
            entity_type="institution",
            entity_id=institution_id,
            action="institution_created",
        )
    ) == 1

    list_result = runner.invoke(app, ["institutions", "list", "--limit", "100", "--json"])
    show_by_id = runner.invoke(app, ["institutions", "show", str(institution_id), "--json"])
    show_by_name = runner.invoke(app, ["institutions", "show", institution_name, "--json"])

    for result in (list_result, show_by_id, show_by_name):
        assert result.exit_code == 0, result.output
        _assert_safe_output(result.stdout)
        assert institution_name in result.stdout

    duplicate = runner.invoke(
        app,
        ["institutions", "create", "--name", institution_name, "--json"],
    )
    assert duplicate.exit_code != 0
    _assert_safe_output(duplicate.output)
    assert "already exists" in duplicate.output


def test_cohort_cli_create_list_show_and_safe_failures(
    runner: CliRunner,
    cli_env: str,
) -> None:
    unique = _unique_label("cohort-cli")
    cohort_name = f"SLAIF Workshop {unique}"
    starts_at = datetime.now(UTC).replace(microsecond=0)
    ends_at = starts_at + timedelta(days=7)

    create_result = runner.invoke(
        app,
        [
            "cohorts",
            "create",
            "--name",
            cohort_name,
            "--description",
            "cohort integration",
            "--starts-at",
            starts_at.isoformat(),
            "--ends-at",
            ends_at.isoformat(),
            "--json",
        ],
    )
    assert create_result.exit_code == 0, create_result.output
    _assert_safe_output(create_result.stdout)
    payload = _load_json(create_result.stdout)
    cohort_id = uuid.UUID(str(payload["id"]))

    cohort = _run(_get_row(cli_env, Cohort, cohort_id))
    assert cohort.name == cohort_name
    assert cohort.description == "cohort integration"
    assert cohort.starts_at is not None
    assert cohort.ends_at is not None
    assert _run(
        _audit_count(cli_env, entity_type="cohort", entity_id=cohort_id, action="cohort_created")
    ) == 1

    list_result = runner.invoke(app, ["cohorts", "list", "--limit", "100", "--json"])
    show_result = runner.invoke(app, ["cohorts", "show", str(cohort_id), "--json"])
    for result in (list_result, show_result):
        assert result.exit_code == 0, result.output
        _assert_safe_output(result.stdout)
        assert cohort_name in result.stdout

    invalid_time = runner.invoke(
        app,
        [
            "cohorts",
            "create",
            "--name",
            f"{cohort_name}-invalid",
            "--starts-at",
            starts_at.isoformat(),
            "--ends-at",
            starts_at.isoformat(),
            "--json",
        ],
    )
    assert invalid_time.exit_code != 0
    _assert_safe_output(invalid_time.output)
    assert "ends_at must be after starts_at" in invalid_time.output

    unsupported_institution = runner.invoke(
        app,
        ["cohorts", "list", "--institution-id", str(uuid.uuid4()), "--json"],
    )
    assert unsupported_institution.exit_code != 0
    _assert_safe_output(unsupported_institution.output)
    assert "not linked to institutions" in unsupported_institution.output


def test_owner_cli_create_list_show_and_duplicate_error(
    runner: CliRunner,
    cli_env: str,
) -> None:
    unique = _unique_label("owner-cli")
    institution_id = _create_institution(runner, name=f"SLAIF Owner Institution {unique}")
    email = f"{unique}@example.org"
    owner_id = _create_owner(
        runner,
        name="Owner",
        surname="Integration",
        email=email.upper(),
        institution_id=institution_id,
    )

    owner = _run(_get_row(cli_env, Owner, owner_id))
    assert owner.name == "Owner"
    assert owner.surname == "Integration"
    assert owner.email == email
    assert owner.institution_id == institution_id
    assert _run(_get_owner_by_email(cli_env, email)).id == owner_id
    assert _run(
        _audit_count(cli_env, entity_type="owner", entity_id=owner_id, action="owner_created")
    ) == 1

    list_result = runner.invoke(
        app,
        ["owners", "list", "--institution-id", str(institution_id), "--limit", "100", "--json"],
    )
    list_by_email = runner.invoke(app, ["owners", "list", "--email", email, "--json"])
    show_by_id = runner.invoke(app, ["owners", "show", str(owner_id), "--json"])
    show_by_email = runner.invoke(app, ["owners", "show", email, "--json"])

    for result in (list_result, list_by_email, show_by_id, show_by_email):
        assert result.exit_code == 0, result.output
        _assert_safe_output(result.stdout)
        assert email in result.stdout

    duplicate = runner.invoke(
        app,
        [
            "owners",
            "create",
            "--name",
            "Duplicate",
            "--surname",
            "Owner",
            "--email",
            email,
            "--json",
        ],
    )
    assert duplicate.exit_code != 0
    _assert_safe_output(duplicate.output)
    assert "already exists" in duplicate.output


def test_bootstrap_cli_records_can_issue_gateway_key(
    runner: CliRunner,
    cli_env: str,
) -> None:
    records = _create_bootstrap_records(runner)

    key_result = runner.invoke(
        app,
        [
            "keys",
            "create",
            "--owner-id",
            str(records.owner_id),
            "--cohort-id",
            str(records.cohort_id),
            "--valid-days",
            "30",
            "--cost-limit-eur",
            "7.500000000",
            "--token-limit-total",
            "1000",
            "--request-limit-total",
            "25",
            "--allowed-model",
            "gpt-test-mini",
            "--allowed-endpoint",
            "/v1/chat/completions",
            "--reason",
            "bootstrap integration key",
            "--json",
        ],
    )

    assert key_result.exit_code == 0, key_result.output
    payload = _load_json(key_result.stdout)
    plaintext_key = str(payload["plaintext_key"])
    gateway_key_id = uuid.UUID(str(payload["gateway_key_id"]))
    assert plaintext_key.startswith("sk-slaif-")
    _assert_safe_output(key_result.stdout, plaintext_key)

    gateway_key = _run(_get_row(cli_env, GatewayKey, gateway_key_id))
    assert gateway_key.owner_id == records.owner_id
    assert gateway_key.cohort_id == records.cohort_id
    assert gateway_key.token_hash
    assert not gateway_key.token_hash.startswith("sk-")
    assert gateway_key.token_hash != plaintext_key
    assert plaintext_key not in gateway_key.token_hash
    assert plaintext_key not in (gateway_key.key_hint or "")

    one_time_secret = _run(_one_time_secret_for_key(cli_env, gateway_key_id))
    assert one_time_secret.encrypted_payload
    assert one_time_secret.nonce
    assert plaintext_key not in one_time_secret.encrypted_payload
    assert plaintext_key not in one_time_secret.nonce

    assert _run(
        _audit_count(
            cli_env,
            entity_type="admin_user",
            entity_id=records.admin_id,
            action="admin_user_created",
        )
    ) == 1
    assert _run(
        _audit_count(
            cli_env,
            entity_type="gateway_key",
            entity_id=gateway_key_id,
            action="gateway_key_created",
        )
    ) == 1


def test_bootstrap_cli_failures_are_nonzero_and_safe(
    runner: CliRunner,
    cli_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unique = _unique_label("bootstrap-failures")
    admin_email = f"{unique}@example.org"
    admin_password = f"{unique}-password"
    create_result = runner.invoke(
        app,
        [
            "admin",
            "create",
            "--email",
            admin_email,
            "--display-name",
            "Failure Admin",
            "--password",
            admin_password,
        ],
    )
    assert create_result.exit_code == 0, create_result.output
    _assert_safe_output(create_result.stdout)
    assert admin_password not in create_result.stdout

    duplicate_admin = runner.invoke(
        app,
        [
            "admin",
            "create",
            "--email",
            admin_email,
            "--display-name",
            "Duplicate Admin",
            "--password",
            admin_password,
            "--json",
        ],
    )
    assert duplicate_admin.exit_code != 0
    _assert_safe_output(duplicate_admin.output)
    assert admin_password not in duplicate_admin.output
    assert "already exists" in duplicate_admin.output

    invalid_owner_uuid = runner.invoke(
        app,
        [
            "owners",
            "create",
            "--name",
            "Invalid",
            "--surname",
            "Owner",
            "--email",
            f"{unique}-invalid-owner@example.org",
            "--institution-id",
            "not-a-uuid",
            "--json",
        ],
    )
    assert invalid_owner_uuid.exit_code != 0
    _assert_safe_output(invalid_owner_uuid.output)

    monkeypatch.delenv("DATABASE_URL", raising=False)
    from slaif_gateway.config import get_settings

    get_settings.cache_clear()
    missing_database = runner.invoke(app, ["admin", "list", "--json"])
    assert missing_database.exit_code == 1
    assert "DATABASE_URL is not configured" in missing_database.output
    _assert_safe_output(missing_database.output)

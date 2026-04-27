"""PostgreSQL-backed integration tests for ``slaif-gateway usage`` reports."""

from __future__ import annotations

import asyncio
import csv
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.db_test_utils import run_alembic_upgrade_head

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for CLI usage PostgreSQL integration tests",
)

SAFE_HMAC_SECRET = "test-hmac-secret-for-cli-usage-integration-123456"
SAFE_ADMIN_SECRET = "test-admin-secret-for-cli-usage-integration-123456"
FORBIDDEN_OUTPUT_TERMS = (
    "real-provider-secret",
    "fake-openai-upstream-key",
    "fake-openrouter-upstream-key",
    "sk-slaif-secret-output",
    "token_hash",
    "encrypted_payload",
    "nonce",
    "password_hash",
    "prompt secret",
    "completion secret",
)


@dataclass(frozen=True, slots=True)
class UsageContext:
    key_id: uuid.UUID
    other_key_id: uuid.UUID
    owner_id: uuid.UUID
    cohort_id: uuid.UUID


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
    monkeypatch.setenv("TOKEN_HMAC_SECRET_V1", SAFE_HMAC_SECRET)
    monkeypatch.setenv("ADMIN_SESSION_SECRET", SAFE_ADMIN_SECRET)
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


async def _seed_usage_records(database_url: str) -> UsageContext:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    unique = _unique_label("cli-usage")
    now = datetime.now(UTC)

    try:
        async with session_factory() as session:
            institutions = InstitutionsRepository(session)
            cohorts = CohortsRepository(session)
            owners = OwnersRepository(session)
            keys = GatewayKeysRepository(session)
            usage = UsageLedgerRepository(session)

            institution = await institutions.create_institution(
                name=f"SLAIF Usage Integration {unique}",
                country="SI",
                notes="usage CLI integration institution",
            )
            cohort = await cohorts.create_cohort(
                name=unique,
                description="usage CLI integration cohort",
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=30),
            )
            owner = await owners.create_owner(
                name="Usage",
                surname="Reporter",
                email=f"{unique}@example.org",
                institution_id=institution.id,
                notes="usage CLI integration owner",
            )
            key = await keys.create_gateway_key_record(
                public_key_id=f"k_{unique.replace('-', '_')}",
                token_hash=f"hmac-sha256:{unique}",
                owner_id=owner.id,
                cohort_id=cohort.id,
                valid_from=now - timedelta(days=1),
                valid_until=now + timedelta(days=30),
                status="active",
                key_hint="...safe",
            )
            other_key = await keys.create_gateway_key_record(
                public_key_id=f"k_other_{unique.replace('-', '_')}",
                token_hash=f"hmac-sha256:other-{unique}",
                owner_id=owner.id,
                cohort_id=cohort.id,
                valid_from=now - timedelta(days=1),
                valid_until=now + timedelta(days=30),
                status="active",
                key_hint="...safe",
            )

            await usage.create_success_record(
                request_id=f"{unique}-success",
                gateway_key_id=key.id,
                owner_id=owner.id,
                institution_id=institution.id,
                cohort_id=cohort.id,
                owner_email_snapshot=owner.email,
                owner_name_snapshot=owner.name,
                owner_surname_snapshot=owner.surname,
                institution_name_snapshot=institution.name,
                cohort_name_snapshot=cohort.name,
                endpoint="/v1/chat/completions",
                provider="openai",
                requested_model="gpt-test-mini",
                resolved_model="gpt-test-mini",
                upstream_request_id=f"upstream-{unique}",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                cached_tokens=2,
                reasoning_tokens=1,
                estimated_cost_eur=Decimal("0.010000000"),
                actual_cost_eur=Decimal("0.008000000"),
                actual_cost_native=Decimal("0.008000000"),
                native_currency="EUR",
                usage_raw={"prompt": "prompt secret must not export"},
                response_metadata={"completion": "completion secret must not export"},
                started_at=now - timedelta(minutes=5),
                finished_at=now - timedelta(minutes=4),
            )
            await usage.create_failure_record(
                request_id=f"{unique}-failure",
                gateway_key_id=key.id,
                owner_id=owner.id,
                institution_id=institution.id,
                cohort_id=cohort.id,
                owner_email_snapshot=owner.email,
                owner_name_snapshot=owner.name,
                owner_surname_snapshot=owner.surname,
                institution_name_snapshot=institution.name,
                cohort_name_snapshot=cohort.name,
                endpoint="/v1/chat/completions",
                provider="openai",
                requested_model="gpt-test-mini",
                resolved_model="gpt-test-mini",
                http_status=502,
                error_type="provider_error",
                error_message="safe upstream failure",
                prompt_tokens=3,
                completion_tokens=0,
                total_tokens=3,
                estimated_cost_eur=Decimal("0.002000000"),
                actual_cost_eur=None,
                native_currency="EUR",
                usage_raw={"request_body": "prompt secret must not export"},
                response_metadata={"response_body": "completion secret must not export"},
                started_at=now - timedelta(minutes=3),
                finished_at=now - timedelta(minutes=2),
            )
            await usage.create_success_record(
                request_id=f"{unique}-other",
                gateway_key_id=other_key.id,
                owner_id=owner.id,
                institution_id=institution.id,
                cohort_id=cohort.id,
                owner_email_snapshot=owner.email,
                owner_name_snapshot=owner.name,
                owner_surname_snapshot=owner.surname,
                institution_name_snapshot=institution.name,
                cohort_name_snapshot=cohort.name,
                endpoint="/v1/chat/completions",
                provider="local-test",
                requested_model="other-model",
                resolved_model="other-model",
                prompt_tokens=7,
                completion_tokens=4,
                total_tokens=11,
                estimated_cost_eur=Decimal("0.004000000"),
                actual_cost_eur=Decimal("0.003000000"),
                native_currency="EUR",
                started_at=now - timedelta(minutes=1),
                finished_at=now,
            )
            await session.commit()
            return UsageContext(
                key_id=key.id,
                other_key_id=other_key.id,
                owner_id=owner.id,
                cohort_id=cohort.id,
            )
    finally:
        await engine.dispose()


def _assert_safe_output(output: str) -> None:
    lowered = output.lower()
    for term in FORBIDDEN_OUTPUT_TERMS:
        assert term.lower() not in lowered


def test_usage_summarize_and_export_against_postgres(
    runner: CliRunner,
    cli_env: str,
    tmp_path,
) -> None:
    context = _run(_seed_usage_records(cli_env))

    summary = runner.invoke(
        app,
        [
            "usage",
            "summarize",
            "--provider",
            "openai",
            "--model",
            "gpt-test-mini",
            "--key-id",
            str(context.key_id),
            "--group-by",
            "provider_model",
            "--json",
        ],
    )
    assert summary.exit_code == 0, summary.output
    _assert_safe_output(summary.stdout)
    summary_payload = json.loads(summary.stdout)["usage_summary"]
    row = next(item for item in summary_payload if item["grouping_key"] == "openai:gpt-test-mini")
    assert row["request_count"] == 2
    assert row["success_count"] == 1
    assert row["failure_count"] == 1
    assert row["prompt_tokens"] == 13
    assert row["completion_tokens"] == 5
    assert row["total_tokens"] == 18
    assert row["estimated_cost_eur"] == "0.012000000"
    assert row["actual_cost_eur"] == "0.008000000"

    text_summary = runner.invoke(app, ["usage", "summarize", "--key-id", str(context.key_id)])
    assert text_summary.exit_code == 0, text_summary.output
    assert "openai:gpt-test-mini" in text_summary.stdout
    _assert_safe_output(text_summary.stdout)

    csv_export = runner.invoke(
        app,
        [
            "usage",
            "export",
            "--format",
            "csv",
            "--owner-id",
            str(context.owner_id),
            "--cohort-id",
            str(context.cohort_id),
            "--key-id",
            str(context.key_id),
        ],
    )
    assert csv_export.exit_code == 0, csv_export.output
    _assert_safe_output(csv_export.stdout)
    csv_rows = list(csv.DictReader(csv_export.stdout.splitlines()))
    assert len(csv_rows) == 2
    assert csv_rows[0]["request_id"].endswith("-success")
    assert csv_rows[0]["actual_cost_eur"] == "0.008000000"
    assert csv_rows[1]["accounting_status"] == "failed"

    json_export = runner.invoke(
        app,
        [
            "usage",
            "export",
            "--format",
            "json",
            "--provider",
            "openai",
            "--model",
            "gpt-test-mini",
            "--key-id",
            str(context.key_id),
        ],
    )
    assert json_export.exit_code == 0, json_export.output
    _assert_safe_output(json_export.stdout)
    json_rows = json.loads(json_export.stdout)
    assert {item["accounting_status"] for item in json_rows} == {"finalized", "failed"}
    assert all(item["gateway_key_id"] == str(context.key_id) for item in json_rows)

    output_path = tmp_path / "usage.csv"
    write_result = runner.invoke(
        app,
        ["usage", "export", "--format", "csv", "--key-id", str(context.key_id), "--output", str(output_path)],
    )
    assert write_result.exit_code == 0, write_result.output
    assert output_path.exists()
    _assert_safe_output(output_path.read_text(encoding="utf-8"))

    existing_result = runner.invoke(
        app,
        ["usage", "export", "--format", "csv", "--key-id", str(context.key_id), "--output", str(output_path)],
    )
    assert existing_result.exit_code == 1
    assert "already exists" in existing_result.stderr

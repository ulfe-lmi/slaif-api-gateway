"""Owned PostgreSQL 16 evidence for owner/cohort partial edits (204-b).

Acceptance A: actual Typer entrypoint owner move through the real CLI
preserves every omitted metadata/flag and all existing key/material
state, applies supported clears/conflicts, refuses duplicate/invalid
email, unknown IDs/institution, no-field/blank-reason/actor errors,
writes ONE exact existing audit, and a late audit fault rolls back the
row and the provisional audit.

Acceptance B: actual cohort partial edits and clears preserve
unrequested fields and member keys; invalid FINAL merged date windows
refuse with zero changes/audits; name normalization/duplicate/unknown/
naive-time handling is honest; no cohort-institution association.

Acceptance C: controlled actual-PG causal lock-wait for BOTH record
types (competitor owns the row BEFORE the updater starts; exact holder/
waiter observation through pg_blocking_pids + fresh pg statistics with
pg_stat_clear_snapshot before each poll; no sleeps alone). The updater
merges AFTER the fresh populated lock read and preserves the committed
omitted field; the audit old/new reflects the latest stored row.

Owned PG discipline: unique labeled postgres:16 container, loopback
bind, tmpfs data dir, exact created ID/ownership inspected BEFORE any
migration, exact container removed in finally.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from slaif_gateway.cli.main import app
from slaif_gateway.config import get_settings
from slaif_gateway.db.models import AdminUser, Cohort, Institution, Owner
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.schemas.record_edits import (
    parse_cohort_update_patch,
    parse_owner_update_patch,
)
from slaif_gateway.services.cohort_service import CohortService
from slaif_gateway.services.owner_service import OwnerService
from tests.integration.db_test_utils import run_alembic_upgrade_head

_OWNER_PREFIX = "slaif204b"

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

TEST_HMAC_SECRET = "test-hmac-secret-for-cli-record-edits-204b"
TEST_ADMIN_SECRET = "test-admin-secret-for-cli-record-edits-204b"

_runner = CliRunner()


# --- owned PostgreSQL 16 fixture (ownership discipline) ---------------------


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
    from slaif_gateway.utils.secrets import generate_secret_key

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


async def _seed_institution(url: str, name: str) -> uuid.UUID:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            inst = Institution(id=uuid.uuid4(), name=name, country="SI")
            session.add(inst)
            await session.flush()
            return inst.id


async def _seed_owner(
    url: str,
    *,
    name: str,
    surname: str,
    email: str,
    institution_id: uuid.UUID | None,
    external_id: str | None,
    notes: str | None,
    is_active: bool,
) -> uuid.UUID:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            owner = Owner(
                id=uuid.uuid4(),
                name=name,
                surname=surname,
                email=email,
                institution_id=institution_id,
                external_id=external_id,
                notes=notes,
                is_active=is_active,
            )
            session.add(owner)
            await session.flush()
            return owner.id


async def _seed_cohort(
    url: str,
    *,
    name: str,
    description: str | None,
    starts_at: datetime | None,
    ends_at: datetime | None,
) -> uuid.UUID:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            cohort = Cohort(
                id=uuid.uuid4(),
                name=name,
                description=description,
                starts_at=starts_at,
                ends_at=ends_at,
            )
            session.add(cohort)
            await session.flush()
            return cohort.id


async def _seed_admin(url: str) -> uuid.UUID:
    factory = _session_factory(url)
    async with factory() as session:
        async with session.begin():
            admin = AdminUser(
                id=uuid.uuid4(),
                email=f"admin-{uuid.uuid4().hex}@example.org",
                display_name="204b Admin",
                password_hash="204b-synthetic-never-used-for-auth",
                role="admin",
            )
            session.add(admin)
            await session.flush()
            return admin.id


def _create_key_cli(
    owner_id: uuid.UUID,
    *,
    cohort_id: uuid.UUID | None,
) -> uuid.UUID:
    """Create ONE key through the ACTUAL CLI entrypoint (real SQL)."""
    args = [
        "keys", "create",
        "--owner-id", str(owner_id),
        "--valid-from", "2026-06-01T00:00:00+00:00",
        "--valid-until", "2027-06-01T00:00:00+00:00",
        "--reason", "204b integration seed",
        "--allow-all-models",
        "--allow-all-endpoints",
        "--request-limit-total", "100",
        "--json", "--show-plaintext",
    ]
    if cohort_id is not None:
        args += ["--cohort-id", str(cohort_id)]
    result = _runner.invoke(app, args, env={"NO_COLOR": "1"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    return uuid.UUID(payload["gateway_key_id"])


async def _owner_row(url: str, owner_id: uuid.UUID) -> dict[str, object]:
    factory = _session_factory(url)
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT name, surname, email, institution_id, external_id,"
                    " notes, is_active FROM owners WHERE id = :o"
                ),
                {"o": owner_id},
            )
        ).mappings().one()
        return dict(row)


async def _cohort_row(url: str, cohort_id: uuid.UUID) -> dict[str, object]:
    factory = _session_factory(url)
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT name, description, starts_at, ends_at"
                    " FROM cohorts WHERE id = :c"
                ),
                {"c": cohort_id},
            )
        ).mappings().one()
        return dict(row)


async def _key_row(url: str, key_id: uuid.UUID) -> dict[str, object]:
    factory = _session_factory(url)
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT public_key_id, token_hash, owner_id, cohort_id,"
                    " status, valid_from, valid_until, request_limit_total,"
                    " tokens_used_total, requests_used_total, cost_used_eur,"
                    " hmac_key_version"
                    " FROM gateway_keys WHERE id = :k"
                ),
                {"k": key_id},
            )
        ).mappings().one()
        return dict(row)


async def _record_audits(
    url: str, entity_type: str, entity_id: uuid.UUID
) -> list[dict[str, object]]:
    factory = _session_factory(url)
    async with factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT action, entity_type, entity_id, admin_user_id,"
                    " old_values, new_values, note"
                    " FROM audit_log"
                    " WHERE entity_type = :t AND entity_id = :e"
                    " ORDER BY created_at, id"
                ),
                {"t": entity_type, "e": entity_id},
            )
        ).mappings().all()
        return [dict(row) for row in rows]


# --- A: owner partial edits ---------------------------------------------------


def test_owner_move_preserves_omitted_fields_keys_material_and_usage(
    cli_env: str,
) -> None:
    url = cli_env
    inst1 = _run(_seed_institution(url, "204b Institute One"))
    inst2 = _run(_seed_institution(url, "204b Institute Two"))
    owner_id = _run(
        _seed_owner(
            url, name="Ada", surname="Lovelace",
            email=f"ada-{uuid.uuid4().hex[:8]}@example.org",
            institution_id=inst1, external_id="ext-orig",
            notes="orig note", is_active=False,
        )
    )
    admin_id = _run(_seed_admin(url))
    key_id = _create_key_cli(owner_id, cohort_id=None)
    before_owner = _run(_owner_row(url, owner_id))
    before_key = _run(_key_row(url, key_id))

    result = _runner.invoke(
        app,
        [
            "owners", "update", str(owner_id),
            "--institution-id", str(inst2),
            "--reason", "move owner to institute two",
            "--actor-admin-id", str(admin_id),
            "--json",
        ],
        env={"NO_COLOR": "1"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["id"] == str(owner_id)
    assert payload["name"] == before_owner["name"]
    assert payload["surname"] == before_owner["surname"]
    assert payload["email"] == before_owner["email"]
    assert payload["institution_id"] == str(inst2)
    # Omitted nullable fields preserved, including is_active=False.
    assert payload["external_id"] == "ext-orig"
    assert payload["notes"] == "orig note"
    assert payload["is_active"] is False

    after_owner = _run(_owner_row(url, owner_id))
    assert after_owner["institution_id"] == inst2
    assert after_owner["external_id"] == "ext-orig"
    assert after_owner["notes"] == "orig note"
    assert after_owner["is_active"] is False

    # Existing key material/state untouched by the owner move.
    after_key = _run(_key_row(url, key_id))
    assert after_key == before_key

    audits = _run(_record_audits(url, "owner", owner_id))
    assert len(audits) == 1
    audit = audits[0]
    assert audit["action"] == "owner_updated"
    assert audit["admin_user_id"] == admin_id
    assert audit["note"] == "move owner to institute two"
    assert audit["old_values"]["institution_id"] == str(inst1)
    assert audit["new_values"]["institution_id"] == str(inst2)
    assert audit["old_values"]["notes"] == "orig note"
    assert audit["new_values"]["notes"] == "orig note"
    assert audit["old_values"]["is_active"] is False


def test_owner_clears_conflicts_and_active_flag(cli_env: str) -> None:
    url = cli_env
    inst1 = _run(_seed_institution(url, "204b Institute Three"))
    owner_id = _run(
        _seed_owner(
            url, name="Bo", surname="B", email=f"bo-{uuid.uuid4().hex[:8]}@example.org",
            institution_id=inst1, external_id="ext-b", notes="notes-b",
            is_active=True,
        )
    )

    result = _runner.invoke(
        app,
        [
            "owners", "update", str(owner_id),
            "--clear-institution", "--clear-external-id", "--clear-notes",
            "--inactive", "--reason", "clear nullable fields", "--json",
        ],
        env={"NO_COLOR": "1"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["institution_id"] is None
    assert payload["external_id"] is None
    assert payload["notes"] is None
    assert payload["is_active"] is False
    assert payload["name"] == "Bo"
    assert len(_run(_record_audits(url, "owner", owner_id))) == 1

    # reactivate through the tri-state flag
    result = _runner.invoke(
        app,
        ["owners", "update", str(owner_id), "--active",
         "--reason", "reactivate", "--json"],
        env={"NO_COLOR": "1"},
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["is_active"] is True

    # replace+clear conflict: refused before any write/audit
    audits_before = _run(_record_audits(url, "owner", owner_id))
    row_before = _run(_owner_row(url, owner_id))
    result = _runner.invoke(
        app,
        ["owners", "update", str(owner_id),
         "--external-id", "ext-new", "--clear-external-id",
         "--reason", "conflict", "--json"],
        env={"NO_COLOR": "1"},
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "invalid_value"
    assert _run(_owner_row(url, owner_id)) == row_before
    assert _run(_record_audits(url, "owner", owner_id)) == audits_before

    result = _runner.invoke(
        app,
        ["owners", "update", str(owner_id), "--active", "--inactive",
         "--reason", "conflict", "--json"],
        env={"NO_COLOR": "1"},
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "invalid_value"


def test_owner_refusals_keep_row_and_audits_unchanged(cli_env: str) -> None:
    url = cli_env
    inst1 = _run(_seed_institution(url, "204b Institute Four"))
    owner_id = _run(
        _seed_owner(
            url, name="Ci", surname="C", email=f"ci-{uuid.uuid4().hex[:8]}@example.org",
            institution_id=inst1, external_id=None, notes=None, is_active=True,
        )
    )
    twin_id = _run(
        _seed_owner(
            url, name="Twin", surname="T",
            email=f"twin-{uuid.uuid4().hex[:8]}@example.org",
            institution_id=None, external_id=None, notes=None, is_active=True,
        )
    )
    twin_email = _run(_owner_row(url, twin_id))["email"]
    row_before = _run(_owner_row(url, owner_id))

    cases = [
        # duplicate normalized email
        (["owners", "update", str(owner_id), "--email", str(twin_email).upper(),
          "--reason", "steal email", "--json"],
         "duplicate_record", "Owner with this email already exists"),
        # unknown institution
        (["owners", "update", str(owner_id),
          "--institution-id", str(uuid.uuid4()), "--reason", "x", "--json"],
         "record_not_found", "Institution not found"),
        # unknown owner id
        (["owners", "update", str(uuid.uuid4()), "--name", "n",
          "--reason", "x", "--json"],
         "record_not_found", "Owner not found"),
        # no-field patch
        (["owners", "update", str(owner_id), "--reason", "x", "--json"],
         "invalid_value", "at least one field"),
        # blank required reason
        (["owners", "update", str(owner_id), "--name", "n", "--reason", "  ",
          "--json"],
         "invalid_value", "audit reason"),
        # invalid actor UUID
        (["owners", "update", str(owner_id), "--name", "n",
          "--actor-admin-id", "nope", "--reason", "x", "--json"],
         "invalid_value", "valid UUID"),
    ]
    for args, code, message in cases:
        result = _runner.invoke(app, args, env={"NO_COLOR": "1"})
        assert result.exit_code == 1, (args, result.output)
        payload = json.loads(result.stdout)
        assert payload["error"]["code"] == code, (args, payload)
        assert message in payload["error"]["message"], (args, payload)
        assert _run(_owner_row(url, owner_id)) == row_before

    # a recognized-secret-shape value is refused without echo
    canary = "sk-proj-canary204bpg000000000000"
    result = _runner.invoke(
        app,
        ["owners", "update", str(owner_id), "--notes", canary,
         "--reason", "x", "--json"],
        env={"NO_COLOR": "1"},
    )
    assert result.exit_code == 1
    assert (
        json.loads(result.stdout)["error"]["code"] == "invalid_value"
    )
    assert canary not in result.stdout
    assert canary not in (result.stderr or "")
    assert _run(_owner_row(url, owner_id)) == row_before
    # every refusal above produced ZERO owner audits
    assert _run(_record_audits(url, "owner", owner_id)) == []


def test_owner_late_audit_failure_rolls_back_row_and_audit(cli_env: str) -> None:
    url = cli_env
    owner_id = _run(
        _seed_owner(
            url, name="De", surname="D",
            email=f"de-{uuid.uuid4().hex[:8]}@example.org",
            institution_id=None, external_id="ext-before", notes=None,
            is_active=True,
        )
    )
    row_before = _run(_owner_row(url, owner_id))

    class _BoomAuditRepository(AuditRepository):
        """Controlled fault injection: raises on the first audit write."""

        async def add_audit_log(self, **kwargs: object) -> None:
            raise RuntimeError("injected late audit failure (204b test)")

    async def _scenario() -> None:
        factory = _session_factory(url)
        async with factory() as session:
            service = OwnerService(
                owners_repository=OwnersRepository(session),
                institutions_repository=InstitutionsRepository(session),
                audit_repository=_BoomAuditRepository(session),
            )
            patch, _, reason = parse_owner_update_patch(
                name=None, surname=None, email=None, institution_id=None,
                clear_institution=False, external_id="ext-after",
                clear_external_id=False, notes=None, clear_notes=False,
                active=False, inactive=False, actor_admin_id=None,
                reason="late audit boom",
            )
            # The fault must PROPAGATE out of the begin block so the
            # caller-owned transaction ROLLS BACK (row + audit).
            with pytest.raises(RuntimeError, match="injected late audit failure"):
                async with session.begin():
                    await service.update_owner_partial(
                        owner_id, patch=patch, reason=reason
                    )

    _run(_scenario())

    # The row and the provisional audit BOTH rolled back.
    assert _run(_owner_row(url, owner_id)) == row_before
    assert _run(_record_audits(url, "owner", owner_id)) == []


# --- B: cohort partial edits --------------------------------------------------


def test_cohort_partial_preserves_unrequested_fields_and_member_keys(
    cli_env: str,
) -> None:
    url = cli_env
    starts = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    ends = datetime(2026, 12, 31, 10, 0, 0, tzinfo=UTC)
    cohort_id = _run(
        _seed_cohort(url, name=f"204b-Group-{uuid.uuid4().hex[:8]}",
                     description="original", starts_at=starts, ends_at=ends)
    )
    owner_id = _run(
        _seed_owner(
            url, name="Me", surname="M",
            email=f"me-{uuid.uuid4().hex[:8]}@example.org",
            institution_id=None, external_id=None, notes=None, is_active=True,
        )
    )
    key_id = _create_key_cli(owner_id, cohort_id=cohort_id)
    before_key = _run(_key_row(url, key_id))

    result = _runner.invoke(
        app,
        ["cohorts", "update", str(cohort_id),
         "--description", "updated description",
         "--reason", "edit description", "--json"],
        env={"NO_COLOR": "1"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    row = _run(_cohort_row(url, cohort_id))
    assert row["name"] == payload["name"]
    assert row["description"] == "updated description"
    # unrequested fields preserved
    assert row["starts_at"].replace(tzinfo=None) == starts.replace(tzinfo=None)
    assert row["ends_at"].replace(tzinfo=None) == ends.replace(tzinfo=None)
    assert _run(_key_row(url, key_id)) == before_key
    audits = _run(_record_audits(url, "cohort", cohort_id))
    assert len(audits) == 1
    assert audits[0]["action"] == "cohort_updated"
    assert audits[0]["old_values"]["description"] == "original"
    assert audits[0]["new_values"]["description"] == "updated description"

    # explicit nullable clears (name is NOT nullable: no clear flag exists)
    result = _runner.invoke(
        app,
        ["cohorts", "update", str(cohort_id),
         "--clear-starts-at", "--clear-ends-at", "--clear-description",
         "--reason", "clear window", "--json"],
        env={"NO_COLOR": "1"},
    )
    assert result.exit_code == 0, result.output
    row = _run(_cohort_row(url, cohort_id))
    assert row["starts_at"] is None and row["ends_at"] is None
    assert row["description"] is None
    assert len(_run(_record_audits(url, "cohort", cohort_id))) == 2

    # naive datetime is interpreted as UTC (honest convention)
    result = _runner.invoke(
        app,
        ["cohorts", "update", str(cohort_id),
         "--starts-at", "2026-02-01T00:00:00",
         "--reason", "naive start", "--json"],
        env={"NO_COLOR": "1"},
    )
    assert result.exit_code == 0, result.output
    row = _run(_cohort_row(url, cohort_id))
    assert row["starts_at"].replace(tzinfo=None) == datetime(
        2026, 2, 1, tzinfo=UTC
    ).replace(tzinfo=None)

    # name normalization (strip) is preserved
    result = _runner.invoke(
        app,
        ["cohorts", "update", str(cohort_id),
         "--name", "   Padded 204b   ",
         "--reason", "rename padded", "--json"],
        env={"NO_COLOR": "1"},
    )
    assert result.exit_code == 0, result.output
    assert _run(_cohort_row(url, cohort_id))["name"] == "Padded 204b"


def test_cohort_merged_window_duplicate_unknown_refusals(cli_env: str) -> None:
    url = cli_env
    starts = datetime(2026, 3, 1, tzinfo=UTC)
    ends = datetime(2026, 3, 31, tzinfo=UTC)
    cohort_id = _run(
        _seed_cohort(url, name=f"204b-Win-{uuid.uuid4().hex[:8]}",
                     description=None, starts_at=starts, ends_at=ends)
    )
    other_id = _run(
        _seed_cohort(url, name=f"204b-Other-{uuid.uuid4().hex[:8]}",
                     description=None, starts_at=None, ends_at=None)
    )
    other_name = _run(_cohort_row(url, other_id))["name"]
    row_before = _run(_cohort_row(url, cohort_id))

    cases = [
        # FINAL merged window: stored starts_at still participates
        (["cohorts", "update", str(cohort_id),
          "--ends-at", "2026-02-01T00:00:00Z", "--reason", "x", "--json"],
         "invalid_value", "ends_at must be after starts_at"),
        # duplicate name (exact, after normalization)
        (["cohorts", "update", str(cohort_id), "--name", other_name,
          "--reason", "x", "--json"],
         "duplicate_record", "Cohort with this name already exists"),
        # unknown cohort
        (["cohorts", "update", str(uuid.uuid4()), "--description", "d",
          "--reason", "x", "--json"],
         "record_not_found", "Cohort not found"),
        # no-field patch
        (["cohorts", "update", str(cohort_id), "--reason", "x", "--json"],
         "invalid_value", "at least one field"),
    ]
    for args, code, message in cases:
        result = _runner.invoke(app, args, env={"NO_COLOR": "1"})
        assert result.exit_code == 1, (args, result.output)
        payload = json.loads(result.stdout)
        assert payload["error"]["code"] == code, (args, payload)
        assert message in payload["error"]["message"], (args, payload)
        assert _run(_cohort_row(url, cohort_id)) == row_before
        assert _run(_record_audits(url, "cohort", cohort_id)) == []

    # no cohort-institution association is exposed or manufactured
    help_result = _runner.invoke(
        app, ["cohorts", "update", "--help"], env={"NO_COLOR": "1"}
    )
    assert help_result.exit_code == 0
    assert "--institution-id" not in help_result.stdout


# --- C: controlled causal lock-wait -------------------------------------------


async def _wait_holder_waiter_observed(
    url: str, holder_pid: int, waiter_pid: int
) -> None:
    """Fresh autocommit observer: clear the stats snapshot before each
    poll (the holder's cached snapshot cannot see waiters) and correlate
    the EXACT causal relation through pg_blocking_pids."""
    factory = _session_factory(url)
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
                return
            await asyncio.sleep(0.2)
    raise AssertionError("causal holder/waiter relation was never observed")


def test_owner_causal_lock_wait_merges_after_fresh_locked_read(
    cli_env: str,
) -> None:
    url = cli_env
    owner_id = _run(
        _seed_owner(
            url, name="Con", surname="C",
            email=f"con-{uuid.uuid4().hex[:8]}@example.org",
            institution_id=None, external_id=None, notes="before",
            is_active=True,
        )
    )

    async def _scenario() -> None:
        factory = _session_factory(url)
        b_pid: list[int] = []
        b_release = asyncio.Event()

        async def _competitor() -> None:
            async with factory() as session:
                async with session.begin():
                    await session.execute(
                        text("SELECT id FROM owners WHERE id = :o FOR UPDATE"),
                        {"o": owner_id},
                    )
                    b_pid.append(
                        (
                            await session.execute(text("SELECT pg_backend_pid()"))
                        ).scalar_one()
                    )
                    await b_release.wait()
                    # Change an OMITTED field of the updater AFTER the
                    # causal wait is observed; commit on block exit.
                    await session.execute(
                        text(
                            "UPDATE owners SET notes = :n WHERE id = :o"
                        ),
                        {"n": "committed-by-competitor", "o": owner_id},
                    )

        a_pid: list[int] = []
        outcome: list[str] = []

        async def _updater() -> None:
            async with factory() as session:
                async with session.begin():
                    a_pid.append(
                        (
                            await session.execute(text("SELECT pg_backend_pid()"))
                        ).scalar_one()
                    )
                    service = OwnerService(
                        owners_repository=OwnersRepository(session),
                        institutions_repository=InstitutionsRepository(session),
                        audit_repository=AuditRepository(session),
                    )
                    patch, _, reason = parse_owner_update_patch(
                        name=None, surname=None, email=None,
                        institution_id=None, clear_institution=False,
                        external_id="new-ext", clear_external_id=False,
                        notes=None, clear_notes=False, active=False,
                        inactive=False, actor_admin_id=None,
                        reason="concurrent owner edit",
                    )
                    updated = await service.update_owner_partial(
                        owner_id, patch=patch, reason=reason
                    )
                    outcome.append(str(updated.external_id))

        competitor_task = asyncio.create_task(_competitor())
        # Readiness barrier: the competitor DEMONSTRABLY owns the row
        # lock BEFORE the updater is even started.
        deadline = time.monotonic() + 60
        while not b_pid and time.monotonic() < deadline:
            assert not competitor_task.done(), "competitor failed to lock the row"
            await asyncio.sleep(0.05)
        assert b_pid, "competitor did not acquire the owner row lock"

        updater_task = asyncio.create_task(_updater())
        deadline = time.monotonic() + 60
        while not a_pid and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        assert a_pid, "updater did not start"

        await _wait_holder_waiter_observed(url, b_pid[0], a_pid[0])
        # Exact causal wait observed: NOW change the omitted field and
        # commit/release in the same competitor transaction.
        await asyncio.sleep(0.2)
        b_release.set()
        await updater_task
        await competitor_task

    _run(_scenario())

    row = _run(_owner_row(url, owner_id))
    # The updater merged AFTER the fresh populated lock read: the
    # committed omitted field is preserved, the provided field applied.
    assert row["notes"] == "committed-by-competitor"
    assert row["external_id"] == "new-ext"
    audits = _run(_record_audits(url, "owner", owner_id))
    assert len(audits) == 1
    # Audit old/new reflects the LATEST stored row.
    assert audits[0]["old_values"]["notes"] == "committed-by-competitor"
    assert audits[0]["new_values"]["notes"] == "committed-by-competitor"
    assert audits[0]["old_values"]["external_id"] is None
    assert audits[0]["new_values"]["external_id"] == "new-ext"


def test_cohort_causal_lock_wait_merges_after_fresh_locked_read(
    cli_env: str,
) -> None:
    url = cli_env
    cohort_id = _run(
        _seed_cohort(
            url, name=f"204b-Lock-{uuid.uuid4().hex[:8]}",
            description="before", starts_at=None,
            ends_at=datetime(2026, 6, 30, tzinfo=UTC),
        )
    )

    async def _scenario() -> None:
        factory = _session_factory(url)
        b_pid: list[int] = []
        b_release = asyncio.Event()

        async def _competitor() -> None:
            async with factory() as session:
                async with session.begin():
                    await session.execute(
                        text("SELECT id FROM cohorts WHERE id = :c FOR UPDATE"),
                        {"c": cohort_id},
                    )
                    b_pid.append(
                        (
                            await session.execute(text("SELECT pg_backend_pid()"))
                        ).scalar_one()
                    )
                    await b_release.wait()
                    await session.execute(
                        text("UPDATE cohorts SET description = :d WHERE id = :c"),
                        {"d": "committed-desc", "c": cohort_id},
                    )

        a_pid: list[int] = []
        outcome: list[str] = []

        async def _updater() -> None:
            async with factory() as session:
                async with session.begin():
                    a_pid.append(
                        (
                            await session.execute(text("SELECT pg_backend_pid()"))
                        ).scalar_one()
                    )
                    service = CohortService(
                        cohorts_repository=CohortsRepository(session),
                        audit_repository=AuditRepository(session),
                    )
                    patch, _, reason = parse_cohort_update_patch(
                        name=None, description=None, clear_description=False,
                        starts_at=None, clear_starts_at=False,
                        ends_at="2026-12-31T00:00:00Z", clear_ends_at=False,
                        actor_admin_id=None, reason="concurrent cohort edit",
                    )
                    updated = await service.update_cohort_partial(
                        cohort_id, patch=patch, reason=reason
                    )
                    outcome.append(updated.name)

        competitor_task = asyncio.create_task(_competitor())
        deadline = time.monotonic() + 60
        while not b_pid and time.monotonic() < deadline:
            assert not competitor_task.done(), "competitor failed to lock the row"
            await asyncio.sleep(0.05)
        assert b_pid, "competitor did not acquire the cohort row lock"

        updater_task = asyncio.create_task(_updater())
        deadline = time.monotonic() + 60
        while not a_pid and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        assert a_pid, "updater did not start"

        await _wait_holder_waiter_observed(url, b_pid[0], a_pid[0])
        await asyncio.sleep(0.2)
        b_release.set()
        await updater_task
        await competitor_task

    _run(_scenario())

    row = _run(_cohort_row(url, cohort_id))
    assert row["description"] == "committed-desc"
    assert row["ends_at"].replace(tzinfo=None) == datetime(
        2026, 12, 31, tzinfo=UTC
    ).replace(tzinfo=None)
    audits = _run(_record_audits(url, "cohort", cohort_id))
    assert len(audits) == 1
    assert audits[0]["old_values"]["description"] == "committed-desc"
    assert audits[0]["new_values"]["description"] == "committed-desc"

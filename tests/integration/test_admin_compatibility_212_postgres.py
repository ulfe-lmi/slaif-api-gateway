"""212-a GUI Codex compatibility: owned PostgreSQL tests.

Real-app, real-PostgreSQL qualification for the 212-a reviewed Codex
compatibility workflow (module upgrade/rollback + 0.162 data-profile
migration) against the qualified owned, labeled, loopback-bound,
tmpfs-backed PostgreSQL fixture.  This module reuses the
``owned_pg_url`` fixture directly, which ALWAYS creates one NEW owned
container and migrates it - so this module is the SOLE PG owner of the
run (no outer runner container, no ambient TEST_DATABASE_URL reuse).

One explicit ordered scenario (file order is significant); every
oracle is scoped to THIS run's exact seeded key IDs and admin user:

- the module UPGRADE dry-run review performs NO domain/audit writes;
- the reviewed apply writes the exact target tuple plus ONE real
  session-actor/reason/tuple audit in the same transaction;
- every unrelated gateway_keys column (material, owner, restrictions,
  expiry, limits, NON-ZERO usage/reservation counters, fence state)
  and every metadata field outside the audited client_module path is
  byte-stable, proved with the accepted shared-Core full-row digest
  (id/updated_at excluded; key-row level - no actual ledger/replay
  rows are seeded or claimed);
- the exact repeat is a no-op with no new write or audit - including
  when the ORIGINAL reviewed token is re-applied after a separate
  authorized rollback/re-upgrade sequence left the key at the same
  target (another authorized action reached the target despite the
  review's older expected source);
- the module ROLLBACK returns to the exact frozen predecessor tuple
  (one audited update);
- a NON-TARGET drifted source (the key moved to an unrelated tuple
  between review and apply) is refused with zero writes/audits;
- a wrong ACTIVE tuple at apply time (the reviewer bound one active
  tuple; the worker registry resolves another) is refused by the
  shared expected-target guard before any mutation;
- the profile MIGRATION to the real bootstrap active profile applies
  one audited update and its exact repeat is a no-op;
- a late failure injected AFTER the real audit flush rolls back the
  WHOLE caller transaction (policy AND audit), and the fixed
  UNCONFIRMED outcome is rendered instead of a success; retrying the
  same reviewed token afterwards applies cleanly;
- native auth/CSRF denials (no session -> 303; valid session + wrong
  CSRF -> 400) with zero DB mutation.

No real provider/Codex request, respx mock, gateway key usage, or
ledger row is involved; the seeded keys are synthetic (never
forwarded).  All mutations go through the shared Core
``codex_module_upgrade`` law; nothing here is a separate write path.
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AuditLog, GatewayKey
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.main import create_app
from slaif_gateway.modules.clients.codex_0162 import CODEX_0162_CLIENT_MODULE_ID
from slaif_gateway.services.codex_module_upgrade import (
    CODEX_0149_V4_CLIENT_MODULE,
    UPGRADE_TARGET_CLIENT_MODULES,
    get_client_module,
)
from slaif_gateway.utils.passwords import hash_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
from tests.integration.test_codex_module_upgrade_postgres import _row_digest
from tests.integration.test_lazy_throttling_postgres_redis import (  # noqa: F401
    owned_pg_url,  # noqa: F401  (module-scoped owned-PG fixture reuse)
)

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r'name="review_token" value="([^"]+)"')

ADMIN_PASSWORD = "correct horse battery staple"

PIN_0149_V4 = dict(CODEX_0149_V4_CLIENT_MODULE)
PIN_0149_V5 = dict(UPGRADE_TARGET_CLIENT_MODULES["0149-v5"])
PIN_0162_V1 = dict(UPGRADE_TARGET_CLIENT_MODULES["0162-v1"])
PIN_0162_V2 = dict(UPGRADE_TARGET_CLIENT_MODULES["0162-v2"])

BASE = "/admin/operations/compatibility"
COMPAT = importlib.import_module("slaif_gateway.api.admin_compatibility")

REASON_UPGRADE = "212 native module upgrade apply"
REASON_ROLLBACK = "212 native module rollback apply"
REASON_UPGRADE2 = "212 native re-upgrade after rollback"
REASON_MIGRATE = "212 native profile migrate to active"
REASON_MIGRATE2 = "212 native profile migrate to frozen"

COMPAT_ACTIONS = (
    "codex_client_module_upgraded",
    "codex_client_module_rolled_back",
    "codex_key_profile_migrated",
)


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET=generate_secret_key(),
        TOKEN_HMAC_SECRET=generate_secret_key(),
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        OPENAI_UPSTREAM_API_KEY="sk-provider-secret-placeholder",
        OPENROUTER_API_KEY="sk-or-provider-secret-placeholder",
    )


def _engine(database_url: str):
    return create_async_engine(database_url, future=True)


def asyncio_run(coro):
    return asyncio.run(coro)


def _key_metadata(pin: dict[str, str], sentinel: str) -> dict[str, Any]:
    return {
        "responses_policy": {
            "client_module": dict(pin),
            "212_sentinel": {"kept": sentinel},
        },
        "212_top_sentinel": {"kept": sentinel},
    }


async def _seed(database_url: str) -> dict[str, Any]:
    """Seed admin + owner + three pinned keys in ONE transaction."""
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    now = datetime.now(UTC)
    quota = dict(
        cost_limit_eur=Decimal("42.5"),
        token_limit_total=1234567,
        request_limit_total=89,
        rate_limit_requests_per_minute=7,
        max_concurrent_requests=3,
    )
    try:
        async with factory() as session:
            async with session.begin():
                admin = await AdminUsersRepository(session).create_admin_user(
                    email=f"gui212-{suffix}@example.org",
                    display_name="212 Compat GUI Admin",
                    password_hash=hash_admin_password(ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                )
                owner = await OwnersRepository(session).create_owner(
                    name="212",
                    surname=f"Compat-{suffix}",
                    email=f"gui212-owner-{suffix}@example.org",
                )
                keys = GatewayKeysRepository(session)

                async def _key(name: str, pin: dict[str, str], sentinel: str):
                    row = await keys.create_gateway_key_record(
                        public_key_id=f"212-{name}-{suffix}",
                        token_hash=f"212-{name}-{suffix}-hash-{uuid.uuid4().hex}",
                        owner_id=owner.id,
                        valid_from=now - timedelta(days=1),
                        valid_until=now + timedelta(days=365),
                        status="active",
                        created_by_admin_user_id=admin.id,
                        metadata_json=_key_metadata(pin, sentinel),
                        allow_all_models=False,
                        allowed_models=[f"212-only-model-{suffix}"],
                        allow_all_endpoints=False,
                        allowed_endpoints=["/v1/chat/completions"],
                        **quota,
                    )
                    # Non-zero accounting sentinels: the reviewed
                    # migration must preserve every one of them (key-row
                    # level; no actual ledger/replay rows are seeded).
                    row.cost_used_eur = Decimal("7.25")
                    row.tokens_used_total = 101
                    row.requests_used_total = 7
                    row.cost_reserved_eur = Decimal("0.05")
                    row.tokens_reserved_total = 13
                    row.requests_reserved_total = 2
                    return row

                module_key = await _key("mod", PIN_0149_V4, "212-mod")
                profile_key = await _key("prof", PIN_0162_V1, "212-prof")
                drift_key = await _key("drift", PIN_0149_V4, "212-drift")
                return {
                    "suffix": suffix,
                    "admin_id": str(admin.id),
                    "admin_email": str(admin.email),
                    "module_key": str(module_key.id),
                    "profile_key": str(profile_key.id),
                    "drift_key": str(drift_key.id),
                    "now": now,
                }
    finally:
        await engine.dispose()


_SEED_CACHE: dict[str, dict[str, Any]] = {}


def _seed_sync(database_url: str) -> dict[str, Any]:
    if database_url not in _SEED_CACHE:
        _SEED_CACHE[database_url] = asyncio_run(_seed(database_url))
    return _SEED_CACHE[database_url]


# ---------------------------------------------------------------------------
# DB oracles (scoped to THIS run's exact seeded key IDs)
# ---------------------------------------------------------------------------


async def _key_facts(database_url: str, key_id: str) -> dict[str, Any]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = (
                (
                    await session.execute(
                        select(GatewayKey).where(GatewayKey.id == uuid.UUID(key_id))
                    )
                )
                .scalars()
                .first()
            )
        if row is None:
            return {}
        return {
            "client_module": copy.deepcopy(
                (row.metadata_json or {}).get("responses_policy", {}).get(
                    "client_module"
                )
            ),
        }
    finally:
        await engine.dispose()


def _facts(data: dict[str, Any], key_id: str) -> dict[str, Any]:
    return asyncio_run(_key_facts(data["database_url"], key_id))


def _digests(data: dict[str, Any], key_id: str) -> tuple[str, str]:
    """Full-row stability digest (accepted shared-Core proof): every
    gateway_keys column except id/updated_at, plus all metadata except
    the audited responses_policy.client_module path."""
    return asyncio_run(_row_digest(data["database_url"], uuid.UUID(key_id)))


def _assert_preserved(
    before: tuple[str, str], after: tuple[str, str]
) -> None:
    # Byte-stable across ALL unrelated columns (material, owner,
    # restrictions, expiry, limits, non-zero usage/reservation counters,
    # fence state) and all metadata outside the audited path.
    assert before[0] == after[0], "unrelated gateway_keys columns changed"
    assert before[1] == after[1], "metadata outside client_module changed"


async def _key_audits(
    database_url: str, key_id: str, admin_id: str
) -> list[dict[str, Any]]:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "gateway_key",
                            AuditLog.entity_id == uuid.UUID(key_id),
                            AuditLog.admin_user_id == uuid.UUID(admin_id),
                            AuditLog.action.in_(COMPAT_ACTIONS),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return [
            {
                "action": r.action,
                "old": r.old_values,
                "new": r.new_values,
                "note": r.note,
            }
            for r in rows
        ]
    finally:
        await engine.dispose()


def _audits(data: dict[str, Any], key_id: str) -> list[dict[str, Any]]:
    return asyncio_run(_key_audits(data["database_url"], key_id, data["admin_id"]))


async def _set_client_module(
    database_url: str, key_id: str, pin: dict[str, str]
) -> None:
    engine = _engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with session.begin():
                row = (
                    (
                        await session.execute(
                            select(GatewayKey).where(
                                GatewayKey.id == uuid.UUID(key_id)
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                metadata = copy.deepcopy(row.metadata_json)
                metadata["responses_policy"]["client_module"] = dict(pin)
                row.metadata_json = metadata
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Module fixture: real app + real login on the owned PG
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env(owned_pg_url: str) -> Iterator[dict[str, Any]]:  # noqa: F811 (fixture dependency on the imported fixture name)
    data = _seed_sync(owned_pg_url)
    app = create_app(_settings(owned_pg_url))
    with TestClient(app) as client:
        _login(client, str(data["admin_email"]))
        data["client"] = client
        data["app"] = app
        data["database_url"] = owned_pg_url
        yield data


def _login(client: TestClient, admin_email: str) -> None:
    login_page = client.get("/admin/login")
    csrf = CSRF_RE.search(login_page.text).group(1)
    response = client.post(
        "/admin/login",
        data={"email": admin_email, "password": ADMIN_PASSWORD, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.status_code


def _key_page(client: TestClient, key_id: str) -> TestClient:
    return client.get(f"{BASE}/key/{key_id}")


def _key_form_fields(client: TestClient, key_id: str) -> dict[str, str]:
    """The exact hidden fields the rendered key form would submit."""
    page = client.get(f"{BASE}/key/{key_id}")
    assert page.status_code == 200
    out: dict[str, str] = {"csrf_token": CSRF_RE.search(page.text).group(1)}
    for name in ("from_version", "from_digest", "pin_selector"):
        match = re.search(rf'name="{name}" value="([^"]*)"', page.text)
        out[name] = match.group(1) if match else ""
    return out


def _review(
    client: TestClient, key_id: str, value: str, reason: str, **extra: Any
) -> TestClient:
    data = _key_form_fields(client, key_id)
    data["operation_target"] = value
    data["reason"] = reason
    data.update(extra)
    return client.post(f"{BASE}/key/{key_id}/review", data=data)


def _apply(
    client: TestClient, key_id: str, token: str, **overrides: Any
) -> TestClient:
    data = {
        "csrf_token": _key_form_fields(client, key_id)["csrf_token"],
        "review_token": token,
        "confirm_apply": "1",
    }
    data.update(overrides)
    return client.post(f"{BASE}/key/{key_id}/apply", data=data)


def _token(response: TestClient) -> str:
    assert response.status_code == 200
    assert "Dry run complete" in response.text, response.text[:400]
    return TOKEN_RE.search(response.text).group(1)


def _active_tuple() -> dict[str, str]:
    active = get_client_module(CODEX_0162_CLIENT_MODULE_ID)
    assert active.module_id == CODEX_0162_CLIENT_MODULE_ID
    return {
        "id": CODEX_0162_CLIENT_MODULE_ID,
        "version": str(active.module_version),
        "fixture_sha256": str(active.fixture_sha256),
    }


# ---------------------------------------------------------------------------
# Ordered scenario
# ---------------------------------------------------------------------------


def test_01_module_review_is_write_free(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    key_id = data["module_key"]

    page = _key_page(client, key_id)
    assert page.status_code == 200
    # finite options for the exact 0149-v4 pin: the two legal upgrades
    assert "module_upgrade:0149-v5" in page.text
    assert "module_upgrade:0162-v1" in page.text

    before = _digests(data, key_id)
    token = _token(
        _review(client, key_id, "module_upgrade:0149-v5", REASON_UPGRADE)
    )
    data["upgrade_token"] = token

    _assert_preserved(before, _digests(data, key_id))
    assert _facts(data, key_id)["client_module"] == PIN_0149_V4
    assert _audits(data, key_id) == []


def test_02_module_apply_one_audit_exact_binding(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    key_id = data["module_key"]
    before = _digests(data, key_id)

    response = _apply(client, key_id, data["upgrade_token"])
    assert response.status_code == 200
    assert "Applied" in response.text

    assert _facts(data, key_id)["client_module"] == PIN_0149_V5
    _assert_preserved(before, _digests(data, key_id))

    audits = _audits(data, key_id)
    assert len(audits) == 1
    entry = audits[0]
    assert entry["action"] == "codex_client_module_upgraded"
    assert entry["note"] == REASON_UPGRADE
    assert entry["old"] == {"client_module": PIN_0149_V4}
    assert entry["new"] == {"client_module": PIN_0149_V5}


def test_03_module_exact_repeat_no_write_no_audit(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    key_id = data["module_key"]
    before = _digests(data, key_id)

    response = _apply(client, key_id, data["upgrade_token"])
    assert response.status_code == 200
    assert "Already at target" in response.text

    _assert_preserved(before, _digests(data, key_id))
    assert len(_audits(data, key_id)) == 1


def test_04_module_rollback_exact_predecessor(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    key_id = data["module_key"]
    before = _digests(data, key_id)

    token = _token(
        _review(client, key_id, "module_rollback:0149-v4", REASON_ROLLBACK)
    )
    response = _apply(client, key_id, token)
    assert response.status_code == 200
    assert "Applied" in response.text

    assert _facts(data, key_id)["client_module"] == PIN_0149_V4
    _assert_preserved(before, _digests(data, key_id))

    audits = _audits(data, key_id)
    assert len(audits) == 2
    assert audits[1]["action"] == "codex_client_module_rolled_back"
    assert audits[1]["note"] == REASON_ROLLBACK
    assert audits[1]["old"] == {"client_module": PIN_0149_V5}
    assert audits[1]["new"] == {"client_module": PIN_0149_V4}


def test_05_original_token_after_authorized_action_reached_target(
    env: dict[str, Any],
) -> None:
    data = env
    client = data["client"]
    key_id = data["module_key"]
    before_repeat = None

    # A SEPARATE fresh upgrade review (new token) is applied after the
    # test_04 rollback: this DIFFERENT authorized action is what puts
    # the key back at the 0149-v5 target.
    new_token = _token(
        _review(client, key_id, "module_upgrade:0149-v5", REASON_UPGRADE2)
    )
    response = _apply(client, key_id, new_token)
    assert response.status_code == 200
    assert "Applied" in response.text
    assert _facts(data, key_id)["client_module"] == PIN_0149_V5
    audits = _audits(data, key_id)
    assert len(audits) == 3
    assert audits[2]["action"] == "codex_client_module_upgraded"
    assert audits[2]["note"] == REASON_UPGRADE2

    # The ORIGINAL reviewed token (older expected source, different
    # review) now finds the key already at its exact target - reached
    # by another authorized action: a no-op with no new write or audit.
    before_repeat = _digests(data, key_id)
    response = _apply(client, key_id, data["upgrade_token"])
    assert response.status_code == 200
    assert "Already at target" in response.text
    assert _facts(data, key_id)["client_module"] == PIN_0149_V5
    _assert_preserved(before_repeat, _digests(data, key_id))
    assert len(_audits(data, key_id)) == 3


def test_06_non_target_drift_refused_zero_writes(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    key_id = data["drift_key"]

    token = _token(
        _review(client, key_id, "module_upgrade:0149-v5", REASON_UPGRADE)
    )
    # The key drifts to an UNRELATED tuple between review and apply.
    asyncio_run(_set_client_module(data["database_url"], key_id, PIN_0162_V2))
    before = _digests(data, key_id)

    response = _apply(client, key_id, token)
    assert response.status_code == 400
    assert "does not match the expected source tuple" in response.text
    assert "Applied" not in response.text

    _assert_preserved(before, _digests(data, key_id))
    assert _facts(data, key_id)["client_module"] == PIN_0162_V2
    assert _audits(data, key_id) == []


def test_07_wrong_active_tuple_refused_at_apply(
    env: dict[str, Any], monkeypatch
) -> None:
    data = env
    client = data["client"]
    key_id = data["profile_key"]

    # The reviewer binds the REAL bootstrap active tuple.
    token = _token(_review(client, key_id, "migrate:active", REASON_MIGRATE))
    data["migrate_active_token"] = token

    # The apply worker's registry resolves a DIFFERENT active tuple:
    # the shared expected-target guard must refuse before any mutation.
    real = _active_tuple()
    drifted = dict(real, fixture_sha256="e" * 64)

    def _drifted_module(_module_id):
        return importlib.import_module("types").SimpleNamespace(
            module_id=CODEX_0162_CLIENT_MODULE_ID,
            module_version=drifted["version"],
            fixture_sha256=drifted["fixture_sha256"],
        )

    monkeypatch.setattr(
        "slaif_gateway.services.codex_module_upgrade.get_client_module",
        _drifted_module,
    )
    before = _digests(data, key_id)
    response = _apply(client, key_id, token)
    assert response.status_code == 400
    assert "The active Codex profile identity changed" in response.text
    assert "Applied" not in response.text

    _assert_preserved(before, _digests(data, key_id))
    assert _facts(data, key_id)["client_module"] == PIN_0162_V1
    assert _audits(data, key_id) == []


def test_08_profile_migrate_active_applied(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    key_id = data["profile_key"]
    before = _digests(data, key_id)
    active = _active_tuple()

    response = _apply(client, key_id, data["migrate_active_token"])
    assert response.status_code == 200
    assert "Applied" in response.text

    assert _facts(data, key_id)["client_module"] == active
    _assert_preserved(before, _digests(data, key_id))

    audits = _audits(data, key_id)
    assert len(audits) == 1
    assert audits[0]["action"] == "codex_key_profile_migrated"
    assert audits[0]["note"] == REASON_MIGRATE
    assert audits[0]["old"] == {"client_module": PIN_0162_V1}
    assert audits[0]["new"] == {"client_module": active}


def test_09_profile_migrate_repeat_no_write_no_audit(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    key_id = data["profile_key"]
    before = _digests(data, key_id)

    response = _apply(client, key_id, data["migrate_active_token"])
    assert response.status_code == 200
    assert "Already at target" in response.text

    _assert_preserved(before, _digests(data, key_id))
    assert len(_audits(data, key_id)) == 1


def test_10_late_failure_rolls_back_policy_and_audit(
    env: dict[str, Any], monkeypatch
) -> None:
    data = env
    client = data["client"]
    key_id = data["profile_key"]
    active = _active_tuple()

    # Choose a frozen legacy target whose revision differs from active.
    target = "0162-v2" if active["version"] != "2" else "0162-v1"
    frozen = PIN_0162_V2 if target == "0162-v2" else PIN_0162_V1

    # Failure injected AFTER the real audit flush, before the commit.
    real_factory = COMPAT.AuditRepository

    def late_fail_factory(session):
        repo = real_factory(session)
        original = repo.add_audit_log

        async def boom(**kwargs):
            await original(**kwargs)
            raise RuntimeError("212 late-failure-injected")

        repo.add_audit_log = boom
        return repo

    monkeypatch.setattr(COMPAT, "AuditRepository", late_fail_factory)

    token = _token(
        _review(client, key_id, f"migrate:{target}", REASON_MIGRATE2)
    )
    data["migrate_frozen_token"] = token
    data["migrate_frozen_target"] = frozen

    before = _digests(data, key_id)
    response = _apply(client, key_id, token)
    assert response.status_code == 400
    assert "UNCONFIRMED" in response.text
    assert "Applied" not in response.text

    # The WHOLE caller transaction rolled back: the provisional tuple
    # AND the flushed audit row are both gone.
    _assert_preserved(before, _digests(data, key_id))
    assert _facts(data, key_id)["client_module"] == active
    assert len(_audits(data, key_id)) == 1


def test_11_retry_after_unconfirmed_applies(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    key_id = data["profile_key"]

    response = _apply(client, key_id, data["migrate_frozen_token"])
    assert response.status_code == 200
    assert "Applied" in response.text
    assert (
        _facts(data, key_id)["client_module"] == data["migrate_frozen_target"]
    )
    audits = _audits(data, key_id)
    assert len(audits) == 2
    assert audits[1]["action"] == "codex_key_profile_migrated"
    assert audits[1]["note"] == REASON_MIGRATE2


def test_12_native_auth_csrf_denials_zero_writes(env: dict[str, Any]) -> None:
    data = env
    client = data["client"]
    key_id = data["module_key"]
    key_ids = (
        data["module_key"],
        data["profile_key"],
        data["drift_key"],
    )
    audits_before = {k: _audits(data, k) for k in key_ids}
    digests_before = {k: _digests(data, k) for k in key_ids}

    # (1) No session at all: both endpoints refuse at the login boundary.
    with TestClient(data["app"]) as fresh:
        review_no_session = fresh.post(
            f"{BASE}/key/{key_id}/review",
            data={
                "csrf_token": "x",
                "operation_target": "module_upgrade:0149-v5",
                "reason": REASON_UPGRADE,
            },
            follow_redirects=False,
        )
        assert review_no_session.status_code == 303
        assert review_no_session.headers["location"] == "/admin/login"
        apply_no_session = fresh.post(
            f"{BASE}/key/{key_id}/apply",
            data={
                "csrf_token": "x",
                "review_token": data["upgrade_token"],
                "confirm_apply": "1",
            },
            follow_redirects=False,
        )
        assert apply_no_session.status_code == 303
        assert apply_no_session.headers["location"] == "/admin/login"

    # (2) Valid session + wrong CSRF: fixed refusal, nothing executes.
    response = client.post(
        f"{BASE}/key/{key_id}/review",
        data={
            "csrf_token": "wrong-csrf",
            "operation_target": "module_upgrade:0162-v1",
            "reason": REASON_UPGRADE,
        },
    )
    assert response.status_code == 400
    assert "CSRF" in response.text

    # Zero DB mutation from any of the denials.
    for key in key_ids:
        assert _audits(data, key) == audits_before[key]
        assert _digests(data, key) == digests_before[key]

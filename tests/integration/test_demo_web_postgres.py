"""Real owned-PostgreSQL-16 evidence for objective 224-c demo web entry.

Runs on the same owned fixture pair as the 222/224-b worker evidence
(``san_env`` from ``test_demo_snapshot_sanitize_postgres`` plus the
function-scoped ``custody`` directory) and reuses the 224-b module's
owned web/worker ROLES (``_wenv_base``) created from the reviewed
224-a grant matrix. This module adds ONE function-scoped fake-admin
account with KNOWN credentials (fresh per test, exact run-owned
teardown) because the 224-b ``wenv`` account has a random password the
browser-driven login cannot use.

Proves, against real PostgreSQL 16 with the REAL restricted web role:

- the full entry cycle: web-role HTTP login (real Argon2id verify
  under the web role's column-scoped credential read) -> fresh pending
  request -> the 224-b ``process-request`` CLI (real worker role, real
  221/222/223 chain on the owned source/target pair) -> the wait
  surface issues EXACTLY ONE session at the verified moment (raw token
  only once, stored form is the SHA-256 hash) -> ready page (per-use
  validation) -> logout revokes idempotently;
- a second login yields a DISTINCT request (224-a law) while the first
  verified copy is still bound to its own request;
- after revocation the 224-b ``cleanup`` CLI drops the bound target
  database and the request row reaches ``cleaned``;
- the web role's privilege boundary is enforced by the database:
  full-row account reads, business-table reads, naming the ``state``
  column in a request INSERT, and ANY request UPDATE are all refused
  with 42501, while the granted column reads succeed;
- with zero enabled accounts EVERY demo route 404s (no oracle), and
  re-enabling restores the surface.

No provider HTTP, no Redis, no normal admin auth, no email. Synthetic
data only; the demo remains unusable from a browser beyond this entry
surface (copy-backed browsing is a later suffix). Ownership discipline
mirrors the 224-b worker module: run-tagged roles, exact run-owned
cleanup only.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from slaif_gateway.demo_web import (
    PENDING_TTL_S,
    DemoWebConfig,
    PgDemoWebFacade,
    create_demo_app,
    verify_signed_payload,
)
from tests.integration.test_demo_snapshot_sanitize_postgres import _Env
from tests.integration.test_demo_web_control_postgres import (
    _denied,
    _exec,
    _scalar,
    _scalar_many,
    _session_factory,
)
from tests.integration.test_demo_web_worker_postgres import (
    _READER_PW,
    _READER_ROLE,
    _request_row,
    _settings_for,
)

# Owned-PostgreSQL fixtures (function-scope ``custody`` + ``san_env``)
# and the 224-b module's run-tagged web/worker ROLES (``_wenv_base``)
# by plugin registration: requested BY NAME without fixture-name
# imports (F811 avoidance).
pytest_plugins = ("tests.integration.test_demo_web_worker_postgres",)


# --- function-scoped account with KNOWN credentials --------------------------------


@pytest.fixture()
def webenv(_wenv_base: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """ONE enabled fake-admin account with known username/password.

    Fresh per test (same isolation law as the 224-b ``wenv``: the
    worker's global recovery/cleanup scan must only ever see one
    test's control rows). Exact run-owned teardown in FK order.
    """
    from slaif_gateway.db.models import FakeAdminAccount
    from slaif_gateway.utils.passwords import hash_admin_password

    source_url = str(_wenv_base["source_url"])
    username = f"slaif224c-admin-{uuid.uuid4().hex[:8]}"
    password = f"seed-web-{uuid.uuid4().hex}"
    account_id = uuid.uuid4()

    async def seed() -> None:
        factory = _session_factory(source_url)
        async with factory() as session, session.begin():
            session.add(
                FakeAdminAccount(
                    id=account_id,
                    username=username,
                    password_hash=hash_admin_password(password),
                    is_enabled=True,
                    credential_generation=0,
                )
            )

    asyncio.run(seed())
    try:
        yield {
            **_wenv_base,
            "account_id": account_id,
            "username": username,
            "password": password,
        }
    finally:
        async def _teardown() -> None:
            # FK order: sessions -> requests -> account.
            await _exec(
                source_url,
                "DELETE FROM demo_control.demo_web_sessions "
                f"WHERE account_id = '{account_id}'",
            )
            await _exec(
                source_url,
                "DELETE FROM demo_control.demo_snapshot_requests "
                f"WHERE account_id = '{account_id}'",
            )
            await _exec(
                source_url,
                f"DELETE FROM demo_control.fake_admin_accounts "
                f"WHERE id = '{account_id}'",
            )
            assert (
                await _scalar(
                    source_url,
                    "SELECT EXISTS (SELECT 1 FROM demo_control.fake_admin_accounts "
                    "WHERE id = :id)",
                    {"id": str(account_id)},
                )
                is False
            ), "seeded account row remains after cleanup"

        asyncio.run(_teardown())


# --- helpers -----------------------------------------------------------------------


def _web_config(env: dict[str, Any], san: _Env) -> DemoWebConfig:
    parsed = urlparse(str(env["source_url"]))
    return DemoWebConfig(
        enabled=True,
        control_host=parsed.hostname,
        control_port=parsed.port or 5432,
        control_database=parsed.path.lstrip("/"),
        control_user=str(env["web_role"]),
        control_password=str(env["web_pw"]),
        cookie_secret=f"pg-e2e-cookie-secret-{uuid.uuid4().hex}",
        # 224-d law: an enabled config must carry the copy-reader
        # binding. These tests never open a copy connection, so the
        # binding is the owned target endpoint under the run-owned
        # reader role (validation-only values here).
        copy_host=str(san.target["host"]),
        copy_port=int(san.target["port"]),
        copy_user=_READER_ROLE,
        copy_password=_READER_PW,
    )


def _parse_pending(secret: str, token: str) -> uuid.UUID:
    payload = verify_signed_payload(secret, "pending", token, PENDING_TTL_S)
    assert payload is not None
    _account, request_id, _gen = payload.split(":")
    return uuid.UUID(request_id)


def _target_db_exists(san: _Env, db: str) -> bool:
    async def run() -> bool:
        s = await asyncpg.connect(
            **{
                "host": san.target["host"],
                "port": int(san.target["port"]),
                "user": san.target["user"],
                "password": san.target["password"],
                "database": str(san.target["database"]),
            }
        )
        try:
            row = await s.fetchrow(
                "SELECT 1 FROM pg_database WHERE datname = $1", db
            )
            return row is not None
        finally:
            await s.close()

    return asyncio.run(run())


def _worker_cli_env(san: _Env, env: dict[str, Any], custody: Path) -> dict[str, str]:
    values = _settings_for(san, custody)
    values.update(
        {
            "DEMO_WEB_WORKER_CONTROL_HOST": san.source["host"],
            "DEMO_WEB_WORKER_CONTROL_PORT": int(san.source["port"]),
            "DEMO_WEB_WORKER_CONTROL_DATABASE": san.source["database"],
            "DEMO_WEB_WORKER_CONTROL_USER": env["worker_role"],
            "DEMO_WEB_WORKER_CONTROL_PASSWORD": env["worker_pw"],
            "COMPLETION_SERVICE_PROFILE_DIR": str(env["profile_dir"]),
            "DEMO_SNAPSHOT_TARGET_READER_ROLE": env["reader_role"],
        }
    )
    return {str(k): str(v) for k, v in values.items()}


def _run_worker_cli(args: list[str], env_vars: dict[str, str],
                    monkeypatch: pytest.MonkeyPatch) -> str:
    from typer.testing import CliRunner

    from slaif_gateway.cli import demo_snapshot_worker as cli_mod
    from slaif_gateway.config import get_settings

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        res = CliRunner().invoke(cli_mod.app, args)
        return res.output
    finally:
        get_settings.cache_clear()


# --- 1. full entry cycle: login -> worker -> one session -> logout -> cleanup ------


def test_e2e_web_entry_full_cycle(
    san_env: _Env, webenv: dict[str, Any], custody: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = webenv
    cfg = _web_config(env, san_env)
    # Each web phase gets its OWN facade: an asyncpg engine binds to the
    # event loop it was first used on, and the synchronous worker-CLI
    # steps run in between (separate asyncio.run loops).

    # Phase 1: login over HTTP (web role end to end). The browser keeps
    # the signed pending cookie for the wait surface.
    async def login_phase() -> tuple[uuid.UUID, str]:
        facade = PgDemoWebFacade(cfg)
        try:
            app = create_demo_app(cfg, facade=facade)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="https://demo.test"
            ) as client:
                r = await client.get("/fakeadmin/login")
                assert r.status_code == 200
                csrf = r.cookies["slaif_demo_csrf"]
                r = await client.post(
                    "/fakeadmin/login",
                    data={
                        "username": env["username"],
                        "password": env["password"],
                        "csrf": csrf,
                    },
                )
                assert r.status_code == 303, r.text
                assert r.headers["location"] == "/fakeadmin/wait"
                pending = r.cookies["slaif_demo_pending"]
                return _parse_pending(cfg.cookie_secret, pending), pending
        finally:
            await facade.close()

    rid, pending_cookie = asyncio.run(login_phase())
    row = _request_row(env, rid)
    assert row["state"] == "pending"
    assert row["worker_job_id"] is None

    # Phase 2: the 224-b worker CLI (real worker role, real chain).
    cli_env = _worker_cli_env(san_env, env, custody)
    output = _run_worker_cli(
        ["process-request", str(rid), "--json"], cli_env, monkeypatch
    )
    assert "verified_unpublished" in output
    # Safe vocabulary: no control passwords, no job/target names.
    assert env["worker_pw"] not in output
    assert env["web_pw"] not in output
    assert "snap-" not in output
    assert "demo_snap_" not in output

    row = _request_row(env, rid)
    assert row["state"] == "verified_unpublished"
    target_db = row["worker_target_db"]
    assert isinstance(target_db, str) and target_db.startswith("demo_snap_")
    assert _target_db_exists(san_env, target_db)

    # Phase 3: wait -> EXACTLY ONE session -> ready -> logout.
    async def wait_phase() -> str:
        facade = PgDemoWebFacade(cfg)
        try:
            app = create_demo_app(cfg, facade=facade)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="https://demo.test"
            ) as client:
                # Restore the browser's pending cookie from phase 1.
                client.cookies.set(
                    "slaif_demo_pending", pending_cookie,
                    domain="demo.test", path="/fakeadmin",
                )
                r = await client.get("/fakeadmin/wait/status")
                assert r.json() == {"state": "ready"}
                r = await client.get("/fakeadmin/wait")
                assert r.status_code == 303
                assert r.headers["location"] == "/fakeadmin/ready"
                token = client.cookies.get("slaif_demo_session")
                assert token
                r = await client.get("/fakeadmin/ready")
                assert r.status_code == 200
                # 224-z: the ready page offers the mounted read GUI.
                assert 'href="/admin"' in r.text
                assert "not enabled yet" not in r.text
                csrf2 = r.cookies["slaif_demo_csrf"]
                r = await client.post("/fakeadmin/logout", data={"csrf": csrf2})
                assert r.status_code == 303
                assert r.headers["location"] == "/fakeadmin/login"
                return token
        finally:
            await facade.close()

    token = asyncio.run(wait_phase())

    # Stored form: ONLY the SHA-256 hash, never the raw token.
    sessions = asyncio.run(
        _scalar_many(
            str(env["source_url"]),
            "SELECT token_hash, revoked_at FROM demo_control.demo_web_sessions "
            "WHERE request_id = :id",
            {"id": str(rid)},
        )
    )
    assert len(sessions) == 1
    stored_hash = sessions[0]._mapping["token_hash"]
    assert stored_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in stored_hash
    assert sessions[0]._mapping["revoked_at"] is not None, "logout must revoke"

    # A second login yields a DISTINCT request (224-a law) and the
    # verified copy stays bound to the FIRST request.
    async def second_login_phase() -> uuid.UUID:
        facade = PgDemoWebFacade(cfg)
        try:
            app = create_demo_app(cfg, facade=facade)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="https://demo.test"
            ) as client:
                r = await client.get("/fakeadmin/login")
                csrf = r.cookies["slaif_demo_csrf"]
                r = await client.post(
                    "/fakeadmin/login",
                    data={
                        "username": env["username"],
                        "password": env["password"],
                        "csrf": csrf,
                    },
                )
                assert r.status_code == 303
                return _parse_pending(
                    cfg.cookie_secret, r.cookies["slaif_demo_pending"]
                )
        finally:
            await facade.close()

    second_rid = asyncio.run(second_login_phase())
    assert second_rid != rid
    row = _request_row(env, rid)
    assert row["state"] == "verified_unpublished"
    assert row["worker_job_id"] is not None

    # The revoked session is refused on the very next use.
    async def refused_phase() -> None:
        facade = PgDemoWebFacade(cfg)
        try:
            app = create_demo_app(cfg, facade=facade)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="https://demo.test"
            ) as client:
                client.cookies.set("slaif_demo_session", token, path="/")
                r = await client.get("/fakeadmin/ready")
                assert r.status_code == 303
                assert r.headers["location"] == "/fakeadmin/login"
        finally:
            await facade.close()

    asyncio.run(refused_phase())

    # Phase 4: worker cleanup drops the now-released copy.
    output = _run_worker_cli(["cleanup", "--json"], cli_env, monkeypatch)
    assert "demo_snap_" not in output

    row = _request_row(env, rid)
    assert row["state"] == "cleaned"
    assert not _target_db_exists(san_env, target_db)


# --- 2. the web role's privilege boundary is enforced by the database --------------


def test_web_role_privilege_boundary(webenv: dict[str, Any]) -> None:
    env = webenv
    url = str(env["web_url"])
    account_id = env["account_id"]

    # Positive control: the GRANTED column reads work under the web role.
    rows = asyncio.run(
        _scalar_many(
            url,
            "SELECT id, username, is_enabled, credential_generation "
            "FROM demo_control.fake_admin_accounts WHERE id = :id",
            {"id": str(account_id)},
        )
    )
    assert len(rows) == 1
    assert rows[0]._mapping["username"]

    # 42501: full-row account read (timestamps are not granted).
    _denied(
        url,
        "SELECT * FROM demo_control.fake_admin_accounts WHERE id = $1",
        {"id": str(account_id)},
    )
    # 42501: business tables (no grant at all).
    _denied(url, "SELECT token_hash FROM public.gateway_keys LIMIT 1")
    # 42501: naming the state column in a request INSERT (the web INSERT
    # grant is exactly the reviewed column set; state is DB-defaulted).
    _denied(
        url,
        "INSERT INTO demo_control.demo_snapshot_requests "
        "(id, account_id, credential_generation, state) "
        "VALUES (gen_random_uuid(), $1, 0, 'pending')",
        {"acc": str(account_id)},
    )
    # 42501: ANY update on the request table (the web role has none).
    _denied(
        url,
        "UPDATE demo_control.demo_snapshot_requests "
        "SET failure_code = NULL WHERE id = $1",
        {"id": str(account_id)},
    )
    # 42501: worker-owned request columns cannot be written by web either
    # (the worker verification columns are worker-grant-only).
    _denied(
        url,
        "UPDATE demo_control.demo_snapshot_requests "
        "SET worker_job_id = NULL, verified_at = NULL WHERE id = $1",
        {"id": str(account_id)},
    )


# --- 3. zero enabled accounts: 404 on every demo route -----------------------------


def test_zero_active_404_and_reenable(
    san_env: _Env, webenv: dict[str, Any]
) -> None:
    env = webenv
    source_url = str(env["source_url"])
    cfg = _web_config(env, san_env)

    def _set_enabled(enabled: bool) -> None:
        # Trusted owner path (test-only): no parameter support on the
        # helper; the boolean is a self-generated literal.
        asyncio.run(
            _exec(
                source_url,
                f"UPDATE demo_control.fake_admin_accounts SET is_enabled = "
                f"{'TRUE' if enabled else 'FALSE'} "
                f"WHERE id = '{env['account_id']}'",
            )
        )

    async def route_codes() -> dict[str, int]:
        facade = PgDemoWebFacade(cfg)
        try:
            app = create_demo_app(cfg, facade=facade)
            codes: dict[str, int] = {}
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="https://demo.test"
            ) as client:
                codes["login"] = (await client.get("/fakeadmin/login")).status_code
                codes["wait"] = (await client.get("/fakeadmin/wait")).status_code
                codes["status"] = (
                    await client.get("/fakeadmin/wait/status")
                ).status_code
                codes["ready"] = (await client.get("/fakeadmin/ready")).status_code
                codes["logout"] = (
                    await client.post("/fakeadmin/logout", data={"csrf": "x"})
                ).status_code
            return codes
        finally:
            await facade.close()

    _set_enabled(False)
    try:
        codes = asyncio.run(route_codes())
        assert all(code == 404 for code in codes.values()), codes
    finally:
        _set_enabled(True)
    codes = asyncio.run(route_codes())
    assert codes["login"] == 200, codes

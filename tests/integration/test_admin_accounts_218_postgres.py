"""218-a: native owned-PG qualification of G17 privileged account management.

Real app (FastAPI TestClient over the REAL create_app, real routes, real
CSRF/session auth, real AdminService/AdminSessionService transactions and
real Argon2id hashing) against ONE NEW owned, labeled, loopback-bound,
tmpfs-backed PostgreSQL 16 (the qualified ``owned_pg_url`` fixture - never
an ambient database). No Redis, no Celery, no email, no upstream network,
no browser (the browser module covers real Chromium separately).

Native proofs (file order is significant; the module environment is
shared):

- list real HTTP: safe metadata only (never a hash, session-token hash,
  or secret), server-derived UUID reset links, honest bounded pagination;
- create real HTTP: hashes-only persistence, EXACT password bytes (never
  trimmed), exact actor/reason audit, safe duplicate refusal;
- reset real HTTP: hash change + complete target-session revocation +
  unrelated-session preservation + exact actor/target/reason audit in one
  committed transaction; old-password and revoked-session refusal;
  new-password login;
- self-reset: cookie cleared, the revoked actor session refused even when
  the old token is presented, secret-free safe-login flash, new-password
  login, old-password refusal;
- the COMMIT-TIME duplicate race (two concurrent creates for one email,
  a deterministic real-PG unique-index wait observed through
  pg_stat_activity): exactly one row, one success, one 409, no raw SQL
  text in the response;
- a pre-commit audit fault on reset: complete NATIVE rollback (hash
  unchanged, sessions untouched, no audit row) with the honest
  outcome-unconfirmed page;
- BOTH concurrent login/reset orderings with deterministic real-PG row-lock
  synchronization: a real commit barrier holds the phased transaction's
  admin-row lock across an observation window, the counterparty is a REAL
  login (app HTTP) or REAL shared-service reset (dedicated engine/loop,
  the exact transaction the GUI route composes), and the observed lock
  wait is proven through pg_stat_activity (real PG state - no sleeps as
  race oracles, no mocked locks):
  - login-first: the GUI login that started first succeeds, but the reset
    that waited on the held row lock revokes the session that login just
    committed (the cookie is then refused);
  - reset-first: the GUI login that waited on the held row lock verifies
    the superseded password against the NEW hash and is refused (no
    session).
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from slaif_gateway.config import Settings
from slaif_gateway.db.models import AdminSession, AdminUser, AuditLog
from slaif_gateway.db.repositories.admin_sessions import AdminSessionsRepository
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.main import create_app
from slaif_gateway.services.admin_service import AdminService
from slaif_gateway.utils.passwords import hash_admin_password, verify_admin_password
from slaif_gateway.utils.secrets import generate_secret_key
# Reuse the qualified owned PostgreSQL fixture (never an ambient fallback).
from tests.integration.test_lazy_throttling_postgres_redis import (
    owned_pg_url as _owned_pg_url_fixture,
)

owned_pg_url = _owned_pg_url_fixture

BASE = "/admin/accounts"
SESSION_COOKIE = "slaif_admin_session"
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')

# Distinct synthetic passwords per account (no reuse across roles).
ROOT_PASSWORD = "218-native-root-base-pw"
ROOT2_PASSWORD = "218-native-root2-base-pw"
TARGET_PASSWORD = "218-native-target-base-pw"
TARGET2_PASSWORD = "218-native-target2-base-pw"
BYSTANDER_PASSWORD = "218-native-bystander-base-pw"
RACE_A_PASSWORD = "218-native-race-a-base-pw"
RACE_B_PASSWORD = "218-native-race-b-base-pw"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(database_url: str) -> Settings:
    return Settings(
        APP_ENV="test",
        DATABASE_URL=database_url,
        ADMIN_SESSION_SECRET="s" * 40,
        TOKEN_HMAC_SECRET=generate_secret_key(),
        ONE_TIME_SECRET_ENCRYPTION_KEY=generate_secret_key(),
        GATEWAY_KEY_PREFIX="sk-slaif-",
        GATEWAY_KEY_ACCEPTED_PREFIXES="sk-slaif-",
        ACTIVE_HMAC_KEY_VERSION="1",
        TOKEN_HMAC_SECRET_V1=generate_secret_key(),
        ENABLE_ADMIN_DASHBOARD=True,
        ENABLE_EMAIL_DELIVERY=False,
        OPENAI_UPSTREAM_API_KEY="provider-secret-placeholder-218",
        OPENROUTER_API_KEY="or-provider-secret-placeholder-218",
    )


def _db_worker(database_url: str, coro_factory) -> Any:
    """Run a DB coroutine in a WORKER THREAD (the 216 threaded pattern):
    the primary TestClient owns a live ASGI loop thread where
    ``asyncio.run`` would raise; a fresh worker thread has no running
    loop, so the SEPARATE fresh PG connection is safe there."""
    box: dict[str, Any] = {}

    def _worker() -> None:
        async def _run() -> None:
            engine = create_async_engine(database_url, future=True)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with factory() as session:
                    box["value"] = await coro_factory(session)
            finally:
                await engine.dispose()

        try:
            asyncio.run(_run())
        except BaseException as exc:  # re-raised below
            box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


async def _seed_admins(database_url: str) -> dict[str, dict[str, Any]]:
    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]
    out: dict[str, dict[str, Any]] = {}
    try:
        async with factory() as session:
            async with session.begin():
                for key, role, password in (
                    ("superadmin", "superadmin", ROOT_PASSWORD),
                    ("root2", "superadmin", ROOT2_PASSWORD),
                    ("target", "admin", TARGET_PASSWORD),
                    ("target2", "admin", TARGET2_PASSWORD),
                    ("bystander", "admin", BYSTANDER_PASSWORD),
                    ("race_a", "admin", RACE_A_PASSWORD),
                    ("race_b", "admin", RACE_B_PASSWORD),
                ):
                    email = f"218-{key}-{suffix}@example.test"
                    row = await AdminUsersRepository(session).create_admin_user(
                        email=email,
                        display_name=f"218 {key} admin",
                        password_hash=hash_admin_password(password),
                        role=role,
                        is_active=True,
                    )
                    out[key] = {"email": email, "password": password, "id": row.id}
    finally:
        await engine.dispose()
    return out


def _login(client: TestClient, *, email: str, password: str) -> Any:
    response = client.get("/admin/login", follow_redirects=False)
    assert response.status_code == 200
    csrf = CSRF_RE.search(response.text).group(1)
    response = client.post(
        "/admin/login",
        data={"csrf_token": csrf, "email": email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303, f"login refused for {email}: {response.status_code}"
    return response


def _login_refused(client: TestClient, *, email: str, password: str) -> Any:
    """A real login POST with a WRONG password: 401 + generic error.

    Any pre-existing session cookie is cleared first so the attempt is a
    genuine password check (the login handler does not consult the
    session cookie, but the login PAGE 303s when one is valid, which
    would otherwise hand us the wrong form token).
    """
    client.cookies.clear()
    response = client.get("/admin/login", follow_redirects=False)
    assert response.status_code == 200
    csrf = CSRF_RE.search(response.text).group(1)
    response = client.post(
        "/admin/login",
        data={"csrf_token": csrf, "email": email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "Invalid email or password." in response.text
    return response


def _page_csrf(client: TestClient, path: str, **params: Any) -> str:
    response = client.get(path, params=params or None)
    assert response.status_code == 200
    match = CSRF_RE.search(response.text)
    assert match, f"no CSRF token on {path}"
    return match.group(1)


def _secondary_client(app: Any, portal: Any) -> TestClient:
    """A cookie-jar-isolated client that SHARES the module client's portal
    (and therefore the app's single event loop).

    The app's asyncpg pool connections are bound to the loop the app
    LIFESPAN started on (the module client's portal); a secondary client
    with its own portal would run on a different loop and hit loop-bound
    asyncpg connections, and a secondary context-manager entry would
    re-run lifespan startup/shutdown and clobber the shared app state
    (the 215/216 single-portal constraint). Sharing the portal keeps the
    jar isolated while every request stays on the app loop.
    """
    tc = TestClient(app)
    tc.portal = portal
    return tc


# -- committed-state readers (fresh connections) ----------------------------


def _admin_by_email(database_url: str, email: str) -> AdminUser:
    async def _run(session) -> AdminUser:
        row = (
            await session.execute(select(AdminUser).where(AdminUser.email == email))
        ).scalar_one()
        return row

    return _db_worker(database_url, _run)


def _admin_count_by_email(database_url: str, email: str) -> int:
    async def _run(session) -> int:
        return int(
            (
                await session.execute(
                    text(
                        "SELECT count(*) FROM admin_users"
                        " WHERE email = :email"
                    ),
                    {"email": email},
                )
            ).scalar_one()
        )

    return _db_worker(database_url, _run)


def _sessions_for_admin(database_url: str, admin_id: uuid.UUID) -> list[AdminSession]:
    async def _run(session) -> list[AdminSession]:
        rows = (
            (
                await session.execute(
                    select(AdminSession).where(AdminSession.admin_user_id == admin_id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    return _db_worker(database_url, _run)


def _audit_rows(
    database_url: str, action: str, entity_id: uuid.UUID | None = None
) -> list[AuditLog]:
    async def _run(session) -> list[AuditLog]:
        stmt = select(AuditLog).where(AuditLog.action == action)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        rows = (await session.execute(stmt)).scalars().all()
        return list(rows)

    return _db_worker(database_url, _run)


def _audit_blob(row: AuditLog) -> str:
    return json.dumps(
        [row.old_values, row.new_values, row.note, row.request_id, row.user_agent],
        default=str,
    )


def _wait_lock_waiters(
    database_url: str, *, what: str = "INSERT", timeout: float = 60.0
) -> int:
    """Wait until at least ONE real PG backend is waiting on a real lock
    for the given admin_users statement class (deterministic native-PG
    synchronization: the loop exits only on observed PG state, never on a
    fixed sleep)."""

    async def _run(session) -> int:
        return int(
            (
                await session.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity"
                        " WHERE wait_event_type = 'Lock'"
                        f"   AND query ILIKE '%{what} INTO admin_users%'"
                    )
                )
            ).scalar_one()
        )

    deadline = time.monotonic() + timeout
    last = -1
    while True:
        last = _db_worker(database_url, _run)
        if last >= 1:
            return last
        if time.monotonic() > deadline:
            raise AssertionError(f"no PG {what} lock waiter observed (last={last})")
        time.sleep(0.1)


def _wait_for_update_waiters(database_url: str, *, timeout: float = 60.0) -> int:
    """Wait until at least ONE real PG backend is waiting on the
    admin_users FOR UPDATE row lock (observed real PG state)."""

    async def _run(session) -> int:
        return int(
            (
                await session.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity"
                        " WHERE wait_event_type = 'Lock'"
                        "   AND query ILIKE '%FROM admin_users%'"
                        "   AND query ILIKE '%FOR UPDATE%'"
                    )
                )
            ).scalar_one()
        )

    deadline = time.monotonic() + timeout
    last = -1
    while True:
        last = _db_worker(database_url, _run)
        if last >= 1:
            return last
        if time.monotonic() > deadline:
            raise AssertionError(f"no PG FOR UPDATE waiter observed (last={last})")
        time.sleep(0.1)


def _reset_worker(
    database_url: str,
    *,
    target_id: uuid.UUID,
    password_hash: str,
    actor_id: uuid.UUID,
    reason: str,
    barrier: tuple[threading.Event, threading.Event] | None = None,
) -> None:
    """Real shared AdminService.reset_admin_password on a DEDICATED
    engine/loop (a worker thread, 216 holder pattern) - the exact
    transaction the GUI route composes. With ``barrier=(at_commit,
    proceed)`` the worker's real COMMIT is delayed (holding its real
    admin-row lock) until ``proceed`` - the 216 holder barrier, on a
    loop that exists only for this holder.
    """
    at_commit, proceed = barrier if barrier is not None else (None, None)

    async def _run(session) -> None:
        if at_commit is not None:

            def _before_commit(_sync: Any) -> None:
                at_commit.set()
                if proceed is not None:
                    assert proceed.wait(timeout=90), "proceed timed out"

            event.listen(session.sync_session, "before_commit", _before_commit)
        service = AdminService(
            admin_users_repository=AdminUsersRepository(session),
            audit_repository=AuditRepository(session),
            admin_sessions_repository=AdminSessionsRepository(session),
        )
        async with session.begin():
            await service.reset_admin_password(
                admin_user_id_or_email=str(target_id),
                password_hash=password_hash,
                actor_admin_id=actor_id,
                reason=reason,
                ip_address="127.0.0.1",
                user_agent="218-native-worker",
            )

    _db_worker(database_url, _run)


class _PhaseBarrierSessionmaker:
    """216-style commit barrier on the app's REAL SQLAlchemy sessions.

    A session whose transaction ADDs an audit row with the marker action
    is the phased mutation; its real ``before_commit`` sets ``at_commit``
    (and optionally waits for ``proceed``). No production seam, no mocked
    locks: the barrier only delays the real COMMIT, and every row lock
    involved is a real PostgreSQL lock.
    """

    def __init__(
        self,
        inner: Any,
        *,
        marker: str,
        at_commit: threading.Event,
        proceed: threading.Event | None = None,
    ) -> None:
        self._inner = inner
        self._marker = marker
        self._at_commit = at_commit
        self._proceed = proceed

    def __call__(self) -> Any:
        session = self._inner()
        phase = {"racing": False}
        inner_add = session.add

        def add(obj: Any) -> None:
            if not phase["racing"] and getattr(obj, "action", None) == self._marker:
                phase["racing"] = True
            inner_add(obj)

        def _before_commit(sync_session: Any) -> None:
            if not phase["racing"]:
                return
            self._at_commit.set()
            if self._proceed is not None:
                assert self._proceed.wait(timeout=90), "proceed timed out"

        event.listen(session.sync_session, "before_commit", _before_commit)
        session.add = add
        return session


# ---------------------------------------------------------------------------
# Module environment: owned PG (sole owner) + real app
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def env218(owned_pg_url: str) -> Iterator[dict[str, Any]]:
    settings = _settings(owned_pg_url)
    base: dict[str, Any] = {"accounts": asyncio.run(_seed_admins(owned_pg_url))}
    base["settings"] = settings
    base["database_url"] = owned_pg_url
    app = create_app(settings)
    # Lifespan-managed client: create_app leaves db_sessionmaker unset;
    # the app LIFESPAN initializes it (216 pattern).
    with TestClient(app) as client:
        _login(
            client,
            email=base["accounts"]["superadmin"]["email"],
            password=ROOT_PASSWORD,
        )
        base["client"] = client
        base["app"] = app
        yield base


# ---------------------------------------------------------------------------
# 1. List: real HTTP, safe metadata only
# ---------------------------------------------------------------------------


def test_list_real_http_safe_metadata_and_server_links(env218: dict[str, Any]) -> None:
    client: TestClient = env218["client"]
    db = env218["database_url"]
    accounts = env218["accounts"]

    response = client.get(BASE)
    assert response.status_code == 200
    body = response.text

    # Every seeded identity is listed with its SERVER-DERIVED UUID link.
    for key in ("superadmin", "root2", "target", "bystander"):
        row = _admin_by_email(db, accounts[key]["email"])
        assert row.email in body
        assert f"{BASE}/reset?admin_id={row.id}" in body
        assert "Reset password" in body

    # No hashes, session-token hashes, or secrets anywhere in the body.
    assert "argon2" not in body
    for key in ("superadmin", "target"):
        assert _admin_by_email(db, accounts[key]["email"]).password_hash not in body
    for session in _sessions_for_admin(db, accounts["superadmin"]["id"]):
        assert session.session_token_hash not in body
    assert "provider-secret-placeholder-218" not in body

    # Structural guards rendered by the shared list partial.
    assert 'role="region"' in body
    assert "data-sortable" in body
    assert "data-ordinal" in body
    # 7 seeded rows <= default page size 50: honest "no more rows".
    assert "No more rows" in body


# ---------------------------------------------------------------------------
# 2. Create: hashes-only persistence, exact bytes, exact actor/reason audit
# ---------------------------------------------------------------------------


def test_create_real_http_hash_only_exact_bytes_actor_reason(
    env218: dict[str, Any],
) -> None:
    client: TestClient = env218["client"]
    db = env218["database_url"]
    accounts = env218["accounts"]
    root = accounts["superadmin"]

    # EXACT password bytes: the trailing space is part of the secret and
    # must survive to the hash untrimmed.
    password = "Pw-218-exact bytes "
    email = f"218-created-{uuid.uuid4().hex[:10]}@example.test"
    csrf = _page_csrf(client, f"{BASE}/create")

    response = client.post(
        f"{BASE}/create",
        data={
            "csrf_token": csrf,
            "email": f"  {email.upper()}  ",
            "display_name": "  218 Created Admin  ",
            "password": password,
            "password_confirmation": password,
            "role": "admin",
            "confirm_create": "1",
            "confirm_superadmin": "",
            "reason": "218 native create",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"{BASE}?message=admin_account_created"
    assert password not in response.text

    row = _admin_by_email(db, email)
    assert row.email == email  # normalized
    assert row.display_name == "218 Created Admin"  # trimmed, bounded
    assert row.role == "admin"
    assert row.is_active is True
    assert row.password_hash.startswith("$argon2id$")
    # Exact bytes were hashed: the untrimmed value verifies, the trimmed
    # value does NOT.
    assert verify_admin_password(password, row.password_hash)
    assert not verify_admin_password(password.rstrip(), row.password_hash)

    rows = _audit_rows(db, "admin_user_created", entity_id=row.id)
    assert len(rows) == 1
    audit = rows[0]
    assert audit.admin_user_id == root["id"]  # exact actor
    assert audit.new_values["reason"] == "218 native create"
    assert audit.new_values["role"] == "admin"
    assert audit.new_values["is_active"] is True
    assert password not in _audit_blob(audit)
    assert row.password_hash not in _audit_blob(audit)

    # A KNOWN duplicate (case-insensitive CITEXT) is refused before write.
    csrf = _page_csrf(client, f"{BASE}/create")
    response = client.post(
        f"{BASE}/create",
        data={
            "csrf_token": csrf,
            "email": f"{email.upper()}",
            "display_name": "Dup",
            "password": "other-password-218",
            "password_confirmation": "other-password-218",
            "role": "admin",
            "confirm_create": "1",
            "confirm_superadmin": "",
            "reason": "duplicate probe",
        },
        follow_redirects=False,
    )
    assert response.status_code == 409
    assert "already exists" in response.text
    assert len(_audit_rows(db, "admin_user_created", entity_id=row.id)) == 1


# ---------------------------------------------------------------------------
# 3. Reset: full target revocation, unrelated preservation, exact audit
# ---------------------------------------------------------------------------


def test_reset_real_http_full_revocation_and_audits(env218: dict[str, Any]) -> None:
    client: TestClient = env218["client"]
    db = env218["database_url"]
    accounts = env218["accounts"]
    root = accounts["superadmin"]
    target = accounts["target"]
    bystander = accounts["bystander"]
    new_password = "Pw-218-target-new-pw"

    # Real logins create REAL session rows (target + unrelated bystander).
    target_client = _secondary_client(env218["app"], env218["client"].portal)
    _login(target_client, email=target["email"], password=target["password"])
    assert len(_sessions_for_admin(db, target["id"])) == 1

    bystander_client = _secondary_client(env218["app"], env218["client"].portal)
    _login(
        bystander_client, email=bystander["email"], password=bystander["password"]
    )
    assert len(_sessions_for_admin(db, bystander["id"])) == 1

    # Server-derived identity + bound form, then the real reset POST.
    page = client.get(f"{BASE}/reset", params={"admin_id": str(target["id"])})
    assert page.status_code == 200
    assert target["email"] in page.text
    assert f'name="admin_id" value="{target["id"]}"' in page.text
    csrf = CSRF_RE.search(page.text).group(1)

    response = client.post(
        f"{BASE}/reset?admin_id={target['id']}",
        data={
            "csrf_token": csrf,
            "admin_id": str(target["id"]),
            "password": new_password,
            "password_confirmation": new_password,
            "confirm_reset": "1",
            "reason": "218 native reset",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"{BASE}?message=admin_password_reset"

    # Native committed state: hash changed, ALL target sessions revoked,
    # the unrelated session untouched.
    row = _admin_by_email(db, target["email"])
    assert row.password_hash.startswith("$argon2id$")
    assert verify_admin_password(new_password, row.password_hash)
    assert not verify_admin_password(target["password"], row.password_hash)
    target_sessions = _sessions_for_admin(db, target["id"])
    assert len(target_sessions) == 1
    assert all(s.revoked_at is not None for s in target_sessions)
    bystander_sessions = _sessions_for_admin(db, bystander["id"])
    assert len(bystander_sessions) == 1
    assert all(s.revoked_at is None for s in bystander_sessions)

    # Exact actor/target/reason audit with the revocation outcome. The
    # EXISTING audit-metadata sanitizer drops session-/password-named
    # keys from committed metadata (pre-218 law, unchanged here), so the
    # committed row carries the sanitizer-safe counter + reason.
    audits = _audit_rows(db, "admin_user_password_reset", entity_id=target["id"])
    assert len(audits) == 1
    audit = audits[0]
    assert audit.admin_user_id == root["id"]
    assert audit.new_values == {
        "revoked_count": 1,
        "reason": "218 native reset",
    }
    assert audit.user_agent is not None  # clean test client UA passes exact
    assert new_password not in _audit_blob(audit)
    assert row.password_hash not in _audit_blob(audit)

    # HTTP consequences: revoked session refused, preserved session still
    # works, new password signs in, old password does not.
    assert target_client.get("/admin", follow_redirects=False).status_code == 303
    assert bystander_client.get("/admin", follow_redirects=False).status_code == 200
    _login(target_client, email=target["email"], password=new_password)
    _login_refused(target_client, email=target["email"], password=target["password"])


# ---------------------------------------------------------------------------
# 4. Self-reset: logout, revoked-actor refusal, safe-login flash
# ---------------------------------------------------------------------------


def test_self_reset_logout_revoked_token_refused_new_login(
    env218: dict[str, Any],
) -> None:
    db = env218["database_url"]
    accounts = env218["accounts"]
    root2 = accounts["root2"]
    new_password = "Pw-218-root2-new-pw"

    actor_client = _secondary_client(env218["app"], env218["client"].portal)
    login_response = _login(
        actor_client, email=root2["email"], password=root2["password"]
    )
    set_cookie = login_response.headers.get("set-cookie", "")
    match = re.search(f"{SESSION_COOKIE}=([^;]+)", set_cookie)
    assert match, "login did not deliver the session cookie"
    old_token = match.group(1)
    assert len(_sessions_for_admin(db, root2["id"])) == 1

    page = actor_client.get(f"{BASE}/reset", params={"admin_id": str(root2["id"])})
    assert page.status_code == 200
    assert "your own account" in page.text
    csrf = CSRF_RE.search(page.text).group(1)

    response = actor_client.post(
        f"{BASE}/reset?admin_id={root2['id']}",
        data={
            "csrf_token": csrf,
            "admin_id": str(root2["id"]),
            "password": new_password,
            "password_confirmation": new_password,
            "confirm_reset": "1",
            "reason": "218 self reset",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == (
        "/admin/login?message=admin_password_reset_self"
    )
    clear_cookie = response.headers.get("set-cookie", "")
    assert f"{SESSION_COOKIE}=" in clear_cookie
    assert "Max-Age=0" in clear_cookie or "Expires=" in clear_cookie
    # The server-set cookie is now cleared from this client's jar by the
    # app's own delete-cookie header (real browser semantics).
    assert SESSION_COOKIE not in dict(actor_client.cookies)

    # The secret-free safe-login flash (no password/hash in it).
    login_body = actor_client.get(
        "/admin/login?message=admin_password_reset_self"
    ).text
    assert "Your password was reset" in login_body
    assert new_password not in login_body

    # The revoked actor session is refused even when the OLD token is
    # presented explicitly (a fresh client, so no jar state is involved).
    stale_client = _secondary_client(env218["app"], env218["client"].portal)
    stale_client.cookies.set(SESSION_COOKIE, old_token, domain="testserver.local")
    assert stale_client.get("/admin", follow_redirects=False).status_code == 303

    # New password signs in; the old password is refused.
    _login(stale_client, email=root2["email"], password=new_password)
    _login_refused(stale_client, email=root2["email"], password=root2["password"])

    # Native committed state: the actor's session revoked, exact audit.
    sessions = _sessions_for_admin(db, root2["id"])
    assert len(sessions) == 2  # original + the new-password login
    original = [s for s in sessions if s.revoked_at is not None]
    assert len(original) == 1
    audits = _audit_rows(db, "admin_user_password_reset", entity_id=root2["id"])
    assert len(audits) == 1
    assert audits[0].admin_user_id == root2["id"]  # actor == target (self)
    assert audits[0].new_values["revoked_count"] == 1
    assert audits[0].new_values["reason"] == "218 self reset"


# ---------------------------------------------------------------------------
# 5. Commit-time duplicate race: deterministic real-PG unique-index wait
# ---------------------------------------------------------------------------


def test_create_duplicate_race_settles_one_row_and_safe_409(
    env218: dict[str, Any],
) -> None:
    client: TestClient = env218["client"]
    db = env218["database_url"]
    email = f"218-race-{uuid.uuid4().hex[:10]}@example.test"

    t1_flushed = threading.Event()
    t1_go = threading.Event()

    async def _holder_run(session) -> None:
        # A concurrent committer for the SAME email: flush (real unique
        # index entry) but hold the transaction open.
        async with session.begin():
            session.add(
                AdminUser(
                    email=email,
                    display_name="218 race seed",
                    password_hash=hash_admin_password("race-seed-pw-218"),
                    role="admin",
                    is_active=True,
                )
            )
            await session.flush()
            t1_flushed.set()
            assert t1_go.wait(timeout=90), "holder proceed timed out"

    def _holder_thread() -> None:
        _db_worker(db, _holder_run)

    holder = threading.Thread(target=_holder_thread, daemon=True)
    holder.start()
    assert t1_flushed.wait(timeout=60), "holder never flushed the racing row"

    box: dict[str, Any] = {}

    def _http_thread() -> None:
        csrf = _page_csrf(client, f"{BASE}/create")
        box["resp"] = client.post(
            f"{BASE}/create",
            data={
                "csrf_token": csrf,
                "email": email,
                "display_name": "218 race gui",
                "password": "race-gui-pw-218",
                "password_confirmation": "race-gui-pw-218",
                "role": "admin",
                "confirm_create": "1",
                "confirm_superadmin": "",
                "reason": "218 race create",
            },
            follow_redirects=False,
        )

    # The holder ALREADY holds the uncommitted unique index entry: only
    # now start the GUI create, so the observed wait is on the real PG
    # index lock (READ COMMITTED pre-check sees the uncommitted row not).
    http = threading.Thread(target=_http_thread, daemon=True)
    http.start()

    # Deterministic native-PG synchronization: wait until the GUI
    # backend is actually WAITING on the real lock (observed PG state).
    _wait_lock_waiters(db)

    # Now the holder commits; the GUI INSERT must receive the real unique
    # violation and settle into the honest fixed 409.
    t1_go.set()
    holder.join(timeout=90)
    http.join(timeout=90)
    assert not holder.is_alive() and not http.is_alive()

    response: Any = box["resp"]
    assert response.status_code == 409
    body = response.text
    assert "already exists" in body
    # No raw SQL/exception/hash text in the fixed outcome.
    for fragment in (
        "duplicate key",
        "UniqueViolation",
        "IntegrityError",
        "psycopg",
        "asyncpg",
        "$argon2id$",
        "race-gui-pw-218",
    ):
        assert fragment not in body

    # Exactly ONE row for the email; the refused GUI create wrote nothing.
    assert _admin_count_by_email(db, email) == 1
    assert _audit_rows(db, "admin_user_created") == [] or all(
        row.entity_id != _admin_by_email(db, email).id
        for row in _audit_rows(db, "admin_user_created")
    )


# ---------------------------------------------------------------------------
# 6. Pre-commit audit fault on reset: complete native rollback
# ---------------------------------------------------------------------------


def test_reset_precommit_audit_fault_rolls_back_natively(
    env218: dict[str, Any],
) -> None:
    client: TestClient = env218["client"]
    db = env218["database_url"]
    accounts = env218["accounts"]
    target2 = accounts["target2"]
    new_password = "Pw-218-target2-would-be-pw"

    # A real session row for the target (so revocation is observable).
    target_client = _secondary_client(env218["app"], env218["client"].portal)
    _login(target_client, email=target2["email"], password=target2["password"])
    before = _admin_by_email(db, target2["email"])
    assert len(_sessions_for_admin(db, target2["id"])) == 1

    page = client.get(f"{BASE}/reset", params={"admin_id": str(target2["id"])})
    csrf = CSRF_RE.search(page.text).group(1)

    original_add = AuditRepository.add_audit_log

    async def _failing_add(self, **kwargs: Any) -> Any:
        if kwargs.get("action") == "admin_user_password_reset":
            raise RuntimeError("218 pre-commit audit fault seam")
        return await original_add(self, **kwargs)

    AuditRepository.add_audit_log = _failing_add
    try:
        response = client.post(
            f"{BASE}/reset?admin_id={target2['id']}",
            data={
                "csrf_token": csrf,
                "admin_id": str(target2["id"]),
                "password": new_password,
                "password_confirmation": new_password,
                "confirm_reset": "1",
                "reason": "218 rollback probe",
            },
            follow_redirects=False,
        )
    finally:
        AuditRepository.add_audit_log = original_add

    assert response.status_code == 500
    assert "could not be confirmed" in response.text
    assert "nothing was committed" not in response.text

    # WHOLE transaction rolled back natively: hash unchanged (old password
    # still verifies), the session is NOT revoked, and NO audit row exists.
    after = _admin_by_email(db, target2["email"])
    assert after.password_hash == before.password_hash
    assert verify_admin_password(target2["password"], after.password_hash)
    assert not verify_admin_password(new_password, after.password_hash)
    sessions = _sessions_for_admin(db, target2["id"])
    assert len(sessions) == 1
    assert all(s.revoked_at is None for s in sessions)
    assert _audit_rows(db, "admin_user_password_reset", entity_id=target2["id"]) == []
    # The target's session still works (nothing was revoked).
    assert target_client.get("/admin", follow_redirects=False).status_code == 200


# ---------------------------------------------------------------------------
# 7. Concurrent login/reset, LOGIN-FIRST ordering
# ---------------------------------------------------------------------------


def test_concurrent_login_reset_login_first_session_revoked(
    env218: dict[str, Any],
) -> None:
    app = env218["app"]
    client: TestClient = env218["client"]
    db = env218["database_url"]
    accounts = env218["accounts"]
    race_a = accounts["race_a"]
    root = accounts["superadmin"]
    new_password = "Pw-218-race-a-new-pw"
    assert _sessions_for_admin(db, race_a["id"]) == []

    login_at_commit = threading.Event()
    login_proceed = threading.Event()
    original = app.state.db_sessionmaker
    # The phased GUI LOGIN transaction holds its real admin-row lock at
    # its real before_commit (the commit is delayed) until
    # ``login_proceed``: the reset below is GUARANTEED to observe and
    # wait on that real PG lock.
    app.state.db_sessionmaker = _PhaseBarrierSessionmaker(
        original,
        marker="admin_login_succeeded",
        at_commit=login_at_commit,
        proceed=login_proceed,
    )

    login_box: dict[str, Any] = {}

    def _login_thread() -> None:
        tc = _secondary_client(app, client.portal)
        login_box["resp"] = _login(
            tc, email=race_a["email"], password=race_a["password"]
        )
        login_box["client"] = tc  # keep the cookie jar alive for the probe

    login = threading.Thread(target=_login_thread, daemon=True)
    login.start()
    # The login transaction now HOLDS the row lock at its real
    # before_commit (verification done, session row flushed).
    assert login_at_commit.wait(timeout=90), "login never reached commit"

    # The counterparty reset: the REAL shared-service transaction on a
    # dedicated engine/loop (216 holder pattern). Its FOR UPDATE must
    # block on the login's held real PG row lock.
    reset_box: dict[str, Any] = {}

    def _reset_thread() -> None:
        try:
            _reset_worker(
                db,
                target_id=race_a["id"],
                password_hash=hash_admin_password(new_password),
                actor_id=root["id"],
                reason="218 race reset (login first)",
            )
            reset_box["done"] = True
        except BaseException as exc:  # propagated below
            reset_box["error"] = exc

    # The login ALREADY holds the row lock: only now start the reset, so
    # the observed wait is on the real held PG lock (not thread startup).
    reset = threading.Thread(target=_reset_thread, daemon=True)
    reset.start()

    # Deterministic native-PG synchronization: wait until the reset
    # backend is actually WAITING on the real FOR UPDATE lock (observed
    # PG state), then prove the holder window was real.
    _wait_for_update_waiters(db)
    assert reset.is_alive(), "reset did not wait on the held PG row lock"

    # Release the login (real commit, real lock release); the reset then
    # acquires the lock and must revoke the session the login committed.
    login_proceed.set()
    login.join(timeout=120)
    reset.join(timeout=120)
    app.state.db_sessionmaker = original
    assert not login.is_alive() and not reset.is_alive()
    assert reset_box.get("done") is True, reset_box.get("error")

    # The login SUCCEEDED (it verified under the lock before the reset)
    # ...
    assert login_box["resp"].status_code == 303
    # ... but the reset that waited on the lock revoked the session that
    # login committed: the cookie is now refused.
    assert (
        login_box["client"].get("/admin", follow_redirects=False).status_code == 303
    )

    row = _admin_by_email(db, race_a["email"])
    assert verify_admin_password(new_password, row.password_hash)
    sessions = _sessions_for_admin(db, race_a["id"])
    assert len(sessions) == 1
    assert all(s.revoked_at is not None for s in sessions)
    audits = _audit_rows(db, "admin_user_password_reset", entity_id=race_a["id"])
    assert len(audits) == 1
    assert audits[0].admin_user_id == root["id"]
    assert audits[0].new_values["revoked_count"] == 1


# ---------------------------------------------------------------------------
# 8. Concurrent login/reset, RESET-FIRST ordering
# ---------------------------------------------------------------------------


def test_concurrent_login_reset_reset_first_superseded_denied(
    env218: dict[str, Any],
) -> None:
    app = env218["app"]
    client: TestClient = env218["client"]
    db = env218["database_url"]
    accounts = env218["accounts"]
    race_b = accounts["race_b"]
    new_password = "Pw-218-race-b-new-pw"
    assert _sessions_for_admin(db, race_b["id"]) == []

    reset_at_commit = threading.Event()
    reset_proceed = threading.Event()
    new_hash = hash_admin_password(new_password)

    reset_box: dict[str, Any] = {}

    def _reset_thread() -> None:
        try:
            _reset_worker(
                db,
                target_id=race_b["id"],
                password_hash=new_hash,
                actor_id=accounts["superadmin"]["id"],
                reason="218 race reset (reset first)",
                barrier=(reset_at_commit, reset_proceed),
            )
            reset_box["done"] = True
        except BaseException as exc:  # propagated below
            reset_box["error"] = exc

    # The phased RESET transaction (real shared-service transaction on a
    # dedicated engine/loop) holds its real admin-row lock at its real
    # before_commit (the commit is delayed) until ``reset_proceed``.
    reset = threading.Thread(target=_reset_thread, daemon=True)
    reset.start()
    assert reset_at_commit.wait(timeout=90), "reset never reached commit"

    login_box: dict[str, Any] = {}

    def _login_thread() -> None:
        tc = _secondary_client(app, client.portal)
        page = tc.get("/admin/login")
        assert page.status_code == 200
        csrf = CSRF_RE.search(page.text).group(1)
        # The SUPERSEDED password: its FOR UPDATE must wait on the held
        # real PG row lock, and the fresh locked read must verify against
        # the NEW hash after the reset commits.
        login_box["resp"] = tc.post(
            "/admin/login",
            data={
                "csrf_token": csrf,
                "email": race_b["email"],
                "password": race_b["password"],
            },
            follow_redirects=False,
        )

    # The reset ALREADY holds the row lock: only now start the login, so
    # the observed wait is on the real held PG lock (not thread startup).
    login = threading.Thread(target=_login_thread, daemon=True)
    login.start()

    # Deterministic native-PG synchronization: wait until the login
    # backend is actually WAITING on the real FOR UPDATE lock (observed
    # PG state), then prove the holder window was real.
    _wait_for_update_waiters(db)
    assert login.is_alive(), "login did not wait on the held PG row lock"

    # Release the reset (real commit, real lock release); the login then
    # acquires the lock and must verify the superseded password against
    # the fresh (new) hash.
    reset_proceed.set()
    reset.join(timeout=120)
    login.join(timeout=120)
    assert not reset.is_alive() and not login.is_alive()
    assert reset_box.get("done") is True, reset_box.get("error")

    # The login was refused - generic failure, no session cookie.
    assert login_box["resp"].status_code == 401
    assert "Invalid email or password." in login_box["resp"].text
    assert SESSION_COOKIE not in login_box["resp"].headers.get("set-cookie", "")

    row = _admin_by_email(db, race_b["email"])
    assert verify_admin_password(new_password, row.password_hash)
    assert _sessions_for_admin(db, race_b["id"]) == []  # no session created
    audits = _audit_rows(db, "admin_user_password_reset", entity_id=race_b["id"])
    assert len(audits) == 1
    assert audits[0].new_values["revoked_count"] == 0
    # The existing failed-login audit behavior is preserved.
    failures = _audit_rows(db, "admin_login_failed", entity_id=race_b["id"])
    assert failures and failures[-1].new_values["email"] == race_b["email"]

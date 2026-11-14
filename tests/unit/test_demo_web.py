"""Objective 224-c unit evidence: the isolated demo web entry.

Database-independent: the ASGI app is driven through a fake control
facade (the same Protocol the real ``PgDemoWebFacade`` implements),
and ``DemoWebConfig`` / the signed-payload helpers are tested directly.
Real web-role grant/privilege evidence lives in
tests/integration/test_demo_web_postgres.py.

Covers: default-off refusal and safe port parsing, enabled validation
fail-closed, signed token law (tamper/expiry/future/oversize),
zero-active-account 404 on every route, constant login failures with
the precomputed dummy-Argon2 uniform path, CSRF and pending-cookie
tamper refusal, the live account fence on every wait poll (disable and
credential reset deny immediately), bounded form bodies (oversized
413, wrong content type 400), exact one-session issuance, per-use
session validation, logout revocation, /v1 absence, the 224-e
default-deny /admin gate (closed admission law, canonical-UUID detail
components, session-binding refusals, preflight dispose, unsafe-method
no-op cuts, CSRF-verified demo sign-out with confirmed-revocation
law), and web-path import isolation (no privileged worker module in
the web process).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from argon2 import PasswordHasher, Type
from httpx import ASGITransport, AsyncClient

from slaif_gateway.api import demo_admin_gate as damg
from slaif_gateway.api import fake_admin as fa
from slaif_gateway.db.repositories.fake_admin_accounts import (
    FakeAdminAccountFacts,
    FakeAdminLoginCredential,
)
from slaif_gateway.demo_web import (
    CSRF_TTL_S,
    PENDING_TTL_S,
    DemoWebConfig,
    DemoWebConfigError,
    make_signed_payload,
    verify_signed_payload,
    create_demo_app,
)
from slaif_gateway.services.demo_web_control import (
    DemoSessionIssuedResult,
    DemoSnapshotRequestProjection,
    DemoWebControlError,
    DemoWebSessionProjection,
)

_PW_HASHER = PasswordHasher(type=Type.ID)
SECRET = "unit-test-cookie-secret-0123456789-0123456789"


def _config(**overrides) -> DemoWebConfig:
    base = dict(
        enabled=True,
        control_host="127.0.0.1",
        control_port=5432,
        control_database="slaif_gateway",
        control_user="slaif_demo_web",
        control_password="unit-test-worker-password",
        cookie_secret=SECRET,
        copy_host="127.0.0.1",
        copy_port=5432,
        copy_user="slaif_demo_copy",
        copy_password="unit-test-copy-password",
    )
    base.update(overrides)
    return DemoWebConfig(**base)


# --- DemoWebConfig ---------------------------------------------------------------


def test_config_default_off_from_empty_env():
    cfg = DemoWebConfig.from_env({})
    assert cfg.enabled is False


def test_config_malformed_port_off_stays_bootable():
    # A malformed optional port must NOT break a default-off startup.
    cfg = DemoWebConfig.from_env({"DEMO_WEB_CONTROL_PORT": "not-a-port"})
    assert cfg.enabled is False
    assert cfg.control_port == 0


def test_config_malformed_port_enabled_refuses():
    with pytest.raises(DemoWebConfigError):
        DemoWebConfig.from_env(
            {
                "DEMO_WEB_ENABLED": "true",
                "DEMO_WEB_CONTROL_HOST": "127.0.0.1",
                "DEMO_WEB_CONTROL_PORT": "not-a-port",
                "DEMO_WEB_CONTROL_DATABASE": "db",
                "DEMO_WEB_CONTROL_USER": "web",
                "DEMO_WEB_CONTROL_PASSWORD": "pw",
                "DEMO_WEB_COOKIE_SECRET": "x" * 40,
            }
        )


def test_config_enabled_missing_fields_refuses():
    with pytest.raises(DemoWebConfigError):
        DemoWebConfig.from_env({"DEMO_WEB_ENABLED": "1"})


def test_config_enabled_weak_secret_refuses():
    with pytest.raises(DemoWebConfigError):
        DemoWebConfig.from_env(
            {
                "DEMO_WEB_ENABLED": "true",
                "DEMO_WEB_CONTROL_HOST": "127.0.0.1",
                "DEMO_WEB_CONTROL_PORT": "5432",
                "DEMO_WEB_CONTROL_DATABASE": "db",
                "DEMO_WEB_CONTROL_USER": "web",
                "DEMO_WEB_CONTROL_PASSWORD": "pw",
                "DEMO_WEB_COOKIE_SECRET": "short",
            }
        )


def test_config_enabled_bad_identifier_refuses():
    with pytest.raises(DemoWebConfigError):
        DemoWebConfig.from_env(
            {
                "DEMO_WEB_ENABLED": "true",
                "DEMO_WEB_CONTROL_HOST": "127.0.0.1",
                "DEMO_WEB_CONTROL_PORT": "5432",
                "DEMO_WEB_CONTROL_DATABASE": "db; DROP TABLE x",
                "DEMO_WEB_CONTROL_USER": "web",
                "DEMO_WEB_CONTROL_PASSWORD": "pw",
                "DEMO_WEB_COOKIE_SECRET": "x" * 40,
            }
        )


def test_config_engine_url_quotes_credentials():
    cfg = _config(control_password="p@ss:word")
    url = cfg.engine_url()
    assert "p%40ss%3Aword" in url
    assert "p@ss:word" not in url


def test_config_repr_never_echoes_secrets():
    cfg = _config()
    assert "unit-test-worker-password" not in repr(cfg)
    assert SECRET not in repr(cfg)


# --- signed payload helpers ---------------------------------------------------------


def test_signed_payload_roundtrip():
    token = make_signed_payload(SECRET, "csrf", "abc", 600, now=1000.0)
    assert verify_signed_payload(SECRET, "csrf", token, 600, now=1100.0) == "abc"


def test_signed_payload_tampered_signature_refused():
    token = make_signed_payload(SECRET, "csrf", "abc", 600, now=1000.0)
    body, sig = token.split(".", 1)
    flipped = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert verify_signed_payload(SECRET, "csrf", f"{body}.{flipped}", 600, now=1100.0) is None


def test_signed_payload_wrong_purpose_refused():
    token = make_signed_payload(SECRET, "csrf", "abc", 600, now=1000.0)
    assert verify_signed_payload(SECRET, "pending", token, 600, now=1100.0) is None


def test_signed_payload_expired_refused():
    token = make_signed_payload(SECRET, "csrf", "abc", 600, now=1000.0)
    assert verify_signed_payload(SECRET, "csrf", token, 600, now=1601.0) is None


def test_signed_payload_future_refused():
    token = make_signed_payload(SECRET, "csrf", "abc", 600, now=5000.0)
    assert verify_signed_payload(SECRET, "csrf", token, 600, now=1000.0) is None


def test_signed_payload_oversized_refused_before_decode():
    token = make_signed_payload(SECRET, "csrf", "abc", 600, now=1000.0)
    bloated = token + "A" * 10000
    assert verify_signed_payload(SECRET, "csrf", bloated, 600, now=1100.0) is None


def test_signed_payload_malformed_refused():
    assert verify_signed_payload(SECRET, "csrf", None, 600) is None
    assert verify_signed_payload(SECRET, "csrf", "", 600) is None
    assert verify_signed_payload(SECRET, "csrf", "nodash", 600) is None
    assert verify_signed_payload(SECRET, "csrf", "a.b.c", 600) is None
    assert verify_signed_payload(SECRET, "csrf", "!!!.sig", 600) is None


# --- fake facade + app harness -------------------------------------------------------

ACC = uuid.UUID("11111111-1111-4111-8111-111111111111")
REQ = uuid.UUID("22222222-2222-4222-8222-222222222222")
OTHER_ACC = uuid.UUID("33333333-3333-4333-8333-333333333333")


class FakeFacade:
    """In-memory control facade simulating the reviewed web-role law."""

    def __init__(self) -> None:
        self.active = 1
        self.enabled = True
        self.live_gen = 1
        self.request_state = "pending"
        self.request_gen = 1
        self.expires_delta = timedelta(minutes=30)
        self.issued = 0
        self.revoked = 0
        self.cred_lookups = 0
        # 224-d knobs: the exact copy binding as stored on the row.
        self.worker_target_db: str | None = None
        self.request_account_id = ACC

    def _request(self) -> DemoSnapshotRequestProjection:
        """Live projection: state/gen/expiry reflect current facade knobs."""
        now = datetime.now(timezone.utc)
        return DemoSnapshotRequestProjection(
            id=REQ,
            account_id=self.request_account_id,
            credential_generation=self.request_gen,
            state=self.request_state,
            failure_code=None,
            worker_job_id=None,
            worker_target_db=self.worker_target_db,
            created_at=now,
            deadline_at=now,
            expires_at=now + self.expires_delta,
        )

    # -- facade protocol --
    async def close(self) -> None:
        pass

    async def count_active_accounts(self) -> int:
        return self.active

    async def get_login_credential(self, username: str) -> FakeAdminLoginCredential | None:
        self.cred_lookups += 1
        if username != "op":
            return None
        return FakeAdminLoginCredential(
            id=ACC,
            username="op",
            password_hash=_PW_HASHER.hash("good-pw"),
            is_enabled=self.enabled,
            credential_generation=self.live_gen,
        )

    async def get_account_facts(self, account_id: uuid.UUID) -> FakeAdminAccountFacts | None:
        if account_id != ACC:
            return None
        return FakeAdminAccountFacts(
            id=ACC, is_enabled=self.enabled, credential_generation=self.live_gen
        )

    async def create_request(self, account_id: uuid.UUID) -> DemoSnapshotRequestProjection:
        assert account_id == ACC
        return self._request()

    async def get_request(self, request_id: uuid.UUID) -> DemoSnapshotRequestProjection | None:
        if request_id != REQ:
            return None
        return self._request()

    async def create_session(
        self, *, account_id: uuid.UUID, request_id: uuid.UUID
    ) -> DemoSessionIssuedResult:
        self.issued += 1
        now = datetime.now(timezone.utc)
        return DemoSessionIssuedResult(
            token="unit-token-1",
            session=DemoWebSessionProjection(
                id=uuid.uuid4(),
                account_id=ACC,
                credential_generation=self.live_gen,
                request_id=request_id,
                created_at=now,
                expires_at=now + timedelta(minutes=30),
                revoked_at=None,
            ),
        )

    async def validate_session(
        self, *, account_id: uuid.UUID, token: str
    ) -> DemoWebSessionProjection:
        if account_id != ACC or token != "unit-token-1":
            raise DemoWebControlError("web_session_not_found", "no")
        now = datetime.now(timezone.utc)
        return DemoWebSessionProjection(
            id=uuid.uuid4(),
            account_id=ACC,
            credential_generation=self.live_gen,
            request_id=REQ,
            created_at=now,
            expires_at=now + timedelta(minutes=30),
            revoked_at=None,
        )

    async def revoke_session(
        self, *, account_id: uuid.UUID, token: str
    ) -> DemoWebSessionProjection | None:
        if account_id == ACC and token == "unit-token-1":
            self.revoked += 1
        return None

    async def session_facts_by_token(self, token: str) -> DemoWebSessionProjection | None:
        if token != "unit-token-1":
            return None
        now = datetime.now(timezone.utc)
        return DemoWebSessionProjection(
            id=uuid.uuid4(),
            account_id=ACC,
            credential_generation=self.live_gen,
            request_id=REQ,
            created_at=now,
            expires_at=now + timedelta(minutes=30),
            revoked_at=None,
        )


def _app(fake: FakeFacade, copy_reader_factory=None, display_reader_factory=None):
    return create_demo_app(
        _config(),
        facade=fake,
        copy_reader_factory=copy_reader_factory,
        display_reader_factory=display_reader_factory,
    )


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://demo.test")


async def _login(client: AsyncClient, username: str = "op", password: str = "good-pw"):
    r = await client.get("/fakeadmin/login")
    csrf = r.cookies.get("slaif_demo_csrf")
    return await client.post(
        "/fakeadmin/login",
        data={"username": username, "password": password, "csrf": csrf},
    )


# --- startup / surface --------------------------------------------------------------


def test_create_app_refuses_when_disabled():
    with pytest.raises(DemoWebConfigError):
        create_demo_app(_config(enabled=False), facade=FakeFacade())


# --- 224-e: request-local sessionmaker seam -------------------------------------


def _bare_request(app, state: dict | None = None):
    from starlette.requests import Request

    scope = {"type": "http", "app": app, "state": dict(state or {})}
    return Request(scope)


def test_demo_sessionmaker_uses_request_local_factory_only():
    from types import SimpleNamespace

    from slaif_gateway.db.session import get_sessionmaker_from_app

    app = _app(FakeFacade())
    local_factory = object()
    request = _bare_request(app, {"demo_admin": SimpleNamespace(sessionmaker=local_factory)})
    assert get_sessionmaker_from_app(request) is local_factory


def test_demo_sessionmaker_fails_closed_despite_populated_global_factory():
    # 224-e: a demo request that never passed the central gate (no
    # request.state.demo_admin) must fail closed even if an app-
    # GLOBAL factory were accidentally present.
    from slaif_gateway.db.session import get_sessionmaker_from_app

    app = _app(FakeFacade())
    app.state.db_sessionmaker = object()  # deliberate misconfiguration
    request = _bare_request(app)
    with pytest.raises(RuntimeError):
        get_sessionmaker_from_app(request)


def test_normal_app_sessionmaker_unchanged():
    # A normal (marker-free) app keeps the exact global-factory law.
    from fastapi import FastAPI

    from slaif_gateway.db.session import get_sessionmaker_from_app

    app = FastAPI()
    global_factory = object()
    app.state.db_sessionmaker = global_factory
    assert get_sessionmaker_from_app(_bare_request(app)) is global_factory


def test_create_app_refuses_direct_enabled_config_missing_copy_binding():
    # The SAME fail-closed law for a directly supplied config (not
    # only from_env): an enabled app cannot start without the
    # copy-reader binding, whatever the facade.
    with pytest.raises(DemoWebConfigError) as exc:
        create_demo_app(
            _config(copy_host=""), facade=FakeFacade()
        )
    assert exc.value.code == "demo_web_misconfigured"


def _mounted_admin_family_paths() -> set[str]:
    """The exact mounted /admin route table (the same router modules
    ``create_demo_app`` mounts; each router's own route list carries the
    full prefixed paths)."""
    from slaif_gateway.api import (
        admin,
        admin_accounting_operations,
        admin_accounts,
        admin_catalog_refresh,
        admin_compatibility,
        admin_email_operations,
        admin_key_batch,
        admin_key_clone,
        admin_operations,
        admin_provider_route_configuration,
        admin_record_choices,
        admin_replay_maintenance,
        admin_reports,
        branding,
    )

    routers = (
        branding.router,
        admin_record_choices.router,
        admin.router,
        admin_email_operations.router,
        admin_accounting_operations.router,
        admin_accounts.router,
        admin_catalog_refresh.router,
        admin_key_clone.router,
        admin_key_batch.router,
        admin_provider_route_configuration.router,
        admin_operations.router,
        admin_compatibility.router,
        admin_replay_maintenance.router,
        admin_reports.router,
    )
    paths: set[str] = set()
    for router in routers:
        for route in router.routes:
            p = getattr(route, "path", None)
            if isinstance(p, str):
                paths.add(p)
    return paths


def test_demo_app_route_table_gated_admin_only():
    """224-e route-table enumeration: /fakeadmin plus the mounted
    (gate-controlled) /admin family only - no /v1, provider, mail or
    worker route exists in the demo process."""
    app = _app(FakeFacade())
    top_paths = {getattr(r, "path", "") for r in app.routes}
    for p in top_paths:
        assert p == "" or p.startswith(
            ("/fakeadmin", "/admin", "/docs", "/openapi.json", "/redoc")
        ), p
    assert "/v1" not in top_paths
    # the mounted admin family is /admin-only by construction...
    family = _mounted_admin_family_paths()
    assert family
    for p in family:
        assert p.startswith("/admin"), p
    # ...and includes the 224-e admitted set plus the unreviewed
    # families (mounted, gate-default-denied).
    for p in (
        "/admin/keys",
        "/admin/owners",
        "/admin/institutions",
        "/admin/cohorts",
        "/admin/record-choices",
        "/admin/providers",
        "/admin/login",
    ):
        assert p in family, p


def test_disabled_env_app_refuses_without_env_vars(monkeypatch):
    monkeypatch.delenv("DEMO_WEB_ENABLED", raising=False)
    with pytest.raises(DemoWebConfigError):
        create_demo_app(None)


def test_v1_absent_admin_gated_on_demo_app():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            assert (await client.get("/v1/models")).status_code == 404
            # 224-e: an admitted admin page WITHOUT a session redirects
            # to the demo entry (never the copied tables)...
            r = await client.get("/admin")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            # ...and unreviewed admin GETs stay default-denied.
            assert (await client.get("/admin/openai-assisted")).status_code == 404
            # 224-f: the new DB-backed families are admitted too
            # (no session -> demo entry redirect); 224-i admits the
            # routes list/detail and the core form GETs as well.
            assert (await client.get("/admin/providers")).status_code == 303
            assert (await client.get("/admin/usage")).status_code == 303
            assert (await client.get("/admin/routes")).status_code == 303
            assert (await client.get("/admin/keys/create")).status_code == 303

    asyncio.run(run())


def test_web_path_import_isolation_subprocess():
    """Importing the demo web module chain must not load the privileged
    worker/snapshot modules (fresh interpreter = no test contamination)."""
    code = (
        "import sys\n"
        "import slaif_gateway.demo_web\n"
        "import slaif_gateway.api.fake_admin\n"
        "bad = [m for m in sys.modules if m in (\n"
        "    'slaif_gateway.services.demo_web_worker',\n"
        "    'slaif_gateway.services.demo_snapshot',\n"
        "    'slaif_gateway.services.demo_snapshot_sanitize',\n"
        "    'slaif_gateway.services.demo_snapshot_files',\n"
        ")]\n"
        "assert not bad, bad\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = "app"
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )


# --- zero enabled accounts: 404 on every route (no oracle) ---------------------------


def test_zero_active_accounts_404_every_route():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            assert (await client.get("/fakeadmin/login")).status_code == 404
            assert (await client.get("/fakeadmin/wait")).status_code == 404
            assert (await client.get("/fakeadmin/wait/status")).status_code == 404
            assert (await client.get("/fakeadmin/ready")).status_code == 404
            r = await client.post("/fakeadmin/login", data={"username": "op", "password": "x"})
            assert r.status_code == 404
            r = await client.post("/fakeadmin/logout", data={"csrf": "x"})
            assert r.status_code == 404

    asyncio.run(run())


# --- login behavior --------------------------------------------------------------------


def test_valid_login_redirects_with_pending_cookie():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            r = await _login(client)
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/wait"
            assert "slaif_demo_pending" in r.cookies
            assert "slaif_demo_csrf" not in r.cookies

    asyncio.run(run())


def test_wrong_password_constant_401():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            r = await _login(client, password="BAD")
            assert r.status_code == 401
            assert "Incorrect username or password." in r.text
            assert "good-pw" not in r.text
            assert "slaif_demo_pending" not in r.cookies

    asyncio.run(run())


def test_unknown_username_constant_401_same_path():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            r = await _login(client, username="ghost", password="whatever")
            assert r.status_code == 401
            assert "Incorrect username or password." in r.text
            assert "ghost" not in r.text

    asyncio.run(run())


def test_disabled_account_constant_401():
    async def run():
        fake = FakeFacade()
        fake.enabled = False
        # NOTE: an all-disabled world also reads as zero ACTIVE accounts
        # for the 404 oracle law only when NO enabled account remains;
        # here the fake reports active=1 (another enabled account exists)
        # so the disabled account still gets the constant 401.
        fake.active = 1
        app = _app(fake)
        async with _client(app) as client:
            r = await _login(client)
            assert r.status_code == 401
            assert "Incorrect username or password." in r.text

    asyncio.run(run())


def test_dummy_hash_precomputed_and_uniform_path():
    """The dummy Argon2id hash is valid and precomputed at import time,
    so the first unknown-user attempt takes the same verification path
    (and cost class) as a genuine wrong-password check."""
    assert isinstance(fa._DUMMY_HASH, str)
    assert fa._DUMMY_HASH.startswith("$argon2id$")
    assert fa._dummy_hash() is fa._DUMMY_HASH
    # A genuine verify against the dummy hash works (no InvalidHashError)
    # and rejects any password.
    assert fa.verify_admin_password("some-password", fa._DUMMY_HASH) is False


def test_login_field_too_long_refused():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            r = await client.get("/fakeadmin/login")
            csrf = r.cookies["slaif_demo_csrf"]
            r = await client.post(
                "/fakeadmin/login",
                data={"username": "u" * 500, "password": "x", "csrf": csrf},
            )
            assert r.status_code == 400

    asyncio.run(run())


def test_login_csrf_mismatch_refused():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            await client.get("/fakeadmin/login")
            r = await client.post(
                "/fakeadmin/login",
                data={"username": "op", "password": "good-pw", "csrf": "forged"},
            )
            assert r.status_code == 400

    asyncio.run(run())


def test_login_csrf_expired_refused():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            # A validly signed CSRF token issued beyond its TTL.
            stale = make_signed_payload(
                SECRET, "csrf", uuid.uuid4().hex, CSRF_TTL_S,
                now=time.time() - CSRF_TTL_S - 10,
            )
            await client.get("/fakeadmin/login")
            client.cookies["slaif_demo_csrf"] = stale
            r = await client.post(
                "/fakeadmin/login",
                data={"username": "op", "password": "good-pw", "csrf": stale},
            )
            assert r.status_code == 400

    asyncio.run(run())


def test_csrf_non_ascii_cookie_refused_without_error():
    """A non-ASCII cookie value must be a safe refusal, never a
    compare_digest TypeError (the equality is on UTF-8 bytes)."""
    assert fa._check_csrf(SECRET, "\u00e9forged", "abc") is False
    assert fa._check_csrf(SECRET, None, "abc") is False
    # A well-formed token in the FIELD but a DIFFERENT (non-ASCII)
    # cookie is refused before any decode.
    good = fa.make_signed_payload(SECRET, "csrf", "abc", fa.CSRF_TTL_S)
    assert fa._check_csrf(SECRET, good + "\u00e9", good) is False
    # And the matching well-formed pair still passes.
    assert fa._check_csrf(SECRET, good, good) is True


def test_login_oversized_body_413_no_credential_lookup():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            before = fake.cred_lookups
            r = await client.post(
                "/fakeadmin/login",
                content=b"x" * (fa.FORM_BODY_MAX_BYTES + 1),
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert r.status_code == 413
            assert fake.cred_lookups == before

    asyncio.run(run())


def test_login_chunked_oversized_body_413():
    """A body streamed in chunks (no reliable Content-Length) is still
    capped on bytes actually received."""

    async def chunks():
        for _ in range(4):
            yield b"x" * 3000

    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            r = await client.post(
                "/fakeadmin/login",
                content=chunks(),
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
            assert r.status_code == 413

    asyncio.run(run())


def test_login_wrong_content_type_400():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            r = await client.post(
                "/fakeadmin/login",
                content=b'{"username":"op"}',
                headers={"content-type": "application/json"},
            )
            assert r.status_code == 400

    asyncio.run(run())


def test_login_attempt_bound_429():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        now = time.monotonic()
        # Seed the in-process window with the maximum failed attempts.
        fa._ATTEMPTS.failures.clear()
        try:
            for _ in range(fa.LOGIN_ATTEMPT_MAX):
                fa._ATTEMPTS.failures.append(now - 10)
            async with _client(app) as client:
                r = await client.get("/fakeadmin/login")
                csrf = r.cookies["slaif_demo_csrf"]
                r = await client.post(
                    "/fakeadmin/login",
                    data={"username": "op", "password": "x", "csrf": csrf},
                )
                assert r.status_code == 429
                assert "Retry-After" in r.headers
        finally:
            fa._ATTEMPTS.failures.clear()

    asyncio.run(run())


def test_login_attempt_window_prunes_old_failures():
    fa._ATTEMPTS.failures.clear()
    try:
        old = time.monotonic() - fa.LOGIN_ATTEMPT_WINDOW_S - 5
        fa._ATTEMPTS.failures.append(old)
        fa._ATTEMPTS.failures.append(time.monotonic())
        assert fa._ATTEMPTS.retry_after_s(time.monotonic()) == 0
    finally:
        fa._ATTEMPTS.failures.clear()


# --- wait flow ------------------------------------------------------------------------


async def _wait_client_with_pending(fake: FakeFacade, client: AsyncClient) -> None:
    """Log in so the client holds a valid signed pending cookie."""
    r = await client.get("/fakeadmin/login")
    csrf = r.cookies["slaif_demo_csrf"]
    r = await client.post(
        "/fakeadmin/login",
        data={"username": "op", "password": "good-pw", "csrf": csrf},
    )
    assert r.status_code == 303


def test_wait_pending_state_shows_waiting_no_session():
    async def run():
        fake = FakeFacade()
        fake.request_state = "pending"
        app = _app(fake)
        async with _client(app) as client:
            await _wait_client_with_pending(fake, client)
            r = await client.get("/fakeadmin/wait/status")
            assert r.json() == {"state": "waiting"}
            r = await client.get("/fakeadmin/wait")
            assert r.status_code == 200
            assert "Waiting" in r.text
            assert fake.issued == 0
            assert "slaif_demo_session" not in client.cookies

    asyncio.run(run())


def test_wait_status_never_issues_session_even_when_ready():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        app = _app(fake)
        async with _client(app) as client:
            await _wait_client_with_pending(fake, client)
            for _ in range(3):
                r = await client.get("/fakeadmin/wait/status")
                assert r.json() == {"state": "ready"}
            assert fake.issued == 0

    asyncio.run(run())


def test_wait_verified_issues_exactly_one_session():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        app = _app(fake)
        async with _client(app) as client:
            await _wait_client_with_pending(fake, client)
            r = await client.get("/fakeadmin/wait")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/ready"
            assert client.cookies.get("slaif_demo_session") == "unit-token-1"
            assert fake.issued == 1
            # The pending cookie is consumed: a repeat wait cannot reissue.
            await client.get("/fakeadmin/wait")
            assert fake.issued == 1
            assert "slaif_demo_session" in client.cookies

    asyncio.run(run())


def test_wait_pending_cookie_bad_signature_refused():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        app = _app(fake)
        async with _client(app) as client:
            await _wait_client_with_pending(fake, client)
            client.cookies["slaif_demo_pending"] = "forged.signature"
            r = await client.get("/fakeadmin/wait/status")
            assert r.json() == {"state": "unavailable"}
            await client.get("/fakeadmin/wait")
            assert fake.issued == 0

    asyncio.run(run())


def test_pending_ttl_matches_request_ttl():
    """The pending cookie lifetime is tied to the 224-a request TTL,
    so a legitimate bounded worker chain (221+222+223+re-proof, each
    capped at 300 s, plus queue time) can finish before the browser
    loses its pending binding."""
    from slaif_gateway.services.demo_web_control import REQUEST_TTL

    assert PENDING_TTL_S == int(REQUEST_TTL.total_seconds())
    assert PENDING_TTL_S >= 3 * 300 + 300  # the worst-case chain


def test_wait_pending_survives_long_worker_chain():
    """A pending cookie more than 900 s old (the old lifetime) on a
    still-unexpired verified request can STILL complete; the zero/
    disable/generation fences are unchanged."""
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        app = _app(fake)
        old_token = make_signed_payload(
            SECRET, "pending", f"{ACC}:{REQ}:{fake.live_gen}", PENDING_TTL_S,
            now=time.time() - 1000,
        )
        async with _client(app) as client:
            client.cookies.set(
                "slaif_demo_pending", old_token,
                domain="demo.test", path="/fakeadmin",
            )
            assert (await client.get("/fakeadmin/wait/status")).json() == {
                "state": "ready"
            }
            r = await client.get("/fakeadmin/wait")
            assert r.status_code == 303
            assert fake.issued == 1
            # fence still applies: disable -> denied, no second issue
            fake.enabled = False
            client.cookies.set(
                "slaif_demo_pending", old_token,
                domain="demo.test", path="/fakeadmin",
            )
            assert (await client.get("/fakeadmin/wait/status")).json() == {
                "state": "unavailable"
            }

    asyncio.run(run())


def test_wait_pending_cookie_expired_refused():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        app = _app(fake)
        stale = make_signed_payload(
            SECRET,
            "pending",
            f"{ACC}:{REQ}:{fake.live_gen}",
            PENDING_TTL_S,
            now=time.time() - PENDING_TTL_S - 10,
        )
        async with _client(app) as client:
            client.cookies["slaif_demo_pending"] = stale
            r = await client.get("/fakeadmin/wait/status")
            assert r.json() == {"state": "unavailable"}
            assert fake.issued == 0

    asyncio.run(run())


def test_wait_pending_cookie_foreign_request_refused():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        app = _app(fake)
        # Cookie claims the request belongs to a different account.
        forged = make_signed_payload(
            SECRET,
            "pending",
            f"{OTHER_ACC}:{REQ}:{fake.live_gen}",
            PENDING_TTL_S,
        )
        async with _client(app) as client:
            client.cookies["slaif_demo_pending"] = forged
            r = await client.get("/fakeadmin/wait/status")
            assert r.json() == {"state": "unavailable"}
            assert fake.issued == 0

    asyncio.run(run())


def test_wait_failed_state_shows_failed():
    async def run():
        fake = FakeFacade()
        fake.request_state = "failed"
        app = _app(fake)
        async with _client(app) as client:
            await _wait_client_with_pending(fake, client)
            assert (await client.get("/fakeadmin/wait/status")).json() == {"state": "failed"}
            r = await client.get("/fakeadmin/wait")
            assert "could not be prepared" in r.text

    asyncio.run(run())


def test_wait_disabled_account_denies_every_poll():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        app = _app(fake)
        async with _client(app) as client:
            await _wait_client_with_pending(fake, client)
            fake.enabled = False  # operator disables mid-wait
            assert (await client.get("/fakeadmin/wait/status")).json() == {
                "state": "unavailable"
            }
            r = await client.get("/fakeadmin/wait")
            assert "no longer available" in r.text
            assert fake.issued == 0

    asyncio.run(run())


def test_wait_account_reset_denies_every_poll():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        app = _app(fake)
        async with _client(app) as client:
            await _wait_client_with_pending(fake, client)
            fake.live_gen = 2  # password reset moves the generation
            assert (await client.get("/fakeadmin/wait/status")).json() == {
                "state": "unavailable"
            }
            r = await client.get("/fakeadmin/wait")
            assert "no longer available" in r.text
            assert fake.issued == 0

    asyncio.run(run())


def test_wait_account_deleted_denies_polls():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"

        class Deleted(FakeFacade):
            async def get_account_facts(self, account_id):
                return None

        app = create_demo_app(_config(), facade=Deleted())
        async with _client(app) as client:
            await _wait_client_with_pending(fake, client)
            assert (await client.get("/fakeadmin/wait/status")).json() == {
                "state": "unavailable"
            }
            assert fake.issued == 0

    asyncio.run(run())


def test_wait_verified_expired_timed_out():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.expires_delta = timedelta(seconds=-5)
        app = _app(fake)
        async with _client(app) as client:
            await _wait_client_with_pending(fake, client)
            assert (await client.get("/fakeadmin/wait/status")).json() == {
                "state": "timed_out"
            }
            assert fake.issued == 0

    asyncio.run(run())


# --- ready / logout ---------------------------------------------------------------------


def test_ready_requires_valid_session():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            # No session cookie -> bounce to login, cookie cleared.
            r = await client.get("/fakeadmin/ready")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            client.cookies["slaif_demo_session"] = "forged"
            r = await client.get("/fakeadmin/ready")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"

    asyncio.run(run())


def test_ready_page_states_browsing_not_enabled():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            client.cookies["slaif_demo_session"] = "unit-token-1"
            r = await client.get("/fakeadmin/ready")
            assert r.status_code == 200
            assert "not enabled yet" in r.text

    asyncio.run(run())


def test_ready_revalidates_every_use_disable_bounces():
    async def run():
        class Denied(FakeFacade):
            async def validate_session(self, *, account_id, token):
                raise DemoWebControlError("web_account_disabled", "disabled")

        app = create_demo_app(_config(), facade=Denied())
        async with _client(app) as client:
            client.cookies["slaif_demo_session"] = "unit-token-1"
            r = await client.get("/fakeadmin/ready")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"

    asyncio.run(run())


def test_logout_revokes_and_clears_all_cookies():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            # Match server-set cookie semantics (domain from the host),
            # so the server-side delete_cookie entries match exactly.
            client.cookies.set(
                "slaif_demo_session", "unit-token-1", domain="demo.test", path="/"
            )
            client.cookies.set(
                "slaif_demo_pending", "stale-pending", domain="demo.test", path="/fakeadmin"
            )
            r = await client.get("/fakeadmin/ready")
            csrf = r.cookies["slaif_demo_csrf"]
            r = await client.post("/fakeadmin/logout", data={"csrf": csrf})
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            assert fake.revoked == 1
            for name in ("slaif_demo_session", "slaif_demo_pending", "slaif_demo_csrf"):
                cookie = client.cookies.get(name)
                # deleted cookies may be absent or empty/expired
                assert cookie is None or cookie == "", name

    asyncio.run(run())


def test_demo_cookie_paths_session_root_others_narrow():
    """The session cookie is Path=/ (forward-compat with the authorized
    copy-backed GUI stage on the demo host); pending and CSRF cookies
    stay Path=/fakeadmin. Deletions use the SAME paths."""
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        app = _app(fake)
        async with _client(app) as client:
            # GET /login issues the CSRF cookie on the narrow path.
            r = await client.get("/fakeadmin/login")
            csrf_cookies = [
                c for c in r.headers.get_list("set-cookie")
                if c.startswith("slaif_demo_csrf=")
            ]
            assert csrf_cookies
            assert "path=/fakeadmin" in csrf_cookies[0].lower()
            csrf = r.cookies["slaif_demo_csrf"]
            # The login POST issues the pending cookie on the narrow path.
            r = await client.post(
                "/fakeadmin/login",
                data={"username": "op", "password": "good-pw", "csrf": csrf},
            )
            assert r.status_code == 303
            pending_cookies = [
                c for c in r.headers.get_list("set-cookie")
                if c.startswith("slaif_demo_pending=")
            ]
            assert pending_cookies
            assert "path=/fakeadmin" in pending_cookies[0].lower()
            # The verified wait issues the session cookie on Path=/.
            r = await client.get("/fakeadmin/wait")
            assert r.status_code == 303
            session_cookies = [
                c for c in r.headers.get_list("set-cookie")
                if c.startswith("slaif_demo_session=")
            ]
            assert session_cookies, r.headers.get_list("set-cookie")
            assert "path=/" in session_cookies[0].lower()
            assert "/fakeadmin" not in session_cookies[0].lower().split("path=/")[-1]
            assert "httponly" in session_cookies[0].lower()
            assert "samesite=strict" in session_cookies[0].lower()
            assert "secure" in session_cookies[0].lower()
            # Logout deletes each cookie with its own (matching) path.
            r = await client.get("/fakeadmin/ready")
            csrf = r.cookies["slaif_demo_csrf"]
            r = await client.post("/fakeadmin/logout", data={"csrf": csrf})
            deletes = {
                c.split("=", 1)[0]: c.lower()
                for c in r.headers.get_list("set-cookie")
                if "max-age=0" in c.lower()
            }
            assert "path=/" in deletes["slaif_demo_session"]
            assert "path=/fakeadmin" in deletes["slaif_demo_pending"]
            assert "path=/fakeadmin" in deletes["slaif_demo_csrf"]

    asyncio.run(run())


def test_logout_without_session_still_clears_and_redirects():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            await client.get("/fakeadmin/ready")  # 303 to login, no csrf set
            r = await client.get("/fakeadmin/login")
            csrf = r.cookies["slaif_demo_csrf"]
            r = await client.post("/fakeadmin/logout", data={"csrf": csrf})
            assert r.status_code == 303
            assert fake.revoked == 0

    asyncio.run(run())


# --- 224-d: copy-reader config, reader, and preview route ---------------------

from slaif_gateway.demo_web import (  # noqa: E402
    COPY_PREVIEW_TABLES,
    CopyReader,
    DemoWebError,
)

COPY_OK = "demo_snap_" + "a1" * 10  # valid closed name (20 hex)
CANARY_DB = "demo_snap_" + "deadbeef" * 5


def test_config_malformed_copy_port_enabled_refuses():
    with pytest.raises(DemoWebConfigError):
        DemoWebConfig.from_env(
            {
                "DEMO_WEB_ENABLED": "true",
                "DEMO_WEB_CONTROL_HOST": "127.0.0.1",
                "DEMO_WEB_CONTROL_PORT": "5432",
                "DEMO_WEB_CONTROL_DATABASE": "db",
                "DEMO_WEB_CONTROL_USER": "web",
                "DEMO_WEB_CONTROL_PASSWORD": "pw",
                "DEMO_WEB_COOKIE_SECRET": "x" * 40,
                "DEMO_WEB_COPY_HOST": "127.0.0.1",
                "DEMO_WEB_COPY_PORT": "not-a-port",
                "DEMO_WEB_COPY_USER": "reader",
                "DEMO_WEB_COPY_PASSWORD": "readerpw",
            }
        )


def test_config_enabled_missing_copy_fields_refuses():
    # The independent copy-reader connection is required for an
    # enabled entry; any gap fails closed before any publication.
    with pytest.raises(DemoWebConfigError):
        DemoWebConfig.from_env(
            {
                "DEMO_WEB_ENABLED": "true",
                "DEMO_WEB_CONTROL_HOST": "127.0.0.1",
                "DEMO_WEB_CONTROL_PORT": "5432",
                "DEMO_WEB_CONTROL_DATABASE": "db",
                "DEMO_WEB_CONTROL_USER": "web",
                "DEMO_WEB_CONTROL_PASSWORD": "pw",
                "DEMO_WEB_COOKIE_SECRET": "x" * 40,
                "DEMO_WEB_COPY_HOST": "127.0.0.1",
                "DEMO_WEB_COPY_PORT": "5432",
                "DEMO_WEB_COPY_USER": "reader",
                # missing DEMO_WEB_COPY_PASSWORD
            }
        )


def test_config_off_garbage_copy_values_stay_bootable():
    # A default-off entry never parses the optional copy values hard.
    cfg = DemoWebConfig.from_env(
        {"DEMO_WEB_COPY_PORT": "garbage", "DEMO_WEB_COPY_USER": "x;y"}
    )
    assert cfg.enabled is False


def test_copy_engine_url_enforces_closed_copy_name_law():
    cfg = _config(
        copy_host="127.0.0.1",
        copy_port=5432,
        copy_user="reader",
        copy_password="readerpw",
    )
    url = cfg.copy_engine_url(COPY_OK)
    assert url.startswith("postgresql+asyncpg://reader:")
    assert url.endswith(f"@127.0.0.1:5432/{COPY_OK}")
    for bad in ("evil_db", "demo_snap_" + "a" * 19, "demo_snap_" + "A" * 20,
                "demo_snap_" + "g" * 20, CANARY_DB + "x"):
        with pytest.raises(DemoWebError) as ei:
            cfg.copy_engine_url(bad)
        assert ei.value.code == "copy_binding_unavailable"


def test_copy_reader_constructor_refuses_malformed_name():
    cfg = _config(copy_host="127.0.0.1", copy_user="reader", copy_password="p")
    with pytest.raises(DemoWebError) as ei:
        CopyReader(cfg, "demo_snap_" + "a" * 21)
    assert ei.value.code == "copy_binding_unavailable"


def test_copy_reader_close_wraps_dispose_failure_safely():
    # A raw driver exception from dispose() must never escape the
    # reader: one safe refusal instead, no detail leaked.
    class _BoomEngine:
        def __init__(self) -> None:
            self.disposed = 0

        async def dispose(self) -> None:
            self.disposed += 1
            raise RuntimeError("driver boom postgresql://secret@x/y")

    engine = _BoomEngine()
    reader = CopyReader(
        _config(copy_host="h", copy_user="u", copy_password="p"), COPY_OK
    )
    reader._engine = engine  # type: ignore[assignment]
    with pytest.raises(DemoWebError) as ei:
        asyncio.run(reader.close())
    assert ei.value.code == "copy_binding_unavailable"
    assert "boom" not in str(ei.value)
    assert "secret" not in str(ei.value)
    assert engine.disposed == 1
    # A second close is a safe no-op.
    asyncio.run(reader.close())


class FakeCopyReader:
    """In-memory copy reader standing in for the per-request engine."""

    def __init__(self, counts=None, raise_code=None, name=None):
        self._counts = counts
        self._raise_code = raise_code
        self.name = name
        self.reads = 0
        self.closed = 0

    async def read(self):
        self.reads += 1
        if self._raise_code is not None:
            raise DemoWebError(
                self._raise_code, "The session copy binding is not available."
            )
        assert self._counts is not None
        return dict(self._counts)

    async def close(self):
        self.closed += 1


def _counts_all(n: int = 3) -> dict[str, int]:
    return {t: n for t in COPY_PREVIEW_TABLES}


def _factory(counts=None, raise_code=None):
    made: list[tuple] = []

    def factory(cfg, target_db):
        made.append((cfg, target_db))
        return FakeCopyReader(counts, raise_code, name=target_db)

    return factory, made


def test_preview_requires_valid_session():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = COPY_OK
        app = _app(fake)
        async with _client(app) as client:
            # No session cookie at all.
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            # A forged (unknown) token: refuse + clear (cookie set with
            # server-matching domain/path so the delete is observable).
            client.cookies.set(
                "slaif_demo_session", "forged", domain="demo.test", path="/"
            )
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 303
            assert client.cookies.get("slaif_demo_session") is None

    asyncio.run(run())


def test_preview_zero_active_accounts_404():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 404

    asyncio.run(run())


async def _verified_session_client(fake: FakeFacade, client: AsyncClient) -> None:
    """Give the client a real session for a verified request."""
    fake.request_state = "verified_unpublished"
    r = await client.get("/fakeadmin/login")
    csrf = r.cookies["slaif_demo_csrf"]
    r = await client.post(
        "/fakeadmin/login",
        data={"username": "op", "password": "good-pw", "csrf": csrf},
    )
    assert r.status_code == 303
    # Complete the wait so exactly one session is issued.
    r = await client.get("/fakeadmin/wait")
    assert r.status_code == 303
    assert client.cookies.get("slaif_demo_session") == "unit-token-1"


def test_preview_unverified_request_safe_note():
    async def run():
        fake = FakeFacade()
        fake.request_state = "claimed"  # not verified yet
        fake.worker_target_db = CANARY_DB
        factory, made = _factory(counts=_counts_all())
        app = _app(fake, copy_reader_factory=factory)
        async with _client(app) as client:
            client.cookies.set(
                "slaif_demo_session", "unit-token-1", domain="demo.test", path="/"
            )
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 200
            assert "not available right now" in r.text
            assert CANARY_DB not in r.text
            assert made == []  # the reader was never constructed

    asyncio.run(run())


def test_preview_expired_verified_request_safe_note():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = CANARY_DB
        fake.expires_delta = timedelta(seconds=-10)
        factory, made = _factory(counts=_counts_all())
        app = _app(fake, copy_reader_factory=factory)
        async with _client(app) as client:
            # The session itself is issued while the (back-dated)
            # request still validates as a session; the COPY read must
            # refuse because the request is expired.
            client.cookies["slaif_demo_session"] = "unit-token-1"
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 200
            assert "not available right now" in r.text
            assert CANARY_DB not in r.text
            assert made == []

    asyncio.run(run())


def test_preview_verified_reads_counts_no_store_no_canary():
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        counts = _counts_all(7)
        factory, made = _factory(counts=counts)
        app = _app(fake, copy_reader_factory=factory)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "no-store"
            for table in COPY_PREVIEW_TABLES:
                assert table in r.text
            assert "not available right now" not in r.text
            # The copy name, DSN and credentials NEVER reach the page.
            assert COPY_OK not in r.text
            assert "postgresql" not in r.text.lower()
            assert "readerpw" not in r.text
            assert "unit-test-worker-password" not in r.text
            # The factory got the EXACT verified copy name once.
            assert [m[1] for m in made] == [COPY_OK]

    asyncio.run(run())


def test_preview_malformed_control_row_name_safe_note():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = "evil_db; DROP TABLE x"
        # The REAL default factory: CopyReader's closed-name law runs
        # inside the route's safe boundary - one safe note, never a
        # 500 or a raw DemoWebError, and nothing reaches a connection.
        app = _app(fake)
        async with _client(app) as client:
            client.cookies.set(
                "slaif_demo_session", "unit-token-1", domain="demo.test", path="/"
            )
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 200
            assert "not available right now" in r.text
            assert "evil_db" not in r.text

    asyncio.run(run())


def test_preview_reader_failure_safe_note():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = COPY_OK
        factory, made = _factory(raise_code="copy_binding_unavailable")
        app = _app(fake, copy_reader_factory=factory)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 200
            assert "not available right now" in r.text
            assert COPY_OK not in r.text
            assert len(made) == 1

    asyncio.run(run())


def test_preview_wrong_account_binding_safe_note():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = CANARY_DB
        # The stored request row belongs to a DIFFERENT account than
        # the validated session: the exactness check refuses.
        fake.request_account_id = uuid.uuid4()
        factory, made = _factory(counts=_counts_all())
        app = _app(fake, copy_reader_factory=factory)
        async with _client(app) as client:
            client.cookies["slaif_demo_session"] = "unit-token-1"
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 200
            assert "not available right now" in r.text
            assert CANARY_DB not in r.text
            assert made == []

    asyncio.run(run())


def test_preview_disabled_account_bounces():
    async def run():
        class Disabled(FakeFacade):
            async def validate_session(self, *, account_id, token):
                # Live fence: the account was disabled mid-session.
                raise DemoWebControlError("web_account_disabled", "disabled")

        fake = Disabled()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = COPY_OK
        factory, made = _factory(counts=_counts_all())
        app = _app(fake, copy_reader_factory=factory)
        async with _client(app) as client:
            client.cookies.set(
                "slaif_demo_session", "unit-token-1", domain="demo.test", path="/"
            )
            r = await client.get("/fakeadmin/copy-preview")
            assert r.status_code == 303
            assert client.cookies.get("slaif_demo_session") is None
            assert made == []

    asyncio.run(run())


# --- 224-e central default-deny admin gate ----------------------------------------

COPY_OK = "demo_snap_a1b2c3d4e5f60718293a"
KEY_UUID = "01234567-89ab-4cde-8f01-23456789abcd"
OWNER_UUID = "11111111-2222-4333-8444-555555555555"


def _session_cookie(client) -> None:
    client.cookies.set("slaif_demo_session", "unit-token-1", domain="demo.test", path="/")


def _demo_csrf() -> str:
    return damg._demo_csrf_token(SECRET, "unit-token-1")


def test_gate_admission_law_closed_sets():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # admitted without a session -> demo entry redirect...
            for p in (
                "/admin",
                "/admin/",
                "/admin/keys",
                "/admin/owners",
                "/admin/institutions",
                "/admin/cohorts",
                # 224-f: the seven reviewed database-backed families;
                # 224-i adds the routes list.
                "/admin/providers",
                "/admin/routes",
                "/admin/pricing",
                "/admin/templates",
                "/admin/fx",
                "/admin/usage",
                "/admin/audit",
                "/admin/email-deliveries",
                # 224-i: the twelve fixed core form GETs.
                "/admin/keys/create",
                "/admin/keys/bulk-import",
                "/admin/owners/new",
                "/admin/institutions/new",
                "/admin/cohorts/new",
                "/admin/providers/new",
                "/admin/routes/new",
                "/admin/routes/import",
                "/admin/pricing/new",
                "/admin/pricing/import",
                "/admin/fx/new",
                "/admin/fx/import",
                # 224-j: the fourteen exact reporting/accounting/
                # accounts/key-batch read GETs.
                "/admin/reports/",
                "/admin/reports/live-burn",
                "/admin/reports/export",
                "/admin/reports/pricing-disable",
                "/admin/reports/fx-lookup",
                "/admin/accounting-operations/",
                "/admin/accounting-operations/expired-reservations",
                "/admin/accounting-operations/external-tool-fences",
                "/admin/accounting-operations/external-tool-holds",
                "/admin/accounting-operations/provider-completed-recovery",
                "/admin/accounts",
                "/admin/accounts/create",
                "/admin/accounts/reset",
                "/admin/key-batch",
                "/admin/record-choices?kind=owner&q=x",
                # 224-q: the three exact key read-page GETs
                # (calibration, clone, clone/receipts).
                f"/admin/keys/{KEY_UUID}/calibration",
                f"/admin/keys/{KEY_UUID}/clone",
                f"/admin/keys/{KEY_UUID}/clone/receipts",
            ):
                r = await client.get(p)
                assert r.status_code == 303, p
                assert r.headers["location"] == "/fakeadmin/login"
            # ...every other admin GET stays default-denied.
            for p in (
                "/admin/operations",
                "/admin/branding",
                # 224-j near-misses: missing slash, extra suffix,
                # export attachment, unknown account action.
                "/admin/reports",
                "/admin/reports/export.csv",
                "/admin/reports/usage",
                "/admin/accounting-operations",
                "/admin/accounting-operations/expired-reservations/preview",
                "/admin/accounts/",
                "/admin/accounts/reset/",
                "/admin/accounts/revoke",
                "/admin/key-batch/plan",
                # 224-i negatives: keys/templates have no edit forms;
                # action GETs stay 404. The 224-w admitted route
                # configuration and codex-profile artifact GETs are
                # proven positive/negative in the 224-w tests.
                f"/admin/keys/{KEY_UUID}/edit",
                f"/admin/templates/{KEY_UUID}/edit",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_gate_detail_requires_canonical_uuid():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # canonical lowercase 8-4-4-4-12 is admitted (redirect: no
            # session in this test)...
            for prefix in (
                "keys",
                "owners",
                "institutions",
                "cohorts",
                "providers",
                "routes",
                "pricing",
                "templates",
                "fx",
                "usage",
                "audit",
                "email-deliveries",
            ):
                r = await client.get(f"/admin/{prefix}/{KEY_UUID}")
                assert r.status_code == 303, prefix
            # ...variant forms are NOT admitted detail components.
            for bad in (
                f"/admin/keys/{KEY_UUID.upper()}",
                "/admin/keys/0123456789abcdef0123456789abcdef",
                f"/admin/keys/urn:uuid:{KEY_UUID}",
                f"/admin/keys/{{{KEY_UUID}}}",
                f"/admin/keys/{KEY_UUID}/extra",
                "/admin/keys/",
                f"/admin/fx/{KEY_UUID}/discover",
                f"/admin/usage/{KEY_UUID}x",
                # 224-i: edit-form middle-segment variants are denied.
                f"/admin/owners/{KEY_UUID.upper()}/edit",
                "/admin/owners/0123456789abcdef0123456789abcdef/edit",
                f"/admin/owners/{KEY_UUID}/extra",
                f"/admin/owners/{KEY_UUID}/edit/",
                "/admin/owners/edit",
            ):
                r = await client.get(bad)
                assert r.status_code == 404, bad

    asyncio.run(run())


def test_gate_224i_edit_and_discover_admission():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # the seven edit families admit exactly one canonical UUID.
            for family in (
                "owners",
                "institutions",
                "cohorts",
                "providers",
                "routes",
                "pricing",
                "fx",
            ):
                r = await client.get(f"/admin/{family}/{KEY_UUID}/edit")
                assert r.status_code == 303, family
                assert r.headers["location"] == "/fakeadmin/login", family
            # provider discover: the read-only form GET.
            r = await client.get(f"/admin/providers/{KEY_UUID}/discover")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            # denied: keys/templates edits, discover on other families,
            # extra/missing segments, uppercase variants.
            for bad in (
                f"/admin/keys/{KEY_UUID}/edit",
                f"/admin/templates/{KEY_UUID}/edit",
                f"/admin/fx/{KEY_UUID}/discover",
                f"/admin/providers/{KEY_UUID}/discover/extra",
                "/admin/providers/discover",
                f"/admin/providers/{KEY_UUID.upper()}/edit",
                f"/admin/routes/{KEY_UUID}/edit/extra",
                "/admin/keys/create/extra",
            ):
                r = await client.get(bad)
                assert r.status_code == 404, bad

    asyncio.run(run())


def test_gate_zero_active_404s_every_admin_path():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            for p in (
                "/admin",
                "/admin/keys",
                "/admin/login",
                "/admin/static/css/admin.css",
                f"/admin/keys/{KEY_UUID}",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p
            r = await client.post("/admin/keys/create", data={"x": "1"})
            assert r.status_code == 404

    asyncio.run(run())


def test_gate_login_get_redirects_to_demo_entry():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            r = await client.get("/admin/login")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"

    asyncio.run(run())


def test_gate_binding_refusals_503_safe_no_leak():
    async def run():
        cases = [
            dict(worker_target_db=None),                       # unbound
            dict(request_state="pending", worker_target_db=COPY_OK),  # unverified
            dict(request_state="verified_unpublished", worker_target_db="demo_snap_ZZ"),  # bad name
            dict(
                request_state="verified_unpublished",
                worker_target_db=COPY_OK,
                expires_delta=timedelta(seconds=-1),           # expired
            ),
        ]
        for knobs in cases:
            fake = FakeFacade()
            state = knobs.pop("request_state", "verified_unpublished")
            fake.request_state = state
            fake.worker_target_db = knobs.get("worker_target_db")
            if "expires_delta" in knobs:
                fake.expires_delta = knobs["expires_delta"]
            app = _app(fake)
            async with _client(app) as client:
                _session_cookie(client)
                r = await client.get("/admin/keys")
                assert r.status_code == 503
                assert r.headers.get("cache-control") == "private, no-store"
                assert "not available right now" in r.text
                # no DSN fragment, copy name or credential may leak.
                assert "unit-test-copy-password" not in r.text
                assert COPY_OK not in r.text

    asyncio.run(run())


class _FakeConn:
    def __init__(self, db: str, ro: str) -> None:
        self.db = db
        self.ro = ro

    async def scalar(self, query: str):
        # The gate passes sqlalchemy text-clauses: normalize to str
        # (a raw `in` test on a clause is not a string search).
        text = str(query)
        if "current_database" in text:
            return self.db
        return self.ro

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeEngine:
    def __init__(self, db: str, ro: str) -> None:
        self.db = db
        self.ro = ro
        self.disposed = 0

    def connect(self):
        return _FakeConn(self.db, self.ro)

    async def dispose(self):
        self.disposed += 1


def _preflight_case(monkeypatch, db: str, ro: str):
    engine = _FakeEngine(db, ro)
    monkeypatch.setattr(damg, "create_async_engine", lambda *a, **k: engine)
    return engine


def test_gate_preflight_wrong_db_disposes_and_refuses(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = COPY_OK
        engine = _preflight_case(monkeypatch, "some_other_db", "on")
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            r = await client.get("/admin/keys")
            assert r.status_code == 503
            assert engine.disposed == 1

    asyncio.run(run())


def test_gate_preflight_read_only_off_disposes_and_refuses(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = COPY_OK
        engine = _preflight_case(monkeypatch, COPY_OK, "off")
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            r = await client.get("/admin/keys")
            assert r.status_code == 503
            assert engine.disposed == 1

    asyncio.run(run())


def test_gate_unsafe_known_no_session_404_body_not_parsed():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # a lying oversized body with a garbage content type: if the
            # gate parsed it we would see 413/400, not the default denial.
            r = await client.post(
                "/admin/keys/create",
                content=b"x" * (fa.FORM_BODY_MAX_BYTES + 1024),
                headers={"content-type": "text/garbage"},
            )
            assert r.status_code == 404

    asyncio.run(run())


def test_gate_unsafe_operational_families_quiet_noop():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            paths = [
                "/admin/keys/create",
                f"/admin/keys/{KEY_UUID}/revoke",
                f"/admin/keys/{KEY_UUID}/rotate",
                f"/admin/keys/{KEY_UUID}/reset-usage",
                "/admin/owners/new",
                f"/admin/owners/{OWNER_UUID}/edit",
                "/admin/institutions/new",
                "/admin/cohorts/new",
                # 224-j: admitted read GETs stay a uniform 204 cut for
                # every unsafe method, body never parsed.
                "/admin/reports/export",
                "/admin/reports/fx-lookup",
                "/admin/accounting-operations/expired-reservations",
                "/admin/accounting-operations/provider-completed-recovery",
                "/admin/accounts/create",
                "/admin/accounts/reset",
                "/admin/key-batch",
            ]
            for p in paths:
                # 200 KB body + garbage content type: a 204 proves the
                # body was never parsed before the cut.
                r = await client.post(
                    p,
                    content=b"x" * 200_000,
                    headers={"content-type": "text/garbage"},
                )
                assert r.status_code == 204, p
                assert r.content == b""

    asyncio.run(run())


def test_gate_unsafe_unknown_path_uniform_law():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # unknown + no session: default denied...
            r = await client.post("/admin/definitely-not-a-route", data={"x": "1"})
            assert r.status_code == 404
            # unknown + authenticated session: the SAME uniform quiet
            # no-content cut (nothing is dispatched, no fake success).
            _session_cookie(client)
            r = await client.post("/admin/definitely-not-a-route", data={"x": "1"})
            assert r.status_code == 204
            assert r.content == b""

    asyncio.run(run())


def test_gate_no_unsafe_handler_dispatch_across_mounted_table():
    """Representative mounted /admin routes (GET-only and POST-only)
    plus an unknown path: every authenticated unsafe method is a 204
    cut. A dispatched GET-only route would answer 405 and a dispatched
    POST handler would fail without the request-local sessionmaker
    (500) - neither outcome can occur behind the gate."""
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            cases = [
                # (path, unsafe method) - path is a mounted route
                ("/admin/owners", "POST"),
                ("/admin/keys", "DELETE"),
                ("/admin/record-choices?kind=owner", "PATCH"),
                ("/admin/keys/create", "POST"),
                f"/admin/keys/{KEY_UUID}/revoke",
                f"/admin/keys/{KEY_UUID}/rotate",
                "/admin/owners/new",
                "/admin/institutions/new",
                "/admin/cohorts/new",
                "/admin/definitely-not-a-route",
            ]
            for case in cases:
                p, method = case if isinstance(case, tuple) else (case, "POST")
                r = await client.request(
                    method,
                    p,
                    content=b"y" * 10_000,
                    headers={"content-type": "text/garbage"},
                )
                assert r.status_code == 204, (p, method)
                assert r.content == b""

    asyncio.run(run())


def test_gate_logout_confirmed_revocation_303_clears_all_cookies():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            r = await client.post(
                "/admin/logout", data={"csrf_token": _demo_csrf()}
            )
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            assert r.headers.get("cache-control") == "private, no-store"
            cleared = {
                h.split("=", 1)[0]
                for h in r.headers.get_list("set-cookie")
            }
            assert {"slaif_demo_session", "slaif_demo_pending", "slaif_demo_csrf"} <= cleared
            assert fake.revoked == 1

    asyncio.run(run())


def test_gate_logout_revoke_runtime_error_refuses_no_false_success():
    async def run():
        class Boom(FakeFacade):
            async def revoke_session(self, *, account_id, token):
                raise RuntimeError("driver exploded: host=secret detail")

        fake = Boom()
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            r = await client.post(
                "/admin/logout", data={"csrf_token": _demo_csrf()}
            )
            assert r.status_code == 400
            assert "location" not in r.headers
            # the session cookie must NOT be cleared (retry allowed).
            cleared = {h.split("=", 1)[0] for h in r.headers.get_list("set-cookie")}
            assert "slaif_demo_session" not in cleared
            # and the session still validates (no false sign-out).
            r2 = await client.get("/admin")
            assert r2.status_code == 503  # bound copy readable path reached

    asyncio.run(run())


def test_gate_logout_unconfirmed_cas_refuses():
    async def run():
        class Unconfirmed(FakeFacade):
            async def revoke_session(self, *, account_id, token):
                now = datetime.now(timezone.utc)
                return DemoWebSessionProjection(
                    id=uuid.uuid4(),
                    account_id=ACC,
                    credential_generation=1,
                    request_id=REQ,
                    created_at=now,
                    expires_at=now + timedelta(minutes=5),
                    revoked_at=None,  # the CAS did not confirm
                )

        fake = Unconfirmed()
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            r = await client.post(
                "/admin/logout", data={"csrf_token": _demo_csrf()}
            )
            assert r.status_code == 400
            assert "location" not in r.headers
            cleared = {h.split("=", 1)[0] for h in r.headers.get_list("set-cookie")}
            assert "slaif_demo_session" not in cleared

    asyncio.run(run())


def test_gate_logout_csrf_mismatch_refuses_without_revocation():
    async def run():
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            r = await client.post("/admin/logout", data={"csrf_token": "wrong" * 10})
            assert r.status_code == 400
            assert "location" not in r.headers
            assert fake.revoked == 0
            # missing field is refused the same way.
            r2 = await client.post("/admin/logout", data={})
            assert r2.status_code == 400
            assert fake.revoked == 0

    asyncio.run(run())


def _minimal_gate_app(fake: FakeFacade):
    """Minimal ASGI app behind DemoAdminGate: proves the central
    no-store guard on admitted dynamic responses (success / JSON /
    error / no-op) without needing a copy database."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, Response

    app = FastAPI()

    @app.get("/admin/usage", response_class=HTMLResponse)
    async def _usage_page():
        return "<html><body>usage</body></html>"

    # 224-i: an admitted core form GET (stub; no DB needed).
    @app.get("/admin/keys/create", response_class=HTMLResponse)
    async def _key_create_form():
        return "<html><body>create key form</body></html>"

    @app.get("/admin/record-choices")
    async def _choices():
        return {"kind": "owner", "choices": []}

    @app.get("/admin/templates/{template_id}")
    async def _template_detail(template_id: str):
        return Response(status_code=404, content="not found")

    app.state.demo_config = _config()
    app.state.demo_facade = fake
    return damg.DemoAdminGate(app)


def test_gate_no_store_on_admitted_success_json_and_error(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        app = _minimal_gate_app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            # successful admitted HTML page
            r = await client.get("/admin/usage")
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            # 224-i: admitted form GETs carry the same central guard
            r = await client.get("/admin/keys/create")
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            # admitted JSON lookup
            r = await client.get("/admin/record-choices?kind=owner&q=")
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            # handler-level error page for a canonical detail id
            r = await client.get(f"/admin/templates/{KEY_UUID}")
            assert r.status_code == 404
            assert r.headers["cache-control"] == "private, no-store"
            # the uniform unsafe no-op carries the same guard (harmless
            # on a 204)
            r = await client.post("/admin/usage/export.csv", data={"x": "1"})
            assert r.status_code == 204
            assert r.headers.get("cache-control") == "private, no-store"

    asyncio.run(run())


def test_gate_no_store_on_zero_account_404_and_login_redirect():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            r = await client.get("/admin/usage")
            assert r.status_code == 404
            assert r.headers["cache-control"] == "private, no-store"
        app = _app(FakeFacade())
        async with _client(app) as client:
            r = await client.get("/admin/login")
            assert r.status_code == 303
            assert r.headers["cache-control"] == "private, no-store"

    asyncio.run(run())


def test_gate_static_passthrough_serves_bundled_assets():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            r = await client.get("/admin/static/css/admin.css")
            assert r.status_code == 200
            assert "admin" in r.text
            # 224-f: the revisioned static passthrough bypasses the
            # dynamic no-store guard (its own cache policy is kept).
            assert r.headers.get("cache-control") is None

    asyncio.run(run())


def test_route_detail_demo_skips_codex_profile_artifacts(monkeypatch):
    """224-i/224-w: demo route detail must never render the LIVE Codex
    profile block (no localhost/live base URL, no profile TOML body);
    224-w replaces the 224-i hint with three INERT reference-attachment
    links on the reserved non-routable api.slaif.invalid placeholder.
    Normal admin still renders the live artifact block."""
    from types import SimpleNamespace

    import slaif_gateway.api.admin as admin_mod

    fake_route = SimpleNamespace(
        id=KEY_UUID,
        requested_model="224i-demo-model",
        match_type="exact",
        endpoint="/v1/chat/completions",
        provider="openrouter",
        upstream_model="224i-upstream-model",
        priority=10,
        enabled=True,
        visible_in_models=True,
        supports_streaming=True,
        capabilities={},
        capabilities_summary="none",
        codex_qualification_badge="qualified",
        codex_qualification_state="ready",
        codex_qualification_reason_codes=None,
        codex_profile_id="registered-profile",
        codex_metadata_version=2,
        codex_cli_version="0.147.0",
        codex_provider_display_name=None,
        codex_provider_kind="module",
        codex_wire_api="responses",
        codex_paired_route_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        notes=None,
        provider_config=None,
        codex_protocol_ready=True,
    )

    class _FakeSvc:
        async def get_route_detail(self, _route_id):
            return fake_route

    class _FakeScope:
        async def __aenter__(self):
            return _FakeSvc()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(
        admin_mod, "_admin_catalog_dashboard_service_scope", lambda _req: _FakeScope()
    )

    async def run():
        # DEMO: render_codex_profile must not run at all during the
        # detail render (the inert attachments are served by the
        # dedicated 224-w codex-artifact route instead).
        def _explode(*_a, **_k):
            raise AssertionError("render_codex_profile must not run in demo mode")

        monkeypatch.setattr(admin_mod, "render_codex_profile", _explode)
        demo_admin = SimpleNamespace(
            nav=(),
            session_context=damg._fictional_admin_context(),
            csrf_token="demo-csrf",
        )
        request = _fake_admin_request(f"/admin/routes/{KEY_UUID}", demo_admin=demo_admin)
        response = await admin_mod.admin_route_detail(request, KEY_UUID)
        html = response.body.decode("utf-8")
        assert "Inert Codex reference artifacts" in html
        assert "api.slaif.invalid" in html
        assert f'href="/admin/routes/{KEY_UUID}/codex-profile/base"' in html
        assert f'href="/admin/routes/{KEY_UUID}/codex-profile/profile"' in html
        assert f'href="/admin/routes/{KEY_UUID}/codex-profile/catalog"' in html
        assert "localhost:8000" not in html
        assert "Credential-free Codex artifacts" not in html
        assert "224i-upstream-model" in html
        assert "Demo preview:" in html

        # NORMAL: the artifact block (links + TOML) still renders.
        def _fake_artifacts(*_a, **_k):
            return SimpleNamespace(
                profile_config_self_contained=True,
                base_config_toml=None,
                profile_config_toml='[model.224i-fake]\nname = "224i-fake"',
                model_catalog_json=None,
                client_module_id="224i-module",
                client_module_version="1",
            )

        monkeypatch.setattr(admin_mod, "render_codex_profile", _fake_artifacts)

        async def _fake_page_context(_req):
            return damg._fictional_admin_context(), "normal-csrf"

        monkeypatch.setattr(admin_mod, "_admin_page_context", _fake_page_context)
        request = _fake_admin_request(f"/admin/routes/{KEY_UUID}")
        response = await admin_mod.admin_route_detail(request, KEY_UUID)
        html = response.body.decode("utf-8")
        assert f'href="/admin/routes/{KEY_UUID}/codex-profile/profile"' in html
        assert "224i-fake" in html
        assert "Credential-free Codex artifacts" in html
        assert "Demo preview:" not in html

    asyncio.run(run())


def _fake_admin_request(path: str = "/admin/keys", demo_admin: object | None = None):
    """Minimal real starlette Request for template render regression."""
    from types import SimpleNamespace

    from starlette.requests import Request

    from slaif_gateway.demo_web import _demo_display_settings

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "root_path": "",
        "headers": [],
        "query_string": b"",
        "server": ("demo.test", 443),
        "client": ("127.0.0.1", 1234),
        "app": SimpleNamespace(state=SimpleNamespace(settings=_demo_display_settings())),
    }
    if demo_admin is not None:
        scope["state"] = {"demo_admin": demo_admin}
    return Request(scope)


def test_base_template_normal_render_unchanged_and_demo_variant():
    """Render regression for the 224-e base.html edits through the REAL
    Starlette TemplateResponse path (context processors active):
    normal mode keeps the full nav and no demo banner; demo mode shows
    the persistent read-only banner and ONLY the five usable nav
    sections (asserted on visible nav/banner, not whitespace)."""
    from slaif_gateway.api.admin import templates as admin_templates

    async def _render(request):
        response = admin_templates.TemplateResponse(
            request,
            "base.html",
            {
                "admin": object(),  # base.html only tests truthiness
                "admin_status_message": None,
            },
        )
        return response.body.decode("utf-8")

    async def run():
        # Normal mode: the FULL nav is present (every section link,
        # including the ones the demo host hides) and no demo banner.
        out_normal = await _render(_fake_admin_request("/admin/keys"))
        for href in (
            "/admin",
            "/admin/keys",
            "/admin/owners",
            "/admin/institutions",
            "/admin/cohorts",
            "/admin/providers",
            "/admin/routes",
            "/admin/pricing",
            "/admin/templates",
            "/admin/fx",
            "/admin/usage",
            "/admin/operations",
            "/admin/audit",
            "/admin/email-deliveries",
            "/admin/openai-assisted",
        ):
            assert f'href="{href}"' in out_normal
        assert "Demo preview:" not in out_normal

        # Demo mode: persistent read-only banner + ONLY the sections
        # admitted through 224-i (thirteen).
        demo_req = _fake_admin_request("/admin/keys", demo_admin=object())
        out_demo = await _render(demo_req)
        assert "Demo preview:" in out_demo
        assert "Read-only" in out_demo
        assert "incomplete" in out_demo
        for href in (
            "/admin",
            "/admin/keys",
            "/admin/owners",
            "/admin/institutions",
            "/admin/cohorts",
            "/admin/providers",
            "/admin/routes",
            "/admin/pricing",
            "/admin/templates",
            "/admin/fx",
            "/admin/usage",
            "/admin/audit",
            "/admin/email-deliveries",
        ):
            assert f'href="{href}"' in out_demo
        for href in (
            "/admin/operations",
            "/admin/openai-assisted",
        ):
            assert f'href="{href}"' not in out_demo

    asyncio.run(run())


def test_demo_display_settings_ignores_ambient_env(monkeypatch):
    from slaif_gateway.demo_web import _demo_display_settings

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://amb:amb@amb/ambient")
    monkeypatch.setenv("SLAIF_BRANDING_DIR", "/etc/ambient-branding")
    monkeypatch.setenv("GATEWAY_KEY_PREFIX", "sk-ambient-")
    s = _demo_display_settings()
    assert s.DATABASE_URL is None
    assert s.SLAIF_BRANDING_DIR == ""
    assert s.ENABLE_ADMIN_DASHBOARD is True
    app = _app(FakeFacade())
    assert app.state.settings is not None
    assert app.state.settings.DATABASE_URL is None
    assert app.state.demo_mode is True


# --- 224-g: display-index reader and files-preview route -----------------------

from slaif_gateway.demo_web import (  # noqa: E402
    DisplayReader,
    _default_display_reader_factory,
)

LEAF_ONE = {
    "logical_name": f"catalog/proposals/{'ab' * 16}/provider-catalog-report.md",
    "kind": "markdown",
    "byte_count": 50,
    "captured_at": 1750000000.0,
}
LEAF_TWO = {
    "logical_name": "branding/logo",
    "kind": "branding",
    "byte_count": 1234,
    "captured_at": 1750000010.5,
}


class FakeDisplayReader:
    """In-memory display-index reader standing in for the per-request
    engine (same seam pattern as FakeCopyReader)."""

    def __init__(self, leaves=None, raise_code=None):
        self._leaves = leaves
        self._raise_code = raise_code
        self.reads = 0

    async def read_index(self):
        self.reads += 1
        if self._raise_code is not None:
            raise DemoWebError(
                self._raise_code, "The session copy binding is not available."
            )
        assert self._leaves is not None
        return [dict(leaf) for leaf in self._leaves]


def _display_factory(leaves=None, raise_code=None):
    made: list[tuple] = []

    def factory(cfg, target_db):
        made.append((cfg, target_db))
        return FakeDisplayReader(leaves, raise_code)

    return factory, made


def test_display_reader_constructor_refuses_malformed_name():
    cfg = _config(copy_host="127.0.0.1", copy_user="reader", copy_password="p")
    with pytest.raises(DemoWebError) as ei:
        DisplayReader(cfg, "demo_snap_" + "a" * 21)
    assert ei.value.code == "copy_binding_unavailable"
    with pytest.raises(DemoWebError):
        DisplayReader(cfg, "evil_db")
    # The real default factory enforces the SAME closed-name law.
    with pytest.raises(DemoWebError):
        _default_display_reader_factory(cfg, "evil_db")


def test_display_reader_close_wraps_dispose_failure_safely():
    class _BoomEngine:
        def __init__(self) -> None:
            self.disposed = 0

        async def dispose(self) -> None:
            self.disposed += 1
            raise RuntimeError("driver boom postgresql://secret@x/y")

    engine = _BoomEngine()
    reader = DisplayReader(
        _config(copy_host="h", copy_user="u", copy_password="p"), COPY_OK
    )
    reader._engine = engine  # type: ignore[assignment]
    with pytest.raises(DemoWebError) as ei:
        asyncio.run(reader.close())
    assert ei.value.code == "copy_binding_unavailable"
    assert "boom" not in str(ei.value)
    assert "secret" not in str(ei.value)
    assert engine.disposed == 1
    asyncio.run(reader.close())  # a second close is a safe no-op


def test_files_preview_requires_valid_session():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = COPY_OK
        app = _app(fake)
        async with _client(app) as client:
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            client.cookies.set(
                "slaif_demo_session", "forged", domain="demo.test", path="/"
            )
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 303
            assert client.cookies.get("slaif_demo_session") is None

    asyncio.run(run())


def test_files_preview_zero_active_accounts_404():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 404

    asyncio.run(run())


def test_files_preview_unverified_request_safe_note():
    async def run():
        fake = FakeFacade()
        fake.request_state = "claimed"
        fake.worker_target_db = CANARY_DB
        factory, made = _display_factory(leaves=[LEAF_ONE])
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            client.cookies.set(
                "slaif_demo_session", "unit-token-1", domain="demo.test", path="/"
            )
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 200
            assert "not available right now" in r.text
            assert CANARY_DB not in r.text
            assert made == []  # the reader was never constructed

    asyncio.run(run())


def test_files_preview_verified_lists_safe_index_no_store_no_canary():
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        factory, made = _display_factory(leaves=[LEAF_ONE, LEAF_TWO])
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "no-store"
            assert LEAF_ONE["logical_name"] in r.text
            assert LEAF_TWO["logical_name"] in r.text
            assert "markdown" in r.text and "branding" in r.text
            assert str(LEAF_ONE["byte_count"]) in r.text
            assert str(LEAF_TWO["byte_count"]) in r.text
            assert "not available right now" not in r.text
            # The copy name, DSN and credentials NEVER reach the page,
            # and no body bytes are rendered (metadata only).
            assert COPY_OK not in r.text
            assert "postgresql" not in r.text.lower()
            assert "readerpw" not in r.text
            assert "Neutral demo display copy" not in r.text
            # The factory got the EXACT verified copy name once.
            assert [m[1] for m in made] == [COPY_OK]

    asyncio.run(run())


def test_files_preview_reader_failure_safe_note_pre_upgrade_copy():
    # A pre-upgrade verified copy lacks the target-only demo_display
    # schema: the reader refuses and the page shows the safe note.
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = COPY_OK
        factory, made = _display_factory(raise_code="copy_binding_unavailable")
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 200
            assert "not available right now" in r.text
            assert COPY_OK not in r.text
            assert len(made) == 1

    asyncio.run(run())


def test_files_preview_wrong_account_binding_safe_note():
    async def run():
        fake = FakeFacade()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = CANARY_DB
        fake.request_account_id = uuid.uuid4()
        factory, made = _display_factory(leaves=[LEAF_ONE])
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            client.cookies["slaif_demo_session"] = "unit-token-1"
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 200
            assert "not available right now" in r.text
            assert CANARY_DB not in r.text
            assert made == []

    asyncio.run(run())


def test_files_preview_disabled_account_bounces():
    async def run():
        class Disabled(FakeFacade):
            async def validate_session(self, *, account_id, token):
                raise DemoWebControlError("web_account_disabled", "disabled")

        fake = Disabled()
        fake.request_state = "verified_unpublished"
        fake.worker_target_db = COPY_OK
        factory, made = _display_factory(leaves=[LEAF_ONE])
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            client.cookies.set(
                "slaif_demo_session", "unit-token-1", domain="demo.test", path="/"
            )
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 303
            assert client.cookies.get("slaif_demo_session") is None
            assert made == []

    asyncio.run(run())


# --- 224-h: no-store on EVERY files-preview response + time law -------------------


def test_files_preview_every_response_no_store():
    async def run():
        # (a) zero active accounts: the 404 is no-store too.
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 404
            assert r.headers.get("cache-control") == "no-store"
        # (b) missing session: the login bounce redirect is no-store.
        fake = FakeFacade()
        app = _app(fake)
        async with _client(app) as client:
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 303
            assert r.headers.get("location") == "/fakeadmin/login"
            assert r.headers.get("cache-control") == "no-store"
        # (c) unverified request: the safe-note page is no-store.
        fake = FakeFacade()
        fake.request_state = "claimed"
        fake.worker_target_db = CANARY_DB
        app = _app(fake)
        async with _client(app) as client:
            client.cookies.set(
                "slaif_demo_session", "unit-token-1", domain="demo.test", path="/"
            )
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "no-store"
            assert "not available right now" in r.text

    asyncio.run(run())


def test_files_preview_out_of_range_capture_time_safe_note():
    # A stored capture time that is finite but NOT representable by
    # datetime.fromtimestamp (a legacy writer predating the 224-h
    # law) must render the SAME safe note - never a 500.
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        bad_leaf = dict(LEAF_ONE)
        bad_leaf["captured_at"] = 9.0e15
        factory, made = _display_factory(leaves=[bad_leaf])
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get("/fakeadmin/files-preview")
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "no-store"
            assert "not available right now" in r.text
            assert COPY_OK not in r.text
            assert len(made) == 1

    asyncio.run(run())


# --- 224-k: demo-only catalog snapshot index ----------------------------------

from slaif_gateway.api import demo_admin_catalog as dac  # noqa: E402

CAT_RUN_ID = "demo-run-" + "a1" * 12  # remapped run id (24 hex)
CAT_JOB_ID = "b2" * 16  # remapped job id (32 hex)
CAT_LEAF_RUN = {
    "logical_name": f"catalog/runs/{CAT_RUN_ID}/catalog-refresh.json",
    "kind": "refresh_bundle",
    "byte_count": 1234567,
    "captured_at": 1750000000.0,
}
CAT_LEAF_JOB = {
    "logical_name": f"catalog/jobs/{CAT_JOB_ID}.json",
    "kind": "job_record",
    "byte_count": 42,
    "captured_at": 1750000010.0,
}
CAT_LEAF_PKG = {
    "logical_name": (
        f"catalog/proposals/{CAT_JOB_ID}"
        "/packages/openrouter-chat-text/routes-proposal.tsv"
    ),
    "kind": "route_tsv",
    "byte_count": 88,
    "captured_at": 1750000020.0,
}
CATALOG_INDEX_URL = "/admin/operations/catalog/"


def test_catalog_index_gate_admission_exact_path():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # The ONE exact path is admitted (no session -> entry
            # redirect)...
            r = await client.get(CATALOG_INDEX_URL)
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            # ...every near-miss catalog GET stays default-denied.
            for p in (
                "/admin/operations/catalog",          # missing slash
                "/admin/operations/catalog//",        # doubled slash
                "/admin/operations/catalog2",         # prefix sibling
                # 224-n: /admin/operations/catalog/proposals is now
                # ADMITTED (exact path) - covered by the 224-n section.
                # 224-o: /admin/operations/catalog/collect is now
                # ADMITTED (exact path) - covered by the 224-o section.
                # 224-p: /admin/operations/catalog/review,
                # /admin/operations/catalog/export-baseline and
                # /admin/operations/catalog/jobs/ are now ADMITTED
                # (exact paths) - covered by the 224-p section; their
                # near misses stay denied there.
                f"/admin/operations/catalog/runs/{KEY_UUID}/",
                f"/admin/operations/catalog/runs/{KEY_UUID}/apply-status",
                f"/admin/operations/catalog/runs/{KEY_UUID}/artifact/x",
                f"/admin/operations/catalog/jobs/{CAT_JOB_ID}/artifact/x",
                f"/admin/operations/catalog/jobs/{CAT_JOB_ID}/package/openrouter-chat-text/x",
                "/admin/operations/catalogx/",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_catalog_index_zero_active_404():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            r = await client.get(CATALOG_INDEX_URL)
            assert r.status_code == 404

    asyncio.run(run())


def test_catalog_index_unsafe_methods_quiet_noop_body_not_parsed():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            paths = [
                CATALOG_INDEX_URL,
                "/admin/operations/catalog/proposals",
                f"/admin/operations/catalog/runs/{CAT_RUN_ID}/apply",
            ]
            for p in paths:
                for method in ("POST", "PUT", "PATCH", "DELETE"):
                    # 200 KB garbage body: a 204 proves the body was
                    # never parsed before the cut.
                    r = await client.request(
                        method,
                        p,
                        content=b"x" * 200_000,
                        headers={"content-type": "text/garbage"},
                    )
                    assert r.status_code == 204, (p, method)
                    assert r.content == b""
            # Without a session the SAME cut is default denial.
        async with _client(app) as anon:
            r = await anon.post(
                CATALOG_INDEX_URL,
                content=b"y" * 200_000,
                headers={"content-type": "text/garbage"},
            )
            assert r.status_code == 404

    asyncio.run(run())


def _norm(text: str) -> str:
    # Template line wraps insert whitespace; assert phrases on the
    # rendered TEXT, not the raw markup.
    return " ".join(text.split())


def test_catalog_index_positive_gated_page(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        engine = _preflight_case(monkeypatch, COPY_OK, "on")
        factory, made = _display_factory(
            leaves=[CAT_LEAF_RUN, CAT_LEAF_JOB, CAT_LEAF_PKG, LEAF_TWO]
        )
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_INDEX_URL)
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "private, no-store"
            text = _norm(r.text)
            # The DEMO handler served it (not the custody-backed
            # normal handler): the demo template + banner...
            assert "Catalog snapshot index" in text
            assert "Demo preview:" in text
            # ...with the remapped metadata only: every area's
            # remapped id and artifact, closed kinds, comma bytes,
            # per-leaf capture times.
            assert CAT_RUN_ID in text
            assert f"{CAT_JOB_ID}.json" in text
            assert "packages/openrouter-chat-text/routes-proposal.tsv" in text
            assert "refresh_bundle" in text
            assert "job_record" in text
            assert "1,234,567" in text
            assert "2025-06-15 15:06:40 UTC" in text
            assert "3 captured catalog artifacts" in text
            assert "at most 4,096 entries" in text
            assert "no completeness claim" in text
            # 224-l: every rendered Artifact cell links the EXACT
            # remapped logical name (closed charset renders literally
            # through urlencode) to the one exact demo download path;
            # no new action column is added.
            for leaf in (CAT_LEAF_RUN, CAT_LEAF_JOB, CAT_LEAF_PKG):
                assert (
                    f'href="/admin/operations/catalog/artifact'
                    f'?name={leaf["logical_name"]}"'
                ) in r.text
            # The forced-download wording is present on the page.
            assert "forced file download" in text
            assert "never rendered as active content" in text
            # The bounded-index / separate-phase / no-seal wording.
            assert "separate, bounded phase" in text
            assert "no original seal or apply authority" in text
            # Non-catalog leaves are NOT catalog artifacts: the
            # branding leaf has no catalog-artifact row/link on this
            # page (the base header's demo branding asset reference
            # is a different, admitted slot URL - 224-u)...
            assert "name=branding/logo" not in r.text
            # ...and no copy name, DSN or credential escapes.
            assert COPY_OK not in text
            assert "unit-test-copy-password" not in text
        # The factory was called EXACTLY once with the session's exact
        # target (no re-read, no other copy).
        assert len(made) == 1
        assert made[0][1] == COPY_OK
        assert engine.disposed == 1

    asyncio.run(run())


def test_catalog_index_download_link_positive_follow(monkeypatch):
    # 224-l positive LINK proof (mocked ASGI): the rendered index's
    # actual href, followed by the same session, serves the
    # byte-accurate sanitized display copy as a forced attachment.
    import hashlib
    import re
    from urllib.parse import unquote_plus, urlsplit

    body = b"sanitized-catalog-refresh-" + b"y" * 4096
    meta = ("refresh_bundle", len(body), hashlib.sha256(body).hexdigest(), len(body))
    session = _ArtifactFakeSession([meta], [(body,)], COPY_OK, "on")

    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        factory, made = _display_factory(
            leaves=[CAT_LEAF_RUN, CAT_LEAF_JOB, LEAF_TWO]
        )
        _patch_sessionmaker(monkeypatch, session)
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_INDEX_URL)
            assert r.status_code == 200
            # The ACTUAL rendered href: the closed name charset renders
            # literally through urlencode (no percent-escaping occurs).
            assert (
                f'href="/admin/operations/catalog/artifact'
                f'?name={CAT_LEAF_RUN["logical_name"]}"'
            ) in r.text
            m = re.search(
                r'href="(/admin/operations/catalog/artifact\?name=[^"]+)"',
                r.text,
            )
            assert m is not None
            r2 = await client.get(m.group(1))
            assert r2.status_code == 200
            assert r2.content == body
            assert r2.headers["content-type"] == "application/octet-stream"
            assert r2.headers["content-disposition"] == (
                'attachment; filename="catalog-refresh.json"'
            )
            assert r2.headers["x-content-type-options"] == "nosniff"
            assert r2.headers["content-security-policy"] == "default-src 'none'"
            assert r2.headers["cache-control"] == "private, no-store"
            # The followed query decodes to the EXACT remapped name.
            q = urlsplit(m.group(1)).query
            assert unquote_plus(q) == f"name={CAT_LEAF_RUN['logical_name']}"
        assert len(made) == 1

    asyncio.run(run())


def test_catalog_index_empty_catalog_leaves(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        factory, made = _display_factory(leaves=[LEAF_TWO])  # branding only
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_INDEX_URL)
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "private, no-store"
            text = _norm(r.text)
            assert "0 captured catalog artifacts" in text
            assert "This copy has no captured catalog artifacts." in text
            # No inference about operator storage configuration.
            assert (
                "does not establish whether operator catalog "
                "storage was configured"
            ) in text
            assert len(made) == 1

    asyncio.run(run())


def test_catalog_index_reader_failure_safe_note(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        factory, made = _display_factory(raise_code="copy_binding_unavailable")
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_INDEX_URL)
            assert r.status_code == 503
            assert r.headers.get("cache-control") == "private, no-store"
            assert dac._SAFE_UNAVAILABLE in r.text
            # No raw DB value, path or traceback.
            assert COPY_OK not in r.text
            assert "demo_display" not in r.text
            assert "Traceback" not in r.text
            assert len(made) == 1

    asyncio.run(run())


def test_catalog_index_corrupt_row_canaries_safe_note(monkeypatch):
    # A corrupted target row must fail the WHOLE page to the fixed
    # safe note; its raw values (source-like ids, traversal, secret-
    # shaped kinds, oversized names) never render.
    async def run():
        canary_cases = [
            (
                {
                    "logical_name": f"catalog/runs/demo-run-{CAT_JOB_ID}/catalog-refresh.json",
                    "kind": "refresh_bundle",
                    "byte_count": 1,
                    "captured_at": 1750000000.0,
                },
                "demo-run-" + CAT_JOB_ID,
            ),
            (
                {
                    "logical_name": f"catalog/jobs/{CAT_JOB_ID}.json",
                    "kind": "sk-slaif-KINDCANARY",
                    "byte_count": 1,
                    "captured_at": 1750000000.0,
                },
                "sk-slaif-KINDCANARY",
            ),
            (
                {
                    "logical_name": f"catalog/proposals/{CAT_JOB_ID}/../../../etc/slaif-passwd",
                    "kind": "markdown",
                    "byte_count": 1,
                    "captured_at": 1750000000.0,
                },
                "etc/slaif-passwd",
            ),
            (
                {
                    "logical_name": f"catalog/jobs/{CAT_JOB_ID}.json" + "z" * 300,
                    "kind": "job_record",
                    "byte_count": 1,
                    "captured_at": 1750000000.0,
                },
                "z" * 300,
            ),
        ]
        for bad_leaf, canary in canary_cases:
            fake = FakeFacade()
            fake.worker_target_db = COPY_OK
            _preflight_case(monkeypatch, COPY_OK, "on")
            factory, made = _display_factory(leaves=[CAT_LEAF_RUN, bad_leaf])
            app = _app(fake, display_reader_factory=factory)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(CATALOG_INDEX_URL)
                assert r.status_code == 503
                assert r.headers.get("cache-control") == "private, no-store"
                assert dac._SAFE_UNAVAILABLE in r.text
                assert canary not in r.text
                assert len(made) == 1

    asyncio.run(run())


def test_catalog_index_handler_without_demo_state_404():
    # Defensive: the handler itself refuses without gate-validated
    # request-local demo state (the gate guarantees it in practice).
    async def run():
        app = _app(FakeFacade())
        request = _bare_request(app)
        response = await dac.demo_catalog_index(request)
        assert response.status_code == 404

    asyncio.run(run())


def test_dashboard_demo_only_catalog_card():
    # The demo dashboard links the exact index path; the normal
    # dashboard is unchanged (no catalog card, no 15th nav item).
    from slaif_gateway.api.admin import templates as admin_templates

    async def _render(request):
        response = admin_templates.TemplateResponse(
            request,
            "dashboard.html",
            {"admin": object(), "csrf_token": "x" * 40, "admin_status_message": None},
        )
        return response.body.decode("utf-8")

    async def run():
        normal = await _render(_fake_admin_request("/admin"))
        assert CATALOG_INDEX_URL not in normal
        demo = await _render(_fake_admin_request("/admin", demo_admin=object()))
        assert f'href="{CATALOG_INDEX_URL}"' in demo
        assert "Catalog snapshot index" in demo

    asyncio.run(run())




# --- 224-l: demo-only sanitized display-copy artifact download ---------------

import hashlib  # noqa: E402

CATALOG_ARTIFACT_URL = "/admin/operations/catalog/artifact"


class _ArtifactResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _ArtifactFakeSession:
    """One fake request-local copy session: preflight scalars plus the
    recorded parameterized statements (metadata with octet_length,
    then the bounded body query). Every executed statement and its
    bound parameters are logged for the seam assertions."""

    def __init__(self, meta_rows, body_rows, db, ro) -> None:
        self.meta_rows = meta_rows
        self.body_rows = body_rows
        self.db = db
        self.ro = ro
        self.executed: list[tuple[str, dict]] = []

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def scalar(self, clause):
        text = str(clause)
        if "current_database" in text:
            return self.db
        return self.ro

    async def execute(self, clause, params=None):
        text = str(clause)
        params = dict(params or {})
        self.executed.append((text, params))
        if text.lstrip().startswith("SELECT body"):
            return _ArtifactResult(self.body_rows)
        return _ArtifactResult(self.meta_rows)


def _meta_row(kind="job_record", size=None, sha=None, actual=None, body=None):
    """A closed, self-consistent metadata tuple; explicit kwargs
    corrupt exactly ONE field per test case."""
    if body is None:
        body = b"payload"
    if size is None:
        size = len(body)
    if actual is None:
        actual = len(body)
    if sha is None:
        sha = hashlib.sha256(body).hexdigest()
    return (kind, size, sha, actual)


def _patch_sessionmaker(monkeypatch, session):
    # The demo handler reaches the copy ONLY through the gate-bound
    # request-local seam; substitute a fake carrying the recorded
    # statements (restored by the fixture).
    monkeypatch.setattr(
        dac, "get_sessionmaker_from_app", lambda _req: lambda: session
    )


def _artifact_app(fake, monkeypatch, session):
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    _patch_sessionmaker(monkeypatch, session)
    return _app(fake), fake


def test_catalog_artifact_gate_admission_exact_path():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # The ONE exact artifact path is ADMITTED (no session ->
            # entry redirect, same law as the index)...
            r = await client.get(CATALOG_ARTIFACT_URL)
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            # ...and every near-miss stays default-denied 404.
            for p in (
                CATALOG_ARTIFACT_URL + "/",        # trailing slash
                CATALOG_ARTIFACT_URL + "s",        # prefix sibling
                CATALOG_ARTIFACT_URL + "/extra",   # deeper path
                "/admin/operations/catalogx/artifact",
                # the 224-k deeper catalog artifact paths stay denied
                f"/admin/operations/catalog/runs/{CAT_RUN_ID}/artifact/x",
                f"/admin/operations/catalog/jobs/{CAT_JOB_ID}/artifact/x",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_catalog_artifact_zero_active_404():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            r = await client.get(
                CATALOG_ARTIFACT_URL, params={"name": f"catalog/jobs/{CAT_JOB_ID}.json"}
            )
            assert r.status_code == 404

    asyncio.run(run())


def test_catalog_artifact_unsafe_methods_quiet_noop_body_not_parsed():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                r = await client.request(
                    method,
                    CATALOG_ARTIFACT_URL,
                    params={"name": f"catalog/jobs/{CAT_JOB_ID}.json"},
                    content=b"x" * 200_000,
                    headers={"content-type": "text/garbage"},
                )
                assert r.status_code == 204, method
                assert r.content == b""
        async with _client(app) as anon:
            r = await anon.post(CATALOG_ARTIFACT_URL, content=b"y" * 200_000)
            assert r.status_code == 404

    asyncio.run(run())


def test_catalog_artifact_query_seams_refused_without_echo(monkeypatch):
    # Exactly ONE bounded `name` value and no duplicate/unknown
    # parameters; unknown, non-catalog, traversal, source-like and
    # overlong selectors get the fixed safe 404 with NO echo and NO
    # copy query (the name law runs before any session use).
    async def run():
        from types import SimpleNamespace

        from starlette.requests import Request

        app = _app(FakeFacade())
        demo = SimpleNamespace(target_db=COPY_OK)
        session = _ArtifactFakeSession([_meta_row()], [(b"payload",)], COPY_OK, "on")
        _patch_sessionmaker(monkeypatch, session)
        cases = [
            b"",                                                # no query
            b"name=",                                           # empty name
            b"name=a&name=a",                                   # duplicate
            b"name=a&x=1",                                      # unknown param
            b"x=1",                                             # missing name
            b"name=branding/logo",                              # non-catalog
            b"name=catalog%2F..%2F..%2Fetc%2Fpasswd",           # traversal
            b"name=catalog%2Fruns%2F" + b"a1" * 16 + b"%2Fx",   # source-like
            b"name=" + b"z" * 300,                              # overlong
        ]
        for query in cases:
            scope = {
                "type": "http",
                "app": app,
                "state": {"demo_admin": demo},
                "query_string": query,
            }
            response = await dac.demo_catalog_artifact(Request(scope))
            assert response.status_code == 404, query
            assert response.body == b"Not Found"
        # The name law refused BEFORE any copy query: nothing executed.
        assert session.executed == []

    asyncio.run(run())


def test_catalog_artifact_handler_without_demo_state_404():
    async def run():
        app = _app(FakeFacade())
        request = _bare_request(app)
        request.scope["query_string"] = (
            b"name=" + f"catalog/jobs/{CAT_JOB_ID}.json".encode()
        )
        response = await dac.demo_catalog_artifact(request)
        assert response.status_code == 404

    asyncio.run(run())


def test_catalog_artifact_preflight_mismatch_503(monkeypatch):
    # The handler's OWN in-transaction recheck (independent of the
    # gate preflight): wrong database or read-only off -> fixed 503
    # and no metadata/body query runs.
    async def run():
        for db, ro in ((COPY_OK, "off"), ("some_other_db", "on")):
            fake = FakeFacade()
            fake.worker_target_db = COPY_OK
            _preflight_case(monkeypatch, COPY_OK, "on")
            session = _ArtifactFakeSession([], [], db, ro)
            _patch_sessionmaker(monkeypatch, session)
            app = _app(fake)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(
                    CATALOG_ARTIFACT_URL,
                    params={"name": f"catalog/jobs/{CAT_JOB_ID}.json"},
                )
                assert r.status_code == 503, (db, ro)
                assert r.headers.get("cache-control") == "private, no-store"
                assert dac._SAFE_ARTIFACT_UNAVAILABLE in r.text
                assert COPY_OK not in r.text
                assert "demo_display" not in r.text
                assert "Traceback" not in r.text
                assert session.executed == []

    asyncio.run(run())


def test_catalog_artifact_metadata_missing_404(monkeypatch):
    async def run():
        good = f"catalog/jobs/{CAT_JOB_ID}.json"
        session = _ArtifactFakeSession([], [], COPY_OK, "on")
        app, fake = _artifact_app(FakeFacade(), monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_ARTIFACT_URL, params={"name": good})
            assert r.status_code == 404
            assert r.content == b"Not Found"
        # One parameterized metadata lookup with the EXACT remapped
        # name (no identifier interpolation), nothing else.
        assert len(session.executed) == 1
        text, params = session.executed[0]
        assert "octet_length(body)" in text
        assert params == {"name": good}

    asyncio.run(run())


def test_catalog_artifact_invalid_metadata_fixed_503_no_body_fetch(monkeypatch):
    # Invalid closed kind/size/hash OR a corrupt actual body length
    # (claimed byte_count small, stored body oversized/different) is
    # one fixed safe 503, and the body query NEVER runs. Each case
    # corrupts exactly ONE otherwise-valid field.
    good = f"catalog/jobs/{CAT_JOB_ID}.json"
    cases = [
        _meta_row(kind="Job_Record"),                  # uppercase kind
        _meta_row(kind="a" * 65),                      # unbounded kind
        _meta_row(size=-1, actual=-1),                 # negative size
        _meta_row(size=True, actual=1),                # bool size
        _meta_row(size=33 * 1024 * 1024,
                  actual=33 * 1024 * 1024),            # claimed+actual over cap
        _meta_row(sha="Z" * 64),                       # non-hex digest
        _meta_row(sha="ab" * 31),                      # short digest (62)
        _meta_row(sha="ab" * 33),                      # long digest (66)
        ("job_record", 7, 123, 7),                     # non-str digest
        ("job_record", 7, None, 7),                    # null digest
        _meta_row(actual=8),                           # actual != claimed
        _meta_row(actual="7"),                         # str actual
        (None, None, None, None),                      # null metadata
    ]

    async def run():
        for meta in cases:
            session = _ArtifactFakeSession([meta], [(b"payload",)], COPY_OK, "on")
            app, fake = _artifact_app(FakeFacade(), monkeypatch, session)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(CATALOG_ARTIFACT_URL, params={"name": good})
                assert r.status_code == 503, meta
                assert r.headers.get("cache-control") == "private, no-store"
                assert dac._SAFE_ARTIFACT_UNAVAILABLE in r.text
                assert "payload" not in r.text
                # Metadata query only: the body query never ran.
                assert len(session.executed) == 1, meta

    asyncio.run(run())


def test_catalog_artifact_body_refusal_on_mismatch_or_absence(monkeypatch):
    good = f"catalog/jobs/{CAT_JOB_ID}.json"
    body = b"the-sanitized-bytes"
    meta = _meta_row(body=body)

    async def run():
        # Re-fetched row no longer satisfies the bounded conditions:
        # no body rows -> fixed 503.
        session = _ArtifactFakeSession([meta], [], COPY_OK, "on")
        app, fake = _artifact_app(FakeFacade(), monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_ARTIFACT_URL, params={"name": good})
            assert r.status_code == 503
            assert dac._SAFE_ARTIFACT_UNAVAILABLE in r.text
        # The bounded body query re-asserts kind/size/digest/cap as
        # BOUND parameters (no identifier interpolation).
        assert len(session.executed) == 2
        text, params = session.executed[1]
        assert text.lstrip().startswith("SELECT body")
        assert params == {
            "name": good,
            "kind": meta[0],
            "size": len(body),
            "digest": meta[2],
            "cap": dac._MAX_ARTIFACT_BYTES,
        }
        # Fetched body whose length or SHA disagrees: fixed 503, no
        # bytes served.
        for bad_body in (b"the-sanitized-bytez", b"the-sanitized-bytesX"):
            session = _ArtifactFakeSession([meta], [(bad_body,)], COPY_OK, "on")
            app, fake = _artifact_app(FakeFacade(), monkeypatch, session)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(CATALOG_ARTIFACT_URL, params={"name": good})
                assert r.status_code == 503, bad_body
                assert r.headers.get("cache-control") == "private, no-store"
                assert dac._SAFE_ARTIFACT_UNAVAILABLE in r.text
                assert bad_body not in r.content

    asyncio.run(run())


def test_catalog_artifact_positive_forced_attachment(monkeypatch):
    body = b'{"demo": "sanitized display copy"}' * 100
    meta = _meta_row(kind="job_record", body=body)
    good = f"catalog/jobs/{CAT_JOB_ID}.json"

    async def run():
        session = _ArtifactFakeSession([meta], [(body,)], COPY_OK, "on")
        app, fake = _artifact_app(FakeFacade(), monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_ARTIFACT_URL, params={"name": good})
            assert r.status_code == 200
            # Byte-accurate sanitized body (the ONLY body source).
            assert r.content == body
            # Forced attachment + nosniff + locked CSP + no-store.
            assert r.headers["content-type"] == "application/octet-stream"
            assert r.headers["content-disposition"] == (
                f'attachment; filename="{CAT_JOB_ID}.json"'
            )
            assert r.headers["x-content-type-options"] == "nosniff"
            assert r.headers["content-security-policy"] == "default-src 'none'"
            assert r.headers["cache-control"] == "private, no-store"
            # No stored hash, DSN, credential or source path echoes.
            assert meta[2] not in r.text
            assert COPY_OK not in r.text
            assert "unit-test-copy-password" not in r.text

    asyncio.run(run())


def test_catalog_artifact_html_name_still_forced_attachment(monkeypatch):
    # Even an artifact literally named REVIEW.html is served as a
    # forced octet-stream attachment, never inline active content.
    body = b"<html><body><script>alert(1)</script></body></html>"
    name = f"catalog/runs/{CAT_RUN_ID}/REVIEW.html"
    meta = _meta_row(kind="review_html", body=body)

    async def run():
        session = _ArtifactFakeSession([meta], [(body,)], COPY_OK, "on")
        app, fake = _artifact_app(FakeFacade(), monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_ARTIFACT_URL, params={"name": name})
            assert r.status_code == 200
            assert r.headers["content-type"] == "application/octet-stream"
            assert r.headers["content-disposition"] == (
                'attachment; filename="REVIEW.html"'
            )
            assert r.headers["x-content-type-options"] == "nosniff"
            assert r.headers["content-security-policy"] == "default-src 'none'"
            assert r.headers["cache-control"] == "private, no-store"
            assert r.content == body

    asyncio.run(run())


# --- 224-m: demo-only copy-backed catalog run detail --------------------------

import json as _rd_json  # noqa: E402

from slaif_gateway.services import demo_snapshot_files as _rd_dsf  # noqa: E402

RD_SEED = b"224m-unit-seed"
RD_ORIGINAL_RUN_ID = "f4" * 16  # an ORIGINAL (non-remapped) run id
RD_RUN_ID = _rd_dsf._demo_run_id(RD_SEED, RD_ORIGINAL_RUN_ID)  # demo-run-<24hex>


def _rd_original_validation_doc(run_id: str = RD_ORIGINAL_RUN_ID, state: str = "VALID"):
    # A synthetic ORIGINAL validation document (the 223 sanitizer's
    # input); the POSITIVE fixture is the sanitizer's OWN output, not
    # a hand-written sanitized document.
    return {
        "state": state,
        "state_reason": "free text that is never displayed",
        "run_id": run_id,
        "generated_at": "2025-06-15T15:06:40+00:00",
        "policy_version": 7,
        "counts": {"routes": 3, "pricing": 2},
        "per_provider": {
            "openai": {"models": 2, "routes": 2},
            "openrouter": {"models": 1, "pricing": 1},
        },
        "dispositions": [
            {"provider": "openai", "model": "gpt-test", "disposition": "kept"}
        ],
        "price_comparisons": [
            {
                "provider": "openrouter",
                "model": "or-test",
                "dimension": "input",
                "old": "1.5",
                "new": "2.0",
                "currency_old": "USD",
                "currency_new": "USD",
                "percent_change": "-33.33",
                "state": "changed",
            }
        ],
        "warnings": [
            {"severity": "info", "code": "demo-warning", "provider": "openai"}
        ],
        "gates": [{"name": "schema"}],
        "import_gates": [],
        "baseline": {"a": 1},
        "research": {},
        "artifacts": {"b": 1},
        "sql_checks": {},
        "baseline_metadata": [
            {
                "provider": "openai",
                "model": "gpt-test",
                "upstream_model": "gpt-real",
                "fields": {"x": 1},
            }
        ],
        "sources": [],
        "source_evidence": {},
        "fx_comparisons": [],
        "execution_context": {},
        "apply_plan": {"plan": "never displayed"},
    }


def _rd_validation_body(state: str = "VALID") -> bytes:
    # The ACTUAL 223 sanitizer output for the synthetic original doc.
    return _rd_dsf._san_validation_json(
        _rd_json.dumps(_rd_original_validation_doc(state=state)).encode(), RD_SEED
    )


def _rd_inventory(run_id: str = RD_RUN_ID, validation_body: bytes | None = None):
    """The closed seven worker-published run content rows (consistent
    kind/size/sha/actual/capture) for one remapped run."""
    if validation_body is None:
        validation_body = _rd_validation_body()
    rows = []
    for filename, kind in dac._RUN_DETAIL_FILES:
        full = f"catalog/runs/{run_id}/{filename}"
        data = validation_body if filename == "validation.json" else b"{}"
        size = len(data)
        rows.append(
            (full, kind, size, hashlib.sha256(data).hexdigest(), 1750000000.0, size)
        )
    return rows


def _rd_app(fake, monkeypatch, session):
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    _patch_sessionmaker(monkeypatch, session)
    return _app(fake), fake


def test_run_detail_gate_admission_exact_shape():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # The ONE canonical shape is ADMITTED (no session -> entry
            # redirect, same law as the index)...
            r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            # ...every near-miss / noncanonical / source ID stays 404.
            for p in (
                f"/admin/operations/catalog/runs/{RD_RUN_ID}",   # no trailing slash
                f"/admin/operations/catalog/runs/{RD_RUN_ID}/x", # deeper path
                f"/admin/operations/catalog/runs/{CAT_RUN_ID}/extra/",
                f"/admin/operations/catalog/runs/demo-run-{'a1' * 16}/",  # 32 hex
                f"/admin/operations/catalog/runs/{CAT_JOB_ID}/",          # original id
                f"/admin/operations/catalog/runs/demo-run-{'A1' * 12}/",  # uppercase hex
                "/admin/operations/catalog/runs/demo-run-a1/short/",      # short hex
                "/admin/operations/catalog/runs/",
                "/admin/operations/catalog/runs",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_run_detail_zero_active_404():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
            assert r.status_code == 404

    asyncio.run(run())


def test_run_detail_unsafe_methods_quiet_noop_body_not_parsed():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                r = await client.request(
                    method,
                    f"/admin/operations/catalog/runs/{RD_RUN_ID}/",
                    content=b"x" * 200_000,
                    headers={"content-type": "text/garbage"},
                )
                assert r.status_code == 204, method
                assert r.content == b""
        async with _client(app) as anon:
            r = await anon.post(f"/admin/operations/catalog/runs/{RD_RUN_ID}/", content=b"y" * 200_000)
            assert r.status_code == 404

    asyncio.run(run())


def test_run_detail_handler_without_demo_state_or_invalid_id_404():
    async def run():
        app = _app(FakeFacade())
        # No gate-validated request-local state: defensive 404.
        request = _bare_request(app)
        assert (await dac.demo_catalog_run_detail(request, RD_RUN_ID)).status_code == 404
        # A source-shaped / noncanonical id is refused even with state.
        from types import SimpleNamespace

        demo = SimpleNamespace(target_db=COPY_OK)
        request = _bare_request(app, {"demo_admin": demo})
        for bad in (
            RD_ORIGINAL_RUN_ID,      # original (non-remapped) id
            "demo-run-" + "a1" * 16,  # 32 hex, not 24
            "x",
        ):
            assert (
                await dac.demo_catalog_run_detail(request, bad)
            ).status_code == 404
        # A CANONICAL id with demo state lacking a usable request-local
        # sessionmaker fails closed to the fixed safe 503 (never a raw
        # error).
        response = await dac.demo_catalog_run_detail(request, CAT_RUN_ID)
        assert response.status_code == 503
        assert dac._SAFE_RUN_DETAIL_UNAVAILABLE in response.body.decode()

    asyncio.run(run())


def test_run_detail_preflight_mismatch_503(monkeypatch):
    async def run():
        for db, ro in ((COPY_OK, "off"), ("some_other_db", "on")):
            fake = FakeFacade()
            fake.worker_target_db = COPY_OK
            _preflight_case(monkeypatch, COPY_OK, "on")
            session = _ArtifactFakeSession(_rd_inventory(), [], db, ro)
            _patch_sessionmaker(monkeypatch, session)
            app = _app(fake)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
                assert r.status_code == 503, (db, ro)
                assert r.headers.get("cache-control") == "private, no-store"
                assert dac._SAFE_RUN_DETAIL_UNAVAILABLE in r.text
                assert COPY_OK not in r.text
                assert "demo_display" not in r.text
                assert "Traceback" not in r.text
                assert session.executed == []

    asyncio.run(run())


def test_run_detail_missing_run_404(monkeypatch):
    async def run():
        session = _ArtifactFakeSession([], [], COPY_OK, "on")
        app, fake = _rd_app(FakeFacade(), monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
            assert r.status_code == 404
            assert r.content == b"Not Found"
        # Exactly ONE parameterized inventory query (the closed seven
        # names, no wildcard, no pathname); no body query.
        assert len(session.executed) == 1
        text, params = session.executed[0]
        assert "IN (" in text
        assert set(params) == {f"n{i}" for i in range(7)}
        assert sorted(params.values()) == sorted(
            f"catalog/runs/{RD_RUN_ID}/{filename}"
            for filename, _kind in dac._RUN_DETAIL_FILES
        )

    asyncio.run(run())


def test_run_detail_incomplete_run_fixed_503(monkeypatch):
    # 1..6 of the seven worker-published files: an incomplete row set
    # is one fixed safe 503, and the body query NEVER runs.
    async def run():
        for keep in (1, 6):
            rows = _rd_inventory()[:keep]
            session = _ArtifactFakeSession(rows, [(_rd_validation_body(),)], COPY_OK, "on")
            app, fake = _rd_app(FakeFacade(), monkeypatch, session)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
                assert r.status_code == 503, keep
                assert r.headers.get("cache-control") == "private, no-store"
                assert dac._SAFE_RUN_DETAIL_UNAVAILABLE in r.text
                assert len(session.executed) == 1, keep

    asyncio.run(run())


def test_run_detail_corrupt_row_fixed_503(monkeypatch):
    async def run():
        cases = []
        rows = _rd_inventory()
        bad_kind = list(rows)
        full, kind, size, sha, at, actual = bad_kind[5]
        bad_kind[5] = (full, "job_record", size, sha, at, actual)  # wrong kind
        cases.append(bad_kind)
        bad_sha = list(rows)
        full, kind, size, sha, at, actual = rows[5]
        bad_sha[5] = (full, kind, size, "Z" * 64, at, actual)
        cases.append(bad_sha)
        bad_size = list(rows)
        full, kind, size, sha, at, actual = rows[5]
        bad_size[5] = (full, kind, size, sha, at, size + 1)  # actual != claimed
        cases.append(bad_size)
        bad_cap = list(rows)
        full, kind, size, sha, at, actual = rows[5]
        huge = 33 * 1024 * 1024
        bad_cap[5] = (full, kind, huge, sha, at, huge)  # above the 32 MiB cap
        cases.append(bad_cap)
        bad_time = list(rows)
        full, kind, size, sha, at, actual = rows[5]
        bad_time[5] = (full, kind, size, sha, float("nan"), actual)
        cases.append(bad_time)
        for corrupt in cases:
            session = _ArtifactFakeSession(corrupt, [(_rd_validation_body(),)], COPY_OK, "on")
            app, fake = _rd_app(FakeFacade(), monkeypatch, session)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
                assert r.status_code == 503, corrupt
                assert dac._SAFE_RUN_DETAIL_UNAVAILABLE in r.text
                assert len(session.executed) == 1, corrupt

    asyncio.run(run())


def test_run_detail_validation_body_refusals_503(monkeypatch):
    async def run():
        body = _rd_validation_body()
        # Bounded body fetch finds no matching row -> 503.
        session = _ArtifactFakeSession(_rd_inventory(), [], COPY_OK, "on")
        app, fake = _rd_app(FakeFacade(), monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
            assert r.status_code == 503
            assert len(session.executed) == 2

        # Non-JSON body (consistent metadata): the typed re-proof fails.
        bad = b"not-json-at-all"
        session = _ArtifactFakeSession(
            _rd_inventory(validation_body=bad), [(bad,)], COPY_OK, "on"
        )
        app, fake = _rd_app(FakeFacade(), monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
            assert r.status_code == 503
            assert b"not-json" not in r.content

        # A typed-valid sanitized doc for ANOTHER seed (another run) is
        # refused by the run-ID routing check.
        other_body = _rd_dsf._san_validation_json(
            _rd_json.dumps(_rd_original_validation_doc()).encode(), b"other-seed"
        )
        session = _ArtifactFakeSession(
            _rd_inventory(validation_body=other_body), [(other_body,)], COPY_OK, "on"
        )
        app, fake = _rd_app(FakeFacade(), monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
            assert r.status_code == 503

        # Hand-mutated sanitized doc (wrong kind): typed re-proof fails.
        doc = _rd_json.loads(body)
        doc["kind"] = "job_record"
        mutated = _rd_json.dumps(doc).encode()
        session = _ArtifactFakeSession(
            _rd_inventory(validation_body=mutated), [(mutated,)], COPY_OK, "on"
        )
        app, fake = _rd_app(FakeFacade(), monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
            assert r.status_code == 503

    asyncio.run(run())


def test_run_detail_positive_page(monkeypatch):
    body = _rd_validation_body()

    async def run():
        session = _ArtifactFakeSession(_rd_inventory(), [(body,)], COPY_OK, "on")
        app, fake = _rd_app(FakeFacade(), monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            text = _norm(r.text)
            # The prominent neutralized banner + historical-status law.
            assert "Sanitized snapshot display" in text
            assert "no original seal" in text
            assert "no live status" in text
            assert "no apply authority" in text
            assert "historical at capture time" in text
            # Bounded sanitized fields render (values from the 223
            # sanitizer output, not a hand-built projection).
            assert "VALID" in text
            assert "2025-06-15T15:06:40+00:00" in text
            assert "Count categories retained" in text
            assert "not a count" in text
            assert "Sum of provider count metrics" in text
            assert "in the captured run" in text
            assert "openai" in text and "openrouter" in text
            # per_provider sums (2 + 2 and 1 + 1), not model counts.
            assert 'title="4"' in r.text
            assert 'title="2"' in r.text
            assert "demo-warning" in text
            assert "gpt-test" in text
            assert "kept" in text
            assert "input" in text
            # Signed percent renders directly (no ± before a signed value).
            assert "-33.33%" in text
            assert "±-33.33" not in text
            # The neutralized-details note.
            assert "neutralized in this sanitized display copy" in text
            # All seven captured artifacts, each linked to the exact
            # 224-l forced-download selector (literal closed charset).
            for filename, _kind in dac._RUN_DETAIL_FILES:
                assert (
                    f'href="/admin/operations/catalog/artifact'
                    f'?name=catalog/runs/{RD_RUN_ID}/{filename}"'
                ) in r.text
            assert "2025-06-15 15:06:40 UTC" in text
            # No DSN fragment, copy name or credential escapes.
            assert COPY_OK not in r.text
            assert "unit-test-copy-password" not in r.text
            assert RD_ORIGINAL_RUN_ID not in r.text
        # Inventory (parameterized) + ONE bounded body fetch only.
        assert len(session.executed) == 2
        body_text, body_params = session.executed[1]
        assert body_text.lstrip().startswith("SELECT body")
        assert body_params["cap"] == dac._MAX_ARTIFACT_BYTES

    asyncio.run(run())


def test_run_detail_html_canary_is_escaped(monkeypatch):
    # A sanitizer-legal string field containing markup must render
    # escaped, never as active content.
    canary = "<script>alert(1)</script>"
    body = _rd_validation_body(state=canary)

    async def run():
        session = _ArtifactFakeSession(
            _rd_inventory(validation_body=body), [(body,)], COPY_OK, "on"
        )
        app, fake = _rd_app(FakeFacade(), monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(f"/admin/operations/catalog/runs/{RD_RUN_ID}/")
            assert r.status_code == 200
            assert "<script>alert(1)</script>" not in r.text
            assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text

    asyncio.run(run())


def test_run_detail_index_links_run_ids_only(monkeypatch):
    # The index links the remapped run id ONLY for run rows; job
    # rows stay plain text.
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        factory, _made = _display_factory(leaves=[CAT_LEAF_RUN, CAT_LEAF_JOB, LEAF_TWO])
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_INDEX_URL)
            assert r.status_code == 200
            assert (
                f'href="/admin/operations/catalog/runs/{CAT_RUN_ID}/"'
            ) in r.text
            # The jobs row's demo id is NOT linked to a run detail.
            assert f'href="/admin/operations/catalog/runs/{CAT_JOB_ID}/"' not in r.text

    asyncio.run(run())


# --- 224-n: demo-only copy-backed captured proposals page ----------------------

from types import SimpleNamespace as _PN_NS  # noqa: E402

PN_SEED = b"224n-unit-seed"
PN_ORIGINAL_JOB_A = "c3" * 16  # ORIGINAL (never displayed)
PN_ORIGINAL_JOB_B = "d4" * 16
PN_JOB_A = _rd_dsf._demo_job_id(PN_SEED, PN_ORIGINAL_JOB_A)  # 32 hex
PN_JOB_B = _rd_dsf._demo_job_id(PN_SEED, PN_ORIGINAL_JOB_B)
PN_URL = "/admin/operations/catalog/proposals"
PN_RECORD_BODY = None  # set lazily by _pn_record_body


def _pn_original_record(job_id: str, family: str = "proposal", status: str = "ready"):
    # A synthetic ORIGINAL custody job record (the 223 sanitizer's
    # input); the POSITIVE fixture is the sanitizer's OWN output.
    return {
        "job_id": job_id,
        "family": family,
        "status": status,
        "progress": "free text never displayed",
        "dispatch": None,
        "run_id": None,
        "artifact_name": None,
        "cancel_requested": False,
        "created_at": "2025-06-15T15:00:00+00:00",
        "updated_at": "2025-06-15T15:06:40+00:00",
    }


def _pn_record_body(job_id: str = PN_ORIGINAL_JOB_A, **kw) -> bytes:
    # The ACTUAL 223 sanitizer output for the synthetic original record.
    return _rd_dsf._sanitize_job_record(
        _rd_json.dumps(_pn_original_record(job_id, **kw)).encode(), PN_SEED
    )


def _pn_leaf(name: str, kind: str, data: bytes, captured: float):
    return (name, kind, len(data), hashlib.sha256(data).hexdigest(), captured)


def _pn_inventory(record: bytes | None = None, extra_rows=(), drop_job_b=False):
    """Two captured proposal job groups (A newer than B), one skipped
    non-proposals run row, and (optionally) A's sanitized job record."""
    rows = [
        _pn_leaf(
            f"catalog/proposals/{PN_JOB_A}/routes-proposal.tsv",
            "route_tsv", b"{}", 1750000100.0,
        ),
        _pn_leaf(
            f"catalog/proposals/{PN_JOB_A}"
            "/packages/openrouter-chat-text/pricing-proposal.tsv",
            "pricing_tsv", b"{}", 1750000050.0,
        ),
    ]
    if not drop_job_b:
        rows.append(
            _pn_leaf(
                f"catalog/proposals/{PN_JOB_B}/warnings.json",
                "warnings_json", b"{}", 1750000000.0,
            )
        )
    rows.append(
        _pn_leaf(
            f"catalog/runs/{CAT_RUN_ID}/catalog-refresh.json",
            "refresh_bundle", b"{}", 1750000001.0,
        )
    )
    if record is not None:
        rows.append(
            _pn_leaf(f"catalog/jobs/{PN_JOB_A}.json", "job_record", record, 1750000002.0)
        )
    rows.extend(extra_rows)
    return rows


_PN_DEFAULT_CHOICES = (_PN_NS(id="gpt-test", label="gpt-test", sub=""),)


def _pn_app(fake, monkeypatch, session, choices=_PN_DEFAULT_CHOICES):
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    _patch_sessionmaker(monkeypatch, session)

    async def _fake_load_choices(session, kind, selected=()):
        assert kind == "catalog_upstream"
        return list(choices)

    monkeypatch.setattr(dac, "load_choices", _fake_load_choices)
    return _app(fake), fake


def _pn_bare_request(app, state, query: str = ""):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "app": app,
        "state": dict(state or {}),
        "query_string": query.encode(),
    }
    return Request(scope)


def test_proposals_gate_admission_exact_path():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # The ONE exact path is ADMITTED (no session -> entry
            # redirect, same law as the index)...
            r = await client.get(PN_URL)
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            # ...and every near-miss / extra suffix stays default-
            # denied 404.
            for p in (
                PN_URL + "/",             # trailing slash
                PN_URL + "s",             # prefix sibling
                PN_URL + "/extra",        # deeper path
                "/admin/operations/catalogx/proposals",
                "/admin/operations/catalog/proposal",
                "/admin/operations/catalog/proposals/generate",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_proposals_zero_active_404():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            r = await client.get(PN_URL)
            assert r.status_code == 404

    asyncio.run(run())


def test_proposals_unsafe_methods_quiet_noop_body_not_parsed():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            paths = (PN_URL, PN_URL + "/generate", PN_URL + "/imports/cancel")
            for p in paths:
                for method in ("POST", "PUT", "PATCH", "DELETE"):
                    # 200 KB garbage body: a 204 proves the body was
                    # never parsed before the cut.
                    r = await client.request(
                        method,
                        p,
                        content=b"x" * 200_000,
                        headers={"content-type": "text/garbage"},
                    )
                    assert r.status_code == 204, (p, method)
                    assert r.content == b""
        async with _client(app) as anon:
            r = await anon.post(
                PN_URL,
                content=b"y" * 200_000,
                headers={"content-type": "text/garbage"},
            )
            assert r.status_code == 404

    asyncio.run(run())


def test_proposals_query_law_refusals_404_no_db_access(monkeypatch):
    async def run():
        app = _app(FakeFacade())
        demo = _PN_NS(target_db=COPY_OK)

        calls: list = []

        def _refusing_sessionmaker(_req):
            calls.append(_req)
            raise RuntimeError("no copy query before the query law")

        # The query law refuses BEFORE any sessionmaker/copy access.
        monkeypatch.setattr(
            dac, "get_sessionmaker_from_app", _refusing_sessionmaker
        )

        # Missing demo state: defensive 404.
        request = _pn_bare_request(app, {})
        assert (await dac.demo_catalog_proposals(request)).status_code == 404
        # With state, every non-canonical query shape is a fixed 404
        # BEFORE any sessionmaker/copy access.
        for query in (
            "job=" + PN_JOB_A + "&job=" + PN_JOB_B,  # duplicate param
            "job=" + PN_JOB_A + "&x=1",              # extra param
            "x=1",                                   # unknown param
            "job=",                                  # empty value
            "job=" + "a1" * 12,                      # wrong length
            "job=" + "A1" * 16,                      # uppercase hex
            "job=" + PN_JOB_A + "!",                 # non-hex char
            "job=" + "a1" * 300,                     # overlong
        ):
            request = _pn_bare_request(app, {"demo_admin": demo}, query)
            assert (
                await dac.demo_catalog_proposals(request)
            ).status_code == 404, query
        # Proven: no refusal path touched the copy seam.
        assert calls == []

    asyncio.run(run())


def test_proposals_canonical_id_no_sessionmaker_503(monkeypatch):
    async def run():
        app = _app(FakeFacade())
        demo = _PN_NS(target_db=COPY_OK)

        class _RaiseFactory:
            def __call__(self):
                raise RuntimeError("no sessionmaker in demo state")

        monkeypatch.setattr(
            dac, "get_sessionmaker_from_app", lambda _req: _RaiseFactory()
        )
        request = _pn_bare_request(app, {"demo_admin": demo})
        response = await dac.demo_catalog_proposals(request)
        assert response.status_code == 503
        assert dac._SAFE_PROPOSALS_UNAVAILABLE in response.body.decode()

    asyncio.run(run())


def test_proposals_preflight_mismatch_503(monkeypatch):
    async def run():
        for db, ro in ((COPY_OK, "off"), ("some_other_db", "on")):
            fake = FakeFacade()
            session = _ArtifactFakeSession(
                meta_rows=[], body_rows=[], db=db, ro=ro
            )
            _pn_app(fake, monkeypatch, session)
            request = _pn_bare_request(app=_app(fake), state={"demo_admin": _PN_NS(target_db=COPY_OK)})
            response = await dac.demo_catalog_proposals(request)
            assert response.status_code == 503
            assert dac._SAFE_PROPOSALS_UNAVAILABLE in response.body.decode()
            # The copy recheck happens BEFORE any copy query.
            assert all("demo_display" not in t for t, _p in session.executed)

    asyncio.run(run())


def test_proposals_inventory_bound_503_and_limit_param(monkeypatch):
    async def run():
        fake = FakeFacade()
        # 4097 rows (all non-proposals, so the bound trips before any
        # per-row law): the bound LIMIT must make the page refuse.
        rows = [
            _pn_leaf(
                f"catalog/jobs/{'a1' * 16}.json", "job_record", b"{}", 1750000000.0
            )
        ] * 4097
        session = _ArtifactFakeSession(meta_rows=rows, body_rows=[], db=COPY_OK, ro="on")
        _pn_app(fake, monkeypatch, session)
        request = _pn_bare_request(_app(fake), {"demo_admin": _PN_NS(target_db=COPY_OK)})
        response = await dac.demo_catalog_proposals(request)
        assert response.status_code == 503
        # The inventory statement carries the BOUND limit parameter.
        inventory = [
            (t, p) for t, p in session.executed if "demo_display.leaves" in t and not t.lstrip().startswith("SELECT body")
        ]
        assert len(inventory) == 1
        stmt, params = inventory[0]
        assert "LIMIT :limit" in stmt
        assert params == {"limit": dac._MAX_INDEX_ROWS + 1}

    asyncio.run(run())


def test_proposals_empty_index_honest_200(monkeypatch):
    async def run():
        fake = FakeFacade()
        # Only a NON-proposals run row: an honest empty proposals list.
        session = _ArtifactFakeSession(
            meta_rows=[
                _pn_leaf(
                    f"catalog/runs/{CAT_RUN_ID}/catalog-refresh.json",
                    "refresh_bundle", b"{}", 1750000001.0,
                )
            ],
            body_rows=[],
            db=COPY_OK,
            ro="on",
        )
        app, _ = _pn_app(fake, monkeypatch, session)
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(PN_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            text = _norm(r.text)
            assert "Sanitized demo snapshot display" in text
            assert "ILLUSTRATIVE demo-only form" in text
            assert "submitting has NO effect" in text
            assert "No captured proposal artifact groups in this snapshot" in text
            assert "This does not establish that the copy has no proposal jobs" in text
            assert "status-only job without captured artifacts is not listed" in text
            # The familiar form controls render (demo-labeled).
            assert 'name="provider_scope"' in r.text
            assert 'name="currency"' in r.text
            # The NORMAL custody-backed last-job section never renders.
            assert "Last proposal job" not in text
            assert "Refresh status" not in text
            # No copy name or credential echo.
            assert COPY_OK not in r.text
            # Copy-backed model choice is present (escaped).
            assert "gpt-test" in r.text

    asyncio.run(run())


def test_proposals_positive_page_default_and_selected(monkeypatch):
    async def run():
        record = _pn_record_body()
        fake = FakeFacade()
        session = _ArtifactFakeSession(
            meta_rows=_pn_inventory(record=record),
            body_rows=[(record,)],
            db=COPY_OK,
            ro="on",
        )
        app, _ = _pn_app(fake, monkeypatch, session)
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            # Default (absent param): the MOST-RECENTLY-captured group
            # (A) is selected; its sanitized job record renders
            # HISTORICAL status (real 223 sanitizer body).
            r = await client.get(PN_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            assert f'value="{PN_JOB_A}" selected' in r.text
            assert f"value=\"{PN_JOB_B}\"" in r.text
            assert "most-recently-captured" in _norm(r.text)
            assert "100" in _norm(r.text)  # the stated bound
            # Both captured artifacts of A, each through the exact
            # 224-l forced-download route (full remapped logical name).
            for href in (
                f"?name=catalog/proposals/{PN_JOB_A}/routes-proposal.tsv",
                f"?name=catalog/proposals/{PN_JOB_A}/packages/openrouter-chat-text/pricing-proposal.tsv",
            ):
                assert (
                    f'href="/admin/operations/catalog/artifact{href}"' in r.text
                ), href
            # The typed job-record status, labeled historical.
            assert "historical at capture time" in _norm(r.text)
            assert ">ready<" in r.text
            assert "2025-06-15T15:00:00+00:00" in r.text
            assert "2025-06-15T15:06:40+00:00" in r.text
            # The ORIGINAL job id, progress free text and copy name
            # never render.
            assert PN_ORIGINAL_JOB_A not in r.text
            assert "free text never displayed" not in r.text
            assert COPY_OK not in r.text
            # The body fetch re-asserted the bound conditions as bound
            # parameters.
            body_stmts = [
                (t, p) for t, p in session.executed if t.lstrip().startswith("SELECT body")
            ]
            assert len(body_stmts) == 1
            _stmt, params = body_stmts[0]
            assert params["cap"] == dac._MAX_ARTIFACT_BYTES
            assert params["kind"] == "job_record"
            # Explicit selection of the OLDER group B (no record leaf).
            r = await client.get(PN_URL + "?job=" + PN_JOB_B)
            assert r.status_code == 200
            assert f'value="{PN_JOB_B}" selected' in r.text
            assert "status unavailable in this snapshot" in _norm(r.text)
            assert (
                f'href="/admin/operations/catalog/artifact'
                f"?name=catalog/proposals/{PN_JOB_B}/warnings.json" in r.text
            )
            assert f"?name=catalog/proposals/{PN_JOB_A}/" not in r.text

    asyncio.run(run())


def test_proposals_job_record_refusals_503(monkeypatch):
    async def run():
        cases = (
            # (label, record meta override, body)
            ("non-json/invalid shape", None, b"{}"),
            ("foreign family", None, _pn_record_body(family="collect")),
            ("different job id", None, _pn_record_body(job_id=PN_ORIGINAL_JOB_B)),
            (
                "size mismatch (cap-before-body body query never matches)",
                {"size": 1},
                _pn_record_body(),
            ),
        )
        for label, override, body in cases:
            record = body
            rows = _pn_inventory(record=record)
            if override:
                fixed = []
                for row in rows:
                    if row[0] == f"catalog/jobs/{PN_JOB_A}.json":
                        row = (
                            row[0], row[1], override["size"], row[3], row[4]
                        )
                    fixed.append(row)
                rows = fixed
            fake = FakeFacade()
            session = _ArtifactFakeSession(
                meta_rows=rows, body_rows=[(body,)], db=COPY_OK, ro="on"
            )
            _pn_app(fake, monkeypatch, session)
            app, _ = _pn_app(fake, monkeypatch, session)
            async with _client(app) as client:
                _session_cookie(client)
                await _verified_session_client(fake, client)
                r = await client.get(PN_URL)
                assert r.status_code == 503, label
                assert r.headers["cache-control"] == "private, no-store"
                assert dac._SAFE_PROPOSALS_UNAVAILABLE in _norm(r.text)
                assert body not in r.content, label
        # Metadata claiming >32 MiB refuses BEFORE any body query.
        big = _pn_record_body()
        rows = []
        for row in _pn_inventory(record=big):
            if row[0] == f"catalog/jobs/{PN_JOB_A}.json":
                row = (
                    row[0],
                    row[1],
                    dac._MAX_ARTIFACT_BYTES + 1,
                    row[3],
                    row[4],
                )
            rows.append(row)
        fake = FakeFacade()
        session = _ArtifactFakeSession(
            meta_rows=rows, body_rows=[(big,)], db=COPY_OK, ro="on"
        )
        _pn_app(fake, monkeypatch, session)
        app, _ = _pn_app(fake, monkeypatch, session)
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(PN_URL)
            assert r.status_code == 503
            assert not any(
                t.lstrip().startswith("SELECT body") for t, _p in session.executed
            )

    asyncio.run(run())


def test_proposals_unknown_job_param_404_no_fallback(monkeypatch):
    async def run():
        record = _pn_record_body()
        fake = FakeFacade()
        session = _ArtifactFakeSession(
            meta_rows=_pn_inventory(record=record),
            body_rows=[(record,)],
            db=COPY_OK,
            ro="on",
        )
        app, _ = _pn_app(fake, monkeypatch, session)
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(PN_URL + "?job=" + "e5" * 16)
            assert r.status_code == 404
            # No fallback: the unknown id never renders and NO body
            # query ran for the other (known) job.
            assert PN_JOB_A not in r.text

    asyncio.run(run())


def test_proposals_group_bound_100(monkeypatch):
    async def run():
        # 101 captured groups (A + B + 99 synthetic), one file each:
        # the page lists at most 100, the OLDEST dropped, bound stated.
        extra = [
            _pn_leaf(
                f"catalog/proposals/{('%02x' % i) + '0' * 30}/warnings.json",
                "warnings_json",
                b"{}",
                1740000000.0 + i,
            )
            for i in range(99)
        ]
        fake = FakeFacade()
        session = _ArtifactFakeSession(
            meta_rows=_pn_inventory(extra_rows=extra),
            body_rows=[],
            db=COPY_OK,
            ro="on",
        )
        app, _ = _pn_app(fake, monkeypatch, session)
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(PN_URL)
            assert r.status_code == 200
            values = [
                m for m in __import__("re").finditer(
                    r'<option value="([0-9a-f]{32})"', r.text
                )
            ]
            assert len(values) == 100
            shown = {v.group(1) for v in values}
            assert PN_JOB_A in shown and PN_JOB_B in shown
            # The oldest synthetic group (i=0) is the one dropped.
            assert ("%02x" % 0) + "0" * 30 not in shown
            assert "100" in _norm(r.text)

    asyncio.run(run())


def test_proposals_closed_file_law_corrupt_503(monkeypatch):
    async def run():
        bad_rows = (
            # unknown top-level file name
            [
                _pn_leaf(
                    f"catalog/proposals/{PN_JOB_A}/evil.txt",
                    "route_tsv", b"{}", 1750000100.0,
                )
            ],
            # package preset outside the closed product vocabulary
            [
                _pn_leaf(
                    f"catalog/proposals/{PN_JOB_A}/packages/zzz-package/routes-proposal.tsv",
                    "route_tsv", b"{}", 1750000100.0,
                )
            ],
            # package file name outside the closed set
            [
                _pn_leaf(
                    f"catalog/proposals/{PN_JOB_A}/packages/openrouter-chat-text/evil.tsv",
                    "route_tsv", b"{}", 1750000100.0,
                )
            ],
            # a bare "packages" segment is not a file
            [
                _pn_leaf(
                    f"catalog/proposals/{PN_JOB_A}/packages",
                    "route_tsv", b"{}", 1750000100.0,
                )
            ],
            # kind disagrees with the worker-published file law
            [
                _pn_leaf(
                    f"catalog/proposals/{PN_JOB_A}/routes-proposal.tsv",
                    "job_record", b"{}", 1750000100.0,
                )
            ],
        )
        for rows in bad_rows:
            fake = FakeFacade()
            session = _ArtifactFakeSession(
                meta_rows=rows, body_rows=[], db=COPY_OK, ro="on"
            )
            _pn_app(fake, monkeypatch, session)
            app, _ = _pn_app(fake, monkeypatch, session)
            async with _client(app) as client:
                _session_cookie(client)
                await _verified_session_client(fake, client)
                r = await client.get(PN_URL)
                assert r.status_code == 503, rows[0][0]

    asyncio.run(run())


def test_proposals_html_canary_escaped(monkeypatch):
    async def run():
        record = _pn_record_body()
        canary = _PN_NS(
            id="gpt-canary", label="<script>alert(1)</script>", sub="x&y"
        )
        fake = FakeFacade()
        session = _ArtifactFakeSession(
            meta_rows=_pn_inventory(record=record),
            body_rows=[(record,)],
            db=COPY_OK,
            ro="on",
        )
        app, _ = _pn_app(fake, monkeypatch, session, choices=(canary,))
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(PN_URL)
            assert r.status_code == 200
            assert "<script>alert(1)</script>" not in r.text
            # The canary survives only as escaped/inert JSON.
            assert "gpt-canary" in r.text

    asyncio.run(run())


def test_index_links_proposals_page(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        factory, _made = _display_factory(leaves=[])
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_INDEX_URL)
            assert r.status_code == 200
            assert (
                'href="/admin/operations/catalog/proposals"' in r.text
            )

    asyncio.run(run())


# --- 224-o: demo-only copy-backed collect page + captured runs ----------------

CO_SEED = b"224o-unit-seed"
CO_ORIGINAL_RUN_A = "a5" * 16  # ORIGINAL (never displayed)
CO_ORIGINAL_RUN_B = "b6" * 16
CO_RUN_A = _rd_dsf._demo_run_id(CO_SEED, CO_ORIGINAL_RUN_A)  # demo-run-<24hex>
CO_RUN_B = _rd_dsf._demo_run_id(CO_SEED, CO_ORIGINAL_RUN_B)
CO_URL = "/admin/operations/catalog/collect"
CO_FILE_DATA = b"{}"  # metadata-only fixture bodies (never loaded)


def _co_run_rows(run_id: str, base_captured: float, count: int = 7):
    """The closed seven worker-published sealed-run content rows for one
    remapped run (consistent kind/size/sha/capture; bodies never read)."""
    return [
        _pn_leaf(
            f"catalog/runs/{run_id}/{filename}",
            kind,
            CO_FILE_DATA,
            base_captured + index,
        )
        for index, (filename, kind) in enumerate(dac._RUN_DETAIL_FILES[:count])
    ]


def _co_app(fake, monkeypatch, session, choices=_PN_DEFAULT_CHOICES):
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    _patch_sessionmaker(monkeypatch, session)

    async def _fake_load_choices(session, kind, selected=()):
        assert kind == "catalog_upstream"
        return list(choices)

    monkeypatch.setattr(dac, "load_choices", _fake_load_choices)
    return _app(fake), fake


def test_collect_gate_admission_exact_path():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # The ONE exact path is ADMITTED (no session -> entry
            # redirect, same law as the index)...
            r = await client.get(CO_URL)
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            # ...and every near-miss / subpath stays default-denied 404.
            for p in (
                CO_URL + "/",                      # trailing slash
                CO_URL + "s",                      # prefix sibling
                CO_URL + "/submit",                # the POST subpath
                CO_URL + "/extra",                 # deeper path
                "/admin/operations/catalogx/collect",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_collect_zero_active_404():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            r = await client.get(CO_URL)
            assert r.status_code == 404

    asyncio.run(run())


def test_collect_unsafe_methods_quiet_noop_body_not_parsed():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            paths = (CO_URL, CO_URL + "/submit", CO_URL + "/export-baseline")
            for p in paths:
                for method in ("POST", "PUT", "PATCH", "DELETE"):
                    # 200 KB garbage body: a 204 proves the body was
                    # never parsed before the cut.
                    r = await client.request(
                        method,
                        p,
                        content=b"x" * 200_000,
                        headers={"content-type": "text/garbage"},
                    )
                    assert r.status_code == 204, (p, method)
                    assert r.content == b""
        async with _client(app) as anon:
            r = await anon.post(
                CO_URL,
                content=b"y" * 200_000,
                headers={"content-type": "text/garbage"},
            )
            assert r.status_code == 404

    asyncio.run(run())


def test_collect_query_law_404_no_db_access(monkeypatch):
    async def run():
        app = _app(FakeFacade())
        demo = _PN_NS(target_db=COPY_OK)

        calls: list = []

        def _refusing_sessionmaker(_req):
            calls.append(_req)
            raise RuntimeError("no copy query before the query law")

        # The demo collect page defines NO query parameters: ANY
        # parameter (including the normal page's `job` value) refuses
        # BEFORE any sessionmaker/copy access.
        monkeypatch.setattr(
            dac, "get_sessionmaker_from_app", _refusing_sessionmaker
        )

        # Missing demo state: defensive 404.
        request = _pn_bare_request(app, {})
        assert (await dac.demo_catalog_collect(request)).status_code == 404
        for query in (
            "job=" + CO_ORIGINAL_RUN_A,
            "job=" + CO_RUN_A,
            "x=1",
            "job=",
        ):
            request = _pn_bare_request(app, {"demo_admin": demo}, query)
            assert (
                await dac.demo_catalog_collect(request)
            ).status_code == 404, query
        # Proven: no refusal path touched the copy seam.
        assert calls == []

    asyncio.run(run())


def test_collect_page_no_sessionmaker_503(monkeypatch):
    async def run():
        app = _app(FakeFacade())
        demo = _PN_NS(target_db=COPY_OK)

        class _RaiseFactory:
            def __call__(self):
                raise RuntimeError("no sessionmaker in demo state")

        monkeypatch.setattr(
            dac, "get_sessionmaker_from_app", lambda _req: _RaiseFactory()
        )
        request = _pn_bare_request(app, {"demo_admin": demo})
        response = await dac.demo_catalog_collect(request)
        assert response.status_code == 503
        assert dac._SAFE_COLLECT_UNAVAILABLE in response.body.decode()

    asyncio.run(run())


def test_collect_preflight_mismatch_503(monkeypatch):
    async def run():
        for db, ro in ((COPY_OK, "off"), ("some_other_db", "on")):
            fake = FakeFacade()
            session = _ArtifactFakeSession(
                meta_rows=[], body_rows=[], db=db, ro=ro
            )
            app, _ = _co_app(fake, monkeypatch, session)
            request = _pn_bare_request(
                app, {"demo_admin": _PN_NS(target_db=COPY_OK)}
            )
            response = await dac.demo_catalog_collect(request)
            assert response.status_code == 503
            assert dac._SAFE_COLLECT_UNAVAILABLE in response.body.decode()
            # The copy recheck happens BEFORE any copy query.
            assert all("demo_display" not in t for t, _p in session.executed)

    asyncio.run(run())


def test_collect_inventory_bound_503_and_limit_param(monkeypatch):
    async def run():
        fake = FakeFacade()
        # 4097 rows (all non-runs, so the bound trips before any
        # per-group law): the bound LIMIT must make the page refuse.
        rows = [
            _pn_leaf(
                f"catalog/jobs/{'a1' * 16}.json", "job_record", b"{}", 1750000000.0
            )
        ] * 4097
        session = _ArtifactFakeSession(
            meta_rows=rows, body_rows=[], db=COPY_OK, ro="on"
        )
        app, _ = _co_app(fake, monkeypatch, session)
        request = _pn_bare_request(
            app, {"demo_admin": _PN_NS(target_db=COPY_OK)}
        )
        response = await dac.demo_catalog_collect(request)
        assert response.status_code == 503
        # The inventory statement carries the BOUND limit parameter.
        inventory = [
            (t, p)
            for t, p in session.executed
            if "demo_display.leaves" in t and not t.lstrip().startswith("SELECT body")
        ]
        assert len(inventory) == 1
        stmt, params = inventory[0]
        assert "LIMIT :limit" in stmt
        assert params == {"limit": dac._MAX_INDEX_ROWS + 1}

    asyncio.run(run())


def test_collect_empty_honest_200(monkeypatch):
    async def run():
        fake = FakeFacade()
        # Only a NON-runs leaf: an honest empty complete-run list.
        session = _ArtifactFakeSession(
            meta_rows=[
                _pn_leaf(
                    f"catalog/jobs/{CAT_JOB_ID}.json",
                    "job_record", b"{}", 1750000001.0,
                )
            ],
            body_rows=[],
            db=COPY_OK,
            ro="on",
        )
        app, _ = _co_app(fake, monkeypatch, session)
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(CO_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            text = _norm(r.text)
            assert "Sanitized demo snapshot display" in text
            assert "ILLUSTRATIVE demo-only form" in text
            assert "submitting has NO effect" in text
            # No FALSE live-availability claim: the normal "shown as
            # available/not configured" wording never renders in demo.
            assert "shown as" not in r.text
            assert "live setup (DATABASE_URL) is NOT available to this demo copy" in text
            assert "research runner is NOT configured or available to this demo copy" in text
            # The familiar form controls render (demo-labeled).
            assert 'name="mode"' in r.text
            assert 'name="providers"' in r.text
            assert 'name="baseline"' in r.text
            assert "gpt-test" in r.text  # copy-backed model choice
            # The NORMAL custody-backed last-job section never renders.
            assert "Last collect job" not in text
            assert "Refresh status" not in text
            # The honest empty complete-run state + no-inference note.
            assert "No captured complete runs in this snapshot" in text
            assert (
                "This does not establish that no collect jobs exist or that live catalog storage is unconfigured"
                in text
            )
            # No copy name or credential echo.
            assert COPY_OK not in r.text

    asyncio.run(run())


def test_collect_positive_page(monkeypatch):
    async def run():
        # Two COMPLETE run groups: A (7 files) newer than B (7 files).
        rows = (
            _co_run_rows(CO_RUN_A, base_captured=1750000100.0)
            + _co_run_rows(CO_RUN_B, base_captured=1750000000.0)
            + [
                _pn_leaf(
                    f"catalog/jobs/{CAT_JOB_ID}.json",
                    "job_record", b"{}", 1750000001.0,
                )
            ]
        )
        fake = FakeFacade()
        session = _ArtifactFakeSession(
            meta_rows=rows, body_rows=[], db=COPY_OK, ro="on"
        )
        app, _ = _co_app(fake, monkeypatch, session)
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(CO_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            text = _norm(r.text)
            assert "Captured complete runs (historical, all acquisition paths)" in r.text
            assert "NOT attributed to this collect form" in text
            assert "100" in text  # the stated bound
            # Both runs link to the EXACT 224-m historical run-detail
            # page (never the original custody).
            for run_id in (CO_RUN_A, CO_RUN_B):
                assert (
                    f'href="/admin/operations/catalog/runs/{run_id}/"' in r.text
                ), run_id
                assert f"<code>{run_id}</code>" in r.text
            # A (newer) is listed BEFORE B.
            assert r.text.index(f'runs/{CO_RUN_A}/') < r.text.index(f'runs/{CO_RUN_B}/')
            # Per-group metadata: seven files, 7 * len(CO_FILE_DATA)
            # bytes, captured UTC stamp.
            assert "7 files" in text
            assert f"{7 * len(CO_FILE_DATA):,}" in text or str(7 * len(CO_FILE_DATA)) in text
            # No original run ID, no copy name, and NO body transfer
            # (only metadata was ever queried).
            assert CO_ORIGINAL_RUN_A not in r.text
            assert CO_ORIGINAL_RUN_B not in r.text
            assert COPY_OK not in r.text
            assert not any(
                t.lstrip().startswith("SELECT body") for t, _p in session.executed
            )

    asyncio.run(run())


def test_collect_partial_run_group_503(monkeypatch):
    async def run():
        for count in (1, 6):  # every partial group is a fixed refusal
            rows = _co_run_rows(CO_RUN_A, base_captured=1750000100.0, count=count)
            fake = FakeFacade()
            session = _ArtifactFakeSession(
                meta_rows=rows, body_rows=[], db=COPY_OK, ro="on"
            )
            app, _ = _co_app(fake, monkeypatch, session)
            async with _client(app) as client:
                _session_cookie(client)
                await _verified_session_client(fake, client)
                r = await client.get(CO_URL)
                assert r.status_code == 503, count
                assert r.headers["cache-control"] == "private, no-store"
                assert dac._SAFE_COLLECT_UNAVAILABLE in _norm(r.text)

    asyncio.run(run())


def test_collect_closed_file_law_corrupt_503(monkeypatch):
    async def run():
        good = _co_run_rows(CO_RUN_A, base_captured=1750000100.0)
        cases = (
            # an unknown top-level file name
            good[:-1]
            + [
                _pn_leaf(
                    f"catalog/runs/{CO_RUN_A}/evil.txt",
                    "route_tsv", CO_FILE_DATA, 1750000100.0 + 6,
                )
            ],
            # a deeper runs path is outside the closed set
            good[:-1]
            + [
                _pn_leaf(
                    f"catalog/runs/{CO_RUN_A}/REVIEW.html/inner",
                    "review_html", CO_FILE_DATA, 1750000100.0 + 6,
                )
            ],
            # kind disagrees with the worker-published file law
            good[:-1]
            + [
                (
                    f"catalog/runs/{CO_RUN_A}/REVIEW.html",
                    "job_record",
                    len(CO_FILE_DATA),
                    hashlib.sha256(CO_FILE_DATA).hexdigest(),
                    1750000100.0 + 6,
                )
            ],
        )
        for rows in cases:
            fake = FakeFacade()
            session = _ArtifactFakeSession(
                meta_rows=rows, body_rows=[], db=COPY_OK, ro="on"
            )
            app, _ = _co_app(fake, monkeypatch, session)
            async with _client(app) as client:
                _session_cookie(client)
                await _verified_session_client(fake, client)
                r = await client.get(CO_URL)
                assert r.status_code == 503, rows[-1][0]

    asyncio.run(run())


def test_collect_group_bound_100(monkeypatch):
    async def run():
        # 101 complete groups: the page lists at most 100, the OLDEST
        # dropped, the bound stated.
        rows: list = []
        for i in range(101):
            run_id = _rd_dsf._demo_run_id(
                CO_SEED, ("%02x" % i) + "0" * 30
            )
            rows.extend(
                _co_run_rows(run_id, base_captured=1740000000.0 + i)
            )
        fake = FakeFacade()
        session = _ArtifactFakeSession(
            meta_rows=rows, body_rows=[], db=COPY_OK, ro="on"
        )
        app, _ = _co_app(fake, monkeypatch, session)
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(CO_URL)
            assert r.status_code == 200
            import re

            links = re.findall(
                r'href="/admin/operations/catalog/runs/(demo-run-[0-9a-f]{24})/"',
                r.text,
            )
            assert len(links) == 100
            # The oldest group (i=0) is the one dropped.
            assert _rd_dsf._demo_run_id(CO_SEED, "00" + "0" * 30) not in links
            assert "100" in _norm(r.text)

    asyncio.run(run())


def test_collect_html_canary_escaped(monkeypatch):
    async def run():
        canary = _PN_NS(
            id="gpt-canary", label="<script>alert(1)</script>", sub="x&y"
        )
        rows = _co_run_rows(CO_RUN_A, base_captured=1750000100.0)
        fake = FakeFacade()
        session = _ArtifactFakeSession(
            meta_rows=rows, body_rows=[], db=COPY_OK, ro="on"
        )
        app, _ = _co_app(fake, monkeypatch, session, choices=(canary,))
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(CO_URL)
            assert r.status_code == 200
            assert "<script>alert(1)</script>" not in r.text
            # The canary survives only as escaped/inert JSON.
            assert "gpt-canary" in r.text

    asyncio.run(run())


def test_index_links_collect_page(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        factory, _made = _display_factory(leaves=[])
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_INDEX_URL)
            assert r.status_code == 200
            assert 'href="/admin/operations/catalog/collect"' in r.text

    asyncio.run(run())


# --- 224-p: demo-only review/export forms + historical job records ------------

P_SEED = b"224p-unit-seed"
P_ORIGINAL_JOB_A = "c9" * 16  # ORIGINAL (never displayed)
P_ORIGINAL_JOB_B = "d9" * 16
P_JOB_A = _rd_dsf._demo_job_id(P_SEED, P_ORIGINAL_JOB_A)  # 32 hex
P_JOB_B = _rd_dsf._demo_job_id(P_SEED, P_ORIGINAL_JOB_B)
P_ORIGINAL_RUN = "e9" * 16  # ORIGINAL run id (never displayed)
P_RUN = _rd_dsf._demo_run_id(P_SEED, P_ORIGINAL_RUN)  # demo-run-<24hex>
P_ORIGINAL_UPLOAD = "bundle-" + "f2" * 16
P_UPLOAD = _rd_dsf._remap_upload_name(P_SEED, P_ORIGINAL_UPLOAD)
P_REVIEW_URL = "/admin/operations/catalog/review"
P_EXPORT_URL = "/admin/operations/catalog/export-baseline"
P_JOBS_URL = "/admin/operations/catalog/jobs/"


def _p_original_record(job_id: str, **kw):
    """A synthetic ORIGINAL custody job record (the 223 sanitizer's
    input); the POSITIVE fixtures are the sanitizer's OWN output."""
    base = {
        "job_id": job_id,
        "family": "review_supplied",
        "status": "ready",
        "progress": "free text never displayed",
        "dispatch": None,
        "run_id": P_ORIGINAL_RUN,
        "artifact_name": P_ORIGINAL_UPLOAD,
        "cancel_requested": False,
        "created_at": "2025-06-15T15:00:00+00:00",
        "updated_at": "2025-06-15T15:06:40+00:00",
    }
    base.update(kw)
    return base


def _p_body(job_id: str = P_ORIGINAL_JOB_A, **kw) -> bytes:
    # The ACTUAL 223 sanitizer output for the synthetic original record.
    return _rd_dsf._sanitize_job_record(
        _rd_json.dumps(_p_original_record(job_id, **kw)).encode(), P_SEED
    )


def _p_run_rows(run_id: str, base_captured: float, count: int = 7):
    """The closed seven worker-published sealed-run content rows for one
    remapped run (metadata-only fixture bodies, never loaded by the
    jobs page)."""
    return [
        _pn_leaf(
            f"catalog/runs/{run_id}/{filename}",
            kind,
            b"{}",
            base_captured + index,
        )
        for index, (filename, kind) in enumerate(dac._RUN_DETAIL_FILES[:count])
    ]


class _PJobFakeSession(_ArtifactFakeSession):
    """The 224-p jobs session: the bounded body query serves ONLY the
    leaf whose logical_name equals the BOUND ``:name`` parameter (a
    real copy never serves another leaf's body). ``bodies`` maps the
    stored logical name to its stored bytes."""

    def __init__(self, meta_rows, bodies, db, ro) -> None:
        super().__init__(meta_rows=meta_rows, body_rows=[], db=db, ro=ro)
        self.bodies = bodies

    async def execute(self, clause, params=None):
        text = str(clause)
        params = dict(params or {})
        self.executed.append((text, params))
        if text.lstrip().startswith("SELECT body"):
            body = self.bodies.get(params.get("name"))
            return _ArtifactResult([(body,)] if body is not None else [])
        return _ArtifactResult(self.meta_rows)


def _p_app(fake, monkeypatch, session):
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    _patch_sessionmaker(monkeypatch, session)
    return _app(fake), fake


def test_p_gate_admission_exact_paths():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # The THREE exact paths are ADMITTED (no session -> entry
            # redirect, same law as the index)...
            for p in (P_REVIEW_URL, P_EXPORT_URL, P_JOBS_URL):
                r = await client.get(p)
                assert r.status_code == 303, p
                assert r.headers["location"] == "/fakeadmin/login"
            # ...and every near miss / subpath stays default-denied.
            for p in (
                P_REVIEW_URL + "/",                  # trailing slash
                P_REVIEW_URL + "s",                  # prefix sibling
                P_REVIEW_URL + "/submit",            # the POST subpath
                P_REVIEW_URL + "/extra",             # deeper path
                P_EXPORT_URL + "/",
                P_EXPORT_URL + "/submit",
                "/admin/operations/catalog/export",  # near sibling
                "/admin/operations/catalog/jobs",    # missing slash
                "/admin/operations/catalog/jobs/extra",
                "/admin/operations/catalog/jobs/" + "a" * 32,
                "/admin/operations/catalogx/review",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_p_zero_active_404():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            for p in (P_REVIEW_URL, P_EXPORT_URL, P_JOBS_URL):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_p_unsafe_methods_quiet_noop_body_not_parsed():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            paths = (
                P_REVIEW_URL,
                P_REVIEW_URL + "/submit",
                P_EXPORT_URL,
                P_EXPORT_URL + "/submit",
                P_JOBS_URL,
                P_JOBS_URL + "a" * 32 + "/cancel",
                P_JOBS_URL + "a" * 32 + "/remove",
                P_JOBS_URL + "a" * 32 + "/artifact/x",
            )
            for p in paths:
                for method in ("POST", "PUT", "PATCH", "DELETE"):
                    # 200 KB garbage body: a 204 proves the body was
                    # never parsed before the cut.
                    r = await client.request(
                        method,
                        p,
                        content=b"x" * 200_000,
                        headers={"content-type": "text/garbage"},
                    )
                    assert r.status_code == 204, (p, method)
                    assert r.content == b""
        async with _client(app) as anon:
            r = await anon.post(
                P_JOBS_URL,
                content=b"y" * 200_000,
                headers={"content-type": "text/garbage"},
            )
            assert r.status_code == 404

    asyncio.run(run())


def test_p_review_export_query_law_404_no_copy_access(monkeypatch):
    async def run():
        app = _app(FakeFacade())
        demo = _PN_NS(target_db=COPY_OK)

        calls: list = []

        def _refusing_sessionmaker(_req):
            calls.append(_req)
            raise RuntimeError("no copy query before the query law")

        monkeypatch.setattr(
            dac, "get_sessionmaker_from_app", _refusing_sessionmaker
        )
        for handler, url in (
            (dac.demo_catalog_review, P_REVIEW_URL),
            (dac.demo_catalog_export, P_EXPORT_URL),
        ):
            # Missing demo state: defensive 404.
            request = _pn_bare_request(app, {})
            assert (await handler(request)).status_code == 404, url
            # Review/export define NO query parameters: ANY
            # parameter (including a `job` value) refuses BEFORE any
            # sessionmaker/copy access.
            for query in ("job=" + P_JOB_A, "x=1", "job="):
                request = _pn_bare_request(
                    app, {"demo_admin": demo}, query
                )
                assert (await handler(request)).status_code == 404, (url, query)
        # Proven: no refusal path touched the copy seam.
        assert calls == []

    asyncio.run(run())


def test_p_jobs_query_law_refusals_404(monkeypatch):
    async def run():
        app = _app(FakeFacade())
        demo = _PN_NS(target_db=COPY_OK)

        calls: list = []

        def _refusing_sessionmaker(_req):
            calls.append(_req)
            raise RuntimeError("no copy query before the query law")

        monkeypatch.setattr(
            dac, "get_sessionmaker_from_app", _refusing_sessionmaker
        )
        # Missing demo state: defensive 404.
        request = _pn_bare_request(app, {})
        assert (await dac.demo_catalog_jobs(request)).status_code == 404
        # Every structurally invalid selector refuses BEFORE any
        # sessionmaker/copy access.
        for query in (
            "job=" + P_JOB_A + "&job=" + P_JOB_B,  # duplicate param
            "job=" + P_JOB_A + "&x=1",             # extra param
            "x=1",                                 # unknown param
            "job=",                                # empty value
            "job=" + "a1" * 15,                    # wrong length (30)
            "job=" + "a1" * 16 + "a1",             # wrong length (34)
            "job=" + "A1" * 16,                    # uppercase hex
            "job=" + "g1" * 16,                    # non-hex char
            "job=" + "a1" * 300,                   # overlong
        ):
            request = _pn_bare_request(app, {"demo_admin": demo}, query)
            assert (
                await dac.demo_catalog_jobs(request)
            ).status_code == 404, query
        # Proven: no structurally invalid path touched the copy seam.
        assert calls == []
        # A structurally valid but UNKNOWN canonical id is a fixed 404
        # AFTER the bounded inventory, with NO body transfer and no
        # fallback to another record.
        body_a = _p_body()
        session = _PJobFakeSession(
            meta_rows=[
                _pn_leaf(
                    f"catalog/jobs/{P_JOB_A}.json", "job_record", body_a,
                    1750000200.0,
                ),
            ],
            bodies={f"catalog/jobs/{P_JOB_A}.json": body_a},
            db=COPY_OK,
            ro="on",
        )
        _p_app(FakeFacade(), monkeypatch, session)
        request = _pn_bare_request(
            app, {"demo_admin": demo}, "job=" + "f1" * 16
        )
        response = await dac.demo_catalog_jobs(request)
        assert response.status_code == 404
        assert "f1" * 16 not in response.body.decode()
        assert not any(
            t.lstrip().startswith("SELECT body") for t, _p in session.executed
        )

    asyncio.run(run())


def test_p_no_sessionmaker_503(monkeypatch):
    async def run():
        app = _app(FakeFacade())
        demo = _PN_NS(target_db=COPY_OK)

        class _RaiseFactory:
            def __call__(self):
                raise RuntimeError("no sessionmaker in demo state")

        monkeypatch.setattr(
            dac, "get_sessionmaker_from_app", lambda _req: _RaiseFactory()
        )
        for handler, message in (
            (dac.demo_catalog_review, dac._SAFE_REVIEW_UNAVAILABLE),
            (dac.demo_catalog_export, dac._SAFE_EXPORT_UNAVAILABLE),
            (dac.demo_catalog_jobs, dac._SAFE_JOBS_UNAVAILABLE),
        ):
            request = _pn_bare_request(app, {"demo_admin": demo})
            response = await handler(request)
            assert response.status_code == 503
            assert message in response.body.decode()

    asyncio.run(run())


def test_p_preflight_mismatch_503(monkeypatch):
    async def run():
        for db, ro in ((COPY_OK, "off"), ("some_other_db", "on")):
            for handler, message in (
                (dac.demo_catalog_review, dac._SAFE_REVIEW_UNAVAILABLE),
                (dac.demo_catalog_export, dac._SAFE_EXPORT_UNAVAILABLE),
                (dac.demo_catalog_jobs, dac._SAFE_JOBS_UNAVAILABLE),
            ):
                fake = FakeFacade()
                session = _PJobFakeSession(
                    meta_rows=[], bodies={}, db=db, ro=ro
                )
                _p_app(fake, monkeypatch, session)
                request = _pn_bare_request(
                    _app(FakeFacade()),
                    {"demo_admin": _PN_NS(target_db=COPY_OK)},
                )
                response = await handler(request)
                assert response.status_code == 503
                assert message in response.body.decode()
                # The binding recheck happens BEFORE any copy query.
                assert not session.executed

    asyncio.run(run())


def test_p_jobs_inventory_bound_503_and_limit_param(monkeypatch):
    async def run():
        fake = FakeFacade()
        # 4097 distinct job rows: the bound LIMIT must make the page
        # refuse before any selection or body transfer.
        rows = [
            _pn_leaf(
                f"catalog/jobs/{('%08x' % i) * 4}.json",
                "job_record",
                b"{}",
                1750000000.0 + i,
            )
            for i in range(4097)
        ]
        session = _PJobFakeSession(
            meta_rows=rows, bodies={}, db=COPY_OK, ro="on"
        )
        _p_app(fake, monkeypatch, session)
        app = _app(FakeFacade())
        request = _pn_bare_request(
            app, {"demo_admin": _PN_NS(target_db=COPY_OK)}
        )
        response = await dac.demo_catalog_jobs(request)
        assert response.status_code == 503
        # The inventory statement carries the BOUND limit parameter.
        inventory = [
            (t, p)
            for t, p in session.executed
            if "demo_display.leaves" in t
            and not t.lstrip().startswith("SELECT body")
        ]
        assert len(inventory) == 1
        stmt, params = inventory[0]
        assert "LIMIT :limit" in stmt
        assert params == {"limit": dac._MAX_INDEX_ROWS + 1}
        assert not any(
            t.lstrip().startswith("SELECT body") for t, _p in session.executed
        )

    asyncio.run(run())


def test_p_jobs_empty_honest_200(monkeypatch):
    async def run():
        fake = FakeFacade()
        # Only NON-jobs leaves: an honest empty job-record list.
        session = _PJobFakeSession(
            meta_rows=[
                _pn_leaf(
                    f"catalog/proposals/{P_JOB_B}/warnings.json",
                    "warnings_json",
                    b"{}",
                    1750000000.0,
                ),
                _pn_leaf(
                    "branding/logo.svg", "profile_asset", b"{}", 1750000001.0
                ),
            ],
            bodies={},
            db=COPY_OK,
            ro="on",
        )
        _p_app(fake, monkeypatch, session)
        async with _client(_app(fake)) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(P_JOBS_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            text = _norm(r.text)
            assert "Captured job records (historical, all job families)" in text
            assert "frozen at capture time" in text
            assert "No captured job records in this snapshot" in text
            assert (
                "This does not establish that live catalog storage was "
                "unconfigured or that no job ran"
            ) in text
            # No copy name echo and NO body transfer (only the bounded
            # metadata inventory was ever queried).
            assert COPY_OK not in r.text
            assert not any(
                t.lstrip().startswith("SELECT body") for t, _p in session.executed
            )

    asyncio.run(run())


def _p_positive_fixture():
    """Two captured job records (A newer than B): A carries a remapped
    run reference (its seven sealed-run content leaves captured) and a
    remapped upload reference (its upload leaf captured); B has no
    references. Bodies are the ACTUAL 223 sanitizer output for the
    synthetic original records."""
    body_a = _p_body()
    body_b = _p_body(
        P_ORIGINAL_JOB_B,
        family="collect",
        status="failed",
        run_id=None,
        artifact_name=None,
    )
    rows = (
        [
            _pn_leaf(
                f"catalog/jobs/{P_JOB_A}.json", "job_record", body_a,
                1750000200.0,
            ),
            _pn_leaf(
                f"catalog/jobs/{P_JOB_B}.json", "job_record", body_b,
                1750000100.0,
            ),
            _pn_leaf(
                f"catalog/uploads/{P_JOB_A}/{P_UPLOAD}",
                "refresh_bundle",
                b"{}",
                1750000150.0,
            ),
        ]
        + _p_run_rows(P_RUN, base_captured=1750000000.0)
        + [
            _pn_leaf(
                f"catalog/proposals/{P_JOB_B}/warnings.json",
                "warnings_json",
                b"{}",
                1750000001.0,
            )
        ]
    )
    bodies = {
        f"catalog/jobs/{P_JOB_A}.json": body_a,
        f"catalog/jobs/{P_JOB_B}.json": body_b,
    }
    return rows, bodies


def test_p_jobs_positive_page(monkeypatch):
    async def run():
        fake = FakeFacade()
        rows, bodies = _p_positive_fixture()
        session = _PJobFakeSession(
            meta_rows=rows, bodies=bodies, db=COPY_OK, ro="on"
        )
        _p_app(fake, monkeypatch, session)
        async with _client(_app(fake)) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(P_JOBS_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            text = _norm(r.text)
            assert "2 shown" in text  # honest count (bound 100 stated)
            assert "at most the 100 most-recently-captured records" in text
            # A (newer) is listed BEFORE B and selected by default.
            assert r.text.index(f">{P_JOB_A}<") < r.text.index(f">{P_JOB_B}<")
            # The sanitized, typed HISTORICAL fields of A render.
            assert ">review_supplied<" in r.text
            assert ">ready<" in r.text
            assert "2025-06-15T15:00:00+00:00" in r.text
            assert "2025-06-15T15:06:40+00:00" in r.text
            # The typed NEUTRAL progress value renders (empty in the
            # sanitized shape -> the fixed neutralized marker).
            assert "Progress (sanitized)" in text
            assert "no progress detail in this sanitized copy" in text
            assert "none (fixed in this sanitized shape)" in r.text
            assert "free text never displayed" not in r.text  # neutralized
            # The VERIFIED references are linked to the exact 224-m
            # run-detail page and the 224-l forced download (never the
            # original custody).
            assert (
                f'href="/admin/operations/catalog/runs/{P_RUN}/"' in r.text
            )
            assert (
                f'href="/admin/operations/catalog/artifact'
                f'?name=catalog/uploads/{P_JOB_A}/{P_UPLOAD}"'
            ) in r.text
            # No original ID, no copy name.
            assert P_ORIGINAL_JOB_A not in r.text
            assert P_ORIGINAL_JOB_B not in r.text
            assert P_ORIGINAL_RUN not in r.text
            assert P_ORIGINAL_UPLOAD not in r.text
            assert COPY_OK not in r.text
            # The bounded body query ran EXACTLY once (only the
            # selected record) with the BOUND 1 MiB cap, exact name,
            # size and digest re-asserts.
            body_stmts = [
                (t, p)
                for t, p in session.executed
                if t.lstrip().startswith("SELECT body")
            ]
            assert len(body_stmts) == 1
            _stmt, params = body_stmts[0]
            assert params["name"] == f"catalog/jobs/{P_JOB_A}.json"
            assert params["cap"] == dac._JOB_RECORD_BYTES
            assert params["kind"] == "job_record"
            assert params["size"] == len(bodies[f"catalog/jobs/{P_JOB_A}.json"])
            assert (
                params["digest"]
                == hashlib.sha256(bodies[f"catalog/jobs/{P_JOB_A}.json"]).hexdigest()
            )
            # Explicit selection of the OLDER record (B, no
            # references).
            r = await client.get(P_JOBS_URL + "?job=" + P_JOB_B)
            assert r.status_code == 200
            text = _norm(r.text)
            assert ">collect<" in text
            assert ">failed<" in text
            assert f'value="{P_JOB_A}" selected' not in r.text
            assert "Run reference:" not in text
            assert "Upload reference:" not in text
            # Unknown canonical job: fixed 404, no fallback.
            r = await client.get(P_JOBS_URL + "?job=" + "e1" * 16)
            assert r.status_code == 404
            assert P_JOB_A not in r.text
            assert P_JOB_B not in r.text
            # Duplicate / extra query parameters: fixed 404.
            r = await client.get(P_JOBS_URL + "?job=" + P_JOB_B + "&job=" + P_JOB_B)
            assert r.status_code == 404
            r = await client.get(P_JOBS_URL + "?x=1")
            assert r.status_code == 404

    asyncio.run(run())


def test_p_jobs_unverified_references_plain_text(monkeypatch):
    async def run():
        # A's run reference has only SIX of the seven content leaves
        # and its upload leaf is absent: both render as PLAIN TEXT
        # (not linked) - and a partial run group is NOT a jobs-area
        # corruption, so the page still renders (200).
        body_a = _p_body()
        rows = (
            [
                _pn_leaf(
                    f"catalog/jobs/{P_JOB_A}.json", "job_record", body_a,
                    1750000200.0,
                )
            ]
            + _p_run_rows(P_RUN, base_captured=1750000000.0, count=6)
        )
        fake = FakeFacade()
        session = _PJobFakeSession(
            meta_rows=rows, bodies={f"catalog/jobs/{P_JOB_A}.json": body_a},
            db=COPY_OK,
            ro="on",
        )
        _p_app(fake, monkeypatch, session)
        async with _client(_app(fake)) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(P_JOBS_URL)
            assert r.status_code == 200
            text = _norm(r.text)
            assert f"<code>{P_RUN}</code>" in r.text
            assert f"runs/{P_RUN}/\"" not in r.text  # never linked
            assert "its captured run is not fully present in this copy" in text
            assert f"<code>{P_UPLOAD}</code>" in r.text
            assert "artifact?name=" not in r.text  # never linked
            assert "its captured upload is not present in this copy" in text

    asyncio.run(run())


def test_p_jobs_metadata_law_503(monkeypatch):
    async def run():
        body_a = _p_body()
        good_name = f"catalog/jobs/{P_JOB_A}.json"
        cases = {
            "wrong kind": [
                _pn_leaf(good_name, "job_records", body_a, 1750000200.0)
            ],
            "over 1 MiB": [
                _pn_leaf(
                    good_name, "job_record", b"x" * (1024 * 1024 + 1),
                    1750000200.0,
                )
            ],
            "noncanonical sha": [
                (good_name, "job_record", len(body_a), "g" * 64, 1750000200.0)
            ],
            "duplicate record": [
                _pn_leaf(good_name, "job_record", body_a, 1750000200.0),
                _pn_leaf(good_name, "job_record", body_a, 1750000201.0),
            ],
            "unknown jobs-area shape": [
                _pn_leaf(
                    "catalog/jobs/notahex.json", "job_record", b"{}",
                    1750000200.0,
                )
            ],
            "deeper jobs path": [
                _pn_leaf(
                    f"catalog/jobs/{P_JOB_A}.json/extra",
                    "job_record",
                    b"{}",
                    1750000200.0,
                )
            ],
            "non-finite capture": [
                (
                    good_name,
                    "job_record",
                    len(body_a),
                    hashlib.sha256(body_a).hexdigest(),
                    float("inf"),
                )
            ],
        }
        for label, rows in cases.items():
            fake = FakeFacade()
            session = _PJobFakeSession(
                meta_rows=rows, bodies={good_name: body_a},
                db=COPY_OK,
                ro="on",
            )
            _p_app(fake, monkeypatch, session)
            app = _app(FakeFacade())
            request = _pn_bare_request(
                app, {"demo_admin": _PN_NS(target_db=COPY_OK)}
            )
            response = await dac.demo_catalog_jobs(request)
            assert response.status_code == 503, label
            assert (
                dac._SAFE_JOBS_UNAVAILABLE in response.body.decode()
            ), label
            # Fixed safe refusal: nothing from the corrupt row echoes.
            assert "g" * 64 not in response.body.decode(), label
            assert "notahex" not in response.body.decode(), label

    asyncio.run(run())
def test_p_jobs_bound_100(monkeypatch):
    async def run():
        # 101 captured records (100 fillers + the sanitizer-remapped
        # newest record P_JOB_A): exactly 100 render, the OLDEST
        # filler is dropped.
        body_a = _p_body()
        rows = [
            _pn_leaf(
                f"catalog/jobs/{('%08x' % i) * 4}.json", "job_record", b"{}",
                1750000000.0 + i,
            )
            for i in range(1, 101)
        ]
        rows.append(
            _pn_leaf(
                f"catalog/jobs/{P_JOB_A}.json", "job_record", body_a,
                1750000101.0,  # newest: the default selection
            )
        )
        oldest_id = ("00000001" * 4)  # filler i=1, the oldest
        fake = FakeFacade()
        session = _PJobFakeSession(
            meta_rows=rows,
            bodies={f"catalog/jobs/{P_JOB_A}.json": body_a},
            db=COPY_OK,
            ro="on",
        )
        _p_app(fake, monkeypatch, session)
        async with _client(_app(fake)) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(P_JOBS_URL)
            assert r.status_code == 200
            text = _norm(r.text)
            assert "100 shown" in text
            assert oldest_id not in r.text  # oldest dropped
            assert f'>{P_JOB_A}<' in r.text

    asyncio.run(run())
def test_p_jobs_body_mismatch_503(monkeypatch):
    async def run():
        good_name = f"catalog/jobs/{P_JOB_A}.json"
        body_a = _p_body()
        meta_a = _pn_leaf(good_name, "job_record", body_a, 1750000200.0)
        # A typed record with an unknown family vocabulary: its
        # metadata is self-consistent, so the bounded fetch SUCCEEDS
        # and the 223 typed re-proof itself must refuse it.
        unknown_family = _rd_json.dumps(
            {
                "schema_version": "demo-display-1",
                "kind": "catalog_job_record",
                "job_id": P_JOB_A,
                "family": "unknown_family",
                "status": "ready",
                "progress": "",
                "dispatch": None,
                "run_id": None,
                "artifact_name": None,
                "error_code": None,
                "cancel_requested": False,
                "created_at": "2025-06-15T15:00:00+00:00",
                "updated_at": "2025-06-15T15:06:40+00:00",
            }
        ).encode()
        cases = {
            # Stored body no longer matches the stored SHA/size.
            "sha/size mismatch": (meta_a, b"corrupted"),
            # The stored record belongs to ANOTHER job id (its size/
            # SHA also differ from A's stored metadata: the digest
            # re-proof refuses before the job-id law is even reached).
            "foreign job id": (
                meta_a,
                _p_body(P_ORIGINAL_JOB_B, run_id=None, artifact_name=None),
            ),
            # Typed re-proof refusal at the validator layer.
            "unknown family": (
                _pn_leaf(good_name, "job_record", unknown_family, 1750000200.0),
                unknown_family,
            ),
            # No stored body at all (absent row).
            "absent row": (meta_a, None),
        }
        for label, (meta, stored) in cases.items():
            fake = FakeFacade()
            session = _PJobFakeSession(
                meta_rows=[meta],
                bodies={good_name: stored} if stored is not None else {},
                db=COPY_OK,
                ro="on",
            )
            _p_app(fake, monkeypatch, session)
            app = _app(FakeFacade())
            request = _pn_bare_request(
                app, {"demo_admin": _PN_NS(target_db=COPY_OK)}
            )
            response = await dac.demo_catalog_jobs(request)
            assert response.status_code == 503, label
            body = response.body.decode()
            assert dac._SAFE_JOBS_UNAVAILABLE in body, label
            # No raw echo of the stored (corrupt) body or record.
            if stored is not None:
                assert stored.decode("utf-8", "ignore") not in body, label
            assert P_ORIGINAL_JOB_B not in body, label

    asyncio.run(run())
def test_p_review_page_200_illustrative(monkeypatch):
    async def run():
        fake = FakeFacade()
        session = _PJobFakeSession(
            meta_rows=[], bodies={}, db=COPY_OK, ro="on"
        )
        _p_app(fake, monkeypatch, session)
        async with _client(_app(fake)) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(P_REVIEW_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            text = _norm(r.text)
            assert "ILLUSTRATIVE demo-only form" in text
            assert "no bundle is sealed or reviewed" in text
            assert "NOT available to this copy" in text
            # The baseline help carries the NARROW demo wording: the
            # illustrative control reads no live DATABASE_URL, and the
            # normal "used lazily" wording never renders in demo.
            assert "no live DATABASE_URL is read" in text
            assert "used lazily" not in r.text
            # The familiar form controls render (demo-labeled).
            assert 'name="bundle"' in r.text
            assert 'name="baseline"' in r.text
            assert 'id="review-first-install"' in r.text
            # The form links the captured historical job-record page.
            assert f'href="{P_JOBS_URL}"' in r.text
            # The NORMAL custody-backed last-job section and its links
            # never render; no job status is claimed.
            assert "Last review job" not in text
            assert "Refresh status" not in text
            assert "Job status unavailable" not in text
            # No copy name echo; NO copy query ran (the read-only
            # transaction carried the binding recheck scalars only).
            assert COPY_OK not in r.text
            assert session.executed == []

    asyncio.run(run())


def test_p_export_page_200_illustrative(monkeypatch):
    async def run():
        fake = FakeFacade()
        session = _PJobFakeSession(
            meta_rows=[], bodies={}, db=COPY_OK, ro="on"
        )
        _p_app(fake, monkeypatch, session)
        async with _client(_app(fake)) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(P_EXPORT_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            text = _norm(r.text)
            assert "ILLUSTRATIVE demo-only form" in text
            assert "no baseline is exported" in text
            assert "Export baseline" in text  # the familiar action
            # NO live-configuration claim: the normal "Database
            # target: configured/not configured" wording never
            # renders in demo.
            assert "Database target" not in r.text
            assert "not configured" not in r.text
            assert "Live setup (DATABASE_URL) is NOT available to this demo copy" in text
            # The form links the captured historical job-record page.
            assert f'href="{P_JOBS_URL}"' in r.text
            # The NORMAL custody-backed last-job section never renders.
            assert "Last export job" not in text
            assert COPY_OK not in r.text
            assert session.executed == []

    asyncio.run(run())


def test_index_links_224p_pages(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        factory, _made = _display_factory(leaves=[])
        app = _app(fake, display_reader_factory=factory)
        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)
            r = await client.get(CATALOG_INDEX_URL)
            assert r.status_code == 200
            assert f'href="{P_REVIEW_URL}"' in r.text
            assert f'href="{P_EXPORT_URL}"' in r.text
            assert f'href="{P_JOBS_URL}"' in r.text

    asyncio.run(run())


# --- 224-q: demo key read pages (gate admission + query law) ---------------

Q_CAL_URL = f"/admin/keys/{KEY_UUID}/calibration"
Q_CLONE_URL = f"/admin/keys/{KEY_UUID}/clone"
Q_RCPT_URL = f"/admin/keys/{KEY_UUID}/clone/receipts"
Q_OP = "12345678-9abc-4def-8123-456789abcdef"


def test_q_gate_admission_exact_paths():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # The THREE exact read-page shapes are ADMITTED (no session
            # -> demo entry redirect, the same law as the other
            # admitted GETs)...
            for p in (Q_CAL_URL, Q_CLONE_URL, Q_RCPT_URL):
                r = await client.get(p)
                assert r.status_code == 303, p
                assert r.headers["location"] == "/fakeadmin/login"
            # ...and every malformed/near-miss shape stays default-
            # denied BEFORE routing: bad IDs, extra/missing segments,
            # trailing slashes, and every
            # submit/apply/preview/retry POST subpath. The two 224-w
            # JSON attachment GETs (calibration/summary.json and
            # configuration.json) are admitted; proven in the 224-w
            # tests.
            for p in (
                f"/admin/keys/{KEY_UUID.upper()}/calibration",
                "/admin/keys/0123456789abcdef0123456789abcdef/calibration",
                f"/admin/keys/urn:uuid:{KEY_UUID}/clone",
                f"/admin/keys/{KEY_UUID}/calibrations",
                f"/admin/keys/{KEY_UUID}/clones",
                f"/admin/keys/{KEY_UUID}/calibration/",
                f"/admin/keys/{KEY_UUID}/calibration/extra",
                f"/admin/keys/{KEY_UUID}/calibration/preview",
                f"/admin/keys/{KEY_UUID}/calibration/create-template",
                f"/admin/keys/{KEY_UUID}/clone/",
                f"/admin/keys/{KEY_UUID}/clone/review",
                f"/admin/keys/{KEY_UUID}/clone/apply",
                f"/admin/keys/{KEY_UUID}/clone/receipts/",
                f"/admin/keys/{KEY_UUID}/clone/receipts/extra",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_q_gate_query_law_through_asgi(monkeypatch):
    """The receipts page's bounded `operation` law, through ASGI.

    With a VERIFIED session: a gate-refused query is the gate's own
    fixed JSON 404 BEFORE routing; an admitted query passes the gate
    (session resolution + preflight) into the REAL handler, proven by
    the handler-rendered page (here a controlled not-found page: the
    key-detail seam reports the copied key missing). Positive
    rendering is covered by the template units and the owned-PG
    transport test.
    """
    from contextlib import asynccontextmanager as _q_acm

    import slaif_gateway.api.admin_key_clone as _q_akc
    from slaif_gateway.services.admin_key_dashboard import (
        AdminKeyNotFoundError as _Q_AdminKeyNotFoundError,
    )

    @_q_acm
    async def _q_missing_key_scope(_request):
        class _Service:
            async def get_key_detail(self, _key_id):
                raise _Q_AdminKeyNotFoundError()

        yield _Service()

    monkeypatch.setattr(
        _q_akc, "_admin_key_dashboard_service_scope", _q_missing_key_scope
    )

    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        app = _app(fake)

        async def _raw_get(path: str, query: bytes):
            """One raw ASGI GET: the query string is the EXACT bytes
            (httpx would normalize a bare ``?`` away, so the gate's
            byte law is proven here directly)."""
            scope = {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "https",
                "path": path,
                "raw_path": path.encode("ascii"),
                "query_string": query,
                "headers": [(b"host", b"demo.test")],
                "client": ("127.0.0.1", 12345),
                "server": ("demo.test", 443),
                "app": app,
                "state": {},
            }
            status = None
            chunks: list[bytes] = []

            async def _receive():
                return {
                    "type": "http.request",
                    "body": b"",
                    "more_body": False,
                }

            async def _send(message):
                nonlocal status
                if message["type"] == "http.response.start":
                    status = message["status"]
                elif message["type"] == "http.response.body":
                    chunks.append(message.get("body") or b"")

            await app(scope, _receive, _send)
            assert status is not None
            return status, b"".join(chunks)

        async with _client(app) as client:
            _session_cookie(client)
            await _verified_session_client(fake, client)

            def _gate_refused(status, body, label):
                assert status == 404, label
                # The gate's own fixed 404 (JSON), never a handler page.
                assert b"Gateway key not found" not in body, label

            def _gate_admitted(status, body, label):
                # The REAL handler ran (gate session + preflight
                # passed): its controlled not-found page, not the
                # gate's JSON 404.
                assert status == 404, label
                assert b"Gateway key not found" in body, label

            # calibration/clone define NO query parameters: ANY
            # nonempty query is refused (404), including the receipts
            # selector.
            for base in (Q_CAL_URL, Q_CLONE_URL):
                for q in ("?x=1", "?operation=" + Q_OP, "?x="):
                    r = await client.get(base + q)
                    _gate_refused(r.status_code, r.content, (base, q))
            # The raw byte form httpx would normalize away (a bare
            # ``?`` = nonempty query string): still refused.
            for base in (Q_CAL_URL, Q_RCPT_URL):
                status, body = await _raw_get(base, b"?")
                _gate_refused(status, body, (base, b"?"))
            # receipts: zero parameters or exactly ONE `operation`
            # pair is admitted (the empty value = the help page, the
            # existing normal-form semantics).
            for q in ("", "?operation=" + Q_OP, "?operation="):
                r = await client.get(Q_RCPT_URL + q)
                _gate_admitted(r.status_code, r.content, q)
            # Duplicate, extra or unknown parameters refuse.
            for q in (
                "?operation=" + Q_OP + "&operation=" + Q_OP,
                "?operation=" + Q_OP + "&x=1",
                "?x=1",
            ):
                r = await client.get(Q_RCPT_URL + q)
                _gate_refused(r.status_code, r.content, q)
            # An overlong value (65 > 64) refuses...
            r = await client.get(Q_RCPT_URL + "?operation=" + "a" * 65)
            _gate_refused(r.status_code, r.content, "overlong value")
            # ...and an oversized WHOLE query (beyond the 72-byte raw
            # ceiling) refuses before any split/parse.
            r = await client.get(Q_RCPT_URL + "?operation=" + "a" * 70)
            _gate_refused(r.status_code, r.content, "oversized query")
            r = await client.get(Q_RCPT_URL + "?" + "x" * 200)
            _gate_refused(r.status_code, r.content, "gibberish oversized")

    asyncio.run(run())


def test_q_unsafe_methods_quiet_noop_body_not_parsed():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            paths = (
                Q_CAL_URL,
                Q_CAL_URL + "/preview",
                Q_CAL_URL + "/summary.json",
                Q_CAL_URL + "/create-template",
                Q_CLONE_URL,
                Q_CLONE_URL + "/review",
                Q_CLONE_URL + "/apply",
                Q_RCPT_URL,
            )
            for p in paths:
                for method in ("POST", "PUT", "PATCH", "DELETE"):
                    # 200 KB garbage body: a 204 proves the body was
                    # never parsed before the cut.
                    r = await client.request(
                        method,
                        p,
                        content=b"x" * 200_000,
                        headers={"content-type": "text/garbage"},
                    )
                    assert r.status_code == 204, (p, method)
                    assert r.content == b""
        async with _client(app) as anon:
            for p in (Q_CAL_URL, Q_CLONE_URL, Q_RCPT_URL):
                r = await anon.post(
                    p,
                    content=b"y" * 200_000,
                    headers={"content-type": "text/garbage"},
                )
                assert r.status_code == 404, p

    asyncio.run(run())


def test_q_zero_active_404():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            for p in (Q_CAL_URL, Q_CLONE_URL, Q_RCPT_URL):
                r = await client.get(p)
                assert r.status_code == 404, p
            r = await client.post(
                Q_RCPT_URL,
                content=b"z" * 100,
                headers={"content-type": "text/garbage"},
            )
            assert r.status_code == 404

    asyncio.run(run())


# --- 224-t: Operations index + captured process configuration ---------------

import hashlib as _t_hashlib  # noqa: E402
import json as _t_json  # noqa: E402
import re as _t_re  # noqa: E402

from slaif_gateway.api import demo_admin_operations as dao  # noqa: E402
from slaif_gateway.config import Settings as _t_Settings  # noqa: E402
from slaif_gateway.services import demo_snapshot_files as _t_dsf  # noqa: E402
from slaif_gateway.services.configuration_inspection import (  # noqa: E402
    CONFIG_INSPECTION_ALLOWLIST as _T_ALLOWLIST,
)

T_IDX_URL = "/admin/operations/"
T_PC_URL = "/admin/operations/process-configuration"
_T_CAPTURED_AT = 1_763_000_000.0  # finite, representable capture time


def _t_settings_doc(**overrides: object) -> dict[str, object]:
    s = _t_Settings(**overrides)
    return {
        "schema": _t_dsf.DEMO_SCHEMA_VERSION,
        "kind": _t_dsf.KIND_PROCESS_CONFIG,
        "schema_version": 1,
        "settings": {
            name: {
                "value": getattr(s, name),
                "source": (
                    "configured" if name in s.model_fields_set else "default"
                ),
            }
            for name in sorted(_T_ALLOWLIST)
        },
    }


def _t_canonical_body(**overrides: object) -> bytes:
    """The canonical display document the worker sanitizer emits."""
    return _t_dsf._dump(_t_settings_doc(**overrides))


class _ProcConfigFakeSession:
    """One fake request-local copy session: preflight scalars plus the
    recorded parameterized statements (metadata with octet_length,
    then the bounded body query)."""

    def __init__(self, meta_rows, body_rows, db, ro) -> None:
        self.meta_rows = meta_rows
        self.body_rows = body_rows
        self.db = db
        self.ro = ro
        self.executed: list[tuple[str, dict]] = []

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def scalar(self, clause):
        text = str(clause)
        if "current_database" in text:
            return self.db
        return self.ro

    async def execute(self, clause, params=None):
        text = str(clause)
        params = dict(params or {})
        self.executed.append((text, params))
        if "octet_length(body) AS actual_bytes" in text:
            return _ArtifactResult(self.meta_rows)
        if text.lstrip().startswith("SELECT body"):
            return _ArtifactResult(self.body_rows)
        return _ArtifactResult([])


def _t_meta_row(body: bytes, *, kind=None, size=None, sha=None,
                actual=None, captured=_T_CAPTURED_AT) -> tuple:
    if body is None:
        body = _t_canonical_body()
    if size is None:
        size = len(body)
    if actual is None:
        actual = len(body)
    if sha is None:
        sha = _t_hashlib.sha256(body).hexdigest()
    if kind is None:
        kind = _t_dsf.KIND_PROCESS_CONFIG
    return (kind, size, sha, captured, actual)


def _t_patch_sessionmaker(monkeypatch, session):
    monkeypatch.setattr(
        dao, "get_sessionmaker_from_app", lambda _req: lambda: session
    )


def test_t_gate_admission_exact_paths():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # The two EXACT paths are admitted (no session -> entry
            # redirect, same law as the other admitted GETs)...
            r = await client.get(T_IDX_URL)
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            r = await client.get(T_PC_URL)
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            # ...and every near miss, alternate slash shape and unknown
            # query stays default-denied 404.
            for p in (
                "/admin/operations",            # missing required slash
                "/admin/operations//",          # double slash
                "/admin/operations/x",          # unknown first segment
                # 224-v: /admin/operations/diagnostics and
                # /admin/operations/replay-maintenance/ are now
                # ADMITTED (proven in the 224-v tests); only these
                # deeper/alternate shapes stay denied here.
                "/admin/operations/diagnostics/",
                "/admin/operations/diagnostics/lookup",
                # 224-u: /admin/operations/compatibility/ is now
                # ADMITTED (proven in the 224-u tests); its near
                # misses stay denied there.
                "/admin/operations/compatibility",
                "/admin/operations/compatibility//",
                "/admin/operations/replay-maintenance",
                T_PC_URL + "/",                 # trailing slash
                T_PC_URL + "x",                 # prefix sibling
                T_PC_URL + "/extra",            # deeper path
                "/admin/operationsx/process-configuration",
                T_IDX_URL + "?x=1",             # query on the index
                T_IDX_URL + "?a=1&b=2",
                T_PC_URL + "?x=1",              # query on the page
                T_PC_URL + "?x=1&y=2",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_t_gate_zero_active_404():
    async def run():
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            for p in (T_IDX_URL, T_PC_URL):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_t_unsafe_methods_quiet_noop_body_not_parsed():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                for p in (T_IDX_URL, T_PC_URL):
                    r = await client.request(
                        method,
                        p,
                        content=b"x" * 200_000,
                        headers={"content-type": "text/garbage"},
                    )
                    assert r.status_code == 204, (method, p)
                    assert r.content == b""
        async with _client(app) as anon:
            for p in (T_IDX_URL, T_PC_URL):
                r = await anon.post(
                    p,
                    content=b"y" * 200_000,
                    headers={"content-type": "text/garbage"},
                )
                assert r.status_code == 404, p

    asyncio.run(run())


def test_t_index_page_from_verified_copy(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        session = _ProcConfigFakeSession([], [], COPY_OK, "on")
        _t_patch_sessionmaker(monkeypatch, session)
        app = _app(fake)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(T_IDX_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            assert "Demo preview:" in r.text
            assert "FROZEN copied data" in r.text
            # Admitted read pages are linked...
            assert 'href="/admin/operations/process-configuration"' in r.text
            assert 'href="/admin/operations/catalog/"' in r.text
            # 224-v: diagnostics and replay maintenance are admitted
            # and linked in the demo branch...
            assert 'href="/admin/operations/diagnostics"' in r.text
            assert 'href="/admin/operations/replay-maintenance/"' in r.text
            # ...and the not-yet-admitted pages are marked unavailable
            # WITHOUT a usable link.
            assert "unavailable in this demo" in r.text
            # 224-u: the compatibility page is now admitted and
            # linked (with the illustrative-operations note).
            assert 'href="/admin/operations/compatibility/"' in r.text
            assert 'href="/admin/email-operations/smtp-test"' not in r.text
            # No copy name or credential material.
            assert COPY_OK not in r.text
            assert "postgresql" not in r.text.lower()
            # The static index performs only the binding recheck.
            assert len(session.executed) == 0

    asyncio.run(run())


def test_t_index_refusals(monkeypatch):
    async def run():
        # Wrong copy database: the recheck refuses before rendering.
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        session = _ProcConfigFakeSession([], [], "some_other_db", "on")
        _t_patch_sessionmaker(monkeypatch, session)
        app = _app(fake)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(T_IDX_URL)
            assert r.status_code == 503
            assert COPY_OK not in r.text
        # Read-only mode off: same fixed safe refusal.
        fake2 = FakeFacade()
        fake2.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "off")
        session2 = _ProcConfigFakeSession([], [], COPY_OK, "off")
        _t_patch_sessionmaker(monkeypatch, session2)
        app2 = _app(fake2)
        async with _client(app2) as client2:
            await _verified_session_client(fake2, client2)
            r = await client2.get(T_IDX_URL)
            assert r.status_code == 503

    asyncio.run(run())


def test_t_pc_positive_from_copy(monkeypatch):
    async def run():
        body = _t_canonical_body(
            CHAT_MAX_IMAGES_PER_REQUEST=7,
            DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE=99,
        )
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        session = _ProcConfigFakeSession(
            [_t_meta_row(body)], [(body,)], COPY_OK, "on"
        )
        _t_patch_sessionmaker(monkeypatch, session)
        app = _app(fake)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(T_PC_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            text = r.text
            assert "Demo preview:" in text
            # Truthful worker-observed scope + capture time.
            assert (
                "worker-observed deployment configuration captured at "
                "copy time" in " ".join(text.split())
            )
            from datetime import UTC, datetime

            expected_utc = datetime.fromtimestamp(
                _T_CAPTURED_AT, tz=UTC
            ).strftime("%Y-%m-%d %H:%M:%S UTC")
            assert "captured " + expected_utc in text
            assert "Captured at (copy time)" in text
            assert "Worker-observed settings (45 finite allowlist, " in text
            # The CANARY values + configured provenance come from the
            # captured copy (never the ambient process settings).
            assert (
                _t_re.search(
                    r"CHAT_MAX_IMAGES_PER_REQUEST</code>.*?"
                    r'title="7 count">7</td>\s*<td>configured</td>',
                    text,
                    _t_re.S,
                )
                is not None
            )
            assert (
                _t_re.search(
                    r"DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE</code>.*?"
                    r"99.*?<td>configured</td>",
                    text,
                    _t_re.S,
                )
                is not None
            )
            # ...while untouched names keep the default provenance.
            assert (
                _t_re.search(
                    r"DEFAULT_MAX_OUTPUT_TOKENS</code>.*?"
                    r'<td>default</td>',
                    text,
                    _t_re.S,
                )
                is not None
            )
            # A nullable rate limit renders as (none), not fabricated.
            assert (
                _t_re.search(
                    r"DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE</code>.*?"
                    r"\(none\).*?<td>default</td>",
                    text,
                    _t_re.S,
                )
                is not None
            )
            # Not-captured identities are honestly labeled...
            assert "not recorded in this demo snapshot" in text
            # ...the package version is explicitly the LIVE demo-web
            # build, and captured-but-not-yet-displayed identities are
            # labeled as such (never claimed absent).
            assert "demo web process, live build" in text
            assert "not displayed on this page yet" in text
            # ...and the live app-global profile table never renders.
            assert 'aria-label="Upstream LLM profiles"' not in text
            # No copy name, DSN fragment or credential material.
            assert COPY_OK not in text
            assert "postgresql" not in text.lower()
            # The closed read law: metadata with octet_length FIRST,
            # then the bounded body query with bound parameters.
            assert len(session.executed) == 2
            meta_text, meta_params = session.executed[0]
            assert "octet_length(body) AS actual_bytes" in meta_text
            assert meta_params == {
                "name": "configuration/process-configuration.json"
            }
            body_text, body_params = session.executed[1]
            assert body_text.lstrip().startswith("SELECT body")
            assert body_params["name"] == (
                "configuration/process-configuration.json"
            )
            assert body_params["size"] == len(body)
            assert body_params["digest"] == _t_hashlib.sha256(body).hexdigest()
            assert body_params["kind"] == _t_dsf.KIND_PROCESS_CONFIG
            assert body_params["cap"] == 1024 * 1024

    asyncio.run(run())


def test_t_pc_ignores_ambient_settings_after_capture(monkeypatch):
    # Changing the AMBIENT demo-web/deployment settings AFTER the copy
    # was built must NOT change the page (no live fallback): the page
    # is frozen at capture time.
    async def run():
        body = _t_canonical_body(
            CHAT_MAX_IMAGES_PER_REQUEST=7,
            DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE=99,
        )
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        session = _ProcConfigFakeSession(
            [_t_meta_row(body)], [(body,)], COPY_OK, "on"
        )
        _t_patch_sessionmaker(monkeypatch, session)
        app = _app(fake)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(T_PC_URL)
            assert r.status_code == 200
            before = r.text
            # Ambient change AFTER the read: a different value than the
            # captured canary, plus the live API-process settings cache
            # cleared so any live fallback would pick it up.
            monkeypatch.setenv("CHAT_MAX_IMAGES_PER_REQUEST", "999")
            monkeypatch.setenv("DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE", "42")
            from slaif_gateway.config import get_settings as _t_get_settings

            _t_get_settings.cache_clear()
            try:
                r2 = await client.get(T_PC_URL)
            finally:
                _t_get_settings.cache_clear()
            assert r2.status_code == 200
            assert r2.text == before
            assert 'title="7 count"' in r2.text
            assert "999" not in _t_re.findall(
                r'title="999[^"]*"', r2.text
            )

    asyncio.run(run())


def test_t_pc_missing_leaf_503(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        session = _ProcConfigFakeSession([], [], COPY_OK, "on")
        _t_patch_sessionmaker(monkeypatch, session)
        app = _app(fake)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(T_PC_URL)
            assert r.status_code == 503
            assert "unavailable" in r.text
            assert COPY_OK not in r.text
            # No body query after a missing leaf.
            assert len(session.executed) == 1

    asyncio.run(run())


def test_t_pc_corrupt_metadata_503(monkeypatch):
    async def run():
        good_body = _t_canonical_body()
        cases = {
            "wrong kind": _t_meta_row(good_body, kind="job_record"),
            "actual over cap": _t_meta_row(
                good_body, actual=2 * 1024 * 1024
            ),
            "actual disagrees with size": _t_meta_row(
                good_body, actual=len(good_body) + 1
            ),
            "negative size": _t_meta_row(good_body, size=-1),
            "size over cap": _t_meta_row(good_body, size=2 * 1024 * 1024),
            "invalid sha": _t_meta_row(good_body, sha="zz" * 32),
            "short sha": _t_meta_row(good_body, sha="ab" * 16),
            "over-range capture time": _t_meta_row(
                good_body, captured=1e18
            ),
            "non-finite capture time": _t_meta_row(good_body, captured=float("inf")),
        }
        for label, meta in cases.items():
            fake = FakeFacade()
            fake.worker_target_db = COPY_OK
            _preflight_case(monkeypatch, COPY_OK, "on")
            session = _ProcConfigFakeSession(
                [meta], [(good_body,)], COPY_OK, "on"
            )
            _t_patch_sessionmaker(monkeypatch, session)
            app = _app(fake)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(T_PC_URL)
                assert r.status_code == 503, label
                assert COPY_OK not in r.text
                # Metadata refused BEFORE any body fetch.
                assert len(session.executed) == 1, label

    asyncio.run(run())


def test_t_pc_body_mismatch_503(monkeypatch):
    async def run():
        good_body = _t_canonical_body()
        for label, bad_body in (
            ("different bytes", _t_canonical_body(HARD_MAX_INPUT_TOKENS=7)),
            ("truncated", good_body[: len(good_body) // 2]),
        ):
            fake = FakeFacade()
            fake.worker_target_db = COPY_OK
            _preflight_case(monkeypatch, COPY_OK, "on")
            session = _ProcConfigFakeSession(
                [_t_meta_row(good_body)],
                [(bad_body,)],
                COPY_OK,
                "on",
            )
            _t_patch_sessionmaker(monkeypatch, session)
            app = _app(fake)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(T_PC_URL)
                assert r.status_code == 503, label
                assert COPY_OK not in r.text

    asyncio.run(run())


def test_t_pc_typed_law_refused_503(monkeypatch):
    # Metadata consistent with a body that BREAKS the closed typed law
    # (extra settings key / string value / wrong source) is refused
    # after the digest/size re-check, before projection.
    async def run():
        from slaif_gateway.services.configuration_inspection import (
            inspect_process_configuration,
        )

        payload = inspect_process_configuration(
            _t_Settings(), process_scope="api"
        )
        settings = {
            name: {"value": payload["config"]["settings"][name]["value"],
                   "source": payload["config"]["settings"][name]["source"]}
            for name in sorted(_T_ALLOWLIST)
        }
        doc_extra = {
            "schema": _t_dsf.DEMO_SCHEMA_VERSION,
            "kind": _t_dsf.KIND_PROCESS_CONFIG,
            "schema_version": 1,
            "settings": dict(settings, EVIL_SETTING={"value": 1, "source": "default"}),
        }
        bad_str = _t_json.loads(_t_json.dumps(doc_extra))
        bad_str["settings"]["HARD_MAX_INPUT_TOKENS"]["value"] = "128000"
        bad_src = _t_json.loads(_t_json.dumps(doc_extra))
        bad_src["settings"]["HARD_MAX_INPUT_TOKENS"]["source"] = "live"
        for label, doc in (
            ("extra settings key", doc_extra),
            ("string value", bad_str),
            ("wrong source", bad_src),
        ):
            body = _t_dsf._dump(doc)
            fake = FakeFacade()
            fake.worker_target_db = COPY_OK
            _preflight_case(monkeypatch, COPY_OK, "on")
            session = _ProcConfigFakeSession(
                [_t_meta_row(body)], [(body,)], COPY_OK, "on"
            )
            _t_patch_sessionmaker(monkeypatch, session)
            app = _app(fake)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(T_PC_URL)
                assert r.status_code == 503, label
                assert "EVIL" not in r.text
                assert COPY_OK not in r.text

    asyncio.run(run())


def test_t_pc_query_refused_before_copy(monkeypatch):
    # The demo page defines NO query parameters: ANY parameter refuses
    # with fixed 404 BEFORE any copy access (structurally, like the
    # 224-l name law).
    async def run():
        from types import SimpleNamespace

        from starlette.requests import Request

        app = _app(FakeFacade())
        demo = SimpleNamespace(target_db=COPY_OK)
        session = _ProcConfigFakeSession([], [], COPY_OK, "on")
        _t_patch_sessionmaker(monkeypatch, session)
        for query in (b"x=1", b"name=a", b"a=1&b=2"):
            scope = {
                "type": "http",
                "app": app,
                "state": {"demo_admin": demo},
                "query_string": query,
            }
            response = await dao.demo_operations_process_configuration(
                Request(scope)
            )
            assert response.status_code == 404, query
            assert response.body == b"Not Found"
        assert session.executed == []

    asyncio.run(run())


def test_t_pc_no_demo_state_404():
    async def run():
        from starlette.requests import Request

        app = _app(FakeFacade())
        scope = {"type": "http", "app": app, "state": {}}
        response = await dao.demo_operations_process_configuration(
            Request(scope)
        )
        assert response.status_code == 404
        assert response.body == b"Not Found"

    asyncio.run(run())


# ===========================================================================
# 224-u: neutral branding assets + read-only Codex compatibility views
# ===========================================================================

import hashlib as _u_hashlib  # noqa: E402
import uuid as _u_uuid  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from types import SimpleNamespace as _U_NS  # noqa: E402

from slaif_gateway.api import admin_compatibility as _u_adcom  # noqa: E402
from slaif_gateway.api import demo_admin_branding as _u_dab  # noqa: E402
from slaif_gateway.api import demo_admin_compatibility as _u_dacom  # noqa: E402
from slaif_gateway.modules.codex_profile_data import (  # noqa: E402
    list_codex_presets as _u_list_presets,
    read_codex_preset as _u_read_preset,
)
from slaif_gateway.services.admin_key_dashboard import (  # noqa: E402
    AdminKeyNotFoundError as _U_KeyNotFound,
)
from slaif_gateway.web import branding as _u_web_branding  # noqa: E402

_U_SLOTS = ("style.css", "logo", "logo-compact", "favicon", "hero")
_U_BRAND_URL = {slot: f"/admin/branding/{slot}" for slot in _U_SLOTS}
_U_COMP_INDEX = "/admin/operations/compatibility/"
_U_SHIPPED = tuple(name for name, _p, _prof in _u_list_presets())
_U_KEY_UUID = str(_u_uuid.uuid4())  # canonical lowercase dashed


class _U_Row:
    def __init__(self, mapping: dict) -> None:
        self._mapping = dict(mapping)

    def __getitem__(self, i):
        return list(self._mapping.values())[i]


class _U_Result:
    def __init__(self, rows) -> None:
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


def _u_neutral_body_map() -> dict:
    return {
        f"branding/{slot}": _u_web_branding.fallback_asset(slot)[0]
        for slot in _U_SLOTS
    }


class _UBrandFakeSession:
    """One fake request-local copy session for the demo branding law:
    preflight scalars, the five-slot metadata query (rows with
    ``_mapping``) and the bounded body query (the stored bytes are
    looked up by the REQUESTED slot name, as the parameterized body
    statement binds); every statement and its bound parameters are
    recorded."""

    def __init__(self, meta_rows, body_rows=None, db=COPY_OK, ro="on") -> None:
        self.meta_rows = meta_rows
        # body_rows: a dict {logical_name: bytes} (the stored body per
        # slot) or an explicit list of raw byte rows.
        self.body_rows = body_rows
        self.db = db
        self.ro = ro
        self.executed: list[tuple[str, dict]] = []

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def scalar(self, clause):
        text = str(clause)
        if "current_database" in text:
            return self.db
        return self.ro

    async def execute(self, clause, params=None):
        text = str(clause)
        params = dict(params or {})
        self.executed.append((text, params))
        if "logical_name IN" in text:
            return _U_Result([_U_Row(m) for m in self.meta_rows])
        if text.lstrip().startswith("SELECT body"):
            rows = []
            if isinstance(self.body_rows, dict):
                data = self.body_rows.get(params.get("name"))
                if data is not None:
                    rows.append(_U_Row({"body": data}))
            else:
                rows = [_U_Row({"body": b}) for b in (self.body_rows or [])]
            return _U_Result(rows)
        return _U_Result([])


def _u_brand_meta_rows() -> list[dict]:
    """The intact five-slot metadata set (every leaf is the packaged
    neutral substitute, self-consistent size/digest)."""
    rows = []
    for slot in _U_SLOTS:
        body, _ct = _u_web_branding.fallback_asset(slot)
        rows.append(
            {
                "logical_name": f"branding/{slot}",
                "kind": "branding",
                "byte_count": len(body),
                "sha256": _u_hashlib.sha256(body).hexdigest(),
                "actual_bytes": len(body),
            }
        )
    return rows


def _u_brand_app(fake, monkeypatch, session):
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    monkeypatch.setattr(
        _u_dab, "get_sessionmaker_from_app", lambda _req: lambda: session
    )
    return _app(fake), fake


class _UComFakeSession:
    """Fake copy session for the demo compatibility recheck (the
    qualification read is separately faked)."""

    def __init__(self, db=COPY_OK, ro="on") -> None:
        self.db = db
        self.ro = ro
        self.executed: list[str] = []

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def scalar(self, clause):
        text = str(clause)
        if "current_database" in text:
            return self.db
        return self.ro

    async def execute(self, clause, params=None):
        self.executed.append(str(clause))
        return _U_Result([])


def _u_com_app(fake, monkeypatch, session):
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    monkeypatch.setattr(
        _u_dacom, "get_sessionmaker_from_app", lambda _req: lambda: session
    )
    # _compat_session (the qualification read) reaches the copy through
    # the admin_compatibility module's own seam.
    monkeypatch.setattr(
        _u_adcom, "get_sessionmaker_from_app", lambda _req: lambda: session
    )
    return _app(fake), fake


def _u_qual_row(**kw) -> _U_NS:
    base = dict(
        ready=False,
        profile_id=None,
        route_id=str(_u_uuid.uuid4()),
        client_module_id=None,
        client_module_version=None,
        reason_codes=("missing_profile",),
        badge="Not ready",
        requested_model="gpt-x",
        provider="openai",
        endpoint="chat/completions",
        metadata_version="0162-v1",
    )
    base.update(kw)
    return _U_NS(**base)


class _UFakeQualService:
    def __init__(self, results) -> None:
        self._results = results

    async def inspect(self):
        return self._results


def _u_patch_qual(monkeypatch, results) -> None:
    monkeypatch.setattr(
        _u_dacom,
        "_qualification_service",
        lambda _s: _UFakeQualService(results),
    )


def test_u_gate_branding_exact_paths_total():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # The five EXACT literals are admitted BEFORE login and
            # serve the packaged neutral fallback (never a login
            # redirect, never the live directory).
            for slot, url in _U_BRAND_URL.items():
                r = await client.get(url)
                assert r.status_code == 200, url
                data, content_type = _u_web_branding.fallback_asset(slot)
                assert r.content == data, url
                assert r.headers["content-type"].startswith(content_type.split(";")[0]), url
                assert r.headers.get("x-content-type-options") == "nosniff", url
                assert r.headers.get("cache-control") == "private, no-store", url
            # Every near miss, alternate slash, unknown slot and query
            # stays default-denied 404.
            for p in (
                "/admin/branding",
                "/admin/branding/",
                "/admin/branding/",
                "/admin/branding/style.css/",
                "/admin/branding/style.css.map",
                "/admin/branding/logos",
                "/admin/branding/logo/extra",
                "/admin/branding/LOGO",
                "/admin/brandingx/logo",
                _U_BRAND_URL["logo"] + "?x=1",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p
        # Zero active accounts: every /admin path is 404 (fail closed).
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            for url in _U_BRAND_URL.values():
                assert (await client.get(url)).status_code == 404, url

    asyncio.run(run())


def test_u_gate_branding_unsafe_methods_quiet_noop():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                r = await client.request(
                    method,
                    _U_BRAND_URL["style.css"],
                    content=b"x" * 200_000,
                    headers={"content-type": "text/garbage"},
                )
                assert r.status_code == 204, method
                assert r.content == b""
        async with _client(app) as anon:
            r = await anon.post(_U_BRAND_URL["logo"], content=b"y" * 200_000)
            assert r.status_code == 404

    asyncio.run(run())


def test_u_gate_compatibility_exact_paths():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            # The exact family is admitted (no session -> entry
            # redirect, the session-required law)...
            r = await client.get(_U_COMP_INDEX)
            assert r.status_code == 303
            assert r.headers["location"] == "/fakeadmin/login"
            for name in _U_SHIPPED:
                r = await client.get(f"/admin/operations/compatibility/preset/{name}")
                assert r.status_code == 303, name
                r = await client.get(
                    f"/admin/operations/compatibility/preset/{name}/download"
                )
                assert r.status_code == 303, name
            r = await client.get(
                f"/admin/operations/compatibility/key/{_U_KEY_UUID}"
            )
            assert r.status_code == 303
            # ...and every near miss, unknown preset name, noncanonical
            # key ID and ANY query stays default-denied 404.
            for p in (
                "/admin/operations/compatibility",  # missing slash
                "/admin/operations/compatibility//",
                "/admin/operations/compatibility/extra",
                "/admin/operations/compatibility/x/",
                "/admin/operations/compatibility/preset/",
                "/admin/operations/compatibility/preset/unknown",
                "/admin/operations/compatibility/preset/Unknown",
                "/admin/operations/compatibility/preset/a/b",
                "/admin/operations/compatibility/preset/downloads",
                "/admin/operations/compatibility/key/",
                "/admin/operations/compatibility/key/" + _U_KEY_UUID.upper(),
                "/admin/operations/compatibility/key/" + _U_KEY_UUID.replace("-", ""),
                "/admin/operations/compatibility/key/" + _U_KEY_UUID[:13],
                f"/admin/operations/compatibility/key/{_U_KEY_UUID}/extra",
                f"/admin/operations/compatibility/key/{_U_KEY_UUID}/review",
                _U_COMP_INDEX + "?x=1",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p
            # An admitted shape with ANY query is refused too.
            for p in (
                f"/admin/operations/compatibility/preset/{_U_SHIPPED[0]}?x=1",
                f"/admin/operations/compatibility/preset/{_U_SHIPPED[0]}/download?x=1",
                f"/admin/operations/compatibility/key/{_U_KEY_UUID}?x=1",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p
        # Zero active accounts: 404.
        fake = FakeFacade()
        fake.active = 0
        app = _app(fake)
        async with _client(app) as client:
            _session_cookie(client)
            assert (await client.get(_U_COMP_INDEX)).status_code == 404

    asyncio.run(run())


def test_u_compatibility_unsafe_methods_quiet_noop():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            for p in (
                _U_COMP_INDEX,
                f"/admin/operations/compatibility/preset/{_U_SHIPPED[0]}",
                f"/admin/operations/compatibility/preset/{_U_SHIPPED[0]}/download",
                f"/admin/operations/compatibility/key/{_U_KEY_UUID}",
                f"/admin/operations/compatibility/key/{_U_KEY_UUID}/review",
                f"/admin/operations/compatibility/key/{_U_KEY_UUID}/apply",
            ):
                r = await client.post(
                    p,
                    content=b"x" * 200_000,
                    headers={"content-type": "text/garbage"},
                )
                assert r.status_code == 204, p
                assert r.content == b""
        async with _client(app) as anon:
            r = await anon.post(_U_COMP_INDEX, content=b"y" * 200_000)
            assert r.status_code == 404

    asyncio.run(run())


def test_u_branding_positive_five_leaf_copy(monkeypatch):
    async def run():
        fake = FakeFacade()
        session = _UBrandFakeSession(_u_brand_meta_rows(), _u_neutral_body_map())
        app, _ = _u_brand_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            for slot, url in _U_BRAND_URL.items():
                before = len(session.executed)
                r = await client.get(url)
                assert r.status_code == 200, url
                data, content_type = _u_web_branding.fallback_asset(slot)
                assert r.content == data, url
                assert r.headers["content-type"].startswith(content_type.split(";")[0]), url
                assert r.headers.get("x-content-type-options") == "nosniff", url
                assert r.headers.get("cache-control") == "private, no-store", url
                # THIS request ran the five-slot metadata law
                # (parameterized) then exactly ONE bounded body fetch
                # re-asserting kind/size/digest as bound parameters.
                new_stmts = session.executed[before:]
                meta_sqls = [s for s, _p in new_stmts if "logical_name IN" in s]
                body_sqls = [
                    (s, p)
                    for s, p in new_stmts
                    if s.lstrip().startswith("SELECT body")
                ]
                assert len(meta_sqls) == 1, url
                assert len(body_sqls) == 1, url
                _bsql, bparams = body_sqls[0]
                assert bparams["kind"] == "branding", url
                assert bparams["name"] == f"branding/{slot}", url
                assert bparams["size"] == len(data), url
                assert bparams["digest"] == _u_hashlib.sha256(data).hexdigest(), url
                assert bparams["cap"] == 256 * 1024, url
            # Across the five requests: five metadata laws, five bodies.
            assert len(
                [s for s, _p in session.executed if "logical_name IN" in s]
            ) == 5
            assert len(
                [
                    s
                    for s, _p in session.executed
                    if s.lstrip().startswith("SELECT body")
                ]
            ) == 5

    asyncio.run(run())


def test_u_branding_zero_or_partial_leaf_set_refuses(monkeypatch):
    async def run():
        fake = FakeFacade()
        session = _UBrandFakeSession([], [])  # ZERO leaves: damaged/pre-upgrade
        app, _ = _u_brand_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(_U_BRAND_URL["logo"])
            assert r.status_code == 503
            assert r.headers.get("cache-control") == "private, no-store"
            assert COPY_OK not in r.text
            # PARTIAL set (four of five): damaged configured copy.
            rows = _u_brand_meta_rows()
            session.meta_rows = rows[:4]
            r = await client.get(_U_BRAND_URL["hero"])
            assert r.status_code == 503
            session.meta_rows = [rows[0]]  # one of five: refused too
            r = await client.get(_U_BRAND_URL["favicon"])
            assert r.status_code == 503
            # No body fetch ever ran (the set law refused first).
            assert not [
                s for s, _p in session.executed if s.lstrip().startswith("SELECT body")
            ]

    asyncio.run(run())


def test_u_branding_corrupt_metadata_refuses(monkeypatch):
    async def run():
        for field, value in (
            ("kind", "job_record"),
            ("byte_count", 256 * 1024 + 1),   # over the reviewed slot cap
            ("byte_count", -1),
            ("byte_count", True),             # bool is not a size
            ("sha256", "zz" * 32),            # not canonical hex
            ("actual_bytes", 12345),          # != claimed byte_count
        ):
            fake = FakeFacade()
            rows = _u_brand_meta_rows()
            rows[0][field] = value
            session = _UBrandFakeSession(rows, [])
            app, _ = _u_brand_app(fake, monkeypatch, session)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(_U_BRAND_URL["style.css"])
                assert r.status_code == 503, (field, value)
                assert "unit-test-copy-password" not in r.text
            # The metadata law refused BEFORE any body fetch.
            assert not [
                s for s, _p in session.executed if s.lstrip().startswith("SELECT body")
            ], (field, value)

    asyncio.run(run())


def test_u_branding_body_mismatch_and_policy_refuses(monkeypatch):
    async def run():
        body_bytes, _ct = _u_web_branding.fallback_asset("logo")
        # (a) the bounded body fetch returns no row (concurrent change).
        fake = FakeFacade()
        session = _UBrandFakeSession(_u_brand_meta_rows(), [])
        app, _ = _u_brand_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            assert (await client.get(_U_BRAND_URL["logo"])).status_code == 503
        # (b) the fetched bytes fail length/digest (metadata is
        # self-consistent for OTHER bytes than the neutral substitute).
        fake = FakeFacade()
        foreign = b"\x00" * 16
        rows = _u_brand_meta_rows()
        for row in rows:
            if row["logical_name"] == "branding/logo":
                row["byte_count"] = len(foreign)
                row["sha256"] = _u_hashlib.sha256(foreign).hexdigest()
                row["actual_bytes"] = len(foreign)
        bodies = _u_neutral_body_map()
        bodies["branding/logo"] = foreign
        session = _UBrandFakeSession(rows, bodies)
        app, _ = _u_brand_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            # The bytes pass size+digest but FAIL the 223 display
            # policy (not the packaged neutral substitute): fixed 503.
            r = await client.get(_U_BRAND_URL["logo"])
            assert r.status_code == 503
            assert foreign not in r.content

    asyncio.run(run())


def test_u_branding_copy_mismatch_refuses(monkeypatch):
    async def run():
        for db, ro in (("some_other_db", "on"), (COPY_OK, "off")):
            fake = FakeFacade()
            session = _UBrandFakeSession(_u_brand_meta_rows(), db=db, ro=ro)
            app, _ = _u_brand_app(fake, monkeypatch, session)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(_U_BRAND_URL["style.css"])
                assert r.status_code == 503, (db, ro)
                assert db != COPY_OK or COPY_OK not in r.text

    asyncio.run(run())


def test_u_branding_prelogin_fallback_no_db(monkeypatch):
    async def run():
        fake = FakeFacade()
        calls = []

        def _boom(_req):
            calls.append(1)
            raise AssertionError("the pre-login fallback must not touch the copy")

        app = _app(fake)
        _preflight_case(monkeypatch, COPY_OK, "on")
        monkeypatch.setattr(_u_dab, "get_sessionmaker_from_app", _boom)
        async with _client(app) as client:
            # NO session cookie: the packaged neutral fallback, no DB.
            for slot, url in _U_BRAND_URL.items():
                r = await client.get(url)
                assert r.status_code == 200, url
                data, _ct = _u_web_branding.fallback_asset(slot)
                assert r.content == data, url
        assert calls == []

    asyncio.run(run())


def test_u_compatibility_index_positive(monkeypatch):
    async def run():
        fake = FakeFacade()
        ready_row = _u_qual_row(
            ready=True,
            profile_id="codex-0162-demo",
            badge="Protocol-qualified",
            reason_codes=(),
        )
        _u_patch_qual(monkeypatch, [ready_row, _u_qual_row()])
        session = _UComFakeSession()
        app, _ = _u_com_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(_U_COMP_INDEX)
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "private, no-store"
            text = " ".join(r.text.split())
            # The persistent demo note (illustrative, no effect)...
            assert "Compatibility operations are illustrative" in text
            assert "have no effect" in text
            assert "no compatibility or replay authority" in text
            # ...the demo web process adopts no startup profile...
            assert "adopts no API startup compatibility profile" in text
            assert "not published as display data to this page yet" in text
            # ...the qualification rows render from the (fake) copy...
            assert "Protocol-qualified" in text
            assert "codex-0162-demo" in text
            # ...NO runnable profile artifact is offered...
            assert "/codex-profile/" not in r.text
            assert "Not offered in the demo snapshot" in text
            # ...and the package-owned shipped presets are listed with
            # their exact demo hrefs.
            for name in _U_SHIPPED:
                assert f'href="/admin/operations/compatibility/preset/{name}"' in r.text
                assert (
                    f'href="/admin/operations/compatibility/preset/{name}/download"'
                    in r.text
                )
            # The base header references the FIVE demo-admitted slot
            # URLs (the demo branding context), which resolve to this
            # visitor's neutral copy or the packaged fallback.
            assert '<link rel="stylesheet" href="/admin/branding/style.css">' in r.text
            assert (
                '<link rel="icon" type="image/svg+xml" href="/admin/branding/favicon">'
                in r.text
            )
            assert 'src="/admin/branding/logo"' in r.text
            assert 'src="/admin/branding/logo-compact"' in r.text
            # No copy name or credential material.
            assert COPY_OK not in r.text
            assert "postgresql" not in r.text.lower()

    asyncio.run(run())


def test_u_compatibility_index_alias_withheld(monkeypatch):
    async def run():
        fake = FakeFacade()
        alias_route = "sk-slaif-" + "a1" * 20
        ready_row = _u_qual_row(
            ready=True,
            profile_id="codex-0162-demo",
            route_id=alias_route,
            badge="Protocol-qualified",
            reason_codes=(),
        )
        _u_patch_qual(monkeypatch, [ready_row])
        monkeypatch.setattr(
            _u_dacom,
            "_is_known_alias",
            lambda _req, value: value == alias_route,
        )
        session = _UComFakeSession()
        app, _ = _u_com_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(_U_COMP_INDEX)
            assert r.status_code == 200
            assert "Withheld: route ID matches a known credential value." in r.text
            # The withheld route ID is displayed withheld and its copy-
            # backed link is dropped (no href at all).
            assert f'href="/admin/routes/{alias_route}"' not in r.text

    asyncio.run(run())


def test_u_compatibility_index_qualification_error_safe(monkeypatch):
    async def run():
        fake = FakeFacade()

        class _Boom:
            async def inspect(self):
                raise RuntimeError("boom")

        monkeypatch.setattr(_u_dacom, "_qualification_service", lambda _s: _Boom())
        session = _UComFakeSession()
        app, _ = _u_com_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(_U_COMP_INDEX)
            assert r.status_code == 200
            assert "boom" not in r.text
            assert "The qualification projection is unavailable right now" in r.text
            # The package presets still render.
            assert f'href="/admin/operations/compatibility/preset/{_U_SHIPPED[0]}"' in r.text

    asyncio.run(run())


def test_u_compatibility_preset_page_and_download(monkeypatch):
    async def run():
        name = _U_SHIPPED[0]
        fake = FakeFacade()
        session = _UComFakeSession()
        app, _ = _u_com_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(f"/admin/operations/compatibility/preset/{name}")
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "private, no-store"
            text = " ".join(r.text.split())
            assert f"Compatibility preset: <code>{name}</code>" in r.text or name in text
            assert "package-owned credential-free reference material" in text
            from markupsafe import escape as _u_escape

            document = _u_read_preset(name)
            assert str(_u_escape(document)) in r.text
            # The exact canonical credential-free bytes, bounded,
            # forced attachment, nosniff, no-store.
            r = await client.get(
                f"/admin/operations/compatibility/preset/{name}/download"
            )
            assert r.status_code == 200
            assert r.content == document.encode("utf-8")
            assert r.headers["content-type"].startswith("application/json")
            assert f'attachment; filename="{name}.json"' in r.headers[
                "content-disposition"
            ]
            assert r.headers.get("x-content-type-options") == "nosniff"
            assert r.headers.get("cache-control") == "private, no-store"

    asyncio.run(run())


def test_u_compatibility_preset_download_withheld(monkeypatch):
    async def run():
        name = _U_SHIPPED[0]
        fake = FakeFacade()
        monkeypatch.setattr(
            _u_dacom, "_is_known_alias", lambda _req, value: True
        )
        session = _UComFakeSession()
        app, _ = _u_com_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(
                f"/admin/operations/compatibility/preset/{name}/download"
            )
            assert r.status_code == 403
            assert "known credential value" in r.text
            # The page display is withheld too (document hidden).
            r = await client.get(f"/admin/operations/compatibility/preset/{name}")
            assert r.status_code == 200
            assert "withheld for display" in r.text

    asyncio.run(run())


def test_u_compatibility_key_page_positive(monkeypatch):
    async def run():
        key_detail = _U_NS(
            public_key_id="slaif-pub-key-1",
            id=_u_uuid.UUID(_U_KEY_UUID),
            computed_display_status="active",
            owner_display_name="Owner One",
            owner_email=None,
            responses_policy=None,
        )

        @asynccontextmanager
        async def _fake_scope(_req):
            class _Svc:
                async def get_key_detail(self, kid):
                    if str(kid) != _U_KEY_UUID:
                        raise _U_KeyNotFound()
                    return key_detail

            yield _Svc()

        monkeypatch.setattr(_u_dacom, "_admin_key_dashboard_service_scope", _fake_scope)
        fake = FakeFacade()
        session = _UComFakeSession()
        app, _ = _u_com_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(
                f"/admin/operations/compatibility/key/{_U_KEY_UUID}"
            )
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "private, no-store"
            text = " ".join(r.text.split())
            assert "slaif-pub-key-1" in text
            assert "Owner One" in text
            assert "Demo snapshot: the key binding shown is a FROZEN read" in text
            assert "the form has no effect" in text
            assert "No readable client-module binding on this key" in text
            # No copy name or credential material.
            assert COPY_OK not in r.text

    asyncio.run(run())


def test_u_compatibility_key_page_not_found(monkeypatch):
    async def run():
        @asynccontextmanager
        async def _fake_scope(_req):
            class _Svc:
                async def get_key_detail(self, _kid):
                    raise _U_KeyNotFound()

            yield _Svc()

        monkeypatch.setattr(_u_dacom, "_admin_key_dashboard_service_scope", _fake_scope)
        fake = FakeFacade()
        session = _UComFakeSession()
        app, _ = _u_com_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(
                f"/admin/operations/compatibility/key/{_u_uuid.uuid4()}"
            )
            assert r.status_code == 404

    asyncio.run(run())


def test_u_compatibility_recheck_refusals_and_no_session(monkeypatch):
    async def run():
        # A present but wrong-bound copy is a fixed safe 503 on every
        # demo compatibility GET.
        for db, ro in (("some_other_db", "on"), (COPY_OK, "off")):
            fake = FakeFacade()
            session = _UComFakeSession(db=db, ro=ro)
            app, _ = _u_com_app(fake, monkeypatch, session)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(_U_COMP_INDEX)
                assert r.status_code == 503, (db, ro)
                assert COPY_OK not in r.text
        # No session at all: the entry redirect (the pages are
        # session-required, unlike the total branding endpoints).
        app = _app(FakeFacade())
        async with _client(app) as client:
            for p in (
                _U_COMP_INDEX,
                f"/admin/operations/compatibility/preset/{_U_SHIPPED[0]}",
                f"/admin/operations/compatibility/preset/{_U_SHIPPED[0]}/download",
                f"/admin/operations/compatibility/key/{_U_KEY_UUID}",
            ):
                r = await client.get(p)
                assert r.status_code == 303, p
                assert r.headers["location"] == "/fakeadmin/login"

    asyncio.run(run())


# --- 224-v: copy-backed request diagnostics + replay maintenance reads ---

from types import SimpleNamespace as _v_NS  # noqa: E402

from slaif_gateway.api import demo_admin_operations as _v_dao  # noqa: E402
from slaif_gateway.api import demo_admin_replay as _v_dar  # noqa: E402

V_DIAG_URL = "/admin/operations/diagnostics"
V_REPLAY_IDX_URL = "/admin/operations/replay-maintenance/"
V_REPLAY_ALL_URL = "/admin/operations/replay-maintenance/all-active"
_V_KEY_UUID = "a2222222-b333-4c44-8555-6666666666aa"
_V_COHORT_UUID = "33333333-4444-4555-8666-777777777777"
_V_ROUTE_UUID = "44444444-5555-4666-8777-888888888888"
_V_SAFE_ID = "gw:abc-123"      # safe grammar (colon included)
_V_ALIAS_ID = "sk-slaif-unit-v1"  # accepted-prefix credential shape


class _VResult:
    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)

    def one(self):
        assert len(self._rows) == 1
        return self._rows[0]

    def scalars(self):
        return self


def _v_raw_get(app):
    async def _raw_get(query: bytes):
        """One raw ASGI GET of the diagnostics path: ``query`` is the
        EXACT ASGI query_string bytes (i.e. the bytes AFTER the
        ``?``; the raw byte law, httpx would normalize)."""
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": V_DIAG_URL,
            "raw_path": V_DIAG_URL.encode("ascii"),
            "query_string": query,
            "headers": [
                (b"host", b"demo.test"),
                (b"cookie", b"slaif_demo_session=unit-token-1"),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("demo.test", 443),
            "app": app,
            "state": {},
        }
        status = None
        chunks: list[bytes] = []

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def _send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body") or b"")

        await app(scope, _receive, _send)
        return status, b"".join(chunks)

    return _raw_get


def _v_diag_record(gwid: str, *, client_id: str | None = "cl-abc123"):
    from datetime import UTC as _V_UTC
    from datetime import datetime as _V_dt

    now = _V_dt(2026, 1, 5, tzinfo=_V_UTC)
    return _v_NS(
        id=uuid.uuid4(),
        gateway_request_id=gwid,
        client_request_id=client_id,
        client_id_unavailable_reason=None,
        method="POST",
        endpoint_template="/v1/chat/completions",
        occurred_at=now,
        http_status=429,
        stream_outcome="http_rejection",
        source="quota",
        reason_code="rate_limit",
        error_code="rate_limit_exceeded",
        error_param="requests",
        positions={"line": 3},
        counts={"count": 5},
        limits={"max_input_tokens": 1000},
        gateway_key_id=uuid.uuid4(),
        route_id=uuid.uuid4(),
        route_pattern="/v1/chat/completions",
        deployment_revision="rev-1",
        estimated_input_tokens=120,
        output_allowance_tokens=None,
        context_window_tokens=None,
        replay_error_code=None,
        recorded_at=now,
    )


class _VDiagFakeSession:
    """One fake request-local copy session for the 224-v diagnostics
    page: the recheck scalars, the COUNT/MIN/MAX SQL, and the ORM
    recent select (identified by table name in the compiled clause)."""

    def __init__(self, count_row, recent_rows, db=COPY_OK, ro="on") -> None:
        self.count_row = count_row
        self.recent_rows = recent_rows
        self.db = db
        self.ro = ro
        self.executed: list[tuple[str, dict]] = []

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def scalar(self, clause):
        text = str(clause)
        if "current_database" in text:
            return self.db
        return self.ro

    async def execute(self, clause, params=None):
        text = str(clause)
        self.executed.append((text, dict(params or {})))
        if "COUNT(*)" in text and "request_diagnostics" in text:
            return _VResult([self.count_row])
        if "FROM request_diagnostics" in text:
            return _VResult(self.recent_rows)
        return _VResult([])


def _v_patch_diag_lookup(monkeypatch, rows, total, calls) -> None:
    class _VLookupRepo:
        def __init__(self, _session) -> None:
            pass

        async def lookup_retained(
            self, *, lookup_id, namespace, not_before, limit
        ):
            calls.append(
                (lookup_id, namespace, not_before, limit)
            )
            return (tuple(rows), total)

    monkeypatch.setattr(_v_dao, "RequestDiagnosticsRepository", _VLookupRepo)


def _v_diag_app(fake, monkeypatch, session):
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    monkeypatch.setattr(
        _v_dao, "get_sessionmaker_from_app", lambda _req: lambda: session
    )
    return _app(fake), fake


# ---------------------------------------------------------------------------


def test_v_gate_admission_exact_paths():
    """224-v gate: the exact diagnostics + replay-maintenance GET
    family is admitted (entry redirect, no session); every near miss,
    alternate slash shape, non-canonical UUID and ANY query on the
    replay family stays default-denied 404."""
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            for p in (
                V_DIAG_URL,
                V_REPLAY_IDX_URL,
                V_REPLAY_ALL_URL,
                f"/admin/operations/replay-maintenance/key/{_V_KEY_UUID}",
                f"/admin/operations/replay-maintenance/cohort/{_V_COHORT_UUID}",
            ):
                r = await client.get(p)
                assert r.status_code == 303, p
                assert r.headers["location"] == "/fakeadmin/login"
            for p in (
                V_DIAG_URL + "/",                  # trailing slash
                V_DIAG_URL + "/lookup",            # deeper
                "/admin/operations/diagnostic",    # misspelled
                V_REPLAY_IDX_URL.rstrip("/"),      # missing slash
                V_REPLAY_IDX_URL + "x",            # prefix sibling
                V_REPLAY_ALL_URL + "/",            # trailing slash
                "/admin/operations/replay-maintenance/key/",
                f"/admin/operations/replay-maintenance/key/{_V_KEY_UUID}/",
                f"/admin/operations/replay-maintenance/key/{_V_KEY_UUID}x",
                "/admin/operations/replay-maintenance/key/not-a-uuid",
                f"/admin/operations/replay-maintenance/key/{_V_KEY_UUID.upper()}",
                f"/admin/operations/replay-maintenance/cohort/{_V_COHORT_UUID}/deep",
                # the replay family is query-free
                V_REPLAY_IDX_URL + "?x=1",
                V_REPLAY_ALL_URL + "?x=1",
                f"/admin/operations/replay-maintenance/key/{_V_KEY_UUID}?x=1",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p

    asyncio.run(run())


def test_v_gate_diagnostics_query_law(monkeypatch):
    """224-v gate: the diagnostics selector's bounded raw query law,
    through ASGI. Refused selectors (unknown/duplicate/empty/
    malformed/over-raw-ceiling/known-alias) are the gate's fixed 404
    BEFORE the copy session exists; admitted selectors reach the REAL
    handler (the fake copy session renders the page)."""
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")

        def _v_boom(_req):
            raise AssertionError("gate-refused query reached the handler")

        monkeypatch.setattr(_v_dao, "get_sessionmaker_from_app", _v_boom)
        app = _app(fake)
        _raw_get = _v_raw_get(app)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            for q in (
                "?x=1",                               # unknown param
                "?lookup=" + _V_SAFE_ID + "&x=1",     # extra param
                "?namespace=any&namespace=gateway",   # duplicate
                "?lookup=",                           # empty value
                "?namespace=other",                   # out of vocabulary
                "?lookup=bad+id",                     # unsafe grammar (+)
                "?lookup=" + _V_ALIAS_ID,             # known alias
            ):
                r = await client.get(V_DIAG_URL + q)
                assert r.status_code == 404, q
            # raw-byte cases: an oversized WHOLE query (beyond the
            # 420-byte ceiling, refused before any split/parse), an
            # invalid percent escape (stays literal, fails grammar),
            # and the alias in exact raw form (refused pre-copy).
            # (ASGI ``query_string`` carries the bytes AFTER the ``?``;
            # the helper takes the exact bytes.)
            for raw in (
                b"lookup=" + b"a" * 500,
                b"lookup=%zz",
                b"lookup=" + _V_ALIAS_ID.encode("ascii"),
            ):
                status, _body = await _raw_get(raw)
                assert status == 404, raw[:40]
            # Admitted selectors: the REAL handler renders. The
            # percent-encoded colon decodes exactly once and is
            # admitted; the re-proven value pre-fills the GET form.
            session = _VDiagFakeSession((0, None, None), [])
            calls: list = []
            _v_patch_diag_lookup(monkeypatch, [], 0, calls)
            monkeypatch.setattr(
                _v_dao,
                "get_sessionmaker_from_app",
                lambda _req: lambda: session,
            )
            status, body = await _raw_get(
                b"lookup=gw%3Aabc-123&namespace=gateway"
            )
            assert status == 200, body[:200]
            text = body.decode()
            assert "No copied record matches this exact ID in this frozen snapshot." in text
            assert 'value="gw:abc-123"' in text
            r = await client.get(V_DIAG_URL, params={"namespace": "client"})
            assert r.status_code == 200
            assert "No copied diagnostic records." in r.text
            assert calls and calls[0][0] == _V_SAFE_ID

    asyncio.run(run())


def test_v_unsafe_methods_quiet_noop():
    """224-v gate: every unsafe method on the five admitted paths is
    the pre-body quiet 204 cut (body never parsed); without a session
    the uniform 404."""
    async def run():
        app = _app(FakeFacade())
        paths = (
            V_DIAG_URL,
            V_REPLAY_IDX_URL,
            V_REPLAY_ALL_URL,
            f"/admin/operations/replay-maintenance/key/{_V_KEY_UUID}",
            f"/admin/operations/replay-maintenance/cohort/{_V_COHORT_UUID}",
        )
        async with _client(app) as client:
            _session_cookie(client)
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                for p in paths:
                    r = await client.request(
                        method,
                        p,
                        content=b"x" * 200_000,
                        headers={"content-type": "text/garbage"},
                    )
                    assert r.status_code == 204, (method, p)
                    assert r.content == b""
        async with _client(app) as anon:
            for p in paths:
                r = await anon.post(
                    p,
                    content=b"y" * 200_000,
                    headers={"content-type": "text/garbage"},
                )
                assert r.status_code == 404, p

    asyncio.run(run())


def test_v_diagnostics_positive_found(monkeypatch):
    """224-v: the copy-backed diagnostics page renders the frozen
    summary, the bounded recent list with exact safe-ID links, and the
    FOUND lookup rendering - in ONE rechecked read transaction."""
    async def run():
        from datetime import UTC as _V_UTC
        from datetime import datetime as _V_dt

        rec1 = _v_diag_record(_V_SAFE_ID)
        rec2 = _v_diag_record("gw-999", client_id=None)
        session = _VDiagFakeSession(
            (2, _V_dt(2026, 1, 4, tzinfo=_V_UTC), _V_dt(2026, 1, 5, tzinfo=_V_UTC)),
            [rec1, rec2],
        )
        calls: list = []
        _v_patch_diag_lookup(monkeypatch, [rec1], 1, calls)
        fake = FakeFacade()
        app, _ = _v_diag_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            # no selector: the frozen summary + recent list only.
            r = await client.get(V_DIAG_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            assert "FROZEN copied content-free" in r.text
            assert "not recorded in this demo snapshot" in r.text
            assert "lookup=gw:abc-123&amp;namespace=any" in r.text
            assert "gw-999" in r.text
            assert "No copied record matches this exact ID" not in r.text
            # exact selector: the FOUND typed rendering.
            r = await client.get(V_DIAG_URL, params={"lookup": _V_SAFE_ID})
            assert r.status_code == 200
            assert f"<code>{_V_SAFE_ID}</code>" in r.text
            assert "rate_limit_exceeded" in r.text
            assert "requests" in r.text
            assert calls and calls[0][0] == _V_SAFE_ID
            # ONE transaction: recheck scalars + count SQL + recent
            # select per request (the lookup is repository-bound).
            sqls = [t for t, _p in session.executed if "COUNT(*)" in t]
            assert len(sqls) == 2

    asyncio.run(run())


def test_v_diagnostics_alias_candidate_withheld(monkeypatch):
    """224-v: an AMBIGUOUS lookup withholds a candidate whose stored
    gateway ID is a known incoming alias - the row stays (honest
    count) but the ID and the resolve link never render."""
    async def run():
        rec_alias = _v_diag_record(_V_ALIAS_ID)
        rec_plain = _v_diag_record("gw-plain-1")
        session = _VDiagFakeSession((2, None, None), [rec_plain])
        calls: list = []
        _v_patch_diag_lookup(monkeypatch, [rec_alias, rec_plain], 2, calls)
        fake = FakeFacade()
        app, _ = _v_diag_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(V_DIAG_URL, params={"lookup": "gw-ambig"})
            assert r.status_code == 200
            assert _V_ALIAS_ID not in r.text
            assert "gw-plain-1" in r.text
            assert "Resolve in gateway" in r.text
            assert "unavailable (known incoming value withheld)" in r.text
            assert "2 retained row(s) match" in r.text

    asyncio.run(run())


def test_v_diagnostics_preflight_mismatch_503(monkeypatch):
    """224-v: a present but wrong-bound (or writable) copy is the
    fixed safe 503 - the count SQL is never issued."""
    async def run():
        for db, ro in (("some_other_db", "on"), (COPY_OK, "off")):
            session = _VDiagFakeSession((1, None, None), [], db=db, ro=ro)
            fake = FakeFacade()
            app, _ = _v_diag_app(fake, monkeypatch, session)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(V_DIAG_URL)
                assert r.status_code == 503, (db, ro)
                assert COPY_OK not in r.text
                sqls = [t for t, _p in session.executed if "COUNT(*)" in t]
                assert sqls == []

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 224-v: replay maintenance fakes + tests
# ---------------------------------------------------------------------------


def _v_ttl_body(ttl: int) -> bytes:
    """A valid worker-captured process-config display document carrying
    the given TTL (the 224-t canonical body law)."""
    return _t_canonical_body(CODEX_REPLAY_REFERENCE_TTL_SECONDS=ttl)


class _VReplayFakeSession:
    """One fake request-local copy session for the 224-v replay views:
    the recheck scalars, the process-config TTL metadata + bounded
    body statements (224-t capture law), the kind-count GROUP BY and
    the bounded recent SELECT (rows carry ``_mapping``)."""

    def __init__(
        self,
        ttl_meta,
        ttl_body,
        kind_rows,
        recent_rows,
        db=COPY_OK,
        ro="on",
    ) -> None:
        self.ttl_meta = ttl_meta  # tuple or None (absent leaf)
        self.ttl_body = ttl_body  # bytes or None
        self.kind_rows = kind_rows
        self.recent_rows = recent_rows
        self.db = db
        self.ro = ro
        self.executed: list[tuple[str, dict]] = []

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def scalar(self, clause):
        text = str(clause)
        if "current_database" in text:
            return self.db
        return self.ro

    async def execute(self, clause, params=None):
        text = str(clause)
        self.executed.append((text, dict(params or {})))
        if "octet_length(body) AS actual_bytes" in text:
            return _VResult(
                [self.ttl_meta] if self.ttl_meta is not None else []
            )
        if text.lstrip().startswith("SELECT body"):
            if self.ttl_body is None:
                return _VResult([])
            return _VResult([(self.ttl_body,)])
        if "GROUP BY item_kind" in text:
            return _VResult(list(self.kind_rows))
        if "FROM codex_replay_references" in text:
            return _VResult(list(self.recent_rows))
        return _VResult([])


def _v_mrow(mapping: dict):
    class _Row:
        def __init__(self, m: dict) -> None:
            self._mapping = dict(m)

    return _Row(mapping)


def _v_patch_replay_repos(
    monkeypatch,
    *,
    keys,
    totals,
    per_key,
    groups,
    groups_total,
    key_by_id=None,
    cohort_by_id=None,
) -> None:
    key_by_id = dict(key_by_id or {})
    cohort_by_id = dict(cohort_by_id or {})

    class _VKeysRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_gateway_key_by_id(self, key_id):
            return key_by_id.get(key_id)

    class _VCohortsRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_cohort_by_id(self, cohort_id):
            return cohort_by_id.get(cohort_id)

    class _VReplayRepo:
        def __init__(self, _session) -> None:
            pass

        async def list_maintenance_key_states(
            self, *, key_id, cohort_id, all_active, limit
        ):
            return list(keys)

        async def inspect_reference_aggregates(
            self, *, key_ids, created_from, created_until, now
        ):
            return totals

        async def inspect_reference_per_key(
            self, *, key_ids, created_from, created_until, now
        ):
            return list(per_key)

        async def inspect_reference_route_groups(
            self, *, key_ids, created_from, created_until, limit
        ):
            return (list(groups), groups_total)

    monkeypatch.setattr(_v_dar, "GatewayKeysRepository", _VKeysRepo)
    monkeypatch.setattr(_v_dar, "CohortsRepository", _VCohortsRepo)
    monkeypatch.setattr(
        _v_dar, "CodexReplayReferencesRepository", _VReplayRepo
    )


def _v_replay_app(fake, monkeypatch, session):
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    monkeypatch.setattr(
        _v_dar, "get_sessionmaker_from_app", lambda _req: lambda: session
    )
    return _app(fake), fake


def test_v_replay_index_positive_ttl(monkeypatch):
    """224-v: the replay index renders the demo banner, the exact
    scope links, and the worker-captured TTL (worker-observed label,
    never the demo process's own settings)."""
    async def run():
        body = _v_ttl_body(3600)
        session = _VReplayFakeSession(_t_meta_row(body), body, [], [])
        _v_patch_replay_repos(
            monkeypatch,
            keys=[],
            totals=_v_NS(
                references=0,
                active_references=0,
                created_min=None,
                created_max=None,
                expiry_min=None,
                expiry_max=None,
            ),
            per_key=[],
            groups=[],
            groups_total=0,
        )
        fake = FakeFacade()
        app, _ = _v_replay_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(V_REPLAY_IDX_URL)
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            assert "NO effect in this demo" in r.text
            assert "HMAC maintenance eligibility is NOT shown" in r.text
            assert (
                'href="/admin/operations/replay-maintenance/all-active"'
                in r.text
            )
            assert "3,600 seconds" in r.text
            assert "worker-observed at copy" in r.text
            # the demo process's own dummy default must never show.
            assert "configured default (0" not in r.text
            assert COPY_OK not in r.text

    asyncio.run(run())


def test_v_replay_scope_key_positive(monkeypatch):
    """224-v: the one-key scope renders the copy-backed summary
    (totals, per-key, groups, bounded safe recent rows, TTL) with the
    visible no-op inspect/preview forms."""
    async def run():
        from datetime import UTC as _V_UTC
        from datetime import datetime as _V_dt

        key_id = uuid.UUID(_V_KEY_UUID)
        route_id = uuid.UUID(_V_ROUTE_UUID)
        cmin = _V_dt(2026, 1, 1, tzinfo=_V_UTC)
        cmax = _V_dt(2026, 1, 3, tzinfo=_V_UTC)
        emax = _V_dt(2026, 12, 31, tzinfo=_V_UTC)
        body = _v_ttl_body(3600)
        session = _VReplayFakeSession(
            _t_meta_row(body),
            body,
            [("message", 3)],
            [
                _v_mrow(
                    {
                        "gateway_key_id": key_id,
                        "item_kind": "message",
                        "provider": "openai",
                        "upstream_model": "gpt-demo",
                        "tool_namespace": None,
                        "tool_name": None,
                        "created_at": cmax,
                        "expires_at": emax,
                    }
                )
            ],
        )
        _v_patch_replay_repos(
            monkeypatch,
            keys=[_v_NS(id=key_id, status="active")],
            totals=_v_NS(
                references=3,
                active_references=2,
                created_min=cmin,
                created_max=cmax,
                expiry_min=cmin,
                expiry_max=emax,
            ),
            per_key=[(key_id, 3, 2, cmin, cmax, cmin, emax)],
            groups=[(route_id, "gpt-demo", 3)],
            groups_total=1,
            key_by_id={key_id: _v_NS(id=key_id, status="active")},
        )
        fake = FakeFacade()
        app, _ = _v_replay_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(
                f"/admin/operations/replay-maintenance/key/{_V_KEY_UUID}"
            )
            assert r.status_code == 200
            assert r.headers["cache-control"] == "private, no-store"
            assert "NO effect in this demo" in r.text
            # copy-backed totals (view-time split of copied expiries).
            assert "3 (active 2, expired 1)" in r.text
            assert "worker-observed at copy time" in r.text
            assert "3,600 seconds" in r.text
            # per-key + group safe links.
            assert f'href="/admin/keys/{_V_KEY_UUID}"' in r.text
            assert f'href="/admin/routes/{_V_ROUTE_UUID}"' in r.text
            assert "gpt-demo" in r.text
            # bounded recent rows: safe metadata only.
            assert "openai" in r.text
            assert "no HMAC digests" in r.text
            # 224-w: the demo help never implies ongoing traffic can
            # change the frozen copy, and every help id renders exactly
            # once on the page.
            assert "Ongoing traffic" not in r.text
            assert "this frozen copy never changes" in r.text
            assert r.text.count('id="preview-expired-help"') == 1
            assert r.text.count('id="preview-reason-help"') == 1
            assert r.text.count('id="preview-bounds-help"') == 1
            # the visible no-op forms stay on the page.
            assert 'action="/admin/operations/replay-maintenance/inspect"' in r.text
            assert 'action="/admin/operations/replay-maintenance/preview"' in r.text
            assert "quiet" in r.text
            # the bounded recent SELECT was issued with its bound
            # parameter (no unbounded transfer).
            recent_sql = [
                (t, p)
                for t, p in session.executed
                if "FROM codex_replay_references" in t and "LIMIT" in t
            ]
            assert len(recent_sql) == 1
            assert recent_sql[0][1]["limit"] == 100
            assert COPY_OK not in r.text

    asyncio.run(run())


def test_v_replay_scope_oversize_and_missing(monkeypatch):
    """224-v: an oversize explicit scope refuses without truncating
    (the bound is stated), and a key absent from the copy is 404."""
    async def run():
        body = _v_ttl_body(3600)
        session = _VReplayFakeSession(_t_meta_row(body), body, [], [])
        _v_patch_replay_repos(
            monkeypatch,
            keys=[_v_NS(id=uuid.uuid4(), status="active") for _ in range(1001)],
            totals=None,
            per_key=[],
            groups=[],
            groups_total=0,
        )
        fake = FakeFacade()
        app, _ = _v_replay_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(V_REPLAY_ALL_URL)
            assert r.status_code == 200
            assert "Scope too large to display" in r.text
            assert "1,001 copied keys exceed the 1,000-key bound" in r.text
            # no reference rows were read for the refused scope.
            ref_sql = [
                t
                for t, _p in session.executed
                if "FROM codex_replay_references" in t
            ]
            assert ref_sql == []

        # A canonical key that is NOT in the copy: fixed 404.
        missing = uuid.uuid4()
        session2 = _VReplayFakeSession(_t_meta_row(body), body, [], [])
        _v_patch_replay_repos(
            monkeypatch,
            keys=[],
            totals=_v_NS(
                references=0,
                active_references=0,
                created_min=None,
                created_max=None,
                expiry_min=None,
                expiry_max=None,
            ),
            per_key=[],
            groups=[],
            groups_total=0,
        )
        app2, fake2 = _v_replay_app(FakeFacade(), monkeypatch, session2)
        async with _client(app2) as client2:
            await _verified_session_client(fake2, client2)
            r = await client2.get(
                f"/admin/operations/replay-maintenance/key/{missing}"
            )
            assert r.status_code == 404

    asyncio.run(run())


def test_v_replay_alias_scope_refusal_400(monkeypatch):
    """224-v: a scope ID equal to an incoming credential of THIS
    request (here the Authorization bearer value) is refused 400 by
    the handler - the fixed refusal, never the value."""
    async def run():
        body = _v_ttl_body(3600)
        session = _VReplayFakeSession(_t_meta_row(body), body, [], [])
        _v_patch_replay_repos(
            monkeypatch,
            keys=[],
            totals=None,
            per_key=[],
            groups=[],
            groups_total=0,
        )
        fake = FakeFacade()
        app, _ = _v_replay_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(
                f"/admin/operations/replay-maintenance/key/{_V_KEY_UUID}",
                headers={"authorization": f"Bearer {_V_KEY_UUID}"},
            )
            assert r.status_code == 400
            assert _V_KEY_UUID not in r.text
            assert "known incoming authentication value" in r.text
            assert COPY_OK not in r.text

    asyncio.run(run())


def test_v_replay_preflight_mismatch_503(monkeypatch):
    """224-v: a present but wrong-bound (or writable) copy is the
    fixed safe 503 on every replay GET - no summary SQL is issued."""
    async def run():
        for db, ro in (("some_other_db", "on"), (COPY_OK, "off")):
            body = _v_ttl_body(3600)
            session = _VReplayFakeSession(
                _t_meta_row(body), body, [], [], db=db, ro=ro
            )
            _v_patch_replay_repos(
                monkeypatch,
                keys=[],
                totals=None,
                per_key=[],
                groups=[],
                groups_total=0,
            )
            fake = FakeFacade()
            app, _ = _v_replay_app(fake, monkeypatch, session)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                for p in (
                    V_REPLAY_IDX_URL,
                    f"/admin/operations/replay-maintenance/key/{_V_KEY_UUID}",
                ):
                    r = await client.get(p)
                    assert r.status_code == 503, (db, ro, p)
                    assert COPY_OK not in r.text
            ref_sql = [
                t
                for t, _p in session.executed
                if "FROM codex_replay_references" in t
                or "demo_display.leaves" in t
            ]
            assert ref_sql == []

    asyncio.run(run())


def test_v_replay_ttl_unavailable_labeled(monkeypatch):
    """224-v: an absent process-config leaf labels the TTL
    unavailable - the page still renders and never shows the demo
    process's own settings value."""
    async def run():
        session = _VReplayFakeSession(None, None, [], [])
        _v_patch_replay_repos(
            monkeypatch,
            keys=[],
            totals=_v_NS(
                references=0,
                active_references=0,
                created_min=None,
                created_max=None,
                expiry_min=None,
                expiry_max=None,
            ),
            per_key=[],
            groups=[],
            groups_total=0,
        )
        fake = FakeFacade()
        app, _ = _v_replay_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(V_REPLAY_IDX_URL)
            assert r.status_code == 200
            assert "unavailable (not recorded in this demo snapshot)" in r.text

    asyncio.run(run())

# ---------------------------------------------------------------------------
# 224-w: demo diagnostics usability + UUID identity withholding
# ---------------------------------------------------------------------------


def test_w_diag_demo_get_lookup_only(monkeypatch):
    """224-w: the demo diagnostics page shows ONLY the working GET
    lookup (with linked help) - the normal POST lookup form is hidden
    in demo while the cleanup no-op control stays visible - and the
    not-found wording makes no expiry/retention suggestion."""

    async def run():
        session = _VDiagFakeSession((0, None, None), [])
        calls: list = []
        _v_patch_diag_lookup(monkeypatch, [], 0, calls)
        fake = FakeFacade()
        app, _ = _v_diag_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(V_DIAG_URL, params={"lookup": "gw-miss-1"})
            assert r.status_code == 200
            # demo not-found wording: frozen snapshot, no retention talk.
            assert (
                "No copied record matches this exact ID in this frozen snapshot."
                in r.text
            )
            assert (
                "it may be expired, never recorded, or outside the retention window"
                not in r.text
            )
            # the working GET selector with linked, visible help.
            assert 'method="get" action="/admin/operations/diagnostics"' in r.text
            assert 'aria-describedby="demo-lookup-id-help"' in r.text
            assert 'id="demo-lookup-id-help"' in r.text
            assert 'aria-describedby="demo-lookup-namespace-help"' in r.text
            assert 'id="demo-lookup-namespace-help"' in r.text
            # the normal POST lookup form is NOT offered in demo.
            assert 'action="/admin/operations/diagnostics/lookup"' not in r.text
            # the cleanup action control remains visible (quiet no-op).
            assert 'action="/admin/operations/diagnostics/cleanup"' in r.text
            assert r.text.count('id="cleanup-reason-help"') == 1
            assert r.text.count('id="cleanup-confirm-help"') == 1

    asyncio.run(run())


def test_w_diag_found_uuid_alias_withheld(monkeypatch):
    """224-w: the FOUND detail withholds gateway_key_id / route_id
    UUIDs whose string is a known incoming (cookie) alias - neither
    value is echoed; without the alias both render as before."""

    async def run():
        key_alias = uuid.uuid4()
        route_alias = uuid.uuid4()
        rec = _v_diag_record(_V_SAFE_ID)
        rec.gateway_key_id = key_alias
        rec.route_id = route_alias
        session = _VDiagFakeSession((1, None, None), [rec])
        calls: list = []
        _v_patch_diag_lookup(monkeypatch, [rec], 1, calls)
        fake = FakeFacade()
        app, _ = _v_diag_app(fake, monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            # no incoming alias: the UUID identities render.
            r0 = await client.get(V_DIAG_URL, params={"lookup": _V_SAFE_ID})
            assert r0.status_code == 200
            assert str(key_alias) in r0.text
            assert str(route_alias) in r0.text
            # the same UUIDs as incoming cookie values: withheld.
            client.cookies.set("w-canary-key", str(key_alias))
            client.cookies.set("w-canary-route", str(route_alias))
            r = await client.get(V_DIAG_URL, params={"lookup": _V_SAFE_ID})
            assert r.status_code == 200
            assert str(key_alias) not in r.text
            assert str(route_alias) not in r.text
            assert "unavailable / unavailable" in r.text

    asyncio.run(run())



# --- 224-w: demo SMTP / key attachments / route config / codex artifacts -------

import json as _w_json  # noqa: E402
from decimal import Decimal as _WDecimal  # noqa: E402
from types import SimpleNamespace as _WNS  # noqa: E402

from slaif_gateway.api import demo_admin_smtp as dsmtp  # noqa: E402
from slaif_gateway.api import demo_admin_key_attachments as dkey  # noqa: E402
from slaif_gateway.api import demo_admin_route_configuration as drcfg  # noqa: E402
from slaif_gateway.api import demo_admin_codex_artifacts as dcodex  # noqa: E402
from slaif_gateway.db.models import (  # noqa: E402
    GatewayKey,
    ModelRoute,
    UsageProfile,
)
from slaif_gateway.services import demo_snapshot_files as _w_dsf  # noqa: E402

W_KEY_UUID = "01234567-89ab-4cde-8f01-23456789abcd"
W_ROUTE_UUID = "99999999-8888-4a77-b666-555544443333"
W_SMTP_URL = "/admin/email-operations/smtp-test"
W_SMTP_APPLY_URL = "/admin/email-operations/smtp-test/apply"
W_CALIB_URL = f"/admin/keys/{W_KEY_UUID}/calibration/summary.json"
W_CONFIG_URL = f"/admin/keys/{W_KEY_UUID}/configuration.json"
W_ROUTE_CFG_URL = f"/admin/routes/{W_ROUTE_UUID}/configuration"
W_CODEX_URL = f"/admin/routes/{W_ROUTE_UUID}/codex-profile"


def test_w_gate_admission_exact_paths():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            for p in (
                W_SMTP_URL,
                W_SMTP_APPLY_URL,
                W_CALIB_URL,
                W_CONFIG_URL,
                W_ROUTE_CFG_URL,
                W_CODEX_URL + "/base",
                W_CODEX_URL + "/profile",
                W_CODEX_URL + "/catalog",
            ):
                r = await client.get(p)
                assert r.status_code == 303, p
                assert r.headers["location"] == "/fakeadmin/login"
            for p in (
                W_SMTP_URL + "/",
                W_SMTP_URL + "s",
                W_SMTP_URL + "/extra",
                "/admin/email-operations/smtp-test-apply",
                W_SMTP_APPLY_URL + "/",
                W_CALIB_URL + "/",
                W_CALIB_URL + "/extra",
                f"/admin/keys/{W_KEY_UUID}/calibration/summary.jsonx",
                W_CONFIG_URL + "/",
                f"/admin/keys/{W_KEY_UUID}/configuration.json/extra",
                W_ROUTE_CFG_URL + "/",
                W_ROUTE_CFG_URL + "x",
                W_CODEX_URL,                 # missing artifact name
                W_CODEX_URL + "/",
                W_CODEX_URL + "/base/",
                W_CODEX_URL + "/blob",       # not the finite vocabulary
                W_CODEX_URL + "/BASE",
                W_CODEX_URL + "/base/extra",
                f"/admin/routes/{W_ROUTE_UUID}/configuration.json",
                f"/admin/keys/{W_KEY_UUID}/calibration/summary.csv",
            ):
                r = await client.get(p)
                assert r.status_code == 404, p
            # the query-free shapes refuse ANY query
            for p in (
                W_SMTP_URL,
                W_SMTP_APPLY_URL,
                W_CONFIG_URL,
                W_ROUTE_CFG_URL,
                W_CODEX_URL + "/base",
            ):
                r = await client.get(p + "?x=1")
                assert r.status_code == 404, p

    asyncio.run(run())


def test_w_gate_calibration_query_law():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            for raw in (
                "",
                "multiplier=3",
                "multiplier=2.5",
                "start_at=2026-01-02T03:04:05Z",
                "start_at=2026-01-02",
                "end_at=2026-01-02T23:59:59+02:00",
                # percent-encoded exactly as the template link emits
                "start_at=2026-01-02T03%3A04%3A05Z",
                "start_at=2026-01-02&end_at=2026-01-03T23%3A59%3A59%2B02%3A00&multiplier=10",
            ):
                r = await client.get(W_CALIB_URL + ("?" + raw if raw else ""))
                assert r.status_code == 303, raw
            for raw in (
                "x=1",                            # unknown
                "start_at=a&start_at=b",          # duplicate
                "multiplier=",                    # empty multiplier
                "multiplier=abc",                 # not decimal
                "multiplier=-1",                  # negative
                "multiplier=1e3",                 # exponent not admitted
                "start_at=%41%42",                # decodes to non-datetime
                "start_at=%ZZ",                   # invalid escape
                "start_at=%2",                    # truncated escape
                "start_at=%C3%A9",                # non-ascii decoded
                "start_at=" + "z" * 65,           # oversized value
                "start_at=2026-01-02" + "&x=1",   # unknown param
            ):
                r = await client.get(W_CALIB_URL + "?" + raw)
                assert r.status_code == 404, raw
            r = await client.get(W_CALIB_URL + "?" + "a" * 257)
            assert r.status_code == 404

    asyncio.run(run())


def test_w_gate_unsafe_methods_quiet_noop():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            _session_cookie(client)
            for p in (
                W_SMTP_URL,
                W_SMTP_APPLY_URL,
                W_CALIB_URL,
                W_CONFIG_URL,
                W_ROUTE_CFG_URL,
                W_CODEX_URL + "/base",
            ):
                for method in ("POST", "PUT", "PATCH", "DELETE"):
                    r = await client.request(
                        method,
                        p,
                        content=b"x" * 200_000,
                        headers={"content-type": "text/garbage"},
                    )
                    assert r.status_code == 204, (method, p)
                    assert r.content == b""
        async with _client(app) as anon:
            r = await anon.post(W_CALIB_URL, content=b"y" * 200_000)
            assert r.status_code == 404

    asyncio.run(run())


# --- 224-w: SMTP GETs ------------------------------------------------------------


def test_w_smtp_form_demo_not_recorded(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        monkeypatch.setattr(
            dsmtp, "get_sessionmaker_from_app", lambda _req: lambda: _WNoopFakeSession(COPY_OK, "on")
        )
        app = _app(fake)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_SMTP_URL)
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "private, no-store"
            text = r.text
            assert "smtp-test-demo-heading" in text
            import re as _re

            norm = _re.sub(r"\s+", " ", text)
            assert "were not recorded in this sanitized copy" in norm
            assert "the demo process's own settings are never used" in norm
            # the styled form with its useful hints stays visible...
            assert 'action="/admin/email-operations/smtp-test/review"' in text
            assert "Test recipient (required)" in text
            # ...clearly labeled a quiet no-op...
            assert "Prepare reviewed test (demo no-op)" in text
            assert "submitting this form does nothing" in norm
            # ...and no readiness fact or credential-shaped setting leaks.
            assert "ENABLE_EMAIL_DELIVERY" not in text
            assert "SMTP_HOST" not in text
            assert "SMTP_FROM" not in text
            assert "unit-test-copy-password" not in text

    asyncio.run(run())


def test_w_smtp_form_preflight_mismatch_503(monkeypatch):
    async def run():
        for db, ro in ((COPY_OK, "off"), ("some_other_db", "on")):
            fake = FakeFacade()
            fake.worker_target_db = COPY_OK
            _preflight_case(monkeypatch, COPY_OK, "on")
            session = _WNoopFakeSession(db, ro)
            monkeypatch.setattr(
                dsmtp, "get_sessionmaker_from_app", lambda _req: lambda: session
            )
            app = _app(fake)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                for url in (W_SMTP_URL, W_SMTP_APPLY_URL):
                    r = await client.get(url)
                    assert r.status_code == 503, (db, ro, url)
                    assert r.headers.get("cache-control") == "private, no-store"
                    assert dsmtp._SAFE_UNAVAILABLE in r.text
                    assert COPY_OK not in r.text

    asyncio.run(run())


def test_w_smtp_apply_recovery_demo(monkeypatch):
    async def run():
        fake = FakeFacade()
        fake.worker_target_db = COPY_OK
        _preflight_case(monkeypatch, COPY_OK, "on")
        monkeypatch.setattr(
            dsmtp, "get_sessionmaker_from_app", lambda _req: lambda: _WNoopFakeSession(COPY_OK, "on")
        )
        app = _app(fake)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_SMTP_APPLY_URL)
            assert r.status_code == 200
            import re as _re

            norm = _re.sub(r"\s+", " ", r.text)
            # the fixed no-send notice + the demo banner.
            assert "This page only accepts the reviewed test submission" in r.text
            assert "no reviewed test content is shown" in norm
            assert "no live one-use token" in norm
            # no reviewed content, no outcome, no live deadline.
            assert "Reviewed test content" not in r.text
            assert "Outcome" not in r.text
            assert "per-attempt deadline" not in r.text

    asyncio.run(run())


def test_w_smtp_handler_without_demo_state_404():
    async def run():
        app = _app(FakeFacade())
        request = _bare_request(app)
        assert (await dsmtp.demo_smtp_test_form(request)).status_code == 404
        assert (await dsmtp.demo_smtp_test_apply_recovery(request)).status_code == 404

    asyncio.run(run())


class _WNoopFakeSession:
    """A request-local copy session that runs only the recheck
    scalars (the SMTP pages record no further copy reads)."""

    def __init__(self, db, ro) -> None:
        self.db = db
        self.ro = ro
        self.executed = []

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def scalar(self, clause):
        text = str(clause)
        if "current_database" in text:
            return self.db
        return self.ro

    async def execute(self, clause, params=None):
        self.executed.append(str(clause))
        return _WResult([])


# --- 224-w: key JSON attachments -------------------------------------------------


class _WResult:
    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        if len(self._rows) > 1:
            raise RuntimeError("multiple rows")
        return self._rows[0] if self._rows else None

    def scalars(self):
        outer = self

        class _S:
            def all(self):
                return [row[0] if isinstance(row, tuple) else row for row in outer._rows]

        return _S()


class _WKeyFakeSession:
    """Recheck scalars + ``session.get`` (key existence) + ``execute``
    (the calibration service's admin-detail key read and usage-profile
    list). Every statement is recorded for the seam assertions."""

    def __init__(self, key_obj, profile_rows, db, ro) -> None:
        self.key_obj = key_obj
        self.profile_rows = profile_rows
        self.db = db
        self.ro = ro
        self.get_calls: list[str] = []
        self.executed: list[str] = []

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def scalar(self, clause):
        text = str(clause)
        if "current_database" in text:
            return self.db
        return self.ro

    async def get(self, model, ident):
        self.get_calls.append(model.__name__)
        if self.key_obj is not None and ident == self.key_obj.id:
            return self.key_obj
        return None

    async def execute(self, stmt, params=None):
        text = str(stmt)
        self.executed.append(text)
        if "usage_profiles" in text:
            return _WResult(self.profile_rows)
        return _WResult([self.key_obj] if self.key_obj is not None else [])


def _w_key_app(monkeypatch, session):
    fake = FakeFacade()
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    monkeypatch.setattr(
        dkey, "get_sessionmaker_from_app", lambda _req: lambda: session
    )
    return _app(fake), fake


def _w_trusted_key(**over):
    kw = dict(
        id=uuid.UUID(W_KEY_UUID),
        public_key_id="pk-w-1",
        status="active",
        key_purpose="trusted_calibration",
        capability_policy_mode="trusted_calibration_discovery",
    )
    kw.update(over)
    return GatewayKey(**kw)


def _w_profile_rows():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return [
        UsageProfile(
            id=uuid.uuid4(),
            gateway_key_id=uuid.UUID(W_KEY_UUID),
            created_at=now,
            endpoint_path="/v1/chat/completions",
            provider="openai",
            requested_model="gpt-4.1-mini",
            resolved_upstream_model="gpt-4.1-mini",
            provider_host="api.openai.com",
            provider_endpoint_path="/chat/completions",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            reasoning_tokens=None,
            cached_tokens=10,
            slaif_calculated_cost=_WDecimal("0.001"),
            provider_reported_cost=None,
            cost_currency="USD",
            cost_source="slaif_calculated",
            profile_metadata={},
        )
    ]


def test_w_key_config_positive_attachment(monkeypatch):
    async def run():
        key = _w_trusted_key()
        session = _WKeyFakeSession(key, [], COPY_OK, "on")
        app, fake = _w_key_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CONFIG_URL)
            assert r.status_code == 200
            assert r.headers["content-type"] == "application/json"
            assert r.headers["content-disposition"] == (
                'attachment; filename="slaif-key-configuration-pk-w-1.json"'
            )
            assert "no-store" in r.headers["cache-control"]
            assert r.headers["x-content-type-options"] == "nosniff"
            doc = _w_json.loads(r.content)
            assert doc["allowed_models"] == []
            assert doc["allow_all_models"] is False
        # the key was read ONLY through the copy session's get().
        assert session.get_calls == ["GatewayKey"]
        assert session.executed == []

    asyncio.run(run())


def test_w_key_config_missing_key_404(monkeypatch):
    async def run():
        session = _WKeyFakeSession(None, [], COPY_OK, "on")
        app, fake = _w_key_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CONFIG_URL)
            assert r.status_code == 404
            assert r.content == b"Not Found"

    asyncio.run(run())


def test_w_key_config_alias_whole_refusal_no_echo(monkeypatch):
    # A copied allowed model that equals an incoming cookie credential:
    # the WHOLE attachment is refused, no partial substitution, no echo.
    canary = "w-canary-model-token-123"

    async def run():
        key = _w_trusted_key(allowed_models=[canary])
        session = _WKeyFakeSession(key, [], COPY_OK, "on")
        app, fake = _w_key_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            client.cookies.set("w-canary-cookie", canary)
            r = await client.get(W_CONFIG_URL)
            assert r.status_code == 400
            assert canary not in r.text
            assert dkey._SAFE_REFUSAL in r.text

    asyncio.run(run())


def test_w_key_config_oversized_refused_not_truncated(monkeypatch):
    async def run():
        monkeypatch.setattr(dkey, "_MAX_ATTACHMENT_BYTES", 10)
        key = _w_trusted_key()
        session = _WKeyFakeSession(key, [], COPY_OK, "on")
        app, fake = _w_key_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CONFIG_URL)
            assert r.status_code == 400
            assert dkey._SAFE_OVERSIZED in r.text

    asyncio.run(run())


def test_w_key_calib_positive_copied_data(monkeypatch):
    async def run():
        key = _w_trusted_key()
        session = _WKeyFakeSession(key, _w_profile_rows(), COPY_OK, "on")
        app, fake = _w_key_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CALIB_URL, params={"multiplier": "3"})
            assert r.status_code == 200
            assert r.headers["content-type"] == "application/json"
            assert r.headers["content-disposition"] == (
                f'attachment; filename="slaif-calibration-summary-{W_KEY_UUID}.json"'
            )
            assert "no-store" in r.headers["cache-control"]
            assert r.headers["x-content-type-options"] == "nosniff"
            doc = _w_json.loads(r.content)
            summary = doc["summary"]
            assert summary["observed_request_count"] == 1
            assert summary["public_key_id"] == "pk-w-1"
            assert doc["is_empty"] is False
        # copy reads: existence get() + the service's admin-detail key
        # select + the usage-profile list.
        assert session.get_calls == ["GatewayKey"]
        assert len(session.executed) == 2
        assert any("usage_profiles" in t for t in session.executed)

    asyncio.run(run())


def test_w_key_calib_not_trusted_400(monkeypatch):
    async def run():
        key = _w_trusted_key(
            key_purpose="standard", capability_policy_mode="standard"
        )
        session = _WKeyFakeSession(key, _w_profile_rows(), COPY_OK, "on")
        app, fake = _w_key_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CALIB_URL, params={"multiplier": "3"})
            assert r.status_code == 400
            assert dkey._SAFE_INPUT_REFUSAL in r.text

    asyncio.run(run())


def test_w_key_calib_semantic_input_400_before_copy(monkeypatch):
    # The gate admits strict GRAMMAR; the handler re-runs the normal
    # STRICT parsers. A grammatical but impossible date is refused with
    # a fixed 400 BEFORE any copy read.
    async def run():
        session = _WKeyFakeSession(_w_trusted_key(), [], COPY_OK, "on")
        app, fake = _w_key_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CALIB_URL, params={"start_at": "2026-13-99"})
            assert r.status_code == 400
            assert "2026-13-99" not in r.text
            assert session.get_calls == []
            assert session.executed == []

    asyncio.run(run())


def test_w_key_calib_multiplier_bound_400(monkeypatch):
    # multiplier=11 passes the gate decimal grammar; the normal service
    # bound (1.0..10.0) refuses it with a fixed 400 after the copy
    # binding (the input itself was strict-valid).
    async def run():
        key = _w_trusted_key()
        session = _WKeyFakeSession(key, [], COPY_OK, "on")
        app, fake = _w_key_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CALIB_URL, params={"multiplier": "11"})
            assert r.status_code == 400
            assert dkey._SAFE_INPUT_REFUSAL in r.text
            assert "11" not in r.text

    asyncio.run(run())


def test_w_key_calib_alias_whole_refusal_no_echo(monkeypatch):
    canary = "w-canary-provider-777"

    async def run():
        key = _w_trusted_key()
        rows = _w_profile_rows()
        rows[0].provider = canary
        session = _WKeyFakeSession(key, rows, COPY_OK, "on")
        app, fake = _w_key_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            client.cookies.set("w-canary-cookie", canary)
            r = await client.get(W_CALIB_URL, params={"multiplier": "3"})
            assert r.status_code == 400
            assert canary not in r.text
            assert dkey._SAFE_REFUSAL in r.text

    asyncio.run(run())


def test_w_key_path_identity_alias_refused_before_copy(monkeypatch):
    # The path key UUID itself as an incoming cookie value: fixed 400
    # BEFORE any copy binding (the replay-page alias law).
    async def run():
        session = _WKeyFakeSession(_w_trusted_key(), [], COPY_OK, "on")
        app, fake = _w_key_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            client.cookies.set("w-canary-uuid", W_KEY_UUID)
            r1 = await client.get(W_CONFIG_URL)
            r2 = await client.get(W_CALIB_URL, params={"multiplier": "3"})
            assert r1.status_code == 400
            assert r2.status_code == 400
            assert W_KEY_UUID not in r1.text
            assert session.get_calls == []
            assert session.executed == []

    asyncio.run(run())


def test_w_key_preflight_mismatch_503(monkeypatch):
    async def run():
        for db, ro in ((COPY_OK, "off"), ("some_other_db", "on")):
            session = _WKeyFakeSession(_w_trusted_key(), [], db, ro)
            app, fake = _w_key_app(monkeypatch, session)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r1 = await client.get(W_CONFIG_URL)
                r2 = await client.get(W_CALIB_URL, params={"multiplier": "3"})
                assert r1.status_code == 503, (db, ro)
                assert r2.status_code == 503, (db, ro)
                assert dkey._SAFE_UNAVAILABLE in r1.text
                assert session.get_calls == []
                assert session.executed == []

    asyncio.run(run())


# --- 224-w: route configuration form ---------------------------------------------


_W_PROFILE_A = "demo-profile-" + "a" * 24
_W_PROFILE_B = "demo-profile-" + "b" * 24


def _w_completion_leaf_body(profiles):
    doc = {
        "schema": _w_dsf.DEMO_SCHEMA_VERSION,
        "kind": _w_dsf.KIND_COMPLETION_CHOICES,
        "schema_version": 1,
        "profiles": list(profiles),
    }
    return _w_json.dumps(doc, sort_keys=True).encode("utf-8")


def _w_completion_meta(body, **corrupt):
    import hashlib

    row = dict(
        kind=_w_dsf.KIND_COMPLETION_CHOICES,
        byte_count=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        captured_at=1_700_000_000.0,
        actual_bytes=len(body),
    )
    row.update(corrupt)
    return (row["kind"], row["byte_count"], row["sha256"], row["captured_at"], row["actual_bytes"])


class _WRouteFakeSession:
    """Recheck scalars + ``session.get`` (the copied route) + ``execute``
    (the choice selects and the completion-leaf metadata/body)."""

    def __init__(self, route_obj, provider_rows, completion_meta, completion_body, db, ro):
        self.route_obj = route_obj
        self.provider_rows = provider_rows
        self.completion_meta = completion_meta
        self.completion_body = completion_body
        self.db = db
        self.ro = ro
        self.get_calls: list[str] = []
        self.executed: list[tuple[str, dict]] = []

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def scalar(self, clause):
        text = str(clause)
        if "current_database" in text:
            return self.db
        return self.ro

    async def get(self, model, ident):
        self.get_calls.append(model.__name__)
        if self.route_obj is not None and ident == self.route_obj.id:
            return self.route_obj
        return None

    async def execute(self, stmt, params=None):
        text = str(stmt)
        params = dict(params or {})
        self.executed.append((text, params))
        if text.lstrip().startswith("SELECT body"):
            rows = [(b,) for b in self.completion_body]
        elif "demo_display.leaves" in text:
            rows = self.completion_meta
        elif "provider_configs" in text:
            rows = self.provider_rows
        else:
            rows = []
        return _WResult(rows)


def _w_route_app(monkeypatch, session):
    fake = FakeFacade()
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    monkeypatch.setattr(
        drcfg, "get_sessionmaker_from_app", lambda _req: lambda: session
    )
    return _app(fake), fake


def _w_route_obj(**over):
    kw = dict(
        id=uuid.UUID(W_ROUTE_UUID),
        requested_model="gpt-4.1-mini",
        match_type="exact",
        endpoint="/v1/chat/completions",
        provider="openai",
        upstream_model=None,
        priority=100,
        notes="route note",
        capabilities={"chat_completions": {}},
    )
    kw.update(over)
    return ModelRoute(**kw)


def test_w_route_config_positive_copy_backed(monkeypatch):
    body = _w_completion_leaf_body([_W_PROFILE_A, _W_PROFILE_B])
    provider_rows = [
        _WNS(id=uuid.uuid4(), provider="openai", display_name="OpenAI", enabled=True)
    ]
    session = _WRouteFakeSession(
        _w_route_obj(), provider_rows, [_w_completion_meta(body)], [body], COPY_OK, "on"
    )
    app, fake = _w_route_app(monkeypatch, session)

    async def run():
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_ROUTE_CFG_URL)
            assert r.status_code == 200
            assert r.headers.get("cache-control") == "private, no-store"
            import re as _re

            norm = _re.sub(r"\s+", " ", r.text)
            # persistent frozen/no-op cue + copied-fact provenance.
            assert "FROZEN copied rows" in norm
            assert "no plan is prepared, nothing is applied" in norm
            assert "sanitized capture of the source operator directory" in norm
            # copy-backed provider choice rendered...
            assert "OpenAI" in r.text
            # ...and the sanitized completion choices.
            assert _W_PROFILE_A in r.text
            assert _W_PROFILE_B in r.text
            # the visible action control stays.
            assert f'action="/admin/routes/{W_ROUTE_UUID}/configuration/plan"' in r.text

    asyncio.run(run())
    # the metadata-first leaf law: metadata query, then the bounded
    # body query re-asserting every condition as bound parameters.
    leaf_queries = [
        (t, p) for t, p in session.executed if "demo_display.leaves" in t
    ]
    assert len(leaf_queries) == 2
    meta_text, meta_params = leaf_queries[0]
    assert "octet_length(body)" in meta_text
    assert meta_params == {"name": drcfg._COMPLETION_CHOICES_NAME}
    body_text, body_params = leaf_queries[1]
    assert body_text.lstrip().startswith("SELECT body")
    assert body_params == {
        "name": drcfg._COMPLETION_CHOICES_NAME,
        "cap": _w_dsf._COMPLETION_PROFILE_MAX_BYTES,
        "size": len(body),
        "digest": session.completion_meta[0][2],
        "kind": _w_dsf.KIND_COMPLETION_CHOICES,
    }
    # the route came from the copy session's get().
    assert session.get_calls == ["ModelRoute"]


def test_w_route_config_completion_unconfigured(monkeypatch):
    session = _WRouteFakeSession(
        _w_route_obj(), [], [], [], COPY_OK, "on"
    )
    app, fake = _w_route_app(monkeypatch, session)

    async def run():
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_ROUTE_CFG_URL)
            assert r.status_code == 200
            import re as _re

            norm = _re.sub(r"\s+", " ", r.text)
            assert "recorded no operator completion profiles" in norm
            assert "package defaults" in norm

    asyncio.run(run())
    # absent leaf: the metadata query ran, the body query never did.
    leaf_queries = [t for t, _ in session.executed if "demo_display.leaves" in t]
    assert len(leaf_queries) == 1


def test_w_route_config_completion_corrupt_503(monkeypatch):
    body = _w_completion_leaf_body([_W_PROFILE_A])
    async def run():
        for bad_meta in (
            _w_completion_meta(body, kind="Completion_Choices"),
            _w_completion_meta(body, byte_count=len(body) + 1,
                               actual_bytes=len(body) + 1),
            _w_completion_meta(body, actual_bytes=len(body) + 1),
            _w_completion_meta(body, sha256="Z" * 64),
            (None, None, None, None, None),
        ):
            session = _WRouteFakeSession(
                _w_route_obj(), [], [bad_meta], [body], COPY_OK, "on"
            )
            app, fake = _w_route_app(monkeypatch, session)
            async with _client(app) as client:
                await _verified_session_client(fake, client)
                r = await client.get(W_ROUTE_CFG_URL)
                assert r.status_code == 503, bad_meta
                assert drcfg._SAFE_UNAVAILABLE in r.text
                assert "payload" not in r.text

    asyncio.run(run())


def test_w_route_config_missing_route_404(monkeypatch):
    session = _WRouteFakeSession(None, [], [], [], COPY_OK, "on")
    app, fake = _w_route_app(monkeypatch, session)

    async def run():
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_ROUTE_CFG_URL)
            assert r.status_code == 404
            assert r.content == b"Not Found"

    asyncio.run(run())


def test_w_route_config_selected_completion_hydrated(monkeypatch):
    # The copied route's completion profile (a sanitizer-remapped id)
    # is hydrated into the choice list even when the captured list does
    # not contain it.
    selected = "demo-profile-" + "c" * 24
    body = _w_completion_leaf_body([_W_PROFILE_A])
    route = _w_route_obj(
        capabilities={
            "completion_service": {"version": 1, "profile": selected}
        }
    )
    session = _WRouteFakeSession(
        route, [], [_w_completion_meta(body)], [body], COPY_OK, "on"
    )
    app, fake = _w_route_app(monkeypatch, session)

    async def run():
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_ROUTE_CFG_URL)
            assert r.status_code == 200
            assert selected in r.text
            assert _W_PROFILE_A in r.text

    asyncio.run(run())


# --- 224-w: inert Codex reference artifacts --------------------------------------


def _w_codex_artifacts(catalog=True):
    return _WNS(
        base_config_toml="BASE-TOML",
        profile_config_toml="PROFILE-TOML",
        profile="slaif",
        model_catalog_json='{"models": []}' if catalog else None,
        model_catalog_target="slaif-model-catalog.json" if catalog else None,
        profile_config_self_contained=False,
    )


def _w_qual_result(route_id, *, state="protocol_qualified", profile_id="w-qual-1"):
    from slaif_gateway.services.codex_qualification import (
        CodexQualificationResult,
    )

    return CodexQualificationResult(
        state=state,
        requested_model="gpt-4.1-mini",
        provider="openai",
        endpoint="/v1/chat/completions",
        route_id=route_id,
        paired_route_id=None,
        reason_codes=(),
        profile_id=profile_id,
        metadata_version=2,
    )


def _w_fake_qual_service(monkeypatch, results):
    class _FakeQualService:
        def __init__(self, **kw) -> None:
            pass

        async def inspect(self, **kw):
            return list(results)

    monkeypatch.setattr(dcodex, "CodexQualificationService", _FakeQualService)


def _w_codex_app(monkeypatch, session):
    fake = FakeFacade()
    fake.worker_target_db = COPY_OK
    _preflight_case(monkeypatch, COPY_OK, "on")
    monkeypatch.setattr(
        dcodex, "get_sessionmaker_from_app", lambda _req: lambda: session
    )
    return _app(fake), fake


def test_w_codex_artifacts_eligible_inert(monkeypatch):
    calls = []

    def _fake_render(base_url, profile_id):
        calls.append((base_url, profile_id))
        return _w_codex_artifacts(catalog=True)

    monkeypatch.setattr(dcodex, "render_codex_profile", _fake_render)
    route = _w_route_obj()
    _w_fake_qual_service(monkeypatch, [_w_qual_result(route.id)])
    session = _WRouteFakeSession(route, [], [], [], COPY_OK, "on")
    app, fake = _w_codex_app(monkeypatch, session)

    async def run():
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CODEX_URL + "/base")
            assert r.status_code == 200
            assert r.content == b"BASE-TOML"
            assert r.headers["content-type"].startswith("text/plain")
            assert r.headers["content-disposition"] == (
                'attachment; filename="codex-provider.config.reference.toml"'
            )
            assert "no-store" in r.headers["cache-control"]
            assert r.headers["x-content-type-options"] == "nosniff"
            r = await client.get(W_CODEX_URL + "/profile")
            assert r.status_code == 200
            assert r.content == b"PROFILE-TOML"
            assert r.headers["content-disposition"] == (
                'attachment; filename="slaif.config.reference.toml"'
            )
            r = await client.get(W_CODEX_URL + "/catalog")
            assert r.status_code == 200
            assert r.content == b'{"models": []}'
            assert r.headers["content-type"] == "application/json"
            assert r.headers["content-disposition"] == (
                'attachment; filename="slaif-model-catalog.reference.json"'
            )
            # the normal process settings PUBLIC_BASE_URL is NEVER read:
            # the SAME pure renderer got the reserved inert URL only.
            assert all(base == "https://api.slaif.invalid/v1" for base, _ in calls)
            assert all(pid == "w-qual-1" for _, pid in calls)

    asyncio.run(run())
    # the inert URL is accepted by the SAME validator the renderer uses
    # (a reserved non-routable placeholder, no live host).
    from slaif_gateway.services.codex_qualification import (
        validate_codex_gateway_base_url,
    )

    assert validate_codex_gateway_base_url("https://api.slaif.invalid/v1") == (
        "https://api.slaif.invalid/v1"
    )


def test_w_codex_artifacts_no_catalog_404(monkeypatch):
    monkeypatch.setattr(dcodex, "render_codex_profile",
                        lambda _b, _p: _w_codex_artifacts(catalog=False))
    route = _w_route_obj()
    _w_fake_qual_service(monkeypatch, [_w_qual_result(route.id)])
    session = _WRouteFakeSession(route, [], [], [], COPY_OK, "on")
    app, fake = _w_codex_app(monkeypatch, session)

    async def run():
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            assert (await client.get(W_CODEX_URL + "/base")).status_code == 200
            r = await client.get(W_CODEX_URL + "/catalog")
            assert r.status_code == 404
            assert r.content == b"Not Found"

    asyncio.run(run())


def test_w_codex_artifacts_ineligible_or_missing_404(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("renderer must not run for ineligible routes")

    monkeypatch.setattr(dcodex, "render_codex_profile", _boom)

    async def run():
        # not ready
        route = _w_route_obj()
        _w_fake_qual_service(
            monkeypatch,
            [_w_qual_result(route.id, state="not_declared", profile_id=None)],
        )
        session = _WRouteFakeSession(route, [], [], [], COPY_OK, "on")
        app, fake = _w_codex_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CODEX_URL + "/base")
            assert r.status_code == 404
        # ready but no registered profile id
        route = _w_route_obj()
        _w_fake_qual_service(
            monkeypatch,
            [_w_qual_result(route.id, profile_id=None)],
        )
        session = _WRouteFakeSession(route, [], [], [], COPY_OK, "on")
        app, fake = _w_codex_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CODEX_URL + "/base")
            assert r.status_code == 404
        # no qualification result for this route
        route = _w_route_obj()
        _w_fake_qual_service(monkeypatch, [])
        session = _WRouteFakeSession(route, [], [], [], COPY_OK, "on")
        app, fake = _w_codex_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CODEX_URL + "/base")
            assert r.status_code == 404
        # missing route
        _w_fake_qual_service(monkeypatch, [])
        session = _WRouteFakeSession(None, [], [], [], COPY_OK, "on")
        app, fake = _w_codex_app(monkeypatch, session)
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CODEX_URL + "/base")
            assert r.status_code == 404

    asyncio.run(run())


def test_w_codex_artifacts_render_failure_404(monkeypatch):
    def _boom(*a, **k):
        raise ValueError("unknown profile")

    monkeypatch.setattr(dcodex, "render_codex_profile", _boom)
    route = _w_route_obj()
    _w_fake_qual_service(monkeypatch, [_w_qual_result(route.id, profile_id="w-bad")])
    session = _WRouteFakeSession(route, [], [], [], COPY_OK, "on")
    app, fake = _w_codex_app(monkeypatch, session)

    async def run():
        async with _client(app) as client:
            await _verified_session_client(fake, client)
            r = await client.get(W_CODEX_URL + "/profile")
            assert r.status_code == 404
            assert "Traceback" not in r.text

    asyncio.run(run())

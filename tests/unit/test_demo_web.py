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
                # action GETs and download GETs stay 404.
                f"/admin/keys/{KEY_UUID}/edit",
                f"/admin/templates/{KEY_UUID}/edit",
                f"/admin/routes/{KEY_UUID}/configuration",
                f"/admin/routes/{KEY_UUID}/codex-profile/base",
                f"/admin/routes/{KEY_UUID}/codex-profile/profile",
                f"/admin/routes/{KEY_UUID}/codex-profile/catalog",
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
    """224-i: demo route detail must not render Codex profile artifacts
    (no localhost/live base URL, no profile TOML, no download links) and
    must show the demo-only hint; normal admin still renders them."""
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
        # DEMO: render_codex_profile must not run at all (a profile from
        # the neutral localhost base URL would be misleading) and the
        # hint replaces the artifact block.
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
        assert "Codex profile artifacts are not rendered in this snapshot" in html
        assert "localhost:8000" not in html
        assert "codex-profile" not in html
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

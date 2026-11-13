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
session validation, logout revocation, /v1+/admin absence, the
login attempt bound, and web-path import isolation (no privileged
worker module in the web process).
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

    def _request(self) -> DemoSnapshotRequestProjection:
        """Live projection: state/gen/expiry reflect current facade knobs."""
        now = datetime.now(timezone.utc)
        return DemoSnapshotRequestProjection(
            id=REQ,
            account_id=ACC,
            credential_generation=self.request_gen,
            state=self.request_state,
            failure_code=None,
            worker_job_id=None,
            worker_target_db=None,
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


def _app(fake: FakeFacade):
    return create_demo_app(_config(), facade=fake)


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


def test_demo_app_routes_are_fakeadmin_only():
    app = _app(FakeFacade())
    paths = {getattr(r, "path", "") for r in app.routes}
    for p in paths:
        assert p == "" or p.startswith(
            ("/fakeadmin", "/docs", "/openapi.json", "/redoc")
        ), p
    assert "/v1" not in paths
    assert "/admin" not in paths


def test_disabled_env_app_refuses_without_env_vars(monkeypatch):
    monkeypatch.delenv("DEMO_WEB_ENABLED", raising=False)
    with pytest.raises(DemoWebConfigError):
        create_demo_app(None)


def test_v1_and_admin_404_on_demo_app():
    async def run():
        app = _app(FakeFacade())
        async with _client(app) as client:
            assert (await client.get("/v1/models")).status_code == 404
            assert (await client.get("/admin")).status_code == 404

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
            r = await client.get("/fakeadmin/login")
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
            r = await client.get("/fakeadmin/login")
            client.cookies["slaif_demo_csrf"] = stale
            r = await client.post(
                "/fakeadmin/login",
                data={"username": "op", "password": "good-pw", "csrf": stale},
            )
            assert r.status_code == 400

    asyncio.run(run())


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
            r = await client.get("/fakeadmin/wait")
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
            r = await client.get("/fakeadmin/wait")
            assert fake.issued == 0

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
            r = await client.get("/fakeadmin/ready")  # 303 to login, no csrf set
            r = await client.get("/fakeadmin/login")
            csrf = r.cookies["slaif_demo_csrf"]
            r = await client.post("/fakeadmin/logout", data={"csrf": csrf})
            assert r.status_code == 303
            assert fake.revoked == 0

    asyncio.run(run())

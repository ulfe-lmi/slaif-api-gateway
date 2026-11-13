"""Objective 224-c: the isolated demo web entry (default OFF).

A purpose-built, STANDALONE ASGI app (``create_demo_app``) serving ONLY
the ``/fakeadmin`` demo entry surface (login / wait / ready / logout)
plus the packaged static assets it needs. It does NOT import or call
``main.create_app`` or its lifespan (which would bootstrap provider
modules, normal routes and normal database/Redis services); it
registers NO ``/v1``, ``/admin`` or ordinary admin routes, so those
paths are unreachable on this process.

The demo app's ONLY database connection is a dedicated demo WEB
control-role connection (the reviewed 224-a column grants), with an
explicit no-TLS ``ssl=False`` stage boundary (the operator must keep
the control endpoint on a trusted private loopback/Compose network;
this stage does not support verified remote DB TLS). It never holds
the owner ``DATABASE_URL``, the 224-b worker control credentials,
provider credentials, the Redis broker, the worker custody directory
or the catalog seal key, and a web request NEVER spawns or imports
the privileged snapshot worker (the 224-b ``process-request`` CLI is
the separate-process handoff for this stage).

Default OFF: nothing here runs unless ``DEMO_WEB_ENABLED=true`` and
the complete demo-web configuration is present; a misconfigured
enabled demo refuses to start with a safe finite error.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import time
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from slaif_gateway.db.repositories.fake_admin_accounts import (
    FakeAdminAccountsRepository,
    FakeAdminAccountFacts,
    FakeAdminLoginCredential,
)
from slaif_gateway.services.demo_web_control import (
    DemoSessionIssuedResult,
    DemoSnapshotRequestProjection,
    DemoWebControlService,
    DemoWebSessionProjection,
)

__all__ = [
    "DemoWebConfig",
    "DemoWebError",
    "DemoWebConfigError",
    "DemoWebFacade",
    "PgDemoWebFacade",
    "create_demo_app",
    "make_signed_payload",
    "verify_signed_payload",
    "CSRF_TTL_S",
    "PENDING_TTL_S",
    "LOGIN_FIELD_MAX",
    "LOGIN_ATTEMPT_MAX",
    "LOGIN_ATTEMPT_WINDOW_S",
]


class DemoWebError(Exception):
    """Safe demo-web error: a finite code + safe message only."""

    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


# --- independent configuration (default OFF) -------------------------------------


# Closed PostgreSQL identifier law (same shape as the 224-a/224-b
# role/database validation): no interpolation escape possible.
_IDENTIFIER_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}")

# Finite demo-web bounds (single demo process, not a public service).
LOGIN_FIELD_MAX = 128  # username / password input lengths
LOGIN_ATTEMPT_MAX = 20  # failed logins per window...
LOGIN_ATTEMPT_WINDOW_S = 300.0  # ...per this bounded window
CSRF_TTL_S = 600  # login/logout form token lifetime
PENDING_TTL_S = 900  # short-lived wait cookie lifetime
# Finite inbound token bound: signed cookies are well under this; a
# longer value is refused BEFORE any decode (no allocation blowup).
SIGNED_TOKEN_MAX_LEN = 512


class DemoWebConfigError(DemoWebError):
    """Configuration is missing/invalid (safe message, no value echo)."""


@dataclass(frozen=True, slots=True)
class DemoWebConfig:
    """Small independent demo-web configuration object.

    Deliberately NOT part of the gateway ``Settings``: the demo web
    process must stay bootable (and auditable) without the ordinary
    application configuration surface. ``control_password`` is
    ``repr=False`` and is never rendered by any helper in this module.
    """

    enabled: bool
    control_host: str = ""
    control_port: int = 5432
    control_database: str = ""
    control_user: str = ""
    control_password: str = field(repr=False, default="")
    cookie_secret: str = field(repr=False, default="")

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "DemoWebConfig":
        """Read the demo-web settings from the environment.

        Missing values are safe defaults (disabled). When ``enabled``
        is true, the complete control-connection set and a strong
        cookie secret are REQUIRED (fail closed, no value echo).
        """
        env = os.environ if environ is None else environ

        def _str(name: str) -> str:
            return str(env.get(name, "") or "").strip()

        enabled_raw = _str("DEMO_WEB_ENABLED").lower()
        enabled = enabled_raw in ("1", "true", "yes", "on")
        port_raw = _str("DEMO_WEB_CONTROL_PORT")
        port = 5432
        port_ok = True
        if port_raw:
            try:
                port = int(port_raw)
            except ValueError:
                port, port_ok = 0, False
        if enabled and not port_ok:
            raise DemoWebConfigError(
                "demo_web_misconfigured",
                "The demo web entry has an invalid control port "
                "configuration.",
            )
        config = cls(
            enabled=enabled,
            control_host=_str("DEMO_WEB_CONTROL_HOST"),
            control_port=port,
            control_database=_str("DEMO_WEB_CONTROL_DATABASE"),
            control_user=_str("DEMO_WEB_CONTROL_USER"),
            control_password=_str("DEMO_WEB_CONTROL_PASSWORD"),
            cookie_secret=_str("DEMO_WEB_COOKIE_SECRET"),
        )
        if config.enabled:
            config._validate_enabled()
        return config

    def _validate_enabled(self) -> None:
        problems: list[str] = []
        if not self.control_host:
            problems.append("host")
        if not (1 <= self.control_port <= 65535):
            problems.append("port")
        if _IDENTIFIER_RE.fullmatch(self.control_database) is None:
            problems.append("database")
        if _IDENTIFIER_RE.fullmatch(self.control_user) is None:
            problems.append("user")
        if not self.control_password:
            problems.append("password")
        if len(self.cookie_secret) < 32:
            problems.append("cookie-secret")
        if problems:
            raise DemoWebConfigError(
                "demo_web_misconfigured",
                "The demo web entry is missing or has invalid "
                + ", ".join(problems)
                + " configuration.",
            )

    def engine_url(self) -> str:
        from urllib.parse import quote

        return (
            "postgresql+asyncpg://"
            f"{quote(self.control_user, safe='')}:"
            f"{quote(self.control_password, safe='')}"
            f"@{self.control_host}:{self.control_port}/"
            f"{quote(self.control_database, safe='')}"
        )


# --- signed-value helpers (independent cookie-signing secret) ---------------------


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign(secret: str, purpose: str, payload: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), f"{purpose}:{payload}".encode("utf-8"), hashlib.sha256
    ).digest()
    return _b64encode(digest)


def make_signed_payload(
    secret: str,
    purpose: str,
    payload: str,
    ttl_s: int,
    *,
    now: float | None = None,
) -> str:
    """Signed, expiring token: ``b64(ts:payload).sig`` (HMAC-SHA256)."""
    issued = int(time.time() if now is None else now)
    body = _b64encode(f"{issued}:{payload}".encode("utf-8"))
    return f"{body}.{_sign(secret, purpose, body)}"


def verify_signed_payload(
    secret: str,
    purpose: str,
    token: str | None,
    ttl_s: int,
    *,
    now: float | None = None,
) -> str | None:
    """Verify and return the payload, or ``None`` (never raises).

    Constant-time signature comparison; finite age bound; the payload
    is only returned when every check passes.
    """
    if not token or not isinstance(token, str):
        return None
    if len(token) > SIGNED_TOKEN_MAX_LEN:
        return None
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None
    if hmac.compare_digest(_sign(secret, purpose, body), signature) is not True:
        return None
    try:
        decoded = _b64decode(body).decode("utf-8")
        issued_text, payload = decoded.split(":", 1)
        issued = int(issued_text)
    except (ValueError, UnicodeDecodeError):
        return None
    current = int(time.time() if now is None else now)
    if issued > current or current - issued > ttl_s:
        return None
    return payload


# --- control facade (web-role only; DI seam for unit tests) ------------------------


class DemoWebFacade(Protocol):
    """The demo web app's entire control-surface boundary.

    Every method is ONE unit of work under the demo WEB role. The web
    request path depends ONLY on this protocol (and the login
    credential lookup), never on the worker or any privileged service.
    """

    async def close(self) -> None: ...

    async def count_active_accounts(self) -> int: ...

    async def get_login_credential(
        self, username: str
    ) -> FakeAdminLoginCredential | None: ...

    async def get_account_facts(
        self, account_id: uuid.UUID
    ) -> FakeAdminAccountFacts | None: ...

    async def create_request(
        self, account_id: uuid.UUID
    ) -> DemoSnapshotRequestProjection: ...

    async def get_request(
        self, request_id: uuid.UUID
    ) -> DemoSnapshotRequestProjection | None: ...

    async def create_session(
        self, *, account_id: uuid.UUID, request_id: uuid.UUID
    ) -> DemoSessionIssuedResult: ...

    async def validate_session(
        self, *, account_id: uuid.UUID, token: str
    ) -> DemoWebSessionProjection: ...

    async def revoke_session(
        self, *, account_id: uuid.UUID, token: str
    ) -> DemoWebSessionProjection | None: ...

    async def session_facts_by_token(
        self, token: str
    ) -> DemoWebSessionProjection | None: ...


class PgDemoWebFacade:
    """Real facade: ONE bounded web-role engine, one transaction per
    unit of work. The DSN is built from the explicit web-role fields
    ONLY (never any owner/worker credential) with an explicit
    no-TLS ``ssl=False`` stage boundary (trusted private
    loopback/Compose network only; no verified remote DB TLS)."""

    def __init__(self, config: DemoWebConfig) -> None:
        self._engine: AsyncEngine = create_async_engine(
            config.engine_url(),
            connect_args={"ssl": False},
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_timeout=10,
        )
        self._sessions: async_sessionmaker = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    async def close(self) -> None:
        await self._engine.dispose()

    async def count_active_accounts(self) -> int:
        async with self._sessions() as session:
            return await FakeAdminAccountsRepository(session).count_active_accounts()

    async def get_login_credential(
        self, username: str
    ) -> FakeAdminLoginCredential | None:
        async with self._sessions() as session:
            return await FakeAdminAccountsRepository(session).get_login_credential(
                username
            )

    async def get_account_facts(
        self, account_id: uuid.UUID
    ) -> FakeAdminAccountFacts | None:
        # Column-scoped facts read (id/is_enabled/credential_generation
        # only), plain MVCC: the web role is column-SELECT-only on this
        # table, so no row lock is possible (PG16 locking-privilege law);
        # the credential fence is re-checked on every use instead.
        async with self._sessions() as session:
            return await FakeAdminAccountsRepository(session).get_account_facts(
                account_id, read_lock=False
            )

    async def create_request(
        self, account_id: uuid.UUID
    ) -> DemoSnapshotRequestProjection:
        async with self._sessions.begin() as session:
            return await DemoWebControlService(session).create_request(
                account_id=account_id
            )

    async def get_request(
        self, request_id: uuid.UUID
    ) -> DemoSnapshotRequestProjection | None:
        async with self._sessions() as session:
            return await DemoWebControlService(session).request_facts(
                request_id=request_id
            )

    async def create_session(
        self, *, account_id: uuid.UUID, request_id: uuid.UUID
    ) -> DemoSessionIssuedResult:
        async with self._sessions.begin() as session:
            return await DemoWebControlService(session).create_session(
                account_id=account_id, request_id=request_id
            )

    async def validate_session(
        self, *, account_id: uuid.UUID, token: str
    ) -> DemoWebSessionProjection:
        async with self._sessions() as session:
            return await DemoWebControlService(session).validate_session(
                account_id=account_id, token=token
            )

    async def revoke_session(
        self, *, account_id: uuid.UUID, token: str
    ) -> DemoWebSessionProjection | None:
        async with self._sessions.begin() as session:
            return await DemoWebControlService(session).revoke_session(
                account_id=account_id, token=token
            )

    async def session_facts_by_token(
        self, token: str
    ) -> DemoWebSessionProjection | None:
        async with self._sessions() as session:
            return await DemoWebControlService(session).session_facts_by_token(
                token=token
            )


# --- the standalone ASGI entrypoint -----------------------------------------------


def create_demo_app(
    config: DemoWebConfig | None = None,
    *,
    facade: DemoWebFacade | None = None,
) -> FastAPI:
    """Build the standalone demo web ASGI app (224-c).

    Default OFF: with no config the app reads the demo-web environment
    and REFUSES to start (safe finite error) unless it is explicitly
    enabled and fully configured. The returned app registers ONLY the
    ``/fakeadmin`` routes and the static assets under
    ``/fakeadmin/static`` - ``/v1``, ``/admin`` and every ordinary
    admin route are absent (404). ``main.create_app`` is never
    imported or called.
    """
    from contextlib import asynccontextmanager

    from fastapi import Request
    from fastapi.responses import JSONResponse

    from slaif_gateway.api.fake_admin import fake_admin_router

    cfg = config if config is not None else DemoWebConfig.from_env()
    if not cfg.enabled:
        raise DemoWebConfigError(
            "demo_web_not_enabled",
            "The demo web entry is disabled (DEMO_WEB_ENABLED is not true).",
        )
    demo_facade = facade if facade is not None else PgDemoWebFacade(cfg)
    templates = Jinja2Templates(
        directory=str(Path(__file__).resolve().parent / "web" / "templates" / "demo")
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            await demo_facade.close()

    app = FastAPI(title="SLAIF demo admin entry", lifespan=lifespan)
    app.state.demo_config = cfg
    app.state.demo_facade = demo_facade
    app.state.demo_templates = templates

    static_dir = Path(__file__).resolve().parent / "web" / "static"
    app.mount(
        "/fakeadmin/static",
        StaticFiles(directory=str(static_dir)),
        name="demo_static",
    )
    app.include_router(fake_admin_router)

    @app.exception_handler(Exception)
    async def _safe_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        # Fail closed: a raw exception must never reach a browser (no
        # traceback, no internal value). One finite safe body only.
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong. Please try again."},
        )

    return app

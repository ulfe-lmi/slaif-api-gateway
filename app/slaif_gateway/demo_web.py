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
from typing import TYPE_CHECKING, Callable, Protocol

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from slaif_gateway.api.demo_admin_gate import DemoAdminGate
    from slaif_gateway.config import Settings

from slaif_gateway.db.repositories.fake_admin_accounts import (
    FakeAdminAccountsRepository,
    FakeAdminAccountFacts,
    FakeAdminLoginCredential,
)
from slaif_gateway.services.demo_web_control import (
    REQUEST_TTL,
    DemoSessionIssuedResult,
    DemoSnapshotRequestProjection,
    DemoWebControlService,
    DemoWebSessionProjection,
)

PENDING_TTL_S = int(REQUEST_TTL.total_seconds())

__all__ = [
    "DemoWebConfig",
    "DemoWebError",
    "DemoWebConfigError",
    "DemoWebFacade",
    "PgDemoWebFacade",
    "CopyReader",
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

# The pending wait cookie lives as long as the request it binds (the
# 224-a REQUEST_TTL, 60 minutes): a legitimate bounded worker chain
# (221 dump + 222 sanitation + 223 file stage + pre-publication
# re-proof, each capped at 300 s, plus queue time) can exceed a 15
# minute cookie, and a successful snapshot must still be able to
# reach the browser. The ABSOLUTE bound is still the request's own
# expires_at (re-checked on every poll), and the live account fences
# apply throughout; the cookie grants nothing by itself.
# Finite inbound token bound: signed cookies are well under this; a
# longer value is refused BEFORE any decode (no allocation blowup).
SIGNED_TOKEN_MAX_LEN = 512

# 224-d: the closed disposable-copy database name law (the 221
# worker-generated name); the web process accepts ONLY this shape from
# the control row and nothing else can be interpolated.
_COPY_TARGET_DB_RE = re.compile(r"demo_snap_[0-9a-f]{20}")

# The fixed, reviewed public tables the read-only preview may COUNT.
# Bounded and closed: no table name is ever taken from a request, and
# the copy itself contains exactly the 222 fail-closed schema
# inventory, so no other business object exists to reach.
COPY_PREVIEW_TABLES: tuple[str, ...] = (
    "owners",
    "gateway_keys",
    "provider_configs",
    "model_routes",
    "usage_ledger",
    "audit_log",
)

# Finite copy-read bounds (one per-request read-only connection).
_COPY_STATEMENT_TIMEOUT_S = 10.0
_COPY_CONNECT_TIMEOUT_S = 10.0

# 224-g: the display index holds at most the 223 leaf ceiling rows;
# the finite row bound makes the SELECT allocation-capped regardless.
_DISPLAY_ROW_MAX = 4096


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
    # 224-d: the independent TARGET COPY READER connection (the
    # operator-created static reader role's own credential). This is
    # NEVER the worker's target-admin passfile, the source-export
    # credential, the owner DATABASE_URL, Redis or a provider secret:
    # the web process reaches ONLY its session's one verified copy
    # through this SELECT-only role. Default empty: enabled app
    # refuses to start (safe misconfiguration) before any publication
    # can be served.
    copy_host: str = ""
    copy_port: int = 5432
    copy_user: str = ""
    copy_password: str = field(repr=False, default="")

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
        copy_port = 5432
        copy_port_ok = True
        copy_port_raw = _str("DEMO_WEB_COPY_PORT")
        if copy_port_raw:
            try:
                copy_port = int(copy_port_raw)
            except ValueError:
                copy_port, copy_port_ok = 0, False
        if enabled and not port_ok:
            raise DemoWebConfigError(
                "demo_web_misconfigured",
                "The demo web entry has an invalid control port "
                "configuration.",
            )
        if enabled and not copy_port_ok:
            raise DemoWebConfigError(
                "demo_web_misconfigured",
                "The demo web entry has an invalid copy-reader port "
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
            copy_host=_str("DEMO_WEB_COPY_HOST"),
            copy_port=copy_port,
            copy_user=_str("DEMO_WEB_COPY_USER"),
            copy_password=_str("DEMO_WEB_COPY_PASSWORD"),
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
        # 224-d: the independent copy-reader connection is required
        # for an enabled entry (the read-only copy preview is part of
        # this stage); missing/malformed fails closed before any
        # publication is served.
        if not self.copy_host:
            problems.append("copy-host")
        if not (1 <= self.copy_port <= 65535):
            problems.append("copy-port")
        if _IDENTIFIER_RE.fullmatch(self.copy_user) is None:
            problems.append("copy-user")
        if not self.copy_password:
            problems.append("copy-password")
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

    def copy_engine_url(self, target_db: str) -> str:
        """Per-request copy-connection DSN for ONE verified copy.

        ``target_db`` must satisfy the closed disposable-copy name
        law (``demo_snap_<20 hex>``) BEFORE any interpolation; the
        credential is the copy reader role's own (SELECT-only), and
        the explicit no-TLS ``ssl=False`` stage boundary matches the
        control connection (trusted private network only).
        """
        from urllib.parse import quote

        if _COPY_TARGET_DB_RE.fullmatch(target_db) is None:
            raise DemoWebError(
                "copy_binding_unavailable",
                "The session copy binding is not available.",
            )
        return (
            "postgresql+asyncpg://"
            f"{quote(self.copy_user, safe='')}:"
            f"{quote(self.copy_password, safe='')}"
            f"@{self.copy_host}:{self.copy_port}/"
            f"{quote(target_db, safe='')}"
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


# --- 224-d session-bound target-copy reader ---------------------------------------


class CopyReader:
    """Bounded, per-request, SELECT-only reader for ONE session's
    verified copy (224-d).

    The web process has NO pathname/custody access. It connects to the
    exact disposable database named by the verified control row (closed
    ``demo_snap_<20hex>`` law) under the operator's static reader role
    over the trusted private network, inside ONE per-request engine
    (``NullPool`` - a fresh connection per checkout, disposed after
    use, so logout/cleanup is never held by an idle web pool). The
    connect itself is bounded (asyncpg connect timeout), and every
    statement runs under a finite ``statement_timeout``.

    The whole preview read is ONE database-side READ ONLY transaction
    (``conn.begin()`` + ``SET TRANSACTION READ ONLY`` as the first
    statement of that transaction - a backstop on top of the role's
    SELECT-only grants):

    1. the transaction is verified read-only
       (``current_setting('transaction_read_only')`` must be ``on``);
    2. ``current_database()`` MUST equal the expected copy name - a
       wrong/stale binding refuses without exposing either name;
    3. the fixed reviewed table allowlist is COUNTED with strict
       ``count(*)`` statements. The allowlist is a module constant
       (never request-derived), and a verified copy always contains
       the 222 fail-closed schema inventory; a missing table means a
       malformed copy and fails closed, it is not reported as absent.

    No request-derived or unknown table name, raw row, DSN,
    credential or error detail ever leaves this object: ``read``
    returns only the fixed six-table allowlist count mapping (its
    keys are module constants, never request input), and every
    failure path raises ``DemoWebError`` with the one safe
    ``copy_binding_unavailable`` vocabulary.
    """

    def __init__(self, config: DemoWebConfig, target_db: str) -> None:
        # Validate BEFORE any allocation/connection: a malformed name
        # from the control row is a safe refusal, never an interpolation.
        if _COPY_TARGET_DB_RE.fullmatch(target_db) is None:
            raise DemoWebError(
                "copy_binding_unavailable",
                "The session copy binding is not available.",
            )
        self._config = config
        self._target_db = target_db
        self._engine: AsyncEngine | None = None

    async def close(self) -> None:
        # Always attempt disposal; a disposal failure must never leak
        # a raw driver exception: it is wrapped in the same safe
        # refusal, so an otherwise successful read surfaces as that
        # safe refusal, never as a raw detail.
        if self._engine is not None:
            engine, self._engine = self._engine, None
            try:
                await engine.dispose()
            except DemoWebError:
                raise
            except Exception:
                raise DemoWebError(
                    "copy_binding_unavailable",
                    "The session copy binding is not available.",
                ) from None

    async def read(self) -> dict[str, int]:
        """Read the bounded preview counts; every failure is the one
        safe refusal (no name, DSN or error detail escapes)."""
        from sqlalchemy import text as _sql_text

        try:
            self._engine = create_async_engine(
                self._config.copy_engine_url(self._target_db),
                poolclass=NullPool,
                connect_args={
                    # Explicit stage boundary (trusted private
                    # network only) plus a bounded connect.
                    "ssl": False,
                    "timeout": _COPY_CONNECT_TIMEOUT_S,
                    "server_settings": {
                        "statement_timeout": str(
                            int(_COPY_STATEMENT_TIMEOUT_S * 1000)
                        )
                    },
                },
            )
            async with self._engine.connect() as conn:
                async with conn.begin():
                    # First statement of this explicit transaction:
                    # make it READ ONLY, then verify the server agrees.
                    await conn.exec_driver_sql(
                        "SET TRANSACTION READ ONLY"
                    )
                    mode = (
                        await conn.exec_driver_sql(
                            "SELECT current_setting("
                            "'transaction_read_only')"
                        )
                    ).first()
                    if mode is None or mode[0] != "on":
                        raise DemoWebError(
                            "copy_binding_unavailable",
                            "The session copy binding is not available.",
                        )
                    row = (
                        await conn.exec_driver_sql(
                            "SELECT current_database()"
                        )
                    ).first()
                    if row is None or row[0] != self._target_db:
                        raise DemoWebError(
                            "copy_binding_unavailable",
                            "The session copy binding is not available.",
                        )
                    counts: dict[str, int] = {}
                    for table in COPY_PREVIEW_TABLES:
                        # Closed module-constant allowlist (never
                        # request-derived); the verified copy always
                        # contains the 222 fail-closed schema
                        # inventory, so a missing table here is a
                        # malformed copy and fails closed.
                        val = (
                            await conn.execute(
                                _sql_text(
                                    "SELECT count(*) FROM "
                                    f"public.{table}"
                                )
                            )
                        ).scalar_one()
                        counts[table] = int(val)
                return counts
        except DemoWebError:
            raise
        except Exception:
            # Driver, connection, dispose or statement failure: one
            # generic safe refusal, never a traceback or internal
            # value.
            raise DemoWebError(
                "copy_binding_unavailable",
                "The session copy binding is not available.",
            ) from None
        finally:
            await self.close()


class DisplayReader:
    """Bounded, per-request, SELECT-only reader for ONE session's
    verified copy target-only display index (224-g).

    Same trust boundary as ``CopyReader``: the web process has NO
    pathname/custody access and reaches ONLY the exact disposable
    database named by the verified control row (closed
    ``demo_snap_<20hex>`` law) under the operator's static reader
    role. It reads ONLY the worker-published ``demo_display`` schema's
    single leaves table - the target-only publication created by the
    224-g worker ingest - never any worker file.

    The whole read is ONE database-side READ ONLY transaction
    (verified ``transaction_read_only`` + ``current_database()``
    binding), and the projection is the closed safe index only:
    logical name, kind, byte count, capture time. The sanitized body
    bytes are NOT returned in this suffix (no permissive download or
    body endpoint exists yet). No request-derived input reaches the
    SQL. Every failure is the one safe refusal; a missing
    ``demo_display`` schema (pre-upgrade copy) is that same refusal -
    the page renders the safe note instead.
    """

    def __init__(self, config: DemoWebConfig, target_db: str) -> None:
        # Validate BEFORE any allocation/connection: a malformed name
        # from the control row is a safe refusal, never an
        # interpolation.
        if _COPY_TARGET_DB_RE.fullmatch(target_db) is None:
            raise DemoWebError(
                "copy_binding_unavailable",
                "The session copy binding is not available.",
            )
        self._config = config
        self._target_db = target_db
        self._engine: AsyncEngine | None = None

    async def close(self) -> None:
        # Always attempt disposal; a disposal failure must never leak
        # a raw driver exception: it is wrapped in the same safe
        # refusal, so an otherwise successful read surfaces as that
        # safe refusal, never as a raw detail.
        if self._engine is not None:
            engine, self._engine = self._engine, None
            try:
                await engine.dispose()
            except DemoWebError:
                raise
            except Exception:
                raise DemoWebError(
                    "copy_binding_unavailable",
                    "The session copy binding is not available.",
                ) from None

    async def read_index(self) -> list[dict[str, object]]:
        """Read the bounded display index; every failure is the one
        safe refusal (no name, DSN or error detail escapes)."""
        from sqlalchemy import text as _sql_text

        try:
            self._engine = create_async_engine(
                self._config.copy_engine_url(self._target_db),
                poolclass=NullPool,
                connect_args={
                    # Explicit stage boundary (trusted private
                    # network only) plus a bounded connect.
                    "ssl": False,
                    "timeout": _COPY_CONNECT_TIMEOUT_S,
                    "server_settings": {
                        "statement_timeout": str(
                            int(_COPY_STATEMENT_TIMEOUT_S * 1000)
                        )
                    },
                },
            )
            async with self._engine.connect() as conn:
                async with conn.begin():
                    # First statement of this explicit transaction:
                    # make it READ ONLY, then verify the server agrees.
                    await conn.exec_driver_sql(
                        "SET TRANSACTION READ ONLY"
                    )
                    mode = (
                        await conn.exec_driver_sql(
                            "SELECT current_setting("
                            "'transaction_read_only')"
                        )
                    ).first()
                    if mode is None or mode[0] != "on":
                        raise DemoWebError(
                            "copy_binding_unavailable",
                            "The session copy binding is not available.",
                        )
                    row = (
                        await conn.exec_driver_sql(
                            "SELECT current_database()"
                        )
                    ).first()
                    if row is None or row[0] != self._target_db:
                        raise DemoWebError(
                            "copy_binding_unavailable",
                            "The session copy binding is not available.",
                        )
                    # Fixed closed table (the worker-published
                    # target-only display schema); no request-derived
                    # identifier reaches the statement, and the row
                    # bound caps the allocation. A missing schema is a
                    # safe refusal (pre-upgrade copies).
                    rows = (
                        await conn.execute(
                            _sql_text(
                                "SELECT logical_name, kind, byte_count, "
                                "captured_at FROM demo_display.leaves "
                                "ORDER BY logical_name LIMIT "
                                f"{_DISPLAY_ROW_MAX}"
                            )
                        )
                    ).all()
                return [
                    {
                        "logical_name": str(r[0]),
                        "kind": str(r[1]),
                        "byte_count": int(r[2]),
                        "captured_at": float(r[3]),
                    }
                    for r in rows
                ]
        except DemoWebError:
            raise
        except Exception:
            # Driver, connection, dispose or statement failure (or a
            # missing demo_display schema): one generic safe refusal.
            raise DemoWebError(
                "copy_binding_unavailable",
                "The session copy binding is not available.",
            ) from None
        finally:
            await self.close()


# --- the standalone ASGI entrypoint -----------------------------------------------


def _default_copy_reader_factory(cfg: DemoWebConfig, target_db: str) -> CopyReader:
    """Default per-request copy-reader factory (224-d)."""
    return CopyReader(cfg, target_db)


def _default_display_reader_factory(
    cfg: DemoWebConfig, target_db: str
) -> DisplayReader:
    """Default per-request display-index reader factory (224-g)."""
    return DisplayReader(cfg, target_db)


def _demo_display_settings() -> Settings:
    """Fixed neutral display settings for the reused admin templates (224-e).

    Constructed from the model's FIXED DEFAULTS only: ``model_construct``
    bypasses validation and never reads ambient ``get_settings()`` /
    production environment, so the demo process carries no source DB,
    worker, Redis or provider credential. Branding stays disabled
    (packaged neutral assets only) and the dashboard is explicitly on.
    """
    from slaif_gateway.config import Settings

    return Settings.model_construct(
        ENABLE_ADMIN_DASHBOARD=True,
        SLAIF_BRANDING_DIR="",
        DATABASE_URL=None,
    )


def _mount_demo_admin_routers(app: FastAPI) -> None:
    """Mount the EXISTING admin routers in the demo process only (224-e).

    Same fixed-literal order as the ordinary app (branding and
    record-choices register before admin so their literals win). No
    ``/v1``, provider, mail or worker route is imported or mounted.
    """
    from slaif_gateway.api.admin import router as admin_router
    from slaif_gateway.api.admin_accounting_operations import (
        router as admin_accounting_operations_router,
    )
    from slaif_gateway.api.admin_accounts import router as admin_accounts_router
    from slaif_gateway.api.demo_admin_catalog import router as demo_admin_catalog_router
    from slaif_gateway.api.admin_catalog_refresh import (
        router as admin_catalog_refresh_router,
    )
    from slaif_gateway.api.admin_compatibility import (
        router as admin_compatibility_router,
    )
    from slaif_gateway.api.admin_email_operations import (
        router as admin_email_operations_router,
    )
    from slaif_gateway.api.admin_key_batch import router as admin_key_batch_router
    from slaif_gateway.api.admin_key_clone import router as admin_key_clone_router
    from slaif_gateway.api.demo_admin_operations import (
        router as demo_admin_operations_router,
    )
    from slaif_gateway.api.admin_operations import router as admin_operations_router
    from slaif_gateway.api.admin_record_choices import (
        router as admin_record_choices_router,
    )
    from slaif_gateway.api.admin_replay_maintenance import (
        router as admin_replay_maintenance_router,
    )
    from slaif_gateway.api.admin_reports import router as admin_reports_router
    from slaif_gateway.api.branding import router as branding_router
    from slaif_gateway.api.admin_provider_route_configuration import (
        router as admin_provider_route_configuration_router,
    )

    static_dir = Path(__file__).resolve().parent / "web" / "static"
    app.mount(
        "/admin/static",
        StaticFiles(directory=str(static_dir)),
        name="admin_static",
    )
    app.include_router(branding_router)
    app.include_router(admin_record_choices_router)
    app.include_router(admin_router)
    app.include_router(admin_email_operations_router)
    app.include_router(admin_accounting_operations_router)
    app.include_router(admin_accounts_router)
    # Demo-specific copy-only catalog index wins over the normal custody route.
    app.include_router(demo_admin_catalog_router)
    app.include_router(admin_catalog_refresh_router)
    app.include_router(admin_key_clone_router)
    app.include_router(admin_key_batch_router)
    app.include_router(admin_provider_route_configuration_router)
    # Demo-specific operations index + captured process-configuration
    # pages win over the normal live-Settings operations routes (224-t).
    app.include_router(demo_admin_operations_router)
    app.include_router(admin_operations_router)
    app.include_router(admin_compatibility_router)
    app.include_router(admin_replay_maintenance_router)
    app.include_router(admin_reports_router)


def create_demo_app(
    config: DemoWebConfig | None = None,
    *,
    facade: DemoWebFacade | None = None,
    copy_reader_factory: Callable[[DemoWebConfig, str], CopyReader] | None = None,
    display_reader_factory: Callable[[DemoWebConfig, str], DisplayReader] | None = None,
) -> DemoAdminGate:
    """Build the standalone demo web ASGI app (224-c; 224-e gated).

    Default OFF: with no config the app reads the demo-web environment
    and REFUSES to start (safe finite error) unless it is explicitly
    enabled and fully configured. ``/v1``, provider, mail and worker
    routes are absent (404) and ``main.create_app`` is never imported
    or called. 224-e: the EXISTING admin routers are mounted here ONLY
    and wrapped in the central default-deny ``DemoAdminGate`` - the
    admitted core GET set browses the session's exact verified copy
    through the 224-d reader credential; every other admin route stays
    gated (the gate table is enumerated by the focused tests).
    """
    from contextlib import asynccontextmanager

    from fastapi import Request
    from fastapi.responses import JSONResponse

    from slaif_gateway.api.demo_admin_gate import DemoAdminGate
    from slaif_gateway.api.fake_admin import fake_admin_router

    cfg = config if config is not None else DemoWebConfig.from_env()
    if not cfg.enabled:
        raise DemoWebConfigError(
            "demo_web_not_enabled",
            "The demo web entry is disabled (DEMO_WEB_ENABLED is not true).",
        )
    # The SAME fail-closed law for a directly supplied enabled config
    # (from_env already validated; this is idempotent for it): an
    # enabled app can never start with a missing copy-reader binding.
    cfg._validate_enabled()
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
    # 224-e fixed marker: the sessionmaker seam (db/session.py) fails
    # every demo request closed to the app-global factory on this app.
    app.state.demo_mode = True
    # 224-e: fixed neutral display settings for the reused admin pages
    # (model defaults only - no ambient env/production config read).
    app.state.settings = _demo_display_settings()
    # 224-e: the existing admin GUI, mounted in this process only and
    # reachable exclusively through the central default-deny gate.
    _mount_demo_admin_routers(app)
    # 224-d: per-request copy-reader factory (the purpose-built
    # reader by default; tests may substitute a fake).
    app.state.demo_copy_reader_factory = (
        copy_reader_factory
        if copy_reader_factory is not None
        else _default_copy_reader_factory
    )
    # 224-g: per-request target-only display-index reader factory
    # (the purpose-built reader by default; tests may substitute a
    # fake).
    app.state.demo_display_reader_factory = (
        display_reader_factory
        if display_reader_factory is not None
        else _default_display_reader_factory
    )

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

    # 224-e: the central server-side default-deny gate wraps the whole
    # app; non-/admin traffic (the /fakeadmin flow, static assets)
    # passes through unchanged.
    return DemoAdminGate(app)

"""Central server-side default-deny gate for the standalone demo admin host (224-e).

``create_demo_app`` mounts the EXISTING admin routers only in the standalone
demo process; this wrapper sits in front of them so the reused handlers are
reachable ONLY through the gate, BEFORE any admin handler or form/body
parsing:

- the admitted admin GET set (dashboard, the core list pages, their
  closed-UUID record detail pages, the 224-i core form GETs, the 224-j
  reporting/accounting/accounts/key-batch read GETs and the
  ``/admin/record-choices`` lookup) dispatches only after the 224-a demo session is validated against the LIVE
  fake-admin account/generation/request fence AND bound to that session's
  exact verified/unexpired ``demo_snap_<20hex>`` copy under the 224-d
  SELECT-only reader credential;
- every admitted read receives a REQUEST-LOCAL sessionmaker stored on
  ``scope["state"]`` (surfaced as ``request.state.demo_admin``); a per-visitor
  app-global factory is never assigned or consulted, the per-request engine
  is a no-idle pool with database-side read-only mode, verifies
  ``current_database()`` before any handler may query, and is disposed after
  the response;
- every unsafe method on ``/admin`` is cut BEFORE routing and body
  parsing: a uniform quiet no-content no-change response for an
  authenticated demo session (including unknown paths - nothing is ever
  dispatched, so no fake success, no visible method error, no handler
  effect), default denial without one; the single explicit exception is
  POST ``/admin/logout``, which performs the DEMO sign-out through the
  224-c control service with CSRF verification and never dispatches the
  production logout service;
- zero active fake-admin accounts means every ``/admin`` path is 404;
- no DSN, copy name, credential, or traceback ever reaches the browser.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache

from fastapi import FastAPI
from starlette.requests import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from slaif_gateway.api.fake_admin import (
    COOKIE_CSRF,
    COOKIE_PENDING,
    COOKIE_SESSION,
    LOGIN_URL,
    SESSION_COOKIE_PATH,
    _FormBodyTooLarge,
    _copy_readable_now,
    _parse_bounded_form,
)
from slaif_gateway.db.models import AdminSession, AdminUser
from slaif_gateway.db.session import create_sessionmaker_from_engine
from slaif_gateway.demo_web import (
    SIGNED_TOKEN_MAX_LEN,
    _COPY_CONNECT_TIMEOUT_S,
    _COPY_STATEMENT_TIMEOUT_S,
    _COPY_TARGET_DB_RE,
)
from slaif_gateway.services.admin_session_service import AdminSessionContext
from slaif_gateway.services.request_diagnostics import (
    is_known_incoming_secret_alias,
    is_safe_diagnostic_id,
)
from urllib.parse import unquote

# --- the fixed 224-e/224-f/224-i admission law (closed sets, never
# input-derived) ---
# 224-f adds the seven reviewed DATABASE-BACKED list/detail families;
# 224-i adds the routes list/detail, the fixed core form GETs, the
# canonical-UUID edit forms (seven families, never keys/templates) and
# the provider discover form (handlers verified: copied-public
# repositories plus fixed package data only, no file/process/network
# reads on GET); 224-j adds the fixed reporting, accounting
# candidate/review entry, administrator-account read and key-batch
# entry GETs (frozen copied rows; request-time calculations carry a
# demo-only hint); 224-t adds the two exact static operations read
# pages (the operations index and the captured worker-observed
# process-configuration page). Everything else - the remaining
# operations pages (diagnostics, compatibility, replay-maintenance),
# catalog (beyond the admitted set), OpenAI-assisted, key clone,
# exports and /admin/branding - stays default-denied.

ADMITTED_DASHBOARD_PATHS = ("/admin", "/admin/")
ADMITTED_LIST_PATHS = (
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
)
ADMITTED_DETAIL_PREFIXES = (
    "/admin/keys/",
    "/admin/owners/",
    "/admin/institutions/",
    "/admin/cohorts/",
    "/admin/providers/",
    "/admin/routes/",
    "/admin/pricing/",
    "/admin/templates/",
    "/admin/fx/",
    "/admin/usage/",
    "/admin/audit/",
    "/admin/email-deliveries/",
)
ADMITTED_RECORD_CHOICES_PATH = "/admin/record-choices"
#: 224-i: the fixed core FORM GETs (positive closed set; their POST/PUT/
#: PATCH/DELETE handlers remain cut to the uniform 204 no-op before
#: routing and body parsing by the unsafe-method branch).
ADMITTED_FORM_PATHS = (
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
)
#: 224-i: the exact edit-form FAMILIES (never keys/templates); the
#: middle segment must be exactly one canonical lowercase UUID.
ADMITTED_EDIT_FAMILY_PREFIXES = (
    "/admin/owners/",
    "/admin/institutions/",
    "/admin/cohorts/",
    "/admin/providers/",
    "/admin/routes/",
    "/admin/pricing/",
    "/admin/fx/",
)
#: 224-j: the fixed reporting, accounting candidate/review entry,
#: administrator-account read and key-batch entry GETs. Positive closed
#: set of EXACT paths - no prefix passthrough: every missing-slash,
#: extra-suffix, export-attachment or file-backed GET stays denied.
ADMITTED_REPORTING_PATHS = (
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
)
# 224-k: only the safe, target-copy catalog metadata index; 224-l
# adds the ONE exact sanitized display-copy artifact download;
# 224-m adds the ONE canonical sanitized run-detail shape
# (demo-run- + 24 lowercase hex, required trailing slash); 224-n
# adds the ONE exact captured-proposals page; 224-o adds the ONE
# exact collect page; 224-p adds the three exact review /
# export-baseline / job-record pages (the jobs path has its
# REQUIRED trailing slash). All use the same gate law and the
# same request-local copy binding.
ADMITTED_CATALOG_INDEX_PATH = "/admin/operations/catalog/"
ADMITTED_CATALOG_ARTIFACT_PATH = "/admin/operations/catalog/artifact"
# 224-n: the ONE exact captured-proposals page (no trailing slash;
# every near miss / extra suffix stays default-denied 404).
ADMITTED_CATALOG_PROPOSALS_PATH = "/admin/operations/catalog/proposals"
# 224-o: the ONE exact collect page (no trailing slash; every
# near miss / subpath stays default-denied 404).
ADMITTED_CATALOG_COLLECT_PATH = "/admin/operations/catalog/collect"
# 224-p: the three exact historical/illustrative catalog pages.
# review and export-baseline take NO trailing slash; the jobs
# page REQUIRES its trailing slash - every near miss, subpath
# (including every submit/cancel/remove POST path) and source ID
# stays default-denied 404, and every unsafe method remains the
# unchanged pre-body quiet 204 cut.
ADMITTED_CATALOG_REVIEW_PATH = "/admin/operations/catalog/review"
ADMITTED_CATALOG_EXPORT_PATH = "/admin/operations/catalog/export-baseline"
ADMITTED_CATALOG_JOBS_PATH = "/admin/operations/catalog/jobs/"
# 224-t: the two exact static demo operations read pages. The index
# REQUIRES its trailing slash; process-configuration takes NONE.
# Both define NO query parameters (any query stays 404).
ADMITTED_OPERATIONS_INDEX_PATH = "/admin/operations/"
ADMITTED_OPERATIONS_PROCESS_CONFIG_PATH = "/admin/operations/process-configuration"
# 224-u: the five EXACT literal branding asset endpoints (the four
# image slots live under /admin/branding/). No query, alternate slash,
# arbitrary slot, prefix passthrough or unsafe method is admitted;
# these endpoints are TOTAL before and after login (with a verified
# session the visitor's own neutral copy leaf is served; before login
# the packaged neutral fallback - the live operator branding directory
# is never read).
ADMITTED_BRANDING_PATHS = (
    "/admin/branding/style.css",
    "/admin/branding/logo",
    "/admin/branding/logo-compact",
    "/admin/branding/favicon",
    "/admin/branding/hero",
)
# 224-u: the exact read-only Codex compatibility GET family. The index
# REQUIRES its trailing slash; the shipped preset page takes the EXACT
# validated preset name from the package's finite preset loader and its
# exact /download child; the key page takes the canonical lowercase
# dashed UUID only. Every near miss, alternate slash, unknown subpath
# and ANY query stays default-denied; every unsafe method (including
# the review/apply POSTs) remains the unchanged pre-body quiet 204 cut.
ADMITTED_COMPATIBILITY_INDEX_PATH = "/admin/operations/compatibility/"
ADMITTED_COMPATIBILITY_PRESET_PREFIX = "/admin/operations/compatibility/preset/"
ADMITTED_COMPATIBILITY_KEY_PREFIX = "/admin/operations/compatibility/key/"
# 224-v: the exact read-only Operations diagnostics + replay GET
# family. The diagnostics page takes ZERO query parameters or its one
# bounded read-only selector (see ``_diagnostics_query_admitted``); the
# replay index REQUIRES its trailing slash, all-active is the exact
# literal, and key/cohort take the canonical lowercase dashed UUID
# only - every replay path is query-free. Every near miss, alternate
# slash, unknown subpath and any replay query stays default-denied;
# every unsafe method (including the normal inspect/preview/apply,
# lookup, choices and cleanup POSTs) remains the unchanged pre-body
# quiet 204 cut.
ADMITTED_DIAGNOSTICS_PATH = "/admin/operations/diagnostics"
ADMITTED_REPLAY_INDEX_PATH = "/admin/operations/replay-maintenance/"
ADMITTED_REPLAY_ALL_ACTIVE_PATH = "/admin/operations/replay-maintenance/all-active"
ADMITTED_REPLAY_KEY_PREFIX = "/admin/operations/replay-maintenance/key/"
ADMITTED_REPLAY_COHORT_PREFIX = "/admin/operations/replay-maintenance/cohort/"
# 224-v diagnostics selector bound: the whole raw query is checked
# against this small ceiling BEFORE it is split or decoded, so an
# oversized or malformed query is refused without allocation or echo.
# The ceiling covers the worst-case LEGITIMATE query under percent
# encoding: "lookup=" (7) + 128 safe-ID characters each encoded as a
# 3-byte %%XX sequence (384) + "&" (1) + "namespace=" (10) + "client"
# percent-encoded (18) = 420 raw bytes.
_DIAGNOSTICS_QUERY_MAX_LEN = 420
# 224-q: the three exact key read-page GET shapes (canonical
# lowercase dashed UUID + exact suffix, no extra path components):
# calibration, clone and clone/receipts. Malformed/uppercase/
# undashed/source-like IDs and every near miss stay 404 before
# routing; the JSON attachment GETs and every submit/apply/preview/
# retry POST stay refused by the existing laws.
_KEY_CANONICAL_UUID = (
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
_KEY_READ_PAGE_RE = re.compile(
    rf"/admin/keys/{_KEY_CANONICAL_UUID}(?:/calibration|/clone|/clone/receipts)\Z"
)
# 224-q receipts query-law bound: the optional `operation` selector
# may be at most this many raw bytes (a canonical UUID is 36); longer
# values are refused here so they are never echoed or used.
_KEY_RECEIPTS_OPERATION_MAX_LEN = 64
# 224-q raw query ceiling for the receipts page: the `operation=`
# name (10 bytes) plus the 64-byte value bound. The WHOLE raw query
# is length-checked BEFORE any split/parse, so a malformed or
# oversized scope query is a fixed default-denied 404 without
# allocation or echo.
_KEY_READ_PAGE_QUERY_MAX_LEN = (
    len(b"operation=") + _KEY_RECEIPTS_OPERATION_MAX_LEN
)
# 224-m: the exact canonical run-detail shape; near misses and
# noncanonical/source IDs are never admitted.
_CATALOG_RUN_DETAIL_RE = re.compile(
    r"/admin/operations/catalog/runs/demo-run-[0-9a-f]{24}/\Z"
)
#: Canonical lowercase 8-4-4-4-12 UUID syntax ONLY (the exact form the
#: GUI generates from ``str(uuid)``); variant forms (no dashes, braces,
#: URN, uppercase) are NOT admitted detail components.
_CANONICAL_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
ADMIN_LOGIN_PATH = "/admin/login"
ADMIN_STATIC_PREFIX = "/admin/static"
DEMO_LOGOUT_PATH = "/admin/logout"

# Fixed fictional administrator identity (224-e): a single shared,
# never-persisted display identity. No password, token, locator or source
# value is part of it; templates only ever read ``display_name``.
DEMO_ADMIN_USER_ID = uuid.uuid5(uuid.NAMESPACE_URL, "slaif/demo-admin/224-e/user")
DEMO_ADMIN_SESSION_ID = uuid.uuid5(uuid.NAMESPACE_URL, "slaif/demo-admin/224-e/session")
DEMO_ADMIN_DISPLAY_NAME = "Demo Administrator"
DEMO_ADMIN_EMAIL = "demo-admin@example.invalid"

_REFUSAL_HTML = (
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    "<title>SLAIF demo</title></head><body>"
    "<p>The requested demo page is not available right now. "
    "Please check back shortly.</p></body></html>"
)


@dataclass(frozen=True, slots=True)
class DemoAdminState:
    """Request-local, gate-validated demo admin state (224-e).

    Stored on ``scope["state"]`` before the inner app runs; the guarded
    admin helpers read it via ``request.state.demo_admin``. The engine is
    disposed by the gate after the response; the state must never outlive
    the request.
    """

    session_context: AdminSessionContext
    csrf_token: str
    target_db: str
    sessionmaker: async_sessionmaker[AsyncSession]
    engine: AsyncEngine


def _fictional_admin_context() -> AdminSessionContext:
    """Build the fixed, non-persisted display identity (once per gate)."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    admin_user = AdminUser(
        id=DEMO_ADMIN_USER_ID,
        email=DEMO_ADMIN_EMAIL,
        display_name=DEMO_ADMIN_DISPLAY_NAME,
        password_hash="demo-fixture: not a credential",
        # 224-j: display role ONLY - lets the isolated demo session pass
        # the existing superadmin GET gate on the copied admin-account
        # read pages. Never persisted; real admin roles, source accounts
        # and every auth decision outside this demo process are
        # untouched, and the central 204 no-op boundary is unchanged.
        role="superadmin",
        mfa_secret=None,
        is_active=True,
        last_login_at=None,
        created_at=now,
        updated_at=now,
    )
    admin_session = AdminSession(
        id=DEMO_ADMIN_SESSION_ID,
        admin_user_id=DEMO_ADMIN_USER_ID,
        session_token_hash="demo-fixture: not a token",
        csrf_token_hash="demo-fixture: not a token",
        ip_address=None,
        user_agent=None,
        expires_at=now,
        revoked_at=None,
        created_at=now,
        last_seen_at=None,
    )
    return AdminSessionContext(admin_user=admin_user, admin_session=admin_session)


def _demo_csrf_token(cookie_secret: str, session_cookie: str) -> str:
    """Per-browser NON-authoritative demo form token.

    Derived one-way from the demo cookie secret and the raw session cookie;
    it never touches the copied ``admin_sessions`` rows, grants no rights,
    and is verified with ``hmac.compare_digest`` only at demo sign-out.
    """
    digest = hmac.new(
        cookie_secret.encode("utf-8"),
        b"demo-admin-csrf:" + session_cookie.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:40]


def _scope_path(scope: dict) -> str:
    path = scope.get("path")
    return path if isinstance(path, str) else ""


def _key_read_page_query_admitted(path: str, query_string: bytes) -> bool:
    """The 224-q query law for the three admitted key read pages.

    The calibration form and the clone form define NO query
    parameters in the demo: ANY query string is refused. The clone
    receipts page accepts ZERO parameters or exactly ONE
    ``operation=<value>`` selector (canonical raw form, bounded
    length); duplicates, extra or unknown parameters and overlong
    values are refused. Every refusal is a plain default-denied 404
    BEFORE session resolution, routing or any echo.

    The whole raw query is also checked against a small byte ceiling
    BEFORE it is split, so an oversized/malformed scope query is
    refused without allocation or echo.
    """
    if not query_string:
        return True
    if not path.endswith("/clone/receipts"):
        return False
    if not isinstance(query_string, (bytes, bytearray)):
        return False
    if len(query_string) > _KEY_READ_PAGE_QUERY_MAX_LEN:
        return False
    pairs = query_string.split(b"&")
    if len(pairs) != 1:
        return False
    name, _, value = pairs[0].partition(b"=")
    if name != b"operation":
        return False
    return len(value) <= _KEY_RECEIPTS_OPERATION_MAX_LEN


def _diagnostics_query_admitted(
    query_string: bytes,
    scope: dict,
    accepted_prefixes: tuple[str, ...] | None,
) -> bool:
    """The 224-v bounded read-only selector law for the demo
    diagnostics page.

    The page defines ZERO parameters or at most ONE of each of the
    two exact read-only selectors ``lookup=<safe diagnostic ID>`` and
    ``namespace=<any|gateway|client>``. Unknown, duplicated or empty
    parameters, non-ASCII parameter names, unsafe IDs,
    out-of-vocabulary namespaces and overlong values are refused with
    a plain default-denied 404 BEFORE session resolution, routing or
    any echo.

    Order of the law: (1) the whole RAW query is checked against the
    small byte ceiling BEFORE it is split; (2) each parameter value
    is percent-decoded EXACTLY ONCE (a strict single pass - invalid
    escapes stay literal and then fail the grammar, and a decoded
    value is never decoded again); (3) the decoded value must match
    the existing safe diagnostic ID grammar (lookup) or the exact
    namespace vocabulary; (4) a decoded lookup that is or embeds a
    KNOWN incoming authentication alias is refused HERE, before the
    session is resolved and before the copy is bound - a credential-
    shaped value can fit the safe-ID grammar. The boundary this code
    proves: a refused value does not reach the copy session,
    application-rendered HTML, an application-produced redirect, or
    any application echo or log under this process's control. An
    upstream proxy or access log that records the raw request line
    before the ASGI gate is outside this code's reach and is not
    claimed.
    """
    if not query_string:
        return True
    if not isinstance(query_string, (bytes, bytearray)):
        return False
    if len(query_string) > _DIAGNOSTICS_QUERY_MAX_LEN:
        return False
    if accepted_prefixes is None:
        # The unavailable sentinel: the alias classifier cannot be
        # proven safe, so every nonempty selector is refused (the
        # parameter-free page still renders its copy-backed facts).
        return False
    seen: set[bytes] = set()
    for pair in bytes(query_string).split(b"&"):
        name, _, raw_value = pair.partition(b"=")
        if name not in (b"lookup", b"namespace") or name in seen:
            return False
        seen.add(name)
        if not raw_value:
            return False
        # Strict single percent-decode; the name itself is NEVER
        # decoded (it must be the exact ASCII literal).
        try:
            value = unquote(raw_value.decode("ascii"))
        except UnicodeDecodeError:
            return False
        if name == b"lookup":
            if not is_safe_diagnostic_id(value):
                return False
            # Fail closed: the admission law only runs with the raw
            # scope and the DEMO APP'S fixed neutral accepted-prefix
            # tuple (never the ambient global settings), and any
            # classifier error refuses the query.
            try:
                alias = is_known_incoming_secret_alias(
                    value, scope=scope, accepted_prefixes=accepted_prefixes
                )
            except Exception:  # noqa: BLE001 - fail closed, no echo
                return False
            if alias:
                return False
        elif value not in ("any", "gateway", "client"):
            return False
    return True


@lru_cache(maxsize=1)
def _shipped_preset_names() -> frozenset[str]:
    """The package's finite shipped preset name vocabulary (224-u).

    Computed ONCE from the reviewed preset loader (package-owned,
    credential-free reference material). Any loader failure fails
    closed: no compatibility preset path is admitted at all.
    """
    try:
        from slaif_gateway.modules.codex_profile_data import (
            list_codex_presets,
        )

        return frozenset(
            name for name, _path, _profile in list_codex_presets()
        )
    except Exception:
        return frozenset()


def _is_admitted_path(path: str) -> bool:
    """The exact closed 224-e/224-f/224-i/224-j/224-k GET admission law."""
    return _is_admitted_path_with_query(path, b"")


def _is_admitted_path_with_query(
    path: str,
    query_string: bytes,
    diagnostics_context: tuple[dict, tuple[str, ...] | None] | None = None,
) -> bool:
    """The closed GET admission law; the 224-q key read pages also
    carry the bounded query law (see ``_key_read_page_query_admitted``),
    and the 224-v diagnostics selector takes the raw scope plus the
    demo app's fixed neutral accepted-prefix tuple for its pre-copy
    alias refusal.
    """
    if path in ADMITTED_DASHBOARD_PATHS or path in ADMITTED_LIST_PATHS:
        return True
    if path == ADMITTED_RECORD_CHOICES_PATH:
        return True
    if path in ADMITTED_FORM_PATHS:
        return True
    if path in ADMITTED_REPORTING_PATHS:
        return True
    if (
        path == ADMITTED_CATALOG_INDEX_PATH
        or path == ADMITTED_CATALOG_ARTIFACT_PATH
        or path == ADMITTED_CATALOG_PROPOSALS_PATH
        or path == ADMITTED_CATALOG_COLLECT_PATH
        or path == ADMITTED_CATALOG_REVIEW_PATH
        or path == ADMITTED_CATALOG_EXPORT_PATH
        or path == ADMITTED_CATALOG_JOBS_PATH
    ):
        return True
    if path in (
        ADMITTED_OPERATIONS_INDEX_PATH,
        ADMITTED_OPERATIONS_PROCESS_CONFIG_PATH,
    ):
        # 224-t: the two static operations read pages define NO query
        # parameters at all; ANY query is refused (before session
        # resolution or routing), like the 224-p form pages.
        return not query_string
    # 224-u: the five exact branding asset literals define NO query
    # parameters (ANY query refused) and never match a prefix.
    if path in ADMITTED_BRANDING_PATHS:
        return not query_string
    # 224-u: the exact read-only compatibility GET family.
    if path == ADMITTED_COMPATIBILITY_INDEX_PATH:
        return not query_string
    if path.startswith(ADMITTED_COMPATIBILITY_PRESET_PREFIX):
        rest = path[len(ADMITTED_COMPATIBILITY_PRESET_PREFIX) :]
        # The preset name is an EXACT member of the package's finite
        # shipped vocabulary (it can never contain a slash, so every
        # subpath shape is refused here).
        if rest and rest in _shipped_preset_names():
            return not query_string
        if rest.endswith("/download"):
            name = rest[: -len("/download")]
            if name and name in _shipped_preset_names():
                return not query_string
        return False
    if path.startswith(ADMITTED_COMPATIBILITY_KEY_PREFIX):
        rest = path[len(ADMITTED_COMPATIBILITY_KEY_PREFIX) :]
        # exactly ONE remaining segment, canonical lowercase UUID
        return (
            rest
            and "/" not in rest
            and _CANONICAL_UUID_RE.fullmatch(rest) is not None
            and not query_string
        )
    # 224-v: the exact read-only diagnostics GET with its bounded
    # optional selector law (the replay family is query-free).
    if path == ADMITTED_DIAGNOSTICS_PATH:
        # The bounded selector law runs BEFORE session resolution:
        # a known-incoming-alias lookup is refused with the fixed
        # 404 without ever binding the copy. The context is
        # mandatory for a nonempty query; fail closed without it.
        if not query_string:
            return True
        if diagnostics_context is None:
            return False
        scope, accepted_prefixes = diagnostics_context
        return _diagnostics_query_admitted(
            query_string, scope, accepted_prefixes
        )
    if path in (ADMITTED_REPLAY_INDEX_PATH, ADMITTED_REPLAY_ALL_ACTIVE_PATH):
        return not query_string
    if path.startswith(ADMITTED_REPLAY_KEY_PREFIX):
        rest = path[len(ADMITTED_REPLAY_KEY_PREFIX) :]
        # exactly ONE remaining segment, canonical lowercase UUID
        return (
            rest
            and "/" not in rest
            and _CANONICAL_UUID_RE.fullmatch(rest) is not None
            and not query_string
        )
    if path.startswith(ADMITTED_REPLAY_COHORT_PREFIX):
        rest = path[len(ADMITTED_REPLAY_COHORT_PREFIX) :]
        # exactly ONE remaining segment, canonical lowercase UUID
        return (
            rest
            and "/" not in rest
            and _CANONICAL_UUID_RE.fullmatch(rest) is not None
            and not query_string
        )
    if _KEY_READ_PAGE_RE.fullmatch(path) is not None:
        # 224-q: exact shape admitted only under the bounded query
        # law (the receipts page's single optional `operation`).
        return _key_read_page_query_admitted(path, query_string)
    if _CATALOG_RUN_DETAIL_RE.fullmatch(path) is not None:
        return True
    for prefix in ADMITTED_EDIT_FAMILY_PREFIXES:
        if path.startswith(prefix) and path.endswith("/edit"):
            middle = path[len(prefix) : -len("/edit")]
            # exactly ONE middle segment, canonical lowercase UUID
            return _CANONICAL_UUID_RE.fullmatch(middle) is not None
    if path.startswith("/admin/providers/"):
        rest = path[len("/admin/providers/") :]
        parts = rest.split("/")
        # /admin/providers/<uuid>/discover : exactly two segments
        if len(parts) == 2 and parts[1] == "discover":
            return _CANONICAL_UUID_RE.fullmatch(parts[0]) is not None
    for prefix in ADMITTED_DETAIL_PREFIXES:
        if path.startswith(prefix):
            rest = path[len(prefix) :]
            # exactly ONE remaining segment, canonical lowercase UUID
            return _CANONICAL_UUID_RE.fullmatch(rest) is not None
    return False


def _scope_cookies(scope: dict) -> dict[str, str]:
    """Minimal cookie parse for the gate (path never matters here)."""
    headers = dict(scope.get("headers") or [])
    raw = headers.get(b"cookie")
    if raw is None:
        return {}
    try:
        text_value = raw.decode("latin-1")
    except Exception:
        return {}
    cookies: dict[str, str] = {}
    for part in text_value.split(";"):
        name, _, value = part.strip().partition("=")
        if name:
            cookies[name] = value
    return cookies


async def _respond_json(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"cache-control", b"no-store"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _respond_404(send) -> None:
    await _respond_json(send, 404, "Not Found")


async def _respond_400(send, detail: str) -> None:
    await _respond_json(send, 400, detail)


async def _respond_413(send) -> None:
    await _respond_json(send, 413, "Request body too large.")


async def _respond_204(send) -> None:
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


def _clear_cookie_header(name: str, path: str) -> tuple[bytes, bytes]:
    return (
        b"set-cookie",
        f"{name}=; Max-Age=0; Path={path}; HttpOnly; SameSite=strict".encode("ascii"),
    )


async def _respond_login_redirect(send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 303,
            "headers": [
                (b"location", LOGIN_URL.encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b""})


async def _respond_refusal(send) -> None:
    """One fixed safe no-store HTML refusal (no name/DSN/traceback)."""
    body = _REFUSAL_HTML.encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"text/html; charset=utf-8"),
                (b"cache-control", b"no-store"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _safe_dispose(engine: AsyncEngine) -> None:
    try:
        await engine.dispose()
    except Exception:
        # Disposal is best-effort; a driver error here must never become a
        # raw response or a log line with connection details.
        pass


class DemoAdminGate:
    """ASGI wrapper implementing the 224-e central demo-host gate.

    Only ``__call__`` is overridden; every other attribute (``routes``,
    ``state``, ``router``, ...) delegates to the wrapped FastAPI app so
    existing tests and tooling keep working against the returned object.
    """

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._cfg = app.state.demo_config
        self._facade = app.state.demo_facade
        self._fictional_context = _fictional_admin_context()
        # 224-v: the diagnostics selector's alias refusal uses the
        # DEMO APP'S fixed neutral settings (never the ambient global
        # settings); the tuple is derived once and is fail-closed
        # (an unusable value tuple still classifies credential
        # shapes and incoming request credentials).
        try:
            _prefixes = app.state.settings.get_gateway_key_accepted_prefixes()
            self._accepted_key_prefixes: tuple[str, ...] | None = (
                tuple(_prefixes)
                if isinstance(_prefixes, (list, tuple))
                and all(isinstance(item, str) for item in _prefixes)
                else None
            )
        except Exception:  # noqa: BLE001 - fail closed
            self._accepted_key_prefixes = None
        # ``None`` is the explicit unavailable sentinel: a derivation
        # failure is NEVER conflated with a legitimately empty
        # configured prefix set, and a nonempty diagnostics selector
        # is denied (fixed 404) while it is unavailable.

    def __getattr__(self, name: str):
        return getattr(self._app, name)

    async def __call__(self, scope: dict, receive, send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        path = _scope_path(scope)
        if not path.startswith("/admin"):
            await self._app(scope, receive, send)
            return

        # 224-f browser-cache privacy boundary: EVERY dynamic /admin
        # response this process emits - admitted pages, JSON, error
        # pages, the zero-account 404, no-ops and redirects - carries
        # exactly one ``Cache-Control: private, no-store`` header so a
        # signed-out browser cannot be served a normally-cached
        # snapshot of identity-masked data. This prevents NORMAL HTTP
        # caching and every dynamic reload rechecks authorization; no
        # absolute browser history/BFCache erasure is claimed. The
        # revisioned static passthrough below deliberately uses the
        # ORIGINAL send and keeps its own cache policy; the ordinary
        # app never runs behind this wrapper. Any pre-existing
        # cache-control header is replaced, never duplicated.
        original_send = send

        async def _send(message: dict) -> None:
            if message.get("type") == "http.response.start":
                kept = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() != b"cache-control"
                ]
                kept.append((b"cache-control", b"private, no-store"))
                message = {**message, "headers": kept}
            await original_send(message)

        send = _send

        # Zero active fake-admin accounts: EVERY /admin path is 404 (the
        # count failure is fail-closed too: a facade error is not a count).
        try:
            active = await self._facade.count_active_accounts()
        except Exception:
            active = -1
        if active <= 0:
            await _respond_404(send)
            return

        # Bundled static assets: the separately allowed passthrough on
        # the ORIGINAL send (their revisioned cache policy is kept).
        if path == ADMIN_STATIC_PREFIX or path.startswith(ADMIN_STATIC_PREFIX + "/"):
            await self._app(scope, receive, original_send)
            return

        method = str(scope.get("method") or "").upper()
        if method in ("GET", "HEAD"):
            if path == ADMIN_LOGIN_PATH or path.startswith(ADMIN_LOGIN_PATH + "/"):
                # Real login GET redirects to the demo entry; the real
                # login POST is handled by the unsafe branch (never
                # dispatched to the production handler).
                await _respond_login_redirect(send)
                return
            # 224-q: the closed law also binds the raw query string
            # (exact bytes, no percent-decode): only the clone
            # receipts page's single optional `operation` selector may
            # appear, bounded in raw length; everything else 404s
            # before session resolution or routing.
            if _is_admitted_path_with_query(
                path,
                scope.get("query_string") or b"",
                (scope, self._accepted_key_prefixes)
                if path == ADMITTED_DIAGNOSTICS_PATH
                else None,
            ):
                projection = await self._resolve_session(scope)
                if path in ADMITTED_BRANDING_PATHS:
                    # 224-u: the five fixed branding asset endpoints
                    # are TOTAL before and after login. With a
                    # validated session the visitor's exact verified
                    # copy is bound and its neutral branding leaves
                    # are served; before login the packaged neutral
                    # fallback is served (no login redirect for a
                    # subresource, never a live-directory read).
                    if projection is not None:
                        state = await self._build_copy_state(
                            scope, projection
                        )
                        if state is None:
                            # A present but broken binding is a safe
                            # refusal: the fallback must not mask a
                            # session whose copy cannot be verified.
                            await _respond_refusal(send)
                            return
                        scope.setdefault("state", {})["demo_admin"] = state
                        try:
                            await self._app(scope, receive, send)
                            return
                        finally:
                            await _safe_dispose(state.engine)
                    await self._app(scope, receive, send)
                    return
                if projection is None:
                    await _respond_login_redirect(send)
                    return
                state = await self._build_copy_state(scope, projection)
                if state is None:
                    await _respond_refusal(send)
                    return
                scope.setdefault("state", {})["demo_admin"] = state
                try:
                    await self._app(scope, receive, send)
                    return
                finally:
                    await _safe_dispose(state.engine)
            # Every other admin GET stays unavailable (default denied).
            await _respond_404(send)
            return

        # Unsafe methods (POST/PUT/PATCH/DELETE/OPTIONS/...): cut BEFORE
        # routing and body parsing (the body is never read except at
        # demo sign-out). Without a session every unsafe admin path is
        # default-denied; with one, the uniform quiet no-content
        # no-change response covers every path - known or unknown - so
        # no handler can dispatch, no fake success page or visible
        # method error can appear, and no DML/audit/mail/provider
        # effect is possible. The single explicit exception is demo
        # sign-out.
        projection = await self._resolve_session(scope)
        if projection is None:
            await _respond_404(send)
            return
        if method == "POST" and path == DEMO_LOGOUT_PATH:
            await self._demo_logout(scope, receive, send)
            return
        await _respond_204(send)

    # --- session resolution (live fences) ------------------------------------

    async def _resolve_session(self, scope: dict):
        """Validate the demo session against the live control state.

        Returns the AUTHORITATIVE session projection (224-a law: live
        account enabled/generation, request and session expiry all
        re-checked), or ``None`` for any refusal - the caller never sees
        a reason, only a redirect or default denial.
        """
        token = _scope_cookies(scope).get(COOKIE_SESSION)
        if not token or len(token) > SIGNED_TOKEN_MAX_LEN:
            return None
        try:
            stored = await self._facade.session_facts_by_token(token)
            if stored is None:
                return None
            return await self._facade.validate_session(
                account_id=stored.account_id, token=token
            )
        except Exception:
            return None

    # --- per-request copy binding ---------------------------------------------

    async def _build_copy_state(self, scope: dict, projection):
        """Bind this read to the session's EXACT verified, unexpired copy.

        Any mismatch (wrong request/account, malformed name, not verified,
        expired, unreachable copy, wrong database) yields ``None`` -> one
        safe no-store refusal. No DSN, name or error detail escapes.
        """
        cfg = self._cfg
        try:
            snap_request = await self._facade.get_request(projection.request_id)
        except Exception:
            return None
        if (
            snap_request is None
            or snap_request.id != projection.request_id
            or snap_request.account_id != projection.account_id
            or snap_request.worker_target_db is None
            or _COPY_TARGET_DB_RE.fullmatch(snap_request.worker_target_db) is None
            or not _copy_readable_now(snap_request)
        ):
            return None
        target_db = snap_request.worker_target_db

        engine: AsyncEngine | None = None
        verified = False
        try:
            engine = create_async_engine(
                cfg.copy_engine_url(target_db),
                poolclass=NullPool,
                connect_args={
                    "ssl": False,
                    "timeout": _COPY_CONNECT_TIMEOUT_S,
                    "server_settings": {
                        "statement_timeout": str(int(_COPY_STATEMENT_TIMEOUT_S * 1000)),
                        "default_transaction_read_only": "on",
                    },
                },
            )
            # Preflight on THIS connection: the bound database AND the
            # database-side read-only mode that is the security backstop
            # for every later handler transaction on this engine.
            async with engine.connect() as conn:
                current = await conn.scalar(text("SELECT current_database()"))
                read_only = await conn.scalar(text("SHOW transaction_read_only"))
            verified = current == target_db and read_only == "on"
        except Exception:
            verified = False
        if not verified:
            # Dispose on EVERY failure path: a refused read must not
            # leave an idle copy connection behind.
            if engine is not None:
                await _safe_dispose(engine)
            return None

        token = _scope_cookies(scope).get(COOKIE_SESSION) or ""
        return DemoAdminState(
            session_context=self._fictional_context,
            csrf_token=_demo_csrf_token(cfg.cookie_secret, token),
            target_db=target_db,
            sessionmaker=create_sessionmaker_from_engine(engine),
            engine=engine,
        )

    # --- demo sign-out (the one unsafe exception) -----------------------------

    async def _demo_logout(self, scope: dict, receive, send) -> None:
        """CSRF-verified demo sign-out through the 224-c control service.

        NEVER dispatches the production admin logout service; the 303 goes
        back to the demo login/ready flow and clears ALL demo cookies.
        """
        cfg = self._cfg
        request = Request(scope, receive=receive)
        try:
            form = await _parse_bounded_form(request)
        except _FormBodyTooLarge:
            await _respond_413(send)
            return
        except ValueError:
            await _respond_400(send, "Invalid form fields.")
            return

        token = _scope_cookies(scope).get(COOKIE_SESSION)
        if not token or len(token) > SIGNED_TOKEN_MAX_LEN:
            await _respond_400(send, "Invalid or expired form. Please try again.")
            return
        expected = _demo_csrf_token(cfg.cookie_secret, token)
        provided = form.get("csrf_token")
        if (
            not isinstance(provided, str)
            or len(provided) > SIGNED_TOKEN_MAX_LEN
            or not hmac.compare_digest(expected, provided)
        ):
            await _respond_400(send, "Invalid or expired form. Please try again.")
            return

        # Sign-out may CLAIM success only after a confirmed revocation
        # (or nothing stored to revoke): the local cookie clear happens
        # only on that path. A revocation/control failure is a safe
        # no-store refusal - the session stays, the browser keeps the
        # cookies, and the operator can retry.
        try:
            stored = await self._facade.session_facts_by_token(token)
        except Exception:
            await _respond_400(
                send, "Sign-out could not be completed. Please try again."
            )
            return
        if stored is not None:
            try:
                result = await self._facade.revoke_session(
                    account_id=stored.account_id, token=token
                )
            except Exception:
                # A driver/control failure must never leak details and
                # must never look like a sign-out: safe no-store
                # refusal, cookies kept, retry allowed.
                await _respond_400(
                    send, "Sign-out could not be completed. Please try again."
                )
                return
            # A failed CAS must not look like a successful sign-out:
            # only a confirmed revoked projection (or absence) may
            # proceed to the redirect + cookie clear.
            if result is not None and result.revoked_at is None:
                await _respond_400(
                    send, "Sign-out could not be completed. Please try again."
                )
                return

        await send(
            {
                "type": "http.response.start",
                "status": 303,
                "headers": [
                    (b"location", LOGIN_URL.encode("ascii")),
                    (b"cache-control", b"no-store"),
                    _clear_cookie_header(COOKIE_SESSION, SESSION_COOKIE_PATH),
                    _clear_cookie_header(COOKIE_PENDING, "/fakeadmin"),
                    _clear_cookie_header(COOKIE_CSRF, "/fakeadmin"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})

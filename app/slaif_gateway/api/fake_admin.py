"""Objective 224-c: the isolated demo web entry surface (``/fakeadmin``).

These routes are mounted ONLY by the standalone demo app
(``demo_web.create_demo_app``). They implement the bounded entry flow:
login -> pending wait -> one session at the verified moment -> ready
page -> read-only copy preview (224-d: bounded counts from the
session's ONE verified copy) -> logout. Full copy-backed GUI
browsing is NOT part of this stage and the pages say so explicitly.

Safety law (224-c):

* zero enabled accounts -> 404 on EVERY demo route (no credential or
  existence oracle; the demo surface is indistinguishable from an
  unknown path);
* login: bounded attempt window, signed double-submit CSRF, finite
  field lengths, column-scoped credential lookup, one real Argon2id
  verification on either path (a precomputed dummy hash is checked for
  unknown/disabled usernames so the dominant verification cost is
  uniform), one constant failure message;
* wait: a signed cookie (lifetime tied to the 224-a request TTL, 60
  minutes - a legitimate bounded worker chain can exceed 15 minutes)
  binds ``account:request:generation``; the request's own expiry is
  the absolute bound and is re-checked on every poll;
  every poll rechecks the live request facts and the live account
  fence; session issuance happens ONLY here (one ``create_session``
  call, at the verified moment) and nowhere else;
* every page revalidates the session on use (``validate_session``);
  logout revokes idempotently and clears ALL demo cookies;
* cookies are HttpOnly, Secure, SameSite=Strict; the pending and CSRF
  cookies are Path=/fakeadmin. The demo SESSION cookie is deliberately
  Path=/ on the dedicated demo hostname (forward-compatible with the
  authorized later copy-backed GUI stage on the same host; this process
  has no normal /admin or /v1 routes and the cookie is demo-named).
  The session cookie carries the raw opaque token only (its hash is
  the only stored form); no raw secret, username, or request detail is
  ever rendered or echoed.
"""

from __future__ import annotations

import hmac
import time
import urllib.parse
import uuid
from collections import deque
from dataclasses import dataclass

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from slaif_gateway.demo_web import (
    CSRF_TTL_S,
    COPY_PREVIEW_TABLES,
    LOGIN_ATTEMPT_MAX,
    LOGIN_ATTEMPT_WINDOW_S,
    LOGIN_FIELD_MAX,
    PENDING_TTL_S,
    DemoWebConfig,
    DemoWebError,
    DemoWebFacade,
    SIGNED_TOKEN_MAX_LEN,
    make_signed_payload,
    verify_signed_payload,
)
from slaif_gateway.services.demo_web_control import DemoWebControlError
from slaif_gateway.utils.passwords import hash_admin_password, verify_admin_password

fake_admin_router = APIRouter(prefix="/fakeadmin", tags=["demo-admin-entry"])

# --- finite constants ---------------------------------------------------------

COOKIE_CSRF = "slaif_demo_csrf"
COOKIE_PENDING = "slaif_demo_pending"
COOKIE_SESSION = "slaif_demo_session"
SESSION_COOKIE_MAX_AGE_S = 3600  # server revalidates expiry on every use

PURPOSE_CSRF = "csrf"
PURPOSE_PENDING = "pending"

LOGIN_URL = "/fakeadmin/login"
WAIT_URL = "/fakeadmin/wait"
READY_URL = "/fakeadmin/ready"
COPY_PREVIEW_URL = "/fakeadmin/copy-preview"
LOGOUT_URL = "/fakeadmin/logout"

# Constant login failure message (no enumeration, ever).
LOGIN_FAILURE_MESSAGE = "Incorrect username or password."

# A REAL Argon2id hash of a fixed dummy secret, computed once per
# process: checked whenever the supplied username is unknown or the
# account is disabled so the verification cost (and thus response
# time) is uniform with a genuine credential check.
_DUMMY_PASSWORD = "slaif-demo-constant-time-dummy-v1"
# Precomputed ONCE at process startup: this module is only imported when
# the enabled demo app is built (or in tests), so the hash-generation
# cost is paid at startup - the FIRST unknown-user/disabled login must
# not carry an extra Argon2-generation timing signature.
_DUMMY_HASH: str = hash_admin_password(_DUMMY_PASSWORD)


def _dummy_hash() -> str:
    return _DUMMY_HASH


@dataclass
class _AttemptWindow:
    """Bounded in-process failed-login window (single demo process)."""

    failures: deque[float]

    def record(self, now: float) -> None:
        self.failures.append(now)

    def prune(self, now: float) -> None:
        cutoff = now - LOGIN_ATTEMPT_WINDOW_S
        while self.failures and self.failures[0] < cutoff:
            self.failures.popleft()

    def retry_after_s(self, now: float) -> int:
        self.prune(now)
        if len(self.failures) < LOGIN_ATTEMPT_MAX:
            return 0
        oldest = self.failures[0]
        return max(1, int(oldest + LOGIN_ATTEMPT_WINDOW_S - now) + 1)


# One limiter per demo process: this is a single-operator entry, not a
# public multi-tenant service (documented in docs/demo-admin.md).
_ATTEMPTS = _AttemptWindow(failures=deque())


# --- per-request accessors -------------------------------------------------------


def _config(request: Request) -> DemoWebConfig:
    return request.app.state.demo_config


def _facade(request: Request) -> DemoWebFacade:
    return request.app.state.demo_facade


def _templates(request: Request) -> Jinja2Templates:
    return request.app.state.demo_templates


def _json(status: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


async def _zero_active(request: Request) -> bool:
    """True when no enabled account exists: EVERY demo route 404s."""
    return await _facade(request).count_active_accounts() <= 0


def _set_cookie(
    response, name: str, value: str, max_age: int, *, path: str = "/fakeadmin"
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=path,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def _clear_cookie(response, name: str, *, path: str = "/fakeadmin") -> None:
    response.delete_cookie(name, path=path, secure=True, samesite="strict")


#: The demo SESSION cookie deliberately uses Path=/ (not /fakeadmin) on the
#: dedicated demo hostname: the authorized later GUI stage will serve
#: copy-backed /admin pages on that same host and the browser must present
#: the demo session cookie there. This is safe because this process
#: registers NO normal /admin or /v1 routes, the cookie has a distinct
#: demo-only name, and it carries the opaque demo token only. The pending
#: and CSRF cookies remain strictly Path=/fakeadmin.
SESSION_COOKIE_PATH = "/"


def _new_csrf_token(secret: str) -> str:
    return make_signed_payload(secret, PURPOSE_CSRF, uuid.uuid4().hex, CSRF_TTL_S)


def _check_csrf(secret: str, cookie_value: str | None, field_value: str | None) -> bool:
    """Signed double-submit CSRF check.

    Both comparisons are constant-time: the double-submit equality is
    ``hmac.compare_digest`` (on UTF-8 bytes, after type/length checks)
    and the signature verification inside ``verify_signed_payload``
    uses ``hmac.compare_digest`` as well. A mismatching equality is
    rejected before any decode; the finite length bound applies to
    BOTH cookie and field values.
    """
    if not isinstance(field_value, str):
        return False
    if len(field_value) > SIGNED_TOKEN_MAX_LEN:
        return False
    if not isinstance(cookie_value, str):
        return False
    if len(cookie_value) > SIGNED_TOKEN_MAX_LEN:
        return False
    if not hmac.compare_digest(
        cookie_value.encode("utf-8"), field_value.encode("utf-8")
    ):
        return False
    return verify_signed_payload(secret, PURPOSE_CSRF, field_value, CSRF_TTL_S) is not None


class _FormBodyTooLarge(Exception):
    """The request body exceeded the finite form bound."""


#: Finite byte bound for the login/logout form bodies (the largest
#: legitimate body is ~1 KiB: 128 + 128 + signed CSRF + separators).
FORM_BODY_MAX_BYTES = 8192


async def _parse_bounded_form(request: Request) -> dict[str, str]:
    """Parse a finite ``application/x-www-form-urlencoded`` body.

    The bound is enforced on the BYTES ACTUALLY RECEIVED while reading
    the stream incrementally, so it applies to chunked/unknown-length
    bodies as well (a lying Content-Length cannot bypass it). Parsing
    never happens before the bound is proven. Raises
    ``_FormBodyTooLarge`` when the bound is exceeded and ``ValueError``
    for unsupported content types or undecodable bytes.
    """
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" not in ctype:
        raise ValueError("unsupported form content type")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > FORM_BODY_MAX_BYTES:
            raise _FormBodyTooLarge()
        chunks.append(chunk)
    try:
        text = b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("undecodable form body") from exc
    return dict(urllib.parse.parse_qsl(text, keep_blank_values=True))


def _parse_pending_payload(payload: str | None) -> tuple[uuid.UUID, uuid.UUID, int] | None:
    """Parse and validate the signed pending payload
    ``account_id:request_id:generation``; None when malformed."""
    if not payload:
        return None
    parts = payload.split(":")
    if len(parts) != 3:
        return None
    try:
        account_id = uuid.UUID(parts[0])
        request_id = uuid.UUID(parts[1])
        generation = int(parts[2])
    except (ValueError, AttributeError):
        return None
    if generation < 0:
        return None
    return account_id, request_id, generation


async def _verify_session_cookie(
    request: Request, token: str | None
) -> bool:
    """Full per-use session validation (account resolved from the token)."""
    if not token:
        return False
    facade = _facade(request)
    facts = await facade.session_facts_by_token(token)
    if facts is None:
        return False
    try:
        await facade.validate_session(account_id=facts.account_id, token=token)
    except DemoWebControlError:
        return False
    return True


# --- login -------------------------------------------------------------------------


@fake_admin_router.get("/login", name="demo_login")
async def demo_login_get(request: Request) -> object:
    cfg = _config(request)
    if await _zero_active(request):
        return _json(404, "Not Found")
    csrf_token = _new_csrf_token(cfg.cookie_secret)
    response = _templates(request).TemplateResponse(
        request, "login.html", {"csrf": csrf_token, "error": None}
    )
    _set_cookie(response, COOKIE_CSRF, csrf_token, int(CSRF_TTL_S))
    return response


@fake_admin_router.post("/login", name="demo_login_post")
async def demo_login_post(request: Request) -> object:
    cfg = _config(request)
    facade = _facade(request)
    if await _zero_active(request):
        return _json(404, "Not Found")

    now = time.monotonic()
    _ATTEMPTS.prune(now)
    if len(_ATTEMPTS.failures) >= LOGIN_ATTEMPT_MAX:
        response = _json(429, "Too many failed login attempts. Try again later.")
        response.headers["Retry-After"] = str(_ATTEMPTS.retry_after_s(now))
        return response

    try:
        form = await _parse_bounded_form(request)
    except _FormBodyTooLarge:
        return _json(413, "Request body too large.")
    except ValueError:
        return _json(400, "Invalid form fields.")
    username = form.get("username")
    password = form.get("password")
    csrf_field = form.get("csrf")
    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or len(username) > LOGIN_FIELD_MAX
        or len(password) > LOGIN_FIELD_MAX
        or not username
        or not password
    ):
        return _json(400, "Invalid form fields.")
    if not _check_csrf(cfg.cookie_secret, request.cookies.get(COOKIE_CSRF), csrf_field):
        return _json(400, "Invalid or expired login form. Please try again.")

    credential = await facade.get_login_credential(username)
    if credential is None or not credential.is_enabled:
        # Uniform cost: run a real Argon2id verification against the
        # fixed dummy hash so unknown and disabled accounts are
        # indistinguishable from genuine wrong-password checks.
        await run_in_threadpool(verify_admin_password, password, _dummy_hash())
    else:
        password_ok = await run_in_threadpool(
            verify_admin_password, password, credential.password_hash
        )
        if not password_ok:
            _ATTEMPTS.record(now)
            return _login_failure(request)
        account_id = credential.id
        generation = credential.credential_generation
    if credential is None or not credential.is_enabled:
        _ATTEMPTS.record(now)
        return _login_failure(request)

    # Success: create ONE fresh pending request, hand off the signed
    # pending cookie, and move the browser to the wait surface.
    try:
        snap_request = await facade.create_request(account_id)
    except DemoWebControlError as exc:
        if exc.code == "web_no_active_accounts":
            return _json(404, "Not Found")
        return _login_failure(request)
    pending_payload = f"{account_id}:{snap_request.id}:{generation}"
    pending_token = make_signed_payload(
        cfg.cookie_secret, PURPOSE_PENDING, pending_payload, PENDING_TTL_S
    )
    response = RedirectResponse(WAIT_URL, status_code=303)
    _set_cookie(response, COOKIE_PENDING, pending_token, int(PENDING_TTL_S))
    _clear_cookie(response, COOKIE_CSRF)
    return response


def _login_failure(request: Request) -> RedirectResponse:
    """Constant-time-safe login failure: one message, fresh CSRF form."""
    cfg = _config(request)
    csrf_token = _new_csrf_token(cfg.cookie_secret)
    response = _templates(request).TemplateResponse(
        request, "login.html", {"csrf": csrf_token, "error": LOGIN_FAILURE_MESSAGE}
    )
    response.status_code = 401
    _set_cookie(response, COOKIE_CSRF, csrf_token, int(CSRF_TTL_S))
    return response


# --- wait --------------------------------------------------------------------------


def _wait_state_for(snap_request) -> str:
    """Finite wait-surface state from the live request projection."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    state = snap_request.state
    if state in ("pending", "claimed"):
        return "waiting"
    if state == "verified_unpublished":
        if snap_request.expires_at is not None and now >= snap_request.expires_at:
            return "timed_out"
        return "ready"
    if state == "failed":
        return "failed"
    return "unavailable"  # cleanup_pending / cleaned


def _pending_binding(request: Request) -> tuple[uuid.UUID, uuid.UUID, int] | None:
    cfg = _config(request)
    payload = verify_signed_payload(
        cfg.cookie_secret,
        PURPOSE_PENDING,
        request.cookies.get(COOKIE_PENDING),
        PENDING_TTL_S,
    )
    return _parse_pending_payload(payload)


def _clear_pending(response, request: Request) -> None:
    _clear_cookie(response, COOKIE_PENDING)


async def _wait_facts(
    request: Request,
) -> tuple[str, object, uuid.UUID | None, uuid.UUID | None, int | None]:
    """(state, snap_request, account_id, request_id, generation).

    ``state`` is one of waiting|ready|timed_out|failed|unavailable.
    Invalid or expired pending cookie -> ("unavailable", None, ...).
    """
    facade = _facade(request)
    binding = _pending_binding(request)
    if binding is None:
        return "unavailable", None, None, None, None
    account_id, request_id, generation = binding
    snap_request = await facade.get_request(request_id)
    if snap_request is None or snap_request.account_id != account_id:
        return "unavailable", None, None, None, None
    # LIVE account fence on EVERY poll (page and /status): a disabled or
    # deleted account, or a credential reset (generation moved) after the
    # request was made, denies the wait surface immediately - even while
    # other fake admins remain active. The cookie generation and the
    # request's recorded generation must still agree with the live
    # account as well.
    account = await facade.get_account_facts(account_id)
    if (
        account is None
        or not account.is_enabled
        or int(account.credential_generation) != int(snap_request.credential_generation)
        or int(generation) != int(snap_request.credential_generation)
    ):
        return "unavailable", None, None, None, None
    return (
        _wait_state_for(snap_request),
        snap_request,
        account_id,
        request_id,
        generation,
    )


@fake_admin_router.get("/wait", name="demo_wait")
async def demo_wait_get(request: Request) -> object:
    facade = _facade(request)
    if await _zero_active(request):
        return _json(404, "Not Found")

    state, snap_request, account_id, request_id, generation = await _wait_facts(request)
    if state in ("failed", "unavailable", "timed_out"):
        # Terminal: drop the pending cookie; the browser may log in again.
        response = _templates(request).TemplateResponse(
            request, "wait.html", {"state": state}
        )
        _clear_pending(response, request)
        return response
    if state == "waiting":
        return _templates(request).TemplateResponse(request, "wait.html", {"state": state})

    # state == "ready": recheck the live account fence, then issue the
    # ONE session for this exact verified copy (the only issuance point
    # in the demo web app).
    if account_id is None or request_id is None or generation is None:
        return _templates(request).TemplateResponse(
            request, "wait.html", {"state": "unavailable"}
        )
    account = await facade.get_account_facts(account_id)
    if (
        account is None
        or not account.is_enabled
        or account.credential_generation != generation
    ):
        response = _templates(request).TemplateResponse(
            request, "wait.html", {"state": "unavailable"}
        )
        _clear_pending(response, request)
        return response
    try:
        issued = await facade.create_session(account_id=account_id, request_id=request_id)
    except DemoWebControlError:
        # Refused (not verified / expired / copy reused / disabled):
        # show the safest finite state the request projection still has.
        refreshed = await facade.get_request(request_id)
        state = _wait_state_for(refreshed) if refreshed is not None else "unavailable"
        response = _templates(request).TemplateResponse(
            request, "wait.html", {"state": state}
        )
        if refreshed is None or refreshed.state != "verified_unpublished":
            _clear_pending(response, request)
        return response
    response = RedirectResponse(READY_URL, status_code=303)
    _set_cookie(
        response, COOKIE_SESSION, issued.token, SESSION_COOKIE_MAX_AGE_S,
        path=SESSION_COOKIE_PATH,
    )
    _clear_pending(response, request)
    return response


@fake_admin_router.get("/wait/status", name="demo_wait_status")
async def demo_wait_status(request: Request) -> object:
    """JSON poll endpoint: reports state only, NEVER issues a session."""
    if await _zero_active(request):
        return _json(404, "Not Found")
    state, _snap, _account, _request_id, _generation = await _wait_facts(request)
    return {"state": state}


# --- ready / logout ------------------------------------------------------------------


@fake_admin_router.get("/ready", name="demo_ready")
async def demo_ready_get(request: Request) -> object:
    cfg = _config(request)
    if await _zero_active(request):
        return _json(404, "Not Found")
    token = request.cookies.get(COOKIE_SESSION)
    if not await _verify_session_cookie(request, token):
        response = RedirectResponse(LOGIN_URL, status_code=303)
        _clear_cookie(response, COOKIE_SESSION, path=SESSION_COOKIE_PATH)
        return response
    csrf_token = _new_csrf_token(cfg.cookie_secret)
    response = _templates(request).TemplateResponse(
        request, "ready.html", {"csrf": csrf_token}
    )
    _set_cookie(response, COOKIE_CSRF, csrf_token, int(CSRF_TTL_S))
    return response


def _copy_readable_now(snap_request) -> bool:
    """The session's copy is readable ONLY while its EXACT request is
    verified and unexpired (re-checked on every read; the request's
    own expiry is the absolute bound)."""
    from datetime import datetime, timezone

    if snap_request.state != "verified_unpublished":
        return False
    if (
        snap_request.expires_at is not None
        and datetime.now(timezone.utc) >= snap_request.expires_at
    ):
        return False
    return True


@fake_admin_router.get("/copy-preview", name="demo_copy_preview")
async def demo_copy_preview_get(request: Request) -> object:
    """224-d read-only copy preview: safe bounded COUNTS from the
    session's ONE verified copy - a proof of the copy binding, not an
    admin UI. Fail-closed: no target name, DSN, credential or
    internal error ever reaches the page; an unreadable copy renders
    the one safe note instead. The response is ``no-store`` so the
    browser cache never retains demo facts after logout.
    """
    cfg = _config(request)
    if await _zero_active(request):
        return _json(404, "Not Found")
    token = request.cookies.get(COOKIE_SESSION)
    facade = _facade(request)

    def _bounce() -> RedirectResponse:
        response = RedirectResponse(LOGIN_URL, status_code=303)
        _clear_cookie(response, COOKIE_SESSION, path=SESSION_COOKIE_PATH)
        return response

    if not token:
        return _bounce()
    # Stored binding (raw token only; the hash is the stored form)
    # resolves the account; the full per-use validation (live
    # account/generation fence) then returns the AUTHORITATIVE
    # session projection - the same law as the ready page.
    stored = await facade.session_facts_by_token(token)
    if stored is None:
        return _bounce()
    try:
        session = await facade.validate_session(
            account_id=stored.account_id, token=token
        )
    except DemoWebControlError:
        return _bounce()
    # The EXACT request binding from the control row: it must be the
    # validated session's own request (id AND account match) and be
    # verified and unexpired; ONLY its closed demo_snap_<20hex> copy
    # name is accepted. Construction AND read share one safe-error
    # boundary: a malformed stored name is a safe refusal, never a
    # raw error or a DSN.
    counts: dict[str, int] | None = None
    snap_request = await facade.get_request(session.request_id)
    if snap_request is not None and (
        snap_request.id == session.request_id
        and snap_request.account_id == session.account_id
        and _copy_readable_now(snap_request)
        and snap_request.worker_target_db is not None
    ):
        factory = request.app.state.demo_copy_reader_factory
        try:
            reader = factory(cfg, snap_request.worker_target_db)
            counts = await reader.read()
        except DemoWebError:
            counts = None  # one safe note; no detail escapes
    csrf_token = _new_csrf_token(cfg.cookie_secret)
    response = _templates(request).TemplateResponse(
        request,
        "copy_preview.html",
        {"csrf": csrf_token, "counts": counts, "tables": COPY_PREVIEW_TABLES},
    )
    response.headers["Cache-Control"] = "no-store"
    _set_cookie(response, COOKIE_CSRF, csrf_token, int(CSRF_TTL_S))
    return response


@fake_admin_router.get("/files-preview", name="demo_files_preview")
async def demo_files_preview_get(request: Request) -> object:
    """224-g read-only display-leaf preview: the SAFE INDEX only
    (closed logical names, kinds, byte counts, capture times) from
    the session's ONE verified copy target-only ``demo_display``
    schema - a proof of the display publication, not a file browser.
    No body bytes are rendered in this suffix. Fail-closed: no target
    name, DSN, credential or internal error ever reaches the page; an
    unreadable or pre-upgrade (display-less) copy renders the one
    safe note instead. EVERY response of this route - login redirect,
    zero-active 404, safe note and successful page - is explicitly
    ``Cache-Control: no-store`` so the browser cache never retains
    demo facts after logout.
    """
    from datetime import datetime, timezone

    cfg = _config(request)
    if await _zero_active(request):
        # 224-h: EVERY files-preview response carries no-store,
        # including this 404 (the shared _json helper used by the
        # other demo routes stays untouched).
        response = JSONResponse(
            status_code=404, content={"detail": "Not Found"}
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    token = request.cookies.get(COOKIE_SESSION)
    facade = _facade(request)

    def _bounce() -> RedirectResponse:
        response = RedirectResponse(LOGIN_URL, status_code=303)
        response.headers["Cache-Control"] = "no-store"
        _clear_cookie(response, COOKIE_SESSION, path=SESSION_COOKIE_PATH)
        return response

    if not token:
        return _bounce()
    # The same full per-use validation law as the copy preview: the
    # stored token resolves the account and the live
    # account/generation fence is re-checked on every read.
    stored = await facade.session_facts_by_token(token)
    if stored is None:
        return _bounce()
    try:
        session = await facade.validate_session(
            account_id=stored.account_id, token=token
        )
    except DemoWebControlError:
        return _bounce()
    # The EXACT request binding from the control row (id AND account
    # match, verified, unexpired) and ONLY its closed demo_snap_<20hex>
    # copy name are accepted. Construction AND read share one
    # safe-error boundary: a malformed stored name or a pre-upgrade
    # display-less copy is a safe note, never a raw error or a DSN.
    leaves: list[dict[str, object]] | None = None
    snap_request = await facade.get_request(session.request_id)
    if snap_request is not None and (
        snap_request.id == session.request_id
        and snap_request.account_id == session.account_id
        and _copy_readable_now(snap_request)
        and snap_request.worker_target_db is not None
    ):
        factory = request.app.state.demo_display_reader_factory
        try:
            reader = factory(cfg, snap_request.worker_target_db)
            raw_leaves = await reader.read_index()
            formatted: list[dict[str, object]] | None = []
            for leaf in raw_leaves:
                try:
                    captured_utc = datetime.fromtimestamp(
                        float(leaf["captured_at"]), tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except (OverflowError, OSError, TypeError, ValueError):
                    # 224-h: a stored capture time outside the
                    # representable range (legacy writer or a
                    # corrupted value) never becomes a 500 or leaks
                    # raw bytes - the page falls back to the same
                    # safe note.
                    formatted = None
                    break
                formatted.append({**leaf, "captured_utc": captured_utc})
            if formatted is not None:
                leaves = formatted
        except DemoWebError:
            leaves = None  # one safe note; no detail escapes
    csrf_token = _new_csrf_token(cfg.cookie_secret)
    response = _templates(request).TemplateResponse(
        request,
        "files_preview.html",
        {"csrf": csrf_token, "leaves": leaves},
    )
    response.headers["Cache-Control"] = "no-store"
    _set_cookie(response, COOKIE_CSRF, csrf_token, int(CSRF_TTL_S))
    return response


@fake_admin_router.post("/logout", name="demo_logout")
async def demo_logout_post(request: Request) -> object:
    cfg = _config(request)
    facade = _facade(request)
    if await _zero_active(request):
        return _json(404, "Not Found")
    try:
        form = await _parse_bounded_form(request)
    except _FormBodyTooLarge:
        return _json(413, "Request body too large.")
    except ValueError:
        return _json(400, "Invalid form fields.")
    if not _check_csrf(cfg.cookie_secret, request.cookies.get(COOKIE_CSRF), form.get("csrf")):
        return _json(400, "Invalid or expired form. Please try again.")
    token = request.cookies.get(COOKIE_SESSION)
    if token:
        facts = await facade.session_facts_by_token(token)
        if facts is not None:
            # Idempotent, safe: revocation never fails the logout flow.
            try:
                await facade.revoke_session(account_id=facts.account_id, token=token)
            except DemoWebControlError:
                pass  # the local cookie clear below always proceeds
    response = RedirectResponse(LOGIN_URL, status_code=303)
    _clear_cookie(response, COOKIE_SESSION, path=SESSION_COOKIE_PATH)
    _clear_cookie(response, COOKIE_PENDING)
    _clear_cookie(response, COOKIE_CSRF)
    return response

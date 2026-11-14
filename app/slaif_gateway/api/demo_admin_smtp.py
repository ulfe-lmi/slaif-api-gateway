"""Demo-host read-only SMTP-test views (224-w).

The standalone demo process admits the exact two GET shapes over the
visitor's verified per-login SELECT-only copy:

* ``GET /admin/email-operations/smtp-test``     (form, query-free);
* ``GET /admin/email-operations/smtp-test/apply`` (recovery, query-free).

The central demo gate admits ONLY these exact shapes and keeps every
unsafe method - including the normal review/apply POSTs - the pre-body
quiet 204 cut.

Read law: ONE request-local SELECT-only transaction on the gate-bound
engine with the independent ``current_database()`` /
``transaction_read_only`` recheck. The 223 capture scope records NO
source email/SMTP facts (there is no SMTP display leaf and no copied
SMTP settings table), so both pages render the fixed "not recorded"
state: the demo process's own (dummy) SMTP settings are NEVER used as
source readiness, and no SMTP host, user or password is ever displayed
or used. The existing styled form/recovery views are shown with their
useful recipient/subject/body hints and visible review/send controls,
clearly labeled as quiet no-ops; the apply-recovery page is a fixed
no-send notice. There is no live one-use token, no test send, no
broker/mail access, and no false success. Corrupt or unavailable copy
binding is the fixed safe 503.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from slaif_gateway.api.admin import templates
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services.email_admin_operations import (
    SMTP_TEST_BUDGET_ATTEMPTS,
    SMTP_TEST_BUDGET_WINDOW_SECONDS,
    SMTP_TEST_DEFAULT_BODY,
    SMTP_TEST_DEFAULT_SUBJECT,
)

router = APIRouter(
    prefix="/admin/email-operations", include_in_schema=False
)

_SAFE_NOT_FOUND = "Not Found"
_SAFE_UNAVAILABLE = (
    "The SMTP test page is unavailable for this demo session."
)


def _not_found() -> Response:
    return HTMLResponse(
        _SAFE_NOT_FOUND, status_code=404, headers={"Cache-Control": "private, no-store"}
    )


def _unavailable() -> Response:
    return HTMLResponse(
        _SAFE_UNAVAILABLE, status_code=503, headers={"Cache-Control": "private, no-store"}
    )


def _no_query(request: Request) -> bool:
    return not request.query_params.multi_items()


async def _copy_recheck(session: Any, target_db: str) -> bool:
    current = await session.scalar(text("SELECT current_database()"))
    read_only = await session.scalar(text("SHOW transaction_read_only"))
    return current == target_db and read_only == "on"


async def _verified_copy_check(request: Request, demo: Any) -> bool:
    """The single request-local rechecked SELECT-only transaction.

    The 223 capture records no SMTP facts, so the recheck itself is the
    only copy read; it proves the request is bound to the session's
    exact verified copy before any page is rendered."""
    try:
        session_factory = get_sessionmaker_from_app(request)
    except Exception:
        return False
    try:
        async with session_factory() as session, session.begin():
            return await _copy_recheck(session, demo.target_db)
    except Exception:  # noqa: BLE001 - unavailable, never ambient
        return False


def _base_context(request: Request, demo: Any) -> dict[str, Any]:
    return {
        "admin": demo.session_context.admin_user,
        "csrf_token": demo.csrf_token,
        "admin_status_message": None,
        "demo_admin": True,
        # Product constants only (finite package strings/numbers): no
        # source deployment setting is read or displayed.
        "default_subject": SMTP_TEST_DEFAULT_SUBJECT,
        "default_body": SMTP_TEST_DEFAULT_BODY,
        "budget_attempts": SMTP_TEST_BUDGET_ATTEMPTS,
        "budget_window_seconds": SMTP_TEST_BUDGET_WINDOW_SECONDS,
    }


@router.get("/smtp-test", response_class=HTMLResponse)
async def demo_smtp_test_form(request: Request) -> Response:
    """224-w: the demo SMTP-test form (query-free, gate-admitted).

    Renders the existing styled form from the fixed "not recorded"
    state: no source SMTP settings were captured, the demo process's
    dummy settings are never shown as readiness, and the visible
    review/send controls are labeled quiet no-ops."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or not _no_query(request):
        return _not_found()
    if not await _verified_copy_check(request, demo):
        return _unavailable()
    context = _base_context(request, demo)
    # The template's unavailable-panel branch is for NORMAL readiness
    # facts; in demo the readiness state is simply not recorded, so the
    # form branch renders with the demo banner (readiness stays None).
    context["readiness"] = None
    response = templates.TemplateResponse(
        request,
        "email_operations/smtp_test.html",
        context,
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get("/smtp-test/apply", response_class=HTMLResponse)
async def demo_smtp_test_apply_recovery(request: Request) -> Response:
    """224-w: the demo apply-recovery page (query-free, gate-admitted).

    A fixed no-send notice: no live one-use token exists in the demo,
    no reviewed content is displayed, and nothing is ever sent."""
    demo = getattr(request.state, "demo_admin", None)
    if demo is None or not _no_query(request):
        return _not_found()
    if not await _verified_copy_check(request, demo):
        return _unavailable()
    context = _base_context(request, demo)
    context.update(
        recovery=True,
        facts=None,
        review_token=None,
        result=None,
        error=None,
        result_recorded=True,
        # Referenced only inside the (absent) facts branch; never a
        # live deadline computation in the demo process.
        outer_deadline_seconds=None,
    )
    response = templates.TemplateResponse(
        request,
        "email_operations/smtp_test_review.html",
        context,
        status_code=200,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response

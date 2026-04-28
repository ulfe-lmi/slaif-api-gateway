"""Server-rendered admin authentication routes."""

from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.auth.csrf import CsrfError, create_login_csrf_token, verify_login_csrf_token
from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.admin_sessions import AdminSessionsRepository
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services.admin_session_service import (
    AdminAuthenticationError,
    AdminSessionContext,
    AdminSessionError,
    AdminSessionService,
)

router = APIRouter(prefix="/admin", include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "web" / "templates"))


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    context = await _get_current_admin_context(request)
    if context is not None:
        return RedirectResponse("/admin", status_code=303)

    try:
        csrf_token = create_login_csrf_token(settings)
    except CsrfError:
        return _admin_unavailable()
    response = _render_login(request, csrf_token=csrf_token)
    _set_login_csrf_cookie(response, settings, csrf_token)
    return response


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        verify_login_csrf_token(
            settings,
            form_token=csrf_token,
            cookie_token=request.cookies.get(settings.ADMIN_LOGIN_CSRF_COOKIE_NAME),
        )
    except CsrfError:
        try:
            replacement = create_login_csrf_token(settings)
        except CsrfError:
            return _admin_unavailable()
        response = _render_login(
            request,
            csrf_token=replacement,
            error="Your login form expired. Try again.",
            status_code=400,
        )
        _set_login_csrf_cookie(response, settings, replacement)
        return response

    try:
        async with _admin_service_scope(request) as service:
            admin_user = await service.authenticate_admin(
                email=email,
                password=password,
                ip_address=_client_host(request),
                user_agent=request.headers.get("user-agent"),
            )
            created_session = await service.create_admin_session(
                admin_user_id=admin_user.id,
                ip_address=_client_host(request),
                user_agent=request.headers.get("user-agent"),
            )
    except AdminAuthenticationError:
        try:
            replacement = create_login_csrf_token(settings)
        except CsrfError:
            return _admin_unavailable()
        response = _render_login(
            request,
            csrf_token=replacement,
            error="Invalid email or password.",
            status_code=401,
        )
        _set_login_csrf_cookie(response, settings, replacement)
        return response
    except (AdminSessionError, RuntimeError):
        try:
            replacement = create_login_csrf_token(settings)
        except CsrfError:
            return _admin_unavailable()
        response = _render_login(
            request,
            csrf_token=replacement,
            error="Admin login is not available.",
            status_code=503,
        )
        _set_login_csrf_cookie(response, settings, replacement)
        return response

    response = RedirectResponse("/admin", status_code=303)
    _clear_login_csrf_cookie(response, settings)
    response.set_cookie(
        settings.ADMIN_SESSION_COOKIE_NAME,
        created_session.session_token,
        max_age=settings.ADMIN_SESSION_TTL_SECONDS,
        httponly=settings.ADMIN_SESSION_COOKIE_HTTPONLY,
        secure=settings.admin_session_cookie_secure(),
        samesite=settings.ADMIN_SESSION_COOKIE_SAMESITE,
    )
    return response


@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    session_token = request.cookies.get(settings.ADMIN_SESSION_COOKIE_NAME)
    if not session_token:
        return RedirectResponse("/admin/login", status_code=303)

    try:
        async with _admin_service_scope(request) as service:
            context = await service.validate_admin_session(session_token=session_token)
            csrf_token = await service.refresh_csrf_token(admin_session_id=context.admin_session.id)
    except (AdminSessionError, RuntimeError):
        response = RedirectResponse("/admin/login", status_code=303)
        _clear_session_cookie(response, settings)
        return response

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
        },
    )


@router.post("/logout", response_class=HTMLResponse)
async def logout(request: Request, csrf_token: str = Form("")) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    session_token = request.cookies.get(settings.ADMIN_SESSION_COOKIE_NAME)
    if not session_token:
        response = RedirectResponse("/admin/login", status_code=303)
        _clear_session_cookie(response, settings)
        return response

    try:
        async with _admin_service_scope(request) as service:
            context = await service.validate_admin_session(session_token=session_token, touch=False)
            if not service.verify_session_csrf_token(context.admin_session, csrf_token):
                return HTMLResponse("Invalid CSRF token.", status_code=400)
            await service.revoke_admin_session(
                session_token=session_token,
                ip_address=_client_host(request),
                user_agent=request.headers.get("user-agent"),
            )
    except (AdminSessionError, RuntimeError):
        pass

    response = RedirectResponse("/admin/login", status_code=303)
    _clear_session_cookie(response, settings)
    return response


async def _get_current_admin_context(request: Request) -> AdminSessionContext | None:
    settings = _settings(request)
    session_token = request.cookies.get(settings.ADMIN_SESSION_COOKIE_NAME)
    if not session_token:
        return None
    try:
        async with _admin_service_scope(request) as service:
            return await service.validate_admin_session(session_token=session_token)
    except (AdminSessionError, RuntimeError):
        return None


@asynccontextmanager
async def _admin_service_scope(request: Request) -> AsyncIterator[AdminSessionService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield _build_admin_session_service(request, session)


def _build_admin_session_service(request: Request, session: AsyncSession) -> AdminSessionService:
    return AdminSessionService(
        settings=_settings(request),
        admin_users_repository=AdminUsersRepository(session),
        admin_sessions_repository=AdminSessionsRepository(session),
        audit_repository=AuditRepository(session),
    )


def _render_login(
    request: Request,
    *,
    csrf_token: str,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "csrf_token": csrf_token,
            "error": error,
        },
        status_code=status_code,
    )


def _set_login_csrf_cookie(response: Response, settings: Settings, csrf_token: str) -> None:
    response.set_cookie(
        settings.ADMIN_LOGIN_CSRF_COOKIE_NAME,
        csrf_token,
        max_age=settings.ADMIN_CSRF_TTL_SECONDS,
        httponly=True,
        secure=settings.admin_session_cookie_secure(),
        samesite=settings.ADMIN_SESSION_COOKIE_SAMESITE,
    )


def _clear_login_csrf_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.ADMIN_LOGIN_CSRF_COOKIE_NAME,
        httponly=True,
        secure=settings.admin_session_cookie_secure(),
        samesite=settings.ADMIN_SESSION_COOKIE_SAMESITE,
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.ADMIN_SESSION_COOKIE_NAME,
        httponly=settings.ADMIN_SESSION_COOKIE_HTTPONLY,
        secure=settings.admin_session_cookie_secure(),
        samesite=settings.ADMIN_SESSION_COOKIE_SAMESITE,
    )


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _client_host(request: Request) -> str | None:
    if request.client is None:
        return None
    host = request.client.host
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return None
    return host


def _admin_not_found() -> HTMLResponse:
    return HTMLResponse("Not found.", status_code=404)


def _admin_unavailable() -> HTMLResponse:
    return HTMLResponse("Admin login is not available.", status_code=503)

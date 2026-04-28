"""Server-rendered admin authentication routes."""

from __future__ import annotations

import ipaddress
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.auth.csrf import CsrfError, create_login_csrf_token, verify_login_csrf_token
from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.admin_sessions import AdminSessionsRepository
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services.admin_catalog_dashboard import AdminCatalogDashboardService, AdminCatalogNotFoundError
from slaif_gateway.services.admin_key_dashboard import AdminKeyDashboardService, AdminKeyNotFoundError
from slaif_gateway.services.admin_records_dashboard import AdminRecordNotFoundError, AdminRecordsDashboardService
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


@router.get("/keys", response_class=HTMLResponse)
async def list_admin_keys(
    request: Request,
    status: str | None = Query(None),
    owner_email: str | None = Query(None),
    public_key_id: str | None = Query(None),
    institution_id: str | None = Query(None),
    cohort_id: str | None = Query(None),
    expired: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    parsed_institution_id = _parse_optional_uuid(institution_id)
    parsed_cohort_id = _parse_optional_uuid(cohort_id)
    if parsed_institution_id is False or parsed_cohort_id is False:
        return HTMLResponse("Invalid filter.", status_code=400)

    async with _admin_key_dashboard_service_scope(request) as service:
        rows = await service.list_keys(
            status=status,
            owner_email=owner_email,
            public_key_id=public_key_id,
            institution_id=parsed_institution_id,
            cohort_id=parsed_cohort_id,
            expired=expired,
            limit=limit,
            offset=offset,
        )

    return templates.TemplateResponse(
        request,
        "keys/list.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "keys": rows,
            "filters": {
                "status": status or "",
                "owner_email": owner_email or "",
                "public_key_id": public_key_id or "",
                "institution_id": institution_id or "",
                "cohort_id": cohort_id or "",
                "expired": "" if expired is None else str(expired).lower(),
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/keys/{gateway_key_id}", response_class=HTMLResponse)
async def admin_key_detail(request: Request, gateway_key_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_key_id = uuid.UUID(gateway_key_id)
    except ValueError:
        return HTMLResponse("Gateway key not found.", status_code=404)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_key_dashboard_service_scope(request) as service:
            key = await service.get_key_detail(parsed_key_id)
    except AdminKeyNotFoundError:
        return HTMLResponse("Gateway key not found.", status_code=404)

    return templates.TemplateResponse(
        request,
        "keys/detail.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "key": key,
        },
    )


@router.get("/owners", response_class=HTMLResponse)
async def list_admin_owners(
    request: Request,
    email: str | None = Query(None),
    institution_id: str | None = Query(None),
    cohort_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    parsed_institution_id = _parse_optional_uuid(institution_id)
    parsed_cohort_id = _parse_optional_uuid(cohort_id)
    if parsed_institution_id is False or parsed_cohort_id is False:
        return HTMLResponse("Invalid filter.", status_code=400)

    async with _admin_records_dashboard_service_scope(request) as service:
        rows = await service.list_owners(
            email=email,
            institution_id=parsed_institution_id,
            cohort_id=parsed_cohort_id,
            limit=limit,
            offset=offset,
        )

    return templates.TemplateResponse(
        request,
        "owners/list.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "owners": rows,
            "filters": {
                "email": email or "",
                "institution_id": institution_id or "",
                "cohort_id": cohort_id or "",
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/owners/{owner_id}", response_class=HTMLResponse)
async def admin_owner_detail(request: Request, owner_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_owner_id = uuid.UUID(owner_id)
    except ValueError:
        return HTMLResponse("Owner not found.", status_code=404)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_records_dashboard_service_scope(request) as service:
            owner = await service.get_owner_detail(parsed_owner_id)
    except AdminRecordNotFoundError:
        return HTMLResponse("Owner not found.", status_code=404)

    return templates.TemplateResponse(
        request,
        "owners/detail.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "owner": owner,
        },
    )


@router.get("/institutions", response_class=HTMLResponse)
async def list_admin_institutions(
    request: Request,
    name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    async with _admin_records_dashboard_service_scope(request) as service:
        rows = await service.list_institutions(name=name, limit=limit, offset=offset)

    return templates.TemplateResponse(
        request,
        "institutions/list.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "institutions": rows,
            "filters": {
                "name": name or "",
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/institutions/{institution_id}", response_class=HTMLResponse)
async def admin_institution_detail(request: Request, institution_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_institution_id = uuid.UUID(institution_id)
    except ValueError:
        return HTMLResponse("Institution not found.", status_code=404)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_records_dashboard_service_scope(request) as service:
            institution = await service.get_institution_detail(parsed_institution_id)
    except AdminRecordNotFoundError:
        return HTMLResponse("Institution not found.", status_code=404)

    return templates.TemplateResponse(
        request,
        "institutions/detail.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "institution": institution,
        },
    )


@router.get("/cohorts", response_class=HTMLResponse)
async def list_admin_cohorts(
    request: Request,
    name: str | None = Query(None),
    active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    async with _admin_records_dashboard_service_scope(request) as service:
        rows = await service.list_cohorts(name=name, active=active, limit=limit, offset=offset)

    return templates.TemplateResponse(
        request,
        "cohorts/list.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "cohorts": rows,
            "filters": {
                "name": name or "",
                "active": "" if active is None else str(active).lower(),
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/cohorts/{cohort_id}", response_class=HTMLResponse)
async def admin_cohort_detail(request: Request, cohort_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_cohort_id = uuid.UUID(cohort_id)
    except ValueError:
        return HTMLResponse("Cohort not found.", status_code=404)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_records_dashboard_service_scope(request) as service:
            cohort = await service.get_cohort_detail(parsed_cohort_id)
    except AdminRecordNotFoundError:
        return HTMLResponse("Cohort not found.", status_code=404)

    return templates.TemplateResponse(
        request,
        "cohorts/detail.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "cohort": cohort,
        },
    )


@router.get("/providers", response_class=HTMLResponse)
async def list_admin_providers(
    request: Request,
    provider: str | None = Query(None),
    enabled: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    async with _admin_catalog_dashboard_service_scope(request) as service:
        rows = await service.list_providers(provider=provider, enabled=enabled, limit=limit, offset=offset)

    return templates.TemplateResponse(
        request,
        "providers/list.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "providers": rows,
            "filters": {
                "provider": provider or "",
                "enabled": "" if enabled is None else str(enabled).lower(),
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/providers/{provider_config_id}", response_class=HTMLResponse)
async def admin_provider_detail(request: Request, provider_config_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_provider_config_id = uuid.UUID(provider_config_id)
    except ValueError:
        return HTMLResponse("Provider config not found.", status_code=404)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_catalog_dashboard_service_scope(request) as service:
            provider_row = await service.get_provider_detail(parsed_provider_config_id)
    except AdminCatalogNotFoundError:
        return HTMLResponse("Provider config not found.", status_code=404)

    return templates.TemplateResponse(
        request,
        "providers/detail.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "provider": provider_row,
        },
    )


@router.get("/routes", response_class=HTMLResponse)
async def list_admin_routes(
    request: Request,
    provider: str | None = Query(None),
    requested_model: str | None = Query(None),
    match_type: str | None = Query(None),
    enabled: bool | None = Query(None),
    visible: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    async with _admin_catalog_dashboard_service_scope(request) as service:
        rows = await service.list_routes(
            provider=provider,
            requested_model=requested_model,
            match_type=match_type,
            enabled=enabled,
            visible=visible,
            limit=limit,
            offset=offset,
        )

    return templates.TemplateResponse(
        request,
        "routes/list.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "routes": rows,
            "filters": {
                "provider": provider or "",
                "requested_model": requested_model or "",
                "match_type": match_type or "",
                "enabled": "" if enabled is None else str(enabled).lower(),
                "visible": "" if visible is None else str(visible).lower(),
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/routes/{route_id}", response_class=HTMLResponse)
async def admin_route_detail(request: Request, route_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_route_id = uuid.UUID(route_id)
    except ValueError:
        return HTMLResponse("Model route not found.", status_code=404)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_catalog_dashboard_service_scope(request) as service:
            route = await service.get_route_detail(parsed_route_id)
    except AdminCatalogNotFoundError:
        return HTMLResponse("Model route not found.", status_code=404)

    return templates.TemplateResponse(
        request,
        "routes/detail.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "route": route,
        },
    )


@router.get("/pricing", response_class=HTMLResponse)
async def list_admin_pricing_rules(
    request: Request,
    provider: str | None = Query(None),
    model: str | None = Query(None),
    endpoint: str | None = Query(None),
    currency: str | None = Query(None),
    enabled: bool | None = Query(None),
    active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    async with _admin_catalog_dashboard_service_scope(request) as service:
        rows = await service.list_pricing_rules(
            provider=provider,
            model=model,
            endpoint=endpoint,
            currency=currency,
            enabled=enabled,
            active=active,
            limit=limit,
            offset=offset,
        )

    return templates.TemplateResponse(
        request,
        "pricing/list.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "pricing_rules": rows,
            "filters": {
                "provider": provider or "",
                "model": model or "",
                "endpoint": endpoint or "",
                "currency": currency or "",
                "enabled": "" if enabled is None else str(enabled).lower(),
                "active": "" if active is None else str(active).lower(),
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/pricing/{pricing_rule_id}", response_class=HTMLResponse)
async def admin_pricing_rule_detail(request: Request, pricing_rule_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_pricing_rule_id = uuid.UUID(pricing_rule_id)
    except ValueError:
        return HTMLResponse("Pricing rule not found.", status_code=404)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_catalog_dashboard_service_scope(request) as service:
            pricing_rule = await service.get_pricing_rule_detail(parsed_pricing_rule_id)
    except AdminCatalogNotFoundError:
        return HTMLResponse("Pricing rule not found.", status_code=404)

    return templates.TemplateResponse(
        request,
        "pricing/detail.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "pricing_rule": pricing_rule,
        },
    )


@router.get("/fx", response_class=HTMLResponse)
async def list_admin_fx_rates(
    request: Request,
    base_currency: str | None = Query(None),
    quote_currency: str | None = Query(None),
    source: str | None = Query(None),
    active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    async with _admin_catalog_dashboard_service_scope(request) as service:
        rows = await service.list_fx_rates(
            base_currency=base_currency,
            quote_currency=quote_currency,
            source=source,
            active=active,
            limit=limit,
            offset=offset,
        )

    return templates.TemplateResponse(
        request,
        "fx/list.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "fx_rates": rows,
            "filters": {
                "base_currency": base_currency or "",
                "quote_currency": quote_currency or "",
                "source": source or "",
                "active": "" if active is None else str(active).lower(),
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/fx/{fx_rate_id}", response_class=HTMLResponse)
async def admin_fx_rate_detail(request: Request, fx_rate_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_fx_rate_id = uuid.UUID(fx_rate_id)
    except ValueError:
        return HTMLResponse("FX rate not found.", status_code=404)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_catalog_dashboard_service_scope(request) as service:
            fx_rate = await service.get_fx_rate_detail(parsed_fx_rate_id)
    except AdminCatalogNotFoundError:
        return HTMLResponse("FX rate not found.", status_code=404)

    return templates.TemplateResponse(
        request,
        "fx/detail.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "fx_rate": fx_rate,
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


async def _admin_page_context(request: Request) -> tuple[AdminSessionContext, str] | Response:
    settings = _settings(request)
    session_token = request.cookies.get(settings.ADMIN_SESSION_COOKIE_NAME)
    if not session_token:
        return RedirectResponse("/admin/login", status_code=303)

    try:
        async with _admin_service_scope(request) as service:
            context = await service.validate_admin_session(session_token=session_token)
            csrf_token = await service.refresh_csrf_token(admin_session_id=context.admin_session.id)
            return context, csrf_token
    except (AdminSessionError, RuntimeError):
        response = RedirectResponse("/admin/login", status_code=303)
        _clear_session_cookie(response, settings)
        return response


@asynccontextmanager
async def _admin_service_scope(request: Request) -> AsyncIterator[AdminSessionService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield _build_admin_session_service(request, session)


@asynccontextmanager
async def _admin_key_dashboard_service_scope(request: Request) -> AsyncIterator[AdminKeyDashboardService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield AdminKeyDashboardService(gateway_keys_repository=GatewayKeysRepository(session))


@asynccontextmanager
async def _admin_records_dashboard_service_scope(request: Request) -> AsyncIterator[AdminRecordsDashboardService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield AdminRecordsDashboardService(
                owners_repository=OwnersRepository(session),
                institutions_repository=InstitutionsRepository(session),
                cohorts_repository=CohortsRepository(session),
            )


@asynccontextmanager
async def _admin_catalog_dashboard_service_scope(request: Request) -> AsyncIterator[AdminCatalogDashboardService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield AdminCatalogDashboardService(
                provider_configs_repository=ProviderConfigsRepository(session),
                model_routes_repository=ModelRoutesRepository(session),
                pricing_rules_repository=PricingRulesRepository(session),
                fx_rates_repository=FxRatesRepository(session),
            )


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


def _parse_optional_uuid(value: str | None) -> uuid.UUID | None | bool:
    if value is None or not value.strip():
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return False


def _admin_not_found() -> HTMLResponse:
    return HTMLResponse("Not found.", status_code=404)


def _admin_unavailable() -> HTMLResponse:
    return HTMLResponse("Admin login is not available.", status_code=503)

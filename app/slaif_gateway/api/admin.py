"""Server-rendered admin authentication routes."""

from __future__ import annotations

import ipaddress
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.auth.csrf import CsrfError, create_login_csrf_token, verify_login_csrf_token
from slaif_gateway.config import Settings
from slaif_gateway.db.repositories.admin_sessions import AdminSessionsRepository
from slaif_gateway.db.repositories.admin_users import AdminUsersRepository
from slaif_gateway.db.repositories.audit import AuditRepository
from slaif_gateway.db.repositories.cohorts import CohortsRepository
from slaif_gateway.db.repositories.email import EmailDeliveriesRepository
from slaif_gateway.db.repositories.fx_rates import FxRatesRepository
from slaif_gateway.db.repositories.institutions import InstitutionsRepository
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.repositories.one_time_secrets import OneTimeSecretsRepository
from slaif_gateway.db.repositories.owners import OwnersRepository
from slaif_gateway.db.repositories.pricing import PricingRulesRepository
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository
from slaif_gateway.db.repositories.routing import ModelRoutesRepository
from slaif_gateway.db.repositories.usage import UsageLedgerRepository
from slaif_gateway.db.session import get_sessionmaker_from_app
from slaif_gateway.services.admin_activity_dashboard import AdminActivityDashboardService, AdminActivityNotFoundError
from slaif_gateway.services.admin_catalog_dashboard import AdminCatalogDashboardService, AdminCatalogNotFoundError
from slaif_gateway.services.admin_export_service import AdminCsvExportResult, AdminCsvExportService
from slaif_gateway.services.admin_key_dashboard import AdminKeyDashboardService, AdminKeyNotFoundError
from slaif_gateway.services.admin_records_dashboard import AdminRecordNotFoundError, AdminRecordsDashboardService
from slaif_gateway.services.admin_record_forms import (
    parse_cohort_form,
    parse_institution_form,
    parse_owner_form,
)
from slaif_gateway.services.admin_session_service import (
    AdminAuthenticationError,
    AdminLoginRateLimitedError,
    AdminSessionContext,
    AdminSessionError,
    AdminSessionService,
)
from slaif_gateway.services.email_delivery_service import EmailDeliveryService, PendingKeyEmailResult
from slaif_gateway.services.email_errors import EmailError
from slaif_gateway.services.email_service import EmailService
from slaif_gateway.services.fx_rate_service import FxRateService
from slaif_gateway.services.fx_import import (
    FxImportExecutionPlan,
    FxImportExecutionResult,
    FxImportPreview,
    build_fx_import_execution_plan,
    classify_fx_import_preview,
    detect_fx_import_format,
    execute_fx_import_plan,
    parse_fx_import_csv,
    parse_fx_import_json,
    validate_fx_import_rows,
)
from slaif_gateway.services.key_errors import KeyManagementError
from slaif_gateway.services.key_import import (
    KeyImportExecutionResult,
    KeyImportCohortRef,
    KeyImportOwnerRef,
    KeyImportPreview,
    KeyImportReadOnlyContext,
    build_key_import_execution_plan,
    detect_key_import_format,
    execute_key_import_plan,
    key_import_execution_error_result,
    key_import_execution_result_from_preview_errors,
    parse_key_import_csv,
    parse_key_import_json,
    validate_key_import_rows,
)
from slaif_gateway.services.key_service import KeyService
from slaif_gateway.services.model_route_service import CHAT_COMPLETIONS_ENDPOINT, ModelRouteService
from slaif_gateway.services.cohort_service import CohortService
from slaif_gateway.services.institution_service import InstitutionService
from slaif_gateway.services.owner_service import OwnerService
from slaif_gateway.services.pricing_import import (
    PricingImportExecutionPlan,
    PricingImportExecutionResult,
    PricingImportPreview,
    build_pricing_import_execution_plan,
    classify_pricing_import_preview,
    detect_pricing_import_format,
    execute_pricing_import_plan,
    parse_pricing_import_csv,
    parse_pricing_import_json,
    validate_pricing_import_rows,
)
from slaif_gateway.services.pricing_rule_service import PricingRuleService
from slaif_gateway.services.provider_config_service import ProviderConfigService
from slaif_gateway.services.record_errors import DuplicateRecordError, RecordNotFoundError, UnsupportedRecordOperationError
from slaif_gateway.services.route_import import (
    RouteImportExecutionPlan,
    RouteImportExecutionResult,
    RouteImportPreview,
    build_route_import_execution_plan,
    classify_route_import_preview,
    detect_route_import_format,
    execute_route_import_plan,
    parse_route_import_csv,
    parse_route_import_json,
    provider_refs_from_rows,
    validate_route_import_rows,
)
from slaif_gateway.schemas.keys import (
    ActivateGatewayKeyInput,
    CreateGatewayKeyInput,
    CreatedGatewayKey,
    RevokeGatewayKeyInput,
    ResetGatewayKeyUsageInput,
    RotatedGatewayKeyResult,
    RotateGatewayKeyInput,
    SuspendGatewayKeyInput,
    UpdateGatewayKeyLimitsInput,
    UpdateGatewayKeyValidityInput,
)
from slaif_gateway.utils.redaction import redact_text
from slaif_gateway.workers.tasks_email import send_pending_key_email_task

router = APIRouter(prefix="/admin", include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "web" / "templates"))

_ADMIN_STATUS_MESSAGES: dict[str, tuple[str, str]] = {
    "key_created": ("success", "Gateway key created."),
    "key_suspended": ("success", "Gateway key suspended."),
    "key_activated": ("success", "Gateway key activated."),
    "key_revoked": ("success", "Gateway key revoked permanently."),
    "key_validity_updated": ("success", "Gateway key validity updated."),
    "key_limits_updated": ("success", "Gateway key hard quota limits updated."),
    "key_usage_reset": ("success", "Gateway key usage counters reset."),
    "rotation_confirmation_required": ("error", "Confirm key rotation before continuing."),
    "rotation_reason_required": ("error", "Enter an audit reason before rotating this key."),
    "revoke_confirmation_required": ("error", "Confirm permanent revocation before continuing."),
    "revoke_reason_required": ("error", "Enter an audit reason before revoking this key."),
    "validity_reason_required": ("error", "Enter an audit reason before updating validity."),
    "limits_reason_required": ("error", "Enter an audit reason before updating hard quota limits."),
    "usage_reset_confirmation_required": ("error", "Confirm usage-counter reset before continuing."),
    "usage_reset_reason_required": ("error", "Enter an audit reason before resetting usage counters."),
    "reserved_reset_confirmation_required": (
        "error",
        "Confirm reserved-counter repair reset before continuing.",
    ),
    "invalid_gateway_key_validity": ("error", "Enter a valid key validity window."),
    "invalid_gateway_key_limits": ("error", "Enter valid positive hard quota limits."),
    "gateway_key_no_validity_change": ("error", "Change at least one validity field before submitting."),
    "gateway_key_no_limit_change": ("error", "Change or clear at least one hard quota limit before submitting."),
    "gateway_key_already_active": ("error", "Gateway key is already active."),
    "gateway_key_already_revoked": ("error", "Gateway key is already revoked."),
    "gateway_key_rotation_failed": ("error", "Gateway key rotation failed."),
    "gateway_key_create_failed": ("error", "Gateway key creation failed."),
    "invalid_email_delivery_mode": ("error", "Select a valid key email delivery mode."),
    "email_delivery_sent": ("success", "Key email delivery sent."),
    "email_delivery_queued": ("success", "Key email delivery queued."),
    "email_delivery_send_failed": ("error", "Key email delivery failed safely."),
    "email_delivery_ambiguous": (
        "error",
        "Email delivery is ambiguous after possible SMTP acceptance. Do not retry; rotate the key if receipt cannot be confirmed.",
    ),
    "email_delivery_not_sendable": (
        "error",
        "This email delivery cannot be sent. Rotate the key and create a new delivery if the secret is unavailable.",
    ),
    "email_delivery_send_confirmation_required": ("error", "Confirm email delivery before sending."),
    "email_delivery_enqueue_confirmation_required": ("error", "Confirm queued email delivery before continuing."),
    "email_delivery_configuration_required": ("error", "Email delivery configuration is incomplete."),
    "provider_config_created": ("success", "Provider config created."),
    "provider_config_updated": ("success", "Provider config updated."),
    "provider_config_enabled": ("success", "Provider config enabled."),
    "provider_config_disabled": ("success", "Provider config disabled."),
    "provider_config_failed": ("error", "Provider config action failed."),
    "provider_config_disable_confirmation_required": (
        "error",
        "Confirm provider config disable before continuing.",
    ),
    "provider_config_reason_required": (
        "error",
        "Enter an audit reason before changing provider config metadata.",
    ),
    "invalid_provider_config": ("error", "Enter valid provider config metadata."),
    "model_route_created": ("success", "Model route created."),
    "model_route_updated": ("success", "Model route updated."),
    "model_route_enabled": ("success", "Model route enabled."),
    "model_route_disabled": ("success", "Model route disabled."),
    "model_route_failed": ("error", "Model route action failed."),
    "model_route_disable_confirmation_required": (
        "error",
        "Confirm model route disable before continuing.",
    ),
    "model_route_reason_required": (
        "error",
        "Enter an audit reason before changing model route metadata.",
    ),
    "invalid_model_route": ("error", "Enter valid model route metadata."),
    "pricing_rule_created": ("success", "Pricing rule created."),
    "pricing_rule_updated": ("success", "Pricing rule updated."),
    "pricing_rule_enabled": ("success", "Pricing rule enabled."),
    "pricing_rule_disabled": ("success", "Pricing rule disabled."),
    "pricing_rule_failed": ("error", "Pricing rule action failed."),
    "pricing_rule_disable_confirmation_required": (
        "error",
        "Confirm pricing rule disable before continuing.",
    ),
    "pricing_rule_reason_required": (
        "error",
        "Enter an audit reason before changing pricing metadata.",
    ),
    "invalid_pricing_rule": ("error", "Enter valid pricing metadata."),
    "fx_rate_created": ("success", "FX rate created."),
    "fx_rate_updated": ("success", "FX rate updated."),
    "fx_rate_failed": ("error", "FX rate action failed."),
    "fx_rate_reason_required": ("error", "Enter an audit reason before changing FX metadata."),
    "invalid_fx_rate": ("error", "Enter valid FX metadata."),
    "institution_created": ("success", "Institution created."),
    "institution_updated": ("success", "Institution updated."),
    "cohort_created": ("success", "Cohort created."),
    "cohort_updated": ("success", "Cohort updated."),
    "owner_created": ("success", "Owner created."),
    "owner_updated": ("success", "Owner updated."),
    "invalid_admin_record": ("error", "Enter valid record metadata."),
    "gateway_key_already_suspended": ("error", "Gateway key is already suspended."),
    "invalid_gateway_key_status_transition": ("error", "That key status transition is not allowed."),
    "key_action_failed": ("error", "Gateway key action failed."),
}

_ADMIN_EMAIL_DELIVERY_MODES = {"none", "pending", "send-now", "enqueue"}


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

    login_failure: tuple[str, int] | None = None
    try:
        async with _admin_service_scope(request) as service:
            try:
                admin_user = await service.authenticate_admin(
                    email=email,
                    password=password,
                    ip_address=_client_host(request),
                    user_agent=request.headers.get("user-agent"),
                )
            except AdminLoginRateLimitedError:
                login_failure = ("Too many failed login attempts. Try again later.", 429)
            except AdminAuthenticationError:
                login_failure = ("Invalid email or password.", 401)
                admin_user = None
            if login_failure is not None:
                created_session = None
            else:
                assert admin_user is not None
                created_session = await service.create_admin_session(
                    admin_user_id=admin_user.id,
                    ip_address=_client_host(request),
                    user_agent=request.headers.get("user-agent"),
                )
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

    if login_failure is not None:
        try:
            replacement = create_login_csrf_token(settings)
        except CsrfError:
            return _admin_unavailable()
        message, status_code = login_failure
        response = _render_login(
            request,
            csrf_token=replacement,
            error=message,
            status_code=status_code,
        )
        _set_login_csrf_cookie(response, settings, replacement)
        return response

    assert created_session is not None

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
            "admin_status_message": _admin_status_message(request),
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


@router.get("/keys/create", response_class=HTMLResponse)
async def create_admin_key_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    options = await _load_key_create_form_options(request)
    return _render_key_create_form(
        request,
        admin=context.admin_user,
        csrf_token=csrf_token,
        options=options,
        form=_default_key_create_form(),
    )


@router.post("/keys/create", response_class=HTMLResponse)
async def create_admin_key(
    request: Request,
    csrf_token: str = Form(""),
    owner_id: str = Form(""),
    cohort_id: str = Form(""),
    valid_from: str = Form(""),
    valid_until: str = Form(""),
    valid_days: str = Form(""),
    cost_limit_eur: str = Form(""),
    token_limit_total: str = Form(""),
    request_limit_total: str = Form(""),
    allowed_models: str = Form(""),
    allowed_endpoints: str = Form(""),
    rate_limit_requests_per_minute: str = Form(""),
    rate_limit_tokens_per_minute: str = Form(""),
    rate_limit_concurrent_requests: str = Form(""),
    rate_limit_window_seconds: str = Form(""),
    email_delivery_mode: str = Form("none"),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = {
        "owner_id": owner_id,
        "cohort_id": cohort_id,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "valid_days": valid_days,
        "cost_limit_eur": cost_limit_eur,
        "token_limit_total": token_limit_total,
        "request_limit_total": request_limit_total,
        "allowed_models": allowed_models,
        "allowed_endpoints": allowed_endpoints,
        "rate_limit_requests_per_minute": rate_limit_requests_per_minute,
        "rate_limit_tokens_per_minute": rate_limit_tokens_per_minute,
        "rate_limit_concurrent_requests": rate_limit_concurrent_requests,
        "rate_limit_window_seconds": rate_limit_window_seconds,
        "email_delivery_mode": email_delivery_mode,
        "reason": reason,
    }
    options = await _load_key_create_form_options(request)

    try:
        parsed_input = _parse_key_create_form(
            form,
            actor_admin_id=action_context.admin_user.id,
        )
        parsed_email_delivery_mode = _parse_admin_email_delivery_mode(email_delivery_mode)
        _validate_admin_email_delivery_preconditions(settings, parsed_email_delivery_mode)
    except ValueError as exc:
        return _render_key_create_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            options=options,
            form=form,
            error=str(exc),
            status_code=400,
        )

    try:
        delivery_result: PendingKeyEmailResult | None = None
        async with _admin_key_email_delivery_runtime_scope(request) as (
            owners_repository,
            cohorts_repository,
            service,
            email_delivery_service,
        ):
            owner = await owners_repository.get_owner_by_id(parsed_input.owner_id)
            if owner is None:
                return _render_key_create_form(
                    request,
                    admin=action_context.admin_user,
                    csrf_token=csrf_token,
                    options=options,
                    form=form,
                    error="Select an existing owner before creating a key.",
                    status_code=400,
                )
            cohort = None
            if parsed_input.cohort_id is not None:
                cohort = await cohorts_repository.get_cohort_by_id(parsed_input.cohort_id)
                if cohort is None:
                    return _render_key_create_form(
                        request,
                        admin=action_context.admin_user,
                        csrf_token=csrf_token,
                        options=options,
                        form=form,
                        error="Select an existing cohort or leave cohort blank.",
                        status_code=400,
                    )
            created = await service.create_gateway_key(parsed_input)
            delivery_result = await _handle_admin_key_email_delivery_in_transaction(
                email_delivery_service,
                mode=parsed_email_delivery_mode,
                gateway_key_id=created.gateway_key_id,
                one_time_secret_id=created.one_time_secret_id,
                owner_id=created.owner_id,
                actor_admin_id=action_context.admin_user.id,
                reason=parsed_input.note,
            )
    except (EmailError, KeyManagementError, ValueError):
        return _render_key_create_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            options=options,
            form=form,
            error=_ADMIN_STATUS_MESSAGES["gateway_key_create_failed"][1],
            status_code=400,
        )

    if parsed_email_delivery_mode == "send-now" and delivery_result is not None:
        try:
            async with _admin_email_delivery_action_scope(request) as email_delivery_service:
                delivery_result = await email_delivery_service.send_pending_key_email(
                    one_time_secret_id=delivery_result.one_time_secret_id,
                    email_delivery_id=delivery_result.email_delivery_id,
                    actor_admin_id=action_context.admin_user.id,
                    reason=parsed_input.note,
                )
        except EmailError:
            delivery_result = PendingKeyEmailResult(
                email_delivery_id=delivery_result.email_delivery_id,
                one_time_secret_id=delivery_result.one_time_secret_id,
                gateway_key_id=delivery_result.gateway_key_id,
                owner_id=delivery_result.owner_id,
                recipient_email=delivery_result.recipient_email,
                status="failed",
                error_code="email_delivery_failed",
            )

    celery_task_id: str | None = None
    if parsed_email_delivery_mode == "enqueue" and delivery_result is not None:
        try:
            celery_task_id = _enqueue_admin_pending_key_email(
                one_time_secret_id=delivery_result.one_time_secret_id,
                email_delivery_id=delivery_result.email_delivery_id,
                actor_admin_id=action_context.admin_user.id,
            )
            delivery_result = PendingKeyEmailResult(
                email_delivery_id=delivery_result.email_delivery_id,
                one_time_secret_id=delivery_result.one_time_secret_id,
                gateway_key_id=delivery_result.gateway_key_id,
                owner_id=delivery_result.owner_id,
                recipient_email=delivery_result.recipient_email,
                status="queued",
            )
        except Exception:  # noqa: BLE001
            delivery_result = PendingKeyEmailResult(
                email_delivery_id=delivery_result.email_delivery_id,
                one_time_secret_id=delivery_result.one_time_secret_id,
                gateway_key_id=delivery_result.gateway_key_id,
                owner_id=delivery_result.owner_id,
                recipient_email=delivery_result.recipient_email,
                status="failed",
                error_code="celery_enqueue_failed",
                error_message="Email delivery could not be queued.",
            )

    if parsed_email_delivery_mode in {"send-now", "enqueue"}:
        response = templates.TemplateResponse(
            request,
            "keys/email_delivery_result.html",
            {
                "admin": action_context.admin_user,
                "workflow": "created",
                "email_delivery_mode": parsed_email_delivery_mode,
                "key_result": _safe_created_key_result(created),
                "delivery": delivery_result,
                "celery_task_id": celery_task_id,
            },
        )
        _set_no_store_headers(response)
        return response

    response = templates.TemplateResponse(
        request,
        "keys/create_result.html",
        {
            "admin": action_context.admin_user,
            "created": created,
            "owner": owner,
            "cohort": cohort,
            "limits": {
                "cost_limit_eur": parsed_input.cost_limit_eur,
                "token_limit_total": parsed_input.token_limit_total,
                "request_limit_total": parsed_input.request_limit_total,
            },
            "policy": {
                "allowed_models": parsed_input.allowed_models,
                "allowed_endpoints": parsed_input.allowed_endpoints,
                "rate_limit_policy": parsed_input.rate_limit_policy,
            },
            "email_delivery_mode": parsed_email_delivery_mode,
            "delivery": delivery_result,
            "celery_task_id": celery_task_id,
        },
    )
    _set_no_store_headers(response)
    return response


@router.get("/keys/bulk-import", response_class=HTMLResponse)
async def bulk_import_admin_keys_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return _render_key_import_form(
        request,
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_default_key_import_form(),
    )


@router.post("/keys/bulk-import/preview", response_class=HTMLResponse)
async def preview_bulk_import_admin_keys(
    request: Request,
    csrf_token: str = Form(""),
    import_format: str = Form("auto"),
    import_file: UploadFile | None = File(None),
    import_text: str = Form(""),
    source_label: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    try:
        _parse_optional_import_source_label(source_label)
        filename, text = await _read_key_import_input(
            import_file=import_file,
            import_text=import_text,
            max_bytes=settings.KEY_IMPORT_MAX_BYTES,
        )
        detected_format = detect_key_import_format(
            filename=filename,
            requested_format=import_format,
            text=text,
        )
        raw_rows = parse_key_import_json(text) if detected_format == "json" else parse_key_import_csv(text)
        preview = await _build_key_import_preview(
            request,
            raw_rows,
            max_rows=settings.KEY_IMPORT_MAX_ROWS,
        )
    except ValueError as exc:
        return _render_key_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": "",
                "source_label": source_label,
            },
            error=str(exc),
            status_code=400,
        )

    response = templates.TemplateResponse(
        request,
        "keys/bulk_import_preview.html",
        {
            "admin": action_context.admin_user,
            "csrf_token": csrf_token,
            "preview": preview,
            "import_format": detected_format,
            "source_label": source_label.strip(),
        },
    )
    _set_no_store_headers(response)
    return response


@router.post("/keys/bulk-import/execute", response_class=HTMLResponse)
async def execute_bulk_import_admin_keys(
    request: Request,
    csrf_token: str = Form(""),
    import_format: str = Form("auto"),
    import_file: UploadFile | None = File(None),
    import_text: str = Form(""),
    source_label: str = Form(""),
    confirm_import: str = Form(""),
    confirm_plaintext_display: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    detected_format = import_format
    try:
        _parse_optional_import_source_label(source_label)
        filename, text = await _read_key_import_input(
            import_file=import_file,
            import_text=import_text,
            max_bytes=settings.KEY_IMPORT_MAX_BYTES,
        )
        detected_format = detect_key_import_format(
            filename=filename,
            requested_format=import_format,
            text=text,
        )
        raw_rows = parse_key_import_json(text) if detected_format == "json" else parse_key_import_csv(text)
        preview = await _build_key_import_preview(
            request,
            raw_rows,
            max_rows=settings.KEY_IMPORT_MAX_ROWS,
        )
        if preview.invalid_count:
            return _render_key_import_result(
                request,
                admin=action_context.admin_user,
                csrf_token=csrf_token,
                result=key_import_execution_result_from_preview_errors(preview),
                import_format=detected_format,
                source_label=source_label.strip(),
                error="All rows must validate before bulk key import execution.",
                status_code=400,
            )
        plan = build_key_import_execution_plan(
            preview,
            actor_admin_id=action_context.admin_user.id,
            reason=reason,
            confirm_import=_is_checked(confirm_import),
            confirm_plaintext_display=_is_checked(confirm_plaintext_display),
        )
    except ValueError as exc:
        return _render_key_import_result(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            result=key_import_execution_error_result(str(exc)),
            import_format=detected_format,
            source_label=source_label.strip(),
            error=str(exc),
            status_code=400,
        )

    try:
        async with _admin_key_email_delivery_runtime_scope(request) as (
            _owners_repository,
            _cohorts_repository,
            key_service,
            email_delivery_service,
        ):
            result = await execute_key_import_plan(
                plan,
                key_service=key_service,
                email_delivery_service=email_delivery_service,
            )
    except (EmailError, KeyManagementError, ValueError):
        return _render_key_import_result(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            result=key_import_execution_error_result(
                "Bulk key import execution failed safely. No keys were created."
            ),
            import_format=detected_format,
            source_label=source_label.strip(),
            error="Bulk key import execution failed safely. No keys were created.",
            status_code=400,
        )

    return _render_key_import_result(
        request,
        admin=action_context.admin_user,
        csrf_token=csrf_token,
        result=result,
        import_format=detected_format,
        source_label=source_label.strip(),
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
            "admin_status_message": _admin_status_message(request),
            "key": key,
        },
    )


@router.post("/keys/{gateway_key_id}/suspend", response_class=HTMLResponse)
async def suspend_admin_key(
    request: Request,
    gateway_key_id: str,
    csrf_token: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    parsed_key_id = _parse_gateway_key_id(gateway_key_id)
    if parsed_key_id is None:
        return HTMLResponse("Gateway key not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    try:
        async with _admin_key_management_service_scope(request) as service:
            await service.suspend_gateway_key(
                SuspendGatewayKeyInput(
                    gateway_key_id=parsed_key_id,
                    actor_admin_id=action_context.admin_user.id,
                    reason=_clean_admin_reason(reason),
                )
            )
    except KeyManagementError as exc:
        return _key_management_error_response(exc, gateway_key_id=parsed_key_id)

    return _redirect_to_admin_key(parsed_key_id, message="key_suspended")


@router.post("/keys/{gateway_key_id}/activate", response_class=HTMLResponse)
async def activate_admin_key(
    request: Request,
    gateway_key_id: str,
    csrf_token: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    parsed_key_id = _parse_gateway_key_id(gateway_key_id)
    if parsed_key_id is None:
        return HTMLResponse("Gateway key not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    try:
        async with _admin_key_management_service_scope(request) as service:
            await service.activate_gateway_key(
                ActivateGatewayKeyInput(
                    gateway_key_id=parsed_key_id,
                    actor_admin_id=action_context.admin_user.id,
                    reason=_clean_admin_reason(reason),
                )
            )
    except KeyManagementError as exc:
        return _key_management_error_response(exc, gateway_key_id=parsed_key_id)

    return _redirect_to_admin_key(parsed_key_id, message="key_activated")


@router.post("/keys/{gateway_key_id}/revoke", response_class=HTMLResponse)
async def revoke_admin_key(
    request: Request,
    gateway_key_id: str,
    csrf_token: str = Form(""),
    reason: str = Form(""),
    confirm_revoke: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    parsed_key_id = _parse_gateway_key_id(gateway_key_id)
    if parsed_key_id is None:
        return HTMLResponse("Gateway key not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    if confirm_revoke != "true":
        return _redirect_to_admin_key(parsed_key_id, message="revoke_confirmation_required")

    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _redirect_to_admin_key(parsed_key_id, message="revoke_reason_required")

    try:
        async with _admin_key_management_service_scope(request) as service:
            await service.revoke_gateway_key(
                RevokeGatewayKeyInput(
                    gateway_key_id=parsed_key_id,
                    actor_admin_id=action_context.admin_user.id,
                    reason=cleaned_reason,
                )
            )
    except KeyManagementError as exc:
        return _key_management_error_response(exc, gateway_key_id=parsed_key_id)

    return _redirect_to_admin_key(parsed_key_id, message="key_revoked")


@router.post("/keys/{gateway_key_id}/validity", response_class=HTMLResponse)
async def update_admin_key_validity(
    request: Request,
    gateway_key_id: str,
    csrf_token: str = Form(""),
    valid_from: str = Form(""),
    valid_until: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    parsed_key_id = _parse_gateway_key_id(gateway_key_id)
    if parsed_key_id is None:
        return HTMLResponse("Gateway key not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _redirect_to_admin_key(parsed_key_id, message="validity_reason_required")

    try:
        parsed_valid_from = _parse_admin_datetime(valid_from)
        parsed_valid_until = _parse_admin_datetime(valid_until)
    except ValueError:
        return _redirect_to_admin_key(parsed_key_id, message="invalid_gateway_key_validity")

    if parsed_valid_from is None and parsed_valid_until is None:
        return _redirect_to_admin_key(parsed_key_id, message="gateway_key_no_validity_change")

    try:
        async with _admin_key_management_runtime_scope(request) as (keys_repository, service):
            gateway_key = await keys_repository.get_gateway_key_by_id(parsed_key_id)
            if gateway_key is None:
                return HTMLResponse("Gateway key not found.", status_code=404)
            await service.update_gateway_key_validity(
                UpdateGatewayKeyValidityInput(
                    gateway_key_id=parsed_key_id,
                    valid_from=parsed_valid_from,
                    valid_until=parsed_valid_until or gateway_key.valid_until,
                    actor_admin_id=action_context.admin_user.id,
                    reason=cleaned_reason,
                )
            )
    except KeyManagementError as exc:
        return _key_management_error_response(exc, gateway_key_id=parsed_key_id)

    return _redirect_to_admin_key(parsed_key_id, message="key_validity_updated")


@router.post("/keys/{gateway_key_id}/limits", response_class=HTMLResponse)
async def update_admin_key_limits(
    request: Request,
    gateway_key_id: str,
    csrf_token: str = Form(""),
    cost_limit_eur: str = Form(""),
    token_limit: str = Form(""),
    request_limit: str = Form(""),
    clear_cost_limit: str = Form(""),
    clear_token_limit: str = Form(""),
    clear_request_limit: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    parsed_key_id = _parse_gateway_key_id(gateway_key_id)
    if parsed_key_id is None:
        return HTMLResponse("Gateway key not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _redirect_to_admin_key(parsed_key_id, message="limits_reason_required")

    clear_cost = _is_checked(clear_cost_limit)
    clear_tokens = _is_checked(clear_token_limit)
    clear_requests = _is_checked(clear_request_limit)
    try:
        cost_provided, parsed_cost_limit = _parse_optional_admin_decimal(cost_limit_eur)
        token_provided, parsed_token_limit = _parse_optional_admin_int(token_limit)
        request_provided, parsed_request_limit = _parse_optional_admin_int(request_limit)
    except ValueError:
        return _redirect_to_admin_key(parsed_key_id, message="invalid_gateway_key_limits")

    if (clear_cost and cost_provided) or (clear_tokens and token_provided) or (clear_requests and request_provided):
        return _redirect_to_admin_key(parsed_key_id, message="invalid_gateway_key_limits")

    if not any((cost_provided, token_provided, request_provided, clear_cost, clear_tokens, clear_requests)):
        return _redirect_to_admin_key(parsed_key_id, message="gateway_key_no_limit_change")

    try:
        async with _admin_key_management_runtime_scope(request) as (keys_repository, service):
            gateway_key = await keys_repository.get_gateway_key_by_id(parsed_key_id)
            if gateway_key is None:
                return HTMLResponse("Gateway key not found.", status_code=404)
            await service.update_gateway_key_limits(
                UpdateGatewayKeyLimitsInput(
                    gateway_key_id=parsed_key_id,
                    cost_limit_eur=(
                        None
                        if clear_cost
                        else parsed_cost_limit
                        if cost_provided
                        else gateway_key.cost_limit_eur
                    ),
                    token_limit_total=(
                        None
                        if clear_tokens
                        else parsed_token_limit
                        if token_provided
                        else gateway_key.token_limit_total
                    ),
                    request_limit_total=(
                        None
                        if clear_requests
                        else parsed_request_limit
                        if request_provided
                        else gateway_key.request_limit_total
                    ),
                    actor_admin_id=action_context.admin_user.id,
                    reason=cleaned_reason,
                )
            )
    except KeyManagementError as exc:
        return _key_management_error_response(exc, gateway_key_id=parsed_key_id)

    return _redirect_to_admin_key(parsed_key_id, message="key_limits_updated")


@router.post("/keys/{gateway_key_id}/reset-usage", response_class=HTMLResponse)
async def reset_admin_key_usage(
    request: Request,
    gateway_key_id: str,
    csrf_token: str = Form(""),
    confirm_reset_usage: str = Form(""),
    reset_reserved: str = Form(""),
    confirm_reset_reserved: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    parsed_key_id = _parse_gateway_key_id(gateway_key_id)
    if parsed_key_id is None:
        return HTMLResponse("Gateway key not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    if not _is_checked(confirm_reset_usage):
        return _redirect_to_admin_key(parsed_key_id, message="usage_reset_confirmation_required")

    reset_reserved_counters = _is_checked(reset_reserved)
    if reset_reserved_counters and not _is_checked(confirm_reset_reserved):
        return _redirect_to_admin_key(parsed_key_id, message="reserved_reset_confirmation_required")

    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _redirect_to_admin_key(parsed_key_id, message="usage_reset_reason_required")

    try:
        async with _admin_key_management_service_scope(request) as service:
            await service.reset_gateway_key_usage(
                ResetGatewayKeyUsageInput(
                    gateway_key_id=parsed_key_id,
                    reset_used_counters=True,
                    reset_reserved_counters=reset_reserved_counters,
                    actor_admin_id=action_context.admin_user.id,
                    reason=cleaned_reason,
                )
            )
    except KeyManagementError as exc:
        return _key_management_error_response(exc, gateway_key_id=parsed_key_id)

    return _redirect_to_admin_key(parsed_key_id, message="key_usage_reset")


@router.post("/keys/{gateway_key_id}/rotate", response_class=HTMLResponse)
async def rotate_admin_key(
    request: Request,
    gateway_key_id: str,
    csrf_token: str = Form(""),
    confirm_rotate: str = Form(""),
    reason: str = Form(""),
    keep_old_active: str = Form(""),
    email_delivery_mode: str = Form("none"),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    parsed_key_id = _parse_gateway_key_id(gateway_key_id)
    if parsed_key_id is None:
        return HTMLResponse("Gateway key not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    if not _is_checked(confirm_rotate):
        return _redirect_to_admin_key(parsed_key_id, message="rotation_confirmation_required")

    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _redirect_to_admin_key(parsed_key_id, message="rotation_reason_required")

    try:
        parsed_email_delivery_mode = _parse_admin_email_delivery_mode(email_delivery_mode)
        _validate_admin_email_delivery_preconditions(settings, parsed_email_delivery_mode)
    except ValueError:
        return _redirect_to_admin_key(parsed_key_id, message="invalid_email_delivery_mode")

    revoke_old_key = not _is_checked(keep_old_active)
    try:
        delivery_result: PendingKeyEmailResult | None = None
        async with _admin_key_email_delivery_runtime_scope(request) as (
            _owners_repository,
            _cohorts_repository,
            service,
            email_delivery_service,
        ):
            rotation = await service.rotate_gateway_key(
                RotateGatewayKeyInput(
                    gateway_key_id=parsed_key_id,
                    actor_admin_id=action_context.admin_user.id,
                    reason=cleaned_reason,
                    revoke_old_key=revoke_old_key,
                )
            )
            if rotation.owner_id is None:
                raise ValueError("Rotated key result did not include owner metadata for email delivery")
            delivery_result = await _handle_admin_key_email_delivery_in_transaction(
                email_delivery_service,
                mode=parsed_email_delivery_mode,
                gateway_key_id=rotation.new_gateway_key_id,
                one_time_secret_id=rotation.one_time_secret_id,
                owner_id=rotation.owner_id,
                actor_admin_id=action_context.admin_user.id,
                reason=cleaned_reason,
            )
    except KeyManagementError as exc:
        return _key_management_error_response(exc, gateway_key_id=parsed_key_id)
    except (EmailError, ValueError):
        return _redirect_to_admin_key(parsed_key_id, message="gateway_key_rotation_failed")

    if parsed_email_delivery_mode == "send-now" and delivery_result is not None:
        try:
            async with _admin_email_delivery_action_scope(request) as email_delivery_service:
                delivery_result = await email_delivery_service.send_pending_key_email(
                    one_time_secret_id=delivery_result.one_time_secret_id,
                    email_delivery_id=delivery_result.email_delivery_id,
                    actor_admin_id=action_context.admin_user.id,
                    reason=cleaned_reason,
                )
        except EmailError:
            delivery_result = PendingKeyEmailResult(
                email_delivery_id=delivery_result.email_delivery_id,
                one_time_secret_id=delivery_result.one_time_secret_id,
                gateway_key_id=delivery_result.gateway_key_id,
                owner_id=delivery_result.owner_id,
                recipient_email=delivery_result.recipient_email,
                status="failed",
                error_code="email_delivery_failed",
            )

    celery_task_id: str | None = None
    if parsed_email_delivery_mode == "enqueue" and delivery_result is not None:
        try:
            celery_task_id = _enqueue_admin_pending_key_email(
                one_time_secret_id=delivery_result.one_time_secret_id,
                email_delivery_id=delivery_result.email_delivery_id,
                actor_admin_id=action_context.admin_user.id,
            )
            delivery_result = PendingKeyEmailResult(
                email_delivery_id=delivery_result.email_delivery_id,
                one_time_secret_id=delivery_result.one_time_secret_id,
                gateway_key_id=delivery_result.gateway_key_id,
                owner_id=delivery_result.owner_id,
                recipient_email=delivery_result.recipient_email,
                status="queued",
            )
        except Exception:  # noqa: BLE001
            delivery_result = PendingKeyEmailResult(
                email_delivery_id=delivery_result.email_delivery_id,
                one_time_secret_id=delivery_result.one_time_secret_id,
                gateway_key_id=delivery_result.gateway_key_id,
                owner_id=delivery_result.owner_id,
                recipient_email=delivery_result.recipient_email,
                status="failed",
                error_code="celery_enqueue_failed",
                error_message="Email delivery could not be queued.",
            )

    if parsed_email_delivery_mode in {"send-now", "enqueue"}:
        response = templates.TemplateResponse(
            request,
            "keys/email_delivery_result.html",
            {
                "admin": action_context.admin_user,
                "workflow": "rotated",
                "email_delivery_mode": parsed_email_delivery_mode,
                "key_result": _safe_rotated_key_result(rotation),
                "delivery": delivery_result,
                "celery_task_id": celery_task_id,
                "old_key_revoked": revoke_old_key,
            },
        )
        _set_no_store_headers(response)
        return response

    response = templates.TemplateResponse(
        request,
        "keys/rotate_result.html",
        {
            "admin": action_context.admin_user,
            "rotation": rotation,
            "old_key_revoked": revoke_old_key,
            "email_delivery_mode": parsed_email_delivery_mode,
            "delivery": delivery_result,
            "celery_task_id": celery_task_id,
        },
    )
    _set_no_store_headers(response)
    return response


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
            "admin_status_message": _admin_status_message(request),
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


@router.get("/owners/new", response_class=HTMLResponse)
async def new_admin_owner_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    institutions = await _load_record_form_institutions(request)
    return _render_owner_form(
        request,
        template_name="owners/create.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_default_owner_form(),
        institutions=institutions,
    )


@router.post("/owners/new", response_class=HTMLResponse)
async def create_admin_owner(
    request: Request,
    csrf_token: str = Form(""),
    name: str = Form(""),
    surname: str = Form(""),
    email: str = Form(""),
    institution_id: str = Form(""),
    external_id: str = Form(""),
    notes: str = Form(""),
    is_active: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = _owner_form_from_values(
        name=name,
        surname=surname,
        email=email,
        institution_id=institution_id,
        external_id=external_id,
        notes=notes,
        is_active=is_active,
        reason=reason,
    )
    try:
        parsed = parse_owner_form(**form)
    except ValueError as exc:
        return _render_owner_form(
            request,
            template_name="owners/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            institutions=await _load_record_form_institutions(request),
            error=str(exc),
            status_code=400,
        )

    try:
        async with _admin_owner_service_scope(request) as service:
            created = await service.create_owner(
                name=parsed.name,
                surname=parsed.surname,
                email=parsed.email,
                institution_id=parsed.institution_id,
                external_id=parsed.external_id,
                notes=parsed.notes,
                is_active=parsed.is_active,
                actor_admin_id=action_context.admin_user.id,
                reason=parsed.reason,
            )
    except (DuplicateRecordError, RecordNotFoundError, ValueError):
        return _render_owner_form(
            request,
            template_name="owners/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            institutions=await _load_record_form_institutions(request),
            error=_ADMIN_STATUS_MESSAGES["invalid_admin_record"][1],
            status_code=400,
        )

    return _redirect_to_admin_owner(created.id, message="owner_created")


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
            "admin_status_message": _admin_status_message(request),
            "owner": owner,
        },
    )


@router.get("/owners/{owner_id}/edit", response_class=HTMLResponse)
async def edit_admin_owner_form(request: Request, owner_id: str) -> Response:
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

    return _render_owner_form(
        request,
        template_name="owners/edit.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_owner_form_from_detail(owner),
        institutions=await _load_record_form_institutions(request),
        owner_id=parsed_owner_id,
    )


@router.post("/owners/{owner_id}/edit", response_class=HTMLResponse)
async def update_admin_owner(
    request: Request,
    owner_id: str,
    csrf_token: str = Form(""),
    name: str = Form(""),
    surname: str = Form(""),
    email: str = Form(""),
    institution_id: str = Form(""),
    external_id: str = Form(""),
    notes: str = Form(""),
    is_active: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_owner_id = uuid.UUID(owner_id)
    except ValueError:
        return HTMLResponse("Owner not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = _owner_form_from_values(
        name=name,
        surname=surname,
        email=email,
        institution_id=institution_id,
        external_id=external_id,
        notes=notes,
        is_active=is_active,
        reason=reason,
    )
    try:
        parsed = parse_owner_form(**form)
    except ValueError as exc:
        return _render_owner_form(
            request,
            template_name="owners/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            institutions=await _load_record_form_institutions(request),
            owner_id=parsed_owner_id,
            error=str(exc),
            status_code=400,
        )

    try:
        async with _admin_owner_service_scope(request) as service:
            updated = await service.update_owner(
                parsed_owner_id,
                name=parsed.name,
                surname=parsed.surname,
                email=parsed.email,
                institution_id=parsed.institution_id,
                external_id=parsed.external_id,
                notes=parsed.notes,
                is_active=parsed.is_active,
                actor_admin_id=action_context.admin_user.id,
                reason=parsed.reason,
            )
    except RecordNotFoundError as exc:
        if getattr(exc, "entity", "") == "Owner":
            return HTMLResponse("Owner not found.", status_code=404)
        return _render_owner_form(
            request,
            template_name="owners/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            institutions=await _load_record_form_institutions(request),
            owner_id=parsed_owner_id,
            error=_ADMIN_STATUS_MESSAGES["invalid_admin_record"][1],
            status_code=400,
        )
    except (DuplicateRecordError, ValueError):
        return _render_owner_form(
            request,
            template_name="owners/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            institutions=await _load_record_form_institutions(request),
            owner_id=parsed_owner_id,
            error=_ADMIN_STATUS_MESSAGES["invalid_admin_record"][1],
            status_code=400,
        )

    return _redirect_to_admin_owner(updated.id, message="owner_updated")


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
            "admin_status_message": _admin_status_message(request),
            "institutions": rows,
            "filters": {
                "name": name or "",
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/institutions/new", response_class=HTMLResponse)
async def new_admin_institution_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return _render_institution_form(
        request,
        template_name="institutions/create.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_default_institution_form(),
    )


@router.post("/institutions/new", response_class=HTMLResponse)
async def create_admin_institution(
    request: Request,
    csrf_token: str = Form(""),
    name: str = Form(""),
    country: str = Form(""),
    notes: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = _institution_form_from_values(name=name, country=country, notes=notes, reason=reason)
    try:
        parsed = parse_institution_form(**form)
    except ValueError as exc:
        return _render_institution_form(
            request,
            template_name="institutions/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            error=str(exc),
            status_code=400,
        )

    try:
        async with _admin_institution_service_scope(request) as service:
            created = await service.create_institution(
                name=parsed.name,
                country=parsed.country,
                notes=parsed.notes,
                actor_admin_id=action_context.admin_user.id,
                reason=parsed.reason,
            )
    except (DuplicateRecordError, ValueError):
        return _render_institution_form(
            request,
            template_name="institutions/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            error=_ADMIN_STATUS_MESSAGES["invalid_admin_record"][1],
            status_code=400,
        )

    return _redirect_to_admin_institution(created.id, message="institution_created")


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
            "admin_status_message": _admin_status_message(request),
            "institution": institution,
        },
    )


@router.get("/institutions/{institution_id}/edit", response_class=HTMLResponse)
async def edit_admin_institution_form(request: Request, institution_id: str) -> Response:
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

    return _render_institution_form(
        request,
        template_name="institutions/edit.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_institution_form_from_detail(institution),
        institution_id=parsed_institution_id,
    )


@router.post("/institutions/{institution_id}/edit", response_class=HTMLResponse)
async def update_admin_institution(
    request: Request,
    institution_id: str,
    csrf_token: str = Form(""),
    name: str = Form(""),
    country: str = Form(""),
    notes: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_institution_id = uuid.UUID(institution_id)
    except ValueError:
        return HTMLResponse("Institution not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = _institution_form_from_values(name=name, country=country, notes=notes, reason=reason)
    try:
        parsed = parse_institution_form(**form)
    except ValueError as exc:
        return _render_institution_form(
            request,
            template_name="institutions/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            institution_id=parsed_institution_id,
            error=str(exc),
            status_code=400,
        )

    try:
        async with _admin_institution_service_scope(request) as service:
            updated = await service.update_institution(
                parsed_institution_id,
                name=parsed.name,
                country=parsed.country,
                notes=parsed.notes,
                actor_admin_id=action_context.admin_user.id,
                reason=parsed.reason,
            )
    except RecordNotFoundError:
        return HTMLResponse("Institution not found.", status_code=404)
    except (DuplicateRecordError, ValueError):
        return _render_institution_form(
            request,
            template_name="institutions/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            institution_id=parsed_institution_id,
            error=_ADMIN_STATUS_MESSAGES["invalid_admin_record"][1],
            status_code=400,
        )

    return _redirect_to_admin_institution(updated.id, message="institution_updated")


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
            "admin_status_message": _admin_status_message(request),
            "cohorts": rows,
            "filters": {
                "name": name or "",
                "active": "" if active is None else str(active).lower(),
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/cohorts/new", response_class=HTMLResponse)
async def new_admin_cohort_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return _render_cohort_form(
        request,
        template_name="cohorts/create.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_default_cohort_form(),
    )


@router.post("/cohorts/new", response_class=HTMLResponse)
async def create_admin_cohort(
    request: Request,
    csrf_token: str = Form(""),
    name: str = Form(""),
    description: str = Form(""),
    starts_at: str = Form(""),
    ends_at: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = _cohort_form_from_values(
        name=name,
        description=description,
        starts_at=starts_at,
        ends_at=ends_at,
        reason=reason,
    )
    try:
        parsed = parse_cohort_form(**form)
    except ValueError as exc:
        return _render_cohort_form(
            request,
            template_name="cohorts/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            error=str(exc),
            status_code=400,
        )

    try:
        async with _admin_cohort_service_scope(request) as service:
            created = await service.create_cohort(
                name=parsed.name,
                description=parsed.description,
                starts_at=parsed.starts_at,
                ends_at=parsed.ends_at,
                actor_admin_id=action_context.admin_user.id,
                reason=parsed.reason,
            )
    except (DuplicateRecordError, ValueError, UnsupportedRecordOperationError):
        return _render_cohort_form(
            request,
            template_name="cohorts/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            error=_ADMIN_STATUS_MESSAGES["invalid_admin_record"][1],
            status_code=400,
        )

    return _redirect_to_admin_cohort(created.id, message="cohort_created")


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
            "admin_status_message": _admin_status_message(request),
            "cohort": cohort,
        },
    )


@router.get("/cohorts/{cohort_id}/edit", response_class=HTMLResponse)
async def edit_admin_cohort_form(request: Request, cohort_id: str) -> Response:
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

    return _render_cohort_form(
        request,
        template_name="cohorts/edit.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_cohort_form_from_detail(cohort),
        cohort_id=parsed_cohort_id,
    )


@router.post("/cohorts/{cohort_id}/edit", response_class=HTMLResponse)
async def update_admin_cohort(
    request: Request,
    cohort_id: str,
    csrf_token: str = Form(""),
    name: str = Form(""),
    description: str = Form(""),
    starts_at: str = Form(""),
    ends_at: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_cohort_id = uuid.UUID(cohort_id)
    except ValueError:
        return HTMLResponse("Cohort not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = _cohort_form_from_values(
        name=name,
        description=description,
        starts_at=starts_at,
        ends_at=ends_at,
        reason=reason,
    )
    try:
        parsed = parse_cohort_form(**form)
    except ValueError as exc:
        return _render_cohort_form(
            request,
            template_name="cohorts/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            cohort_id=parsed_cohort_id,
            error=str(exc),
            status_code=400,
        )

    try:
        async with _admin_cohort_service_scope(request) as service:
            updated = await service.update_cohort(
                parsed_cohort_id,
                name=parsed.name,
                description=parsed.description,
                starts_at=parsed.starts_at,
                ends_at=parsed.ends_at,
                actor_admin_id=action_context.admin_user.id,
                reason=parsed.reason,
            )
    except RecordNotFoundError:
        return HTMLResponse("Cohort not found.", status_code=404)
    except (DuplicateRecordError, ValueError, UnsupportedRecordOperationError):
        return _render_cohort_form(
            request,
            template_name="cohorts/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            cohort_id=parsed_cohort_id,
            error=_ADMIN_STATUS_MESSAGES["invalid_admin_record"][1],
            status_code=400,
        )

    return _redirect_to_admin_cohort(updated.id, message="cohort_updated")


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
            "admin_status_message": _admin_status_message(request),
            "providers": rows,
            "filters": {
                "provider": provider or "",
                "enabled": "" if enabled is None else str(enabled).lower(),
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/providers/new", response_class=HTMLResponse)
async def new_admin_provider_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return _render_provider_config_form(
        request,
        template_name="providers/create.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_default_provider_config_form(),
    )


@router.post("/providers/new", response_class=HTMLResponse)
async def create_admin_provider(
    request: Request,
    csrf_token: str = Form(""),
    provider: str = Form(""),
    display_name: str = Form(""),
    kind: str = Form("openai_compatible"),
    base_url: str = Form(""),
    api_key_env_var: str = Form(""),
    enabled: str = Form(""),
    timeout_seconds: str = Form("300"),
    max_retries: str = Form("2"),
    notes: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = _provider_config_form_from_values(
        provider=provider,
        display_name=display_name,
        kind=kind,
        base_url=base_url,
        api_key_env_var=api_key_env_var,
        enabled=enabled,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        notes=notes,
        reason=reason,
    )
    try:
        parsed = _parse_provider_config_form(form, require_reason=True)
    except ValueError as exc:
        return _render_provider_config_form(
            request,
            template_name="providers/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            error=str(exc),
            status_code=400,
        )

    try:
        async with _admin_provider_config_service_scope(request) as service:
            created = await service.create_provider_config(
                provider=parsed["provider"],
                display_name=parsed["display_name"],
                kind=parsed["kind"],
                base_url=parsed["base_url"],
                api_key_env_var=parsed["api_key_env_var"],
                enabled=parsed["enabled"],
                timeout_seconds=parsed["timeout_seconds"],
                max_retries=parsed["max_retries"],
                notes=parsed["notes"],
                actor_admin_id=action_context.admin_user.id,
                reason=parsed["reason"],
            )
    except (DuplicateRecordError, ValueError):
        return _render_provider_config_form(
            request,
            template_name="providers/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            error=_ADMIN_STATUS_MESSAGES["invalid_provider_config"][1],
            status_code=400,
        )

    return _redirect_to_admin_provider(created.id, message="provider_config_created")


@router.get("/providers/{provider_config_id}/edit", response_class=HTMLResponse)
async def edit_admin_provider_form(request: Request, provider_config_id: str) -> Response:
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

    return _render_provider_config_form(
        request,
        template_name="providers/edit.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_provider_config_form_from_detail(provider_row),
        provider_config_id=parsed_provider_config_id,
    )


@router.post("/providers/{provider_config_id}/edit", response_class=HTMLResponse)
async def update_admin_provider(
    request: Request,
    provider_config_id: str,
    csrf_token: str = Form(""),
    provider: str = Form(""),
    display_name: str = Form(""),
    kind: str = Form("openai_compatible"),
    base_url: str = Form(""),
    api_key_env_var: str = Form(""),
    enabled: str = Form(""),
    timeout_seconds: str = Form("300"),
    max_retries: str = Form("2"),
    notes: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_provider_config_id = uuid.UUID(provider_config_id)
    except ValueError:
        return HTMLResponse("Provider config not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = _provider_config_form_from_values(
        provider=provider,
        display_name=display_name,
        kind=kind,
        base_url=base_url,
        api_key_env_var=api_key_env_var,
        enabled=enabled,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        notes=notes,
        reason=reason,
    )
    try:
        parsed = _parse_provider_config_form(form, require_reason=True, require_base_url=True)
    except ValueError as exc:
        return _render_provider_config_form(
            request,
            template_name="providers/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            provider_config_id=parsed_provider_config_id,
            error=str(exc),
            status_code=400,
        )

    try:
        async with _admin_provider_config_service_scope(request) as service:
            updated = await service.update_provider_config(
                str(parsed_provider_config_id),
                provider=parsed["provider"],
                display_name=parsed["display_name"],
                kind=parsed["kind"],
                base_url=parsed["base_url"] or "",
                api_key_env_var=parsed["api_key_env_var"],
                enabled=parsed["enabled"],
                timeout_seconds=parsed["timeout_seconds"],
                max_retries=parsed["max_retries"],
                notes=parsed["notes"],
                actor_admin_id=action_context.admin_user.id,
                reason=parsed["reason"],
            )
    except RecordNotFoundError:
        return HTMLResponse("Provider config not found.", status_code=404)
    except (DuplicateRecordError, ValueError):
        return _render_provider_config_form(
            request,
            template_name="providers/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            provider_config_id=parsed_provider_config_id,
            error=_ADMIN_STATUS_MESSAGES["invalid_provider_config"][1],
            status_code=400,
        )

    return _redirect_to_admin_provider(updated.id, message="provider_config_updated")


@router.post("/providers/{provider_config_id}/enable", response_class=HTMLResponse)
async def enable_admin_provider(
    request: Request,
    provider_config_id: str,
    csrf_token: str = Form(""),
    reason: str = Form(""),
) -> Response:
    return await _set_admin_provider_enabled(
        request,
        provider_config_id=provider_config_id,
        csrf_token=csrf_token,
        enabled=True,
        reason=reason,
    )


@router.post("/providers/{provider_config_id}/disable", response_class=HTMLResponse)
async def disable_admin_provider(
    request: Request,
    provider_config_id: str,
    csrf_token: str = Form(""),
    confirm_disable: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_provider_config_id = uuid.UUID(provider_config_id)
    except ValueError:
        return HTMLResponse("Provider config not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    if not _is_checked(confirm_disable):
        return _redirect_to_admin_provider(
            parsed_provider_config_id,
            message="provider_config_disable_confirmation_required",
        )

    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _redirect_to_admin_provider(parsed_provider_config_id, message="provider_config_reason_required")

    try:
        async with _admin_provider_config_service_scope(request) as service:
            await service.set_provider_enabled(
                str(parsed_provider_config_id),
                enabled=False,
                actor_admin_id=action_context.admin_user.id,
                reason=cleaned_reason,
            )
    except RecordNotFoundError:
        return HTMLResponse("Provider config not found.", status_code=404)
    except ValueError:
        return _redirect_to_admin_provider(parsed_provider_config_id, message="provider_config_failed")

    return _redirect_to_admin_provider(parsed_provider_config_id, message="provider_config_disabled")


async def _set_admin_provider_enabled(
    request: Request,
    *,
    provider_config_id: str,
    csrf_token: str,
    enabled: bool,
    reason: str,
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_provider_config_id = uuid.UUID(provider_config_id)
    except ValueError:
        return HTMLResponse("Provider config not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _redirect_to_admin_provider(parsed_provider_config_id, message="provider_config_reason_required")

    try:
        async with _admin_provider_config_service_scope(request) as service:
            await service.set_provider_enabled(
                str(parsed_provider_config_id),
                enabled=enabled,
                actor_admin_id=action_context.admin_user.id,
                reason=cleaned_reason,
            )
    except RecordNotFoundError:
        return HTMLResponse("Provider config not found.", status_code=404)
    except ValueError:
        return _redirect_to_admin_provider(parsed_provider_config_id, message="provider_config_failed")

    return _redirect_to_admin_provider(
        parsed_provider_config_id,
        message="provider_config_enabled" if enabled else "provider_config_disabled",
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
            "admin_status_message": _admin_status_message(request),
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
            "admin_status_message": _admin_status_message(request),
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


@router.get("/routes/import", response_class=HTMLResponse)
async def admin_route_import_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return _render_route_import_form(
        request,
        admin=context.admin_user,
        csrf_token=csrf_token,
    )


@router.post("/routes/import/preview", response_class=HTMLResponse)
async def admin_route_import_preview(
    request: Request,
    csrf_token: str = Form(""),
    import_format: str = Form("auto"),
    import_text: str = Form(""),
    source_label: str = Form(""),
    import_file: UploadFile | None = File(None),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    try:
        _parse_optional_import_source_label(source_label)
        filename, text = await _read_route_import_input(
            import_file=import_file,
            import_text=import_text,
            max_bytes=settings.ROUTE_IMPORT_MAX_BYTES,
        )
        detected_format = detect_route_import_format(
            filename=filename,
            requested_format=import_format,
            text=text,
        )
        raw_rows = (
            parse_route_import_json(text)
            if detected_format == "json"
            else parse_route_import_csv(text)
        )
        preview = await _build_route_import_preview(
            request,
            raw_rows,
            max_rows=settings.ROUTE_IMPORT_MAX_ROWS,
        )
    except ValueError as exc:
        return _render_route_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": "",
                "source_label": "",
            },
            error=str(exc),
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "routes/import_preview.html",
        {
            "admin": action_context.admin_user,
            "csrf_token": csrf_token,
            "preview": preview,
            "import_format": detected_format,
            "source_label": source_label.strip(),
            "max_rows": settings.ROUTE_IMPORT_MAX_ROWS,
            "max_bytes": settings.ROUTE_IMPORT_MAX_BYTES,
        },
    )


@router.post("/routes/import/execute", response_class=HTMLResponse)
async def admin_route_import_execute(
    request: Request,
    csrf_token: str = Form(""),
    import_format: str = Form("auto"),
    import_text: str = Form(""),
    source_label: str = Form(""),
    reason: str = Form(""),
    confirm_import: str = Form(""),
    import_file: UploadFile | None = File(None),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    if confirm_import != "true":
        return _render_route_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": "",
                "source_label": "",
                "reason": reason,
            },
            error="Confirm route import execution before continuing.",
            status_code=400,
        )
    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _render_route_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": "",
                "source_label": "",
                "reason": reason,
            },
            error="Enter an audit reason before importing model route rows.",
            status_code=400,
        )

    try:
        _parse_optional_import_source_label(source_label)
        filename, text = await _read_route_import_input(
            import_file=import_file,
            import_text=import_text,
            max_bytes=settings.ROUTE_IMPORT_MAX_BYTES,
        )
        detected_format = detect_route_import_format(
            filename=filename,
            requested_format=import_format,
            text=text,
        )
        raw_rows = (
            parse_route_import_json(text)
            if detected_format == "json"
            else parse_route_import_csv(text)
        )
        preview = await _build_route_import_preview(
            request,
            raw_rows,
            max_rows=settings.ROUTE_IMPORT_MAX_ROWS,
        )
        plan = build_route_import_execution_plan(preview)
    except ValueError as exc:
        return _render_route_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": "",
                "source_label": "",
                "reason": reason,
            },
            error=str(exc),
            status_code=400,
        )

    if not plan.executable:
        return _render_route_import_result(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            result=_blocked_route_import_result(plan),
            import_format=detected_format,
            source_label=source_label.strip(),
            status_code=400,
        )

    try:
        async with _admin_model_route_service_scope(request) as service:
            result = await execute_route_import_plan(
                plan,
                model_route_service=service,
                actor_admin_id=action_context.admin_user.id,
                reason=cleaned_reason,
            )
    except ValueError:
        return _render_route_import_result(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            result=_blocked_route_import_result(plan),
            import_format=detected_format,
            source_label=source_label.strip(),
            error="Route import execution failed validation. No rows were written.",
            status_code=400,
        )

    return _render_route_import_result(
        request,
        admin=action_context.admin_user,
        csrf_token=csrf_token,
        result=result,
        import_format=detected_format,
        source_label=source_label.strip(),
    )


@router.get("/routes/new", response_class=HTMLResponse)
async def create_admin_route_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return _render_route_form(
        request,
        template_name="routes/create.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_default_route_form(),
        provider_choices=await _load_route_provider_choices(request),
    )


@router.post("/routes/new", response_class=HTMLResponse)
async def create_admin_route(
    request: Request,
    csrf_token: str = Form(""),
    requested_model: str = Form(""),
    match_type: str = Form("exact"),
    endpoint: str = Form(CHAT_COMPLETIONS_ENDPOINT),
    provider: str = Form(""),
    upstream_model: str = Form(""),
    priority: str = Form("100"),
    enabled: str = Form(""),
    visible_in_models: str = Form(""),
    supports_streaming: str = Form(""),
    capabilities: str = Form(""),
    notes: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    provider_choices = await _load_route_provider_choices(request)
    form = _route_form_from_values(
        requested_model=requested_model,
        match_type=match_type,
        endpoint=endpoint,
        provider=provider,
        upstream_model=upstream_model,
        priority=priority,
        enabled=enabled,
        visible_in_models=visible_in_models,
        supports_streaming=supports_streaming,
        capabilities=capabilities,
        notes=notes,
        reason=reason,
    )
    try:
        parsed = _parse_model_route_form(form, provider_choices=provider_choices, require_reason=True)
    except ValueError as exc:
        return _render_route_form(
            request,
            template_name="routes/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            provider_choices=provider_choices,
            error=str(exc),
            status_code=400,
        )

    try:
        async with _admin_model_route_service_scope(request) as service:
            created = await service.create_model_route(
                requested_model=parsed["requested_model"],
                match_type=parsed["match_type"],
                endpoint=parsed["endpoint"],
                provider=parsed["provider"],
                upstream_model=parsed["upstream_model"],
                priority=parsed["priority"],
                enabled=parsed["enabled"],
                visible_in_models=parsed["visible_in_models"],
                supports_streaming=parsed["supports_streaming"],
                capabilities=parsed["capabilities"],
                notes=parsed["notes"],
                actor_admin_id=action_context.admin_user.id,
                reason=parsed["reason"],
            )
    except ValueError:
        return _render_route_form(
            request,
            template_name="routes/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            provider_choices=provider_choices,
            error=_ADMIN_STATUS_MESSAGES["invalid_model_route"][1],
            status_code=400,
        )

    return _redirect_to_admin_route(created.id, message="model_route_created")


@router.get("/routes/{route_id}/edit", response_class=HTMLResponse)
async def edit_admin_route_form(request: Request, route_id: str) -> Response:
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

    return _render_route_form(
        request,
        template_name="routes/edit.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_route_form_from_detail(route),
        provider_choices=await _load_route_provider_choices(request),
        route_id=parsed_route_id,
    )


@router.post("/routes/{route_id}/edit", response_class=HTMLResponse)
async def update_admin_route(
    request: Request,
    route_id: str,
    csrf_token: str = Form(""),
    requested_model: str = Form(""),
    match_type: str = Form("exact"),
    endpoint: str = Form(CHAT_COMPLETIONS_ENDPOINT),
    provider: str = Form(""),
    upstream_model: str = Form(""),
    priority: str = Form("100"),
    enabled: str = Form(""),
    visible_in_models: str = Form(""),
    supports_streaming: str = Form(""),
    capabilities: str = Form(""),
    notes: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_route_id = uuid.UUID(route_id)
    except ValueError:
        return HTMLResponse("Model route not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    provider_choices = await _load_route_provider_choices(request)
    form = _route_form_from_values(
        requested_model=requested_model,
        match_type=match_type,
        endpoint=endpoint,
        provider=provider,
        upstream_model=upstream_model,
        priority=priority,
        enabled=enabled,
        visible_in_models=visible_in_models,
        supports_streaming=supports_streaming,
        capabilities=capabilities,
        notes=notes,
        reason=reason,
    )
    try:
        parsed = _parse_model_route_form(form, provider_choices=provider_choices, require_reason=True)
    except ValueError as exc:
        return _render_route_form(
            request,
            template_name="routes/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            provider_choices=provider_choices,
            route_id=parsed_route_id,
            error=str(exc),
            status_code=400,
        )

    try:
        async with _admin_model_route_service_scope(request) as service:
            updated = await service.update_model_route(
                parsed_route_id,
                requested_model=parsed["requested_model"],
                match_type=parsed["match_type"],
                endpoint=parsed["endpoint"],
                provider=parsed["provider"],
                upstream_model=parsed["upstream_model"],
                priority=parsed["priority"],
                enabled=parsed["enabled"],
                visible_in_models=parsed["visible_in_models"],
                supports_streaming=parsed["supports_streaming"],
                capabilities=parsed["capabilities"],
                notes=parsed["notes"],
                actor_admin_id=action_context.admin_user.id,
                reason=parsed["reason"],
            )
    except RecordNotFoundError:
        return HTMLResponse("Model route not found.", status_code=404)
    except ValueError:
        return _render_route_form(
            request,
            template_name="routes/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            provider_choices=provider_choices,
            route_id=parsed_route_id,
            error=_ADMIN_STATUS_MESSAGES["invalid_model_route"][1],
            status_code=400,
        )

    return _redirect_to_admin_route(updated.id, message="model_route_updated")


@router.post("/routes/{route_id}/enable", response_class=HTMLResponse)
async def enable_admin_route(
    request: Request,
    route_id: str,
    csrf_token: str = Form(""),
    reason: str = Form(""),
) -> Response:
    return await _set_admin_route_enabled(
        request,
        route_id=route_id,
        csrf_token=csrf_token,
        enabled=True,
        reason=reason,
    )


@router.post("/routes/{route_id}/disable", response_class=HTMLResponse)
async def disable_admin_route(
    request: Request,
    route_id: str,
    csrf_token: str = Form(""),
    confirm_disable: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_route_id = uuid.UUID(route_id)
    except ValueError:
        return HTMLResponse("Model route not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    if not _is_checked(confirm_disable):
        return _redirect_to_admin_route(parsed_route_id, message="model_route_disable_confirmation_required")

    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _redirect_to_admin_route(parsed_route_id, message="model_route_reason_required")

    try:
        async with _admin_model_route_service_scope(request) as service:
            await service.set_model_route_enabled(
                parsed_route_id,
                enabled=False,
                actor_admin_id=action_context.admin_user.id,
                reason=cleaned_reason,
            )
    except RecordNotFoundError:
        return HTMLResponse("Model route not found.", status_code=404)
    except ValueError:
        return _redirect_to_admin_route(parsed_route_id, message="model_route_failed")

    return _redirect_to_admin_route(parsed_route_id, message="model_route_disabled")


async def _set_admin_route_enabled(
    request: Request,
    *,
    route_id: str,
    csrf_token: str,
    enabled: bool,
    reason: str,
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_route_id = uuid.UUID(route_id)
    except ValueError:
        return HTMLResponse("Model route not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _redirect_to_admin_route(parsed_route_id, message="model_route_reason_required")

    try:
        async with _admin_model_route_service_scope(request) as service:
            await service.set_model_route_enabled(
                parsed_route_id,
                enabled=enabled,
                actor_admin_id=action_context.admin_user.id,
                reason=cleaned_reason,
            )
    except RecordNotFoundError:
        return HTMLResponse("Model route not found.", status_code=404)
    except ValueError:
        return _redirect_to_admin_route(parsed_route_id, message="model_route_failed")

    return _redirect_to_admin_route(
        parsed_route_id,
        message="model_route_enabled" if enabled else "model_route_disabled",
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
            "admin_status_message": _admin_status_message(request),
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
            "admin_status_message": _admin_status_message(request),
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


@router.get("/pricing/import", response_class=HTMLResponse)
async def admin_pricing_import_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return _render_pricing_import_form(
        request,
        admin=context.admin_user,
        csrf_token=csrf_token,
    )


@router.post("/pricing/import/preview", response_class=HTMLResponse)
async def admin_pricing_import_preview(
    request: Request,
    csrf_token: str = Form(""),
    import_format: str = Form("auto"),
    import_text: str = Form(""),
    source_label: str = Form(""),
    import_file: UploadFile | None = File(None),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    try:
        _parse_optional_import_source_label(source_label)
        filename, text = await _read_pricing_import_input(
            import_file=import_file,
            import_text=import_text,
            max_bytes=settings.PRICING_IMPORT_MAX_BYTES,
        )
        detected_format = detect_pricing_import_format(
            filename=filename,
            requested_format=import_format,
            text=text,
        )
        raw_rows = (
            parse_pricing_import_json(text)
            if detected_format == "json"
            else parse_pricing_import_csv(text)
        )
        preview = validate_pricing_import_rows(
            raw_rows,
            max_rows=settings.PRICING_IMPORT_MAX_ROWS,
        )
        preview = await _classify_pricing_import_preview(request, preview)
    except ValueError as exc:
        return _render_pricing_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": "",
                "source_label": "",
            },
            error=str(exc),
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "pricing/import_preview.html",
        {
            "admin": action_context.admin_user,
            "csrf_token": csrf_token,
            "preview": preview,
            "import_format": detected_format,
            "source_label": source_label.strip(),
            "max_rows": settings.PRICING_IMPORT_MAX_ROWS,
            "max_bytes": settings.PRICING_IMPORT_MAX_BYTES,
        },
    )


@router.post("/pricing/import/execute", response_class=HTMLResponse)
async def admin_pricing_import_execute(
    request: Request,
    csrf_token: str = Form(""),
    import_format: str = Form("auto"),
    import_text: str = Form(""),
    source_label: str = Form(""),
    reason: str = Form(""),
    confirm_import: str = Form(""),
    import_file: UploadFile | None = File(None),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    if confirm_import != "true":
        return _render_pricing_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": import_text,
                "source_label": source_label,
                "reason": reason,
            },
            error="Confirm pricing import execution before continuing.",
            status_code=400,
        )
    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _render_pricing_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": import_text,
                "source_label": source_label,
                "reason": reason,
            },
            error="Enter an audit reason before importing pricing rows.",
            status_code=400,
        )

    try:
        _parse_optional_import_source_label(source_label)
        filename, text = await _read_pricing_import_input(
            import_file=import_file,
            import_text=import_text,
            max_bytes=settings.PRICING_IMPORT_MAX_BYTES,
        )
        detected_format = detect_pricing_import_format(
            filename=filename,
            requested_format=import_format,
            text=text,
        )
        raw_rows = (
            parse_pricing_import_json(text)
            if detected_format == "json"
            else parse_pricing_import_csv(text)
        )
        preview = validate_pricing_import_rows(
            raw_rows,
            max_rows=settings.PRICING_IMPORT_MAX_ROWS,
        )
        preview = await _classify_pricing_import_preview(request, preview)
        plan = build_pricing_import_execution_plan(preview)
    except ValueError as exc:
        return _render_pricing_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": import_text,
                "source_label": source_label,
                "reason": reason,
            },
            error=str(exc),
            status_code=400,
        )

    if not plan.executable:
        return _render_pricing_import_result(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            result=_blocked_pricing_import_result(plan),
            import_format=detected_format,
            source_label=source_label.strip(),
            status_code=400,
        )

    try:
        async with _admin_pricing_rule_service_scope(request) as service:
            result = await execute_pricing_import_plan(
                plan,
                pricing_rule_service=service,
                actor_admin_id=action_context.admin_user.id,
                reason=cleaned_reason,
            )
    except ValueError:
        return _render_pricing_import_result(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            result=_blocked_pricing_import_result(plan),
            import_format=detected_format,
            source_label=source_label.strip(),
            error="Pricing import execution failed validation. No rows were written.",
            status_code=400,
        )

    return _render_pricing_import_result(
        request,
        admin=action_context.admin_user,
        csrf_token=csrf_token,
        result=result,
        import_format=detected_format,
        source_label=source_label.strip(),
    )


@router.get("/pricing/new", response_class=HTMLResponse)
async def create_admin_pricing_rule_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return _render_pricing_rule_form(
        request,
        template_name="pricing/create.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_default_pricing_rule_form(),
        provider_choices=await _load_catalog_provider_choices(request),
    )


@router.post("/pricing/new", response_class=HTMLResponse)
async def create_admin_pricing_rule(
    request: Request,
    csrf_token: str = Form(""),
    provider: str = Form(""),
    upstream_model: str = Form(""),
    endpoint: str = Form(CHAT_COMPLETIONS_ENDPOINT),
    currency: str = Form("EUR"),
    input_price_per_1m: str = Form(""),
    cached_input_price_per_1m: str = Form(""),
    output_price_per_1m: str = Form(""),
    reasoning_price_per_1m: str = Form(""),
    request_price: str = Form(""),
    pricing_metadata: str = Form(""),
    valid_from: str = Form(""),
    valid_until: str = Form(""),
    enabled: str = Form(""),
    source_url: str = Form(""),
    notes: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    provider_choices = await _load_catalog_provider_choices(request)
    form = _pricing_rule_form_from_values(
        provider=provider,
        upstream_model=upstream_model,
        endpoint=endpoint,
        currency=currency,
        input_price_per_1m=input_price_per_1m,
        cached_input_price_per_1m=cached_input_price_per_1m,
        output_price_per_1m=output_price_per_1m,
        reasoning_price_per_1m=reasoning_price_per_1m,
        request_price=request_price,
        pricing_metadata=pricing_metadata,
        valid_from=valid_from,
        valid_until=valid_until,
        enabled=enabled,
        source_url=source_url,
        notes=notes,
        reason=reason,
    )
    try:
        parsed = _parse_pricing_rule_form(form, provider_choices=provider_choices, require_reason=True)
    except ValueError:
        return _render_pricing_rule_form(
            request,
            template_name="pricing/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            provider_choices=provider_choices,
            error=_ADMIN_STATUS_MESSAGES["invalid_pricing_rule"][1],
            status_code=400,
        )

    try:
        async with _admin_pricing_rule_service_scope(request) as service:
            created = await service.create_pricing_rule(
                provider=parsed["provider"],
                model=parsed["upstream_model"],
                endpoint=parsed["endpoint"],
                currency=parsed["currency"],
                input_price_per_1m=parsed["input_price_per_1m"],
                cached_input_price_per_1m=parsed["cached_input_price_per_1m"],
                output_price_per_1m=parsed["output_price_per_1m"],
                reasoning_price_per_1m=parsed["reasoning_price_per_1m"],
                request_price=parsed["request_price"],
                pricing_metadata=parsed["pricing_metadata"],
                valid_from=parsed["valid_from"],
                valid_until=parsed["valid_until"],
                source_url=parsed["source_url"],
                notes=parsed["notes"],
                enabled=parsed["enabled"],
                actor_admin_id=action_context.admin_user.id,
                reason=parsed["reason"],
            )
    except ValueError:
        return _render_pricing_rule_form(
            request,
            template_name="pricing/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            provider_choices=provider_choices,
            error=_ADMIN_STATUS_MESSAGES["invalid_pricing_rule"][1],
            status_code=400,
        )

    return _redirect_to_admin_pricing_rule(created.id, message="pricing_rule_created")


@router.get("/pricing/{pricing_rule_id}/edit", response_class=HTMLResponse)
async def edit_admin_pricing_rule_form(request: Request, pricing_rule_id: str) -> Response:
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

    return _render_pricing_rule_form(
        request,
        template_name="pricing/edit.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_pricing_rule_form_from_detail(pricing_rule),
        provider_choices=await _load_catalog_provider_choices(request),
        pricing_rule_id=parsed_pricing_rule_id,
    )


@router.post("/pricing/{pricing_rule_id}/edit", response_class=HTMLResponse)
async def update_admin_pricing_rule(
    request: Request,
    pricing_rule_id: str,
    csrf_token: str = Form(""),
    provider: str = Form(""),
    upstream_model: str = Form(""),
    endpoint: str = Form(CHAT_COMPLETIONS_ENDPOINT),
    currency: str = Form("EUR"),
    input_price_per_1m: str = Form(""),
    cached_input_price_per_1m: str = Form(""),
    output_price_per_1m: str = Form(""),
    reasoning_price_per_1m: str = Form(""),
    request_price: str = Form(""),
    pricing_metadata: str = Form(""),
    valid_from: str = Form(""),
    valid_until: str = Form(""),
    enabled: str = Form(""),
    source_url: str = Form(""),
    notes: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_pricing_rule_id = uuid.UUID(pricing_rule_id)
    except ValueError:
        return HTMLResponse("Pricing rule not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    provider_choices = await _load_catalog_provider_choices(request)
    form = _pricing_rule_form_from_values(
        provider=provider,
        upstream_model=upstream_model,
        endpoint=endpoint,
        currency=currency,
        input_price_per_1m=input_price_per_1m,
        cached_input_price_per_1m=cached_input_price_per_1m,
        output_price_per_1m=output_price_per_1m,
        reasoning_price_per_1m=reasoning_price_per_1m,
        request_price=request_price,
        pricing_metadata=pricing_metadata,
        valid_from=valid_from,
        valid_until=valid_until,
        enabled=enabled,
        source_url=source_url,
        notes=notes,
        reason=reason,
    )
    try:
        parsed = _parse_pricing_rule_form(form, provider_choices=provider_choices, require_reason=True)
    except ValueError:
        return _render_pricing_rule_form(
            request,
            template_name="pricing/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            provider_choices=provider_choices,
            pricing_rule_id=parsed_pricing_rule_id,
            error=_ADMIN_STATUS_MESSAGES["invalid_pricing_rule"][1],
            status_code=400,
        )

    try:
        async with _admin_pricing_rule_service_scope(request) as service:
            updated = await service.update_pricing_rule(
                parsed_pricing_rule_id,
                provider=parsed["provider"],
                model=parsed["upstream_model"],
                endpoint=parsed["endpoint"],
                currency=parsed["currency"],
                input_price_per_1m=parsed["input_price_per_1m"],
                cached_input_price_per_1m=parsed["cached_input_price_per_1m"],
                output_price_per_1m=parsed["output_price_per_1m"],
                reasoning_price_per_1m=parsed["reasoning_price_per_1m"],
                request_price=parsed["request_price"],
                pricing_metadata=parsed["pricing_metadata"],
                valid_from=parsed["valid_from"],
                valid_until=parsed["valid_until"],
                source_url=parsed["source_url"],
                notes=parsed["notes"],
                enabled=parsed["enabled"],
                actor_admin_id=action_context.admin_user.id,
                reason=parsed["reason"],
            )
    except RecordNotFoundError:
        return HTMLResponse("Pricing rule not found.", status_code=404)
    except ValueError:
        return _render_pricing_rule_form(
            request,
            template_name="pricing/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            provider_choices=provider_choices,
            pricing_rule_id=parsed_pricing_rule_id,
            error=_ADMIN_STATUS_MESSAGES["invalid_pricing_rule"][1],
            status_code=400,
        )

    return _redirect_to_admin_pricing_rule(updated.id, message="pricing_rule_updated")


@router.post("/pricing/{pricing_rule_id}/enable", response_class=HTMLResponse)
async def enable_admin_pricing_rule(
    request: Request,
    pricing_rule_id: str,
    csrf_token: str = Form(""),
    reason: str = Form(""),
) -> Response:
    return await _set_admin_pricing_rule_enabled(
        request,
        pricing_rule_id=pricing_rule_id,
        enabled=True,
        csrf_token=csrf_token,
        reason=reason,
    )


@router.post("/pricing/{pricing_rule_id}/disable", response_class=HTMLResponse)
async def disable_admin_pricing_rule(
    request: Request,
    pricing_rule_id: str,
    csrf_token: str = Form(""),
    confirm_disable: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_pricing_rule_id = uuid.UUID(pricing_rule_id)
    except ValueError:
        return HTMLResponse("Pricing rule not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    if confirm_disable != "true":
        return _redirect_to_admin_pricing_rule(
            parsed_pricing_rule_id,
            message="pricing_rule_disable_confirmation_required",
        )
    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _redirect_to_admin_pricing_rule(parsed_pricing_rule_id, message="pricing_rule_reason_required")

    try:
        async with _admin_pricing_rule_service_scope(request) as service:
            await service.set_pricing_rule_enabled(
                parsed_pricing_rule_id,
                enabled=False,
                actor_admin_id=action_context.admin_user.id,
                reason=cleaned_reason,
            )
    except RecordNotFoundError:
        return HTMLResponse("Pricing rule not found.", status_code=404)
    except ValueError:
        return _redirect_to_admin_pricing_rule(parsed_pricing_rule_id, message="pricing_rule_failed")

    return _redirect_to_admin_pricing_rule(parsed_pricing_rule_id, message="pricing_rule_disabled")


async def _set_admin_pricing_rule_enabled(
    request: Request,
    *,
    pricing_rule_id: str,
    enabled: bool,
    csrf_token: str,
    reason: str,
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_pricing_rule_id = uuid.UUID(pricing_rule_id)
    except ValueError:
        return HTMLResponse("Pricing rule not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _redirect_to_admin_pricing_rule(parsed_pricing_rule_id, message="pricing_rule_reason_required")

    try:
        async with _admin_pricing_rule_service_scope(request) as service:
            await service.set_pricing_rule_enabled(
                parsed_pricing_rule_id,
                enabled=enabled,
                actor_admin_id=action_context.admin_user.id,
                reason=cleaned_reason,
            )
    except RecordNotFoundError:
        return HTMLResponse("Pricing rule not found.", status_code=404)
    except ValueError:
        return _redirect_to_admin_pricing_rule(parsed_pricing_rule_id, message="pricing_rule_failed")

    return _redirect_to_admin_pricing_rule(
        parsed_pricing_rule_id,
        message="pricing_rule_enabled" if enabled else "pricing_rule_disabled",
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
            "admin_status_message": _admin_status_message(request),
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
            "admin_status_message": _admin_status_message(request),
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


@router.get("/fx/new", response_class=HTMLResponse)
async def create_admin_fx_rate_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return _render_fx_rate_form(
        request,
        template_name="fx/create.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_default_fx_rate_form(),
    )


@router.get("/fx/import", response_class=HTMLResponse)
async def admin_fx_import_form(request: Request) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    return _render_fx_import_form(
        request,
        admin=context.admin_user,
        csrf_token=csrf_token,
    )


@router.post("/fx/import/preview", response_class=HTMLResponse)
async def admin_fx_import_preview(
    request: Request,
    csrf_token: str = Form(""),
    import_format: str = Form("auto"),
    import_text: str = Form(""),
    source_label: str = Form(""),
    import_file: UploadFile | None = File(None),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    try:
        _parse_optional_import_source_label(source_label)
        filename, text = await _read_fx_import_input(
            import_file=import_file,
            import_text=import_text,
            max_bytes=settings.FX_IMPORT_MAX_BYTES,
        )
        detected_format = detect_fx_import_format(
            filename=filename,
            requested_format=import_format,
            text=text,
        )
        raw_rows = parse_fx_import_json(text) if detected_format == "json" else parse_fx_import_csv(text)
        preview = validate_fx_import_rows(
            raw_rows,
            max_rows=settings.FX_IMPORT_MAX_ROWS,
        )
        preview = await _classify_fx_import_preview(request, preview)
    except ValueError as exc:
        return _render_fx_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": "",
                "source_label": "",
            },
            error=str(exc),
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "fx/import_preview.html",
        {
            "admin": action_context.admin_user,
            "csrf_token": csrf_token,
            "preview": preview,
            "import_format": detected_format,
            "source_label": source_label.strip(),
            "max_rows": settings.FX_IMPORT_MAX_ROWS,
            "max_bytes": settings.FX_IMPORT_MAX_BYTES,
        },
    )


@router.post("/fx/import/execute", response_class=HTMLResponse)
async def admin_fx_import_execute(
    request: Request,
    csrf_token: str = Form(""),
    import_format: str = Form("auto"),
    import_text: str = Form(""),
    source_label: str = Form(""),
    reason: str = Form(""),
    confirm_import: str = Form(""),
    import_file: UploadFile | None = File(None),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    if confirm_import != "true":
        return _render_fx_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": "",
                "source_label": "",
                "reason": reason,
            },
            error="Confirm FX import execution before continuing.",
            status_code=400,
        )
    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return _render_fx_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": "",
                "source_label": "",
                "reason": reason,
            },
            error="Enter an audit reason before importing FX rows.",
            status_code=400,
        )

    try:
        _parse_optional_import_source_label(source_label)
        filename, text = await _read_fx_import_input(
            import_file=import_file,
            import_text=import_text,
            max_bytes=settings.FX_IMPORT_MAX_BYTES,
        )
        detected_format = detect_fx_import_format(
            filename=filename,
            requested_format=import_format,
            text=text,
        )
        raw_rows = parse_fx_import_json(text) if detected_format == "json" else parse_fx_import_csv(text)
        preview = validate_fx_import_rows(
            raw_rows,
            max_rows=settings.FX_IMPORT_MAX_ROWS,
        )
        preview = await _classify_fx_import_preview(request, preview)
        plan = build_fx_import_execution_plan(preview)
    except ValueError as exc:
        return _render_fx_import_form(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form={
                "format": import_format,
                "import_text": "",
                "source_label": "",
                "reason": reason,
            },
            error=str(exc),
            status_code=400,
        )

    if not plan.executable:
        return _render_fx_import_result(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            result=_blocked_fx_import_result(plan),
            import_format=detected_format,
            source_label=source_label.strip(),
            status_code=400,
        )

    try:
        async with _admin_fx_rate_service_scope(request) as service:
            result = await execute_fx_import_plan(
                plan,
                fx_rate_service=service,
                actor_admin_id=action_context.admin_user.id,
                reason=cleaned_reason,
            )
    except ValueError:
        return _render_fx_import_result(
            request,
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            result=_blocked_fx_import_result(plan),
            import_format=detected_format,
            source_label=source_label.strip(),
            error="FX import execution failed validation. No rows were written.",
            status_code=400,
        )

    return _render_fx_import_result(
        request,
        admin=action_context.admin_user,
        csrf_token=csrf_token,
        result=result,
        import_format=detected_format,
        source_label=source_label.strip(),
    )


@router.post("/fx/new", response_class=HTMLResponse)
async def create_admin_fx_rate(
    request: Request,
    csrf_token: str = Form(""),
    base_currency: str = Form(""),
    quote_currency: str = Form("EUR"),
    rate: str = Form(""),
    valid_from: str = Form(""),
    valid_until: str = Form(""),
    source: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = _fx_rate_form_from_values(
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate=rate,
        valid_from=valid_from,
        valid_until=valid_until,
        source=source,
        reason=reason,
    )
    try:
        parsed = _parse_fx_rate_form(form, require_reason=True)
    except ValueError:
        return _render_fx_rate_form(
            request,
            template_name="fx/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            error=_ADMIN_STATUS_MESSAGES["invalid_fx_rate"][1],
            status_code=400,
        )

    try:
        async with _admin_fx_rate_service_scope(request) as service:
            created = await service.create_fx_rate(
                base_currency=parsed["base_currency"],
                quote_currency=parsed["quote_currency"],
                rate=parsed["rate"],
                valid_from=parsed["valid_from"],
                valid_until=parsed["valid_until"],
                source=parsed["source"],
                actor_admin_id=action_context.admin_user.id,
                reason=parsed["reason"],
            )
    except ValueError:
        return _render_fx_rate_form(
            request,
            template_name="fx/create.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            error=_ADMIN_STATUS_MESSAGES["invalid_fx_rate"][1],
            status_code=400,
        )

    return _redirect_to_admin_fx_rate(created.id, message="fx_rate_created")


@router.get("/fx/{fx_rate_id}/edit", response_class=HTMLResponse)
async def edit_admin_fx_rate_form(request: Request, fx_rate_id: str) -> Response:
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

    return _render_fx_rate_form(
        request,
        template_name="fx/edit.html",
        admin=context.admin_user,
        csrf_token=csrf_token,
        form=_fx_rate_form_from_detail(fx_rate),
        fx_rate_id=parsed_fx_rate_id,
    )


@router.post("/fx/{fx_rate_id}/edit", response_class=HTMLResponse)
async def update_admin_fx_rate(
    request: Request,
    fx_rate_id: str,
    csrf_token: str = Form(""),
    base_currency: str = Form(""),
    quote_currency: str = Form("EUR"),
    rate: str = Form(""),
    valid_from: str = Form(""),
    valid_until: str = Form(""),
    source: str = Form(""),
    reason: str = Form(""),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_fx_rate_id = uuid.UUID(fx_rate_id)
    except ValueError:
        return HTMLResponse("FX rate not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context

    form = _fx_rate_form_from_values(
        base_currency=base_currency,
        quote_currency=quote_currency,
        rate=rate,
        valid_from=valid_from,
        valid_until=valid_until,
        source=source,
        reason=reason,
    )
    try:
        parsed = _parse_fx_rate_form(form, require_reason=True)
    except ValueError:
        return _render_fx_rate_form(
            request,
            template_name="fx/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            fx_rate_id=parsed_fx_rate_id,
            error=_ADMIN_STATUS_MESSAGES["invalid_fx_rate"][1],
            status_code=400,
        )

    try:
        async with _admin_fx_rate_service_scope(request) as service:
            updated = await service.update_fx_rate(
                parsed_fx_rate_id,
                base_currency=parsed["base_currency"],
                quote_currency=parsed["quote_currency"],
                rate=parsed["rate"],
                valid_from=parsed["valid_from"],
                valid_until=parsed["valid_until"],
                source=parsed["source"],
                actor_admin_id=action_context.admin_user.id,
                reason=parsed["reason"],
            )
    except RecordNotFoundError:
        return HTMLResponse("FX rate not found.", status_code=404)
    except ValueError:
        return _render_fx_rate_form(
            request,
            template_name="fx/edit.html",
            admin=action_context.admin_user,
            csrf_token=csrf_token,
            form=form,
            fx_rate_id=parsed_fx_rate_id,
            error=_ADMIN_STATUS_MESSAGES["invalid_fx_rate"][1],
            status_code=400,
        )

    return _redirect_to_admin_fx_rate(updated.id, message="fx_rate_updated")


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
            "admin_status_message": _admin_status_message(request),
            "fx_rate": fx_rate,
        },
    )


@router.get("/usage", response_class=HTMLResponse)
async def list_admin_usage(
    request: Request,
    provider: str | None = Query(None),
    model: str | None = Query(None),
    endpoint: str | None = Query(None),
    status: str | None = Query(None),
    gateway_key_id: str | None = Query(None),
    owner_id: str | None = Query(None),
    institution_id: str | None = Query(None),
    cohort_id: str | None = Query(None),
    request_id: str | None = Query(None),
    streaming: bool | None = Query(None),
    start_at: datetime | None = Query(None),
    end_at: datetime | None = Query(None),
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

    parsed_gateway_key_id = _parse_optional_uuid(gateway_key_id)
    parsed_owner_id = _parse_optional_uuid(owner_id)
    parsed_institution_id = _parse_optional_uuid(institution_id)
    parsed_cohort_id = _parse_optional_uuid(cohort_id)
    if False in {parsed_gateway_key_id, parsed_owner_id, parsed_institution_id, parsed_cohort_id}:
        return HTMLResponse("Invalid filter.", status_code=400)

    async with _admin_activity_dashboard_service_scope(request) as service:
        rows = await service.list_usage(
            provider=provider,
            model=model,
            endpoint=endpoint,
            status=status,
            gateway_key_id=parsed_gateway_key_id,
            owner_id=parsed_owner_id,
            institution_id=parsed_institution_id,
            cohort_id=parsed_cohort_id,
            request_id=request_id,
            streaming=streaming,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
            offset=offset,
        )

    return templates.TemplateResponse(
        request,
        "usage/list.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "usage_rows": rows,
            "filters": {
                "provider": provider or "",
                "model": model or "",
                "endpoint": endpoint or "",
                "status": status or "",
                "gateway_key_id": gateway_key_id or "",
                "owner_id": owner_id or "",
                "institution_id": institution_id or "",
                "cohort_id": cohort_id or "",
                "request_id": request_id or "",
                "streaming": "" if streaming is None else str(streaming).lower(),
                "start_at": start_at.isoformat() if start_at is not None else "",
                "end_at": end_at.isoformat() if end_at is not None else "",
                "limit": limit,
                "offset": offset,
            },
            "export_max_rows": settings.ADMIN_USAGE_EXPORT_MAX_ROWS,
        },
    )


@router.get("/usage/{usage_ledger_id}", response_class=HTMLResponse)
async def admin_usage_detail(request: Request, usage_ledger_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_usage_ledger_id = uuid.UUID(usage_ledger_id)
    except ValueError:
        return HTMLResponse("Usage ledger row not found.", status_code=404)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_activity_dashboard_service_scope(request) as service:
            usage = await service.get_usage_detail(parsed_usage_ledger_id)
    except AdminActivityNotFoundError:
        return HTMLResponse("Usage ledger row not found.", status_code=404)

    return templates.TemplateResponse(
        request,
        "usage/detail.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "usage": usage,
        },
    )


@router.post("/usage/export.csv")
async def export_admin_usage_csv(
    request: Request,
    csrf_token: str = Form(""),
    confirm_export: str | None = Form(None),
    reason: str | None = Form(None),
    provider: str | None = Form(None),
    model: str | None = Form(None),
    endpoint: str | None = Form(None),
    status: str | None = Form(None),
    gateway_key_id: str | None = Form(None),
    owner_id: str | None = Form(None),
    institution_id: str | None = Form(None),
    cohort_id: str | None = Form(None),
    request_id: str | None = Form(None),
    streaming: str | None = Form(None),
    start_at: str | None = Form(None),
    end_at: str | None = Form(None),
    limit: str | None = Form(None),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context
    if not _is_checked(confirm_export):
        return HTMLResponse("Confirm the CSV export before continuing.", status_code=400)
    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return HTMLResponse("Enter an audit reason before exporting usage rows.", status_code=400)

    try:
        parsed_gateway_key_id = _parse_optional_admin_uuid(gateway_key_id, field_name="gateway_key_id")
        parsed_owner_id = _parse_optional_admin_uuid(owner_id, field_name="owner_id")
        parsed_institution_id = _parse_optional_admin_uuid(institution_id, field_name="institution_id")
        parsed_cohort_id = _parse_optional_admin_uuid(cohort_id, field_name="cohort_id")
        parsed_streaming = _parse_optional_admin_bool(streaming, field_name="streaming")
        parsed_start_at = _parse_admin_datetime(start_at)
        parsed_end_at = _parse_admin_datetime(end_at)
        if parsed_start_at is not None and parsed_end_at is not None and parsed_end_at < parsed_start_at:
            raise ValueError("end_at must be greater than or equal to start_at.")
        parsed_limit = _parse_admin_export_limit(
            limit,
            default=settings.ADMIN_USAGE_EXPORT_MAX_ROWS,
            maximum=settings.ADMIN_USAGE_EXPORT_MAX_ROWS,
        )
    except ValueError as exc:
        return HTMLResponse(str(exc), status_code=400)

    async with _admin_csv_export_service_scope(request) as service:
        result = await service.export_usage_csv(
            actor_admin_id=action_context.admin_user.id,
            reason=cleaned_reason,
            provider=provider,
            model=model,
            endpoint=endpoint,
            status=status,
            gateway_key_id=parsed_gateway_key_id,
            owner_id=parsed_owner_id,
            institution_id=parsed_institution_id,
            cohort_id=parsed_cohort_id,
            request_id=request_id,
            streaming=parsed_streaming,
            start_at=parsed_start_at,
            end_at=parsed_end_at,
            limit=parsed_limit,
            ip_address=_client_host(request),
            user_agent=request.headers.get("user-agent"),
            audit_request_id=request.headers.get(_settings(request).REQUEST_ID_HEADER),
        )
    return _csv_export_response(result)


@router.get("/audit", response_class=HTMLResponse)
async def list_admin_audit_logs(
    request: Request,
    actor_admin_id: str | None = Query(None),
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    target_id: str | None = Query(None),
    request_id: str | None = Query(None),
    start_at: datetime | None = Query(None),
    end_at: datetime | None = Query(None),
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

    parsed_actor_admin_id = _parse_optional_uuid(actor_admin_id)
    parsed_target_id = _parse_optional_uuid(target_id)
    if parsed_actor_admin_id is False or parsed_target_id is False:
        return HTMLResponse("Invalid filter.", status_code=400)

    async with _admin_activity_dashboard_service_scope(request) as service:
        rows = await service.list_audit_logs(
            actor_admin_id=parsed_actor_admin_id,
            action=action,
            target_type=target_type,
            target_id=parsed_target_id,
            request_id=request_id,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
            offset=offset,
        )

    return templates.TemplateResponse(
        request,
        "audit/list.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "audit_logs": rows,
            "filters": {
                "actor_admin_id": actor_admin_id or "",
                "action": action or "",
                "target_type": target_type or "",
                "target_id": target_id or "",
                "request_id": request_id or "",
                "start_at": start_at.isoformat() if start_at is not None else "",
                "end_at": end_at.isoformat() if end_at is not None else "",
                "limit": limit,
                "offset": offset,
            },
            "export_max_rows": settings.ADMIN_AUDIT_EXPORT_MAX_ROWS,
        },
    )


@router.post("/audit/export.csv")
async def export_admin_audit_csv(
    request: Request,
    csrf_token: str = Form(""),
    confirm_export: str | None = Form(None),
    reason: str | None = Form(None),
    actor_admin_id: str | None = Form(None),
    action: str | None = Form(None),
    target_type: str | None = Form(None),
    target_id: str | None = Form(None),
    request_id: str | None = Form(None),
    start_at: str | None = Form(None),
    end_at: str | None = Form(None),
    limit: str | None = Form(None),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context
    if not _is_checked(confirm_export):
        return HTMLResponse("Confirm the CSV export before continuing.", status_code=400)
    cleaned_reason = _clean_admin_reason(reason)
    if cleaned_reason is None:
        return HTMLResponse("Enter an audit reason before exporting audit rows.", status_code=400)

    try:
        parsed_actor_admin_id = _parse_optional_admin_uuid(actor_admin_id, field_name="actor_admin_id")
        parsed_target_id = _parse_optional_admin_uuid(target_id, field_name="target_id")
        parsed_start_at = _parse_admin_datetime(start_at)
        parsed_end_at = _parse_admin_datetime(end_at)
        if parsed_start_at is not None and parsed_end_at is not None and parsed_end_at < parsed_start_at:
            raise ValueError("end_at must be greater than or equal to start_at.")
        parsed_limit = _parse_admin_export_limit(
            limit,
            default=settings.ADMIN_AUDIT_EXPORT_MAX_ROWS,
            maximum=settings.ADMIN_AUDIT_EXPORT_MAX_ROWS,
        )
    except ValueError as exc:
        return HTMLResponse(str(exc), status_code=400)

    async with _admin_csv_export_service_scope(request) as service:
        result = await service.export_audit_csv(
            actor_admin_id=action_context.admin_user.id,
            reason=cleaned_reason,
            actor_filter_admin_id=parsed_actor_admin_id,
            action=action,
            target_type=target_type,
            target_id=parsed_target_id,
            request_id=request_id,
            start_at=parsed_start_at,
            end_at=parsed_end_at,
            limit=parsed_limit,
            ip_address=_client_host(request),
            user_agent=request.headers.get("user-agent"),
            audit_request_id=request.headers.get(_settings(request).REQUEST_ID_HEADER),
        )
    return _csv_export_response(result)


@router.get("/audit/{audit_log_id}", response_class=HTMLResponse)
async def admin_audit_detail(request: Request, audit_log_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_audit_log_id = uuid.UUID(audit_log_id)
    except ValueError:
        return HTMLResponse("Audit log row not found.", status_code=404)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_activity_dashboard_service_scope(request) as service:
            audit_log = await service.get_audit_detail(parsed_audit_log_id)
    except AdminActivityNotFoundError:
        return HTMLResponse("Audit log row not found.", status_code=404)

    return templates.TemplateResponse(
        request,
        "audit/detail.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "audit_log": audit_log,
        },
    )


@router.get("/email-deliveries", response_class=HTMLResponse)
async def list_admin_email_deliveries(
    request: Request,
    status: str | None = Query(None),
    owner_email: str | None = Query(None),
    gateway_key_id: str | None = Query(None),
    one_time_secret_id: str | None = Query(None),
    start_at: datetime | None = Query(None),
    end_at: datetime | None = Query(None),
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

    parsed_gateway_key_id = _parse_optional_uuid(gateway_key_id)
    parsed_one_time_secret_id = _parse_optional_uuid(one_time_secret_id)
    if parsed_gateway_key_id is False or parsed_one_time_secret_id is False:
        return HTMLResponse("Invalid filter.", status_code=400)

    async with _admin_activity_dashboard_service_scope(request) as service:
        rows = await service.list_email_deliveries(
            status=status,
            owner_email=owner_email,
            gateway_key_id=parsed_gateway_key_id,
            one_time_secret_id=parsed_one_time_secret_id,
            start_at=start_at,
            end_at=end_at,
            limit=limit,
            offset=offset,
        )

    return templates.TemplateResponse(
        request,
        "email_deliveries/list.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "email_deliveries": rows,
            "filters": {
                "status": status or "",
                "owner_email": owner_email or "",
                "gateway_key_id": gateway_key_id or "",
                "one_time_secret_id": one_time_secret_id or "",
                "start_at": start_at.isoformat() if start_at is not None else "",
                "end_at": end_at.isoformat() if end_at is not None else "",
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/email-deliveries/{email_delivery_id}", response_class=HTMLResponse)
async def admin_email_delivery_detail(request: Request, email_delivery_id: str) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_email_delivery_id = uuid.UUID(email_delivery_id)
    except ValueError:
        return HTMLResponse("Email delivery row not found.", status_code=404)

    page_context = await _admin_page_context(request)
    if isinstance(page_context, Response):
        return page_context
    context, csrf_token = page_context

    try:
        async with _admin_activity_dashboard_service_scope(request) as service:
            delivery = await service.get_email_delivery_detail(parsed_email_delivery_id)
    except AdminActivityNotFoundError:
        return HTMLResponse("Email delivery row not found.", status_code=404)

    return templates.TemplateResponse(
        request,
        "email_deliveries/detail.html",
        {
            "admin": context.admin_user,
            "csrf_token": csrf_token,
            "admin_status_message": _admin_status_message(request),
            "email_delivery": delivery,
        },
    )


@router.post("/email-deliveries/{email_delivery_id}/send-now", response_class=HTMLResponse)
async def send_admin_email_delivery_now(
    request: Request,
    email_delivery_id: str,
    csrf_token: str = Form(""),
    confirm_send: str | None = Form(None),
    reason: str | None = Form(None),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_email_delivery_id = uuid.UUID(email_delivery_id)
    except ValueError:
        return HTMLResponse("Email delivery row not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context
    if confirm_send != "true":
        return _redirect_to_admin_email_delivery(
            parsed_email_delivery_id,
            message="email_delivery_send_confirmation_required",
        )

    try:
        _validate_admin_email_delivery_preconditions(settings, "send-now")
        async with _admin_email_delivery_action_scope(request) as service:
            sendability = await service.get_key_email_delivery_sendability(parsed_email_delivery_id)
            if not sendability.can_send or sendability.one_time_secret_id is None:
                return _redirect_to_admin_email_delivery(parsed_email_delivery_id, message="email_delivery_not_sendable")
            result = await service.send_pending_key_email(
                one_time_secret_id=sendability.one_time_secret_id,
                email_delivery_id=parsed_email_delivery_id,
                actor_admin_id=action_context.admin_user.id,
                reason=_clean_admin_reason(reason),
            )
    except ValueError:
        return _redirect_to_admin_email_delivery(
            parsed_email_delivery_id,
            message="email_delivery_configuration_required",
        )
    except EmailError:
        return _redirect_to_admin_email_delivery(parsed_email_delivery_id, message="email_delivery_send_failed")

    if result.status == "sent":
        message = "email_delivery_sent"
    elif result.status == "ambiguous":
        message = "email_delivery_ambiguous"
    else:
        message = "email_delivery_send_failed"
    return _redirect_to_admin_email_delivery(parsed_email_delivery_id, message=message)


@router.post("/email-deliveries/{email_delivery_id}/enqueue", response_class=HTMLResponse)
async def enqueue_admin_email_delivery(
    request: Request,
    email_delivery_id: str,
    csrf_token: str = Form(""),
    confirm_enqueue: str | None = Form(None),
    reason: str | None = Form(None),
) -> Response:
    settings = _settings(request)
    if not settings.ENABLE_ADMIN_DASHBOARD:
        return _admin_not_found()

    try:
        parsed_email_delivery_id = uuid.UUID(email_delivery_id)
    except ValueError:
        return HTMLResponse("Email delivery row not found.", status_code=404)

    action_context = await _admin_action_context(request, csrf_token=csrf_token)
    if isinstance(action_context, Response):
        return action_context
    if confirm_enqueue != "true":
        return _redirect_to_admin_email_delivery(
            parsed_email_delivery_id,
            message="email_delivery_enqueue_confirmation_required",
        )

    try:
        _validate_admin_email_delivery_preconditions(settings, "enqueue")
        async with _admin_email_delivery_action_scope(request) as service:
            sendability = await service.get_key_email_delivery_sendability(parsed_email_delivery_id)
            if not sendability.can_send or sendability.one_time_secret_id is None:
                return _redirect_to_admin_email_delivery(parsed_email_delivery_id, message="email_delivery_not_sendable")
            one_time_secret_id = sendability.one_time_secret_id
    except ValueError:
        return _redirect_to_admin_email_delivery(
            parsed_email_delivery_id,
            message="email_delivery_configuration_required",
        )
    except EmailError:
        return _redirect_to_admin_email_delivery(parsed_email_delivery_id, message="email_delivery_not_sendable")

    try:
        _enqueue_admin_pending_key_email(
            one_time_secret_id=one_time_secret_id,
            email_delivery_id=parsed_email_delivery_id,
            actor_admin_id=action_context.admin_user.id,
        )
    except Exception:  # noqa: BLE001
        return _redirect_to_admin_email_delivery(parsed_email_delivery_id, message="email_delivery_send_failed")

    _ = reason
    return _redirect_to_admin_email_delivery(parsed_email_delivery_id, message="email_delivery_queued")


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


async def _admin_action_context(request: Request, *, csrf_token: str) -> AdminSessionContext | Response:
    settings = _settings(request)
    session_token = request.cookies.get(settings.ADMIN_SESSION_COOKIE_NAME)
    if not session_token:
        return RedirectResponse("/admin/login", status_code=303)

    try:
        async with _admin_service_scope(request) as service:
            context = await service.validate_admin_session(session_token=session_token)
            if not service.verify_session_csrf_token(context.admin_session, csrf_token):
                return HTMLResponse("Invalid CSRF token.", status_code=400)
            return context
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
async def _admin_key_management_service_scope(request: Request) -> AsyncIterator[KeyService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield KeyService(
                settings=_settings(request),
                gateway_keys_repository=GatewayKeysRepository(session),
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
            )


@asynccontextmanager
async def _admin_key_management_runtime_scope(
    request: Request,
) -> AsyncIterator[tuple[GatewayKeysRepository, KeyService]]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            keys_repository = GatewayKeysRepository(session)
            yield keys_repository, KeyService(
                settings=_settings(request),
                gateway_keys_repository=keys_repository,
                one_time_secrets_repository=OneTimeSecretsRepository(session),
                audit_repository=AuditRepository(session),
            )


@asynccontextmanager
async def _admin_key_creation_runtime_scope(
    request: Request,
) -> AsyncIterator[tuple[OwnersRepository, CohortsRepository, KeyService]]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield (
                OwnersRepository(session),
                CohortsRepository(session),
                KeyService(
                    settings=_settings(request),
                    gateway_keys_repository=GatewayKeysRepository(session),
                    one_time_secrets_repository=OneTimeSecretsRepository(session),
                    audit_repository=AuditRepository(session),
                ),
            )


@asynccontextmanager
async def _admin_key_email_delivery_runtime_scope(
    request: Request,
) -> AsyncIterator[tuple[OwnersRepository, CohortsRepository, KeyService, EmailDeliveryService]]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            settings = _settings(request)
            keys_repository = GatewayKeysRepository(session)
            one_time_secrets_repository = OneTimeSecretsRepository(session)
            owners_repository = OwnersRepository(session)
            audit_repository = AuditRepository(session)
            yield (
                owners_repository,
                CohortsRepository(session),
                KeyService(
                    settings=settings,
                    gateway_keys_repository=keys_repository,
                    one_time_secrets_repository=one_time_secrets_repository,
                    audit_repository=audit_repository,
                ),
                EmailDeliveryService(
                    settings=settings,
                    one_time_secrets_repository=one_time_secrets_repository,
                    email_deliveries_repository=EmailDeliveriesRepository(session),
                    gateway_keys_repository=keys_repository,
                    owners_repository=owners_repository,
                    audit_repository=audit_repository,
                    email_service=EmailService(settings),
                    session=session,
                ),
            )


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
async def _admin_institution_service_scope(request: Request) -> AsyncIterator[InstitutionService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield InstitutionService(
                institutions_repository=InstitutionsRepository(session),
                audit_repository=AuditRepository(session),
            )


@asynccontextmanager
async def _admin_cohort_service_scope(request: Request) -> AsyncIterator[CohortService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield CohortService(
                cohorts_repository=CohortsRepository(session),
                audit_repository=AuditRepository(session),
            )


@asynccontextmanager
async def _admin_owner_service_scope(request: Request) -> AsyncIterator[OwnerService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield OwnerService(
                owners_repository=OwnersRepository(session),
                institutions_repository=InstitutionsRepository(session),
                audit_repository=AuditRepository(session),
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


@asynccontextmanager
async def _admin_provider_config_service_scope(request: Request) -> AsyncIterator[ProviderConfigService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield ProviderConfigService(
                provider_configs_repository=ProviderConfigsRepository(session),
                audit_repository=AuditRepository(session),
            )


@asynccontextmanager
async def _admin_model_route_service_scope(request: Request) -> AsyncIterator[ModelRouteService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield ModelRouteService(
                model_routes_repository=ModelRoutesRepository(session),
                audit_repository=AuditRepository(session),
            )


@asynccontextmanager
async def _admin_pricing_rule_service_scope(request: Request) -> AsyncIterator[PricingRuleService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield PricingRuleService(
                pricing_rules_repository=PricingRulesRepository(session),
                audit_repository=AuditRepository(session),
            )


@asynccontextmanager
async def _admin_fx_rate_service_scope(request: Request) -> AsyncIterator[FxRateService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield FxRateService(
                fx_rates_repository=FxRatesRepository(session),
                audit_repository=AuditRepository(session),
            )


@asynccontextmanager
async def _admin_activity_dashboard_service_scope(request: Request) -> AsyncIterator[AdminActivityDashboardService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield AdminActivityDashboardService(
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
                email_deliveries_repository=EmailDeliveriesRepository(session),
            )


@asynccontextmanager
async def _admin_csv_export_service_scope(request: Request) -> AsyncIterator[AdminCsvExportService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            yield AdminCsvExportService(
                usage_ledger_repository=UsageLedgerRepository(session),
                audit_repository=AuditRepository(session),
            )


@asynccontextmanager
async def _admin_email_delivery_action_scope(request: Request) -> AsyncIterator[EmailDeliveryService]:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        settings = _settings(request)
        yield EmailDeliveryService(
            settings=settings,
            one_time_secrets_repository=OneTimeSecretsRepository(session),
            email_deliveries_repository=EmailDeliveriesRepository(session),
            gateway_keys_repository=GatewayKeysRepository(session),
            owners_repository=OwnersRepository(session),
            audit_repository=AuditRepository(session),
            email_service=EmailService(settings),
            session=session,
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


def _admin_status_message(request: Request) -> dict[str, str] | None:
    message_code = request.query_params.get("message")
    if message_code is None:
        return None
    message = _ADMIN_STATUS_MESSAGES.get(message_code)
    if message is None:
        return None
    level, text = message
    return {"level": level, "text": text}


def _redirect_to_admin_key(gateway_key_id: uuid.UUID, *, message: str) -> RedirectResponse:
    query = urlencode({"message": message})
    return RedirectResponse(f"/admin/keys/{gateway_key_id}?{query}", status_code=303)


def _redirect_to_admin_email_delivery(email_delivery_id: uuid.UUID, *, message: str) -> RedirectResponse:
    query = urlencode({"message": message})
    return RedirectResponse(f"/admin/email-deliveries/{email_delivery_id}?{query}", status_code=303)


def _redirect_to_admin_provider(provider_config_id: uuid.UUID, *, message: str) -> RedirectResponse:
    query = urlencode({"message": message})
    return RedirectResponse(f"/admin/providers/{provider_config_id}?{query}", status_code=303)


def _redirect_to_admin_route(route_id: uuid.UUID, *, message: str) -> RedirectResponse:
    query = urlencode({"message": message})
    return RedirectResponse(f"/admin/routes/{route_id}?{query}", status_code=303)


def _redirect_to_admin_pricing_rule(pricing_rule_id: uuid.UUID, *, message: str) -> RedirectResponse:
    query = urlencode({"message": message})
    return RedirectResponse(f"/admin/pricing/{pricing_rule_id}?{query}", status_code=303)


def _redirect_to_admin_fx_rate(fx_rate_id: uuid.UUID, *, message: str) -> RedirectResponse:
    query = urlencode({"message": message})
    return RedirectResponse(f"/admin/fx/{fx_rate_id}?{query}", status_code=303)


def _redirect_to_admin_owner(owner_id: uuid.UUID, *, message: str) -> RedirectResponse:
    query = urlencode({"message": message})
    return RedirectResponse(f"/admin/owners/{owner_id}?{query}", status_code=303)


def _redirect_to_admin_institution(institution_id: uuid.UUID, *, message: str) -> RedirectResponse:
    query = urlencode({"message": message})
    return RedirectResponse(f"/admin/institutions/{institution_id}?{query}", status_code=303)


def _redirect_to_admin_cohort(cohort_id: uuid.UUID, *, message: str) -> RedirectResponse:
    query = urlencode({"message": message})
    return RedirectResponse(f"/admin/cohorts/{cohort_id}?{query}", status_code=303)


def _set_no_store_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"


async def _load_key_create_form_options(request: Request) -> dict[str, object]:
    async with _admin_records_dashboard_service_scope(request) as service:
        owners = await service.list_owners(limit=200)
        cohorts = await service.list_cohorts(limit=200)
    return {"owners": owners, "cohorts": cohorts}


async def _load_record_form_institutions(request: Request) -> list[object]:
    async with _admin_records_dashboard_service_scope(request) as service:
        return await service.list_institutions(limit=200)


def _render_institution_form(
    request: Request,
    *,
    template_name: str,
    admin: object,
    csrf_token: str,
    form: dict[str, str],
    institution_id: uuid.UUID | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "institution_id": institution_id,
            "form": form,
            "error": error,
        },
        status_code=status_code,
    )


def _render_cohort_form(
    request: Request,
    *,
    template_name: str,
    admin: object,
    csrf_token: str,
    form: dict[str, str],
    cohort_id: uuid.UUID | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "cohort_id": cohort_id,
            "form": form,
            "error": error,
        },
        status_code=status_code,
    )


def _render_owner_form(
    request: Request,
    *,
    template_name: str,
    admin: object,
    csrf_token: str,
    form: dict[str, str],
    institutions: list[object],
    owner_id: uuid.UUID | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "owner_id": owner_id,
            "form": form,
            "institutions": institutions,
            "error": error,
        },
        status_code=status_code,
    )


def _render_key_create_form(
    request: Request,
    *,
    admin: object,
    csrf_token: str,
    options: dict[str, object],
    form: dict[str, str],
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "keys/create.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "owners": options["owners"],
            "cohorts": options["cohorts"],
            "form": form,
            "error": error,
        },
        status_code=status_code,
    )


def _render_key_import_form(
    request: Request,
    *,
    admin: object,
    csrf_token: str,
    form: dict[str, str],
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "keys/bulk_import.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "form": form,
            "error": error,
        },
        status_code=status_code,
    )


def _render_key_import_result(
    request: Request,
    *,
    admin: object,
    csrf_token: str,
    result: KeyImportExecutionResult,
    import_format: str,
    source_label: str,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    response = templates.TemplateResponse(
        request,
        "keys/bulk_import_result.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "result": result,
            "import_format": import_format,
            "source_label": source_label,
            "error": error,
        },
        status_code=status_code,
    )
    _set_no_store_headers(response)
    return response


def _default_key_create_form() -> dict[str, str]:
    return {
        "owner_id": "",
        "cohort_id": "",
        "valid_from": "",
        "valid_until": "",
        "valid_days": "",
        "cost_limit_eur": "",
        "token_limit_total": "",
        "request_limit_total": "",
        "allowed_models": "",
        "allowed_endpoints": "",
        "rate_limit_requests_per_minute": "",
        "rate_limit_tokens_per_minute": "",
        "rate_limit_concurrent_requests": "",
        "rate_limit_window_seconds": "",
        "email_delivery_mode": "none",
        "reason": "",
    }


def _default_key_import_form() -> dict[str, str]:
    return {
        "format": "auto",
        "import_text": "",
        "source_label": "",
    }


def _default_institution_form() -> dict[str, str]:
    return _institution_form_from_values(name="", country="", notes="", reason="")


def _institution_form_from_values(*, name: str, country: str, notes: str, reason: str) -> dict[str, str]:
    return {
        "name": name,
        "country": country,
        "notes": notes,
        "reason": reason,
    }


def _institution_form_from_detail(institution: object) -> dict[str, str]:
    return _institution_form_from_values(
        name=str(getattr(institution, "name", "") or ""),
        country=str(getattr(institution, "country", "") or ""),
        notes=str(getattr(institution, "notes", "") or ""),
        reason="",
    )


def _default_cohort_form() -> dict[str, str]:
    return _cohort_form_from_values(name="", description="", starts_at="", ends_at="", reason="")


def _cohort_form_from_values(
    *,
    name: str,
    description: str,
    starts_at: str,
    ends_at: str,
    reason: str,
) -> dict[str, str]:
    return {
        "name": name,
        "description": description,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "reason": reason,
    }


def _cohort_form_from_detail(cohort: object) -> dict[str, str]:
    starts_at = getattr(cohort, "starts_at", None)
    ends_at = getattr(cohort, "ends_at", None)
    return _cohort_form_from_values(
        name=str(getattr(cohort, "name", "") or ""),
        description=str(getattr(cohort, "description", "") or ""),
        starts_at=starts_at.isoformat() if starts_at is not None else "",
        ends_at=ends_at.isoformat() if ends_at is not None else "",
        reason="",
    )


def _default_owner_form() -> dict[str, str]:
    return _owner_form_from_values(
        name="",
        surname="",
        email="",
        institution_id="",
        external_id="",
        notes="",
        is_active="true",
        reason="",
    )


def _owner_form_from_values(
    *,
    name: str,
    surname: str,
    email: str,
    institution_id: str,
    external_id: str,
    notes: str,
    is_active: str,
    reason: str,
) -> dict[str, str]:
    return {
        "name": name,
        "surname": surname,
        "email": email,
        "institution_id": institution_id,
        "external_id": external_id,
        "notes": notes,
        "is_active": is_active,
        "reason": reason,
    }


def _owner_form_from_detail(owner: object) -> dict[str, str]:
    institution_id = getattr(owner, "institution_id", None)
    return _owner_form_from_values(
        name=str(getattr(owner, "name", "") or ""),
        surname=str(getattr(owner, "surname", "") or ""),
        email=str(getattr(owner, "email", "") or ""),
        institution_id=str(institution_id) if institution_id is not None else "",
        external_id=str(getattr(owner, "external_id", "") or ""),
        notes=str(getattr(owner, "notes", "") or ""),
        is_active="true" if getattr(owner, "is_active", False) else "",
        reason="",
    )


def _render_provider_config_form(
    request: Request,
    *,
    template_name: str,
    admin: object,
    csrf_token: str,
    form: dict[str, str],
    provider_config_id: uuid.UUID | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "provider_config_id": provider_config_id,
            "form": form,
            "error": error,
        },
        status_code=status_code,
    )


def _render_pricing_import_form(
    request: Request,
    *,
    admin: object,
    csrf_token: str,
    form: dict[str, str] | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "pricing/import.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "form": form or {"format": "auto", "import_text": "", "source_label": "", "reason": ""},
            "error": error,
            "settings": _settings(request),
        },
        status_code=status_code,
    )


def _render_pricing_import_result(
    request: Request,
    *,
    admin: object,
    csrf_token: str,
    result: PricingImportExecutionResult,
    import_format: str,
    source_label: str,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "pricing/import_result.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "result": result,
            "import_format": import_format,
            "source_label": source_label,
            "error": error,
        },
        status_code=status_code,
    )


def _default_provider_config_form() -> dict[str, str]:
    return {
        "provider": "",
        "display_name": "",
        "kind": "openai_compatible",
        "base_url": "",
        "api_key_env_var": "",
        "enabled": "true",
        "timeout_seconds": "300",
        "max_retries": "2",
        "notes": "",
        "reason": "",
    }


def _provider_config_form_from_detail(provider: object) -> dict[str, str]:
    return _provider_config_form_from_values(
        provider=str(getattr(provider, "provider")),
        display_name=str(getattr(provider, "display_name")),
        kind=str(getattr(provider, "kind")),
        base_url=str(getattr(provider, "base_url")),
        api_key_env_var=str(getattr(provider, "api_key_env_var")),
        enabled="true" if bool(getattr(provider, "enabled")) else "",
        timeout_seconds=str(getattr(provider, "timeout_seconds")),
        max_retries=str(getattr(provider, "max_retries")),
        notes=str(getattr(provider, "notes") or ""),
        reason="",
    )


def _provider_config_form_from_values(
    *,
    provider: str,
    display_name: str,
    kind: str,
    base_url: str,
    api_key_env_var: str,
    enabled: str,
    timeout_seconds: str,
    max_retries: str,
    notes: str,
    reason: str,
) -> dict[str, str]:
    return {
        "provider": provider,
        "display_name": display_name,
        "kind": kind,
        "base_url": base_url,
        "api_key_env_var": api_key_env_var,
        "enabled": enabled,
        "timeout_seconds": timeout_seconds,
        "max_retries": max_retries,
        "notes": notes,
        "reason": reason,
    }


async def _load_route_provider_choices(request: Request) -> list[object]:
    return await _load_catalog_provider_choices(request)


async def _load_catalog_provider_choices(request: Request) -> list[object]:
    async with _admin_catalog_dashboard_service_scope(request) as service:
        return await service.list_providers(limit=200)


def _render_route_form(
    request: Request,
    *,
    template_name: str,
    admin: object,
    csrf_token: str,
    form: dict[str, str],
    provider_choices: list[object],
    route_id: uuid.UUID | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "route_id": route_id,
            "form": form,
            "provider_choices": provider_choices,
            "error": error,
        },
        status_code=status_code,
    )


def _render_route_import_form(
    request: Request,
    *,
    admin: object,
    csrf_token: str,
    form: dict[str, str] | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "routes/import.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "form": form or {"format": "auto", "import_text": "", "source_label": "", "reason": ""},
            "error": error,
            "settings": _settings(request),
        },
        status_code=status_code,
    )


def _render_route_import_result(
    request: Request,
    *,
    admin: object,
    csrf_token: str,
    result: RouteImportExecutionResult,
    import_format: str,
    source_label: str,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "routes/import_result.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "result": result,
            "import_format": import_format,
            "source_label": source_label,
            "error": error,
        },
        status_code=status_code,
    )


def _render_fx_import_form(
    request: Request,
    *,
    admin: object,
    csrf_token: str,
    form: dict[str, str] | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "fx/import.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "form": form or {"format": "auto", "import_text": "", "source_label": "", "reason": ""},
            "error": error,
            "settings": _settings(request),
        },
        status_code=status_code,
    )


def _render_fx_import_result(
    request: Request,
    *,
    admin: object,
    csrf_token: str,
    result: FxImportExecutionResult,
    import_format: str,
    source_label: str,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "fx/import_result.html",
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "result": result,
            "import_format": import_format,
            "source_label": source_label,
            "error": error,
        },
        status_code=status_code,
    )


def _default_route_form() -> dict[str, str]:
    return {
        "requested_model": "",
        "match_type": "exact",
        "endpoint": CHAT_COMPLETIONS_ENDPOINT,
        "provider": "",
        "upstream_model": "",
        "priority": "100",
        "enabled": "true",
        "visible_in_models": "true",
        "supports_streaming": "true",
        "capabilities": "",
        "notes": "",
        "reason": "",
    }


def _route_form_from_detail(route: object) -> dict[str, str]:
    capabilities = getattr(route, "capabilities", {}) or {}
    return _route_form_from_values(
        requested_model=str(getattr(route, "requested_model")),
        match_type=str(getattr(route, "match_type")),
        endpoint=str(getattr(route, "endpoint")),
        provider=str(getattr(route, "provider")),
        upstream_model=str(getattr(route, "upstream_model")),
        priority=str(getattr(route, "priority")),
        enabled="true" if bool(getattr(route, "enabled")) else "",
        visible_in_models="true" if bool(getattr(route, "visible_in_models")) else "",
        supports_streaming="true" if bool(getattr(route, "supports_streaming")) else "",
        capabilities=json.dumps(capabilities, sort_keys=True) if capabilities else "",
        notes=str(getattr(route, "notes") or ""),
        reason="",
    )


def _route_form_from_values(
    *,
    requested_model: str,
    match_type: str,
    endpoint: str,
    provider: str,
    upstream_model: str,
    priority: str,
    enabled: str,
    visible_in_models: str,
    supports_streaming: str,
    capabilities: str,
    notes: str,
    reason: str,
) -> dict[str, str]:
    return {
        "requested_model": requested_model,
        "match_type": match_type,
        "endpoint": endpoint,
        "provider": provider,
        "upstream_model": upstream_model,
        "priority": priority,
        "enabled": enabled,
        "visible_in_models": visible_in_models,
        "supports_streaming": supports_streaming,
        "capabilities": capabilities,
        "notes": notes,
        "reason": reason,
    }


def _parse_model_route_form(
    form: dict[str, str],
    *,
    provider_choices: list[object],
    require_reason: bool,
) -> dict[str, object]:
    requested_model = _parse_route_text(form.get("requested_model"), field_name="Requested model")
    match_type = (form.get("match_type") or "exact").strip()
    if match_type not in {"exact", "prefix", "glob"}:
        raise ValueError("Match type must be exact, prefix, or glob.")
    endpoint = _parse_route_endpoint(form.get("endpoint"))
    provider = _parse_provider_slug(form.get("provider"))
    known_providers = {str(getattr(choice, "provider")) for choice in provider_choices}
    if provider not in known_providers:
        raise ValueError("Select a known provider config.")
    upstream_model = _clean_admin_reason(form.get("upstream_model")) or requested_model
    priority = _parse_required_non_negative_admin_int(form.get("priority"), field_name="priority")
    capabilities = _parse_route_capabilities(form.get("capabilities"))
    reason = _clean_admin_reason(form.get("reason"))
    if require_reason and reason is None:
        raise ValueError(_ADMIN_STATUS_MESSAGES["model_route_reason_required"][1])

    return {
        "requested_model": requested_model,
        "match_type": match_type,
        "endpoint": endpoint,
        "provider": provider,
        "upstream_model": upstream_model,
        "priority": priority,
        "enabled": _is_checked(form.get("enabled")),
        "visible_in_models": _is_checked(form.get("visible_in_models")),
        "supports_streaming": _is_checked(form.get("supports_streaming")),
        "capabilities": capabilities,
        "notes": _clean_admin_reason(form.get("notes")),
        "reason": reason,
    }


def _parse_route_text(value: str | None, *, field_name: str) -> str:
    cleaned = _clean_admin_reason(value)
    if cleaned is None:
        raise ValueError(f"{field_name} is required.")
    if any(ch.isspace() for ch in cleaned):
        raise ValueError(f"{field_name} must not contain whitespace.")
    if _looks_like_provider_secret_value(cleaned):
        raise ValueError(f"{field_name} must not contain secret-looking values.")
    return cleaned


def _parse_route_endpoint(value: str | None) -> str:
    endpoint = _parse_route_text(value, field_name="Endpoint")
    if endpoint == "chat.completions":
        return CHAT_COMPLETIONS_ENDPOINT
    if not endpoint.startswith("/v1/"):
        raise ValueError("Endpoint must be a /v1 path or chat.completions.")
    parsed = urlparse(endpoint)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Endpoint must be a safe path without query parameters.")
    return endpoint


def _parse_route_capabilities(value: str | None) -> dict[str, object]:
    raw = (value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Capabilities must be a JSON object.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Capabilities must be a JSON object.")
    if _route_metadata_contains_secret(parsed):
        raise ValueError("Route metadata must not contain secret-looking values.")
    return parsed


def _route_metadata_contains_secret(value: object) -> bool:
    secret_key_names = {
        "api_key",
        "api_key_value",
        "authorization",
        "encrypted_payload",
        "nonce",
        "password",
        "password_hash",
        "provider_key",
        "secret",
        "session_token",
        "token",
        "token_hash",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).strip().lower()
            if key_text in secret_key_names or "secret" in key_text:
                return True
            if _route_metadata_contains_secret(item):
                return True
        return False
    if isinstance(value, list):
        return any(_route_metadata_contains_secret(item) for item in value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        return _looks_like_provider_secret_value(value) or lowered.startswith(("bearer ", "sk-"))
    return False


def _render_fx_rate_form(
    request: Request,
    *,
    template_name: str,
    admin: object,
    csrf_token: str,
    form: dict[str, str],
    fx_rate_id: uuid.UUID | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "fx_rate_id": fx_rate_id,
            "form": form,
            "error": error,
        },
        status_code=status_code,
    )


def _default_fx_rate_form() -> dict[str, str]:
    return {
        "base_currency": "",
        "quote_currency": "EUR",
        "rate": "",
        "valid_from": "",
        "valid_until": "",
        "source": "",
        "reason": "",
    }


def _fx_rate_form_from_detail(fx_rate: object) -> dict[str, str]:
    valid_from = getattr(fx_rate, "valid_from")
    valid_until = getattr(fx_rate, "valid_until")
    return _fx_rate_form_from_values(
        base_currency=str(getattr(fx_rate, "base_currency")),
        quote_currency=str(getattr(fx_rate, "quote_currency")),
        rate=_decimal_form_value(getattr(fx_rate, "rate")),
        valid_from=valid_from.isoformat() if isinstance(valid_from, datetime) else "",
        valid_until=valid_until.isoformat() if isinstance(valid_until, datetime) else "",
        source=str(getattr(fx_rate, "source") or ""),
        reason="",
    )


def _fx_rate_form_from_values(
    *,
    base_currency: str,
    quote_currency: str,
    rate: str,
    valid_from: str,
    valid_until: str,
    source: str,
    reason: str,
) -> dict[str, str]:
    return {
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "rate": rate,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "source": source,
        "reason": reason,
    }


def _parse_fx_rate_form(form: dict[str, str], *, require_reason: bool) -> dict[str, object]:
    base_currency = _parse_pricing_currency(form.get("base_currency"))
    quote_currency = _parse_pricing_currency(form.get("quote_currency"))
    if base_currency == quote_currency:
        raise ValueError("base_currency and quote_currency must differ.")
    valid_from = _parse_admin_datetime(form.get("valid_from")) or datetime.now(UTC)
    valid_until = _parse_admin_datetime(form.get("valid_until"))
    if valid_until is not None and valid_until <= valid_from:
        raise ValueError("valid_until must be after valid_from.")
    source = _clean_admin_reason(form.get("source"))
    if source is not None and _looks_like_fx_secret_value(source):
        raise ValueError("Source must not contain secret-looking values.")
    reason = _clean_admin_reason(form.get("reason"))
    if require_reason and reason is None:
        raise ValueError(_ADMIN_STATUS_MESSAGES["fx_rate_reason_required"][1])
    return {
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "rate": _parse_required_positive_admin_decimal(form.get("rate"), field_name="rate"),
        "valid_from": valid_from,
        "valid_until": valid_until,
        "source": source,
        "reason": reason,
    }


def _parse_required_positive_admin_decimal(value: str | None, *, field_name: str) -> Decimal:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    try:
        parsed = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a decimal string.") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{field_name} must be positive.")
    return parsed


def _looks_like_fx_secret_value(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith(("bearer ", "sk-", "sk_", "sk-or-"))


def _render_pricing_rule_form(
    request: Request,
    *,
    template_name: str,
    admin: object,
    csrf_token: str,
    form: dict[str, str],
    provider_choices: list[object],
    pricing_rule_id: uuid.UUID | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "admin": admin,
            "csrf_token": csrf_token,
            "pricing_rule_id": pricing_rule_id,
            "form": form,
            "provider_choices": provider_choices,
            "error": error,
        },
        status_code=status_code,
    )


def _default_pricing_rule_form() -> dict[str, str]:
    return {
        "provider": "",
        "upstream_model": "",
        "endpoint": CHAT_COMPLETIONS_ENDPOINT,
        "currency": "EUR",
        "input_price_per_1m": "",
        "cached_input_price_per_1m": "",
        "output_price_per_1m": "",
        "reasoning_price_per_1m": "",
        "request_price": "",
        "pricing_metadata": "",
        "valid_from": "",
        "valid_until": "",
        "enabled": "true",
        "source_url": "",
        "notes": "",
        "reason": "",
    }


def _pricing_rule_form_from_detail(pricing_rule: object) -> dict[str, str]:
    metadata = getattr(pricing_rule, "pricing_metadata", {}) or {}
    valid_from = getattr(pricing_rule, "valid_from")
    valid_until = getattr(pricing_rule, "valid_until")
    return _pricing_rule_form_from_values(
        provider=str(getattr(pricing_rule, "provider")),
        upstream_model=str(getattr(pricing_rule, "upstream_model")),
        endpoint=str(getattr(pricing_rule, "endpoint")),
        currency=str(getattr(pricing_rule, "currency")),
        input_price_per_1m=_decimal_form_value(getattr(pricing_rule, "input_price_per_1m")),
        cached_input_price_per_1m=_decimal_form_value(getattr(pricing_rule, "cached_input_price_per_1m")),
        output_price_per_1m=_decimal_form_value(getattr(pricing_rule, "output_price_per_1m")),
        reasoning_price_per_1m=_decimal_form_value(getattr(pricing_rule, "reasoning_price_per_1m")),
        request_price=_decimal_form_value(getattr(pricing_rule, "request_price")),
        pricing_metadata=json.dumps(metadata, sort_keys=True) if metadata else "",
        valid_from=valid_from.isoformat() if isinstance(valid_from, datetime) else "",
        valid_until=valid_until.isoformat() if isinstance(valid_until, datetime) else "",
        enabled="true" if bool(getattr(pricing_rule, "enabled")) else "",
        source_url=str(getattr(pricing_rule, "source_url") or ""),
        notes=str(getattr(pricing_rule, "notes") or ""),
        reason="",
    )


def _pricing_rule_form_from_values(
    *,
    provider: str,
    upstream_model: str,
    endpoint: str,
    currency: str,
    input_price_per_1m: str,
    cached_input_price_per_1m: str,
    output_price_per_1m: str,
    reasoning_price_per_1m: str,
    request_price: str,
    pricing_metadata: str,
    valid_from: str,
    valid_until: str,
    enabled: str,
    source_url: str,
    notes: str,
    reason: str,
) -> dict[str, str]:
    return {
        "provider": provider,
        "upstream_model": upstream_model,
        "endpoint": endpoint,
        "currency": currency,
        "input_price_per_1m": input_price_per_1m,
        "cached_input_price_per_1m": cached_input_price_per_1m,
        "output_price_per_1m": output_price_per_1m,
        "reasoning_price_per_1m": reasoning_price_per_1m,
        "request_price": request_price,
        "pricing_metadata": pricing_metadata,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "enabled": enabled,
        "source_url": source_url,
        "notes": notes,
        "reason": reason,
    }


def _parse_pricing_rule_form(
    form: dict[str, str],
    *,
    provider_choices: list[object],
    require_reason: bool,
) -> dict[str, object]:
    provider = _parse_provider_slug(form.get("provider"))
    known_providers = {str(getattr(choice, "provider")) for choice in provider_choices}
    if provider not in known_providers:
        raise ValueError("Select a known provider config.")
    upstream_model = _parse_pricing_text(form.get("upstream_model"), field_name="Model")
    endpoint = _parse_route_endpoint(form.get("endpoint"))
    currency = _parse_pricing_currency(form.get("currency"))
    valid_from = _parse_admin_datetime(form.get("valid_from")) or datetime.now(UTC)
    valid_until = _parse_admin_datetime(form.get("valid_until"))
    if valid_until is not None and valid_until <= valid_from:
        raise ValueError("valid_until must be after valid_from.")
    pricing_metadata = _parse_pricing_metadata(form.get("pricing_metadata"))
    reason = _clean_admin_reason(form.get("reason"))
    if require_reason and reason is None:
        raise ValueError(_ADMIN_STATUS_MESSAGES["pricing_rule_reason_required"][1])

    return {
        "provider": provider,
        "upstream_model": upstream_model,
        "endpoint": endpoint,
        "currency": currency,
        "input_price_per_1m": _parse_required_non_negative_admin_decimal(
            form.get("input_price_per_1m"),
            field_name="input_price_per_1m",
        ),
        "cached_input_price_per_1m": _parse_optional_non_negative_admin_decimal(
            form.get("cached_input_price_per_1m"),
            field_name="cached_input_price_per_1m",
        ),
        "output_price_per_1m": _parse_required_non_negative_admin_decimal(
            form.get("output_price_per_1m"),
            field_name="output_price_per_1m",
        ),
        "reasoning_price_per_1m": _parse_optional_non_negative_admin_decimal(
            form.get("reasoning_price_per_1m"),
            field_name="reasoning_price_per_1m",
        ),
        "request_price": _parse_optional_non_negative_admin_decimal(
            form.get("request_price"),
            field_name="request_price",
        ),
        "pricing_metadata": pricing_metadata,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "enabled": _is_checked(form.get("enabled")),
        "source_url": _parse_pricing_source_url(form.get("source_url")),
        "notes": _clean_admin_reason(form.get("notes")),
        "reason": reason,
    }


def _parse_pricing_text(value: str | None, *, field_name: str) -> str:
    cleaned = _clean_admin_reason(value)
    if cleaned is None:
        raise ValueError(f"{field_name} is required.")
    if _looks_like_provider_secret_value(cleaned):
        raise ValueError(f"{field_name} must not contain secret-looking values.")
    return cleaned


def _parse_pricing_currency(value: str | None) -> str:
    currency = (value or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("Currency must be a safe 3-letter code.")
    return currency


def _parse_pricing_source_url(value: str | None) -> str | None:
    source_url = _clean_admin_reason(value)
    if source_url is None:
        return None
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Source URL must be an absolute http or https URL.")
    if parsed.username or parsed.password:
        raise ValueError("Source URL must not contain credentials.")
    if _looks_like_provider_secret_value(source_url):
        raise ValueError("Source URL must not contain secret-looking values.")
    return source_url


def _parse_pricing_metadata(value: str | None) -> dict[str, object]:
    raw = (value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Pricing metadata must be a JSON object.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Pricing metadata must be a JSON object.")
    if _route_metadata_contains_secret(parsed):
        raise ValueError("Pricing metadata must not contain secret-looking values.")
    return parsed


async def _read_pricing_import_input(
    *,
    import_file: UploadFile | None,
    import_text: str,
    max_bytes: int,
) -> tuple[str | None, str]:
    text_supplied = bool(import_text.strip())
    file_supplied = import_file is not None and bool(import_file.filename)
    if text_supplied and file_supplied:
        raise ValueError("Use either a file upload or pasted content, not both.")
    if not text_supplied and not file_supplied:
        raise ValueError("Paste pricing content or upload a pricing file.")

    if text_supplied:
        encoded = import_text.encode("utf-8")
        if len(encoded) > max_bytes:
            raise ValueError(f"Pricing import content must be at most {max_bytes} bytes.")
        return None, import_text

    assert import_file is not None
    content = await import_file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"Pricing import content must be at most {max_bytes} bytes.")
    if not content:
        raise ValueError("Pricing import file is empty.")
    try:
        return import_file.filename, content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Pricing import content must be UTF-8 text.") from exc


async def _read_route_import_input(
    *,
    import_file: UploadFile | None,
    import_text: str,
    max_bytes: int,
) -> tuple[str | None, str]:
    text_supplied = bool(import_text.strip())
    file_supplied = import_file is not None and bool(import_file.filename)
    if text_supplied and file_supplied:
        raise ValueError("Use either a file upload or pasted content, not both.")
    if not text_supplied and not file_supplied:
        raise ValueError("Paste route content or upload a route file.")

    if text_supplied:
        encoded = import_text.encode("utf-8")
        if len(encoded) > max_bytes:
            raise ValueError(f"Route import content must be at most {max_bytes} bytes.")
        return None, import_text

    assert import_file is not None
    content = await import_file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"Route import content must be at most {max_bytes} bytes.")
    if not content:
        raise ValueError("Route import file is empty.")
    try:
        return import_file.filename, content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Route import content must be UTF-8 text.") from exc


async def _read_fx_import_input(
    *,
    import_file: UploadFile | None,
    import_text: str,
    max_bytes: int,
) -> tuple[str | None, str]:
    text_supplied = bool(import_text.strip())
    file_supplied = import_file is not None and bool(import_file.filename)
    if text_supplied and file_supplied:
        raise ValueError("Use either a file upload or pasted content, not both.")
    if not text_supplied and not file_supplied:
        raise ValueError("Paste FX content or upload an FX file.")

    if text_supplied:
        encoded = import_text.encode("utf-8")
        if len(encoded) > max_bytes:
            raise ValueError(f"FX import content must be at most {max_bytes} bytes.")
        return None, import_text

    assert import_file is not None
    content = await import_file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"FX import content must be at most {max_bytes} bytes.")
    if not content:
        raise ValueError("FX import file is empty.")
    try:
        return import_file.filename, content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("FX import content must be UTF-8 text.") from exc


async def _read_key_import_input(
    *,
    import_file: UploadFile | None,
    import_text: str,
    max_bytes: int,
) -> tuple[str | None, str]:
    text_supplied = bool(import_text.strip())
    file_supplied = import_file is not None and bool(import_file.filename)
    if text_supplied and file_supplied:
        raise ValueError("Use either a file upload or pasted content, not both.")
    if not text_supplied and not file_supplied:
        raise ValueError("Paste key import content or upload a key import file.")

    if text_supplied:
        encoded = import_text.encode("utf-8")
        if len(encoded) > max_bytes:
            raise ValueError(f"Key import content must be at most {max_bytes} bytes.")
        return None, import_text

    assert import_file is not None
    content = await import_file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"Key import content must be at most {max_bytes} bytes.")
    if not content:
        raise ValueError("Key import file is empty.")
    try:
        return import_file.filename, content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Key import content must be UTF-8 text.") from exc


def _parse_optional_import_source_label(value: str | None) -> str | None:
    source_label = _clean_admin_reason(value)
    if source_label is None:
        return None
    lowered = source_label.lower()
    if lowered.startswith(("bearer ", "sk-", "sk_", "sk-or-")) or redact_text(source_label) != source_label:
        raise ValueError("Source label must not contain secret-looking values.")
    return source_label


async def _build_route_import_preview(
    request: Request,
    raw_rows: list[dict[str, object]],
    *,
    max_rows: int,
) -> RouteImportPreview:
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            providers = await ProviderConfigsRepository(session).list_provider_configs(limit=1000)
            preview = validate_route_import_rows(
                raw_rows,
                provider_configs=provider_refs_from_rows(providers),
                max_rows=max_rows,
            )
            valid_rows = [row for row in preview.rows if row.status == "valid"]
            if not valid_rows:
                return preview

            route_repository = ModelRoutesRepository(session)
            existing_by_row: dict[int, list[object]] = {}
            for row in valid_rows:
                if not row.requested_model or not row.match_type or not row.endpoint:
                    continue
                existing_by_row[row.row_number] = await route_repository.list_model_routes(
                    endpoint=row.endpoint,
                    limit=1000,
                )
    return classify_route_import_preview(preview, existing_routes_by_row=existing_by_row)


async def _build_key_import_preview(
    request: Request,
    raw_rows: list[dict[str, object]],
    *,
    max_rows: int,
) -> KeyImportPreview:
    settings = _settings(request)
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            owners = await OwnersRepository(session).list_owners_for_admin(limit=1000)
            cohorts = await CohortsRepository(session).list_cohorts(limit=1000)

    owner_refs = [
        KeyImportOwnerRef(
            id=owner.id,
            email=str(owner.email).strip().lower(),
            display_name=f"{owner.name} {owner.surname}".strip(),
            institution_id=owner.institution_id,
            institution_name=getattr(getattr(owner, "institution", None), "name", None),
        )
        for owner in owners
    ]
    context = KeyImportReadOnlyContext(
        owners_by_id={owner.id: owner for owner in owner_refs},
        owners_by_email={owner.email.lower(): owner for owner in owner_refs},
        cohorts_by_id={
            cohort.id: KeyImportCohortRef(id=cohort.id, name=cohort.name)
            for cohort in cohorts
        },
        email_delivery_enabled=settings.ENABLE_EMAIL_DELIVERY,
        smtp_configured=bool(settings.SMTP_HOST and settings.SMTP_FROM),
        celery_configured=bool(settings.get_celery_broker_url()),
    )
    return validate_key_import_rows(
        raw_rows,
        context=context,
        max_rows=max_rows,
    )


async def _classify_pricing_import_preview(
    request: Request,
    preview: PricingImportPreview,
) -> PricingImportPreview:
    valid_rows = [row for row in preview.rows if row.status == "valid"]
    if not valid_rows:
        return preview

    existing_by_row: dict[int, list[object]] = {}
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            repository = PricingRulesRepository(session)
            for row in valid_rows:
                if not row.provider or not row.model or not row.endpoint:
                    continue
                existing_by_row[row.row_number] = await repository.list_pricing_rules(
                    provider=row.provider,
                    upstream_model=row.model,
                    endpoint=row.endpoint,
                    limit=200,
                )
    return classify_pricing_import_preview(preview, existing_rules_by_row=existing_by_row)


async def _classify_fx_import_preview(
    request: Request,
    preview: FxImportPreview,
) -> FxImportPreview:
    valid_rows = [row for row in preview.rows if row.status == "valid"]
    if not valid_rows:
        return preview

    existing_by_row: dict[int, list[object]] = {}
    session_factory = get_sessionmaker_from_app(request)
    async with session_factory() as session:
        async with session.begin():
            repository = FxRatesRepository(session)
            for row in valid_rows:
                if not row.base_currency or not row.quote_currency:
                    continue
                existing_by_row[row.row_number] = await repository.list_rates_for_pair(
                    base_currency=row.base_currency,
                    quote_currency=row.quote_currency,
                    limit=200,
                )
    return classify_fx_import_preview(preview, existing_rates_by_row=existing_by_row)


def _blocked_pricing_import_result(plan: PricingImportExecutionPlan) -> PricingImportExecutionResult:
    return PricingImportExecutionResult(
        total_rows=plan.total_rows,
        created_count=0,
        updated_count=0,
        skipped_count=sum(1 for row in plan.rows if row.action == "skipped"),
        error_count=plan.blocked_count,
        rows=plan.rows,
        audit_summary="No pricing rows were written.",
    )


def _blocked_route_import_result(plan: RouteImportExecutionPlan) -> RouteImportExecutionResult:
    return RouteImportExecutionResult(
        total_rows=plan.total_rows,
        created_count=0,
        updated_count=0,
        skipped_count=sum(1 for row in plan.rows if row.action == "skipped"),
        error_count=plan.blocked_count,
        rows=plan.rows,
        audit_summary="No model route rows were written.",
    )


def _blocked_fx_import_result(plan: FxImportExecutionPlan) -> FxImportExecutionResult:
    return FxImportExecutionResult(
        total_rows=plan.total_rows,
        created_count=0,
        updated_count=0,
        skipped_count=sum(1 for row in plan.rows if row.action == "skipped"),
        error_count=plan.blocked_count,
        rows=plan.rows,
        audit_summary="No FX rows were written.",
    )


def _decimal_form_value(value: object) -> str:
    return str(value) if isinstance(value, Decimal) else ""


def _parse_provider_config_form(
    form: dict[str, str],
    *,
    require_reason: bool,
    require_base_url: bool = False,
) -> dict[str, object]:
    provider = _parse_provider_slug(form.get("provider"))
    display_name = _clean_admin_reason(form.get("display_name")) or provider
    kind = (form.get("kind") or "openai_compatible").strip()
    if kind != "openai_compatible":
        raise ValueError("Provider kind must be openai_compatible.")
    base_url = _clean_admin_reason(form.get("base_url"))
    if require_base_url and base_url is None:
        raise ValueError("Base URL is required.")
    if base_url is not None:
        _validate_admin_base_url(base_url)
    api_key_env_var = _parse_provider_api_key_env_var(form.get("api_key_env_var"))
    timeout_seconds = _parse_required_positive_admin_int(form.get("timeout_seconds"), field_name="timeout_seconds")
    max_retries = _parse_required_non_negative_admin_int(form.get("max_retries"), field_name="max_retries")
    reason = _clean_admin_reason(form.get("reason"))
    if require_reason and reason is None:
        raise ValueError(_ADMIN_STATUS_MESSAGES["provider_config_reason_required"][1])

    return {
        "provider": provider,
        "display_name": display_name,
        "kind": kind,
        "base_url": base_url,
        "api_key_env_var": api_key_env_var,
        "enabled": _is_checked(form.get("enabled")),
        "timeout_seconds": timeout_seconds,
        "max_retries": max_retries,
        "notes": _clean_admin_reason(form.get("notes")),
        "reason": reason,
    }


def _parse_key_create_form(
    form: dict[str, str],
    *,
    actor_admin_id: uuid.UUID,
) -> CreateGatewayKeyInput:
    owner_id = _parse_required_admin_uuid(form.get("owner_id"), field_name="owner_id")
    cohort_id = _parse_optional_admin_uuid(form.get("cohort_id"), field_name="cohort_id")
    cleaned_reason = _clean_admin_reason(form.get("reason"))
    if cleaned_reason is None:
        raise ValueError("Enter an audit reason before creating a key.")

    try:
        valid_from = _parse_admin_datetime(form.get("valid_from")) or datetime.now(UTC)
        valid_until = _parse_create_valid_until(
            valid_from=valid_from,
            valid_until=form.get("valid_until"),
            valid_days=form.get("valid_days"),
        )
    except ValueError as exc:
        raise ValueError("Enter a valid key validity window.") from exc
    if valid_until <= valid_from:
        raise ValueError("Enter a valid key validity window.")

    try:
        _, cost_limit_eur = _parse_optional_admin_decimal(form.get("cost_limit_eur"))
        _, token_limit_total = _parse_optional_admin_int(form.get("token_limit_total"))
        _, request_limit_total = _parse_optional_admin_int(form.get("request_limit_total"))
        rate_limit_policy = _parse_admin_rate_limit_policy(form)
    except ValueError as exc:
        raise ValueError("Enter valid positive quota and rate-limit values.") from exc

    return CreateGatewayKeyInput(
        owner_id=owner_id,
        cohort_id=cohort_id,
        valid_from=valid_from,
        valid_until=valid_until,
        created_by_admin_id=actor_admin_id,
        cost_limit_eur=cost_limit_eur,
        token_limit_total=token_limit_total,
        request_limit_total=request_limit_total,
        allowed_models=_parse_admin_text_list(form.get("allowed_models")),
        allowed_endpoints=_parse_admin_text_list(form.get("allowed_endpoints")),
        rate_limit_policy=rate_limit_policy,
        note=cleaned_reason,
    )


def _parse_admin_email_delivery_mode(value: str | None) -> str:
    mode = (value or "none").strip().lower()
    if mode not in _ADMIN_EMAIL_DELIVERY_MODES:
        raise ValueError("Select a valid key email delivery mode.")
    return mode


def _validate_admin_email_delivery_preconditions(settings: Settings, mode: str) -> None:
    if mode in {"none", "pending"}:
        return
    if not settings.ENABLE_EMAIL_DELIVERY:
        raise ValueError("Email delivery must be enabled before using this delivery mode.")
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        raise ValueError("SMTP_HOST and SMTP_FROM are required for this delivery mode.")
    if mode == "enqueue" and not settings.get_celery_broker_url():
        raise ValueError("CELERY_BROKER_URL or REDIS_URL is required for queued delivery.")


async def _handle_admin_key_email_delivery_in_transaction(
    service: EmailDeliveryService,
    *,
    mode: str,
    gateway_key_id: uuid.UUID,
    one_time_secret_id: uuid.UUID,
    owner_id: uuid.UUID,
    actor_admin_id: uuid.UUID,
    reason: str | None,
) -> PendingKeyEmailResult | None:
    if mode == "none":
        return None
    pending = await service.create_pending_key_email_delivery(
        gateway_key_id=gateway_key_id,
        one_time_secret_id=one_time_secret_id,
        owner_id=owner_id,
        actor_admin_id=actor_admin_id,
        reason=reason,
    )
    if mode == "send-now":
        return pending
    return pending


def _enqueue_admin_pending_key_email(
    *,
    one_time_secret_id: uuid.UUID,
    email_delivery_id: uuid.UUID,
    actor_admin_id: uuid.UUID | None,
) -> str:
    result = send_pending_key_email_task.delay(
        str(one_time_secret_id),
        str(email_delivery_id),
        str(actor_admin_id) if actor_admin_id else None,
    )
    return str(result.id)


def _safe_created_key_result(created: CreatedGatewayKey) -> dict[str, object]:
    return {
        "gateway_key_id": created.gateway_key_id,
        "public_key_id": created.public_key_id,
        "display_prefix": created.display_prefix,
        "owner_id": created.owner_id,
        "valid_from": created.valid_from,
        "valid_until": created.valid_until,
    }


def _safe_rotated_key_result(rotation: RotatedGatewayKeyResult) -> dict[str, object]:
    return {
        "old_gateway_key_id": rotation.old_gateway_key_id,
        "new_gateway_key_id": rotation.new_gateway_key_id,
        "new_public_key_id": rotation.new_public_key_id,
        "old_status": rotation.old_status,
        "new_status": rotation.new_status,
        "valid_from": rotation.valid_from,
        "valid_until": rotation.valid_until,
        "owner_id": rotation.owner_id,
    }


def _parse_create_valid_until(
    *,
    valid_from: datetime,
    valid_until: str | None,
    valid_days: str | None,
) -> datetime:
    has_valid_until = bool((valid_until or "").strip())
    has_valid_days = bool((valid_days or "").strip())
    if has_valid_until and has_valid_days:
        raise ValueError("Use either valid_until or valid_days, not both.")
    if has_valid_until:
        parsed_valid_until = _parse_admin_datetime(valid_until)
        if parsed_valid_until is None:
            raise ValueError("Enter a valid key validity window.")
        return parsed_valid_until
    if has_valid_days:
        try:
            days = int(str(valid_days).strip(), 10)
        except ValueError as exc:
            raise ValueError("valid_days must be a positive integer.") from exc
        if days <= 0:
            raise ValueError("valid_days must be a positive integer.")
        return valid_from + timedelta(days=days)
    raise ValueError("Enter valid_until or valid_days before creating a key.")


def _parse_admin_rate_limit_policy(form: dict[str, str]) -> dict[str, int] | None:
    fields = (
        ("rate_limit_requests_per_minute", "requests_per_minute"),
        ("rate_limit_tokens_per_minute", "tokens_per_minute"),
        ("rate_limit_concurrent_requests", "max_concurrent_requests"),
        ("rate_limit_window_seconds", "window_seconds"),
    )
    policy: dict[str, int] = {}
    for form_name, policy_name in fields:
        provided, value = _parse_optional_admin_int(form.get(form_name))
        if provided and value is not None:
            policy[policy_name] = value
    return policy or None


def _parse_admin_text_list(value: str | None) -> list[str]:
    if value is None:
        return []
    normalized = value.replace(",", "\n")
    return [item.strip() for item in normalized.splitlines() if item.strip()]


def _parse_provider_slug(value: str | None) -> str:
    provider = (value or "").strip().lower()
    if not provider:
        raise ValueError("Provider is required.")
    if not all(ch.isalnum() or ch in {"-", "_"} for ch in provider):
        raise ValueError("Provider may contain only letters, numbers, hyphens, and underscores.")
    return provider


def _parse_provider_api_key_env_var(value: str | None) -> str:
    env_var = (value or "").strip()
    if not env_var:
        raise ValueError("API key environment variable name is required.")
    if _looks_like_provider_secret_value(env_var):
        raise ValueError("Enter an environment variable name, not a provider API key value.")
    if not (env_var[0].isalpha() or env_var[0] == "_"):
        raise ValueError("API key environment variable name must start with a letter or underscore.")
    if not all(ch.isalnum() or ch == "_" for ch in env_var):
        raise ValueError("API key environment variable name may contain only letters, numbers, and underscores.")
    return env_var


def _looks_like_provider_secret_value(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith(("sk-", "sk_", "sk-or-")) or any(ch.isspace() for ch in value)


def _validate_admin_base_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL must be an absolute http or https URL.")
    if parsed.username or parsed.password:
        raise ValueError("Base URL must not contain credentials.")


def _parse_required_positive_admin_int(value: str | None, *, field_name: str) -> int:
    provided, parsed = _parse_optional_admin_int(value)
    if not provided or parsed is None:
        raise ValueError(f"{field_name} is required.")
    return parsed


def _parse_required_non_negative_admin_int(value: str | None, *, field_name: str) -> int:
    if value is None or not value.strip():
        raise ValueError(f"{field_name} is required.")
    try:
        parsed = int(value.strip(), 10)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a whole number.") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return parsed


def _parse_required_admin_uuid(value: str | None, *, field_name: str) -> uuid.UUID:
    if value is None or not value.strip():
        raise ValueError(f"{field_name} is required.")
    return _parse_optional_admin_uuid(value, field_name=field_name)


def _parse_optional_admin_uuid(value: str | None, *, field_name: str) -> uuid.UUID | None:
    if value is None or not value.strip():
        return None
    try:
        return uuid.UUID(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID.") from exc


def _key_management_error_response(exc: KeyManagementError, *, gateway_key_id: uuid.UUID) -> Response:
    if exc.status_code == 404:
        return HTMLResponse("Gateway key not found.", status_code=404)
    message = exc.error_code if exc.error_code in _ADMIN_STATUS_MESSAGES else "key_action_failed"
    return _redirect_to_admin_key(gateway_key_id, message=message)


def _parse_gateway_key_id(gateway_key_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(gateway_key_id)
    except ValueError:
        return None


def _clean_admin_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    cleaned = reason.strip()
    return cleaned or None


def _parse_admin_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("invalid datetime") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_optional_admin_decimal(value: str | None) -> tuple[bool, Decimal | None]:
    if value is None:
        return False, None
    normalized = value.strip()
    if not normalized:
        return False, None
    try:
        parsed = Decimal(normalized)
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("decimal must be positive")
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid decimal") from exc
    return True, parsed


def _parse_required_non_negative_admin_decimal(value: str | None, *, field_name: str) -> Decimal:
    parsed = _parse_optional_non_negative_admin_decimal(value, field_name=field_name)
    if parsed is None:
        raise ValueError(f"{field_name} is required.")
    return parsed


def _parse_optional_non_negative_admin_decimal(value: str | None, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a decimal string.") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field_name} must be non-negative.")
    return parsed


def _parse_optional_admin_int(value: str | None) -> tuple[bool, int | None]:
    if value is None:
        return False, None
    normalized = value.strip()
    if not normalized:
        return False, None
    try:
        parsed = int(normalized, 10)
    except ValueError as exc:
        raise ValueError("invalid integer") from exc
    if parsed <= 0:
        raise ValueError("integer must be positive")
    return True, parsed


def _parse_admin_export_limit(value: str | None, *, default: int, maximum: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value.strip(), 10)
    except ValueError as exc:
        raise ValueError("limit must be a positive integer.") from exc
    if parsed <= 0:
        raise ValueError("limit must be a positive integer.")
    if parsed > maximum:
        raise ValueError(f"limit must be less than or equal to {maximum}.")
    return parsed


def _parse_optional_admin_bool(value: str | None, *, field_name: str) -> bool | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{field_name} must be true or false.")


def _csv_export_response(result: AdminCsvExportResult) -> Response:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"{result.filename_prefix}-{timestamp}.csv"
    return Response(
        content=result.content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _is_checked(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "on", "yes"}


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

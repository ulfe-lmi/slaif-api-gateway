"""API dependency wiring helpers for /v1 authentication."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator

from fastapi import Header, Request

from slaif_gateway.api.auth_errors import openai_error_from_auth_error
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import get_settings
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.session import (
    AsyncSession,
    get_db_session,
    get_db_session_from_app_state,
)
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.auth_service import (
    GatewayAuthError,
    GatewayAuthService,
    MalformedGatewayKeyError,
)
from slaif_gateway.utils.crypto import parse_gateway_key_public_id


def _database_session_unavailable_error() -> OpenAICompatibleError:
    return OpenAICompatibleError(
        "Database session could not be created.",
        status_code=500,
        error_type="server_error",
        code="database_session_unavailable",
    )


async def get_db_session_after_auth_header_check(
    request: Request | None = None,
) -> AsyncIterator:
    """Yield a DB session after cheap Authorization header validation has succeeded.

    The inner session generator is held explicitly and closed in ``finally``
    so that closing (or exhausting) this wrapper deterministically returns the
    DB connection to the pool. A bare ``async for`` over the inner generator
    would only release the connection when the inner async generator's GC
    finalizer later runs, leaving the connection checked out between the
    consumer's ``aclose()`` and that finalizer.
    """
    inner: AsyncGenerator[AsyncSession, None] | None = None
    try:
        if request is not None:
            inner = get_db_session_from_app_state(request)
        else:
            inner = get_db_session(settings=get_settings())
        async for session in inner:
            yield session
    except RuntimeError as exc:
        raise _database_session_unavailable_error() from exc
    finally:
        if inner is not None:
            await inner.aclose()


_get_db_session_after_auth_header_check = get_db_session_after_auth_header_check


async def get_authenticated_gateway_key(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AuthenticatedGatewayKey:
    """Authenticate gateway key from Authorization header for /v1 endpoints."""
    try:
        settings = getattr(request.app.state, "settings", None) or get_settings()
        token = GatewayAuthService._extract_bearer_token(authorization)
        parse_gateway_key_public_id(token, settings.get_gateway_key_accepted_prefixes())
    except ValueError as exc:
        raise openai_error_from_auth_error(MalformedGatewayKeyError()) from exc
    except GatewayAuthError as exc:
        raise openai_error_from_auth_error(exc) from exc

    try:
        session_iterator = _get_db_session_after_auth_header_check(request)
    except TypeError:
        session_iterator = _get_db_session_after_auth_header_check()

    async for session in session_iterator:
        repository = GatewayKeysRepository(session)
        service = GatewayAuthService(settings=settings, gateway_keys_repository=repository)
        try:
            return await service.authenticate_authorization_header(authorization)
        except GatewayAuthError as exc:
            raise openai_error_from_auth_error(exc) from exc

    raise openai_error_from_auth_error(GatewayAuthError())

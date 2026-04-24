"""API dependency wiring helpers for /v1 authentication."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Header

from slaif_gateway.api.auth_errors import openai_error_from_auth_error
from slaif_gateway.config import get_settings
from slaif_gateway.db.repositories.keys import GatewayKeysRepository
from slaif_gateway.db.session import get_db_session
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.auth_service import (
    GatewayAuthError,
    GatewayAuthService,
    MalformedGatewayKeyError,
)
from slaif_gateway.utils.crypto import parse_gateway_key_public_id


async def _get_db_session_after_auth_header_check() -> AsyncIterator:
    settings = get_settings()
    async for session in get_db_session(settings=settings):
        yield session


async def get_authenticated_gateway_key(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AuthenticatedGatewayKey:
    """Authenticate gateway key from Authorization header for /v1 endpoints."""
    try:
        token = GatewayAuthService._extract_bearer_token(authorization)
        parse_gateway_key_public_id(token)
    except ValueError as exc:
        raise openai_error_from_auth_error(MalformedGatewayKeyError()) from exc
    except GatewayAuthError as exc:
        raise openai_error_from_auth_error(exc) from exc

    settings = get_settings()
    async for session in _get_db_session_after_auth_header_check():
        repository = GatewayKeysRepository(session)
        service = GatewayAuthService(settings=settings, gateway_keys_repository=repository)
        try:
            return await service.authenticate_authorization_header(authorization)
        except GatewayAuthError as exc:
            raise openai_error_from_auth_error(exc) from exc

    raise openai_error_from_auth_error(GatewayAuthError())

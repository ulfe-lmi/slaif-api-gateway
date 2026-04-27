from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.endpoint_policy import (
    CHAT_COMPLETIONS,
    MODELS_LIST,
    EndpointPolicyService,
)
from slaif_gateway.services.endpoint_policy_errors import EndpointNotAllowedError


def _auth(
    *,
    allow_all_endpoints: bool = False,
    allowed_endpoints: tuple[str, ...] = (),
) -> AuthenticatedGatewayKey:
    now = datetime.now(UTC)
    return AuthenticatedGatewayKey(
        gateway_key_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        cohort_id=None,
        public_key_id="public1234abcd",
        status="active",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=allow_all_endpoints,
        allowed_endpoints=allowed_endpoints,
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
    )


def test_allow_all_endpoints_allows_known_endpoints() -> None:
    service = EndpointPolicyService()
    auth = _auth(allow_all_endpoints=True)

    service.ensure_endpoint_allowed(auth, MODELS_LIST)
    service.ensure_endpoint_allowed(auth, CHAT_COMPLETIONS)


def test_stable_endpoint_identifiers_are_enforced() -> None:
    service = EndpointPolicyService()

    service.ensure_endpoint_allowed(_auth(allowed_endpoints=("models.list",)), MODELS_LIST)
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("chat.completions",)),
        CHAT_COMPLETIONS,
    )

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("models.list",)), CHAT_COMPLETIONS)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("chat.completions",)), MODELS_LIST)


def test_empty_endpoint_allow_list_rejects_when_allow_all_false() -> None:
    service = EndpointPolicyService()

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(), MODELS_LIST)


def test_literal_method_paths_and_bare_paths_are_supported() -> None:
    service = EndpointPolicyService()

    service.ensure_endpoint_allowed(_auth(allowed_endpoints=("GET /v1/models",)), MODELS_LIST)
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("POST /v1/chat/completions",)),
        CHAT_COMPLETIONS,
    )
    service.ensure_endpoint_allowed(_auth(allowed_endpoints=("/v1/models",)), MODELS_LIST)
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("/v1/chat/completions",)),
        CHAT_COMPLETIONS,
    )


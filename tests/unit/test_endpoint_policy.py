from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.services.endpoint_policy import (
    CHAT_COMPLETIONS,
    CONVERSATIONS_CREATE,
    CONVERSATIONS_DELETE,
    CONVERSATIONS_RETRIEVE,
    MODELS_LIST,
    RESPONSES,
    RESPONSES_COMPACT,
    RESPONSES_DELETE,
    RESPONSES_INPUT_ITEMS,
    RESPONSES_INPUT_TOKENS,
    RESPONSES_RETRIEVE,
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
    service.ensure_endpoint_allowed(auth, RESPONSES)
    service.ensure_endpoint_allowed(auth, RESPONSES_INPUT_TOKENS)
    service.ensure_endpoint_allowed(auth, RESPONSES_RETRIEVE)
    service.ensure_endpoint_allowed(auth, RESPONSES_DELETE)
    service.ensure_endpoint_allowed(auth, RESPONSES_INPUT_ITEMS)
    service.ensure_endpoint_allowed(auth, RESPONSES_COMPACT)
    service.ensure_endpoint_allowed(auth, CONVERSATIONS_CREATE)
    service.ensure_endpoint_allowed(auth, CONVERSATIONS_RETRIEVE)
    service.ensure_endpoint_allowed(auth, CONVERSATIONS_DELETE)


def test_stable_endpoint_identifiers_are_enforced() -> None:
    service = EndpointPolicyService()

    service.ensure_endpoint_allowed(_auth(allowed_endpoints=("models.list",)), MODELS_LIST)
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("chat.completions",)),
        CHAT_COMPLETIONS,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("responses.input_tokens",)),
        RESPONSES_INPUT_TOKENS,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("responses.retrieve",)),
        RESPONSES_RETRIEVE,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("responses.delete",)),
        RESPONSES_DELETE,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("responses.input_items",)),
        RESPONSES_INPUT_ITEMS,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("responses.compact",)),
        RESPONSES_COMPACT,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("conversations.create",)),
        CONVERSATIONS_CREATE,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("conversations.retrieve",)),
        CONVERSATIONS_RETRIEVE,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("conversations.delete",)),
        CONVERSATIONS_DELETE,
    )

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("models.list",)), CHAT_COMPLETIONS)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("chat.completions",)), MODELS_LIST)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("responses",)), RESPONSES_INPUT_TOKENS)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("responses",)), RESPONSES_RETRIEVE)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("responses.retrieve",)), RESPONSES_DELETE)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("responses",)), RESPONSES_INPUT_ITEMS)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("responses.retrieve",)), RESPONSES_INPUT_ITEMS)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("responses",)), RESPONSES_COMPACT)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("responses.input_tokens",)), RESPONSES_COMPACT)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("responses.input_items",)), RESPONSES_COMPACT)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("responses",)), CONVERSATIONS_CREATE)

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(
            _auth(allowed_endpoints=("conversations.create",)),
            CONVERSATIONS_RETRIEVE,
        )

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(
            _auth(allowed_endpoints=("conversations.retrieve",)),
            CONVERSATIONS_DELETE,
        )


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
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("POST /v1/responses/input_tokens",)),
        RESPONSES_INPUT_TOKENS,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("/v1/responses/input_tokens",)),
        RESPONSES_INPUT_TOKENS,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("GET /v1/responses/{response_id}",)),
        RESPONSES_RETRIEVE,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("DELETE /v1/responses/{response_id}",)),
        RESPONSES_DELETE,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("GET /v1/responses/{response_id}/input_items",)),
        RESPONSES_INPUT_ITEMS,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("POST /v1/responses/compact",)),
        RESPONSES_COMPACT,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("/v1/responses/compact",)),
        RESPONSES_COMPACT,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("POST /v1/conversations",)),
        CONVERSATIONS_CREATE,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("/v1/conversations",)),
        CONVERSATIONS_CREATE,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("GET /v1/conversations/{conversation_id}",)),
        CONVERSATIONS_RETRIEVE,
    )
    service.ensure_endpoint_allowed(
        _auth(allowed_endpoints=("DELETE /v1/conversations/{conversation_id}",)),
        CONVERSATIONS_DELETE,
    )

    with pytest.raises(EndpointNotAllowedError):
        service.ensure_endpoint_allowed(_auth(allowed_endpoints=("/v1/responses",)), RESPONSES_INPUT_TOKENS)

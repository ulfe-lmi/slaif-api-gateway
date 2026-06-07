from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from slaif_gateway.services.key_errors import InvalidGatewayKeyPolicyError
from slaif_gateway.services.key_policy_validation import GatewayKeyPolicy, validate_gateway_key_policy


class _RoutesRepo:
    def __init__(self, routes: list[object]) -> None:
        self.routes = routes

    async def list_enabled_model_routes(self, *, endpoint: str | None = None) -> list[object]:
        return [route for route in self.routes if endpoint is None or route.endpoint == endpoint]


def _route(
    requested_model: str,
    *,
    match_type: str = "exact",
    endpoint: str = "/v1/chat/completions",
    visible_in_models: bool = True,
) -> object:
    return SimpleNamespace(
        id=uuid.uuid4(),
        requested_model=requested_model,
        match_type=match_type,
        endpoint=endpoint,
        visible_in_models=visible_in_models,
    )


@pytest.mark.asyncio
async def test_policy_validation_accepts_route_backed_chat_models() -> None:
    policy = await validate_gateway_key_policy(
        GatewayKeyPolicy(
            allowed_models=["gpt-5.2", "gpt-5.2", "gpt-4o-mini"],
            allowed_endpoints=["/v1/models", "/v1/chat/completions"],
        ),
        model_routes_repository=_RoutesRepo([_route("gpt-5.2"), _route("gpt-4o-*", match_type="glob")]),
    )

    assert policy.allowed_models == ["gpt-5.2", "gpt-4o-mini"]
    assert policy.allowed_endpoints == ["/v1/models", "/v1/chat/completions"]


@pytest.mark.asyncio
async def test_policy_validation_rejects_swapped_endpoint_and_model_values() -> None:
    with pytest.raises(InvalidGatewayKeyPolicyError, match="Allowed endpoints must be API paths"):
        await validate_gateway_key_policy(
            GatewayKeyPolicy(
                allowed_models=["/v1/models", "/v1/chat/completions"],
                allowed_endpoints=["gpt-5.2", "gpt-5.1"],
            ),
            model_routes_repository=_RoutesRepo([]),
        )


@pytest.mark.asyncio
async def test_policy_validation_rejects_non_path_endpoint_values() -> None:
    with pytest.raises(InvalidGatewayKeyPolicyError, match="Allowed endpoints must be API paths"):
        await validate_gateway_key_policy(
            GatewayKeyPolicy(
                allowed_models=["gpt-5.2"],
                allowed_endpoints=["gpt-5.2"],
            ),
            model_routes_repository=_RoutesRepo([_route("gpt-5.2")]),
        )


@pytest.mark.asyncio
async def test_policy_validation_rejects_endpoint_paths_as_models() -> None:
    with pytest.raises(InvalidGatewayKeyPolicyError, match="Allowed models must be model IDs"):
        await validate_gateway_key_policy(
            GatewayKeyPolicy(
                allowed_models=["/v1/models", "/v1/chat/completions"],
                allowed_endpoints=["/v1/models"],
            ),
            model_routes_repository=_RoutesRepo([]),
        )


@pytest.mark.asyncio
async def test_policy_validation_rejects_unimplemented_endpoints() -> None:
    for endpoint in ("/v1/completions", "/v1/not-real"):
        with pytest.raises(InvalidGatewayKeyPolicyError, match="not implemented"):
            await validate_gateway_key_policy(
                GatewayKeyPolicy(
                    allowed_models=["gpt-5.2"],
                    allowed_endpoints=[endpoint],
                ),
                model_routes_repository=_RoutesRepo([_route("gpt-5.2")]),
            )


@pytest.mark.asyncio
async def test_policy_validation_accepts_route_backed_responses_models() -> None:
    policy = await validate_gateway_key_policy(
        GatewayKeyPolicy(
            allowed_models=["gpt-5.2"],
            allowed_endpoints=["/v1/responses"],
        ),
        model_routes_repository=_RoutesRepo([_route("gpt-5.2", endpoint="/v1/responses")]),
    )

    assert policy.allowed_models == ["gpt-5.2"]
    assert policy.allowed_endpoints == ["/v1/responses"]


@pytest.mark.asyncio
async def test_policy_validation_accepts_route_backed_responses_input_token_count_models() -> None:
    policy = await validate_gateway_key_policy(
        GatewayKeyPolicy(
            allowed_models=["gpt-5.2"],
            allowed_endpoints=["/v1/responses/input_tokens"],
        ),
        model_routes_repository=_RoutesRepo(
            [_route("gpt-5.2", endpoint="/v1/responses/input_tokens")]
        ),
    )

    assert policy.allowed_models == ["gpt-5.2"]
    assert policy.allowed_endpoints == ["/v1/responses/input_tokens"]


@pytest.mark.asyncio
async def test_policy_validation_accepts_explicit_responses_lifecycle_endpoints_without_model_routes() -> None:
    policy = await validate_gateway_key_policy(
        GatewayKeyPolicy(
            allowed_models=[],
            allowed_endpoints=[
                "GET /v1/responses/{response_id}",
                "DELETE /v1/responses/{response_id}",
            ],
        ),
        model_routes_repository=_RoutesRepo([]),
    )

    assert policy.allowed_models == []
    assert policy.allowed_endpoints == [
        "GET /v1/responses/{response_id}",
        "DELETE /v1/responses/{response_id}",
    ]


@pytest.mark.asyncio
async def test_policy_validation_rejects_unimplemented_responses_lifecycle_paths() -> None:
    with pytest.raises(InvalidGatewayKeyPolicyError, match="not implemented"):
        await validate_gateway_key_policy(
            GatewayKeyPolicy(
                allowed_models=[],
                allowed_endpoints=["POST /v1/responses/{response_id}/cancel"],
            ),
            model_routes_repository=_RoutesRepo([]),
        )


@pytest.mark.asyncio
async def test_policy_validation_rejects_responses_model_without_responses_route() -> None:
    with pytest.raises(InvalidGatewayKeyPolicyError, match="No enabled route exists for model gpt-5.2"):
        await validate_gateway_key_policy(
            GatewayKeyPolicy(
                allowed_models=["gpt-5.2"],
                allowed_endpoints=["/v1/responses"],
            ),
            model_routes_repository=_RoutesRepo([_route("gpt-5.2")]),
        )


@pytest.mark.asyncio
async def test_policy_validation_rejects_input_token_count_model_without_matching_route() -> None:
    with pytest.raises(InvalidGatewayKeyPolicyError, match="No enabled route exists for model gpt-5.2"):
        await validate_gateway_key_policy(
            GatewayKeyPolicy(
                allowed_models=["gpt-5.2"],
                allowed_endpoints=["/v1/responses/input_tokens"],
            ),
            model_routes_repository=_RoutesRepo([_route("gpt-5.2", endpoint="/v1/responses")]),
        )


@pytest.mark.asyncio
async def test_policy_validation_rejects_model_without_enabled_route() -> None:
    with pytest.raises(InvalidGatewayKeyPolicyError, match="No enabled route exists for model gpt-5.2"):
        await validate_gateway_key_policy(
            GatewayKeyPolicy(
                allowed_models=["gpt-5.2"],
                allowed_endpoints=["/v1/models", "/v1/chat/completions"],
            ),
            model_routes_repository=_RoutesRepo([_route("gpt-4o-mini")]),
        )


@pytest.mark.asyncio
async def test_models_only_policy_validates_against_visible_routes() -> None:
    with pytest.raises(InvalidGatewayKeyPolicyError, match="No enabled route exists"):
        await validate_gateway_key_policy(
            GatewayKeyPolicy(
                allowed_models=["hidden-model"],
                allowed_endpoints=["/v1/models"],
            ),
            model_routes_repository=_RoutesRepo([_route("hidden-model", visible_in_models=False)]),
        )

    policy = await validate_gateway_key_policy(
        GatewayKeyPolicy(
            allowed_models=["visible-model"],
            allowed_endpoints=["/v1/models"],
        ),
        model_routes_repository=_RoutesRepo([_route("visible-model")]),
    )

    assert policy.allowed_models == ["visible-model"]

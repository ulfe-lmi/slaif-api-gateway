from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from slaif_gateway.api.errors import OpenAICompatibleError
from slaif_gateway.config import Settings
from slaif_gateway.modules.servers.local_coding.adapter import LocalCodingAdapter
from slaif_gateway.modules.servers.local_coding.contract import (
    LOCAL_CODING_SERVER_MODULE_ID,
    parse_local_coding_route_contract,
)
from slaif_gateway.modules.servers.local_coding.identity import (
    LocalCodingRequestIdentity,
    canonical_identity_bytes,
    derive_request_identity,
    expected_signature,
)
import slaif_gateway.modules.servers.local_coding.identity as identity_module
from slaif_gateway.modules.servers.registry import resolve_server_module
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.providers import ProviderRequest
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.responses_gateway import _build_local_coding_server_context

FIXTURE = Path("tests/fixtures/local_coding/signed_identity_v1_vectors.json")
SIGNING_SECRET = "local-coding-signing-secret-012345678901"
DERIVATION_SECRET = "local-coding-derivation-secret-0123456789"
SERVICE_SECRET = "local-coding-service-bearer-secret-0123456789"
ROUTE_CAPABILITIES = {
    "local_coding": {
        "contract_version": "local-coding-v1",
        "route_name": "vision",
        "tool_policy_version": "responses-tool-policy-v1",
        "identity_mode": "signed_identity_v1",
        "replay_mode": "process_local_ttl_lru",
        "deployment_mode": "single_worker",
    }
}
STATIC_ROUTE_CAPABILITIES = {
    "local_coding": {
        **ROUTE_CAPABILITIES["local_coding"],
        "identity_mode": "static",
    }
}


def test_local_coding_route_contract_is_exact_and_default_denied() -> None:
    contract = parse_local_coding_route_contract(ROUTE_CAPABILITIES)
    assert contract is not None
    assert contract.contract_version == LOCAL_CODING_SERVER_MODULE_ID
    assert contract.route_name == "vision"
    assert contract.nonce_min_length == 16
    assert contract.replay_ttl_seconds >= contract.clock_skew_seconds

    with pytest.raises(ValueError):
        parse_local_coding_route_contract(
            {"local_coding": {**ROUTE_CAPABILITIES["local_coding"], "unknown": True}}
        )
    with pytest.raises(ValueError):
        parse_local_coding_route_contract(
            {"local_coding": {**ROUTE_CAPABILITIES["local_coding"], "contract_version": "v2"}}
        )
    assert parse_local_coding_route_contract({"responses": {"text": True}}) is None
    assert (
        resolve_server_module("local-model", "openai_compatible", ROUTE_CAPABILITIES).module_id
        == LOCAL_CODING_SERVER_MODULE_ID
    )
    assert resolve_server_module("local-model", "openai_compatible").module_id == (
        "openai-compatible"
    )
    with pytest.raises(ProviderConfigurationError):
        resolve_server_module("local-model", "openai", ROUTE_CAPABILITIES)


def test_signed_identity_fixture_matches_exact_canonical_bytes_and_hmac() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["source"] == {
        "repository": "ulfe-lmi/slaif-local-coding",
        "commit": "356be8345dd71d6fddf829278651d18e485731d4",
        "source_fixture_sha256": "92c09c03a40dbdf5e6e08b9e5d7f5c6e2c777e14467845d351f219cbb9a66588",
    }
    contract = fixture["contract"]
    request = contract["request"]
    body = b'{"model":"qwen"}'
    identity = LocalCodingRequestIdentity(
        principal=request["principal"],
        session=request["session"],
        repository=request["repository"],
        route=request["route"],
        identity_mode="signed_identity_v1",
    )
    canonical = canonical_identity_bytes(
        method=request["method"],
        path=request["path"],
        raw_query=request["raw_query"].encode(),
        body=body,
        identity=identity,
        timestamp=request["timestamp"],
        nonce=request["nonce"],
    )
    assert hashlib.sha256(body).hexdigest() == request["body_sha256"]
    assert hashlib.sha256(canonical).hexdigest() == contract["canonical_string_sha256"]
    assert expected_signature(
        secret=contract["secret"]["value"].encode(), canonical=canonical
    ) == contract["expected_hmac"]


def test_identity_derivation_is_opaque_and_requires_trusted_repository_and_session() -> None:
    contract = parse_local_coding_route_contract(ROUTE_CAPABILITIES)
    assert contract is not None
    owner_id = uuid.uuid4()
    gateway_key_id = uuid.uuid4()
    session = "123e4567-e89b-12d3-a456-426614174000"
    identity = derive_request_identity(
        owner_id=owner_id,
        gateway_key_id=gateway_key_id,
        identity_hints={"session_id": session},
        repository_scope="repo-scope",
        route=contract,
        derivation_secret=DERIVATION_SECRET.encode(),
    )
    assert identity is not None
    assert "owner-uuid" not in identity.principal
    assert session not in identity.session
    assert "repo-scope" not in identity.repository
    for hints, repository in (
        ({}, "repo-scope"),
        ({"session_id": session, "thread_id": session}, "repo-scope"),
        ({"session_id": session}, None),
    ):
        with pytest.raises(ValueError):
            derive_request_identity(
                owner_id=owner_id,
                gateway_key_id=gateway_key_id,
                identity_hints=hints,
                repository_scope=repository,
                route=contract,
                derivation_secret=DERIVATION_SECRET.encode(),
            )


def test_codex_0149_identity_prefix_repairs_legacy_leading_punctuation_vectors() -> None:
    secret = b"155-ai-synthetic-secret-0123456789"
    for index, expected_leading_character in ((27, "-"), (170, "_")):
        legacy_message = f"slaif-local-coding:principal:v1\nowner-{index}".encode()
        digest = hmac.new(secret, legacy_message, hashlib.sha256).digest()
        legacy = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        assert legacy.startswith(expected_leading_character)
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", legacy) is None

        corrected = identity_module._opaque_hmac(
            secret, "slaif-local-coding:principal:v1", f"owner-{index}"
        )
        assert corrected.startswith("h")
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", corrected)
        assert base64.urlsafe_b64decode(corrected[1:] + "=") == digest


def test_codex_0149_identity_matrix_is_stable_injective_and_local_grammar_safe() -> None:
    contract = parse_local_coding_route_contract(ROUTE_CAPABILITIES)
    assert contract is not None
    identities = []
    for owner_index in range(4):
        identity = derive_request_identity(
            owner_id=uuid.UUID(f"00000000-0000-4000-8000-{owner_index:012d}"),
            gateway_key_id=uuid.UUID(f"10000000-0000-4000-8000-{owner_index:012d}"),
            identity_hints={"session_id": f"20000000-0000-4000-8000-{owner_index:012d}"},
            repository_scope=f"repo-{owner_index}",
            route=contract,
            derivation_secret=DERIVATION_SECRET.encode(),
        )
        assert identity is not None
        identities.append(identity)
        assert all(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,255}", value)
            for value in (
                identity.principal,
                identity.session,
                identity.repository,
                identity.route,
            )
        )
        assert identity == derive_request_identity(
            owner_id=uuid.UUID(f"00000000-0000-4000-8000-{owner_index:012d}"),
            gateway_key_id=uuid.UUID(f"10000000-0000-4000-8000-{owner_index:012d}"),
            identity_hints={"session_id": f"20000000-0000-4000-8000-{owner_index:012d}"},
            repository_scope=f"repo-{owner_index}",
            route=contract,
            derivation_secret=DERIVATION_SECRET.encode(),
        )
    assert len({identity.principal for identity in identities}) == len(identities)
    assert len({identity.session for identity in identities}) == len(identities)
    assert len({identity.repository for identity in identities}) == len(identities)


def test_signed_identity_signer_rejects_invalid_hand_built_fields() -> None:
    identity = LocalCodingRequestIdentity(
        principal="-invalid",
        session="session-opaque",
        repository="repository-opaque",
        route="vision",
        identity_mode="signed_identity_v1",
    )
    contract = parse_local_coding_route_contract(ROUTE_CAPABILITIES)
    assert contract is not None
    with pytest.raises(ValueError, match="Local Coding principal is invalid"):
        from slaif_gateway.modules.servers.local_coding.identity import sign_identity

        sign_identity(
            signing_secret=SIGNING_SECRET.encode(),
            identity=identity,
            body=b"{}",
            route=contract,
            timestamp="1700000000",
            nonce="1234567890abcdef",
        )
    valid_identity = replace(identity, principal="principal-opaque")
    for field in ("session", "repository", "route"):
        invalid_identity = replace(valid_identity, **{field: "-invalid"})
        with pytest.raises(ValueError, match=f"Local Coding {field} is invalid"):
            sign_identity(
                signing_secret=SIGNING_SECRET.encode(),
                identity=invalid_identity,
                body=b"{}",
                route=contract,
                timestamp="1700000000",
                nonce="1234567890abcdef",
            )


@pytest.mark.parametrize("route_name", ["-bad", "_bad", "dotted.route"])
def test_signed_local_route_uses_pinned_peer_grammar(route_name: str) -> None:
    with pytest.raises(ValueError, match="route name is invalid"):
        parse_local_coding_route_contract(
            {"local_coding": {**ROUTE_CAPABILITIES["local_coding"], "route_name": route_name}}
        )
    for valid in ("qwen38-vision-codex", "internal_name", "internal-name"):
        parsed = parse_local_coding_route_contract(
            {"local_coding": {**ROUTE_CAPABILITIES["local_coding"], "route_name": valid}}
        )
        assert parsed is not None and parsed.route_name == valid
    if route_name == "dotted.route":
        static = parse_local_coding_route_contract(
            {"local_coding": {**ROUTE_CAPABILITIES["local_coding"], "route_name": route_name, "identity_mode": "static"}}
        )
        assert static is not None


@pytest.mark.asyncio
async def test_local_coding_adapter_sends_exact_bytes_and_separate_signed_headers() -> None:
    observed: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(
            200,
            json={
                "id": "response-local-coding",
                "object": "response",
                "model": "qwen",
                "output": [],
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            },
        )

    settings = Settings(
        LOCAL_CODING_SIGNING_SECRET_V1=SIGNING_SECRET,
        LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1=DERIVATION_SECRET,
    )
    identity = LocalCodingRequestIdentity(
        principal="principal-opaque",
        session="session-opaque",
        repository="repository-opaque",
        route="vision",
        identity_mode="signed_identity_v1",
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://local-coding.test/v1",
    ) as client:
        adapter = LocalCodingAdapter(
            settings,
                provider_name="local-coding",
                api_key=SERVICE_SECRET,
            base_url="http://local-coding.test/v1",
            timeout_seconds=10,
            max_retries=0,
            http_client=client,
            route_capabilities=ROUTE_CAPABILITIES,
        )
        response = await adapter.forward_response(
            ProviderRequest(
                provider="local-coding",
                upstream_model="qwen3.8-27b",
                endpoint="/v1/responses",
                body={"input": "synthetic", "store": False},
                request_id="request-safe",
                extra_headers={"Authorization": "client-bearer", "X-SLAIF-Principal": "client"},
                server_context={
                    "identity_mode": identity.identity_mode,
                    "principal": identity.principal,
                    "session": identity.session,
                    "repository": identity.repository,
                    "route": identity.route,
                },
            )
        )

    assert response.status_code == 200
    assert len(observed) == 1
    request = observed[0]
    assert request.headers["authorization"] == f"Bearer {SERVICE_SECRET}"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["x-slaif-principal"] == identity.principal
    assert request.headers["x-slaif-session"] == identity.session
    assert request.headers["x-slaif-repository"] == identity.repository
    assert request.headers["x-slaif-route"] == identity.route
    assert "client-bearer" not in str(request.headers)
    assert request.content == json.dumps(
        {"input": "synthetic", "model": "qwen3.8-27b", "store": False},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "kwargs"),
    [
        ("forward_chat_completion", {}),
        ("create_speech", {}),
        ("create_transcription", {}),
        ("create_translation", {}),
        ("create_embedding", {}),
        ("create_realtime_client_secret", {}),
        ("forward_response_input_tokens", {}),
        ("compact_response", {}),
        ("retrieve_response", {"response_id": "response-id"}),
        ("delete_response", {"response_id": "response-id"}),
        ("list_response_input_items", {"response_id": "response-id"}),
        ("create_conversation", {}),
        ("retrieve_conversation", {"conversation_id": "conversation-id"}),
        ("update_conversation", {"conversation_id": "conversation-id"}),
        ("delete_conversation", {"conversation_id": "conversation-id"}),
        ("create_conversation_items", {"conversation_id": "conversation-id"}),
        ("list_conversation_items", {"conversation_id": "conversation-id"}),
        (
            "retrieve_conversation_item",
            {"conversation_id": "conversation-id", "item_id": "item-id"},
        ),
        (
            "delete_conversation_item",
            {"conversation_id": "conversation-id", "item_id": "item-id"},
        ),
        ("stream_chat_completion", {}),
    ],
)
async def test_local_coding_adapter_rejects_every_non_responses_create_operation(
    operation: str,
    kwargs: dict[str, str],
) -> None:
    observed = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed
        observed = True
        return httpx.Response(500, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://local-coding.test/v1",
    ) as client:
        adapter = LocalCodingAdapter(
            Settings(),
            provider_name="local-coding",
            api_key=SERVICE_SECRET,
            base_url="http://local-coding.test/v1",
            http_client=client,
            route_capabilities=STATIC_ROUTE_CAPABILITIES,
        )
        request = ProviderRequest(
            provider="local-coding",
            upstream_model="qwen",
            endpoint="/v1/responses",
            body={"input": "synthetic"},
        )
        method = getattr(adapter, operation)
        result = method(request, **kwargs)
        with pytest.raises(ProviderConfigurationError) as exc_info:
            if operation.startswith("stream_"):
                await anext(result)
            else:
                await result

    assert exc_info.value.error_code == "unsupported_provider_endpoint"
    assert observed is False


@pytest.mark.parametrize(
    ("service", "signing", "derivation"),
    [
        (SIGNING_SECRET, SIGNING_SECRET, DERIVATION_SECRET),
        (DERIVATION_SECRET, SIGNING_SECRET, DERIVATION_SECRET),
    ],
)
def test_local_coding_service_credential_cannot_equal_identity_secret_roles(
    service: str,
    signing: str,
    derivation: str,
) -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        LocalCodingAdapter(
            Settings(
                LOCAL_CODING_SIGNING_SECRET_V1=signing,
                LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1=derivation,
            ),
            provider_name="local-coding",
            api_key=service,
            route_capabilities=ROUTE_CAPABILITIES,
        )
    assert exc_info.value.error_code == "local_coding_secret_roles_not_separate"


def test_local_coding_secret_roles_cover_known_core_secrets_and_malformed_service() -> None:
    with pytest.raises(ValueError, match="separate"):
        Settings(
            LOCAL_CODING_SIGNING_SECRET_V1=SIGNING_SECRET,
            LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1=SIGNING_SECRET,
        )

    with pytest.raises(ValueError, match="separate"):
        Settings(
            TOKEN_HMAC_SECRET_V1=SIGNING_SECRET,
            LOCAL_CODING_SIGNING_SECRET_V1=SIGNING_SECRET,
            LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1=DERIVATION_SECRET,
        )

    with pytest.raises(ProviderConfigurationError) as exc_info:
        LocalCodingAdapter(
            Settings(),
            provider_name="local-coding",
            api_key="short-service",
            route_capabilities=STATIC_ROUTE_CAPABILITIES,
        )
    assert exc_info.value.error_code == "local_coding_service_credential_invalid"


def test_local_coding_static_adapter_allows_distinct_optional_identity_secrets() -> None:
    adapter = LocalCodingAdapter(
        Settings(
            LOCAL_CODING_SIGNING_SECRET_V1=SIGNING_SECRET,
            LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1=DERIVATION_SECRET,
        ),
        provider_name="local-coding",
        api_key=SERVICE_SECRET,
        route_capabilities=STATIC_ROUTE_CAPABILITIES,
    )
    assert adapter.provider_name == "local-coding"


def _authenticated_key(
    *,
    owner_id: uuid.UUID,
    gateway_key_id: uuid.UUID | None = None,
    repository_scope: str | None = "server-repository-scope",
) -> AuthenticatedGatewayKey:
    return AuthenticatedGatewayKey(
        gateway_key_id=gateway_key_id or uuid.uuid4(),
        owner_id=owner_id,
        cohort_id=None,
        public_key_id="pk-local-coding",
        status="active",
        valid_from=datetime.now(UTC),
        valid_until=datetime.now(UTC),
        allow_all_models=True,
        allowed_models=(),
        allow_all_endpoints=True,
        allowed_endpoints=(),
        allowed_providers=None,
        cost_limit_eur=None,
        token_limit_total=None,
        request_limit_total=None,
        rate_limit_policy={},
        responses_policy=(
            {"local_coding_repository_scope": repository_scope}
            if repository_scope is not None
            else {}
        ),
    )


def _local_route(*, route_name: str = "vision", identity_mode: str = "signed_identity_v1") -> RouteResolutionResult:
    capabilities = {
        "local_coding": {
            **ROUTE_CAPABILITIES["local_coding"],
            "route_name": route_name,
            "identity_mode": identity_mode,
        }
    }
    return RouteResolutionResult(
        requested_model="qwen-local",
        resolved_model="qwen-local",
        provider="local-model",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="qwen-local",
        priority=1,
        provider_kind="openai_compatible",
        capabilities=capabilities,
    )


def test_core_local_coding_identity_context_is_opaque_stable_and_isolated() -> None:
    owner_id = uuid.uuid4()
    gateway_key_id = uuid.uuid4()
    session = "123e4567-e89b-12d3-a456-426614174000"
    client_request = SimpleNamespace(identity_hints={"session_id": session})
    route = _local_route()
    settings = Settings(LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1=DERIVATION_SECRET)
    context = _build_local_coding_server_context(
        client_request=client_request,
        authenticated_key=_authenticated_key(owner_id=owner_id, gateway_key_id=gateway_key_id),
        route=route,
        settings=settings,
    )
    assert context is not None
    assert set(context) == {"identity_mode", "principal", "session", "repository", "route"}
    assert context["identity_mode"] == "signed_identity_v1"
    assert context["route"] == "vision"
    assert str(owner_id) not in str(context)
    assert session not in str(context)
    assert "server-repository-scope" not in str(context)
    assert context == _build_local_coding_server_context(
        client_request=client_request,
        authenticated_key=_authenticated_key(owner_id=owner_id, gateway_key_id=gateway_key_id),
        route=route,
        settings=settings,
    )

    changed_owner = _build_local_coding_server_context(
        client_request=client_request,
        authenticated_key=_authenticated_key(owner_id=uuid.uuid4()),
        route=route,
        settings=settings,
    )
    changed_gateway_key = _build_local_coding_server_context(
        client_request=client_request,
        authenticated_key=_authenticated_key(owner_id=owner_id, gateway_key_id=uuid.uuid4()),
        route=route,
        settings=settings,
    )
    changed_session = _build_local_coding_server_context(
        client_request=SimpleNamespace(identity_hints={"session_id": "123e4567-e89b-12d3-a456-426614174001"}),
        authenticated_key=_authenticated_key(owner_id=owner_id, gateway_key_id=gateway_key_id),
        route=route,
        settings=settings,
    )
    changed_repository = _build_local_coding_server_context(
        client_request=client_request,
        authenticated_key=_authenticated_key(owner_id=owner_id, gateway_key_id=gateway_key_id, repository_scope="other-repo"),
        route=route,
        settings=settings,
    )
    changed_route = _build_local_coding_server_context(
        client_request=client_request,
        authenticated_key=_authenticated_key(owner_id=owner_id, gateway_key_id=gateway_key_id),
        route=_local_route(route_name="other-route"),
        settings=settings,
    )
    assert changed_owner is not None and changed_owner["principal"] != context["principal"]
    assert changed_gateway_key is not None and changed_gateway_key["session"] != context["session"]
    assert changed_session is not None and changed_session["session"] != context["session"]
    assert changed_repository is not None and changed_repository["repository"] != context["repository"]
    assert changed_route is not None and changed_route["route"] != context["route"]


@pytest.mark.parametrize(
    "case",
    ["missing_session", "ambiguous_session", "missing_repository"],
)
def test_core_local_coding_identity_context_fails_closed_for_missing_or_ambiguous_inputs(
    case: str,
) -> None:
    owner_id = uuid.uuid4()
    key = _authenticated_key(owner_id=owner_id)
    request = SimpleNamespace(identity_hints={"session_id": "session"})
    if case == "missing_session":
        request = SimpleNamespace(identity_hints={})
    elif case == "ambiguous_session":
        request = SimpleNamespace(identity_hints={"session_id": "a", "thread_id": "b"})
    else:
        key = _authenticated_key(owner_id=owner_id, repository_scope=None)
    route = _local_route()
    settings = Settings(LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1=DERIVATION_SECRET)
    with pytest.raises(OpenAICompatibleError):
        _build_local_coding_server_context(
            client_request=request,
            authenticated_key=key,
            route=route,
            settings=settings,
        )


def test_core_local_coding_identity_context_fails_without_secret_or_for_malformed_route() -> None:
    owner_id = uuid.uuid4()
    request = SimpleNamespace(identity_hints={"session_id": "session"})
    key = _authenticated_key(owner_id=owner_id)
    with pytest.raises(OpenAICompatibleError):
        _build_local_coding_server_context(
            client_request=request,
            authenticated_key=key,
            route=_local_route(),
            settings=Settings(),
        )
    malformed = replace(_local_route(), capabilities={"local_coding": {}})
    with pytest.raises(OpenAICompatibleError):
        _build_local_coding_server_context(
            client_request=request,
            authenticated_key=key,
            route=malformed,
            settings=Settings(LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1=DERIVATION_SECRET),
        )


def test_core_local_coding_identity_context_returns_none_for_non_local_route_and_static_is_safe() -> None:
    owner_id = uuid.uuid4()
    key = _authenticated_key(owner_id=owner_id, repository_scope=None)
    non_local = RouteResolutionResult(
        requested_model="gpt-test",
        resolved_model="gpt-test",
        provider="openai",
        route_id=uuid.uuid4(),
        route_match_type="exact",
        route_pattern="gpt-test",
        priority=1,
        provider_kind="openai",
        capabilities=None,
    )
    assert _build_local_coding_server_context(
        client_request=SimpleNamespace(identity_hints={}),
        authenticated_key=key,
        route=non_local,
        settings=Settings(),
    ) is None
    static_context = _build_local_coding_server_context(
        client_request=SimpleNamespace(identity_hints={}),
        authenticated_key=key,
        route=_local_route(identity_mode="static"),
        settings=Settings(),
    )
    assert static_context == {"identity_mode": "static", "route": "vision"}

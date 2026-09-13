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
    LOCAL_CODING_REPLAY_MODE,
    LOCAL_CODING_SERVER_MODULE_ID,
    LOCAL_CODING_SERVER_MODULE_VERSION,
    parse_local_coding_route_contract,
)
from slaif_gateway.modules.servers.local_coding.identity import (
    LocalCodingRequestIdentity,
    canonical_identity_bytes,
    derive_request_identity,
    expected_signature,
)
import slaif_gateway.modules.servers.local_coding.identity as identity_module
from slaif_gateway.modules.servers.registry import SERVER_MODULE_REGISTRY, resolve_server_module
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.schemas.auth import AuthenticatedGatewayKey
from slaif_gateway.schemas.providers import ProviderRequest
from slaif_gateway.schemas.routing import RouteResolutionResult
from slaif_gateway.services.responses_gateway import _build_local_coding_server_context

FIXTURE = Path("tests/fixtures/local_coding/signed_identity_v1_vectors.json")
REPLAY_AUTHORITY_FIXTURE = Path("tests/fixtures/local_coding/local_replay_authority.json")
SIGNING_SECRET = "local-coding-signing-secret-012345678901"
DERIVATION_SECRET = "local-coding-derivation-secret-0123456789"
SERVICE_SECRET = "local-coding-service-bearer-secret-0123456789"
ROUTE_CAPABILITIES = {
    "local_coding": {
        "contract_version": "local-coding-v1",
        "route_name": "vision",
        "tool_policy_version": "responses-tool-policy-v1",
        "identity_mode": "signed_identity_v1",
        "replay_mode": "process_local_inclusive_horizon_fail_closed",
        "deployment_mode": "single_worker",
        "clock_skew_seconds": 60,
        "replay_ttl_seconds": 60,
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
    assert contract.replay_mode == LOCAL_CODING_REPLAY_MODE
    assert contract.deployment_mode == "single_worker"
    assert contract.clock_skew_seconds == 60
    assert contract.replay_ttl_seconds == 60
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
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
        "4fdbc6dd46fcd11819a60a7dd4e8892a82ff64cd8da1e108a9fdb2482c13e1f0"
    )
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

# Objective-164 obligation manifest.  Every obligation maps to one exact,
# explicitly named test node covering the affected/required boundary.  The two
# complete verifier unit files are executed separately in full, not enumerated
# here.  The collector must prove missing=[] and zero skips.
LOCAL_CODING_REPLAY_OBLIGATION_TO_TEST_NODE = {
    "parser.accepts-new-mode": "tests/unit/test_local_coding_server_module.py::test_local_coding_route_contract_is_exact_and_default_denied",
    "parser.rejects-retired-mode": "tests/unit/test_local_coding_server_module.py::test_local_coding_parser_rejects_retired_and_unknown_replay_modes[retired-ttl-lru]",
    "parser.rejects-truncated-synonym": "tests/unit/test_local_coding_server_module.py::test_local_coding_parser_rejects_retired_and_unknown_replay_modes[truncated-synonym]",
    "parser.rejects-unknown-mode": "tests/unit/test_local_coding_server_module.py::test_local_coding_parser_rejects_retired_and_unknown_replay_modes[unknown-synonym]",
    "signed.accepts-explicit-60-60": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_accepts_explicit_replay_timing[explicit-60-60]",
    "signed.accepts-explicit-60-120": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_accepts_explicit_replay_timing[explicit-60-120]",
    "signed.rejects-missing-both": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[missing-both]",
    "signed.rejects-missing-skew": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[missing-skew]",
    "signed.rejects-missing-ttl": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[missing-ttl]",
    "signed.rejects-bool-skew": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[bool-skew]",
    "signed.rejects-bool-ttl": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[bool-ttl]",
    "signed.rejects-coercible-skew": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[coercible-skew]",
    "signed.rejects-coercible-ttl": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[coercible-ttl]",
    "signed.rejects-float-ttl": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[float-ttl]",
    "signed.rejects-skew-zero": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[skew-zero]",
    "signed.rejects-skew-301": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[skew-301]",
    "signed.rejects-ttl-zero": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[ttl-zero]",
    "signed.rejects-ttl-86401": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[ttl-86401]",
    "signed.rejects-ttl-below-skew": "tests/unit/test_local_coding_server_module.py::test_local_coding_signed_identity_requires_explicit_replay_timing[ttl-below-skew]",
    "static.inert-defaults-no-signed-leak": "tests/unit/test_local_coding_server_module.py::test_local_coding_static_mode_keeps_inert_timing_defaults",
    "module-version-2.descriptor-and-resolution": "tests/unit/test_local_coding_server_module.py::test_local_coding_server_module_version_two_selects_only_exact_contract",
    "registry.rejects-retired-mode": "tests/unit/test_local_coding_server_module.py::test_local_coding_registry_resolution_fails_closed_for_stale_contract[retired-replay-mode]",
    "registry.rejects-unknown-mode": "tests/unit/test_local_coding_server_module.py::test_local_coding_registry_resolution_fails_closed_for_stale_contract[unknown-replay-mode]",
    "registry.rejects-wrong-provider-kind": "tests/unit/test_local_coding_server_module.py::test_local_coding_registry_resolution_fails_closed_for_stale_contract[wrong-provider-kind]",
    "factory.version-2-new-contract": "tests/unit/test_provider_factory.py::test_factory_builds_local_coding_responses_only_adapter_from_route_metadata",
    "factory.rejects-retired-mode": "tests/unit/test_provider_factory.py::test_factory_rejects_retired_local_coding_replay_mode_before_construction",
    "source.replay-authority-fixture-pinned": "tests/unit/test_local_coding_server_module.py::test_local_coding_replay_authority_fixture_pins_exact_source_facts",
    "signing.canonical-fixture-unchanged": "tests/unit/test_local_coding_server_module.py::test_signed_identity_fixture_matches_exact_canonical_bytes_and_hmac",
    "postgres.roundtrip-no-reservation-no-ledger": "tests/integration/test_local_coding_server_module_postgres.py::test_local_coding_identity_failure_creates_no_reservation_or_ledger",
    "postgres.route-row-roundtrip-version-2": "tests/integration/test_local_coding_server_module_postgres.py::test_local_coding_route_row_roundtrips_new_mode_and_resolves_version_two",
    "postgres.e2e-route-creation-roundtrip": "tests/e2e/test_openai_python_client_responses.py::test_openai_python_client_codex_0149_signed_thread_namespace_e2e",
    "e2e.signed-thread-namespace": "tests/e2e/test_openai_python_client_responses.py::test_openai_python_client_codex_0149_signed_thread_namespace_e2e",
    "e2e.static-server-module": "tests/e2e/test_openai_python_client_responses.py::test_openai_python_client_local_coding_server_module_e2e",
    "e2e.codex-streaming": "tests/e2e/test_openai_python_client_responses.py::test_openai_python_client_codex_0149_local_coding_streaming_e2e",
    "e2e.zero-argument-function": "tests/e2e/test_openai_python_client_responses.py::test_openai_python_client_codex_0149_zero_argument_function_streaming_e2e",
    "e2e.malformed-stream-before-output": "tests/e2e/test_openai_python_client_responses.py::test_local_coding_malformed_stream_before_output_releases_accounting",
    "e2e.malformed-stream-after-output": "tests/e2e/test_openai_python_client_responses.py::test_local_coding_malformed_stream_after_output_records_interruption",
    "framing.adapter-bounded-framer-unchanged": "tests/unit/test_local_coding_sse_framing.py::test_local_adapter_uses_bounded_framer_and_closes_after_parse_error",
    "framing.adapter-done-marker-unchanged": "tests/unit/test_local_coding_sse_framing.py::test_local_adapter_yields_bounded_events_and_preserves_done_marker",
    "deployment.single-worker-only": "tests/unit/test_local_coding_server_module.py::test_local_coding_deployment_mode_is_single_worker_only[multi-worker]",
    "deployment.rejects-cluster": "tests/unit/test_local_coding_server_module.py::test_local_coding_deployment_mode_is_single_worker_only[cluster]",
    "deployment.rejects-missing": "tests/unit/test_local_coding_server_module.py::test_local_coding_deployment_mode_is_single_worker_only[missing]",
    "verifier.metadata-sync-roundtrip-manifest": "tests/unit/test_codex_0149_local_roundtrip.py::test_obligation_manifest_is_complete_and_bounded",
    "verifier.metadata-sync-assistant-history-source": "tests/unit/test_codex_0149_assistant_output_history.py::test_turn_failure_projection_positive_is_closed_and_source_pinned",
    "obligation.map-literal-complete": "tests/unit/test_local_coding_server_module.py::test_objective_164_obligation_map_is_literal_and_complete",
}

LOCAL_CODING_REPLAY_REQUIRED_OBLIGATION_IDS = frozenset(
    {
        "parser.accepts-new-mode",
        "parser.rejects-retired-mode",
        "parser.rejects-truncated-synonym",
        "parser.rejects-unknown-mode",
        "signed.accepts-explicit-60-60",
        "signed.accepts-explicit-60-120",
        "signed.rejects-missing-both",
        "signed.rejects-missing-skew",
        "signed.rejects-missing-ttl",
        "signed.rejects-bool-skew",
        "signed.rejects-bool-ttl",
        "signed.rejects-coercible-skew",
        "signed.rejects-coercible-ttl",
        "signed.rejects-float-ttl",
        "signed.rejects-skew-zero",
        "signed.rejects-skew-301",
        "signed.rejects-ttl-zero",
        "signed.rejects-ttl-86401",
        "signed.rejects-ttl-below-skew",
        "static.inert-defaults-no-signed-leak",
        "module-version-2.descriptor-and-resolution",
        "registry.rejects-retired-mode",
        "registry.rejects-unknown-mode",
        "registry.rejects-wrong-provider-kind",
        "factory.version-2-new-contract",
        "factory.rejects-retired-mode",
        "source.replay-authority-fixture-pinned",
        "signing.canonical-fixture-unchanged",
        "postgres.roundtrip-no-reservation-no-ledger",
        "postgres.route-row-roundtrip-version-2",
        "postgres.e2e-route-creation-roundtrip",
        "e2e.signed-thread-namespace",
        "e2e.static-server-module",
        "e2e.codex-streaming",
        "e2e.zero-argument-function",
        "e2e.malformed-stream-before-output",
        "e2e.malformed-stream-after-output",
        "framing.adapter-bounded-framer-unchanged",
        "framing.adapter-done-marker-unchanged",
        "deployment.single-worker-only",
        "deployment.rejects-cluster",
        "deployment.rejects-missing",
        "verifier.metadata-sync-roundtrip-manifest",
        "verifier.metadata-sync-assistant-history-source",
        "obligation.map-literal-complete",
    }
)


@pytest.mark.parametrize(
    "replay_mode",
    [
        "process_local_ttl_lru",
        "process_local_inclusive_horizon",
        "process_local_lru",
    ],
    ids=["retired-ttl-lru", "truncated-synonym", "unknown-synonym"],
)
def test_local_coding_parser_rejects_retired_and_unknown_replay_modes(replay_mode: str) -> None:
    with pytest.raises(ValueError, match="replay mode is unsupported"):
        parse_local_coding_route_contract(
            {"local_coding": {**ROUTE_CAPABILITIES["local_coding"], "replay_mode": replay_mode}}
        )


_MISSING = object()
SIGNED_TIMING_NEGATIVE_CASES = {
    "missing-skew": {"clock_skew_seconds": _MISSING},
    "missing-ttl": {"replay_ttl_seconds": _MISSING},
    "missing-both": {"clock_skew_seconds": _MISSING, "replay_ttl_seconds": _MISSING},
    "bool-skew": {"clock_skew_seconds": True},
    "bool-ttl": {"replay_ttl_seconds": True},
    "coercible-skew": {"clock_skew_seconds": "60"},
    "coercible-ttl": {"replay_ttl_seconds": "60"},
    "float-ttl": {"replay_ttl_seconds": 60.0},
    "skew-zero": {"clock_skew_seconds": 0},
    "skew-301": {"clock_skew_seconds": 301},
    "ttl-zero": {"replay_ttl_seconds": 0},
    "ttl-86401": {"replay_ttl_seconds": 86_401},
    "ttl-below-skew": {"clock_skew_seconds": 60, "replay_ttl_seconds": 59},
}


@pytest.mark.parametrize("case", sorted(SIGNED_TIMING_NEGATIVE_CASES))
def test_local_coding_signed_identity_requires_explicit_replay_timing(case: str) -> None:
    contract_dict = dict(ROUTE_CAPABILITIES["local_coding"])
    for field, value in SIGNED_TIMING_NEGATIVE_CASES[case].items():
        if value is _MISSING:
            contract_dict.pop(field, None)
        else:
            contract_dict[field] = value
    with pytest.raises(ValueError):
        parse_local_coding_route_contract({"local_coding": contract_dict})


@pytest.mark.parametrize(
    ("skew", "ttl"),
    [(60, 60), (60, 120)],
    ids=["explicit-60-60", "explicit-60-120"],
)
def test_local_coding_signed_identity_accepts_explicit_replay_timing(skew: int, ttl: int) -> None:
    parsed = parse_local_coding_route_contract(
        {
            "local_coding": {
                **ROUTE_CAPABILITIES["local_coding"],
                "clock_skew_seconds": skew,
                "replay_ttl_seconds": ttl,
            }
        }
    )
    assert parsed is not None
    assert parsed.clock_skew_seconds == skew
    assert parsed.replay_ttl_seconds == ttl
    assert parsed.replay_mode == LOCAL_CODING_REPLAY_MODE


def test_local_coding_static_mode_keeps_inert_timing_defaults() -> None:
    static_values = {
        "contract_version": "local-coding-v1",
        "route_name": "vision",
        "tool_policy_version": "responses-tool-policy-v1",
        "identity_mode": "static",
        "replay_mode": "process_local_inclusive_horizon_fail_closed",
        "deployment_mode": "single_worker",
    }
    parsed = parse_local_coding_route_contract({"local_coding": dict(static_values)})
    assert parsed is not None
    assert parsed.identity_mode == "static"
    assert parsed.replay_mode == LOCAL_CODING_REPLAY_MODE
    assert parsed.clock_skew_seconds == 60
    assert parsed.replay_ttl_seconds == 60
    explicit = parse_local_coding_route_contract(
        {"local_coding": {**static_values, "clock_skew_seconds": 60, "replay_ttl_seconds": 120}}
    )
    assert explicit is not None
    assert explicit.clock_skew_seconds == 60
    assert explicit.replay_ttl_seconds == 120


@pytest.mark.parametrize(
    "case",
    ["retired-replay-mode", "unknown-replay-mode", "wrong-provider-kind"],
)
def test_local_coding_registry_resolution_fails_closed_for_stale_contract(case: str) -> None:
    if case == "wrong-provider-kind":
        with pytest.raises(ProviderConfigurationError) as exc_info:
            resolve_server_module("local-model", "openai", ROUTE_CAPABILITIES)
        assert exc_info.value.error_code == "local_coding_provider_kind_invalid"
        return
    replay_mode = "process_local_ttl_lru" if case == "retired-replay-mode" else "process_local_lru"
    with pytest.raises(ProviderConfigurationError) as exc_info:
        resolve_server_module(
            "local-model",
            "openai_compatible",
            {"local_coding": {**ROUTE_CAPABILITIES["local_coding"], "replay_mode": replay_mode}},
        )
    assert exc_info.value.error_code == "local_coding_route_contract_invalid"


def test_local_coding_server_module_version_two_selects_only_exact_contract() -> None:
    descriptor = SERVER_MODULE_REGISTRY[LOCAL_CODING_SERVER_MODULE_ID][0]
    assert descriptor.module_id == LOCAL_CODING_SERVER_MODULE_ID
    assert descriptor.module_version == LOCAL_CODING_SERVER_MODULE_VERSION
    assert LOCAL_CODING_SERVER_MODULE_VERSION == "2"
    resolved = resolve_server_module("local-model", "openai_compatible", ROUTE_CAPABILITIES)
    assert resolved.module_id == LOCAL_CODING_SERVER_MODULE_ID
    assert resolved.module_version == LOCAL_CODING_SERVER_MODULE_VERSION


@pytest.mark.parametrize(
    "deployment_mode",
    ["multi_worker", "cluster", None],
    ids=["multi-worker", "cluster", "missing"],
)
def test_local_coding_deployment_mode_is_single_worker_only(deployment_mode: str | None) -> None:
    contract_dict = dict(ROUTE_CAPABILITIES["local_coding"])
    if deployment_mode is None:
        contract_dict.pop("deployment_mode")
    else:
        contract_dict["deployment_mode"] = deployment_mode
    with pytest.raises(ValueError, match="deployment mode|incomplete or contains unknown fields"):
        parse_local_coding_route_contract({"local_coding": contract_dict})


def test_local_coding_replay_authority_fixture_pins_exact_source_facts() -> None:
    assert hashlib.sha256(REPLAY_AUTHORITY_FIXTURE.read_bytes()).hexdigest() == (
        "da6a9423d4d028e218270329d083550a7c7c552d8877312e5d291b574fc4893d"
    )
    fixture = json.loads(REPLAY_AUTHORITY_FIXTURE.read_text(encoding="utf-8"))
    assert fixture["source"] == {
        "repository": "ulfe-lmi/slaif-local-coding",
        "merged_main": "efc4dbcd377dd796a670726b16ebc06bd54b6356",
        "merged_main_tree": "68144646615cf8aec954f737261060f1b1601033",
        "implementation_commit": "4e1f07adc5d71c3f17e71b73cb57aec76aa28d9a",
        "report_commit": "67d895b9666a7b59753c4a373a6d15bc5884e099",
        "report_path": "oap/reports/006-a-signed-request-replay-hardening.md",
        "gateway_identity_py_sha256": "8ea6e63920d3a3e4db6d80c1bed7300cacf21e74a7e3d359583dad5694cdd4b5",
        "config_py_sha256": "871c4336068c2e27dad1cae0a5a0f036c4e43e00300b28b2e44d8f4418ee4a6e",
        "report_sha256": "3df009a5d95fdfda3413e69f2c2293bfca991ce6d7fa2d9bde5824a808ae161b",
        "handoff_comment": "https://github.com/ulfe-lmi/slaif-api-gateway/pull/299#issuecomment-5649192000",
    }
    assert fixture["capability"]["replay_mode"] == LOCAL_CODING_REPLAY_MODE
    assert fixture["capability"]["rejected_replay_mode"] == "process_local_ttl_lru"
    assert fixture["semantics"]["retention"] == (
        "each admitted SHA-256 nonce digest is retained through the inclusive effective "
        "horizon max(admission_time + replay_ttl_seconds, signed_timestamp + clock_skew_seconds)"
    )
    assert fixture["semantics"]["reclamation"] == (
        "only when the current time is strictly later than the retained expiry"
    )
    assert fixture["semantics"]["live_digest_eviction"] == "never"
    assert fixture["semantics"]["capacity_full"] == (
        "fail closed with 503 signed_identity_replay_capacity_unavailable"
    )
    assert fixture["semantics"]["unsafe_wall_clock"] == (
        "fail closed with 503 signed_identity_clock_unavailable on non-finite or backward observation"
    )
    assert fixture["semantics"]["known_replay"] == (
        "distinct closed outcome with 409 signed_identity_replayed"
    )
    assert fixture["peer_defaults"] == {
        "clock_skew_seconds": 60,
        "replay_ttl_seconds": 60,
        "max_replay_entries": 4096,
        "nonce_min_length": 16,
        "nonce_max_length": 128,
    }
    assert fixture["peer_bounds"] == {
        "clock_skew_seconds": [1, 300],
        "replay_ttl_seconds": [1, 86_400],
    }
    assert fixture["wire"]["identity_mode"] == "signed_identity_v1"
    assert fixture["wire"]["identity_version"] == "v1"
    assert fixture["wire"]["signature_format"] == "v1=<64 lowercase hex hmac-sha256>"
    assert fixture["limitations"] == [
        "digest-only state",
        "bounded process-local store",
        "single worker/process",
        "non-durable",
        "state resets on restart",
    ]
    assert (
        "does not configure, verify, or replicate peer replay state"
        in fixture["ownership"]["gateway"]
    )
    assert "owns nonce admission" in fixture["ownership"]["local"]


def test_objective_164_obligation_map_is_literal_and_complete() -> None:
    obligation_ids = set(LOCAL_CODING_REPLAY_OBLIGATION_TO_TEST_NODE)
    assert obligation_ids == LOCAL_CODING_REPLAY_REQUIRED_OBLIGATION_IDS
    assert len(obligation_ids) == len(LOCAL_CODING_REPLAY_OBLIGATION_TO_TEST_NODE)
    assert all("[" not in key for key in obligation_ids)
    assert all(
        value.startswith("tests/") for value in LOCAL_CODING_REPLAY_OBLIGATION_TO_TEST_NODE.values()
    )
    assert all("<" not in value for value in LOCAL_CODING_REPLAY_OBLIGATION_TO_TEST_NODE.values())

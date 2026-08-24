from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest
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
from slaif_gateway.modules.servers.registry import resolve_server_module
from slaif_gateway.providers.errors import ProviderConfigurationError
from slaif_gateway.schemas.providers import ProviderRequest

FIXTURE = Path("tests/fixtures/local_coding/signed_identity_v1_vectors.json")
SIGNING_SECRET = "local-coding-signing-secret-012345678901"
DERIVATION_SECRET = "local-coding-derivation-secret-0123456789"
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
    identity = derive_request_identity(
        owner_id="owner-uuid",
        identity_hints={"session_id": "thread-private"},
        repository_scope="repo-scope",
        route=contract,
        derivation_secret=DERIVATION_SECRET.encode(),
    )
    assert identity is not None
    assert "owner-uuid" not in identity.principal
    assert "thread-private" not in identity.session
    assert "repo-scope" not in identity.repository
    for hints, repository in (({}, "repo-scope"), ({"session_id": "a", "thread_id": "b"}, "repo-scope"), ({"session_id": "a"}, None)):
        with pytest.raises(ValueError):
            derive_request_identity(
                owner_id="owner-uuid",
                identity_hints=hints,
                repository_scope=repository,
                route=contract,
                derivation_secret=DERIVATION_SECRET.encode(),
            )


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
            api_key="service-bearer-secret",
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
    assert request.headers["authorization"] == "Bearer service-bearer-secret"
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

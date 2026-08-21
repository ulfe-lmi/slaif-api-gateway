from __future__ import annotations

import copy
import json
import tomllib
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import verify_codex_profile as profile_verifier
from slaif_gateway.services.codex_qualification import (
    CODEX_COMPACT_ENDPOINT,
    CODEX_FIXTURE_SHA256,
    CODEX_MODEL,
    CODEX_PROFILE_ID,
    CODEX_PROFILE_METADATA_VERSION,
    CODEX_QUALIFICATION_METADATA,
    CODEX_RESPONSES_ENDPOINT,
    CODEX_RESPONSES_POLICY,
    CodexQualificationService,
    parse_codex_qualification_metadata,
    parse_codex_profile_metadata,
    render_codex_profile,
    render_codex_profile_text,
    validate_codex_gateway_base_url,
    validate_codex_pilot_key_input,
)
from slaif_gateway.services.responses_route_capabilities import (
    enforce_responses_route_capabilities,
)

NOW = datetime(2026, 8, 18, tzinfo=UTC)


def _capabilities(companion: uuid.UUID) -> dict[str, object]:
    return {
        "responses": {
            "text": True,
            "stateless": True,
            "streaming": True,
            "compact": True,
            "codex_request_envelope": True,
            "codex_client_tools": True,
            "codex_streaming_tool_events": True,
            "codex_encrypted_reasoning_replay": True,
            "codex_compaction": True,
        },
        "codex_limits": {
            "context_window_tokens": 1_050_000,
            "default_max_output_tokens": 32_768,
            "max_output_tokens": 128_000,
        },
        "codex_compaction_compatible_route_ids": [str(companion)],
        "codex_qualification": copy.deepcopy(CODEX_QUALIFICATION_METADATA),
    }


def _v2_capabilities(companion: uuid.UUID) -> dict[str, object]:
    capabilities = _capabilities(companion)
    capabilities.pop("codex_qualification")
    capabilities["codex_profile"] = {
        "version": CODEX_PROFILE_METADATA_VERSION,
        "profile_id": CODEX_PROFILE_ID,
        "fixture_sha256": CODEX_FIXTURE_SHA256,
    }
    return capabilities


def _pair(**responses_overrides: object) -> tuple[SimpleNamespace, SimpleNamespace]:
    responses_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    compact_id = uuid.UUID("22222222-2222-4222-8222-222222222222")
    common = {
        "requested_model": CODEX_MODEL,
        "match_type": "exact",
        "provider": "openai",
        "upstream_model": CODEX_MODEL,
        "priority": 10,
        "enabled": True,
        "visible_in_models": True,
        "supports_streaming": True,
    }
    responses = SimpleNamespace(
        **common,
        id=responses_id,
        endpoint=CODEX_RESPONSES_ENDPOINT,
        capabilities=_capabilities(compact_id),
    )
    for key, value in responses_overrides.items():
        setattr(responses, key, value)
    compact_values = {
        **common,
        "id": compact_id,
        "endpoint": CODEX_COMPACT_ENDPOINT,
        "visible_in_models": False,
        "supports_streaming": False,
        "capabilities": _capabilities(responses_id),
    }
    compact = SimpleNamespace(**compact_values)
    return responses, compact


def _pricing(endpoint: str, *, currency: str = "EUR", **overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "provider": "openai",
        "upstream_model": CODEX_MODEL,
        "endpoint": endpoint,
        "currency": currency,
        "input_price_per_1m": Decimal("1"),
        "cached_input_price_per_1m": Decimal("0.5"),
        "output_price_per_1m": Decimal("2"),
        "reasoning_price_per_1m": Decimal("2"),
        "pricing_metadata": {
            "codex_accounting": {
                "long_context_threshold_tokens": 272_000,
                "long_context_input_multiplier": "2",
                "long_context_output_multiplier": "1.5",
                "cache_write_input_multiplier": "1.25",
            }
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _Routes:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    async def list_model_routes(self, *, limit: int = 100, offset: int = 0) -> list[object]:
        assert (limit, offset) == (1000, 0)
        return self.rows


class _Providers:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled

    async def list_provider_configs(self, **kwargs: object) -> list[object]:
        assert kwargs == {"limit": 1000, "offset": 0}
        return [SimpleNamespace(provider="openai", enabled=self.enabled)]


class _Pricing:
    def __init__(self, rows: dict[str, object | None] | None = None) -> None:
        self.rows = rows or {
            CODEX_RESPONSES_ENDPOINT: _pricing(CODEX_RESPONSES_ENDPOINT),
            CODEX_COMPACT_ENDPOINT: _pricing(CODEX_COMPACT_ENDPOINT),
        }

    async def find_active_pricing_rule(self, **kwargs: object) -> object | None:
        assert kwargs["provider"] == "openai"
        assert kwargs["upstream_model"] == CODEX_MODEL
        assert kwargs["at_time"] == NOW
        return self.rows.get(str(kwargs["endpoint"]))


class _Fx:
    def __init__(self, row: object | None = None) -> None:
        self.row = row
        self.calls: list[dict[str, object]] = []

    async def find_latest_rate(self, **kwargs: object) -> object | None:
        self.calls.append(kwargs)
        return self.row


def _service(
    rows: list[object],
    *,
    provider_enabled: bool = True,
    pricing: _Pricing | None = None,
    fx: _Fx | None = None,
) -> CodexQualificationService:
    return CodexQualificationService(
        provider_configs_repository=_Providers(enabled=provider_enabled),
        model_routes_repository=_Routes(rows),
        pricing_rules_repository=pricing or _Pricing(),
        fx_rates_repository=fx or _Fx(),
    )


@pytest.mark.asyncio
async def test_exact_route_pair_is_protocol_qualified_and_safe() -> None:
    responses, compact = _pair()

    results = await _service([compact, responses]).inspect(now=NOW)

    assert [result.endpoint for result in results] == [
        CODEX_RESPONSES_ENDPOINT,
        CODEX_COMPACT_ENDPOINT,
    ]
    assert all(result.state == "protocol_qualified" for result in results)
    assert all(result.reason_codes == () for result in results)
    selected = await _service([responses, compact]).ready_responses_profile(now=NOW)
    assert selected.route_id == responses.id
    assert selected.paired_route_id == compact.id
    payload = selected.to_safe_dict()
    assert payload["cli_version"] == "0.147.0"
    assert payload["real_provider_e2e"] is False
    assert set(payload) == {
        "state",
        "requested_model",
        "provider",
        "endpoint",
        "route_id",
        "paired_route_id",
        "reason_codes",
        "profile_version",
        "cli_version",
        "profile",
        "catalog_source",
        "wire_api",
        "real_provider_e2e",
        "profile_id",
        "metadata_version",
        "ready",
    }


def test_positive_pair_maps_are_accepted_by_exact_runtime_operations() -> None:
    responses, compact = _pair()

    enforce_responses_route_capabilities(
        route_capabilities=responses.capabilities,
        streaming_requested=True,
        route_supports_streaming=True,
        codex_request_envelope_requested=True,
        codex_client_tools_requested=True,
        codex_streaming_tool_events_requested=True,
        codex_encrypted_reasoning_replay_requested=True,
        codex_extended_limits_requested=True,
        codex_compaction_requested=True,
    )
    enforce_responses_route_capabilities(
        route_capabilities=compact.capabilities,
        compact_requested=True,
        codex_request_envelope_requested=True,
        codex_client_tools_requested=True,
        codex_streaming_tool_events_requested=True,
        codex_encrypted_reasoning_replay_requested=True,
        codex_extended_limits_requested=True,
        codex_compaction_requested=True,
    )


@pytest.mark.parametrize("target_endpoint", [CODEX_RESPONSES_ENDPOINT, CODEX_COMPACT_ENDPOINT])
@pytest.mark.parametrize("mutation", ["missing_text", "false_text", "unknown", "non_boolean"])
@pytest.mark.asyncio
async def test_runtime_rejected_nested_responses_maps_cannot_qualify(
    target_endpoint: str,
    mutation: str,
) -> None:
    responses, compact = _pair()
    target = responses if target_endpoint == CODEX_RESPONSES_ENDPOINT else compact
    nested = target.capabilities["responses"]
    assert isinstance(nested, dict)
    if mutation == "missing_text":
        nested.pop("text")
    elif mutation == "false_text":
        nested["text"] = False
    elif mutation == "unknown":
        nested["unknown_runtime_flag"] = True
    else:
        nested["text"] = "true"

    results = await _service([responses, compact]).inspect(now=NOW)

    selected = next(result for result in results if result.endpoint == target_endpoint)
    assert selected.state == "not_ready"
    assert "responses_runtime_capabilities_invalid" in selected.reason_codes


@pytest.mark.asyncio
async def test_missing_and_non_exact_metadata_fail_closed_without_model_inference() -> None:
    responses, compact = _pair()
    responses.capabilities.pop("codex_qualification")
    compact.capabilities["codex_qualification"]["real_provider_e2e"] = True

    results = await _service([responses, compact]).inspect(now=NOW)

    by_endpoint = {result.endpoint: result for result in results}
    assert by_endpoint[CODEX_RESPONSES_ENDPOINT].state == "not_declared"
    assert by_endpoint[CODEX_RESPONSES_ENDPOINT].reason_codes == (
        "codex_qualification_not_declared",
    )
    assert by_endpoint[CODEX_COMPACT_ENDPOINT].state == "invalid"
    assert by_endpoint[CODEX_COMPACT_ENDPOINT].reason_codes == ("codex_qualification_invalid",)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"unknown": False}),
        lambda value: value.pop("fixture_sha256"),
        lambda value: value.update({"profile_version": True}),
        lambda value: value.update({"model": "alias"}),
        lambda value: value.update({"fixture_sha256": CODEX_FIXTURE_SHA256.upper()}),
    ],
)
def test_metadata_parser_rejects_unknown_partial_coerced_and_alias_values(mutate) -> None:
    value = copy.deepcopy(CODEX_QUALIFICATION_METADATA)
    mutate(value)
    assert parse_codex_qualification_metadata({"codex_qualification": value}) == "invalid"


@pytest.mark.asyncio
async def test_known_v2_profile_pair_is_qualified_without_route_capability_authority() -> None:
    responses, compact = _pair()
    responses.capabilities = _v2_capabilities(compact.id)
    compact.capabilities = _v2_capabilities(responses.id)
    results = await _service([responses, compact]).inspect(now=NOW)
    assert all(result.state == "protocol_qualified" for result in results)
    assert all(result.profile_id == CODEX_PROFILE_ID for result in results)
    assert all(result.metadata_version == CODEX_PROFILE_METADATA_VERSION for result in results)
    assert all("metadata v2" in result.badge for result in results)
    assert parse_codex_profile_metadata(responses.capabilities) == (
        "protocol_qualified",
        CODEX_PROFILE_ID,
        CODEX_PROFILE_METADATA_VERSION,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "declaration",
    [
        {"version": 2, "profile_id": "unknown-profile", "fixture_sha256": "0" * 64},
        {
            "version": 2,
            "profile_id": CODEX_PROFILE_ID,
            "fixture_sha256": "0" * 64,
        },
        {
            "version": 2,
            "profile_id": CODEX_PROFILE_ID,
            "fixture_sha256": CODEX_FIXTURE_SHA256,
            "extra": "rejected",
        },
    ],
)
async def test_v2_unknown_or_drifted_profile_fails_closed(declaration: dict[str, object]) -> None:
    responses, compact = _pair()
    responses.capabilities = _v2_capabilities(compact.id)
    compact.capabilities = _v2_capabilities(responses.id)
    responses.capabilities["codex_profile"] = declaration
    result = next(
        item
        for item in await _service([responses, compact]).inspect(now=NOW)
        if item.route_id == responses.id
    )
    assert result.state in {"invalid", "not_ready"}
    assert result.reason_codes[0].startswith("codex_profile_")


@pytest.mark.asyncio
async def test_route_pair_requirements_emit_only_fixed_reason_codes() -> None:
    responses, compact = _pair(enabled=False)
    responses.visible_in_models = False
    responses.supports_streaming = False
    responses.capabilities["responses"]["codex_client_tools"] = False
    compact.capabilities["codex_compaction_compatible_route_ids"] = []

    result = (await _service([responses, compact], provider_enabled=False).inspect(now=NOW))[0]

    assert result.state == "not_ready"
    assert set(result.reason_codes) >= {
        "route_disabled",
        "codex_gates_incomplete",
        "responses_route_not_visible",
        "responses_route_not_streaming",
        "provider_disabled",
    }
    assert all(
        "openai" not in reason and CODEX_MODEL not in reason for reason in result.reason_codes
    )


@pytest.mark.asyncio
async def test_pair_must_be_reciprocal_and_pricing_must_be_complete() -> None:
    responses, compact = _pair()
    compact.capabilities["codex_compaction_compatible_route_ids"] = [str(uuid.uuid4())]
    pricing = _Pricing(
        {
            CODEX_RESPONSES_ENDPOINT: _pricing(
                CODEX_RESPONSES_ENDPOINT,
                cached_input_price_per_1m=None,
            ),
            CODEX_COMPACT_ENDPOINT: None,
        }
    )

    result = (await _service([responses, compact], pricing=pricing).inspect(now=NOW))[0]

    assert result.state == "not_ready"
    assert "paired_route_not_reciprocal" in result.reason_codes
    assert "pricing_invalid_responses" in result.reason_codes
    assert "pricing_missing_compact" in result.reason_codes


@pytest.mark.asyncio
async def test_qualified_pair_must_be_selected_by_provider_constrained_runtime_ranking() -> None:
    responses, compact = _pair()
    shadow = SimpleNamespace(
        id=uuid.uuid4(),
        requested_model=CODEX_MODEL,
        match_type="exact",
        endpoint=CODEX_RESPONSES_ENDPOINT,
        provider="openai",
        upstream_model="unqualified-shadow",
        priority=1,
        enabled=True,
        visible_in_models=True,
        supports_streaming=True,
        capabilities={},
    )
    service = _service([responses, compact, shadow])

    results = await service.inspect(now=NOW)

    by_id = {result.route_id: result for result in results}
    assert "route_not_selected" in by_id[responses.id].reason_codes
    assert "paired_route_not_selected" in by_id[compact.id].reason_codes
    with pytest.raises(ValueError, match="Exactly one ready"):
        await service.ready_responses_profile(now=NOW)


@pytest.mark.asyncio
async def test_non_eur_pricing_requires_active_positive_fx() -> None:
    responses, compact = _pair()
    pricing = _Pricing(
        {
            CODEX_RESPONSES_ENDPOINT: _pricing(CODEX_RESPONSES_ENDPOINT, currency="USD"),
            CODEX_COMPACT_ENDPOINT: _pricing(CODEX_COMPACT_ENDPOINT, currency="USD"),
        }
    )
    missing_fx = _Fx()

    result = (
        await _service([responses, compact], pricing=pricing, fx=missing_fx).inspect(now=NOW)
    )[0]

    assert result.state == "not_ready"
    assert "fx_missing_responses" in result.reason_codes
    assert "fx_missing_compact" in result.reason_codes
    assert missing_fx.calls[0]["base_currency"] == "USD"

    valid_fx = _Fx(SimpleNamespace(rate=Decimal("0.92")))
    ready = (await _service([responses, compact], pricing=pricing, fx=valid_fx).inspect(now=NOW))[0]
    assert ready.state == "protocol_qualified"


def test_profile_v2_artifacts_parse_independently_and_are_credential_free() -> None:
    artifacts = render_codex_profile("https://Gateway.Example.org/edge/v1")

    base = tomllib.loads(artifacts.base_config_toml)
    profile = tomllib.loads(artifacts.profile_config_toml)
    assert base == {
        "model_providers": {
            "slaif": {
                "name": "OpenAI",
                "base_url": "https://gateway.example.org/edge/v1",
                "env_key": "OPENAI_API_KEY",
                "wire_api": "responses",
                "requires_openai_auth": False,
                "supports_websockets": False,
            }
        }
    }
    assert profile == {
        "model": CODEX_MODEL,
        "model_provider": "slaif",
        "features": {"remote_compaction_v2": False},
    }
    combined = artifacts.base_config_toml + artifacts.profile_config_toml
    assert "model_catalog_json" not in combined
    assert "[profiles" not in combined
    assert 'profile = "slaif"' not in combined
    assert "sk-" not in combined
    safe_json = json.dumps(artifacts.to_safe_dict(), sort_keys=True)
    assert "$CODEX_HOME/config.toml" in safe_json
    assert "$CODEX_HOME/slaif.config.toml" in safe_json
    assert "gateway-issued" not in safe_json


def test_profile_text_marks_merge_and_complete_targets_without_combining_toml() -> None:
    output = render_codex_profile_text(render_codex_profile("https://gateway.example.org/v1"))
    assert "Merge this fragment into $CODEX_HOME/config.toml" in output
    assert "Place this complete content in $CODEX_HOME/slaif.config.toml" in output
    assert "Set the gateway-issued key only in OPENAI_API_KEY" in output
    assert "Run: codex --profile slaif" in output
    assert "one TOML" not in output


def test_manual_profile_verifier_helpers_apply_profile_without_selection_overrides() -> None:
    artifacts = render_codex_profile("http://127.0.0.1:8123/v1")
    profile_verifier.validate_profile_documents(artifacts)

    command = profile_verifier.build_codex_command(workdir=Path("/tmp/work"))

    assert command[:6] == [
        "/usr/bin/codex",
        "--ask-for-approval",
        "never",
        "--profile",
        "slaif",
        "exec",
    ]
    assert "--ignore-user-config" not in command
    assert not any(value.startswith("model=") for value in command)
    assert not any(value.startswith("model_provider=") for value in command)
    assert "model_catalog_json" not in "\n".join(command)


def test_manual_profile_verifier_reduces_request_to_safe_facts() -> None:
    request = profile_verifier.capture.ParsedHttpRequest(
        method="POST",
        target="/v1/responses",
        version="HTTP/1.1",
        headers=(
            ("content-type", "application/json"),
            ("authorization", "Bearer fixed-dummy"),
        ),
        body=json.dumps({"model": CODEX_MODEL, "stream": True}).encode(),
    )

    facts = profile_verifier.validate_request(request)

    assert facts == profile_verifier.RequestFacts(
        model_matched=True,
        content_encoding_absent=True,
        authorization_present=True,
        streamed_responses_json=True,
    )


def test_manual_profile_verifier_rejects_every_argument_without_reflection() -> None:
    for arguments in (
        ["--base-url", "http://127.0.0.1:8123/v1"],
        ["--unknown"],
        ["sk-sensitive-operator-text"],
    ):
        with pytest.raises(
            profile_verifier.VerificationError,
            match=r"^Verifier accepts no arguments\.$",
        ) as exc_info:
            profile_verifier.parse_verifier_arguments(arguments)
        assert all(argument not in str(exc_info.value) for argument in arguments)


@pytest.mark.parametrize(
    "value",
    [
        "http://127.0.0.1:8123/v1",
        "http://[::1]:8123/v1",
        "https://gateway.example.org/v1",
        "https://gateway.example.org/prefix/v1",
    ],
)
def test_base_url_accepts_https_and_numeric_loopback_http(value: str) -> None:
    assert validate_codex_gateway_base_url(value).endswith("/v1")


@pytest.mark.parametrize(
    "value",
    [
        "http://gateway.example.org/v1",
        "https://user:password@gateway.example.org/v1",
        "https://gateway.example.org/v1?api_key=value",
        "https://gateway.example.org/v1#fragment",
        "https://gateway.example.org/v1/",
        "https://gateway.example.org/v2",
        "https://gateway.example.org/a/../v1",
        "https://gateway.example.org/%2e%2e/v1",
        "https://gateway.example.org//v1",
        "https://gateway.example.org\\evil/v1",
        "https://gateway .example.org/v1",
        "https://gateway.example.org/path with space/v1",
        " https://gateway.example.org/v1",
        "https://gateway.example.org/v1\n",
        "https://gateway.example.org/sk-proj-abcdefghijklmnop/v1",
    ],
)
def test_base_url_rejects_unsafe_or_noncanonical_values(value: str) -> None:
    with pytest.raises(ValueError):
        validate_codex_gateway_base_url(value)


def _pilot_payload(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "key_purpose": "standard",
        "allow_all_models": False,
        "allow_all_endpoints": False,
        "allowed_providers": ["openai"],
        "allowed_models": [CODEX_MODEL],
        "allowed_endpoints": [
            "/v1/models",
            CODEX_RESPONSES_ENDPOINT,
            CODEX_COMPACT_ENDPOINT,
        ],
        "request_limit_total": 10,
        "token_limit_total": 100_000,
        "cost_limit_eur": Decimal("5"),
        "note": "reviewed pilot",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_pilot_key_validation_and_policy_are_exact() -> None:
    validate_codex_pilot_key_input(_pilot_payload(), confirmed=True)
    assert CODEX_RESPONSES_POLICY == {
        "version": 1,
        "allowed_capabilities": [
            "codex_request_envelope",
            "codex_client_tools",
            "codex_streaming_tool_events",
            "codex_encrypted_reasoning_replay",
            "codex_compaction",
        ],
        "allowed_local_tool_types": ["function", "custom"],
    }


@pytest.mark.parametrize(
    ("overrides", "confirmed"),
    [
        ({}, False),
        ({"key_purpose": "trusted_calibration"}, True),
        ({"allow_all_models": True}, True),
        ({"allow_all_endpoints": True}, True),
        ({"allowed_providers": None}, True),
        ({"allowed_providers": ["openai", "openrouter"]}, True),
        ({"allowed_models": [CODEX_MODEL, "extra"]}, True),
        ({"allowed_endpoints": [CODEX_RESPONSES_ENDPOINT]}, True),
        ({"request_limit_total": None}, True),
        ({"token_limit_total": 0}, True),
        ({"cost_limit_eur": Decimal("NaN")}, True),
        ({"note": ""}, True),
    ],
)
def test_pilot_key_validation_rejects_unbounded_or_widened_policy(
    overrides: dict[str, object], confirmed: bool
) -> None:
    with pytest.raises(ValueError):
        validate_codex_pilot_key_input(_pilot_payload(**overrides), confirmed=confirmed)

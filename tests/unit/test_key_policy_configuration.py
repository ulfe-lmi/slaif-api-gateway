"""Typed key-policy configuration (196-a).

Covers the strict Responses/Codex authoring validator, the version-1
configuration schema (safe file errors, exact money, presence semantics),
the shared group helpers, and the KeyService update/export laws (partial
preservation, migration law, rate vocabulary, fenced confirmations,
rollback, and the secret-safe audit projection).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaif_gateway.modules.clients.codex_0147 import CODEX_0147_CLIENT_MODULE_ID
from slaif_gateway.modules.clients.codex_0149 import CODEX_0149_CLIENT_MODULE_ID
from slaif_gateway.modules.clients.codex_0162 import (
    CODEX_0162_CLIENT_MODULE_ID,
    CODEX_0162_V1_CLIENT_MODULE,
)
from slaif_gateway.modules.clients.registry import client_module_metadata, get_client_module
from slaif_gateway.schemas.key_configuration import (
    ABSENT,
    KEY_CONFIGURATION_SCHEMA_VERSION,
    MAX_KEY_CONFIGURATION_FILE_BYTES,
    KeyConfiguration,
    KeyConfigurationError,
    key_configuration_export,
    parse_key_configuration,
    parse_key_configuration_file,
)
from slaif_gateway.schemas.keys import UpdateGatewayKeyConfigurationInput
from slaif_gateway.services.key_errors import (
    GatewayKeyNotFoundError,
    InvalidGatewayKeyLimitsError,
    InvalidGatewayKeyPolicyError,
)
from slaif_gateway.services.key_policy_configuration import (
    UNBOUND,
    KeyConfigurationExportError,
    canonical_rate_policy_members,
    proposed_matches_stored_binding,
    quota_group_values,
    request_policy_group_values,
    stored_module_binding,
)
from slaif_gateway.services.responses_policy_validation import (
    MIGRATION_HINT,
    SUPPORTED_RESPONSES_CAPABILITIES,
    validate_key_responses_policy,
)
from tests.unit.key_management_fakes import FakeGatewayKeyRow, make_key_service

PIN_0162 = client_module_metadata(get_client_module(CODEX_0162_CLIENT_MODULE_ID))
PIN_0147 = client_module_metadata(get_client_module(CODEX_0147_CLIENT_MODULE_ID))
PIN_0149 = client_module_metadata(get_client_module(CODEX_0149_CLIENT_MODULE_ID))
STALE_0162_V1 = dict(CODEX_0162_V1_CLIENT_MODULE)

OWNER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


# --------------------------------------------------------------------------
# R4 strict Responses/Codex authoring validator
# --------------------------------------------------------------------------


def test_validator_accepts_four_grant_codex_policy_with_current_pin() -> None:
    canonical = validate_key_responses_policy(
        {
            "version": 1,
            "allowed_capabilities": [
                "codex_request_envelope",
                "codex_client_tools",
                "codex_streaming_tool_events",
                "codex_encrypted_reasoning_replay",
            ],
            "allowed_local_tool_types": ["custom", "function"],
            "client_module": dict(PIN_0162),
        }
    )
    assert canonical is not None
    assert canonical["allowed_capabilities"] == sorted(
        [
            "codex_request_envelope",
            "codex_client_tools",
            "codex_streaming_tool_events",
            "codex_encrypted_reasoning_replay",
        ]
    )
    assert canonical["allowed_local_tool_types"] == ["function", "custom"]
    assert canonical["client_module"] == PIN_0162
    # Canonical output is idempotent.
    assert validate_key_responses_policy(canonical) == canonical


def test_validator_accepts_envelope_only_grant_with_retained_pin() -> None:
    # A pin never grants authority by itself; an envelope-only grant with a
    # pin is a valid (minimal) authoring state.
    canonical = validate_key_responses_policy(
        {
            "version": 1,
            "allowed_capabilities": ["codex_request_envelope"],
            "client_module": dict(PIN_0162),
        }
    )
    assert canonical is not None
    assert canonical["client_module"] == PIN_0162
    assert "allowed_local_tool_types" not in canonical


def test_validator_accepts_retained_pin_without_capabilities() -> None:
    # Deauthorization state: same pin, no grants.
    canonical = validate_key_responses_policy(
        {
            "version": 1,
            "allowed_capabilities": [],
            "client_module": dict(PIN_0162),
        }
    )
    assert canonical is not None
    assert canonical == {"version": 1, "client_module": PIN_0162}


def test_validator_rejects_float_and_bool_versions() -> None:
    for bad_version in (1.0, True):
        with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
            validate_key_responses_policy({"version": bad_version})
        assert exc.value.param == "responses_policy.version"


def test_validator_rejects_unknown_fields_without_echoing_them() -> None:
    canary = "SYNTHETIC_OPERATOR_PRIVATE_TEXT_196"
    with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
        validate_key_responses_policy({"version": 1, "not_a_field": canary})
    assert "Responses policy contains unsupported fields." in str(exc.value)
    assert canary not in str(exc.value)


def test_validator_rejects_reserved_generic_authority_capabilities() -> None:
    for reserved in ("background", "storage", "multimodal"):
        with pytest.raises(InvalidGatewayKeyPolicyError):
            validate_key_responses_policy(
                {"version": 1, "allowed_capabilities": [reserved]}
            )
    # The reserved names are excluded from the finite supported vocabulary.
    assert not {"background", "storage", "multimodal"} & SUPPORTED_RESPONSES_CAPABILITIES


def test_validator_rejects_unknown_and_duplicate_capabilities() -> None:
    with pytest.raises(InvalidGatewayKeyPolicyError):
        validate_key_responses_policy(
            {"version": 1, "allowed_capabilities": ["definitely_not_a_capability"]}
        )
    with pytest.raises(InvalidGatewayKeyPolicyError):
        validate_key_responses_policy(
            {"version": 1, "allowed_capabilities": ["text", "text"]}
        )


def test_validator_enforces_codex_prerequisite_closure() -> None:
    # client_tools requires envelope.
    with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
        validate_key_responses_policy(
            {"version": 1, "allowed_capabilities": ["codex_client_tools"]}
        )
    assert "codex_request_envelope" in str(exc.value)
    # compaction requires streaming tool events plus encrypted replay
    # (and their transitive prerequisites).
    with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
        validate_key_responses_policy(
            {"version": 1, "allowed_capabilities": ["codex_compaction"]}
        )
    assert "codex_streaming_tool_events" in str(exc.value)
    assert "codex_encrypted_reasoning_replay" in str(exc.value)


def test_validator_pairs_local_tool_types_with_reviewed_capabilities() -> None:
    with pytest.raises(InvalidGatewayKeyPolicyError):
        validate_key_responses_policy(
            {
                "version": 1,
                "allowed_capabilities": ["text"],
                "allowed_local_tool_types": ["function"],
            }
        )
    with pytest.raises(InvalidGatewayKeyPolicyError):
        validate_key_responses_policy(
            {
                "version": 1,
                "allowed_capabilities": ["custom_tools"],
                "allowed_local_tool_types": ["function"],
            }
        )
    # The Codex client-tools grant requires the FULL local tool type set.
    with pytest.raises(InvalidGatewayKeyPolicyError):
        validate_key_responses_policy(
            {
                "version": 1,
                "allowed_capabilities": [
                    "codex_request_envelope",
                    "codex_client_tools",
                ],
                "allowed_local_tool_types": ["function"],
            }
        )


def test_validator_rejects_malformed_or_unknown_client_module_pins() -> None:
    # Missing a pin member.
    with pytest.raises(InvalidGatewayKeyPolicyError):
        validate_key_responses_policy(
            {
                "version": 1,
                "client_module": {"id": PIN_0162["id"], "version": PIN_0162["version"]},
            }
        )
    # Unregistered module id: safe fixed message, no echo of the id.
    canary_id = "synthetic-unregistered-module-196"
    with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
        validate_key_responses_policy(
            {
                "version": 1,
                "client_module": {
                    "id": canary_id,
                    "version": "1",
                    "fixture_sha256": "0" * 64,
                },
            }
        )
    assert canary_id not in str(exc.value)
    assert exc.value.param == "responses_policy.client_module.id"


def test_validator_rejects_stale_pins_with_migration_hint() -> None:
    with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
        validate_key_responses_policy(
            {"version": 1, "allowed_capabilities": [], "client_module": dict(STALE_0162_V1)}
        )
    assert MIGRATION_HINT in str(exc.value)
    assert exc.value.param == "responses_policy.client_module"


def test_validator_preserves_inert_legacy_fields_verbatim_and_rejects_others() -> None:
    canonical = validate_key_responses_policy(
        {
            "version": 1,
            "allowed_capabilities": ["text"],
            "allowed_local_tool_types": [],
            "hosted_tools_allowed": [],
            "stateful": False,
            "storage": False,
            "background": False,
            "multimodal": False,
            "notes": "standard template shape",
        }
    )
    assert canonical is not None
    assert canonical["hosted_tools_allowed"] == []
    assert canonical["stateful"] is False
    assert canonical["storage"] is False
    assert canonical["background"] is False
    assert canonical["multimodal"] is False
    assert canonical["notes"] == "standard template shape"
    assert "allowed_local_tool_types" not in canonical

    with pytest.raises(InvalidGatewayKeyPolicyError):
        validate_key_responses_policy(
            {"version": 1, "hosted_tools_allowed": ["web_search"]}
        )
    for flag in ("stateful", "storage", "background", "multimodal"):
        with pytest.raises(InvalidGatewayKeyPolicyError):
            validate_key_responses_policy({"version": 1, flag: True})
    with pytest.raises(InvalidGatewayKeyPolicyError):
        validate_key_responses_policy({"version": 1, "notes": "x" * 1001})


def test_validator_accepts_reviewed_existing_producer_shapes() -> None:
    from slaif_gateway.services.key_template_service import (
        _normalize_responses_template_policy as template_producer,
    )

    base = {
        "hosted_tools_allowed": [],
        "stateful": False,
        "storage": False,
        "background": False,
        "multimodal": False,
    }
    # Standard template shape.
    standard = template_producer(
        {**base, "version": 1, "allowed_capabilities": ["text", "stateless"]}
    )
    assert validate_key_responses_policy(standard) is not None
    # Function variant.
    function = template_producer(
        {
            **base,
            "version": 1,
            "allowed_capabilities": ["text", "stateless", "function_tools"],
            "allowed_local_tool_types": ["function"],
        }
    )
    assert validate_key_responses_policy(function) is not None
    # Custom variant.
    custom = template_producer(
        {
            **base,
            "version": 1,
            "allowed_capabilities": ["text", "stateless", "custom_tools"],
            "allowed_local_tool_types": ["custom"],
        }
    )
    assert validate_key_responses_policy(custom) is not None
    # Full Codex template variant (the template producer hard-pins the
    # qualified 0147 identity; the key authoring validator accepts it).
    codex = template_producer(
        {
            **base,
            "version": 1,
            "allowed_capabilities": [
                "text",
                "stateless",
                "function_tools",
                "custom_tools",
                "codex_request_envelope",
                "codex_client_tools",
                "codex_streaming_tool_events",
                "codex_encrypted_reasoning_replay",
                "codex_compaction",
            ],
            "allowed_local_tool_types": ["function", "custom"],
        }
    )
    canonical = validate_key_responses_policy(codex)
    assert canonical is not None
    assert canonical["client_module"] == PIN_0147
    # Admin Qwen Codex producer shape: Codex gates plus image_input and the
    # current registered pin.
    qwen = {
        "version": 1,
        "allowed_capabilities": [
            "image_input",
            "codex_request_envelope",
            "codex_client_tools",
            "codex_streaming_tool_events",
            "codex_encrypted_reasoning_replay",
        ],
        "allowed_local_tool_types": ["function", "custom"],
        "client_module": dict(PIN_0162),
    }
    canonical = validate_key_responses_policy(qwen)
    assert canonical is not None
    assert "image_input" in canonical["allowed_capabilities"]


def test_validator_none_is_absent_and_empty_lists_are_inert() -> None:
    assert validate_key_responses_policy(None) is None
    canonical = validate_key_responses_policy(
        {
            "version": 1,
            "allowed_capabilities": None,
            "allowed_local_tool_types": [],
        }
    )
    assert canonical == {"version": 1}


# --------------------------------------------------------------------------
# Version-1 configuration schema: safe file errors and exact semantics
# --------------------------------------------------------------------------


def test_schema_minimal_document_and_absent_semantics() -> None:
    config = parse_key_configuration({"schema_version": 1})
    assert config.is_empty()
    assert not config.has("allowed_models")
    assert config.allowed_models is ABSENT


def test_schema_rejects_missing_and_wrong_version_without_echo() -> None:
    with pytest.raises(KeyConfigurationError):
        parse_key_configuration({})
    for bad_version in (2, 1.0, True, "1"):
        with pytest.raises(KeyConfigurationError):
            parse_key_configuration({"schema_version": bad_version})


def test_schema_rejects_unknown_fields_and_duplicate_keys() -> None:
    canary = "SYNTHETIC_OPERATOR_PRIVATE_TEXT_196"
    with pytest.raises(KeyConfigurationError) as exc:
        parse_key_configuration({"schema_version": 1, "totally_unknown": canary})
    assert canary not in str(exc.value)
    with pytest.raises(KeyConfigurationError):
        parse_key_configuration_file(
            b'{"schema_version": 1, "allowed_models": ["a"], "allowed_models": ["b"]}'
        )


def test_schema_rejects_nan_and_infinity() -> None:
    with pytest.raises(KeyConfigurationError):
        parse_key_configuration_file(b'{"schema_version": 1, "cost_limit_eur": NaN}')
    with pytest.raises(KeyConfigurationError):
        parse_key_configuration_file(b'{"schema_version": 1, "cost_limit_eur": Infinity}')


def test_schema_preserves_exact_money_decimal_through_export() -> None:
    config = parse_key_configuration({"schema_version": 1, "cost_limit_eur": "99999999.123456789"})
    assert config.cost_limit_eur == Decimal("99999999.123456789")
    export = key_configuration_export(config)
    assert export["cost_limit_eur"] == "99999999.123456789"
    # The export re-parses exactly.
    reparsed = parse_key_configuration(export)
    assert reparsed.cost_limit_eur == Decimal("99999999.123456789")


def test_schema_rejects_programmatic_float_costs() -> None:
    with pytest.raises(KeyConfigurationError):
        parse_key_configuration({"schema_version": 1, "cost_limit_eur": 12.5})


def test_schema_rate_members_positive_int_or_null_and_strict_vocabulary() -> None:
    config = parse_key_configuration(
        {
            "schema_version": 1,
            "rate_limit_policy": {"window_seconds": 45, "tokens_per_minute": None},
        }
    )
    assert config.rate_limit_policy == {"tokens_per_minute": None, "window_seconds": 45}
    with pytest.raises(KeyConfigurationError):
        parse_key_configuration(
            {"schema_version": 1, "rate_limit_policy": {"window_seconds": True}}
        )
    with pytest.raises(KeyConfigurationError):
        parse_key_configuration(
            {"schema_version": 1, "rate_limit_policy": {"window_seconds": 0}}
        )
    # Unknown members (and aliases with no canonical spelling) are rejected,
    # never silently ignored.
    with pytest.raises(KeyConfigurationError) as exc:
        parse_key_configuration(
            {"schema_version": 1, "rate_limit_policy": {"unrecognised_rate": 7}}
        )
    assert "unsupported fields" in str(exc.value)
    # The historical alias canonicalizes to the canonical member.
    aliased = parse_key_configuration(
        {"schema_version": 1, "rate_limit_policy": {"concurrent_requests": 5}}
    )
    assert aliased.rate_limit_policy == {"max_concurrent_requests": 5}
    # Alias + canonical spelling for one member is ambiguous.
    with pytest.raises(KeyConfigurationError) as exc:
        parse_key_configuration(
            {
                "schema_version": 1,
                "rate_limit_policy": {
                    "concurrent_requests": 5,
                    "max_concurrent_requests": 6,
                }
            }
        )
    assert "alias" in str(exc.value)


def test_schema_null_groups_keep_explicit_null() -> None:
    config = parse_key_configuration(
        {
            "schema_version": 1,
            "allowed_providers": None,
            "responses_policy": None,
            "rate_limit_policy": None,
            "lazy_throttling_policy": None,
            "cost_limit_eur": None,
        }
    )
    assert config.has("allowed_providers") and config.allowed_providers is None
    assert config.has("responses_policy") and config.responses_policy is None
    assert config.has("rate_limit_policy") and config.rate_limit_policy is None
    assert config.has("lazy_throttling_policy") and config.lazy_throttling_policy is None
    assert config.has("cost_limit_eur") and config.cost_limit_eur is None


def test_schema_file_size_bound_is_enforced() -> None:
    def padded(item_count: int) -> bytes:
        return json.dumps(
            {"schema_version": 1, "allowed_models": [f"m{i}" for i in range(item_count)]}
        ).encode()

    at_limit = padded(1)
    assert len(at_limit) <= MAX_KEY_CONFIGURATION_FILE_BYTES
    parse_key_configuration_file(at_limit)
    oversized = b'{"schema_version": 1, "pad": "' + b"p" * MAX_KEY_CONFIGURATION_FILE_BYTES + b'"}'
    assert len(oversized) > MAX_KEY_CONFIGURATION_FILE_BYTES
    with pytest.raises(KeyConfigurationError) as exc:
        parse_key_configuration_file(oversized)
    assert "exceeds" in str(exc.value).lower()
    assert "65536" in str(exc.value)
    assert b"p" * 100 not in str(exc.value).encode()


# --------------------------------------------------------------------------
# Shared group helpers
# --------------------------------------------------------------------------


def test_request_policy_group_values_merge_per_member_with_current() -> None:
    config = KeyConfiguration()
    config.allowed_models = ["new-model"]
    values = request_policy_group_values(
        config,
        current_allowed_models=["old-model"],
        current_allow_all_models=False,
        current_allowed_endpoints=["/v1/chat/completions"],
        current_allow_all_endpoints=False,
    )
    allowed_models, allow_all_models, allowed_endpoints, allow_all_endpoints = values
    assert allowed_models == ["new-model"]
    assert allow_all_models is False
    assert allowed_endpoints == ["/v1/chat/completions"]
    assert allow_all_endpoints is False


def test_quota_group_values_replace_only_present_members() -> None:
    config = KeyConfiguration()
    config.cost_limit_eur = Decimal("5")
    values = quota_group_values(
        config,
        current_cost_limit_eur=Decimal("25"),
        current_token_limit_total=100_000,
        current_request_limit_total=1_000,
    )
    assert values == (Decimal("5"), 100_000, 1_000)


def test_canonical_rate_policy_members_rejects_unknown_and_ambiguity() -> None:
    assert canonical_rate_policy_members(None) == {}
    assert canonical_rate_policy_members({"concurrent_requests": 5}) == {
        "max_concurrent_requests": 5
    }
    with pytest.raises(InvalidGatewayKeyLimitsError):
        canonical_rate_policy_members({"unrecognised_rate": 7})
    with pytest.raises(InvalidGatewayKeyLimitsError):
        canonical_rate_policy_members(
            {"concurrent_requests": 5, "max_concurrent_requests": 6}
        )


# --------------------------------------------------------------------------
# Migration law: stored binding classification
# --------------------------------------------------------------------------


def test_stored_module_binding_classifies_resolved_and_stale_states() -> None:
    # No block / default module: unbound.
    assert stored_module_binding(None) is UNBOUND
    assert stored_module_binding({"version": 1, "allowed_capabilities": ["text"]}) is UNBOUND
    # Explicit current pin: resolved.
    bound = stored_module_binding(
        {"version": 1, "allowed_capabilities": [], "client_module": dict(PIN_0162)}
    )
    assert bound == ("resolved", (PIN_0162["id"], PIN_0162["version"], PIN_0162["fixture_sha256"]))
    # Historical frozen 0162 v1 pin: BOUND (stored), never initial binding.
    stale = stored_module_binding(
        {"version": 1, "allowed_capabilities": [], "client_module": dict(STALE_0162_V1)}
    )
    assert stale[0] == "stored"
    # Unregistered module pin: bound (stored), unmatchable unless exact.
    unknown = stored_module_binding(
        {
            "version": 1,
            "client_module": {
                "id": "synthetic-unregistered-196",
                "version": "1",
                "fixture_sha256": "0" * 64,
            },
        }
    )
    assert unknown[0] == "stored"
    # Malformed pin shape: bound with an unmatchable (None) pin.
    malformed = stored_module_binding({"version": 1, "client_module": ["nope"]})
    assert malformed == ("stored", None)
    # Implicit legacy five-gate shape: resolved to the qualified 0147 module.
    legacy = stored_module_binding(
        {
            "version": 1,
            "allowed_capabilities": sorted(
                [
                    "codex_request_envelope",
                    "codex_client_tools",
                    "codex_streaming_tool_events",
                    "codex_encrypted_reasoning_replay",
                    "codex_compaction",
                ]
            ),
            "allowed_local_tool_types": ["function", "custom"],
        }
    )
    assert legacy == ("resolved", (PIN_0147["id"], PIN_0147["version"], PIN_0147["fixture_sha256"]))


def test_proposed_matches_stored_binding_law() -> None:
    stale = stored_module_binding(
        {"version": 1, "allowed_capabilities": [], "client_module": dict(STALE_0162_V1)}
    )
    # A current-identity repin of a stale source is NOT a match.
    assert (
        proposed_matches_stored_binding(
            stale,
            {
                "version": 1,
                "allowed_capabilities": [],
                "client_module": dict(PIN_0162),
            },
        )
        is False
    )
    # The exact stored stale pin matches (validator accepts it only if it is
    # registered; here we compare the classifier directly).
    assert (
        proposed_matches_stored_binding(
            stale,
            {"version": 1, "allowed_capabilities": [], "client_module": dict(STALE_0162_V1)},
        )
        is True
    )
    # A no-pin proposal (default module) never matches a stored binding.
    assert proposed_matches_stored_binding(stale, {"version": 1}) is False
    malformed = stored_module_binding({"version": 1, "client_module": ["nope"]})
    assert (
        proposed_matches_stored_binding(
            malformed, {"version": 1, "client_module": dict(PIN_0162)}
        )
        is False
    )
    # Resolved stored identity matches only itself.
    resolved = stored_module_binding(
        {"version": 1, "allowed_capabilities": [], "client_module": dict(PIN_0162)}
    )
    assert (
        proposed_matches_stored_binding(
            resolved, {"version": 1, "allowed_capabilities": [], "client_module": dict(PIN_0162)}
        )
        is True
    )
    assert (
        proposed_matches_stored_binding(
            resolved, {"version": 1, "allowed_capabilities": [], "client_module": dict(PIN_0149)}
        )
        is False
    )


# --------------------------------------------------------------------------
# KeyService update_gateway_key_configuration laws (fakes)
# --------------------------------------------------------------------------


def _update_payload(row: FakeGatewayKeyRow, config: KeyConfiguration, reason: str = "r"):
    return UpdateGatewayKeyConfigurationInput(
        gateway_key_id=row.id,
        configuration=config,
        actor_admin_id=None,
        reason=reason,
    )


@pytest.mark.asyncio
async def test_update_provider_only_preserves_request_policy_and_metadata() -> None:
    row = FakeGatewayKeyRow(
        metadata_json={"responses_policy": {"version": 1, "allowed_capabilities": ["text"]}}
    )
    service, repo, _, audit, _ = make_key_service(row)
    config = KeyConfiguration()
    config.allowed_providers = ["openai"]
    await service.update_gateway_key_configuration(_update_payload(row, config))
    assert row.allowed_models == ["gpt-test-mini"]
    assert row.allowed_endpoints == ["/v1/chat/completions"]
    assert row.metadata_json["allowed_providers"] == ["openai"]
    # Unrelated stored policy survives verbatim.
    assert row.metadata_json["responses_policy"] == {
        "version": 1,
        "allowed_capabilities": ["text"],
    }
    assert len(audit.calls) == 1
    assert audit.calls[0]["action"] == "update_key_configuration"
    # Key material and counters untouched.
    assert row.token_hash == "a" * 64
    assert row.tokens_used_total == 100
    assert repo.limit_calls == []


@pytest.mark.asyncio
async def test_update_rate_per_member_patch_and_explicit_null_reset() -> None:
    row = FakeGatewayKeyRow(
        rate_limit_requests_per_minute=7,
        rate_limit_tokens_per_minute=12_000,
        max_concurrent_requests=2,
        metadata_json={"rate_limit_policy": {"window_seconds": 45}},
    )
    service, _, _, audit, _ = make_key_service(row)
    config = KeyConfiguration()
    config.rate_limit_policy = {"max_concurrent_requests": 3, "tokens_per_minute": None}
    await service.update_gateway_key_configuration(_update_payload(row, config))
    assert row.rate_limit_requests_per_minute == 7  # preserved
    assert row.rate_limit_tokens_per_minute is None  # explicit null reset
    assert row.max_concurrent_requests == 3
    assert row.metadata_json["rate_limit_policy"] == {"window_seconds": 45}  # preserved
    assert len(audit.calls) == 1


@pytest.mark.asyncio
async def test_update_rate_unknown_member_is_rejected_before_any_write() -> None:
    row = FakeGatewayKeyRow(max_concurrent_requests=2)
    service, repo, _, audit, _ = make_key_service(row)
    config = KeyConfiguration()
    config.rate_limit_policy = {"unrecognised_rate": 7}
    with pytest.raises(InvalidGatewayKeyLimitsError):
        await service.update_gateway_key_configuration(_update_payload(row, config))
    assert row.max_concurrent_requests == 2
    assert repo.metadata_calls == []
    assert repo.rate_limit_calls == []
    assert audit.calls == []


@pytest.mark.asyncio
async def test_update_rate_legacy_alias_canonicalizes() -> None:
    row = FakeGatewayKeyRow(max_concurrent_requests=2)
    service, _, _, audit, _ = make_key_service(row)
    config = KeyConfiguration()
    config.rate_limit_policy = {"concurrent_requests": 5}
    await service.update_gateway_key_configuration(_update_payload(row, config))
    assert row.max_concurrent_requests == 5
    assert len(audit.calls) == 1


@pytest.mark.asyncio
async def test_update_fenced_quota_clear_is_rejected_without_mutation() -> None:
    from slaif_gateway.services.external_tool_policy_contract import (
        EXTERNAL_TOOL_FENCED,
    )

    row = FakeGatewayKeyRow(
        request_limit_total=10,
        token_limit_total=100,
        cost_limit_eur=Decimal("5"),
        metadata_json={
            "external_tool_policy": {
                "version": 1,
                "mode": EXTERNAL_TOOL_FENCED,
                "allowed_capabilities": ["provider_web_search"],
                "allowed_destination_ids": [],
                "max_provider_tool_calls_per_request": 1,
                "single_request_overrun_acknowledged": True,
            }
        },
    )
    service, repo, _, audit, _ = make_key_service(row)
    before = dict(row.metadata_json)
    config = KeyConfiguration()
    config.request_limit_total = None  # explicit unlimited would drop the fence
    with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
        await service.update_gateway_key_configuration(_update_payload(row, config))
    assert "fenced" in str(exc.value)
    assert row.metadata_json == before
    assert row.request_limit_total == 10
    assert repo.limit_calls == []
    assert audit.calls == []


@pytest.mark.asyncio
async def test_update_bound_policy_repin_is_rejected_with_migration_guidance() -> None:
    row = FakeGatewayKeyRow(
        metadata_json={
            "responses_policy": {
                "version": 1,
                "allowed_capabilities": ["codex_request_envelope"],
                "client_module": dict(PIN_0162),
            }
        }
    )
    service, repo, _, audit, _ = make_key_service(row)
    before = dict(row.metadata_json)
    config = KeyConfiguration()
    config.responses_policy = {
        "version": 1,
        "allowed_capabilities": ["codex_request_envelope"],
        "client_module": dict(PIN_0149),
    }
    with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
        await service.update_gateway_key_configuration(_update_payload(row, config))
    assert "client-module migration" in str(exc.value)
    assert row.metadata_json == before
    assert audit.calls == []


@pytest.mark.asyncio
async def test_update_stale_historical_pin_repin_is_not_initial_binding() -> None:
    row = FakeGatewayKeyRow(
        metadata_json={
            "responses_policy": {
                "version": 1,
                "allowed_capabilities": ["codex_request_envelope"],
                "client_module": dict(STALE_0162_V1),
            }
        }
    )
    service, repo, _, audit, _ = make_key_service(row)
    before = dict(row.metadata_json)
    # Re-pinning the stale source straight to the active identity must fail.
    config = KeyConfiguration()
    config.responses_policy = {
        "version": 1,
        "allowed_capabilities": ["codex_request_envelope"],
        "client_module": dict(PIN_0162),
    }
    with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
        await service.update_gateway_key_configuration(_update_payload(row, config))
    assert "client-module migration" in str(exc.value)
    assert row.metadata_json == before
    assert audit.calls == []
    # Clearing a stale binding is refused too.
    clear_config = KeyConfiguration()
    clear_config.responses_policy = None
    with pytest.raises(InvalidGatewayKeyPolicyError):
        await service.update_gateway_key_configuration(_update_payload(row, clear_config))
    assert row.metadata_json == before


@pytest.mark.asyncio
async def test_update_unbound_key_accepts_initial_binding() -> None:
    row = FakeGatewayKeyRow(metadata_json={})
    service, _, _, audit, _ = make_key_service(row)
    config = KeyConfiguration()
    config.responses_policy = {
        "version": 1,
        "allowed_capabilities": ["codex_request_envelope"],
        "client_module": dict(PIN_0162),
    }
    await service.update_gateway_key_configuration(_update_payload(row, config))
    assert row.metadata_json["responses_policy"]["client_module"] == PIN_0162
    assert len(audit.calls) == 1


@pytest.mark.asyncio
async def test_update_deauthorizes_grants_while_retaining_same_pin() -> None:
    row = FakeGatewayKeyRow(
        metadata_json={
            "responses_policy": {
                "version": 1,
                "allowed_capabilities": ["codex_request_envelope", "codex_client_tools"],
                "allowed_local_tool_types": ["function", "custom"],
                "client_module": dict(PIN_0162),
            }
        }
    )
    service, _, _, audit, _ = make_key_service(row)
    config = KeyConfiguration()
    config.responses_policy = {
        "version": 1,
        "allowed_capabilities": [],
        "client_module": dict(PIN_0162),
    }
    await service.update_gateway_key_configuration(_update_payload(row, config))
    stored = row.metadata_json["responses_policy"]
    assert stored["client_module"] == PIN_0162
    assert "allowed_capabilities" not in stored  # canonical omits empty grants
    assert len(audit.calls) == 1


@pytest.mark.asyncio
async def test_update_clears_bound_policy_rejected_even_from_null() -> None:
    row = FakeGatewayKeyRow(
        metadata_json={
            "responses_policy": {
                "version": 1,
                "allowed_capabilities": ["codex_request_envelope"],
                "client_module": dict(PIN_0162),
            }
        }
    )
    service, _, _, audit, _ = make_key_service(row)
    config = KeyConfiguration()
    config.responses_policy = None
    with pytest.raises(InvalidGatewayKeyPolicyError) as exc:
        await service.update_gateway_key_configuration(_update_payload(row, config))
    assert "client-module migration" in str(exc.value)
    assert audit.calls == []


@pytest.mark.asyncio
async def test_update_requires_reason_and_rejects_empty_configuration() -> None:
    row = FakeGatewayKeyRow()
    service, _, _, audit, _ = make_key_service(row)
    config = KeyConfiguration()
    config.allowed_providers = ["openai"]
    with pytest.raises(InvalidGatewayKeyPolicyError):
        await service.update_gateway_key_configuration(
            UpdateGatewayKeyConfigurationInput(
                gateway_key_id=row.id, configuration=config, actor_admin_id=None, reason="  "
            )
        )
    empty = KeyConfiguration()
    with pytest.raises(InvalidGatewayKeyPolicyError):
        await service.update_gateway_key_configuration(_update_payload(row, empty))
    assert audit.calls == []


@pytest.mark.asyncio
async def test_update_later_write_failure_leaves_no_partial_state_or_audit() -> None:
    row = FakeGatewayKeyRow()
    service, repo, _, audit, _ = make_key_service(row)

    async def failing_update(*args, **kwargs):
        return False

    monkeypatch_target = repo.update_gateway_key_limits
    repo.update_gateway_key_limits = failing_update  # type: ignore[method-assign]
    try:
        config = KeyConfiguration()
        config.cost_limit_eur = Decimal("5")
        with pytest.raises(GatewayKeyNotFoundError):
            await service.update_gateway_key_configuration(_update_payload(row, config))
    finally:
        repo.update_gateway_key_limits = monkeypatch_target  # type: ignore[method-assign]
    assert row.cost_limit_eur == Decimal("25.000000000")
    assert audit.calls == []


@pytest.mark.asyncio
async def test_update_on_fenced_row_is_blocked() -> None:
    from slaif_gateway.services.external_tool_policy_contract import EXTERNAL_TOOL_FENCED

    row = FakeGatewayKeyRow(
        external_tool_fence_state="held",
        metadata_json={
            "external_tool_policy": {
                "version": 1,
                "mode": EXTERNAL_TOOL_FENCED,
                "allowed_capabilities": ["provider_web_search"],
                "allowed_destination_ids": [],
                "max_provider_tool_calls_per_request": 1,
                "single_request_overrun_acknowledged": True,
            }
        },
    )
    service, repo, _, audit, _ = make_key_service(row)
    config = KeyConfiguration()
    config.allowed_providers = ["openai"]
    from slaif_gateway.services.key_service import GatewayKeyExternalToolFenceActiveError

    with pytest.raises(GatewayKeyExternalToolFenceActiveError) as exc:
        await service.update_gateway_key_configuration(_update_payload(row, config))
    assert "fence" in str(exc.value).lower()
    assert repo.metadata_calls == []
    assert audit.calls == []


# --------------------------------------------------------------------------
# export_gateway_key_configuration (fakes)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_emits_explicit_nulls_and_round_trips_compatible_target() -> None:
    row = FakeGatewayKeyRow(
        allowed_models=["gpt-test-mini"],
        allowed_endpoints=["/v1/chat/completions"],
        rate_limit_requests_per_minute=None,
        rate_limit_tokens_per_minute=None,
        max_concurrent_requests=None,
        metadata_json={"allowed_providers": ["openai"]},
    )
    service, _, _, _, _ = make_key_service(row)
    document = await service.export_gateway_key_configuration(row.id)
    assert document["schema_version"] == KEY_CONFIGURATION_SCHEMA_VERSION
    # Explicit nulls for absent groups (never omitted).
    assert "responses_policy" in document and document["responses_policy"] is None
    assert "rate_limit_policy" in document and document["rate_limit_policy"] is None
    assert "lazy_throttling_policy" in document and document["lazy_throttling_policy"] is None
    assert document["allowed_providers"] == ["openai"]
    # No fresh confirmation is ever emitted.
    assert "confirm_external_tool_fenced" not in document

    # Round-trip onto a COMPATIBLE (unbound) target: the document consumes
    # through the strict schema and updates the target to the same state.
    target = FakeGatewayKeyRow(
        allowed_models=["other-model"],
        allowed_endpoints=["/v1/models"],
        metadata_json={},
    )
    target_service, _, _, target_audit, _ = make_key_service(target)
    config = parse_key_configuration(document)
    await target_service.update_gateway_key_configuration(
        UpdateGatewayKeyConfigurationInput(
            gateway_key_id=target.id,
            configuration=config,
            actor_admin_id=None,
            reason="clone export",
        )
    )
    assert target.allowed_models == ["gpt-test-mini"]
    assert target.allowed_endpoints == ["/v1/chat/completions"]
    assert target.metadata_json["allowed_providers"] == ["openai"]
    assert len(target_audit.calls) == 1


@pytest.mark.asyncio
async def test_export_bound_round_trip_keeps_same_identity() -> None:
    source = FakeGatewayKeyRow(
        metadata_json={
            "responses_policy": {
                "version": 1,
                "allowed_capabilities": ["codex_request_envelope"],
                "client_module": dict(PIN_0162),
            }
        }
    )
    source_service, _, _, _, _ = make_key_service(source)
    document = await source_service.export_gateway_key_configuration(source.id)
    assert document["responses_policy"]["client_module"] == PIN_0162

    target = FakeGatewayKeyRow(metadata_json={})
    target_service, _, _, _, _ = make_key_service(target)
    await target_service.update_gateway_key_configuration(
        UpdateGatewayKeyConfigurationInput(
            gateway_key_id=target.id,
            configuration=parse_key_configuration(document),
            actor_admin_id=None,
            reason="clone export",
        )
    )
    assert target.metadata_json["responses_policy"]["client_module"] == PIN_0162


@pytest.mark.asyncio
async def test_export_malformed_stored_policy_fails_explicitly() -> None:
    row = FakeGatewayKeyRow(
        metadata_json={
            "responses_policy": {
                "version": 1,
                "allowed_capabilities": ["definitely_not_registered_capability"],
            }
        }
    )
    service, _, _, _, _ = make_key_service(row)
    with pytest.raises(KeyConfigurationExportError):
        await service.export_gateway_key_configuration(row.id)


@pytest.mark.asyncio
async def test_export_stale_stored_pin_fails_explicitly() -> None:
    row = FakeGatewayKeyRow(
        metadata_json={
            "responses_policy": {
                "version": 1,
                "allowed_capabilities": [],
                "client_module": dict(STALE_0162_V1),
            }
        }
    )
    service, _, _, _, _ = make_key_service(row)
    with pytest.raises(KeyConfigurationExportError):
        await service.export_gateway_key_configuration(row.id)


@pytest.mark.asyncio
async def test_configuration_audit_never_copies_unknown_stored_fields() -> None:
    canary = "SYNTHETIC_OPERATOR_PRIVATE_TEXT_196"
    row = FakeGatewayKeyRow(
        metadata_json={"responses_policy": {"version": 1, "opaque_field": canary}}
    )
    service, repo, _, audit, _ = make_key_service(row)
    config = KeyConfiguration()
    config.allowed_providers = []
    await service.update_gateway_key_configuration(_update_payload(row, config))
    assert len(audit.calls) == 1
    blob = json.dumps(audit.calls, default=str)
    assert canary not in blob
    for values in (audit.calls[0]["old_values"], audit.calls[0]["new_values"]):
        assert values["responses_policy"] == {"version": 1, "unsupported_fields": 1}


def _make_create_config(providers: object) -> KeyConfiguration:
    config = KeyConfiguration()
    if providers is not ABSENT:
        config.allowed_providers = providers
    return config


def test_build_create_input_carries_provider_semantics() -> None:
    from slaif_gateway.services.key_policy_configuration import (
        build_create_gateway_key_input,
    )

    base = {
        "owner_id": OWNER_ID,
        "valid_from": datetime.now(UTC),
        "valid_until": datetime.now(UTC) + timedelta(days=1),
    }
    unrestricted = build_create_gateway_key_input(
        config=KeyConfiguration(), **base  # type: ignore[arg-type]
    )
    assert unrestricted.allowed_providers is None
    deny_all = build_create_gateway_key_input(
        config=_make_create_config([]), **base  # type: ignore[arg-type]
    )
    assert deny_all.allowed_providers == []
    allow_list = build_create_gateway_key_input(
        config=_make_create_config(["openai"]), **base  # type: ignore[arg-type]
    )
    assert allow_list.allowed_providers == ["openai"]

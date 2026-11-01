"""Objective 199: strict provider/route configuration contracts (unit).

Objective 199-a established the versioned file envelopes (capabilities
file, route update plan), the typed partial capability patch, the
merge/preserve law, the public configuration fingerprint, and the shared
typed operations (provider partial update, route preview/execute) against
fakes — no database, no network, no credential loading. Objective 199-b
extends the same contract: route-bound fingerprints, destination-provider
identity/context bindings, canonical current/proposed preview, nonblank
reasons, known-shape secret refusals, zero-retry completion rule, and
strict new-document transport contract parsing. Objective 199-c completes
the parity: explicit provider-note clearing through the shared audited
service, creation-surface known-shape guards, and complete pure
server-module/transport validation (registered module, implicit legacy
binding, no advertised streaming on configured-completion routes).
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from slaif_gateway.schemas.provider_route_configuration import (
    CAPABILITIES_FILE_MAX_BYTES,
    ProviderRouteConfigError,
    ProviderRouteStaleError,
    RouteUpdatePlan,
    CapabilityPatch,
    merge_capability_patch,
    parse_capabilities_file,
    parse_capability_patch,
    parse_route_update_plan_document,
    parse_route_update_plan_file,
    render_route_update_plan,
    validate_capabilities_document,
)
from slaif_gateway.services.provider_route_configuration import (
    _route_fingerprint,
    contains_known_secret_shape,
    compute_provider_context_fingerprint,
    compute_route_configuration_fingerprint,
    execute_route_update_plan,
    partial_update_provider_config,
    preview_route_update,
    preview_route_update_for_route,
    validate_merged_route_candidate,
    validate_route_creation_candidate,
)
from slaif_gateway.db.repositories.provider_configs import ProviderConfigsRepository

CHAT_BLOCK = {"chat_text": True, "chat_streaming": True, "chat_function_tools": False}
CODEX_BLOCK = {
    "context_window_tokens": 1050000,
    "default_max_output_tokens": 32768,
    "max_output_tokens": 128000,
}
ROUTE_ID = "11111111-2222-4333-8444-555555555555"
PROVIDER_ID = uuid.UUID("99999999-8888-4777-8666-555555555555")
SECOND_PROVIDER_ID = uuid.UUID("88888888-7777-4666-8555-444444444444")

# Valid, unambiguous supported transport-contract fixtures (199-b): the
# strict NEW-document parser must accept these and refuse malformed or
# conflicting declarations.
LOCAL_CODING_CONTRACT = {
    "contract_version": "local-coding-v1",
    "route_name": "codex-local-1",
    "tool_policy_version": "responses-tool-policy-v1",
    "identity_mode": "static",
    "replay_mode": "process_local_inclusive_horizon_fail_closed",
    "deployment_mode": "single_worker",
}
VLLM_CONTRACT = {
    "contract_version": "local-coding-vLLM",
    "route_name": "codex-vllm-1",
    "tool_policy_version": "responses-tool-policy-v1",
    "identity_mode": "static",
    "replay_mode": "process_local_inclusive_horizon_fail_closed",
    "deployment_mode": "single_worker",
}


# --- fixtures -----------------------------------------------------------------


def _caps_doc(**overrides: Any) -> dict[str, Any]:
    document = {"schema_version": 1, "capabilities": {"chat_completions": dict(CHAT_BLOCK)}}
    document.update(overrides)
    return document


def _parse(doc: dict[str, Any] | str) -> dict[str, Any]:
    payload = doc if isinstance(doc, str) else json.dumps(doc)
    return parse_capabilities_file(payload.encode("utf-8"))


@dataclass
class FakeProviderRow:
    id: uuid.UUID = PROVIDER_ID
    provider: str = "mod-a"
    display_name: str = "Mod A"
    kind: str = "openai_compatible"
    base_url: str = "https://svc-a.example/api"
    api_key_env_var: str = "SVC_A_KEY"
    enabled: bool = False
    timeout_seconds: int = 30
    max_retries: int = 0
    notes: str | None = "old notes"
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class FakeRouteRow:
    id: str = ROUTE_ID
    requested_model: str = "zap-it-1"
    match_type: str = "exact"
    endpoint: str = "/v1/chat/completions"
    provider: str = "mod-a"
    upstream_model: str = "zap-it-1"
    priority: int = 100
    enabled: bool = True
    visible_in_models: bool = True
    supports_streaming: bool = True
    capabilities: dict[str, Any] = field(
        default_factory=lambda: {
            "chat_completions": dict(CHAT_BLOCK),
            "codex_limits": dict(CODEX_BLOCK),
        }
    )
    notes: str | None = "route notes"
    created_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)
    updated_at: datetime = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class FakeSession:
    flushes: int = 0

    async def flush(self) -> None:
        self.flushes += 1


# --- capabilities file contract -------------------------------------------------


class TestCapabilitiesFile:
    def test_valid_envelope_parses(self) -> None:
        document = _parse(_caps_doc())
        assert document["chat_completions"] == CHAT_BLOCK

    def test_missing_schema_version_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="schema_version"):
            _parse({"capabilities": dict(CHAT_BLOCK)})

    def test_wrong_schema_version_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="schema_version"):
            _parse(_caps_doc(schema_version=2))

    def test_float_schema_version_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="schema_version"):
            _parse('{"schema_version": 1.0, "capabilities": {"chat_completions": {}}}')

    def test_unknown_top_level_field_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="unsupported fields"):
            _parse(_caps_doc(extras="nope"))

    def test_missing_capabilities_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="capabilities"):
            _parse({"schema_version": 1})

    def test_empty_capabilities_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="must not be empty"):
            _parse(_caps_doc(capabilities={}))

    def test_non_object_top_level_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="Top level"):
            parse_capabilities_file(b"[]")

    def test_invalid_utf8_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="UTF-8"):
            parse_capabilities_file(b"\xff\xfe\x00{}")

    def test_duplicate_key_refused(self) -> None:
        payload = b'{"schema_version":1,"schema_version":1,"capabilities":{}}'
        with pytest.raises(ProviderRouteConfigError, match="duplicate key"):
            parse_capabilities_file(payload)

    def test_nonfinite_constant_refused(self) -> None:
        payload = b'{"schema_version":NaN,"capabilities":{"chat_completions":{}}}'
        with pytest.raises(ProviderRouteConfigError, match="NaN or Infinity"):
            parse_capabilities_file(payload)

    def test_oversize_refused_without_full_read(self) -> None:
        payload = b"{" + b'"pad":' + b"x" * (CAPABILITIES_FILE_MAX_BYTES + 16) + b"}"
        assert len(payload) > CAPABILITIES_FILE_MAX_BYTES
        with pytest.raises(ProviderRouteConfigError, match="bounded size"):
            parse_capabilities_file(payload)

    def test_unknown_group_refused(self) -> None:
        document = _caps_doc(capabilities={"chat_completions": CHAT_BLOCK, "made_up": True})
        with pytest.raises(ProviderRouteConfigError, match="unsupported groups"):
            _parse(document)

    @pytest.mark.parametrize(
        "canary",
        [
            "sk-slaif-1234567890abcdef1234567890abcdef12345678.deadbeef",
            "Authorization: Bearer abcdef1234567890",
            "OPENAI_UPSTREAM_API_KEY=sk-or-v1-abcdef1234567890",
            "api_key: sk-abcdef1234567890abcdef",
        ],
    )
    def test_known_secret_shapes_refused(self, canary: str) -> None:
        payload = json.dumps(
            {
                "schema_version": 1,
                "capabilities": {
                    "chat_completions": dict(CHAT_BLOCK),
                    "codex_compaction_compatible_route_ids": [canary],
                },
            }
        )
        with pytest.raises(ProviderRouteConfigError, match="secret shape"):
            parse_capabilities_file(payload.encode("utf-8"))

    def test_float_values_rejected_in_integer_leaves(self) -> None:
        payload = json.dumps(
            {
                "schema_version": 1,
                "capabilities": {
                    "codex_limits": {
                        "context_window_tokens": 1.5,
                        "default_max_output_tokens": 2,
                        "max_output_tokens": 3,
                    }
                },
            }
        )
        with pytest.raises(ProviderRouteConfigError, match="codex_limits"):
            parse_capabilities_file(payload.encode("utf-8"))


class TestCapabilityGroups:
    def test_all_contract_groups_accepted(self) -> None:
        document = _parse(
            _caps_doc(
                capabilities={
                    "chat_completions": dict(CHAT_BLOCK),
                    "responses": {"text": True, "stateless": True},
                    "codex_limits": dict(CODEX_BLOCK),
                    "codex_compaction_compatible_route_ids": [ROUTE_ID],
                    "media_input_estimation": {
                        "version": 1,
                        "image_tokens": 1024,
                        "video_tokens": 2048,
                        "video_frames": 8,
                    },
                    "completion_service": {"version": 1, "profile": "zap-it-v1"},
                    "audio_endpoints": {"audio_speech": False, "audio_transcriptions": True, "audio_translations": False},
                    "embeddings": {"embeddings": True, "embeddings_dimensions": True},
                    "realtime": {
                        "audio": True,
                        "webrtc_client_secrets": True,
                        "transcription": False,
                        "client_secret_direct_provider_exposure_accepted": True,
                    },
                }
            )
        )
        assert document["codex_limits"] == CODEX_BLOCK

    def test_valid_local_coding_contract_accepted(self) -> None:
        # 199-b: NEW complete documents must re-author transport contracts
        # and satisfy the existing pure parsers (no more permissive
        # "preserved" pass-through).
        document = _parse(
            _caps_doc(
                capabilities={
                    "chat_completions": dict(CHAT_BLOCK),
                    "local_coding": dict(LOCAL_CODING_CONTRACT),
                }
            )
        )
        assert document["local_coding"] == LOCAL_CODING_CONTRACT

    def test_valid_vllm_contract_accepted(self) -> None:
        document = _parse(
            _caps_doc(
                capabilities={
                    "chat_completions": dict(CHAT_BLOCK),
                    "local_coding_vllm": dict(VLLM_CONTRACT),
                }
            )
        )
        assert document["local_coding_vllm"] == VLLM_CONTRACT

    def test_malformed_local_coding_contract_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="local_coding"):
            _parse(
                _caps_doc(
                    capabilities={
                        "chat_completions": dict(CHAT_BLOCK),
                        # wrong version + missing required fields: the old
                        # permissive oracle accepted this "preserved" data
                        "local_coding": {"contract_version": 1, "route_name": "r1"},
                    }
                )
            )

    def test_conflicting_transport_selectors_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError):
            _parse(
                _caps_doc(
                    capabilities={
                        "chat_completions": dict(CHAT_BLOCK),
                        "local_coding": dict(LOCAL_CODING_CONTRACT),
                        "local_coding_vllm": dict(VLLM_CONTRACT),
                    }
                )
            )

    def test_completion_service_conflicts_with_exclusive_selectors(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="exclusive transport"):
            _parse(
                _caps_doc(
                    capabilities={
                        "completion_service": {"version": 1, "profile": "zap-it-v1"},
                        "vllm_chat_video": {"version": 1},
                    }
                )
            )

    def test_unknown_chat_flag_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="known boolean flags"):
            _parse(_caps_doc(capabilities={"chat_completions": {"chat_text": True, "made_up": True}}))

    def test_non_bool_chat_flag_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="known boolean flags"):
            _parse(_caps_doc(capabilities={"chat_completions": {"chat_text": "yes"}}))

    @pytest.mark.parametrize(
        "limits",
        [
            {"context_window_tokens": 100, "default_max_output_tokens": 32768},  # missing
            {"context_window_tokens": 100, "default_max_output_tokens": 200, "max_output_tokens": 300},  # default > max impossible order
            {"context_window_tokens": -1, "default_max_output_tokens": 1, "max_output_tokens": 2},
            {"context_window_tokens": 10, "default_max_output_tokens": 5, "max_output_tokens": 200},  # default > context
            {"context_window_tokens": 100, "default_max_output_tokens": 50, "max_output_tokens": 40},  # max < default
        ],
    )
    def test_codex_numeric_relationships_enforced(self, limits: dict[str, int]) -> None:
        with pytest.raises(ProviderRouteConfigError, match="codex_limits"):
            validate_capabilities_document({"codex_limits": limits})

    @pytest.mark.parametrize("tokens", [0, 1_050_001])
    def test_media_token_ceilings_enforced(self, tokens: int) -> None:
        with pytest.raises(ProviderRouteConfigError, match="media"):
            validate_capabilities_document(
                {"media_input_estimation": {"version": 1, "image_tokens": tokens}}
            )

    def test_media_frames_ceiling_enforced(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="media"):
            validate_capabilities_document(
                {"media_input_estimation": {"version": 1, "video_frames": 33}}
            )

    def test_media_version_must_be_one(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="media"):
            validate_capabilities_document(
                {"media_input_estimation": {"version": 2, "image_tokens": 10}}
            )

    def test_unavailable_profile_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="completion_service"):
            _parse(
                _caps_doc(capabilities={"completion_service": {"version": 1, "profile": "nope-v9"}})
            )

    def test_invalid_external_tools_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="external_tools"):
            _parse(_caps_doc(capabilities={"external_tools": {"mode": "made_up"}}))

    def test_external_tools_above_installation_ceiling_refused(self) -> None:
        # 199-b: full-replacement documents are validated with the ACTUAL
        # installation ceilings, not defaulted-away limits.
        from slaif_gateway.services.external_tool_policy_contract import (
            build_external_tool_operator_ceilings,
        )

        ceilings = build_external_tool_operator_ceilings(
            max_provider_tool_calls_per_request=1
        )
        policy = {
            "version": 1,
            "supported_capabilities": ["provider_web_search"],
            "approved_destination_ids": [],
            "max_provider_tool_calls_per_request": 2,
            "call_limit_enforced": True,
            "final_usage_required": True,
            "final_cost_required": True,
        }
        with pytest.raises(ProviderRouteConfigError, match="external_tools"):
            validate_capabilities_document(
                {"external_tools": policy},
                external_tool_ceilings=ceilings,
            )
        within = dict(policy, max_provider_tool_calls_per_request=1)
        document = validate_capabilities_document(
            {"external_tools": within}, external_tool_ceilings=ceilings
        )
        assert document["external_tools"]["max_provider_tool_calls_per_request"] == 1


# --- capability patch ------------------------------------------------------------


class TestCapabilityPatch:
    def test_empty_patch_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="at least one explicit leaf"):
            parse_capability_patch({})
        assert parse_capability_patch(None).is_empty()

    def test_unknown_group_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="unsupported groups"):
            parse_capability_patch({"made_up": {}})

    def test_codex_leaf_validation(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="codex_limits"):
            parse_capability_patch({"codex_limits": {"made_up_field": 1}})
        with pytest.raises(ProviderRouteConfigError, match="positive integer"):
            parse_capability_patch({"codex_limits": {"max_output_tokens": 0}})
        patch = parse_capability_patch({"codex_limits": {"max_output_tokens": 400000}})
        assert patch.codex_limits == {"max_output_tokens": 400000}

    def test_media_leaf_validation(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="media_input_estimation"):
            parse_capability_patch({"media_input_estimation": {"made_up": 1}})

    def test_chat_flags_validation(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="unsupported flags"):
            parse_capability_patch({"chat_completions": {"made_up": True}})
        patch = parse_capability_patch({"chat_completions": {"chat_text": False}})
        assert patch.chat_completions == {"chat_text": False}

    def test_completion_clear_and_set(self) -> None:
        assert parse_capability_patch({"completion_service": None}).completion_service is None
        patch = parse_capability_patch(
            {"completion_service": {"version": 1, "profile": "zap-it-v1"}}
        )
        assert patch.completion_service == {"version": 1, "profile": "zap-it-v1"}
        with pytest.raises(ProviderRouteConfigError, match="completion_service"):
            parse_capability_patch({"completion_service": {"version": 1, "profile": "nope-v9"}})

    def test_secret_shape_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="secret shape"):
            parse_capability_patch({"chat_completions": {"chat_text": "Bearer abcdef1234567890"}})


class TestMergeCapabilityPatch:
    def test_codex_leaf_preserves_siblings(self) -> None:
        merged = merge_capability_patch(
            {"codex_limits": dict(CODEX_BLOCK), "chat_completions": dict(CHAT_BLOCK)},
            parse_capability_patch({"codex_limits": {"max_output_tokens": 400000}}),
        )
        assert merged["codex_limits"] == {
            "context_window_tokens": 1050000,
            "default_max_output_tokens": 32768,
            "max_output_tokens": 400000,
        }
        assert merged["chat_completions"] == CHAT_BLOCK

    def test_media_leaf_preserves_siblings(self) -> None:
        merged = merge_capability_patch(
            {"media_input_estimation": {"version": 1, "image_tokens": 1, "video_tokens": 2, "video_frames": 3}},
            parse_capability_patch({"media_input_estimation": {"video_frames": 4}}),
        )
        assert merged["media_input_estimation"] == {
            "version": 1,
            "image_tokens": 1,
            "video_tokens": 2,
            "video_frames": 4,
        }

    def test_chat_flag_merge_preserves_other_flags(self) -> None:
        merged = merge_capability_patch(
            {"chat_completions": dict(CHAT_BLOCK)},
            parse_capability_patch({"chat_completions": {"chat_text": False}}),
        )
        assert merged["chat_completions"]["chat_streaming"] is True
        assert merged["chat_completions"]["chat_text"] is False

    def test_completion_clear_removes_selector(self) -> None:
        merged = merge_capability_patch(
            {"completion_service": {"version": 1, "profile": "zap-it-v1"}, "chat_completions": CHAT_BLOCK},
            CapabilityPatch(completion_service=None),
        )
        assert "completion_service" not in merged
        assert merged["chat_completions"] == CHAT_BLOCK


# --- fingerprint -----------------------------------------------------------------


def _fingerprint(**overrides: Any) -> str:
    base: dict[str, Any] = dict(
        route_id=ROUTE_ID,
        requested_model="m",
        match_type="exact",
        endpoint="/v1/chat/completions",
        provider="p",
        upstream_model="u",
        priority=1,
        visible_in_models=True,
        supports_streaming=True,
        enabled=True,
        capabilities={"a": 1},
        notes=None,
    )
    base.update(overrides)
    return compute_route_configuration_fingerprint(**base)


class TestFingerprint:
    def test_stable_64_hex(self) -> None:
        value = _fingerprint()
        assert len(value) == 64
        int(value, 16)
        assert value == _fingerprint()

    @pytest.mark.parametrize(
        "field", ["route_id", "requested_model", "priority", "enabled", "notes"]
    )
    def test_sensitive_to_config_fields(self, field: str) -> None:
        value = _fingerprint()
        overrides = {
            "route_id": "22222222-3333-4444-8555-666666666666",
            "requested_model": "m2",
            "priority": 2,
            "enabled": False,
            "notes": "n2",
        }[field]
        assert _fingerprint(**{field: overrides}) != value

    def test_route_bound_only_timestamps_excluded(self) -> None:
        # 199-b: the route UUID IS bound (a different route can never
        # validate the same expected pre-state); only timestamps are
        # excluded from the digest.
        import inspect

        signature = inspect.signature(compute_route_configuration_fingerprint)
        names = set(signature.parameters)
        assert "route_id" in names
        assert not {"created_at", "updated_at"} & names


# --- route plan document -----------------------------------------------------------


def _plan_doc(**overrides: Any) -> dict[str, Any]:
    document = {
        "schema_version": 1,
        "route_id": ROUTE_ID,
        "expected_route_id": ROUTE_ID,
        "expected_provider_id": str(PROVIDER_ID),
        "expected_provider_context_fingerprint": "b" * 64,
        "requested_model": "zap-it-1",
        "match_type": "exact",
        "endpoint": "/v1/chat/completions",
        "provider": "mod-a",
        "upstream_model": "zap-it-1",
        "priority": 100,
        "visible_in_models": True,
        "supports_streaming": True,
        "enabled": True,
        "notes": "n",
        "capabilities_mode": "unchanged",
        "capabilities": None,
        "capability_patch": None,
        "expected_configuration_fingerprint": "a" * 64,
    }
    document.update(overrides)
    return document


class TestRoutePlanDocument:
    def test_round_trip(self) -> None:
        plan = parse_route_update_plan_document(_plan_doc())
        rendered = render_route_update_plan(plan)
        again = parse_route_update_plan_document(rendered)
        assert again.route_id == plan.route_id
        assert again.expected_configuration_fingerprint == plan.expected_configuration_fingerprint
        assert again.expected_route_id == ROUTE_ID
        assert again.expected_provider_id == str(PROVIDER_ID)
        assert again.expected_provider_context_fingerprint == "b" * 64

    def test_partial_mode_requires_patch(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="capability_patch"):
            parse_route_update_plan_document(_plan_doc(capabilities_mode="partial"))

    def test_full_mode_requires_capabilities(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="capabilities"):
            parse_route_update_plan_document(_plan_doc(capabilities_mode="full-replacement"))

    def test_full_mode_refuses_patch(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="combine"):
            parse_route_update_plan_document(
                _plan_doc(
                    capabilities_mode="full-replacement",
                    capabilities={"chat_completions": dict(CHAT_BLOCK)},
                    capability_patch={"chat_completions": {"chat_text": False}},
                )
            )

    def test_bad_uuid_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="route_id"):
            parse_route_update_plan_document(_plan_doc(route_id="not-a-uuid"))

    def test_missing_expected_route_id_refused(self) -> None:
        document = _plan_doc()
        del document["expected_route_id"]
        with pytest.raises(ProviderRouteConfigError, match="expected_route_id"):
            parse_route_update_plan_document(document)

    def test_bad_expected_provider_id_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="expected_provider_id"):
            parse_route_update_plan_document(
                _plan_doc(expected_provider_id="not-a-uuid")
            )

    def test_bad_provider_context_fingerprint_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="context_fingerprint"):
            parse_route_update_plan_document(
                _plan_doc(expected_provider_context_fingerprint="zz")
            )

    def test_old_unmerged_plan_shape_refused(self) -> None:
        # 199-b: pre-b plan shapes (no identity/context bindings) fail
        # fixed-safe; a new dry-run is required, never silent adoption.
        document = _plan_doc()
        del document["expected_route_id"]
        del document["expected_provider_id"]
        del document["expected_provider_context_fingerprint"]
        with pytest.raises(ProviderRouteConfigError):
            parse_route_update_plan_document(document)

    def test_bad_match_type_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="match_type"):
            parse_route_update_plan_document(_plan_doc(match_type="regex"))

    def test_bad_fingerprint_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="fingerprint"):
            parse_route_update_plan_document(_plan_doc(expected_configuration_fingerprint="zz"))

    def test_unknown_field_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="unsupported fields"):
            parse_route_update_plan_document(_plan_doc(made_up="x"))

    def test_secret_shape_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="secret shape"):
            parse_route_update_plan_document(_plan_doc(notes="Bearer abcdef1234567890"))

    def test_preview_keys_bounded(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="preview"):
            parse_route_update_plan_document(_plan_doc(preview={"note": "x", "made_up": 1}))

    def test_preview_canonical_blocks_shape_checked(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="canonical"):
            parse_route_update_plan_document(
                _plan_doc(
                    preview={
                        "note": "x",
                        "current_configuration": {"made_up": 1},
                    }
                )
            )
        with pytest.raises(ProviderRouteConfigError, match="changed_fields"):
            parse_route_update_plan_document(
                _plan_doc(preview={"changed_fields": "not-a-list"})
            )


# --- preview (pure) -----------------------------------------------------------------


class TestPreviewRouteUpdate:
    def test_unchanged_mode_no_changes(self) -> None:
        plan = preview_route_update(FakeRouteRow(), FakeProviderRow())
        assert plan.capabilities_mode == "unchanged"
        assert plan.preview["changed_fields"] == []
        assert plan.enabled is True
        # 199-b: the plan binds the route UUID and the destination
        # provider identity + context digest.
        assert plan.expected_route_id == ROUTE_ID
        assert plan.expected_provider_id == str(PROVIDER_ID)
        assert plan.expected_provider_context_fingerprint == (
            compute_provider_context_fingerprint(FakeProviderRow())
        )

    def test_partial_codex_change(self) -> None:
        plan = preview_route_update(
            FakeRouteRow(),
            FakeProviderRow(),
            capability_patch=CapabilityPatch(codex_limits={"max_output_tokens": 400000}),
        )
        assert plan.capabilities_mode == "partial"
        assert plan.preview["changed_fields"] == ["capabilities"]
        assert len(plan.expected_configuration_fingerprint) == 64
        int(plan.expected_configuration_fingerprint, 16)
        # Canonical proposed configuration carries the numeric gateway
        # values (default/max output), not only changed-field names.
        proposed = plan.preview["proposed_configuration"]
        assert proposed["capabilities"]["codex_limits"]["default_max_output_tokens"] == 32768
        assert proposed["capabilities"]["codex_limits"]["max_output_tokens"] == 400000
        assert proposed["capabilities"]["codex_limits"]["context_window_tokens"] == 1050000

    def test_field_change_tracked(self) -> None:
        plan = preview_route_update(FakeRouteRow(), FakeProviderRow(), priority=50, notes="other")
        assert sorted(plan.preview["changed_fields"]) == ["notes", "priority"]

    def test_endpoint_alias_normalized(self) -> None:
        plan = preview_route_update(FakeRouteRow(), FakeProviderRow(), endpoint="chat.completions")
        assert plan.endpoint == "/v1/chat/completions"
        assert "endpoint" not in plan.preview["changed_fields"]

    def test_invalid_endpoint_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError):
            preview_route_update(FakeRouteRow(), FakeProviderRow(), endpoint="   ")

    def test_clear_notes_changes(self) -> None:
        plan = preview_route_update(FakeRouteRow(), FakeProviderRow(), clear_notes=True)
        assert plan.notes is None
        assert "notes" in plan.preview["changed_fields"]

    def test_notes_and_clear_conflict(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="notes"):
            preview_route_update(
                FakeRouteRow(), FakeProviderRow(), notes="x", clear_notes=True
            )

    def test_notes_known_secret_shape_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="notes"):
            preview_route_update(
                FakeRouteRow(),
                FakeProviderRow(),
                notes="upstream key sk-proj-abcdef1234567890abcdef1234567890",
            )

    def test_codex_relationship_broken_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="codex_limits"):
            preview_route_update(
                FakeRouteRow(),
                FakeProviderRow(),
                capability_patch=CapabilityPatch(codex_limits={"context_window_tokens": 10}),
            )

    def test_completion_kind_mismatch_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="module provider kind"):
            preview_route_update(
                FakeRouteRow(),
                FakeProviderRow(kind="openai_compatible"),
                capabilities_document={"completion_service": {"version": 1, "profile": "zap-it-v1"}},
            )

    def test_completion_model_mismatch_refused(self) -> None:
        route = FakeRouteRow(
            requested_model="wrong",
            upstream_model="wrong",
            supports_streaming=False,
        )
        with pytest.raises(ProviderRouteConfigError, match="profile public model"):
            preview_route_update(
                route,
                FakeProviderRow(kind="module"),
                capabilities_document={"completion_service": {"version": 1, "profile": "zap-it-v1"}},
            )

    def test_completion_retrying_provider_refused(self) -> None:
        # 199-b zero-retry rule: the completion adapter raises on
        # max_retries != 0, so a retrying provider cannot back a
        # configured-completion route at configuration time.
        with pytest.raises(ProviderRouteConfigError, match="must not retry"):
            preview_route_update(
                FakeRouteRow(supports_streaming=False),
                FakeProviderRow(kind="module", max_retries=2),
                capability_patch=CapabilityPatch(
                    completion_service={"version": 1, "profile": "zap-it-v1"}
                ),
            )

    def test_completion_profile_valid_for_matching_route(self) -> None:
        # 199-c: the completion adapter refuses streaming, so the valid
        # completion fixture advertises no streaming anywhere.
        route = FakeRouteRow(
            supports_streaming=False,
            capabilities={
                "chat_completions": {
                    "chat_text": True,
                    "chat_streaming": False,
                    "chat_function_tools": False,
                },
                "codex_limits": dict(CODEX_BLOCK),
            },
        )
        plan = preview_route_update(
            route,
            FakeProviderRow(kind="module"),
            capability_patch=CapabilityPatch(
                completion_service={"version": 1, "profile": "zap-it-v1"}
            ),
        )
        assert plan.capabilities_mode == "partial"

    def test_full_replacement_mode(self) -> None:
        plan = preview_route_update(
            FakeRouteRow(),
            FakeProviderRow(),
            capabilities_document={
                "chat_completions": {"chat_text": True, "chat_streaming": False}
            },
        )
        assert plan.capabilities_mode == "full-replacement"
        assert plan.capabilities == {"chat_completions": {"chat_text": True, "chat_streaming": False}}

    def test_endpoint_change_renders_actual_defaults(self) -> None:
        # Root 199-a gap: an endpoint change previewed
        # capabilities_mode=unchanged while the core service ADDS a
        # Responses capability block on store. The canonical preview must
        # render what the service will actually store.
        route = FakeRouteRow()
        plan = preview_route_update(
            route, FakeProviderRow(), endpoint="/v1/responses"
        )
        proposed = plan.preview["proposed_configuration"]
        current = plan.preview["current_configuration"]
        assert "responses" in proposed["capabilities"]
        assert "responses" not in current["capabilities"]
        assert "capabilities" in plan.preview["changed_fields"]
        assert "endpoint" in plan.preview["changed_fields"]

    def test_plan_round_trips_through_file(self) -> None:
        plan = preview_route_update(
            FakeRouteRow(),
            FakeProviderRow(),
            capability_patch=CapabilityPatch(codex_limits={"max_output_tokens": 400000}),
            priority=77,
        )
        data = json.dumps(render_route_update_plan(plan)).encode("utf-8")
        again = parse_route_update_plan_file(data)
        assert again.capability_patch.codex_limits == {"max_output_tokens": 400000}
        assert again.priority == 77
        assert again.expected_route_id == plan.expected_route_id
        assert again.expected_provider_id == plan.expected_provider_id
        assert (
            again.expected_provider_context_fingerprint
            == plan.expected_provider_context_fingerprint
        )

    def test_cross_provider_preview_binds_destination(self) -> None:
        # 199-b R2: preview resolves the PROPOSED destination provider and
        # binds ITS identity/context — not the route's old provider.
        route = FakeRouteRow(provider="mod-a")
        destination = FakeProviderRow(
            id=SECOND_PROVIDER_ID, provider="mod-b", kind="openai_compatible"
        )
        plan = preview_route_update(route, destination, provider="mod-b")
        assert plan.provider == "mod-b"
        assert plan.expected_provider_id == str(SECOND_PROVIDER_ID)
        assert plan.expected_provider_context_fingerprint == (
            compute_provider_context_fingerprint(destination)
        )
        proposed = plan.preview["proposed_configuration"]
        current = plan.preview["current_configuration"]
        assert proposed["provider"] == "mod-b"
        assert current["provider"] == "mod-a"
        assert "provider" in plan.preview["changed_fields"]


# --- provider partial update (fakes) -------------------------------------------------


class _FakeProviderConfigsRepo:
    def __init__(self, session: Any, row: FakeProviderRow | None) -> None:
        self._row = row
        self.lock_reads = 0

    async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
        self.lock_reads += 1
        assert str(provider_or_id) in {str(self._row.id), self._row.provider} if self._row else True
        return self._row


class _RecordingUpdateService:
    def __init__(self, row: FakeProviderRow) -> None:
        self._row = row
        self.calls: list[dict[str, Any]] = []

    async def update_provider_config(self, provider_or_id: str, **kwargs: Any) -> Any:
        self.calls.append({"provider_or_id": provider_or_id, **kwargs})
        return self._row


@pytest.fixture()
def provider_update_harness(monkeypatch: pytest.MonkeyPatch):
    row = FakeProviderRow()
    repo = _FakeProviderConfigsRepo(None, row)
    service = _RecordingUpdateService(row)

    monkeypatch.setattr(
        ProviderConfigsRepository,
        "get_provider_config_for_update",
        lambda self, provider_or_id: repo.get_provider_config_for_update(provider_or_id),
    )
    monkeypatch.setattr(
        "slaif_gateway.services.provider_route_configuration.ProviderConfigService",
        lambda **_: service,
    )
    monkeypatch.setattr(
        "slaif_gateway.services.provider_route_configuration.AuditRepository",
        lambda session: object(),
    )
    return row, repo, service


async def _run_provider_update(provider_update_harness, **kwargs: Any) -> Any:
    row, repo, _service = provider_update_harness
    kwargs.setdefault("reason", "reviewed change")
    return await partial_update_provider_config(FakeSession(), str(row.id), **kwargs)


class TestPartialUpdateProvider:
    def test_omitted_fields_preserved(self, provider_update_harness) -> None:
        row, repo, service = provider_update_harness

        async def go() -> None:
            await partial_update_provider_config(
                FakeSession(), "mod-a", timeout_seconds=180, reason="tune timeout"
            )

        pytest.importorskip("anyio")
        import asyncio

        asyncio.run(go())
        assert repo.lock_reads == 1
        call = service.calls[0]
        assert call["timeout_seconds"] == 180
        assert call["max_retries"] == 0  # zero retries preserved from fresh row
        assert call["enabled"] is False
        assert call["provider"] == "mod-a"
        assert call["display_name"] == "Mod A"
        assert call["kind"] == "openai_compatible"
        assert call["base_url"] == "https://svc-a.example/api"
        assert call["api_key_env_var"] == "SVC_A_KEY"
        assert call["notes"] == "old notes"
        assert call["reason"] == "tune timeout"

    def test_explicit_zero_retries_won(self, provider_update_harness) -> None:
        row, _repo, service = provider_update_harness
        row.max_retries = 2

        async def go() -> None:
            await partial_update_provider_config(FakeSession(), "mod-a", max_retries=0, reason="r")

        import asyncio

        asyncio.run(go())
        assert service.calls[0]["max_retries"] == 0

    def test_replace_notes(self, provider_update_harness) -> None:
        _row, _repo, service = provider_update_harness

        async def go() -> None:
            await partial_update_provider_config(FakeSession(), "mod-a", notes="fresh", reason="r")

        import asyncio

        asyncio.run(go())
        assert service.calls[0]["notes"] == "fresh"

    def test_clear_notes_sets_none_before_service(self, provider_update_harness) -> None:
        row, _repo, service = provider_update_harness
        row.notes = "real prior value"

        async def go() -> None:
            session = FakeSession()
            await partial_update_provider_config(
                session, "mod-a", clear_notes=True, reason="r"
            )
            return session

        import asyncio

        session = asyncio.run(go())
        # 199-b R1: NO direct pre-mutation. The complete intended state
        # (notes=None) is delegated through the unchanged service so its
        # audit captures the REAL prior value; the typed operation itself
        # performs no column write and no flush.
        assert row.notes == "real prior value"  # untouched before the service
        assert service.calls[0]["notes"] is None
        assert session.flushes == 0

    def test_clear_notes_delegates_explicit_intent(self, provider_update_harness) -> None:
        # 199-c: the typed clear intent flows through the UNCHANGED shared
        # service (no pre-clear), so its audit captures real old -> null.
        _row, _repo, service = provider_update_harness

        async def go() -> None:
            await partial_update_provider_config(
                FakeSession(), "mod-a", clear_notes=True, reason="r"
            )

        import asyncio

        asyncio.run(go())
        call = service.calls[0]
        assert call["notes"] is None
        assert call["clear_notes"] is True

    def test_default_update_keeps_none_preservation(self, provider_update_harness) -> None:
        # 199-c: omitted notes without clear intent preserve the fresh row
        # value and never set the clear flag (default callers unchanged).
        _row, _repo, service = provider_update_harness

        async def go() -> None:
            await partial_update_provider_config(
                FakeSession(), "mod-a", timeout_seconds=45, reason="r"
            )

        import asyncio

        asyncio.run(go())
        call = service.calls[0]
        assert call["notes"] == "old notes"
        assert call["clear_notes"] is False

    def test_blank_reason_refused_before_mutation(self, provider_update_harness) -> None:
        row, _repo, service = provider_update_harness

        async def go() -> None:
            await partial_update_provider_config(
                FakeSession(), "mod-a", timeout_seconds=90, reason="   "
            )

        import asyncio

        with pytest.raises(ProviderRouteConfigError, match="reason"):
            asyncio.run(go())
        assert service.calls == []
        assert row.timeout_seconds == 30  # no mutation

    def test_notes_known_secret_shape_refused(self, provider_update_harness) -> None:
        row, _repo, service = provider_update_harness
        canary = "sk-proj-abcdef1234567890abcdef1234567890"

        async def go() -> None:
            await partial_update_provider_config(
                FakeSession(), "mod-a", notes=canary, reason="r"
            )

        import asyncio

        with pytest.raises(ProviderRouteConfigError, match="notes"):
            asyncio.run(go())
        assert service.calls == []  # refused BEFORE any mutation
        assert row.notes == "old notes"
        assert not contains_known_secret_shape(row.notes)

    def test_display_name_known_secret_shape_refused(
        self, provider_update_harness
    ) -> None:
        _row, _repo, service = provider_update_harness

        async def go() -> None:
            await partial_update_provider_config(
                FakeSession(),
                "mod-a",
                display_name="Auth: Bearer abcdef1234567890",
                reason="r",
            )

        import asyncio

        with pytest.raises(ProviderRouteConfigError, match="display_name"):
            asyncio.run(go())
        assert service.calls == []

    def test_notes_and_clear_conflict(self, provider_update_harness) -> None:
        row, _repo, service = provider_update_harness

        async def go() -> None:
            await partial_update_provider_config(
                FakeSession(), "mod-a", notes="x", clear_notes=True, reason="r"
            )

        import asyncio

        with pytest.raises(ProviderRouteConfigError, match="notes"):
            asyncio.run(go())
        assert service.calls == []

    def test_missing_provider_not_found(self, provider_update_harness, monkeypatch) -> None:
        monkeypatch.setattr(
            ProviderConfigsRepository,
            "get_provider_config_for_update",
            lambda self, provider_or_id: _missing(),
        )

        async def _missing() -> None:
            return None

        async def go() -> None:
            await partial_update_provider_config(FakeSession(), "ghost", reason="r")

        import asyncio

        from slaif_gateway.services.record_errors import RecordNotFoundError

        with pytest.raises(RecordNotFoundError):
            asyncio.run(go())


# --- route execute (fakes) ------------------------------------------------------------


def _plan_for(row: FakeRouteRow, **edits: Any) -> RouteUpdatePlan:
    return preview_route_update(row, FakeProviderRow(), **edits)


def _route_fingerprint_of(row: FakeRouteRow) -> str:
    return _route_fingerprint(row)


class TestExecuteRouteUpdatePlan:
    @pytest.fixture()
    def harness(self, monkeypatch):
        row = FakeRouteRow()
        provider_row = FakeProviderRow()

        class _Repo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_model_route_for_update(self, route_id: Any) -> Any:
                assert str(route_id) == row.id
                return row

        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                assert provider_or_id == "mod-a"
                return provider_row

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return provider_row

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ModelRoutesRepository", _Repo)
        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository", _PRRepo)
        return row, provider_row

    def test_stale_fingerprint_refused_zero_writes(self, harness) -> None:
        row, _provider_row = harness
        plan = _plan_for(row, priority=50)
        row.priority = 99  # someone else changed the row

        async def go() -> None:
            with pytest.raises(ProviderRouteStaleError):
                await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        asyncio.run(go())

    def test_stale_enabled_refused(self, harness) -> None:
        row, _provider_row = harness
        plan = _plan_for(row, priority=50)
        row.enabled = False

        async def go() -> None:
            with pytest.raises(ProviderRouteStaleError, match="enabled"):
                await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        asyncio.run(go())

    def test_no_op_plan_returns_row_without_service_call(self, harness, monkeypatch) -> None:
        row, _provider_row = harness
        plan = _plan_for(row)  # nothing changed
        calls: list[Any] = []

        class _NoService:
            async def update_model_route(self, *args: Any, **kwargs: Any) -> Any:
                calls.append(kwargs)
                return row

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ModelRouteService", lambda **_: _NoService())

        async def go() -> None:
            return await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        result = asyncio.run(go())
        assert result is row
        assert calls == []  # zero writes, zero audits

    def test_happy_path_merges_and_calls_service_once(self, harness, monkeypatch) -> None:
        row, _provider_row = harness
        plan = _plan_for(row, capability_patch=CapabilityPatch(codex_limits={"max_output_tokens": 400000}), priority=50)
        calls: list[dict[str, Any]] = []

        class _RecordingService:
            async def update_model_route(self, route_id: Any, **kwargs: Any) -> Any:
                calls.append({"route_id": route_id, **kwargs})
                return row

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ModelRouteService", lambda **_: _RecordingService())

        async def go() -> None:
            return await execute_route_update_plan(FakeSession(), plan, reason="reviewed", actor_admin_id=None)

        import asyncio

        asyncio.run(go())
        assert len(calls) == 1
        call = calls[0]
        assert call["priority"] == 50
        assert call["enabled"] is True
        assert call["capabilities"]["codex_limits"]["max_output_tokens"] == 400000
        assert call["capabilities"]["codex_limits"]["context_window_tokens"] == 1050000
        assert call["capabilities"]["codex_limits"]["default_max_output_tokens"] == 32768
        assert call["capabilities"]["chat_completions"] == CHAT_BLOCK
        assert call["notes"] == "route notes"
        # An omitted notes preview carries the CURRENT notes: the service
        # call keeps the default preserve behavior (no explicit clear).
        assert call["clear_notes"] is False

    def test_cleared_notes_target_applies_explicit_clear(self, harness, monkeypatch) -> None:
        """Reviewed canonical target notes=null => the execute path
        applies the EXPLICIT clear (repository writes NULL; the service
        captures the REAL prior notes in its one audit)."""
        row, _provider_row = harness
        plan = _plan_for(row, clear_notes=True)
        assert plan.notes is None
        assert row.notes == "route notes"
        calls: list[dict[str, Any]] = []

        class _RecordingService:
            async def update_model_route(self, route_id: Any, **kwargs: Any) -> Any:
                calls.append({"route_id": route_id, **kwargs})
                return row

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ModelRouteService", lambda **_: _RecordingService())

        async def go() -> None:
            return await execute_route_update_plan(FakeSession(), plan, reason="reviewed")

        import asyncio

        asyncio.run(go())
        assert len(calls) == 1
        assert calls[0]["notes"] is None
        assert calls[0]["clear_notes"] is True

    def test_repeated_apply_refused_stale(self, harness) -> None:
        row, _provider_row = harness
        plan = _plan_for(row, priority=50)
        # Simulate the first apply having already landed: the row now holds
        # the proposed state, so the plan's expected pre-state is stale.
        row.priority = 50

        async def go() -> None:
            with pytest.raises(ProviderRouteStaleError):
                await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        asyncio.run(go())

    def test_proposed_value_revalidation_distinct_from_source_staleness(
        self, harness, monkeypatch
    ) -> None:
        # 199-d: expected_configuration_fingerprint binds the SOURCE
        # pre-state at review time, NOT the plan's proposed values. A
        # valid operator-edited proposal is revalidated against current
        # policy and applies while the source is unchanged; only an
        # actual source mutation behind the plan makes it stale (zero
        # writes, zero audits). Editing a valid scalar is not in itself
        # an authentication or staleness breach.
        row, _provider_row = harness
        plan = _plan_for(row, priority=50)  # source priority is 100
        calls: list[dict[str, Any]] = []

        class _RecordingService:
            async def update_model_route(self, route_id: Any, **kwargs: Any) -> Any:
                calls.append({"route_id": route_id, **kwargs})
                return row

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ModelRouteService", lambda **_: _RecordingService())

        async def go() -> None:
            # 1) source unchanged: proposed scalar (50) differs from the
            #    reviewed pre-state (100) but is valid; it applies once.
            await execute_route_update_plan(FakeSession(), plan, reason="reviewed")
            # 2) source then mutated behind the plan: the SAME plan is
            #    refused stale with no further writes or audits.
            row.priority = 77
            with pytest.raises(ProviderRouteStaleError, match="configuration"):
                await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        asyncio.run(go())
        assert len(calls) == 1
        assert calls[0]["priority"] == 50

    def test_blank_reason_refused_before_locks(self, harness) -> None:
        _row, _provider_row = harness
        async def go() -> None:
            with pytest.raises(ProviderRouteConfigError, match="reason"):
                await execute_route_update_plan(FakeSession(), _plan_for(_row), reason="   ")

        import asyncio

        asyncio.run(go())

    def test_reason_known_secret_shape_refused(self, harness) -> None:
        row, _provider_row = harness

        async def go() -> None:
            with pytest.raises(
                ProviderRouteConfigError, match="credential patterns"
            ):
                await execute_route_update_plan(
                    FakeSession(),
                    _plan_for(row, priority=50),
                    reason="key sk-proj-abcdef1234567890abcdef1234567890",
                )

        import asyncio

        asyncio.run(go())

    def test_route_identity_swap_refused(self, harness, monkeypatch) -> None:
        # 199-b R2: a DIFFERENT route carrying identical configuration can
        # never reuse the reviewed expected pre-state: even if the expected
        # fingerprint were recomputed for the twin row, the bound
        # expected_route_id still refuses it.
        twin_id = "22222222-3333-4444-8555-666666666666"
        twin = FakeRouteRow(id=twin_id)

        class _TwinRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_model_route_for_update(self, route_id: Any) -> Any:
                assert str(route_id) == twin_id
                return twin

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ModelRoutesRepository", _TwinRepo)
        plan = _plan_for(twin, priority=50)
        tampered = dataclasses.replace(
            plan,
            route_id=twin_id,
            expected_route_id=ROUTE_ID,  # still bound to the reviewed route
            expected_configuration_fingerprint=_route_fingerprint_of(twin),  # type: ignore[arg-type]
        )

        async def go() -> None:
            with pytest.raises(ProviderRouteStaleError, match="route identity"):
                await execute_route_update_plan(FakeSession(), tampered, reason="r")

        import asyncio

        asyncio.run(go())

    def test_provider_context_stale_after_preview(self, harness, monkeypatch) -> None:
        # 199-b R2: a meaningful destination-provider edit AFTER the review
        # (retries 0 -> 2) makes the plan stale — the adapter forbids
        # retries, so this must not be "revalidated and silently accepted".
        row, provider_row = harness
        plan = _plan_for(row, priority=50)
        provider_row.max_retries = 2

        async def go() -> None:
            with pytest.raises(ProviderRouteStaleError, match="provider context"):
                await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        asyncio.run(go())

    def test_provider_identity_stale(self, harness, monkeypatch) -> None:
        # The destination provider ROW was replaced by another provider
        # with identical context fields: identity binding still refuses.
        row, _provider_row = harness
        plan = _plan_for(row, priority=50)
        impostor = FakeProviderRow(
            id=SECOND_PROVIDER_ID, provider="mod-a", kind="module"
        )

        class _ImpostorRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                return impostor

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return impostor

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository", _ImpostorRepo)

        async def go() -> None:
            with pytest.raises(ProviderRouteStaleError, match="provider identity"):
                await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        asyncio.run(go())

    def test_missing_destination_provider_stale(self, harness, monkeypatch) -> None:
        # The reviewed destination provider no longer EXISTS at apply time.
        row, _provider_row = harness
        plan = _plan_for(row, priority=50)

        class _GoneRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                return None

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return None

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository", _GoneRepo)

        async def go() -> None:
            with pytest.raises(
                ProviderRouteStaleError, match="destination provider"
            ):
                await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        asyncio.run(go())


class TestPreviewForRoute:
    def test_missing_route_not_found(self, monkeypatch) -> None:
        from slaif_gateway.services.record_errors import RecordNotFoundError

        class _Repo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_model_route_by_id(self, route_id: Any) -> Any:
                return None

        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return object()

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ModelRoutesRepository", _Repo)
        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository", _PRRepo)

        async def go() -> None:
            await preview_route_update_for_route(FakeSession(), ROUTE_ID)

        import asyncio

        with pytest.raises(RecordNotFoundError):
            asyncio.run(go())

    def test_missing_provider_refused(self, monkeypatch) -> None:
        row = FakeRouteRow()

        class _Repo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_model_route_by_id(self, route_id: Any) -> Any:
                return row

        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return None

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ModelRoutesRepository", _Repo)
        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository", _PRRepo)

        async def go() -> None:
            await preview_route_update_for_route(FakeSession(), row.id)

        import asyncio

        with pytest.raises(ProviderRouteConfigError, match="provider configuration"):
            asyncio.run(go())

    def test_cross_provider_preview_resolves_destination(self, monkeypatch) -> None:
        # 199-b R2: the destination provider is resolved from the PROPOSED
        # candidate (not the route's old provider) and bound into the plan.
        row = FakeRouteRow(provider="mod-a")
        destination = FakeProviderRow(
            id=SECOND_PROVIDER_ID, provider="mod-b", kind="openai_compatible"
        )

        class _Repo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_model_route_by_id(self, route_id: Any) -> Any:
                return row

        lookups: list[str] = []

        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                lookups.append(provider)
                if provider == "mod-b":
                    return destination
                return FakeProviderRow()

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                return destination

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ModelRoutesRepository", _Repo)
        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository", _PRRepo)

        async def go() -> RouteUpdatePlan:
            return await preview_route_update_for_route(
                FakeSession(), row.id, provider="mod-b"
            )

        import asyncio

        plan = asyncio.run(go())
        assert lookups == ["mod-b"]  # destination, not the old provider
        assert plan.provider == "mod-b"
        assert plan.expected_provider_id == str(SECOND_PROVIDER_ID)
        assert plan.expected_provider_context_fingerprint == (
            compute_provider_context_fingerprint(destination)
        )


# --- merged candidate validator -----------------------------------------------------


class TestValidateMergedRouteCandidate:
    def test_transport_requires_compatible_kind(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="openai_compatible"):
            validate_merged_route_candidate(
                {
                    "vllm_chat_video": {"version": 1},
                    "media_input_estimation": {
                        "version": 1,
                        "video_frames": 8,
                        "video_tokens": 1024,
                    },
                },
                endpoint="/v1/chat/completions",
                provider="p",
                provider_row=FakeProviderRow(kind="module"),
                requested_model="m",
                upstream_model="m",
                supports_streaming=False,
            )

    def test_completion_endpoint_mismatch_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="chat completions endpoint"):
            validate_merged_route_candidate(
                {"completion_service": {"version": 1, "profile": "zap-it-v1"}},
                endpoint="/v1/embeddings",
                provider="p",
                provider_row=FakeProviderRow(kind="module"),
                requested_model="zap-it-1",
                upstream_model="zap-it-1",
                supports_streaming=False,
            )

    def test_completion_retrying_provider_refused(self) -> None:
        # 199-b: the completion adapter raises on max_retries != 0, so the
        # configuration-time candidate validation enforces zero retries.
        with pytest.raises(ProviderRouteConfigError, match="must not retry"):
            validate_merged_route_candidate(
                {"completion_service": {"version": 1, "profile": "zap-it-v1"}},
                endpoint="/v1/chat/completions",
                provider="p",
                provider_row=FakeProviderRow(kind="module", max_retries=2),
                requested_model="zap-it-1",
                upstream_model="zap-it-1",
                supports_streaming=False,
            )


    # --- 199-c: complete pure module/transport parity ----------------------------------

    def _completion_kwargs(self, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = dict(
            endpoint="/v1/chat/completions",
            provider="facial_scoring",
            requested_model="facial-manipulation-scoring",
            upstream_model="facial-manipulation-scoring",
            supports_streaming=False,
        )
        base.update(overrides)
        return base

    def test_unknown_module_without_selector_refused(self) -> None:
        # Module-kind provider with no selector and no legacy binding:
        # the existing pure resolver says unsupported_module, so the
        # configuration-time candidate must refuse it too.
        with pytest.raises(ProviderRouteConfigError, match="supported server module"):
            validate_merged_route_candidate(
                {"chat_completions": dict(CHAT_BLOCK)},
                endpoint="/v1/chat/completions",
                provider="ghost-mod",
                provider_row=FakeProviderRow(provider="ghost-mod", kind="module"),
                requested_model="m",
                upstream_model="m",
                supports_streaming=True,
            )

    def test_legacy_binding_valid_without_selector(self) -> None:
        # Implicit binding (bindings.json: facial_scoring -> facial-scoring-v1)
        # is a supported declaration and must pass the SAME completion
        # contract as an explicit selector.
        document = validate_merged_route_candidate(
            {"chat_completions": {"chat_text": True, "chat_streaming": False}},
            **self._completion_kwargs(),
            provider_row=FakeProviderRow(provider="facial_scoring", kind="module"),
        )
        assert "completion_service" not in document  # no fabricated selector

    def test_legacy_binding_wrong_public_model_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="profile public model"):
            validate_merged_route_candidate(
                {"chat_completions": {"chat_text": True, "chat_streaming": False}},
                **self._completion_kwargs(requested_model="wrong-model"),
                provider_row=FakeProviderRow(provider="facial_scoring", kind="module"),
            )

    def test_legacy_binding_wrong_upstream_model_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="profile upstream model"):
            validate_merged_route_candidate(
                {"chat_completions": {"chat_text": True, "chat_streaming": False}},
                **self._completion_kwargs(upstream_model="other-model"),
                provider_row=FakeProviderRow(provider="facial_scoring", kind="module"),
            )

    def test_legacy_binding_wrong_endpoint_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="chat completions endpoint"):
            validate_merged_route_candidate(
                {"chat_completions": {"chat_text": True, "chat_streaming": False}},
                **self._completion_kwargs(endpoint="/v1/responses"),
                provider_row=FakeProviderRow(provider="facial_scoring", kind="module"),
            )

    def test_legacy_binding_retrying_provider_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="must not retry"):
            validate_merged_route_candidate(
                {"chat_completions": {"chat_text": True, "chat_streaming": False}},
                **self._completion_kwargs(),
                provider_row=FakeProviderRow(
                    provider="facial_scoring", kind="module", max_retries=1
                ),
            )

    def test_explicit_selector_streaming_flag_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="streaming"):
            validate_merged_route_candidate(
                {
                    "chat_completions": {"chat_text": True, "chat_streaming": False},
                    "completion_service": {"version": 1, "profile": "zap-it-v1"},
                },
                endpoint="/v1/chat/completions",
                provider="mod-a",
                provider_row=FakeProviderRow(kind="module"),
                requested_model="zap-it-1",
                upstream_model="zap-it-1",
                supports_streaming=True,
            )

    def test_implicit_binding_streaming_flag_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="streaming"):
            validate_merged_route_candidate(
                {"chat_completions": {"chat_text": True, "chat_streaming": False}},
                **self._completion_kwargs(supports_streaming=True),
                provider_row=FakeProviderRow(provider="facial_scoring", kind="module"),
            )

    def test_explicit_selector_chat_streaming_capability_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="advertise streaming"):
            validate_merged_route_candidate(
                {
                    "chat_completions": {"chat_text": True, "chat_streaming": True},
                    "completion_service": {"version": 1, "profile": "zap-it-v1"},
                },
                endpoint="/v1/chat/completions",
                provider="mod-a",
                provider_row=FakeProviderRow(kind="module"),
                requested_model="zap-it-1",
                upstream_model="zap-it-1",
                supports_streaming=False,
            )

    def test_implicit_binding_chat_streaming_capability_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="advertise streaming"):
            validate_merged_route_candidate(
                {"chat_completions": {"chat_text": True, "chat_streaming": True}},
                **self._completion_kwargs(),
                provider_row=FakeProviderRow(provider="facial_scoring", kind="module"),
            )

    def test_operator_directory_resolves_implicit_binding(self, tmp_path) -> None:
        # The SAME configured operator directory the runtime uses applies
        # to implicit bindings, not only explicit selectors.
        import os

        from pathlib import Path as _Path

        bundled = (
            _Path(__file__).resolve().parents[2]
            / "app/slaif_gateway/modules/servers/completion_service/profiles/facial-scoring-v1.json"
        )
        directory = tmp_path / "profiles-199c"
        directory.mkdir()
        target = directory / "facial-scoring-v1.json"
        target.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")
        os.chmod(target, 0o600)  # operator directories enforce 0600
        document = validate_merged_route_candidate(
            {"chat_completions": {"chat_text": True, "chat_streaming": False}},
            **self._completion_kwargs(),
            provider_row=FakeProviderRow(provider="facial_scoring", kind="module"),
            profile_dir=str(directory),
        )
        assert document["chat_completions"]["chat_streaming"] is False

    def test_operator_directory_missing_profile_refused(self, tmp_path) -> None:
        directory = tmp_path / "profiles-199c-empty"
        directory.mkdir()
        with pytest.raises(ProviderRouteConfigError, match="valid available profile selector"):
            validate_merged_route_candidate(
                {"chat_completions": {"chat_text": True, "chat_streaming": False}},
                **self._completion_kwargs(),
                provider_row=FakeProviderRow(provider="facial_scoring", kind="module"),
                profile_dir=str(directory),
            )


# --- route creation candidate (199-b R4) ---------------------------------------------


def _creation_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        requested_model="plain-1",
        match_type="exact",
        provider="mod-a",
        upstream_model="plain-1",
        priority=50,
        visible_in_models=True,
        enabled=True,
        supports_streaming=True,
        notes=None,
        endpoint="/v1/chat/completions",
        capabilities={"chat_completions": dict(CHAT_BLOCK)},
    )
    base.update(overrides)
    return base


class TestValidateRouteCreationCandidate:
    def test_missing_provider_refused(self, monkeypatch) -> None:
        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return None

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                return None

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository", _PRRepo)

        async def go() -> None:
            await validate_route_creation_candidate(
                FakeSession(),
                requested_model="m",
                match_type="exact",
                provider="ghost",
                upstream_model=None,
                priority=100,
                visible_in_models=True,
                enabled=False,
                supports_streaming=True,
                notes=None,
                endpoint="/v1/chat/completions",
                capabilities=None,
            )

        import asyncio

        with pytest.raises(ProviderRouteConfigError, match="provider configuration"):
            asyncio.run(go())

    def test_valid_candidate_accepted(self, monkeypatch) -> None:
        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return FakeProviderRow(kind="openai_compatible")

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                return FakeProviderRow(kind="openai_compatible")

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository", _PRRepo)

        async def go() -> None:
            await validate_route_creation_candidate(FakeSession(), **_creation_kwargs())

        import asyncio

        asyncio.run(go())  # no exception: valid configuration accepted

    def test_completion_retrying_provider_refused_on_create(self, monkeypatch) -> None:
        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return FakeProviderRow(kind="module", max_retries=2)

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                return FakeProviderRow(kind="module", max_retries=2)

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository", _PRRepo)

        async def go() -> None:
            await validate_route_creation_candidate(
                FakeSession(),
                **_creation_kwargs(
                    capabilities={
                        "chat_completions": dict(CHAT_BLOCK),
                        "completion_service": {"version": 1, "profile": "zap-it-v1"},
                    }
                ),
            )

        import asyncio

        with pytest.raises(ProviderRouteConfigError, match="must not retry"):
            asyncio.run(go())

    def test_notes_known_secret_shape_refused(self, monkeypatch) -> None:
        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return FakeProviderRow()

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                return FakeProviderRow()

        monkeypatch.setattr("slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository", _PRRepo)
        canary = "sk-proj-abcdef1234567890abcdef1234567890"

        async def go() -> None:
            await validate_route_creation_candidate(
                FakeSession(), **_creation_kwargs(notes=canary, capabilities=None)
            )

        import asyncio

        with pytest.raises(ProviderRouteConfigError, match="notes"):
            asyncio.run(go())

    # --- 199-c: complete module/transport parity at creation ---------------------

    def test_unknown_module_refused_on_create(self, monkeypatch) -> None:
        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return FakeProviderRow(provider="ghost-mod", kind="module")

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                return FakeProviderRow(provider="ghost-mod", kind="module")

        monkeypatch.setattr(
            "slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository",
            _PRRepo,
        )

        async def go() -> None:
            await validate_route_creation_candidate(
                FakeSession(), **_creation_kwargs(provider="ghost-mod")
            )

        import asyncio

        with pytest.raises(ProviderRouteConfigError, match="supported server module"):
            asyncio.run(go())

    def test_legacy_binding_valid_on_create(self, monkeypatch) -> None:
        # Implicit legacy binding with truthful no-streaming declarations
        # is a valid NEW route (no selector needed).
        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return FakeProviderRow(provider="facial_scoring", kind="module")

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                return FakeProviderRow(provider="facial_scoring", kind="module")

        monkeypatch.setattr(
            "slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository",
            _PRRepo,
        )

        async def go() -> None:
            await validate_route_creation_candidate(
                FakeSession(),
                **_creation_kwargs(
                    provider="facial_scoring",
                    requested_model="facial-manipulation-scoring",
                    upstream_model="facial-manipulation-scoring",
                    supports_streaming=False,
                    capabilities={
                        "chat_completions": {
                            "chat_text": True,
                            "chat_streaming": False,
                        }
                    },
                ),
            )

        import asyncio

        asyncio.run(go())  # no exception: supported implicit binding

    def test_completion_streaming_refused_on_create(self, monkeypatch) -> None:
        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return FakeProviderRow(provider="facial_scoring", kind="module")

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                return FakeProviderRow(provider="facial_scoring", kind="module")

        monkeypatch.setattr(
            "slaif_gateway.services.provider_route_configuration.ProviderConfigsRepository",
            _PRRepo,
        )

        async def go() -> None:
            await validate_route_creation_candidate(
                FakeSession(),
                **_creation_kwargs(
                    provider="facial_scoring",
                    requested_model="facial-manipulation-scoring",
                    upstream_model="facial-manipulation-scoring",
                    supports_streaming=True,
                    capabilities={
                        "chat_completions": {
                            "chat_text": True,
                            "chat_streaming": False,
                        }
                    },
                ),
            )

        import asyncio

        with pytest.raises(ProviderRouteConfigError, match="streaming"):
            asyncio.run(go())

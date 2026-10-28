"""Objective 199-a: strict provider/route configuration contracts (unit).

Covers the versioned file envelopes (capabilities file, route update plan),
the typed partial capability patch, the merge/preserve law, the public
configuration fingerprint, and the shared typed operations (provider
partial update, route preview/execute) against fakes — no database, no
network, no credential loading.
"""

from __future__ import annotations

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
    compute_route_configuration_fingerprint,
    execute_route_update_plan,
    partial_update_provider_config,
    preview_route_update,
    preview_route_update_for_route,
    validate_merged_route_candidate,
)

CHAT_BLOCK = {"chat_text": True, "chat_streaming": True, "chat_function_tools": False}
CODEX_BLOCK = {
    "context_window_tokens": 1050000,
    "default_max_output_tokens": 32768,
    "max_output_tokens": 128000,
}
ROUTE_ID = "11111111-2222-4333-8444-555555555555"
PROVIDER_ID = uuid.UUID("99999999-8888-4777-8666-555555555555")


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
    kind: str = "module"
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

    def test_preserved_local_coding_groups_pass_through(self) -> None:
        document = _parse(
            _caps_doc(
                capabilities={
                    "chat_completions": dict(CHAT_BLOCK),
                    "local_coding": {"contract_version": 1, "route_name": "r1"},
                    "local_coding_vllm": {"contract_version": 1, "route_name": "r1"},
                }
            )
        )
        assert "local_coding" in document

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

    @pytest.mark.parametrize("field", ["requested_model", "priority", "enabled", "notes"])
    def test_sensitive_to_config_fields(self, field: str) -> None:
        value = _fingerprint()
        overrides = {
            "requested_model": "m2",
            "priority": 2,
            "enabled": False,
            "notes": "n2",
        }[field]
        assert _fingerprint(**{field: overrides}) != value

    def test_identity_and_timestamps_excluded(self) -> None:
        # The fingerprint function takes no id/created_at/updated_at at all.
        import inspect

        signature = inspect.signature(compute_route_configuration_fingerprint)
        names = set(signature.parameters)
        assert not {"id", "created_at", "updated_at"} & names


# --- route plan document -----------------------------------------------------------


def _plan_doc(**overrides: Any) -> dict[str, Any]:
    document = {
        "schema_version": 1,
        "route_id": ROUTE_ID,
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


# --- preview (pure) -----------------------------------------------------------------


class TestPreviewRouteUpdate:
    def test_unchanged_mode_no_changes(self) -> None:
        plan = preview_route_update(FakeRouteRow(), "module")
        assert plan.capabilities_mode == "unchanged"
        assert plan.preview["changed_fields"] == []
        assert plan.enabled is True

    def test_partial_codex_change(self) -> None:
        plan = preview_route_update(
            FakeRouteRow(),
            "module",
            capability_patch=CapabilityPatch(codex_limits={"max_output_tokens": 400000}),
        )
        assert plan.capabilities_mode == "partial"
        assert plan.preview["changed_fields"] == ["capabilities"]
        assert len(plan.expected_configuration_fingerprint) == 64
        int(plan.expected_configuration_fingerprint, 16)

    def test_field_change_tracked(self) -> None:
        plan = preview_route_update(FakeRouteRow(), "module", priority=50, notes="other")
        assert sorted(plan.preview["changed_fields"]) == ["notes", "priority"]

    def test_endpoint_alias_normalized(self) -> None:
        plan = preview_route_update(FakeRouteRow(), "module", endpoint="chat.completions")
        assert plan.endpoint == "/v1/chat/completions"
        assert "endpoint" not in plan.preview["changed_fields"]

    def test_invalid_endpoint_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError):
            preview_route_update(FakeRouteRow(), "module", endpoint="   ")

    def test_clear_notes_changes(self) -> None:
        plan = preview_route_update(FakeRouteRow(), "module", clear_notes=True)
        assert plan.notes is None
        assert "notes" in plan.preview["changed_fields"]

    def test_notes_and_clear_conflict(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="notes"):
            preview_route_update(FakeRouteRow(), "module", notes="x", clear_notes=True)

    def test_codex_relationship_broken_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="codex_limits"):
            preview_route_update(
                FakeRouteRow(),
                "module",
                capability_patch=CapabilityPatch(codex_limits={"context_window_tokens": 10}),
            )

    def test_completion_kind_mismatch_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="module provider kind"):
            preview_route_update(
                FakeRouteRow(),
                "openai_compatible",
                capabilities_document={"completion_service": {"version": 1, "profile": "zap-it-v1"}},
            )

    def test_completion_model_mismatch_refused(self) -> None:
        route = FakeRouteRow(requested_model="wrong", upstream_model="wrong")
        with pytest.raises(ProviderRouteConfigError, match="profile public model"):
            preview_route_update(
                route,
                "module",
                capabilities_document={"completion_service": {"version": 1, "profile": "zap-it-v1"}},
            )

    def test_completion_profile_valid_for_matching_route(self) -> None:
        plan = preview_route_update(
            FakeRouteRow(),
            "module",
            capability_patch=CapabilityPatch(
                completion_service={"version": 1, "profile": "zap-it-v1"}
            ),
        )
        assert plan.capabilities_mode == "partial"

    def test_full_replacement_mode(self) -> None:
        plan = preview_route_update(
            FakeRouteRow(),
            "module",
            capabilities_document={
                "chat_completions": {"chat_text": True, "chat_streaming": False}
            },
        )
        assert plan.capabilities_mode == "full-replacement"
        assert plan.capabilities == {"chat_completions": {"chat_text": True, "chat_streaming": False}}

    def test_plan_round_trips_through_file(self) -> None:
        plan = preview_route_update(
            FakeRouteRow(),
            "module",
            capability_patch=CapabilityPatch(codex_limits={"max_output_tokens": 400000}),
            priority=77,
        )
        data = json.dumps(render_route_update_plan(plan)).encode("utf-8")
        again = parse_route_update_plan_file(data)
        assert again.capability_patch.codex_limits == {"max_output_tokens": 400000}
        assert again.priority == 77


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

    import slaif_gateway.services.provider_route_configuration as prc

    monkeypatch.setattr(
        prc.ProviderConfigsRepository,
        "get_provider_config_for_update",
        lambda self, provider_or_id: repo.get_provider_config_for_update(provider_or_id),
    )
    monkeypatch.setattr(
        prc,
        "ProviderConfigService",
        lambda **_: service,
    )
    monkeypatch.setattr(
        prc,
        "AuditRepository",
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
        assert call["kind"] == "module"
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

        async def go() -> None:
            session = FakeSession()
            await partial_update_provider_config(
                session, "mod-a", clear_notes=True, reason="r"
            )
            return session

        import asyncio

        session = asyncio.run(go())
        assert row.notes is None  # cleared in the locked row before the service write
        assert service.calls[0]["notes"] is None
        assert session.flushes == 1

    def test_clear_notes_no_flush_when_already_empty(self, provider_update_harness) -> None:
        row, _repo, _service = provider_update_harness
        row.notes = None

        async def go() -> None:
            session = FakeSession()
            await partial_update_provider_config(session, "mod-a", clear_notes=True, reason="r")
            return session

        import asyncio

        session = asyncio.run(go())
        assert session.flushes == 0

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
        import slaif_gateway.services.provider_route_configuration as prc

        monkeypatch.setattr(
            prc.ProviderConfigsRepository,
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
    return preview_route_update(row, "module", **edits)


class TestExecuteRouteUpdatePlan:
    @pytest.fixture()
    def harness(self, monkeypatch):
        import slaif_gateway.services.provider_route_configuration as prc

        row = FakeRouteRow()

        class _Repo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_model_route_for_update(self, route_id: Any) -> Any:
                assert str(route_id) == row.id
                return row

        class _Provider:
            id = PROVIDER_ID
            provider = "mod-a"
            kind = "module"
            enabled = False

        class _PRRepo:
            def __init__(self, session: Any) -> None:
                pass

            async def get_provider_config_for_update(self, provider_or_id: str) -> Any:
                return _Provider()

            async def get_provider_config_by_provider(self, provider: str) -> Any:
                return _Provider()

        monkeypatch.setattr(prc, "ModelRoutesRepository", _Repo)
        monkeypatch.setattr(prc, "ProviderConfigsRepository", _PRRepo)
        return row

    def test_stale_fingerprint_refused_zero_writes(self, harness) -> None:
        row = harness
        plan = _plan_for(row, priority=50)
        row.priority = 99  # someone else changed the row

        async def go() -> None:
            with pytest.raises(ProviderRouteStaleError):
                await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        asyncio.run(go())

    def test_stale_enabled_refused(self, harness) -> None:
        row = harness
        plan = _plan_for(row, priority=50)
        row.enabled = False

        async def go() -> None:
            with pytest.raises(ProviderRouteStaleError, match="enabled"):
                await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        asyncio.run(go())

    def test_no_op_plan_returns_row_without_service_call(self, harness, monkeypatch) -> None:
        import slaif_gateway.services.provider_route_configuration as prc

        row = harness
        plan = _plan_for(row)  # nothing changed
        calls: list[Any] = []

        class _NoService:
            async def update_model_route(self, *args: Any, **kwargs: Any) -> Any:
                calls.append(kwargs)
                return row

        monkeypatch.setattr(prc, "ModelRouteService", lambda **_: _NoService())

        async def go() -> None:
            return await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        result = asyncio.run(go())
        assert result is row
        assert calls == []  # zero writes, zero audits

    def test_happy_path_merges_and_calls_service_once(self, harness, monkeypatch) -> None:
        import slaif_gateway.services.provider_route_configuration as prc

        row = harness
        plan = _plan_for(row, capability_patch=CapabilityPatch(codex_limits={"max_output_tokens": 400000}), priority=50)
        calls: list[dict[str, Any]] = []

        class _RecordingService:
            async def update_model_route(self, route_id: Any, **kwargs: Any) -> Any:
                calls.append({"route_id": route_id, **kwargs})
                return row

        monkeypatch.setattr(prc, "ModelRouteService", lambda **_: _RecordingService())

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

    def test_repeated_apply_refused_stale(self, harness) -> None:
        row = harness
        plan = _plan_for(row, priority=50)
        # Simulate the first apply having already landed: the row now holds
        # the proposed state, so the plan's expected pre-state is stale.
        row.priority = 50

        async def go() -> None:
            with pytest.raises(ProviderRouteStaleError):
                await execute_route_update_plan(FakeSession(), plan, reason="r")

        import asyncio

        asyncio.run(go())


class TestPreviewForRoute:
    def test_missing_route_not_found(self, monkeypatch) -> None:
        import slaif_gateway.services.provider_route_configuration as prc

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

        monkeypatch.setattr(prc, "ModelRoutesRepository", _Repo)
        monkeypatch.setattr(prc, "ProviderConfigsRepository", _PRRepo)

        async def go() -> None:
            await preview_route_update_for_route(FakeSession(), ROUTE_ID)

        import asyncio

        with pytest.raises(RecordNotFoundError):
            asyncio.run(go())

    def test_missing_provider_refused(self, monkeypatch) -> None:
        import slaif_gateway.services.provider_route_configuration as prc

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

        monkeypatch.setattr(prc, "ModelRoutesRepository", _Repo)
        monkeypatch.setattr(prc, "ProviderConfigsRepository", _PRRepo)

        async def go() -> None:
            await preview_route_update_for_route(FakeSession(), row.id)

        import asyncio

        with pytest.raises(ProviderRouteConfigError, match="provider configuration"):
            asyncio.run(go())


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
                provider_kind="module",
                requested_model="m",
                upstream_model="m",
            )

    def test_completion_endpoint_mismatch_refused(self) -> None:
        with pytest.raises(ProviderRouteConfigError, match="chat completions endpoint"):
            validate_merged_route_candidate(
                {"completion_service": {"version": 1, "profile": "zap-it-v1"}},
                endpoint="/v1/embeddings",
                provider="p",
                provider_kind="module",
                requested_model="zap-it-1",
                upstream_model="zap-it-1",
            )

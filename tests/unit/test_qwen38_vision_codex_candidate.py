from __future__ import annotations

import base64
import hashlib
import json
import threading
from types import MappingProxyType, SimpleNamespace

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    responses_image_input_requested,
)
from scripts import verify_qwen38_vision_codex as verifier
import slaif_gateway.services.codex_profile_registry as registry


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "qwen3.8-27b-vision",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Describe the image."},
                    {"type": "input_image", "image_url": verifier.synthetic_png_data_url()},
                ],
            }
        ],
        "max_output_tokens": 20,
        "store": False,
    }
    body.update(overrides)
    return body


def test_candidate_is_exact_and_unregistered() -> None:
    profile = registry.QWEN38_VISION_CODEX_CANDIDATE
    assert profile.profile_id == registry.QWEN38_VISION_PROFILE_ID
    assert profile.public_model == "qwen3.8-27b-vision"
    assert profile.upstream_model == "qwen3.8-27b"
    assert profile.cli_version == "0.148.0"
    assert profile.context_window_tokens == 100_000
    assert profile.auto_compaction_token_threshold == 75_000
    assert profile.default_max_output_tokens == 8_192
    assert profile.max_output_tokens == 24_576
    assert profile.input_modalities == ("text", "image")
    assert profile.local_tools == ("function",)
    assert "image_input" in profile.required_route_gates
    assert profile.catalog_source == "replacement"
    assert profile.mocked_qualification is True
    assert profile.live_qualification is False
    assert registry.get_codex_profile(profile.profile_id) is None


def test_candidate_registry_is_immutable_and_valid() -> None:
    profiles = MappingProxyType({
        registry.OPENAI_CODEX_PROFILE.profile_id: registry.OPENAI_CODEX_PROFILE,
        registry.QWEN38_VISION_CODEX_CANDIDATE.profile_id: registry.QWEN38_VISION_CODEX_CANDIDATE,
    })
    registry.validate_codex_profile_registry(profiles)


def test_catalog_artifact_explicitly_denies_unsafe_authority() -> None:
    artifact = json.loads(registry.QWEN38_VISION_CODEX_CANDIDATE.model_catalog_artifact)
    model = artifact["models"][0]
    assert model["input_modalities"] == ["text", "image"]
    assert model["supports_search_tool"] is False
    assert model["supports_parallel_tool_calls"] is False
    assert model["supports_reasoning_summaries"] is False
    assert model["supports_image_detail_original"] is False
    assert "apply_patch_tool_type" not in model


def test_synthetic_fixture_is_small_inline_png() -> None:
    url = verifier.synthetic_png_data_url()
    raw = base64.b64decode(url.partition(",")[2])
    assert url.startswith("data:image/png;base64,")
    assert len(raw) <= 16_000


def test_remote_image_urls_are_not_accepted_as_inline_data() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(
        _body(
            input=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_image", "image_url": "https://example.invalid/image.png"}],
                }
            ]
        )
    )
    part = result.effective_body["input"][0]["content"][0]
    assert part["image_url"] == "https://example.invalid/image.png"
    assert responses_image_input_requested(result.effective_body) is True


@pytest.mark.parametrize("url", ["ftp://example.invalid/image.png", "data:text/plain;base64,aGVsbG8="])
def test_non_http_or_non_image_url_shapes_are_rejected(url: str) -> None:
    with pytest.raises(RequestPolicyError):
        ResponsesRequestPolicy(Settings()).apply(
            _body(
                input=[
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_image", "image_url": url}],
                    }
                ]
            )
        )


def test_remote_https_image_is_rejected_by_route_capability_boundary() -> None:
    from slaif_gateway.services.responses_route_capabilities import (
        enforce_responses_route_capabilities,
        default_responses_capabilities,
    )

    capabilities = default_responses_capabilities()
    capabilities.update({"text": True, "stateless": True, "streaming": True})
    body = _body(
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_image", "image_url": "https://example.invalid/image.png"}],
            }
        ]
    )
    with pytest.raises(Exception):
        enforce_responses_route_capabilities(
            route_capabilities=capabilities,
            streaming_requested=True,
            route_supports_streaming=True,
            image_input_requested=False,
        )


def test_single_inline_image_is_accepted_and_detected() -> None:
    result = ResponsesRequestPolicy(Settings()).apply(_body())
    item = result.effective_body["input"][0]
    images = [part for part in item["content"] if part.get("type") == "input_image"]
    assert len(images) == 1
    assert responses_image_input_requested(result.effective_body) is True


@pytest.mark.parametrize("count", [2, 3])
def test_multi_image_requests_are_rejected_by_global_cap(count: int) -> None:
    body = _body()
    body["input"][0]["content"].extend(
        {"type": "input_image", "image_url": verifier.synthetic_png_data_url()} for _ in range(count)
    )
    with pytest.raises(RequestPolicyError) as caught:
        ResponsesRequestPolicy(Settings(RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST=1)).apply(body)
    assert caught.value.error_code == "responses_input_image_count_exceeded"


def test_hermetic_runner_seam_returns_structural_result() -> None:
    def runner() -> dict[str, object]:
        return {
            "codex_version": "0.148.0", "request_count": 2, "event_count": 10,
            "accounting_proved": True, "privacy_proved": True,
        }

    result = verifier.run_hermetic_phase(runner=runner)
    assert result["request_count"] == 2
    assert result["accounting_proved"] is True


def test_absent_live_environment_reports_safely_without_network() -> None:
    assert verifier.validate_environment({}) == "live_target_absent"


def test_present_live_environment_enters_sequential_guard() -> None:
    calls: list[str] = []

    def live(base_url: str, api_key: str) -> dict[str, object]:
        calls.extend((base_url, api_key))
        return {"real_provider_called": True}

    assert verifier.validate_environment({
        verifier.BASE_URL_ENV: "http://10.0.0.1:18020/v1",
        verifier.API_KEY_ENV: "bounded-lan-key",
    }) == "live_target_present"

    def first() -> None:
        with verifier.LIVE_GUARD.acquire():
            try:
                verifier.run_live_phase(base_url="http://10.0.0.1:18020/v1", api_key="x", runner=live)
            except verifier.VerificationError as exc:
                calls.append(str(exc))

    thread = threading.Thread(target=first)
    thread.start()
    thread.join()
    assert calls == ["live_execution_must_be_sequential"]


def test_live_phase_requires_observed_real_provider() -> None:
    with pytest.raises(verifier.VerificationError):
        verifier.run_live_phase(
            base_url="http://127.0.0.1:8080/v1",
            api_key="private-test-key",
            runner=lambda *_: {"real_provider_called": False},
        )


def test_candidate_not_selectable_until_registered_or_live_qualified() -> None:
    from slaif_gateway.services.codex_qualification import CodexQualificationService

    service = CodexQualificationService(
        provider_configs_repository=None,
        model_routes_repository=None,
        pricing_rules_repository=None,
        fx_rates_repository=None,
        profile_registry=MappingProxyType({}),
    )
    import asyncio

    async def reject() -> None:
        await service.ready_responses_profile(
            provider="openai_compatible",
            qualification_profile=registry.QWEN38_VISION_PROFILE_ID,
        )

    with pytest.raises(ValueError, match="Unknown Codex qualification profile"):
        asyncio.run(reject())


def test_accounting_proof_rejects_incomplete_live_facts() -> None:
    accounting = SimpleNamespace(
        requests_used=2, tokens_used=5, requests_reserved=0, tokens_reserved=0,
        cost_reserved_eur=0, reservation_statuses=("finalized", "finalized"),
        ledger_statuses=("finalized", "finalized"), ledger_successes=(True, True),
        ledger_error_types=(None, None), ledger_http_statuses=(200, 200),
        ledger_native_currencies=("EUR", "EUR"), usage=((3, 0, 1, 0, 4), (1, 0, 1, 0, 2)),
        ledger_actual_costs_eur=(0, 0), cost_used_eur=0,
    )
    assert verifier._accounting_proved(accounting, pending=0, exact_hermetic=False) is False


def test_text_profile_regression_exactness() -> None:
    profile = registry.QWEN38_TEXT_CODEX_CANDIDATE
    assert profile.input_modalities == ("text",)
    assert profile.public_model == "qwen3.8-27b-text"

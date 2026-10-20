"""Media transport bytes, bounded admission budgets, and native-video gates."""

import base64
from types import SimpleNamespace

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.services.media_input_estimation import (
    MediaInputEstimateError,
    apply_media_input_estimate,
    video_frame_limit,
)
from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    apply_codex_route_limits,
)
from slaif_gateway.services.chat_completion_route_capabilities import (
    default_chat_completion_capabilities,
    enforce_chat_completion_route_capabilities,
)
from slaif_gateway.services.chat_completion_gateway import _build_safe_chat_completion_upstream_body
from slaif_gateway.modules.servers.vllm_chat_video import VLLMChatVideoAdapter
from slaif_gateway.schemas.providers import ProviderRequest
from slaif_gateway.services.policy_errors import RequestPolicyError


def _url(size=474454, kind="image/png"):
    return "data:" + kind + ";base64," + base64.b64encode(b"a" * size).decode()


def _chat(url=None, kind="image_url"):
    return {
        "model": "synthetic",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this media."},
                    {"type": kind, kind: {"url": url or _url()}},
                ],
            }
        ],
    }


def _caps(**budget):
    return {
        "media_input_estimation": {"version": 1, **budget},
        **({"vllm_chat_video": {"version": 1}} if "video_frames" in budget else {}),
    }


def _policy(body):
    return ChatCompletionRequestPolicy(Settings()).apply(body, defer_media_limit=True)


@pytest.mark.parametrize("size", [32, 474454, 1500000])
def test_encoding_size_does_not_become_media_tokens(size):
    raw = _policy(_chat(_url(size)))
    adjusted = apply_media_input_estimate(
        raw, route_capabilities=_caps(image_tokens=16384), input_ceiling=128000
    )
    assert 16384 < adjusted.estimated_input_tokens < 16500
    assert adjusted.estimated_media_input_tokens == 16384
    assert adjusted.encoded_media_input_bytes == len(_url(size))
    assert adjusted.effective_body == raw.effective_body
    assert (
        apply_media_input_estimate(
            adjusted, route_capabilities=_caps(image_tokens=16384), input_ceiling=128000
        )
        == adjusted
    )


def test_no_budget_keeps_original_limit_and_current_route_revalidation_recomputes():
    raw = _policy(_chat())
    with pytest.raises(MediaInputEstimateError):
        apply_media_input_estimate(raw, route_capabilities={}, input_ceiling=128000)
    adjusted = apply_media_input_estimate(
        raw, route_capabilities=_caps(image_tokens=1000), input_ceiling=128000
    )
    changed = apply_media_input_estimate(
        adjusted, route_capabilities=_caps(image_tokens=9000), input_ceiling=128000
    )
    assert changed.estimated_input_tokens - adjusted.estimated_input_tokens == 8000
    with pytest.raises(MediaInputEstimateError):
        apply_media_input_estimate(adjusted, route_capabilities={}, input_ceiling=128000)


@pytest.mark.parametrize("invalid", [0, -1, True, 1.5, 1050001, "1000"])
def test_invalid_route_budgets_never_disable_accounting(invalid):
    with pytest.raises(MediaInputEstimateError):
        apply_media_input_estimate(
            _policy(_chat()), route_capabilities=_caps(image_tokens=invalid), input_ceiling=128000
        )


@pytest.mark.parametrize(
    "raw",
    [
        {"version": True, "image_tokens": 1000},
        {"version": 2},
        {"version": 1, "ignore_quota": True},
        "any",
    ],
)
def test_unknown_policy_versions_or_authority_are_rejected(raw):
    with pytest.raises(MediaInputEstimateError):
        apply_media_input_estimate(
            _policy(_chat()),
            route_capabilities={"media_input_estimation": raw},
            input_ceiling=128000,
        )


def test_text_resembling_a_data_url_stays_text():
    body = {"model": "synthetic", "messages": [{"role": "user", "content": _url(100000)}]}
    raw = _policy(body)
    result = apply_media_input_estimate(
        raw, route_capabilities=_caps(image_tokens=1), input_ceiling=128000
    )
    assert result.estimated_input_tokens == raw.estimated_input_tokens
    assert result.estimated_media_input_tokens == 0


def test_existing_image_byte_limit_still_runs_before_estimation():
    with pytest.raises(RequestPolicyError):
        ChatCompletionRequestPolicy(Settings(CHAT_MAX_IMAGE_DATA_URL_BYTES=100)).apply(
            _chat(), defer_media_limit=True
        )


def test_codex_route_context_uses_budget_and_keeps_real_context_limit():
    body = {
        "model": "synthetic",
        "max_output_tokens": 8192,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "A" * 180000},
                    {"type": "input_image", "image_url": _url()},
                ],
            }
        ],
    }
    settings = Settings(
        RESPONSES_MAX_INPUT_TEXT_BYTES=262144, RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES=524288
    )
    raw = ResponsesRequestPolicy(settings).apply(
        body, allow_codex_extended_limits=True, defer_media_limit=True
    )
    caps = {
        "codex_limits": {
            "context_window_tokens": 262144,
            "default_max_output_tokens": 8192,
            "max_output_tokens": 16384,
        }
    }
    with pytest.raises(RequestPolicyError):
        apply_codex_route_limits(raw, route_capabilities=caps, settings=settings)
    caps.update(_caps(image_tokens=16384))
    fixed = apply_codex_route_limits(raw, route_capabilities=caps, settings=settings)
    assert fixed.estimated_input_tokens + fixed.effective_output_tokens < 262144
    caps["codex_limits"]["context_window_tokens"] = 70000
    with pytest.raises(RequestPolicyError):
        apply_codex_route_limits(raw, route_capabilities=caps, settings=settings)


def test_direct_video_is_bounded_and_forwarded_with_operator_frame_limit():
    raw = _policy(_chat(_url(900000, "video/mp4"), kind="video_url"))
    chat = default_chat_completion_capabilities()
    chat["chat_video_inputs"] = True
    caps = {**_caps(video_tokens=65536, video_frames=4), "chat_completions": chat}
    enforce_chat_completion_route_capabilities(
        raw.effective_body,
        route_capabilities=caps,
        route_supports_streaming=True,
        requested_model="synthetic",
        provider_kind="openai_compatible",
    )
    adjusted = apply_media_input_estimate(raw, route_capabilities=caps, input_ceiling=128000)
    assert 65536 < adjusted.estimated_input_tokens < 65700
    route = SimpleNamespace(provider_kind="openai_compatible", capabilities=caps)
    body = _build_safe_chat_completion_upstream_body(
        policy_result=adjusted, upstream_model="synthetic"
    )
    assert body["messages"] == raw.effective_body["messages"]
    adapter = VLLMChatVideoAdapter(
        Settings(),
        route_capabilities=route.capabilities,
        provider_name="synthetic",
        api_key="synthetic-upstream",
    )
    prepared = adapter.prepare(
        ProviderRequest(
            provider="synthetic", upstream_model="synthetic", endpoint="chat.completions", body=body
        )
    )
    assert prepared.body["media_io_kwargs"] == {"video": {"num_frames": 4}}
    assert "media_io_kwargs" not in body


@pytest.mark.parametrize("provider", ["openai", "openrouter", "module", None])
def test_video_requires_reviewed_native_transport(provider):
    with pytest.raises(MediaInputEstimateError):
        video_frame_limit(
            _chat(_url(20, "video/mp4"), "video_url"),
            _caps(video_tokens=65536, video_frames=4),
            provider,
        )


@pytest.mark.parametrize(
    "value",
    [
        "https://example.org/movie.mp4",
        "file:///tmp/movie.mp4",
        "data:video/mp4;base64,???",
        "data:text/plain;base64,YQ==",
        "data:video/mp4;base64,",
    ],
)
def test_video_remote_local_and_malformed_data_are_rejected(value):
    with pytest.raises(RequestPolicyError):
        _policy(_chat(value, "video_url"))


def test_video_route_permission_and_caps_are_independent():
    body = _chat(_url(20, "video/mp4"), "video_url")
    with pytest.raises(RequestPolicyError):
        enforce_chat_completion_route_capabilities(
            body,
            route_capabilities=_caps(video_tokens=65536, video_frames=4),
            route_supports_streaming=True,
            requested_model="synthetic",
            provider_kind="openai_compatible",
        )
    for name, value in [("CHAT_MAX_VIDEOS_PER_REQUEST", 0), ("CHAT_MAX_VIDEO_DATA_URL_BYTES", 10)]:
        with pytest.raises(RequestPolicyError):
            ChatCompletionRequestPolicy(Settings(**{name: value})).apply(
                body, defer_media_limit=True
            )


@pytest.mark.parametrize("kind", ["function_call_output", "custom_tool_call_output"])
def test_image_tool_outputs_keep_native_inline_only_boundary(kind):
    from slaif_gateway.services.openai_compatible_request_boundary import (
        enforce_openai_compatible_request_boundary,
        OpenAICompatibleRequestBoundaryError,
    )

    body = {
        "input": [
            {
                "type": kind,
                "call_id": "synthetic",
                "output": [{"type": "input_image", "image_url": "http://127.0.0.1/private"}],
            }
        ]
    }
    route = SimpleNamespace(provider_kind="openai_compatible", provider="synthetic")
    with pytest.raises(OpenAICompatibleRequestBoundaryError):
        enforce_openai_compatible_request_boundary(body, route=route, endpoint="responses")


@pytest.mark.parametrize("frames", [0, True, 33, "4"])
def test_native_video_contract_is_static_and_bounded(frames):
    from slaif_gateway.modules.servers.registry import resolve_server_module
    from slaif_gateway.providers.errors import ProviderConfigurationError

    with pytest.raises(ProviderConfigurationError):
        resolve_server_module(
            "synthetic", "openai_compatible", _caps(video_tokens=65536, video_frames=frames)
        )


def test_native_video_cannot_be_selected_by_brand_or_codex_pair():
    from slaif_gateway.modules.servers.registry import (
        resolve_server_module,
        ensure_client_server_pair,
    )
    from slaif_gateway.providers.errors import ProviderConfigurationError

    assert resolve_server_module("vllm", "openai_compatible", {}).module_id == "openai-compatible"
    caps = _caps(video_tokens=65536, video_frames=4)
    assert (
        resolve_server_module("synthetic", "openai_compatible", caps).module_id
        == "vllm-chat-video-v1"
    )
    with pytest.raises(ProviderConfigurationError):
        ensure_client_server_pair("codex-0.162-responses-v1", "vllm-chat-video-v1")


@pytest.mark.asyncio
async def test_native_video_wire_preserves_input_and_uses_server_credential(respx_mock):
    import json
    import httpx

    route = respx_mock.post("https://native.invalid/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chat_synthetic",
                "object": "chat.completion",
                "model": "synthetic",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "red"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 84, "completion_tokens": 1, "total_tokens": 85},
            },
        )
    )
    body = _policy(_chat(_url(20, "video/mp4"), "video_url")).effective_body
    adapter = VLLMChatVideoAdapter(
        Settings(),
        route_capabilities=_caps(video_tokens=65536, video_frames=4),
        base_url="https://native.invalid/v1",
        provider_name="synthetic",
        api_key="synthetic-upstream",
    )
    response = await adapter.forward_chat_completion(
        ProviderRequest(
            provider="synthetic", upstream_model="synthetic", endpoint="chat.completions", body=body
        )
    )
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer synthetic-upstream"
    assert json.loads(sent.content)["media_io_kwargs"] == {"video": {"num_frames": 4}}
    assert json.loads(sent.content)["messages"] == body["messages"]
    assert response.usage.prompt_tokens == 84

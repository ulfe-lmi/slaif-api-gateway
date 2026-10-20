"""Route-owned media budgets, independent of transport encoding and billing."""

from collections.abc import Mapping

from slaif_gateway.services.policy_errors import RequestPolicyError


class MediaInputEstimateError(RequestPolicyError):
    error_code = "media_input_estimation_invalid"


def media_parts(body):
    """Yield only typed, previously validated message/tool-result media URLs."""
    for item in body.get("input", []) if isinstance(body.get("input"), list) else []:
        if not isinstance(item, Mapping):
            continue
        parts = (
            item.get("output")
            if item.get("type") in {"function_call_output", "custom_tool_call_output"}
            else item.get("content")
        )
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, Mapping) and part.get("type") == "input_image":
                    url = part.get("image_url")
                    if isinstance(url, str):
                        yield "image", url
    for message in body.get("messages", []):
        if not isinstance(message, Mapping) or not isinstance(message.get("content"), list):
            continue
        for part in message["content"]:
            if not isinstance(part, Mapping) or part.get("type") not in {"image_url", "video_url"}:
                continue
            kind = "image" if part["type"] == "image_url" else "video"
            value = part.get(part["type"])
            if isinstance(value, Mapping) and isinstance(value.get("url"), str):
                yield kind, value["url"]


def text_only_input_estimate(estimate, body):
    """Pre-route guard only; the complete estimate MUST be checked after routing."""
    encoded_bytes = sum(len(url.encode("utf-8")) for _, url in media_parts(body))
    return max(1, estimate - encoded_bytes // 3)


def apply_media_input_estimate(policy_result, *, route_capabilities, input_ceiling):
    """Opt-in per-model budgets affect admission/reservations, never final usage.

    Without configured budgets the historical estimate is retained. Byte/count
    limits have already run, and authorization remains the caller's responsibility.
    Retain the unadjusted estimate so route revalidation is idempotent.
    """
    raw = (route_capabilities or {}).get("media_input_estimation")
    budgets = {}
    if raw is not None:
        if (
            not isinstance(raw, Mapping)
            or set(raw) - {"version", "image_tokens", "video_tokens", "video_frames"}
            or type(raw.get("version")) is not int
            or raw["version"] != 1
        ):
            raise MediaInputEstimateError("Invalid route media estimation policy.", param="model")
        for kind in ("image", "video"):
            value = raw.get(kind + "_tokens")
            if value is not None:
                if type(value) is not int or not 1 <= value <= 1_050_000:
                    raise MediaInputEstimateError(
                        "Invalid route media token budget.", param="model"
                    )
                budgets[kind] = value
        frames = raw.get("video_frames")
        if frames is not None and (type(frames) is not int or not 1 <= frames <= 32):
            raise MediaInputEstimateError("Invalid route video frame budget.", param="model")
    original = policy_result.unadjusted_input_tokens
    if original is None:
        original = policy_result.estimated_input_tokens
    encoded_bytes = media_tokens = 0
    for kind, url in media_parts(policy_result.effective_body):
        if kind in budgets:
            encoded_bytes += len(url.encode("utf-8"))
            media_tokens += budgets[kind]
    estimate = max(1, original - encoded_bytes // 3) + media_tokens
    if estimate > input_ceiling:
        error = MediaInputEstimateError(
            "Estimated input exceeds the configured hard maximum.", param="input"
        )
        error.error_code = "input_token_limit_exceeded"
        raise error
    return policy_result.model_copy(
        update={
            "unadjusted_input_tokens": original,
            "estimated_input_tokens": estimate,
            "estimated_message_input_tokens": max(
                0, estimate - policy_result.estimated_non_message_input_tokens
            ),
            "estimated_media_input_tokens": media_tokens,
            "encoded_media_input_bytes": encoded_bytes,
        }
    )


def video_frame_limit(body, route_capabilities, provider_kind):
    """Only the reviewed native-vLLM Chat video transport is enabled here."""
    if not any(kind == "video" for kind, _ in media_parts(body)):
        return None
    from slaif_gateway.modules.servers.vllm_chat_video import parse_video_frames

    try:
        if provider_kind != "openai_compatible":
            raise ValueError("Unsupported video transport")
        return parse_video_frames(route_capabilities)
    except ValueError:
        raise MediaInputEstimateError(
            "Video input requires an explicit native video/frame estimation policy.", param="model"
        ) from None

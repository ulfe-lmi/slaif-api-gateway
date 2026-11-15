"""Image geometry admission, bounded header parsing, and real-context regression."""

import base64
import copy
from importlib.resources import files
import json
import struct
import zlib

import pytest

from slaif_gateway.config import Settings
from slaif_gateway.schemas.provider_route_configuration import (
    ProviderRouteConfigError,
    parse_capabilities_file,
    parse_capability_patch,
    merge_capability_patch,
)
import slaif_gateway.services.image_token_estimation as image_estimation
from slaif_gateway.services.media_input_estimation import (
    MediaInputEstimateError,
    apply_media_input_estimate,
)
from slaif_gateway.services.request_policy import ChatCompletionRequestPolicy
from slaif_gateway.services.responses_request_policy import (
    ResponsesRequestPolicy,
    ResponsesRequestPolicyError,
    apply_codex_route_limits,
)


@pytest.fixture
def media():
    presets = json.loads(files("slaif_gateway").joinpath(
        "resources/media-input-estimation-presets.json"
    ).read_text())
    return copy.deepcopy(presets["presets"]["qwen-patch16-merge2-images"])


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(
        ">I", zlib.crc32(kind + data) & 0xFFFFFFFF
    )


def _png(width=512, height=512, extra=b"", payload=b"header-parser-fixture"):
    # Header-only fixtures deliberately test metadata inspection without any
    # dependency on a pixel decoder. Live PNG evidence is documented separately.
    return b"\x89PNG\r\n\x1a\n" + _chunk(
        b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ) + extra + _chunk(b"IDAT", payload) + _chunk(b"IEND", b"")


def _url(data, mime="image/png"):
    return "data:" + mime + ";base64," + base64.b64encode(data).decode()


def _policy(url):
    return ChatCompletionRequestPolicy(Settings()).apply({
        "model": "synthetic", "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Describe the image."},
            {"type": "image_url", "image_url": {"url": url}},
        ]}],
    }, defer_media_limit=True)


def _estimate(url, media):
    raw = _policy(url)
    result = apply_media_input_estimate(
        raw, route_capabilities={"media_input_estimation": media}, input_ceiling=196608
    )
    assert result.effective_body == raw.effective_body
    assert result.encoded_media_input_bytes == len(url.encode())
    return result


@pytest.mark.parametrize("width,height,expected", [
    (256, 256, 128), (512, 512, 320), (1024, 1024, 1088),
    (513, 512, 336), (8, 8, 128), (2, 80, 166), (8192, 8192, 16896),
])
def test_patch_grid_bounds_alignment_minimum_upscaling_and_route_cap(
    media, width, height, expected
):
    assert _estimate(_url(_png(width, height)), media).estimated_media_input_tokens == expected


def test_compression_size_does_not_change_geometry_and_header_decode_is_bounded(media, monkeypatch):
    small = _url(_png(payload=b"small"))
    large = _url(_png(payload=b"a" * 1_500_000))
    first, second = _policy(small), _policy(large)
    decode = image_estimation.base64.b64decode
    sizes = []

    def bounded_decode(data, **kwargs):
        sizes.append(len(data))
        return decode(data, **kwargs)

    monkeypatch.setattr(image_estimation.base64, "b64decode", bounded_decode)
    results = [apply_media_input_estimate(
        raw, route_capabilities={"media_input_estimation": media}, input_ceiling=196608
    ) for raw in (first, second)]
    assert all(r.estimated_media_input_tokens == 320 for r in results)
    assert len(sizes) == 2 and max(sizes) <= 87_384
    assert abs(results[0].estimated_input_tokens - results[1].estimated_input_tokens) <= 1


def _jpeg(width, height, marker=0xC0, extra=b""):
    frame = bytes([8]) + struct.pack(">HHB", height, width, 3) + b"\x01\x11\0\x02\x11\0\x03\x11\0"
    return b"\xff\xd8" + extra + bytes([0xFF, marker]) + struct.pack(">H", len(frame) + 2) + frame


@pytest.mark.parametrize("marker", [0xC0, 0xC1, 0xC2])
def test_jpeg_header_skips_app_metadata_and_handles_progressive_images(media, marker):
    app = b"\xff\xe1" + struct.pack(">H", 13) + b"Exif\0\0other"
    image = _url(_jpeg(1024, 512, marker, app), "image/jpeg")
    assert _estimate(image, media).estimated_media_input_tokens == 576


def _webp(kind, payload, prefix=b""):
    def chunk(name, value):
        return name + struct.pack("<I", len(value)) + value + b"\0" * (len(value) % 2)
    chunks = prefix + chunk(kind, payload)
    return b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WEBP" + chunks


@pytest.mark.parametrize("lossless", [False, True])
def test_static_webp_headers(media, lossless):
    if lossless:
        kind, payload = b"VP8L", b"\x2f" + struct.pack("<I", 511 | (511 << 14))
    else:
        kind, payload = b"VP8 ", b"\0\0\0\x9d\x01\x2a" + struct.pack("<HH", 512, 512)
    image = _url(_webp(kind, payload), "image/webp")
    assert _estimate(image, media).estimated_media_input_tokens == 320


@pytest.mark.parametrize("data,mime", [
    (b"not an image", "image/png"), (_png()[:24], "image/png"),
    (_png(0, 512), "image/png"), (_png(2_000_000, 1), "image/png"),
    (_png(extra=_chunk(b"acTL", struct.pack(">II", 2, 0))), "image/png"),
    (_png(extra=_chunk(b"IHDR", struct.pack(">IIBBBBB", 8192, 8192, 8, 2, 0, 0, 0))),
     "image/png"),
    (_png(extra=_chunk(b"tEXt", b"x" * 70_000)), "image/png"),
    (_png()[:29] + b"bad!" + _png()[33:], "image/png"),
    (b"GIF89a" + b"\0" * 40, "image/gif"),
    (_jpeg(512, 512)[:12], "image/jpeg"),
    (b"\xff\xd8\xff\xe1\0\x01", "image/jpeg"),
    (_webp(b"VP8X", b"\x02" + b"\0" * 9), "image/webp"),
    (_webp(b"VP8L", b"\x2f\0\0\0\xe0"), "image/webp"),
])
def test_unknown_animated_invalid_or_unbounded_headers_keep_full_fallback(media, data, mime):
    assert _estimate(_url(data, mime), media).estimated_media_input_tokens == 16896


def test_remote_images_are_never_fetched(media, respx_mock):
    result = _estimate("https://images.example.test/image.png", media)
    assert result.estimated_media_input_tokens == 16896
    assert not respx_mock.calls


@pytest.mark.parametrize("change", [
    {"method": "execute_python"}, {"patch_size": True}, {"patch_size": 0},
    {"patch_size": 257}, {"spatial_merge_size": 17}, {"min_tokens": 0},
    {"min_tokens": 16896}, {"overhead_tokens": -1}, {"overhead_tokens": 65537},
    {"extra": 1}, {"patch_size": "16"},
])
def test_invalid_geometry_fails_closed_at_runtime_and_in_route_files(media, change):
    media["image_geometry"].update(change)
    with pytest.raises(MediaInputEstimateError):
        _estimate(_url(_png()), media)
    with pytest.raises(ProviderRouteConfigError):
        parse_capabilities_file(json.dumps({"schema_version": 1, "capabilities": {
            "media_input_estimation": media,
        }}).encode())


@pytest.mark.parametrize("geometry", [None, {}, "any", {"method": "patch_grid"}])
def test_incomplete_geometry_is_not_an_implicit_discount(media, geometry):
    media["image_geometry"] = geometry
    with pytest.raises(MediaInputEstimateError):
        _estimate(_url(_png()), media)


def test_geometry_requires_explicit_fallback_budget(media):
    del media["image_tokens"]
    with pytest.raises(MediaInputEstimateError):
        _estimate(_url(_png()), media)


def test_route_files_preserve_geometry_and_revalidation_recomputes_once(media):
    caps = parse_capabilities_file(json.dumps({"schema_version": 1, "capabilities": {
        "media_input_estimation": media,
    }}).encode())
    raw = _policy(_url(_png()))
    result = apply_media_input_estimate(raw, route_capabilities=caps, input_ceiling=196608)
    assert apply_media_input_estimate(result, route_capabilities=caps, input_ceiling=196608) == result
    fixed = copy.deepcopy(caps)
    del fixed["media_input_estimation"]["image_geometry"]
    previous = apply_media_input_estimate(result, route_capabilities=fixed, input_ceiling=196608)
    assert previous.estimated_media_input_tokens == 16896
    assert apply_media_input_estimate(previous, route_capabilities=caps, input_ceiling=196608) == result


@pytest.mark.parametrize("item_type", ["function_call_output", "custom_tool_call_output"])
def test_image_tool_results_use_the_same_geometry_and_preserve_contents(media, item_type):
    url = _url(_png())
    raw = _policy(url).model_copy(update={"effective_body": {"input": [{
        "type": item_type, "output": [{"type": "input_image", "image_url": url}],
    }]}})
    result = apply_media_input_estimate(
        raw, route_capabilities={"media_input_estimation": media}, input_ceiling=196608
    )
    assert result.estimated_media_input_tokens == 320
    assert result.effective_body == raw.effective_body


def test_image_padding_no_longer_requires_a_400k_window_for_100k_class_history(media):
    part = "The quick brown fox jumps over the lazy dog.\n" * 3800
    body = {"model": "synthetic", "input": [
        {"role": "user", "content": [{"type": "input_text", "text": part}]},
        {"role": "user", "content": [{"type": "input_text", "text": part}] + [
            {"type": "input_image", "image_url": _url(_png())} for _ in range(16)
        ]},
    ]}
    settings = Settings()
    raw = ResponsesRequestPolicy(settings).apply(
        body, allow_codex_extended_limits=True, defer_media_limit=True
    )
    caps = {"media_input_estimation": media, "codex_limits": {
        "context_window_tokens": 196608, "default_max_output_tokens": 16384,
        "max_output_tokens": 32768,
    }}
    fixed = copy.deepcopy(caps)
    del fixed["media_input_estimation"]["image_geometry"]
    fixed["codex_limits"]["context_window_tokens"] = 400000
    with pytest.raises(ResponsesRequestPolicyError) as error:
        apply_codex_route_limits(raw, route_capabilities=fixed, settings=settings)
    assert error.value.error_code == "responses_codex_context_window_exceeded"
    result = apply_codex_route_limits(raw, route_capabilities=caps, settings=settings)
    assert result.estimated_input_tokens + result.effective_output_tokens < 196608
    assert result.estimated_media_input_tokens == 16 * 320
    assert result.effective_body["input"] == raw.effective_body["input"]
    # Real text remains bounded even with the image correction enabled.
    text = {"model": "synthetic", "input": [{
        "role": "user", "content": [{"type": "input_text", "text": "x" * 190000}],
    } for _ in range(3)]}
    oversized = ResponsesRequestPolicy(settings).apply(
        text, allow_codex_extended_limits=True, defer_media_limit=True
    )
    with pytest.raises(ResponsesRequestPolicyError) as error:
        apply_codex_route_limits(oversized, route_capabilities=caps, settings=settings)
    assert error.value.error_code == "responses_codex_context_window_exceeded"


@pytest.mark.parametrize("count", [17, 65, 129])
def test_default_image_count_is_model_owned_and_each_image_is_metered(media, count):
    settings = Settings()
    assert settings.RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST == 0
    body = {"model": "synthetic", "input": [{"role": "user", "content": [
        {"type": "input_text", "text": "Describe these images."},
        *[{"type": "input_image", "image_url": _url(_png())} for _ in range(count)],
    ]}]}
    raw = ResponsesRequestPolicy(settings).apply(
        body, allow_codex_extended_limits=True, defer_media_limit=True
    )
    result = apply_media_input_estimate(
        raw, route_capabilities={"media_input_estimation": media}, input_ceiling=196608
    )
    assert result.estimated_media_input_tokens == count * 320
    assert result.effective_body["input"] == body["input"]
    # An explicitly requested operator count cap remains opt-in.
    with pytest.raises(ResponsesRequestPolicyError) as error:
        ResponsesRequestPolicy(settings.model_copy(update={
            "RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST": 16,
        })).apply(body, allow_codex_extended_limits=True, defer_media_limit=True)
    assert error.value.error_code == "responses_input_image_count_exceeded"


def test_negative_image_count_limit_is_invalid():
    with pytest.raises(ValueError, match="RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST"):
        Settings(RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST=-1)


def test_small_thin_images_include_minimum_resize_alignment(media):
    policy = image_estimation.parse_image_geometry(media["image_geometry"], 16896)
    assert policy.estimate(_url(_png(2, 80)), 16896) == 166
    assert policy.estimate(_url(_png(80, 2)), 16896) == 166


def test_partial_geometry_edits_preserve_legacy_metadata_and_other_media(media):
    current = {
        "codex_profile": {"profile_id": "opaque-existing-declaration"},
        "media_input_estimation": {"version": 1, "image_tokens": 16896, "video_tokens": 65536},
    }
    patch = parse_capability_patch({"media_input_estimation": media})
    merged = merge_capability_patch(current, patch)
    assert merged["codex_profile"] == current["codex_profile"]
    assert merged["media_input_estimation"] == {**media, "video_tokens": 65536}
    cleared = merge_capability_patch(merged, parse_capability_patch({
        "media_input_estimation": {"image_geometry": None},
    }))
    assert cleared == current
    assert merge_capability_patch({}, parse_capability_patch({
        "media_input_estimation": {"image_geometry": None},
    })) == {}


@pytest.mark.parametrize("value", [True, 0, 2, "1", None])
def test_partial_media_policy_rejects_unknown_version(value):
    with pytest.raises(ProviderRouteConfigError):
        parse_capability_patch({"media_input_estimation": {"version": value}})


@pytest.mark.parametrize("mismatch", [False, True])
def test_extended_webp_canvas_must_match_the_static_frame(media, mismatch):
    width = 1024 if mismatch else 512
    canvas = b"\0\0\0\0" + (width - 1).to_bytes(3, "little") + (511).to_bytes(3, "little")
    prefix = b"VP8X" + struct.pack("<I", 10) + canvas
    payload = b"\0\0\0\x9d\x01\x2a" + struct.pack("<HH", 512, 512)
    result = _estimate(_url(_webp(b"VP8 ", payload, prefix), "image/webp"), media)
    assert result.estimated_media_input_tokens == (16896 if mismatch else 320)


def test_route_file_preserves_only_registered_pinned_qualification_declarations(media):
    from slaif_gateway.services.codex_profile_registry import QWEN38_240K_CODEX_PROFILE

    declaration = {
        "version": 2, "profile_id": QWEN38_240K_CODEX_PROFILE.profile_id,
        "fixture_sha256": QWEN38_240K_CODEX_PROFILE.fixture_sha256,
    }
    document = {"schema_version": 1, "capabilities": {
        "media_input_estimation": media, "codex_profile": declaration,
    }}
    parsed = parse_capabilities_file(json.dumps(document).encode())
    assert parsed["codex_profile"] == declaration
    for change in (
        {"profile_id": "unregistered-repaired-alias"}, {"fixture_sha256": "0" * 64},
        {"version": 2.0}, {"version": True}, {"invented_authority": True},
    ):
        bad = copy.deepcopy(document)
        bad["capabilities"]["codex_profile"].update(change)
        with pytest.raises(ProviderRouteConfigError):
            parse_capabilities_file(json.dumps(bad).encode())

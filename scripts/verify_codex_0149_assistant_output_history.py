"""Prove the Codex 0.149 assistant-output history rejection before correction.

The verifier uses a task-local Codex CLI, the unchanged Gateway application,
an in-process signed fake Local service, and a fake downstream stream.  It
retains only fixed structural facts.  Request bodies, text, images, IDs,
headers, credentials, paths, and arbitrary subprocess output are discarded.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import hashlib
import hmac
import http.client
import http.server
import json
import logging
import os
import platform
import re
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import zlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_PACKAGE = "@openai/codex@0.149.0"
CODEX_MODEL = "codex-0149-assistant-history-model"
CODEX_ROOT_PACKAGE_NAME = "@openai/codex"
CODEX_ROOT_PACKAGE_VERSION = "0.149.0"
CODEX_PLATFORM_PACKAGE_NAME = "@openai/codex-linux-x64"
CODEX_PLATFORM_DISTRIBUTION_NAME = "@openai/codex"
CODEX_PLATFORM_PACKAGE_VERSION = "0.149.0-linux-x64"
CODEX_PLATFORM_OPTIONAL_ALIAS = "npm:@openai/codex@0.149.0-linux-x64"
CODEX_ROOT_PACKAGE_INTEGRITY = "sha512-i4dryj2Y1j+00Mb5n+0n71EYnTK9/KDc2cdFo/dXD0d1oTog2bhUssKDEIOnKmnEf51P0Z/HJTWvTKw/UHyOvQ=="
CODEX_PLATFORM_PACKAGE_INTEGRITY = "sha512-uZXaN9JPxu0/jjnqqJeTd4kRYPnjVZK3MiVndfG1mHhEaoDKL7ScWHfPqvAEOjwsSDEmQSlMfUkmvYp/CHciYw=="
CODEX_LAUNCHER_RELATIVE_PATH = "../@openai/codex/bin/codex.js"
CODEX_LAUNCHER_SHA256 = "134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477"
CODEX_NATIVE_RELATIVE_PATH = (
    "node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex"
)
CODEX_SOURCE_TAG = "rust-v0.149.0"
CODEX_SOURCE_COMMIT = "758ef40f50c1a458425c7cfbf1eb12cbc07af0b0"
CODEX_NATIVE_TARGET = "x86_64-unknown-linux-musl"
CODEX_0149_BINARY_SHA256 = "bbc3341e44c9ead340ed9570c17be936e37870f570751a941699ffd04d672827"
CODEX_NATIVE_SIZE_BYTES = 258_322_048
CODEX_VERSION_OUTPUT = b"codex-cli 0.149.0\n"
MAX_CODEX_METADATA_BYTES = 1_048_576
MAX_CODEX_LAUNCHER_BYTES = 4 * 1024 * 1024
MAX_CODEX_NATIVE_BYTES = CODEX_NATIVE_SIZE_BYTES
LOCAL_005Q_SOURCE_COMMIT = "64e50172ee02563e2b021554f6b0d345cc7dfdec"
LOCAL_005Q_VISION_SOURCE_PATH = "tests/helpers/vision_e2e_support.py"
LOCAL_005Q_VISION_FACTS = {
    "input_modalities": ["text", "image"],
    "supports_image_detail_original": False,
    "context_window": 100_000,
    "max_context_window": 100_000,
    "supports_parallel_tool_calls": False,
}
LOCAL_SERVICE_TOKEN = "synthetic-local-history-service-token-161-a"
LOCAL_SIGNING_SECRET = "synthetic-local-history-signing-secret-161-a"
LOCAL_DERIVATION_SECRET = "synthetic-local-history-derivation-secret-161-a"
GATEWAY_HMAC_SECRET = "synthetic-local-history-gateway-hmac-secret-161-a"
ADMIN_SECRET = "synthetic-local-history-admin-secret-161-a"
ONE_TIME_SECRET_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY"
MAX_CAPTURE_BODY_BYTES = 1_048_576
MAX_CAPTURE_ERROR_BYTES = 16_384
MAX_HISTORY_TEXT_BYTES = 65_536
MAX_IMAGE_PARTS = 8
FULL_IMAGE_SHA256 = "98219eff9b1ebec112240aef4928d7cf7e50ecb333176d4c8db946769dd564cb"
CROP_IMAGE_SHA256 = "5a989a94885576fef961a926fcfb1430e9030e9d3aabdef408502b2b1f713c10"
FULL_IMAGE_BYTE_LENGTH = 80
CROP_IMAGE_BYTE_LENGTH = 76
FULL_IMAGE_DIMENSIONS = (4, 2)
CROP_IMAGE_DIMENSIONS = (2, 2)

_ALLOWED_ERROR_CODE = "responses_input_content_part_not_supported"
_SAFE_ERROR_CODES = frozenset({_ALLOWED_ERROR_CODE})
_SAFE_DIAGNOSTIC_GATEWAY_CODES = frozenset(
    {
        "responses_input_content_part_not_supported",
        "responses_input_multimodal_not_supported",
        "responses_input_image_part_invalid",
        "responses_input_image_url_invalid",
        "responses_input_image_mime_not_supported",
        "responses_input_item_invalid",
        "responses_input_invalid",
        "responses_codex_envelope_not_allowed",
        "responses_codex_client_tools_not_allowed",
        "responses_codex_streaming_tool_events_not_allowed",
        "responses_stream_event_not_supported",
        "responses_streaming_usage_missing_estimated",
        "responses_route_capability_not_supported",
        "responses_route_capability_missing",
        "responses_codex_tool_roundtrip_invalid",
        "incompatible_client_server_pair",
        "provider_response_invalid",
        "route_resolution_error",
    }
)
_SAFE_CODEX_FAILURES = frozenset(
    {
        "argument_separator_rejected",
        "configuration_rejected",
        "mock_http_status_rejected",
        "loopback_request_failed",
        "loopback_connection_failed",
        "mock_stream_rejected",
        "mock_response_failed",
        "turn_failed",
        "error_event",
        "nonzero_after_turn_completed",
        "incomplete_event_sequence",
        "unclassified",
    }
)


class VerificationError(RuntimeError):
    """A fixed verifier failure; its argument never contains request data."""


def _type_class(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "other"


def _size_class(value: object) -> str:
    if not isinstance(value, str):
        return "not_string"
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        return "invalid_unicode"
    return "empty" if size == 0 else "bounded" if size <= MAX_HISTORY_TEXT_BYTES else "oversized"


def _byte_size_class(value: int) -> str:
    return "zero" if value == 0 else "bounded" if value <= MAX_CAPTURE_BODY_BYTES else "oversized"


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    if len(kind) != 4:
        raise VerificationError("image_fixture_chunk_invalid")
    checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def _rgb_png(width: int, height: int, rows: tuple[bytes, ...]) -> bytes:
    if width <= 0 or height <= 0 or len(rows) != height:
        raise VerificationError("image_fixture_dimensions_invalid")
    if any(len(row) != width * 3 for row in rows):
        raise VerificationError("image_fixture_pixels_invalid")
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanlines = b"".join(b"\x00" + row for row in rows)
    return (
        signature
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanlines, 9))
        + _png_chunk(b"IEND", b"")
    )


def _validate_rgb_png(data: bytes, *, dimensions: tuple[int, int]) -> bool:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset = 8
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(data):
        if offset + 12 > len(data):
            return False
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(data):
            return False
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        stored_crc = struct.unpack(">I", data[offset + 8 + length : end])[0]
        if stored_crc != zlib.crc32(kind + payload) & 0xFFFFFFFF:
            return False
        chunks.append((kind, payload))
        offset = end
        if kind == b"IEND":
            break
    if offset != len(data) or not chunks or chunks[0][0] != b"IHDR":
        return False
    if len(chunks[0][1]) != 13:
        return False
    width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    if (width, height) != dimensions or (bit_depth, color_type) != (8, 2):
        return False
    if compression != 0 or filtering != 0 or interlace != 0:
        return False
    return chunks[-1][0] == b"IEND" and any(kind == b"IDAT" for kind, _ in chunks)


def _write_image_fixtures(root: Path) -> dict[str, object]:
    full_rows = (
        bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0]),
        bytes([0, 255, 255, 255, 0, 255, 255, 255, 255, 64, 64, 64]),
    )
    crop_rows = (full_rows[0][6:12], full_rows[1][6:12])
    full_bytes = _rgb_png(4, 2, full_rows)
    crop_bytes = _rgb_png(2, 2, crop_rows)
    full_path = root / "full-scene.png"
    crop_path = root / "crop-right.png"
    full_path.write_bytes(full_bytes)
    crop_path.write_bytes(crop_bytes)
    os.chmod(full_path, 0o600)
    os.chmod(crop_path, 0o600)
    full_digest = hashlib.sha256(full_bytes).hexdigest()
    crop_digest = hashlib.sha256(crop_bytes).hexdigest()
    facts = {
        "full_path": full_path,
        "crop_path": crop_path,
        "full_sha256": full_digest,
        "crop_sha256": crop_digest,
        "full_sha256_expected": full_digest == FULL_IMAGE_SHA256,
        "crop_sha256_expected": crop_digest == CROP_IMAGE_SHA256,
        "distinct_sha256": full_digest != crop_digest,
        "full_length": len(full_bytes),
        "crop_length": len(crop_bytes),
        "full_length_expected": len(full_bytes) == FULL_IMAGE_BYTE_LENGTH,
        "crop_length_expected": len(crop_bytes) == CROP_IMAGE_BYTE_LENGTH,
        "full_valid_rgb": _validate_rgb_png(full_bytes, dimensions=FULL_IMAGE_DIMENSIONS),
        "crop_valid_rgb": _validate_rgb_png(crop_bytes, dimensions=CROP_IMAGE_DIMENSIONS),
    }
    del full_bytes, crop_bytes, full_rows, crop_rows, full_digest, crop_digest
    return facts


def _catalog_value_class(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "other"


def _prepare_vision_catalog_document(document: object, *, model: str) -> dict[str, object]:
    if not isinstance(document, Mapping):
        raise VerificationError("vision_catalog_not_object")
    models = document.get("models")
    if not isinstance(models, list):
        raise VerificationError("vision_catalog_models_invalid")
    matches = [item for item in models if isinstance(item, Mapping) and item.get("slug") == model]
    if not matches:
        raise VerificationError("vision_catalog_model_missing")
    if len(matches) != 1:
        raise VerificationError("vision_catalog_model_duplicate")
    selected = matches[0]
    if not isinstance(selected, dict):
        raise VerificationError("vision_catalog_model_invalid")
    try:
        prepared = json.loads(json.dumps(document))
    except (TypeError, ValueError, json.JSONDecodeError):
        raise VerificationError("vision_catalog_noncanonical") from None
    prepared_models = prepared.get("models")
    if not isinstance(prepared_models, list):
        raise VerificationError("vision_catalog_models_invalid")
    prepared_selected = next(
        (item for item in prepared_models if isinstance(item, dict) and item.get("slug") == model),
        None,
    )
    if not isinstance(prepared_selected, dict):
        raise VerificationError("vision_catalog_model_missing")
    prepared_selected.update(LOCAL_005Q_VISION_FACTS)
    return prepared


def _validate_vision_catalog_document(
    document: object,
    *,
    model: str,
    baseline: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if not isinstance(document, Mapping):
        raise VerificationError("vision_catalog_not_object")
    models = document.get("models")
    if not isinstance(models, list):
        raise VerificationError("vision_catalog_models_invalid")
    matches = [item for item in models if isinstance(item, Mapping) and item.get("slug") == model]
    if not matches:
        raise VerificationError("vision_catalog_model_missing")
    if len(matches) != 1:
        raise VerificationError("vision_catalog_model_duplicate")
    selected = matches[0]
    if not isinstance(selected, Mapping):
        raise VerificationError("vision_catalog_model_invalid")
    if selected.get("input_modalities") != ["text", "image"]:
        raise VerificationError("vision_catalog_modalities_invalid")
    if selected.get("supports_image_detail_original") is not False:
        raise VerificationError("vision_catalog_image_detail_invalid")
    for field in ("context_window", "max_context_window"):
        value = selected.get(field)
        if isinstance(value, bool) or value != 100_000:
            raise VerificationError("vision_catalog_context_invalid")
    if selected.get("supports_parallel_tool_calls") is not False:
        raise VerificationError("vision_catalog_parallel_tools_invalid")
    if baseline is not None:
        baseline_models = baseline.get("models")
        if not isinstance(baseline_models, list):
            raise VerificationError("vision_catalog_baseline_invalid")
        baseline_matches = [
            item
            for item in baseline_models
            if isinstance(item, Mapping) and item.get("slug") == model
        ]
        if len(baseline_matches) != 1 or not isinstance(baseline_matches[0], Mapping):
            raise VerificationError("vision_catalog_baseline_model_invalid")
        baseline_selected = dict(baseline_matches[0])
        selected_unrelated = dict(selected)
        baseline_selected.update(LOCAL_005Q_VISION_FACTS)
        for field in LOCAL_005Q_VISION_FACTS:
            selected_unrelated.pop(field, None)
            baseline_selected.pop(field, None)
        if selected_unrelated != baseline_selected:
            raise VerificationError("vision_catalog_unrelated_mutation")
    return {
        "model_present": True,
        "model_count": len(matches),
        "modalities_exact": selected.get("input_modalities") == ["text", "image"],
        "image_detail_false": selected.get("supports_image_detail_original") is False,
        "context_exact": selected.get("context_window") == 100_000,
        "max_context_exact": selected.get("max_context_window") == 100_000,
        "parallel_tools_false": selected.get("supports_parallel_tool_calls") is False,
        "selected_field_classes": {
            field: _catalog_value_class(selected.get(field))
            for field in (
                "input_modalities",
                "supports_image_detail_original",
                "context_window",
                "max_context_window",
                "supports_parallel_tool_calls",
            )
        },
    }


def _write_and_validate_vision_catalog(
    path: Path, document: Mapping[str, object], *, model: str
) -> dict[str, object]:
    prepared = _prepare_vision_catalog_document(document, model=model)
    canonical = json.dumps(prepared, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if len(canonical.encode("utf-8")) > MAX_CAPTURE_BODY_BYTES:
        raise VerificationError("vision_catalog_oversized")
    path.write_text(canonical, encoding="utf-8")
    os.chmod(path, 0o600)
    reread = json.loads(path.read_text(encoding="utf-8"))
    return _validate_vision_catalog_document(reread, model=model, baseline=document)


def _image_expectations(facts: Mapping[str, object]) -> dict[str, object]:
    required = (
        facts.get("full_sha256_expected") is True,
        facts.get("crop_sha256_expected") is True,
        facts.get("distinct_sha256") is True,
        facts.get("full_length_expected") is True,
        facts.get("crop_length_expected") is True,
        facts.get("full_valid_rgb") is True,
        facts.get("crop_valid_rgb") is True,
    )
    if not all(required):
        raise VerificationError("image_fixture_validation_failed")
    return {
        "full_sha256": facts["full_sha256"],
        "crop_sha256": facts["crop_sha256"],
        "full_length": facts["full_length"],
        "crop_length": facts["crop_length"],
    }


def _validate_image_pair(full_path: Path, crop_path: Path) -> dict[str, object]:
    try:
        full_bytes = full_path.read_bytes()
        crop_bytes = crop_path.read_bytes()
    except (OSError, ValueError):
        raise VerificationError("image_fixture_missing") from None
    if full_bytes == crop_bytes:
        del full_bytes, crop_bytes
        raise VerificationError("image_fixture_pair_not_distinct")
    if not _validate_rgb_png(full_bytes, dimensions=FULL_IMAGE_DIMENSIONS):
        del full_bytes, crop_bytes
        raise VerificationError("image_fixture_full_invalid")
    if not _validate_rgb_png(crop_bytes, dimensions=CROP_IMAGE_DIMENSIONS):
        del full_bytes, crop_bytes
        raise VerificationError("image_fixture_crop_invalid")
    full_digest = hashlib.sha256(full_bytes).hexdigest()
    crop_digest = hashlib.sha256(crop_bytes).hexdigest()
    if full_digest != FULL_IMAGE_SHA256 or len(full_bytes) != FULL_IMAGE_BYTE_LENGTH:
        del full_bytes, crop_bytes, full_digest, crop_digest
        raise VerificationError("image_fixture_full_unexpected")
    if crop_digest != CROP_IMAGE_SHA256 or len(crop_bytes) != CROP_IMAGE_BYTE_LENGTH:
        del full_bytes, crop_bytes, full_digest, crop_digest
        raise VerificationError("image_fixture_crop_unexpected")
    result = {
        "full_sha256": full_digest,
        "crop_sha256": crop_digest,
        "full_length": len(full_bytes),
        "crop_length": len(crop_bytes),
        "full_sha256_expected": True,
        "crop_sha256_expected": True,
        "distinct_sha256": True,
        "full_length_expected": True,
        "crop_length_expected": True,
        "full_valid_rgb": True,
        "crop_valid_rgb": True,
        "full_path": full_path,
        "crop_path": crop_path,
    }
    del full_bytes, crop_bytes, full_digest, crop_digest
    return result


def _classify_image_part(
    part: Mapping[str, object], expectations: Mapping[str, object] | None
) -> str:
    if expectations is None or part.get("type") != "input_image":
        return "other"
    image_url = part.get("image_url")
    if not isinstance(image_url, str) or not image_url.startswith("data:image/png;base64,"):
        return "other"
    encoded = image_url.partition(",")[2]
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError, zlib.error):
        return "other"
    digest = hashlib.sha256(image_bytes).hexdigest()
    length = len(image_bytes)
    if digest == expectations.get("full_sha256") and length == expectations.get("full_length"):
        result = "full"
    elif digest == expectations.get("crop_sha256") and length == expectations.get("crop_length"):
        result = "crop"
    else:
        result = "other"
    del encoded, image_bytes, digest
    return result


def _fixed_error_code(value: object) -> str:
    return value if isinstance(value, str) and value in _SAFE_ERROR_CODES else "other"


def _safe_diagnostic_error_code(value: object) -> str:
    return value if isinstance(value, str) and value in _SAFE_DIAGNOSTIC_GATEWAY_CODES else "other"


def _fixed_param_class(value: object) -> str:
    if not isinstance(value, str):
        return "other"
    if value == "input[5].content[0].type":
        return "input_5_content_0_type"
    match = re.fullmatch(r"input\[([0-9]{1,4})\]\.content\[([0-9]{1,4})\]\.type", value)
    if match is not None:
        input_index = int(match.group(1))
        content_index = int(match.group(2))
        if input_index <= 32 and content_index <= 32:
            return f"input_index_{input_index}_content_index_{content_index}_type"
        return "input_index_or_content_index_other"
    return "other"


def _codex_failure_category(stderr: bytes, stdout: bytes) -> str:
    from scripts.capture_codex_protocol import classify_codex_failure

    value = classify_codex_failure(stderr, stdout)
    return value if value in _SAFE_CODEX_FAILURES else "other"


def _safe_progress_class(value: int) -> str:
    return "zero" if value == 0 else "one" if value == 1 else "two" if value == 2 else "other"


def _safe_status_class(value: int | None) -> str:
    if value is None:
        return "none"
    return (
        "2xx"
        if 200 <= value < 300
        else "4xx"
        if 400 <= value < 500
        else "5xx"
        if 500 <= value < 600
        else "other"
    )


def _safe_failure_progress(observation: GatewayObservation, local: _LocalServer) -> str:
    status = observation.response_statuses[-1] if observation.response_statuses else None
    error_code = _safe_diagnostic_error_code(
        observation.error_codes[-1] if observation.error_codes else None
    )
    param_class = observation.param_classes[-1] if observation.param_classes else "other"
    return (
        f"gateway_{_safe_progress_class(observation.request_count)}"
        f"_status_{_safe_status_class(status)}"
        f"_error_{error_code}"
        f"_param_{param_class}"
        f"_local_{_safe_progress_class(local.state.request_count)}"
    )


def _safe_status_sequence(observation: GatewayObservation) -> str:
    statuses = observation.response_statuses[:4]
    return "_".join(_safe_status_class(status) for status in statuses) or "none"


def _safe_history_projection(
    body: object,
    *,
    image_expectations: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Project one request into fixed facts without retaining text or IDs."""

    projection: dict[str, object] = {
        "body_object": isinstance(body, Mapping),
        "assistant_history_count": 0,
        "assistant_history_present": False,
        "assistant_role_exact": False,
        "assistant_output_text_count": 0,
        "assistant_output_text_type_exact": False,
        "assistant_output_text_nonempty_unicode": False,
        "assistant_output_text_size_class": "not_string",
        "image_part_count_class": "zero",
        "image_wire_class": "none",
        "raw_value_retained": False,
    }
    if not isinstance(body, Mapping):
        return projection
    input_items = body.get("input")
    if not isinstance(input_items, list):
        return projection
    image_classes: list[str] = []
    for item in input_items:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") == "input_image":
            image_classes.append(_classify_image_part(item, image_expectations))
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "input_image":
                if len(image_classes) < MAX_IMAGE_PARTS:
                    image_classes.append(_classify_image_part(part, image_expectations))
        if item.get("role") != "assistant":
            continue
        projection["assistant_history_count"] = int(projection["assistant_history_count"]) + 1
        projection["assistant_history_present"] = True
        projection["assistant_role_exact"] = True
        for part in content:
            if not isinstance(part, Mapping) or part.get("type") != "output_text":
                continue
            projection["assistant_output_text_count"] = (
                int(projection["assistant_output_text_count"]) + 1
            )
            projection["assistant_output_text_type_exact"] = part.get("type") == "output_text"
            text = part.get("text")
            if not isinstance(text, str):
                continue
            projection["assistant_output_text_size_class"] = _size_class(text)
            try:
                encoded_size = len(text.encode("utf-8"))
            except UnicodeEncodeError:
                continue
            projection["assistant_output_text_nonempty_unicode"] = (
                encoded_size > 0 and encoded_size <= MAX_HISTORY_TEXT_BYTES
            )
    projection["image_part_count_class"] = (
        "zero" if not image_classes else "one" if len(image_classes) == 1 else "many"
    )
    projection["image_wire_class"] = (
        "none" if not image_classes else image_classes[0] if len(image_classes) == 1 else "many"
    )
    return projection


def _safe_error_projection(body: bytes) -> dict[str, str | bool]:
    """Parse only the closed error code/parameter classes."""

    try:
        decoded = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return {"json_object": False, "error_code": "other", "param_class": "other"}
    error = decoded.get("error") if isinstance(decoded, Mapping) else None
    if not isinstance(error, Mapping):
        return {
            "json_object": isinstance(decoded, Mapping),
            "error_code": "other",
            "param_class": "other",
        }
    return {
        "json_object": True,
        "error_code": _fixed_error_code(error.get("code")),
        "param_class": _fixed_param_class(error.get("param")),
    }


class GatewayObservation:
    """ASGI observer retaining only bounded request/response predicates."""

    def __init__(self, app, *, image_expectations: Mapping[str, object] | None = None) -> None:
        self.app = app
        self.image_expectations = image_expectations
        self.request_count = 0
        self.response_statuses: list[int] = []
        self.error_codes: list[str] = []
        self.param_classes: list[str] = []
        self.image_count_classes: list[str] = []
        self.request_projections: list[dict[str, object]] = []
        self.request_overflow_classes: list[str] = []
        self.second_projection: dict[str, object] | None = None
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send) -> None:
        is_responses = (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == "/v1/responses"
        )
        ordinal = 0
        if is_responses:
            with self._lock:
                self.request_count += 1
                ordinal = self.request_count
        request_body = bytearray()
        request_overflow = False

        async def observed_receive():
            nonlocal request_overflow
            message = await receive()
            if is_responses and message.get("type") == "http.request":
                chunk = message.get("body", b"")
                if (
                    isinstance(chunk, bytes)
                    and len(request_body) + len(chunk) <= MAX_CAPTURE_BODY_BYTES
                ):
                    request_body.extend(chunk)
                else:
                    request_overflow = True
                if not message.get("more_body", False):
                    if request_overflow:
                        self.request_overflow_classes.append("request_body_overflow")
                    else:
                        try:
                            decoded = json.loads(bytes(request_body))
                        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                            decoded = None
                        candidate_projection = _safe_history_projection(
                            decoded, image_expectations=self.image_expectations
                        )
                        if len(self.request_projections) < 4:
                            self.request_projections.append(candidate_projection)
                        self.image_count_classes.append(
                            str(candidate_projection["image_part_count_class"])
                        )
                        if (
                            ordinal > 1
                            and candidate_projection["assistant_history_present"] is True
                        ):
                            self.second_projection = candidate_projection
                    request_body.clear()
            return message

        status: int | None = None
        response_body = bytearray()
        response_overflow = False

        async def observed_send(message) -> None:
            nonlocal status, response_overflow
            if message.get("type") == "http.response.start":
                status = int(message.get("status", 0))
            elif is_responses and status is not None and status >= 400:
                chunk = message.get("body", b"")
                if (
                    isinstance(chunk, bytes)
                    and len(response_body) + len(chunk) <= MAX_CAPTURE_ERROR_BYTES
                ):
                    response_body.extend(chunk)
                else:
                    response_overflow = True
            await send(message)

        await self.app(scope, observed_receive, observed_send)
        if is_responses and status is not None:
            parsed = (
                _safe_error_projection(bytes(response_body))
                if status >= 400 and not response_overflow
                else {"error_code": "other", "param_class": "other"}
            )
            with self._lock:
                self.response_statuses.append(status)
                self.error_codes.append(str(parsed["error_code"]))
                self.param_classes.append(str(parsed["param_class"]))
            response_body.clear()


def _sse(event: Mapping[str, object]) -> bytes:
    return ("data: " + json.dumps(event, separators=(",", ":")) + "\n\n").encode()


def _usage() -> dict[str, object]:
    return {
        "input_tokens": 2,
        "input_tokens_details": {
            "cached_tokens": 0,
            "input_tokens_per_turn": [2],
            "cached_tokens_per_turn": [0],
        },
        "output_tokens": 2,
        "output_tokens_details": {
            "reasoning_tokens": 0,
            "tool_output_tokens": 0,
            "output_tokens_per_turn": [2],
            "tool_output_tokens_per_turn": [0],
        },
        "total_tokens": 4,
    }


def _tool_name(payload: Mapping[str, object]) -> str:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        raise VerificationError("known_local_tool_missing")
    for tool in tools:
        if (
            isinstance(tool, Mapping)
            and tool.get("type") == "function"
            and tool.get("name") in {"shell_command", "exec_command"}
        ):
            return str(tool["name"])
    raise VerificationError("known_local_tool_missing")


def _tool_arguments(payload: Mapping[str, object], name: str) -> str:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        raise VerificationError("known_local_tool_missing")
    for tool in tools:
        if (
            not isinstance(tool, Mapping)
            or tool.get("type") != "function"
            or tool.get("name") != name
        ):
            continue
        parameters = tool.get("parameters")
        if not isinstance(parameters, Mapping):
            return "{}"
        properties = parameters.get("properties")
        required = parameters.get("required")
        if not isinstance(properties, Mapping) or not isinstance(required, list):
            return "{}"
        values: dict[str, object] = {}
        for field in required[:8]:
            schema = properties.get(field)
            schema_type = schema.get("type") if isinstance(schema, Mapping) else None
            values[str(field)] = (
                "cat SYNTHETIC_TASK.md"
                if schema_type == "string"
                else 1
                if schema_type == "integer"
                else False
                if schema_type == "boolean"
                else []
                if schema_type == "array"
                else {}
            )
        return json.dumps(values, separators=(",", ":"))
    raise VerificationError("known_local_tool_missing")


def _function_stream(arguments: str, tool_name: str) -> tuple[dict[str, object], ...]:
    response_id = "response_history_function"
    item_id = "function_history_first"
    call_id = "call_history_first"
    return (
        {
            "type": "response.created",
            "sequence_number": 0,
            "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL},
        },
        {
            "type": "response.in_progress",
            "sequence_number": 1,
            "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL},
        },
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "sequence_number": 2,
            "item": {
                "type": "function_call",
                "id": item_id,
                "status": "in_progress",
                "namespace": None,
                "name": tool_name,
                "arguments": "",
                "call_id": call_id,
                "caller": None,
            },
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": item_id,
            "output_index": 0,
            "sequence_number": 3,
            "delta": arguments,
        },
        {
            "type": "response.function_call_arguments.done",
            "item_id": item_id,
            "output_index": 0,
            "sequence_number": 4,
            "name": tool_name,
            "arguments": arguments,
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "sequence_number": 5,
            "item": {
                "type": "function_call",
                "id": item_id,
                "status": "completed",
                "namespace": None,
                "name": tool_name,
                "arguments": arguments,
                "call_id": call_id,
                "caller": None,
            },
        },
        {
            "type": "response.completed",
            "sequence_number": 6,
            "response": {
                "id": response_id,
                "status": "completed",
                "model": CODEX_MODEL,
                "output": [
                    {
                        "type": "function_call",
                        "id": "parser_function",
                        "status": "completed",
                        "namespace": None,
                        "name": tool_name,
                        "arguments": arguments,
                        "call_id": "parser_call",
                    }
                ],
                "usage": _usage(),
            },
        },
    )


def _message_stream() -> tuple[dict[str, object], ...]:
    response_id = "response_history_first"
    item_id = "message_history_first"
    return (
        {
            "type": "response.created",
            "sequence_number": 0,
            "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL},
        },
        {
            "type": "response.in_progress",
            "sequence_number": 1,
            "response": {"id": response_id, "status": "in_progress", "model": CODEX_MODEL},
        },
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "sequence_number": 2,
            "item": {
                "type": "message",
                "id": item_id,
                "status": "in_progress",
                "role": "assistant",
                "content": [],
                "phase": None,
            },
        },
        {
            "type": "response.content_part.added",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "sequence_number": 3,
            "part": {"type": "output_text", "text": "", "annotations": [], "logprobs": []},
        },
        {
            "type": "response.output_text.delta",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "sequence_number": 4,
            "delta": "synthetic",
            "logprobs": [],
        },
        {
            "type": "response.output_text.done",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "sequence_number": 5,
            "text": "synthetic",
            "logprobs": [],
        },
        {
            "type": "response.content_part.done",
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "sequence_number": 6,
            "part": {
                "type": "output_text",
                "text": "synthetic",
                "annotations": [],
                "logprobs": None,
            },
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "sequence_number": 7,
            "item": {
                "type": "message",
                "id": item_id,
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "synthetic",
                        "annotations": [],
                        "logprobs": None,
                    }
                ],
                "phase": None,
                "summary": [],
            },
        },
        {
            "type": "response.completed",
            "sequence_number": 8,
            "response": {
                "id": response_id,
                "status": "completed",
                "model": CODEX_MODEL,
                "output": [
                    {
                        "type": "message",
                        "id": "parser_message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "synthetic",
                                "annotations": [],
                                "logprobs": None,
                            }
                        ],
                        "phase": None,
                    }
                ],
                "usage": _usage(),
            },
        },
    )


class HistoryLocalState:
    def __init__(self) -> None:
        self.request_count = 0
        self.signed_request_count = 0
        self.function_count = 0
        self.message_count = 0
        self._lock = threading.Lock()

    def observe(
        self, body: bytes, headers: http.client.HTTPMessage, path: str
    ) -> tuple[dict[str, object], ...]:
        if path != "/v1/responses":
            raise VerificationError("local_path_invalid")
        if headers.get("authorization") != "Bearer " + LOCAL_SERVICE_TOKEN:
            raise VerificationError("local_service_auth_invalid")
        required = {
            "x-slaif-identity-version",
            "x-slaif-principal",
            "x-slaif-session",
            "x-slaif-repository",
            "x-slaif-route",
            "x-slaif-timestamp",
            "x-slaif-nonce",
            "x-slaif-signature",
        }
        if not required.issubset({name.lower() for name in headers}):
            raise VerificationError("local_signed_headers_missing")
        from slaif_gateway.modules.servers.local_coding.identity import (
            LocalCodingRequestIdentity,
            canonical_identity_bytes,
            expected_signature,
        )

        identity = LocalCodingRequestIdentity(
            principal=headers["x-slaif-principal"],
            session=headers["x-slaif-session"],
            repository=headers["x-slaif-repository"],
            route=headers["x-slaif-route"],
            identity_mode="signed_identity_v1",
        )
        canonical = canonical_identity_bytes(
            method="POST",
            path=path,
            raw_query=b"",
            body=body,
            identity=identity,
            timestamp=headers["x-slaif-timestamp"],
            nonce=headers["x-slaif-nonce"],
        )
        expected = expected_signature(secret=LOCAL_SIGNING_SECRET.encode(), canonical=canonical)
        if not hmac.compare_digest(headers["x-slaif-signature"], expected):
            raise VerificationError("local_signature_invalid")
        with self._lock:
            self.request_count += 1
            self.signed_request_count += 1
            ordinal = self.request_count
        payload = json.loads(body)
        if not isinstance(payload, Mapping):
            raise VerificationError("local_body_invalid")
        if ordinal == 1:
            tool_name = _tool_name(payload)
            arguments = _tool_arguments(payload, tool_name)
            self.function_count += 1
            return _function_stream(arguments, tool_name)
        if ordinal == 2:
            items = payload.get("input")
            if not isinstance(items, list):
                raise VerificationError("local_tool_result_input_missing")
            calls = [
                item
                for item in items
                if isinstance(item, Mapping) and item.get("type") == "function_call"
            ]
            outputs = [
                item
                for item in items
                if isinstance(item, Mapping) and item.get("type") == "function_call_output"
            ]
            if len(calls) != 1 or len(outputs) != 1:
                raise VerificationError("local_tool_result_pair_invalid")
            if items.index(calls[0]) + 1 != items.index(outputs[0]) or calls[0].get(
                "call_id"
            ) != outputs[0].get("call_id"):
                raise VerificationError("local_tool_result_adjacency_invalid")
            self.message_count += 1
            return _message_stream()
        raise VerificationError("local_request_count_exceeded")


class _LocalHandler(http.server.BaseHTTPRequestHandler):
    server: "_LocalServer"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > MAX_CAPTURE_BODY_BYTES:
                raise VerificationError("local_body_bound_invalid")
            body = self.rfile.read(length)
            events = self.server.state.observe(body, self.headers, self.path)
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.end_headers()
            for event in events:
                self.wfile.write(_sse(event))
                self.wfile.flush()
        except VerificationError:
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"code":"history_fake_local_failed"}}')


class _LocalServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, state: HistoryLocalState) -> None:
        super().__init__(("127.0.0.1", 0), _LocalHandler)
        self.state = state


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run(
    command: list[str], *, cwd: Path, env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, check=False, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError("process_launch_failed") from exc


@dataclass(frozen=True)
class CodexProvenance:
    launcher: Path
    native: Path


def _provenance_path(root: Path, relative: str, *, error: str) -> Path:
    try:
        root_absolute = root.absolute()
        candidate = root.joinpath(*Path(relative).parts)
        candidate.absolute().relative_to(root_absolute)
        root_resolved = root.resolve(strict=True)
        candidate.resolve(strict=False).relative_to(root_resolved)
    except (OSError, RuntimeError, ValueError):
        raise VerificationError(error) from None
    return candidate


def _require_regular_file(
    path: Path,
    *,
    error: str,
    maximum: int,
    executable: bool,
    expected_size: int | None = None,
    size_error: str | None = None,
) -> int:
    try:
        if path.is_symlink():
            raise VerificationError(error)
        info = path.stat()
    except VerificationError:
        raise
    except (OSError, ValueError):
        raise VerificationError(error) from None
    if not stat.S_ISREG(info.st_mode):
        raise VerificationError(error)
    if expected_size is not None and info.st_size != expected_size:
        raise VerificationError(size_error or error)
    if info.st_size > maximum:
        raise VerificationError(error)
    if executable and info.st_mode & 0o111 == 0:
        raise VerificationError(error)
    return info.st_size


def _read_json_file(path: Path, *, error: str) -> Mapping[str, object]:
    _require_regular_file(path, error=error, maximum=MAX_CODEX_METADATA_BYTES, executable=False)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise VerificationError(error) from None
    if not isinstance(value, Mapping):
        raise VerificationError(error)
    return value


def _sha256_file(
    path: Path,
    *,
    error: str,
    maximum: int,
    expected_size: int | None = None,
    size_error: str | None = None,
) -> str:
    _require_regular_file(
        path,
        error=error,
        maximum=maximum,
        executable=True,
        expected_size=expected_size,
        size_error=size_error,
    )
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except (OSError, ValueError):
        raise VerificationError(error) from None
    return digest.hexdigest()


def _probe_codex_version(executable: Path, *, install: Path, runner: object) -> None:
    try:
        result = runner(  # type: ignore[operator]
            [str(executable), "--version"],
            cwd=install,
            env=os.environ.copy(),
            timeout=10,
        )
    except VerificationError:
        raise
    except Exception:
        raise VerificationError("codex_version_probe_failed") from None
    if (
        getattr(result, "returncode", None) != 0
        or getattr(result, "stdout", None) != CODEX_VERSION_OUTPUT
        or getattr(result, "stderr", None) != b""
    ):
        raise VerificationError("codex_version_mismatch")


def _validate_package_lock(install: Path) -> None:
    lock = _read_json_file(
        _provenance_path(install, "package-lock.json", error="codex_lock_invalid"),
        error="codex_lock_invalid",
    )
    if lock.get("lockfileVersion") not in {2, 3}:
        raise VerificationError("codex_lock_invalid")
    packages = lock.get("packages")
    if not isinstance(packages, Mapping):
        raise VerificationError("codex_lock_invalid")
    expected = {
        "node_modules/@openai/codex": CODEX_ROOT_PACKAGE_INTEGRITY,
        "node_modules/@openai/codex-linux-x64": CODEX_PLATFORM_PACKAGE_INTEGRITY,
    }
    for package_path, integrity in expected.items():
        entry = packages.get(package_path)
        if not isinstance(entry, Mapping) or entry.get("integrity") != integrity:
            raise VerificationError("codex_lock_integrity_invalid")


def _attest_codex_installation(
    install: Path,
    *,
    runner: object = _run,
    platform_name: str | None = None,
    architecture: str | None = None,
    launcher_digest: str = CODEX_LAUNCHER_SHA256,
    native_digest: str = CODEX_0149_BINARY_SHA256,
    native_size: int | None = None,
) -> CodexProvenance:
    expected_native_size = CODEX_NATIVE_SIZE_BYTES if native_size is None else native_size
    if isinstance(expected_native_size, bool) or not isinstance(expected_native_size, int):
        raise VerificationError("codex_native_size_invalid")
    if expected_native_size <= 0 or expected_native_size > CODEX_NATIVE_SIZE_BYTES:
        raise VerificationError("codex_native_size_invalid")
    current_platform = (platform_name or platform.system()).lower()
    current_architecture = (architecture or platform.machine()).lower()
    if current_platform != "linux" or current_architecture not in {"x86_64", "x64"}:
        raise VerificationError("codex_runtime_unsupported")

    root_manifest_path = _provenance_path(
        install,
        "node_modules/@openai/codex/package.json",
        error="codex_root_manifest_invalid",
    )
    platform_manifest_path = _provenance_path(
        install,
        "node_modules/@openai/codex-linux-x64/package.json",
        error="codex_platform_manifest_invalid",
    )
    root_manifest = _read_json_file(root_manifest_path, error="codex_root_manifest_invalid")
    root_bin = root_manifest.get("bin")
    root_optional = root_manifest.get("optionalDependencies")
    if (
        root_manifest.get("name") != CODEX_ROOT_PACKAGE_NAME
        or root_manifest.get("version") != CODEX_ROOT_PACKAGE_VERSION
        or not isinstance(root_bin, Mapping)
        or root_bin.get("codex") != "bin/codex.js"
        or not isinstance(root_optional, Mapping)
        or root_optional.get(CODEX_PLATFORM_PACKAGE_NAME) != CODEX_PLATFORM_OPTIONAL_ALIAS
    ):
        raise VerificationError("codex_root_manifest_invalid")
    platform_manifest = _read_json_file(
        platform_manifest_path, error="codex_platform_manifest_invalid"
    )
    if (
        platform_manifest.get("name") != CODEX_PLATFORM_DISTRIBUTION_NAME
        or platform_manifest.get("version") != CODEX_PLATFORM_PACKAGE_VERSION
        or platform_manifest.get("os") != ["linux"]
        or platform_manifest.get("cpu") != ["x64"]
    ):
        raise VerificationError("codex_platform_manifest_invalid")
    _validate_package_lock(install)

    launcher_link = _provenance_path(
        install, "node_modules/.bin/codex", error="codex_launcher_link_invalid"
    )
    try:
        if (
            not launcher_link.is_symlink()
            or os.readlink(launcher_link) != CODEX_LAUNCHER_RELATIVE_PATH
        ):
            raise VerificationError("codex_launcher_link_invalid")
        launcher = _provenance_path(
            install,
            "node_modules/@openai/codex/bin/codex.js",
            error="codex_launcher_invalid",
        )
        if launcher_link.resolve(strict=False) != launcher.resolve(strict=False):
            raise VerificationError("codex_launcher_link_invalid")
    except VerificationError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise VerificationError("codex_launcher_link_invalid") from None
    if (
        _sha256_file(launcher, error="codex_launcher_invalid", maximum=MAX_CODEX_LAUNCHER_BYTES)
        != launcher_digest
    ):
        raise VerificationError("codex_launcher_digest_invalid")

    native = _provenance_path(install, CODEX_NATIVE_RELATIVE_PATH, error="codex_native_invalid")
    if (
        _sha256_file(
            native,
            error="codex_native_invalid",
            maximum=MAX_CODEX_NATIVE_BYTES,
            expected_size=expected_native_size,
            size_error="codex_native_size_invalid",
        )
        != native_digest
    ):
        raise VerificationError("codex_native_digest_invalid")
    _probe_codex_version(launcher, install=install, runner=runner)
    _probe_codex_version(native, install=install, runner=runner)
    return CodexProvenance(launcher=launcher_link, native=native)


def _install_codex(root: Path) -> CodexProvenance:
    install = root / "codex-install"
    install.mkdir(mode=0o700)
    if _run(["npm", "init", "-y"], cwd=install, env=os.environ.copy(), timeout=30).returncode != 0:
        raise VerificationError("codex_install_failed")
    if (
        _run(
            ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", CODEX_PACKAGE],
            cwd=install,
            env=os.environ.copy(),
            timeout=180,
        ).returncode
        != 0
    ):
        raise VerificationError("codex_install_failed")
    return _attest_codex_installation(install)


def _codex_profile_args(*, port: int, model_catalog: Path) -> list[str]:
    base_url = f'"http://127.0.0.1:{port}/v1"'
    return [
        "-m",
        CODEX_MODEL,
        "-c",
        'model_provider="slaif-capture"',
        "-c",
        (
            "model_providers.slaif-capture={"
            f'name="Synthetic capture",base_url={base_url},'
            'env_key="SLAIF_CAPTURE_API_KEY",wire_api="responses"}'
        ),
        "-c",
        f"model_catalog_json={json.dumps(str(model_catalog))}",
        "-c",
        "check_for_update_on_startup=false",
        "-c",
        "model_providers.slaif-capture.request_max_retries=0",
        "-c",
        "model_providers.slaif-capture.stream_max_retries=0",
    ]


def _initial_command(
    binary: Path,
    *,
    workdir: Path,
    port: int,
    model_catalog: Path,
    output: Path,
    full_image: Path,
) -> list[str]:
    return [
        str(binary),
        "--dangerously-bypass-approvals-and-sandbox",
        "exec",
        "--json",
        "--strict-config",
        "--ignore-user-config",
        *_codex_profile_args(port=port, model_catalog=model_catalog),
        "--cd",
        str(workdir),
        "--image",
        str(full_image),
        "--output-last-message",
        str(output),
        "Describe the attached synthetic full scene briefly without tools.",
    ]


def _resume_last_command(
    binary: Path,
    *,
    workdir: Path,
    port: int,
    model_catalog: Path,
    output: Path,
    crop_image: Path,
) -> list[str]:
    return [
        str(binary),
        "--dangerously-bypass-approvals-and-sandbox",
        "exec",
        "resume",
        "--last",
        "--json",
        "--strict-config",
        "--ignore-user-config",
        *_codex_profile_args(port=port, model_catalog=model_catalog),
        "--image",
        str(crop_image),
        "--output-last-message",
        str(output),
        "Inspect the attached synthetic crop and return one short answer.",
    ]


def _command_shape(
    command: list[str], *, expected_image: Path | None = None, resume: bool | None = None
) -> dict[str, object]:
    image_positions = [index for index, value in enumerate(command) if value == "--image"]
    image_binding = (
        len(image_positions) == 1
        and expected_image is not None
        and image_positions[0] + 1 < len(command)
        and command[image_positions[0] + 1] == str(expected_image)
    )
    resume_last = "resume" in command and "--last" in command
    if "--cd" in command:
        suffix = command[command.index("--cd") :]
    elif "--image" in command:
        suffix = command[command.index("--image") :]
    else:
        suffix = []
    return {
        "zero_request_retries": "model_providers.slaif-capture.request_max_retries=0" in command,
        "zero_stream_retries": "model_providers.slaif-capture.stream_max_retries=0" in command,
        "resume_last": resume_last,
        "image_option_count_one": len(image_positions) == 1,
        "image_binding": image_binding,
        "output_last_message": "--output-last-message" in command,
        "cd_flag": "--cd" in command,
        "suffix_has_image_before_output": (
            "--image" in suffix
            and "--output-last-message" in suffix
            and suffix.index("--image") < suffix.index("--output-last-message")
        ),
        "resume_expected": resume is None or resume_last is resume,
    }


def _validate_command_binding(command: list[str], *, expected_image: Path, resume: bool) -> None:
    shape = _command_shape(command, expected_image=expected_image, resume=resume)
    if shape["image_option_count_one"] is not True:
        raise VerificationError(
            "image_command_missing" if "--image" not in command else "image_command_multiple"
        )
    if shape["image_binding"] is not True:
        raise VerificationError("image_command_binding_invalid")
    if (
        shape["output_last_message"] is not True
        or shape["suffix_has_image_before_output"] is not True
    ):
        raise VerificationError("image_command_suffix_invalid")
    if shape["resume_expected"] is not True:
        raise VerificationError("image_command_resume_invalid")
    if shape["zero_request_retries"] is not True or shape["zero_stream_retries"] is not True:
        raise VerificationError("image_command_retry_invalid")


def _database() -> tuple[str, bool, str | None]:
    provided = os.environ.get("TEST_DATABASE_URL")
    if provided:
        return provided, False, None
    name = f"slaif_gateway_161_assistant_history_test_{os.getpid()}"
    from scripts.verify_codex_0149_local_roundtrip import _run as run_command

    result = run_command(
        ["bash", "scripts/create-test-db.sh"],
        cwd=REPO_ROOT,
        env={**os.environ, "TEST_DB_NAME": name},
        timeout=30,
    )
    if result.returncode != 0:
        raise VerificationError("postgres_setup_failed")
    return f"postgresql+asyncpg://slaif:slaif@localhost:5432/{name}", True, name


def _private_session_count(home: Path) -> int:
    matches = [path for path in home.rglob("*.jsonl") if path.is_file()]
    return len(matches) if len(matches) <= 4 else 5


@contextlib.contextmanager
def _environment(values: dict[str, str]) -> Iterator[None]:
    previous = os.environ.copy()
    os.environ.clear()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


async def _accounting_count(database_url: str, key_id: object) -> int:
    from slaif_gateway.db.models import QuotaReservation, UsageLedger

    engine = create_async_engine(database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            reservations = await session.scalar(
                select(func.count())
                .select_from(QuotaReservation)
                .where(QuotaReservation.gateway_key_id == key_id)
            )
            ledgers = await session.scalar(
                select(func.count())
                .select_from(UsageLedger)
                .where(UsageLedger.gateway_key_id == key_id)
            )
            return int(reservations or 0) + int(ledgers or 0)
    finally:
        await engine.dispose()


def run_prefixed_reproduction() -> str:
    from scripts import capture_codex_protocol as capture
    from tests.e2e.test_openai_python_client_responses import _create_responses_test_data
    from tests.e2e.test_openai_python_client_chat import _run_uvicorn_server
    from slaif_gateway.config import get_settings
    from slaif_gateway.main import create_app
    from slaif_gateway.modules.clients.codex_0149 import (
        CODEX_0149_CLIENT_MODULE_VERSION,
        CODEX_0149_FIXTURE_SHA256,
    )

    database_url, own_db, db_name = _database()
    local = _LocalServer(HistoryLocalState())
    local_thread = threading.Thread(target=local.serve_forever, daemon=True)
    local_thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="slaif-161-history-") as temporary:
            root = Path(temporary)
            home = root / "codex-home"
            work = root / "workspace"
            home.mkdir(mode=0o700)
            work.mkdir(mode=0o700)
            written_facts = _write_image_fixtures(root)
            fixture_facts = _validate_image_pair(
                written_facts["full_path"], written_facts["crop_path"]
            )
            image_expectations = _image_expectations(fixture_facts)
            state = local.state
            values = {
                "DATABASE_URL": database_url,
                "APP_ENV": "test",
                "GATEWAY_KEY_PREFIX": "sk-slaif-",
                "GATEWAY_KEY_ACCEPTED_PREFIXES": "sk-slaif-",
                "ACTIVE_HMAC_KEY_VERSION": "1",
                "TOKEN_HMAC_SECRET_V1": GATEWAY_HMAC_SECRET,
                "ADMIN_SESSION_SECRET": ADMIN_SECRET,
                "ONE_TIME_SECRET_ENCRYPTION_KEY": ONE_TIME_SECRET_KEY,
                "LOCAL_CODING_SERVICE_TOKEN": LOCAL_SERVICE_TOKEN,
                "LOCAL_CODING_SIGNING_SECRET_V1": LOCAL_SIGNING_SECRET,
                "LOCAL_CODING_IDENTITY_DERIVATION_SECRET_V1": LOCAL_DERIVATION_SECRET,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PYTHONPATH": str(REPO_ROOT / "app"),
            }
            with _environment(values):
                get_settings.cache_clear()
                migration = _run(
                    [sys.executable, "-m", "alembic", "upgrade", "head"],
                    cwd=REPO_ROOT,
                    env=values,
                    timeout=120,
                )
                if migration.returncode != 0:
                    raise VerificationError("migration_failed")
                from slaif_gateway.config import get_settings as configured_settings

                created = asyncio.run(
                    _create_responses_test_data(
                        database_url,
                        provider="local-coding",
                        model=CODEX_MODEL,
                        upstream_model=CODEX_MODEL,
                        base_url=f"http://127.0.0.1:{local.server_address[1]}/v1",
                        api_key_env_var="LOCAL_CODING_SERVICE_TOKEN",
                        streaming=True,
                        function_tools=True,
                        custom_tools=True,
                        image_input=True,
                        local_coding_contract={
                            "contract_version": "local-coding-v1",
                            "route_name": "vision",
                            "tool_policy_version": "responses-tool-policy-v1",
                            "identity_mode": "signed_identity_v1",
                            "replay_mode": "process_local_ttl_lru",
                            "deployment_mode": "single_worker",
                        },
                        responses_policy={
                            "version": 1,
                            "local_coding_repository_scope": "assistant-history-repository",
                            "allowed_capabilities": [
                                "codex_request_envelope",
                                "codex_client_tools",
                                "codex_streaming_tool_events",
                            ],
                            "client_module": {
                                "id": "codex-0.149-responses-v1",
                                "version": CODEX_0149_CLIENT_MODULE_VERSION,
                                "fixture_sha256": CODEX_0149_FIXTURE_SHA256,
                            },
                        },
                        codex_request_envelope=True,
                        codex_client_tools=True,
                        codex_streaming_tool_events=True,
                    )
                )
                provenance = _install_codex(root)
                binary = provenance.launcher
                catalog = root / "model-catalog.json"
                environment = capture._isolated_environment(home)
                environment.update(values)
                environment[capture.CAPTURE_API_KEY_ENV] = created.plaintext_key
                capture._write_0149_model_catalog(
                    binary, catalog, environment=environment, model=CODEX_MODEL
                )
                catalog_value = json.loads(catalog.read_text(encoding="utf-8"))
                if not isinstance(catalog_value, Mapping):
                    raise VerificationError("vision_catalog_not_object")
                _write_and_validate_vision_catalog(catalog, catalog_value, model=CODEX_MODEL)
                gateway_port = _free_port()
                observation = GatewayObservation(
                    create_app(configured_settings()), image_expectations=image_expectations
                )
                first = _initial_command(
                    binary,
                    workdir=work,
                    port=gateway_port,
                    model_catalog=catalog,
                    output=root / "first-output.json",
                    full_image=fixture_facts["full_path"],
                )
                _validate_command_binding(
                    first, expected_image=fixture_facts["full_path"], resume=False
                )
                first_result = None
                previous_logging_disable = logging.root.manager.disable
                logging.disable(logging.CRITICAL)
                try:
                    with _run_uvicorn_server(observation, gateway_port):
                        first_result = _run(first, cwd=work, env=environment, timeout=180)
                        if first_result.returncode != 0:
                            category = _codex_failure_category(
                                first_result.stderr, first_result.stdout
                            )
                            raise VerificationError(
                                f"codex_first_turn_{category}_{_safe_failure_progress(observation, local)}"
                            )
                        del first_result
                        if _private_session_count(home) != 1:
                            raise VerificationError("private_session_count_invalid")
                        second = _resume_last_command(
                            binary,
                            workdir=work,
                            port=gateway_port,
                            model_catalog=catalog,
                            output=root / "second-output.json",
                            crop_image=fixture_facts["crop_path"],
                        )
                        _validate_command_binding(
                            second, expected_image=fixture_facts["crop_path"], resume=True
                        )
                        second_result = _run(second, cwd=work, env=environment, timeout=180)
                        if second_result.returncode == 0:
                            raise VerificationError("history_rejection_not_reproduced")
                        del second_result
                finally:
                    logging.disable(previous_logging_disable)
                if observation.request_count != 3 or observation.response_statuses != [
                    200,
                    200,
                    400,
                ]:
                    raise VerificationError(
                        f"gateway_request_progression_{_safe_progress_class(observation.request_count)}"
                        f"_statuses_{_safe_status_sequence(observation)}"
                        f"_local_{_safe_progress_class(state.request_count)}"
                    )
                if observation.error_codes[-1] != _ALLOWED_ERROR_CODE:
                    raise VerificationError("history_error_code_invalid")
                if observation.param_classes[-1] != "input_5_content_0_type":
                    raise VerificationError(f"history_error_param_{observation.param_classes[-1]}")
                projection = observation.second_projection or {}
                if not observation.request_projections:
                    raise VerificationError("gateway_image_projection_missing")
                if observation.request_projections[0].get("image_wire_class") != "full":
                    raise VerificationError("gateway_full_image_missing")
                if observation.request_projections[-1].get("image_wire_class") != "crop":
                    raise VerificationError("gateway_crop_image_missing")
                if any(
                    item.get("image_wire_class") not in {"full", "none"}
                    for item in observation.request_projections[1:-1]
                ):
                    raise VerificationError("gateway_intermediate_image_class_invalid")
                required = (
                    projection.get("assistant_history_present") is True,
                    projection.get("assistant_role_exact") is True,
                    projection.get("assistant_output_text_count") == 1,
                    projection.get("assistant_output_text_type_exact") is True,
                    projection.get("assistant_output_text_nonempty_unicode") is True,
                    projection.get("image_part_count_class") == "one",
                    projection.get("image_wire_class") == "crop",
                    projection.get("raw_value_retained") is False,
                )
                if not all(required):
                    if projection.get("image_part_count_class") != "one":
                        raise VerificationError(
                            f"history_projection_image_count_{projection.get('image_part_count_class', 'other')}"
                            f"_sequence_{'_'.join(observation.image_count_classes[:4]) or 'none'}"
                        )
                    names = (
                        "history_present",
                        "role",
                        "output_text_count",
                        "output_text_type",
                        "output_text_unicode",
                        "image_count",
                        "crop_image",
                        "raw_absent",
                    )
                    failed = "_".join(name for name, passed in zip(names, required) if not passed)
                    raise VerificationError(f"history_projection_invalid_{failed or 'other'}")
                if state.request_count != 2 or state.signed_request_count != 2:
                    raise VerificationError("fake_local_advanced_on_rejection")
                if state.function_count != 1 or state.message_count != 1:
                    raise VerificationError("fake_local_lifecycle_invalid")
                return "VERIFY_CODEX_0149_ASSISTANT_HISTORY_REPRODUCTION_OK request_count=3 local_count=2 clean_rejection=true"
    finally:
        local.shutdown()
        local.server_close()
        local_thread.join(timeout=5)
        if own_db and db_name:
            try:
                subprocess.run(
                    ["sudo", "-n", "-u", "postgres", "dropdb", "--if-exists", db_name],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    check=False,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        print(run_prefixed_reproduction())
        return 0
    except VerificationError as exc:
        print(f"VERIFY_CODEX_0149_ASSISTANT_HISTORY_BASE_FAILED code={exc.args[0]}")
        return 1
    except Exception as exc:
        name = type(exc).__name__
        safe_name = (
            name
            if name in {"AttributeError", "KeyError", "TypeError", "ValueError", "IndexError"}
            else "other"
        )
        print(f"VERIFY_CODEX_0149_ASSISTANT_HISTORY_BASE_FAILED code=unexpected_{safe_name}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

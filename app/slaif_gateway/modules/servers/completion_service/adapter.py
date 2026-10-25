"""One bounded completion adapter; service behavior is selected by JSON profiles."""

from __future__ import annotations

import base64
import binascii
import math
import json
import re
import secrets
import time
from collections.abc import Mapping
from typing import Any

import httpx

from slaif_gateway.config import Settings
from slaif_gateway.modules.servers.base import ServerModuleAdapter
from slaif_gateway.modules.servers.completion_service.profiles import (
    CompletionProfile,
    load_default_profile,
)
from slaif_gateway.providers.diagnostics import build_provider_error_diagnostic_from_response
from slaif_gateway.providers.errors import (
    MissingProviderApiKeyError,
    ProviderConfigurationError,
    ProviderHTTPError,
    ProviderRequestError,
    ProviderResponseParseError,
    ProviderTimeoutError,
    UnsupportedProviderEndpointError,
)
from slaif_gateway.schemas.providers import ProviderRequest, ProviderResponse, ProviderUsage

DEFAULT_SCORE_TYPE = "uncalibrated_model_score"

_ALLOWED_ENDPOINTS = {"/v1/chat/completions", "chat.completions"}
_ALLOWED_TOP_LEVEL_FIELDS = frozenset(
    {"model", "messages", "stream", "n", "max_tokens", "max_completion_tokens"}
)
_ALLOWED_MESSAGE_FIELDS = frozenset({"role", "content"})
_ALLOWED_TEXT_PART_FIELDS = frozenset({"type", "text"})
_ALLOWED_IMAGE_PART_FIELDS = frozenset({"type", "image_url"})
_ALLOWED_IMAGE_URL_FIELDS = frozenset({"url", "detail"})
_IMAGE_MEDIA = {
    "image/png": ("image.png", "image/png"),
    "image/jpeg": ("image.jpg", "image/jpeg"),
    "image/webp": ("image.webp", "image/webp"),
    "image/gif": ("image.gif", "image/gif"),
}
_DATA_URL_PATTERN = re.compile(
    r"data:(image/(?:png|jpeg|webp|gif));base64,([A-Za-z0-9+/]+={0,2})",
    re.IGNORECASE,
)
_MAX_DATA_URL_BYTES = int(Settings.model_fields["CHAT_MAX_IMAGE_DATA_URL_BYTES"].default)
_MAX_SCORE_TYPE_BYTES = 128
_MAX_REASON_BYTES = 512


class CompletionServiceAdapter(ServerModuleAdapter):
    """Translate authorized Chat inputs using fixed, declarative mapping primitives."""

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        timeout_seconds: int,
        max_retries: int,
        http_client: httpx.AsyncClient | None = None,
        profile: CompletionProfile | None = None,
    ) -> None:
        self.profile = profile or load_default_profile()
        if max_retries != 0:
            raise ProviderConfigurationError(
                "Completion service does not support retries.",
                provider=provider_name,
                status_code=500,
                error_code="invalid_provider_configuration",
            )
        super().__init__(
            provider_name=provider_name,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=0,
        )
        self._http_client = http_client

    @property
    def module_id(self) -> str:
        return self.profile.module_id

    async def forward_chat_completion(self, request: ProviderRequest) -> ProviderResponse:
        if request.endpoint not in _ALLOWED_ENDPOINTS:
            raise UnsupportedProviderEndpointError(provider=self.provider_name)
        if request.upstream_model != self.profile.upstream_model:
            raise self._invalid_request("The selected completion service model is not available.")
        if not self._api_key:
            raise MissingProviderApiKeyError(provider=self.provider_name)

        image_data, filename, media_type = self._extract_image(request.body)
        yaml_text = self._extract_yaml(request.body)
        response = await self._post_service(
            yaml_text=yaml_text,
            image_data=image_data,
            filename=filename,
            media_type=media_type,
        )
        return await self._completion_response(request, response)

    def _extract_image(self, body: Mapping[str, Any]) -> tuple[bytes, str, str]:
        if not isinstance(body, Mapping):
            raise self._invalid_request("Completion service request body is invalid.")

        unexpected_fields = set(body) - _ALLOWED_TOP_LEVEL_FIELDS
        if unexpected_fields:
            raise self._invalid_request(
                "This completion service route does not support that request field."
            )
        if body.get("model") not in {self.profile.public_model, self.profile.upstream_model}:
            raise self._invalid_request("The selected completion service model is not available.")
        if "stream" in body and body.get("stream") is not False:
            raise self._invalid_request("Completion service does not support streaming.")
        if "n" in body and body.get("n") != 1:
            raise self._invalid_request("Completion service supports exactly one choice.")
        for field in ("max_tokens", "max_completion_tokens"):
            value = body.get(field)
            if field in body and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise self._invalid_request("Completion service output controls are invalid.")

        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise self._invalid_request("Completion service requires one image content part.")

        image: tuple[bytes, str, str] | None = None
        for message in messages:
            if not isinstance(message, Mapping):
                raise self._invalid_request("Completion service message content is invalid.")
            if set(message) - _ALLOWED_MESSAGE_FIELDS:
                raise self._invalid_request("Completion service message content is invalid.")
            if not isinstance(message.get("role"), str) or not message["role"].strip():
                raise self._invalid_request("Completion service message content is invalid.")
            content = message.get("content")
            if not isinstance(content, list) or not content:
                raise self._invalid_request("Completion service requires one image content part.")
            for part in content:
                if not isinstance(part, Mapping) or not isinstance(part.get("type"), str):
                    raise self._invalid_request("Completion service message content is invalid.")
                part_type = part["type"]
                if part_type == "text":
                    if set(part) != _ALLOWED_TEXT_PART_FIELDS or not isinstance(
                        part.get("text"), str
                    ):
                        raise self._invalid_request("Completion service text content is invalid.")
                    continue
                if part_type != "image_url":
                    raise self._invalid_request(
                        "Completion service supports image_url content only."
                    )
                if set(part) != _ALLOWED_IMAGE_PART_FIELDS:
                    raise self._invalid_request("Completion service image content is invalid.")
                image_url = part.get("image_url")
                if not isinstance(image_url, Mapping) or set(image_url) - _ALLOWED_IMAGE_URL_FIELDS:
                    raise self._invalid_request("Completion service image content is invalid.")
                detail = image_url.get("detail")
                if detail is not None and detail not in {"auto", "low", "high"}:
                    raise self._invalid_request("Completion service image detail is invalid.")
                if image is not None:
                    raise self._invalid_request("Completion service accepts exactly one image.")
                image = self._decode_image_url(image_url)

        if image is None:
            raise self._invalid_request("Completion service requires one image content part.")
        return image

    def _decode_image_url(self, image_url: Mapping[str, Any]) -> tuple[bytes, str, str]:
        value = image_url.get("url")
        if not isinstance(value, str) or not value:
            raise self._invalid_request("Completion service image content is invalid.")
        if len(value.encode("utf-8")) > min(
            _MAX_DATA_URL_BYTES, self.profile.max_image_data_url_bytes
        ):
            raise self._invalid_request("Completion service image data exceeds the gateway limit.")

        match = _DATA_URL_PATTERN.fullmatch(value)
        if match is None:
            raise self._invalid_request(
                "Completion service requires a supported base64 image data URL."
            )
        media_type = match.group(1).lower()
        if media_type not in self.profile.image_media_types:
            raise self._invalid_request("Image media type is not supported by this route.")
        encoded = match.group(2)
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise self._invalid_request(
                "Completion service image data is not valid base64."
            ) from exc
        if not decoded:
            raise self._invalid_request("Completion service image data is empty.")

        filename, canonical_media_type = _IMAGE_MEDIA[media_type]
        return decoded, filename, canonical_media_type

    def _extract_yaml(self, body: Mapping[str, Any]) -> str | None:
        if self.profile.request_mapping == "multipart_image":
            return None
        messages = body["messages"]
        if len(messages) != 1 or messages[0]["role"] != "user":
            raise self._invalid_request("This service requires exactly one user message.")
        parts = [p["text"] for p in messages[0]["content"] if p["type"] == "text"]
        if len(parts) != 1 or not parts[0].strip():
            raise self._invalid_request("This service requires exactly one YAML text part.")
        if len(parts[0].encode("utf-8")) > self.profile.max_yaml_bytes:
            raise self._invalid_request("Service configuration exceeds the route size limit.")
        return parts[0]

    async def _post_service(
        self,
        *,
        image_data: bytes,
        filename: str,
        media_type: str,
        yaml_text: str | None = None,
    ) -> httpx.Response:
        timeout_seconds = float(self._timeout_seconds)
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ProviderConfigurationError(provider=self.provider_name)
        timeout = httpx.Timeout(timeout_seconds)
        headers = {
            self.profile.auth_header: self.profile.auth_prefix + self._api_key,
            "Accept": "application/json",
        }
        url = f"{self._base_url.rstrip('/')}{self.profile.upstream_path}"
        if self.profile.request_mapping == "multipart_image":
            kwargs = {"files": {"image": (filename, image_data, media_type)}}
        else:
            assert yaml_text is not None
            image_url = (
                "data:" + media_type + ";base64," + base64.b64encode(image_data).decode("ascii")
            )
            file_url = "data:application/yaml;base64," + base64.b64encode(
                yaml_text.encode("utf-8")
            ).decode("ascii")
            kwargs = {
                "json": {
                    "model": self.profile.upstream_model,
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_image", "image_url": image_url, "detail": "auto"},
                                {
                                    "type": "input_file",
                                    "filename": "task.yaml",
                                    "file_data": file_url,
                                },
                            ],
                        }
                    ],
                }
            }
            if self.profile.request_image_output:
                kwargs["json"]["tools"] = [{"type": "image_generation"}]
        try:
            if self._http_client is not None:
                return await self._bounded_post(self._http_client, url, headers, timeout, kwargs)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                return await self._bounded_post(client, url, headers, timeout, kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(provider=self.provider_name) from exc
        except httpx.HTTPError as exc:
            raise ProviderRequestError(provider=self.provider_name) from exc

    async def _bounded_post(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        timeout: httpx.Timeout,
        kwargs: dict[str, Any],
    ) -> httpx.Response:
        async with client.stream(
            "POST", url, headers=headers, timeout=timeout, follow_redirects=False, **kwargs
        ) as response:
            chunks = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self.profile.max_response_bytes:
                    raise ProviderResponseParseError(provider=self.provider_name)
                chunks.append(chunk)
            return httpx.Response(
                response.status_code,
                content=b"".join(chunks),
                request=response.request,
                headers={
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() not in {"content-encoding", "content-length"}
                },
            )

    async def _completion_response(
        self, request: ProviderRequest, response: httpx.Response
    ) -> ProviderResponse:
        if response.status_code < 200 or response.status_code >= 300:
            diagnostic = await build_provider_error_diagnostic_from_response(
                provider=self.provider_name,
                response=response,
            )
            raise ProviderHTTPError(
                provider=self.provider_name,
                upstream_status_code=response.status_code,
                diagnostic=diagnostic,
            )
        try:
            payload = response.json()
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            raise ProviderResponseParseError(provider=self.provider_name) from exc
        if not isinstance(payload, Mapping):
            raise ProviderResponseParseError(provider=self.provider_name)

        image_url = None
        if self.profile.response_mapping == "json_fields":
            text, image_url = self._map_output_fields(payload)
        else:
            text = (
                self._format_score(payload)
                if self.profile.response_mapping == "score_status"
                else self._format_json_projection(payload)
            )
        message = {"role": "assistant", "content": text}
        if image_url is not None:
            message["images"] = [{"type": "image_url", "image_url": {"url": image_url}}]
        body = {
            "id": f"{self.profile.response_id_prefix}{secrets.token_hex(12)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.profile.public_model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
        return ProviderResponse(
            provider=self.provider_name,
            upstream_model=request.upstream_model,
            status_code=200,
            json_body=body,
            usage=ProviderUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )

    def _format_score(self, payload: Mapping[str, Any]) -> str:
        status = payload.get("status")
        if status == "scored":
            score = payload.get("score")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise ProviderResponseParseError(provider=self.provider_name)
            if not math.isfinite(float(score)) or not 0 <= float(score) <= 1:
                raise ProviderResponseParseError(provider=self.provider_name)
            score_type = payload.get("score_type", DEFAULT_SCORE_TYPE)
            if not isinstance(score_type, str) or not score_type.strip():
                raise ProviderResponseParseError(provider=self.provider_name)
            score_type = _sanitize_text(score_type, max_bytes=_MAX_SCORE_TYPE_BYTES)
            if not score_type:
                raise ProviderResponseParseError(provider=self.provider_name)
            return f"Score: {float(score):.4f} (type: {score_type})"
        if status == "unscorable":
            reason = payload.get("reason")
            if reason is None:
                return "Result: unscorable"
            if not isinstance(reason, str):
                raise ProviderResponseParseError(provider=self.provider_name)
            sanitized_reason = _sanitize_text(reason, max_bytes=_MAX_REASON_BYTES)
            if not sanitized_reason:
                return "Result: unscorable"
            return f"Result: unscorable ({sanitized_reason})"
        raise ProviderResponseParseError(provider=self.provider_name)

    def _format_json_projection(self, payload: Mapping[str, Any]) -> str:
        try:
            if payload.get("status") != "completed":
                raise ValueError("Incomplete response")
            output = payload["output"]
            if not isinstance(output, list) or len(output) != 1:
                raise ValueError("Unsupported output items")
            message = output[0]
            if message.get("type") != "message" or message.get("role") != "assistant":
                raise ValueError("Unsupported message")
            parts = message["content"]
            if (
                not isinstance(parts, list)
                or len(parts) != 1
                or parts[0].get("type") != "output_text"
            ):
                raise ValueError("Unsupported content")
            text = parts[0]["text"]
            if not isinstance(text, str):
                raise ValueError("Invalid text")
            projection = json.loads(text)
            if (
                not isinstance(projection, dict)
                or projection.get("schema_version") != self.profile.result_schema_version
            ):
                raise ValueError("Unexpected projection schema")
            return json.dumps(
                projection,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
            raise ProviderResponseParseError(provider=self.provider_name) from exc

    def _map_output_fields(self, payload: Mapping[str, Any]) -> tuple[str, str | None]:
        """Map text and one image using profile data, independent of service identity."""
        try:
            for pointer, expected in self.profile.response_checks.items():
                actual = _json_pointer(payload, pointer)
                if type(actual) is not type(expected) or actual != expected:
                    raise ValueError("Response check failed")
            for pointer, length in self.profile.response_array_lengths.items():
                value = _json_pointer(payload, pointer)
                if not isinstance(value, list) or len(value) != length:
                    raise ValueError("Response cardinality check failed")
            text = _json_pointer(payload, self.profile.text_pointer)
            if not isinstance(text, str):
                raise ValueError("Output text must be a string")
            if self.profile.result_schema_version is not None:
                projection = json.loads(text)
                if (
                    not isinstance(projection, dict)
                    or projection.get("schema_version") != self.profile.result_schema_version
                ):
                    raise ValueError("Unexpected projection schema")
                text = json.dumps(
                    projection,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            image = self.profile.image_output
            if image is None:
                return text, None
            encoded = _json_pointer(payload, image.pointer)
            if (
                not isinstance(encoded, str)
                or not encoded
                or len(encoded) > 4 * ((image.max_decoded_bytes + 2) // 3)
            ):
                raise ValueError("Image output exceeds its encoded bound")
            decoded = base64.b64decode(encoded, validate=True)
            if not decoded or len(decoded) > image.max_decoded_bytes:
                raise ValueError("Image output exceeds its decoded bound")
            signatures = {
                "image/png": decoded.startswith(b"\x89PNG\r\n\x1a\n"),
                "image/jpeg": decoded.startswith(b"\xff\xd8\xff"),
                "image/webp": decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP",
            }
            if not signatures[image.media_type]:
                raise ValueError("Image signature does not match profile media type")
            return text, f"data:{image.media_type};base64,{encoded}"
        except (ValueError, KeyError, TypeError, IndexError, RecursionError) as exc:
            raise ProviderResponseParseError(provider=self.provider_name) from exc

    def _invalid_request(self, message: str) -> ProviderRequestError:
        return ProviderRequestError(
            message,
            provider=self.provider_name,
            status_code=400,
            error_type="invalid_request_error",
            error_code=self.profile.request_error_code,
        )


def _json_pointer(value: Any, pointer: str) -> Any:
    for segment in pointer[1:].split("/"):
        key = segment.replace("~1", "/").replace("~0", "~")
        if isinstance(value, Mapping):
            value = value[key]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
            value = value[int(key)]
        else:
            raise ValueError("Output selector does not match response")
    return value


def _sanitize_text(value: str, *, max_bytes: int) -> str:
    sanitized = " ".join(value.split())
    encoded = sanitized.encode("utf-8")
    if len(encoded) <= max_bytes:
        return sanitized
    return encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip()

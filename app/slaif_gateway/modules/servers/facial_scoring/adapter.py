"""Native adapter for the bounded facial-manipulation scoring server module."""

from __future__ import annotations

import base64
import binascii
import math
import re
import secrets
import time
from collections.abc import Mapping
from typing import Any

import httpx

from slaif_gateway.config import Settings
from slaif_gateway.modules.servers.base import ServerModuleAdapter
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

FACIAL_SCORING_MODULE_ID = "facial_scoring"
FACIAL_SCORING_PUBLIC_MODEL = "facial-manipulation-scoring"
FACIAL_SCORING_SCORE_PATH = "/v1/score"
FACIAL_SCORING_DEFAULT_SCORE_TYPE = "uncalibrated_model_score"

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


class FacialScoringAdapter(ServerModuleAdapter):
    """Translate one validated Chat image into the module's score request."""

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        api_key: str,
        timeout_seconds: int,
        max_retries: int,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if max_retries != 0:
            raise ProviderConfigurationError(
                "Facial scoring does not support retries.",
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
        return FACIAL_SCORING_MODULE_ID

    async def forward_chat_completion(self, request: ProviderRequest) -> ProviderResponse:
        if request.endpoint not in _ALLOWED_ENDPOINTS:
            raise UnsupportedProviderEndpointError(provider=self.provider_name)
        if request.upstream_model != FACIAL_SCORING_PUBLIC_MODEL:
            raise self._invalid_request("The selected facial scoring model is not available.")
        if not self._api_key:
            raise MissingProviderApiKeyError(provider=self.provider_name)

        image_data, filename, media_type = self._extract_image(request.body)
        response = await self._post_score(
            image_data=image_data,
            filename=filename,
            media_type=media_type,
        )
        return await self._score_response(request, response)

    def _extract_image(self, body: Mapping[str, Any]) -> tuple[bytes, str, str]:
        if not isinstance(body, Mapping):
            raise self._invalid_request("Facial scoring request body is invalid.")

        unexpected_fields = set(body) - _ALLOWED_TOP_LEVEL_FIELDS
        if unexpected_fields:
            raise self._invalid_request("This facial scoring route does not support that request field.")
        if body.get("model") != FACIAL_SCORING_PUBLIC_MODEL:
            raise self._invalid_request("The selected facial scoring model is not available.")
        if "stream" in body and body.get("stream") is not False:
            raise self._invalid_request("Facial scoring does not support streaming.")
        if "n" in body and body.get("n") != 1:
            raise self._invalid_request("Facial scoring supports exactly one choice.")
        for field in ("max_tokens", "max_completion_tokens"):
            value = body.get(field)
            if field in body and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
                raise self._invalid_request("Facial scoring output controls are invalid.")

        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise self._invalid_request("Facial scoring requires one image content part.")

        image: tuple[bytes, str, str] | None = None
        for message in messages:
            if not isinstance(message, Mapping):
                raise self._invalid_request("Facial scoring message content is invalid.")
            if set(message) - _ALLOWED_MESSAGE_FIELDS:
                raise self._invalid_request("Facial scoring message content is invalid.")
            if not isinstance(message.get("role"), str) or not message["role"].strip():
                raise self._invalid_request("Facial scoring message content is invalid.")
            content = message.get("content")
            if not isinstance(content, list) or not content:
                raise self._invalid_request("Facial scoring requires one image content part.")
            for part in content:
                if not isinstance(part, Mapping) or not isinstance(part.get("type"), str):
                    raise self._invalid_request("Facial scoring message content is invalid.")
                part_type = part["type"]
                if part_type == "text":
                    if set(part) != _ALLOWED_TEXT_PART_FIELDS or not isinstance(part.get("text"), str):
                        raise self._invalid_request("Facial scoring text content is invalid.")
                    continue
                if part_type != "image_url":
                    raise self._invalid_request("Facial scoring supports image_url content only.")
                if set(part) != _ALLOWED_IMAGE_PART_FIELDS:
                    raise self._invalid_request("Facial scoring image content is invalid.")
                image_url = part.get("image_url")
                if not isinstance(image_url, Mapping) or set(image_url) - _ALLOWED_IMAGE_URL_FIELDS:
                    raise self._invalid_request("Facial scoring image content is invalid.")
                detail = image_url.get("detail")
                if detail is not None and detail not in {"auto", "low", "high"}:
                    raise self._invalid_request("Facial scoring image detail is invalid.")
                if image is not None:
                    raise self._invalid_request("Facial scoring accepts exactly one image.")
                image = self._decode_image_url(image_url)

        if image is None:
            raise self._invalid_request("Facial scoring requires one image content part.")
        return image

    def _decode_image_url(self, image_url: Mapping[str, Any]) -> tuple[bytes, str, str]:
        value = image_url.get("url")
        if not isinstance(value, str) or not value:
            raise self._invalid_request("Facial scoring image content is invalid.")
        if len(value.encode("utf-8")) > _MAX_DATA_URL_BYTES:
            raise self._invalid_request("Facial scoring image data exceeds the gateway limit.")

        match = _DATA_URL_PATTERN.fullmatch(value)
        if match is None:
            raise self._invalid_request("Facial scoring requires a supported base64 image data URL.")
        media_type = match.group(1).lower()
        encoded = match.group(2)
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise self._invalid_request("Facial scoring image data is not valid base64.") from exc
        if not decoded:
            raise self._invalid_request("Facial scoring image data is empty.")

        filename, canonical_media_type = _IMAGE_MEDIA[media_type]
        return decoded, filename, canonical_media_type

    async def _post_score(self, *, image_data: bytes, filename: str, media_type: str) -> httpx.Response:
        timeout_seconds = float(self._timeout_seconds)
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ProviderRequestError(
                "Facial scoring provider timeout is not configured correctly.",
                provider=self.provider_name,
                error_code="invalid_provider_configuration",
            )
        timeout = httpx.Timeout(
            timeout_seconds,
            connect=timeout_seconds,
            read=timeout_seconds,
            write=timeout_seconds,
            pool=timeout_seconds,
        )
        files = {"image": (filename, image_data, media_type)}
        headers = {"X-API-Key": self._api_key, "Accept": "application/json"}
        url = f"{self._base_url.rstrip('/')}{FACIAL_SCORING_SCORE_PATH}"
        try:
            if self._http_client is not None:
                return await self._http_client.post(
                    url,
                    files=files,
                    headers=headers,
                    timeout=timeout,
                    follow_redirects=False,
                )
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                return await client.post(
                    url,
                    files=files,
                    headers=headers,
                    timeout=timeout,
                    follow_redirects=False,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(provider=self.provider_name) from exc
        except httpx.HTTPError as exc:
            raise ProviderRequestError(provider=self.provider_name) from exc

    async def _score_response(self, request: ProviderRequest, response: httpx.Response) -> ProviderResponse:
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
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderResponseParseError(provider=self.provider_name) from exc
        if not isinstance(payload, Mapping):
            raise ProviderResponseParseError(provider=self.provider_name)

        text = self._format_score(payload)
        body = {
            "id": f"chatcmpl-facial-{secrets.token_hex(12)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": FACIAL_SCORING_PUBLIC_MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
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
            score_type = payload.get("score_type", FACIAL_SCORING_DEFAULT_SCORE_TYPE)
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

    def _invalid_request(self, message: str) -> ProviderRequestError:
        return ProviderRequestError(
            message,
            provider=self.provider_name,
            status_code=400,
            error_type="invalid_request_error",
            error_code="facial_scoring_request_invalid",
        )


def _sanitize_text(value: str, *, max_bytes: int) -> str:
    sanitized = " ".join(value.split())
    encoded = sanitized.encode("utf-8")
    if len(encoded) <= max_bytes:
        return sanitized
    return encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip()

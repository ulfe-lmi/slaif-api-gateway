"""Static, Chat-only native-vLLM media transport; no policy/accounting authority."""

import copy
from collections.abc import Mapping
from dataclasses import replace

from slaif_gateway.providers.base import ProviderAdapter
from slaif_gateway.providers.errors import ProviderConfigurationError, ProviderRequestError
from slaif_gateway.providers.openai_compatible import OpenAICompatibleProviderAdapter

MODULE_ID = "vllm-chat-video-v1"
CAPABILITY_KEY = "vllm_chat_video"


def parse_video_frames(capabilities):
    if not isinstance(capabilities, Mapping):
        raise ValueError("Missing native video contract")
    contract = capabilities.get(CAPABILITY_KEY)
    media = capabilities.get("media_input_estimation")
    if (
        not isinstance(contract, Mapping)
        or set(contract) != {"version"}
        or type(contract["version"]) is not int
        or contract["version"] != 1
        or not isinstance(media, Mapping)
        or type(media.get("version")) is not int
        or media["version"] != 1
    ):
        raise ValueError("Invalid native video contract")
    frames, tokens = media.get("video_frames"), media.get("video_tokens")
    if (
        type(frames) is not int
        or not 1 <= frames <= 32
        or type(tokens) is not int
        or not 1 <= tokens <= 1_050_000
    ):
        raise ValueError("Missing bounded video processing policy")
    if "local_coding" in capabilities or "local_coding_vllm" in capabilities:
        raise ValueError("Conflicting server contracts")
    return frames


class VLLMChatVideoAdapter(ProviderAdapter):
    def __init__(self, settings, *, route_capabilities=None, **kwargs):
        try:
            self._frames = parse_video_frames(route_capabilities)
        except ValueError as exc:
            raise ProviderConfigurationError(
                provider=kwargs.get("provider_name"), error_code="vllm_video_contract_invalid"
            ) from exc
        self._delegate = OpenAICompatibleProviderAdapter(settings, **kwargs)

    @property
    def provider_name(self):
        return self._delegate.provider_name

    def prepare(self, request):
        body = copy.deepcopy(dict(request.body))
        if any(k in body for k in ("media_io_kwargs", "mm_processor_kwargs", "chat_template")):
            raise ProviderRequestError(provider=self.provider_name)
        videos = []
        for message in body.get("messages", []):
            if not isinstance(message, Mapping) or not isinstance(message.get("content"), list):
                continue
            for part in message["content"]:
                if isinstance(part, Mapping) and part.get("type") == "video_url":
                    value = part.get("video_url")
                    url = value.get("url") if isinstance(value, Mapping) else None
                    if (
                        message.get("role") != "user"
                        or not isinstance(url, str)
                        or not url.startswith(("data:video/mp4;base64,", "data:video/webm;base64,"))
                    ):
                        raise ProviderRequestError(provider=self.provider_name)
                    videos.append(url)
        if len(videos) > 1:
            raise ProviderRequestError(provider=self.provider_name)
        if videos:
            body["media_io_kwargs"] = {"video": {"num_frames": self._frames}}
        return replace(request, body=body)

    async def forward_chat_completion(self, request):
        return await self._delegate.forward_chat_completion(self.prepare(request))

    async def stream_chat_completion(self, request):
        async for chunk in self._delegate.stream_chat_completion(self.prepare(request)):
            yield chunk

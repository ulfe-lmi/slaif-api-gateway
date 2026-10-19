"""Native vLLM Responses transport with explicit bidirectional tool translation."""

import json
from dataclasses import replace

from slaif_gateway.modules.servers.local_coding.adapter import LocalCodingAdapter
from slaif_gateway.modules.servers.local_coding_vllm.codec import VLLMToolCodec
from slaif_gateway.modules.servers.local_coding_vllm.contract import parse_vllm_route_contract
from slaif_gateway.providers.errors import ProviderConfigurationError


class LocalCodingVLLMAdapter(LocalCodingAdapter):
    def __init__(self, settings, *, route_capabilities=None, **kwargs):
        try:
            contract = parse_vllm_route_contract(route_capabilities)
            if contract is None:
                raise ValueError("Native vLLM contract missing")
        except ValueError as exc:
            raise ProviderConfigurationError(
                provider=kwargs.get("provider_name"), error_code="vllm_route_contract_invalid"
            ) from exc
        legacy = dict(route_capabilities["local_coding_vllm"], contract_version="local-coding-v1")
        super().__init__(settings, route_capabilities={"local_coding": legacy}, **kwargs)
        self._local_coding_contract = contract

    async def forward_response(self, request):
        codec = VLLMToolCodec(request.body)
        result = await super().forward_response(replace(request, body=codec.body))
        return replace(result, json_body=codec.response(result.json_body))

    async def stream_response(self, request):
        codec = VLLMToolCodec(request.body)
        async for chunk in super().stream_response(replace(request, body=codec.body)):
            if chunk.is_done or chunk.json_body is None:
                yield chunk
                continue
            for event in codec.events(chunk.json_body):
                data = json.dumps(event, ensure_ascii=True, separators=(",", ":"))
                yield replace(
                    chunk,
                    data=data,
                    json_body=event,
                    raw_sse_event=f"event: {event['type']}\ndata: {data}\n\n",
                )

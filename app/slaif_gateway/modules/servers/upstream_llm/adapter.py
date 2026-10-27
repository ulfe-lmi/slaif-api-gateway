"""One Responses transport with explicit, data-selected upstream translations."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

from slaif_gateway.modules.servers.local_coding.adapter import LocalCodingAdapter
from slaif_gateway.modules.servers.local_coding_vllm.codec import VLLMToolCodec
from slaif_gateway.modules.servers.upstream_llm.profiles import validate_route


def normalize_instructions(body: dict, placement: str) -> dict:
    """Stable partition of canonical messages; no role/content changes or deletion.

    Moving instructions changes their temporal position. Only an explicitly
    selected operator profile requests this tradeoff for prefix-only templates.
    Tool calls, results, identifiers, images, and their relative order stay intact.
    """
    result = copy.deepcopy(body)
    if placement == "leading_system_developer" and isinstance(result.get("input"), list):
        instructions, history = [], []
        for item in result["input"]:
            is_instruction = (
                isinstance(item, dict)
                and item.get("type", "message") == "message"
                and isinstance(item.get("role"), str)
                and item.get("role") in {"system", "developer"}
            )
            (instructions if is_instruction else history).append(item)
        result["input"] = instructions + history
    return result


class ConfiguredUpstreamLLMAdapter(LocalCodingAdapter):
    """Profiles configure existing transport operations; they grant no authority."""

    def __init__(self, settings, *, route_capabilities=None, **kwargs):
        self.profile = validate_route(route_capabilities)
        super().__init__(settings, route_capabilities=route_capabilities, **kwargs)

    def _prepare(self, request):
        body = normalize_instructions(dict(request.body), self.profile.instruction_placement)
        codec = VLLMToolCodec(body) if self.profile.tool_encoding == "native_vllm" else None
        return replace(request, body=codec.body if codec is not None else body), codec

    async def forward_response(self, request):
        prepared, codec = self._prepare(request)
        response = await super().forward_response(prepared)
        if codec is not None:
            return replace(response, json_body=codec.response(response.json_body))
        return response

    async def stream_response(self, request):
        prepared, codec = self._prepare(request)
        async for chunk in super().stream_response(prepared):
            if codec is None or chunk.is_done or chunk.json_body is None:
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

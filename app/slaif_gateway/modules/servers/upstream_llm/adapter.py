"""One Responses transport with explicit, data-selected upstream translations."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

from slaif_gateway.modules.servers.local_coding.adapter import LocalCodingAdapter
from slaif_gateway.modules.servers.local_coding_vllm.codec import VLLMToolCodec
from slaif_gateway.modules.servers.upstream_llm.profiles import validate_route
from slaif_gateway.providers.errors import ProviderRequestError


def _is_instruction_item(item: object) -> bool:
    return (
        isinstance(item, dict)
        and item.get("type", "message") == "message"
        and isinstance(item.get("role"), str)
        and item.get("role") in {"system", "developer"}
    )


def instructions_already_leading(input_items: object) -> bool:
    """True when no instruction item follows a non-instruction item.

    That is exactly the case in which ``normalize_instructions`` with
    ``leading_system_developer`` is a no-op on relative order, so a
    lifecycle-bearing request remains representable on such a profile.
    """
    seen_non_instruction = False
    for item in input_items or []:
        if _is_instruction_item(item):
            if seen_non_instruction:
                return False
        else:
            seen_non_instruction = True
    return True


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
            is_instruction = _is_instruction_item(item)
            (instructions if is_instruction else history).append(item)
        result["input"] = instructions + history
    return result


def prepare_upstream_llm_body(
    body: dict,
    profile,
    *,
    tool_call_bindings=None,
) -> tuple[dict, object]:
    """Pure request-body preparation for one validated upstream LLM profile.

    Shared by the production adapter and the pre-admission core preview so
    both run the exact deterministic transformation (instruction placement
    plus codec translation) with no provider, credential, HTTP, or
    route-lookup machinery.  Returns ``(prepared body, codec or None)``.
    """
    prepared = normalize_instructions(dict(body), profile.instruction_placement)
    if profile.tool_encoding in {"native_vllm", "function_tools"}:
        codec = VLLMToolCodec(
            prepared,
            portable_names=profile.tool_encoding == "function_tools",
            tool_call_bindings=tool_call_bindings,
        )
        return codec.body, codec
    return prepared, None


class ConfiguredUpstreamLLMAdapter(LocalCodingAdapter):
    """Profiles configure existing transport operations; they grant no authority."""

    def _forbidden_service_secret_values(self) -> tuple[str | None, ...]:
        # This transport deliberately uses the selected provider credential.
        # Gateway authentication/encryption and identity secrets stay separate.
        return (
            self._settings.TOKEN_HMAC_SECRET_V1,
            self._settings.TOKEN_HMAC_SECRET,
            self._settings.ADMIN_SESSION_SECRET,
            self._settings.ONE_TIME_SECRET_ENCRYPTION_KEY,
        )

    def __init__(self, settings, *, route_capabilities=None, **kwargs):
        self.profile = validate_route(route_capabilities)
        super().__init__(settings, route_capabilities=route_capabilities, **kwargs)

    def _prepare(self, request):
        if (
            request.codex_tool_call_bindings is not None
            and self.profile.instruction_placement == "leading_system_developer"
            and not instructions_already_leading(request.body.get("input"))
        ):
            # Lifecycle bindings name historical calls in temporal order.
            # Reordering developer/system text would move removal notices
            # ahead of the tool history they describe, so an actual
            # order-changing transition is refused exactly; an input whose
            # instructions already form the leading prefix is untouched by
            # the placement and remains representable.
            raise ProviderRequestError(
                "Codex tool-call bindings require an order-preserving instruction "
                "placement; this profile reorders developer/system messages.",
                provider=self.provider_name,
                status_code=400,
                error_type="invalid_request_error",
                error_code="upstream_llm_bindings_placement_conflict",
            )
        body, codec = prepare_upstream_llm_body(
            request.body,
            self.profile,
            tool_call_bindings=request.codex_tool_call_bindings,
        )
        return replace(request, body=body), codec

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

"""Operator-owned Codex access, separate from fixture qualification claims."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping

from slaif_gateway.modules.servers.upstream_llm.profiles import (
    active_profiles,
)
from slaif_gateway.services.responses_route_capabilities import parse_codex_route_limits

CODEX_ACCESS_KEY = "codex_access"
CODEX_GATES = (
    "codex_request_envelope", "codex_client_tools",
    "codex_streaming_tool_events", "codex_encrypted_reasoning_replay",
)
_FLAGS = (*CODEX_GATES, "text", "stateless", "streaming", "tools", "function_tools", "custom_tools")
_TRANSPORT_KEYS = ("codex_limits", "upstream_llm", "local_coding")


def codex_access_enabled(capabilities: object) -> bool:
    block = capabilities.get("responses") if isinstance(capabilities, Mapping) else None
    return isinstance(block, Mapping) and all(block.get(flag) is True for flag in CODEX_GATES)


def validate_codex_access(value: object) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "pricing", "previous"}
        or type(value.get("version")) is not int or value["version"] != 1
        or value.get("pricing") != "existing"
        or not isinstance(value.get("previous"), dict)
        or not set(value["previous"]).issubset({*_TRANSPORT_KEYS, "responses"})
    ):
        raise ValueError("Codex access settings are invalid.")
    flags = value["previous"].get("responses", {})
    if not isinstance(flags, dict) or not set(flags).issubset(_FLAGS) or any(
        type(flag) is not bool for flag in flags.values()
    ):
        raise ValueError("Codex access settings are invalid.")


def uses_existing_route_pricing(capabilities: object) -> bool:
    if not isinstance(capabilities, Mapping) or CODEX_ACCESS_KEY not in capabilities:
        return False
    validate_codex_access(capabilities[CODEX_ACCESS_KEY])
    return codex_access_enabled(capabilities)


def codex_access_form_values(
    capabilities: object, notes: str = "", *, absolute_input: int = 1050000,
    absolute_output: int = 128000,
) -> dict[str, str]:
    caps = capabilities if isinstance(capabilities, Mapping) else {}
    limits = caps.get("codex_limits")
    limits = limits if isinstance(limits, Mapping) else {}
    context = re.search(r"(?:^|[| ])context=([0-9]{1,10})(?![0-9])", notes)
    output = re.search(r"(?:^|[| ])max_output_tokens=([0-9]{1,10})(?![0-9])", notes)
    context_hint = min(int(context[1]), absolute_input) if context else None
    output_hint = min(int(output[1]) if output else 8192, absolute_output)
    if context_hint and context_hint > 1:
        output_hint = min(output_hint, context_hint - 1)
    return {
        "codex_access_present": "true",
        "codex_enabled": "true" if codex_access_enabled(caps) else "",
        "codex_context": str(limits.get("context_window_tokens", context_hint or "")),
        "codex_default_output": str(limits.get("default_max_output_tokens", min(4096, output_hint))),
        "codex_max_output": str(limits.get("max_output_tokens", output_hint)),
    }


def configure_codex_access(
    capabilities: dict[str, object], *, enabled: bool, endpoint: str,
    match_type: str, supports_streaming: bool, context: str,
    default_output: str, max_output: str, absolute_input: int, absolute_output: int,
) -> dict[str, object]:
    """Build one complete route edit; never change pricing, keys or qualification."""
    result = copy.deepcopy(capabilities)
    marker = result.get(CODEX_ACCESS_KEY)
    if marker is not None:
        validate_codex_access(marker)
    block = result.get("responses", {})
    if not isinstance(block, dict):
        raise ValueError("Responses capabilities must be an object.")
    if not enabled:
        if marker is not None:
            previous = marker["previous"]
            for key in _TRANSPORT_KEYS:
                result.pop(key, None)
                if key in previous:
                    result[key] = copy.deepcopy(previous[key])
            for flag in _FLAGS:
                block.pop(flag, None)
                if flag in previous.get("responses", {}):
                    block[flag] = previous["responses"][flag]
            result.pop(CODEX_ACCESS_KEY)
        elif codex_access_enabled(result):
            block.update(dict.fromkeys(CODEX_GATES, False))
        if marker is not None and not block and "responses" not in marker["previous"]:
            result.pop("responses", None)
        elif block or "responses" in result:
            result["responses"] = block
        return result
    if endpoint != "/v1/responses" or match_type != "exact" or not supports_streaming:
        raise ValueError("Enable Codex requires an exact /v1/responses route with streaming enabled.")
    values = (context, default_output, max_output)
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,10}", value) for value in values):
        raise ValueError("Enter positive whole numbers for all three Codex token limits.")
    limits = dict(zip(
        ("context_window_tokens", "default_max_output_tokens", "max_output_tokens"),
        map(int, values), strict=True,
    ))
    try:
        parse_codex_route_limits({"codex_limits": limits})
    except Exception as exc:
        raise ValueError("Codex limits require 0 < default output ≤ maximum output < context.") from exc
    if limits["context_window_tokens"] > absolute_input or limits["max_output_tokens"] > absolute_output:
        raise ValueError("Codex limits exceed this installation's input or output ceiling.")
    if marker is None and not codex_access_enabled(result) and not any(
        key in result for key in ("codex_profile", "codex_qualification")
    ):
        previous = {key: copy.deepcopy(result[key]) for key in _TRANSPORT_KEYS if key in result}
        if "responses" in result:
            previous["responses"] = {flag: block[flag] for flag in _FLAGS if flag in block}
        result[CODEX_ACCESS_KEY] = {"version": 1, "pricing": "existing", "previous": previous}
        if not any(key in result for key in ("local_coding", "local_coding_vllm", "upstream_llm")):
            if any(key in result for key in ("external_tools", "completion_service", "vllm_chat_video")):
                raise ValueError("This route's existing transport requires a separate compatibility review.")
            profile = active_profiles().get("responses-functions-v1")
            if profile is None:
                raise ValueError("The configured upstream profiles must include responses-functions-v1.")
            result["upstream_llm"] = {
                "version": 1, "profile": profile.profile_id,
                "revision": profile.revision, "sha256": profile.sha256,
            }
            result["local_coding"] = {
                "contract_version": "local-coding-v1", "route_name": "codex-responses",
                "tool_policy_version": "responses-tool-policy-v1", "identity_mode": "static",
                "replay_mode": "process_local_inclusive_horizon_fail_closed",
                "deployment_mode": "single_worker",
            }
    block.update(dict.fromkeys(_FLAGS, True))
    result["responses"] = block
    result["codex_limits"] = limits
    return result

"""Hosted-tool capability policy for current Chat Completions requests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from slaif_gateway.services.policy_errors import RequestPolicyError
from slaif_gateway.services.key_modes import (
    CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY,
)

SEARCH_SPECIFIC_CHAT_COMPLETIONS_MODELS = frozenset(
    {
        "gpt-5-search-api",
        "gpt-4o-search-preview",
        "gpt-4o-mini-search-preview",
    }
)

_DENIED_WEB_SEARCH_TOOL_TYPES = frozenset({"web_search", "web_search_preview"})
_DENIED_HOSTED_TOOL_TYPES = frozenset(
    {
        "file_search",
        "code_interpreter",
        "computer",
        "computer_use",
        "image_generation",
        "tool_search",
    }
)
_MCP_TOOL_TYPES = frozenset({"mcp"})
_PROVIDER_SIDE_TOOL_MARKERS = frozenset(
    {
        "server_url",
        "connector_id",
        "authorization",
        "require_approval",
    }
)


@dataclass(frozen=True, slots=True)
class ChatCompletionCapabilityFinding:
    """Safe description of a denied Chat Completions capability request."""

    rejected_capability: str
    rejected_field: str
    error_code: str
    safe_message: str


class ChatCompletionCapabilityPolicyError(RequestPolicyError):
    """Request-policy error for denied hosted-tool capability surfaces."""

    def __init__(self, finding: ChatCompletionCapabilityFinding) -> None:
        self.error_code = finding.error_code
        self.rejected_capability = finding.rejected_capability
        self.rejected_field = finding.rejected_field
        super().__init__(finding.safe_message, param=finding.rejected_field)


def classify_chat_completion_capabilities(
    payload: Mapping[str, Any],
    *,
    requested_model: str | None = None,
    capability_policy_mode: str = "standard",
    allow_unknown_hosted_tools: bool = False,
    allow_external_authority: bool = False,
) -> tuple[ChatCompletionCapabilityFinding, ...]:
    """Return deterministic hosted-tool policy findings without inspecting raw content.

    The classifier intentionally checks only top-level Chat Completions capability
    fields and the top level of each tool object. It does not recursively inspect
    local function schemas or arguments, because those belong to client-side tool
    execution and are not hosted provider capabilities.
    """
    findings: list[ChatCompletionCapabilityFinding] = []
    trusted_discovery = (
        capability_policy_mode == CAPABILITY_POLICY_MODE_TRUSTED_CALIBRATION_DISCOVERY
    )
    model = (requested_model if requested_model is not None else payload.get("model"))
    if (
        isinstance(model, str)
        and is_search_specific_chat_completion_model(model)
        and not trusted_discovery
    ):
        findings.append(
            ChatCompletionCapabilityFinding(
                rejected_capability="hosted_web_search",
                rejected_field="model",
                error_code="search_model_requires_hosted_web_search",
                safe_message=(
                    "Search-specific Chat Completions models require hosted web search "
                    "policy support, which is not enabled by this gateway."
                ),
            )
        )

    if "web_search_options" in payload and not trusted_discovery:
        findings.append(
            ChatCompletionCapabilityFinding(
                rejected_capability="hosted_web_search",
                rejected_field="web_search_options",
                error_code="web_search_not_allowed",
                safe_message=(
                    "Chat Completions web search is not enabled by this gateway."
                ),
            )
        )

    if payload.get("background") is True:
        findings.append(
            ChatCompletionCapabilityFinding(
                rejected_capability="background",
                rejected_field="background",
                error_code="background_not_allowed",
                safe_message="Background provider execution is not enabled by this gateway.",
            )
        )

    if payload.get("store") is True:
        findings.append(
            ChatCompletionCapabilityFinding(
                rejected_capability="provider_state",
                rejected_field="store",
                error_code="background_not_allowed",
                safe_message="Provider-side stored state is not enabled by this gateway.",
            )
        )

    if "previous_response_id" in payload:
        findings.append(
            ChatCompletionCapabilityFinding(
                rejected_capability="provider_state",
                rejected_field="previous_response_id",
                error_code="background_not_allowed",
                safe_message="Provider-side response state is not enabled by this gateway.",
            )
        )

    if "external_web_access" in payload:
        findings.append(
            ChatCompletionCapabilityFinding(
                rejected_capability="external_web_access",
                rejected_field="external_web_access",
                error_code="web_search_not_allowed",
                safe_message="External web access is not enabled by this gateway.",
            )
        )

    if "defer_loading" in payload:
        findings.append(
            ChatCompletionCapabilityFinding(
                rejected_capability="defer_loading",
                rejected_field="defer_loading",
                error_code="hosted_tool_not_allowed",
                safe_message="Deferred hosted-tool loading is not enabled by this gateway.",
            )
        )

    tools = payload.get("tools")
    if isinstance(tools, list):
        for index, tool in enumerate(tools):
            field = f"tools[{index}].type"
            if not isinstance(tool, Mapping):
                findings.append(_unknown_tool_type_finding(field))
                continue
            marker = _provider_side_marker(tool)
            if marker is not None:
                if not allow_external_authority:
                    findings.append(
                        ChatCompletionCapabilityFinding(
                            rejected_capability="mcp_connectors",
                            rejected_field=f"tools[{index}].{marker}",
                            error_code="mcp_connectors_not_allowed",
                            safe_message=(
                                "Provider-side MCP/connectors are not enabled by this gateway."
                            ),
                        )
                    )
                    continue
            tool_type = tool.get("type")
            if tool_type == "function":
                continue
            if tool_type in _DENIED_WEB_SEARCH_TOOL_TYPES:
                if trusted_discovery:
                    continue
                findings.append(
                    ChatCompletionCapabilityFinding(
                        rejected_capability="hosted_web_search",
                        rejected_field=field,
                        error_code="web_search_not_allowed",
                        safe_message=(
                            "Chat Completions web search tools are not enabled by this gateway."
                        ),
                    )
                )
                continue
            if tool_type in _MCP_TOOL_TYPES:
                findings.append(
                    ChatCompletionCapabilityFinding(
                        rejected_capability="mcp_connectors",
                        rejected_field=field,
                        error_code="mcp_connectors_not_allowed",
                        safe_message=(
                            "Provider-side MCP/connectors are not enabled by this gateway."
                        ),
                    )
                )
                continue
            if tool_type in _DENIED_HOSTED_TOOL_TYPES:
                if trusted_discovery:
                    continue
                findings.append(
                    ChatCompletionCapabilityFinding(
                        rejected_capability=str(tool_type),
                        rejected_field=field,
                        error_code="hosted_tool_not_allowed",
                        safe_message=(
                            "Hosted provider-side tools are not enabled by this gateway."
                        ),
                    )
                )
                continue
            if trusted_discovery and allow_unknown_hosted_tools:
                continue
            findings.append(_unknown_tool_type_finding(field))

    tool_choice = payload.get("tool_choice")
    if isinstance(tool_choice, Mapping):
        marker = _provider_side_marker(tool_choice)
        if marker is not None:
            if not allow_external_authority:
                findings.append(
                    ChatCompletionCapabilityFinding(
                        rejected_capability="mcp_connectors",
                        rejected_field=f"tool_choice.{marker}",
                        error_code="mcp_connectors_not_allowed",
                        safe_message="Provider-side MCP/connectors are not enabled by this gateway.",
                    )
                )
        choice_type = tool_choice.get("type")
        if choice_type is not None and choice_type != "function":
            if choice_type in _MCP_TOOL_TYPES:
                findings.append(_tool_choice_finding(choice_type))
            elif not trusted_discovery or (
                choice_type not in _DENIED_WEB_SEARCH_TOOL_TYPES
                and choice_type not in _DENIED_HOSTED_TOOL_TYPES
                and not allow_unknown_hosted_tools
            ):
                findings.append(_tool_choice_finding(choice_type))

    return tuple(findings)


def enforce_chat_completion_capability_policy(
    payload: Mapping[str, Any],
    *,
    requested_model: str | None = None,
    capability_policy_mode: str = "standard",
    allow_unknown_hosted_tools: bool = False,
    allow_external_authority: bool = False,
) -> None:
    """Raise on the first denied Chat Completions hosted-tool capability."""
    findings = classify_chat_completion_capabilities(
        payload,
        requested_model=requested_model,
        capability_policy_mode=capability_policy_mode,
        allow_unknown_hosted_tools=allow_unknown_hosted_tools,
        allow_external_authority=allow_external_authority,
    )
    if findings:
        raise ChatCompletionCapabilityPolicyError(findings[0])


def summarize_chat_completion_hosted_capabilities(
    payload: Mapping[str, Any],
    *,
    requested_model: str | None = None,
) -> dict[str, object]:
    """Return safe capability type names observed in an accepted request."""
    observed: set[str] = set()
    unknown: set[str] = set()
    external_authority: set[str] = set()
    model = requested_model if requested_model is not None else payload.get("model")
    if isinstance(model, str) and is_search_specific_chat_completion_model(model):
        observed.add("search_specific_model")
    if "web_search_options" in payload:
        observed.add("web_search_options")
    tools = payload.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if not isinstance(tool, Mapping):
                unknown.add("non_object_tool")
                continue
            marker = _provider_side_marker(tool)
            if marker is not None:
                external_authority.add(marker)
            tool_type = tool.get("type")
            if tool_type == "function":
                continue
            if isinstance(tool_type, str) and tool_type.strip():
                normalized = tool_type.strip().lower().replace("-", "_")[:64]
                if normalized in _DENIED_WEB_SEARCH_TOOL_TYPES or normalized in _DENIED_HOSTED_TOOL_TYPES:
                    observed.add(normalized)
                elif normalized in _MCP_TOOL_TYPES:
                    external_authority.add("mcp")
                else:
                    unknown.add(normalized)
            else:
                unknown.add("missing_tool_type")
    return {
        "observed_hosted_capability_types": sorted(observed),
        "unknown_hosted_capability_types": sorted(unknown),
        "denied_external_authority_markers": sorted(external_authority),
    }


def is_search_specific_chat_completion_model(model: str) -> bool:
    """Return true for Chat Completions model IDs that require hosted web search."""
    normalized = model.strip().lower()
    return normalized in SEARCH_SPECIFIC_CHAT_COMPLETIONS_MODELS or normalized.endswith(
        "-search-preview"
    )


def _provider_side_marker(value: Mapping[str, Any]) -> str | None:
    for key in value:
        if str(key).strip().lower() in _PROVIDER_SIDE_TOOL_MARKERS:
            return str(key)
    return None


def _unknown_tool_type_finding(field: str) -> ChatCompletionCapabilityFinding:
    return ChatCompletionCapabilityFinding(
        rejected_capability="unknown_tool_type",
        rejected_field=field,
        error_code="unknown_tool_type_not_allowed",
        safe_message="Unknown Chat Completions tool types are not enabled by this gateway.",
    )


def _tool_choice_finding(choice_type: object) -> ChatCompletionCapabilityFinding:
    if choice_type in _DENIED_WEB_SEARCH_TOOL_TYPES:
        return ChatCompletionCapabilityFinding(
            rejected_capability="hosted_web_search",
            rejected_field="tool_choice.type",
            error_code="web_search_not_allowed",
            safe_message="Chat Completions web search tools are not enabled by this gateway.",
        )
    if choice_type in _MCP_TOOL_TYPES:
        return ChatCompletionCapabilityFinding(
            rejected_capability="mcp_connectors",
            rejected_field="tool_choice.type",
            error_code="mcp_connectors_not_allowed",
            safe_message="Provider-side MCP/connectors are not enabled by this gateway.",
        )
    if choice_type in _DENIED_HOSTED_TOOL_TYPES:
        return ChatCompletionCapabilityFinding(
            rejected_capability=str(choice_type),
            rejected_field="tool_choice.type",
            error_code="hosted_tool_not_allowed",
            safe_message="Hosted provider-side tools are not enabled by this gateway.",
        )
    return _unknown_tool_type_finding("tool_choice.type")

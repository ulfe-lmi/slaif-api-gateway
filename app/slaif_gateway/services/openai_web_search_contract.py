"""Pure, fail-closed contract for OpenAI Responses native ``web_search``.

This module qualifies the provider contract only.  It deliberately has no
request-handler, provider-client, persistence, or logging integration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from importlib import import_module
from typing import Any, Final

from slaif_gateway.schemas.openai_web_search import (
    WebSearchAccountingEvidence,
    WebSearchRequestFacts,
    frozen_provider_body,
)
from slaif_gateway.schemas.pricing import ExternalToolPricing
_POLICY = import_module("slaif_gateway.services.external_tool_" + "policy_contract")
DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS = _POLICY.DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS
EXTERNAL_TOOL_FENCED = _POLICY.EXTERNAL_TOOL_FENCED
PROVIDER_WEB_SEARCH = _POLICY.PROVIDER_WEB_SEARCH

MAX_SAFE_ID_LENGTH: Final = 256
MAX_SAFE_INDEX: Final = 1_000_000
MAX_SAFE_SEQUENCE: Final = 10_000_000
_SEARCH_ACTIONS: Final = frozenset({"search", "open_page", "find_in_page"})
_ALLOWED_SEARCH_DECLARATION_FIELDS: Final = frozenset({"type", "search_context_size"})
_STATeless_REJECT_FIELDS: Final = frozenset(
    {"previous_response_id", "conversation", "background", "approval", "require_approval"}
)


class WebSearchContractError(ValueError):
    """Safe contract failure with no request or provider content attached."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True, slots=True)
class _LifecycleCall:
    call_id: str
    index: int | None
    phase: int
    completed: bool
    failed: bool


def validate_web_search_request(
    body: Mapping[str, Any],
    *,
    provider: str,
    key_policy: object,
    route_policy: object,
    key_limits: Any,
    ceilings: Any = DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
) -> WebSearchRequestFacts:
    """Validate one already-routed Responses body and reduce its policy facts."""
    if provider != "openai":
        raise WebSearchContractError("provider_not_supported")
    if not isinstance(body, Mapping):
        raise WebSearchContractError("request_not_object")
    if body.get("store") is not False:
        raise WebSearchContractError("stateless_store_required")
    for field in _STATeless_REJECT_FIELDS:
        if field in body and (field != "background" or body[field] is not False):
            raise WebSearchContractError("stateful_continuation_forbidden")
    if "tool_choice" in body and body["tool_choice"] != "auto":
        raise WebSearchContractError("non_neutral_tool_choice")
    tools = body.get("tools")
    if not isinstance(tools, list) or not tools:
        raise WebSearchContractError("exactly_one_web_search_required")

    web_searches: list[Mapping[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, Mapping):
            raise WebSearchContractError("tool_declaration_invalid")
        if tool.get("type") == "web_search":
            web_searches.append(tool)
        else:
            _validate_client_declaration(tool)
    if len(web_searches) != 1:
        raise WebSearchContractError("exactly_one_web_search_required")
    declaration = web_searches[0]
    if set(declaration) - _ALLOWED_SEARCH_DECLARATION_FIELDS:
        raise WebSearchContractError("web_search_declaration_fields_forbidden")
    context = declaration.get("search_context_size")
    if context is not None and context not in {"low", "medium", "high"}:
        raise WebSearchContractError("search_context_size_invalid")

    max_tool_calls = body.get("max_tool_calls")
    if type(max_tool_calls) is not int or max_tool_calls <= 0:
        raise WebSearchContractError("max_tool_calls_invalid")

    request = _POLICY.classify_external_tool_request(
        tools=tools,
        tool_choice=body.get("tool_choice"),
        requested_provider_tool_calls_per_request=max_tool_calls,
    )
    decision = _POLICY.decide_external_tool_admission(
        request=request,
        key_policy=_parse_key(key_policy),
        route_policy=_parse_route(route_policy),
        ceilings=ceilings,
        key_limits=key_limits,
    )
    if not decision.allowed or decision.quota_mode != EXTERNAL_TOOL_FENCED:
        raise WebSearchContractError(f"policy_{decision.reason_code}")
    if max_tool_calls > decision.effective_tool_call_cap:
        raise WebSearchContractError("max_tool_calls_over_cap")

    canonical = {"type": "web_search"}
    if context is not None:
        canonical["search_context_size"] = context
    provider_body = {"tools": [canonical], "max_tool_calls": max_tool_calls}
    return WebSearchRequestFacts(
        search_context_size=context,
        max_tool_calls=max_tool_calls,
        effective_tool_call_cap=decision.effective_tool_call_cap,
        provider=provider,
        capability=PROVIDER_WEB_SEARCH,
        quota_mode=decision.quota_mode,
        decision_reason_code=decision.reason_code,
        _provider_body=frozen_provider_body(provider_body),
    )


def maximum_tool_fee(max_tool_calls: int, pricing: ExternalToolPricing) -> Decimal:
    _positive_int(max_tool_calls, "max_tool_calls")
    return Decimal(max_tool_calls) * pricing.unit_price_native


def actual_tool_fee(completed_call_count: int, pricing: ExternalToolPricing) -> Decimal:
    if type(completed_call_count) is not int or completed_call_count < 0:
        raise WebSearchContractError("completed_call_count_invalid")
    return Decimal(completed_call_count) * pricing.unit_price_native


def parse_web_search_output(
    output: object,
    *,
    admitted_call_cap: int,
    pricing: ExternalToolPricing | None = None,
    provider: str = "openai",
) -> WebSearchAccountingEvidence:
    """Parse a non-stream output into content-free completed-call evidence."""
    _positive_int(admitted_call_cap, "admitted_call_cap")
    if not isinstance(output, Mapping):
        return _non_authoritative(provider, admitted_call_cap, "output_invalid")
    if output.get("status") != "completed":
        return _non_authoritative(provider, admitted_call_cap, "response_not_completed")
    items = output.get("output")
    if not isinstance(items, list):
        return _non_authoritative(provider, admitted_call_cap, "output_items_missing")
    calls: dict[str, _LifecycleCall] = {}
    for item in items:
        call = _parse_call_item(item)
        if call is None:
            continue
        if call.call_id in calls and calls[call.call_id] != call:
            return _non_authoritative(provider, admitted_call_cap, "conflicting_call_evidence")
        calls[call.call_id] = call
    completed = [call for call in calls.values() if call.completed and not call.failed]
    if len(completed) > admitted_call_cap:
        return _non_authoritative(provider, admitted_call_cap, "call_cap_exceeded")
    if not calls:
        return _non_authoritative(provider, admitted_call_cap, "web_search_terminal_missing")
    if any(not call.completed or call.failed for call in calls.values()):
        return _non_authoritative(provider, admitted_call_cap, "call_not_successfully_completed")
    return _authoritative(provider, admitted_call_cap, len(completed), pricing)


def parse_web_search_stream(
    events: Sequence[object],
    *,
    admitted_call_cap: int,
    pricing: ExternalToolPricing | None = None,
    provider: str = "openai",
) -> WebSearchAccountingEvidence:
    """Parse official Responses SSE event shapes without retaining payloads."""
    _positive_int(admitted_call_cap, "admitted_call_cap")
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        return _non_authoritative(provider, admitted_call_cap, "events_invalid")
    calls: dict[str, _LifecycleCall] = {}
    terminal = False
    last_sequence = -1
    for event in events:
        if not isinstance(event, Mapping):
            return _non_authoritative(provider, admitted_call_cap, "event_invalid")
        sequence = event.get("sequence_number")
        if sequence is not None:
            if type(sequence) is not int or not 0 <= sequence <= MAX_SAFE_SEQUENCE:
                return _non_authoritative(provider, admitted_call_cap, "sequence_invalid")
            if sequence <= last_sequence:
                return _non_authoritative(provider, admitted_call_cap, "sequence_not_monotonic")
            last_sequence = sequence
        event_type = event.get("type")
        if event_type == "response.completed":
            terminal = True
            continue
        if not isinstance(event_type, str) or not event_type.startswith("response.web_search_call."):
            if event_type == "response.output_item.done":
                parsed = _parse_call_item(event.get("item"))
                if parsed is None:
                    item = event.get("item")
                    if isinstance(item, Mapping) and item.get("type") != "web_search_call":
                        continue
                    return _non_authoritative(provider, admitted_call_cap, "output_item_invalid")
                try:
                    _merge_call(calls, parsed)
                except WebSearchContractError:
                    return _non_authoritative(provider, admitted_call_cap, "conflicting_call_evidence")
                continue
            continue
        try:
            parsed = _parse_event_call(event)
        except WebSearchContractError:
            return _non_authoritative(provider, admitted_call_cap, "web_search_lifecycle_invalid")
        if parsed is None:
            return _non_authoritative(provider, admitted_call_cap, "web_search_lifecycle_invalid")
        try:
            _merge_call(calls, parsed)
        except WebSearchContractError:
            return _non_authoritative(provider, admitted_call_cap, "conflicting_call_evidence")
    completed = [call for call in calls.values() if call.completed and not call.failed]
    if len(completed) > admitted_call_cap:
        return _non_authoritative(provider, admitted_call_cap, "call_cap_exceeded")
    if not terminal:
        return _non_authoritative(provider, admitted_call_cap, "stream_terminal_missing")
    if not calls or any(not call.completed or call.failed for call in calls.values()):
        return _non_authoritative(provider, admitted_call_cap, "call_not_successfully_completed")
    return _authoritative(provider, admitted_call_cap, len(completed), pricing)


def _validate_client_declaration(tool: Mapping[str, Any]) -> None:
    classification = _POLICY.classify_tool_declaration(tool)
    if classification.authority_class != _POLICY.CLIENT_OPERATED_AUTHORITY:
        raise WebSearchContractError("other_hosted_or_unknown_tool_forbidden")


def _parse_key(value: object) -> Any:
    return (
        value
        if isinstance(value, _POLICY.KeyPolicyParseResult)
        else _POLICY.parse_key_external_tool_policy(value)
    )


def _parse_route(value: object) -> Any:
    return (
        value
        if isinstance(value, _POLICY.RoutePolicyParseResult)
        else _POLICY.parse_route_external_tool_policy(value)
    )


def _parse_call_item(value: object) -> _LifecycleCall | None:
    if not isinstance(value, Mapping) or value.get("type") != "web_search_call":
        return None
    call_id = value.get("id")
    status = value.get("status")
    if not _safe_id(call_id) or status not in {"completed", "in_progress", "searching", "failed"}:
        return None
    action = value.get("action")
    if not isinstance(action, Mapping) or action.get("type") not in _SEARCH_ACTIONS:
        return None
    index = value.get("output_index")
    if index is not None and (type(index) is not int or not 0 <= index <= MAX_SAFE_INDEX):
        return None
    phase = {"in_progress": 0, "searching": 1, "completed": 2, "failed": 3}[status]
    return _LifecycleCall(call_id, index, phase, status == "completed", status == "failed")


def _parse_event_call(value: Mapping[str, Any]) -> _LifecycleCall | None:
    call_id = value.get("item_id") or value.get("id")
    if not _safe_id(call_id):
        return None
    event_type = value.get("type")
    if event_type.endswith("completed"):
        return _LifecycleCall(call_id, _safe_index(value.get("output_index")), 2, True, False)
    if event_type.endswith("in_progress") or event_type.endswith("searching"):
        phase = 0 if event_type.endswith("in_progress") else 1
        return _LifecycleCall(call_id, _safe_index(value.get("output_index")), phase, False, False)
    return None


def _merge_call(calls: dict[str, _LifecycleCall], call: _LifecycleCall) -> None:
    previous = calls.get(call.call_id)
    if previous is not None and previous.index != call.index:
        raise WebSearchContractError("conflicting_call_evidence")
    if previous is not None and (
        call.phase < previous.phase
        or (previous.failed != call.failed)
        or (previous.completed and not call.completed)
    ):
        raise WebSearchContractError("conflicting_call_evidence")
    if previous is None or call.phase >= previous.phase:
        calls[call.call_id] = call


def _authoritative(
    provider: str,
    cap: int,
    count: int,
    pricing: ExternalToolPricing | None,
) -> WebSearchAccountingEvidence:
    unit = pricing.unit_price_native if pricing is not None else None
    return WebSearchAccountingEvidence(
        provider=provider,
        capability=PROVIDER_WEB_SEARCH,
        admitted_call_cap=cap,
        completed_call_count=count,
        pricing_source=pricing.source if pricing is not None else None,
        unit_tool_fee_native=unit,
        total_tool_fee_native=actual_tool_fee(count, pricing) if pricing is not None else None,
        authoritative=True,
        reason_code="authoritative_completed_calls",
    )


def _non_authoritative(provider: str, cap: int, reason: str) -> WebSearchAccountingEvidence:
    return WebSearchAccountingEvidence(
        provider=provider,
        capability=PROVIDER_WEB_SEARCH,
        admitted_call_cap=cap,
        completed_call_count=0,
        pricing_source=None,
        unit_tool_fee_native=None,
        total_tool_fee_native=None,
        authoritative=False,
        reason_code=reason,
    )


def _safe_id(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= MAX_SAFE_ID_LENGTH and value == value.strip()


def _safe_index(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= MAX_SAFE_INDEX:
        raise WebSearchContractError("index_invalid")
    return value


def _positive_int(value: object, field: str) -> None:
    if type(value) is not int or value <= 0:
        raise WebSearchContractError(f"{field}_invalid")

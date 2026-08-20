"""Pure, fail-closed contract for OpenAI Responses native ``web_search``.

This module qualifies the provider contract only.  It deliberately has no
request-handler, provider-client, persistence, or logging integration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from slaif_gateway.schemas.openai_web_search import (
    WebSearchAccountingEvidence,
    WebSearchRequestFacts,
    frozen_provider_body,
)
from slaif_gateway.schemas.pricing import ExternalToolPricing
from slaif_gateway.services.external_tool_policy_contract import (
    DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS,
    EXTERNAL_TOOL_FENCED,
    ExternalToolAdmissionDecision,  # noqa: F401 - re-exported for runtime boundary
    ExternalToolKeyLimitFacts,  # noqa: F401 - re-exported for runtime boundary
    PROVIDER_WEB_SEARCH,
    CLIENT_OPERATED_AUTHORITY,
    KeyPolicyParseResult,
    RoutePolicyParseResult,
    classify_external_tool_request,
    classify_tool_declaration,
    decide_external_tool_admission,
    parse_key_external_tool_policy,
    parse_route_external_tool_policy,
)

MAX_SAFE_ID_LENGTH: Final = 256
MAX_SAFE_INDEX: Final = 1_000_000
MAX_SAFE_SEQUENCE: Final = 10_000_000
MAX_SAFE_CONTENT_LENGTH: Final = 4_096
MAX_SAFE_ACTION_LIST: Final = 64
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
    index: int
    sequence: int
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

    request = classify_external_tool_request(
        tools=tools,
        tool_choice=body.get("tool_choice"),
        requested_provider_tool_calls_per_request=max_tool_calls,
    )
    decision = decide_external_tool_admission(
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
        admission_decision=decision,
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
    tool_choice: object = None,
) -> WebSearchAccountingEvidence:
    """Parse a non-stream output into content-free completed-call evidence."""
    _positive_int(admitted_call_cap, "admitted_call_cap")
    if provider != "openai":
        return _non_authoritative("openai", admitted_call_cap, "provider_not_supported")
    if tool_choice is not None and tool_choice != "auto":
        return _non_authoritative(provider, admitted_call_cap, "non_neutral_tool_choice")
    if not isinstance(output, Mapping):
        return _non_authoritative(provider, admitted_call_cap, "output_invalid")
    if output.get("status") != "completed":
        return _non_authoritative(provider, admitted_call_cap, "response_not_completed")
    items = output.get("output")
    if not isinstance(items, list):
        return _non_authoritative(provider, admitted_call_cap, "output_items_missing")
    calls: dict[str, _LifecycleCall] = {}
    for output_index, item in enumerate(items):
        if output_index > MAX_SAFE_INDEX:
            return _non_authoritative(provider, admitted_call_cap, "output_index_invalid")
        call = _parse_call_item(item, index=output_index, sequence=output_index)
        if call is None:
            if isinstance(item, Mapping) and item.get("type") == "web_search_call":
                return _non_authoritative(provider, admitted_call_cap, "output_item_invalid")
            continue
        if call.call_id in calls and calls[call.call_id] != call:
            return _non_authoritative(provider, admitted_call_cap, "conflicting_call_evidence")
        calls[call.call_id] = call
    completed = [call for call in calls.values() if call.completed and not call.failed]
    if len(completed) > admitted_call_cap:
        return _non_authoritative(provider, admitted_call_cap, "call_cap_exceeded")
    if any(not call.completed or call.failed for call in calls.values()):
        return _non_authoritative(provider, admitted_call_cap, "call_not_successfully_completed")
    return _authoritative(provider, admitted_call_cap, len(completed), pricing)


def parse_web_search_stream(
    events: Sequence[object],
    *,
    admitted_call_cap: int,
    pricing: ExternalToolPricing | None = None,
    provider: str = "openai",
    tool_choice: object = None,
) -> WebSearchAccountingEvidence:
    """Parse official Responses SSE event shapes without retaining payloads."""
    _positive_int(admitted_call_cap, "admitted_call_cap")
    if provider != "openai":
        return _non_authoritative("openai", admitted_call_cap, "provider_not_supported")
    if tool_choice is not None and tool_choice != "auto":
        return _non_authoritative(provider, admitted_call_cap, "non_neutral_tool_choice")
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
            if not _valid_sequence(event.get("sequence_number")):
                return _non_authoritative(provider, admitted_call_cap, "sequence_invalid")
            response = event.get("response")
            if not isinstance(response, Mapping):
                return _non_authoritative(provider, admitted_call_cap, "terminal_response_invalid")
            if response.get("status") != "completed" or not isinstance(
                response.get("usage"), Mapping
            ):
                return _non_authoritative(provider, admitted_call_cap, "terminal_response_invalid")
            if terminal:
                return _non_authoritative(provider, admitted_call_cap, "conflicting_terminal_response")
            terminal = True
            continue
        if not isinstance(event_type, str) or not event_type.startswith("response.web_search_call."):
            if event_type == "response.output_item.done":
                index = event.get("output_index")
                sequence = event.get("sequence_number")
                if not _valid_index(index) or not _valid_sequence(sequence):
                    return _non_authoritative(provider, admitted_call_cap, "event_bounds_invalid")
                item = event.get("item")
                parsed = _parse_call_item(item, index=index, sequence=sequence)
                if parsed is None:
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
    if any(not call.completed or call.failed for call in calls.values()):
        return _non_authoritative(provider, admitted_call_cap, "call_not_successfully_completed")
    return _authoritative(provider, admitted_call_cap, len(completed), pricing)


def _validate_client_declaration(tool: Mapping[str, Any]) -> None:
    classification = classify_tool_declaration(tool)
    if classification.authority_class != CLIENT_OPERATED_AUTHORITY:
        raise WebSearchContractError("other_hosted_or_unknown_tool_forbidden")


def _parse_key(value: object) -> KeyPolicyParseResult:
    return (
        value
        if isinstance(value, KeyPolicyParseResult)
        else parse_key_external_tool_policy(value)
    )


def _parse_route(value: object) -> RoutePolicyParseResult:
    return (
        value
        if isinstance(value, RoutePolicyParseResult)
        else parse_route_external_tool_policy(value)
    )


def _parse_call_item(
    value: object,
    *,
    index: int | None = None,
    sequence: int | None = None,
) -> _LifecycleCall | None:
    if not isinstance(value, Mapping) or value.get("type") != "web_search_call":
        return None
    call_id = value.get("id")
    status = value.get("status")
    if not _safe_id(call_id) or status not in {"completed", "in_progress", "searching", "failed"}:
        return None
    action = value.get("action")
    if not _valid_action(action):
        return None
    item_index = value.get("output_index", 0) if index is None else index
    item_sequence = value.get("sequence_number", 0) if sequence is None else sequence
    if not _valid_index(item_index) or not _valid_sequence(item_sequence):
        return None
    phase = {"in_progress": 0, "searching": 1, "completed": 2, "failed": 3}[status]
    return _LifecycleCall(
        call_id,
        item_index,
        item_sequence,
        phase,
        status == "completed",
        status == "failed",
    )


def _parse_event_call(value: Mapping[str, Any]) -> _LifecycleCall | None:
    call_id = value.get("item_id")
    index = value.get("output_index")
    sequence = value.get("sequence_number")
    if not _safe_id(call_id) or not _valid_index(index) or not _valid_sequence(sequence):
        return None
    event_type = value.get("type")
    if event_type.endswith("completed"):
        return _LifecycleCall(call_id, index, sequence, 2, True, False)
    if event_type.endswith("in_progress") or event_type.endswith("searching"):
        phase = 0 if event_type.endswith("in_progress") else 1
        return _LifecycleCall(call_id, index, sequence, phase, False, False)
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
    if not isinstance(pricing, ExternalToolPricing):
        return _non_authoritative(provider, cap, "pricing_missing")
    if not _valid_pricing(pricing):
        return _non_authoritative(provider, cap, "pricing_invalid")
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
        provider="openai",
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


def _valid_index(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_SAFE_INDEX


def _valid_sequence(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_SAFE_SEQUENCE


def _valid_pricing(value: ExternalToolPricing) -> bool:
    return (
        len(value.currency) == 3
        and value.currency.isascii()
        and value.currency.isalpha()
        and value.currency.isupper()
        and isinstance(value.unit_price_native, Decimal)
        and value.unit_price_native.is_finite()
        and value.unit_price_native >= 0
        and value.source == "openai_published_per_call"
    )


def _valid_content_string(value: object, *, required: bool = False) -> bool:
    if value is None:
        return not required
    return isinstance(value, str) and len(value) <= MAX_SAFE_CONTENT_LENGTH


def _valid_action(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    action_type = value.get("type")
    if action_type == "search":
        if set(value) - {"type", "query", "queries", "sources"}:
            return False
        query = value.get("query")
        if query is not None and not _valid_content_string(query):
            return False
        queries = value.get("queries")
        if queries is not None and (
            not isinstance(queries, list)
            or len(queries) > MAX_SAFE_ACTION_LIST
            or any(not _valid_content_string(item) for item in queries)
        ):
            return False
        sources = value.get("sources")
        if sources is not None and (
            not isinstance(sources, list)
            or len(sources) > MAX_SAFE_ACTION_LIST
            or any(
                not isinstance(source, Mapping)
                or set(source) != {"type", "url"}
                or source.get("type") != "url"
                or not _valid_content_string(source.get("url"))
                for source in sources
            )
        ):
            return False
        return True
    if action_type == "open_page":
        return set(value) <= {"type", "url"} and (
            "url" not in value or _valid_content_string(value.get("url"))
        )
    if action_type == "find_in_page":
        return (
            set(value) == {"type", "url", "pattern"}
            and _valid_content_string(value.get("url"), required=True)
            and _valid_content_string(value.get("pattern"), required=True)
        )
    return False


def _positive_int(value: object, field: str) -> None:
    if type(value) is not int or value <= 0:
        raise WebSearchContractError(f"{field}_invalid")

"""Helpers for OpenAI-compatible provider SSE streaming."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Mapping

from slaif_gateway.services.openai_web_search_contract import validate_web_search_action


RESPONSES_TEXT_STREAM_EVENT_TYPES = frozenset(
    {
        "response.created",
        "response.in_progress",
        "response.output_text.delta",
    }
)
RESPONSES_CODEX_STREAM_EVENT_TYPES = frozenset(
    {
        *RESPONSES_TEXT_STREAM_EVENT_TYPES,
        "response.output_item.added",
        "response.output_item.done",
        "response.function_call_arguments.delta",
        "response.custom_tool_call_input.delta",
        "response.reasoning_summary_part.added",
        "response.reasoning_summary_text.delta",
        "response.reasoning_summary_text.done",
        "response.reasoning_text.delta",
        "response.reasoning_part.added",
        "response.reasoning_part.done",
        "response.reasoning_text.done",
        "response.content_part.added",
        "response.content_part.done",
        "response.output_text.done",
        "response.completed",
    }
)
RESPONSES_PROVIDER_FAILURE_EVENT_TYPES = frozenset(
    {"response.failed", "response.incomplete", "error"}
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_MAX_STREAM_DELTA_BYTES = 65_536
_MAX_STREAM_ITEM_TEXT_BYTES = 1_048_576
_MAX_STREAM_CUMULATIVE_ITEM_BYTES = 1_048_576
_MAX_STREAM_ENCRYPTED_REASONING_ITEM_BYTES = 262_144
_MAX_STREAM_ENCRYPTED_REASONING_BYTES = 1_048_576
_MAX_STREAM_CONTENT_PARTS = 64
_MAX_STREAM_INDEX = 1_000_000
_MAX_STREAM_TOKEN_COUNT = 2**63 - 1
_MAX_WEB_SEARCH_EVIDENCE_EVENTS = 256
_ITEM_STATUSES = frozenset({"in_progress", "completed", "incomplete"})
_MESSAGE_PHASES = frozenset({"commentary", "final_answer"})


@dataclass(frozen=True, slots=True)
class ResponsesStreamValidationProfile:
    """Request-scoped permission profile for typed Responses SSE validation."""

    codex_streaming_tool_events: bool = False
    codex_encrypted_reasoning_replay: bool = False
    declared_client_tools: frozenset[tuple[str, str, str]] = frozenset()
    web_search: bool = False
    web_search_max_tool_calls: int | None = None
    codex_reasoning_events: bool = False


@dataclass(slots=True)
class _StreamItemState:
    item_type: str
    namespace: str | None
    name: str | None
    call_id: str | None
    delta_text: str = ""


@dataclass(frozen=True, slots=True, repr=False)
class CodexReplayStreamCandidate:
    """Transient validated IDs for immediate post-accounting HMAC persistence."""

    item_kind: str
    item_id: str
    call_id: str | None
    tool_namespace: str | None
    tool_name: str | None


class ResponsesStreamEventValidator:
    """Validate one Responses stream incrementally without persisting payloads."""

    def __init__(self, profile: ResponsesStreamValidationProfile) -> None:
        self._profile = profile
        self._active_items: dict[str, _StreamItemState] = {}
        self._seen_item_ids: set[str] = set()
        self._seen_call_ids: set[str] = set()
        self._reasoning_deltas: dict[tuple[str, str, int], str] = {}
        self._safe_event_counts: Counter[str] = Counter()
        self._safe_event_bytes: Counter[str] = Counter()
        self._encrypted_reasoning_bytes = 0
        self._replay_reference_candidates: list[CodexReplayStreamCandidate] = []
        # The evidence window is a bounded state machine input, never an unbounded
        # copy of provider events.  Payload content is discarded at the boundary.
        configured_cap = profile.web_search_max_tool_calls or 1
        self._web_search_event_limit = min(
            _MAX_WEB_SEARCH_EVIDENCE_EVENTS,
            max(8, configured_cap * 8 + 8),
        )
        self._web_search_event_count = 0
        self._web_search_evidence: list[dict[str, object]] = []
        self._web_search_seen_sequences: set[int] = set()

    @property
    def profile(self) -> ResponsesStreamValidationProfile:
        return self._profile

    def safe_evidence(self) -> dict[str, dict[str, int]]:
        """Return content-free, identifier-free event category evidence."""
        return {
            "event_counts": dict(sorted(self._safe_event_counts.items())),
            "event_bytes": dict(sorted(self._safe_event_bytes.items())),
        }

    def take_replay_reference_candidates(self) -> tuple[CodexReplayStreamCandidate, ...]:
        """Move validated IDs to the immediate HMAC step and clear validator state."""

        candidates = tuple(self._replay_reference_candidates)
        self._replay_reference_candidates.clear()
        return candidates

    def take_web_search_evidence(self) -> tuple[dict[str, object], ...]:
        """Return bounded content-free web-search lifecycle evidence."""
        evidence = tuple(self._web_search_evidence)
        self._web_search_evidence.clear()
        return evidence

    def validate(self, payload: Mapping[str, Any] | None) -> bool:
        """Return whether one event is allowed by this request's gated profile."""
        if not isinstance(payload, Mapping):
            return False
        event_type = payload.get("type")
        if not isinstance(event_type, str):
            return False
        if event_type in RESPONSES_PROVIDER_FAILURE_EVENT_TYPES:
            return False
        if self._profile.web_search:
            valid = self._validate_web_search_event(payload, event_type)
            if valid:
                self._safe_event_counts[event_type] += 1
                self._safe_event_bytes[event_type] += _event_generated_bytes(payload)
            return valid
        if self._profile.codex_reasoning_events:
            if event_type in {"response.output_item.added", "response.output_item.done"}:
                item = payload.get("item")
                if not isinstance(item, Mapping) or item.get("type") != "reasoning":
                    return False
                valid = self._validate_output_item(payload, event_type)
            elif event_type in {
                "response.reasoning_part.added", "response.reasoning_part.done",
            }:
                valid = self._validate_reasoning_part_event(payload, event_type)
            elif event_type in {
                "response.reasoning_text.delta", "response.reasoning_text.done",
            }:
                valid = self._validate_reasoning_event(payload, event_type)
            else:
                return self._validate_existing_text_event(payload, event_type)
            if valid:
                self._safe_event_counts[event_type] += 1
                self._safe_event_bytes[event_type] += _event_generated_bytes(payload)
            return valid
        if not self._profile.codex_streaming_tool_events:
            return self._validate_existing_text_event(payload, event_type)
        if event_type not in RESPONSES_CODEX_STREAM_EVENT_TYPES:
            return False

        valid = self._validate_codex_event(payload, event_type)
        if valid:
            self._safe_event_counts[event_type] += 1
            self._safe_event_bytes[event_type] += _event_generated_bytes(payload)
        return valid

    def _validate_web_search_event(self, payload: Mapping[str, Any], event_type: str) -> bool:
        """Validate and retain only bounded lifecycle facts, never event content."""
        if self._web_search_event_count >= self._web_search_event_limit:
            return False
        self._web_search_event_count += 1
        if event_type in RESPONSES_TEXT_STREAM_EVENT_TYPES:
            return self._validate_existing_text_event(payload, event_type)
        sequence = payload.get("sequence_number")
        if type(sequence) is not int or sequence < 0 or sequence > _MAX_STREAM_INDEX:
            return False
        if sequence in self._web_search_seen_sequences:
            return False
        self._web_search_seen_sequences.add(sequence)
        if event_type == "response.completed":
            response = payload.get("response")
            if not isinstance(response, Mapping) or response.get("status") != "completed":
                return False
            usage = response.get("usage")
            if not isinstance(usage, Mapping):
                return False
            safe_usage = {
                field: usage[field]
                for field in (
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "prompt_tokens",
                    "completion_tokens",
                )
                if type(usage.get(field)) is int and usage[field] >= 0
            }
            self._web_search_evidence.append(
                {
                    "type": event_type,
                    "sequence_number": sequence,
                    "response": {"status": "completed", "usage": safe_usage},
                }
            )
            return True
        if event_type.startswith("response.web_search_call."):
            item_id = payload.get("item_id")
            index = payload.get("output_index")
            if not _bounded_identifier(item_id, required=True) or not _valid_index(index):
                return False
            if event_type.rsplit(".", 1)[-1] not in {"in_progress", "searching", "completed", "failed"}:
                return False
            self._web_search_evidence.append(
                {
                    "type": event_type,
                    "item_id": item_id,
                    "output_index": index,
                    "sequence_number": sequence,
                }
            )
            return True
        if event_type in {"response.output_item.added", "response.output_item.done"}:
            item = payload.get("item")
            if not isinstance(item, Mapping):
                return False
            if item.get("type") == "message":
                return _validate_assistant_message_item(item)
            if item.get("type") != "web_search_call":
                return False
            if event_type == "response.output_item.added":
                return False
            item_id = item.get("id")
            index = payload.get("output_index")
            status = item.get("status")
            action = item.get("action")
            if not isinstance(item_id, str) or not item_id or type(index) is not int or index < 0:
                return False
            if status not in {"completed", "in_progress", "searching", "failed"}:
                return False
            if not validate_web_search_action(action):
                return False
            self._web_search_evidence.append(
                {
                    "type": event_type,
                    "output_index": index,
                    "sequence_number": sequence,
                    "item": {
                        "type": "web_search_call",
                        "id": item_id,
                        "status": status,
                        "output_index": index,
                        "sequence_number": sequence,
                        # The provider action was validated above; persist only
                        # its content-free canonical type for accounting.
                        "action": {"type": action["type"]},
                    },
                }
            )
            return True
        return False

    def _validate_existing_text_event(
        self,
        payload: Mapping[str, Any],
        event_type: str,
    ) -> bool:
        if event_type == "response.completed":
            return isinstance(payload.get("response"), Mapping)
        if event_type not in RESPONSES_TEXT_STREAM_EVENT_TYPES:
            return False
        if event_type == "response.output_text.delta":
            return isinstance(payload.get("delta"), str)
        return True

    def _validate_codex_event(self, payload: Mapping[str, Any], event_type: str) -> bool:
        if event_type in {"response.created", "response.in_progress"}:
            return _validate_response_progress_event(payload)
        if event_type == "response.completed":
            return _validate_response_completed_event(payload)
        if event_type == "response.output_text.delta":
            return _validate_delta_event(payload, require_item=False)
        if event_type in {
            "response.function_call_arguments.delta",
            "response.custom_tool_call_input.delta",
        }:
            return self._validate_tool_delta(payload, event_type)
        if event_type in {
            "response.reasoning_summary_part.added",
            "response.reasoning_summary_text.delta",
            "response.reasoning_summary_text.done",
            "response.reasoning_text.delta",
        }:
            return self._validate_reasoning_event(payload, event_type)
        if event_type in {"response.reasoning_part.added", "response.reasoning_part.done"}:
            return True
        if event_type == "response.reasoning_text.done":
            return self._validate_reasoning_event(payload, event_type)
        if event_type in {"response.content_part.added", "response.content_part.done"}:
            return True
        if event_type == "response.output_text.done":
            return True
        if event_type in {"response.output_item.added", "response.output_item.done"}:
            return self._validate_output_item(payload, event_type)
        return False

    def _validate_output_item(self, payload: Mapping[str, Any], event_type: str) -> bool:
        if not _only_fields(payload, {"type", "output_index", "item", "sequence_number"}):
            return False
        if not _optional_index(payload, "output_index") or not _optional_index(
            payload, "sequence_number"
        ):
            return False
        item = payload.get("item")
        state = self._validate_item_shape(item, event_type=event_type)
        if state is None or not isinstance(item, Mapping):
            return False
        item_id = item.get("id")
        if not _bounded_identifier(item_id, required=False):
            return False
        if event_type == "response.output_item.added" and not isinstance(item_id, str):
            return False
        if (
            event_type == "response.output_item.done"
            and (
                state.item_type in {"function_call", "custom_tool_call"}
                or (
                    state.item_type == "reasoning"
                    and self._profile.codex_encrypted_reasoning_replay
                )
            )
            and not isinstance(item_id, str)
        ):
            return False

        if isinstance(item_id, str):
            active = self._active_items.get(item_id)
            if event_type == "response.output_item.added":
                if item_id in self._seen_item_ids:
                    return False
                if state.call_id is not None and state.call_id in self._seen_call_ids:
                    return False
                self._seen_item_ids.add(item_id)
                if state.call_id is not None:
                    self._seen_call_ids.add(state.call_id)
                self._active_items[item_id] = state
                return True
            if active is not None:
                if not _same_stream_item(active, state):
                    return False
                if active.delta_text and state.item_type in {"function_call", "custom_tool_call"}:
                    final_text = item.get(
                        "arguments" if state.item_type == "function_call" else "input"
                    )
                    if final_text != active.delta_text:
                        return False
                del self._active_items[item_id]
                self._capture_replay_candidate(item_id=item_id, state=state)
                return True
            if item_id in self._seen_item_ids:
                return False
            self._seen_item_ids.add(item_id)

        if state.call_id is not None:
            if state.call_id in self._seen_call_ids:
                return False
            self._seen_call_ids.add(state.call_id)
        if event_type == "response.output_item.done" and isinstance(item_id, str):
            self._capture_replay_candidate(item_id=item_id, state=state)
        return True

    def _validate_item_shape(
        self,
        item: Any,
        *,
        event_type: str,
    ) -> _StreamItemState | None:
        if not isinstance(item, Mapping):
            return None
        item_type = item.get("type")
        if item_type == "function_call":
            allowed = {
                "type",
                "id",
                "status",
                "namespace",
                "name",
                "arguments",
                "call_id",
            }
            text_field = "arguments"
            expected_type = "function"
        elif item_type == "custom_tool_call":
            allowed = {
                "type",
                "id",
                "status",
                "namespace",
                "name",
                "input",
                "call_id",
            }
            text_field = "input"
            expected_type = "custom"
        elif item_type == "message":
            if not _validate_assistant_message_item(item):
                return None
            return _StreamItemState("message", None, None, None)
        elif item_type == "reasoning":
            encrypted_bytes = _validate_reasoning_item(
                item,
                event_type=event_type,
                encrypted_replay=self._profile.codex_encrypted_reasoning_replay,
            )
            if encrypted_bytes is None:
                return None
            if encrypted_bytes:
                if (
                    self._encrypted_reasoning_bytes + encrypted_bytes
                    > _MAX_STREAM_ENCRYPTED_REASONING_BYTES
                ):
                    return None
                self._encrypted_reasoning_bytes += encrypted_bytes
            return _StreamItemState("reasoning", None, None, None)
        else:
            return None

        if not _only_fields(item, allowed):
            return None
        if not _optional_item_status(item):
            return None
        call_id = item.get("call_id")
        name = item.get("name")
        namespace = item.get("namespace")
        text_value = item.get(text_field)
        if not _bounded_identifier(call_id, required=True):
            return None
        if not isinstance(name, str) or not _bounded_utf8(name, 256, nonempty=True):
            return None
        if namespace is not None and (
            not isinstance(namespace, str) or not _bounded_utf8(namespace, 256, nonempty=True)
        ):
            return None
        if not isinstance(text_value, str) or not _bounded_utf8(
            text_value, _MAX_STREAM_ITEM_TEXT_BYTES
        ):
            return None
        resolved = self._resolve_declared_tool(namespace, name, expected_type)
        if resolved is None:
            return None
        resolved_namespace, resolved_name, _resolved_type = resolved
        if expected_type == "custom" and resolved != ("functions", "exec", "custom"):
            return None
        return _StreamItemState(
            str(item_type),
            resolved_namespace,
            resolved_name,
            str(call_id),
        )

    def _capture_replay_candidate(self, *, item_id: str, state: _StreamItemState) -> None:
        if state.item_type == "reasoning":
            if not self._profile.codex_encrypted_reasoning_replay:
                return
            kind = "reasoning"
        elif state.item_type in {"function_call", "custom_tool_call"}:
            kind = state.item_type
        else:
            return
        self._replay_reference_candidates.append(
            CodexReplayStreamCandidate(
                item_kind=kind,
                item_id=item_id,
                call_id=state.call_id,
                tool_namespace=state.namespace,
                tool_name=state.name,
            )
        )

    def _resolve_declared_tool(
        self,
        namespace: Any,
        name: str,
        tool_type: str,
    ) -> tuple[str, str, str] | None:
        if isinstance(namespace, str):
            candidate = (namespace, name, tool_type)
            return candidate if candidate in self._profile.declared_client_tools else None
        matches = [
            declaration
            for declaration in self._profile.declared_client_tools
            if declaration[1] == name and declaration[2] == tool_type
        ]
        return matches[0] if len(matches) == 1 else None

    def _validate_tool_delta(self, payload: Mapping[str, Any], event_type: str) -> bool:
        allowed = {"type", "item_id", "output_index", "delta", "sequence_number"}
        if event_type == "response.custom_tool_call_input.delta":
            allowed.add("call_id")
        if not _only_fields(payload, allowed) or not _validate_delta_event(
            payload, require_item=True
        ):
            return False
        item_id = payload.get("item_id")
        if not isinstance(item_id, str):
            return False
        state = self._active_items.get(item_id)
        expected_item_type = (
            "function_call"
            if event_type == "response.function_call_arguments.delta"
            else "custom_tool_call"
        )
        if state is None or state.item_type != expected_item_type:
            return False
        call_id = payload.get("call_id")
        if call_id is not None and (
            not _bounded_identifier(call_id, required=True) or call_id != state.call_id
        ):
            return False
        delta = payload.get("delta")
        assert isinstance(delta, str)
        if len((state.delta_text + delta).encode("utf-8")) > _MAX_STREAM_CUMULATIVE_ITEM_BYTES:
            return False
        state.delta_text += delta
        return True

    def _validate_reasoning_event(self, payload: Mapping[str, Any], event_type: str) -> bool:
        common = {"type", "item_id", "output_index", "sequence_number"}
        if event_type == "response.reasoning_summary_part.added":
            allowed = common | {"summary_index", "part"}
        elif event_type == "response.reasoning_summary_text.done":
            allowed = common | {"summary_index", "text"}
        elif event_type == "response.reasoning_summary_text.delta":
            allowed = common | {"summary_index", "delta"}
        elif event_type == "response.reasoning_text.done":
            allowed = common | {"content_index", "text"}
        else:
            allowed = common | {"content_index", "delta"}
        if not _only_fields(payload, allowed):
            return False
        item_id = payload.get("item_id")
        if not _bounded_identifier(item_id, required=True):
            return False
        if not _required_index(payload, "output_index") or not _optional_index(
            payload, "sequence_number"
        ):
            return False
        state = self._active_items.get(str(item_id))
        if state is None or state.item_type != "reasoning":
            return False

        if event_type == "response.reasoning_summary_part.added":
            if not _required_index(payload, "summary_index"):
                return False
            part = payload.get("part")
            return isinstance(part, Mapping) and _validate_reasoning_text_part(
                part, expected_type="summary_text"
            )

        is_content = event_type in ("response.reasoning_text.delta", "response.reasoning_text.done")
        index_name = "content_index" if is_content else "summary_index"
        if not _required_index(payload, index_name):
            return False
        index = int(payload[index_name])
        category = "content" if is_content else "summary"
        key = (str(item_id), category, index)
        field = "text" if event_type in ("response.reasoning_summary_text.done", "response.reasoning_text.done") else "delta"
        value = payload.get(field)
        limit = _MAX_STREAM_ITEM_TEXT_BYTES if field == "text" else _MAX_STREAM_DELTA_BYTES
        if not isinstance(value, str) or not _bounded_utf8(value, limit):
            return False
        if field == "text":
            prior = self._reasoning_deltas.get(key)
            return prior is None or prior == value
        combined = self._reasoning_deltas.get(key, "") + value
        if len(combined.encode("utf-8")) > _MAX_STREAM_CUMULATIVE_ITEM_BYTES:
            return False
        self._reasoning_deltas[key] = combined
        return True

    def _validate_reasoning_part_event(
        self, payload: Mapping[str, Any], event_type: str
    ) -> bool:
        if not _only_fields(
            payload,
            {"type", "item_id", "output_index", "content_index", "part", "sequence_number"},
        ):
            return False
        item_id = payload.get("item_id")
        if not _bounded_identifier(item_id, required=True):
            return False
        if not _required_index(payload, "output_index") or not _required_index(
            payload, "content_index"
        ) or not _optional_index(payload, "sequence_number"):
            return False
        state = self._active_items.get(str(item_id))
        if state is None or state.item_type != "reasoning":
            return False
        part = payload.get("part")
        return isinstance(part, Mapping) and _validate_reasoning_text_part(
            part, expected_type="reasoning_text"
        )


def _only_fields(value: Mapping[str, Any], allowed: set[str]) -> bool:
    return not (set(value) - allowed)


def _bounded_utf8(value: str, max_bytes: int, *, nonempty: bool = False) -> bool:
    if nonempty and not value:
        return False
    return len(value.encode("utf-8")) <= max_bytes


def _bounded_identifier(value: Any, *, required: bool) -> bool:
    if value is None:
        return not required
    return isinstance(value, str) and _IDENTIFIER_RE.fullmatch(value) is not None


def _optional_index(value: Mapping[str, Any], name: str) -> bool:
    if name not in value:
        return True
    return _valid_index(value.get(name))


def _required_index(value: Mapping[str, Any], name: str) -> bool:
    return name in value and _valid_index(value.get(name))


def _valid_index(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and 0 <= value <= _MAX_STREAM_INDEX
    )


def _optional_item_status(item: Mapping[str, Any]) -> bool:
    status = item.get("status")
    return status is None or status in _ITEM_STATUSES


def _validate_response_progress_event(payload: Mapping[str, Any]) -> bool:
    if not _only_fields(payload, {"type", "response", "sequence_number"}):
        return False
    if not _optional_index(payload, "sequence_number"):
        return False
    response = payload.get("response")
    if not isinstance(response, Mapping):
        return False
    if "id" not in response:
        return False
    if not _bounded_identifier(response.get("id"), required=True):
        return False
    object_type = response.get("object")
    if object_type is not None and object_type != "response":
        return False
    status = response.get("status")
    if status is not None and status not in {"queued", "in_progress"}:
        return False
    created_at = response.get("created_at")
    if created_at is not None and (
        isinstance(created_at, bool) or not isinstance(created_at, int) or created_at < 0
    ):
        return False
    model = response.get("model")
    return model is None or (isinstance(model, str) and _bounded_utf8(model, 256, nonempty=True))


def _validate_response_completed_event(payload: Mapping[str, Any]) -> bool:
    response = payload.get("response")
    if not isinstance(response, Mapping):
        return False
    if "id" not in response:
        return False
    status = response.get("status")
    return status is None or status in {"completed", "incomplete"}


def _validate_completed_usage(usage: Mapping[str, Any]) -> bool:
    if not _only_fields(
        usage,
        {
            "input_tokens",
            "input_tokens_details",
            "output_tokens",
            "output_tokens_details",
            "total_tokens",
        },
    ):
        return False
    for name in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= _MAX_STREAM_TOKEN_COUNT
        ):
            return False
    input_details = usage.get("input_tokens_details")
    if input_details is not None and not isinstance(input_details, Mapping):
        return False
    output_details = usage.get("output_tokens_details")
    if output_details is not None and not isinstance(output_details, Mapping):
        return False
        reasoning_tokens = output_details.get("reasoning_tokens")
        if (
            isinstance(reasoning_tokens, bool)
            or not isinstance(reasoning_tokens, int)
            or not 0 <= reasoning_tokens <= _MAX_STREAM_TOKEN_COUNT
        ):
            return False
    return True


def _validate_delta_event(payload: Mapping[str, Any], *, require_item: bool) -> bool:
    allowed = {
        "type",
        "item_id",
        "output_index",
        "content_index",
        "delta",
        "sequence_number",
        "logprobs",
        "obfuscation",
    }
    if payload.get("type") == "response.custom_tool_call_input.delta":
        allowed.add("call_id")
    if not _only_fields(payload, allowed):
        return False
    delta = payload.get("delta")
    if not isinstance(delta, str) or not _bounded_utf8(delta, _MAX_STREAM_DELTA_BYTES):
        return False
    if not _optional_index(payload, "sequence_number"):
        return False
    if require_item:
        return _bounded_identifier(payload.get("item_id"), required=True) and _required_index(
            payload, "output_index"
        )
    if not _bounded_identifier(payload.get("item_id"), required=False):
        return False
    return _optional_index(payload, "output_index") and _optional_index(
        payload, "content_index"
    )


def _validate_assistant_message_item(item: Mapping[str, Any]) -> bool:
    if not _only_fields(item, {"type", "id", "status", "role", "content", "phase", "summary", "annotations"}):
        return False
    if item.get("role") != "assistant" or not _optional_item_status(item):
        return False
    phase = item.get("phase")
    if phase is not None and phase not in _MESSAGE_PHASES:
        return False
    content = item.get("content")
    if not isinstance(content, list) or len(content) > _MAX_STREAM_CONTENT_PARTS:
        return False
    total_bytes = 0
    for part in content:
        if not isinstance(part, Mapping) or not _only_fields(part, {"type", "text", "annotations", "logprobs"}):
            return False
        if part.get("type") != "output_text":
            return False
        text = part.get("text")
        if not isinstance(text, str) or not _bounded_utf8(text, _MAX_STREAM_ITEM_TEXT_BYTES):
            return False
        total_bytes += len(text.encode("utf-8"))
    return total_bytes <= _MAX_STREAM_ITEM_TEXT_BYTES


def _validate_reasoning_text_part(part: Mapping[str, Any], *, expected_type: str) -> bool:
    if not _only_fields(part, {"type", "text"}) or part.get("type") != expected_type:
        return False
    text = part.get("text")
    return isinstance(text, str) and _bounded_utf8(text, _MAX_STREAM_ITEM_TEXT_BYTES)


def _validate_reasoning_item(
    item: Mapping[str, Any],
    *,
    event_type: str,
    encrypted_replay: bool,
) -> int | None:
    if encrypted_replay:
        if event_type == "response.output_item.done":
            if set(item) != {"type", "id", "summary", "encrypted_content"}:
                return None
            if not _bounded_identifier(item.get("id"), required=True):
                return None
            encrypted_content = item.get("encrypted_content")
            if not isinstance(encrypted_content, str) or not _bounded_utf8(
                encrypted_content,
                _MAX_STREAM_ENCRYPTED_REASONING_ITEM_BYTES,
                nonempty=True,
            ):
                return None
            encrypted_bytes = len(encrypted_content.encode("utf-8"))
        else:
            if not _only_fields(item, {"type", "id", "status", "summary", "content", "encrypted_content"}):
                return None
            if not _optional_item_status(item):
                return None
            encrypted_value = item.get("encrypted_content")
            if isinstance(encrypted_value, str) and encrypted_value:
                return None
            encrypted_bytes = 0
    else:
        if not _only_fields(item, {"type", "id", "status", "summary", "content", "encrypted_content"}):
            return None
        if not _optional_item_status(item):
            return None
        encrypted_value = item.get("encrypted_content")
        if isinstance(encrypted_value, str) and encrypted_value:
            return None
        encrypted_bytes = 0
    summary = item.get("summary")
    if not isinstance(summary, list) or len(summary) > _MAX_STREAM_CONTENT_PARTS:
        return None
    total_bytes = 0
    for part in summary:
        if not isinstance(part, Mapping) or not _validate_reasoning_text_part(
            part, expected_type="summary_text"
        ):
            return None
        total_bytes += len(str(part["text"]).encode("utf-8"))
    content = item.get("content")
    if content is not None:
        if not isinstance(content, list) or len(content) > _MAX_STREAM_CONTENT_PARTS:
            return None
        for part in content:
            if not isinstance(part, Mapping) or not _validate_reasoning_text_part(
                part, expected_type="reasoning_text"
            ):
                return None
            total_bytes += len(str(part["text"]).encode("utf-8"))
    if total_bytes > _MAX_STREAM_ITEM_TEXT_BYTES:
        return None
    return encrypted_bytes


def _same_stream_item(first: _StreamItemState, second: _StreamItemState) -> bool:
    return (
        first.item_type,
        first.namespace,
        first.name,
        first.call_id,
    ) == (
        second.item_type,
        second.namespace,
        second.name,
        second.call_id,
    )


def _event_generated_bytes(payload: Mapping[str, Any]) -> int:
    """Count generated string bytes without retaining or returning any content."""
    total = 0
    for field in ("delta", "text"):
        value = payload.get(field)
        if isinstance(value, str):
            total += len(value.encode("utf-8"))
    item = payload.get("item")
    if not isinstance(item, Mapping):
        return total
    for field in ("arguments", "input"):
        value = item.get(field)
        if isinstance(value, str):
            total += len(value.encode("utf-8"))
    encrypted_content = item.get("encrypted_content")
    if isinstance(encrypted_content, str):
        total += len(encrypted_content.encode("utf-8"))
    for field in ("content", "summary"):
        parts = item.get(field)
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                    total += len(part["text"].encode("utf-8"))
    return total


@dataclass(frozen=True, slots=True)
class ParsedSSEEvent:
    """Parsed SSE event data from an upstream provider."""

    data: str
    raw_event: str
    json_body: Mapping[str, Any] | None
    is_done: bool


def parse_sse_lines(lines: Iterable[str]) -> list[ParsedSSEEvent]:
    """Parse complete SSE events from line strings.

    This helper is intentionally small and does not log or persist event data.
    """
    events: list[ParsedSSEEvent] = []
    data_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                events.append(_event_from_data_lines(data_lines))
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            data_lines.append(value)

    if data_lines:
        events.append(_event_from_data_lines(data_lines))
    return events


def format_sse_data(data: str) -> str:
    """Format data as an SSE event compatible with OpenAI SDK streaming."""
    return "".join(f"data: {line}\n" for line in data.splitlines() or [""]) + "\n"


def format_openai_error_event(
    *,
    message: str,
    error_type: str,
    code: str | None,
    request_id: str | None = None,
) -> str:
    """Format a safe OpenAI-shaped error event for an already-open stream."""
    payload = {
        "error": {
            "message": message,
            "type": error_type,
            "param": None,
            "code": code,
        }
    }
    if request_id is not None:
        payload["request_id"] = request_id
    return format_sse_data(json.dumps(payload, separators=(",", ":")))


def format_responses_error_event(
    *,
    message: str,
    code: str | None,
    param: str | None = None,
    request_id: str | None = None,
) -> str:
    """Format a safe Responses typed error event for an already-open stream."""
    payload: dict[str, object | None] = {
        "type": "error",
        "message": message,
        "code": code,
        "param": param,
        "sequence_number": 0,
    }
    if request_id is not None:
        payload["request_id"] = request_id
    return format_sse_data(json.dumps(payload, separators=(",", ":")))


def with_streaming_usage_options(body: Mapping[str, Any]) -> dict[str, Any]:
    """Return a streaming upstream body that requests provider final usage metadata."""
    upstream_body = dict(body)
    upstream_body["stream"] = True
    stream_options = upstream_body.get("stream_options")
    if isinstance(stream_options, Mapping):
        upstream_body["stream_options"] = {
            **dict(stream_options),
            "include_usage": True,
        }
    else:
        upstream_body["stream_options"] = {"include_usage": True}
    return upstream_body


def _event_from_data_lines(data_lines: list[str]) -> ParsedSSEEvent:
    data = "\n".join(data_lines)
    json_body: Mapping[str, Any] | None = None
    is_done = data.strip() == "[DONE]"
    if not is_done:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, Mapping):
            json_body = parsed

    return ParsedSSEEvent(
        data=data,
        raw_event=format_sse_data(data),
        json_body=json_body,
        is_done=is_done,
    )

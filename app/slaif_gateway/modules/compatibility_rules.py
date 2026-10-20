"""Bounded, non-executable value rules for inert client dialect metadata.

Presets can describe optional metadata; they cannot replace core fields,
invent identities, select providers, authorize tools, or change accounting.
The interpreter contains no field-specific compatibility exceptions.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

MAX_RULE_DEPTH = 6
MAX_RULE_NODES = 256
MAX_RULE_FIELDS = 32
MAX_VALUE_BYTES = 65_536
MAX_ARRAY_ITEMS = 64
MAX_ENUM_VALUES = 32

FEATURE_NAMES = frozenset({
    "schema_property_names", "sparse_visible_reasoning", "empty_visible_reasoning",
    "sparse_function_events",
})
OPTIONAL_FEATURE_NAMES = frozenset({"tool_output_images"})
SCOPES = frozenset({
    "request", "message.assistant", "message.user", "message.developer", "message.system",
    "part.output_text", "part.input_text", "part.input_image", "part.input_file", "part.input_audio",
    "item.function_call", "item.function_call_output",
    "item.custom_tool_call", "item.custom_tool_call_output", "item.reasoning", "item.compaction",
})
_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_AUTHORITY_MARKERS = (
    "auth", "secret", "password", "credential", "header", "cookie", "provider", "endpoint",
    "capabilit", "approval", "permission", "execution", "connector", "mcp", "signing",
    "token", "budget", "limit", "quota", "billing", "cost", "tool", "stream", "sandbox",
    "api_key", "apikey", "bearer", "session", "thread", "tenant", "principal", "identity",
    "request_id", "replay",
)
_CORE_FIELDS = frozenset({
    "type", "id", "role", "content", "text", "name", "namespace", "arguments", "input",
    "output", "call_id", "encrypted_content", "summary", "internal_chat_message_metadata_passthrough",
    "model", "tools", "tool_choice", "store", "background", "conversation", "previous_response_id",
    "instructions", "stream", "include", "reasoning", "client_metadata", "prompt_cache_key",
    "parallel_tool_calls", "max_output_tokens", "max_tool_calls", "temperature", "top_p",
    "metadata", "truncation", "user", "service_tier", "safety_identifier", "stream_options",
    "cache_control", "route", "url", "base_url",
    "image_url", "detail", "file_id", "file_data", "file_url", "filename", "audio", "format",
    "encoding", "data",
})
_PROTECTED_FIELDS_BY_SCOPE = {
    scope: _CORE_FIELDS | ({"status"} if scope.startswith("item.") else set())
    for scope in SCOPES
}


class CompatibilityRuleError(ValueError):
    """Fixed safe error, without preset contents or client values."""

    def __init__(self, code: str = "dialect_rule_invalid", field: str | None = None) -> None:
        self.code = code
        self.field = field
        super().__init__("The client compatibility rule is invalid.")


def _check(condition: bool) -> None:
    if not condition:
        raise CompatibilityRuleError()


def _integer(value: object, minimum: int, maximum: int) -> int:
    _check(type(value) is int and minimum <= value <= maximum)
    return value


def _field_name(value: object, *, scope: str | None = None) -> str:
    _check(isinstance(value, str) and _NAME.fullmatch(value) is not None)
    _check(not any(marker in value for marker in _AUTHORITY_MARKERS))
    _check(scope is None or value not in _PROTECTED_FIELDS_BY_SCOPE[scope])
    return value


def _scalar(value: object) -> bool:
    return value is None or type(value) in (str, bool, int)


def _same(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


@dataclass(frozen=True, slots=True)
class ValueRule:
    kind: str
    values: tuple[object, ...] = ()
    maximum: int | float = 0
    minimum: int | float = 0
    children: tuple[ValueRule, ...] = ()
    fields: tuple[tuple[str, bool, ValueRule], ...] = ()

    def accepts(self, value: object) -> bool:
        if self.kind == "enum":
            return any(_same(value, item) for item in self.values)
        if self.kind == "null":
            return value is None
        if self.kind == "boolean":
            return type(value) is bool
        if self.kind == "integer":
            return type(value) is int and self.minimum <= value <= self.maximum
        if self.kind == "number":
            return type(value) in (int, float) and self.minimum <= value <= self.maximum and math.isfinite(value)
        if self.kind == "string":
            if not isinstance(value, str):
                return False
            try:
                return self.minimum <= len(value.encode("utf-8")) <= self.maximum
            except UnicodeEncodeError:
                return False
        if self.kind == "array":
            return (
                isinstance(value, list) and len(value) <= self.maximum
                and all(self.children[0].accepts(item) for item in value)
            )
        if self.kind == "object":
            if not isinstance(value, Mapping) or len(value) > self.maximum:
                return False
            allowed = {name for name, _, _ in self.fields}
            return set(value) <= allowed and all(
                (not required or name in value)
                and (name not in value or rule.accepts(value[name]))
                for name, required, rule in self.fields
            )
        if self.kind == "one_of":
            return any(rule.accepts(value) for rule in self.children)
        return False

    def only_empty(self) -> bool:
        """Only empty/null values may be explicitly discarded by a preset."""
        return (
            self.kind == "null"
            or (self.kind == "string" and self.maximum == 0)
            or (self.kind == "array" and self.maximum == 0)
            or (self.kind == "object" and not self.fields)
            or (self.kind == "enum" and all(v is None or (type(v) is str and v == "") for v in self.values))
            or (self.kind == "one_of" and all(r.only_empty() for r in self.children))
        )


@dataclass(frozen=True, slots=True)
class FieldRule:
    name: str
    action: str
    value: ValueRule


@dataclass(frozen=True, slots=True)
class DialectRules:
    features: frozenset[str] = frozenset()
    extensions: tuple[tuple[str, tuple[FieldRule, ...]], ...] = ()
    custom_tools: frozenset[tuple[str, str, str]] = frozenset()

    def split(self, value: Mapping, scope: str) -> tuple[dict, dict, int]:
        """Validate declared optional fields, preserving all core/unknown fields.

        Unknown fields reach the existing strict core validator. No input is
        mutated. Preserved metadata is conservatively included in input bytes.
        """
        rules = next((rules for name, rules in self.extensions if name == scope), ())
        if not rules or not any(rule.name in value for rule in rules):
            return dict(value), {}, 0
        original = dict(value)
        preserved = {}
        for rule in rules:
            if rule.name not in original:
                continue
            item = original.pop(rule.name)
            try:
                encoded = json.dumps(item, ensure_ascii=False, allow_nan=False).encode("utf-8")
            except (ValueError, TypeError, UnicodeError, RecursionError):
                raise CompatibilityRuleError("dialect_value_invalid", rule.name) from None
            if len(encoded) > MAX_VALUE_BYTES or not rule.value.accepts(item):
                raise CompatibilityRuleError("dialect_value_invalid", rule.name)
            if rule.action == "preserve":
                preserved[rule.name] = copy.deepcopy(item)
        size = len(json.dumps(preserved, ensure_ascii=False).encode("utf-8")) if preserved else 0
        if size > MAX_VALUE_BYTES:
            raise CompatibilityRuleError("dialect_value_invalid")
        return original, preserved, size


def _parse_value(document: object, *, depth: int, nodes: list[int]) -> ValueRule:
    _check(isinstance(document, Mapping) and depth <= MAX_RULE_DEPTH)
    nodes[0] += 1
    _check(nodes[0] <= MAX_RULE_NODES)
    kind = document.get("kind")
    keys = set(document)
    if kind in ("null", "boolean"):
        _check(keys == {"kind"})
        return ValueRule(kind)
    if kind == "enum":
        _check(keys == {"kind", "values"})
        values = document["values"]
        _check(isinstance(values, list) and 1 <= len(values) <= MAX_ENUM_VALUES)
        _check(all(_scalar(v) for v in values))
        _check(all(not isinstance(v, str) or len(v.encode("utf-8")) <= 256 for v in values))
        _check(all(type(v) is not int or -(2**31) <= v < 2**31 for v in values))
        _check(not any(_same(v, w) for i, v in enumerate(values) for w in values[:i]))
        return ValueRule(kind, values=tuple(values))
    if kind in ("integer", "string"):
        _check(keys == {"kind", "minimum", "maximum"})
        floor, ceiling = (-(2**31), 2**31-1) if kind == "integer" else (0, MAX_VALUE_BYTES)
        minimum = _integer(document["minimum"], floor, ceiling)
        maximum = _integer(document["maximum"], minimum, ceiling)
        return ValueRule(kind, minimum=minimum, maximum=maximum)
    if kind == "number":
        _check(keys == {"kind", "minimum", "maximum"})
        minimum, maximum = document["minimum"], document["maximum"]
        _check(type(minimum) in (int, float) and type(maximum) in (int, float))
        _check(-1e12 <= minimum <= maximum <= 1e12 and math.isfinite(minimum) and math.isfinite(maximum))
        return ValueRule(kind, minimum=minimum, maximum=maximum)
    if kind == "array":
        _check(keys == {"kind", "max_items", "items"})
        maximum = _integer(document["max_items"], 0, MAX_ARRAY_ITEMS)
        child = _parse_value(document["items"], depth=depth+1, nodes=nodes)
        return ValueRule(kind, maximum=maximum, children=(child,))
    if kind == "object":
        _check(keys == {"kind", "fields"})
        raw = document["fields"]
        _check(isinstance(raw, Mapping) and len(raw) <= MAX_RULE_FIELDS)
        fields = []
        for name, rule in sorted(raw.items()):
            name = _field_name(name)
            _check(isinstance(rule, Mapping) and set(rule) == {"required", "value"})
            _check(type(rule["required"]) is bool)
            fields.append((name, rule["required"], _parse_value(rule["value"], depth=depth+1, nodes=nodes)))
        return ValueRule(kind, maximum=len(fields), fields=tuple(fields))
    if kind == "one_of":
        _check(keys == {"kind", "rules"})
        raw = document["rules"]
        _check(isinstance(raw, list) and 1 <= len(raw) <= 4)
        return ValueRule(kind, children=tuple(_parse_value(r, depth=depth+1, nodes=nodes) for r in raw))
    raise CompatibilityRuleError()


def _parse_dialect_rules(document: object) -> DialectRules:
    """Compile the exact finite rule vocabulary into a deeply frozen snapshot."""
    _check(isinstance(document, Mapping) and set(document) == {"features", "extensions", "custom_tools"})
    features = document["features"]
    _check(isinstance(features, Mapping) and FEATURE_NAMES <= set(features)
           and set(features) <= FEATURE_NAMES | OPTIONAL_FEATURE_NAMES)
    _check(all(type(value) is bool for value in features.values()))
    raw = document["extensions"]
    _check(isinstance(raw, Mapping) and set(raw) <= SCOPES)
    extensions = []
    nodes = [0]
    total_fields = 0
    for scope, values in sorted(raw.items()):
        _check(isinstance(values, Mapping) and len(values) <= MAX_RULE_FIELDS)
        fields = []
        for name, field in sorted(values.items()):
            name = _field_name(name, scope=scope)
            _check(isinstance(field, Mapping) and set(field) == {"action", "value"})
            _check(field["action"] in ("preserve", "drop"))
            rule = _parse_value(field["value"], depth=0, nodes=nodes)
            _check(field["action"] != "drop" or rule.only_empty())
            fields.append(FieldRule(name, field["action"], rule))
        total_fields += len(fields)
        _check(total_fields <= MAX_RULE_FIELDS)
        extensions.append((scope, tuple(fields)))
    custom_tools = document["custom_tools"]
    _check(isinstance(custom_tools, list) and len(custom_tools) <= MAX_RULE_FIELDS)
    custom = set()
    for tool in custom_tools:
        _check(isinstance(tool, Mapping) and set(tool) == {"namespace", "name", "type"})
        _check(all(isinstance(tool[k], str) and _NAME.fullmatch(tool[k]) for k in tool))
        _check(tool["type"] == "custom")
        entry = (tool["namespace"], tool["name"], tool["type"])
        _check(entry not in custom)
        custom.add(entry)
    return DialectRules(
        frozenset(name for name, enabled in features.items() if enabled),
        tuple(extensions), frozenset(custom),
    )


def parse_dialect_rules(document: object) -> DialectRules:
    """Every malformed document fails safely, including direct Python callers."""
    try:
        return _parse_dialect_rules(document)
    except (TypeError, UnicodeError, RecursionError):
        raise CompatibilityRuleError() from None

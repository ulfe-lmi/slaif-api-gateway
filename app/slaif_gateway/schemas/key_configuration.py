"""Versioned, strict key-configuration schema (policy files and partial updates).

The single source of truth for the ``schema_version`` 1 key-configuration
document used by ``keys create --policy-file``, ``keys policy update
--policy-file``, and ``keys policy export``.

Field presence is first-class: an ABSENT field means "leave the current
value untouched" on update (or the service default on create), which is
distinct from an explicit ``null`` (clear/unlimited/inherit, per field) and
from an explicit empty value (for example a deny-all provider list).

Decimal contract: JSON numbers with a fractional part are decoded with the
lexical decimal precision (``parse_float=Decimal``), so money values such as
``99999999.123456789`` are preserved exactly and export round-trips as the
same decimal string. Programmatic callers of
:func:`parse_key_configuration` must pass ``Decimal`` or ``str`` for decimal
fields, never binary ``float``.

Error contract: :class:`KeyConfigurationError` messages use fixed safe
vocabulary and field paths only; they never echo file bodies, field names,
or operator-supplied values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from decimal import InvalidOperation
from typing import Any

KEY_CONFIGURATION_SCHEMA_VERSION = 1

# Conservative conservative file and value bounds (safe errors, no echoes).
MAX_KEY_CONFIGURATION_FILE_BYTES = 64 * 1024
MAX_KEY_CONFIGURATION_LIST_ITEMS = 100
MAX_KEY_CONFIGURATION_ITEM_LENGTH = 256
MAX_KEY_CONFIGURATION_REASON_LENGTH = 512

#: Canonical rate-limit override members of a version-1 configuration
#: (matching the key-override columns and the existing rate-limit
#: validator vocabulary). The historical runtime alias is canonicalized
#: before any merge; anything else is rejected, never silently ignored.
RATE_POLICY_MEMBER_NAMES: tuple[str, ...] = (
    "requests_per_minute",
    "tokens_per_minute",
    "max_concurrent_requests",
    "window_seconds",
)

RATE_POLICY_LEGACY_ALIASES: dict[str, str] = {
    "concurrent_requests": "max_concurrent_requests",
}


class _Absent:
    """Marker for a field that is not present in the configuration."""

    _instance = None

    def __new__(cls) -> "_Absent":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "ABSENT"

    def __bool__(self) -> bool:
        return False


class _AbsentMarker:
    """Placeholder for a required document key that is missing."""


_ABSENT_MARKER = _AbsentMarker()

ABSENT = _Absent()

#: Sentinel-aware field type: omitted, explicit null, or a concrete value.
Field = Any  # ABSENT | None | value; documented per field below.


@dataclass(slots=True)
class KeyConfiguration:
    """Typed, presence-aware key configuration.

    Every field defaults to :data:`ABSENT` (omitted). Field semantics:

    - ``allowed_models`` / ``allowed_endpoints``: list of values, or an
      explicit ``null`` treated as the empty list for that dimension;
      ``ABSENT`` preserves the current values on update.
    - ``allow_all_models`` / ``allow_all_endpoints``: bool; ``ABSENT``
      preserves the current value.
    - ``allowed_providers``: ``ABSENT`` preserves; ``null`` is
      UNRESTRICTED; ``[]`` denies ALL providers; a list is an allow-list.
    - ``responses_policy``: ``ABSENT`` preserves; ``null`` clears the block
      (no Codex authority); an object is a COMPLETE replacement block
      (strictly validated; no partial member merge).
    - ``rate_limit_policy``: ``ABSENT`` preserves; ``null`` clears every
      per-key override (inherit the deployment); an object with nullable
      members where ``null`` inherits that member.
    - ``lazy_throttling_policy``: ``ABSENT`` preserves; ``null`` removes the
      stored policy (immediate rejection default); an object is a complete
      block.
    - ``cost_limit_eur`` / ``token_limit_total`` / ``request_limit_total``:
      ``ABSENT`` preserves; ``null`` means UNLIMITED for that quota.
    - ``chat_streaming_live_burn_policy``: ``ABSENT`` preserves; an object is
      a complete block (``null`` is not accepted - use the existing command
      to disable).
    - ``external_tool_policy``: ``ABSENT`` preserves; ``null`` removes the
      fenced policy (returns to strict bounded); an object is a complete
      block.
    - ``confirm_external_tool_fenced``: bool acknowledgement for fenced
      blocks.
    """

    allowed_models: Field = ABSENT
    allow_all_models: Field = ABSENT
    allowed_endpoints: Field = ABSENT
    allow_all_endpoints: Field = ABSENT
    allowed_providers: Field = ABSENT
    responses_policy: Field = ABSENT
    rate_limit_policy: Field = ABSENT
    lazy_throttling_policy: Field = ABSENT
    cost_limit_eur: Field = ABSENT
    token_limit_total: Field = ABSENT
    request_limit_total: Field = ABSENT
    chat_streaming_live_burn_policy: Field = ABSENT
    external_tool_policy: Field = ABSENT
    confirm_external_tool_fenced: Field = ABSENT

    def has(self, name: str) -> bool:
        """True when the field is present (explicitly, including null)."""
        return getattr(self, name) is not ABSENT

    def as_present_fields(self) -> dict[str, Any]:
        """Mapping of present fields to their explicit values (incl. None)."""
        present: dict[str, Any] = {}
        for name in _FIELD_NAMES:
            value = getattr(self, name)
            if value is not ABSENT:
                present[name] = value
        return present

    def is_empty(self) -> bool:
        return not self.as_present_fields()


_FIELD_NAMES: tuple[str, ...] = (
    "allowed_models",
    "allow_all_models",
    "allowed_endpoints",
    "allow_all_endpoints",
    "allowed_providers",
    "responses_policy",
    "rate_limit_policy",
    "lazy_throttling_policy",
    "cost_limit_eur",
    "token_limit_total",
    "request_limit_total",
    "chat_streaming_live_burn_policy",
    "external_tool_policy",
    "confirm_external_tool_fenced",
)

_KNOWN_CONFIGURATION_FIELDS: frozenset[str] = frozenset(_FIELD_NAMES)


class KeyConfigurationError(ValueError):
    """A safe, fixed-message configuration file or value error.

    Messages name only the fixed field and the problem class; they never
    echo file bodies or operator-supplied values.
    """


def _fail(field: str, message: str) -> None:
    raise KeyConfigurationError(f"{field}: {message}")


def _strict_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _value in pairs:
        if not isinstance(key, str):
            _fail("file", "JSON object keys must be strings.")
        if key in seen:
            _fail("file", "JSON object contains a duplicate key.")
        seen.add(key)
    return dict(pairs)


def _strict_constant(name: str) -> Any:
    _fail("file", f"JSON constant {name} is not allowed.")


def _load_strict_object(data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _fail("file", "File must be valid UTF-8 JSON.")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_pairs_hook,
            parse_constant=_strict_constant,
            parse_float=Decimal,
        )
    except KeyConfigurationError:
        raise
    except json.JSONDecodeError:
        _fail("file", "File is not valid JSON.")
    if not isinstance(value, dict):
        _fail("file", "Top level must be a JSON object.")
    return value


def _bounded_str(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(field_name, "Value must be a non-empty string.")
    if len(value) > MAX_KEY_CONFIGURATION_ITEM_LENGTH:
        _fail(field_name, f"Value exceeds {MAX_KEY_CONFIGURATION_ITEM_LENGTH} characters.")
    return value


def _bounded_str_list(value: Any, *, field_name: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        _fail(field_name, "Value must be a list of strings or null.")
    if len(value) > MAX_KEY_CONFIGURATION_LIST_ITEMS:
        _fail(field_name, f"Value exceeds {MAX_KEY_CONFIGURATION_LIST_ITEMS} items.")
    items: list[str] = []
    for item in value:
        items.append(_bounded_str(item, field_name=field_name))
    return items


def _bounded_nonneg_int(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(field_name, "Value must be an integer or null.")
    if value < 0:
        _fail(field_name, "Value must not be negative.")
    return value


def _bounded_decimal(value: Any, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        _fail(field_name, "Value must be a decimal number or null.")
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            _fail(field_name, "Value must be a decimal number or null.")
        try:
            parsed = Decimal(raw)
        except InvalidOperation:
            _fail(field_name, "Value must be a valid decimal number or null.")
    else:
        _fail(field_name, "Value must be a decimal number or null.")
    if not parsed.is_finite():
        _fail(field_name, "Value must be a finite decimal number or null.")
    if parsed < 0:
        _fail(field_name, "Value must not be negative.")
    return parsed


def _bounded_object(value: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(field_name, "Value must be a JSON object.")
    if not all(isinstance(key, str) for key in value):
        _fail(field_name, "Object keys must be strings.")
    return value


def _strict_bool(value: Any, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        _fail(field_name, "Value must be a boolean.")
    return value


def parse_key_configuration(document: dict[str, Any]) -> KeyConfiguration:
    """Parse a strict schema-version-1 configuration document.

    The document must carry ``schema_version`` exactly equal to
    :data:`KEY_CONFIGURATION_SCHEMA_VERSION`; unknown fields are rejected.
    Nested objects (responses/rate/lazy/live-burn/external-tool policy) are
    accepted here only as well-typed opaque blocks; their field-level rules
    are enforced by the shared service validators (single source of truth).
    """
    unknown = sorted(str(key) for key in set(document) - _KNOWN_CONFIGURATION_FIELDS - {"schema_version"})
    if unknown:
        _fail("schema", "Document contains unsupported fields.")

    raw_version = document.get("schema_version", _ABSENT_MARKER)
    if raw_version is _ABSENT_MARKER:
        _fail("schema_version", "Field is required.")
    if (
        not isinstance(raw_version, int)
        or isinstance(raw_version, bool)
        or raw_version != KEY_CONFIGURATION_SCHEMA_VERSION
    ):
        _fail(
            "schema_version",
            "Value must be exactly the current schema version.",
        )

    config = KeyConfiguration()
    if "allowed_models" in document:
        config.allowed_models = _bounded_str_list(
            document["allowed_models"], field_name="allowed_models"
        )
    if "allow_all_models" in document:
        config.allow_all_models = _strict_bool(document["allow_all_models"], field_name="allow_all_models")
    if "allowed_endpoints" in document:
        config.allowed_endpoints = _bounded_str_list(
            document["allowed_endpoints"], field_name="allowed_endpoints"
        )
    if "allow_all_endpoints" in document:
        config.allow_all_endpoints = _strict_bool(
            document["allow_all_endpoints"], field_name="allow_all_endpoints"
        )
    if "allowed_providers" in document:
        config.allowed_providers = _bounded_str_list(
            document["allowed_providers"], field_name="allowed_providers"
        )
    if "responses_policy" in document:
        raw = document["responses_policy"]
        config.responses_policy = (
            None if raw is None else _bounded_object(raw, field_name="responses_policy")
        )
    if "rate_limit_policy" in document:
        raw = document["rate_limit_policy"]
        if raw is not None:
            raw = _bounded_object(raw, field_name="rate_limit_policy")
            canonical: dict[str, object] = {}
            for key, member in raw.items():
                if not isinstance(key, str):
                    _fail(
                        "rate_limit_policy",
                        "Rate limit policy contains unsupported fields."
                    )
                target = RATE_POLICY_LEGACY_ALIASES.get(key, key)
                if target not in RATE_POLICY_MEMBER_NAMES:
                    _fail(
                        "rate_limit_policy",
                        "Rate limit policy contains unsupported fields."
                    )
                if target in canonical:
                    _fail(
                        "rate_limit_policy",
                        "Rate limit policy repeats one member through an alias."
                    )
                if member is not None:
                    if isinstance(member, bool) or not isinstance(member, int) or member <= 0:
                        _fail(
                            "rate_limit_policy",
                            "Rate-limit members must be positive integers or null."
                        )
                canonical[target] = member
            raw = {
                name: canonical[name] for name in RATE_POLICY_MEMBER_NAMES if name in canonical
            }
        config.rate_limit_policy = raw
    if "lazy_throttling_policy" in document:
        raw = document["lazy_throttling_policy"]
        config.lazy_throttling_policy = (
            None if raw is None else _bounded_object(raw, field_name="lazy_throttling_policy")
        )
    if "cost_limit_eur" in document:
        config.cost_limit_eur = _bounded_decimal(
            document["cost_limit_eur"], field_name="cost_limit_eur"
        )
    if "token_limit_total" in document:
        config.token_limit_total = _bounded_nonneg_int(
            document["token_limit_total"], field_name="token_limit_total"
        )
    if "request_limit_total" in document:
        config.request_limit_total = _bounded_nonneg_int(
            document["request_limit_total"], field_name="request_limit_total"
        )
    if "chat_streaming_live_burn_policy" in document:
        raw = document["chat_streaming_live_burn_policy"]
        if raw is None:
            _fail(
                "chat_streaming_live_burn_policy",
                "Set the existing streaming live-burn command to disable monitoring; "
                "policy files carry complete blocks only."
            )
        config.chat_streaming_live_burn_policy = _bounded_object(
            raw, field_name="chat_streaming_live_burn_policy"
        )
    if "external_tool_policy" in document:
        raw = document["external_tool_policy"]
        config.external_tool_policy = (
            None if raw is None else _bounded_object(raw, field_name="external_tool_policy")
        )
    if "confirm_external_tool_fenced" in document:
        config.confirm_external_tool_fenced = _strict_bool(
            document["confirm_external_tool_fenced"],
            field_name="confirm_external_tool_fenced",
        )
    return config


def parse_key_configuration_file(data: bytes) -> KeyConfiguration:
    """Read and strictly parse one key-configuration file payload."""
    if len(data) > MAX_KEY_CONFIGURATION_FILE_BYTES:
        _fail("file", f"File exceeds {MAX_KEY_CONFIGURATION_FILE_BYTES} bytes.")
    document = _load_strict_object(data)
    return parse_key_configuration(document)


def key_configuration_export(
    config: KeyConfiguration,
) -> dict[str, Any]:
    """Render the safe versioned export document (allowlisted fields only).

    The document always re-parses with :func:`parse_key_configuration`; it
    never carries non-conformant keys or stored-policy diagnostics. Stored
    policy that the shared validators cannot administer must make the
    surrounding export operation fail explicitly instead of producing a
    partial document.
    """
    export: dict[str, Any] = {"schema_version": KEY_CONFIGURATION_SCHEMA_VERSION}
    for name in _FIELD_NAMES:
        value = getattr(config, name)
        if value is ABSENT:
            continue
        if name == "cost_limit_eur" and isinstance(value, Decimal):
            export[name] = str(value)
        else:
            export[name] = value
    return export

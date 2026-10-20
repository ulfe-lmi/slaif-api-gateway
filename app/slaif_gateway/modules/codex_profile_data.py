"""Bounded parser and immutable snapshot for Codex compatibility profile DATA.

A Codex compatibility profile is operator-maintained JSON *data*, not code:
it describes the finite namespace vocabulary (literal built-in names and
bounded connector prefixes), the bounded identifier grammar for namespace
suffixes and tool names (finite, known grammar-trait identifiers only), and
cardinality/schema/byte ceilings that may only *lower* the engine's fixed
hard caps.  It never contains a tool-name inventory, executable content,
import paths, arbitrary regular expressions, authority grants, or any field
outside the exact reviewed schema below. Schema 2 additionally describes
optional inert metadata through a bounded value-rule grammar and selects known
parser modes. All such data is included in its canonical identity.

The parser accepts one bounded regular UTF-8 JSON document with a duplicate
key hook, a nonfinite-value hook, strict types, exact key sets, and literal
grammar-trait identifiers.  It returns a deeply immutable snapshot; the
canonical digest (SHA-256 over the sorted-key compact serialization of the
validated document) is what binds a key's pinned ``fixture_sha256`` to the
profile data.  Revisions ``1`` and ``2`` are reserved frozen identities kept
as source literals elsewhere; this loader only accepts bounded decimal data
revisions of three or higher and applies no compiled upper revision bound.

Safe failures: every rejection raises :class:`CodexProfileDataError` with a
fixed message and code.  Profile contents, file names, and exception detail
are never echoed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat as stat_module
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from re import Pattern
from functools import lru_cache

from slaif_gateway.modules.compatibility_rules import (
    CompatibilityRuleError,
    DialectRules,
    parse_dialect_rules,
)

CODEX_PROFILE_MODULE_ID = "codex-0.162-responses-v1"
CODEX_PROFILE_SCHEMA_VERSION = 1
CODEX_PROFILE_SUPPORTED_SCHEMA_VERSIONS = (1, 2)
# Revisions 1 and 2 are the frozen historical identities; data revisions
# start at 3.  Revisions are bounded ASCII decimal strings (no leading
# zeros, at most nine digits) with no compiled upper bound.
CODEX_PROFILE_MIN_DATA_REVISION = 3
CODEX_PROFILE_RESERVED_REVISIONS = frozenset({"1", "2"})

# Known finite grammar traits.  A trait identifier maps to one fixed
# character class inside this module; profiles cannot supply patterns.
KNOWN_INITIAL_TRAITS = frozenset({"lowercase_ascii", "ascii_letter"})
KNOWN_TAIL_TRAITS = frozenset(
    {
        "lowercase_ascii_digits_underscore_dot_hyphen",
        "ascii_letters_digits_underscore_hyphen",
    }
)
_INITIAL_TRAIT_CLASSES = {
    "lowercase_ascii": "a-z",
    "ascii_letter": "A-Za-z",
}
_TAIL_TRAIT_CLASSES = {
    "lowercase_ascii_digits_underscore_dot_hyphen": "a-z0-9_.-",
    "ascii_letters_digits_underscore_hyphen": "A-Za-z0-9_-",
}

# Engine-fixed hard caps.  Profile data may lower them, never raise them.
MAX_NAMESPACES_HARD_CAP = 16
MAX_TOTAL_TOOLS_HARD_CAP = 256
MAX_TOOLS_PER_NAMESPACE_HARD_CAP = 256
MAX_SCHEMA_DEPTH_HARD_CAP = 16
MAX_SCHEMA_PROPERTIES_HARD_CAP = 4096
MAX_TOOL_DESCRIPTION_BYTES_HARD_CAP = 20000
MAX_TOTAL_DESCRIPTION_BYTES_HARD_CAP = 262_144
MAX_DECLARATION_BYTES_HARD_CAP = 589_824
MAX_IDENTIFIER_CHARACTERS_HARD_CAP = 64
MAX_NAMESPACE_SUFFIX_CHARACTERS_HARD_CAP = 64
MAX_BUILTIN_NAMES_HARD_CAP = 32
MAX_CONNECTOR_PREFIXES_HARD_CAP = 8
MAX_PROFILE_FILE_BYTES = 65_536

# Bounded positive ASCII decimal revision: no sign, no leading zeros, at
# most nine digits.  The reserved 1/2 check and the >= 3 floor are applied
# numerically after this shape check.
_REVISION_PATTERN = re.compile(r"[1-9][0-9]{0,8}")
_CLI_VERSION_PATTERN = re.compile(r"[0-9]{1,9}(\.[0-9]{1,9}){2}")
_SOURCE_TAG_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_SOURCE_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
_CONNECTOR_PREFIX_PATTERN = re.compile(r"[a-z][a-z0-9_.-]{0,63}")
_BUILTIN_LIKE_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_.-]*")

_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "module_id",
        "revision",
        "provenance",
        "namespace_rules",
        "tool_name_rules",
        "limits",
    }
)
_PROVENANCE_FIELDS = frozenset({"cli_version", "source_tag", "source_commit"})
_NAMESPACE_RULE_FIELDS = frozenset(
    {
        "builtin_names",
        "connector_prefixes",
        "suffix_initial",
        "suffix_tail",
        "max_suffix_characters",
    }
)
_NAME_RULE_FIELDS = frozenset({"initial", "tail", "max_characters", "max_leading_underscores"})
_LIMIT_FIELDS = frozenset(
    {
        "max_namespaces",
        "max_total_tools",
        "max_tools_per_namespace",
        "max_schema_depth",
        "max_schema_properties",
        "max_tool_description_bytes",
        "max_total_description_bytes",
        "max_declaration_bytes",
    }
)
_LIMIT_HARD_CAPS = {
    "max_namespaces": MAX_NAMESPACES_HARD_CAP,
    "max_total_tools": MAX_TOTAL_TOOLS_HARD_CAP,
    "max_tools_per_namespace": MAX_TOOLS_PER_NAMESPACE_HARD_CAP,
    "max_schema_depth": MAX_SCHEMA_DEPTH_HARD_CAP,
    "max_schema_properties": MAX_SCHEMA_PROPERTIES_HARD_CAP,
    "max_tool_description_bytes": MAX_TOOL_DESCRIPTION_BYTES_HARD_CAP,
    "max_total_description_bytes": MAX_TOTAL_DESCRIPTION_BYTES_HARD_CAP,
    "max_declaration_bytes": MAX_DECLARATION_BYTES_HARD_CAP,
}


class CodexProfileDataError(ValueError):
    """Safe rejection of one compatibility profile data document.

    ``code`` is a fixed machine-readable category; ``safe_message`` is a
    fixed operator-facing sentence.  Neither carries document contents.
    """

    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True)
class CodexProfileNameRule:
    """One immutable bounded identifier rule derived from known traits."""

    initial_trait: str
    tail_trait: str
    max_characters: int
    max_leading_underscores: int
    pattern: Pattern[str]

    def is_allowed(self, name: object) -> bool:
        """Return True only for an exact, bounded match; nothing is rewritten."""
        return (
            isinstance(name, str)
            and 0 < len(name) <= self.max_characters
            and self.pattern.fullmatch(name) is not None
        )


def _compile_name_rule(
    *,
    initial_trait: str,
    tail_trait: str,
    max_leading_underscores: int,
) -> Pattern[str]:
    initial_class = _INITIAL_TRAIT_CLASSES[initial_trait]
    tail_class = _TAIL_TRAIT_CLASSES[tail_trait]
    return re.compile(rf"_{{0,{max_leading_underscores}}}[{initial_class}][{tail_class}]*")


def _fail(code: str, safe_message: str) -> CodexProfileDataError:
    return CodexProfileDataError(code, safe_message)


def _require_object(document: object, fields: frozenset[str], code: str) -> dict:
    if not isinstance(document, Mapping):
        raise _fail(code, "The Codex compatibility profile section is invalid.")
    if set(document) != fields:
        raise _fail(code, "The Codex compatibility profile fields are invalid.")
    return dict(document)


def _require_int(value: object, minimum: int, maximum: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise _fail(code, "The Codex compatibility profile limit is invalid.")
    return value


def _require_bounded_name(value: object, *, max_characters: int, code: str) -> str:
    if (
        not isinstance(value, str)
        or not 0 < len(value) <= max_characters
        or _BUILTIN_LIKE_NAME_PATTERN.fullmatch(value) is None
    ):
        raise _fail(code, "The Codex compatibility profile identifier is invalid.")
    return value


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise _fail(
                "duplicate_key",
                "The Codex compatibility profile contains a duplicate field.",
            )
        seen.add(key)
    return dict(pairs)


def _reject_nonfinite_value(name: str) -> float:
    raise _fail(
        "non_finite_value",
        "The Codex compatibility profile contains a nonfinite value.",
    )


def canonical_profile_digest(document: Mapping[str, object]) -> str:
    """SHA-256 over the sorted-key compact serialization of the data."""
    serialized = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


@dataclass(frozen=True, slots=True)
class CodexProfileData:
    """Deeply immutable, fully validated Codex compatibility profile snapshot."""

    schema_version: int
    module_id: str
    revision: str
    cli_version: str
    source_tag: str
    source_commit: str
    builtin_names: frozenset[str]
    connector_prefixes: tuple[str, ...]
    namespace_suffix_initial: str
    namespace_suffix_tail: str
    max_namespace_suffix_characters: int
    namespace_suffix_pattern: Pattern[str]
    builtin_name_rule: CodexProfileNameRule
    connector_name_rule: CodexProfileNameRule
    max_namespaces: int
    max_total_tools: int
    max_tools_per_namespace: int
    max_schema_depth: int
    max_schema_properties: int
    max_tool_description_bytes: int
    max_total_description_bytes: int
    max_declaration_bytes: int
    dialect: DialectRules
    digest: str

    def classify_namespace_name(self, name: object) -> str | None:
        """Return ``builtin``, ``connector``, or None for an exact bounded match."""
        if not isinstance(name, str) or not name:
            return None
        if name in self.builtin_names:
            return "builtin"
        for prefix in self.connector_prefixes:
            if name.startswith(prefix):
                suffix = name[len(prefix) :]
                if self.namespace_suffix_pattern.fullmatch(suffix) is not None:
                    return "connector"
        return None

    def is_tool_name_allowed(self, kind: str, name: object) -> bool:
        """Validate one tool name under the builtin or connector rule."""
        if kind == "builtin":
            return self.builtin_name_rule.is_allowed(name)
        if kind == "connector":
            return self.connector_name_rule.is_allowed(name)
        return False

    def to_facts(self) -> dict[str, str]:
        """Return fixed safe operator-facing facts without raw document content."""
        return {
            "module_id": self.module_id,
            "profile_schema_version": str(self.schema_version),
            "revision": self.revision,
            "digest": self.digest,
            "cli_version": self.cli_version,
            "source_tag": self.source_tag,
            "source_commit": self.source_commit,
            "builtin_names": ",".join(sorted(self.builtin_names)),
            "connector_prefixes": ",".join(self.connector_prefixes),
            "max_namespaces": str(self.max_namespaces),
            "max_total_tools": str(self.max_total_tools),
            "max_tools_per_namespace": str(self.max_tools_per_namespace),
            "dialect_features": ",".join(sorted(self.dialect.features)),
            "dialect_extension_scopes": ",".join(scope for scope, _ in self.dialect.extensions),
        }


def _parse_name_rule(section: Mapping[str, object]) -> CodexProfileNameRule:
    raw = _require_object(section, _NAME_RULE_FIELDS, "name_rule_invalid")
    initial_trait = raw.get("initial")
    tail_trait = raw.get("tail")
    if (
        not isinstance(initial_trait, str)
        or initial_trait not in KNOWN_INITIAL_TRAITS
        or not isinstance(tail_trait, str)
        or tail_trait not in KNOWN_TAIL_TRAITS
    ):
        raise _fail(
            "grammar_trait_unknown",
            "The Codex compatibility profile grammar trait is invalid.",
        )
    max_characters = _require_int(
        raw.get("max_characters"),
        1,
        MAX_IDENTIFIER_CHARACTERS_HARD_CAP,
        "limit_above_hard_cap",
    )
    # Derived engine bound: the rule must leave room for at least one
    # initial letter inside the total character cap, for both categories.
    # The data value itself (for example 0, 1, or a larger revision value)
    # is policy, not a compiled engine constant.
    max_leading_underscores = _require_int(
        raw.get("max_leading_underscores"),
        0,
        max_characters - 1,
        "limit_above_hard_cap",
    )
    return CodexProfileNameRule(
        initial_trait=initial_trait,
        tail_trait=tail_trait,
        max_characters=max_characters,
        max_leading_underscores=max_leading_underscores,
        pattern=_compile_name_rule(
            initial_trait=initial_trait,
            tail_trait=tail_trait,
            max_leading_underscores=max_leading_underscores,
        ),
    )


@lru_cache(maxsize=1)
def _legacy_dialects() -> tuple[tuple[int, DialectRules], ...]:
    """Frozen schema-1 behavior; new schema-2 presets bind their own rules."""
    path = Path(__file__).parent / "clients/profiles/codex_0162_legacy_dialects.json"
    try:
        raw = _read_codex_profile_text(path).encode("utf-8")
        if hashlib.sha256(raw).hexdigest() != "2317b86d83eb7879bb538ec8d1ed1fb6f869c18c6ec3eb97ee29bec7a3a00a5d":
            raise ValueError
        document = json.loads(raw)
        return tuple(
            (entry["minimum_revision"], parse_dialect_rules(entry["dialect"]))
            for entry in document["profiles"]
        )
    except (OSError, ValueError, KeyError, TypeError):
        raise _fail("dialect_rule_invalid", "The frozen legacy compatibility presets are invalid.") from None


def _validate_document(document: object) -> CodexProfileData:
    if not isinstance(document, Mapping):
        raise _fail("schema_invalid", "The Codex compatibility profile is invalid.")
    top = dict(document)
    schema_version = top.get("schema_version")
    fields = _TOP_LEVEL_FIELDS | {"dialect"} if schema_version == 2 else _TOP_LEVEL_FIELDS
    if set(top) != fields:
        raise _fail("schema_invalid", "The Codex compatibility profile fields are invalid.")

    schema_version = top.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version not in CODEX_PROFILE_SUPPORTED_SCHEMA_VERSIONS
    ):
        raise _fail("schema_invalid", "The Codex compatibility profile version is unsupported.")
    if top.get("module_id") != CODEX_PROFILE_MODULE_ID:
        raise _fail(
            "module_id_mismatch",
            "The Codex compatibility profile module identity is invalid.",
        )
    revision = top.get("revision")
    if (
        not isinstance(revision, str)
        or _REVISION_PATTERN.fullmatch(revision) is None
        or int(revision) < CODEX_PROFILE_MIN_DATA_REVISION
    ):
        raise _fail(
            "revision_reserved_or_invalid",
            "The Codex compatibility profile revision is invalid.",
        )

    provenance = _require_object(top.get("provenance"), _PROVENANCE_FIELDS, "provenance_invalid")
    cli_version = provenance.get("cli_version")
    source_tag = provenance.get("source_tag")
    source_commit = provenance.get("source_commit")
    if (
        not isinstance(cli_version, str)
        or _CLI_VERSION_PATTERN.fullmatch(cli_version) is None
        or not isinstance(source_tag, str)
        or _SOURCE_TAG_PATTERN.fullmatch(source_tag) is None
        or not isinstance(source_commit, str)
        or _SOURCE_COMMIT_PATTERN.fullmatch(source_commit) is None
    ):
        raise _fail("provenance_invalid", "The Codex compatibility profile provenance is invalid.")

    namespace_rules = _require_object(
        top.get("namespace_rules"), _NAMESPACE_RULE_FIELDS, "namespace_rules_invalid"
    )
    builtin_names_raw = namespace_rules.get("builtin_names")
    if (
        not isinstance(builtin_names_raw, list)
        or not 1 <= len(builtin_names_raw) <= MAX_BUILTIN_NAMES_HARD_CAP
    ):
        raise _fail(
            "namespace_rules_invalid", "The Codex compatibility profile builtin names are invalid."
        )
    builtin_names: set[str] = set()
    for name in builtin_names_raw:
        validated = _require_bounded_name(
            name, max_characters=MAX_IDENTIFIER_CHARACTERS_HARD_CAP, code="namespace_rules_invalid"
        )
        if validated in builtin_names:
            raise _fail(
                "namespace_rules_invalid",
                "The Codex compatibility profile builtin names are invalid.",
            )
        builtin_names.add(validated)
    connector_prefixes_raw = namespace_rules.get("connector_prefixes")
    if (
        not isinstance(connector_prefixes_raw, list)
        or not 1 <= len(connector_prefixes_raw) <= MAX_CONNECTOR_PREFIXES_HARD_CAP
    ):
        raise _fail(
            "namespace_rules_invalid",
            "The Codex compatibility profile connector prefixes are invalid.",
        )
    connector_prefixes: list[str] = []
    for prefix in connector_prefixes_raw:
        if (
            not isinstance(prefix, str)
            or not 0 < len(prefix) <= MAX_IDENTIFIER_CHARACTERS_HARD_CAP
            or _CONNECTOR_PREFIX_PATTERN.fullmatch(prefix) is None
        ):
            raise _fail(
                "namespace_rules_invalid",
                "The Codex compatibility profile connector prefixes are invalid.",
            )
        connector_prefixes.append(prefix)
    if len(set(connector_prefixes)) != len(connector_prefixes):
        raise _fail(
            "namespace_rules_invalid",
            "The Codex compatibility profile connector prefixes are invalid.",
        )
    for shorter in connector_prefixes:
        for longer in connector_prefixes:
            if shorter != longer and longer.startswith(shorter):
                raise _fail(
                    "namespace_rules_invalid",
                    "The Codex compatibility profile connector prefixes are invalid.",
                )
    for name in builtin_names:
        for prefix in connector_prefixes:
            if name.startswith(prefix):
                raise _fail(
                    "namespace_rules_invalid",
                    "The Codex compatibility profile namespace vocabulary is ambiguous.",
                )

    suffix_initial = namespace_rules.get("suffix_initial")
    suffix_tail = namespace_rules.get("suffix_tail")
    if (
        not isinstance(suffix_initial, str)
        or suffix_initial not in KNOWN_INITIAL_TRAITS
        or not isinstance(suffix_tail, str)
        or suffix_tail not in KNOWN_TAIL_TRAITS
    ):
        raise _fail(
            "grammar_trait_unknown", "The Codex compatibility profile grammar trait is invalid."
        )
    max_suffix_characters = _require_int(
        namespace_rules.get("max_suffix_characters"),
        1,
        MAX_NAMESPACE_SUFFIX_CHARACTERS_HARD_CAP,
        "limit_above_hard_cap",
    )
    namespace_suffix_pattern = re.compile(
        rf"[{_INITIAL_TRAIT_CLASSES[suffix_initial]}]"
        rf"[{_TAIL_TRAIT_CLASSES[suffix_tail]}]{{0,{max_suffix_characters - 1}}}"
    )

    tool_name_rules = _require_object(
        top.get("tool_name_rules"), frozenset({"builtin", "connector"}), "name_rule_invalid"
    )
    builtin_name_rule = _parse_name_rule(tool_name_rules.get("builtin"))
    connector_name_rule = _parse_name_rule(tool_name_rules.get("connector"))

    limits = _require_object(top.get("limits"), _LIMIT_FIELDS, "limits_invalid")
    limit_values: dict[str, int] = {}
    for field, hard_cap in _LIMIT_HARD_CAPS.items():
        limit_values[field] = _require_int(limits.get(field), 1, hard_cap, "limit_above_hard_cap")

    try:
        if schema_version == 2:
            dialect = parse_dialect_rules(top["dialect"])
        else:
            dialect = next(
                rules for minimum, rules in reversed(_legacy_dialects())
                if int(revision) >= minimum
            )
    except CompatibilityRuleError as exc:
        raise _fail(exc.code, "The Codex compatibility preset dialect rules are invalid.") from None
    if any(
        namespace not in builtin_names or not builtin_name_rule.is_allowed(name)
        for namespace, name, _ in dialect.custom_tools
    ):
        raise _fail("dialect_rule_invalid", "Custom dialect tools must use declared builtin namespaces.")
    digest = canonical_profile_digest(top)
    return CodexProfileData(
        schema_version=schema_version,
        module_id=CODEX_PROFILE_MODULE_ID,
        revision=revision,
        cli_version=cli_version,
        source_tag=source_tag,
        source_commit=source_commit,
        builtin_names=frozenset(builtin_names),
        connector_prefixes=tuple(connector_prefixes),
        namespace_suffix_initial=suffix_initial,
        namespace_suffix_tail=suffix_tail,
        max_namespace_suffix_characters=max_suffix_characters,
        namespace_suffix_pattern=namespace_suffix_pattern,
        builtin_name_rule=builtin_name_rule,
        connector_name_rule=connector_name_rule,
        max_namespaces=limit_values["max_namespaces"],
        max_total_tools=limit_values["max_total_tools"],
        max_tools_per_namespace=limit_values["max_tools_per_namespace"],
        max_schema_depth=limit_values["max_schema_depth"],
        max_schema_properties=limit_values["max_schema_properties"],
        max_tool_description_bytes=limit_values["max_tool_description_bytes"],
        max_total_description_bytes=limit_values["max_total_description_bytes"],
        max_declaration_bytes=limit_values["max_declaration_bytes"],
        dialect=dialect,
        digest=digest,
    )


def parse_codex_profile_data(text: str) -> CodexProfileData:
    """Parse and validate one bounded regular UTF-8 JSON profile document."""
    if not isinstance(text, str):
        raise _fail("malformed_json", "The Codex compatibility profile is not valid JSON.")
    if len(text.encode("utf-8")) > MAX_PROFILE_FILE_BYTES:
        raise _fail("profile_too_large", "The Codex compatibility profile is too large.")
    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite_value,
        )
    except CodexProfileDataError:
        raise
    except (ValueError, RecursionError):
        raise _fail(
            "malformed_json", "The Codex compatibility profile is not valid JSON."
        ) from None
    return _validate_document(document)


def _read_codex_profile_text(path: object) -> str:
    """Load one bounded operator profile file; no silent fallback on failure.

    Opens the path once in non-blocking read mode, verifies through ``fstat``
    on the open handle that it is a regular file of bounded size, and reads
    from the same handle to EOF under a ``MAX + 1`` byte cap.  A FIFO,
    device, or oversize target is rejected before any unbounded allocation
    or read; a byte count that grew or shrank relative to the ``fstat``
    snapshot is rejected so trailing bytes are never silently ignored.
    """
    if not isinstance(path, (str, Path)):
        raise _fail("profile_unreadable", "The Codex compatibility profile file is unreadable.")
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NONBLOCK)
    except (OSError, ValueError):
        raise _fail(
            "profile_unreadable", "The Codex compatibility profile file is unreadable."
        ) from None
    try:
        try:
            file_stat = os.fstat(fd)
        except OSError:
            raise _fail(
                "profile_unreadable", "The Codex compatibility profile file is unreadable."
            ) from None
        if not stat_module.S_ISREG(file_stat.st_mode):
            raise _fail("profile_unreadable", "The Codex compatibility profile file is unreadable.")
        if file_stat.st_size > MAX_PROFILE_FILE_BYTES:
            raise _fail("profile_too_large", "The Codex compatibility profile is too large.")
        expected = file_stat.st_size
        limit = MAX_PROFILE_FILE_BYTES + 1
        buffer = bytearray()
        while len(buffer) < limit:
            chunk = os.read(fd, limit - len(buffer))
            if not chunk:
                break
            buffer.extend(chunk)
        if len(buffer) > MAX_PROFILE_FILE_BYTES:
            raise _fail("profile_too_large", "The Codex compatibility profile is too large.")
        if len(buffer) != expected:
            raise _fail("profile_unreadable", "The Codex compatibility profile file is unreadable.")
    except CodexProfileDataError:
        raise
    except OSError:
        raise _fail(
            "profile_unreadable", "The Codex compatibility profile file is unreadable."
        ) from None
    finally:
        os.close(fd)
    try:
        text = bytes(buffer).decode("utf-8")
    except UnicodeDecodeError:
        raise _fail(
            "malformed_json", "The Codex compatibility profile is not valid JSON."
        ) from None
    return text


def load_codex_profile_file(path: object) -> CodexProfileData:
    """Validate one bounded document from one regular-file snapshot."""
    return parse_codex_profile_data(_read_codex_profile_text(path))


_PACKAGED_DEFAULT_PROFILE_PATH = (
    Path(__file__).resolve().parent / "clients" / "profiles" / "codex_0162.json"
)


def load_default_codex_profile() -> CodexProfileData:
    """Load the packaged default profile DATA shipped with the engine."""
    return load_codex_profile_file(_PACKAGED_DEFAULT_PROFILE_PATH)


def list_codex_presets() -> tuple[tuple[str, Path, CodexProfileData], ...]:
    """Inspect shipped presets offline; neither activate nor mutate anything."""
    root = _PACKAGED_DEFAULT_PROFILE_PATH.parent
    try:
        data = (root / "presets.json").read_bytes()
        if len(data) > MAX_PROFILE_FILE_BYTES:
            raise ValueError
        document = json.loads(data, object_pairs_hook=_reject_duplicate_pairs)
        if not isinstance(document, dict) or set(document) != {"schema_version", "presets"}:
            raise ValueError
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            raise ValueError
        entries = document["presets"]
        if not isinstance(entries, list) or not 1 <= len(entries) <= 16:
            raise ValueError
        result = []
        names = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"name", "file"}:
                raise ValueError
            name, filename = entry["name"], entry["file"]
            if (
                not isinstance(name, str) or re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,79}", name) is None
                or name in names or not isinstance(filename, str)
                or re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,79}\.json", filename) is None
                or ".." in filename
            ):
                raise ValueError
            path = root / filename
            result.append((name, path, load_codex_profile_file(path)))
            names.add(name)
        return tuple(result)
    except (OSError, ValueError, TypeError, KeyError):
        raise _fail("preset_index_invalid", "The shipped compatibility preset index is invalid.") from None


def read_codex_preset(name: str) -> str:
    """Return a validated shipped document by literal preset name."""
    for candidate, path, _ in list_codex_presets():
        if candidate == name:
            text = _read_codex_profile_text(path)
            parse_codex_profile_data(text)
            return text
    raise _fail("preset_unknown", "The requested compatibility preset is unavailable.")


__all__ = [
    "CODEX_PROFILE_MIN_DATA_REVISION",
    "CODEX_PROFILE_MODULE_ID",
    "CODEX_PROFILE_RESERVED_REVISIONS",
    "CODEX_PROFILE_SCHEMA_VERSION",
    "CodexProfileData",
    "CodexProfileDataError",
    "CodexProfileNameRule",
    "canonical_profile_digest",
    "load_codex_profile_file",
    "load_default_codex_profile",
    "parse_codex_profile_data",
]

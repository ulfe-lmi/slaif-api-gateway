"""Pure bounded Codex declaration-history lifecycle facts (objective 226).

Shared runtime groundwork for versioned Codex ``additional_tools``
declaration history.  This module analyzes declarations that have ALREADY
been individually validated by the policy-owned per-declaration
taxonomy/schema validation into bounded request-local chronological
facts:

- the applied snapshots/updates in caller-supplied order;
- the final active (namespaced) tool taxonomy;
- per-call binding facts keyed by the original ``call_id`` as
  ``(namespace, name, kind)`` with ``kind`` in ``{"function", "custom"}``;
- the call IDs that are still pending (no output item yet);
- the ACTIVE tool definitions by reference (the caller's validated
  definition objects, never copied or read) so later lowering has
  definitions/schema provenance without a schema copy per step;
- safe structured error positions (fixed reason code, event position,
  field, observed/limit counts) for every fail-closed refusal.

Scope honesty: this helper enforces, over the event sequence it is
supplied, call ID uniqueness, output ID uniqueness, one output per call,
exact function/custom linkage between a call and its output, and
call-position binding.  It does NOT see, and does NOT enforce, the
replay item ID checks for other item families (reasoning, compaction,
encrypted content, message IDs) or HMAC replay ownership; those remain
with their existing owners.  It is NOT a validator: it does not
re-validate raw declaration data, names, schemas, or free text; every raw
declaration must have passed the existing policy-owned per-declaration
taxonomy/schema validation (including invalid earlier entries) before the
caller constructs an event sequence for it.  It is NOT a replay
authority: HMAC replay ownership proves historical calls, not the current
catalog, and declaration item IDs are inert metadata that may repeat (or
be absent) without becoming authority.

Two explicit, profile-declared modes are supported (absence of an
explicit mode keeps legacy gateway behavior because this helper is only
consulted by callers that have a mode):

``full_snapshot``
    Every declaration event is a complete replacement of the active
    catalog.  This models a client profile that declares each
    ``additional_tools`` item to be the full current set (the Codex
    client builds a full prefix only when its current tool set is
    nonempty, so an absent first declaration legally means "no local
    tools").  Removal notices are not part of this mode.

``positional_updates``
    Every declaration event is an adds/changes-only update applied to
    the active catalog (a redefinition of the same ``namespace.tool``
    name replaces the earlier entry, including a
    function/custom kind change).  Removals arrive separately as
    :class:`CodexToolRemovalEvent` facts parsed from the pinned
    machine-readable removal-notice grammar below; a notice only
    REDUCES authority — a later re-addition cannot retroactively
    authorize a historical call, and a call is bound to the identity
    active at its own position, immutably.

A call with ``namespace=None`` resolves against the active catalog
exactly as the existing policy matches declared local tools by name and
type: it must find ONE unambiguous ``(name, kind)`` match; zero matches
or multiple matches are fixed safe refusals.  A call whose kind does not
equal the declared kind at its position is refused.

Unknown or ambiguous transitions fail closed with a fixed safe
compatibility error.  Requests with insufficient information (a call
whose identity is not declared at its position) are refused.

Source-derived wire contract, pinned official Codex CLI
``rust-v0.167.1`` (source commit
``0a94398fa60c4fac0e7659e4213a0a36e613dd46``):

- ``core/src/client.rs`` ``build_responses_request``: for Responses
  Lite the full current ``AdditionalTools`` prefix is inserted at input
  index zero ONLY when ``prompt.tools`` is nonempty.
- ``core/src/session/turn.rs`` ``build_prompt``: in incremental mode
  ``prompt.tools`` keeps only hosted tool specs, so the full local
  prefix may be absent.
- ``core/src/context/world_state/top_level_tools.rs``: incremental
  batches carry only added/changed definitions; removals are a separate
  developer notice (content kind ``tools.removed_definition``) whose
  structured metadata is stripped for non-OpenAI providers
  (``protocol/src/models.rs`` ``clear_internal_chat_message_metadata_passthrough``),
  leaving the configurable header text (bundled defaults below, each
  resolved at most 512 bytes upstream).

Consequently neither "first item = current set", "last item = current
set", nor "every item = full snapshot" is justified by source, and this
module never infers a full snapshot from a partial item nor parses
arbitrary prose as authority: only the exact pinned notice grammar
below is accepted.

This module carries no provider or client secret, no execution or
replay authorization, and no persistent state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
import types

# --- explicit modes -------------------------------------------------------

MODE_FULL_SNAPSHOT = "full_snapshot"
MODE_POSITIONAL_UPDATES = "positional_updates"
_MODES = frozenset({MODE_FULL_SNAPSHOT, MODE_POSITIONAL_UPDATES})

# --- pinned removal-notice defaults (Codex rust-v0.167.1 bundled wording) --

DEFAULT_REMOVED_NAMESPACES_HEADER = (
    "The following namespaces are no longer available. Do not call tools in "
    "them unless those tools are declared in a later update:"
)
DEFAULT_REMOVED_TOOLS_HEADER = (
    "The following tools are no longer available. Do not call them:"
)
# Pinned bundled default tool-update hint (prompts/src/model_messages/
# incremental_tools.rs, rust-v0.167.1).  Only this EXACT standalone
# developer text immediately preceding a validated declaration is
# declaration metadata; any other prose is ordinary history.
DEFAULT_INCREMENTAL_TOOLS_HINT = (
    "This is an incremental tools update. Previously declared tools remain "
    "available for direct calls unless explicitly marked unavailable. If a "
    "tool is redefined here, its latest definition replaces the earlier one."
)

# --- stable, content-free rejection reason codes ---------------------------

REASON_MODE_UNSUPPORTED = "codex_tool_history_mode_unsupported"
REASON_MAX_ITEMS_INVALID = "codex_tool_history_max_items_invalid"
REASON_EVENT_INVALID = "codex_tool_history_event_invalid"
REASON_TOO_MANY_EVENTS = "codex_tool_history_too_many_events"
REASON_POSITION_OUT_OF_RANGE = "codex_tool_history_position_out_of_range"
REASON_POSITION_NOT_MONOTONIC = "codex_tool_history_position_not_monotonic"
REASON_TAXONOMY_INVALID = "codex_tool_history_taxonomy_invalid"
REASON_DEFINITIONS_MISMATCH = "codex_tool_history_definitions_mismatch"
REASON_DEFINITIONS_INCONSISTENT = "codex_tool_history_definitions_inconsistent"
REASON_CALL_KIND_INVALID = "codex_tool_history_call_kind_invalid"
REASON_CALL_KIND_MISMATCH = "codex_tool_history_call_kind_mismatch"
REASON_CALL_NOT_DECLARED = "codex_tool_history_call_not_declared"
REASON_CALL_AMBIGUOUS = "codex_tool_history_call_ambiguous"
REASON_CALL_ID_REPEATED = "codex_tool_history_call_id_repeated"
REASON_OUTPUT_CALL_NOT_BOUND = "codex_tool_history_output_call_not_bound"
REASON_OUTPUT_CALL_REPEATED = "codex_tool_history_output_call_repeated"
REASON_OUTPUT_KIND_MISMATCH = "codex_tool_history_output_kind_mismatch"
REASON_OUTPUT_ID_REPEATED = "codex_tool_history_output_id_repeated"
REASON_REMOVAL_UNKNOWN = "codex_tool_history_removal_unknown"
REASON_NOTICE_IN_SNAPSHOT_MODE = "codex_tool_history_notice_in_snapshot_mode"
REASON_REMOVAL_EMPTY = "codex_removal_notice_empty"
REASON_REMOVAL_BODY_TOO_LARGE = "codex_removal_notice_body_too_large"
REASON_REMOVAL_INVALID = "codex_removal_notice_invalid"
REASON_REMOVAL_HEADER_UNRECOGNIZED = "codex_removal_notice_header_unrecognized"
REASON_REMOVAL_NAME_INVALID = "codex_removal_notice_name_invalid"
REASON_REMOVAL_NAME_DUPLICATE = "codex_removal_notice_name_duplicate"
REASON_REMOVAL_SECTION_REPEATED = "codex_removal_notice_section_repeated"
REASON_REMOVAL_SUBSUMED = "codex_removal_notice_subsumed"
REASON_REMOVAL_TOO_MANY_NAMES = "codex_removal_notice_too_many_names"

_KINDS = frozenset({"function", "custom"})


class CodexToolHistoryError(ValueError):
    """Fixed safe compatibility error for an ambiguous or insufficient
    declaration-history transition.

    ``reason_code`` is a stable content-free marker; ``position`` names the
    0-based position of the offending event in the caller's chronological
    sequence (or ``None`` for sequence-level failures); ``field`` names the
    checked fact; ``observed``/``limit`` carry counts for cardinality
    failures.  No raw request content is ever echoed.
    """

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        position: int | None = None,
        field: str | None = None,
        observed: int | None = None,
        limit: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.position = position
        self.field = field
        self.observed = observed
        self.limit = limit


def _error(
    reason_code: str,
    message: str,
    *,
    position: int | None = None,
    field: str | None = None,
    observed: int | None = None,
    limit: int | None = None,
) -> CodexToolHistoryError:
    return CodexToolHistoryError(
        message,
        reason_code=reason_code,
        position=position,
        field=field,
        observed=observed,
        limit=limit,
    )


# --- immutable lifecycle facts ---------------------------------------------

# Canonical ordered taxonomy: (namespace, ((tool, kind), ...), ...), the same
# shape as the policy-owned CodexTaxonomyResult.taxonomy.
CodexToolTaxonomy = tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
# Per-call binding fact: (namespace, name, kind).
CodexToolBinding = tuple[str | None, str, str]


@dataclass(frozen=True, slots=True)
class CodexToolDeclarationEvent:
    """One ALREADY policy-validated ``additional_tools`` declaration.

    ``taxonomy`` is the canonical tuple from the existing per-declaration
    validation.  ``item_id`` is the optional item ID: inert metadata that
    may repeat or be absent and never gains authority.  ``position`` is
    the 0-based index of this item in the caller's chronological
    sequence.  ``definitions`` optionally carries the caller's validated
    definition objects keyed by ``(namespace, tool)``; when present it
    must cover exactly the taxonomy's tools.  Objects are referenced
    (provenance for later lowering), never copied or read.
    """

    taxonomy: CodexToolTaxonomy
    position: int
    item_id: str | None = None
    definitions: Mapping[tuple[str, str], Any] | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, slots=True)
class CodexToolRemovalEvent:
    """Structured facts of one pinned-grammar removal notice.

    ``namespaces`` are whole removed namespaces (their members are
    subsumed); ``tools`` are individually removed ``(namespace, tool)``
    pairs not already subsumed by a removed namespace.
    """

    namespaces: frozenset[str]
    tools: frozenset[tuple[str, str]]
    position: int


@dataclass(frozen=True, slots=True)
class CodexToolCallEvent:
    """One ALREADY validated Codex tool call item at its input position.

    ``namespace`` may be ``None``: the call then resolves against the
    active catalog by ONE unambiguous ``(name, kind)`` match, exactly as
    the existing policy matches declared local tools by name and type.
    """

    call_id: str
    namespace: str | None
    name: str
    kind: str
    position: int


@dataclass(frozen=True, slots=True)
class CodexToolCallOutputEvent:
    """One ALREADY validated tool call output item at its input position.

    ``kind`` must equal the bound call's kind (exact function/custom
    linkage).  ``output_id`` is the optional output item ID:
    uniqueness-checked metadata, not authority.  One output per call.
    """

    call_id: str
    kind: str
    position: int
    output_id: str | None = None


CodexToolHistoryEvent = (
    CodexToolDeclarationEvent
    | CodexToolRemovalEvent
    | CodexToolCallEvent
    | CodexToolCallOutputEvent
)


@dataclass(frozen=True, slots=True)
class CodexToolHistoryStep:
    """One applied chronological fact, in caller-supplied order.

    ``detail`` is a content-free marker (``"snapshot"``, ``"update"``,
    ``"removed"``, ``"bound"``, ``"completed"``).  ``definition`` on a
    call step references (never copies) the caller's definition object
    active at the CALL position, so later core can detect
    schema/type transport conflicts without rebuilding a second
    lifecycle; it is ``None`` when the sequence uses no-definition
    mode.
    """

    position: int
    kind: str
    detail: str | None = None
    namespaces: frozenset[str] = frozenset()
    tools: frozenset[tuple[str, str]] = frozenset()
    call_id: str | None = None
    binding: CodexToolBinding | None = None
    definition: Any = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class CodexToolHistoryFacts:
    """Bounded request-local chronological facts.

    ``call_bindings`` is the stable core-to-adapter shape: an immutable
    mapping keyed by the ORIGINAL ``call_id`` to ``(namespace, name,
    kind)``, covering exactly the supplied call events.  Bindings are
    fixed at call position and are immutable through subsequent
    updates; a later declaration never authorizes a preceding call.
    ``active_definitions`` references (never copies) the caller's
    validated definition objects for the final active catalog.
    Both mappings are stdlib :class:`types.MappingProxyType` views:
    immutable, O(1) lookup, and equal to their dict contents.
    Replay item ID checks for other item families and HMAC replay
    ownership are NOT covered by these facts; they remain with their
    existing owners.
    """

    mode: str
    steps: tuple[CodexToolHistoryStep, ...]
    active_taxonomy: CodexToolTaxonomy
    call_bindings: Mapping[str, CodexToolBinding] = None  # type: ignore[assignment]
    active_definitions: Mapping[tuple[str, str], Any] = field(
        default=None, repr=False
    )
    pending_call_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.call_bindings, types.MappingProxyType):
            object.__setattr__(
                self,
                "call_bindings",
                types.MappingProxyType(dict(self.call_bindings or {})),
            )
        if not isinstance(self.active_definitions, types.MappingProxyType):
            object.__setattr__(
                self,
                "active_definitions",
                types.MappingProxyType(dict(self.active_definitions or {})),
            )


# --- pinned machine-readable removal-notice grammar -------------------------


@dataclass(frozen=True, slots=True)
class CodexRemovalNotice:
    """Exact structured result of one pinned-grammar removal notice."""

    namespaces: frozenset[str]
    tools: frozenset[tuple[str, str]]


def parse_codex_removal_notice(
    body: Any,
    *,
    namespaces_header: str = DEFAULT_REMOVED_NAMESPACES_HEADER,
    tools_header: str = DEFAULT_REMOVED_TOOLS_HEADER,
    max_names: int = 4096,
    max_body_bytes: int = 65536,
) -> CodexRemovalNotice:
    """Parse ONE removal notice in the exact pinned Codex grammar.

    Grammar (mirrors ``top_level_tools.rs`` ``RemovedTools::body``):

    - at most two sections joined by ``"\\n\\n"``;
    - each section is its exact pinned header line followed by one or more
      ``"- " name`` lines (no trailing blank);
    - section order: removed namespaces first (bare names, no ``.``),
      then individually removed tools as ``namespace.tool`` (exactly one
      ``.``); a single section may be either kind; a section kind never
      repeats;
    - names are unique within a section; a tool whose namespace is listed
      in the same notice is subsumed and must not also be listed;
    - the headers must EXACTLY equal the caller's pinned values (the
      upstream bundled defaults when the operator keeps them); arbitrary
      prose, reworded headers, unknown sections, or an empty notice are
      refused with a fixed safe error.  The grammar never infers a
      removal from unrecognized text.

    ``max_names``/``max_body_bytes`` are explicit resource bounds.
    """
    if not isinstance(body, str):
        raise _error(
            REASON_REMOVAL_INVALID,
            "The Codex removal notice must be text",
            field="body",
        )
    if body == "":
        raise _error(
            REASON_REMOVAL_EMPTY,
            "The Codex removal notice is empty",
            field="body",
        )
    if not isinstance(max_names, int) or isinstance(max_names, bool) or max_names < 1:
        raise _error(
            REASON_REMOVAL_TOO_MANY_NAMES,
            "The Codex removal notice name bound is invalid",
            field="max_names",
            limit=max_names if isinstance(max_names, int) else None,
        )
    if (
        not isinstance(max_body_bytes, int)
        or isinstance(max_body_bytes, bool)
        or max_body_bytes < 1
    ):
        raise _error(
            REASON_REMOVAL_BODY_TOO_LARGE,
            "The Codex removal notice byte bound is invalid",
            field="max_body_bytes",
        )
    if len(body.encode("utf-8")) > max_body_bytes:
        raise _error(
            REASON_REMOVAL_BODY_TOO_LARGE,
            "The Codex removal notice is too large",
            field="body",
            observed=len(body.encode("utf-8")),
            limit=max_body_bytes,
        )
    if (
        not isinstance(namespaces_header, str)
        or not isinstance(tools_header, str)
        or namespaces_header == tools_header
        or namespaces_header == ""
        or tools_header == ""
    ):
        raise _error(
            REASON_REMOVAL_INVALID,
            "The Codex removal notice headers must be distinct and nonempty",
            field="headers",
        )
    if "\n" in namespaces_header or "\n" in tools_header:
        # A newline inside a pinned header makes the section grammar
        # ambiguous; refuse closed instead of guessing.
        raise _error(
            REASON_REMOVAL_INVALID,
            "The Codex removal notice headers must not contain line breaks",
            field="headers",
        )

    sections = body.split("\n\n")
    if len(sections) > 2:
        raise _error(
            REASON_REMOVAL_INVALID,
            "The Codex removal notice has too many sections",
            field="body",
            observed=len(sections),
            limit=2,
        )
    namespaces: set[str] = set()
    tools: set[tuple[str, str]] = set()
    seen_kinds: set[str] = set()
    for index, section in enumerate(sections):
        lines = section.split("\n")
        header, name_lines = lines[0], lines[1:]
        if not name_lines:
            raise _error(
                REASON_REMOVAL_INVALID,
                "The Codex removal notice section lists no names",
                field=f"section[{index}]",
            )
        if header == namespaces_header:
            kind = "namespace"
            if index == 1:
                raise _error(
                    REASON_REMOVAL_INVALID,
                    "The Codex removal notice section order is invalid",
                    field=f"section[{index}].header",
                )
        elif header == tools_header:
            kind = "tool"
        else:
            raise _error(
                REASON_REMOVAL_HEADER_UNRECOGNIZED,
                "The Codex removal notice header is not recognized",
                field=f"section[{index}].header",
            )
        if kind in seen_kinds:
            raise _error(
                REASON_REMOVAL_SECTION_REPEATED,
                "The Codex removal notice section kind is repeated",
                field=f"section[{index}].header",
            )
        seen_kinds.add(kind)
        seen: set[str] = set()
        for line in name_lines:
            if not line.startswith("- "):
                raise _error(
                    REASON_REMOVAL_INVALID,
                    "The Codex removal notice entry is malformed",
                    field=f"section[{index}].entries",
                )
            name = line[2:]
            if not name or any(character.isspace() for character in name):
                raise _error(
                    REASON_REMOVAL_NAME_INVALID,
                    "The Codex removal notice name is invalid",
                    field=f"section[{index}].entries",
                )
            if kind == "namespace":
                if "." in name:
                    raise _error(
                        REASON_REMOVAL_NAME_INVALID,
                        "The Codex removal notice namespace name is invalid",
                        field=f"section[{index}].entries",
                    )
            else:
                namespace, dot, tool = name.partition(".")
                if not dot or not namespace or not tool or "." in tool:
                    raise _error(
                        REASON_REMOVAL_NAME_INVALID,
                        "The Codex removal notice tool name is invalid",
                        field=f"section[{index}].entries",
                    )
            if name in seen:
                raise _error(
                    REASON_REMOVAL_NAME_DUPLICATE,
                    "The Codex removal notice name is repeated",
                    field=f"section[{index}].entries",
                )
            seen.add(name)
            if kind == "namespace":
                namespaces.add(name)
            else:
                namespace, _, tool = name.partition(".")
                tools.add((namespace, tool))
    for namespace, _tool in tools:
        if namespace in namespaces:
            raise _error(
                REASON_REMOVAL_SUBSUMED,
                "The Codex removal notice lists a tool subsumed by a removed namespace",
                field="tools",
            )
    total = len(namespaces) + len(tools)
    if total > max_names:
        raise _error(
            REASON_REMOVAL_TOO_MANY_NAMES,
            "The Codex removal notice lists too many names",
            field="body",
            observed=total,
            limit=max_names,
        )
    return CodexRemovalNotice(
        namespaces=frozenset(namespaces),
        tools=frozenset(tools),
    )


# --- bounded chronological analysis -----------------------------------------


def codex_positional_compiled_out_positions(
    canonical_items: Sequence[Mapping[str, Any]],
    facts: CodexToolHistoryFacts,
) -> frozenset[int]:
    """Input positions of declaration metadata compiled out of provider bodies.

    Exactly: (a) every ``additional_tools`` declaration; (b) every validated
    removal notice (positions recorded in ``facts.steps``); and (c) the EXACT
    pinned incremental tool-update hint, only when it is a standalone
    developer text item immediately preceding a declaration.  Nothing else is
    ever compiled out: ordinary messages (including arbitrary developer
    prose), tool calls, outputs, IDs, and relative order are preserved.
    """
    positions = set(
        index
        for index, item in enumerate(canonical_items)
        if isinstance(item, Mapping) and item.get("type") == "additional_tools"
    )
    positions.update(step.position for step in facts.steps if step.kind == "removal")
    positions.update(codex_positional_hint_positions(canonical_items))
    return frozenset(positions)


def codex_standalone_text_content(content: Any) -> str | None:
    """Decode standalone text without assigning it protocol authority."""
    if isinstance(content, str):
        return content
    if isinstance(content, list) and len(content) == 1:
        part = content[0]
        if (
            isinstance(part, Mapping)
            and part.get("type") == "input_text"
            and isinstance(part.get("text"), str)
        ):
            return part["text"]
    return None


def codex_positional_hint_positions(
    canonical_items: Sequence[Mapping[str, Any]],
) -> frozenset[int]:
    """Positions of the EXACT pinned incremental hint, immediately before a declaration.

    The hint is a standalone developer text item (a string or exactly one
    input_text part) whose content is exactly
    the pinned bundled default literal; it is declaration metadata only in
    that position.  Any other text is ordinary history and is never
    compiled out or dropped.
    """
    positions: set[int] = set()
    for index, item in enumerate(canonical_items):
        if (
            not isinstance(item, Mapping)
            or item.get("type") != "additional_tools"
            or index == 0
        ):
            continue
        previous = canonical_items[index - 1]
        if (
            isinstance(previous, Mapping)
            and previous.get("role") == "developer"
            and previous.get("type") in (None, "message")
            and codex_standalone_text_content(previous.get("content"))
            == DEFAULT_INCREMENTAL_TOOLS_HINT
        ):
            positions.add(index - 1)
    return frozenset(positions)


def _canonical_taxonomy(
    taxonomy: Any,
    position: int,
) -> tuple[CodexToolTaxonomy, set[tuple[str, str]]]:
    """Rebuild an immutable canonical taxonomy from validated input.

    The caller guarantees the declarations already passed the policy-owned
    per-declaration taxonomy/schema validation; this performs only the
    minimal structural/type check needed to build an independent immutable
    copy and refuses closed on anything else (no raw re-validation).
    Returns the canonical taxonomy and its ``(namespace, tool)`` key set.
    """
    try:
        rebuilt: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        keys: set[tuple[str, str]] = set()
        for namespace, tools in taxonomy:
            if not isinstance(namespace, str) or not namespace:
                raise ValueError
            if not isinstance(tools, (list, tuple)) or not tools:
                raise ValueError
            canonical_tools: list[tuple[str, str]] = []
            for tool in tools:
                if not isinstance(tool, (list, tuple)) or len(tool) != 2:
                    raise ValueError
                tool_name, kind = tool
                if (
                    not isinstance(tool_name, str)
                    or not tool_name
                    or not isinstance(kind, str)
                    or kind not in _KINDS
                ):
                    raise ValueError
                canonical_tools.append((tool_name, kind))
                keys.add((namespace, tool_name))
            rebuilt.append((namespace, tuple(canonical_tools)))
    except (TypeError, ValueError):
        raise _error(
            REASON_TAXONOMY_INVALID,
            "The Codex declaration taxonomy is invalid",
            position=position,
            field="taxonomy",
        ) from None
    return tuple(rebuilt), keys


def _check_definitions(
    definitions: Mapping[tuple[str, str], Any] | None,
    keys: set[tuple[str, str]],
    position: int,
) -> None:
    """Fail closed unless the supplied definitions cover the taxonomy
    exactly (reference provenance, never a content check)."""
    if definitions is None:
        return
    if not isinstance(definitions, Mapping):
        raise _error(
            REASON_DEFINITIONS_MISMATCH,
            "The Codex declaration definitions are invalid",
            position=position,
            field="definitions",
        )
    provided = set(definitions)
    if provided != keys:
        raise _error(
            REASON_DEFINITIONS_MISMATCH,
            "The Codex declaration definitions do not match the taxonomy",
            position=position,
            field="definitions",
            observed=len(provided),
            limit=len(keys),
        )


def analyze_codex_tool_history(
    events: Sequence[CodexToolHistoryEvent],
    *,
    mode: str,
    max_items: int,
) -> CodexToolHistoryFacts:
    """Analyze validated declaration/call events into bounded facts.

    ``events`` is the caller's chronological sequence of ALREADY validated
    facts (declarations from the policy-owned per-declaration validation,
    calls/outputs from the validated input items, removals from
    :func:`parse_codex_removal_notice`).  ``mode`` is the explicit
    profile-declared mode; ``max_items`` is the explicit request item
    bound (positions are 0-based indices into it).  Every unknown or
    ambiguous transition raises :class:`CodexToolHistoryError` with a
    fixed safe reason code and position.  The inputs are never mutated.
    """
    if mode not in _MODES:
        raise _error(
            REASON_MODE_UNSUPPORTED,
            "The Codex tool history mode is not supported",
            field="mode",
        )
    if (
        not isinstance(max_items, int)
        or isinstance(max_items, bool)
        or max_items < 1
    ):
        raise _error(
            REASON_MAX_ITEMS_INVALID,
            "The Codex tool history item bound is invalid",
            field="max_items",
            limit=max_items if isinstance(max_items, int) else None,
        )
    if not isinstance(events, (list, tuple)):
        raise _error(
            REASON_EVENT_INVALID,
            "The Codex tool history event sequence is invalid",
            field="events",
        )
    if len(events) > max_items:
        raise _error(
            REASON_TOO_MANY_EVENTS,
            "The Codex tool history has too many events",
            field="events",
            observed=len(events),
            limit=max_items,
        )

    # active: namespace -> {tool name: declared kind}, in declaration order
    active: dict[str, dict[str, str]] = {}
    definitions: dict[tuple[str, str], Any] = {}
    definitions_mode = False
    steps: list[CodexToolHistoryStep] = []
    bindings: dict[str, CodexToolBinding] = {}
    completed: set[str] = set()
    seen_output_ids: set[str] = set()
    previous_position = -1

    for event in events:
        if not isinstance(
            event,
            (
                CodexToolDeclarationEvent,
                CodexToolRemovalEvent,
                CodexToolCallEvent,
                CodexToolCallOutputEvent,
            ),
        ):
            raise _error(
                REASON_EVENT_INVALID,
                "The Codex tool history event is invalid",
                field="events",
            )
        position = event.position
        if not isinstance(position, int) or isinstance(position, bool) or position < 0:
            raise _error(
                REASON_POSITION_OUT_OF_RANGE,
                "The Codex tool history position is out of range",
                position=position if isinstance(position, int) else None,
                field="position",
                limit=max_items,
            )
        if position >= max_items:
            raise _error(
                REASON_POSITION_OUT_OF_RANGE,
                "The Codex tool history position is out of range",
                position=position,
                field="position",
                observed=position,
                limit=max_items,
            )
        if position <= previous_position:
            raise _error(
                REASON_POSITION_NOT_MONOTONIC,
                "The Codex tool history positions must be strictly increasing",
                position=position,
                field="position",
            )
        previous_position = position

        if isinstance(event, CodexToolDeclarationEvent):
            canonical, keys = _canonical_taxonomy(event.taxonomy, position)
            if event.definitions is None and definitions_mode:
                raise _error(
                    REASON_DEFINITIONS_INCONSISTENT,
                    "The Codex declaration definitions mode is inconsistent",
                    position=position,
                    field="definitions",
                )
            _check_definitions(event.definitions, keys, position)
            if event.definitions is not None:
                definitions_mode = True
            if mode == MODE_FULL_SNAPSHOT:
                active.clear()
                definitions.clear()
                detail = "snapshot"
                for namespace, tools in canonical:
                    active[namespace] = {tool: kind for tool, kind in tools}
                if event.definitions is not None:
                    definitions.update(event.definitions)
            else:
                detail = "update"
                for namespace, tools in canonical:
                    slot = active.setdefault(namespace, {})
                    for tool, kind in tools:
                        slot[tool] = kind
                if event.definitions is not None:
                    definitions.update(event.definitions)
            steps.append(
                CodexToolHistoryStep(
                    position=position, kind="declaration", detail=detail
                )
            )
        elif isinstance(event, CodexToolRemovalEvent):
            if mode == MODE_FULL_SNAPSHOT:
                raise _error(
                    REASON_NOTICE_IN_SNAPSHOT_MODE,
                    "The Codex removal notice is not supported in snapshot mode",
                    position=position,
                    field="removal",
                )
            for namespace in sorted(event.namespaces):
                if namespace not in active:
                    raise _error(
                        REASON_REMOVAL_UNKNOWN,
                        "The Codex removal notice names an unknown namespace",
                        position=position,
                        field="removal.namespaces",
                    )
            for namespace, tool in sorted(event.tools):
                if namespace not in active or tool not in active[namespace]:
                    raise _error(
                        REASON_REMOVAL_UNKNOWN,
                        "The Codex removal notice names an unknown tool",
                        position=position,
                        field="removal.tools",
                    )
            for namespace in event.namespaces:
                del active[namespace]
            for key in [key for key in definitions if key[0] in event.namespaces]:
                del definitions[key]
            for namespace, tool in event.tools:
                del active[namespace][tool]
                definitions.pop((namespace, tool), None)
            steps.append(
                CodexToolHistoryStep(
                    position=position,
                    kind="removal",
                    detail="removed",
                    namespaces=event.namespaces,
                    tools=event.tools,
                )
            )
        elif isinstance(event, CodexToolCallEvent):
            if event.kind not in _KINDS:
                raise _error(
                    REASON_CALL_KIND_INVALID,
                    "The Codex tool call kind is invalid",
                    position=position,
                    field="call.kind",
                )
            if event.call_id in bindings:
                raise _error(
                    REASON_CALL_ID_REPEATED,
                    "The Codex tool call ID is repeated",
                    position=position,
                    field="call.id",
                )
            if event.namespace is None:
                # Existing-policy law: match the declared local tool by
                # name AND type; require exactly one unambiguous match.
                matches = [
                    (namespace, tool, kind)
                    for namespace, slot in active.items()
                    for tool, kind in slot.items()
                    if tool == event.name and kind == event.kind
                ]
                if not matches:
                    raise _error(
                        REASON_CALL_NOT_DECLARED,
                        "The Codex tool call is not declared at its position",
                        position=position,
                        field="call.name",
                    )
                if len(matches) > 1:
                    raise _error(
                        REASON_CALL_AMBIGUOUS,
                        "The Codex tool call name is ambiguous at its position",
                        position=position,
                        field="call.name",
                        observed=len(matches),
                        limit=1,
                    )
                namespace, name, declared_kind = matches[0]
            else:
                slot = active.get(event.namespace)
                if slot is None or event.name not in slot:
                    raise _error(
                        REASON_CALL_NOT_DECLARED,
                        "The Codex tool call is not declared at its position",
                        position=position,
                        field="call.name",
                    )
                namespace, name = event.namespace, event.name
                declared_kind = slot[event.name]
            if declared_kind != event.kind:
                raise _error(
                    REASON_CALL_KIND_MISMATCH,
                    "The Codex tool call kind does not match the declaration",
                    position=position,
                    field="call.kind",
                )
            binding: CodexToolBinding = (namespace, name, declared_kind)
            bindings[event.call_id] = binding
            steps.append(
                CodexToolHistoryStep(
                    position=position,
                    kind="call",
                    detail="bound",
                    call_id=event.call_id,
                    binding=binding,
                    definition=definitions.get((namespace, name)),
                )
            )
        else:  # CodexToolCallOutputEvent
            if event.kind not in _KINDS:
                raise _error(
                    REASON_CALL_KIND_INVALID,
                    "The Codex tool call output kind is invalid",
                    position=position,
                    field="output.kind",
                )
            if event.call_id not in bindings:
                raise _error(
                    REASON_OUTPUT_CALL_NOT_BOUND,
                    "The Codex tool call output references an unbound call",
                    position=position,
                    field="output.call_id",
                )
            if bindings[event.call_id][2] != event.kind:
                raise _error(
                    REASON_OUTPUT_KIND_MISMATCH,
                    "The Codex tool call output kind does not match the call",
                    position=position,
                    field="output.kind",
                )
            if event.call_id in completed:
                raise _error(
                    REASON_OUTPUT_CALL_REPEATED,
                    "The Codex tool call has a repeated output",
                    position=position,
                    field="output.call_id",
                )
            if event.output_id is not None:
                if event.output_id in seen_output_ids:
                    raise _error(
                        REASON_OUTPUT_ID_REPEATED,
                        "The Codex tool call output ID is repeated",
                        position=position,
                        field="output.id",
                    )
                seen_output_ids.add(event.output_id)
            completed.add(event.call_id)
            steps.append(
                CodexToolHistoryStep(
                    position=position,
                    kind="call_output",
                    detail="completed",
                    call_id=event.call_id,
                )
            )

    final_taxonomy: CodexToolTaxonomy = tuple(
        (namespace, tuple(sorted(slot.items())))
        for namespace, slot in active.items()
    )
    pending = frozenset(bindings) - frozenset(completed)
    return CodexToolHistoryFacts(
        mode=mode,
        steps=tuple(steps),
        active_taxonomy=final_taxonomy,
        call_bindings=types.MappingProxyType(bindings),
        active_definitions=types.MappingProxyType(definitions),
        pending_call_ids=pending,
    )

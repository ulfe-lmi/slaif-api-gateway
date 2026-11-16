"""Focused 226-a tests for the pure Codex declaration-history helper."""

import copy

import pytest

from slaif_gateway.services.codex_tool_history import (
    DEFAULT_REMOVED_NAMESPACES_HEADER,
    DEFAULT_REMOVED_TOOLS_HEADER,
    CodexToolCallEvent,
    CodexToolCallOutputEvent,
    CodexToolDeclarationEvent,
    CodexToolHistoryError,
    CodexToolRemovalEvent,
    MODE_FULL_SNAPSHOT,
    MODE_POSITIONAL_UPDATES,
    analyze_codex_tool_history,
    parse_codex_removal_notice,
)

NS = "functions"
NS2 = "collaboration"
NS3 = "mcp__codex_tui"
T_EXEC = ((NS, (("exec", "custom"), ("search", "function"))),)
T_EXEC_FN = ((NS, (("exec", "function"), ("search", "function"))),)
T_EXTRA = ((NS, (("exec", "custom"), ("search", "function"), ("render", "function"))),)
T_SORTED_EXTRA = ((NS, (("exec", "custom"), ("render", "function"), ("search", "function"))),)
T_SECOND_NS = ((NS, (("exec", "custom"),)), (NS2, (("ask", "custom"),)),)


def decl(position, taxonomy, item_id=None, definitions=None):
    return CodexToolDeclarationEvent(
        taxonomy=taxonomy,
        position=position,
        item_id=item_id,
        definitions=definitions,
    )


def call(position, call_id, namespace, name, kind="function"):
    return CodexToolCallEvent(
        call_id=call_id, namespace=namespace, name=name, kind=kind, position=position
    )


def out(position, call_id, kind="function", output_id=None):
    return CodexToolCallOutputEvent(
        call_id=call_id, kind=kind, position=position, output_id=output_id
    )


def removal(position, namespaces=(), tools=()):
    return CodexToolRemovalEvent(
        namespaces=frozenset(namespaces),
        tools=frozenset(tools),
        position=position,
    )


def analyze(events, mode=MODE_POSITIONAL_UPDATES, max_items=512):
    return analyze_codex_tool_history(events, mode=mode, max_items=max_items)


def reason(excinfo):
    return excinfo.value.reason_code


# --- explicit modes ---------------------------------------------------------


def test_unknown_mode_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze([decl(0, T_EXEC)], mode="whatever", max_items=10)
    assert reason(exc) == "codex_tool_history_mode_unsupported"


def test_absent_first_declaration_keeps_empty_catalog():
    facts = analyze([], mode=MODE_POSITIONAL_UPDATES, max_items=16)
    assert facts.active_taxonomy == ()
    assert len(facts.call_bindings) == 0
    assert facts.pending_call_ids == frozenset()
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze([call(0, "c1", NS, "exec", "custom")], max_items=16)
    assert reason(exc) == "codex_tool_history_call_not_declared"


# --- single full set (full_snapshot mode) -----------------------------------


def test_single_full_set_snapshot_mode():
    facts = analyze([decl(0, T_EXEC, item_id="at-1")], mode=MODE_FULL_SNAPSHOT)
    assert facts.mode == MODE_FULL_SNAPSHOT
    assert facts.active_taxonomy == T_EXEC
    assert facts.steps[0].kind == "declaration"
    assert facts.steps[0].detail == "snapshot"


def test_snapshot_replaces_catalog_completely():
    facts = analyze(
        [
            decl(0, T_EXTRA, item_id="at-1"),
            decl(2, T_EXEC, item_id="at-2"),
            call(3, "c1", NS, "exec", "custom"),
        ],
        mode=MODE_FULL_SNAPSHOT,
    )
    assert facts.active_taxonomy == T_EXEC
    assert facts.call_bindings == {"c1": (NS, "exec", "custom")}
    # "render" dropped by the second snapshot is no longer callable.
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXTRA, item_id="at-1"),
                decl(2, T_EXEC, item_id="at-2"),
                call(3, "c1", NS, "render", "function"),
            ],
            mode=MODE_FULL_SNAPSHOT,
        )
    assert reason(exc) == "codex_tool_history_call_not_declared"


def test_removal_notice_refused_in_snapshot_mode():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [decl(0, T_EXEC), removal(1, namespaces={NS})],
            mode=MODE_FULL_SNAPSHOT,
        )
    assert reason(exc) == "codex_tool_history_notice_in_snapshot_mode"


# --- positional updates: identical/equivalent, protocol IDs inert -----------


def test_identical_updates_with_same_and_different_protocol_ids():
    facts = analyze(
        [
            decl(0, T_EXEC, item_id="at-1"),
            decl(2, T_EXEC, item_id="at-1"),  # repeated inert ID: fine
            decl(4, T_EXEC, item_id=None),    # absent ID: fine
        ],
        max_items=16,
    )
    assert facts.active_taxonomy == T_EXEC
    assert [step.detail for step in facts.steps] == ["update", "update", "update"]


# --- successive add / remove / reintroduce ----------------------------------


def test_successive_add_remove_reintroduce():
    facts = analyze(
        [
            decl(0, T_EXEC, item_id="at-1"),
            removal(2, tools={(NS, "search")}),
            call(3, "c1", NS, "exec", "custom"),
            decl(5, ((NS, (("search", "function"),)),), item_id="at-2"),
            call(6, "c2", NS, "search", "function"),
        ],
        max_items=16,
    )
    assert facts.call_bindings["c1"] == (NS, "exec", "custom")
    assert facts.call_bindings["c2"] == (NS, "search", "function")
    assert facts.active_taxonomy == T_EXEC


def test_call_between_removal_and_reintroduce_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXEC, item_id="at-1"),
                removal(2, tools={(NS, "search")}),
                call(3, "c1", NS, "search", "function"),
            ],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_call_not_declared"


def test_new_call_after_removal_refused_and_historical_binding_retained():
    facts = analyze(
        [
            decl(0, T_EXEC, item_id="at-1"),
            call(1, "c1", NS, "search", "function"),
            removal(2, tools={(NS, "search")}),
        ],
        max_items=16,
    )
    # The historical call stays bound to its ORIGINAL identity.
    assert facts.call_bindings["c1"] == (NS, "search", "function")
    assert facts.pending_call_ids == frozenset({"c1"})
    # A new call to the removed tool is refused.
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXEC, item_id="at-1"),
                call(1, "c1", NS, "search", "function"),
                removal(2, tools={(NS, "search")}),
                call(3, "c2", NS, "search", "function"),
            ],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_call_not_declared"


def test_removal_of_unknown_tool_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [decl(0, T_EXEC, item_id="at-1"), removal(1, tools={(NS2, "ask")})],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_removal_unknown"
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [decl(0, T_EXEC, item_id="at-1"), removal(1, namespaces={NS2})],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_removal_unknown"


# --- same-name function/custom change ----------------------------------------


def test_same_name_kind_change_rebinds_only_later_calls():
    facts = analyze(
        [
            decl(0, T_EXEC, item_id="at-1"),
            call(1, "c1", NS, "exec", "custom"),
            decl(2, T_EXEC_FN, item_id="at-2"),
            call(3, "c2", NS, "exec", "function"),
        ],
        max_items=16,
    )
    assert facts.call_bindings["c1"] == (NS, "exec", "custom")
    assert facts.call_bindings["c2"] == (NS, "exec", "function")
    assert facts.active_taxonomy == T_EXEC_FN


def test_call_kind_mismatch_with_declaration_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [decl(0, T_EXEC, item_id="at-1"), call(1, "c1", NS, "exec", "function")],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_call_kind_mismatch"
    # After the kind change, the OLD kind is a mismatch at the new position.
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXEC, item_id="at-1"),
                decl(2, T_EXEC_FN, item_id="at-2"),
                call(3, "c1", NS, "exec", "custom"),
            ],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_call_kind_mismatch"


# --- namespace=None resolution law ---------------------------------------------


def test_none_namespace_resolves_one_unambiguous_name_kind_match():
    facts = analyze(
        [
            decl(0, T_SECOND_NS, item_id="at-1"),
            call(1, "c1", None, "exec", "custom"),
        ],
        max_items=16,
    )
    assert facts.call_bindings["c1"] == (NS, "exec", "custom")


def test_none_namespace_zero_matches_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [decl(0, T_EXEC, item_id="at-1"), call(1, "c1", None, "absent", "custom")],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_call_not_declared"
    # Same name but a different kind is not a match.
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [decl(0, T_EXEC, item_id="at-1"), call(1, "c1", None, "exec", "function")],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_call_not_declared"


def test_none_namespace_ambiguous_refused():
    dual = (
        (NS, (("shared", "function"),)),
        (NS2, (("shared", "function"),)),
    )
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [decl(0, dual, item_id="at-1"), call(1, "c1", None, "shared", "function")],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_call_ambiguous"
    assert exc.value.observed == 2
    assert exc.value.limit == 1


# --- call position law --------------------------------------------------------


def test_call_before_declaration_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [call(0, "c1", NS, "exec", "custom"), decl(1, T_EXEC, item_id="at-1")],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_call_not_declared"
    assert exc.value.position == 0


def test_pending_call_cannot_be_rebound_by_metadata_updates():
    facts = analyze(
        [
            decl(0, T_EXEC, item_id="at-1"),
            call(1, "c1", NS, "exec", "custom"),
            decl(2, T_EXEC_FN, item_id="at-2"),  # redefinition
            decl(4, T_EXEC, item_id="at-3"),     # revert
            decl(6, T_EXTRA, item_id="at-4"),    # growth
        ],
        max_items=16,
    )
    # The pending call keeps its position-bound identity through all updates.
    assert facts.call_bindings["c1"] == (NS, "exec", "custom")
    assert facts.pending_call_ids == frozenset({"c1"})
    # Re-issuing the same call ID is refused, not silently rebound.
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXEC, item_id="at-1"),
                call(1, "c1", NS, "exec", "custom"),
                call(2, "c1", NS, "exec", "function"),
            ],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_call_id_repeated"


# --- repeated IDs, mismatched and repeated outputs ------------------------------


def test_repeated_call_ids_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXEC),
                call(1, "c1", NS, "exec", "custom"),
                call(2, "c1", NS, "search", "function"),
            ],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_call_id_repeated"


def test_mismatched_outputs_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXEC),
                call(1, "c1", NS, "exec", "custom"),
                out(2, "c2", kind="custom", output_id="o1"),
            ],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_output_call_not_bound"


def test_output_kind_mismatch_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXEC),
                call(1, "c1", NS, "exec", "custom"),
                out(2, "c1", kind="function", output_id="o1"),
            ],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_output_kind_mismatch"


def test_repeated_output_for_one_call_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXEC),
                call(1, "c1", NS, "exec", "custom"),
                out(2, "c1", kind="custom", output_id="o1"),
                out(3, "c1", kind="custom", output_id="o2"),
            ],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_output_call_repeated"


def test_repeated_output_ids_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXEC),
                call(1, "c1", NS, "exec", "custom"),
                call(2, "c2", NS, "search", "function"),
                out(3, "c1", kind="custom", output_id="o1"),
                out(4, "c2", kind="function", output_id="o1"),
            ],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_output_id_repeated"


def test_output_completes_pending_call():
    facts = analyze(
        [
            decl(0, T_EXEC),
            call(1, "c1", NS, "exec", "custom"),
            out(2, "c1", kind="custom", output_id="o1"),
            call(3, "c2", NS, "search", "function"),
        ],
        max_items=16,
    )
    assert facts.pending_call_ids == frozenset({"c2"})
    assert [step.kind for step in facts.steps] == [
        "declaration",
        "call",
        "call_output",
        "call",
    ]


# --- synthetic index 265 under an explicit 512-item configuration -------------


def _big_history():
    events = [decl(0, T_EXEC, item_id="at-1")]
    for i in range(52):
        position_call = 1 + i * 5
        events.append(call(position_call, f"c{i:02d}", NS, "exec", "custom"))
        events.append(out(position_call + 1, f"c{i:02d}", kind="custom", output_id=f"o{i:02d}"))
    events.append(decl(265, T_EXTRA, item_id="at-2"))
    events.append(call(266, "c-late", NS, "render", "function"))
    return events


def test_second_declaration_at_index_265_under_explicit_512_items():
    facts = analyze(_big_history(), max_items=512)
    assert facts.call_bindings["c-late"] == (NS, "render", "function")
    assert facts.active_taxonomy == T_SORTED_EXTRA
    positions = [step.position for step in facts.steps]
    assert positions == sorted(positions)
    assert 265 in positions
    assert len(facts.call_bindings) == 53


def test_position_at_the_explicit_bound_is_out_of_range():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze([decl(0, T_EXEC), decl(512, T_EXTRA)], max_items=512)
    assert reason(exc) == "codex_tool_history_position_out_of_range"
    assert exc.value.observed == 512
    assert exc.value.limit == 512


# --- resource bounds and sequence law ------------------------------------------


def test_too_many_events_refused():
    events = [decl(0, T_EXEC)] + [
        call(i * 2, f"c{i:03d}", NS, "exec", "custom") for i in range(1, 12)
    ]
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(events, max_items=5)
    assert reason(exc) == "codex_tool_history_too_many_events"
    assert exc.value.observed == 12
    assert exc.value.limit == 5


@pytest.mark.parametrize("bad", [0, -1, True, "512", None])
def test_invalid_max_items_refused(bad):
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze([decl(0, T_EXEC)], max_items=bad)
    assert reason(exc) == "codex_tool_history_max_items_invalid"


def test_non_monotonic_positions_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [decl(0, T_EXEC), decl(3, T_EXTRA), decl(2, T_EXEC)],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_position_not_monotonic"
    assert exc.value.position == 2


def test_negative_position_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze([decl(-1, T_EXEC)], max_items=16)
    assert reason(exc) == "codex_tool_history_position_out_of_range"


# --- no mutation, no ordinary-item loss, no reordering --------------------------


def test_inputs_not_mutated_and_event_order_preserved():
    events = [
        decl(0, T_EXEC, item_id="at-1"),
        call(1, "c1", NS, "exec", "custom"),
        removal(2, tools={(NS, "search")}),
        decl(3, T_EXEC, item_id="at-2"),
        out(4, "c1", kind="custom", output_id="o1"),
    ]
    snapshot = copy.deepcopy(events)
    facts = analyze(events, max_items=16)
    assert events == snapshot
    assert [(step.kind, step.position) for step in facts.steps] == [
        ("declaration", 0),
        ("call", 1),
        ("removal", 2),
        ("declaration", 3),
        ("call_output", 4),
    ]


def test_invalid_taxonomy_structure_refused_without_echo():
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze([decl(0, ((NS, (("exec", "weird-kind"),)),))], max_items=16)
    assert reason(exc) == "codex_tool_history_taxonomy_invalid"


# --- active definitions provenance (references, never copies) -------------------


def test_definitions_provenance_tracked_and_referenced():
    d1_exec = {"type": "custom", "name": "exec", "format": {"type": "grammar", "syntax": "lark"}}
    d1_search = {"type": "function", "name": "search"}
    defs1 = {(NS, "exec"): d1_exec, (NS, "search"): d1_search}
    d2_exec = {"type": "function", "name": "exec"}
    defs2 = {(NS, "exec"): d2_exec, (NS, "search"): d1_search}
    facts = analyze(
        [
            decl(0, T_EXEC, item_id="at-1", definitions=defs1),
            decl(2, T_EXEC_FN, item_id="at-2", definitions=defs2),
        ],
        max_items=16,
    )
    assert facts.active_definitions[(NS, "exec")] is d2_exec
    assert facts.active_definitions[(NS, "search")] is d1_search
    assert len(facts.active_definitions) == 2


def test_definitions_dropped_on_removal_and_replaced_on_snapshot():
    d1 = {(NS, "exec"): {"a": 1}, (NS, "search"): {"b": 2}}
    facts = analyze(
        [
            decl(0, T_EXEC, item_id="at-1", definitions=d1),
            removal(1, tools={(NS, "search")}),
        ],
        max_items=16,
    )
    assert (NS, "search") not in facts.active_definitions
    assert (NS, "exec") in facts.active_definitions
    d2 = {(NS2, "ask"): {"c": 3}}
    snapshot = analyze(
        [
            decl(0, T_EXEC, item_id="at-1", definitions=d1),
            decl(1, ((NS2, (("ask", "custom"),)),), item_id="at-2", definitions=d2),
        ],
        mode=MODE_FULL_SNAPSHOT,
        max_items=16,
    )
    assert list(snapshot.active_definitions) == [(NS2, "ask")]
    assert snapshot.active_definitions[(NS2, "ask")] is d2[(NS2, "ask")]


def test_definitions_mode_must_be_consistent():
    d1 = {(NS, "exec"): {"a": 1}, (NS, "search"): {"b": 2}}
    # Update mode: an update that omits definitions after definitions
    # started is an explicit mismatch, not a silent stale state.
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXEC, item_id="at-1", definitions=d1),
                decl(1, T_EXEC_FN, item_id="at-2"),
            ],
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_definitions_inconsistent"
    # Snapshot mode: same law.
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze(
            [
                decl(0, T_EXEC, item_id="at-1", definitions=d1),
                decl(1, T_EXEC_FN, item_id="at-2"),
            ],
            mode=MODE_FULL_SNAPSHOT,
            max_items=16,
        )
    assert reason(exc) == "codex_tool_history_definitions_inconsistent"
    # No-definition mode stays consistently definition-free.
    facts = analyze(
        [
            decl(0, T_EXEC, item_id="at-1"),
            decl(1, T_EXEC_FN, item_id="at-2"),
        ],
        max_items=16,
    )
    assert len(facts.active_definitions) == 0


def test_definition_provenance_at_call_position():
    d1_exec = {"type": "custom", "v": 1}
    d1_search = {"type": "function", "v": 1}
    d2_exec = {"type": "function", "v": 2}
    facts = analyze(
        [
            decl(0, T_EXEC, item_id="at-1", definitions={(NS, "exec"): d1_exec, (NS, "search"): d1_search}),
            call(1, "c1", NS, "exec", "custom"),
            decl(2, T_EXEC_FN, item_id="at-2", definitions={(NS, "exec"): d2_exec, (NS, "search"): d1_search}),
            call(3, "c2", NS, "exec", "function"),
        ],
        max_items=16,
    )
    call_steps = [s for s in facts.steps if s.kind == "call"]
    assert call_steps[0].definition is d1_exec
    assert call_steps[1].definition is d2_exec
    # No-definition mode: provenance reference is simply absent.
    bare = analyze([decl(0, T_EXEC), call(1, "c1", NS, "exec", "custom")], max_items=16)
    assert bare.steps[1].definition is None


def test_definitions_mismatch_refused():
    d1 = {(NS, "exec"): {"a": 1}}  # missing "search"
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze([decl(0, T_EXEC, item_id="at-1", definitions=d1)], max_items=16)
    assert reason(exc) == "codex_tool_history_definitions_mismatch"
    d2 = {(NS, "exec"): {}, (NS, "search"): {}, (NS, "extra"): {}}  # extra key
    with pytest.raises(CodexToolHistoryError) as exc:
        analyze([decl(0, T_EXEC, item_id="at-1", definitions=d2)], max_items=16)
    assert reason(exc) == "codex_tool_history_definitions_mismatch"


# --- truly immutable facts mappings ----------------------------------------------


def test_facts_mappings_are_immutable():
    facts = analyze(
        [
            decl(
                0,
                T_EXEC,
                item_id="at-1",
                definitions={(NS, "exec"): {"a": 1}, (NS, "search"): {"b": 2}},
            ),
            call(1, "c1", NS, "exec", "custom"),
        ],
        max_items=16,
    )
    with pytest.raises(TypeError):
        facts.call_bindings["c1"] = (NS, "exec", "function")
    with pytest.raises(TypeError):
        facts.active_definitions[(NS, "exec")] = {"z": 9}
    # Stdlib MappingProxyType: O(1) lookup, dict equality (stable
    # adapter interface shape), unhashable.
    assert facts.call_bindings == {"c1": (NS, "exec", "custom")}
    assert "c1" in facts.call_bindings
    with pytest.raises(TypeError):
        hash(facts.call_bindings)


def test_definition_content_never_appears_in_facts_repr():
    sentinel = "CANARY-DEFINITION-CONTENT-226"
    d1 = {(NS, "exec"): {"type": "custom", "definition": sentinel}, (NS, "search"): {"type": "function"}}
    facts = analyze(
        [
            decl(0, T_EXEC, item_id="at-1", definitions=d1),
            call(1, "c1", NS, "exec", "custom"),
        ],
        max_items=16,
    )
    # Definition objects are references for provenance, but their
    # content-bearing payloads must not leak into fact reprs.
    assert sentinel not in repr(facts)
    assert sentinel not in repr(facts.steps)
    assert sentinel not in repr(facts.steps[1])


# --- pinned removal-notice grammar ----------------------------------------------


def notice(namespaces=(), tools=()):
    sections = []
    if namespaces:
        sections.append(
            DEFAULT_REMOVED_NAMESPACES_HEADER
            + "".join("\n- " + name for name in sorted(namespaces))
        )
    if tools:
        sections.append(
            DEFAULT_REMOVED_TOOLS_HEADER
            + "".join("\n- " + f"{ns}.{tool}" for ns, tool in sorted(tools))
        )
    return "\n\n".join(sections)


def test_notice_both_sections_exact_grammar():
    parsed = parse_codex_removal_notice(
        notice(namespaces={NS2}, tools={(NS, "search")})
    )
    assert parsed.namespaces == frozenset({NS2})
    assert parsed.tools == frozenset({(NS, "search")})


def test_notice_single_section_either_kind():
    assert parse_codex_removal_notice(notice(namespaces={NS})).namespaces == frozenset({NS})
    single = parse_codex_removal_notice(notice(tools={(NS, "exec")}))
    assert single.tools == frozenset({(NS, "exec")})
    assert single.namespaces == frozenset()


def test_notice_custom_pinned_headers_accepted_when_passed():
    body = (
        "Custom namespace header:\n- " + NS2
        + "\n\nCustom tool header:\n- " + f"{NS}.search"
    )
    parsed = parse_codex_removal_notice(
        body,
        namespaces_header="Custom namespace header:",
        tools_header="Custom tool header:",
    )
    assert parsed.namespaces == frozenset({NS2})
    assert parsed.tools == frozenset({(NS, "search")})


def test_notice_unrecognized_header_or_prose_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(DEFAULT_REMOVED_TOOLS_HEADER + "\n- reworded")
    assert reason(exc) == "codex_removal_notice_name_invalid"
    # A well-formed entry list under an unpinned header is refused by the
    # header law (never inferred as a removal).
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice("Some other header:\n- " + NS + ".search")
    assert reason(exc) == "codex_removal_notice_header_unrecognized"
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice("The tools were removed earlier, I believe.")
    # Prose with no pinned header line and no "- name" entries is refused
    # by the section structure before any header comparison.
    assert reason(exc) == "codex_removal_notice_invalid"
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            DEFAULT_REMOVED_TOOLS_HEADER + "\n- " + NS + ".search\n\nextra section"
        )
    # The trailing bare section has no "- name" entries; the structure
    # check refuses before any header comparison.
    assert reason(exc) == "codex_removal_notice_invalid"


def test_notice_empty_and_oversized_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice("")
    assert reason(exc) == "codex_removal_notice_empty"
    big = notice(tools={(f"ns{i}", "t") for i in range(50)})
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(big, max_body_bytes=64)
    assert reason(exc) == "codex_removal_notice_body_too_large"
    assert exc.value.limit == 64


def test_notice_name_laws():
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            DEFAULT_REMOVED_NAMESPACES_HEADER + "\n- " + NS + "\n- " + NS
        )
    assert reason(exc) == "codex_removal_notice_name_duplicate"
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            DEFAULT_REMOVED_NAMESPACES_HEADER + "\n- has dot"
        )
    assert reason(exc) == "codex_removal_notice_name_invalid"
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            DEFAULT_REMOVED_TOOLS_HEADER + "\n- nodot"
        )
    assert reason(exc) == "codex_removal_notice_name_invalid"
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            DEFAULT_REMOVED_TOOLS_HEADER + "\n- a.b.c"
        )
    assert reason(exc) == "codex_removal_notice_name_invalid"
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            DEFAULT_REMOVED_TOOLS_HEADER + "\n- " + NS + ".search \n"
        )
    assert reason(exc) == "codex_removal_notice_name_invalid"
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            DEFAULT_REMOVED_TOOLS_HEADER
            + "\n- " + NS + ".search\n- " + NS + ".search"
        )
    assert reason(exc) == "codex_removal_notice_name_duplicate"


def test_notice_subsumed_tool_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            notice(namespaces={NS}, tools={(NS, "search")})
        )
    assert reason(exc) == "codex_removal_notice_subsumed"


def test_notice_section_order_count_and_repeat_laws():
    # Tools section before namespace section violates the pinned order.
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            notice(tools={(NS, "search")})
            + "\n\n"
            + notice(namespaces={NS2})
        )
    assert reason(exc) == "codex_removal_notice_invalid"
    # A header with no names is not a valid section.
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(DEFAULT_REMOVED_NAMESPACES_HEADER)
    assert reason(exc) == "codex_removal_notice_invalid"
    # A repeated section kind must not silently union.
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            notice(tools={(NS, "search")})
            + "\n\n"
            + notice(tools={(NS2, "ask")})
        )
    assert reason(exc) == "codex_removal_notice_section_repeated"


def test_notice_name_bound_explicit():
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            notice(tools={(NS, "search"), (NS2, "ask")}), max_names=1
        )
    assert reason(exc) == "codex_removal_notice_too_many_names"
    assert exc.value.observed == 2
    assert exc.value.limit == 1


def test_notice_parser_feeds_removal_event():
    parsed = parse_codex_removal_notice(notice(tools={(NS, "search")}))
    facts = analyze(
        [
            decl(0, T_EXEC, item_id="at-1"),
            call(1, "c1", NS, "search", "function"),
            removal(
                2,
                namespaces=parsed.namespaces,
                tools=parsed.tools,
            ),
        ],
        max_items=16,
    )
    assert facts.active_taxonomy == ((NS, (("exec", "custom"),)),)
    assert facts.call_bindings["c1"] == (NS, "search", "function")


def test_notice_non_string_body_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(b"")
    assert reason(exc) == "codex_removal_notice_invalid"


def test_notice_newline_header_refused():
    with pytest.raises(CodexToolHistoryError) as exc:
        parse_codex_removal_notice(
            "a\n\nb", namespaces_header="a", tools_header="b"
        )
    assert reason(exc) == "codex_removal_notice_invalid"

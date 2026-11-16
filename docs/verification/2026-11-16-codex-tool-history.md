# Codex declaration-history foundation (objective 226-a) — 2026-11-16

Staged groundwork for versioned Codex ``additional_tools`` declaration
history.  This round adds ONE new pure shared module, its focused unit
suite, and this record.  HTTP acceptance is deliberately UNCHANGED (the
single-``additional_tools``-item law and the 0.162 lowering remain in
force); gateway integration, profile promotion, and estimation arrive in
later same-PR rounds.

## Source provenance

Pinned official Codex CLI **``rust-v0.167.1``**, source commit
``0a94398fa60c4fac0e7659e4213a0a36e613dd46`` (tag ``rust-v0.167.1``),
read from a local pinned checkout that does not track moving upstream
main.  Seven root-fetched copies of the exact source files were
independently provided and verified byte-identical against that ref
(``cmp`` clean for every file; SHA-256 of the fetched copies):

| fetched file (SHA-256) | pinned path |
| --- | --- |
| ``/tmp/slaif-codex-01671-client.rs`` ``662cf64d10f4b0d7eaf3ad046e53b1eb6dcf8dfb3cb5a425a3c8c222adc05da5`` | ``core/src/client.rs`` |
| ``/tmp/slaif-codex-01671-client-common.rs`` ``43a540ecd99856644ec01c57708838779b118c3b583e218c9ef307e0dcefcb4b`` | ``core/src/client_common.rs`` |
| ``/tmp/slaif-codex-01671-turn.rs`` ``c4bbb7f36f58736963181fedb0e6f885ce8e99d6a70cc89bcbb0f475027c8a61`` | ``core/src/session/turn.rs`` |
| ``/tmp/slaif-codex-01671-step-context.rs`` ``372bc9b4cacf16d5ade275c0002562d49ffd9f673a03f336bf50dfb7743ec8c1`` | ``core/src/session/step_context.rs`` |
| ``/tmp/slaif-codex-01671-world-state.rs`` ``79aa91535e9c195b7ffab3d30ff1b5efda6737b24e17afb51899f9700110c08a`` | ``core/src/session/world_state.rs`` |
| ``/tmp/slaif-codex-01671-top-level-tools.rs`` ``6c241cfe0904af7595737dd5677a445e6d85f0191c59569dd5533edc8acf29b2`` | ``core/src/context/world_state/top_level_tools.rs`` |
| ``/tmp/slaif-codex-01671-models.rs`` ``daeb5bd499ed49b364be4c031e3c754f7fb39945531214c0b8fe00896eb3da82`` | ``protocol/src/models.rs`` |

No private request body, raw prompt/history, credential, or real
response ID is used or recorded here; the affected request is referred
to only by the operator-safe fact that a second ``additional_tools``
item sits at ``input[265]``.

## Source-derived wire findings (rust-v0.167.1)

- ``core/src/client.rs`` ``build_responses_request``: for Responses
  Lite the full current ``AdditionalTools`` prefix is inserted at input
  index zero **only when ``prompt.tools`` is nonempty**; its item ID is
  a deterministic UUIDv5 over the thread namespace and serialized tool
  payload (an ID is derivable metadata, not authority).
- ``core/src/session/turn.rs`` ``build_prompt``: with the default
  incremental-tools feature, ``prompt.tools`` keeps only hosted tool
  specs (``WebSearch``), so the full LOCAL prefix may be absent from a
  turn even though local tools exist in the session catalog.
- ``core/src/context/world_state/top_level_tools.rs``: incremental
  batches contain ONLY added/changed definitions (a namespace appears
  with only its changed members); one developer hint notice may precede
  a batch; removals are a separate standalone developer notice
  (content kind ``tools.removed_definition``) with two sections —
  removed whole namespaces, then individually removed
  ``namespace.tool`` names (members of a removed namespace are
  subsumed and not repeated) — built from configurable header strings
  (bundled defaults, each resolved at most 512 bytes upstream).
- ``protocol/src/models.rs`` ``clear_internal_chat_message_metadata_passthrough``
  (applied for non-OpenAI providers in ``client.rs``): the structured
  content-kind metadata is stripped before the wire, leaving only the
  plain configurable header text. A gateway therefore cannot rely on
  kind markers and must not parse arbitrary prose as removal authority.

Consequently no blanket positional rule ("first item = current set",
"last item = current set", "every item = full snapshot") or authority
union is justified by source.  The observed rejection proves only the
PRESENCE of a second item at ``input[265]`` — not its contents,
equivalence, cause, or the private client settings — and this record
makes no claim about that request.

## Implemented shared foundation

New module ``app/slaif_gateway/services/codex_tool_history.py`` (pure,
stdlib-only, no app imports):

- **Explicit modes.** ``full_snapshot`` (every declaration replaces the
  catalog; an absent first declaration legally means "no local
  tools") and ``positional_updates`` (declarations are adds/changes
  only; removals arrive as parsed notice facts).  Absence of a mode
  keeps legacy behavior because the gateway does not consult the
  helper yet.  Unknown modes fail closed.
- **Events** (all frozen dataclasses): validated declaration
  (canonical taxonomy + optional inert item ID + optional definition
  references keyed ``(namespace, tool)``), parsed removal notice, tool
  call (``namespace`` may be ``None``), tool call output (exact
  ``function``/``custom`` kind, optional output item ID).
- **Facts** (immutable ``CodexToolHistoryFacts``): applied
  chronological steps in caller order, final active taxonomy,
  ``call_bindings`` — the stable core-to-adapter shape: an immutable
  stdlib ``types.MappingProxyType`` mapping keyed by the ORIGINAL
  ``call_id`` to ``(namespace, name, kind)`` — pending call IDs, and
  ``active_definitions`` (the caller's validated definition objects
  **by reference**, never copied or read).  Call steps additionally
  carry the definition reference **at the call position**, so later
  core can detect schema/type transport conflicts without rebuilding a
  second lifecycle.
- **Laws.** A call binds to the identity active at its own position,
  immutably; a later declaration never authorizes a preceding call; a
  removed tool cannot be newly called; a same-name
  function/custom redefinition rebinds only LATER calls; a
  ``namespace=None`` call resolves by ONE unambiguous ``(name, kind)``
  match (the existing policy's name-and-type law, with ambiguity
  refused); call IDs and output IDs are unique; exactly one output per
  call; output kind must equal the bound call's kind; a declaration
  sequence is either consistently definition-free or every declaration
  supplies exactly its taxonomy's definitions (no silent stale
  references); positions are strictly increasing within the explicit
  ``max_items`` item bound; removals must name only currently active
  tools.  Every refusal is a fixed
  ``CodexToolHistoryError`` with a stable content-free ``reason_code``,
  the event ``position``, ``field``, and ``observed``/``limit``
  counts — no raw request content is echoed.
- **Pinned removal-notice grammar**
  (``parse_codex_removal_notice``): at most two sections joined by
  ``"\n\n"``; each section is its EXACT pinned header line (the bundled
  upstream defaults, or caller-supplied pinned values) followed by one
  or more ``"- " name`` lines; namespace section first (bare names, no
  dot) then tool section (``namespace.tool``, exactly one dot);
  no repeated section kind; no duplicate names; no tool subsumed by a
  removed namespace in the same notice; explicit
  ``max_names``/``max_body_bytes`` bounds.  Anything else — prose,
  reworded headers, unknown sections — is a fixed safe refusal.

**Scope honesty.**  The helper is not a validator (raw declarations
must already have passed the existing policy-owned per-declaration
taxonomy/schema validation, including invalid earlier entries) and not
a replay authority.  It enforces call/output ID uniqueness, one-output
per call, and kind linkage over the events it is supplied; it does NOT
see or enforce replay item ID checks for other item families
(reasoning, compaction, encrypted content, message IDs) or HMAC replay
ownership — those remain with their existing owners.  It grants no
execution or persistence and carries no secrets.

## Verification

- Focused unit suite
  ``tests/unit/test_codex_tool_history.py``: 53 tests (49 test
functions, one parametrized) covering the
  single full set; identical/equivalent updates with same, different
  and absent protocol IDs; successive add/remove/reintroduce;
  same-name function/custom changes; call-before-declaration refusal;
  historical bindings retained after removal; new-calls-after-removal
  refusal; pending calls un-rebindable; repeated call/output IDs and
  mismatched/repeated outputs; a synthetic second declaration at
  ``input[265]`` under an explicit 512-item configuration (with the
  boundary position refused); explicit resource bounds; no mutation,
  no event loss, no reordering; kind-mismatch refusal;
  ``namespace=None`` resolution (unique/zero/ambiguous); consistent
  definition mode with reference provenance at declaration and call
  position; and the full pinned notice grammar including every
  refusal law.  All pass (``.venv/bin/python -m pytest
  tests/unit/test_codex_tool_history.py -p no:warnings -q``).
- Ruff on the changed Python files: All checks passed.
- No real provider/Codex process, production database, or credentials
  were used; no template, CSS, schema, or frozen profile/fixture
  digest changed.

**NOT RUN in this round** (required for the final integrated head):
the full unit matrix, the isolated-PostgreSQL replay/local-server/
accounting tests, and hosted CI on the final head.  The normal-admin
byte oracle need not rerun (no template/CSS change).

## Documentation-impact statement

This round changes: one new pure module
(``services/codex_tool_history.py``), one new focused unit test file,
this verification record, and ONE link from
``responses-compatibility.md``.  All existing contracts — request
policy, the single-item law, the 0.162 lowering, response validation,
replay ownership, accounting, estimation, and the frozen revision-15
profile identity (module ID, revision, fixture digest) — are
unchanged.  Gateway/policy integration, profile promotion (including
any audited migrate-key-profile identity), route-aware admission
estimation, and adapter binding integration are PENDING in later
same-PR rounds, which must update
``responses-compatibility.md``, ``provider-forwarding-contract.md``,
``accounting.md``, ``security-model.md``, the client preset/module
docs, and deployment/rollback documentation.  This is a staged
implementation, not completion of the reported bug.

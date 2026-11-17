# Codex declaration history (objective 226, rounds a + b) — 2026-11-16

Versioned Codex ``additional_tools`` declaration-history support for the
``codex-0.162-responses-v1`` client module: the pure shared lifecycle module
(round a) plus its integration into the request policy, gateway, lowering,
replay ownership, output validation, registered transports, and admission
estimation under ONE new gated operator profile (round b).  Unit/request
fixtures are synthetic and providers are mocked; the PostgreSQL evidence
uses one REAL disposable PostgreSQL 16 instance.  No real private client
body, credential, or inference was used.

## Delivered feature

- A pure, stdlib-only lifecycle module that validates a bounded
  incremental declaration history (adds/changes plus pinned removal
  notices) and produces immutable facts: final active catalog, per-call
  bindings, and definition provenance at declaration and call position.
- One new operator profile DATA file (``codex-0.167.1.json``, revision 16,
  same module ID ``codex-0.162-responses-v1``) whose
  ``codex_tool_history_positional_updates`` feature activates the
  ``positional_updates`` lifecycle mode and
  ``allow_idless_tool_call_replay``.  The packaged default (revision 8) and
  every frozen legacy preset are unchanged.
- Request-policy integration: positional validation with request-local
  facts, exact lowering to the final active tools, replay-candidate
  ownership extraction (including the qualified ID-less law and a
  fail-closed completeness guard), and an output current-set guard for
  non-streaming and SSE responses.
- Transport integration on the already registered
  ``codex-0.162-responses-v1`` pairs (local coding, local vLLM, configured
  upstream LLM): per-call wire identity translation, a shared pure
  instruction-placement guard with one fixed safe refusal code, and a
  bounded codec-refusal accounting seam that preserves already-settled
  usage.
- Route-aware admission estimation anchored on the PREPARED body the
  resolved transport actually forwards (byte-based approximation), with the
  exact fixed representability codes preserved through the policy wrapper.
- Audited no-key-rotation profile migration/rollback documentation reusing
  the existing ``migrate-key-profile`` mechanism.

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
| ``/tmp/slaif-codex-01671-models.rs`` ``daeb5bd499ed49b364be4c031e3c754f7fb39945531214c0b8fe0096eb3da82`` | ``protocol/src/models.rs`` |

No private request body, raw prompt/history, credential, or real
response ID is used or recorded here; the motivating request is referred
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

## Final implementation

### Pure lifecycle helper (round a, relocated in round b)

``app/slaif_gateway/modules/codex_tool_history.py`` — pure, stdlib-only,
no app imports.  Round b relocated it from ``services/`` to ``modules/``
to satisfy the client-module no-gateway-authority-imports dependency gate
(no duplicated helper, no re-export wrapper); the relocation preserved the
round-a lifecycle logic, and round b additionally added the bounded
pinned-hint recognition helpers.

- **Explicit modes.** ``full_snapshot`` and ``positional_updates``; absent
  mode keeps legacy behavior; unknown modes fail closed.
- **Events** (frozen dataclasses): validated declaration (canonical
  taxonomy + optional inert item ID + definition references keyed
  ``(namespace, tool)``), parsed removal notice, tool call (``namespace``
  may be ``None``), tool call output (exact ``function``/``custom`` kind).
- **Facts** (immutable ``CodexToolHistoryFacts``): applied chronological
  steps, final active taxonomy, ``call_bindings`` — an immutable
  stdlib ``MappingProxyType`` mapping ORIGINAL ``call_id`` to
  ``(namespace, name, kind)`` — pending call IDs, and
  ``active_definitions`` (the caller's validated definition objects
  **by reference**).  Call steps carry the definition reference at the
  call position for later schema/type transport-conflict detection.
- **Laws.** A call binds to the identity active at its own position,
  immutably; a later declaration never authorizes a preceding call; a
  removed tool cannot be newly called; a same-name function/custom
  redefinition rebinds only LATER calls; a ``namespace=None`` call
  resolves by ONE unambiguous ``(name, kind)`` match (ambiguity and
  zero matches refuse); call/output IDs are unique; exactly one output
  per call; output kind equals the bound call's kind; the policy always
  supplies validated definition references for the selected taxonomy
  (production invariant); removals name only currently active tools.  Every refusal is a fixed
  ``CodexToolHistoryError`` with a stable content-free ``reason_code``,
  the event position, and bounded counts — no raw request content.
- **Pinned removal-notice grammar.** At most two sections joined by
  ``"\n\n"``; each section is the EXACT pinned header (bundled upstream
  defaults or caller-pinned values) plus one or more ``"- " name``
  lines; namespace section first, tool section second; no repeated
  section kind, duplicate names, or subsumed tools; explicit
  ``max_names``/``max_body_bytes`` bounds.  At the policy, only a
  developer message beginning with one of the EXACT pinned bundled
  headers is a recognition candidate; a recognized candidate that then
  fails the pinned grammar is a fixed safe refusal.  Every other
  developer message — including customized or reworded removal wording,
  which upstream metadata stripping makes indistinguishable from ordinary
  prose — is ordinary history, preserved with no removal or authorization
  effect: customized removal wording is unsupported, and the parser's
  direct refusal is not automatic detection of arbitrary customized
  developer prose.  An ordinary developer instruction is never an
  addition/authorization source.

Scope honesty: the helper is not a validator (raw declarations must
already pass the policy-owned per-declaration validation) and not a
replay authority (item-ID and HMAC ownership checks remain with their
existing owners).  It grants no execution or persistence and carries no
secrets.

### New gated profile DATA (round b)

``app/slaif_gateway/modules/clients/profiles/codex-0.167.1.json`` —
schema v2, module ID ``codex-0.162-responses-v1``, **revision 16**,
provenance ``rust-v0.167.1`` / ``0a94398fa60c4fac0e7659e4213a0a36e613dd46``,
registered in ``profiles/presets.json`` as preset ``codex-0.167.1``.
Its dialect feature ``codex_tool_history_positional_updates`` maps to
spec ``codex_tool_history_mode="positional_updates"`` and
``allow_idless_tool_call_replay=True``.  Canonical identity is the
loader digest **``cff9f7b56966eb2068fdbeb203fe04ac32890e34524200372c2d3f2a30e566ed``**
(``load_codex_profile_file(...).digest`` / ``module.fixture_sha256``) —
NOT the SHA-256 of the pretty-printed file.  The packaged default stays
``codex_0162.json`` revision 8 (digest
``1d1e5b05587d1a8bf1f90057e43e357b7b3627dc3268ec09108e5fafa52e6d11``);
frozen legacy presets are immutable.

The registry binds ONE concrete profile at bootstrap
(``bind_codex_0162_client_module``): same-identity re-initialization is an
idempotent no-op, the first different identity completes the one-shot
bootstrap, and any later different identity fails closed
(``codex_0162_bootstrap_locked``).  A process therefore serves exactly
one active profile data revision (see Deployment).

### Request policy integration (round b)

``services/responses_request_policy.py``:

- In ``positional_updates`` mode, ``apply()`` validates the full
  declaration history through the helper and stores request-local
  ``CodexToolHistoryFacts`` on the policy result (ephemeral, excluded
  from ``model_dump``).  Facts are reset on every public ``apply`` /
  ``apply_compact`` entry, so a reused policy instance never carries
  stale state.  A new-mode request with no declarations (including plain
  string input) materializes EMPTY active facts, so the output guard
  denies any generated tool call.
- ``codex_replay_request_candidates(...)`` extracts replay candidates
  with validated per-call bindings: in new mode EVERY actual
  function/custom call emits exactly one candidate from its immutable
  positional identity; an omitted namespace resolves from the trusted
  binding, an EXPLICIT contradicting namespace denies, and
  unbound/duplicate/missing-bound identities deny with fixed safe codes.
  ``require_call_completeness=True`` makes any extraction mismatch a
  fixed safe denial (never a silent omission).  ID-less replay is
  qualified only for the existing 0.149 module path OR the new lifecycle
  mode, AND only when the selected spec declares
  ``allow_idless_tool_call_replay``; the existing deferred same-key
  CALL-ID HMAC check remains.  Reasoning/compaction candidates and
  legacy/0147 compact behavior are unchanged.  Facts are naming-only:
  the gateway still verifies every candidate's key/route/provider
  HMAC.  Wired at the ``policy.apply`` provider-state-mixing check and
  ``handle_response_create`` ownership extraction.

### Lowering (round b)

``codex_0162_lower_positional_tool_history`` (``modules/clients/codex_0162.py``)
lowers the FULL validated history for the exact 0.162 x local pair under
the profile-selected mode: the final active catalog becomes top-level
``tools`` (first-seen declaration order; empty namespace groups omitted;
latest namespace-header semantics — a later header without description
clears that optional field); every ``additional_tools`` item and its
inert ID, every validated removal notice, and the EXACT pinned upstream
incremental hint when it is a standalone developer text immediately
preceding a validated declaration are compiled out; EVERY other input
item (ordinary messages, tool calls, outputs, IDs, non-adjacent hints)
is preserved in order.  A historical function/custom call that omits
``namespace`` is forwarded with its bound namespace MATERIALIZED from
the immutable ``facts.call_bindings`` entry keyed by the original call
ID (name/kind checked, never the current catalog union), so distinct
histories that later converge on the same final catalog still produce
distinct provider bodies; explicit namespaces, args, results, IDs, and
relative order are unchanged, and the policy representation/facts are
never mutated.  A non-empty top-level ``tools`` field, missing/foreign facts,
or non-list input fail closed.  The canonical incoming body remains the
validation/HMAC/resource/diagnostics representation.

### Transports and placement (round b)

- Local vLLM and configured upstream LLM translate historical calls with
  the validated per-call bindings (native wire names or portable
  ``tool_<label>_<sha256-24>`` names); ``preserve`` encodings forward the
  canonical body with no codec.
- The order-changing instruction-placement guard lives in the SHARED
  pure ``prepare_upstream_llm_body`` (run by both the production
  ``_prepare`` and the pre-admission core preview): a lifecycle request
  (non-``None`` bindings) on a ``leading_system_developer`` profile whose
  instructions do not already form the leading prefix is refused exactly
  with ``upstream_llm_bindings_placement_conflict`` (400, fixed safe
  message); prefix-only inputs remain representable; legacy
  ``bindings=None`` requests keep the existing reordering behavior.

### Output current-set guard (round b)

``responses_gateway._enforce_codex_positional_output_policy`` applies to
new-mode non-streaming output and SSE frames: generated function/custom
calls must name a tool in the FINAL active catalog (after removals);
malformed identities (missing/non-string name, non-string namespace)
refuse; with an empty catalog any generated tool call refuses.  The
guard runs after accounting settlement and before references/storage.

### Codec-refusal accounting seam (round b)

``ProviderResponse`` gains one optional ``repr=False`` str field
``safe_rejection_code`` (default ``None``; ``json_body`` stays
``Mapping[str, Any]``).  On an explicit lifecycle request, a codec
transport that rejects a removed/undeclared wire tool (local vLLM and
configured upstream) clears ``json_body={}``, ``text_body=None``,
``binary_body=None`` and sets the fixed code (e.g.
``vllm_tool_protocol_invalid``) while preserving the already-PARSED
usage/cost/provider metadata; on ``bindings=None`` the parse error
propagates unchanged (legacy behavior).  The core's normal settlement
settles that parsed usage, and only then does
``_reject_settled_codec_rejection`` — which refuses, it does not settle
— withhold the marked response with a fixed 502 (code passed through,
fixed content-free message) BEFORE replay references/storage/return: no
free release, no double finalization; no raw or partly decoded provider
output crosses the seam (exceptions, logs, persistence), and the denied
call receives no replay references.

### Admission estimation (round b)

``apply_codex_positional_prepared_estimate`` runs the resolved
transport's OWN pure preparation (``prepare_vllm_body`` for native vLLM
routes, ``prepare_upstream_llm_body`` for configured upstream routes,
exact canonical otherwise) over the actual lowered body and re-estimates
with the bounded prepared-JSON calculation: canonical JSON bytes of the
COMPLETE prepared input (list items or plain string; real IDs exactly
once as forwarded) plus forwarded ``instructions`` and the relevant
non-message fields PRESENT in the prepared body (``tools``, ``include``,
``parallel_tool_calls``, ``prompt_cache_key``, ``reasoning``, ``text``),
with the existing ``ceil(bytes/3)`` token convention.  This is a
byte-based approximation — not an exact tokenizer measurement and not a
mathematical no-overrun promise.  ``unadjusted_input_tokens`` anchors to
the prepared estimate so later route/media handling and revalidation
neither accumulate deltas nor restore stale canonical totals; the
canonical ``effective_body`` is preserved untouched for replay and
resource ownership.  A prepared body the transport itself would refuse
fails closed BEFORE any admission side effect, preserving the two known
fixed representability codes
(``upstream_llm_bindings_placement_conflict``,
``vllm_native_wire_identity_collision``) with status 400 and
appropriate param, and a generic safe ``responses_codex_tool_wire_invalid``
fallback for all other preparation failures — no raw provider message or
request content crosses the wrapper.  Raw byte/item/text/schema bounds
stay independent and always active; legacy (non-positional) profiles
retain their exact old estimator and ordering.

### Compact boundary (round b, verified)

The client-server registry pairs ``codex-0.162-responses-v1`` only with
local server modules, and ``handle_response_compact`` immediately
rejects the local coding auxiliary endpoint, so 0.167.1/0162 compact is
NOT a qualified transport; the denial is retained and frozen
0147/OpenAI compact behavior is unchanged.  Legacy compact may forward
declarations and retains their bytes; lifecycle/replay helpers remain
coherent for already-supported compact requests.

## Deployment and migration

- A process binds ONE active profile data revision at bootstrap (one-shot
  guarded binding; see above).  Loading revision 16 makes keys pinned to
  the packaged default (revision 8) or any other earlier revision STALE
  until explicitly migrated; the packaged default remains unchanged, so
  deployments that do not configure the new profile file are unaffected.
- Migration reuses the existing audited
  ``migrate-key-profile`` dry-run/apply/rollback mechanism with source
  and target full identities (module ID + data revision + canonical
  digest); pin preservation, restart, and configuration steps are
  documented in ``docs/upgrade-runbook.md``.  NO actual operator keys
  were migrated or rotated in this work, and no same-process one-key
  "canary" is claimed: while the process serves one active profile,
  other-pinned requests are denied closed until migrated or the process
  is restarted on the previous profile file (the rollback path).
- No data or schema migration was required or performed.

## Verification

### Accepted round-a component evidence (reused, not rerun)

- Shared helper suite ``tests/unit/test_codex_tool_history.py``:
  **54** tests (single full set; identical/equivalent updates with same,
  different and absent protocol IDs; successive add/remove/reintroduce;
  same-name function/custom changes; call-before-declaration refusal;
  historical bindings retained after removal; new-calls-after-removal
  refusal; pending calls un-rebindable; repeated call/output IDs and
  mismatched/repeated outputs; a synthetic second declaration at
  ``input[265]`` under an explicit 512-item configuration with the
  boundary position refused; explicit resource bounds; no mutation, no
  event loss, no reordering; kind-mismatch refusal; ``namespace=None``
  resolution (unique/zero/ambiguous); consistent definition mode with
  reference provenance at declaration and call position; the full pinned
  notice grammar including every refusal law).
- Adapter suites ``tests/unit/test_upstream_llm_adapter.py`` +
  ``tests/unit/test_local_coding_vllm.py`` at the round-a checkpoint:
  **103** tests (shared pure preparation parity, placement refusal,
  codec wire identity).  54 + 103 = **157** focused cases, plus
  governance 10 and Ruff/docs hygiene.  Root independently ran the
  helper suite (53 before the added canary) and the final adapter suite
  (103).  These round-a cases do NOT cover the b-round marker seam or
  the pure-preview wiring.

### Round-b focused evidence (this record's commits)

- Root's six-variant mocked marker-seam probe (round b; lifecycle/
  legacy across local vLLM, configured native_vllm, and configured
  function_tools): lifecycle retains parsed usage/cost metadata,
  clears the rejected body, keeps the fixed code out of ``repr``/
  errors; legacy codec refusal unchanged.  No provider/DB calls.
- New integration regression module
  ``tests/unit/test_codex_tool_history_replay_wiring.py``: **45** tests
  covering extractor ownership law (same-name-later-namespace binding,
  explicit-namespace contradiction, unbound/duplicate denial, ID-less
  qualification both modes, completeness denial, reasoning/compaction
  coexistence), policy-level positives (index-265 under an explicit
  512-item configuration, identical/equivalent repeated declarations,
  ``functions.exec`` function/custom transitions both directions with
  completed historical calls, same-name schema redefinition, missing
  key/route permission denials, provider-state-mixing denials including
  the union-drop case, predeclaration/removed-call/invalid-position/
  duplicate/unfinished guards, add-remove-reintroduce final catalog,
  content-free transition errors, reused-policy state reset,
  string-input and declaration-free-list empty facts), lowering
  (entire ordinary history preserved at explicit canonical indices with
  a non-adjacent hint retained and the adjacent hint compiled out; no
  mutation), both backends' prepared bodies (native ``functions.alpha``
  vs portable ``tool_functions_alpha_…``), prepared-estimate forwarded
  field counting with prompt-cache stripping and reanchoring
  idempotence, the pure-preview/transport placement refusal parity
  (prefix-only acceptance and legacy reordering preserved), the
  pre-admission refusal with the precise wire codes, the empty-catalog
  and post-removal output guards, and the codec-refusal settlement
  seam (local vLLM + configured upstream + core fixed-502 marker check
  with ``repr``/message canaries), and bound-namespace materialization
  in the provider copy (two valid namespace-less histories that later
  converge on the same final catalog produce distinct provider bodies;
  explicit-resolved vs previous implicit-binding parity across the
  native and portable preparations; the prepared estimate includes the
  materialized namespace bytes).
  Command: ``.venv/bin/python -m pytest
  -o addopts= tests/unit/test_codex_tool_history_replay_wiring.py`` —
  45 passed.
- Changed-component suites at the final integrated code head
  ``8a831a2b`` (superseding the ``ef6fe594`` pre-integration run of
  313 + 125):
  wiring 45 + request policy 214 + upstream LLM adapter 57 = **316
  passed**; Codex 0162/0149 roundtrip + local vLLM suites **125 passed**
  (441 total; both runs exit 0).
  Command: ``.venv/bin/python -m pytest -o addopts= -q
  tests/unit/test_codex_tool_history_replay_wiring.py
  tests/unit/test_responses_request_policy.py
  tests/unit/test_upstream_llm_adapter.py`` and ``.venv/bin/python -m
  pytest -o addopts= -q tests/unit/test_codex_0162_client_tools.py
  tests/unit/test_codex_0162_apply_patch.py
  tests/unit/test_codex_0149_local_roundtrip.py
  tests/unit/test_local_coding_vllm.py``.
- The 834-test focused matrix (14 files including streaming/replay/
  policy/codec suites) was green at checkpoint ``bdf5a7da`` and is
  superseded for the changed components by the runs above; the full unit
  suite runs ONCE at the final implementation head (recorded there).

### Owned PostgreSQL and final matrix (recorded at the final head)

- Owned disposable PostgreSQL 16 fixture (container ``slaif-oap226-pg16``,
  ``127.0.0.1:33934``, database ``slaif226test``; ``TEST_DATABASE_URL``
  delivered through a 0600 env file; no production DB, no password
  rotation, no raw DSN in evidence).
- Secondary-owned acceptance module
  ``tests/integration/test_codex_tool_history_postgres.py`` (owned-row
  HMAC route/provider denials, qualified ID-less success + forged/
  other-key/route negatives, codec settlement against real PostgreSQL,
  profile migration resume, final isolated PG matrix): **22** cases
  passed against the corrected source (exit 0) — A1–A5 ownership law
  (ambiguity bound to the earlier same-name namespace, other-key and
  wrong-route denials enforced before quota/provider — the wrong-route
  case requires route resolution to identify the mismatch, ID-less owned
  positive through the deferred call-id HMAC lookup, ID-less
  unowned/other-key/wrong-route denials), B1 codec refusal across all
  three codec modes with usage settled exactly once and the fixed 502
  after settlement, B2 preserve passthrough settlement, B3 all five
  owned nonempty-history success kinds (LocalCoding preserve, vLLM,
  llama-preserve, configured native, configured portable) carrying the
  same removed historical tool plus removal notice and second
  current-kept update with per-codec wire identity asserted, B4 the
  preserve-identity regression (two distinct namespace-less histories
  produce distinct wire bodies), B5 missing key/route Codex-grant
  negatives (400 before quota/provider, zero reservation/ledger
  writes), and C the rev15→rev16 migration dry-run/apply/idempotency
  with the drifted-digest negative and full preservation.
  Focused new cases (5 success kinds + 4 missing-grant negatives +
  preserve-wire regression): **10** passed.
- The relevant isolated PG modules
  ``test_codex_replay_references_postgres.py`` (2),
  ``test_local_coding_server_module_postgres.py`` (3), and
  ``test_accounting_finalization_postgres.py`` (6) are unchanged by
  every 226-b commit; their **11** passes are reused from the isolated
  matrix run at ``194f11c1`` (2 + 3 + 6 = 11, with the then-current
  owned-module slice = 20 total) and were not re-run (agreed test
  economy).
- Total owned PostgreSQL qualification: **33** unique cases
  (22 owned-module + 11 reused), no production DB, no provider calls,
  provider HTTP mocked via ``httpx.MockTransport`` in owned cases,
  Redis disabled there.
- Intermediate hosted CI at code head ``f43794e0`` (CI run
  ``43973480725``, unit job ``133671381058``, log
  ``/tmp/slaif-226b-intermediate-unit-ci-failure.log``):
  **8183 passed, 1 skipped, 2 failed** — both failures were stale
  shipped-preset inventory expectations in
  ``tests/unit/test_compatibility_presets.py`` (the fifth preset
  ``codex-0.167.1`` shipped at ``867bc0f0`` was missing from the
  expected set/count).  Fixed test-only at ``8a831a2b`` (expectations
  updated; all validation/export/overwrite assertions preserved; no
  runtime or pin changes); the fixed module then passed 86/86 locally
  and is covered by the final full-unit run below.
- Final full unit suite (``.venv/bin/python -m pytest tests/unit -o
  addopts=``, once, no production DB environment) at the final
  integrated code head: **8185 passed, 1 skipped**, exit 0 (16m20s).
  The single skip is the optional live-plumbing test
  ``tests/unit/test_qwen38_text_codex_candidate.py::
  test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`` —
  skipped because the Codex 0.148 CLI binary is unavailable in this
  environment; no real Codex CLI was installed or run, and the skip is
  preserved rather than removed.
- Final-head hosted CI at the report SELF commit — **PENDING strategic
  verification; not claimed passed before publication.**

**NOT RUN**: real private-client reproduction, real upstream inference,
any real operator key migration.  Mocked HTTP paths are clearly
distinguished from actual inference throughout; synthetic gateway-key
canaries only.

## Boundaries and honesty notes

- This is a bounded CREATE-only client-tool lifecycle: one new gated
  profile data revision, no new unqualified route/backend, no hosted
  tool authority, no gateway execution, no stored tool content.
- A turn WITHOUT the full current prefix (the default incremental wire)
  IS supported whenever the applicable earlier validated declarations
  are present; the limitations are a call with no applicable validated
  declaration preceding it, and unsupported mixed full-snapshot/
  positional dialects. Customized (non-pinned) notice wording remains
  unsupported, and arbitrary customized prose is not a detection or
  authorization source after upstream metadata stripping.
- The prepared-body estimate is a conservative byte approximation, not a
  tokenizer measurement or no-overrun guarantee; raw bounds remain
  authoritative.
- The immutable round-a report records its publication-order deviation
  (committed 16 s before PR #386 creation) as-is; this record does not
  rewrite that sequence.

# OAP 226-a — Final Report (versioned Codex declaration history
foundation: shared lifecycle helper + adapter transport support)

Report publication commit: SELF

## Commit topology

- Activation commit:
  `ee5c01cba3e431d10c965bb49d561ca1d4245217` (tree
  `03c276e1816d91084c902c33120b28d8a4dbb345`, sole parent
  `3abe5bafca48f9f61c0d37bc8645d45ce8946da0`, the exact canonical
  main) — committed the root-authored order and the exact
  `oap/active` = `226-a` pointer unchanged, FIRST (2 files, +48/−1).
- Immutable order:
  `oap/orders/226-a-codex-tool-history-foundation.md`, SHA256
  `ced7b31d32a5c92adc9ab1342f96bc19bad718ae906789f13c74cb8e58193d09`
  (re-verified at report time). First line exact
  `# OAP Work Order — 226-a`; `PR mode: CREATE_NEW_PR` is a standalone
  declaration line.
- Secondary integration (cherry-picked by primary, sole authorship
  preserved): `eee31c92f00ffa5a41fd611c6afc9ecd6002c0ab` ("226-a
  adapter track: versioned Codex declaration history transport
  support"), cherry-picked unchanged from the isolated adapter-track
  commit `d89fe8b0c3e3cc817893692e1c8d162cd3bb63a5` (branch
  `oap/226-adapter-track`, sole parent the activation commit; 6 files,
  +776/−9, exactly the secondary's exclusive paths). Cherry-pick was
  conflict-free (disjoint paths); no owned conflicts needed resolving.
- Implementation head (sole SELF parent):
  `d0b9b0c10e24c4f3aaa1ea6fe6e757369f5692e8` ("226-a: pure Codex
  declaration-history lifecycle helper, pinned notice grammar,
  verification record"; sole parent the integration commit; 4 files,
  +1996: `app/slaif_gateway/services/codex_tool_history.py` (new
  pure module), `tests/unit/test_codex_tool_history.py` (new focused
  suite), `docs/verification/2026-11-16-codex-tool-history.md` (new
  verification record), `docs/responses-compatibility.md` (one link
  section)).
- This report: report-only SELF, sole parent = the implementation
  head, sole diff = this file.
- PR: per the order's `CREATE_NEW_PR`, exactly ONE new PR is opened
  from this branch after this report commit: branch
  `oap/226-codex-tool-history`, base `main`
  (`3abe5bafca48f9f61c0d37bc8645d45ce8946da0`), title exactly
  `226: Support versioned Codex declaration history`. Branch, base
  and head are verified per protocol. No merge, no auto-merge.

## Verified state at activation (re-checked at report time)

- `oap/active` exact `226-a` on branch
  `oap/226-codex-tool-history`; remote/local main exact
  `3abe5bafca48f9f61c0d37bc8645d45ce8946da0` (fresh fetch at report
  time).
- All three main workflows successful: CI `43766942976`, CodeQL
  `43766942984` (latest `43870508997`), Code Quality
  `43766943297`.
- OAP `225-b` terminal; PR #384 merged as `73297bb7c6e99d7fa2c83cfec70c6c5800fb5236`
  (verified `mergedAt=2026-11-15T01:39:43Z`); its orders/reports
  immutable.
- Only unrelated open PR at activation: #319 (dependabot). Release
  only `v0.1.0-rc.1`. Main ruleset active against
  deletion/non-fast-forward. No 226 PR/order/report pre-existed.

## Source-derived contract (pinned Codex rust-v0.167.1)

- Pinned official Codex CLI `rust-v0.167.1`, source commit
  `0a94398fa60c4fac0e7659e4213a0a36e613dd46` (tag `rust-v0.167.1`),
  read from a local pinned checkout that does not track moving
  upstream main. Seven root-fetched copies of the exact source files
  (`/tmp/slaif-codex-01671-{client,client-common,turn,step-context,world-state,top-level-tools,models}.rs`)
  were verified BYTE-IDENTICAL against that ref (`cmp` clean, all
  seven); their SHA-256 values are recorded in the verification
  record.
- Findings (exact references in
  `docs/verification/2026-11-16-codex-tool-history.md`):
  `core/src/client.rs` `build_responses_request` inserts the full
  current `AdditionalTools` prefix at input index zero ONLY when
  `prompt.tools` is nonempty (Responses Lite); `core/src/session/turn.rs`
  `build_prompt` keeps only hosted tool specs in `prompt.tools` in
  incremental mode, so the full local prefix may be absent;
  `core/src/context/world_state/top_level_tools.rs` emits
  added/changed-only incremental batches with a developer hint notice,
  and removals as a separate developer notice (content kind
  `tools.removed_definition`, configurable headers, bundled defaults
  resolved at most 512 bytes upstream); `protocol/src/models.rs`
  `clear_internal_chat_message_metadata_passthrough` strips the
  structured kind metadata for non-OpenAI providers, leaving only
  configurable text. Neither a positional first/latest/every-item
  full-snapshot rule nor an authority union is justified by source.
- The observed rejection proves only the PRESENCE of a second
  `additional_tools` item at `input[265]` — not its contents,
  equivalence, cause, or private client settings. No private request
  body was read, and the affected person's identity/correlation ID is
  not published anywhere in this work.

## Primary implementation (shared lifecycle groundwork)

`app/slaif_gateway/services/codex_tool_history.py` (new, pure,
stdlib-only, no app imports):

- Two explicit profile-declared modes — `full_snapshot` (every
  declaration replaces the catalog; an absent first declaration
  legally means "no local tools") and `positional_updates`
  (declarations are adds/changes only; removals are parsed notice
  facts).  Absence of a mode keeps legacy behavior (the gateway does
  not consult the helper yet); unknown modes fail closed.
- Immutable frozen events (validated declaration with canonical
  taxonomy + inert optional item ID + optional definition references;
  parsed removal notice; tool call with optional `namespace=None`;
  tool call output with exact function/custom kind and optional
  output ID) and immutable `CodexToolHistoryFacts` (chronological
  steps, final active taxonomy, `call_bindings` — the stable
  core-to-adapter shape, an immutable stdlib `types.MappingProxyType`
  mapping keyed by the ORIGINAL `call_id` to `(namespace, name, kind)`
  — pending call IDs, `active_definitions` by REFERENCE with
  `repr=False`, and call-position definition references on call
  steps so later core can detect schema/type transport conflicts
  without a second lifecycle).
- Laws: call-position binding immutable through later updates; later
  declarations never authorize preceding calls; removed tools cannot
  be newly called; same-name function/custom redefinition rebinds
  only LATER calls (per-call historical kind is representable — no
  blanket kind-transition refusal); `namespace=None` resolves by ONE
  unambiguous `(name, kind)` match (existing-policy name-and-type
  law, ambiguity refused); call/output ID uniqueness; exactly one
  output per call with exact kind linkage; consistent
  definition-free-or-fully-defined declaration sequences (no silent
  stale references); strictly increasing positions inside the
  explicit `max_items` bound; removals must name only active tools.
  Every refusal is a fixed `CodexToolHistoryError` with a stable
  content-free `reason_code`, event `position`, `field`, and
  `observed`/`limit` — no raw content echoed.
- Pinned machine-readable removal-notice grammar
  (`parse_codex_removal_notice`): at most two sections joined by
  `"\n\n"`; each section is its EXACT pinned header line (bundled
  upstream defaults, or caller-supplied pinned values) plus one or
  more `"- " name` lines; namespace section first (bare names) then
  tool section (`namespace.tool`, exactly one dot); no repeated
  section kind; no duplicate names; no tool subsumed by a removed
  namespace in the same notice; explicit `max_names`/`max_body_bytes`
  bounds.  Prose, reworded or unknown headers, and malformed
  structure are fixed safe refusals — removal authority is never
  inferred from unrecognized text.
- Scope honesty (documented in module and verification record): the
  helper is not a validator (raw declarations must already have
  passed the existing policy-owned per-declaration
  taxonomy/schema validation, including invalid earlier entries) and
  not a replay authority.  It enforces call/output ID uniqueness,
  one-output-per-call, and kind linkage over the supplied events; it
  does NOT see or enforce replay item ID checks for other item
  families (reasoning, compaction, encrypted content, message IDs) or
  HMAC replay ownership, which remain with their existing owners.

## Secondary integration (isolated adapter track)

- Primary notified root via `/tmp/slaif-226-adapters-ready.json`
  (worktree `/home/janezp/codex-work/slaif-api-gateway-226-adapters`,
  branch `oap/226-adapter-track`, base = activation commit) before
  any primary implementation edits; root dispatched secondary %84;
  secondary never touched the primary worktree, PR/OAP/FIFOs, and
  never pushed or merged (result-JSON governance block confirms:
  `pr_created/pushed/fifo_used/merge_performed/primary_checkout_touched/helpers_spawned` all
  false, OAP files untouched).
- Secondary commit `d89fe8b0c3e3cc817893692e1c8d162cd3bb63a5`
  (6 files, +776/−9; exactly its exclusive paths) cherry-picked as
  `eee31c92...`:
  - `schemas/providers.py`: the stable interface — frozen
    `ProviderRequest` extended with the optional trailing
    `codex_tool_call_bindings: Mapping[str, tuple[str | None, str, str]] | None = None`
    (`repr=False`): ephemeral core-validated per-call translation
    facts, NOT client JSON, NOT execution/replay authorization, NOT
    persistent data; adapters reject missing/mismatched entries when
    a map is supplied; legacy behavior only when the map is None;
    never enters provider JSON, signature inputs, responses, logs,
    audit, metrics, or stored rows.
  - `local_coding_vllm/codec.py`: `VLLMToolCodec(body, *,
    portable_names=False, tool_call_bindings=None)`; active response
    map built only from current tools (no union of historical
    declarations); historical calls translated against per-call
    bindings even for removed tools; function/custom output
    association and original history order preserved; stable
    wire-name mapping in native and portable modes.
  - `upstream_llm/adapter.py`: the exact llama.cpp adapter continues
    receiving ordinary canonical historical types/namespace and
    current top-level tools (bindings inert on non-translating
    profiles); configured `leading_system_developer` placement with
    supplied lifecycle bindings is refused exactly
    (`upstream_llm_bindings_placement_conflict`, 400, pre-HTTP)
    because reordering could move removal notices ahead of the
    history they describe.
  - Focused adapter unit tests: 103 total (74 baseline + 29 new),
    mock HTTP only (httpx.MockTransport); no real provider, email,
    or database.
- Transition review compliance: per root's strategic review
  (`/tmp/slaif-226-transition-review.txt`, also sent to secondary),
  the integrated codec contains NO blanket same-name
  kind-transition refusal: same namespace/name kind transitions are
  accepted in both directions (old-custom/current-function and
  reverse) using the per-call historical wrapper for old encoding and
  the active current map for new decoding, with synthetic tests in
  both directions.  The precise refusals retained are (a) native
  dot-flattening collisions between genuinely DIFFERENT
  namespace/name identities sharing one wire string (fixed
  `vllm_native_wire_identity_collision`, history-vs-history and
  history-vs-current-declaration; portable hashed identities remain
  distinct by design) and (b) a wire name currently owned by a
  different declared identity.  Core HMAC identity including call
  kind remains checked; binding kind is part of the per-call
  identity and stays checked against the item.

## Verification evidence (focused, this round)

- Integrated focused suite, exact command:
  `.venv/bin/python -m pytest tests/unit/test_local_coding_vllm.py tests/unit/test_upstream_llm_adapter.py tests/unit/test_codex_tool_history.py -p no:warnings`
  Result: **157 passed** (103 adapter + 54 helper, collect-only
  verified 103/54), exit 0.  (Root independently re-ran the helper
  suite with `-o addopts=` during review: authoritative pass; the
  pyproject `addopts=-q` plus a second `-q` suppresses the summary
  line, so count was verified by collect-only, not repeated
  execution.)
- Ruff on all eight changed Python files: All checks passed.
- Docs hygiene: `DOCUMENTATION_CHECK=OK files=139`.
- Focused `tests/unit/test_oap_governance.py`: 10/10, real exit 0
  (the activated order's canonical metadata passes the strict
  active-order test).
- Whitespace: no trailing whitespace or tabs in the new files;
  `git diff --check` clean on the modified doc.
- Reused accepted evidence per order; NO unchanged local full
  matrices were rerun.  The normal-admin byte oracle need not rerun
  (no template/CSS change).

**NOT RUN in this round** (required at the final integrated head):
the full unit matrix, the relevant isolated-PostgreSQL
replay/local-server/accounting tests, and hosted CI on the final
head.  No real provider/Codex process, production database, or
credentials were used.

## Real vs synthetic (exact)

- REAL: the pinned Codex rust-v0.167.1 source contract (byte-verified
  files above); the real integrated code under real pytest.
- SYNTHETIC/MOCK: all adapter transport evidence is mocked HTTP
  (httpx.MockTransport) with synthetic declarations, calls, and
  canaries; no live inference, no production data, no real provider
  credentials, no real email, no database.  No production request
  populates `codex_tool_call_bindings` yet (field None keeps exact
  legacy behavior) — the core-to-adapter wiring is a later same-PR
  round.

## Limitations (honest)

- This is a STAGED implementation, not completion of the reported
  bug: HTTP acceptance is unchanged (the single-`additional_tools`-
  item law and the 0.162 lowering remain in force), no profile
  feature/schema exists yet, no key migration, no estimation
  change, and no frozen revision-15 profile or qualification fixture
  digest was touched.  No database schema change appears necessary.
- The helper's bounds are explicit caller parameters
  (`max_items`, `max_names`, `max_body_bytes`); no
  transport-level cardinality cap was added to the bindings map
  (cardinality is bounded by the core-configured input size/item
  bounds, per root review).
- All original 18 acceptance categories remain mandatory before
  merge; later rounds must update
  `responses-compatibility.md`, `provider-forwarding-contract.md`,
  `accounting.md`, `security-model.md`, the client preset/module
  docs, and deployment/rollback documentation with the exact
  migration identity if a new profile is introduced.

## GitHub state (observed at report time)

- `origin/main` = `3abe5bafca48f9f61c0d37bc8645d45ce8946da0`
  (fresh fetch).
- Open PRs at report time: only #319; no objective-226 PR exists
  yet.  Exactly ONE new PR is opened from this branch after this
  commit (branch `oap/226-codex-tool-history`, base `main`, title
  exactly `226: Support versioned Codex declaration history`), head
  = this report commit.  No merge, no auto-merge.

## Protected untracked files (untouched, unread, unstaged)

- `CODEX-SESSIONS.md` (recorded `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`)
- `codex.sh` (recorded `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`)
- `uv.lock` (recorded `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`)
Remain untracked in `git status` at report time, staged for nothing,
and were not read, per the order; the recorded values are the
activation order's own.

## Objective status

226-a acceptance is complete: ONE draft/open feature PR (opened from
this branch, head this report), the activated order is
immutable/canonical, the shared lifecycle helper and the isolated
adapter changes are integrated with passing focused tests (157),
HTTP acceptance and frozen profiles are NOT broadened, and the exact
pure/adapter limitations are documented.  The PR awaits hosted CI
and strategic review on the final head; nothing is merged by the
coding agent.

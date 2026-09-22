# OAP Immutable Report — 180-f: close catalog roundtrip and comparison gaps

PR mode: AMEND_EXISTING_PR on PR #317 (branch
`oap/180-catalog-refresh-bundle-review`, base `main`).

## Identity

- Starting SHA (worktree HEAD / committed PR head when this order started):
  `68d2605e22c77cf0c48503e192a4ce57e9735229`
- Implementation head SHA: `244d1019df348c4e20192ab28187a105cc6f67fb`
- Report publication commit: SELF
- PR #317 remains OPEN. Never merged, auto-merge not enabled, no tag, no
  release. The only published release remains `v0.1.0-rc.1`. No
  production-certification claim follows.

## Changed paths (implementation head vs starting SHA)

- `app/slaif_gateway/schemas/catalog_refresh.py` — F2 single derived
  capability mapping (`FLAT_CAPABILITY_TO_CHAT_FIELD`,
  `declared_capability_overlay`, `derive_standard_create_capabilities`,
  `overlay_route_capabilities`, `derived_route_capabilities`);
  `RENDERER_VERSION` 180.3 -> 180.4.
- `app/slaif_gateway/services/catalog_refresh/bundle.py` — F2: route TSV
  emits the derived nested runtime capability shape only (no stray flat
  storage keys); pricing TSV emits `source_retrieved_at=""` and
  `pricing_metadata=""` (the `{"dimensions":...}` blob and the dead
  `_source_retrieved_at` helper removed).
- `app/slaif_gateway/services/catalog_refresh/policy.py` — F4:
  `source_age_state` inclusive boundary (<=24h fresh);
  `fx_age_state` on a calendar-day basis (`fx_stale_review_days` /
  `fx_stale_blocked_days` int fields, still configurable via the bundle
  policy block).
- `app/slaif_gateway/services/catalog_refresh/validation.py` — F2: derived
  contract drives evidence requirements
  (`_effective_chat_text_capability`), the before/after comparison
  (declared-intent-only overlay naming `route.capabilities.<chat_field>`),
  explicit `streaming_intent_conflict` and `text_disabled_route` blockers;
  F3: FX quote comparison as exact Decimals in the fact pair's direction
  grouped by (publication date, direction) with bounded 1e-8 reciprocal
  tolerance (no invert-back), supporting-quote selection restricted to the
  fact's own declared/approved/parsed sources, and `fx_to_eur` registration
  with same-direction exact / cross-direction tolerance agreement.
- `docs/catalog-refresh.md` — F2 effective-eligibility semantics rewritten
  to the derived contract; F3 FX binding bullets (direction,
  (date, direction) grouping, reciprocal tolerance, declared-source
  selection); F4 threshold table (inclusive 24h, calendar-day FX age,
  exact pre-rounding 25%/3%); renderer 180.4 versioning note.
- `tests/unit/test_documentation_contract_drift.py` — F1: exactly one
  reviewed allowlist entry for the read-only consumer
  `app/slaif_gateway/schemas/catalog_refresh.py` (comment documents the
  read-only projection use).
- `tests/unit/test_catalog_refresh_policy.py` — F4 boundary tests
  (below/equal/above every boundary; calendar-day FX age; exact 25%/3%
  pre-rounding comparisons).
- `tests/unit/test_catalog_refresh_source_evidence.py` — F3 tests (quoted
  second source READY; later matching publication date not shadowed by an
  earlier uncited snapshot; rate match at an undeclared source is not
  backing) plus the preserved contradiction/semantic/date/rate negatives.
- `tests/integration/test_catalog_refresh_baseline.py` — F2
  `test_f2_generated_routes_survive_create_export_refresh` (fresh
  task-owned DB round trip with real imports);
  `test_e3_text_disabled_declaration_on_existing_route_is_visible_change`
  (renamed from the effective-default test; asserts the honest
  narrowing/visible change); widened openrouter `synthetic/%` cleanup.
- `tests/fixtures/catalog_refresh/bundle-{blocked,first-install,
  refresh-ready,truncated}.json` — `revision.renderer_version` 180.4
  (re-dumped `indent=2, sort_keys`); no semantic content change.
- `tests/fixtures/catalog_refresh/browser-screenshots/{first-install,
  ready,warnings,blocked,large-unchanged}.png` — re-captured at 180.4
  (real Chromium, 1440x900, see Screenshots).
- Not touched although allowed (not needed): `baseline.py`,
  `source_evidence.py`, `rendering.py`, `tests/unit/test_catalog_refresh_{
  baseline,bundle,report,seal}.py`, `test_cli_catalog_refresh.py`,
  `docs/cli-reference.md`, `admin/catalog-refresh/README.md`.
- `oap/orders/180-f-close-catalog-roundtrip-and-comparison-gaps.md` and
  `oap/active` committed unchanged (strategic bytes preserved).

No application/provider/accounting runtime changes, no import-executor
change, no schema/migration, dependency, deployment, workflow or
historical-record change. No live retrieval, provider call, Codex
research, real import, or apply. Runtime capability/policy/import modules
were read/reuse-only.

## F1 — Register the reviewed read-only policy consumer (closed)

- The drift gate's consumer allowlist gained exactly one entry:
  `REPO_ROOT / "app/slaif_gateway/schemas/catalog_refresh.py"` with a
  comment identifying it as the read-only baseline projection consumer of
  the authoritative `external_tool_policy_contract` parser
  (`parse_route_external_tool_policy` +
  `DEFAULT_EXTERNAL_TOOL_OPERATOR_CEILINGS`).
- No parser duplication, no indirect/hiding import, no dropped
  `external_tools` metadata, no weakened assertion, no broad directory
  exception; the allowlist mechanism and all other consumers are
  unchanged.
- This use grants no runtime hosted-tool authority: the parser output is
  consumed only to validate/project existing metadata into a read-only
  baseline document; nothing in the catalog-refresh path executes,
  authorizes, or forwards external tools.
- Malformed/unknown `external_tools` metadata still fails safely without
  private content leakage: the 180-e E1 external-tools projection tests
  (verbatim recognized contract, opaque unrepresented flag, canary
  absence) are preserved and pass in this round's suite.
- CI effect: the `Unit, lint, and migration head` gate that failed at 180-e
  on
  `test_external_tool_policy_contract_consumers_remain_allowlisted` now
  passes; final-head CI is 10/10 (see Final-head CI).

## F2 — Generated routes survive create -> export -> refresh (closed)

One deterministic mapping now takes proposal intent to the actual runtime
`chat_completions` shape, and the same derived intent drives the emitted
import bytes, the evidence requirements, the before/after comparison and
the rendered rows:

- NEW rows: `derive_standard_create_capabilities` — the documented
  standard scope (text, declared-or-True; streaming, declared-or-column)
  plus ONLY explicitly declared standard keys. Undeclared function tools,
  structured outputs, logprobs or any other runtime default stay absent
  (runtime-denied): the create never turns on permissions the proposal did
  not request.
- EXISTING rows: `overlay_route_capabilities` — the reviewed baseline
  block is the base and only the explicitly declared intent is overlaid;
  omitted approved fields, including explicit denials, are preserved
  verbatim. A partial proposal is therefore an honest no-op; an explicitly
  requested capability change is shown as a change. Create-only behavior
  is preserved (an excluded update mutation still blocks the import plan).
- `streaming_intent_conflict` BLOCKER: a proposal declaring the streaming
  capability with a contradicting `supports_streaming` column is rejected
  explicitly, never resolved by a silent precedence.
- `text_disabled_route` BLOCKER: a new row whose derived contract disables
  text is not a usable standard text candidate; it is blocked with a clear
  reason rather than silently enabled or claimed as a text bootstrap.
- Emitted artifacts: route TSV capabilities are the nested runtime shape
  only (no stray flat storage keys); generated pricing rows carry no
  `pricing_metadata` blob and no fabricated `source_retrieved_at`, so the
  import stores only representable metadata.

Strategic F2 reproducer (partial-intent preservation), before/after:

- Setup: the FULL actual runtime `chat_completions` default block with ONLY
  `chat_function_tools` stored false; proposal declares ONLY
  `text:true, streaming:true`.
- BEFORE (180-e semantics): the full validator returned CHANGED for ONLY
  `route.capabilities.chat_function_tools` because the derived defaults
  proposed `true` — a permission change nobody requested.
- AFTER: UNCHANGED — the declared-only overlay preserves the stored
  denial. A 2-field nested block plus explicit denial variant behaves
  identically (a valid 2-field nested block is legitimate runtime
  metadata; the fix is the mapping, not fixture expansion).
- Explicit requested capability change is visible: flipping
  `json_mode` reports CHANGED with detail `route.capabilities.chat_json_mode`.
- Contradictory streaming intent (capability vs column) is rejected with
  the explicit `streaming_intent_conflict` blocker.

E3 correction (audio-only + text:false): with an existing row, an
audio-only source (observed `text=false`) and a model/route
`text:false` declaration, the derived contract genuinely narrows: there is
NO `source_evidence_value_mismatch` (the declaration agrees with the
observation), the plan gate `gate:import.routes` is present (create-only:
the update is an excluded mutation), exit 20, disposition CHANGED with
`route.capabilities.chat_text` in the detail. See the Corrections section
for the relation to the 180-e E3 closure claim.

Actual persisted round-trip / no-op proof (fresh task-owned database,
`test_f2_generated_routes_survive_create_export_refresh`):

1. Seed synthetic provider state only; first-install review of the valid
   fixture: exit 0 READY.
2. Emitted route capabilities JSON is exactly
   `{"chat_completions": {"chat_streaming": true, "chat_text": true}}` —
   nested runtime shape, no stray flat keys.
3. Dry-run: routes `valid_count=1, invalid_count=0`; pricing
   `validated_count=1, invalid_count=0`.
4. Explicitly confirmed imports with audit reasons: routes
   `created_count=1`, pricing `created_count=1`.
5. ACTUAL persisted capabilities read back by SQL: exactly
   `{"chat_completions": {"chat_streaming": true, "chat_text": true}}` —
   no permission widening by the importer.
6. `export-baseline` on the real rows; re-review the same synthetic source
   facts against the exported baseline (declared baseline identity copied
   from the exported document, run_id `fixture-refresh-002`):
   - exit 0 READY on a fresh CI database (exit 10 READY_WITH_WARNINGS is
     tolerated against a shared session database carrying other files'
     openrouter rows via `model_disappeared` REVIEW findings; neither may
     be BLOCKED);
   - no BLOCKER severity; no `baseline_unrepresented_capabilities`, no
     `baseline_unrepresented_metadata`, no `source_observations_contradict`;
   - disposition for `synthetic/chat-v1` is UNCHANGED; `counts.changed==0`;
   - route and pricing artifacts are header-only (exactly one line each);
   - exactly one `model_routes` row and one `pricing_rules` row — zero
     executable duplicates.

This used ONLY existing import commands with synthetic data in a task-owned
test database. No product apply workflow was added or authorized.

## F3 — Compare FX values, not their spellings (closed)

- Same-context contradiction check: official quotes for the pair are
  compared as EXACT Decimal values in the fact pair's direction, grouped by
  (publication date, direction). Equivalent spellings of the same quote
  (`1.08` vs `1.080`) never fabricate a conflict; genuinely different
  same-context quotes block (`source_observations_contradict`); same-date
  quotes supplied in the reciprocal direction must agree within the
  bounded 1e-8 reciprocal tolerance in the proposed pair's direction —
  never by an unstable invert-back equality.
- A reciprocal quote is validated in the proposed pair's direction (quote
  normalized; the fact rate is never inverted back).
- `fx_to_eur` registration: same-direction quotes must be exactly equal;
  quotes reaching the same currency from opposite directions (rounded
  reciprocals) must agree within the bounded tolerance.

Declared-source selection (strategic review within this round, artifact
`180-f-draft/fx-declared-source-selection.json`):

- BEFORE: the code picked the FIRST GLOBAL rate match, then rejected its
  reference/date, ignoring a later correctly cited quote.
- Repro: valid first-install fixture + duplicate ECB `SourceRecord` with
  model `USD-EUR` and identical bytes/date/rate. Citing the original
  `ecb|EUR-USD|ecb_reference_xml` is READY; changing ONLY
  `fx[0].provenance.sources` to `[ecb|USD-EUR|ecb_reference_xml]` was
  BLOCKED with `source_evidence_reference_mismatch` plus cascading
  `source_evidence_unsupported` (pricing:input, pricing:output),
  `fx_evidence_unbound` and `gate:completeness`.
- AFTER: the supporting quote is selected from the fact's OWN declared,
  approved, parsed sources with matching pair/date/value before choosing
  it — a rate match at an undeclared source is not backing, and an earlier
  uncited match never shadows a correctly cited later quote. No declared
  quote: `source_evidence_reference_mismatch`; value + date match: bound;
  value-only match: date check applies (`fx_evidence_date_mismatch`); no
  value match: `source_evidence_value_mismatch`. The independent
  same-context contradiction check still runs over ALL authoritative
  evidence for the pair.
- Repro after the fix: cites-first READY; cites-second-matching-source
  READY with `backed_by = ecb|USD-EUR|ecb_reference_xml`,
  `quote_date = 2026-09-21`; the cascading issues are gone.

Tests added (all passing in this round's suite):

- `test_fx_cited_second_source_with_identical_quote_is_ready` — the exact
  strategic reproducer (duplicate record, identical bytes/date/rate).
- `test_fx_cited_later_matching_quote_not_shadowed_by_earlier_uncited` —
  two official ECB snapshots, same rate, different publication dates
  (2026-09-20 and 2026-09-21); the fact cites only the later one and is
  READY with `quote_date = 2026-09-21` (the earlier uncited snapshot does
  not shadow and does not fail the date check in its place).
- `test_fx_rate_match_at_undeclared_source_is_not_backing` — a matching
  1.08 quote exists globally (record modelled `USD-EUR`) while the fact
  cites the `ecb|EUR-USD` record whose snapshot carries no EUR/USD quote
  (GBP cube only): BLOCKED with `source_evidence_reference_mismatch` (not
  a value mismatch), unbound. (Citing a source record that does not exist
  at all is already refused at bundle schema level with
  `bundle_schema_invalid`; the cited record must exist and parse.)

Preserved negatives (still passing): genuinely different same-context
quotes block (`test_fx_two_distinct_ecb_snapshots_contradict_block` —
1.08 vs 1.10 still blocks, so the contradiction check over all official
quotes is intact); a semantic source cannot bind an FX fact
(`fx_evidence_unbound`, zero guessed-rate normalization,
`pricing_rows == 0`); wrong fact date blocks
(`fx_evidence_date_mismatch`); wrong fact rate blocks
(`source_evidence_value_mismatch`); USD normalization binds quote and date
exactly (`test_ecb_quote_and_date_bind_usd_normalization`).

Implementation note (honest record): the first declared-selection
implementation contained a guard defect — when a value AND date match was
found the loop set `matched` and broke before `value_matched` was
assigned, so the `if value_matched is None` guard falsely emitted
`source_evidence_value_mismatch` and the committed first-install fixture
BLOCKED. The guard was corrected to
`if matched is None and value_matched is None` before publication; the
fixture was re-verified READY and the full suites re-run green.

## F4 — Decisions use the exact documented thresholds (closed)

- Source retrieval age: `age <= 24h` fresh (inclusive); `24h < age <= 72h`
  REVIEW; `age > 72h` BLOCKED. (180-e used `age < 24h`, so exactly 24h was
  already REVIEW; corrected.)
- FX publication age: CALENDAR-DAY basis — whole days between the UTC
  publication date and the UTC review reference date; the time-of-day
  never changes the state. `<= 3` days fresh; `3 < age <= 7` REVIEW;
  `> 7` BLOCKED. (180-e used a timedelta age, so 73h was already REVIEW;
  corrected: 73h is calendar age 3 and stays fresh.)
- Price movement: exact relative change `> 25%` REVIEW; exact 25% does not
  trigger; compared BEFORE any display rounding (the 1e-6 quantization is
  display-only and can no longer round an above-threshold value back to
  the threshold).
- FX movement: exact normalized-pair relative change `> 3%` REVIEW; exact
  3% does not trigger; compared before display rounding.
- Policy stays configurable via the bundle policy block
  (`source_stale_review_hours`, `source_stale_blocked_hours`,
  `fx_stale_review_days`, `fx_stale_blocked_days`, `price_change_review`,
  `fx_change_review`); defaults unchanged (0.25 / 0.03 / 24h / 72h / 3d /
  7d).
- Tests: below/equal/above at every boundary, including date-vs-time-of-day
  behavior for FX age and an exactly-3%-is-not-review FX pair. Zero
  transitions, missing dimensions, stale/future/unknown/conflicting facts
  and true excessive movements remain explicit deterministic findings
  (preserved 180-e tests pass).

## Negative privacy/authority cases (exercised in this round)

- Semantic/manual FX escape hatch: an FX fact pointed at a docs-page or
  operator input with no verified quote blocks unbound; its rate is never
  used to normalize any price (`fx_evidence_unbound`, `pricing_rows == 0`).
- Rate match at an undeclared source is not backing (F3 negative above).
- Genuinely conflicting official quotes block over ALL authoritative
  evidence, not just the cited one.
- Unknown provenance source references are refused at bundle schema level
  (`bundle_schema_invalid`): a citation must name an existing record.
- `external_tools`: read-only allowlist only; malformed/unknown metadata
  fails closed with no private content leakage (180-e E1 suite preserved).
- Free-form pricing metadata remains `pricing_metadata_unrepresented`
  (180-e E2 canary suite preserved); generated rows now inject no
  proposal-internal state at all.
- No new live collector, researcher, apply wrapper, pricing supersession or
  arbitrary capability profile; unsupported/hosted/multimodal/Responses/
  Codex authority remains denied; a text-disabled create is blocked, never
  silently enabled.

## Source / report / seal correspondence

- All four CLI report captures are sealed runs (`catalog-refresh review`
  with `--seal-key`): first-install exit 0 READY; ready (scoped
  `synthetic/stable-v1` vs `baseline-synthetic.json`) exit 0 READY;
  warnings (scoped stable+new, `generated_at=2026-09-22T18:00:00Z`) exit
  10 READY_WITH_WARNINGS; blocked (`bundle-blocked.json`) exit 20 BLOCKED
  (plan blocked). The large 80-model case is the same in-process pipeline
  the unit test uses (READY, 80 unchanged, all-eligible inventory
  reconciles with zero unexplained omissions).
- Seal suite (`test_catalog_refresh_seal.py`, in the 253-unit run):
  round-trip verifies cleanly; per-content-file tamper fails; manifest or
  receipt tamper fails; wrong key fails; coordinated tamper without the
  key still fails; missing file/run dir fail; path-traversal manifest
  entry refused; symlinked content file refused; parent symlink component
  refused; dangling symlink refused; file-size and nested-depth bounds
  enforced; duplicate JSON key in bundle fails verification; verify never
  writes or re-signs; no key material in artifacts.
- Report/seal replay against a live db_snapshot (180-e E5 integration
  test) passes unchanged in this round's integration run.

## Screenshots (180.4 renderer)

Five PNGs re-captured in `tests/fixtures/catalog_refresh/browser-screenshots/`
with real Chromium at 1440x900 via the repository venv's Playwright. Per
report: exactly one document request, zero sub-resource requests, zero
`<script>` tags, zero `on*` attributes, expected state banner, expected
plan box (ok/blocked), first-viewport placement of the core decision
sections, and the D5 expanded evidence details rendering the actual
observations (`data[0].pricing.prompt`, observed values `0.27` /
`0.54`, `per_1m_tokens`). The 180-e addition is retained: every report
renders the "Capture path (this execution)" baseline-identity line. The
fixture revisions assert `renderer_version == 180.4` before capture.

## Local verification and actual collection counts

- Focused 8-file catalog-refresh unit suite
  (`test_catalog_refresh_baseline`, `test_catalog_refresh_bundle`,
  `test_catalog_refresh_policy`, `test_catalog_refresh_report`,
  `test_catalog_refresh_seal`, `test_catalog_refresh_source_evidence`,
  `test_cli_catalog_refresh`, `test_documentation_contract_drift`):
  **253 passed** in 28.81s.
- Full integration suite (exact CI invocation, task-owned disposable
  PostgreSQL): **244 passed, 2 skipped, 0 failed**, RC=0, 141.91s.
  Skips are environmental and unrelated to 180-f (exact reasons):
  - `test_backup_restore_postgres.py:42` — pg_dump unavailable or
    incompatible: the pg_dump 17.11 client attempted a default-socket
    connection (it received the full URL as a database name and dialed
    socket `/var/run/postgresql/.s.PGSQL.5432`); environment gap, not a
    180-f change.
  - `test_gateway_key_prefix_migration_postgres.py:35` — the test requires
    an explicitly disposable PostgreSQL URL name (e.g. `restore_test`,
    `restore_local_<suffix>`, or a documented test name); `obj180f_test`
    is outside that naming set.
- `ruff check` on all changed Python files: All checks passed.
- `python3 scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK
  files=91`.
- `git diff --check 68d2605e22c77cf0c48503e192a4ce57e9735229
  244d1019df348c4e20192ab28187a105cc6f67fb`: clean.
- No full local/HPC matrix was run this round (the work order defaults to
  focused verification); the post-#220 128-worker HPC qualification
  remains **NOT RUN**. Skips are not passes.

## Resource identity and cleanup

- Task-owned disposable PostgreSQL (verified before setup and before
  cleanup): `/usr/lib/postgresql/16/bin`, data directory
  `/tmp/obj180f-pg/data` (PG 16), `127.0.0.1:5433`, user `ubuntu`
  (trust), database `obj180f_test`. The `obj180f_test` name ending in
  `test` satisfies the TEST-SUITE safety guard (conftest
  `_looks_like_safe_test_database_url`); that guard is a test-environment
  property, not product behavior — the product runtime does not validate
  database names. The DB was recreated fresh before the final integration
  run.
- Shared cluster: NO access to the shared 5432 instance, its
  configuration or logs, the privileged `postgres` identity, or protected
  credentials was attempted in this round (honest statement: none
  attempted, none needed). A shorter database transaction than Python
  processing time was never treated as evidence of a different server;
  the export duration observed in this round includes Python
  projection/rendering after the database transaction closes.
- Cleanup (completed before this report was committed): postmaster for
  `/tmp/obj180f-pg/data` (PID 71861) stopped with `pg_ctl stop -m fast`
  (verified: port 5433 free); `/tmp/obj180f-pg` removed; all
  `/tmp/obj180f*` logs, seal keys, workdirs and run dirs removed. No
  global prune/reset/cleanup was performed; unrelated worktrees,
  `.local-provider-catalog/`, the root `AGENTS.md`, and the permanent
  `message.txt` are untouched.

## Corrections to the 180-e broad closure claims (this report only;
the 180-e report is immutable and preserved unchanged)

- Thresholds (180-e E2 claimed closed with "source <24h fresh / 24-72h
  REVIEW / >72h BLOCKED; FX publication <3d fresh / 3-7d REVIEW / >7d
  BLOCKED"). The original 180-e order required strict >24h / >3d review
  thresholds — i.e. `<=24h` fresh inclusive — and a documented consistent
  calendar/date basis for FX. The 180-e `<` comparison (exactly 24h already
  REVIEW) and the timedelta FX age (time-of-day dependent; 73h already
  REVIEW) did not satisfy that requirement. F4 in this round implements
  the strict semantics: inclusive 24h source freshness, calendar-day FX
  publication age (UTC date basis; the time-of-day never changes the
  state), and exact 25%/3% movement comparisons before display rounding.
  The 180-e boundary closure is therefore superseded, not affirmed.
- E3 effective eligibility (180-e E3 claimed closed via the importer's
  default expansion: "the flat declarations cannot narrow the runtime
  contract the import path actually creates, because
  `ensure_default_chat_completion_capabilities` adds the default
  `chat_completions` block (which enables `chat_text`)"). That closure
  relied on importer defaults to define the effective contract. F2
  replaces the mechanism: the emitted import bytes carry the derived
  nested contract, so a `text:false` declaration genuinely narrows the
  stored contract; the audio-only + `text:false` case is an honest
  agreement (no invented `source_evidence_value_mismatch`) and a
  text-disabled create is explicitly blocked as not a usable standard
  text candidate (`text_disabled_route`). The 180-e E3 closure claim is
  not accepted as stated; the F2 semantics supersede it.
- Test-only database-name assertions: the safe-test-database name guard in
  the integration conftest and the explicitly-disposable-URL guard in the
  gateway-key-prefix migration test are test-environment guards (they keep
  destructive harness setup away from non-test databases). They are not
  product behavior.
- Task-owned-database-only restriction: it existed in the ORIGINAL 180-e
  order ("Use task-owned local databases only. ... No shared 5432
  instance, its configuration/logs, privileged postgres identity,
  protected credentials or production systems."), not only after a later
  reminder. This round reaffirms it; no shared-5432 access was attempted.

## Still REQUIRED for a later same-PR correction (not implemented here,
not claimed)

- Filesystem descriptor-walk / parent-replacement safety
- Symlinked verify-key handling
- Bounded input / aggregate reads
- Special files
- No-clobber run publication
- Opened-file identity / permissions
- First-screen / expanded-print layout

## Status

- Objective 180 is NOT complete. This round closes the F1-F4 focused
  corrections on PR #317 only; it does not complete the administrator
  workflow (one refresh command, one trustworthy REVIEW.html, one
  explicitly confirmed audited apply command). Live collection, isolated
  Codex research, atomic historical supersession and final wrappers remain
  later numeric objectives after PR #317 is accepted and resolved.
- No merge, no auto-merge, no tag, no release. No production-certification,
  security, or compliance claim follows.
- No later numeric objective is activated; the next strategic order is
  awaited after PR #317 resolves.

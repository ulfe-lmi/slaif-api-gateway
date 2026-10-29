# OAP Objective 203-a — final report: reviewed key-configuration batches

Work order: `oap/orders/203-a-reviewed-key-configuration-batches.md`
(committed unchanged on the objective branch with `oap/active` =
`203-a` (5 bytes, no trailing newline); order sha256
`c55bed7032eadff4bd59a38493f9a0206e9c5ec6338683701bd066ad9654dbed`,
active pointer sha256
`1715b5ae6c12be69c1a804c64277ecacf5fc6922d20d7749f4219db02023d69c`,
both verified before committing and re-verified at HEAD).
Branch: `oap/203-reviewed-key-batches`; base: `main`
`a1f7abdfc86b137e7bbece5c44face42b8e6b902` (merged 202 PR #358;
unchanged). PR mode: CREATE_NEW_PR — PR #359,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/359; no
auto-merge. The coding agent never merges; root reviews independently
and guard-merges.

Implementation head SHA: 19ab814b93c467474458a78c3cc1b3404a57a2ca
Report publication commit: SELF

## Implementation commits (this round)

1. `19ab814b93c467474458a78c3cc1b3404a57a2ca` — "Add reviewed
   key-configuration batches (plan/apply) (203-a)": the strategic
   order (bytes verified unchanged, sha256 above) + exact `oap/active`
   = `203-a` + the bounded allowed changes (15 files). First parent is
   the base `a1f7abd` above. This is the single implementation commit;
   all required work (items 1-13 of the root review aids) landed in it.

## What changed (allowed paths only)

New product surface (4 files):
- `app/slaif_gateway/schemas/key_batch.py` — strict version-1 plan
  document: safe fixed errors, derived per-key diffs/counts
  (re-derived, never trusted from the document), deterministic
  source/post state fingerprints (usage/rate/cache/broker state and
  crypto material excluded), known-shape refusal at parse AND write,
  duplicate/sort/count bounds (selected+excluded combined 1,000),
  bounded exclusive 0600 artifact write.
- `app/slaif_gateway/services/key_batch_service.py` — the shared
  KeyBatchService: READ ONLY exact preview (locks rows in sorted UUID
  order, exits the caller transaction without commit, zero
  writes/audits); bounded selection (cohort OR explicit UUID list,
  cap+1 overflow, duplicates, missing-ID whole-request refusal with a
  count only, no ID echo); apply re-locks the exact rows, re-resolves
  cohort membership AFTER the last potentially blocking selected-key
  lock, re-derives every target through the SAME shared policy law
  under the locks, validates saved source/post fingerprint coherence
  against the key's CURRENT identity/lifecycle context BEFORE any
  first/repeat/no-op decision, and refuses the whole batch (stale) on
  any drift with zero writes/audits; explicit `already_at_target`
  repeat (state equality, not historical proof); a late
  validation/write/audit failure propagates so the caller transaction
  rolls back ALL keys and ALL provisional (flushed) audits; the fresh
  `confirm_external_tool_fenced` apply-time control (saved confirmation
  stripped, never authority; repeated decisions re-require it through
  the same law); bounded no-echo reason law; and the NEW batch
  known-shape guards on the typed input policy and on each selected
  key's RETAINED canonical configuration BEFORE shared
  route/model validation can reflect a configured value into an error
  message (finite recognized shapes, not a universal sanitizer).
- `app/slaif_gateway/cli/key_batch.py` — the `keys batch` Typer
  sub-app: no-echo typed selection/page parsing, known-shape guards on
  policy file CONTENT, plan artifact PATHNAME, and audit reason (fixed
  safe errors, never echoed, refused before any write/artifact/output),
  `--json` honored, fresh `--confirm-external-tool-fenced` flag
  passthrough.
- `app/slaif_gateway/schemas/key_batch.py` plan file IO: new 0600 file,
  never overwritten, bounded read-back.

Modified existing files (3 product files, bounded):
- `app/slaif_gateway/services/key_service.py` — route-aware
  `project_key_configuration_update` projection (plan-time validation
  reuse), `render_key_configuration_document` shared renderer, and the
  persisted-state (database-coerced) post-update configuration check
  with exact `Numeric(18, 9)` money normalization in the shared
  projection (an unrepresentable cost target is refused, never
  silently rounded).
- `app/slaif_gateway/db/repositories/keys.py` — additive batch
  selection read (status-filtered, limit+1) and exact-ID batch reads
  (no behavior change to existing reads).
- `app/slaif_gateway/cli/keys.py` — registration of the `batch`
  sub-app (+4 lines).

Tests (3 new files):
- `tests/unit/test_key_batch.py` (38 cases) — schema/IO boundaries and
  the shared service laws on honest fakes (see verification record).
- `tests/unit/test_cli_key_batch.py` (12 cases) — actual Typer CLI
  surface, no-echo canaries, fresh-flag passthrough.
- `tests/integration/test_cli_key_batch_postgres.py` (13 cases) —
  owned-PostgreSQL-16 actual-CLI evidence (mandatory 37-key cohort,
  concurrency, rollback, money, fenced, edited artifacts, canaries).

Documentation (4 files):
- `docs/cli-reference.md` — literal `slaif-gateway keys batch plan` /
  `apply` invocations and semantics.
- `docs/security-model.md` — CLI Safety subsection: preview read-only
  law, one-transaction atomic apply, plan-never-authority, fresh
  fenced confirmation, known-shape (not DLP) boundary.
- `docs/verification/2026-10-29-cli-key-batches.md` — the dated
  verification record (evidence layers, exact commands, per-file
  JUnit counts, negatives, limitations, deployment).
- `docs/verification/README.md` — newest-first index entry.

No schema, migration, or settings change (migration head stays
0026/33 tables); no key creation, cohort, delivery, template, or
runtime-auth change; `services/key_policy_configuration.py` untouched.

## Verification evidence (recorded 2026-10-29)

Command for every layer: from the repository root,
`env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app
/tmp/slaif192-coding-venv/bin/python -m pytest <paths> -p
no:cacheprovider -q --junitxml=<file>`; every command exited 0.
Counts are per `classname` from the JUnit XML (not guesses).

- Owned PostgreSQL 16 (ACTUAL PG, actual CLI entrypoint, real SQL,
  synthetic data, one new owned labeled loopback tmpfs container,
  identity inspected before migration, exact container removed):
  `tests/integration/test_cli_key_batch_postgres.py` = **13 PASS / 0
  fail / 0 skip / 0 error** (37.65 s). Cases: 37-key cohort READ ONLY
  exact preview (`excluded_by_status == []` per cohort contract, 0600
  strict artifact); one-transaction apply with EXACT per-key audits
  (reason/actor, old/new values) and same-scope preservation
  (suspended/revoked controls, 101-key unrelated, 105-key tail, zero
  usage/reservation counters, 1001-key overflow untouched) plus
  whole-set repeat `already_at_target` (zero writes/audits); explicit
  selection mixed statuses/duplicate/missing-ID (count-only no echo);
  >100-eligible no-truncation; cap+1 overflow refusal before any
  artifact/write/audit; stale membership/config/status drift refusals
  (zero writes/audits); controlled real-PG lock-wait cohort join
  (competitor readiness barrier, causal holder/waiter observed via
  `pg_stat_activity` with `pg_stat_clear_snapshot()`, joined observer,
  post-last-lock re-resolution refuses with the newcomer visible);
  late-audit failure on key 3 of 3 propagates OUT of the caller
  transaction (fresh-session proof: all keys + all provisional audits
  rolled back, no partial commit); usage-only movement non-staleness
  across preview -> committed movement BEFORE the first config write
  -> actual write (counters preserved, one audit per key) -> second
  movement -> repeat (zero new audits); real-PG money target
  `"2"` -> `"2.000000000"` (9-decimal persisted) + repeat + 10-decimal
  plan-time refusal; fenced target fresh-confirmation refusal/apply/
  repeat-guard; edited before (first + repeat) and coherently edited
  policy+after+diff with stale post digest (applied state; the
  FIRST-apply variant is the durable unit regression); no-echo
  canaries in policy content, plan pathname, audit reason, and a
  selected key's RETAINED current configuration (fixed safe errors,
  no artifact, no writes, state/audit counts proven unchanged).
- Focused unit (honest fakes / actual Typer):
  `tests/unit/test_key_batch.py` = **38 PASS / 0 skip**;
  `tests/unit/test_cli_key_batch.py` = **12 PASS / 0 skip** (50 total).
- Unchanged consumers (same source state):
  `tests/unit/test_cli_key_policy_files.py` (28),
  `tests/unit/test_key_clone_service.py` (34),
  `tests/unit/test_key_policy_configuration.py` (56),
  `tests/unit/test_key_service_policy_update.py` (19) = **137 PASS / 0
  skip**.
- Governance/protocol/CLI replay: `tests/unit/test_oap_governance.py`
  (9), `tests/unit/test_codex_protocol_capture.py` (26),
  `tests/unit/test_cli_codex_replay.py` (21) = **56 PASS / 0 skip**.
- Documentation: `tests/unit/test_documentation_inventory.py` (16,
  including literal `keys batch plan`/`apply` naming),
  `tests/unit/test_documentation_contract_drift.py` (15),
  `tests/unit/test_documentation_asof.py` (13) = **44 PASS / 0 skip**;
  the expanded final documentation batch (adding
  `test_product_scope_docs.py` + `test_rc2_feature_scope_docs.py`) =
  **53 PASS / 0 skip**; `python3 scripts/check_documentation.py` ->
  `DOCUMENTATION_CHECK=OK files=130`; `git diff --check` clean.
- Static: ruff (E4/E7/E9/F, line-length 100) clean on all nine changed
  product/test Python files.

Root independent evidence (credited as root, not agent runs):
- Actual owned-PG16 boundary probes and fixed rechecks for the money
  target normalization and quota first/repeat
  (`203-a-projected-postgres-money-normalization-probe.json`,
  `203-a-first-repeat-postgres-recheck.json`), the saved
  fenced-confirmation probe (`203-a-saved-fenced-confirmation-probe.json`),
  the plan fingerprint-consistency probe
  (`203-a-plan-fingerprint-consistency-probe.json`), the CLI
  plan-path canary probe (`203-a-cli-plan-path-canary-probe.json`), and
  their fixed rechecks at stable service/core/CLI hashes (items 8/9/10
  of the root aids).
- Actual shared-service/fake-repo validation-error canary probe and
  fixed recheck (`203-a-validation-error-canary-probe.json`,
  `203-a-validation-error-canary-recheck.json`): normal nonsecret model
  denial unchanged (one route read); input and stored-current canaries
  refused with `KeyBatchError`, no echo, zero route reads, zero
  writes/audits after the fix.
- The root native-test review aids (items 1-13) identified the
  harness issues corrected in the final 13-green owned-PG run and the
  first-state coherent-edit regression added at unit level.

## Negative, privacy, security, accounting, and concurrency evidence

- No partial batch state: every refusal (stale membership/config/
  status, lock-join, overflow, duplicate, missing-ID, fenced
  confirmation, known-shape, reason bounds) leaves zero key/audit/
  material state (unit + owned-PG).
- No secret echo: canary values never appear in stdout/stderr in text
  or JSON mode (policy content, plan pathname, audit reason, retained
  current configuration); the known-shape guard fires BEFORE route/
  model validation can reflect a configured value into an error
  message. This is finite known-shape protection, NOT universal
  content sanitization and no DLP claim.
- No confirmation replay: a saved `confirm_external_tool_fenced` is
  stripped before validation; the fresh flag is required for first
  apply AND re-required by repeated decisions through the same shared
  law.
- No plan authority: an edited advertised before (with the derived
  diff) and a coherently edited policy+after+diff carrying a stale post
  digest are refused on first apply AND repeat with zero writes
  (durable unit + native coverage).
- No usage staleness: usage/reservation counters are excluded from the
  fingerprints; committed synthetic movement between preview and the
  first configuration write is preserved by the actual write and
  neither stales nor disturbs the repeat (synthetic fixture injection,
  not actual request/accounting qualification).
- No all-key scope: the 1001-key overflow cohort and every
  non-selected cohort are untouched (exact-scope snapshots in the
  owned-PG run).
- Concurrency: one controlled causal holder/waiter lock-wait refusal
  under READ COMMITTED with the membership re-resolution as the
  documented linearization point (no global serializability claim).

## Limitations

- One local disposable owned PostgreSQL 16 run with synthetic data:
  not concurrency-scale, load, or production qualification.
- The unit layer uses honest fakes (including an exact 9-decimal
  `Numeric(18, 9)` column emulation in the fake limit writer); only the
  owned-PG layer is storage proof for money coercion.
- No real provider, model, client, request-accounting, SMTP, mail,
  broker, HPC, or installed-wheel (205) claim is made by this record;
  the source entrypoint + real PG evidence is not 205 installed
  executable qualification.

## Deployment

No schema migration, key-policy migration, or new settings. Operators
apply this surface with the ordinary image rebuild/recreate; no data
migration or feature flag is required.

## CI status (honest, pending at publication)

At report publication the ten PR #359 checks were still in progress
(`Documentation hygiene` already SUCCESS; `Unit, lint, and migration
head`, `PostgreSQL integration tests`, `OpenAI-compatible E2E tests`,
`Playwright browser smoke`, `Docker Compose smoke`, and the code-scanning
checks IN_PROGRESS). Final-head CI for the SELF commit is gated by
root; this report does not certify CI results.

## Protocol invariants

- Order/active bytes committed unchanged (sha256 above, re-verified at
  HEAD); PR mode CREATE_NEW_PR (#359), one objective -> one PR; the
  coding agent did not merge and will not merge; no 204 activation;
  prior reports/orders immutable.
- `Documentation updated: docs/cli-reference.md, docs/security-model.md, docs/verification/2026-10-29-cli-key-batches.md, docs/verification/README.md`

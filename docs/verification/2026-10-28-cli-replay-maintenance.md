# Objective 200-a — Codex replay reference inspection and reviewed expiry extension verification

Recorded 2026-10-28 for the 200 PR (base `main` at
`4c265bc3c9668a66bb1643915d442fb8c411ff11`, the merged 199 PR #355).
This record describes what the bounded local runs below actually proved.
It is not provider, model, client, SMTP, credential, performance, security,
compliance, or release qualification, and it is not the 205 executable-only
transcript.

## Scope

Objective 200 replaced operator-authored expiry SQL for retained Codex
replay references with content-free inspection and an explicit reviewed
maintenance operation:

- New `codex replay inspect`: READ-ONLY summary. Exactly ONE explicit
  scope: `--key-id` (one gateway key), `--cohort-id` (one cohort), or
  `--all-active` (every currently active key); no bearer-secret lookup and
  no unscoped implicit database-wide operation. Optional documented
  UTC creation bounds `--created-from` (inclusive) / `--created-until`
  (exclusive), validated for order before any query. Returns stable safe
  JSON (`--json`) or a human summary: selected key/reference counts,
  active/expired counts, stored creation/expiry ranges, bounded
  gateway-route/public-requested-model groupings, and fixed
  exclusion-reason counts. It distinguishes expiry eligibility from
  actual client/model readiness and makes no credential, provider, or
  audit write of any kind.
- New `codex replay extend` two-step reviewed plan:
  `--output PATH` (dry-run; READ-ONLY; writes a NEW 0600 plan file,
  never overwritten) XOR `--execute PATH --reason` (applies the reviewed
  file exactly; `--reason` nonblank and secret-shape guarded; edit flags
  refused in mixed mode). `--ttl-seconds` accepts 1..31,536,000 and
  defaults to the ACTUAL configured `CODEX_REPLAY_REFERENCE_TTL_SECONDS`
  when omitted; the selected and the configured lifetime are rendered
  distinctly. `--include-expired` explicitly restores references whose
  stored expiry is already past.
- Plan law: strict schema version 1, at most 32 KiB, read at cap+1
  before parse, unknown-field/duplicate-key/nonfinite/oversize and
  recognized-secret-shape refusal with fixed no-echo errors, written
  exclusively with mode 0600. The plan binds scope/time filters,
  selected TTL, `include_expired`, safe aggregate counts, and THREE
  public hex-64 fingerprints computed from stable row identities:
  `expected_source_fingerprint` (full 10-element row identity including
  expiry, with the selected key identities prepended),
  `expected_source_state_fingerprint` (same entries with expiry
  stripped), and `expected_post_state_fingerprint` (eligible rows at
  their computed target expiries). These are public optimistic guards,
  not authentication or replay authority.
- Decision law at execute (all revalidated under the locks with a fresh
  clock sampled AFTER all locks): actual full identity == source
  fingerprint is a FIRST apply (zero eligible updates = zero-write
  no-op with zero audits; otherwise one audited extension using counts
  DERIVED from the locked rows, never plan metadata); source-state
  fingerprint still matches AND actual full identity == post-state
  fingerprint is an already-applied no-op with no duplicate audit;
  anything else is refused stale with zero writes and zero audits, so an
  unrelated modification is never mistaken for this operation's
  idempotent result and no unreviewed subset is ever applied.
- Eligibility and target law: target expiry = ORIGINAL STORED
  `created_at` + selected TTL (never execute-now + TTL); `created_at`
  is never rewritten; only monotonic extension (a row whose stored
  expiry is already later or equal is untouched); rows whose computed
  target is not in the future are excluded, never revived by refreshing
  age; expired rows are excluded unless `--include-expired` was
  explicitly previewed and approved. Fixed exclusion reason codes:
  `key_not_active_or_valid`, `unsupported_kind`,
  `ledger_not_finalized`, `hmac_version_unavailable`,
  `outside_lifetime`, `expired_not_included`.
- Concurrency law: deterministic lock order (keys FOR UPDATE, then
  reference rows FOR UPDATE); after the key locks the scope membership
  is RE-RESOLVED fresh and must be set-equal to the previewed membership
  (a key added to, or leaving, the cohort during the lock wait is
  refused stale); fresh eligible counts are re-derived from the locked
  rows and must equal the plan's safe counts (a strictly parsed but
  hand-edited count is refused); the saved plan is a public staleness
  guard, not signed authority.
- Update mechanics: caller-owned transaction, no inner commit; the rows
  are updated in chunked 10,000-row `CASE` UPDATE batches (staying under
  the PostgreSQL 65,535 bind-parameter limit) each carrying a SQL-level
  monotonic guard (`expires_at < target`), so only `expires_at` of
  exactly the eligible reviewed rows changes. ONE bounded audit records
  scope, selected lifetime, old/new expiry ranges, derived counts,
  exclusion counts, and the public operation fingerprint — never HMAC
  digests, provider IDs, replay-row UUIDs, or content. A late audit or
  transaction failure rolls back the entire extension.
- Ceilings (documented and enforced): 1,000 selected keys, 50,000
  inspected references, 100 route/model groups; cap+1 is fetched before
  materialization and oversized scopes are refused with a fixed safe
  narrowing instruction — never silently truncated and never reported
  as a complete partial inspection.

No schema/DDL, no migration, no dependency, no UI, no
auth/admission/accounting, no provider-adapter, no runtime
replay-service behavior change (the runtime `CodexReplayService`
lookup/persistence path is byte-identical), no namespace, and no 201+
scope changes. No real provider, client, model, SMTP, Redis, or network
calls; no production database. No expiry-shortening or rollback command
exists by design: extensions are monotonic and irreversible by this
surface; backup/restore is the operator's normal responsibility, and
`inspect`/dry-run re-preview after a failure is the documented recovery
path.

## Layers and exact commands

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python` with
`env -u DATABASE_URL -u TEST_DATABASE_URL`; no ambient `DATABASE_URL`
and no foreign PostgreSQL/Redis; JUnit receipts under `/tmp/slaif200a/`
(disposable).

### New unit suites (pure layer + actual-Typer, no DB)

```text
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_codex_replay_maintenance.py \
  tests/unit/test_cli_codex_replay.py \
  -p no:cacheprovider -q
# 42 passed, 0 failed, 0 errors, 0 skipped, exit 0
```

Per file: `test_codex_replay_maintenance` 30 (strict plan schema, scope
bounds, eligibility/target/monotonic law, first-apply/no-op/already-
applied/stale decision law, post-lock scope revalidation, derived-count
consistency, cap+1 refusal, actual shared service + fake
repository/clock) and `test_cli_codex_replay` 12 (actual-Typer
inspect/extend surface: scope exclusivity, bound validation,
dry-run/execute XOR, mixed-mode and secret-shape refusals, fixed
no-echo JSON errors on stdout with exit 1).

### Focused regression batch (new + touched suites)

```text
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_codex_replay_service.py \
  tests/unit/test_codex_replay_limits.py \
  tests/unit/test_cli_codex.py \
  tests/unit/test_codex_replay_maintenance.py \
  tests/unit/test_cli_codex_replay.py \
  -p no:cacheprovider -q
# 150 passed, 0 failed, 0 errors, 0 skipped, exit 0
```

Per file: existing `test_codex_replay_service` 24 and
`test_codex_replay_limits` 57 unchanged, existing `test_cli_codex` 27
unchanged (no new help oracle was needed), plus the 42 new tests above.

### New owned-PostgreSQL-16 suite

```text
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/integration/test_cli_codex_replay_maintenance_postgres.py \
  -p no:cacheprovider -q
# 14 passed, 0 failed, 0 errors, 0 skipped, exit 0 (~55 s)
```

Owned disposable container (owner label prefix `slaif200a.*.owner`,
tmpfs data directory, loopback-only port binding, `postgres:16`,
alembic head), identity inspected BEFORE readiness and migration, torn
down by exact ID after the module. World (all synthetic): a
`replay-maint` cohort with 8 special keys (active, revoked, suspended,
not-yet-valid, expired key, and a key with an unavailable HMAC
version/failed or mismatched ledger) carrying 18 references covering
all four `item_kind` values and all six exclusion reasons; a
`replay-bulk` cohort with 26 keys and exactly 20,451 references of
which 91 are stored-expired (upserted in chunks under the bind-
parameter limit); plus a dedicated `replay-ttl` cohort/key/reference
(created 2 h before the run) for the one-day TTL case. The 14 ordered
tests proved:

- exact READ-ONLY inspection (8 keys / 18 references, reason counts
  4/1/0/1/1/4, no audit row, no write, no digest/row-UUID leak in the
  output);
- dry-run writes a 0600 plan with zero writes/audits and no digests,
  row UUIDs, or secrets in the file; reuse of an existing path is
  refused;
- execute extends exactly the eligible rows monotonically to
  `created_at` + 365 d (one audit; the late-expiry row and every
  excluded row untouched; every other column byte-equal);
- repeat execute is already-applied with still exactly ONE audit;
- an unrelated committed change just short of the target and an
  unrelated extension beyond the target are both refused stale;
- an eligibility boundary crossed while the service clock advanced
  (row expiry crossing `now` after preview) is refused stale;
- `--include-expired` restores exactly the four explicitly included
  expired rows;
- explicit `--ttl-seconds 86400` targets `created_at` + 86,400 s
  (distinct from the configured one-year default);
- a zero-reference key added to the cohort between preview and execute
  is refused stale (post-lock scope revalidation);
- a REAL-PG concurrent cohort move during the key lock: a second
  asyncpg session holds an uncommitted `UPDATE gateway_keys SET
  cohort_id` on the selected key, the execute thread demonstrably
  blocks on that row lock (the holder observes the waiter through
  `pg_stat_activity` after `SELECT pg_stat_clear_snapshot()`, the
  documented cached-stats-snapshot refresh; NOT `pg_stat_reset()`),
  then commits — execute is refused stale with zero writes and the
  move stands;
- a hand-edited plan file (strictly parsed, round-trips, but with
  altered `selected_keys`/`eligible_references` counts) is refused
  stale against the re-derived fresh counts, and the honest apply
  audit carries the DERIVED 1/1 counts;
- a forced LATE audit failure (hook asserting the NEW expiry is
  visible in the SAME transaction before raising) rolls back the whole
  extension: a fresh session sees every row byte-equal to before with
  zero audit rows;
- scale: all 20,451 references across 26 eligible keys, including the
  91 explicitly included expired rows, extended in ONE reviewed
  operation (every row exactly `created_at` + 365 d, `created_at`
  digest unchanged, exactly ONE audit).

The concurrent-test observer fix and its attribution: an early draft of
that test polled `pg_stat_activity` inside the held transaction without
refreshing statistics; root's independent owned-PG16 probe (receipt
`review-artifacts/cli-feature-round/200-independent-pg-stat-snapshot-
probe.json`, reproducible via the documented cache behavior) showed a
lock holder inside an open transaction sees 0 waiters until
`pg_stat_clear_snapshot()` runs, so the draft could have timed out,
rolled back, and let execute apply an unchanged scope — a false pass.
The test now clears the stats snapshot before each poll (product SQL
and locking unchanged; this is a test-observer correction only), and
the final 14/14 run above postdates that correction.

### Strategic-review probe regressions (fake-repository layer)

Two rounds of root-authored probes exercised the ACTUAL shared
maintenance service with fake repositories/clock before finalization.
Round 1 (5 cases: zero-reference key added to the scope while selected
counts lagged; reference UUID replacement; changed ledger UUID or
available HMAC version; expiry crossing during the reference-row lock
with `include_expired=false`) and round 2 (2 cases: a key leaving the
selected cohort during the key-lock wait; strictly parsed edited
`selected_keys`/`eligible_references` counts producing audit/report
counts that did not match the actual rows) were all reproduced, fixed
as the post-lock scope revalidation + derived-count consistency law
above, and root-rechecked green (receipts
`200-draft-boundary-recheck-20261028T2203Z.json`, 5/5, and
`200-draft-scope-count-recheck-20261028T2214Z.json`, 2/2 — all cases
refuse `ReplayMaintenanceStaleError`). These probes are root
fake-repository evidence, not PostgreSQL proof; the real-PG proofs for
the same laws are the two concurrent/stale PG tests above.

### Gates (focused)

```text
/tmp/slaif192-coding-venv/bin/python -m ruff check app/ tests/
# All checks passed

python3 scripts/check_documentation.py
# DOCUMENTATION_CHECK=OK files=127

git diff --check
# clean

# governance/inventory/drift + new CLI suite:
# 49 selected tests, 48 passed, 1 FAILED (the known unresolved
# documentation-inventory scanner case described below), exit 1
```

A full verification matrix was not run for this objective; final-head
CI remains the root-gated gate.

Known unresolved inventory-checker failure: `codex_replay.py` is the
repository's first separate-file Typer sub-app module (nested under
`codex` as `replay` from `codex.py`). The documentation-inventory
scanner derives a top-level group from the file stem, so for this
module it computes the invocations `slaif-gateway codex-replay
inspect` / `... extend`, which do not exist; the actual registered
invocations are `slaif-gateway codex replay inspect` / `slaif-gateway
codex replay extend`, and both are documented in the Codex command
block and the checked complete command inventory, with the registered
surface proven by the 12 actual-Typer tests above. Repairing the
checker for genuine nested-command coverage requires editing
`tests/unit/test_documentation_inventory.py`, which is outside the
200-a allowed edit scope; per the strategic decision the checker was
NOT edited and no nonexistent `codex-replay` invocation was documented.
This is therefore a KNOWN UNRESOLVED failure of
`tests/unit/test_documentation_inventory.py::test_every_typer_subcommand
_is_named_in_cli_reference` at this head, to be addressed by a bounded
same-PR continuation.

## Privacy, atomicity, and concurrency statements

- No provider item/call ID, HMAC digest, compaction ciphertext, raw
  stored JSON, secret material, prompt, argument, result, or tool
  payload is ever emitted by inspection, plan files, audits, or errors;
  individual replay-row UUIDs are used only inside repository
  selection/fingerprints and are not an export feature. Gateway
  key/cohort/route UUIDs, aggregate timestamps, and counts are the
  allowed safe administration metadata. Recognized secret shapes in
  plan input are refused with fixed no-echo errors (known-shape
  protection, not universal content sanitization).
- Every extension is one audited change in one caller-owned
  transaction on the locked rows; a late audit or transaction failure
  rolls back the entire change (proven in PG with same-transaction
  visibility of the new expiry before the forced failure).
- Plans are staleness-checked AFTER the locks with fresh membership and
  re-derived counts; a repeated apply is recognized as already-applied
  (no duplicate audit) and any other drift is refused stale.
- Plan files are read at cap+1 before parse, written exclusively with
  mode 0600, and never overwritten; every dry-run document is
  non-secret by schema.

## Documentation impact

- `docs/cli-reference.md`: the two new subcommands in the Codex and
  diagnostics command block and the checked complete command inventory,
  plus a descriptive paragraph for the inspect/extend law (scope,
  bounds, plan, monotonic target, lock/revalidation, audit).
- `docs/cli-field-administration.md`: new "Implemented in objective
  200" table (replay expiry metadata, `expires_at` only; no ownership
  administration or transfer); the 200 row removed from the proposed
  table (201-205 remain proposed).
- `docs/database-schema.md` §5.13.1: the TTL-rule bullet now names the
  `codex replay extend` surface as the already-allowed separate audited
  operator update (bounded, lock-protected, monotonic, `expires_at`-
  only, one audit; no DDL).
- This record plus its `docs/verification/README.md` index entry.

## Limitations

- This is synthetic CLI/PostgreSQL evidence, not real
  client/backend qualification: no real provider, client, model, SMTP,
  Redis, or network contact was made, and no production database was
  touched.
- Known unresolved at this head: the documentation-inventory scanner
  failure described above (1 failed test in
  `tests/unit/test_documentation_inventory.py`); the checker file is
  outside the 200-a allowed scope and the repair is deferred to a
  bounded same-PR continuation.
- The 205 full executable-only transcript remains outstanding; no
  all-11-DoD or installed-executable claim.
- No full verification matrix, Docker Compose, browser, or Redis
  coverage was run for this objective; final-head CI is gated by root.
- The plan-file fingerprint guards are optimistic staleness guards, not
  signed authority; they protect against membership/count drift but do
  not certify the reviewing operator's intent.
- Plan files and JUnit receipts under `/tmp/slaif200a/` are disposable
  execution state, not durable evidence.
- This record is commit-specific evidence for the 200 PR head; it does
  not certify later commits, production fitness, security, compliance,
  or scale.

## 200-b ADDENDUM — real nested-command coverage in the documentation inventory checker

Recorded 2026-10-28 for the same 200 PR. This addendum resolves the
200-a "known unresolved inventory-checker failure"; the 200-a text
above (including that failure statement as the 200-a state) remains
unchanged historical record.

### What 200-b changed (test-only, allowed paths only)

- `tests/unit/test_documentation_inventory.py`: the
  command-inventory test now resolves each module's local
  `typer.Typer` instances against `app.add_typer(<alias>, name=...)`
  registrations in the same module OR in importing modules, using a
  small pure static source scan (no production imports, no settings,
  credentials, backend profiles, or providers loaded). A sub-app whose
  Typer object is imported from a separate module therefore resolves
  under its ACTUAL parent namespace — `cli/codex_replay.py` ->
  `codex replay` — instead of its file stem, so the checker now
  demands the real registered invocations `slaif-gateway codex replay
  inspect` / `slaif-gateway codex replay extend` (both present in
  `docs/cli-reference.md`) and can no longer fabricate a
  `codex-replay` alias. In-file nested apps (e.g. `keys policy`,
  `keys external-tools`, `secrets generate`) and all top-level groups
  keep their previous resolution. Both positional
  `@app.command("name")` and explicit `@app.command(name="name")`
  declarations are detected, so changing decorator spelling cannot
  remove inventory coverage.
- New focused self-contained regressions in the same file (pure
  temporary source fixtures): a registered separate-file nested app
  resolving to its parent namespace (with both command-name
  spellings detected and an unregistered module keeping its stem
  group), and a negative case where an undocumented nested command is
  reported missing. A real-repository case asserts the inventory
  contains the two true `codex replay` invocations and contains no
  `codex-replay` alias.
- `docs/cli-reference.md`: unchanged — it already documented the true
  invocations in both the Codex command block and the complete
  command inventory; no operator-facing name correction was needed.
- This addendum.

### Honest history of the rejected workaround

During 200-a, the two registrations were temporarily rewritten to the
behaviorally identical `@app.command(name=...)` spelling so the old
scanner regex would not match them. The strategic review REJECTED
that as coverage-removing; the standard positional decorators were
restored before the 200-a report was published, the checker was left
unedited (outside the 200-a allowed scope), and the failure was
reported as known-unresolved. 200-b repairs the checker itself; the
positional decorators are the spelling verified at the 200-a
implementation head and remain unchanged.

### Actual focused verification (200-b)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
with `env -u DATABASE_URL -u TEST_DATABASE_URL`; no database,
container, provider, client, SMTP, or Redis contact (this repair is
pure static test code).

- Focused batch, one run: **52 passed, 0 failed / 0 errors / 0
  skipped**, exit 0 (`b-gov.xml`): updated
  `test_documentation_inventory` (16 = 13 pre-existing + 3 new),
  `test_oap_governance` (9), `test_documentation_contract_drift` (15,
  consumer guard unchanged), `test_cli_codex_replay` (12 actual-Typer
  registration/help proofs).
- Product-byte preservation: `git diff <200-a implementation> -- app/`
  is EMPTY — every product file is byte-identical to the verified
  200-a implementation (schema/plan contract, service, repository,
  CLI callbacks, fingerprints, transaction/lock/clock/expiry/audit
  logic, runtime replay, accounting).
- The 200-a owned-PG-16 suite (14) and root's independent
  real-reference expiry-wait test are existing 200-a/root evidence and
  were NOT rerun for this inventory fix.
- Gates: `ruff check app/ tests/` clean;
  `python3 scripts/check_documentation.py` -> `DOCUMENTATION_CHECK=OK
  files=127`; `git diff --check` clean.
- No full verification matrix was run; final-head CI remains the
  root-gated gate and is PENDING at this addendum.

The 200-a report and its historical evidence (including the then
known-unresolved failure) are immutable and were not rewritten; the
200-b report records this resolution.

## 200-c ADDENDUM — bounded plan-file, mixed-mode, preview-range, and final-scope repairs

Recorded 2026-10-28 for the same 200 PR. This addendum completes the
concrete boundary gaps found by root's independent probes after 200-b
(actual-schema/Typer/shared-service probes, fake-repository probes, and
a real owned-PG16/actual-Typer membership probe; receipts
`200-final-plan-boundary-probe.json`, `200-independent-final-membership-
defect.json`, `200-c-draft-nested-secret-walk-probe.json`,
`200-c-draft-json-integer-limit-probe.json` under strategic
`review-artifacts/cli-feature-round/`). The 200-a and 200-b text above,
including the historical claims corrected below, remains unchanged
record.

### What 200-c changed (allowed paths only)

Product — EXACTLY the three allowed files, nothing else under `app/`
changed from the 200-b implementation (`8466d93…`):

- **A. `schemas/codex_replay_maintenance.py` (bounded, safe-domain plan
  parsing).** `parse_replay_extend_plan_file` now reads at most
  `REPLAY_PLAN_MAX_BYTES + 1` bytes from a binary stream BEFORE parse
  (an oversize file is refused by the size bound and never fully read).
  Scope `key_id`/`cohort_id` are validated for string type and
  canonical form BEFORE `uuid.UUID` conversion, and `all_active` must
  be exactly `bool`, so ordinary malformed strings, numbers, lists,
  nulls, and non-canonical forms all become the fixed
  `ReplayMaintenanceError` vocabulary (never raw ValueError/TypeError/
  AttributeError). The bounded parser's residual failures are mapped
  into the same safe domain: `json.JSONDecodeError` and a plain
  `ValueError` (e.g. an absurdly long integer literal such as a
  5,000-digit `schema_version` tripping Python's integer
  string-conversion guard) refuse as "not valid JSON", and a
  pathologically deep (valid JSON) structure refusing as "exceeds the
  bounded structure depth" (no recursion-limit change, no malformed
  data accepted). The subsequent recursive `_contains_known_secret_
  shape` walk is guarded the same way (a 600-level nested list parses
  as JSON but exhausts the walk). Unknown-field/duplicate-key/
  nonfinite/strict-canonical/secret-shape checks are preserved.
- **B. Same file (writer before the open, honest static failure).**
  `write_replay_extend_plan_file` now renders, strictly re-validates,
  and size-bounds the document BEFORE opening its new-file-only 0600
  `O_EXCL` descriptor, so a refused plan leaves no file and leaks no
  descriptor (the CodeQuality-flagged forced-oversize FD leak is
  closed). Every successful open enters reliable context-managed
  closure on all subsequent failures (an `os.fdopen` failure closes
  the raw fd). If a write then fails, the fixed error is raised and NO
  path is removed: a partial file may remain at the exact output path
  (the operator removes it and re-runs the dry-run); the path is
  never overwritten (O_EXCL) and no existing/unrelated path is ever
  touched. Format/schema version unchanged.
- **C. `cli/codex_replay.py` (mixed-mode law).** `--execute` now
  refuses EVERY preview/edit flag — the scope selectors
  (`--key-id`/`--cohort-id`/`--all-active`), `--ttl-seconds`,
  `--include-expired`, `--created-from`/`--created-until` — with a
  fixed no-echo stderr message and exit 2 BEFORE the plan file is read
  or any database access. The existing output/execute XOR, reason/
  actor/JSON support are unchanged.
- **D. `services/codex_replay_maintenance.py` (preview range only).**
  The preview `new_expiry` range now reports, per eligible row, the
  ACTUAL post-apply expiry `max(existing expiry, original created_at +
  selected TTL)` — consistent with
  `expected_post_state_fingerprint` and apply. A row whose stored
  expiry is already later or equal no longer advertises a shortening;
  eligibility, target law, monotonic mutation, and the audit (which
  always derived the actual updated range) are unchanged.
- **E. Same file (final membership recheck only).** Apply now
  re-resolves the exact reviewed scope membership AFTER the blocking
  reference-row locks as well as after the key locks, before any
  mutation (fresh clock still sampled after ALL locks). A cohort
  member entering or leaving during the reference-lock wait is refused
  stale with zero expiry writes and zero audits. Deterministic key-then-
  reference lock ordering, count-consistency, full pre/post identity
  fingerprints, and idempotence are preserved; no isolation change,
  global lock, job, or broad scope UPDATE.

Tests (allowed paths only): `tests/unit/test_codex_replay_maintenance.
py` 30 → 48 (finite stream-read request of exactly cap+1 with a
canary beyond the cap; deep-JSON and deep-secret-walk depth refusals;
5,000-digit integer literal; full scope type/canonical matrix; writer
oversize-without-open, forced write failure with close proof and
partial file REMAINING while the sibling path is untouched, existing-
file never overwritten with 0600; later/equal/mixed preview ranges
agreeing with the audited result and an already-applied repeat;
scripted fake-repository final-scope join/leave-during-reference-
wait/stable cases), `tests/unit/test_cli_codex_replay.py` 12 → 17
(each conflicting flag individually refused before plan read and any
DB/apply call, no-echo canary), and
`tests/integration/test_cli_codex_replay_maintenance_postgres.py`
14 → 15 (the new real owned-PG16 reference-lock waiter case below).

### Honest corrections of 200-a claims (never rewritten above)

1. **Bounded read.** The 200-a record claimed the plan file is "read
   at cap+1 before parse". At that head `parse_replay_extend_plan_file`
   used unbounded `Path.read_bytes()`; the 32 KiB cap bounded parsing
   only, after the whole file was consumed. The bounded stream read
   above makes the claim true.
2. **Mixed-mode refusal.** The 200-a record claimed "edit flags
   refused in mixed mode". At that head only the output/execute XOR
   was enforced: `--execute` silently ignored `--key-id`,
   `--ttl-seconds`, `--include-expired`, and the creation bounds and
   proceeded to apply the plan. The explicit per-flag refusal above
   makes the claim true.
3. **Preview new-expiry range.** The 200-a dry run advertised
   `new_expiry` as `created_at + TTL` even for rows whose stored
   expiry was already later — advertising a shortening that apply
   itself never performed. The range now reports the actual
   post-apply expiries.
4. **Bind-limit wording.** The 200-a record described the chunked
   10,000-row `CASE` UPDATE batches as "staying under the PostgreSQL
   65,535 bind-parameter limit". Corrected: the 10k-row statement
   chunks are bounded for the ACTUAL asyncpg wire protocol used by
   this suite; no universal 65,535 driver-limit claim is made. The
   65,535 figure is a PostgreSQL protocol message-size fact, not a
   server or driver bind-variable rule.

### Actual focused verification (200-c)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
with `env -u DATABASE_URL -u TEST_DATABASE_URL`; no ambient
`DATABASE_URL`, no foreign PostgreSQL/Redis; JUnit receipts under
`/tmp/slaif200a/` (disposable).

- New unit suites (pure layer + actual-Typer, no DB): **65 passed,
  0 failed / 0 errors / 0 skipped**, exit 0 (`c-unit-new.xml`):
  `test_codex_replay_maintenance` 48 + `test_cli_codex_replay` 17.
- Focused affected batch: **173 passed, 0 failed / 0 errors / 0
  skipped**, exit 0 (`c-unit-affected.xml`): unchanged
  `test_codex_replay_service` 24, `test_codex_replay_limits` 57,
  `test_cli_codex` 27, plus the 65 above.
- Owned-PostgreSQL-16 suite: **15 passed, 0 failed / 0 errors / 0
  skipped**, exit 0 (`c-pg.xml`): the 14 ordered 200-a proofs
  re-run unchanged at these bytes plus the NEW
  `test_zero_ref_key_join_during_reference_lock_wait_fails_stale`:
  a dedicated cohort with one reference-carrying key (k1) is
  previewed (`selected_keys` 1, `eligible_references` 1); a second
  asyncpg session BEGINs, takes `FOR UPDATE` on k1's reference row
  (the lock apply takes LAST), captures its `pg_backend_pid()`, and —
  after `SELECT pg_stat_clear_snapshot()` before each poll (the
  documented cached-stats refresh, NOT `pg_stat_reset()`) — requires
  another PID in `wait_event_type = 'Lock'` whose
  `pg_blocking_pids` set includes the holder before committing a
  zero-reference key (k2) joining the cohort; the committed join
  lands exactly as the reference lock releases, so only the final
  post-reference-lock revalidation can observe it. Execute is
  refused stale (exit 1, JSON `invalid_value`, "pre-state no longer
  matches") with every k1 reference column byte-equal (full row
  snapshot), expiries unchanged, and zero audits, while the unreviewed
  join stands (cohort count 2).
- Governance/inventory/drift: **40 passed, 0 failed / 0 errors / 0
  skipped**, exit 0 (`c-gov.xml`): `test_documentation_inventory`
  16 (the accepted 200-b repair, file byte-unchanged here),
  `test_oap_governance` 9, `test_documentation_contract_drift` 15.
- Gates: `ruff check app/ tests/` clean;
  `python3 scripts/check_documentation.py` -> `DOCUMENTATION_CHECK=OK
  files=127`; `git diff --check` clean.
- Product-byte preservation: `git diff 8466d93 -- app/` shows EXACTLY
  the three allowed files (schema, service, CLI);
  `app/slaif_gateway/db/repositories/codex_replay.py` and every other
  product file are byte-identical to the 200-b implementation;
  `tests/unit/test_documentation_inventory.py` byte-identical.

Root independently rechecked the repaired plan boundary (3-product
hashes) and re-ran the actual-Typer/owned-PG16 reference-wait cohort
join and the real expiry-crossing case — both PASS with stale refusal,
all reference columns unchanged, and zero audits (root receipts
`200-c-independent-plan-boundary-recheck.json` and
`200-c-independent-realpg-rechecks.json`; root evidence, not agent
runs).

### Documentation impact (200-c)

- `docs/cli-reference.md`: the extend paragraph now states the
  bounded cap+1 stream read, the dry-run `new_expiry_range` semantics
  (actual post-apply expiries, never a shortening), the explicit
  per-flag `--execute` mixed-mode refusal BEFORE plan read/database
  access, and the double membership revalidation (after the key
  locks AND after the reference-row locks).
- `docs/cli-field-administration.md`: the objective-200 row carries
  the same two corrections.
- This addendum.

### Limitations (200-c)

- No full verification matrix was run; final-head CI remains the
  root-gated gate and is PENDING at this addendum.
- The deep-JSON depth refusals are proven at the CPython recursion
  limit of this interpreter (a 10,000-level structure refuses; a
  3,000-level one parses) — the guard maps the interpreter failure
  into the fixed domain rather than raising limits.
- The writer's honest static semantics intentionally leave a partial
  file at the exact output path after a forced write failure
  (documented); no cleanup/rebinding machinery was added.

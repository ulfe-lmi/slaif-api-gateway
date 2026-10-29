# OAP Objective 200-a — final report: replay reference inspection and reviewed expiry extensions

Work order: `oap/orders/200-a-replay-reference-maintenance.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `200-a` (5 bytes, no trailing newline); order sha256
`e3054c664a9c595e079dcd9bd43cfb5648ff27d6a87efa615fe6eb6567106f40`
(14,509 bytes), active pointer sha256
`4235ee5b0684532541b10d466d02d31baef39a817d2c9ba4f36283a20ea9f73f`,
both verified before committing and re-verified in the implementation
commit).
Branch: `oap/200-replay-reference-maintenance`; base: `main`
`4c265bc3c9668a66bb1643915d442fb8c411ff11` (re-fetched and re-verified
unchanged at publication time).
PR mode: CREATE_NEW_PR — the ONE objective-200 PR #356,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/356, base `main`,
title "Inspect retained Codex replay references and apply reviewed
expiry extensions" (OPEN/MERGEABLE at publication). The coding agent
never merges; no auto-merge; root reviews independently and
guard-merges.

Implementation head SHA: 9873a4a7a95e4df1fe1ed7d02b97c338d69fa48f
Report publication commit: SELF

## Predecessor state (immutable)

Objective 199 is terminal: PR #355 merged into `main` as
`4c265bc3c9668a66bb1643915d442fb8c411ff11` on 2026-10-28T18:48:54Z,
with ALL 10 final-SELF `7754f70` checks and ALL 9 actual main/3
workflows (2 push + 1 dynamic) SUCCESS, verified
2026-10-28T21:26:07Z; accepted tree
`a9a94a4dafcb64d51b66645a7573cd476675917d`. The 199-a/b/c/d orders and
reports are immutable and unamended. Objectives 200-205 were INERT
before activation; after this publication, 201-205 remain INERT and
no other 200 suffix was activated. No schema, key-migration,
deployment, or release action was taken by this objective.

## Implementation commit (this round)

1. `9873a4a7a95e4df1fe1ed7d02b97c338d69fa48f` — "Inspect retained
   Codex replay references and apply reviewed expiry extensions
   (200-a)": the strategic order (bytes verified unchanged, sha256
   above) + exact `oap/active` = `200-a` + the bounded implementation,
   tests, docs, and verification record listed below (15 files).

No schema migration, no DDL, no new dependency, no
workflow/config/template/CSS change, no UI change, and no runtime
auth/admission/accounting/forwarding/Redis behavior was modified. The
runtime `CodexReplayService` lookup/persistence path,
`db/repositories/codex_replay.py` runtime methods, key material,
quotas, ledgers, fences, routes, providers, and one-time delivery
state are unchanged. The 200 PR head's first parent is the verified
base `4c265bc`.

## Allowed diff (implementation commit, 15 files)

Product (allowed paths only):

- `app/slaif_gateway/services/codex_replay_maintenance.py` — NEW typed
  shared service: read-only `inspect_replay_references`,
  `preview_replay_extend`, `apply_replay_extend` with the final
  decision law; ceilings MAX_SELECTED_KEYS=1,000 /
  MAX_INSPECTED_REFERENCES=50,000 / MAX_ROUTE_MODEL_GROUPS=100 with
  cap+1 refusal; deterministic lock order (keys FOR UPDATE, then rows
  FOR UPDATE); post-lock scope re-resolution (set equality) and
  re-derived eligible counts; fresh clock AFTER all locks; six fixed
  exclusion-reason codes; first-apply / already-applied no-op /
  stale decision law (a zero-diff first apply makes zero writes and
  zero audits; an already-applied repeat adds no duplicate audit);
  target = original stored `created_at` + selected TTL, monotonic
  only.
- `app/slaif_gateway/schemas/codex_replay_maintenance.py` — NEW strict
  version-1 NON-secret plan schema: 32 KiB cap read at cap+1,
  unknown-field/duplicate-key/nonfinite/oversize and recognized
  secret-shape refusal with fixed no-echo errors, exclusive 0600
  write (never overwritten), and the three public hex-64 fingerprints
  (full source identity with key markers, expiry-stripped source
  state, computed post-state).
- `app/slaif_gateway/cli/codex_replay.py` — NEW Typer sub-app
  (`codex replay inspect` / `codex replay extend`): exactly-one-scope
  law, UTC creation-bound validation, dry-run/execute mutex,
  secret-shape guarded reason, fixed safe JSON/text output.
- `app/slaif_gateway/cli/codex.py` — registration only
  (`app.add_typer(..., name="replay")`); no existing command touched.
- `app/slaif_gateway/db/repositories/codex_replay.py` — additive
  administrative selection/summary/lock/expiry methods only,
  including chunked 10k-row `CASE` UPDATE batches with a SQL-level
  monotonic guard (`expires_at < target`) under the 65,535
  bind-parameter limit; runtime methods unchanged.

Tests (allowed paths only):

- `tests/unit/test_codex_replay_maintenance.py` (NEW, 30): plan
  schema, scope/bounds, eligibility/target/monotonic law, decision
  law, post-lock scope revalidation, derived-count consistency, cap+1
  refusal, and the two rounds of root strategic-review probe
  regressions (TestDraftBoundaryRegressions 7,
  TestScopeCountRegressions 2) — actual shared service with fake
  repositories/clock.
- `tests/unit/test_cli_codex_replay.py` (NEW, 12): actual-Typer
  surface (scope exclusivity, mode mutex, TTL range, reason law,
  dry-run 0600 new-file-only, strict refusals without canary echo,
  fixed no-echo JSON errors on stdout with exit 1).
- `tests/integration/test_cli_codex_replay_maintenance_postgres.py`
  (NEW, 14): owned-PG16 ordered proofs listed below.
- `tests/unit/test_cli_codex.py` unchanged (no new help oracle was
  needed).

Docs (allowed paths only):

- `docs/verification/2026-10-28-cli-replay-maintenance.md` (NEW record
  incl. the known-unresolved inventory failure) and its
  `docs/verification/README.md` index entry.
- `docs/cli-reference.md`: the two subcommands in the Codex command
  block and the checked complete command inventory, plus the
  descriptive law paragraph.
- `docs/cli-field-administration.md`: new objective-200 table
  (`expires_at` only; NOT ownership administration or transfer); the
  200 row removed from the proposed table (201-205 remain proposed).
- `docs/database-schema.md` §5.13.1: the TTL-rule bullet now names
  `codex replay extend` as the already-allowed separate audited
  operator update (bounded, lock-protected, monotonic,
  `expires_at`-only, one audit; NO DDL).

OAP: exact `oap/active` = `200-a` (5 bytes, no newline) and the
strategic order, both byte-verified unchanged at the implementation
head.

## Actual focused verification (this execution)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
(Python 3.12) with `env -u DATABASE_URL -u TEST_DATABASE_URL`; no
ambient `DATABASE_URL`, no foreign PostgreSQL/Redis, no real
provider/model/client/SMTP/Redis contact, no production database.
JUnit receipts under `/tmp/slaif200a/` (disposable).

- New unit suites, final bytes: **42 passed, 0 failed / 0 errors /
  0 skipped**, exit 0 (30 + 12).
- Focused affected batch (new + touched suites), one run at the final
  implementation bytes: **150 passed, 0 failed / 0 errors / 0
  skipped**, exit 0 (`unit-final2.xml`): `test_codex_replay_service`
  24, `test_codex_replay_limits` 57, `test_cli_codex` 27 (all
  unchanged), plus the 42 new tests.
- Owned-PostgreSQL-16 suite (label prefix `slaif200a.*.owner`, tmpfs,
  loopback-only, identity inspected before readiness, exact-ID
  cleanup): **14 passed, 0 failed / 0 errors / 0 skipped** (`pg6.xml`
  at the identical final product bytes — the only byte delta since
  that run was a decorator-spelling edit that was fully reverted,
  leaving `app/` and `tests/` byte-equal): exact read-only
  inspection; dry-run 0600 zero-writes; monotonic execute + ONE safe
  audit with every other column byte-equal; already-applied repeat
  without duplicate audit; unrelated short-of-target and
  beyond-target changes refused stale; eligibility-boundary crossing
  refused stale; `--include-expired` restores exactly the included
  rows; explicit one-day TTL targets `created_at` + 86,400 s;
  zero-reference key added between preview and execute refused stale;
  REAL-PG concurrent cohort move during the key lock refused stale
  with zero writes and the move standing (the lock-holder observer
  uses the documented `pg_stat_clear_snapshot()` refresh, per root's
  independent owned-PG16 probe receipt
  `200-independent-pg-stat-snapshot-probe.json`; NOT
  `pg_stat_reset()`; product SQL/locking unchanged); hand-edited plan
  counts refused against re-derived fresh counts with the honest
  derived 1/1 audit; forced LATE audit failure (same-transaction
  visibility of the new expiry before raising) rolled back atomically
  (fresh session unchanged, 0 audits); and the encountered scale:
  20,451 references / 26 keys / 91 expired extended in ONE reviewed
  operation (every row exactly `created_at` + 365 d, `created_at`
  digest unchanged, exactly ONE audit).
- Strategic-review probe regressions: two rounds of root-authored
  probes (actual shared service + fake repositories) — round 1 (5
  cases) and round 2 (2 cases) — were reproduced, fixed as the
  post-lock revalidation + derived-count law, and root-rechecked
  green (receipts `200-draft-boundary-recheck-20261028T2203Z.json`
  5/5 and `200-draft-scope-count-recheck-20261028T2214Z.json` 2/2,
  all refusing `ReplayMaintenanceStaleError`). These are root
  fake-repository evidence, not PostgreSQL proof; the real-PG proofs
  for the same laws are the concurrent/stale PG tests above.
- Gates at final bytes: `ruff check app/ tests/` clean;
  `python3 scripts/check_documentation.py` -> `DOCUMENTATION_CHECK=OK
  files=127`; `git diff --check` clean.
- Governance/inventory/drift, one run at final bytes
  (`gov-final.xml`): **36 passed, 1 FAILED, 0 errors, 0 skipped** —
  the single failure is the KNOWN UNRESOLVED documentation-inventory
  scanner case documented below. Together with the 12 new
  actual-Typer tests (in the 150 above): 49 selected tests, 48
  passed, 1 failed.

## Known unresolved failure (explicit)

`tests/unit/test_documentation_inventory.py::
test_every_typer_subcommand_is_named_in_cli_reference` FAILS at this
head (1/13 in that file). The scanner derives a top-level group from
the file stem; `codex_replay.py` is the repository's first
separate-file Typer sub-app module (nested under `codex` as `replay`
from `codex.py`), so the scanner computes the invocations
`slaif-gateway codex-replay inspect` / `... extend`, which do not
exist. The actual registered invocations (`codex replay inspect` /
`codex replay extend`) ARE documented in both the Codex command block
and the checked complete command inventory of `docs/cli-reference.md`,
and the registered surface is proven by the 12 actual-Typer tests.
Per the strategic decision taken during this execution: the standard
positional `@app.command(...)` decorators are KEPT (a
behaviorally-identical `name=` spelling was tried and then reverted
as coverage-removing and not accepted), no nonexistent
`codex-replay` invocation was documented, and the checker was NOT
edited because `tests/unit/test_documentation_inventory.py` is
outside the 200-a allowed edit scope. The repair of genuine
nested-command inventory coverage is deferred to a bounded 200-b on
this same PR.

## Security and privacy statements

- No provider item/call ID, HMAC digest, compaction ciphertext, raw
  stored JSON, secret material, prompt, argument, result, or tool
  payload is emitted by inspection, plan files, audits, or errors;
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
- Plans are staleness-checked AFTER the locks with fresh membership
  and re-derived counts; the saved plan is a public optimistic guard,
  not signed authority; repeated applies are recognized
  (already-applied, no duplicate audit) and any other drift is
  refused stale.
- Plan files are read at cap+1 before parse, written exclusively with
  mode 0600, and never overwritten; the schema is non-secret by
  construction.
- No real provider, client, model, SMTP, Redis, or network contact
  was made by this execution's evidence; no production database was
  touched.

## Honest state and limitations

- Final-head CI is root-gated and its state is **PENDING** at this
  publication: head `9873a4a` was pushed immediately before report
  publication. No CI result is claimed here. The new SELF must have
  all checks green before root merges.
- The documentation-inventory scanner failure above is KNOWN
  UNRESOLVED at this head (explicit, strategic decision); the bounded
  same-PR continuation 200-b will repair it.
- No full verification matrix, browser, or Docker Compose coverage
  was run for 200-a. This is synthetic CLI/PostgreSQL evidence, not
  real client/backend qualification; the 205 full executable-only
  transcript remains outstanding. No all-11-DoD, installed-
  executable, or release claim.
- Plan files and JUnit receipts under `/tmp/slaif200a/` are
  disposable execution state, not durable evidence.
- This report is immutable: subsequent 200 suffixes do not edit it.

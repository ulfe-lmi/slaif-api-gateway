# OAP Objective 200-c — final report: bounded plan-file, mixed-mode, preview-range, and final-scope repairs

Work order: `oap/orders/200-c-plan-boundaries-and-final-scope.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `200-c` (5 bytes, no trailing newline); order sha256
`32731646a5f93fa2e6c0715ceffff1199287a7c17f4cbb103f1325a059509761`
(11,713 bytes), active pointer sha256
`aed88235368e97c2fcc79351106e85255addbae8ef7a5fd902a21381a8cafe44`,
both verified before committing and re-verified at HEAD).
Branch: `oap/200-replay-reference-maintenance`; base: `main`
`4c265bc3c9668a66bb1643915d442fb8c411ff11` (unchanged).
PR mode: AMEND_EXISTING_PR — the SAME unique PR #356 created by
200-a, https://github.com/ulfe-lmi/slaif-api-gateway/pull/356, base
`main`, OPEN/MERGEABLE with head at this implementation at
publication. The coding agent never merges; no auto-merge; root
reviews independently and guard-merges.

Implementation head SHA: d86bc0d3933481a2d4797ebdfc1bc4abbd775d97
Report publication commit: SELF

## Predecessor state (immutable)

200-b is complete on this branch: implementation head
`8466d9364bd93175a8a370e8f5bc51d6af86b628` and report commit
`32a9f0ca3c231eaf95d88667ce4ad089a5d08f3b` (order sha256
`337ce4d5cdfb4716e64d1b2975f62ea1240c8a561b936c43d903d35d084d5ac2`,
report sha256 `2f6296b01e69f1c82a97b806a7cd2c2cca923bfd02510bd445c328a9d54ef0e9`).
200-a implementation head `9873a4a7a95e4df1fe1ed7d02b97c338d69fa48f`,
report commit `64338b08ee146f4a66658a1d27ef3b50dba7afef` (report
sha256 `6a769f4cf80fffcb2c953d4f400a37306a808726facb3eb2f400ca13a6f459a0`).
Root's 200-b sole response was polled CLOSED with the exact response
OK; it was never reopened or re-signaled. Objective 199 remains
terminal (PR #355 merged); 201-205 remain INERT; no other 200 suffix
was activated; the 205 installed-executable transcript/all-11-DoD
remains unproven. The 200-a/200-b orders and reports are immutable
and were NOT edited.

## Implementation commit (this round)

1. `d86bc0d3933481a2d4797ebdfc1bc4abbd775d97` — "Repair the reviewed
   plan boundary, mixed-mode law, and final scope recheck (200-c)":
   the strategic order (bytes verified unchanged, sha256 above) +
   exact `oap/active` = `200-c` + the allowed changes listed below
   (11 files total). First parent is the 200-b report commit
   `32a9f0c`.

Product-byte preservation: `git diff 8466d9364bd93175a8a370e8f5bc51d6af86b628
d86bc0d3933481a2d4797ebdfc1bc4abbd775d97 -- app/` shows EXACTLY the
three allowed product files (`schemas/codex_replay_maintenance.py`,
`services/codex_replay_maintenance.py`, `cli/codex_replay.py`); every
other product file — including
`app/slaif_gateway/db/repositories/codex_replay.py`, the runtime
replay service, and all accounting code — is BYTE-IDENTICAL to the
200-b implementation. `tests/unit/test_documentation_inventory.py`
is byte-identical to the accepted 200-b repair. No schema/DDL, no
migration, no dependency, no workflow, no UI, no config, no 201+
change; no release action.

## What changed (allowed paths only)

Product (3 files):

- A. `app/slaif_gateway/schemas/codex_replay_maintenance.py`:
  bounded stream read of at most `REPLAY_PLAN_MAX_BYTES + 1` bytes
  before parse; scope UUIDs validated for string type and canonical
  form before conversion and `all_active` strict-boolean; residual
  bounded-parser failures (JSONDecodeError, the plain ValueError from
  absurdly long integer literals, deep-structure RecursionError) and
  the recursive secret-shape walk mapped into the fixed no-echo
  `ReplayMaintenanceError` vocabulary without raising interpreter
  limits; writer renders/strict-re-validates/size-bounds BEFORE
  opening the new-file-only 0600 O_EXCL descriptor, closes the raw fd
  on `os.fdopen` failure, enters context-managed closure on all later
  failures, and on a forced write failure raises the fixed error with
  NO path removed (a partial file may remain at the exact output
  path, never overwritten).
- C. `app/slaif_gateway/cli/codex_replay.py`: `--execute` refuses
  every preview/edit flag (scope selectors, `--ttl-seconds`,
  `--include-expired`, `--created-from`/`--created-until`) with a
  fixed no-echo message and exit 2 BEFORE plan read or database
  access; existing XOR/reason/actor/JSON support unchanged.
- D/E. `app/slaif_gateway/services/codex_replay_maintenance.py`
  (preview range + final membership recheck ONLY): the preview
  `new_expiry` range now reports the actual post-apply expiry
  `max(existing expiry, original created_at + selected TTL)` per
  eligible row, consistent with
  `expected_post_state_fingerprint` and apply; apply re-resolves the
  exact reviewed scope membership AFTER the blocking reference-row
  locks (in addition to after the key locks), before mutation, with
  the fresh clock still sampled after ALL locks. Deterministic
  key-then-reference lock order, count consistency, full pre/post
  identity fingerprints, and idempotence preserved; no isolation
  change, global lock, job, or broad scope UPDATE.

Tests (3 files): `tests/unit/test_codex_replay_maintenance.py`
30 → 48, `tests/unit/test_cli_codex_replay.py` 12 → 17,
`tests/integration/test_cli_codex_replay_maintenance_postgres.py`
14 → 15 (new real owned-PG16 reference-lock waiter case).

Docs (3 files): the two operator-contract corrections plus the
200-c addendum (details below).

Order/active (2 files): committed unchanged as specified.

## Verification (exact layers and receipts)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
with `env -u DATABASE_URL -u TEST_DATABASE_URL`; no ambient
`DATABASE_URL`, no foreign PostgreSQL/Redis/container; JUnit receipts
under `/tmp/slaif200a/` (disposable).

- New unit suites (pure layer + actual-Typer, no DB): 65 passed /
  0 failed / 0 errors / 0 skipped, exit 0 —
  `test_codex_replay_maintenance` 48 + `test_cli_codex_replay` 17
  (finite cap+1 stream-read request with a canary beyond the cap;
  deep-JSON and deep-secret-walk depth refusals; 5,000-digit integer
  literal; scope type/canonical matrix; writer oversize-without-open,
  forced write-failure close proof with the partial file REMAINING
  and the sibling untouched, existing-file non-overwrite with 0600;
  later/equal/mixed preview ranges agreeing with the audited result
  plus an already-applied repeat; scripted fake-repository
  final-scope join/leave-during-reference-wait/stable cases; each
  conflicting CLI flag refused before plan read and any DB/apply
  call with a no-echo canary).
- Focused affected batch: 173 passed / 0 failed / 0 errors / 0
  skipped, exit 0 — unchanged `test_codex_replay_service` 24,
  `test_codex_replay_limits` 57, `test_cli_codex` 27, plus the 65
  above (overlap with the new-suite run: the 65).
- Owned-PostgreSQL-16 suite (unique owned label, loopback, tmpfs,
  identity inspected before readiness/migration, exact-ID cleanup):
  15 passed / 0 failed / 0 errors / 0 skipped, exit 0 — the 14
  ordered 200-a proofs re-run unchanged at these bytes plus the NEW
  `test_zero_ref_key_join_during_reference_lock_wait_fails_stale`:
  a real asyncpg holder takes `FOR UPDATE` on the reviewed reference
  row (the lock apply takes LAST), then — after
  `SELECT pg_stat_clear_snapshot()` before each poll — requires
  another PID in `wait_event_type = 'Lock'` whose
  `pg_blocking_pids` set includes the holder before committing a
  zero-reference key joining the cohort exactly as the lock
  releases; execute is refused stale (exit 1, JSON
  `invalid_value`, "pre-state no longer matches") with every
  reference column byte-equal (full row snapshot), expiries
  unchanged, zero audits, and the unreviewed join standing (cohort
  count 2).
- Governance/inventory/drift: 40 passed / 0 failed / 0 errors / 0
  skipped, exit 0 — `test_documentation_inventory` 16 (the accepted
  200-b repair, file byte-unchanged here), `test_oap_governance` 9,
  `test_documentation_contract_drift` 15.
- Gates: `ruff check app/ tests/` clean;
  `python3 scripts/check_documentation.py` -> `DOCUMENTATION_CHECK=OK
  files=127`; `git diff --check` clean.

Root independently rechecked the repaired plan boundary at the
3-product hashes and re-ran the actual-Typer/owned-PG16 reference-
wait cohort join and the real expiry-crossing case — both PASS with
stale refusal, all reference columns unchanged, and zero audits
(root receipts `200-c-independent-plan-boundary-recheck.json` and
`200-c-independent-realpg-rechecks.json`; root evidence, not agent
runs, and no duplicate agent rerun was performed).

## Remaining finding recorded for a bounded 200-d (NOT fixed in c)

Root's post-c strict-parse probe (receipt
`200-c-reviewed-target-consistency-probe.json`): parsing a valid
preview plan and changing ONLY `ttl_seconds` (e.g. to 180 days),
leaving the reviewed ranges and all three fingerprints untouched, is
accepted by the actual service/fake repository and updates rows to a
target different from the range the CLI advertised (updated to the
edited TTL target while the plan advertised the previewed one). This
is a plan self-consistency/reporting defect, NOT an authentication
bypass, and it does not require tamper-proof or signed plans. The
200-c service allowlist is preview-range and final-membership
recheck ONLY, so this was deliberately NOT implemented here. Expected
minimal 200-d shape: derive/compare the actual expected post-state
under the reviewed TTL before the first mutation, plus fresh report-
descriptor consistency as necessary; no schema or new framework. All
green c proofs and the current PG oracles stand; 201 remains inert.

## CodeQuality thread

Thread `PRRT_kwDOSLm-qM6xWx_i` ("File is not always closed", the old
writer's forced-oversize FD leak) was answered at this head (the
writer now serializes/bounds/validates before any open; no
descriptor leak on any refusal path; context-managed closure on all
subsequent failures) and marked RESOLVED. No workflow suppression.

## Documentation impact

Documentation updated: docs/cli-reference.md,
docs/cli-field-administration.md,
docs/verification/2026-10-28-cli-replay-maintenance.md

- `docs/cli-reference.md`: the extend paragraph now states the
  bounded cap+1 stream read, the dry-run `new_expiry_range`
  semantics (actual post-apply expiries, never a shortening), the
  explicit per-flag `--execute` mixed-mode refusal BEFORE plan
  read/database access, and the double membership revalidation
  (after the key locks AND after the reference-row locks).
- `docs/cli-field-administration.md`: the objective-200 row carries
  the same two corrections.
- `docs/verification/2026-10-28-cli-replay-maintenance.md`: 200-c
  addendum appended (A-E repairs; honest corrections of the 200-a
  "read at cap+1" and "edit flags refused" claims; the preview
  shortening advertisement; the bind-limit wording correction —
  10k-row chunks are bounded for the actual asyncpg wire protocol,
  no universal 65,535 driver-limit claim; exact evidence counts;
  product-byte preservation). The 200-a/200-b historical text is
  unchanged.

## CI / final-head state

Final-head CI for the new head is PENDING at this publication and
remains the root-gated gate; no all-green claim is made here. All
final SELF checks are mandatory before any merge. No full local
verification matrix was run; no release, RC, production, security,
or compliance claim follows. The 205 executable-only transcript
remains outstanding.

201-205 remain INERT. Same unique PR #356; the coding agent does not
merge, auto-merge, or self-activate.

# Objective 198-a — faithful standard-key cloning (`keys clone`) verification

Dated evidence for the faithful standard-key cloning objective (198-a),
which replaces operator Python cloning with a shared, auditable,
retry-safe plan/execute operation and executable CLI. This is a focused
objective record, not a full-matrix qualification, and not a release or
production-certification decision.

## Scope

Bounded CLI/service functionality built on existing services (no schema
migration, no DDL, no new dependencies, no API/template/CSS changes, no
runtime forwarding/accounting/Redis changes):

- New `app/slaif_gateway/schemas/key_clone.py`: strict version-1 NON-secret
  clone-plan document (128 KiB envelope bound; unknown/duplicate JSON
  fields, bad types, non-UTF-8, and oversized files rejected with fixed
  safe errors that never echo file bodies, paths, or values; optional
  non-authoritative `preview` block).
- New `app/slaif_gateway/services/key_clone_service.py`: plan build
  (read-only, no audit) and execute (source `FOR UPDATE` lock, eligibility
  revalidation, receipt-first deduplication, strict canonical re-derivation
  and fingerprint comparison, creation + one-time secret + optional pending
  delivery + bounded safe receipt + clone audit in one caller-owned
  transaction).
- `app/slaif_gateway/db/repositories/keys.py`: narrowly typed receipt
  lookup (JSONB containment namespaced by `(source, operation)`, scoped to
  the target owner) and receipt persistence on the NEW target key's
  metadata (`metadata_json`, no DDL).
- `app/slaif_gateway/cli/keys.py`: `keys clone` with `--dry-run PATH` /
  `--execute PATH` (exactly one), explicit validity mode options, fresh
  `--confirm-external-tool-fenced`, and EXACTLY ONE explicit one-time key
  channel for execute (`--show-plaintext`, `--secret-output-file`, or
  `--email-delivery pending/send-now/enqueue`).
- `tests/unit/test_documentation_contract_drift.py`: one justified exact
  allowlist entry for the clone service's read-only consumption of
  `external_tool_policy_contract` (fenced-policy detection only; no runtime
  authority).

Canonical policy semantics are reused unchanged from the 196 export/parser/
create-builder: providers (explicit `null` = unrestricted vs `[]` = deny
all), exact Responses/module identity/grants, nullable lifetime quotas,
nullable rate overrides/window, lazy policy, supported Chat live-burn, and
external policy. Non-default or malformed raw
`responses_streaming_live_burn` source policies are refused (creation
always writes the default), and policy values carrying RECOGNIZED secret
shapes (gateway key text, bearer token, provider key, sensitive
assignment — the existing redaction patterns) are refused with a fixed
safe unsupported-source explanation instead of being emitted or silently
altered (known-shape protection, not universal content sanitization).

## Layers and exact commands

Environment: `/tmp/slaif192-coding-venv` (Python 3.12, editable project).
`PYTHONPATH=app` for all runs. No ambient `DATABASE_URL`; the integration
layer runs against its own owned PostgreSQL 16 container only.

### New unit suites (pure layer, no DB)

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_key_clone_service.py \
  tests/unit/test_cli_keys_clone.py -p no:cacheprovider \
  --junitxml=/tmp/slaif198/unit-clone.xml -q
# 40 passed (19 + 21; 0 failed, 0 errors, 0 skipped), exit 0
```

- 19 service cases (fakes, no DB): strict non-secret plan document with
  source fingerprint and preview; ineligible sources (calibration purpose,
  discovery mode, suspended/revoked, fenced, not-yet-valid, expired)
  refused without mutation/audit; missing target owner/cohort; default
  allowed vs non-default/malformed Responses-streaming live-burn refused;
  recognized secret shapes in kept policy strings refused; fingerprint
  stable under usage drift but moved by configuration change; validity
  modes (copy-source-expiry / duration-from-now / absolute) with
  invalid/expired windows rejected at plan and execute time; tampered plan
  documents (unknown/duplicate fields, bad types, bad fingerprint/UUID)
  rejected; execute happy path (independent target, receipt, pending
  delivery, one clone audit with safe values only); stale plan refused
  before any write; exact repeat returns `already-applied` (no new
  key/secret/audit, no plaintext); completed operation stays identifiable
  after the source is edited; same-operation changed plan refused; fresh
  fenced confirmation required; missing source = not found; source
  became ineligible = refused; canonical semantics (providers absent /
  explicit `null` / `[]`, nullable rate members, unlimited quotas stay
  `None`).
- 21 actual-Typer CLI cases (DB helpers faked): exactly-one mode flag;
  dry-run required flags and per-mode consistency; plan file written 0600
  and never overwritten; JSON output byte-equivalent to the file and
  re-parseable by the same strict schema; dry-run text output safe
  (no policy detail, no secret); service errors surfaced as fixed safe
  codes; execute requires `--reason` and exactly one channel (zero/two
  refused before DB); `--show-plaintext` JSON includes the plaintext
  exactly once; `--secret-output-file` writes 0600 with no plaintext in
  output and refuses an existing file BEFORE any DB call;
  `--email-delivery pending/send-now/enqueue` suppress plaintext and
  report safe delivery/task metadata; send-now failure exits nonzero with
  safe IDs; already-applied repeats never emit plaintext or re-run the
  operation; missing/tampered plan files rejected without DB contact;
  post-commit output failure exits nonzero with safe created-key/secret/
  delivery IDs + recovery guidance and never re-clones;
  `--confirm-external-tool-fenced`/`--actor-admin-id` pass-through.

### New owned-PostgreSQL-16 suite

```text
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/integration/test_cli_key_clone_postgres.py -p no:cacheprovider \
  --junitxml=/tmp/slaif198/integration-clone.xml
# 5 passed, 0 failed, 0 errors, 0 skipped, exit 0
```

Ownership discipline (mirrors the 184/185/197 fixtures): a NEW
`postgres:16` container labeled `slaif198a.owner`, bound to 127.0.0.1
only, tmpfs-backed, identity re-inspected AFTER creation and BEFORE
readiness/migration, and removed by exact container ID in `finally`
(verified absent after the run; no ambient/unverified `DATABASE_URL`, no
shared or foreign DB, no apt/HPC/production).

- Student-style source (explicit `null` provider policy = unrestricted,
  unlimited cost, configured token limit, nullable request limit):
  dry-run wrote a 0600 plan and mutated NOTHING (full source column
  snapshot + table counts identical, no audit); execute with
  `--email-delivery pending` created the target with EXACT canonical
  configuration equality (`keys policy export` documents identical),
  independent material (different `token_hash`, `hmac_key_version = 1`,
  IDs), zero usage, no copied replay/ledger rows, `copy-source-expiry`
  window (from execution, to the source's fresh `valid_until`), a bounded
  safe `clone_receipt` on the target (safe UUIDs/fingerprint only — no key
  material), exactly one `gateway_key_cloned` audit with safe values, and
  the source completely unchanged with its planted finalized usage +
  `codex_replay_references` evidence intact.
- Beta-style source (deny-all `[]` providers, cost/token/request limits,
  configured rate members): exact canonical equality including `[]` and
  the rate block; exact repeat returned `already-applied` with no new
  key/secret/plaintext; a same-operation tampered plan was refused with
  `key_clone_plan_mismatch`; unknown-field and >128 KiB plan files were
  rejected before any DB write; source unchanged.
- Forced LATE clone-audit failure (real service path, monkeypatched only
  at the final `gateway_key_cloned` action): the hook observed the new
  target key + receipt + one-time secret already visible in the SAME
  transaction before raising; the CLI exited nonzero and a fresh session
  confirmed the caller transaction rolled back ALL new rows (counts and
  every source column identical; zero persisted receipts for the
  operation).
- TWO separate processes (separate OS processes, separate DB sessions)
  concurrently executing the SAME plan file: statuses were exactly
  `{created, already-applied}` with one shared target; exactly one
  one-time secret, one receipt, and one clone audit for the operation;
  only the created process wrote a secret file; neither output contained
  plaintext. `current_setting('transaction_isolation')` = `read
  committed`, the supported deduplication boundary (a pre-established
  REPEATABLE READ snapshot is documented as unsupported).
- Simulated post-commit mail failure (`--email-delivery send-now` pointed
  at a refused local port 127.0.0.1:1): the commit succeeded, the mail
  failed AFTER commit, the CLI exited nonzero with safe IDs and
  `email_delivery_status = failed` (no plaintext); the exact retry then
  returned `already-applied` with no second key, no plaintext, and no
  auto-resend.

### Gates (focused)

```text
# New + touched unit governance:
PYTHONPATH=app .../python -m pytest \
  tests/unit/test_oap_governance.py \
  tests/unit/test_documentation_inventory.py -p no:cacheprovider -q
# 22 passed (9 + 13), exit 0

PYTHONPATH=app .../python -m pytest \
  tests/unit/test_documentation_contract_drift.py -p no:cacheprovider -q
# 15 passed, exit 0 (after the one justified 198-a allowlist entry)

/tmp/slaif192-coding-venv/bin/python -m ruff check \
  app/slaif_gateway/cli/keys.py \
  app/slaif_gateway/schemas/key_clone.py \
  app/slaif_gateway/services/key_clone_service.py \
  app/slaif_gateway/db/repositories/keys.py \
  tests/unit/test_key_clone_service.py \
  tests/unit/test_cli_keys_clone.py \
  tests/integration/test_cli_key_clone_postgres.py \
  tests/unit/test_documentation_contract_drift.py
# All checks passed (E4/E7/E9/F, line-length 100)

git diff --check            # clean
/tmp/slaif192-coding-venv/bin/python scripts/check_documentation.py
# DOCUMENTATION_CHECK=OK files=125
```

Passed suites were not repeated for display/count formatting; no full
local matrix was run. Normal final-report-head CI (broad gate) remains
required and was PENDING at the time of this record; root independently
owns final-head CI.

## Privacy, atomicity, and concurrency statements

- The plan file, ordinary stdout, JSON, audit rows, and logs never
  contain a complete key, token hash, provider environment name or base
  URL, raw metadata, usage, or replay rows. The one-time plaintext
  exists only in the in-process result and the operator's explicitly
  chosen channel; repeats (`already-applied`) never recover or re-send it.
- Key + one-time secret + pending delivery + receipt + audits commit
  atomically in one caller-owned transaction; late failures roll back all
  new rows (proven in PG). No SMTP, output-file write, or enqueue happens
  before commit. There is no exactly-once SMTP promise; recovery is the
  existing explicit `email send-pending-key` for still-unconsumed
  material, otherwise rotation.
- Deduplication is bounded and honest: it is proven under the PostgreSQL
  default READ COMMITTED isolation (source `FOR UPDATE` lock + per-statement
  snapshot), not by pretending row locks guarantee arbitrary-isolation
  dedup. No schema, uniqueness constraint, or new receipt registry was
  introduced.

## Documentation impact

Required by AGENTS.md §5.1. This objective changed the documented CLI and
schema contracts:

- `docs/cli-reference.md`: new `keys clone` section with actual
  plan → review → execute → repeat/failure-recovery commands, eligibility,
  canonical-equality, fingerprint, validity, fenced-confirmation,
  retry-safety, transaction, isolation-boundary, and no-plaintext-recovery
  semantics; command inventory updated.
- `docs/cli-field-administration.md`: the 198 row moved from
  "Proposed for later objectives" to a new "Implemented in objective 198"
  row (199-205 remain proposed; the full brief and the eleven DoD are NOT
  declared complete — the objective-205 installed-executable-only
  transcript remains mandatory).
- `docs/database-schema.md`: bounded `clone_receipt` JSON contract on
  `gateway_keys.metadata` (JSON only; no DDL change) plus the supported
  READ COMMITTED deduplication boundary.
- `docs/verification/README.md`: this record indexed.

## Limitations

- Synthetic data only: fictional owners/cohorts, fake provider
  configuration, canned routes; no real provider/model contact, no real
  SMTP delivery (send-now targeted a refused local port), no Redis, no
  upstream smoke.
- The objective-205 installed-executable transcript is still outstanding;
  this record does not declare the full brief or the eleven DoD complete.
- No release, RC, production, security, or compliance claim follows from
  this record.

## 198-b ADDENDUM — clone plan and retry guards (same PR #354)

Continuation 198-b on the SAME branch/PR repairs eight demonstrated
limitations of the 198-a implementation (the 198-a record above is retained
as history and is NOT rewritten). This addendum is evidence for the 198-b
changes only; it is not a release or production-certification decision.

### Corrections to demonstrated 198-a limitations

1. **Retry lookup was scoped to the target owner.** The receipt lookup is
   now namespaced by `(source, operation)` ONLY and INDEPENDENT of the
   (mutable) target selection: `find_clone_receipt` became
   `find_clone_receipts` (returns every match, no owner predicate), so a
   retry that changes the target owner or cohort still finds the completed
   operation. MORE THAN ONE receipt for `(source, operation)` is refused as
   ambiguous (`key_clone_receipt_ambiguous`) rather than silently choosing
   one.
2. **The reviewed plan content was not revalidated after locking.** On
   FIRST execution, after the source-row lock, the service now re-derives
   the source fingerprint and the FRESH canonical policy document and
   rechecks the plan's reviewed `policy` (via a new `policy_fingerprint`
   over sort-keys canonical JSON), `source_public_key_id`, and
   `requires_fenced_confirmation` against the locked source. Any mismatch is
   refused with `key_clone_reviewed_policy_mismatch` before any write — a
   reviewed policy the (unchanged) source does not back is refused, never
   silently ignored; the editable plan is never authority to widen or
   narrow the source policy. Repeat comparison covers the FULL business
   identity (source fingerprint, policy fingerprint, target owner, target
   cohort, all four validity parameters, fenced-confirmation requirement);
   legacy 198-a-shape receipts lacking the new fields are refused as a
   mismatch rather than adopted.
3. **READ COMMITTED was documented but not enforced.** Before any write the
   execution reads `current_setting('transaction_isolation')` (new
   `current_transaction_isolation` repository method, after the lock) and
   refuses any level other than `read committed`
   (`key_clone_unsupported_isolation`), committing nothing.
4. **Execution time was sampled before the lock.** The clock is now sampled
   AFTER the source-row lock (R3 clock hook), so a source that expires
   while the lock is acquired is refused.
5. **Plan-file read was unbounded.** The execute read is bounded at
   128 KiB + 1 byte (`_read_bounded_plan_file`); an oversized file is
   refused with a fixed safe error BEFORE any database access, and a
   missing/unreadable file produces a fixed error without the path.
6. **A post-commit output/mail exception surfaced as a generic error.**
   Post-commit secret-file/send-now/enqueue failures now produce a safe
   `recovery` block (target key, one-time secret, delivery IDs, fixed
   guidance; `plaintext_recoverable: false`) and exit nonzero without
   rolling back the committed clone.
7. **An exact repeat through `--secret-output-file` was refused pre-dedup.**
   The pre-database `secret_output_file.exists()` check is removed: a NEW
   operation with an already-existing output file COMMITS first, then the
   exclusive write fails after commit (recovery block), and a TRUE exact
   repeat reaches receipt deduplication before any file channel — it never
   clobbers the file.
8. **CI cache leak.** `_clean_profile_env` (autouse) in
   `tests/unit/test_cli_key_policy_files.py` now clears the settings cache
   in `try/finally`, so later tests in one process no longer inherit a
   cached configured profile.

Mixed-mode refusal (R4) was also added: `--execute` refuses the dry-run-only
flags and `--dry-run` refuses the execute-only channel/confirmation flags;
absolute validity timestamps are normalized (naive → UTC) so mixed
aware/naive windows are compared predictably and rejected, and
`duration-from-now` is bounded by a documented 1,000-year maximum.

### Exact verification

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest`
(no ambient `DATABASE_URL`; PG tests against an owned disposable
`postgres:16` instance with label prefix `slaif198a`).

- `pytest tests/unit/test_key_clone_service.py tests/unit/test_cli_keys_clone.py
  -p no:cacheprovider -q --junitxml=/tmp/slaif198/unit-clone-b.xml`
  → **54 passed** (26 service + 28 CLI), 0 failed/0 errors/0 skipped. New
  focused coverage: changed-owner retry still dedups; edited-reviewed-policy
  before create refused; same operation with a different policy after commit
  refused; unsupported (REPEATABLE READ) isolation refused before writes;
  post-lock clock expiry refused; ambiguous multi-receipt refused; legacy
  a-shape receipt refused; mixed-mode flag refusals; bounded plan read
  (exactly 128 KiB + 1 read; oversized refused before any DB access);
  existing-file exact repeat commits then recovers; file-ExistsError
  refusal without path echo; post-commit mail failure recovery.
- `pytest tests/integration/test_cli_key_clone_postgres.py
  -p no:cacheprovider -q --junitxml=/tmp/slaif198/integration-clone-b.xml`
  → **7 passed**, 0 failed/0 errors/0 skipped, against the owned PG
  instance. Proofs: two concurrent same-source executions serialize (one
  created, the other dedups); `--email-delivery pending` commits exactly
  one pending delivery for the target; a real `KeyService` session at
  `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` is refused with no rows
  and no audits (rollback); two DIFFERENT operations for the same source
  create two independent keys (same cohort, distinct token hashes); the
  oversized-plan refusal and the cohort-UUID comparison are proven
  end-to-end.
- R6 leak regression: `test_cli_key_policy_files.py::test_create_invalid_configured_profile_fails_closed`
  run in ONE process together with
  `tests/unit/test_v1_chat_completions_pricing.py` and
  `tests/unit/test_v1_endpoint_allowlist.py` → all pass; the full
  `tests/unit/test_cli_key_policy_files.py` file is 28 passed.
- `tests/unit/test_documentation_contract_drift.py` → **15 passed**;
  `tests/unit/test_documentation_inventory.py` +
  `tests/unit/test_oap_governance.py` → **22 passed**;
  `scripts/check_documentation.py` → `OK files=125`; Ruff clean over all
  eight changed product/test files; `git diff --check` clean.
- Owned-PG cleanup: no leftover `slaif198a`-prefixed containers remain.

### Privacy, atomicity, isolation, concurrency

No key material, token hashes, provider references, raw metadata, usage, or
secrets are stored in the receipt, echoed in errors, or added to logs; all
new errors are fixed safe messages. Key creation, one-time secret, optional
pending delivery, receipt, and audits still commit atomically in one
caller-owned transaction, and nothing (no SMTP, no output file, no enqueue)
happens before commit. READ COMMITTED is now the ENFORCED deduplication
boundary; same-source executions serialize on the existing source-row
`FOR UPDATE` lock, and the post-lock receipt read sees the prior commit.
No schema, column, constraint, or migration was added; no real
provider/model contact, real SMTP, Redis, or upstream smoke occurred.

### CI state

GitHub final-head CI for the 198-b head is PENDING (root-gated). The 198-a
CI run FAILED (15/5868 PASS/1 SKIP; unit job 122804543472 / run
40684723649) on the settings-cache leak that limitation 8 above repairs; no
198-b CI result is claimed here and the coding agent never merges.

### Documentation impact

Required by AGENTS.md §5.1. 198-b changed the documented contracts:

- `docs/cli-reference.md`: the `keys clone` section now documents
  (source, operation) retry safety independent of target selection with
  full business-identity comparison and ambiguity refusal, reviewed-plan
  revalidation, post-lock execution time, mixed-mode refusals, bounded plan
  read, the enforced isolation boundary, and post-commit output recovery.
- `docs/database-schema.md`: the `clone_receipt` JSON contract gained
  `target_owner_id`, `policy_fingerprint`, and
  `requires_fenced_confirmation`; the lookup is documented as
  (source, operation) only, repeat comparison as FULL business identity,
  and READ COMMITTED as ENFORCED.
- `docs/cli-field-administration.md`: the 198 row reflects the 198-b guards
  (199–205 remain proposed; the objective-205
  installed-executable-only transcript remains mandatory).
- This file: 198-b addendum appended; `docs/verification/README.md`
  unchanged (the record is already indexed).

### Limitations

- Synthetic data only: fictional owners/cohorts, fake provider
  configuration, canned routes; no real provider/model contact, no real
  SMTP delivery, no Redis, no upstream smoke.
- The objective-205 installed-executable transcript is still outstanding;
  this record does not declare the full brief or the eleven DoD complete.
- No release, RC, production, security, or compliance claim follows from
  this record.

## 198-c ADDENDUM — complete reviewed-plan binding and consumable dry-run (same PR #354)

Continuation 198-c on the SAME branch/PR completes the reviewed-plan
binding and the consumable dry-run contract, plus two test hygiene repairs.
The 198-a record and the 198-b ADDENDUM above are retained as history and
are NOT rewritten. This addendum is evidence for the 198-c changes only; it
is not a release or production-certification decision.

### Corrections to demonstrated 198-b limitations

1. **A completed operation whose `source_public_key_id` was changed still
   returned `already-applied`.** The receipt now stores
   `source_public_key_id` and the repeat comparison includes it: a
   changed reviewed public ID on a completed operation is refused
   (`key_clone_plan_mismatch`), never re-applied.
2. **The reviewed COPY-SOURCE-EXPIRY `validity.source_valid_until` was not
   bound.** First execution now compares the reviewed source-expiry value
   to the fresh locked source's actual expiry (normalized ISO datetime
   comparison) and refuses a mismatch BEFORE any write
   (`key_clone_reviewed_policy_mismatch`) — another expiry is never
   substituted while claiming the exact reviewed plan executed. The
   receipt stores the reviewed value (`source_valid_until`; `null` for the
   other validity modes) and repeats compare it, so a differently dated
   repeat of a completed operation is refused. An ACTUAL source validity
   edit after completion does NOT change a completed operation: the
   ORIGINAL exact repeat still returns `already-applied` for the same
   target (dedup precedes staleness; the source fingerprint change only
   makes a FRESH plan stale).
3. **A successful dry-run could produce a non-consumable plan.** The
   builder returned a 100,000,000,000-second duration plan that
   `parse_clone_plan_document` immediately refused under the documented
   bound. `build_plan` now re-validates the built document with the SAME
   strict version-1 schema and bounds (reusing the parser; no second
   duration rule) BEFORE returning: the documented maximum stays
   consumable, maximum+1 and impossible datetime/duration windows fail
   predictably with a fixed safe error — no echo, no DB mutation, no
   audit, no plan file.
4. **Test hygiene (review threads PRRT_kwDOSLm-qM6xIbdN /
   PRRT_kwDOSLm-qM6xIbdj).** The CLI bounded-read test's empty broad
   `except/pass` was replaced with an assertion of the EXPECTED fixed
   error (`Clone plan file exceeds the bounded size`, no path echo),
   retaining the cap+1 and before-DB oracles. The post-lock-clock test no
   longer assigns `svc_mod._now` directly (leaked lambda); it uses
   dotted-target `monkeypatch.setattr` so teardown restores the clock,
   with the duplicate module import removed and the semantic
   expiry-during-lock test kept.

### Final receipt representation (no new authority)

The smallest bounded typed representation was chosen: two extra safe
identity fields on the existing JSONB receipt
(`source_public_key_id`, `source_valid_until`) — no signatures, jobs,
general serializer, or new authority. The source/policy fingerprints
remain dedup data, never authentication/replay authority. Old unmerged
receipt shapes (198-a/b) lacking any required identity member fail
CONTROLLED (`key_clone_plan_mismatch`) rather than becoming "no receipt /
new creation". The ambiguity lookup is bounded by a SQL `LIMIT 2`: two
matches prove ambiguity; a corrupted third receipt adds no decision
information and no unbounded scan cost.

### Exact verification

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest`
(no ambient `DATABASE_URL`; PG tests against an owned disposable
`postgres:16` instance, label prefix `slaif198a`; inspect before
readiness/migration; exact-ID cleanup).

- `pytest tests/unit/test_key_clone_service.py tests/unit/test_cli_keys_clone.py
  -p no:cacheprovider -q --junitxml=/tmp/slaif198/unit-clone-c.xml`
  → **62 passed** (34 service + 28 CLI), 0 failed / 0 errors / 0 skipped.
  New focused regressions: copy-expiry reviewed mismatch refused before
  create (no create, no audit); changed public ID on completed operation
  refused; changed reviewed expiry on completed operation refused;
  original repeat after an ACTUAL source expiry edit still
  `already-applied` for the same target; inert preview change remains
  inert; receipt carries the complete business identity (no `sk-`
  material); dry-run strict round trip at the documented maximum
  (consumable); duration maximum+1 fails safely (fixed message, value not
  echoed).
- `pytest tests/integration/test_cli_key_clone_postgres.py
  -p no:cacheprovider -q --junitxml=/tmp/slaif198/integration-clone-c.xml`
  → **8 passed** (the 7 retained owned-PG cases + 1 NEW bounded
  regression), 0 failed / 0 errors / 0 skipped. The new
  `test_clone_reviewed_identity_and_expiry_binding` proves against owned
  PostgreSQL: an exact valid copy-source-expiry plan creates; a
  contradictory reviewed expiry on a FRESH plan's first execution refuses
  with NO new rows and NO audits; changed reviewed public ID / changed
  reviewed expiry repeats refuse with NO duplicate key; and after an
  ACTUAL source validity edit (`UPDATE gateway_keys SET valid_until`) the
  original exact repeat still returns the same target. The existing
  two-new-plans case now also asserts both targets' canonical policy
  exports equal the source's and that the source row is unchanged; the
  concurrency case now asserts the CHILD CLI `exit_code == 0` in both
  processes (OS-helper exit 0 alone does not report the CLI exit).
- Root repro re-run (fresh receipts, old evidence preserved):
  `198-c-independent-recheck.json` and
  `198-c-independent-recheck-2.json` under
  `review-artifacts/cli-feature-round/`. The probe was adapted in two
  harness-only places (its unguarded `build_plan` call now legitimately
  raises under the consumable-dry-run contract; the
  `different_source_expiry_repeat` case sequence was reordered so it
  repeats AFTER completion, preserving its intent). Result: changed
  public ID repeat refused; tampered reviewed expiry first execution
  refused with 0 creates; differently dated repeat refused with 1 create;
  over-maximum duration plan refused by the builder
  (`KeyClonePlanError`). All previously fixed b cases remain fixed.
- `tests/unit/test_documentation_contract_drift.py` → 15 passed (the
  unchanged consumer guard included);
  `tests/unit/test_documentation_inventory.py` +
  `tests/unit/test_oap_governance.py` → 22 passed;
  `scripts/check_documentation.py` → `OK files=125`; Ruff clean over all
  five changed product/test files; `git diff --check` clean.
- Owned-PG cleanup: no leftover `slaif198a`-prefixed containers remain.

### Privacy, atomicity, isolation, concurrency

The two new receipt members are bounded safe public identity data (a
public key ID string and an ISO datetime / null) — no key material, token
hashes, provider references, raw metadata, usage, or secrets; all new
errors are fixed safe messages. Atomicity, the enforced READ COMMITTED
boundary, source-row lock serialization, and no-plaintext-recovery are
unchanged. No schema, column, constraint, or migration was added. No real
provider/model contact, real SMTP, Redis, or upstream smoke occurred.

### CI state

GitHub final-head CI for the 198-c head is PENDING (root-gated; no CI
result is claimed here). The 198-b report-head checks all ten SUCCESS
were observed at 2026-10-28T13:18Z (the old 15-failure cache leak stayed
repaired), but the independent source-contract gaps repaired above and
the two open review threads still block merge; green CI is necessary, not
sufficient. The coding agent never merges.

### Documentation impact

Required by AGENTS.md §5.1. 198-c changed the documented contracts:

- `docs/cli-reference.md`: the `keys clone` section now documents the
  consumed consumable-dry-run guarantee, the reviewed copy-source-expiry
  expiry revalidation (never substituted), and the FULL business identity
  (source public key ID + reviewed copy-source-expiry expiry) with
  two-bounded ambiguity lookup and retry-after-actual-source-edit
  behavior.
- `docs/database-schema.md`: the `clone_receipt` JSON contract gained
  `source_public_key_id` and `source_valid_until`; the lookup is
  documented as bounded to two matches; repeat comparison as the FULL
  business identity; old-shape receipts as controlled refusal; actual
  source edits as non-identity-changing for completed operations.
- `docs/cli-field-administration.md`: the 198 row reflects the 198-c
  binding and consumable-dry-run behavior (199-205 remain proposed; the
  objective-205 installed-executable-only transcript remains mandatory).
- This file: 198-c addendum appended; `docs/verification/README.md`
  unchanged (the record is already indexed).

### Limitations

- Synthetic data only: fictional owners/cohorts, fake provider
  configuration, canned routes; no real provider/model contact, no real
  SMTP delivery, no Redis, no upstream smoke.
- The objective-205 installed-executable transcript is still outstanding;
  this record does not declare the full brief or the eleven DoD complete.
- No release, RC, production, security, or compliance claim follows from
  this record.

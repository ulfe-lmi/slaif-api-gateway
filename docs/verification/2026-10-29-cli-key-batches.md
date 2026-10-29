# Objective 203-a — Reviewed key-configuration batches verification

Recorded 2026-10-29 for the 203 PR (base `main` at
`a1f7abdfc86b137e7bbece5c44face42b8e6b902`, the merged 202 PR #358).
This record describes what the bounded local runs below actually proved.
It is not provider, model, client, request-accounting, SMTP, credential,
performance, security, compliance, or release qualification, and it is
not the 205 installed-wheel executable-only operator transcript.
Final-head CI for the publication commit is gated by root and is reported
honestly in the objective report, not certified here.

## Scope

Objective 203 added the reviewed key-configuration batch surface:
`slaif-gateway keys batch plan` (READ ONLY preview that saves a strict
non-secret 0600 plan file) and `slaif-gateway keys batch apply` (atomic
application of the EXISTING supported key-policy/rate changes to the
EXACT selected EXISTING keys), through NEW typed
`schemas/key_batch.py`, shared `services/key_batch_service.py`, and a new
`cli/key_batch.py` sub-app. No schema, migration, settings, new
capability, key-creation, cohort, or delivery change: deployment is the
ordinary image rebuild/recreate (migration head stays 0026/33 tables).

- Selection: exactly one of `--cohort-id` or repeatable `--key-id`;
  statuses finite (active/suspended/revoked, default active); bounded to
  1,000 keys; duplicates refused; any missing key ID fails the WHOLE
  request with a count only (no ID echo). A cohort preview selects the
  EXACT currently eligible members and reports `excluded_by_status`
  empty per contract; explicit selection reports selected rows outside
  the status filter as `excluded_by_status` objects.
- Preview law: locks the exact rows in sorted UUID order, re-derives the
  canonical before/after/diff and the deterministic source/post
  fingerprints through the EXISTING shared policy law, and exits the
  caller transaction WITHOUT commit (zero writes, zero audits, zero
  material/state change).
- Apply law: re-locks the exact rows, re-resolves cohort membership
  AFTER the last potentially blocking selected-key lock, re-derives every
  target under the locks (saved display values never trusted), validates
  the saved source/post fingerprint coherence against the key's CURRENT
  identity/lifecycle context, and refuses the whole batch (stale) on any
  drift with zero writes and zero audits. Every check completes before
  the first write; a late validation/write/audit failure propagates so
  the ONE caller-owned transaction rolls back ALL keys and ALL
  provisional (flushed) audits. Whole-set repeat is an explicit
  `already_at_target` with zero writes and zero new audits (state
  equality, not historical proof).
- Fresh controls: the saved plan is a review artifact, never authority.
  A recorded `confirm_external_tool_fenced` is stripped before
  validation; only the fresh apply-time `--confirm-external-tool-fenced`
  flag satisfies the shared fenced law (repeated decisions re-require it
  through the same law). The apply reason is bounded, nonblank, and
  known-shape guarded.
- Known-shape protection (finite recognized credential shapes, NOT a
  universal sanitizer and no DLP claim): a recognized shape in the typed
  input policy, in a selected key's RETAINED canonical configuration, in
  the plan artifact pathname, or in the audit reason is refused with a
  fixed safe error before shared route/model validation can reflect the
  value into an error message and before any write, artifact, or output.
  Ordinary values and the existing per-key validation/error law are
  unchanged.
- Money projection: cost targets render/apply at the exact
  `Numeric(18, 9)` storage scale (`"2"` -> `"2.000000000"`); a target
  that cannot be honestly represented at that scale is refused at plan
  time with no artifact; the post-update check re-reads the persisted
  (database-coerced) value under the held locks.

## Evidence

All runs below: Python 3.12.15,
`env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app
/tmp/slaif192-coding-venv/bin/python -m pytest <paths> -p
no:cacheprovider -q --junitxml=<file>` from the repository root; every
command exited 0; counts are per `classname` from the JUnit XML, not
guesses.

### Owned PostgreSQL 16 (actual CLI entrypoint + actual service + real SQL)

`tests/integration/test_cli_key_batch_postgres.py` — **13 PASS / 0 fail /
0 skip / 0 error** (37.65 s), one NEW owned, uniquely labeled,
loopback-bound, tmpfs-backed `postgres:16` container (owner label
`slaif203a.owner`, identity inspected BEFORE readiness/migration, exact
container ID removed in cleanup), migration head 0026 (33 tables),
synthetic data only, no provider/SMTP/broker contact. The 37-key
mandatory cohort was created through the ACTUAL `keys create` CLI; all
other fixture data is direct SQL seed (labeled as such). The 13 cases:

1. `test_plan_37_key_cohort_is_read_only_exact_preview` — the mandatory
   37-key cohort preview is READ ONLY (zero writes/audits/state change,
   0600 strict artifact), selects the EXACT 37 active UUIDs, reports
   `excluded_by_status == []` per the cohort contract, with exact
   canonical per-key before/after/diff.
2. `test_apply_37_key_cohort_one_transaction_audits_preservation_repeat`
   — one-transaction apply with EXACT per-key audits (reason/actor,
   old/new request limits), same-scope preservation of the
   suspended/revoked control members, the 101-key unrelated cohort, the
   105-key tail cohort, all zero usage/reservation counters, the 1001-key
   overflow cohort untouched, and a whole-set repeat that is
   `already_at_target` with zero writes and zero new audits.
3. `test_explicit_key_selection_mixed_statuses_duplicates_missing` —
   explicit UUID selection with mixed statuses (excluded object
   reporting), duplicate refusal, missing-ID whole-request refusal
   (count only, no ID echo), and separate `--status` inclusion;
   refusals never write.
4. `test_cohort_over_100_eligible_is_not_truncated` — a 105-eligible
   cohort previews ALL 105 (no first-100 tail truncation).
5. `test_cohort_overflow_beyond_cap_refused_before_artifact` — a
   1001-key cohort is refused (cap+1 overflow) before any artifact,
   write, or audit.
6. `test_stale_membership_and_drift_refusals_zero_writes` — member add,
   member removal, configuration drift, and status drift each refuse the
   whole batch with zero writes and zero audits, then reset.
7. `test_controlled_pg_lock_wait_cohort_join_refused` — a competitor
   session DEMONSTRABLY owns the later selected-key row lock BEFORE the
   applier starts (readiness barrier); the causal holder/waiter relation
   is observed via `pg_stat_activity` with `pg_stat_clear_snapshot()`
   before each poll; the competitor commits a NEW eligible cohort member
   in the same transaction; the post-last-lock membership re-resolution
   refuses the whole batch (stale) with both selected keys untouched,
   zero audits, and the newcomer visible.
8. `test_late_audit_failure_rolls_back_all_keys_and_audits` — an injected
   audit failure on the THIRD of three keys propagates OUT of the caller
   transaction; a fresh session proves ALL keys and ALL provisional
   (flushed) audits rolled back (no partial commit).
9. `test_usage_only_movement_does_not_stale_repeat` — committed
   SYNTHETIC fixture-injection usage movement BETWEEN the preview and the
   FIRST configuration write (order D) is preserved by the actual write
   (nonzero counters + one audit per key + target applied); a second
   movement between the first write and the repeat neither stales the
   `already_at_target` repeat nor moves the counters; zero new audits.
10. `test_money_integer_target_pg_apply_repeat` — real-PG money
    normalization: `"2"` previews/applies as the exact
    `"2.000000000"` (persisted at 9-decimal scale), the repeat is
    `already_at_target` with zero new audits, and a 10-decimal target is
    refused at plan time (no artifact).
11. `test_fenced_target_requires_fresh_confirmation_cli` — a SAVED plan
    confirmation is not authority: apply without the fresh flag refuses
    before any write/audit; the fresh flag applies with one per-key
    audit; repeated decisions re-require the fresh flag (refusal) or are
    explicit `already_at_target` (zero new audits).
12. `test_edited_plan_fingerprints_refused_pg` — an edited advertised
    before (with the derived diff) is refused on first apply AND repeat;
    the unedited control applies; a coherently edited policy+after+diff
    carrying the stale post digest is refused in the applied state with
    the 9000 target never written (the FIRST-apply variant of that
    coherent edit is the durable unit regression
    `test_apply_coherent_edit_stale_post_fingerprint_refused_on_first`).
13. `test_cli_canaries_no_echo_policy_path_reason` — credential shapes in
    the policy file CONTENT, in the plan artifact PATHNAME, in the audit
    REASON, and in a selected key's RETAINED current configuration are
    all refused with fixed safe errors, never echoed in stdout or stderr
    (text and JSON modes), with no artifact and no writes; the 37-key
    cohort state and audit count are proven unchanged.

### Focused unit layers (honest fakes / actual Typer)

- `tests/unit/test_key_batch.py` — **38 PASS / 0 skip**: strict plan
  schema/IO boundaries (safe fixed errors, derived diff/count
  re-derivation, tamper refusal, known-shape refusal at parse/write,
  duplicate/sort/count bounds, bounded exclusive 0600 write) and the
  shared KeyBatchService selection/preview/apply laws (read-only
  preview, bounded selection, stale/membership/drift refusal with ZERO
  writes, repeat no-op law, usage-only non-staleness, deterministic lock
  order, reason bounds, money projection, fresh fenced confirmation,
  edited-artifact fingerprint refusal in BOTH first-apply and
  after-prior-apply states, and the new-batch known-shape guards for
  input policy, retained current configuration, and parsed plan objects).
- `tests/unit/test_cli_key_batch.py` — **12 PASS / 0 skip**: actual
  Typer CLI surface (command registration, no-echo typed selection
  parsing, cap refusal, policy/plan/reason credential canaries never
  echoed, happy-path JSON/0600 file, bounded text summary, reason/actor
  handling, `--confirm-external-tool-fenced` passthrough, plan-pathname
  credential-shape refusal, database-not-configured).

### Unchanged consumers and governance (same source state)

- `tests/unit/test_cli_key_policy_files.py` (28),
  `tests/unit/test_key_clone_service.py` (34),
  `tests/unit/test_key_policy_configuration.py` (56),
  `tests/unit/test_key_service_policy_update.py` (19) — **137 PASS / 0
  skip** (unchanged consumers of the modified
  `services/key_service.py` / `db/repositories/keys.py` /
  `cli/keys.py`).
- `tests/unit/test_oap_governance.py` (9),
  `tests/unit/test_codex_protocol_capture.py` (26),
  `tests/unit/test_cli_codex_replay.py` (21) — **56 PASS / 0 skip**.
- `tests/unit/test_documentation_inventory.py` (16, including the
  literal `slaif-gateway keys batch plan` / `apply` naming),
  `tests/unit/test_documentation_contract_drift.py` (15),
  `tests/unit/test_documentation_asof.py` (13) — **44 PASS / 0 skip**;
  `python3 scripts/check_documentation.py` ->
  `DOCUMENTATION_CHECK=OK files=129`.

## Negative and boundary evidence

- No partial batch state: every refusal (stale, overflow, duplicate,
  missing, fenced, known-shape, reason) leaves zero key/audit/material
  state (unit + owned-PG).
- No secret echo: canary values never appear in stdout/stderr in text or
  JSON mode (policy content, pathname, reason, retained config); the
  known-shape guard fires BEFORE route/model validation can reflect a
  configured value into an error (root independent
  actual-service/fake-repo probe and fixed recheck, credited as root
  evidence, booleans only).
- No confirmation replay: saved fenced confirmation stripped; fresh flag
  required for first apply AND repeated decisions.
- No plan authority: edited before/after/diff/policy documents with
  stale or inconsistent fingerprints are refused in both first-apply and
  repeat states.
- No usage staleness: usage/reservation counters are excluded from the
  fingerprints; committed movement between preview and first write is
  preserved by the actual write.
- No all-key scope: the 1001-key overflow cohort and every non-selected
  cohort are untouched (exact-scope snapshots).
- No new schema/settings: migration head stays 0026 (33 tables); no
  settings, tables, or migrations added.

## Limitations

- The owned-PG suite is one local disposable PostgreSQL 16 run with
  synthetic data; it is not concurrency-scale, load, or production
  qualification. The controlled lock-wait case proves ONE causal
  holder/waiter refusal under READ COMMITTED linearization, not global
  serializability (the re-resolution is the documented linearization
  point).
- The unit layer uses honest fakes (including an exact 9-decimal
  `Numeric(18, 9)` column emulation in the fake limit writer); only the
  owned-PG layer is storage proof for money coercion.
- The stored-current-configuration canary is natively proven in the
  owned-PG suite; the root independent probe for that path was
  actual-service/fake-repo qualified (credited as root evidence).
- No real provider, model, client, request-accounting, SMTP, mail,
  broker, or installed-wheel (205) claim is made by this record.

## Deployment

No schema migration, key-policy migration, or new settings. Operators
apply this surface with the ordinary image rebuild/recreate; no
operator data migration or feature flag is required.

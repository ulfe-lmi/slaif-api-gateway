# Objective 202-a — Email delivery inspection and safe explicit retries verification

Recorded 2026-10-29 for the 202 PR (base `main` at
`d2ad3465d5b953d5247ecce28451649cf7764890`, the merged 201 PR #357).
This record describes what the bounded local runs below actually proved.
It is not provider, model, client, SMTP, mailbox, credential, performance,
security, compliance, or release qualification, and it is not the 205
installed-wheel executable-only operator transcript. Final-head CI for the
publication commit is gated by root and is reported honestly in the
objective report, not certified here. The 202-a layer below is historical
evidence for implementation `bb96266`; the clearly separated 202-b
section at the end of this record covers the bounded prepared-recipient
correction on the SAME PR and supersedes the 202-a recipient caveat
without editing that historical layer.

## Scope

Objective 202 added operator email-delivery administration that reuses the
existing sender and CLI email group, with no schema, queue framework, SMTP
redesign, settings, or UI changes:

- Read-only inspection: `slaif-gateway email list` and
  `slaif-gateway email show <delivery-uuid>` through NEW typed
  `schemas/email_inspection.py` and shared `services/email_inspection.py`.
  Allowlisted metadata only (delivery/owner/key/secret UUIDs, persisted
  recipient, persisted status, created/sent/failed timestamps, existing
  service-derived secret lifecycle/sendability, safe last-recorded audit
  error code with provenance/time/action). No subject, rendered/body, raw
  error prose, SMTP/provider message ID, encrypted payload/nonce, plaintext
  key, or hash/HMAC values. Fixed safe not-found/validation/unavailable
  outcomes, nonzero errors, `--json` honored.
- List filters: exact delivery/key/owner UUID, normalized exact owner email
  (strip/lower, never substring identity), persisted status, inclusive aware
  UTC creation bounds; AND-combined; SQL predicates applied BEFORE
  deterministic `(created_at DESC, id DESC)` paging; at most `limit + 1`
  fetched with honest `has_more`/`next_offset`; `--limit` 1..100 (default
  50) and `--offset` 0..1000000 parsed by a strict no-echo typed page parser
  (malformed values fail fixed-safe without echoing the supplied text);
  missing result distinct from store unavailable.
- Explicit safe retry on the existing `email send-pending-key` action:
  `--retry-failed` requires an operator-selected existing FAILED delivery
  UUID and a bounded nonblank `--reason`, rejected before send/queue;
  sent/sending/ambiguous/consumed/expired/missing/mismatched states are
  never blindly retried; no plaintext recovery or key recreation.
- Enqueue-intent audit: the existing audit repository records a bounded
  safe operator enqueue REQUEST (selected IDs, actor, reason, explicit
  intent) committed BEFORE dispatch; audit failure prevents dispatch; the
  Celery task payload remains exactly the existing three UUIDs (no
  reason/body/secret/context); `queued` is the CLI broker-submission result
  only, never a database delivery status or worker acknowledgement.
- Shared send-boundary guard repairs (concrete root baseline evidence):
  exact selected delivery-to-secret UUID equality plus ownership/key/purpose
  binding at the shared locked send-preparation boundary; a supplied or
  omitted selector can never manufacture a substitute delivery or bypass a
  retained same-secret sending/sent/ambiguous attempt; fresh current
  state/clock re-verified after blocking row-lock waits (stale ORM identity
  map does not authorize); known-binding refusals raised BEFORE any
  decryption.
- The global durable metadata sanitizer intentionally drops fields whose
  names contain "secret" (including `one_time_secret_id`) from audit
  `new_values`; the NEW intent event records the secret strictly under the
  safe field `one_time_reference_id` (the already-parsed UUID string),
  documented in code, so intent attribution survives without relaxing the
  existing global boundary.

No schema, head, table, or key-policy change: the migration head remains
`0026_request_diagnostics` (33 tables). `docs/database-schema.md` §5.18 only
documents the ALREADY-EXISTING `one_time_secrets.status` column, check, and
index from migration 0004, which its description previously omitted.

## Layers and exact commands

Environment for every run: existing Python 3.12 venv
(`/tmp/slaif192-coding-venv`), ambient `DATABASE_URL`/`TEST_DATABASE_URL`
unset, `-p no:cacheprovider`, JUnit captured and counts read from the XML
(pyproject `addopts=-q` suppresses the human summary by design). No real
provider/model/client/SMTP/Redis contact anywhere: SMTP and the Celery
broker are explicitly faked in the integration layer, and the unit layer
uses fake repositories/services only.

### 1. Affected unit batch (145 PASS / 0 SKIP)

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_email_inspection.py \
  tests/unit/test_cli_email.py \
  tests/unit/test_email_delivery_service.py \
  tests/unit/test_cli_secrets.py \
  tests/unit/test_cli_keys_email_delivery.py \
  tests/unit/test_cli_keys_secret_output.py \
  tests/unit/test_admin_email_delivery_actions_routes.py \
  tests/unit/test_admin_key_create_email_delivery_routes.py \
  tests/unit/test_admin_key_rotation_email_delivery_routes.py \
  tests/unit/test_email_service.py \
  tests/unit/test_email_rendering.py \
  tests/unit/test_email_security.py \
  tests/unit/test_secret_service.py \
  tests/unit/test_crypto_one_time_secrets.py \
  tests/unit/test_celery_email_task.py \
  tests/unit/test_alembic_email_jobs.py \
  tests/unit/test_db_models_email_jobs.py \
  -p no:cacheprovider -q --junitxml=/tmp/slaif202/email-units-final3.xml
# JUnit: tests=145 failures=0 errors=0 skipped=0, exit 0
```

Per-file counts derived from the JUnit `testcase.classname`:

- NEW files: `test_email_inspection` 18 (typed schemas/service: exact
  filters, lifecycle/sendability projection, historical audit error-code
  selection with exact target/type/action and id tie-breaker, unknown
  latest code -> unavailable, read-only invariants, safe error taxonomy)
  and `test_email_delivery_service` 21 (19 existing behavioral assertions
  preserved + 2 new pre-decryption binding regressions with real-crypto
  hooks: foreign selected owner refused `not sendable` with 0 decryption
  calls; revoked/consumed secret refused as `already consumed` with 0
  decryption calls).
- NEW focused cases in `test_cli_email` (27 total, 3 new):
  `--limit`/`--offset` credential canary is never echoed in the error,
  default and explicit in-range values parse as typed integers, and
  out-of-range values fail fixed-safe without echo; `--json` is honored by
  the page parser errors (`invalid_parameter`).
- UNCHANGED consumers (79 total, run unmodified):
  `test_admin_email_delivery_actions_routes` 9,
  `test_admin_key_create_email_delivery_routes` 5,
  `test_admin_key_rotation_email_delivery_routes` 4,
  `test_alembic_email_jobs` 3, `test_celery_email_task` 4,
  `test_cli_keys_email_delivery` 6, `test_cli_keys_secret_output` 2,
  `test_cli_secrets` 21, `test_crypto_one_time_secrets` 7,
  `test_db_models_email_jobs` 6, `test_email_rendering` 2,
  `test_email_security` 2, `test_email_service` 4, `test_secret_service` 4.

### 2. Owned-PostgreSQL-16 actual-CLI + actual-service evidence (12 PASS / 0 SKIP)

PostgreSQL evidence used a freshly created unique-owned container (name
prefix `slaif202a`, owner label `slaif202a.owner`, loopback binding,
tmpfs-backed), identity inspected BEFORE readiness/migration, and removed
by exact container ID after the run. After the final full-module run,
`docker ps -a --filter "label=slaif202a.owner"` was verified empty. The
fixture drives the ACTUAL CLI entrypoint (Typer app, real repositories,
real SQL) and the ACTUAL `EmailDeliveryService` with a real
`decrypt_secret` counting hook; only the SMTP sender and Celery task are
fakes, so no mail is sent and no broker/Redis is contacted.

```bash
env -u DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/integration/test_cli_email_inspection_postgres.py \
  -p no:cacheprovider -q --junitxml=/tmp/slaif202/pg-inspection-final.xml
# JUnit: tests=12 failures=0 errors=0 skipped=0, time 58.152s, exit 0
```

The twelve tests and what each proves:

1. `test_list_exact_filters_and_tied_paging` — 110-row batch with TIED
   `created_at` (4 CLI-created hero keys + 106 directly inserted synthetic
   rows across three owners with OVERLAPPING email substrings, all six
   persisted statuses): exact AND-combined filters evaluated in SQL before
   deterministic paging; `--owner-email b@example.org` never matches owner
   `a.b@example.org`; correct last page; honest `has_more`/`next_offset`;
   inclusive creation windows; readable text mode.
2. `test_list_invalid_inputs_and_canaries_no_echo` — invalid UUID, unknown
   status (including the CLI-only word `queued`), naive/reversed time
   windows, and malformed/out-of-range `--limit`/`--offset` all fail
   nonzero with fixed safe messages; a credential-like value in every
   filter position is never echoed; missing result is distinct from
   unavailable/invalid.
3. `test_show_lifecycle_sendability_and_historical_audit` — show lifecycle
   across present (pending usable material, not proof sent), consumed,
   expired, unavailable/missing, and wrong-purpose/mismatched secrets; the
   latest exact `email_key_failed`/`email_key_ambiguous` audit projection
   (entity_type exactly `email_delivery`, entity_id exactly the delivery
   UUID, `created_at` then `id` tie-breaker, known code only, explicit
   "last recorded audit error" provenance); unknown latest code ->
   unavailable; foreign-entity/foreign-action/wrong-type/later-time
   distractor audit rows excluded; a sent row retaining a historical
   failure is labeled historical, never "current attempt's error".
4. `test_show_list_read_only_zero_side_effects` — whole scoped tables
   (deliveries/secrets/keys/audit/ledger) byte- and row-identical after
   list/show; zero fake sends; subject, raw error prose, audit-leak,
   encrypted payload/nonce, and plaintext canaries absent from every
   output field.
5. `test_actions_send_retry_and_refusals` — actual service actions:
   initial pending send-now consumes once; repeated already-sent denied;
   SMTP failure persists `failed` with safe code; `--retry-failed` without
   flag or with blank reason rejected before send/queue; pending/expired/
   sending/ambiguous/missing-UUID/secret-UUID-mismatch/foreign-selected
   all denied without wrong-target mutation, substitute rows, or mock
   sends; an explicit retry with a reason is audited.
6. `test_actions_no_id_bypass_refusals_and_pre_decrypt_guard` — omitting
   the delivery selector (or selecting a different retryable row) cannot
   bypass a retained same-secret sending/sent/ambiguous state; a
   retained-failed same-secret history blocks a fresh no-ID attempt; the
   legitimate fresh no-ID first send still works (decrypt exactly once);
   a foreign selected owner/key binding is refused BEFORE decryption
   (real crypto count 0).
7. `test_actions_ambiguous_after_finalization_failure` — SMTP accepted
   then finalization failure (injected `mark_consumed` fault) leaves the
   delivery `ambiguous`, and it cannot be resent even via selector
   omission or the retry flag.
8. `test_concurrency_delivery_lock_wait_consumed_refusal` — sender holds
   the delivery row lock and blocks on the secret row lock while the holder
   consumes the secret; after the CAUSAL lock wait is observed the fresh
   for-update re-read refuses the stale preflight.
9. `test_concurrency_secret_lock_wait_consumed_refusal` — same law on the
   secret-row wait path; stale preflight cannot authorize after the state
   changes while waiting.
10. `test_concurrency_secret_lock_wait_expiry_after_wait_fresh_clock` —
    injected clock boundary: sender pre-wait instant `t0`, holder advances
    `t1` ONLY after the causal lock wait is observed and moves expiry to
    `t0 < expiry < t1`; the stale pre-wait time would not itself have
    expired, so only the fresh post-wait clock rejects; actual crypto
    count stays 0.
11. `test_enqueue_intent_audit_payload_and_queued_distinct` — the enqueue
    intent audit is committed BEFORE dispatch (verified from inside the
    fake task `delay` by in-DB query); payload is exactly the existing
    three UUIDs (no reason/body/key/crypto); `queued` CLI result is
    distinct from the persisted `pending` list status; the reason is
    persisted and no longer ignored for enqueue; the audit records
    `one_time_reference_id` (parsed UUID) and no secret-named key.
12. `test_enqueue_no_id_preflight_and_failure_boundaries` — no-ID enqueue
    preflight refuses retained-failed and blocked-sibling same-secret
    states before intent audit/dispatch while preserving a valid fresh
    no-ID enqueue; show `can_send` and enqueue accept/refuse agree on the
    shared sendability; an audit-commit failure prevents dispatch (safe
    `command_failed` JSON, no exception detail); a dispatch failure leaves
    only the honestly committed intent with delivery and secret unchanged.

Concurrency observer: the holder is correlated to the WAITER, not counted
blindly — the test polls `pg_stat_activity` (after
`pg_stat_clear_snapshot()` on each poll, because snapshot caches inside a
held transaction) for a `wait_event_type='Lock'` row whose
`pg_blocking_pids(pid)` contains the holder PID and whose `pid` is the
sender. The sender additionally prefetches delivery/secret/sendability in
the SAME session before blocking, so the post-wait identity-map refresh
(`populate_existing`) is genuinely exercised. A focused 3-test
concurrency rerun after the item-16 clock fix passed
`/tmp/slaif202/pg-concurrency-1.xml` (3 PASS / 0 SKIP, 7.188s).

### 3. Root independent evidence (attribution)

The following receipts live under
`/home/janezp/codex-supervision/slaif-api-gateway/review-artifacts/cli-feature-round/`
and are ROOT runs (independent probes/rechecks), not agent pytest runs:

- `202-a-independent-postgres-boundaries-baseline.json` — baseline
  reproduction (actual owned PostgreSQL 16, actual sender service, fake
  SMTP) of the three original guard gaps: >100-row tail attempts missed by
  the old oldest-100 `any()` check, omitted-selector alternative-row
  bypass, and no-ID after a failed history; plus three passing controls.
  Service source sha `64618145` unchanged during the probe.
- `202-a-independent-postgres-boundaries-fixed-recheck.json` — fixed-mode
  recheck PASS: all named guard/read-only checks including the >100
  blocking tail, omitted failed/ambiguous selectors, no decryption on
  known-invalid cases, and scoped delivery/secret/key state preservation.
  Service source sha `dad935eb`.
- `202-a-cli-dispatch-mode-probe.json` and
  `202-a-cli-dispatch-mode-recheck.json` — four-mode Typer dispatch
  routing (selected-ID/no-ID × send-now/enqueue) reproduced the
  cross-wired dispatch regression and then verified 4/4 correct routing
  after the branch fix.
- `202-a-page-parse-secret-canary-probe.json` and
  `202-a-page-parse-secret-canary-recheck.json` — malformed
  `--limit`/`--offset` errors echoed a synthetic credential and ignored
  `--json`; recheck passed all five no-echo/JSON cases plus two typed
  in-bounds controls.
- `202-a-predecrypt-actual-crypto-probe.json` and
  `202-a-predecrypt-actual-crypto-recheck-and-recipient-probe.json` —
  foreign selected owner actually decrypted before refusal in the draft
  (reproduced with an actual-crypto hook); recheck: foreign owner
  0-decrypt/no-SMTP refusal, normal pending control 1-decrypt/1-fake-send,
  revoked already 0-decrypt.
- `202-a-recipient-projection-canary-probe.json` — a recognized synthetic
  gateway-key shape embedded in `recipient_email` passed the draft
  projection unchanged; now masked by reusing the existing
  known-shape redaction at the metadata output boundary.
- `202-a-first-green-native-PG-junit.json`,
  `202-a-focused-unit-143-junit.json`, and
  `202-a-root-QA-strengthening.json` — root verification of the agent's
  JUnit artifacts and QA strengthening notes.

### 4. Static gates

- `ruff check` on all changed Python files: clean.
- `python3 scripts/check_documentation.py`: PASS.
- `git diff --check`: clean.
- Focused documentation-inventory / contract-drift / OAP-governance unit
  batch re-run green (see objective report for the JUnit).

## Negatives (privacy / identity / concurrency / accounting)

- Privacy: credential-like inputs to every list filter and to the page
  parser are never echoed; subject/body/raw-error-prose/SMTP-message-ID/
  encrypted-payload/nonce/plaintext canaries are absent from list, show,
  text, JSON, audit, and broker payloads; the broker payload is exactly
  the three UUIDs; the intent audit carries no secret-named fields.
- Identity: exact delivery/secret/owner/key UUID bindings only; no
  substitute delivery row, no neighboring/nearest inference in show;
  wrong-target mutation counters stay at zero on every refusal; a foreign
  selected binding is refused before any decryption.
- Concurrency: causally correlated lock-wait proof (blocking-pids
  correlation, snapshot-cleared polls, fresh autocommit semantics), stale
  preflight overridden by post-wait state, `t0 < expiry < t1` fresh-clock
  boundary, actual crypto count 0 on every post-wait refusal; lock order
  remains delivery-then-secret with no inverse ordering.
- Accounting: read-only inspection leaves byte/row-identical
  deliveries/secrets/keys/audit/ledger state; inspection causes zero
  decrypt/render/send/queue; no quota/accounting/key-policy change.

## Limitations

- `queued` means CLI broker submission only; `sent` means recorded SMTP
  acceptance/finalization; neither proves mailbox arrival. No real SMTP,
  mail, or inbox contact occurred anywhere in this evidence.
- Recipient caveat (SUPERSEDED by the 202-b section below, which
  resolved this pre-merge per order 202-b; this 202-a text is kept as
  historical evidence): at implementation `bb96266` the persisted
  `recipient` was the creation-time recorded field, while the existing
  sender delivers using the current `Owner.email` after an
  owner-address change. The 202-a layer described the recipient as the
  recorded field and did not infer historical actual destinations; no
  SMTP destination policy was changed.
- The global audit sanitizer drops secret-named fields by design; the
  intent event's `one_time_reference_id` is a documented safe reference
  (strictly the parsed UUID), not a relaxation.
- Wrong-purpose secret material is unreachable through the database
  purpose CHECK; the service-level purpose guard is defense-in-depth, not
  the primary barrier.
- Not client, provider, model, backend, or installed-wheel
  qualification; the 205 all-eleven installed-executable operator
  transcript remains unclaimed. Final-head CI is pending at record time
  and gated by root.

## Deployment / upgrade

No schema or key-policy migration: the migration head remains
`0026_request_diagnostics` with 33 tables (only the already-existing
`one_time_secrets.status` documentation was added). Deploy by rebuilding
and recreating the API and worker code consistently; no new settings,
queue contract, or transport changes are required.

## 202-b — bounded prepared-recipient correction (same PR, same record)

Order 202-b (AMEND_EXISTING_PR, same PR #358) required the NEW inspection
to report the recipient prepared for a NEW actual send attempt rather
than an obsolete creation address after an owner-address edit, with no
new recipient-selection policy, mail subsystem, schema, version marker,
or backfill.

### What changed

- `app/slaif_gateway/services/email_delivery_service.py` ONLY: after the
  existing exact-identity/lifecycle/prior-attempt validations succeed and
  the canonical current owner destination is resolved, the existing
  `EmailDelivery.recipient_email` is refreshed to the SAME value used in
  `_PreparedKeyEmailDelivery.recipient_email` / the existing SMTP `to`,
  within the existing locked sending preparation immediately before the
  existing `mark_sending` flush/commit (one captured local value, small
  ORM assignment, no new repository/transaction/framework).
- Scope guarantee: only attempts prepared by this code record the exact
  prepared `to` in the sending commit. Untouched older rows and rows that
  were never prepared may retain creation-time metadata; the actual
  historical destination of a pre-upgrade attempt is unknown and is never
  reconstructed or backfilled. No row mutation for invalid identity or
  blocked attempts; read-only list/show still updates nothing; the
  known-shape output masking is unchanged; the existing
  sent/failed/ambiguous law, single consumption, lock order, and
  pre-decryption refusals are preserved.

### Evidence (newest totals; 202-a layer above stays historical)

- Affected unit batch: 149 PASS / 0 SKIP
  (`/tmp/slaif202/unit-affected-202b.xml`, exit 0) — the 145 202-a
  batch plus 4 new cases in `tests/unit/test_email_delivery_service.py`
  (parametrized sent / smtp-failure / finalization-failure asserting the
  PERSISTED row carries the prepared recipient in every outcome plus a
  no-ID first-creation control).
- Owned PostgreSQL 16, actual CLI entrypoint + actual shared sender,
  fake SMTP/Celery, real crypto hooks: 13 PASS / 0 SKIP
  (`/tmp/slaif202/pg-202b.xml`, time 62.677s, exit 0) — the 12 202-a
  cases plus one new focused case
  (`test_prepared_recipient_refreshes_to_current_owner_email`):
  owner address edited after the pending rows existed (fictional
  creation address); for EACH attempt — actual-CLI success, shared-sender
  SMTP failure, and shared-sender accepted-then-finalization-failure — a
  FRESH separate session read DURING the attempt proves the committed
  `sending` row already carries the prepared recipient equal to the exact
  fake `to`; after success the fresh row and the ACTUAL CLI
  `list`/`show` reflect the prepared address; the failed/ambiguous rows
  retain the prepared recipient under the existing law with the secret
  untouched; the ambiguous retry adds no SMTP attempt. The existing
  foreign-binding refusal case also asserts the selected recipient stays
  untouched on the invalid-identity path (zero decrypt/SMTP).
- Root independent evidence (root runs, not agent runs):
  `202-b-independent-postgres-recipient-and-boundary-recheck.json`
  (sender source sha `f57d0648`; fresh separate PostgreSQL session
  DURING fake SMTP sees the committed sending recipient equal to the
  actual prepared `to`; success, SMTP-failure and finalization-failure
  targets persist; read-only inspection projects them unchanged; 3
  positive controls + 12 existing guards + 9 recipient-named assertions;
  mocked SMTP, no real mail/CLI/concurrency claim; the first root
  fixture omitted a required `provider_status` and failed — corrected
  fixture only, rerun exit 0, source stable, exact containers removed).

### Review-thread disposition (recorded, root-owned)

`github-code-quality[bot]` "Statement has no effect" on
`tests/integration/test_cli_email_inspection_postgres.py` line 1429
(discussion_r4409208194) targets `await o_task`. Inspection: the await is
a deliberate synchronization point — it propagates the observer's
timeout `AssertionError` into the test and guarantees the observer's
session has closed before the final assertions, preserving the causal
coordination of the lock-wait proof. It is a FALSE POSITIVE; the
statement has effect through exception propagation and task-completion
ordering. The await is preserved unchanged (root resolved the thread the
same way); the three causal lock-wait cases still run as part of the full
focused file with their wait/current-clock assertions unweakened.

### Report provenance note (documented per order, immutable A untouched)

The 202-a report's "+3 CLI" and "+2 sender" items were the LAST
incremental fixes in those files, not all additions in them; the 145/12
202-a counts were the complete latest totals at that head and remain the
historical 202-a layer.

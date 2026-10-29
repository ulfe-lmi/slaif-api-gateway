# OAP Objective 202-a — final report: email delivery inspection and safe explicit retries

Work order: `oap/orders/202-a-email-delivery-inspection-and-safe-retries.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `202-a` (5 bytes, no trailing newline); order sha256
`c9fbfddeed7c9f1ff73c053c66cf3968113d5af95080d3dd8827f104b9a36b38`
(20,722 bytes), active pointer sha256
`56040e37672fa598a754bd78b6dbf6f9d197ad07675be5e2e4d6ff89dc79a25a`,
both verified before committing and re-verified at HEAD).
Branch: `oap/202-email-delivery-inspection`; base: `main`
`d2ad3465d5b953d5247ecce28451649cf7764890` (merged 201 PR #357;
unchanged). PR mode: CREATE_NEW_PR — the ONE new PR for objective 202,
#358, https://github.com/ulfe-lmi/slaif-api-gateway/pull/358, base
`main`. The coding agent never merges; no auto-merge; root reviews
independently and guard-merges.

Implementation head SHA: bb9626697699e9d4ab72d7e4bd4dc26fda57cbbd
Report publication commit: SELF

## Implementation commit (this round)

1. `bb9626697699e9d4ab72d7e4bd4dc26fda57cbbd` — "Add read-only email
   delivery inspection and safe explicit retries (202-a)": the
   strategic order (bytes verified unchanged, sha256 above) + exact
   `oap/active` = `202-a` + the allowed changes listed below
   (19 files total). First parent is `main`
   `d2ad3465d5b953d5247ecce28451649cf7764890`.

## What changed (allowed paths only)

New product surface (all new files):

- `app/slaif_gateway/schemas/email_inspection.py` — typed
  allowlisted list/show output schemas, finite status/time/page
  validation (inclusive aware-UTC creation window; limit 1..100
  default 50; offset 0..1000000), strict no-echo page-value parser,
  fixed safe error taxonomy (not-found/validation/unavailable).
- `app/slaif_gateway/services/email_inspection.py` — typed shared
  read-only service: exact AND-combined filters (delivery/key/owner
  UUID, normalized exact owner email via the same strip/lower
  normalization as OwnerService — never substring identity, no GUI
  substring reuse), persisted status, inclusive creation bounds; SQL
  predicates applied before deterministic `(created_at DESC, id DESC)`
  paging with at most `limit + 1` fetched and honest
  `has_more`/`next_offset`; exact delivery-UUID show (no
  neighboring/nearest inference); existing
  `EmailDeliveryService.get_key_email_delivery_sendability` reused for
  the secret lifecycle (`present`/`consumed`/`expired`/`unavailable`)
  — no second divergent eligibility validator; latest exact
  `email_key_failed`/`email_key_ambiguous` audit projection
  (entity_type exactly `email_delivery`, entity_id exactly the
  delivery UUID, `created_at` then `id` tie-breaker) projecting only a
  finite known error code with safe action/time and explicit
  "last recorded audit error" provenance — unknown/missing/unsafe
  latest code is unavailable, never parsed from prose; a sent row's
  retained failure is labeled historical.

Modified existing product paths (additive, no refactor):

- `app/slaif_gateway/cli/email.py` — `email list` / `email show`
  registration with typed output and fixed safe errors; `--retry-failed`
  on the existing `send-pending-key` (requires a selected delivery UUID
  and a bounded nonblank `--reason`, rejected before send/queue;
  existing flag exclusivity and pending mode preserved); the previously
  ignored enqueue reason is persisted; the enqueue-intent audit is
  recorded through the existing audit repository and committed BEFORE
  dispatch (audit failure prevents dispatch); the intent event records
  the secret strictly as `one_time_reference_id` (the already-parsed
  UUID string) because the global durable sanitizer drops secret-named
  fields from audit `new_values`; `--limit`/`--offset` are strict
  typed-string parses that never echo malformed input and honor
  `--json`.
- `app/slaif_gateway/db/repositories/email.py` — additive exact bounded
  inspection/history/identity queries (point lookups, bounded
  existence across the full status set for the same-secret prior
  attempts, current-row refresh) preserving the existing GUI
  substring/list behavior.
- `app/slaif_gateway/db/repositories/audit.py` — additive exact
  latest email-error query only; existing broad admin queries
  unchanged.
- `app/slaif_gateway/db/repositories/one_time_secrets.py` — the
  existing FOR UPDATE lookup refreshes current state after a wait
  (identity-map `populate_existing`); selection/crypto/consumption
  semantics unchanged.
- `app/slaif_gateway/services/email_delivery_service.py` — shared
  locked send-preparation guards: exact selected delivery-to-secret
  UUID equality plus ownership/key/purpose/expiry/consumption binding;
  same-secret prior sending/sent/ambiguous attempts block whether the
  selector is omitted or a different retryable row is selected; a
  supplied missing/unsafe selection is a fixed selection-required
  refusal, never a manufactured substitute delivery; fresh current
  state/clock re-verified after blocking row-lock waits (lock order
  remains delivery-then-secret, no inverse ordering); known-binding
  refusals raised BEFORE any decryption. The sender's sending-commit,
  SMTP, finalization, and ambiguity law are preserved.

New tests:

- `tests/unit/test_email_inspection.py` (18) — typed schemas/service:
  filter validation, exact AND semantics, lifecycle/sendability
  projection, historical audit error-code selection with exact
  target/type/action and id tie-breaker, unknown latest code ->
  unavailable, read-only invariants, safe error taxonomy.
- `tests/integration/test_cli_email_inspection_postgres.py` (12) —
  actual CLI entrypoint + actual EmailDeliveryService against owned
  PostgreSQL 16 with fake SMTP/Celery and a real `decrypt_secret`
  counting hook (details and per-test proofs below).
- Focused additions to existing suites (all old assertions preserved):
  `tests/unit/test_cli_email.py` (+3: page-parser credential canary
  no-echo, default/explicit in-range typed parsing, out-of-range
  no-echo with `--json` honored) and
  `tests/unit/test_email_delivery_service.py` (+2 pre-decryption
  binding regressions with real-crypto hooks).

Docs: `docs/cli-reference.md` (new commands/filters/JSON/action
meanings and inventory), `docs/database-schema.md` §5.18 (documents the
ALREADY-EXISTING `one_time_secrets.status` column, check, and index
from migration 0004 that the description omitted — verified against
the migration; no schema/head/count/table change),
`docs/runbooks/ambiguous-email-delivery.md` (inspection workflow,
explicit failed-retry rules, IDless safety, exact `queued`/`sent`
meanings), `docs/security-model.md` (bounded metadata, read-only,
identity + intent audit, ID-only payload),
`docs/verification/2026-10-29-cli-email-inspection.md` (NEW) and
`docs/verification/README.md` (index).

## Old failure -> evidence mapping (root baseline -> fix -> proof)

The order's "Necessary shared send-boundary repairs" cite concrete root
probe evidence. Mapping of each demonstrated gap to its fix and the
evidence that it is closed:

1. >100-row tail attempts missed by the old oldest-100 `any()`
   prior-attempt check — root
   `202-a-independent-postgres-boundaries-baseline.json` (actual owned
   PG16 + actual sender + fake SMTP, service sha `64618145`, three
   passing controls). Fix: bounded exact-secret existence query
   filtering sending/sent/ambiguous across the whole set. Proof: root
   `202-a-independent-postgres-boundaries-fixed-recheck.json`
   (service sha `dad935eb`, PASS) + agent PG tests 1, 5, 6 (110-row
   tied batch; retained tail states block regardless of selectors).
2. Omitted-selector alternative-row bypass (same secret, different
   delivery row, fake sender invoked) — root
   `202-inert-omitted-delivery-boundary-probe` (cited in the order) +
   the baseline receipt above. Fix: shared locked boundary enforces
   same-secret prior-attempt state and exact selected binding
   regardless of selectors. Proof: fixed recheck PASS + agent PG
   test 6 (`test_actions_no_id_bypass_refusals_and_pre_decrypt_guard`)
   and test 12.
3. No-ID turning a failed history into a fresh attempt — root baseline
   receipt. Fix: retained-failed same-secret state blocks no-ID
   enqueues/sends before intent audit/dispatch; legitimate fresh no-ID
   preserved. Proof: fixed recheck PASS + agent PG tests 6 and 12.
4. Cross-wired CLI dispatch (no-ID+enqueue sent synchronously;
   selected-ID+send-now enqueued) — root
   `202-a-cli-dispatch-mode-probe.json` ->
   `202-a-cli-dispatch-mode-recheck.json` (4/4 after the branch fix).
   Proof: fixed 4/4 recheck + agent PG tests 5/11/12 covering all
   ID/IDless × send-now/enqueue combinations.
5. `--limit`/`--offset` malformed-input echo of a complete synthetic
   credential + ignored `--json` — root
   `202-a-page-parse-secret-canary-probe.json` ->
   `202-a-page-parse-secret-canary-recheck.json` (all five no-echo/JSON
   cases + two typed in-bounds controls PASS). Proof: recheck PASS +
   agent unit +3 and PG test 2.
6. Selected owner/key binding checked AFTER decryption — root
   `202-a-predecrypt-actual-crypto-probe.json` ->
   `202-a-predecrypt-actual-crypto-recheck-and-recipient-probe.json`
   (foreign owner 0-decrypt/no-SMTP; normal control 1-decrypt/1
   fake-send; revoked 0-decrypt). Proof: recheck PASS + agent unit +2
   and PG tests 6, 8, 9, 10 (real crypto count 0 on every post-wait
   refusal).
7. Recognized synthetic gateway-key shape passing the recipient
   projection unchanged — root
   `202-a-recipient-projection-canary-probe.json`. Fix: reuse of the
   existing known-shape redaction at the metadata output boundary
   (no new sanitizer framework). Proof: agent PG tests 3/4
   read-only canary assertions.

## Evidence, layers, and exact commands

All commands ran with the existing Python 3.12 venv
(`/tmp/slaif192-coding-venv`), ambient `DATABASE_URL`/`TEST_DATABASE_URL`
unset, `PYTHONPATH=app`, `-p no:cacheprovider`; pyproject `addopts=-q`
suppresses the human summary by design, so counts are read from the
JUnit XML plus the actual exit code. Full detail lives in
`docs/verification/2026-10-29-cli-email-inspection.md`.

### Unit (mocked layer; no DB contact): 145 PASS / 0 SKIP

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_email_inspection.py tests/unit/test_cli_email.py \
  tests/unit/test_email_delivery_service.py tests/unit/test_cli_secrets.py \
  tests/unit/test_cli_keys_email_delivery.py tests/unit/test_cli_keys_secret_output.py \
  tests/unit/test_admin_email_delivery_actions_routes.py \
  tests/unit/test_admin_key_create_email_delivery_routes.py \
  tests/unit/test_admin_key_rotation_email_delivery_routes.py \
  tests/unit/test_email_service.py tests/unit/test_email_rendering.py \
  tests/unit/test_email_security.py tests/unit/test_secret_service.py \
  tests/unit/test_crypto_one_time_secrets.py tests/unit/test_celery_email_task.py \
  tests/unit/test_alembic_email_jobs.py tests/unit/test_db_models_email_jobs.py \
  -p no:cacheprovider -q --junitxml=/tmp/slaif202/email-units-final3.xml
# JUnit tests=145 failures=0 errors=0 skipped=0, exit 0
```

Per-file (JUnit `classname`): NEW `test_email_inspection` 18; new
focused cases in `test_cli_email` (27 total, +3 page-parse) and
`test_email_delivery_service` (21 total, +2 pre-decryption binding);
79 unchanged consumers (`test_cli_secrets` 21,
`test_admin_email_delivery_actions_routes` 9,
`test_crypto_one_time_secrets` 7, `test_cli_keys_email_delivery` 6,
`test_admin_key_create_email_delivery_routes` 5,
`test_admin_key_rotation_email_delivery_routes` 4,
`test_celery_email_task` 4, `test_email_service` 4,
`test_secret_service` 4, `test_alembic_email_jobs` 3,
`test_cli_keys_secret_output` 2, `test_db_models_email_jobs` 6,
`test_email_rendering` 2, `test_email_security` 2). After this batch
went green, `ruff check` on all changed files flagged one unused
import in `services/email_inspection.py`; that single line was removed
(no behavior change) and `tests/unit/test_email_inspection.py` was
re-verified 18 PASS / 0 SKIP
(`/tmp/slaif202/email-inspection-ruff.xml`, exit 0). Ruff is clean on
all changed files at the implementation head.

### Owned PostgreSQL 16 (genuine DB; actual CLI + actual service; fake SMTP/Celery): 12 PASS / 0 SKIP

```bash
env -u DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/integration/test_cli_email_inspection_postgres.py \
  -p no:cacheprovider -q --junitxml=/tmp/slaif202/pg-inspection-final.xml
# JUnit tests=12 failures=0 errors=0 skipped=0, time 58.152s, exit 0
```

Freshly created unique-owned container (name prefix `slaif202a`, owner
label `slaif202a.owner`, loopback-bound, tmpfs-backed), identity
inspected BEFORE readiness/migration, removed by exact container ID;
`docker ps -a --filter "label=slaif202a.owner"` verified empty after
the run. The twelve tests: exact AND-combined filters in SQL before
deterministic paging of a 110-row TIED-`created_at` batch with
overlapping owner-email substrings (test 1); invalid inputs and
credential canaries never echoed, missing ≠ unavailable (test 2);
show lifecycle/sendability and safe historical audit projection with
exact target/type/action tie-breaker and distractor exclusion (test 3);
read-only byte/row-identical scoped state with zero decrypt/render/
send/queue and no canary leakage (test 4); actual sender actions —
initial send, repeat-sent denied, SMTP-fail → failed, explicit
failed-retry with flag+reason audited, and every refusal class without
wrong-target mutation or mock sends (test 5); omitted-selector and
alternative-retryable-row bypass denied, retained-failed no-ID denied,
fresh no-ID positive (decrypt exactly once), foreign binding refused
before decryption (test 6); SMTP-accepted-then-finalization-failure →
ambiguous, unresent via retry or omission (test 7); three controlled
blocking/current-state concurrency cases with real row locks —
delivery-lock wait + consumed refusal (test 8), secret-lock wait +
consumed refusal (test 9), and the fresh-clock boundary with injected
`t0 < expiry < t1` where the holder advances `t1` only after the
causal lock wait is observed and actual crypto stays 0 (test 10);
enqueue intent audit committed BEFORE dispatch (verified from inside
the fake task via in-DB query) with the payload exactly the existing
three UUIDs, `queued` distinct from the persisted `pending` status,
and the reason persisted (test 11); no-ID enqueue preflight
refusals before audit/dispatch, shared show/enqueue sendability
agreement, audit-failure-prevents-dispatch, and dispatch-failure
leaving only the honestly committed intent (test 12). The concurrency
observer correlates the WAITER to the holder (`wait_event_type='Lock'`
with `:holder = ANY(pg_blocking_pids(pid))`, `pg_stat_clear_snapshot()`
per poll) and the sender prefetches delivery/secret/sendability in the
same session before blocking so the post-wait identity-map refresh is
genuinely exercised. Focused 3-test concurrency rerun after the
item-16 clock correction: `/tmp/slaif202/pg-concurrency-1.xml`
(3 PASS / 0 SKIP, 7.188s, exit 0).

### Root independent evidence (attribution: root runs, not agent runs)

Under `/home/janezp/codex-supervision/slaif-api-gateway/review-artifacts/cli-feature-round/`:
`202-a-independent-postgres-boundaries-baseline.json` (3 guard gaps
reproduced on actual owned PG16 + actual sender + fake SMTP, service
sha `64618145`), `202-a-independent-postgres-boundaries-fixed-recheck.json`
(fixed mode PASS, service sha `dad935eb`),
`202-a-cli-dispatch-mode-probe.json` / `-recheck.json` (4-mode routing,
4/4 after fix), `202-a-page-parse-secret-canary-probe.json` /
`-recheck.json`, `202-a-predecrypt-actual-crypto-probe.json` /
`202-a-predecrypt-actual-crypto-recheck-and-recipient-probe.json`,
`202-a-recipient-projection-canary-probe.json`,
`202-a-first-green-native-PG-junit.json`,
`202-a-focused-unit-143-junit.json`, and
`202-a-root-QA-strengthening.json`. These are credited as root evidence
and were not rerun by the coding agent.

### Static gates

- `ruff check` on all changed Python files: clean at the
  implementation head.
- `python3 scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK
  files=129`.
- `git diff --check`: clean.
- Focused documentation-inventory + contract-drift + OAP-governance
  batch: 40 PASS / 0 SKIP
  (`/tmp/slaif202/gov-docs-202a.xml`, exit 0).

## Negative evidence (privacy / identity / concurrency / accounting)

- Privacy: credential-like inputs to every list filter and the page
  parser are never echoed; subject/body/raw-error-prose/SMTP-message-ID/
  encrypted-payload/nonce/plaintext canaries are absent from list,
  show, text, JSON, audit, and broker payloads; the broker payload is
  exactly three UUIDs; the intent audit carries no secret-named fields
  (safe `one_time_reference_id` only, strictly the parsed UUID).
- Identity: exact delivery/secret/owner/key UUID bindings only; no
  substitute delivery row; no neighboring/nearest show inference;
  wrong-target mutation counters stay at zero on every refusal;
  foreign selected binding refused before any decryption.
- Concurrency: causally correlated lock-wait proof, stale preflight
  overridden by post-wait state, `t0 < expiry < t1` fresh-clock
  boundary, actual crypto count 0 on every post-wait refusal; lock
  order delivery-then-secret with no inverse ordering.
- Accounting: read-only inspection leaves byte/row-identical
  deliveries/secrets/keys/audit/ledger state; zero decrypt/render/
  send/queue from inspection; no quota/accounting/key-policy change.

## Limitations

- `queued` means CLI broker submission only; `sent` means recorded SMTP
  acceptance/finalization; neither proves mailbox arrival. No real
  SMTP, mail, or inbox contact occurred; SMTP and the Celery broker are
  explicitly faked in every layer of this evidence.
- Recipient caveat: the persisted `recipient` is the creation-time
  recorded field, while the existing sender delivers using the current
  `Owner.email` after an owner-address change. This report describes
  the recipient as the recorded field and does not infer historical
  actual destinations; no SMTP destination policy was changed. Root
  recorded an inert producer-side candidate that may be scoped by a
  post-merge continuation.
- The global audit sanitizer drops secret-named fields by design;
  `one_time_reference_id` is a documented safe reference, not a
  relaxation of that boundary.
- Wrong-purpose secret material is unreachable through the database
  purpose CHECK; the service-level purpose guard is defense-in-depth.
- Not client, provider, model, backend, or installed-wheel
  qualification. The 205 all-eleven installed-executable operator
  transcript remains unclaimed.

## Deployment / upgrade

No schema or key-policy migration: the migration head remains
`0026_request_diagnostics` with 33 tables (the `docs/database-schema.md`
change documents the already-existing `one_time_secrets.status`
column/check/index from migration 0004 only). Deploy by rebuilding and
recreating the API and worker code consistently; no new settings, queue
contract, or transport changes are required.

## CI state (honest)

At implementation head `bb9626697699e9d4ab72d7e4bd4dc26fda57cbbd`, all
ten final-head checks on PR #358 completed `success` (verified via the
GitHub check-runs API on 2026-10-29: CodeQL, PostgreSQL integration
tests, OpenAI-compatible E2E tests, Playwright browser smoke, Docker
Compose smoke, Documentation hygiene, Unit/lint/migration head,
Analyze Python, Analyze javascript-typescript, Analyze python); the PR
is `MERGEABLE`/`CLEAN`. The report-only SELF head triggers its own
check runs, which are in progress at publication and remain a
mandatory root gate before merge; nothing here certifies the SELF head
or a merged state.

## Changed paths (19, all within the order's exact allowed paths)

- `app/slaif_gateway/schemas/email_inspection.py` (new)
- `app/slaif_gateway/services/email_inspection.py` (new)
- `app/slaif_gateway/cli/email.py`
- `app/slaif_gateway/db/repositories/email.py`
- `app/slaif_gateway/db/repositories/audit.py`
- `app/slaif_gateway/db/repositories/one_time_secrets.py`
- `app/slaif_gateway/services/email_delivery_service.py`
- `tests/unit/test_email_inspection.py` (new)
- `tests/unit/test_cli_email.py`
- `tests/unit/test_email_delivery_service.py`
- `tests/integration/test_cli_email_inspection_postgres.py` (new)
- `docs/cli-reference.md`
- `docs/database-schema.md`
- `docs/runbooks/ambiguous-email-delivery.md`
- `docs/security-model.md`
- `docs/verification/2026-10-29-cli-email-inspection.md` (new)
- `docs/verification/README.md`
- `oap/active` (unchanged strategic bytes, committed per protocol)
- `oap/orders/202-a-email-delivery-inspection-and-safe-retries.md`
  (unchanged strategic bytes, committed per protocol)

No changes to workers/tasks_email.py, the worker queue contract,
EmailService SMTP transport, models/migrations/settings,
provider/policy/replay/rate/ledger surfaces, web UI, dependencies, or
workflows. Untracked `CODEX-SESSIONS.md` / `codex.sh` and ignored
catalogs/configs preserved and unstaged.

Documentation updated: docs/cli-reference.md, docs/database-schema.md, docs/runbooks/ambiguous-email-delivery.md, docs/security-model.md, docs/verification/2026-10-29-cli-email-inspection.md, docs/verification/README.md

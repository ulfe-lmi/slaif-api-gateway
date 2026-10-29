# OAP Objective 202-b — final report: prepared email recipient reporting

Work order: `oap/orders/202-b-prepared-email-recipient-reporting.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `202-b` (5 bytes, no trailing newline); order sha256
`89ada9a37a3c4184ac60615fffc8682ca022835afaddc8bd02364cd666efe701`
(13,572 bytes), active pointer sha256
`a46846055a005554c766a89ffb67308fcf98ce80a282e3ed2002bc7f56f6eea1`,
both verified before committing and re-verified at HEAD).
Branch: `oap/202-email-delivery-inspection`; base: `main`
`d2ad3465d5b953d5247ecce28451649cf7764890` (merged 201 PR #357;
unchanged). PR mode: AMEND_EXISTING_PR — the SAME objective PR #358,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/358; no second PR,
no auto-merge. The coding agent never merges; root reviews
independently and guard-merges. Expected starting head
`766a018b4e4148853ef13f9e7f6552d100c480b7` (the immutable 202-a
report-only SELF) verified before editing.

Implementation head SHA: c74c33dec417a720800363b9a4207c4860ac1110
Report publication commit: SELF

## Implementation commits (this round, same PR)

1. `bf07bc4941778bcadb6375f72497e3b66febf00d` — "Report the recipient
   prepared for each actual email attempt (202-b)": the strategic
   order (bytes verified unchanged, sha256 above) + exact
   `oap/active` = `202-b` + the bounded allowed changes (10 files).
   First parent is the 202-a report-only SELF
   `766a018b4e4148853ef13f9e7f6552d100c480b7`.
2. `c74c33dec417a720800363b9a4207c4860ac1110` — "Correct 202-b
   root-receipt provenance in the verification record (202-b)":
   docs-only provenance correction (no product/test changes, no
   retest; doc checks only). First parent is `bf07bc4`.

The recorded implementation head is `c74c33d` (the final non-SELF
head); the product behavior is fully contained in `bf07bc4`.

## What changed (allowed paths only)

- `app/slaif_gateway/services/email_delivery_service.py` ONLY (product):
  after the existing exact-identity/lifecycle/prior-attempt
  validations succeed and the canonical current owner destination is
  resolved, the existing `EmailDelivery.recipient_email` is refreshed
  to the SAME value used in `_PreparedKeyEmailDelivery.recipient_email`
  / the existing SMTP `to`, within the existing locked sending
  preparation immediately before the existing `mark_sending`
  flush/commit — one captured local value (`prepared_recipient`) and a
  small ORM assignment; no new repository, transaction, or framework.
  No new recipient-selection policy, mail subsystem, schema, version
  marker, backfill, or repair. The legitimate no-ID first creation
  already used this same target and is untouched.
- `tests/unit/test_email_delivery_service.py` (+4 cases, all existing
  assertions preserved): parametrized sent / smtp-failure /
  finalization-failure proving the PERSISTED row carries the prepared
  recipient in every outcome (result-shape distinctions for the
  existing failed-result `recipient_email=None` law asserted
  explicitly), plus a no-ID first-creation control using the current
  owner email.
- `tests/integration/test_cli_email_inspection_postgres.py` (+1 focused
  case, all 12 existing cases preserved):
  `test_prepared_recipient_refreshes_to_current_owner_email` — owner
  address edited after the pending rows existed (fictional creation
  address); for EACH attempt — actual-CLI success, shared-sender SMTP
  failure, and shared-sender accepted-then-finalization-failure — a
  FRESH separate session read DURING the attempt proves the committed
  `sending` row already carries the prepared recipient equal to the
  exact fake `to`; after success the fresh row and the ACTUAL CLI
  `list`/`show` reflect the prepared address; failed/ambiguous rows
  retain the prepared recipient under the existing law with the secret
  untouched; the ambiguous retry adds no SMTP attempt. The existing
  foreign-binding refusal case additionally asserts the selected
  recipient stays untouched on the invalid-identity path. Minimal
  DURING-attempt observation hook added to the existing fake
  `EmailService` (fires at the start of every attempt, before a
  recorded failure raises, for successful and failed attempts alike;
  reset by the existing autouse fixture).
- Docs (accurate semantics/evidence only): `docs/cli-reference.md`,
  `docs/runbooks/ambiguous-email-delivery.md`,
  `docs/security-model.md`, `docs/verification/2026-10-29-cli-email-inspection.md`
  (202-a layer kept historical; clearly separated 202-b layer added;
  the 202-a recipient caveat marked superseded pre-merge), and
  `docs/verification/README.md`.
- Orchestration: the unchanged 202-b order + exact `oap/active`
  committed per protocol.

No changes to repositories, schemas, the inspection projection, CLI
commands, models, migrations, settings, the global redactor/sanitizer,
worker/task/payload, EmailService transport, SecretService, key policy,
auth, accounting, ledger/quota/reservation/fence/hold,
route/provider/module/replay, or any other product/migration/settings
byte beyond the single allowed service file.

## Recipient semantics (the bounded guarantee)

- ONLY attempts prepared by this code after upgrade record the exact
  prepared `to` in the existing sending commit.
- Untouched older rows and rows that were never prepared may retain
  creation-time metadata; the actual historical destination of a
  pre-upgrade attempt is UNKNOWN and is never reconstructed or
  backfilled. No historical repair was performed or is claimed.
- The field is inspection metadata: it never infers or rewrites
  historical destinations and proves nothing about SMTP acceptance or
  mailbox arrival. `sent` still means recorded SMTP
  acceptance/finalization, not inbox arrival; `queued` remains the CLI
  broker-submission result only, never a database status or worker
  acknowledgement.
- No row mutation for invalid identity or blocked attempts (the
  foreign-binding refusal case asserts recipient invariance with zero
  decrypt/SMTP); read-only list/show still updates no record.
- The existing law is preserved: delivery-then-secret lock order,
  fresh owned post-wait identity-map/time checks, pre-crypto refusals,
  same-secret blocking/history guards, pending/failed selection rules,
  sending commit BEFORE SMTP, SMTP-failure `failed` handling, single
  consumption/sent finalization, and ambiguous handling after
  accepted-but-unfinalized SMTP (failure after preparation may retain
  the prepared recipient under the EXISTING transaction law).

## Evidence, commands, JUnits, exits, and layers

All commands: existing Python 3.12 venv `/tmp/slaif192-coding-venv`,
ambient `DATABASE_URL`/`TEST_DATABASE_URL` unset for units,
`PYTHONPATH=app`, `-p no:cacheprovider`; counts read from JUnit XML +
actual exit (pyproject `addopts=-q` suppresses the human summary by
design).

### Unit (mocked layer; no DB contact): 149 PASS / 0 SKIP

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
  -p no:cacheprovider -q --junitxml=/tmp/slaif202/unit-affected-202b.xml
# JUnit tests=149 failures=0 errors=0 skipped=0, exit 0
```

The 145 202-a cases (complete, unchanged assertions) plus the 4 new
202-b sender cases. The sender file alone: 25 PASS / 0 SKIP
(`/tmp/slaif202/unit-sender-202b.xml`, exit 0).

### Owned PostgreSQL 16 (genuine DB; actual CLI + actual shared sender;
fake SMTP/Celery; real crypto hooks): 13 PASS / 0 SKIP

```bash
env -u DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/integration/test_cli_email_inspection_postgres.py \
  -p no:cacheprovider -q --junitxml=/tmp/slaif202/pg-202b.xml
# JUnit tests=13 failures=0 errors=0 skipped=0, time 62.677s, exit 0
```

Freshly created unique-owned container (prefix `slaif202a`, owner
label `slaif202a.owner`, loopback-bound, tmpfs-backed), identity
inspected BEFORE readiness/migration, removed by exact container ID
(`docker ps -a --filter "label=slaif202a.owner"` verified empty after).
The 12 202-a cases (including all three causal lock-wait concurrency
cases, re-run unweakened because shared preparation changed) plus the
new prepared-recipient case described above.

### Static gates and focused governance/docs batch

- `ruff check` on all changed Python files: clean.
- `python3 scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK
  files=129` (re-run after the docs-only provenance correction).
- `git diff --check`: clean.
- `tests/unit/test_documentation_inventory.py` +
  `tests/unit/test_documentation_contract_drift.py` +
  `tests/unit/test_oap_governance.py`: 40 PASS / 0 SKIP
  (`/tmp/slaif202/gov-docs-202b.xml`, exit 0).

## Root independent evidence (attribution: root runs, not agent runs)

- `202-b-independent-postgres-recipient-and-boundary-recheck.json`
  (under `/home/janezp/codex-supervision/slaif-api-gateway/review-artifacts/cli-feature-round/`):
  root QA on sender source sha `f57d0648` — a fresh separate
  PostgreSQL session DURING fake SMTP sees the committed sending
  recipient equal to the actual prepared `to`; success, SMTP-failure,
  and finalization-failure targets persist; read-only inspection
  projects them unchanged. 3 positive controls + 12 existing guards +
  9 recipient-named assertions — NOT a pytest count; mocked SMTP, no
  real mail/CLI/concurrency claim. The first root fixture omitted a
  required `provider_status` and failed; corrected fixture only,
  rerun exit 0, source stable, both exact containers removed.
- The 202-a root receipts (baseline/fixed rechecks, CLI dispatch-mode
  and page-parse canaries, pre-decrypt crypto, recipient-projection
  canary) remain credited as in the immutable 202-a report and the
  verification record.

## Negative evidence (privacy / identity / accounting / concurrency)

- Privacy: the prepared-recipient change adds no content, secret,
  subject, raw error, or provider-message exposure; the known-shape
  output masking and allowlisted metadata surface are unchanged; all
  202-a privacy canaries (list/show/text/JSON/audit/broker) still pass
  in the 13-case PG run and the 149-case unit batch.
- Identity: invalid-identity/blocked paths leave the selected recipient
  and every other wrong-target field unchanged with zero decrypt/SMTP
  (extended foreign-binding case + all 202-a refusal cases re-run
  green); no substitute delivery, no neighboring inference.
- Accounting: inspection remains read-only with zero
  decrypt/render/send/queue; the recipient refresh is part of the
  existing sending commit law — no quota/accounting/key-policy change;
  single consumption and sent/failed/ambiguous finalization preserved.
- Concurrency: all three causal lock-wait cases (delivery-lock,
  secret-lock, and the `t0 < expiry < t1` fresh-clock boundary with
  actual crypto 0) re-ran green within the 13-case PG run; wait and
  current-clock assertions unweakened.

## Review-thread disposition (recorded; root owns disposition)

`github-code-quality[bot]` "Statement has no effect" on
`tests/integration/test_cli_email_inspection_postgres.py` line 1429
(discussion_r4409208194) targets `await o_task`. Inspection: the await
is a deliberate synchronization point — it propagates the observer's
timeout `AssertionError` into the test and guarantees the observer's
session has closed before the final assertions, preserving the causal
coordination of the lock-wait proof. Recorded as a FALSE POSITIVE; the
await is preserved unchanged (root resolved the thread the same way).

## Report provenance corrections (documented per order; immutable A untouched)

- The 202-a report's "+3 CLI" and "+2 sender" items were the LAST
  incremental fixes in those files, not all additions in them; the
  145/12 202-a counts were the complete latest totals at that head and
  remain the historical 202-a layer.
- The 202-a report's old-failure->evidence mapping labels the >100-row
  tail and failed-history guards as reproduced by
  `202-a-independent-postgres-boundaries-baseline.json`. That label is
  inaccurate: the baseline receipt (read directly) reproduces exactly
  the mismatched-secret sent, the supplied-missing-delivery
  substitute-created/sent, and the omitted-selector ambiguous bypass
  (three passing positive controls), and contains no tail or
  failed-history case. Those guards are supported by
  `202-a-independent-postgres-boundaries-fixed-recheck.json`
  (blocked-tail and omitted-failed-selector checks, all no-decryption)
  and the native owned-PG cases. The corrected attribution is in the
  amended verification record (commit `c74c33d`); the immutable 202-a
  report is not rewritten.

## Deployment / upgrade

No schema or key-policy migration: the migration head remains
`0026_request_diagnostics` with 33 tables; no new settings, queue
contract, or transport changes. Deploy by rebuilding and recreating the
API and worker code consistently. No backfill or data repair is
required or possible for pre-upgrade rows.

## CI state (honest)

- 202-a implementation head `bb96266`: all ten final-head checks
  completed `success` (verified via the GitHub API).
- 202-a report-only SELF `766a018`: nine of ten checks SUCCESS with
  PostgreSQL integration in progress at the order's preactivation
  lookup (pending is not a pass).
- 202-b implementation head `bf07bc4`: all ten checks in progress at
  the single honest snapshot taken before publication (Documentation
  hygiene success; the rest in progress); PR `mergeable_state`
  `unstable` while checks run.
- 202-b docs correction `c74c33d` (recorded implementation head):
  checks in progress at publication. Per the order, no repeated
  IMPL-CI waiting cycles were spent; the report-only SELF head will
  trigger the final checks, which root independently owns as the
  merge gate. Nothing here certifies any pending head or a merged
  state.

## Limitations

- No real SMTP, mail, or inbox contact anywhere; SMTP and the Celery
  broker are explicitly faked. No real provider/model/client, no
  Redis/broker, no HPC matrix. Not installed-wheel qualification: the
  205 all-eleven installed-executable operator transcript remains
  unclaimed.
- Pre-upgrade recipient history is unknown and unreconstructable (see
  Recipient semantics).

## Changed paths (this round, all within the order's exact allowed paths)

- `app/slaif_gateway/services/email_delivery_service.py`
- `tests/unit/test_email_delivery_service.py`
- `tests/integration/test_cli_email_inspection_postgres.py`
- `docs/cli-reference.md`
- `docs/runbooks/ambiguous-email-delivery.md`
- `docs/security-model.md`
- `docs/verification/2026-10-29-cli-email-inspection.md`
- `docs/verification/README.md`
- `oap/active` (unchanged strategic bytes, committed per protocol)
- `oap/orders/202-b-prepared-email-recipient-reporting.md`
  (unchanged strategic bytes, committed per protocol)

Untracked `CODEX-SESSIONS.md` / `codex.sh` and ignored catalogs/configs
preserved and unstaged.

Documentation updated: docs/cli-reference.md, docs/runbooks/ambiguous-email-delivery.md, docs/security-model.md, docs/verification/2026-10-29-cli-email-inspection.md, docs/verification/README.md

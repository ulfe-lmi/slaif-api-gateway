# OAP Objective 204-b — final report: complete record edits and safe
configuration inspection

Work order: `oap/orders/204-b-complete-record-edits-and-safe-config-imports.md`
(committed unchanged on the objective branch with `oap/active` =
`204-b` (5 bytes, no trailing newline); order sha256
`f6e53f19dab48807e7b546456a0fe0d6476da8b53e283d6502c6ad6dac1bf44d`,
active pointer sha256
`24f5e368cf8b497b47142086d8835ce02b2719d08d3ec8ab845f2a3297120c96`,
both verified before committing).
Branch: `oap/204-record-edits-config-inspection`; base: `main`
`6a523cb75b91899d1376c0ab7909404a242f44ac` (unchanged). PR mode:
CONTINUE_EXISTING_PR — PR #360,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/360 (unique PR for
objective 204); no auto-merge. The coding agent never merges; root
reviews independently and guard-merges.

204-a is CLOSED and immutable: its unique report
`oap/reports/204-a-record-edits-and-config-inspection.md` (sha256
`d8499d9e9be6c572f3f06ded814fbbb895aa91e1cbf15564d733250508c59315`)
and order (sha256
`f3aa217cea36d008aed04b30b15beffdd00144dd912b2575cdb26b53865420fa`)
are never rewritten. One factual clarification for readers (A report is
NOT edited): the A report states the A active pointer was "6 bytes";
the actual 204-a pointer was 5 bytes with no trailing newline (sha256
`1d0993e3a8b0c08df431bb1776664d12bd45a03830388dc1cf4ddc8274dbe67a`),
as this B report's own pointer bytes confirm.

Implementation head SHA: eb1c5c18dd867f1a3feffbcf187f88b9dacc8291
Report publication commit: SELF

## Implementation commits (this round)

1. `0b705bc44b483f0f92500adc3d318d3a5ff235e6` — "Complete objective
   204: safe owner/cohort partial edits and process configuration
   inspection (204-b)": strategic order + exact `oap/active` =
   `204-b` + all bounded allowed-path work (21 files).
2. `eb1c5c18dd867f1a3feffbcf187f88b9dacc8291` — "Strengthen native
   late-audit rollback proof and observer comment (204-b finding
   12/13)": root native source review items — the late-audit fault
   injection now performs the REAL `AuditRepository.add_audit_log`
   (add + flush, recorded provisional AuditLog ID) BEFORE raising, so
   the owned-PG case proves the flushed provisional audit rolls back
   with the row (fresh-session absence of the exact provisional ID);
   the concurrency observer docstring corrected (independent observer
   session with `pg_stat_clear_snapshot()` before each poll — no
   autocommit claim; no transaction machinery change); verification
   prose corrected (existing complete-update contracts retained and
   regression-tested, not byte identity).

First parent of the report-only SELF is the implementation head
`eb1c5c18dd867f1a3feffbcf187f88b9dacc8291`; only this new report
differs.

## What changed (allowed paths only)

- `app/slaif_gateway/cli/email.py` + `app/slaif_gateway/cli/keys.py`
  — the ONLY key/mail change: the fixed `send_pending_key_email_task`
  import is deferred to the enqueue seam through a tiny deferred-call
  object (`_PendingKeyEmailTaskSeam`, defined once in `cli/email.py`)
  that KEEPS the module attribute name in both modules. Exact `.delay`
  UUID arguments, lifecycle/preflight/retry checks, audit-before-
  dispatch and post-commit ordering are unchanged; the seam resolves
  the real worker task only when `delay` is actually called (the
  worker/task modules still validate Settings normally when actually
  used). No generalized lazy-command/dependency framework, no argv
  sniffing, no global import-error fallback; `workers/celery_app.py`,
  `workers/tasks_email.py`, `config.py`, broker payloads, sender/
  service/queue logic untouched.
- `app/slaif_gateway/schemas/record_edits.py` — completed the A draft
  typed partial-edit boundary: `parse_owner_update_patch` /
  `parse_cohort_update_patch` (None=omitted, explicit nullable-only
  clears, replace/clear and no-field refusals, required nonblank
  bounded reason, UTC-aware datetime convention) plus the service-
  boundary guards `assert_owner_update_patch_safe` /
  `assert_cohort_update_patch_safe` (direct non-CLI callers),
  supplied-blank UUID/date/actor and blank-replacement refusals (a
  supplied blank is never an omission and cannot evade replace+clear
  conflicts), and the fresh-current-metadata guards
  `assert_owner_current_metadata_safe` /
  `assert_cohort_current_metadata_safe`. Value refusal uses ONLY the
  existing finite credential/bearer/credential-assignment VALUE
  patterns (`utils.redaction.redact_text`); bare keyword substrings
  and map/header-key classification do NOT reject ordinary free-form
  values. All refusals are fixed no-echo errors.
- `app/slaif_gateway/services/owner_service.py` —
  `update_owner_partial` (required reason; locks the row FIRST via
  `get_owner_for_update`, guards the fresh current metadata, merges
  provided fields with the fresh stored values, then DELEGATES to the
  shared `_validate_owner_update_values` / `_commit_owner_update`
  helpers). The existing `update_owner` was refactored to the SAME two
  helpers with its exact original contract (optional reason, same
  check order, same `owner_updated` audit); the previous A draft's
  duplicated validation/write/audit body was removed (root finding 2).
  No internal commit: a late validation/write/audit failure propagates
  so the caller transaction rolls back the row and the provisional
  audit.
- `app/slaif_gateway/services/cohort_service.py` —
  `update_cohort_partial` with the same reuse law (shared
  `_validate_cohort_update_values` / `_commit_cohort_update` also
  called by the unchanged-contract `update_cohort`, incl. its
  cohort-institution `UnsupportedRecordOperationError` guard). The
  cohort date window is validated on the FINAL MERGED values, so an
  omitted start/end still participates and a one-field patch cannot
  bypass `ends_at > starts_at`.
- `app/slaif_gateway/db/repositories/owners.py` / `cohorts.py` —
  additive `get_owner_for_update` / `get_cohort_for_update` (existing
  key-repository pattern: `SELECT ... FOR UPDATE` +
  `.execution_options(populate_existing=True)`; the installed
  SQLAlchemy has no `sqlalchemy.orm.populate_existing` import, so the
  execution-option form is used).
- `app/slaif_gateway/cli/owners.py` / `cli/cohorts.py` — literal
  `slaif-gateway owners update OWNER_UUID` / `slaif-gateway cohorts
  update COHORT_UUID` commands: typed optional flags, required
  nonblank `--reason`, optional `--actor-admin-id`, `--json`; owner
  tri-state `--active` / `--inactive`; nullable-only clear flags; the
  owner update response includes `external_id`. Parsing happens
  outside the DB session (fail fast); all mutations go through the
  shared services — no CLI ORM/SQL writes; no plan-file/
  idempotency/batch machinery.
- `app/slaif_gateway/services/configuration_inspection.py` (NEW) —
  finite reviewed 45-name allowlist (Codex replay TTL; default/hard
  token bounds; Chat/Responses request and media budgets; default
  nullable rate limits; bounded lazy-throttling ceilings; no
  `RATE_LIMIT_WINDOW_SECONDS`/`LAZY_THROTTLING_ENABLED` exist and none
  are invented), each entry reporting effective value, honest
  `configured`/`default` source (process `model_fields_set`), and the
  shared restart scope; explicit limitations (current CLI process
  cached snapshot, not live API/worker state; no DB/network/broker/
  provider access; no credential values; configured DB URL is not
  connectivity/auth proof; external reverse-proxy limit NOT observed).
  No wildcard enumeration, no `model_dump`, no arbitrary setting
  lookup/env/file reader, no setter.
- `app/slaif_gateway/cli/configuration.py` (NEW) — literal
  `slaif-gateway config show [--json]`. An invalid Settings
  environment maps to the fixed safe `configuration_unavailable`
  payload (text + JSON, exit 1) with NO ValidationError value,
  traceback, or log echo.
- `app/slaif_gateway/cli/main.py` — registration of the `config`
  group plus the smallest root-callback guard: when the invoked
  subcommand is `config`, the root callback defers `get_settings()` to
  the config handler (no debug log either, since logging
  configuration itself needs Settings); every other subcommand keeps
  its existing root settings/logging behavior.
- Tests (NEW): `tests/unit/test_record_edits.py`,
  `tests/unit/test_cli_record_edits.py`,
  `tests/unit/test_cli_configuration_inspection.py`,
  `tests/integration/test_cli_record_edits_postgres.py`. Existing
  `tests/unit/test_cli_email.py` / `test_cli_keys_email_delivery.py` /
  `test_record_services.py` / `test_cli_owners.py` /
  `test_cli_cohorts.py` / `test_cli.py` /
  `test_cli_admin_owner_safety.py` / `test_admin_record_forms.py` are
  BYTE-IDENTICAL and were run unchanged.
- Docs: `docs/cli-reference.md`, `docs/deployment.md`,
  `docs/security-model.md`, NEW
  `docs/verification/2026-10-29-cli-record-edits-and-config.md`,
  `docs/verification/README.md`.

Documentation updated: docs/cli-reference.md, docs/deployment.md,
docs/security-model.md, docs/verification/2026-10-29-cli-record-edits-
and-config.md (new), docs/verification/README.md

## Import-boundary evidence (actual cold entrypoint)

- Actual cold source-entrypoint subprocess under a recognized-shape
  SYNTHETIC invalid numeric Settings environment (`HARD_MAX_INPUT_
  TOKENS=sk-proj-…`, no real credential): `import
  slaif_gateway.cli.main` exits 0 with `worker_task_loaded=false`,
  `celery_app_loaded=false`, no canary/traceback. Under a valid
  environment the same import exits 0 with the same module facts.
- Actual Typer/source entrypoint `config show --json` subprocess:
  valid env → exit 0, exactly the 45 reviewed entries with value /
  source / per-entry restart scope; invalid env → exit 1 with the
  fixed `configuration_unavailable` JSON and NO canary/traceback in
  stdout/stderr (these are source-PYTHONPATH subprocess proofs, NOT
  205 installed-wheel/executable proofs).
- Root receipts credited (ROOT evidence, qualified per their own
  receipts): `204-b-cold-import-seam-recheck.json` (true cold import,
  invalid + valid env, no worker stubs) and
  `204-b-email-task-seam-probe.json` (seam forwards exact UUID args;
  legacy module mocks still intercept; the actual deferred REAL worker
  import still raises Settings ValidationError before dispatch).
- Unchanged seam consumers: `tests/unit/test_cli_email.py` (27) and
  `tests/unit/test_cli_keys_email_delivery.py` (6) pass byte-identical.

## Verification evidence (this environment)

Unit layer (venv Python 3.12, `env -u DATABASE_URL -u TEST_DATABASE_URL
PYTHONPATH=app`, JUnit XML — repository addopts suppress console
summaries; zero skips):

- `tests/unit/test_record_edits.py` — 42 PASS (typed omission/clear/
  conflict/no-field law, required bounded reason, UTC-aware datetime
  convention, supplied-blank UUID/date/actor refusals, recognized-
  shape canary refusals without echo, ordinary-value positives,
  service-boundary asserts, fresh-current-metadata guard).
- `tests/unit/test_cli_record_edits.py` — 21 PASS (honest-fake service
  evidence: lock-first call ordering, merge preserves ALL omitted
  fields incl. nullable + `is_active=False`, delegation, exact
  audits, late-fault propagation, stored-canary unrelated-edit/clear
  refusals with zero writes/audits, hand-built blank replacement
  refusals, complete-update contracts retained; actual-Typer CLI law
  for both update commands).
- `tests/unit/test_cli_configuration_inspection.py` — 11 PASS (exact
  45-name secret-free allowlist, configured/default/nullable
  projection, text render with shared restart/recreate line, actual
  root-callback behavior — root `get_settings` NOT called for `config`,
  still called for other commands — unavailable mapping without echo,
  COLD actual subprocess entrypoint coverage).
- Unchanged consumers (one JUnit run) — 61 PASS, 0 skip:
  `test_cli_email.py` 27, `test_cli_keys_email_delivery.py` 6,
  `test_record_services.py` 4, `test_cli_owners.py` 4,
  `test_cli_cohorts.py` 4, `test_cli.py` 8,
  `test_cli_admin_owner_safety.py` 3, `test_admin_record_forms.py` 5.
- Governance/documentation (one JUnit run) — 69 PASS, 0 skip:
  `test_oap_governance.py` 9, `test_documentation_inventory.py` 16,
  `test_documentation_contract_drift.py` 15,
  `test_documentation_asof.py` 13, `test_documentation_logo.py` 6,
  `test_product_scope_docs.py` 4, `test_rc2_feature_scope_docs.py` 5,
  `test_openai_assisted_import_contract_docs.py` 1.

Owned-PostgreSQL-16 layer (`tests/integration/
test_cli_record_edits_postgres.py`; uniquely labeled `slaif204b.*`,
loopback-bound, tmpfs-backed `postgres:16`; exact created ID/ownership
inspected BEFORE migration; exact container removed; synthetic data
only) — full-file run 8 PASS, 0 skip:

- actual Typer entrypoint owner move to an existing institution: every
  omitted metadata/flag preserved (incl. `is_active=False`,
  `external_id`, `notes`), real CLI-created key material/state
  byte-identical, ONE exact `owner_updated` audit with locked old/new
  + reason + actor;
- clears / conflicts / `--active`/`--inactive`; duplicate normalized
  email, unknown institution/owner, no-field, blank reason, invalid
  actor, and recognized-shape canary refusals with row/audits
  unchanged and no echo;
- late audit fault under a caller-owned transaction: the genuinely
  flushed provisional audit (real add+flush, recorded ID) and the row
  BOTH rolled back (fresh-session absence proof, finding 12);
- cohort partial/clears preserve unrequested fields and the member key
  row; naive datetime interpreted as UTC; name strip normalization;
  invalid FINAL MERGED window / duplicate name / unknown cohort /
  no-field refusals with zero changes/audits; no cohort-institution
  association exposed or manufactured;
- controlled causal lock-wait for BOTH record types: competitor owns
  the row lock BEFORE the updater starts (readiness barrier), exact
  holder/waiter correlation via `pg_blocking_pids` with
  `pg_stat_clear_snapshot()` before each poll (independent observer
  session; no sleeps alone); competitor changes an OMITTED field and
  commits only after the wait is observed; the updater merges AFTER
  the fresh populated lock read and preserves the committed omitted
  field; audit old/new reflects the latest stored row. This is ONE
  causal case per record type, not global serializability.
- Targeted re-run after finding 12: the single changed late-audit
  case re-run with a fresh owned fixture, 1 PASS, 0 skip (the prior
  full-file 8-PASS is prior evidence; not 9 unique cases).

Independent root-side receipts credited (root evidence, each
qualified per its own receipt — source-intermediate/fake-repo layers,
not PG/CLI/205 proof): `204-b-partial-record-boundary-probe.json`
(baseline reproduction of the stored-canary audit-leak, fixed with
native regressions), `204-b-direct-blank-patch-probe.json` (hand-built
blank nullable replacements, fixed at the shared guard),
`204-b-config-and-input-boundary-probe.json` (text restart line +
supplied-blank UUID/date findings, fixed), `204-b-ordinary-metadata-
value-probe.json` (six ordinary-value false positives, fixed by
moving to finite `redact_text` VALUE patterns).

Hygiene: ruff (E4/E7/E9,F; line 100) clean on every changed Python
file; `python3 scripts/check_documentation.py` OK (131 files);
`git diff --check` clean.

## Scope, safety, and limitations

- Product changes are limited to the 204-b allowed paths listed above.
  No schema, migration, settings default, model, UI, provider,
  adapter, auth, accounting, runtime, queue, or mail-transport change;
  no new dependencies; no config.py/`.env.example` change. No schema
  or key-policy migration is required; upgrade is an ordinary image
  rebuild + container recreate (`docker compose up -d --build`).
- The import deferral changes only WHEN the workers task module is
  imported by the CLI (at the actual enqueue call); worker/runtime
  Settings validation is unchanged, and an actual deferred call still
  loads the real task and validates Settings before dispatch.
- Privacy boundary: finite recognized credential VALUE shapes only
  (`redact_text`), at the NEW partial interface (provided values,
  audit reason, fresh current row metadata) — not DLP, not universal
  content sanitization; ordinary free-form values (words such as
  "session", "token", "secretariat") are accepted; existing complete-
  update and admin-form semantics are retained and regression-tested.
- `config show` reports the CURRENT CLI process's cached `Settings`
  snapshot, not live API/worker state; no DB/network/broker/provider
  access; no credential values; a configured database URL is not
  connectivity or authentication proof; the external reverse-proxy
  request-size limit is NOT observed (shipped Nginx `location /v1/`
  `client_max_body_size 128m` is an example, documented in
  `docs/deployment.md` with its existing `nginx -t`/reload guidance).
- Successful updates are operator record edits; they are NOT
  authentication, provider, client, request-accounting, SMTP, or 205
  installed-wheel qualification. All 11 final installed-executable
  outcomes remain UNPROVEN until 205. No production, real upstream/
  provider/client, real SMTP, release, or scale claim.
- CI at the implementation head was still running at report time
  (pending); the report supersedes those IMPL checks and root owns
  the ALL-final-SELF checks/review/merge gate.

Boundary confirmations: protected unrelated untracked
`CODEX-SESSIONS.md` (sha256
`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`)
and `codex.sh` (sha256
`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`)
were verified byte-identical before and after all commits and were
never staged. Exact owned PG container removed; no ambient production
`DATABASE_URL` used for destructive setup. 205 remains inactive; no
merge or auto-merge was performed.

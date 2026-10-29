# Objective 204 CLI Record Edits And Process Configuration Inspection Verification

Date: 2026-10-29

Corrected in 204-c (prose only): the native-run chronology (full-file run
predates the late-audit case strengthening), the lock-wait observer
phrasing, and the stored-current-canary evidence attribution. See the
immutable 204-c report for the clarification of the immutable B
report's overclaim. No transaction machinery or native-test change.

Environment: local Codex checkout of `ulfe-lmi/slaif-api-gateway`,
branch `oap/204-record-edits-config-inspection` (objective 204, PR #360,
continuation 204-b), Python 3.12 venv (`/tmp/slaif192-coding-venv`,
typer 0.27.3), Docker available. Owned, uniquely labeled, loopback-bound,
tmpfs-backed `postgres:16` container for all integration evidence (exact
created container ID/ownership inspected before migration and removed in
`finally`); no ambient or production `DATABASE_URL`. All fixtures are
synthetic; no real provider, client, upstream, SMTP, or 205 installed-wheel
evidence is claimed here.

## What this record proves

Objective 204 completes two operator capabilities on the SAME PR as
204-a:

1. The two narrowly authorized CLI import deferrals
   (`cli/email.py` + `cli/keys.py`): the fixed
   `send_pending_key_email_task` is resolved lazily at the enqueue seam
   through a tiny deferred-call object that KEEPS the module attribute
   name, so existing native test mocks are unchanged. Actual cold
   source-entrypoint subprocess imports succeed under a recognized-shape
   SYNTHETIC invalid numeric Settings environment (exit 0, no worker task
   or Celery app loaded, no canary/traceback) and under a valid
   environment; an actual deferred call still imports the real worker
   task (which validates Settings normally when actually used).

2. `slaif-gateway owners update OWNER_UUID` and
   `slaif-gateway cohorts update COHORT_UUID`: typed partial edits through
   the shared `OwnerService` / `CohortService`. Omitted flags preserve ALL
   current values (including nullable fields and `is_active=False`);
   explicit clears exist only for nullable fields; replace+clear and
   no-field patches are refused before writes; the target row is locked
   (`SELECT ... FOR UPDATE` + `populate_existing`) FIRST, then the merged
   values are delegated to the SAME shared normalization/validation and
   repository-write/audit helpers as the existing complete update (no
   duplicated body; the existing complete-update contracts are retained and regression-tested, not claimed as byte identity). The exact
   existing `owner_updated` / `cohort_updated` audit with locked old/new,
   required bounded reason, and optional actor commits with the record in
   the caller-owned transaction; a late audit fault rolls back row and
   audit. The cohort date window is validated on the FINAL MERGED values
   (an omitted side still participates).

3. `slaif-gateway config show [--json]`: finite reviewed 45-name
   allowlist (replay TTL, token bounds, Chat/Responses budgets, default
   rate limits, lazy-throttling ceilings) projected from the CURRENT CLI
   process's cached `Settings` with honest `configured` / `default`
   source, per-entry restart scope, and explicit limitations (current
   process snapshot, not live API/worker state; no DB/network/broker/
   provider access; no credential values; proxy limits not observed).
   The `cli/main.py` root callback defers `get_settings()` for the `config`
   group only, so an invalid Settings environment maps to the fixed safe
   `configuration_unavailable` payload (text + JSON, nonzero exit) with NO
   value/traceback echo; every other subcommand keeps its existing
   root settings/logging behavior.

Privacy boundary at the NEW partial interface: finite recognized
credential VALUE shapes (`redact_text`: bearer, gateway/provider key,
credential assignments) in a provided value, in the audit reason, in
supplied blanks disguised as replacements, or in the FRESH current
metadata of the selected row are refused with fixed no-echo errors before
any write or audit snapshot (a stored known shape cannot be copied into
the new audit by an unrelated edit or an explicit clear). Ordinary
free-form values are accepted; this is not DLP and existing complete
update / admin-form semantics are unchanged.

## Verification evidence (this environment)

Unit layer (venv Python 3.12, `env -u DATABASE_URL -u TEST_DATABASE_URL
PYTHONPATH=app`, JUnit XML, repository addopts suppress console
summaries; zero skips):

- `tests/unit/test_record_edits.py` — 42 PASS: typed omission/clear/
  conflict/no-field law, required bounded reason, UTC-aware datetime
  convention, supplied-blank UUID/date/actor refusals (not omissions;
  blanks cannot evade replace+clear conflicts), recognized-shape canary
  refusals without echo, ordinary-value positives (Workshop Session 1,
  token/secretariat/session free-form), service-boundary asserts
  (hand-built patches), fresh-current-metadata guard.
- `tests/unit/test_cli_record_edits.py` — 21 PASS: honest-fake service
  evidence (lock-first call ordering, merge preserves all omitted fields
  including `is_active=False`, delegation, exact audits, late-fault
  propagation, stored-canary unrelated-edit/clear refusals with zero
  writes/audits, hand-built blank replacement refusals, complete-update
  semantics preserved) plus actual-Typer `owners update` / `cohorts
  update` CLI law (JSON output incl. `external_id`, fixed no-echo error
  codes, required `--reason`).
- `tests/unit/test_cli_configuration_inspection.py` — 11 PASS: exact
  45-name secret-free allowlist, configured/default/nullable projection,
  text render with shared restart/recreate line, actual root-callback
  behavior (root `get_settings` NOT called for `config`; still called for
  other commands), unavailable mapping without echo, and COLD actual
  subprocess entrypoint coverage (cold import under invalid numeric +
  valid environments; real `config show --json` valid/invalid with no
  canary/traceback).
- Unchanged consumers (one JUnit run) — 61 PASS, 0 skip:
  `test_cli_email.py` 27, `test_cli_keys_email_delivery.py` 6 (both seam
  consumers byte-identical), `test_record_services.py` 4,
  `test_cli_owners.py` 4, `test_cli_cohorts.py` 4, `test_cli.py` 8,
  `test_cli_admin_owner_safety.py` 3, `test_admin_record_forms.py` 5.
- Governance/documentation (one JUnit run) — 69 PASS, 0 skip:
  `test_oap_governance.py` 9, `test_documentation_inventory.py` 16,
  `test_documentation_contract_drift.py` 15,
  `test_documentation_asof.py` 13, `test_documentation_logo.py` 6,
  `test_product_scope_docs.py` 4, `test_rc2_feature_scope_docs.py` 5,
  `test_openai_assisted_import_contract_docs.py` 1.

Owned-PostgreSQL-16 layer (actual owned `postgres:16`, loopback + tmpfs,
label `slaif204b.*`, identity inspected before migration, exact container
removed) — `tests/integration/test_cli_record_edits_postgres.py`:

- full-file run BEFORE the late-audit case strengthening (before its
  audit add+flush body was added): 8 PASS, 0 skip;
- AFTER the strengthening, ONLY the changed late-audit case re-run with a
  fresh owned fixture: 1 PASS, 0 skip (overlaps the 8; not a 9th unique
  case). The earlier full-file run did NOT execute the later
  audit-insertion body.

- actual Typer entrypoint owner move to an existing institution: every
  omitted metadata/flag preserved (incl. `is_active=False`, `external_id`,
  `notes`), real CLI-created key material/state byte-identical, ONE exact
  `owner_updated` audit with locked old/new + reason + actor;
- clears / conflicts / `--active`/`--inactive`; duplicate normalized
  email, unknown institution/owner, no-field, blank reason, invalid
  actor, and recognized-shape canary refusals with row/audits unchanged
  and no echo;
- late audit fault under a caller-owned transaction: the genuinely
  flushed provisional audit (real add+flush, recorded ID) and the row BOTH
  rolled back (fresh-session absence proof) — evidence from the targeted
  post-strengthening re-run above, not the earlier full-file run;
- cohort partial/clears preserve unrequested fields and the member key
  row; naive datetime interpreted as UTC; name strip normalization;
  invalid FINAL MERGED window / duplicate name / unknown cohort /
  no-field refusals with zero changes/audits; no cohort-institution
  association;
- controlled causal lock-wait for BOTH record types: competitor owns the
  row lock BEFORE the updater starts (readiness barrier), exact holder /
  waiter correlation via `pg_blocking_pids` in an independent observer
  session that explicitly clears the statistics snapshot
  (`pg_stat_clear_snapshot()`) before each poll (the default AsyncSession
  is not autocommit; no sleeps alone); competitor changes an OMITTED
  field and commits only
  after the wait is observed; the updater merges AFTER the fresh populated
  lock read and preserves the committed omitted field; audit old/new
  reflects the latest stored row.

Independent root-side receipts credited (root evidence, not agent runs):
`204-b-cold-import-seam-recheck.json` and
`204-b-email-task-seam-probe.json` (import seam + exact `.delay` UUID
arguments + legacy mock interception + real deferred import still raising
Settings ValidationError before dispatch);
`204-b-partial-record-boundary-probe.json` (baseline reproduction of the
stored-canary audit-leak at the fake-audit-capture level — not proof of
persisted real-audit leakage, because the real `AuditRepository` also
sanitizes values; fixed in the shared guard, which refuses unsafe fresh
current metadata before mutation/return/audit, and covered by the
UNIT-level regressions above plus the root
actual-shared-service/FAKE-repository rechecks; the native PG file covers
the PROVIDED note canary, not the retained-current metadata cases);
`204-b-direct-blank-patch-probe.json`,
`204-b-config-and-input-boundary-probe.json`, and
`204-b-ordinary-metadata-value-probe.json` (supplied-blank, text restart
line, and ordinary-value boundary findings, all addressed in source with
focused regressions). These are qualified per their own receipts (source
intermediary/fake-repo layers, not PG/CLI/205 proof).

## Scope, safety, and limitations

- Product changes are limited to the 204-b allowed paths:
  `schemas/record_edits.py`, `services/owner_service.py`,
  `services/cohort_service.py`, `services/configuration_inspection.py`
  (new), `cli/owners.py`, `cli/cohorts.py`, `cli/configuration.py` (new),
  `cli/main.py` (config registration + root-callback guard), and the two
  fixed task-import seams in `cli/email.py` / `cli/keys.py`. No schema,
  migration, settings default, model, UI, provider, adapter, auth,
  accounting, runtime, queue, or mail-transport change; no new
  dependencies.
- No schema or key-policy migration is required; upgrade is an ordinary
  image rebuild + container recreate (`docker compose up -d --build`).
- The lock-wait cases are ONE causal case per record type under
  READ COMMITTED, not a global serializability or concurrency
  certification. The `config show` snapshot is the current CLI process's
  cached Settings, not live API/worker state; workers must be configured
  consistently (Compose `env_file` changes require recreation, not plain
  restart).
- No production, real upstream/provider/client, real SMTP, installed
  205 wheel, release, or scale claim. All data synthetic; exact owned PG
  container removed; no secrets printed or committed.

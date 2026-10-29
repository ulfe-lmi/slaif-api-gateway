# OAP Objective 204-a — final report: PARTIAL discovery handoff (typed
record-edit drafts + CLI import-boundary finding)

Work order: `oap/orders/204-a-record-edits-and-config-inspection.md`
(committed unchanged on the objective branch with `oap/active` =
`204-a` (6 bytes, no trailing newline); order sha256
`f3aa217cea36d008aed04b30b15beffdd00144dd912b2575cdb26b53865420fa`,
active pointer sha256
`1d0993e3a8b0c08df431bb1776664d12bd45a03830388dc1cf4ddc8274dbe67a`,
both verified before committing).
Branch: `oap/204-record-edits-config-inspection`; base: `main`
`6a523cb75b91899d1376c0ab7909404a242f44ac` (the merged 203 PR #359;
unchanged). PR mode: CREATE_NEW_PR — PR #360,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/360; no auto-merge.
The coding agent never merges; root reviews independently and
guard-merges. All prior orders/reports (including the immutable
203-a/203-b pair) are unchanged.

Implementation head SHA: 67a390e22373e5e24d5194bad325c48a056ac2bd
Report publication commit: SELF

## Status: PARTIAL discovery handoff per root scope decision

Per root decision
(`review-artifacts/cli-feature-round/204-a-import-deferral-scope-decision.json`,
2026-10-29T10:07:01Z), this handoff publishes the UNVERIFIED authorized
record-edit drafts started under 204-a plus the import-boundary
discovery, and root will activate 204-b on the SAME unique PR carrying
the full 204 implementation mandate (acceptance A-E) plus the two
narrowly necessary CLI import-deferral paths. No mid-round silent scope
expansion occurred: no argv sniffing, no global import catch, no
lazy-command framework, and worker/runtime Settings validation is
unchanged.

## Import-boundary finding (reported, NOT implemented — paths outside
the immutable 204-a allowed list)

Root baseline (credited as ROOT evidence, safe booleans/frames only):
`review-artifacts/cli-feature-round/204-a-settings-entry-boundary-baseline.json`
and `204-a-settings-import-stack-investigation.json` — `import
slaif_gateway.cli.main` fails and echoes the synthetic invalid numeric
Settings canary BEFORE the root callback runs.

Locally reproduced (synthetic known-shape canary as an invalid numeric
value for `CODEX_REPLAY_REFERENCE_TTL_SECONDS`; no real credential, no
value published in this report):

- Exact failing chain (frames only):
  `cli/main.py:20` -> `cli/email.py:44`
  (`from slaif_gateway.workers.tasks_email import
  send_pending_key_email_task`) -> `workers/tasks_email.py:17` ->
  `workers/celery_app.py:61` (module-level
  `celery_app = create_celery_app()`) ->
  `create_celery_app:12` -> `get_settings()` -> `ValidationError`.
- Consequence: the safe `config show` unavailable boundary required by
  the order (fixed safe text/JSON, nonzero exit, no secret-like value
  echo) CANNOT be reached by a handler/root-callback guard alone: the
  failure happens at import time, before any command dispatch.
- A second eager import exists at `cli/keys.py:122`
  (`send_pending_key_email_task`), verified by root: a workers-module
  stub masks BOTH imports, so deferring only `cli/email.py` is NOT
  sufficient and must not be claimed as such.
- Needed, narrowly bounded fix (NOT made — reported before editing per
  the order's extra-path rule and deferred to 204-b per the root
  scope decision): move the `workers.tasks_email` task import to
  function scope inside the single command handler using it in
  `app/slaif_gateway/cli/email.py` (module line 44) and
  `app/slaif_gateway/cli/keys.py` (module line 122). No other change in
  either file; the worker task import (and its validation) still runs
  when those email commands execute; no worker/runtime change, no
  argv parsing, no global catch, no lazy-command framework.
- 204-b must add the focused regression: under an invalid numeric
  Settings environment, `import slaif_gateway.cli.main` succeeds and
  `config show --json` exits nonzero with the fixed safe unavailable
  payload, with the canary absent from stdout/stderr/logs.

## UNVERIFIED authorized record-edit drafts (preserved as started)

Drafts within 204-a allowed paths, import-verified only, NO tests
executed, reported as UNVERIFIED/PARTIAL (not finished):

- NEW `app/slaif_gateway/schemas/record_edits.py` — strict typed
  partial-edit boundary: `OwnerUpdatePatch` / `CohortUpdatePatch`
  frozen dataclasses (None = omitted/preserved; explicit clears ONLY
  for nullable fields; replace+clear conflicts, no-field patch,
  blank replacement, malformed UUID/datetime, unknown values, and
  overlong reasons refused with fixed no-echo errors; known-shape
  refusal through the existing finite redaction helpers; 1024-UTF-8
  bounded audit reason law; naive datetimes interpreted as UTC per the
  existing CLI convention).
- `app/slaif_gateway/db/repositories/owners.py` /
  `cohorts.py` — additive `get_owner_for_update` /
  `get_cohort_for_update` (SELECT FOR UPDATE + the existing
  `execution_options(populate_existing=True)` key-repository pattern).
- `app/slaif_gateway/services/owner_service.py` —
  `OwnerService.update_owner_partial` (locks the target row FIRST in
  the caller-owned transaction, merges provided fields with the fresh
  stored values, reuses the existing complete-update
  normalization/validation/repository write and the exact
  `owner_updated` audit; late failure propagates for rollback).

NOT started (204-b scope): the cohort partial method, the
`owners update` / `cohorts update` CLI commands,
`services/configuration_inspection.py`, `cli/configuration.py`, the
`cli/main.py` registration and new-config-group guarded settings path,
all four new test files, additive consumer cases, and all documentation.

## Evidence performed in this round (honest, minimal)

- Local import-boundary reproduction under a synthetic invalid numeric
  Settings environment (frames recorded; canary value not published):
  `IMPORT_FAILED: ValidationError` at the exact chain above; with a
  `workers.tasks_email` stub the import succeeded
  (`IMPORT_OK_WITH_STUB`) — masked-stub evidence only, superseded by
  the root two-import finding.
- Draft product modules import cleanly
  (`schemas.record_edits`, `db.repositories.owners`,
  `db.repositories.cohorts`, `services.owner_service`,
  `services.cohort_service` all IMPORT_OK) after the locked lookups
  were corrected from an unavailable `sqlalchemy.orm.populate_existing`
  import to the existing
  `execution_options(populate_existing=True)` pattern (root-verified
  against the installed SQLAlchemy).
- No JUnit/test matrix, no owned-PostgreSQL run, and no CI wait were
  performed for this discovery handoff (per the root scope decision);
  all functional acceptance (A-E) remains to be implemented and proven
  in 204-b.

## Boundaries and limitations

- No schema migration, no key-policy migration, no new settings, no
  `.env.example` change, no UI/provider/adapter/module/auth/
  accounting/runtime/queue/mail/dependency/workflow change in this
  handoff.
- No 205 installed-wheel/executable, provider, client, or mail
  qualification is claimed; nothing here proves any of the eleven
  final installed-executable outcomes.
- Protected unrelated untracked `CODEX-SESSIONS.md`
  (sha256 `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`)
  and `codex.sh` (sha256
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`)
  remain untracked and preserved; ignored configs/catalogs/foreign
  worktrees/resources untouched.
- Deployment of the eventual 204 surface remains the ordinary image
  rebuild/recreate (no migration); documented in 204-b.

Documentation intentionally deferred: no CLI surface is implemented or
verified in this discovery handoff; the full operator documentation
(`owners update` / `cohorts update` / `config show` sections, portable
deployment guidance, and the verification record) is due with the 204-b
implementation on the same PR #360.

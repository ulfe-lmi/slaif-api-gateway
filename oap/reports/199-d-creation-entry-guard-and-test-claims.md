# OAP Objective 199-d — final report: creation entry guard and precise test claims

Work order: `oap/orders/199-d-creation-entry-guard-and-test-claims.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `199-d` (5 bytes, no trailing newline); order sha256
`c15f562f1ca5e3335b34130b9f79277f3529f15da844015b28eb5384e9b97707`
(9304 bytes), active pointer sha256
`4ab56068bdfb7ffc7023929bc0c52d0d7c03b14d275214f72f36b6af443779e3`,
both verified before committing and re-verified in the implementation
commit).
Branch: `oap/199-provider-route-configuration`; base: `main`
`df7fb43cc9898cc784cf83cd10ddad9e946fc2af`.
PR mode: AMEND_EXISTING_PR — the same unique PR #355 created by 199-a,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/355, base `main`,
title "Configure provider timeouts and update routes through reviewed CLI
plans" (OPEN/MERGEABLE at publication; the only other open PR is the
unrelated #319). The coding agent never merges; no auto-merge; root
reviews independently and guard-merges.

Implementation head SHA: d420c7f24ea0857520476fd8086554768fe3b0de
Report publication commit: SELF

## Predecessor state (immutable)

199-a is complete on this branch: implementation head
`af792c9a00ff519f20cd20c39fbdf709fb76221c` and its report commit
`3170b6611b0e7765f071eedec8e859bc867d505c` (order sha256
`18f50b2dcfda225a7d358db1a167a66a576c0f8c6b5d3e93623ed19c9525fee6`).
199-b is complete on this branch: implementation head
`16d3a2d7e492f646d315f9e15858373a2b234ac8` (order sha256
`d1846162e5a85496ae49aa45511a3eb0c787f805d4fc057ede8c0fb64672dcb6`) and
its report commit `e0c0e3c9fb8a4c8eea2936dd326758cc47b0c8da` (report
sha256 `6e0fa48050742067d01207d205eae65ace2011b19074bfb3e4930195b7bd7c2f`).
199-c is complete on this branch: implementation head
`581d52f4be4758b6e5d830da5a7feacdee3b872a` and its report commit
`d0fdb2f12159409cd9a8cc6bd6b558413e04af85` (order sha256
`0bedb600ce7aea086da355530dbaa8d622c148a2e7c0a25037ef8e944db345af`,
report sha256
`c9048f780fe3947fd945571ebf5b4ff1861cc83c5fc70b995cdc97bab1b52dac`).
None was amended by this round; the 199-d implementation commit's first
parent is the 199-c report commit `d0fdb2f`. Objectives 200-205 remain
INERT; no other 199 suffix was activated. The 199-c response session
40737 was polled CLOSED with the exact response OK and was never
reopened or re-signaled.

## Implementation commit (this round)

1. `d420c7f24ea0857520476fd8086554768fe3b0de` — "Guard the actual async
   provider creation entry point and make 199 test claims precise
   (199-d)": the strategic order (bytes verified unchanged, sha256
   above) + exact `oap/active` = `199-d` + the bounded implementation,
   tests, docs, and verification addendum listed below.

No schema migration, no DDL, no new dependency, no workflow/config/
template/CSS change, no UI change, and no runtime
auth/admission/accounting/forwarding/Redis behavior was modified. The
core `ProviderConfigService` / `ProviderConfigsRepository` creation
path, the route service, the schema, and every other entry point are
unchanged; only `cli/providers.py` gained the small shared check.
Objectives 200-205 were not started.

## Allowed diff (implementation commit, 6 files)

Product (allowed paths only):

- `app/slaif_gateway/cli/providers.py` — D1: one small shared
  `_refuse_known_secret_shapes` check for the SAME four free-form
  creation fields (`display_name`/`base_url`/`notes`/`reason`), invoked
  by the Typer `add` command (replacing its previous inline loop, same
  fixed no-echo `BadParameter` errors) AND at the top of the ACTUAL
  async `_add_provider`, BEFORE `cli_db_session` is opened. Reuses the
  existing `contains_known_secret_shape`; no sanitizer/configuration
  framework. The public CLI refusal, the optional-creation-reason law,
  environment-variable-reference NAMES, the disabled default, the
  timeout/retry values, the HTTP confirmation law, and the output
  behavior are all unchanged.

Tests (allowed paths only):

- `tests/unit/test_cli_provider_route_configuration.py` — 35 -> 37
  actual-Typer tests: (D1) two new direct-helper regressions call the
  ACTUAL async `_add_provider` directly with a recognized canary in each
  field while the DB context is instrumented to fail if reached (fixed
  refusal asserted, no canary echo, no DB open, no service call) plus
  one positive ordinary-text/env-NAME/optional-reason case reaching a
  recording service; (D2b) `test_tampered_plan_forwarded_and_detected_
  stale` renamed to `test_tampered_plan_strictly_parsed_and_forwarded`
  with a truthful comment: its MOCKED execute proves strict parsing and
  forwarding of the tampered document exactly as stored (and that the
  expected configuration fingerprint is bound to the SOURCE
  configuration, unchanged by the proposed priority) — NOT actual
  service staleness; the assertions are unchanged.
- `tests/unit/test_provider_route_configuration.py` — 135 -> 136
  pure-layer tests: (D2a) `test_route_identity_swap_refused` had its
  unused `row`/`_provider_row` assignment removed (harness fixture, its
  dependency execution, tampered identity, expected exception, and
  zero-write law unchanged); (D2b) one new focused actual-service test
  `test_proposed_value_revalidation_distinct_from_source_staleness`:
  a valid proposed scalar edit (source priority 100, proposed 50)
  applies exactly once while the source is unchanged (no stale
  refusal), and an actual source mutation behind the plan then refuses
  the SAME plan stale with no further writes or audits. No signed
  plans, no proposal integrity signature, no new digest field, no
  approval receipts, no trust-model change; the existing
  route/provider identity/context guards, candidate validation, and
  policy limits are intact.

Docs (allowed paths only):

- `docs/verification/2026-10-28-cli-provider-route-configuration.md` —
  APPENDED "199-d ADDENDUM" (the 199-a text, 199-b addendum, and 199-c
  addendum are unchanged). The addendum CORRECTS the 199-c boundary
  claim without rewriting 199-c history: the 199-c known-shape guard
  sat only in the Typer `add` handler, so a direct call to the private
  async `_add_provider` still opened the database context and invoked
  the actual core creation service with a recognized canary in `notes`
  (a PRIVATE-helper boundary nonconformance, not a demonstrated public
  CLI/HTTP authentication bypass); 199-d completes the 199-c C2
  requirement by invoking one shared check at BOTH entry points.
  Operator docs are unchanged because public behavior is unchanged.

OAP: exact `oap/active` = `199-d` (5 bytes, no newline) and the
strategic order, both byte-verified unchanged at the implementation
head.

## Actual focused verification (this execution)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
(Python 3.12) with `env -u DATABASE_URL -u TEST_DATABASE_URL`; no
ambient `DATABASE_URL` / foreign PG and no database or backend contact
in any 199-d run (the guard executes before any database access);
JUnit receipts under `/tmp/slaif199/` (disposable). The genuine 199-c
receipts (`c-affected.xml` 330, `c-pg.xml` 31, `c-gov-inv-drift.xml`
37) were NOT rerun and are attributed to 199-c evidence; no 199-d PG,
full-matrix, browser, or Docker Compose run was performed or claimed —
the 199-c creation no-write/no-audit owned-PG proofs remain the
PostgreSQL proof for creation.

- The two affected unit suites, one run, after all 199-d changes:
  **173 passed, 0 failed / 0 errors / 0 skipped**, exit 0
  (`d-affected.xml`): `test_provider_route_configuration` (136 = 135 + 1
  new) and `test_cli_provider_route_configuration` (37 = 35 + 2 new),
  including the existing CLI creation tests, the renamed truthful
  mocked-plan test, and the new direct-helper cases.
- `test_cli_providers` (help/signature suite, affected by the touched
  CLI module): **7 passed, 0 failed / 0 errors / 0 skipped**, exit 0
  (`d-cli-providers.xml`).
- Governance/inventory/drift, one run after the docs append: **37
  passed, 0 failed / 0 errors / 0 skipped**, exit 0 (`d-gov.xml`):
  `test_oap_governance` (9), `test_documentation_inventory` (13),
  `test_documentation_contract_drift` (15) — the unchanged
  consumer-allowlist guard included; these 37 are disjoint from the 173
  above (no overlapping counts are claimed).
- Gates: `ruff check app/ tests/` clean;
  `python3 scripts/check_documentation.py` -> `OK files=126`;
  `git diff --check` clean.

## Security and privacy statements

- Secret protection remains KNOWN-SHAPE protection: recognized
  credential patterns are refused on new input (creation free-form
  fields now guarded at BOTH the public Typer command and the actual
  async helper entry point, before any database access) and redacted on
  safe reads; it is NOT universal content sanitization. `api_key_env_var`
  NAMES and structured fields are never masked; no credential VALUE is
  ever accepted, resolved, or printed. No canary appears in any new
  error, output, or log path (the direct-helper regressions assert the
  fixed refusal carries no canary text).
- The guard placement change is private-boundary only: public CLI
  refusals, output, defaults, and laws are unchanged, so no user-facing
  behavior or security property changed beyond the previously missing
  helper-level refusal.
- No real provider, client, SMTP, Redis, or network contact was made by
  this execution's evidence; no database was contacted at all.

## Honest state and limitations

- Final-head CI is root-gated and its state is **PENDING** at this
  publication: the new head `d420c7f` was pushed immediately before
  report publication with all final-head checks pending (only the
  Documentation hygiene job had passed at the moment of publication).
  The 199-c head checks were still in progress at 199-c review time and
  are not claimed as a pass. The final new SELF must have all checks
  green before root merges; no CI result is claimed here.
- No owned-PostgreSQL run for 199-d (unit-layer proof of the
  before-DB-access guard; the 199-c PG proofs stand as 199-c evidence).
  No full verification matrix, browser, or Docker Compose coverage was
  run for 199-d.
- The two CodeQuality unused-variable threads are addressed in source;
  root independently verifies and resolves the threads.
- The 200-205 rows and the 205 full executable-only transcript remain
  outstanding. No 205/all-11-DoD or real-backend qualification claim.
- Plan files and JUnit receipts under `/tmp/slaif199/` are disposable
  execution state, not durable evidence.

# OAP Objective 199-a — final report: provider/route configuration parity

Work order: `oap/orders/199-a-provider-route-configuration.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `199-a` (5 bytes, no trailing newline); order sha256
`18f50b2dcfda225a7d358db1a167a66a576c0f8c6b5d3e93623ed19c9525fee6`,
verified before and after committing).
Branch: `oap/199-provider-route-configuration`; base: `main`
`df7fb43cc9898cc784cf83cd10ddad9e946fc2af`.
PR mode: CREATE_NEW_PR — NEW unique PR #355,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/355, base `main`,
title "Configure provider timeouts and update routes through reviewed CLI
plans". The coding agent never merges; no auto-merge; root reviews
independently and guard-merges.

Implementation head SHA: af792c9a00ff519f20cd20c39fbdf709fb76221c
Report publication commit: SELF

## Predecessor state (unchanged)

Objective 198 is TERMINAL: its unique PR #354 was merged into `main` as
`df7fb43cc9898cc784cf83cd10ddad9e946fc2af` (the base of this branch;
198-c was its final suffix). Objectives 200-205 remain INERT. The only
other open PR is the unrelated Dependabot PR #319 (preserved). No 199
suffix beyond this `199-a` was activated.

## Implementation commit (this round)

1. `af792c9a00ff519f20cd20c39fbdf709fb76221c` — "Configure provider
   timeouts and update routes through reviewed CLI plans (199-a)": the
   strategic order (bytes verified unchanged, sha256 above) + exact
   `oap/active` = `199-a` + the bounded implementation, tests, docs, and
   verification record listed below.

No schema migration, no DDL, no new dependency, no workflow/config/
template/CSS change, no UI change, and no runtime
auth/admission/accounting/forwarding/Redis behavior was modified.
Objectives 200-205 were not started.

## Allowed diff (implementation commit, 24 files)

Product (allowed paths only):

- `app/slaif_gateway/schemas/provider_route_configuration.py` (NEW, 769
  lines) — strict envelopes: capabilities file (schema version 1,
  `{"schema_version", "capabilities"}` only, 64 KiB bound) and route
  update plan (schema version 1, every top-level field explicit, 128 KiB
  bound). Unknown/duplicate JSON keys, wrong types, non-UTF-8, and
  oversized inputs are refused with fixed safe errors that never echo
  file bodies, paths, or values. `validate_capabilities_document`
  reuses the existing pure group validators (chat/responses bool blocks,
  codex limits strict relationships, media engine ceilings,
  external_tools parser + approved operator ceilings,
  completion_service selector). `CapabilityPatch` (frozen, `_ABSENT`
  sentinel for completion-service omitted-vs-clear) +
  `merge_capability_patch` merge explicit leaves only, deeply
  preserving all siblings. `parse/render_route_update_plan` strict
  round-trip.
- `app/slaif_gateway/services/provider_route_configuration.py` (NEW,
  516 lines) — shared service: `compute_route_configuration_fingerprint`
  (SHA-256 over the 11 reviewed configuration fields — capabilities,
  notes, enabled, endpoint, match type, provider, upstream model,
  priority, visibility, streaming, requested model; identity and
  timestamps excluded; staleness data only, never credential or replay
  authority); `validate_merged_route_candidate` (existing capability /
  module / profile / kind contracts, incl. completion-service selector
  vs module kind + chat endpoint + public/upstream model identity);
  `partial_update_provider_config` (FOR UPDATE lock before assembling
  the complete service input, so omitted fields preserve fresh values
  and zero retries survive; explicit clear-notes is a single-column
  change in the same locked transaction under the service's one audit
  record; `enabled` preserved — enable/disable own that field);
  `preview_route_update` / `preview_route_update_for_route` (read-only;
  the preview note states configuration review only, the distinct
  ceiling/reservation/physical/client values, and that NO credential,
  model, or SMTP qualification is performed);
  `execute_route_update_plan` (route FOR UPDATE, then fresh
  fingerprint/enabled/provider-kind revalidation → stale refusal with
  zero writes/audits; merged candidate revalidated against the fresh
  provider kind; ONE audited
  `ModelRouteService.update_model_route` in the caller transaction;
  documented no-op law: zero-diff proposed state returns the row with
  ZERO writes and ZERO audits).
- `app/slaif_gateway/cli/provider_route_files.py` (NEW, 90 lines) —
  `read_bounded_file` (cap+1 before parse), `read_capabilities_file`,
  `read_route_plan_file`, `write_route_plan_file` (strict round-trip
  gate, `O_EXCL` 0600, no overwrite, fixed no-echo errors).
- `app/slaif_gateway/cli/providers.py` — `add` gains
  `--timeout-seconds` (positive, default 300), `--max-retries`
  (non-negative, 0 valid, default 2), `--actor-admin-id`; deliberate
  default change: omitted `--enabled/--disabled` at creation stays
  DISABLED (explicit `--enabled` only activates). NEW `update` command:
  `--reason` required; partial update of display name, base URL, kind,
  credential ENV-var name, timeout, retries, notes;
  `--notes`/`--clear-notes` mutually exclusive; no `--enabled` flag.
- `app/slaif_gateway/cli/routes.py` — `add` gains
  `--capabilities-file` (COMPLETE strict document), optional
  `--reason`, `--actor-admin-id`; deliberate default: capabilities-file
  preparation stays DISABLED unless explicit `--enabled`, flag-free
  creation keeps the historical enabled default. NEW `update` command:
  `--dry-run PATH` (READ-ONLY; typed edit flags; writes NEW 0600 plan)
  XOR `--execute PATH --reason` (edit flags on execute refused — mixed
  mode; file+partial-flags refused; `--notes`/`--clear-notes` and
  `--completion-service-profile`/`--clear-completion-service` mutually
  exclusive).
- `app/slaif_gateway/db/repositories/provider_configs.py`,
  `app/slaif_gateway/db/repositories/routing.py` — ONLY additive
  `get_provider_config_for_update` / `get_model_route_for_update`
  (FOR UPDATE readers); no other repository behavior changed.
- `app/slaif_gateway/services/chat_completion_route_capabilities.py`,
  `responses_route_capabilities.py`, `media_input_estimation.py` —
  extracted pure config-time validators
  (`validate_chat_completion_capability_block`,
  `validate_responses_capability_block`,
  `validate_media_input_estimation_block`) as public wrappers over the
  EXACT existing runtime metadata rules, so configuration surfaces
  reuse the same acceptance without a second drifting rule; runtime
  behavior preserved (their full existing suites pass unchanged).

Tests (allowed paths only):

- NEW `tests/unit/test_provider_route_configuration.py` (1035 lines) —
  90 pure-layer tests: capabilities file schema, capability groups,
  typed patch/merge, fingerprint, preview, provider partial update,
  plan document, execute service, merged-candidate validation.
- NEW `tests/unit/test_cli_provider_route_configuration.py` (540 lines)
  — 25 actual-Typer CLI tests: providers add/update, routes add,
  routes update dry-run/execute surface, tri-state enabled defaults,
  refusal matrix.
- NEW `tests/integration/test_cli_provider_route_configuration_postgres.py`
  (1002 lines) — 19 owned-PostgreSQL-16 tests (owned disposable
  container, label-owner `slaif199a.*.owner`, loopback-only, tmpfs,
  alembic head; fictional module/openai_compatible providers, zero-price
  pricing rows, Codex/media/completion-service routes, planted
  owner/key/ledger/replay).
- `tests/unit/test_cli_providers.py`, `tests/unit/test_cli_routes.py` —
  help-command inventory lists include `update` (changed help surface
  only).
- `tests/unit/test_documentation_contract_drift.py` — the two exact
  justified 199-a consumer allowlist entries (the NEW schema module is a
  read-only consumer validating the external_tools block against the
  authoritative parser/ceilings; the NEW service module is a config-time
  consumer validating merged candidates against the operator ceilings;
  both grant no runtime hosted-tool authority). Discovery and all other
  assertions preserved; the guard is not weakened.

Docs (allowed paths only):

- `docs/cli-reference.md` — family lines + new "Provider and route
  configuration parity" section (options, defaults,
  partial-vs-replacement, clear/conflict refusals, plan/fingerprint/
  stale/no-op law, review-context note, secret-safe behavior) + the two
  new subcommands in the checked command inventory.
- `docs/cli-field-administration.md` — new "Implemented in objective
  199" table; the 199 row removed from the proposed table (200-205
  remain proposed).
- `docs/completion-services.md` — the operator Python setup snippet
  replaced with the actual CLI commands (module provider creation with
  30/180 s timeouts and 0 retries, capabilities-file route
  preparation, explicit enablement); zero-priced module billing
  statement unchanged.
- `docs/media-input-estimation.md` — actual CLI partial budget edit
  example through the reviewed plan workflow.
- NEW `docs/verification/2026-10-28-cli-provider-route-configuration.md`
  + `docs/verification/README.md` index entry.

OAP: exact `oap/active` = `199-a` (5 bytes, no newline) and the
strategic order, both byte-verified unchanged.

## Actual focused verification (this execution)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
(Python 3.12) with `env -u DATABASE_URL -u TEST_DATABASE_URL`; no
ambient `DATABASE_URL` / foreign PG (the integration layer's owned
container is the only database); JUnit receipts under `/tmp/slaif199/`
(disposable).

- New unit suite, pure layer, no DB: 90 passed, 0 failed / 0 errors /
  0 skipped, exit 0 (`unit-pure.xml`).
- New unit suite, actual-Typer CLI: 25 passed, 0 failed / 0 errors /
  0 skipped, exit 0 (`unit-cli.xml`).
- Owned-PostgreSQL-16 integration module: 19 passed, 0 failed / 0
  errors / 0 skipped, exit 0 (~21 s) (`pg3.xml`). Demonstrated in PG:
  dry-run read-only + 0600 plan; partial apply preserves unmentioned
  fields and sibling capability groups; repeated apply of an applied
  plan refused stale with zero writes/audits; forced LATE audit failure
  (hook asserting the updated row visible in the SAME transaction
  before raising) rolls back the whole mutation — row byte-equal to
  before, no orphan audit — and the same plan re-executes successfully;
  competing committed route change invalidates a previewed plan (stale,
  zero writes); competing provider change preserves omitted provider
  fields while the plan's provider-kind revalidation still gates the
  route update; zero-diff plan no-op with zero writes/audits;
  secret-shape/oversize/invalid refusals with fixed no-echo errors and
  no mutation.
- Focused regression batch (both new unit suites + touched suites
  `test_chat_completion_route_capabilities` 29,
  `test_responses_route_capabilities` 57,
  `test_media_input_estimation` 36,
  `test_provider_config_service` 8, `test_model_route_service` 4,
  `test_cli_providers` 7, `test_cli_routes` 8 + governance
  `test_oap_governance` 9, `test_documentation_inventory` 13,
  `test_documentation_contract_drift` 15): 301 passed, 0 failed / 0
  errors / 0 skipped, exit 0 (`unit-final.xml`).
- Gates: `ruff check app/ tests/` — All checks passed;
  `scripts/check_documentation.py` — `DOCUMENTATION_CHECK=OK
  files=126`; `git diff --check` — clean.
- Passed suites were not repeated for display/count formatting; no
  full local unit/browser/HPC matrix was run.

## CI state (honest)

At publication the implementation head
`af792c9a00ff519f20cd20c39fbdf709fb76221c` and this report-only head
have NO completed final-head CI result recorded here; the normal
FINAL-head CI is the broad gate and was PENDING at the time of this
record. Root independently owns final-head CI and strategic review; the
coding agent did not wait on, merge, or act on CI results.

## Security / privacy / accounting statements

- No provider credential VALUE is accepted, resolved, printed, stored,
  or logged by any new command; only environment-variable NAMES are
  administered. Recognized secret shapes (existing redaction patterns)
  in new configuration/plan input are refused with fixed no-echo
  errors — known-shape protection, not universal content sanitization.
- Every mutation is one audited change in one caller transaction on the
  FOR UPDATE-locked row; a late audit or transaction failure rolls back
  the entire change (proven in PG with a forced late-audit failure and
  same-transaction visibility of the updated row before the failure).
- Reviewed plans are staleness-checked after locks: fresh
  fingerprint/enabled/provider-kind must still match, otherwise the
  execute is refused with zero writes and zero audits; repeated applies
  of an already-applied plan are refused stale rather than re-mutated;
  zero-diff plans no-op with zero writes/audits.
- Plan and capabilities files are read at cap+1 before parse; plans are
  written exclusively with mode 0600 and never overwritten; every
  successful dry-run document re-parses with the same strict schema
  before the file exists.
- The extracted pure validators are parity wrappers over the exact
  existing runtime metadata rules (their unchanged existing suites
  pass), so configuration acceptance and runtime acceptance cannot
  drift.

## Documentation impact

Required by AGENTS.md §5.1. Changed documented CLI and configuration
contracts: `docs/cli-reference.md` (new section + command inventory),
`docs/cli-field-administration.md` (199 → implemented; 200-205
proposed), `docs/completion-services.md` (CLI replaces operator Python),
`docs/media-input-estimation.md` (CLI example), plus the new
verification record and its README index entry.

## Limitations

- Synthetic data only: fictional providers (module
  `svc-a`/`svc-b`/`svc-c`, openai_compatible), zero-price pricing rows,
  planted fictional owner/key; no real provider/model contact, no
  credential, no real SMTP, no Redis, no upstream smoke. Config
  validation is NOT credential/model/SMTP/provider qualification, and
  no plan performs any such qualification.
- The objective-205 installed-executable transcript is still
  outstanding; this record does not declare the full brief or the
  eleven DoD complete, and makes no release/compliance/performance
  claim.
- No full verification matrix, Docker Compose, browser, or Redis
  coverage was run for this objective; final-head CI is gated by root.
- JUnit receipts under `/tmp/slaif199/` are disposable execution
  state, not durable evidence. This record is commit-specific evidence
  for the 199 PR head; it does not certify later commits, production
  fitness, security, compliance, or scale.

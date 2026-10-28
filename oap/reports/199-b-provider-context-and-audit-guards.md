# OAP Objective 199-b — final report: provider context bindings, audit and privacy guards

Work order: `oap/orders/199-b-provider-context-and-audit-guards.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `199-b` (5 bytes, no trailing newline); order sha256
`d1846162e5a85496ae49aa45511a3eb0c787f805d4fc057ede8c0fb64672dcb6`,
verified before and after committing).
Branch: `oap/199-provider-route-configuration`; base: `main`
`df7fb43cc9898cc784cf83cd10ddad9e946fc2af`.
PR mode: AMEND_EXISTING_PR — the same unique PR #355 created by 199-a,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/355, base `main`,
title "Configure provider timeouts and update routes through reviewed CLI
plans". The coding agent never merges; no auto-merge; root reviews
independently and guard-merges.

Implementation head SHA: 16d3a2d7e492f646d315f9e15858373a2b234ac8
Report publication commit: SELF

## Predecessor state (immutable)

199-a is complete on this branch: implementation head
`af792c9a00ff519f20cd20c39fbdf709fb76221c` and its report commit
`3170b6611b0e7765f071eedec8e859bc867d505c` (report order sha256
`18f50b2dcfda225a7d358db1a167a66a576c0f8c6b5d3e93623ed19c9525fee6`).
Neither was amended by this round; the 199-b implementation commit's
first parent is the 199-a report commit. Objectives 200-205 remain
INERT; no other 199 suffix was activated.

## Implementation commit (this round)

1. `16d3a2d7e492f646d315f9e15858373a2b234ac8` — "Bind reviewed provider
   context, fix provider audit and privacy guards (199-b)": the
   strategic order (bytes verified unchanged, sha256 above) + exact
   `oap/active` = `199-b` + the bounded implementation, tests, docs,
   and verification addendum listed below.

No schema migration, no DDL, no new dependency, no workflow/config/
template/CSS change, no UI change, and no runtime
auth/admission/accounting/forwarding/Redis behavior was modified.
ProviderConfigService/ModelRouteService CRUD bodies, AuditRepository,
the three extracted pure validators, and the registry/modules/profiles/
adapter layer are unchanged. Objectives 200-205 were not started.

## Allowed diff (implementation commit, 15 files)

Product (allowed paths only):

- `app/slaif_gateway/services/provider_route_configuration.py` — R1:
  `partial_update_provider_config` no longer pre-clears notes before
  mutation; the nonblank reason is enforced and display name / base URL
  / notes / reason are refused pre-mutation when they carry a recognized
  credential shape (fixed no-echo errors); the explicit clear delegates
  `notes=None` through the UNCHANGED shared service, so the one audit
  record carries the REAL prior notes value. R2: destination-provider
  resolution (`_resolve_destination_provider`: read-only for preview,
  FOR UPDATE for execution — deterministic lock order route, then
  provider); the plan now binds `expected_route_id`,
  `expected_provider_id`, and
  `expected_provider_context_fingerprint` (SHA-256 over kind, base URL,
  credential env-var NAME, timeout, retries; display fields and enabled
  excluded on purpose); the route configuration fingerprint is
  ROUTE-BOUND (route UUID included, only timestamps excluded);
  `preview_route_update` renders CANONICAL current/proposed
  configurations (the exact stored shape the service writes, defaults
  included, from the shared pure normalizer) plus changed canonical
  field names — review data, never execution authority;
  `execute_route_update_plan` revalidates in order (route identity,
  enabled, route-bound fingerprint, destination existence, provider
  identity, provider context fingerprint), canonicalizes the merged
  candidate with the same pure normalizer (installation ceilings
  included), revalidates it against the FRESH provider row, and keeps
  the documented no-op law (zero-diff returns the row with zero
  writes/audits). R4: NEW `validate_route_creation_candidate` —
  provider existence, notes secret guard, and strict merged-candidate
  validation (kind, chat endpoint, zero-retry rule, configured profile
  directory) BEFORE any route write.
- `app/slaif_gateway/schemas/provider_route_configuration.py` — plan
  schema gains the three binding fields (UUID/UUID/hex64; old unmerged
  shapes fail strict parsing — a new dry-run is required); the preview
  block is validated against the exact canonical key set;
  `local_coding`/`local_coding_vllm` are parsed with the existing strict
  transport-contract parsers (mutual exclusion enforced by the vLLM
  parser); `external_tool_ceilings` and `profile_dir` are threaded
  through capabilities/patch/plan parsing, validation, and rendering.
- `app/slaif_gateway/services/model_route_service.py` — additive PURE
  `normalize_route_configuration` wrapper (composes the private
  normalizers; installation ceilings included); CRUD bodies untouched.
- `app/slaif_gateway/cli/routes.py` — `add` guards `--notes` against
  known credential shapes BEFORE any database access and validates the
  creation candidate with the actual settings before writing; `update`
  requires a NONBLANK, secret-shape-guarded `--reason` on execute, binds
  the route ARGUMENT to the reviewed plan ("The route argument must
  match the reviewed plan."), and threads the actual installation
  ceilings + configured `COMPLETION_SERVICE_PROFILE_DIR` through
  preview, plan reads, and the plan-write round-trip gate (the
  round-trip previously revalidated under default ceilings and the
  bundled profile directory — fixed by this round and proven by the
  configured-profile PG test).
- `app/slaif_gateway/cli/providers.py` — `update` enforces a NONBLANK
  reason and refuses known credential shapes in
  `--display-name`/`--base-url`/`--notes`/`--reason` before mutation;
  `_safe_provider_dict` projects free-form read values (display name,
  base URL, notes) through the existing known-shape redaction while
  `api_key_env_var` NAMES are never masked.
- `app/slaif_gateway/cli/provider_route_files.py` — ceilings/profile
  directory threaded through `read_capabilities_file`,
  `read_route_plan_file`, and `write_route_plan_file`; the ceilings
  types are re-exported through the allowlisted route service module
  (the external-tool consumer-allowlist guard stays unchanged).

Tests (allowed paths only):

- `tests/unit/test_provider_route_configuration.py` — grown to 118
  pure-layer tests: route-bound fingerprints; plan document binding
  fields + old-shape refusals; permissive local-coding oracle replaced
  with strict valid/malformed/conflicting-contract cases; installation
  ceiling enforcement; canonical preview blocks (codex 32768/400000/
  1050000, endpoint-change defaults, cross-provider binding);
  clear-notes without pre-mutation/pre-flush and real prior-value
  audit; blank-reason and known-shape canary refusals; execute stale
  matrix (route-identity swap, provider-context drift, provider-identity
  impostor, missing destination); NEW `TestValidateRouteCreationCandidate`.
- `tests/unit/test_cli_provider_route_configuration.py` — grown to 31
  actual-Typer tests: renderer-stable terminal env (COLUMNS/NO_COLOR)
  with ANSI/wrapping-independent assertions on every invoke; new
  blank-reason, known-secret-shape (canary
  `sk-proj-…`), and safe-output redaction tests; route-argument/plan
  binding test.
- `tests/integration/test_cli_provider_route_configuration_postgres.py`
  — grown to 24 owned-PostgreSQL-16 tests (same owned-container
  discipline); five NEW 199-b proofs: successive real provider updates
  audit the REAL prior notes value; provider switch binds destination
  identity + context (context drift refused stale with zero
  writes/audits; fresh review applies exactly once; a plan tampered to
  target a twin route refused on route identity with zero writes; a
  deleted destination provider refused as missing); a lowered
  `EXTERNAL_TOOL_MAX_PROVIDER_TOOL_CALLS_PER_REQUEST=1` ceiling denies a
  cap-2 policy at dry-run and stores cap-1 after review; a configured
  `COMPLETION_SERVICE_PROFILE_DIR` operator directory (0600 file)
  resolves a custom profile, refuses bundled-only and unknown profiles,
  and executes without resolving or printing the credential env-var
  reference; known credential shapes refused pre-mutation (provider
  notes/display name, route creation notes) with zero writes/audits and
  a directly planted LEGACY stored notes value redacted on
  `providers show`.

Docs (allowed paths only):

- `docs/cli-reference.md` — the 199 section corrected for 199-b:
  nonblank + secret-shape-guarded reasons; guarded `routes add --notes`;
  route-bound fingerprint and the destination-provider bindings (old
  plans need a new dry-run); deterministic lock order and the full stale
  chain; canonical preview blocks; ACTUAL installation ceilings and the
  configured profile directory (operator files 0600; bundled directory
  not visible when configured; zero-retry rule; model identity match);
  clear-notes delegation + real-repo None-skip boundary; safe-read
  redaction (env-var NAMES never masked).
- `docs/cli-field-administration.md` — the 199 rows corrected to the
  199-b semantics (nonblank reason, guarded fields, clear-notes
  delegation/boundary, plan bindings, route-argument binding, actual
  ceilings + configured profile directory, route-bound fingerprint).
- `docs/completion-services.md` — configuration-time validation
  statement (module kind, chat endpoint, `max_retries=0` zero-retry
  rule, configured profile directory, public/upstream model identity;
  configuration validation is not credential/model readiness).
- `docs/verification/2026-10-28-cli-provider-route-configuration.md` —
  APPENDED "199-b ADDENDUM" (the 199-a text is unchanged); the
  `docs/verification/README.md` index is unchanged (same objective).

OAP: exact `oap/active` = `199-b` (5 bytes, no newline) and the
strategic order, both byte-verified unchanged at the implementation
head.

## Actual focused verification (this execution)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
(Python 3.12) with `env -u DATABASE_URL -u TEST_DATABASE_URL`; no
ambient `DATABASE_URL` / foreign PG (the integration layer's owned
container is the only database); JUnit receipts under `/tmp/slaif199/`
(disposable).

- Affected/touched suites, one run, after all 199-b product fixes:
  298 passed, 0 failed / 0 errors / 0 skipped, exit 0
  (`b-affected3.xml`): `test_chat_completion_route_capabilities` (29),
  `test_responses_route_capabilities` (57),
  `test_media_input_estimation` (36), `test_provider_config_service`
  (8), `test_model_route_service` (4), `test_cli_providers` (7),
  `test_cli_routes` (8), plus the two 199-b unit suites
  (`test_provider_route_configuration` 118,
  `test_cli_provider_route_configuration` 31). Earlier receipts for the
  two new suites alone: `b-unit-pure1.xml` (118), `b-unit-cli1.xml`
  (31) — counts match the final batch.
- Owned-PostgreSQL-16 integration module (owned disposable container,
  label-owner `slaif199a.*.owner`, loopback-only, tmpfs, alembic head;
  container removed on teardown, zero leftover containers): 24 passed,
  0 failed / 0 errors / 0 skipped, exit 0 (~28 s) (`pg-b.xml`) — the
  post-fix run, including the five new 199-b proofs above.
- Governance/inventory/drift, one run: 37 passed, 0 failed / 0 errors /
  0 skipped, exit 0 (`b-gov-inv-drift.xml`): `test_oap_governance` (9),
  `test_documentation_inventory` (13),
  `test_documentation_contract_drift` (15) — including the unchanged
  external-tool consumer-allowlist guard.
- Gates: `ruff check app/ tests/` — All checks passed;
  `scripts/check_documentation.py` — `DOCUMENTATION_CHECK=OK
  files=126`; `git diff --check` — clean.
- The new configured-profile PG test caught a real 199-b gap (plan
  write round-trip revalidated under default ceilings/bundled profile
  directory instead of the configured installation state); the fix is
  in this commit and the green PG run above is post-fix.
- Passed suites were not repeated for display/count formatting; no
  full local unit/browser/HPC matrix was run.

## CI state (honest)

At publication the implementation head
`16d3a2d7e492f646d315f9e15858373a2b234ac8` and this report-only head
have NO completed final-head CI result recorded here; the normal
FINAL-head CI is the broad gate and was PENDING at the time of this
record. Root independently owns final-head CI and strategic review; the
coding agent did not wait on, merge, or act on CI results.

## Security / privacy / accounting statements

- No provider credential VALUE is accepted, resolved, printed, stored,
  or logged by any new command; only environment-variable NAMES are
  administered. Recognized credential shapes (existing redaction
  patterns) in new free-form input are refused pre-mutation with fixed
  no-echo errors, and free-form READ values are projected with the same
  known-shape redaction — known-shape protection, not universal content
  sanitization. `api_key_env_var` NAMES and structured fields are never
  masked.
- The clear-notes stored-column behavior on real PostgreSQL is the
  shared metadata repository's pre-existing None-skip law (also used by
  the admin form path), outside the 199 allowed paths; the 199-b path
  no longer pre-clears, so the audited OLD value is the REAL prior
  value, and the shared law is documented/asserted as verified
  behavior, flagged for strategic follow-up.
- Every mutation is one audited change in one caller transaction on the
  FOR UPDATE-locked row(s), locked in deterministic route-then-provider
  order; a late audit or transaction failure rolls back the entire
  change (199-a PG proof, unchanged).
- Reviewed plans are staleness-checked after locks: route identity,
  enabled state, route-bound fingerprint, destination existence,
  provider identity, and provider context fingerprint must still
  match; the route argument is bound to the reviewed plan; any mismatch
  is refused with zero writes and zero audits; repeated applies are
  refused stale; zero-diff plans no-op.
- Plan and capabilities files are read at cap+1 before parse; plans are
  written exclusively with mode 0600 and never overwritten; every
  successful dry-run document re-parses with the same strict schema
  under the SAME configured installation ceilings and profile directory
  before the file exists.
- Config validation is not qualification: no credential loading,
  adapter construction, or network call is performed by configuration
  surfaces, and no plan performs credential, model, or SMTP
  qualification.

## Limitations

- Synthetic data only: fictional providers (module `svc-a`..`svc-e`,
  openai_compatible `svc-c`), zero-price pricing rows, planted fictional
  owner/key; no real provider/model contact, no credential, no real
  SMTP, no Redis, no upstream smoke.
- The objective-200-205 rows (including the 205 full executable-only
  transcript and the eleven DoD) remain outstanding; this record makes
  no release/compliance/performance claim.
- No full verification matrix, Docker Compose, browser, or Redis
  coverage was run for 199-b; final-head CI is gated by root.
- JUnit receipts under `/tmp/slaif199/` are disposable execution
  state, not durable evidence. This record is commit-specific evidence
  for the 199 PR head; it does not certify later commits, production
  fitness, security, compliance, or scale.

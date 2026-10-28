# Objective 199-a — provider/route configuration parity (`providers update`, `routes update`) verification

Recorded 2026-10-28 for the 199 PR (base `main` at
`df7fb43cc9898cc784cf83cd10ddad9e946fc2af`). This record describes what the
bounded local runs below actually proved. It is not provider, model,
SMTP, credential, performance, security, compliance, or release
qualification, and it is not the 205 executable-only transcript.

## Scope

Objective 199 administered the remaining provider and route configuration
fields through the installed CLI, replacing operator Python for these
surfaces:

- `providers add` gained `--timeout-seconds` (positive, default 300),
  `--max-retries` (non-negative, 0 valid, default 2), and
  `--actor-admin-id`; deliberate default change: an omitted
  `--enabled/--disabled` at creation now stays DISABLED (explicit
  `--enabled` only activates).
- New `providers update PROVIDER`: `--reason` required; partial update of
  display name, base URL, kind, credential ENV-var name, timeout, retries,
  and notes; the row is locked FOR UPDATE before the complete service input
  is assembled, so omitted fields preserve fresh values and a stored zero
  retry count survives; no `--enabled` flag (enable/disable commands
  own that field); `--notes`/`--clear-notes` mutually exclusive, with the
  explicit clear as a single-column change in the same locked transaction
  covered by the service's one audit record.
- `routes add` gained `--capabilities-file PATH` (a COMPLETE strict
  capabilities document, schema version 1, at most 64 KiB, read at cap+1
  before parse), optional `--reason`, and `--actor-admin-id`; deliberate
  default: a capabilities-file preparation stays DISABLED unless explicit
  `--enabled`, while flag-free creation keeps the historical enabled
  default.
- New `routes update ROUTE_UUID` two-step reviewed plan:
  `--dry-run PATH` (READ-ONLY; typed edit flags; writes a NEW 0600 plan
  file, never overwritten; the built document re-parses with the same
  strict schema before the file is written) XOR `--execute PATH --reason`
  (applies the reviewed file exactly; edit flags refused — mixed mode).
  Partial capability leaves: the three `--codex-*` ints, the three
  `--media-*` ints, repeatable `--chat-capability` /
  `--responses-capability NAME=true|false`, and
  `--completion-service-profile` / `--clear-completion-service`; route
  fields: `--requested-model --match-type --endpoint --provider
  --upstream-model --priority --visible/--hidden --streaming/--no-streaming
  --notes/--clear-notes`. `--capabilities-file` is a COMPLETE replacement
  and cannot combine with partial capability flags (ambiguity refused).
- Plan law: `expected_configuration_fingerprint` = SHA-256 over the 11
  reviewed configuration fields (capabilities/notes/enabled included;
  identity and timestamps excluded). Execute locks the route FOR UPDATE,
  revalidates the fresh fingerprint, enabled state, and provider
  existence/kind, revalidates the merged candidate, then performs ONE
  audited `ModelRouteService.update_model_route` in the caller
  transaction. Stale mismatch = refusal with zero writes and zero audits;
  a repeated apply of an already-applied plan is therefore refused stale.
  A plan whose proposed state already equals the fresh row (zero diff)
  returns the row with ZERO writes and ZERO audits. Transaction or audit
  failure rolls back everything.
- Security: credential references are ENVIRONMENT NAMES only; recognized
  secret shapes in new configuration/plan input are refused with fixed
  no-echo errors (known-shape protection, not universal sanitization);
  files are bounded at cap+1 before parse; plans are written exclusively
  with mode 0600 after strict round-trip.

No schema/DDL, dependency, UI, auth/admission/accounting, provider-adapter,
namespace, or 200+ scope changes. No real provider, client, model, SMTP,
Redis, or network calls; no production database.

## Layers and exact commands

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python` with
`env -u DATABASE_URL -u TEST_DATABASE_URL`; JUnit receipts under
`/tmp/slaif199/` (disposable).

### New unit suites (pure layer, no DB)

```text
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_provider_route_configuration.py -p no:cacheprovider -q
# 90 passed, 0 failed, 0 errors, 0 skipped, exit 0
# (capabilities file schema, capability groups, typed patch/merge,
#  fingerprint, preview, provider partial update, plan document,
#  execute service, merged-candidate validation)

env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_cli_provider_route_configuration.py -p no:cacheprovider -q
# 25 passed, 0 failed, 0 errors, 0 skipped, exit 0
# (actual-Typer providers add/update, routes add, routes update
#  dry-run/execute surface, tri-state enabled defaults, refusals)
```

### New owned-PostgreSQL-16 suite

```text
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/integration/test_cli_provider_route_configuration_postgres.py \
  -p no:cacheprovider -q
# 19 passed, 0 failed, 0 errors, 0 skipped, exit 0 (~21 s)
```

Owned disposable container (label-owner `slaif199a.*.owner`, tmpfs data
directory, loopback-only port binding, `postgres:16`, alembic head), torn
down after the module. World: two fictional `module` providers
(`svc-a` 30 s/0 retries, `svc-b` 180 s, both created DISABLED through the
real CLI and svc-a explicitly enabled) plus one `openai_compatible`
provider; real `pricing add` rows (zero prices); routes carrying Codex
limits (1,050,000/32,768/128,000), media budgets, and
`completion_service` selectors; a planted fictional owner/key, usage
ledger row, and replay reference on the primary route. Demonstrated in PG:

- dry-run is read-only (no row change, no audit) and writes a 0600 plan;
- partial apply preserves every unmentioned field and sibling capability
  group (Codex ceiling raise, media frame change, notes replace/clear);
- repeated apply of an applied plan is refused stale with zero writes and
  zero audits;
- forced LATE audit failure (hook asserting the updated row is visible in
  the SAME transaction before raising) rolls back the whole mutation
  (row byte-equal to before, no orphan audit row), and the same plan
  re-executes successfully afterward;
- a competing committed route change invalidates a previewed plan (stale
  at execute, zero writes);
- a competing provider change preserves the provider's omitted fields
  (fresh locked row wins for preservation; the plan's provider kind
  revalidation still gates the route update);
- a zero-diff plan returns the row with zero writes and zero audits;
- secret-shape, oversize-file, and invalid-document refusals produce
  fixed no-echo errors and no mutation.

### Focused regression batch (new + touched suites)

```text
env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app \
  /tmp/slaif192-coding-venv/bin/python -m pytest \
  tests/unit/test_provider_route_configuration.py \
  tests/unit/test_cli_provider_route_configuration.py \
  tests/unit/test_chat_completion_route_capabilities.py \
  tests/unit/test_responses_route_capabilities.py \
  tests/unit/test_media_input_estimation.py \
  tests/unit/test_provider_config_service.py \
  tests/unit/test_model_route_service.py \
  tests/unit/test_cli_providers.py \
  tests/unit/test_cli_routes.py \
  tests/unit/test_documentation_contract_drift.py \
  tests/unit/test_oap_governance.py \
  tests/unit/test_documentation_inventory.py \
  -p no:cacheprovider -q
# 301 passed, 0 failed, 0 errors, 0 skipped, exit 0
```

Per-file: new pure 90, new CLI 25, chat capability 29, responses
capability 57, media estimation 36, provider config service 8, model route
service 4, CLI providers 7 (help inventory now includes `update`), CLI
routes 8 (same), documentation contract drift 15 (with the two justified
199-a read-only/config-time consumer allowlist entries), OAP governance 9,
documentation inventory 13 (CLI reference names both new subcommands).

### Gates (focused)

```text
/tmp/slaif192-coding-venv/bin/python -m ruff check app/ tests/
# All checks passed

python3 scripts/check_documentation.py
# DOCUMENTATION_CHECK=OK files=126

git diff --check
# clean
```

A full verification matrix was not run for this objective; final-head CI
remains the root-gated gate.

## Privacy, atomicity, and concurrency statements

- No provider credential value is accepted, resolved, printed, stored, or
  logged by any new command; only environment-variable NAMES are
  administered. Recognized secret shapes in new configuration/plan input
  are refused with fixed no-echo errors; this is known-shape protection,
  not universal content sanitization.
- Every mutation is one audited change in one caller transaction on the
  locked row; a late audit or transaction failure rolls back the entire
  change (proven in PG with a forced late-audit failure and same-transaction
  visibility of the updated row before the failure).
- Reviewed plans are staleness-checked after locks: fresh fingerprint,
  enabled state, and provider existence/kind must still match, otherwise
  the execute is refused with zero writes and zero audits; repeated applies
  are refused stale rather than re-mutated.
- Plan and capabilities files are read at cap+1 before parse, plans are
  written exclusively with mode 0600 and never overwritten, and every
  successful dry-run document re-parses with the same strict schema
  before the file exists.

## Documentation impact

- `docs/cli-reference.md`: family lines and a new section for the
  provider/route configuration parity commands (options, defaults,
  partial-vs-replacement, clear/conflict refusals, plan/fingerprint/stale/
  no-op law, review-context note, secret-safe behavior) plus the two new
  subcommands in the checked command inventory.
- `docs/cli-field-administration.md`: new "Implemented in objective 199"
  table; the 199 row removed from the proposed table (200-205 remain
  proposed).
- `docs/completion-services.md`: the operator Python setup snippet is
  replaced with the actual CLI commands (module provider creation,
  capabilities-file route preparation, explicit enablement, zero-priced
  module billing unchanged).
- `docs/media-input-estimation.md`: actual CLI partial budget edit example
  through the reviewed plan workflow.
- This record plus its `docs/verification/README.md` index entry.

## Limitations

- Config validation is not qualification: no credential, model, SMTP,
  provider, or client behavior was tested; no real upstream call was made.
- The 205 full executable-only transcript remains outstanding.
- No full verification matrix, Docker Compose, browser, or Redis coverage
  was run for this objective; final-head CI is gated by root.
- Plan files and JUnit receipts under `/tmp/slaif199/` are disposable
  execution state, not durable evidence.
- This record is commit-specific evidence for the 199 PR head; it does not
  certify later commits, production fitness, security, compliance, or
  scale.

## 199-b ADDENDUM — provider context bindings, audit and privacy guards

Recorded 2026-10-28 for the same 199 PR. This addendum describes the
199-b amendment evidence; the 199-a text above remains unchanged and its
recorded results stand as 199-a results.

### What 199-b changed (allowed paths only)

- `services/provider_route_configuration.py`: provider audit/secret
  guards and the clear-notes delegation fix (no direct pre-clear; the
  audited OLD value is the real prior value); destination-provider
  resolution with deterministic route-then-provider lock order; plan
  binding of `expected_route_id`, `expected_provider_id`, and
  `expected_provider_context_fingerprint` (kind, base URL, credential
  env-var NAME, timeout, retries; display/enabled excluded); canonical
  current/proposed preview blocks from the shared pure normalizer;
  route-bound configuration fingerprint; `validate_route_creation_candidate`
  (R4) with the completion zero-retry rule and the configured profile
  directory; execution-time canonical revalidation against the FRESH
  provider row and the no-op law.
- `schemas/provider_route_configuration.py`: plan schema version with the
  three binding fields (old unmerged plan shapes fail strict parsing);
  canonical preview block validation; `local_coding`/`local_coding_vllm`
  parsed with the existing strict transport-contract parsers (mutual
  exclusion enforced by the vLLM parser); ceilings and `profile_dir`
  threaded through capabilities/patch/plan parsing and rendering.
- `cli/routes.py`, `cli/providers.py`, `cli/provider_route_files.py`:
  nonblank + secret-shape guarded reasons; `routes add --notes` guarded
  before database access; command-level route-argument/plan binding;
  safe read projections with known-shape redaction (env-var NAMES never
  masked); ACTUAL installation ceilings and the configured
  `COMPLETION_SERVICE_PROFILE_DIR` operator directory threaded through
  every file read, preview, and plan write round-trip.
- `services/model_route_service.py`: additive pure
  `normalize_route_configuration` wrapper only; CRUD bodies unchanged.

ProviderConfigService/ModelRouteService CRUD bodies, AuditRepository, the
three extracted pure validators, registry/modules/profiles/adapter, auth,
admission, pricing, FX, accounting, Redis, key, clone, replay, and capture
paths are unchanged. No schema, DDL, dependency, workflow, UI, or
sanitizer-framework changes.

### Evidence (focused, not a full matrix)

All runs: `env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app
/tmp/slaif192-coding-venv/bin/python -m pytest ... -p no:cacheprovider`,
JUnit receipts under `/tmp/slaif199/`.

- 199-b unit suites: 118 passed
  (`tests/unit/test_provider_route_configuration.py`,
  `/tmp/slaif199/b-unit-pure1.xml`) and 31 passed
  (`tests/unit/test_cli_provider_route_configuration.py`,
  `/tmp/slaif199/b-unit-cli1.xml`), including the ANSI/wrapping-independent
  assertion helpers and the known-secret-shape canary refusals.
- Affected/touched suites in one run: 298 passed, 0 failed, 0 skipped
  (`/tmp/slaif199/b-affected1.xml`): `test_chat_completion_route_capabilities`
  (29), `test_responses_route_capabilities` (57), `test_media_input_estimation`
  (36), `test_provider_config_service` (8), `test_model_route_service` (4),
  `test_cli_providers` (7), `test_cli_routes` (8), plus the two 199-b unit
  suites above (118 + 31).
- Real owned PostgreSQL 16 (unique owner label, loopback-bound,
  tmpfs-backed; container removed on teardown, no leftovers): 24 passed,
  0 failed, 0 skipped in one module run
  (`tests/integration/test_cli_provider_route_configuration_postgres.py`,
  `/tmp/slaif199/pg-b.xml`). New 199-b PG proofs: successive real provider
  updates audit the REAL prior notes value; a provider switch binds the
  destination identity and context (context drift refused stale with zero
  writes/audits; fresh review applies exactly once; a plan tampered to
  target a twin route refused on route identity; a deleted destination
  provider refused as missing); a lowered
  `EXTERNAL_TOOL_MAX_PROVIDER_TOOL_CALLS_PER_REQUEST=1` installation
  ceiling denies a cap-2 route policy at dry-run and stores cap-1 after
  review; a configured `COMPLETION_SERVICE_PROFILE_DIR` operator directory
  (0600 file) resolves a custom profile, refuses bundled-only and unknown
  profiles, and executes without resolving or printing the credential
  env-var reference; known credential shapes are refused pre-mutation
  (provider notes/display name, route creation notes) with zero
  writes/audits, and a directly planted LEGACY stored notes value is
  redacted on `providers show`.
- The new configured-profile PG test caught and fixed a 199-b product
  gap: the dry-run plan-write round-trip gate previously revalidated the
  rendered document under default ceilings and the bundled profile
  directory instead of the configured installation state, so a plan
  referencing an operator-directory profile failed at write time after a
  successful preview. `cli/routes.py` now threads the actual ceilings and
  profile directory into `write_route_plan_file`; the rerun above is the
  post-fix result.
- Gates: `ruff check app/ tests/` clean;
  `python3 scripts/check_documentation.py` → `OK files=126`;
  `git diff --check` clean.

### Honest state

- Secret protection is KNOWN-SHAPE protection (recognized credential
  patterns refused on new input and redacted on safe reads), not
  universal content sanitization; `api_key_env_var` NAMES and structured
  fields are never masked.
- The clear-notes stored-column boundary is the shared metadata
  repository's pre-existing None-skip law (also used by the admin form
  path), outside the 199 allowed paths; it is asserted as verified
  behavior and flagged for strategic follow-up.
- Config validation is not qualification: no real provider, client,
  SMTP, Redis, or network contact; no credential, model, or performance
  claim. The 200-205 rows and the 205 full executable-only transcript
  remain outstanding.
- No full verification matrix, browser, or Docker Compose coverage was
  run for 199-b; final-head CI is root-gated and its state is PENDING at
  this publication.
- Plan files and JUnit receipts under `/tmp/slaif199/` are disposable
  execution state, not durable evidence.

## 199-c ADDENDUM — explicit note clearing and module/transport parity

Recorded 2026-10-28 for the same 199 PR. This addendum describes the
199-c amendment evidence; the 199-a text and the 199-b addendum above
remain unchanged, and their recorded results stand as 199-a/199-b
results. Two of those historical claims are CORRECTED here, without
editing the old text:

- **Corrected (199-b no-op caveat).** The 199-b addendum recorded that
  `--clear-notes` delegated `notes=None` through the shared service and
  that "the shared metadata repository's pre-existing None-skip law
  (also used by the admin form path) governs whether the stored column
  actually clears on real PostgreSQL." Root's own earlier inference
  (in the 199-b order) that this None forward therefore cleared the
  column was incorrect: the repository skipped `None`, so the stored
  column was NOT cleared. 199-c completes the operation: an opt-in
  `clear_notes` intent was added to
  `ProviderConfigService.update_provider_config` and
  `ProviderConfigsRepository.update_provider_metadata`. The shared
  service captures the REAL prior values before mutation, the repository
  stores NULL within that same operation, and the ONE audit records real
  old notes -> real new null. Existing shared callers keep the
  pre-existing default (`clear_notes=False`; `notes=None` means
  preserve), so the admin form and all other shared behavior are
  unchanged. Contradictory `notes` + `clear_notes` is refused before
  mutation at both the 199 typed operation and the shared service.
- **Corrected (199-b too-broad creation claim).** Root's actual
  `_add_provider` + real create service probe accepted and STORED a
  recognized synthetic `sk-proj-` canary in `providers add --notes`;
  safe output redacted it, but the storage/input surface was unguarded.
  199-c applies the SAME existing known-shape guard to `providers add`
  `--display-name` / `--base-url` / `--notes` / `--reason` before any
  database access. Known-shape protection, not universal content
  sanitization; safe environment-variable NAMES stay literal.
- **New (C3 parity gap).** `validate_merged_route_candidate` previously
  checked completion contracts only when an explicit
  `completion_service` selector was present. An unregistered
  `module`-kind provider with no selector or legacy binding was accepted
  at configuration time while the existing pure
  `resolve_server_module` rejects it (`unsupported_module`); an implicit
  legacy-bound provider with the wrong model/endpoint/retries also
  passed; and the function did not even receive the complete streaming
  state, although the completion adapter refuses every stream value
  other than `false`. 199-c closes the gap with the EXISTING pure
  resolution and parsers (no adapter construction, credentials, or
  network): every candidate must resolve to a supported server module
  for the provider's actual kind/slug/capabilities; the implicit
  legacy binding gets the SAME configured profile directory, public/
  upstream model identity, endpoint, zero-retry, and no-advertised-
  streaming validation as an explicit selector; reviewed streaming
  declarations (route flag or `chat_completions.chat_streaming`) are
  refused, never silently stripped; compatible/local/vLLM/upstream/
  video contracts keep their own endpoint rules.

### What 199-c changed (allowed paths only)

- `services/provider_route_configuration.py`: `supports_streaming`
  threaded into `validate_merged_route_candidate` (required keyword at
  all three call sites: preview, execute, creation); explicit-selector
  kind check kept before resolution; pure `resolve_server_module`
  wrapped into the fixed safe candidate error; completion contract
  (endpoint, zero retries, no streaming flag/capability, profile
  availability in the SAME configured directory, public/upstream model
  identity) applied to explicit selector AND implicit legacy binding;
  the 199 typed clear delegates `notes=None` + `clear_notes=True`
  through the shared service (no direct pre-clear, no second audit).
- `services/provider_config_service.py` (C1 ONLY):
  `update_provider_config` gained opt-in `clear_notes: bool = False`
  with a pre-mutation contradiction refusal and delegation of the
  explicit intent; all other behavior unchanged.
- `db/repositories/provider_configs.py` (C1 ONLY):
  `update_provider_metadata` gained opt-in `clear_notes: bool = False`;
  `True` stores NULL within the same operation, the default keeps the
  pre-existing None-means-preserve law for every other caller.
- `cli/providers.py`: the SAME known-shape guards as update now apply
  to `providers add` free-form fields before any database access.
- Tests: the four 199 suites (two unit, one CLI unit, one owned-PG);
  `tests/unit/test_provider_config_service.py` gained ONLY the narrow
  explicit-clear/default-None-preservation regressions (fake repository
  mirrors the real clear-intent law). Synthetic fixtures corrected to
  valid supported declarations: unregistered module/no-selector fakes
  became genuinely compatible providers or explicit/profile-mapped
  declarations, and completion fixtures advertise no streaming
  (truly compatible providers keep streaming-free declarations).
  `cli/routes.py` and the schema file needed no changes
  (`supports_streaming` was already a plan/canonical field).

Everything else - ModelRouteService CRUD/normalizer, the routing
repository, the three extracted validators, registry/modules/profiles/
adapters/data, auth/admission/pricing/FX/accounting/Redis/keys/clone/
replay/capture, AuditRepository - is unchanged. No schema, DDL,
dependency, workflow, UI, or sanitizer-framework changes.

### Evidence (focused, not a full matrix)

All runs: `env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app
/tmp/slaif192-coding-venv/bin/python -m pytest ... -p no:cacheprovider`,
JUnit receipts under `/tmp/slaif199/`. The genuine 199-b receipts
(`b-unit-pure1.xml` 118, `b-unit-cli1.xml` 31, `b-affected1.xml` 298,
`pg-b.xml` 24, `b-gov-inv-drift.xml` 37) were NOT rerun for formatting;
the changed code justifies the affected regressions below.

- Affected/touched suites in one run: **330 passed, 0 failed, 0
  skipped** (`/tmp/slaif199/c-affected.xml`):
  `test_chat_completion_route_capabilities` (29),
  `test_responses_route_capabilities` (57),
  `test_media_input_estimation` (36), `test_provider_config_service`
  (10 = 8 + 2 new), `test_model_route_service` (4), `test_cli_providers`
  (7), `test_cli_routes` (8), `test_provider_route_configuration` (135 =
  118 + 17 new), `test_cli_provider_route_configuration` (35 = 31 + 4
  new), `test_oap_governance` (9).
- Real owned PostgreSQL 16 (unique owner label, loopback-bound,
  tmpfs-backed; container removed on teardown, no leftovers): **31
  passed, 0 failed, 0 skipped** in one module run
  (`tests/integration/test_cli_provider_route_configuration_postgres.py`,
  `/tmp/slaif199/c-pg.xml`; the 24 199-b proofs plus 7 new 199-c
  proofs). New 199-c PG proofs: `--clear-notes` stores NULL with ONE
  audit carrying real old text -> real new null while every sibling
  field survives, and a forced LATE provider audit failure rolls back
  BOTH the clear and the sibling change with no orphan audit (updated
  row visible in the SAME transaction before the failure; retry
  succeeds and audits real old -> null); a known credential shape in
  `providers add --notes` is refused with zero rows/audits while
  ordinary text and safe env-variable NAMES store literally; an
  unregistered module-kind provider cannot back a NEW route (refused
  before write/audit); the implicit legacy binding
  (`facial_scoring` -> `facial-scoring-v1`) creates a valid no-selector
  route with truthful no-streaming declarations while a wrong requested
  model and advertised streaming are refused with zero writes/audits;
  an explicit-selector route update advertising streaming is refused
  before any plan file; and the implicit binding resolves through the
  SAME configured `COMPLETION_SERVICE_PROFILE_DIR` operator directory
  (0600 file present: accepted; absent: refused with the fixed safe
  error).
- Unit-layer 199-c proofs (in `c-affected.xml`): explicit clear
  delegates `notes=None` + `clear_notes=True` with the fresh-row
  default preserving `notes`; shared-service explicit clear stores NULL
  with one audit (real old -> real new null) and default callers keep
  None-preservation; unknown module without selector/binding refused;
  legacy binding valid and wrong public model/upstream model/endpoint/
  retries refused; explicit AND implicit streaming flag and
  `chat_streaming` capability refusals; operator-directory implicit
  resolution (present/absent); creation-candidate unknown module,
  valid legacy binding, and streaming refusals; `providers add`
  canary refusals (notes/reason/display name/base URL) with
  not-called creation service and no canary echo, plus ordinary
  text/env-reference acceptance.

Gates: `ruff check app/ tests/` clean;
`python3 scripts/check_documentation.py` -> `OK files=126`;
`git diff --check` clean (recorded at the 199-c implementation commit).

### Honest state

- The clear operation is now REAL (NULL stored, one audit, old -> new
  truth) for the 199 CLI surface; the shared service/repository gained
  only the opt-in typed intent, and every pre-existing caller keeps the
  None-means-preserve default.
- Secret protection remains KNOWN-SHAPE protection (recognized
  credential patterns refused on new input - now including provider
  creation - and redacted on safe reads), not universal content
  sanitization; `api_key_env_var` NAMES and structured fields are never
  masked.
- Configuration validation reuses the EXISTING pure module resolution,
  profile/binding parsers, and loaders: it is not credential, model,
  SMTP, or performance qualification. No real provider, client, SMTP,
  Redis, or network contact. The 200-205 rows and the 205 full
  executable-only transcript remain outstanding.
- No full verification matrix, browser, or Docker Compose coverage was
  run for 199-c; final-head CI is root-gated and its state is PENDING
  at this publication.
- Plan files and JUnit receipts under `/tmp/slaif199/` are disposable
  execution state, not durable evidence.

## 199-d ADDENDUM — creation entry guard and precise test claims

Recorded 2026-10-28 for the same 199 PR. This addendum describes the
199-d amendment evidence; the 199-a text and the 199-b/199-c addenda
above remain unchanged, and their recorded results stand as 199-a/199-b/
199-c results. One historical boundary claim is CORRECTED here, without
editing the old text:

- **Corrected (199-c guard placement).** The 199-c addendum recorded
  that "the SAME known-shape guards as update now apply to `providers
  add` free-form fields before any database access." In fact that guard
  sat only in the Typer `add` command handler: the public CLI correctly
  refused known-shaped credentials, but the private async
  `_add_provider` helper itself was unguarded — a direct helper call
  (as tests do when they replace the Typer surface) still opened the
  database context and invoked the actual core creation service with a
  recognized synthetic credential in `notes`. That is a PRIVATE-helper
  boundary nonconformance, not a demonstrated public CLI/HTTP
  authentication bypass. 199-d completes the 199-c C2 requirement ("put
  the protection where actual async CLI creation cannot bypass it"):
  one small shared check (`_refuse_known_secret_shapes`) now runs at
  BOTH entry points — in the Typer `add` command (the existing public
  refusal is retained even when tests replace the async helper) and at
  the top of the ACTUAL async `_add_provider`, before `cli_db_session`
  is opened. Known-shape protection only; no sanitizer/framework; the
  core service and repository are unchanged.

### What 199-d changed (allowed paths only)

- `cli/providers.py` (the only product file): the new small shared
  `_refuse_known_secret_shapes` check for the SAME four free-form fields
  (`display_name`/`base_url`/`notes`/`reason`), invoked by the Typer
  `add` command (replacing its previous inline loop with the same fixed
  no-echo errors) AND by the actual async `_add_provider` before any
  database access. The public CLI refusal, the optional-creation-reason
  law, environment-variable-reference NAMES, the disabled default, the
  timeout/retry values, and the output behavior are all unchanged.
- `tests/unit/test_cli_provider_route_configuration.py`:
  - Two new 199-d direct-helper regressions: the ACTUAL async
    `_add_provider` is called directly with a recognized canary in each
    field while the DB context is instrumented to fail if reached
    (fixed refusal asserted, no canary echo, no DB open, no service
    call), plus one positive ordinary-text/env-NAME/optional-reason
    case reaching a recording service. No database or backend contact.
  - `test_tampered_plan_forwarded_and_detected_stale` renamed to
    `test_tampered_plan_strictly_parsed_and_forwarded`: its MOCKED
    execute proves strict parsing and forwarding of the tampered
    document exactly as stored — not actual service staleness. The
    comment now says what the mock proves: the plan's expected
    configuration fingerprint binds the SOURCE configuration at review
    time (the assertion shows it is unchanged by the proposed
    priority), and proposed values are revalidated against current
    policy at execute time.
- `tests/unit/test_provider_route_configuration.py`:
  - `test_route_identity_swap_refused`: the unused
    `row`/`_provider_row` assignment was removed (CodeQuality threads);
    the harness fixture, its dependency execution, the tampered
    identity, the expected exception, and the zero-write law are
    unchanged.
  - One new focused actual-service test,
    `test_proposed_value_revalidation_distinct_from_source_staleness`:
    a valid proposed scalar edit (source priority 100, proposed 50)
    applies exactly once while the source is unchanged (no stale
    refusal), and an actual source mutation behind the plan then refuses
    the SAME plan stale with no further writes or audits. Editing a
    valid scalar is not in itself an authentication or staleness breach.
- Docs: this addendum (operator docs unchanged; public behavior
  unchanged).

No core service/repository/route-service/schema changes. No signed
plans, proposal integrity signatures, new digest fields, approval
receipts, migrations, dependencies, workflows, UI, or trust-model
changes. Everything else is unchanged.

### Evidence (focused, not a full matrix)

All runs: `env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app
/tmp/slaif192-coding-venv/bin/python -m pytest ... -p no:cacheprovider`,
JUnit receipts under `/tmp/slaif199/`. The 199-c receipts
(`c-affected.xml` 330, `c-pg.xml` 31, `c-gov-inv-drift.xml` 37) were
NOT rerun and remain 199-c evidence. NO owned-PostgreSQL run was
performed for 199-d: the guard executes before any database access and
is proven at the unit layer, and the 199-c creation no-write/no-audit
PG proofs remain the PostgreSQL proof for creation. No 199-d PG,
full-matrix, browser, or Docker Compose evidence is claimed.

- The two affected unit suites in one run: **173 passed, 0 failed, 0
  skipped** (`/tmp/slaif199/d-affected.xml`):
  `test_provider_route_configuration` (136 = 135 + 1 new) and
  `test_cli_provider_route_configuration` (37 = 35 + 2 new).
- `test_cli_providers` (help/signature suite): **7 passed, 0 failed, 0
  skipped** (`/tmp/slaif199/d-cli-providers.xml`).
- Governance/inventory/drift in one run after the docs append: **37
  passed, 0 failed, 0 skipped** (`/tmp/slaif199/d-gov.xml`):
  `test_oap_governance` (9), `test_documentation_inventory` (13),
  `test_documentation_contract_drift` (15). These 37 are disjoint from
  the 173 above (the 199-c 330-run overlap note with its own
  governance 9 does not apply to 199-d, which did not rerun those
  affected suites).

Gates: `ruff check app/ tests/` clean;
`python3 scripts/check_documentation.py` -> `OK files=126`;
`git diff --check` clean (recorded at the 199-d implementation commit).

### Honest state

- The creation guard now covers the public Typer command AND the actual
  async helper entry point; protection remains KNOWN-SHAPE protection
  (recognized credential patterns refused on new input, redacted on
  safe reads), not universal content sanitization.
- No public behavior change: public CLI refusals, output, defaults, and
  laws are unchanged; only the private-helper boundary gained the
  shared check.
- Final-head CI for the new 199-d SELF is PENDING at this publication;
  final-head checks and strategic review remain root gates. No 200-205
  rows or 205 full executable-only transcript claim follows.
- Plan files and JUnit receipts under `/tmp/slaif199/` are disposable
  execution state, not durable evidence.

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

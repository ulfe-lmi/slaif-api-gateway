# OAP Work Order — 013-a

## Objective

Persist the objective-012 external-tool contract safely in existing key,
template-snapshot, and route-capability JSON; add exact audited admin/CLI
create/update/detail controls; propagate immutable template policy; validate
route/import metadata; and keep every runtime provider-hosted tool path denied
until objectives 014–016 implement the fence, hold, and selected provider
contracts.

## Authoritative start state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Starting remote `main`:
  `7ced94da57a338bd14bc74e25d40fd78f166f879`, merge commit for PR #237.
- Objective 012 is merged with exact contract module, two quota modes, schemas,
  ceilings, safe destination IDs, position-aware taxonomy, and pure admission
  decisions. Runtime remains deny-only.
- Current Alembic head is `0014_codex_context_accounting_compaction`.
- Existing `gateway_keys.metadata` and immutable key-template `template_snapshot`
  JSON can carry the new exact policy; `model_routes.capabilities` can carry the
  exact route contract. No new column/table/migration is required.
- Existing keys and template revisions lack this metadata and therefore mean
  exact `strict_bounded` denial.
- The only unrelated open PR is Dependabot #224. No objective-013 PR/branch
  existed at activation.
- PR mode: `CREATE_NEW_PR`.
- Required branch: `oap/013-external-tool-key-template-admin-controls`.
- Required PR title:
  `[OAP 013] Add external-tool key and admin controls`.
- Preserve `.local-provider-catalog/`, linked worktrees, secrets, user config,
  and unrelated artifacts.

Reconcile GitHub/governance/current code before editing and start from current
remote `main`.

## Current/future boundary

This objective makes policy durable and operator-visible. It does **not** make
provider-hosted tools executable. Every existing Chat/Responses hosted-tool,
MCP, connector, URL-authority, background, and unknown-authority runtime denial
must remain unchanged. UI/CLI must label external mode as configured policy
awaiting the later fence/hold/provider qualification; never claim it is active.

## Operator ceilings

Add four validated installation settings with objective-012 defaults and hard
absolute maxima:

```text
EXTERNAL_TOOL_MAX_DISTINCT_CAPABILITIES=16
EXTERNAL_TOOL_MAX_APPROVED_DESTINATIONS=8
EXTERNAL_TOOL_MAX_PROVIDER_TOOL_DECLARATIONS_PER_REQUEST=16
EXTERNAL_TOOL_MAX_PROVIDER_TOOL_CALLS_PER_REQUEST=16
```

Values may only narrow the contract maxima, use positive integers, and fail
startup validation otherwise. Add a pure helper returning
`ExternalToolOperatorCeilings`. No runtime forwarding uses them yet.

## Key persistence and service invariants

Use `gateway_keys.metadata.external_tool_policy` only. Add the exact canonical
v1 object produced by `parse_key_external_tool_policy()`; never store malformed
input, raw URLs, credentials, arbitrary labels, content, or unreviewed wire
values.

- Missing policy on old keys authenticates/displays as exact strict default.
- New ordinary keys default to strict; storing the explicit strict object is
  preferred for new keys.
- `external_tool_fenced` requires standard key purpose, positive finite
  request/token/EUR limits, exact capabilities/destinations/call cap, and
  literal overrun acknowledgement.
- Trusted-calibration keys must remain strict in this metadata. Their existing
  observation-only behavior is not standard-key permission.
- Any limit update that would make a fenced key unbounded/non-positive must
  reject before mutation/audit.
- Rotation preserves the canonical policy exactly and does not widen it.
- General provider/model/endpoint/rate/live-burn/Responses-policy updates must
  preserve the external policy.

Add `external_tool_policy` to `CreateGatewayKeyInput`, authenticated-key safe
facts, key dashboard DTOs, CLI safe output, and creation results. Add a dedicated
`UpdateGatewayKeyExternalToolPolicyInput` and KeyService method. Update requires
an authenticated admin/operator path, non-empty audit reason, explicit
confirmation for fenced mode, validation before repository mutation, and one
safe audit event containing canonical IDs/mode/caps/acknowledgement only.

Bearer API keys never mutate their own policy. No allow-all external-tool
switch, wildcard capability, arbitrary URL, inline auth, or implicit permission
from endpoint/model/provider allowlists is permitted.

## Route policy persistence and validation

Use only `model_routes.capabilities.external_tools` with the exact objective-012
route schema. Extend model-route create/update and route-import validation so:

- missing metadata means strict/no external support;
- present strict or external metadata canonicalizes exactly under installation
  ceilings;
- invalid/partial/extra/coerced/over-ceiling/destination-mismatched metadata
  rejects before route mutation/import execution/audit;
- route audit values and list/detail/CLI summaries expose only safe canonical
  capability/destination IDs, caps, and evidence booleans.

Keep the existing confirmed/audited capabilities JSON workflow; a dedicated
route toggle is not required. External route metadata remains future support
metadata, not active forwarding.

## Admin and CLI key controls

### Create/update/detail

Add one explicit external-tool policy section to ordinary key creation and key
detail/update:

- mode: strict/default or fenced future opt-in;
- exact reviewed capability checkboxes/choices, never allow-all;
- opaque reviewed destination IDs with canonical prefix validation;
- positive per-request provider call cap;
- explicit single-request-overrun acknowledgement;
- second confirmation plus required audit reason for fenced mode;
- prominent promise: one admitted future external-tool request may overrun,
  concurrent requests will be fenced, following exhausted requests blocked,
  and missing/ambiguous final cost held;
- prominent current status: runtime still denies until objectives 014–016.

Invalid/stale/unchecked input must reject before key mutation and preserve form
state safely. Strict mode must render with empty/zero/false policy. Existing
ordinary and Codex-pilot creation remains unchanged except explicit strict
external policy.

Add matching CLI create options and a dedicated audited update command. Secret
values must not be accepted as arguments or printed. JSON/human output contains
only the canonical safe policy summary. Require `--confirm` and `--reason` for
fenced mode; strict reset still requires an audit reason.

### Route/template/admin displays

Key, route, and template list/detail pages show safe mode/cap/destination/
acknowledgement summaries and the current deny-only warning. Creation results
show the stored safe policy. No raw metadata dump is added beyond existing
audited route-capabilities views.

## Template policy and immutable provenance

Add canonical `external_tool_policy` to new immutable template snapshots.

- Missing historical snapshot policy means strict.
- Calibration observations never auto-enable capabilities or destinations.
- Creating/revising a template with fenced policy requires exact explicit
  operator input, confirmation, audit reason, positive finite template limits,
  and canonical policy validation.
- Creating one key from a template copies the exact policy and provenance
  through normal `KeyService`; it never reinterprets observed hosted tools.
- Template edits/revisions never mutate existing keys or older revisions.
- Template list/detail/CLI show a safe summary and deny-only-current warning.

Extend the existing CLI/admin create-from-calibration workflow rather than
inventing an unaudited shortcut.

## Bulk/import behavior

Direct bulk key import remains strict-only in objective 013. Reject any
external-tool mode/capability/destination/acknowledgement fields as unsupported
before preview/execution mutation; do not silently drop them. Bulk-created keys
receive strict/default policy. Template-created single keys may carry explicit
fenced policy as above. Route import may carry exact route support metadata
because it already uses reviewed capabilities JSON.

## Runtime non-enablement proof

Add static and behavior tests proving:

- Chat/Responses runtime request policy does not consume stored external policy;
- current hosted/MCP/provider-authority requests remain rejected before Redis,
  route/pricing/quota/provider side effects;
- no fence/hold/accounting/provider execution code is added;
- policy storage alone cannot authorize a request.

Objectives 014–016 will activate intersections only after the required durable
fence/hold/provider contracts exist.

## Documentation

Synchronize configuration, schema, key/template, security, accounting,
compatibility, and operator docs. State exact storage locations, old-key strict
default, settings ceilings, audit/confirmation behavior, template/bulk rules,
current deny-only runtime, and later-objective dependencies. Preserve honest
overrun/hold wording and no-content/provider-secret guarantees.

## Allowed paths

Implementation may change only:

```text
.env.example
AGENTS.md
app/slaif_gateway/api/admin.py
app/slaif_gateway/cli/keys.py
app/slaif_gateway/cli/routes.py
app/slaif_gateway/cli/templates.py
app/slaif_gateway/config.py
app/slaif_gateway/schemas/admin_keys.py
app/slaif_gateway/schemas/auth.py
app/slaif_gateway/schemas/keys.py
app/slaif_gateway/services/admin_key_dashboard.py
app/slaif_gateway/services/auth_service.py
app/slaif_gateway/services/external_tool_policy_contract.py
app/slaif_gateway/services/key_import.py
app/slaif_gateway/services/key_service.py
app/slaif_gateway/services/key_template_service.py
app/slaif_gateway/services/model_route_service.py
app/slaif_gateway/services/route_import.py
app/slaif_gateway/web/templates/keys/_policy_selector.html
app/slaif_gateway/web/templates/keys/bulk_import.html
app/slaif_gateway/web/templates/keys/bulk_import_preview.html
app/slaif_gateway/web/templates/keys/create.html
app/slaif_gateway/web/templates/keys/create_result.html
app/slaif_gateway/web/templates/keys/detail.html
app/slaif_gateway/web/templates/keys/email_delivery_result.html
app/slaif_gateway/web/templates/routes/create.html
app/slaif_gateway/web/templates/routes/detail.html
app/slaif_gateway/web/templates/routes/edit.html
app/slaif_gateway/web/templates/routes/import_preview.html
app/slaif_gateway/web/templates/routes/list.html
app/slaif_gateway/web/templates/templates/detail.html
app/slaif_gateway/web/templates/templates/list.html
docs/accounting.md
docs/compatibility-matrix.md
docs/configuration.md
docs/database-schema.md
docs/key-templates.md
docs/openai-compatibility.md
docs/product-scope.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
oap/active
oap/orders/013-a-external-tool-key-template-admin-controls.md
tests/browser/test_admin_dashboard_smoke.py
tests/integration/test_external_tool_policy_postgres.py
tests/unit/key_management_fakes.py
tests/unit/test_admin_bulk_key_import_routes.py
tests/unit/test_admin_key_create_routes.py
tests/unit/test_admin_key_create_templates.py
tests/unit/test_admin_key_actions_routes.py
tests/unit/test_admin_keys_dashboard_service.py
tests/unit/test_admin_keys_routes.py
tests/unit/test_admin_keys_templates_safety.py
tests/unit/test_auth_service.py
tests/unit/test_cli_keys_create.py
tests/unit/test_cli_keys_safety.py
tests/unit/test_cli_routes.py
tests/unit/test_cli_templates.py
tests/unit/test_documentation_contract_drift.py
tests/unit/test_external_tool_policy_contract.py
tests/unit/test_key_import_service.py
tests/unit/test_key_management_service_limits.py
tests/unit/test_key_management_service_rotation.py
tests/unit/test_key_service_create.py
tests/unit/test_key_service_policy_update.py
tests/unit/test_key_service_safety.py
tests/unit/test_key_template_service.py
tests/unit/test_model_route_service.py
tests/unit/test_route_import_service.py
```

The final report-only commit adds only:

```text
oap/reports/013-a-external-tool-key-template-admin-controls.md
```

If another exact implementation/test path is required, do not edit it; report
`BLOCKED` for a narrow 013 continuation. Do not change DB models/migrations,
runtime Chat/Responses request/forwarding/quota/accounting/provider code,
dependencies, CI, Compose, README, fixtures, or prior OAP history.

## Focused verification and test economy

Run only directly affected unit files above, scoped lint/format/compile/docs/
path checks, one focused admin browser smoke only if local prerequisites already
work, and the new dedicated PostgreSQL policy round-trip/audit/template/
old-key-default integration file using a safe `TEST_DATABASE_URL`.

Because this objective adds DB-backed metadata behavior, the dedicated
PostgreSQL integration test must actually pass, not skip. Obtain a safe existing
test DB or one explicit disposable test DB through documented commands and
clean it. Do not additionally run full local unit, integration, E2E, browser
matrix, Docker/Compose, HPC, manual Codex, or provider suites. GitHub CI owns
broad routine coverage. Never call a provider, gateway, external tool/MCP,
production, or staging system.

## Acceptance criteria

1. Existing/missing and new default policies are strict; fenced policy is exact,
   standard-key-only, finite-limit, explicitly acknowledged/confirmed, and
   canonical in metadata/auth/dashboard/CLI output.
2. Admin and CLI create/update/detail paths validate before mutation, require
   reason/confirmation, audit safe old/new values, preserve unrelated metadata,
   and give bearers no self-service widening path.
3. Limit changes and trusted-calibration creation cannot violate policy
   invariants; rotation preserves policy exactly.
4. Route create/update/import canonicalizes exact external support metadata and
   rejects invalid values before mutation/audit; displays remain safe and
   explicitly future/deny-only.
5. New immutable template snapshots can carry only explicit confirmed policy;
   historical missing is strict, calibration never auto-enables, one-key
   creation copies exact policy/provenance, old revisions/keys never widen.
6. Direct bulk import rejects external opt-in fields and stays strict-only.
7. Stored policies do not enable runtime forwarding; all current hosted/MCP/
   external requests remain denied with no provider/quota side effect.
8. Focused unit/PostgreSQL/browser-if-available/docs/privacy/path evidence and
   every required report-head GitHub check pass; broad local suites and external
   calls do not run.
9. One new objective-013 PR only; coding agent never merges/enables auto-merge;
   immutable report topology satisfies `SELF`.

## GitHub and report contract

Commit the unchanged 013-a order and `oap/active=013-a`, create the required
branch/PR, inspect checks, and repair only in-scope failures. Never merge or
enable auto-merge.

Publish exactly one immutable report at
`oap/reports/013-a-external-tool-key-template-admin-controls.md` with literal
implementation SHA, `Report publication commit: SELF`, exact key/route/template/
bulk matrices, audit/CSRF/confirmation/old-key/rotation/limit/runtime-denial
evidence, actual PostgreSQL result and cleanup, focused tests/GitHub checks,
broad suites not run, no-provider/no-runtime-enablement evidence, docs impact,
and no-merge/no-auto-merge. The final commit changes only that report and has
the implementation head as first parent. Verify remote report head and all
required checks, then signal exact `OK`.


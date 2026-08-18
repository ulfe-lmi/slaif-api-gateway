# OAP Coding-Agent Report — 013-a

## Work order

- Identifier: 013-a
- Work-order file: `oap/orders/013-a-external-tool-key-template-admin-controls.md`
- Numeric objective: 013
- PR mode: CREATED_NEW_PR

## Status

COMPLETE

## Executive summary

Objective 013 now persists and exposes the objective-012 external-tool policy on the bounded operator surfaces without enabling runtime provider-hosted tool execution. Fenced policies are stored canonically in existing key JSON, immutable template snapshots, and route capabilities. Missing key/template/route policy remains exact strict default; ordinary strict key creation remains implicit in key JSON for compatibility while its safe creation result and audit record are canonical strict. Admin and CLI create/update/detail paths require the intended reason, acknowledgement, confirmation, finite limits, reviewed capability IDs, and opaque destination IDs. Bulk key import stays strict-only. Runtime Chat/Responses/provider/quota code was not changed and remains deny-only pending objectives 014–016.

One initial GitHub PostgreSQL check failed because a pre-existing broad integration assertion expected the complete ordinary-key metadata dictionary not to have a new explicit strict member. The in-scope repair retained implicit strict semantics for ordinary keys while continuing to persist fenced policy explicitly. The refreshed implementation head passed all ten GitHub checks.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 238
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/238
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/013-external-tool-key-template-admin-controls`
- Starting remote SHA: `7ced94da57a338bd14bc74e25d40fd78f166f879`
- Implementation head SHA: `c537760f8f26409ca1a4db8d9a443bed98271fcb`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `d66542d069fd9db8091248bfc4f46ca15b88036d`, `c537760f8f26409ca1a4db8d9a443bed98271fcb`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Auto-merge enabled: NO
- Merge performed: NO

## Changes made

- Added four startup-validated positive installation ceilings, bounded by the immutable objective-012 absolute maxima, and a pure ceiling builder.
- Added exact JSON serialization for canonical key and route policy objects.
- Added canonical external-tool policy to key creation inputs/results, authenticated safe facts, dashboard DTOs, management results, audited policy replacement, limit validation, and rotation preservation.
- Added CSRF-protected admin create/update/detail controls and safe creation/email result rendering with the future overrun/hold promise and current deny-only warning.
- Added CLI key creation flags and `keys external-tools show/update` commands with safe human/JSON output; fenced mode requires acknowledgement, `--confirm`, finite key limits, and audit reason through service validation.
- Added exact route create/update/import canonicalization under installation ceilings, plus safe admin/CLI summaries. Existing audited capabilities JSON remains the route mutation workflow.
- Added immutable template snapshot policy, historical missing-policy strict fallback, fenced confirmation/finite-limit validation, exact one-key policy/provenance copying, and safe admin/CLI summaries.
- Kept direct bulk key import strict-only and rejected external-tool fields before preview/execution mutation.
- Updated focused unit, PostgreSQL, browser, documentation-drift, privacy, and path evidence.
- Updated configuration, schema, security, accounting, compatibility, forwarding, template, product-scope, Responses, and durable governance documentation.

## Files changed

- Configuration/governance: `.env.example`, `AGENTS.md`, `app/slaif_gateway/config.py`, unchanged strategic `oap/active`, and unchanged activated order.
- Schemas/services: key/auth/admin schemas and the external policy, key, auth, dashboard, import, template, route, and route-import services named by the order.
- Operator surfaces: bounded admin API, key/route/template CLI modules, and the allowed key/route/template Jinja templates.
- Documentation: `docs/accounting.md`, `docs/compatibility-matrix.md`, `docs/configuration.md`, `docs/database-schema.md`, `docs/key-templates.md`, `docs/openai-compatibility.md`, `docs/product-scope.md`, `docs/provider-forwarding-contract.md`, `docs/responses-compatibility.md`, and `docs/security-model.md`.
- Tests: only the unit/browser paths allowed by the order plus new `tests/integration/test_external_tool_policy_postgres.py`.
- No model, migration, runtime Chat/Responses request/forwarding/quota/accounting/provider, dependency, CI, Compose, README, fixture, prior order, or prior report path changed.

## Key policy matrix

| Case | Stored key JSON | Safe facts/display/result | Mutation requirements | Outcome |
|---|---|---|---|---|
| Historical missing policy | Missing | Canonical `strict_bounded`, empty capabilities/destinations, zero calls, acknowledgement false | None | Strict denial |
| New ordinary strict key | Missing/implicit strict for broad compatibility | Canonical strict in creation result and audit | Normal key validation | Strict denial |
| New fenced standard key | Exact canonical v1 object | Same canonical safe IDs/cap/acknowledgement | Positive finite request/token/EUR limits, non-empty reason, acknowledgement, second confirmation | Persisted future policy; runtime denied |
| Trusted-calibration key | Missing/implicit strict | Canonical strict | Existing calibration confirmation remains; fenced input rejected | Observation only; no external permission |
| Dedicated policy update | Exact canonical replacement | Safe old/new values and management result | Authenticated admin/operator path, CSRF on admin, reason; fenced additionally confirmed | One audit event after validation |
| Strict reset | Exact canonical strict replacement | Canonical strict | Audit reason required; no fenced confirmation | Strict denial |
| Limit update on fenced key | Existing fenced object preserved | Existing safe policy | Every request/token/EUR limit remains positive and finite | Invalid clearing/non-positive update rejects before mutation/audit |
| Rotation | Exact policy semantics preserved; fenced remains explicit | Canonical safe policy | Fenced rotation cannot discard finite limits | No widening |
| Other policy/rate/provider/Responses updates | External member preserved by metadata-copying paths | Unchanged safe policy | Existing independent validation | No widening |

Bearer keys received no policy mutation route. There is no wildcard, allow-all external switch, arbitrary URL, inline authorization, credential, or implicit permission from model/provider/endpoint allowlists.

## Route policy matrix

| Input | Canonicalization | Mutation/audit | Display/runtime result |
|---|---|---|---|
| Missing `capabilities.external_tools` | Interpreted as exact strict route policy | Existing capabilities remain otherwise unchanged | Safe strict summary; runtime denied |
| Present exact strict object | Canonical sorted exact v1 object | Stored/audited only after validation | Safe strict summary; runtime denied |
| Present exact supported object | Canonical reviewed capability/destination IDs, positive bounded calls, all evidence booleans true | Stored/audited after installation-ceiling validation | Future-support summary only; runtime denied |
| Partial/extra/coerced/duplicate/unknown/URL-like/secret-looking/over-ceiling/mismatched destination | Invalid | Rejected before create/update/import execution and audit | No permission |
| Route import | Same parser and installation ceilings as direct service | Preview canonicalizes; invalid rows block execution | Safe preview/detail/list/CLI summaries |

## Template policy matrix

| Case | Snapshot/result | Requirements | Outcome |
|---|---|---|---|
| New strict template | Immutable snapshot contains canonical strict object | Existing reviewed calibration proposal, confirmation, reason | Strict future keys |
| New fenced template | Immutable snapshot contains exact fenced object | Explicit capabilities/destinations/cap/acknowledgement, second confirmation, audit reason, positive finite proposed request/token/EUR limits | Future policy only; runtime denied |
| Historical missing snapshot member | Parsed as canonical strict | None | Strict denial |
| Malformed/over-ceiling snapshot | Invalid | Key creation/display does not reinterpret it | Key creation blocked / display marks invalid |
| Calibration observations | Remain review-required warnings | Never copied into external allowlists automatically | No auto-enablement |
| One key from revision | Copies exact policy plus template/revision provenance through `KeyService` | Existing single-key confirmation/reason and all key invariants | No mutation of template, older revisions, or existing keys |

## Bulk/import matrix

| Surface | External fields | Result |
|---|---|---|
| Direct bulk key import top level | Any external-tool mode/capability/destination/acknowledgement field | Rejected before preview/execution mutation |
| Direct bulk key import metadata | `external_tool_policy` or external-tool-prefixed member | Rejected before preview/execution mutation |
| Direct bulk-created key | No external fields | Exact implicit strict default and canonical safe strict result |
| Template-created single key | Exact immutable template policy | Strict or explicitly confirmed fenced policy copied exactly |
| Route import capabilities JSON | Exact `external_tools` object | Canonicalized under installation ceilings; invalid input blocks execution |

## Acceptance-criteria evidence

### Criterion 1 — strict defaults and exact fenced policy

- Result: PASSED.
- Evidence: pure parser/settings unit coverage; key creation/auth/dashboard/CLI tests; PostgreSQL old-key default and fenced JSON round trip; narrowed-ceiling dashboard coverage.

### Criterion 2 — admin/CLI validation, confirmation, audit, and preservation

- Result: PASSED.
- Evidence: CSRF-protected dedicated admin POST, CLI create/update argument tests, service pre-mutation rejection tests, one-event safe audit assertions, and unrelated metadata preservation assertions.

### Criterion 3 — limits, calibration, and rotation

- Result: PASSED.
- Evidence: fenced limit-clear/non-positive rejection tests, trusted-calibration fenced rejection, exact rotation preservation, and preserve-limits enforcement.

### Criterion 4 — route create/update/import

- Result: PASSED.
- Evidence: service/import canonical round-trip tests, malformed/raw-authority rejection before mutation/audit, safe admin/CLI rendering, and PostgreSQL route JSON assertion.

### Criterion 5 — immutable templates and provenance

- Result: PASSED.
- Evidence: strict historical fallback, fenced confirmation/finite-limit tests, observation non-enablement, snapshot persistence, exact key copy/provenance, and PostgreSQL template snapshot assertion.

### Criterion 6 — strict-only direct bulk import

- Result: PASSED.
- Evidence: top-level and nested external-field rejection tests plus strict key creation input assertion.

### Criterion 7 — no runtime enablement

- Result: PASSED for objective-013 scope.
- Evidence: external contract imports are statically restricted to settings/operator/policy surfaces; migrations contain no external policy hook; runtime Chat/Responses request, Redis, route-selection, pricing, quota, accounting, forwarding, and provider modules were not changed. Existing hosted/MCP/external-authority denial code remains unchanged. The pure stored-policy contract is not called by runtime forwarding. No provider or external tool was called.

### Criterion 8 — focused and GitHub verification

- Result: PASSED.
- Evidence: 418 focused unit tests, 1 dedicated PostgreSQL test, 2 focused browser tests, scoped lint/format/compile checks, and all ten implementation-head GitHub checks passed.

### Criterion 9 — one PR, SELF topology, no merge

- Result: PASSED at report drafting; final SELF topology is established by the commit containing this report.
- Evidence: only PR #238 was created for objective 013; auto-merge is null/off; coding agent did not merge; report records literal implementation parent and `SELF`.

## Audit, CSRF, privacy, and runtime-denial evidence

- Dedicated key policy replacement requires a non-empty audit reason for strict reset and fenced update; fenced also requires exact acknowledgement and second confirmation.
- Admin mutation uses the existing authenticated session plus CSRF action context and records actor ID/reason.
- Audit values contain canonical mode, capability IDs, destination IDs, call cap, acknowledgement, and ordinary safe key identifiers only; no URL, header, credential, secret, prompt, completion, arguments, results, or provider payload is recorded.
- Failed validation occurs before repository mutation/audit in key, route, template, and import service tests.
- Auth converts missing or malformed key policy to exact strict facts.
- Rotation and ordinary metadata update paths preserve external policy; fenced keys cannot rotate without finite limits.
- Static drift coverage rejects imports of the contract module from runtime modules and rejects migration references.

## Local verification

- Focused 23-file unit command from the work order: PASSED — 418 tests collected and passed; one existing Starlette/httpx deprecation warning.
- `.venv/bin/python -m pytest -q tests/integration/test_external_tool_policy_postgres.py`: PASSED — 1 test, actual migrated PostgreSQL 16 execution, no skip.
- `.venv/bin/python -m pytest -q tests/browser/test_admin_dashboard_smoke.py`: PASSED — 2 Playwright Chromium tests, no skip.
- Scoped Ruff format/check/format-check over 33 changed Python files: PASSED.
- `.venv/bin/python -m compileall -q` over the same 33 changed Python files: PASSED.
- Focused repair subset after the initial CI failure: PASSED; the complete 418-test focused unit set and dedicated PostgreSQL test were rerun and passed.
- PostgreSQL: local server 16.14; explicit databases `slaif_oap013_test`, `slaif_oap013_browser_test`, `slaif_oap013_final_test`, and `slaif_oap013_fix_test` were created only for focused runs and dropped by shell traps. Final catalog probe found zero `slaif_oap013%` databases.
- `DATABASE_URL` was unset for disposable setup; only safe test-named `TEST_DATABASE_URL` values were used.
- Full local unit/integration/E2E/browser matrix, Docker/Compose suite, HPC harness, manual Codex verifier, upstream/provider tests, production, and staging: NOT RUN — prohibited by the active order's test-economy boundary. GitHub CI owned broad routine coverage.

## GitHub CI / required checks

Check state observed for implementation head `c537760f8f26409ca1a4db8d9a443bed98271fcb`:

| Check | State | Duration shown by GitHub |
|---|---|---:|
| Analyze (javascript-typescript) | SUCCESS | 46s |
| Analyze (python) | SUCCESS | 1m47s |
| Analyze Python | SUCCESS | 1m0s |
| CodeQL | SUCCESS | 2s |
| Docker Compose smoke | SUCCESS | 1m0s |
| Documentation hygiene | SUCCESS | 6s |
| OpenAI-compatible E2E tests | SUCCESS | 1m27s |
| Playwright browser smoke | SUCCESS | 1m32s |
| PostgreSQL integration tests | SUCCESS | 2m4s |
| Unit, lint, and migration head | SUCCESS | 1m59s |

- Initial implementation head `d66542d069fd9db8091248bfc4f46ca15b88036d`: PostgreSQL integration tests FAILED 1/133 (`test_admin_key_create_form_postgres` exact metadata assertion); the other checks passed. This was repaired in scope and is not represented as green.
- All required checks green for the final implementation head at report drafting: yes.
- Report-only commit may trigger fresh checks: strategic model must verify the `SELF` commit without rewriting this report.

## Local setup / dependencies

- Packages/tools/services installed or configured: none. Existing PostgreSQL 16 and installed Playwright Chromium were used.
- `sudo`-level setup performed: none.
- Durable setup changes committed/documented: four external-tool ceiling settings and `.env.example`/operator documentation only.

## Documentation

Documentation updated: `AGENTS.md`, `docs/accounting.md`, `docs/compatibility-matrix.md`, `docs/configuration.md`, `docs/database-schema.md`, `docs/key-templates.md`, `docs/openai-compatibility.md`, `docs/product-scope.md`, `docs/provider-forwarding-contract.md`, `docs/responses-compatibility.md`, and `docs/security-model.md`.

The documentation states exact JSON locations, implicit/missing strict behavior, installation ceilings, audit/confirmation rules, immutable template behavior, strict-only bulk import, the honest one-request-overrun/final-cost-hold promise, no-content/no-provider-secret guarantees, and the current deny-only dependency on objectives 014–016. No migration or runtime support claim is made.

## Safety and scope confirmations

- Unrelated files changed: no.
- `.local-provider-catalog/` and linked worktrees modified/cleaned/committed: no.
- Production secrets accessed: no.
- Production systems accessed: no.
- Staging systems accessed: no.
- Real upstream/provider/external-tool/MCP calls: no.
- Real email sent: no.
- Schema/model/migration changes: no.
- Required tests skipped/not run: no. The dedicated PostgreSQL and browser evidence ran without skip. Broad local suites were intentionally not run under the order's explicit test-economy rule.
- Scope deviation: no. The stale broad integration assertion was satisfied through an allowed service/unit compatibility repair; the out-of-scope integration file was not edited.
- Extra PR created for same numeric objective: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order and `oap/active` edited by coding agent: NO. Their published SHA-256 values remained `5155147bc97dcf5b5734541936bf4bd562f90a63cfee01a95a7735d08cbc0bb7` and `e96d03c20505ff74b87acb2beaf745fc6b40df9338b0d57925ec33724ebbd989` respectively.
- Report-publication commit changes only this report file: yes (to be verified before push and again from remote).
- Report publication first parent: `c537760f8f26409ca1a4db8d9a443bed98271fcb`.

## Known limitations / blockers

- Provider-hosted tools, remote MCP, connectors, URL authority, background/unknown external authority, exclusive fencing, post-exhaustion blocking, missing/ambiguous-final-cost holds, provider execution contracts, and reconciliation remain unimplemented by design. Objectives 014–016/017 own those runtime boundaries.
- A configured fenced policy is policy/provenance only and cannot authorize a request in objective 013.
- No RC2 release, production, security-certification, compliance, invoice-accuracy, or full Codex compatibility claim follows from this objective.

## Recommended strategic follow-up

Independently verify the SELF report commit topology and report-head checks, review PR #238 against the active order, and decide acceptance/continuation. Do not infer runtime external-tool readiness from stored policy.

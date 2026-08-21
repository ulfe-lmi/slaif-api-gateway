# OAP Work Order — 019-b

PR mode: `AMEND_EXISTING_PR`

## Objective and reason

Amend only Objective 019 PR #245. The 019-a implementation establishes bounded
discovery and setup, but the initial order omitted the repository-tested literal
`PR mode: CREATE_NEW_PR`, leaving the unit job red. The agent correctly did not
edit the immutable order. Product review also found implicit zero-price
selection, no public-model-ID override in operator surfaces, no CLI setup
execution, and missing direct admin/rollback evidence. Close those exact gaps.

Start implementation now after one focused read of the new discovery/setup,
admin form, CLI, and tests. No broad reconnaissance or broad local suite.

## Verified continuation state

- Sole PR #245 on `oap/019-openai-compatible-backend-wizard-discovery`, base
  `main`, current report head `a25d37db4c698c8bd771a0e4fdf2260b6ddd7d93`.
- 019-a implementation head:
  `11d8259438c7747167e90a1ec44c22ff25b1cdb1`.
- All checks except `Unit, lint, and migration head` are green or finishing;
  the unit failure is only the missing literal in immutable 019-a.
- Reuse this branch/PR. Do not edit 019-a order/report, create another PR,
  merge, or enable auto-merge.

## Required closures

1. **Explicit zero-pricing choice**
   - Add `confirm_local_zero` to the setup request/validation.
   - `local_zero` requires that exact acknowledgement; missing acknowledgement
     rejects before discovery/mutation. `explicit` requires both finite
     non-negative prices and must reject a contradictory zero-mode
     acknowledgement if supplied.
   - Admin pricing select starts with a non-value “Choose pricing mode” option;
     never default silently to local zero. Show the dedicated local-zero
     checkbox and clear non-invoice wording.
   - CLI setup requires exactly the equivalent pricing mode/confirmation.

2. **Public model ID mapping without JSON**
   - Preview each discovered model with a safe editable default public ID
     `<provider>/<upstream_model>`.
   - Submit bounded repeated scalar mappings, not JSON or raw preview body.
     Re-probe, accept mappings only for selected fresh IDs, reject duplicate,
     missing, unknown, unsafe, or conflicting mappings, and pass the exact map
     into `SetupRequest.public_model_ids`.
   - Render only escaped safe IDs; never put a provider body/metadata/key in a
     hidden field, session, cookie, or URL.

3. **CLI confirmed atomic setup**
   - Add one command under `providers` (use a clear name such as
     `setup-models`) taking repeated selected models and optional repeated
     `upstream=public` mappings, exact preset, priority/visibility/streaming/
     local-function flags, pricing mode and values, optional enable-unqualified
     confirmation, required execute confirmation, and audit reason.
   - It must use the same `OpenAICompatibleSetupService`, re-probe, transaction,
     validation, route/pricing services, and safe result DTO as admin; no
     duplicate business logic.
   - JSON output contains only provider, selected safe IDs, created route/
     pricing IDs/counts, preset, enabled flag, and pricing mode—never secret,
     raw body, headers, arbitrary metadata, or content.

4. **Admin and transaction evidence**
   - Add direct authenticated admin route tests for discovery confirmation,
     no-mutation preview, safe rendered IDs/mapping controls, execute
     confirmation, local-zero acknowledgement, explicit prices, re-probe, CSRF,
     and generic-only failure.
   - Add a focused template/browser assertion for the provider detail →
     discovery form/preview controls. Do not make a real network call.
   - Extend PostgreSQL evidence with an injected failure after at least one
     route/pricing/audit write inside the caller transaction; after rollback in
     a fresh transaction/session, assert zero rows from that attempted setup.
     Keep existing preflight-conflict no-additional-row proof.

5. **Governance/check closure**
   - This active continuation uses the canonical heading and PR-mode line, so
     the unchanged 019-a order no longer drives the initial-round assertion.
   - Do not weaken or special-case the governance test.

## Allowed paths

Only the existing 019-a implementation/test/template/doc paths plus this order,
`oap/active`, and the 019-b report. One focused browser test path is allowed.
No migration, provider runtime refactor, new public endpoint, real LAN/provider,
Qwen/Codex, image behavior, hosted tool, automatic discovery, or unrelated
documentation expansion.

## Acceptance and verification

- Admin and CLI share the exact setup service and both prove preview/re-probe/
  confirm/atomic semantics.
- Zero pricing cannot occur without literal acknowledgement; explicit pricing
  remains exact Decimal EUR metadata.
- Custom public IDs work without JSON and conflict/secret/mismatch cases fail
  before mutation.
- Mid-write PostgreSQL failure rolls back routes, pricing, and audits.
- Focused discovery/setup/CLI/admin/template/browser/PostgreSQL tests pass with
  zero skips; scoped Ruff, Jinja parse, compileall, Alembic head, governance,
  docs drift, and diff check pass. No full local suite.
- Every final-head required GitHub check must be green before reporting it as
  passed.

## Publication duties

Commit this exact order and `oap/active=019-b` to existing PR #245. Publish one
immutable
`oap/reports/019-b-close-setup-confirmation-cli-and-atomicity-gaps.md` in a
final report-only commit with literal implementation head and
`Report publication commit: SELF`. Push/verify remote head, send exact FIFO
`OK`, and return to one control wait. Coding agent never merges.

# OAP Work Order — 151-e

PR mode: `AMEND_EXISTING_PR`
PR: `#286`
Branch: `oap/151-production-appliance-closure`
Base: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
Current remote head: `d362439e132275833f0fe4e963ac9af7497e01c6`
Title remains: `obj151: qualify production appliance boundary`

## Objective and reason

Close the last evidence-only defects in objective 151. Preserve the accepted
151-d production repairs, but make the qualification prove positive exercised
Prometheus samples, include the authenticated landing page in privacy scanning,
and publish an exact, self-correlating Compose project identifier and cleanup
audit. This is the same PR and numeric objective; do not rewrite features.

## Verified starting state and rejection provenance

- Remote `main` remains
  `ce0cf95685796477685a3aab6edacb39def6c27b`.
- PR #286 is OPEN with no auto-merge. Its remote head is valid report-only
  commit `d362439e132275833f0fe4e963ac9af7497e01c6`; sole parent/151-d
  implementation head is `a6d5d8c3da381827e5b7fc0fd0e019f314aad4b0`, and the
  commit changes only
  `oap/reports/151-d-production-dashboard-metrics-and-restore-truth-closure.md`.
- All required checks succeeded on that report head.
- The 151-d implementation correctly fixes exact `/admin` routing, follows the
  real HTTPS login redirect, reads authorized in-container metrics while
  preserving public/default denial, tightens restore verification, tests the
  0024 migration round-trip, and passes all 16 no-keep phases. Preserve it.
- The actual final 151-d Runner project and runtime directory were
  `slaif-151-3981570-28080c`, but the immutable report records
  `slaif-151-3981570-28080` (missing the final `c`). The coding agent then used
  that truncated label for its external container/network/volume check. An
  independent check confirmed both names currently have zero containers, the
  full actual name has no network/volume, and the full actual runtime is
  absent, so cleanup occurred; nevertheless the immutable report cannot
  correlate its claimed cleanup to the exact run and is rejected.
- The metrics code requires HELP/TYPE metadata for four families but does not
  require a positive emitted sample for each. The 151-d report calls them
  exercised. HELP registration is not proof that real requests/accounting
  incremented the production exposition.
- The dashboard phase verifies the landing body but adds only usage/audit
  subpage bodies to the later privacy scan. Include the authenticated landing
  body too.
- No real provider credential is authorized. Continue to treat the inherited
  exposed credential as unusable and explicitly unset all provider variables.

## Required implementation and evidence

### 1. Positive metrics samples

- Parse the actual authorized Prometheus exposition already obtained through
  API-container loopback. For each of
  `gateway_http_requests_total`, `gateway_provider_requests_total`,
  `gateway_tokens_total`, and `gateway_cost_eur_total`, require at least one
  non-comment sample with a finite numeric value greater than zero.
- Do not count `# HELP`, `# TYPE`, `_created`, an empty family, or a fabricated
  string as an exercised sample. Keep the existing public NGINX denial and
  unallowlisted diagnostic denial assertions unchanged.
- Emit only bounded sanitized evidence in the final JSON: per-family positive
  sample count/boolean or another equivalently bounded aggregate. Do not emit
  the exposition, labels, URLs, prompts, models supplied by users, or secrets.
- Add a focused test for positive, zero-only, metadata-only, malformed, and
  unrelated samples. Prefer a small parsing helper over brittle source-string
  assertions.

### 2. Complete dashboard privacy input

- Add the verified authenticated `/admin` landing HTML to the exact dashboard
  body collection scanned for all generated canaries and secrets. Continue to
  scan usage and audit bodies. Do not store or print those bodies.
- Emit a bounded dashboard evidence object containing only final path/status,
  redirect-followed boolean, secure-cookie boolean, and scanned-body count (or
  equivalent safe fields). The final report must cite these bounded facts.

### 3. Exact run and cleanup correlation

- Run one new complete no-keep qualification after these evidence changes.
  Capture the exact `project` string directly from its final JSON without
  retyping/truncating it.
- Independently query Docker containers, networks, and volumes using that exact
  full string and check the exact `.qualification-runtime-<project>` path.
  Record only counts/booleans. Prefixes, visually copied IDs, or a different
  project name do not pass.
- Preserve restore-count, accounting, dashboard, privacy, and every existing
  phase assertion. All 16 phases and automatic cleanup must remain `OK`.

### 4. Documentation and immutable report

- Append honest history to the production qualification record: 151-d fixed
  the product boundary but its report was rejected because the project ID and
  external cleanup target were truncated, metrics exercise checked metadata
  rather than positive samples, and the landing body was omitted from the
  privacy-body set.
- Publish exactly one immutable
  `oap/reports/151-e-exact-project-and-metrics-sample-evidence-closure.md` in a
  final report-only commit. It must record the exact final implementation
  head, exact machine-copied project string, bounded metrics/dashboard
  evidence, restore counts, accounting evidence, all phases, automatic and
  independent cleanup for that exact string, final-head checks, and unchanged
  limitations.
- The report commit must have the implementation head as first parent, change
  only that report path, say `Report publication commit: SELF`, be the remote
  PR head, and precede exact `OK`.

## Exact allowed paths

```text
scripts/production-qualification/run.py
tests/unit/test_production_compose_contract.py
docs/verification/2026-08-24-production-appliance-qualification.md
oap/orders/151-e-exact-project-and-metrics-sample-evidence-closure.md
oap/reports/151-e-exact-project-and-metrics-sample-evidence-closure.md
oap/active
```

Use the narrowest subset. Do not edit NGINX, Compose, restore, migration,
application, provider, endpoint, policy, pricing, accounting, dashboard, or
adapter code unless a new concrete product defect is first reported for
strategic continuation.

## Anti-false-positive acceptance

- Each named metric has a positive non-comment sample from the real authorized
  exposition obtained in the composed run. Registration metadata alone fails.
- Landing, usage, and audit HTML are all included in privacy scanning; none is
  emitted or persisted as evidence.
- The report's project string exactly equals the final JSON `project` value.
  Independent cleanup checks use that exact string and exact runtime path.
- A fresh no-keep run at the final implementation head passes every phase and
  automatic cleanup. A prior 151-d run, kept run, hand-edited ID, prefix label,
  or manual cleanup does not pass.
- No provider credential value is enumerated, printed, validated, or used. All
  relevant commands explicitly unset `OPENAI_API_KEY`,
  `OPENAI_UPSTREAM_API_KEY`, `OPENROUTER_API_KEY`, and upstream-test toggles.
- All required final-report-head checks are successful. The coding agent does
  not merge or enable auto-merge.

## Required verification

```text
git diff --check
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY python -m ruff check <changed Python/tests>
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY python -m pytest <focused metrics/dashboard qualification tests> -q
env -u APP_ENV -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY ENABLE_EMAIL_DELIVERY=false .venv/bin/python scripts/production-qualification/run.py
<parse exact project from final JSON>
<independent exact container/network/volume/runtime checks using that value>
```

GitHub CI is required at the final report head. Do not run a broad local suite
merely for appearance.

## Boundaries and non-goals

- No real provider, production/staging/shared database, real email,
  deployment, release, credential rotation implementation, or external state.
- No enterprise feature, endpoint/field expansion, provider/module/tool work,
  adapter generalization, plugin SDK, dashboard polish, certification,
  penetration test, compliance, HA, invoice, support, or SLA work.
- Keep PostgreSQL authoritative and preserve every existing auth, policy,
  key-isolation, quota, accounting, privacy, and fail-closed behavior.
- This remains disposable fixture qualification, not production certification.

## Publication and response duties

- Commit/push bounded implementation changes on PR #286; do not merge.
- Publish the required one-file immutable report only after implementation and
  fresh evidence are frozen.
- Verify all final-report-head checks, topology, exact cleanup correlation, PR
  open state, and auto-merge absence; then write exactly two bytes `OK` to the
  response FIFO and resume the control FIFO.

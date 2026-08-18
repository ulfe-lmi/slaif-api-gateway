# OAP Work Order — 007-b

## Objective

Correct the strategic transcript/governance activation defect reported in
007-a by publishing a governance-compliant continuation, activating it, and
amending the existing PR #232 without changing implementation or immutable
007-a history.

Do not create another PR and do not rerun product or broad local tests.

## GitHub state

- Numeric objective: `007`
- Execution round: `007-b`
- PR mode: `AMEND_EXISTING_PR`
- Existing PR: `#232`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/232`
- Head branch: `oap/007-codex-streaming-tool-event-roundtrip`
- Base: `main`
- Starting remote PR head:
  `b98f7a5d87c50123788b834d409bce5ffd880a0f`
- Prior implementation head:
  `01e794a0ae21ed36bfbd37660c9015c760f51e9d`
- Prior round: `007-a`, truthfully `BLOCKED`

Amend PR #232 only. Never create a replacement/second objective-007 PR.

## Cause and resolution

The immutable 007-a order states `CREATE_NEW_PR` and correctly created one PR,
but omitted the exact active-order marker required by
`tests/unit/test_oap_governance.py`:

```text
PR mode: `CREATE_NEW_PR`
```

The coding agent correctly preserved the order, published the implementation,
and reported the failure. All 007 product-focused tests passed; GitHub's unit
job ran 2,566 tests with 2,565 passing and only this active-order assertion
failing.

The 007-a order/report are immutable. This continuation is the deliberate
strategic correction: it contains the exact continuation PR marker above,
becomes the active order, and records that the same PR is amended. No product
code/test/doc change is necessary.

## Governing/start requirements

Re-read AGENTS, OAP protocol, immutable 007-a order/report, current PR state,
the governance test, and this order. Verify PR #232 remains open on the exact
branch/head and no second objective PR exists.

The strategic model atomically published this order and `oap/active=007-b`;
they must be the only dirty paths and must be committed unchanged. Preserve all
other state.

## Allowed paths

Implementation/transcript commit may change only:

```text
oap/active
oap/orders/007-b-correct-active-order-governance-marker.md
```

Final report-only commit may add only:

```text
oap/reports/007-b-correct-active-order-governance-marker.md
```

Do not edit 007-a history, application, providers, policies, tests, docs,
fixture, scripts, dependencies, CI, or unrelated paths.

## Focused verification only

Run only:

```bash
.venv/bin/python -m pytest tests/unit/test_oap_governance.py -q
git diff --check
git status --short
```

Do not rerun the product-focused 007 tests, live Codex verifier, full unit,
integration, E2E, browser, Docker, or HPC locally. Their immutable 007-a report
and GitHub state remain evidence. GitHub CI will evaluate the new head.

## Acceptance criteria

1. `oap/active` selects exactly `007-b` and one matching order.
2. The focused governance test passes.
3. PR #232 is amended in place with only the two transcript paths.
4. Immutable 007-a implementation/order/report and fixture remain unchanged.
5. All final 007-b report-head GitHub checks eventually pass.
6. Coding agent creates no PR, merge, auto-merge, code edit, or broad local run.
7. Final report-only commit has the transcript implementation head as first
   parent and only the new report path.

## Report and merge requirements

Commit/push exact strategic files to the existing branch. Inspect real GitHub
checks; pending/missing/failed is not green. Never merge.

Publish one immutable report at
`oap/reports/007-b-correct-active-order-governance-marker.md` with literal
implementation SHA, `Report publication commit: SELF`, exact governance result,
path scope, prior product evidence reference, broad/product tests NOT RUN this
round, check states, and no production/secret action.

The report-only commit changes only that report and has the implementation head
as first parent. Push/verify and signal exact `OK`.

Do not merge under any circumstance.

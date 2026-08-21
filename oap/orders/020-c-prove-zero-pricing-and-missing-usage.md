# OAP Work Order — 020-c

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend only PR #246 with tests-first evidence for the two remaining explicit
020-b accounting outcomes: an actual generic gateway request using an
Objective-019 `operator_confirmed_local_zero` pricing row, and a generic
provider response/stream missing final usage following the existing endpoint
fail-closed or estimated-interrupted contract. Production code may change only
if one of these new focused tests proves a real defect.

## Verified state

- PR #246, current report head
  `1563051d46cd31ee068f25f113d5ad13abe5b8f6`; 020-b implementation head
  `4d8cc6d7f08574768d9b3c042943d0c6b5f36268`.
- All ten checks are green; no review threads; PR open/clean/mergeable.
- Reuse this PR. Do not edit prior orders/reports, merge, auto-merge, or create
  another PR.

## Required evidence

1. Extend the focused actual-gateway PostgreSQL matrix with a generic Chat or
   Responses route whose active EUR pricing rule has exact zero input/output
   prices and
   `pricing_metadata.pricing_basis=operator_confirmed_local_zero`. Execute the
   request through ASGI with provider usage and assert the pricing row basis,
   finalized zero native/EUR ledger charge, used/reserved counters, one ledger,
   zero pending reservation, and no content/secret persistence. Zero must not be
   inferred from absent pricing.
2. Add at least one generic-provider gateway missing-final-usage case on the
   actual endpoint path. Prefer a streaming case after a visible output delta so
   the existing estimated-interrupted behavior is exercised; otherwise prove
   the exact documented non-stream fail-closed behavior. Assert no normal
   success terminal, no zero-cost-success classification, safe error, one
   consistent reservation/ledger outcome, zero duplicate, and no canary
   persistence.
3. Prove the equivalent built-in path is unchanged by reusing the existing
   focused missing-usage regression, not by adding a broad suite.

## Allowed paths

```text
tests/integration/test_openai_compatible_conformance_postgres.py
tests/e2e/test_openai_python_client_chat.py
tests/e2e/test_openai_python_client_responses.py
app/slaif_gateway/services/chat_completion_gateway.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/accounting.py
docs/accounting.md
docs/compatibility-matrix.md
oap/active
oap/orders/020-c-prove-zero-pricing-and-missing-usage.md
oap/reports/020-c-prove-zero-pricing-and-missing-usage.md
```

Use tests only unless they expose a defect. No migration, preset/UI/CLI change,
real provider, Qwen/Codex, remote URL, hosted tool, or broad local suite.

## Verification and publication

Run the focused generic PostgreSQL file and exact existing missing-usage unit/
E2E regression against a disposable `TEST_DATABASE_URL`, scoped Ruff,
compileall if production changes, Alembic head, docs drift if docs change, and
diff check. Require zero skips. Publish one immutable 020-c report-only final
commit with literal implementation head and `Report publication commit: SELF`,
verify all final-head checks, send exact FIFO `OK`, and return to one control
wait. Coding agent never merges.

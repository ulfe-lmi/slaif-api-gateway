# OAP Work Order — 152-b

PR mode: `AMEND_EXISTING_PR`
PR: `#287`
Branch: `oap/152-real-provider-accounting-qualification`
Base: `main @ 8f2813bf745b90221da33a7cfaf40726c5b1b480`
Current remote head: `346cdc13bcc1eb42035fb1d6a3e82c137651f4a4`
Title remains: `obj152: qualify real-provider accounting evidence`

## Objective and reason

Close four verifier defects found in independent review of 152-a before any
live authorization: prove the selected Gateway key is fresh and that no
uncorrelated rows coexist with the eight flows; scan the complete key row for
plaintext; make successful output fully bounded while including required model
and token facts; and stop claiming a real provider call from a mere failed
Gateway attempt. No real provider call is authorized in this round.

## Verified starting state and accepted evidence

- Remote `main` remains
  `8f2813bf745b90221da33a7cfaf40726c5b1b480`.
- PR #287 is open and mergeable with no auto-merge. Remote head
  `346cdc13bcc1eb42035fb1d6a3e82c137651f4a4` is a valid report-only commit;
  its sole parent and implementation head is
  `38951e044b51b2a5a576524c747349a3cad19b15`. All ten report-head checks
  succeeded.
- 152-a made no HTTP request, SQL connection, provider call, or credential
  read. Its 37 verifier tests and 67 focused adapter/header tests passed.
  Preserve its authorization, safe target, stream parsing, exact-ID
  correlation, cost summing, no-retry, privacy, and documentation work.
- The inherited exposed OpenAI credential remains unusable. Never enumerate,
  validate, print, source, or call with it; never read historical key files.

## Independent review defects to close

### 1. Fresh-key baseline and exact run isolation

`PostgresProbe.final_run_check()` currently selects only the eight request IDs
already collected. A pre-existing or concurrent ninth reservation/ledger row
for the same key can coexist and the verifier still passes, contradicting the
order/report claim of exactly eight rows for this run and no uncorrelated rows.

- Require one explicit Gateway key UUID as a safe, non-secret input. Validate
  canonical UUID syntax before SQL and do not print it.
- Before any HTTP request, select exactly that key and require active disposable
  state, zero used and reserved request/token/cost counters, zero total quota
  reservations, and zero total usage-ledger rows. Missing, ambiguous, used, or
  non-fresh state fails before traffic.
- Scan the complete serialized Gateway key row in memory and require the
  plaintext Gateway key is absent. Include at least public ID/prefix/hint,
  token hash, service fields, model/endpoint policy, calibration/metadata JSON,
  fence metadata, and counters. Do not emit the row or any fragment.
- Every exact-ID correlation must match the preselected key UUID. After each
  ordinal 1 through 8, query all reservation and ledger request IDs for that
  key and require each total equals the ordinal and each set equals only the
  verifier's seen Gateway IDs. This catches pre-existing, concurrent, duplicate,
  and uncorrelated state rather than filtering it away.
- The final check must again require total counts and exact sets of eight, zero
  pending reservations, and zero reserved counters. Queries by only
  `request_id = ANY(seen_ids)` cannot satisfy run isolation.

### 2. Fully bounded successful and failed output

- Each successful flow summary must include the validated operator-selected
  model and exact stored/response input, output, and total token integers in
  addition to provider, endpoint, streaming, HTTP, terminal, accounting,
  cost-source, and correlation facts. Never include IDs or content.
- Permit only the exact current Chat/Responses cost-confidence vocabulary:
  `slaif_calculated`, `slaif_calculated_with_fallbacks`,
  `slaif_calculated_provider_cost_untrusted`, and
  `provider_reported_with_slaif_comparison`. Reject any other value before it
  reaches output. `cost_source` remains the existing exact two-value set.
- Bound model length/grammar as already implemented. Ensure every emitted
  string is from an explicit allowlist or that model grammar; no database,
  provider, HTTP, or exception string may flow through merely because it is a
  string.
- On failure, distinguish `gateway_requests_attempted` from proven provider
  execution. A transport/TLS/HTTP/parse failure is not proof that the real
  provider was called. Emit a real-provider proof boolean only when at least one
  flow reached a valid provider terminal and exact terminal PostgreSQL
  correlation; otherwise false. Track correlated-completed count separately
  and never infer it from attempted count.
- On success, require attempted=correlated-completed=8 before
  `real_provider_call_proven=true`.

### 3. Protected-file and cost truth tightening

- Reject protected paths whose raw absolute normalized path differs from the
  resolved path, so symlinked parent components cannot bypass the current
  final-component check. Read and validate metadata from the same opened file
  descriptor where practical; do not widen permissions or repository paths.
- Preserve actual-cost summing. Document that the authorization-cost check is
  post-response SLAIF accounting evidence and cannot guarantee provider invoice
  totals or prevent a single request from crossing the cap. The 32-token bound,
  selected low-cost models, and human authorization remain the pre-call limits.

### 4. Tests and truthful documentation

- Add tests proving pre-traffic rejection of non-fresh key state; exact ordinal
  total/set enforcement with stray old and concurrent rows; wrong-key
  correlation; complete-key-row plaintext detection; output token/model facts;
  cost-confidence allowlisting; and attempted versus correlated provider proof.
- Add a protected-parent-symlink refusal test where supported by the local
  filesystem.
- Preserve all 152-a parser/refusal/no-retry tests and focused provider
  Authorization-replacement tests.
- Amend canonical documentation and the report history to describe the exact
  152-a review defects and the post-hoc cost limitation. Keep live qualification
  `NOT RUN`.

## Exact allowed paths

```text
scripts/verify_real_provider_qualification.py
tests/unit/test_real_provider_qualification_verifier.py
docs/real-provider-qualification.md
oap/orders/152-b-verifier-run-isolation-and-bounded-output.md
oap/reports/152-b-verifier-run-isolation-and-bounded-output.md
oap/active
```

Use the narrowest subset. Do not change application, adapter, database schema,
Compose, policy, or accounting code. A product defect becomes another
same-number continuation.

## Anti-false-positive acceptance

- No real provider call, Gateway request, PostgreSQL connection, or protected
  credential read occurs in 152-b verification.
- Freshness is checked before traffic against total key-scoped PostgreSQL
  truth. Caller claims, timestamps, filtered `ANY(seen_ids)` queries, and final
  count eight over only seen IDs do not pass.
- After each ordinal, one injected old/foreign request ID must make the
  verifier fail even when all eight expected IDs exist and are terminal.
- Key-row privacy scans cover the complete selected row, not only token hash.
- No arbitrary cost-confidence/provider metadata string can reach output.
- A failed first Gateway attempt reports attempted=1, correlated=0, provider
  proof=false. It cannot report `real_provider_called=true`.
- Unit tests remain synthetic and do not satisfy the live objective. Report
  result is implementation hardened, live qualification `NOT RUN`.
- Every command unsets `OPENAI_API_KEY`, `OPENAI_UPSTREAM_API_KEY`,
  `OPENROUTER_API_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, and
  `RUN_UPSTREAM_TESTS`; historical keys/files are never touched.
- Every final report-head check succeeds. CI cannot override a failed refusal,
  bounded-output, or run-isolation test.

## Required verification

```text
git diff --check
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS .venv/bin/python -m ruff check scripts/verify_real_provider_qualification.py tests/unit/test_real_provider_qualification_verifier.py
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS .venv/bin/python -m pytest -q tests/unit/test_real_provider_qualification_verifier.py <same focused Authorization-replacement tests>
<guarded dry run and missing-file live-shaped run proving zero HTTP/SQL>
```

Do not run broad local suites. GitHub CI is required on the final report head.

## Boundaries and non-goals

- No live authorization, real provider, credential validation, production or
  shared DB, deployment, release, key rotation, or external state change.
- No provider/endpoint/model feature, adapter/accounting rewrite, retry system,
  plugin/module/facial work, hosted-tool qualification, or abstraction.
- No enterprise, certification, compliance, penetration-test, HA, invoice,
  support, or SLA work.

## Publication and response duties

- Amend only PR #287; do not merge or enable auto-merge.
- Publish one immutable
  `oap/reports/152-b-verifier-run-isolation-and-bounded-output.md` as the sole
  path in a final report-only commit. Mark live evidence `NOT RUN`.
- Verify report SELF topology, PR/hash/state, no-live-call evidence, and every
  final check; then write exact `OK` to the response FIFO and resume control.

# OAP Coding-Agent Report — 162-c

RESULT=PASSED

## Work order

- Identifier: `162-c`
- Work-order file: `oap/orders/162-c-close-exact-negative-node-mapping.md`
- Numeric objective: `162`, exact omission-negative node mapping
- PR mode: `AMENDED_EXISTING_PR`

## Status

COMPLETE

## Executive summary

Closed the final Objective-162 evidence defect on existing PR #299. Production,
docs, source fixture, handler E2E, PostgreSQL tests, and all accepted 162-a and
162-b behavior remain frozen.

The strict stream unit file now has stable, descriptive parameter IDs for 19
direct omission-item mutations, three pre-completion rejection cases, four
post-completion cases, and six terminal mutations, plus explicit duplicate and
pre-item terminal tests. Every omission-item mutation validates the exact
created/in-progress/added prefix, changes only the direct completed-item event,
rejects at that item boundary, creates no replay candidate, and leaves terminal
completion invalid. The obligation map contains 54 literal required IDs and 47
distinct exact node references, with no anonymous `<lambda>` mappings and
`missing=[]`.

## Lifecycle labels

```text
PRODUCTION-UNCHANGED-FROM-162-A = YES
EXACT-OMISSION-NEGATIVE-MATRIX = YES
EXACT-TERMINAL-NEGATIVE-MATRIX = YES
OBLIGATION-NODES-COLLECTED-AND-EXECUTED = YES
MODEL-FREE-REGRESSION-ACCEPTED = YES
POSTGRESQL-ACCOUNTING-REPLAY-ACCEPTED = YES
PROTECTED-ACCEPTED = NO
LOCAL-HANDBACK-READY = NO
MERGED = NO
RELEASE-READY = NO
```

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: `299`
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/299
- PR state at report time: `OPEN`
- Base branch: `main`
- Head branch: `oap/162-zero-argument-function-stream-closure`
- Starting remote SHA: `f8a6315c572313cfb7f4e3eacb0068a9749b705e`
- Implementation head SHA: `2c8fa51840a9ef035b52f8467a45b2faf628a7ae`
- Report publication commit: `SELF`
- Remote PR head after report publication: `SELF` (literal SHA to be derived from GitHub)
- Implementation commits pushed before the report commit: `2c8fa51840a9ef035b52f8467a45b2faf628a7ae`
- Report commit first parent: `2c8fa51840a9ef035b52f8467a45b2faf628a7ae`
- Created a new PR this turn: no
- Amended existing PR this turn: yes
- Merge performed: NO
- PR was open, non-draft, and mergeable at implementation-head verification.

## Changes made

- Added named mutation helpers and stable `pytest.param(..., id=...)` cases
  for every exact omission-item identity, coordinate, status, namespace,
  caller, name, argument, field, and sequence negative required by 162-c.
- Added stable pre-completion, post-completion, terminal, duplicate-terminal,
  and terminal-before-item-completion controls on the omission lifecycle.
- Replaced broad 162-b map entries with one-to-one stable nodes, using exact
  parameterized IDs for all mapped parameterized cases.
- Kept the independently literal required obligation set and strengthened its
  checks for exact mapping equality, duplicate/missing/unknown IDs, safe paths,
  and absence of anonymous lambda IDs.
- Synchronized and committed the unchanged c order and `oap/active` bytes.

## Files changed

The c implementation commit changes exactly:

- `tests/unit/test_responses_codex_streaming_tools.py`
- `oap/active`
- `oap/orders/162-c-close-exact-negative-node-mapping.md`

The final report-only commit changes only this report. All app files,
documentation, source fixture, E2E test, PostgreSQL tests, migrations,
dependencies, CI, verifier, Local, Qwen, and prior reports remain unchanged
from 162-b.

## Acceptance-criteria evidence

### Exact omission-item mutation matrix

- Result: PASSED.
- Evidence: stable nodes cover missing/mismatched item ID,
  missing/mismatched call ID, missing/mismatched output index,
  missing/wrong completed status, wrong namespace, non-null caller, wrong name,
  non-empty arguments, canonical `{}` arguments, extra event/item fields,
  missing sequence, missing item type, duplicate sequence, and non-monotonic
  sequence. Every case reaches the direct `response.output_item.done` event
  after a valid added item and then rejects without a replay candidate or valid
  terminal completion.

### Exact post-completion and terminal matrix

- Result: PASSED.
- Evidence: stable nodes reject duplicate item completion, late argument delta,
  late arguments-done, and a second function item after valid omission
  completion. Stable terminal nodes reject wrong name, arguments, type, status,
  missing usage, invalid usage, duplicate terminal completion, and terminal
  completion before item completion. The valid source lifecycle continues to
  prove detailed usage and one transient replay candidate; durable persistence
  remains after accounting as proven by the accepted PostgreSQL/E2E nodes.

### Frozen production and cross-contract evidence

- Result: PASSED.
- Evidence: `git diff` from the 162-b report head contains only the strict
  stream test and c orchestration files. The 162-a production implementation,
  module version, source fixture, docs, E2E helper, and PostgreSQL tests are
  byte-identical. No new compatibility discovery, diagnostic, provider,
  protected, Local, Qwen, or production action occurred.

## Obligation manifest and collection

- Required obligation IDs: 54.
- Mapped obligation IDs: 54.
- Distinct mapped node references: 47.
- Duplicate obligation IDs: 0.
- Anonymous `<lambda>` mapped node IDs: 0.
- Unknown IDs: 0.
- Missing IDs: 0 (`missing=[]`).
- `PYTHONPATH=. .venv/bin/pytest --collect-only -q` over the affected unit,
  PostgreSQL, and Responses E2E files: succeeded with 245 nodes collected.
- `PYTHONPATH=. .venv/bin/pytest -vv --collect-only` over the same files:
  succeeded with 245 nodes; an external parser mechanically verified every one
  of the 47 distinct mapped node references was present in collection.
- Affected collection breakdown: 41 client-module unit nodes, 175 strict
  stream unit nodes, 4 client-module PostgreSQL nodes, 1 replay PostgreSQL
  node, and 24 Responses E2E nodes.
- The mapping uses stable descriptive IDs for all new matrix nodes. Existing
  historical parameterized nodes remain mapped only with their exact concrete
  collected IDs where referenced.

## Local verification

- `PYTHONPATH=. .venv/bin/pytest -q tests/unit/test_codex_client_modules.py tests/unit/test_responses_codex_streaming_tools.py`: PASSED — 216 collected and passed.
- `TEST_DATABASE_URL=<fresh unique disposable PostgreSQL database> PYTHONPATH=. .venv/bin/pytest -vv --disable-warnings tests/integration/test_codex_client_modules_postgres.py tests/integration/test_codex_replay_references_postgres.py`: PASSED — 5 collected, 5 passed; actual execution, not skips.
- `TEST_DATABASE_URL=<fresh unique disposable PostgreSQL database> PYTHONPATH=. .venv/bin/pytest -vv --disable-warnings tests/e2e/test_openai_python_client_responses.py`: PASSED — 24 collected, 24 passed.
- `PYTHONPATH=. .venv/bin/pytest -q tests/unit/test_oap_governance.py tests/unit/test_agentic_client_integration_governance.py tests/unit/test_module_architecture.py`: PASSED — 49 tests.
- `.venv/bin/ruff check tests/unit/test_responses_codex_streaming_tools.py`: PASSED.
- `.venv/bin/ruff format --check tests/unit/test_responses_codex_streaming_tools.py`: PASSED — 1 file already formatted.
- `.venv/bin/python -m compileall -q tests/unit/test_responses_codex_streaming_tools.py`: PASSED.
- `python -m json.tool tests/fixtures/codex/0.149.0/vllm-0.27.1-zero-argument-function-stream.json`: PASSED; fixture unchanged.
- `git diff --check`: PASSED.
- Exact c allowed-path/tree check: PASSED.

The unrelated full-unit opt-in Codex-version mismatch from 162-a remains
outside this evidence-only correction and was not modified or rerun. The 128-
worker HPC harness, Objective-160 verifier, protected inference, and real
provider were not invoked.

## PostgreSQL, accounting, replay, and privacy

- PostgreSQL ran against a uniquely named disposable `TEST_DATABASE_URL`,
  executed all five selected tests, and was dropped and confirmed absent.
- The full Responses E2E ran on fresh disposable PostgreSQL state and included
  the accepted five-event handler path.
- No raw item/call IDs, arguments, schemas, prompts, completions, media,
  credentials, provider secrets, database rows, or arbitrary event bodies were
  added to the report or durable evidence.
- No accounting, quota, replay, provider, route, authority, retention, or
  production behavior changed in c.

## GitHub CI / required checks

All ten required checks were observed `SUCCESS` for implementation head
`2c8fa51840a9ef035b52f8467a45b2faf628a7ae` before report publication:

- Unit, lint, and migration head — SUCCESS, 2m21s.
- PostgreSQL integration tests — SUCCESS, 2m35s.
- OpenAI-compatible E2E tests — SUCCESS, 1m28s.
- Playwright browser smoke — SUCCESS, 1m22s.
- Docker Compose smoke — SUCCESS, 49s.
- Documentation hygiene — SUCCESS, 12s.
- Analyze Python — SUCCESS, 1m27s.
- Analyze (python) — SUCCESS, 2m03s.
- Analyze (javascript-typescript) — SUCCESS, 44s.
- CodeQL — SUCCESS, 3s.

The report-only commit may trigger fresh checks; the strategic agent must
independently verify the `SELF` commit without rewriting this report.

## Documentation

Documentation checked, no update needed because c only tightens evidence for
unchanged 162-a behavior/contracts.

## Local setup / cleanup

- Used the existing task-private Python environment and local PostgreSQL
  tooling; no dependency or lock file changed.
- Used only an isolated disposable PostgreSQL database through
  `TEST_DATABASE_URL`; it was dropped after the final tests and confirmed
  absent.
- No protected service, Qwen process, vLLM runtime, model, real provider,
  real email, production system, or Local repository was accessed or mutated.

## Safety and scope confirmations

- Production implementation unchanged from 162-a: yes.
- Unrelated files changed: no; all c paths are authorized.
- Production secrets accessed: no.
- Production systems accessed: no.
- Real upstream/provider calls: no.
- Real email sent: no.
- Required tests skipped/not run: no for the selected unit, PostgreSQL, E2E,
  governance, collection, static, and CI evidence. The unrelated full-unit
  opt-in candidate mismatch remains carried from 162-a; prohibited HPC and
  protected runs were not required or executed.
- Scope deviation: no.
- Extra PR created for same numeric objective: NO.
- PR merged by coding agent: NO.
- Activated order and `oap/active` edited by coding agent: NO; synchronized
  unchanged from the strategic worktree.
- Report-publication commit changes only this report file: yes.

## Known limitations / blockers

- This remains finite evidence correction for bounded mocked/local Gateway
  conformance. It is not protected acceptance, real-provider qualification,
  production certification, release readiness, or compliance evidence.
- The accepted 162-a E2E's harmless namespace declaration remains the existing
  mechanism that activates the already-gated Codex stream path; c does not
  change it.
- GitHub checks for the report-containing `SELF` commit must be rechecked by
  strategy before merge.

## Recommended strategic follow-up

Review PR #299's c diff, exact stable omission/terminal nodes, the mechanically
verified 54-ID/47-reference mapping, immutable report topology, and all
report-head checks. If accepted, merge strategically only. Any Local handback
remains strategic-owned after Gateway merge.

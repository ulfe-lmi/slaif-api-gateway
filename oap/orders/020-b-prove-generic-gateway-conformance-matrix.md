# OAP Work Order — 020-b

PR mode: `AMEND_EXISTING_PR`

## Objective and reason

Amend only Objective 020 PR #246. The 020-a implementation adds the correct
generic pre-side-effect remote-image boundary and useful unit coverage, but its
report overstates the required conformance evidence: no official-client E2E
file changed, and the sole new PostgreSQL test exercises direct quota/accounting
services rather than Chat/Responses gateway execution. The vision preset also
sets broad `chat_multimodal` and Responses `multimodal` flags although this
objective implements image input only. Close those exact gaps.

Start implementation now after reading the existing generic E2E fixture helpers
and the Objective 017 PostgreSQL gateway-test pattern once. Reuse helpers; do
not loop through broad reconnaissance or run broad suites.

## Verified continuation state

- PR #246, <https://github.com/ulfe-lmi/slaif-api-gateway/pull/246>, branch
  `oap/020-generic-backend-chat-responses-conformance`, base `main`.
- Current report head `5a3c93f8f594a2ae59b7b7b7647c1de785924e47`;
  020-a implementation head `ba637ad4c9481aeac041e6bddff5476ab3bf18b3`.
- Report topology is valid; all ten checks are green; no review threads.
- Reuse this PR. Do not edit prior order/report, create another PR, merge, or
  enable auto-merge.

## Required closures

### 1. Exact image-input capability truth

- In `chat_and_responses_vision_inline_v1`, enable only
  `chat_image_inputs=true` and Responses `image_input=true` in addition to the
  selected text/stateless/streaming/function controls.
- Keep `chat_multimodal=false` and Responses `multimodal=false`; those reserved
  flags must not imply broader multimodal input/output. Keep every file/audio/
  generation/storage/state/background/hosted/Codex flag false.
- Update setup/PostgreSQL/admin/CLI/docs assertions accordingly. Preserve no
  profile-specific image-count cap and inline-only generic behavior.

### 2. Official OpenAI-client mocked E2E

Add focused cases in both existing official-client E2E files using a real local
gateway app, PostgreSQL setup helpers, a configured generic provider slug/base
URL/env-var, route/pricing/key facts, and mocked upstream:

- Chat non-stream with two inline data images plus one explicitly enabled local
  function tool; assert upstream model/body/auth/header isolation and finalized
  usage/cost.
- Chat SSE streaming with final usage and safe completion.
- Stateless Responses non-stream with two inline images and an explicitly
  enabled local function declaration/output shape already supported by current
  policy; do not invent unsupported composition.
- Responses typed SSE text streaming with completed usage.
- At least one remote image URL through an official client/helper must reject
  before upstream and durable accounting mutation.

Use exact ordinary OpenAI Python client configuration against SLAIF. No direct
adapter-only substitute may be reported as official-client E2E.

### 3. PostgreSQL gateway matrix

Replace/extend the direct-service-only evidence with actual gateway request
execution (ASGI/TestClient or AsyncClient) and mocked generic upstream. Reuse
the current disposable DB and existing route/pricing/key service helpers.
Required outcomes, which may be parametrized/combined safely:

1. Chat success under `local_zero`: one finalized reservation/ledger, exact
   generic provider/route/model/endpoint, zero native/EUR price labeled local
   operator zero, counters consistent, no pending reservation.
2. Responses success under explicit non-zero EUR pricing with provider usage:
   one exact final charge/ledger and no duplicate.
3. Chat and Responses streaming success each finalize from terminal provider
   usage and leave zero reserved counters.
4. A deliberately small finite key is exhausted by finalized actual usage;
   the following fitting Chat or Responses request fails normal quota admission
   with no new upstream call/reservation/ledger.
5. Provider error before authoritative usage follows the existing safe failure/
   release contract; missing final usage follows the endpoint's existing
   fail-closed/estimated-interrupted contract and is never zero-cost success.
6. Generic remote image URL rejects before Redis, pricing/quota reservation,
   ledger, or provider call.

Across the matrix assert prompts/completions, both inline image base64 canaries,
function schema/name arguments/results canaries where applicable, raw bodies,
client/backend keys, Authorization/cookies/internal headers, and arbitrary
provider metadata are absent from durable ledger/audit/projection state.

### 4. Honest documentation/reporting

- Keep status `mocked_conformance`, not live Qwen/vLLM/Codex qualification.
- Update compatibility/accounting docs only as required to name the actual
  official-client and PostgreSQL gateway evidence; remove any broader
  multimodal implication.
- Report exact test counts and distinguish implementation-head versus
  report-head checks.

## Allowed paths

Use only existing 020-a paths plus:

```text
tests/e2e/test_openai_python_client_chat.py
tests/e2e/test_openai_python_client_responses.py
tests/integration/test_openai_compatible_conformance_postgres.py
tests/integration/test_openai_compatible_setup_postgres.py
docs/accounting.md
docs/responses-compatibility.md
oap/active
oap/orders/020-b-prove-generic-gateway-conformance-matrix.md
oap/reports/020-b-prove-generic-gateway-conformance-matrix.md
```

One exact existing test helper path may change if required. No migration,
public behavior widening, real network/provider, Qwen/Codex, hosted tool,
remote URL, or unrelated refactor.

## Verification economy and acceptance

- Run only the changed generic unit tests, the two targeted official-client E2E
  files/groups, and the one focused generic PostgreSQL matrix against an exact
  disposable `TEST_DATABASE_URL` with zero skips.
- Run scoped Ruff, compileall, Alembic head, Jinja parse if template changed,
  docs drift, and diff check. Do not run complete local suites; routine GitHub
  CI is broad evidence.
- Acceptance requires all outcomes above, exact privacy/accounting assertions,
  valid report topology, no unresolved review thread, and every final-head
  required check green.

## Publication

Commit this exact order and `oap/active=020-b` on PR #246. Publish one immutable
`oap/reports/020-b-prove-generic-gateway-conformance-matrix.md` report-only
final commit with literal implementation head and
`Report publication commit: SELF`, verify remote head/check state, send exact
FIFO `OK`, and return to one control wait. Coding agent never merges.

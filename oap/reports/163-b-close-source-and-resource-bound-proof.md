# OAP Objective 163-b Immutable Report

RESULT=PASSED

Implementation head SHA: ee12ff8885b86192e60b302ef76fa089471efb2c
Report publication commit: SELF

## Topology and scope

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR: #300, `https://github.com/ulfe-lmi/slaif-api-gateway/pull/300`
- Base branch: `main`
- Activation base: `5ea38325ef3a3ebc69524b4679b795fab0c52935`
- Branch: `oap/163-local-coding-sse-framing-bounds`
- 163-a report/current PR head preserved unchanged: `fc39f6874c8239b37e0904f9c966572f6f771695`
- Consolidated b implementation: `9fd3e6b912e5bd315313eb3772f36edbb9e16294`
- Final production-overflow evidence refinement: `ee12ff8885b86192e60b302ef76fa089471efb2c`
- Final report commit: `SELF`
- PR state at publication: OPEN, not merged
- `oap/active`: `163-b`
- Exact selected order: `oap/orders/163-b-close-source-and-resource-bound-proof.md`

The final report-only commit has the final b implementation as its first
parent and changes only this report. The previously published 163-a report was
not rewritten. The b implementation changes only the b allowlist: Local-owned
framing/streaming code, the pinned content-free vLLM envelope fixture, the
named unit/E2E tests, the five affected contract documents, `oap/active`, and
the exact b order. No schema, migration, dependency, configuration, CI,
generic provider path, client module, Local identity/signing path, verifier,
historical report, or protected resource changed.

## Findings closed

### Exact vLLM 0.27.1 response envelope

The content-free fixture
`tests/fixtures/codex/0.149.0/vllm-0.27.1-responses-response-envelope.json`
pins:

- provider/version: vLLM 0.27.1;
- tag commit: `6e448d0ea9bf3d88d898b65449ca6dc2aec170ac`;
- source file: `vllm/entrypoints/openai/responses/protocol.py`;
- source-file SHA-256:
  `6aeabf69dbc924b238172b505730a8a8321b50a819891d2a72a690963c970fba`;
- fixture SHA-256:
  `fb297b6425343c94145a1ffbb63bfbd1a41dfbbcead1e5549f206b169657aeec`;
- exact field count: 32; and
- source type/nullability/default classes, including default factories for
  `id` and `created_at` and default/null classes for every other field.

The production allowlist is tested for exact set equality with those 32 names:

`id`, `created_at`, `incomplete_details`, `instructions`, `metadata`, `model`,
`object`, `output`, `parallel_tool_calls`, `temperature`, `tool_choice`,
`tools`, `top_p`, `background`, `max_output_tokens`, `max_tool_calls`,
`previous_response_id`, `prompt`, `reasoning`, `service_tier`, `status`, `text`,
`top_logprobs`, `truncation`, `usage`, `user`, `presence_penalty`,
`frequency_penalty`, `kv_transfer_params`, `ec_transfer_params`,
`input_messages`, and `output_messages`.

The unreviewed names from 163-a (`error`, `store`, and `prompt_cache_key`) are
removed. `output` and `usage` retain their independent strict validators.
`input_messages`, `output_messages`, `kv_transfer_params`, and
`ec_transfer_params` are accepted only absent or null on the Gateway path.
Full source-shaped `response.created`, `response.in_progress`, and
`response.completed` envelopes containing every emitted default/null field
passed the strict validator. The source used for the pin was inspected
without importing or initializing vLLM or a model.

### Exact four-MiB co-resident event derivation

The strict terminal event has at most three output items, each with at most one
MiB aggregate content/arguments, plus a separately bounded one-MiB serialized
non-output/usage envelope. Reasoning summary is empty in the exact terminal
reasoning item; reasoning, function, and assistant-message content are not
incorrectly summed as co-resident summary-plus-terminal state. The resulting
static constants are:

| Quantity | Derivation | Value |
| --- | --- | ---: |
| terminal output item count | reviewed strict profile cardinality | 3 |
| terminal output bytes | `3 × 1,048,576` | 3,145,728 |
| serialized non-output/usage envelope | reviewed strict envelope ceiling | 1,048,576 |
| co-resident semantic budget | `3,145,728 + 1,048,576` | 4,194,304 |
| joined data / largest `json.loads` input | `4,194,304 × 6 + 131,072` | 25,296,896 |
| one line | `joined + len("data: ") + optional CR` | 25,296,903 |
| data segments | `64 semantic parts × 32 framing lines/part` | 2,048 |
| ignored-field allowance | `4 × 65,536-byte existing semantic delta bound` | 262,144 |
| complete CRLF frame | `joined + N×8 − (N−1) + ignored + 2`, `N=2,048` | 25,573,379 |

The six-fold expansion is the worst-case ASCII JSON escaping of one-byte
control characters (`\\u00XX`). The 128 KiB structural allowance covers field
names, bounded IDs/indexes, usage arrays, punctuation, and fixed JSON
structure. The `N−1` subtraction is required because joined data already
includes the newlines inserted between data segments. Eight bytes per CRLF
data line covers `data: `, CR, and LF; the final two bytes are the blank CRLF
delimiter. The hard constants are source-owned and cannot be raised by route,
provider, response header, or environment data.

The maximum typed test drives a valid 64-event strict lifecycle containing
maximum legal reasoning, function-argument, and assistant-message delta
families, then validates a terminal with three output items and three MiB
aggregate output. The full source-shaped progress/terminal envelope is also
included. Worst-case escaping produces a 19,923,803-byte serialized terminal
data record and a 1,048,573-byte non-output envelope; the strict validator
accepts it and the same record passes the Local framer's joined-data, line, and
frame inequalities. Individual item/delta limits and the maximum progress
envelope are exercised by the same lifecycle and source-envelope tests.

### Framer state, close, and failure cleanup

`BoundedSSEFramer` now clears `_line`, data segments, frame bytes, and joined
data in one central failure path before closing the upstream response. Numeric
peak counters survive for tests; current content-bearing counters are exposed
only as numeric diagnostics and are zero after every parse/overflow,
cancellation, and consumer-close test. The framer still supports LF/CRLF,
arbitrary chunk boundaries, split UTF-8, split delimiters, exact multi-line
`data:` newlines, comments/ignored fields, final EOF dispatch, and `[DONE]`.

The cancellation test now starts a real consumer task on a blocking async byte
stream, waits until the stream is active, cancels the consumer, verifies
`CancelledError` propagation, prompt upstream close, zero current state, task
completion, and no remaining task. Existing parser-error and generator-
`aclose` tests remain. Unsupported content encoding fails before raw iteration.

### Production ceiling evidence

The tests use generated/repeated chunks rather than constructing an all-stream
buffer. Each overflow monkeypatches `json.loads` to fail the test if parsing is
entered. Observed content-free peak statistics were:

| Case | Safe provider code | Peak line | Peak frame | Peak joined data | Peak segments | Current state after failure |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| production line + 1 byte | `local_coding_sse_line_too_large` | 25,296,903 | 25,296,903 | 0 | 0 | all zero |
| production joined data + 1 byte | `local_coding_sse_data_too_large` | 12,434 | 25,311,234 | 25,296,895 | 2,047 | all zero |
| production frame + bounded ignored fields | `local_coding_sse_frame_too_large` | 262,144 | 25,573,378 | 25,296,896 | 2,048 | all zero |
| production segment cardinality + 1 | `local_coding_sse_data_segments_too_many` | 9 | 20,490 | 6,143 | 2,048 | all zero |

The line case isolates the first byte after the exact line ceiling. The joined
case makes the final small data segment the first over-bound contribution. The
frame case reaches exact joined data with 2,048 CRLF data lines, adds the
reviewed ignored-field allowance, and rejects at the first byte beyond the
frame ceiling. The segment case rejects the 2,049th data segment before
retaining it. No case enters JSON parsing or retains oversized state.

Parse failures use only these low-cardinality provider codes:

`local_coding_sse_malformed_chunk`,
`local_coding_sse_content_encoding_unsupported`,
`local_coding_sse_invalid_utf8`, `local_coding_sse_invalid_json`,
`local_coding_sse_json_not_object`, `local_coding_sse_line_too_large`,
`local_coding_sse_frame_too_large`, `local_coding_sse_data_too_large`, and
`local_coding_sse_data_segments_too_many`.

### Gateway accounting and privacy

Fresh loopback PostgreSQL E2E evidence passed both malformed Local Coding
Gateway paths. Before any forwarded/token-bearing event, the existing provider
failure/release law produced a released reservation, failed ledger, and zero
reserved tokens. After a forwarded output delta, the existing estimated
interruption law produced finalized estimated accounting, no success terminal
or `[DONE]`, and zero reserved tokens. The malformed canary was absent from
client errors and ledger metadata. The upstream stream closed through the
adapter/framer path. No raw malformed/oversized content entered logs, metrics,
audit, ledger metadata, OAP evidence, or client errors.

The final b database reconciliation before removal reported 26 finalized and
4 released reservations, zero gateway keys with reserved cost/tokens, and zero
pending accounting ledgers. The explicitly named b database was dropped. The
previous a disposable databases and the b map database were also dropped and
the PostgreSQL inventory confirmed zero remaining `slaif_oap163%` databases.

## Regression and obligation evidence

The independent literal map is
`LOCAL_CODING_SSE_OBLIGATION_TO_TEST_NODE` and its independently literal
required-ID set is `LOCAL_CODING_SSE_REQUIRED_OBLIGATION_IDS` in
`tests/unit/test_local_coding_sse_framing.py`. The contract asserts exact set
equality, no duplicate/unknown/missing IDs, safe test paths, and no anonymous
parameter IDs. It contains 41 required obligation IDs mapped to 34 unique
nodes. Verbose collection found 233 nodes across the framer, strict Codex, and
Responses E2E files; all 34 distinct mapped nodes were directly executed with
`TEST_DATABASE_URL` set and passed, with `missing=[]` and no skips.

The 17 original regression groups remain covered by the map: normal/chunked
streams; byte-wise UTF-8; CRLF; multiline data; comments/ignored fields;
maximum typed event; exact line/frame/joined-data/segment overflows;
unterminated lines; many small data lines; valid and malformed EOF;
provider parse codes; parser error/consumer close/cancellation; many events;
all Objective-162 zero-argument/ordinary function/reasoning/message/usage/
terminal/replay/privacy nodes; content encoding; and pre-/post-output Gateway
accounting. Additional b IDs cover the exact source fixture/full envelope,
corrected arithmetic/rationales, state clearing, real task cancellation, and
each production ceiling.

Final local counts:

| Suite | Collected | Passed |
| --- | ---: | ---: |
| `test_local_coding_sse_framing.py` | 28 | 28 |
| `test_local_coding_server_module.py` | 40 | 40 |
| `test_provider_streaming_sse.py` | 2 | 2 |
| `test_responses_codex_streaming_tools.py` | 179 | 179 |
| `test_v1_responses_quota.py` | 82 | 82 |
| OAP, agentic, and provider governance | 13 | 13 |
| focused total | 344 | 344 |
| complete Responses official-client E2E on fresh b PostgreSQL | 26 | 26 |
| required PostgreSQL integration files | 3 | 3 |
| distinct mapped-node execution | 34 | 34 |

## Corrected failures and verification commands

- The initial b E2E run found one legitimate source-envelope mismatch in the
  signed Local stream fixture: `store` is not a vLLM 0.27.1
  `ResponsesResponse` field. The test fixture was corrected, the targeted test
  passed, and the complete E2E file passed 26/26 on a new database.
- A first combined manifest execution was accidentally run without
  `TEST_DATABASE_URL`; two E2E nodes skipped. It was not counted as evidence.
  A new map database was created, the same 34 distinct nodes were rerun with
  the safe test URL, and all passed with no skips. That database was dropped.
- The prior a database-retention finding was closed by reconciling and
  dropping every explicitly task-owned a/b database; no unrelated database was
  touched.

The final commands and results were:

```text
/tmp/slaif-gateway-163-venv/bin/python -m pytest -q \
  tests/unit/test_local_coding_sse_framing.py \
  tests/unit/test_local_coding_server_module.py \
  tests/unit/test_provider_streaming_sse.py \
  tests/unit/test_responses_codex_streaming_tools.py \
  tests/unit/test_v1_responses_quota.py \
  tests/unit/test_oap_governance.py \
  tests/unit/test_agentic_client_integration_governance.py \
  tests/unit/test_provider_governance.py
RESULT: 344 passed

TEST_DATABASE_URL=postgresql+asyncpg:///slaif_oap163_b_final_test_1789256417_1796082 \
  /tmp/slaif-gateway-163-venv/bin/python -m pytest -q \
  tests/e2e/test_openai_python_client_responses.py
RESULT: 26 passed

TEST_DATABASE_URL=postgresql+asyncpg:///slaif_oap163_b_final_test_1789256417_1796082 \
  /tmp/slaif-gateway-163-venv/bin/python -m pytest -q \
  tests/integration/test_local_coding_server_module_postgres.py \
  tests/integration/test_provider_diagnostics_postgres.py
RESULT: 3 passed

pytest --collect-only -vv plus independent map parser: 233 collected, 41 required IDs, 34 unique mapped, missing=[]
independent direct mapped execution: 34 passed, zero skipped
Ruff check/format, compileall, JSON fixture validation, git diff --check: PASS
```

No HPC harness, real provider traffic, real email, Local/Qwen/vLLM process,
GPU, protected inference, deployment, release, certification, compliance
action, or Codex evidence-tool action was performed. The referenced source pin
was inspected publicly at the [pinned vLLM response protocol source](https://raw.githubusercontent.com/vllm-project/vllm/6e448d0ea9bf3d88d898b65449ca6dc2aec170ac/vllm/entrypoints/openai/responses/protocol.py).

## Documentation impact and limitations

Updated b contract documentation in `docs/provider-forwarding-contract.md`,
`docs/responses-compatibility.md`, `docs/openai-compatibility.md`,
`docs/accounting.md`, and `docs/streaming-live-burn-margin.md` with the exact
vLLM field set, four-MiB derivation, CRLF frame equation, segment/ignored-field
rationales, failure cleanup, and unchanged accounting law. Existing a
architecture/security/agentic documentation remains in the PR unchanged from
the a report. README remains unchanged because the endpoint/support claim is
unchanged.

This is a static Local-owned transport/resource-boundary qualification using
synthetic byte streams, loopback mocks, and disposable PostgreSQL. It is not a
Local Coding deployment qualification, live vLLM/Qwen/Codex inference
qualification, production certification, security certification, compliance
attestation, provider-invoice truth, release approval, or merge authorization.
The generic non-Local streaming parser and provider paths remain outside this
objective. The finite frame bound is intentionally large enough for the exact
reviewed typed profile but cannot be enlarged by provider/client/route state.

VLLM-0271-FULL-ENVELOPE-ACCEPTED = YES
MAXIMUM-TYPED-EVENT-WITHIN-FRAMER = YES
EXACT-FOUR-MIB-DERIVATION = YES
PRODUCTION-CEILING-OVERFLOW-PROVEN = YES
FAILURE-STATE-CLEARED = YES
REAL-CONSUMER-TASK-CANCELLATION = YES
OBLIGATION-CONTRACT-COMPLETE = YES
UPSTREAM-CLOSE-AND-ACCOUNTING-ACCEPTED = YES
OBJECTIVE-162-LIFECYCLES-REGRESSION-ACCEPTED = YES
TASK-DATABASES-CLEANED = YES
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO

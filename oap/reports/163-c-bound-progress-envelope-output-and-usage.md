# OAP Objective 163-c Immutable Report

RESULT=PASSED

Implementation head SHA: acc88bcf17d383210994f656ca94959a0b2e8b2e
Report publication commit: SELF

## Topology and immutable history

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR: #300, `https://github.com/ulfe-lmi/slaif-api-gateway/pull/300`
- Base branch: `main`
- Activation base: `5ea38325ef3a3ebc69524b4679b795fab0c52935`
- Branch: `oap/163-local-coding-sse-framing-bounds`
- 163-a report/head preserved: `fc39f6874c8239b37e0904f9c966572f6f771695`
- 163-b report/head preserved: `9497c326a0b45762fe34231bc683171bcd4bea94`
- 163-c implementation: `acc88bcf17d383210994f656ca94959a0b2e8b2e`
- 163-c implementation parent: `9497c326a0b45762fe34231bc683171bcd4bea94`
- Final report commit: `SELF`
- PR state at publication: OPEN, not merged
- `oap/active`: `163-c`
- Exact selected order: `oap/orders/163-c-bound-progress-envelope-output-and-usage.md`

The c implementation changes only the authorized strict Responses validator,
the c source fact fixture, the independent Objective-163 obligation map/tests,
the two named contract documents, `oap/active`, and the exact c order. The a
and b reports/orders and all prior implementation history remain unchanged. No
framer constant, Local adapter, provider/client selection, generic provider
path, schema, migration, dependency, configuration, identity/replay path,
accounting law, or protected resource changed.

## Root cause and correction

The 163-b validator removed `response.output` and `response.usage` from the
one-MiB response-envelope serialization calculation, but the strict
`response.created`/`response.in_progress` branch did not validate those two
progress values separately. A model-free witness against the b head therefore
reported:

```text
CREATED_WITH_60MB_UNVALIDATED_OUTPUT_USAGE_ACCEPTED=True
CREATED_WITH_MALFORMED_OUTPUT_USAGE_ACCEPTED=True
```

The c correction is narrow and fail-closed. In the exact strict Codex/Local
progress branch, a present `output` must be exactly `[]`, and a present
`usage` must be exactly `None`. Absent fields remain accepted for existing
minimal fixtures because absence contributes no state. Non-empty output,
mapping/string/null output, non-null or malformed usage, and generated large
values are rejected before any completed-terminal logic. The corresponding
post-correction witness result is false for both acceptance cases, covered by
the named created/in-progress negative nodes.

The completed `response.completed` branch is unchanged: `output` and `usage`
remain independently validated for exact lifecycle, item/call/sequence
relations, cardinality, aggregate semantic bytes, detailed usage, and terminal
consistency. The 32-name vLLM `ResponsesResponse` allowlist and one-MiB
non-output/usage envelope ceiling are unchanged. `error`, `store`, and
`prompt_cache_key` remain denied; transfer/message fields remain absent/null.

## Exact source evidence

The content-free fixture
`tests/fixtures/codex/0.149.0/vllm-0.27.1-responses-progress-emission.json`
pins:

- provider/version: vLLM 0.27.1;
- tag commit: `6e448d0ea9bf3d88d898b65449ca6dc2aec170ac`;
- source file: `vllm/entrypoints/openai/responses/serving.py`;
- source-file SHA-256:
  `628429902ff26b87f86eae1a45297f647f3712d7b421ca9a4866a3fd0f046a5b`;
- fixture SHA-256:
  `f4f83c604dc600d65aefe27b4b6035c334ae17375745d5cbd4fa26854c33f99f`; and
- source fact: the shared initial response is emitted to both created and
  in-progress events with `output=[]`, `status="in_progress"`, and
  `usage=None`.

The b fixture remains pinned and tested with source-file SHA-256
`6aeabf69dbc924b238172b505730a8a8321b50a819891d2a72a690963c970fba` and
fixture SHA-256
`fb297b6425343c94145a1ffbb63bfbd1a41dfbbcead1e5549f206b169657aeec` for the
exact 32 response-envelope fields/type/default classes. Neither fixture imports
or initializes vLLM or a model.

## Progress-state audit

All 32 response-envelope fields are audited across the three strict states.
For created/in-progress, the source-shaped fields are full default/null
envelopes; present output is empty and usage is null, while the four
transfer/raw-message fields are absent/null. For completed, output and usage
are excluded from the envelope byte sum only because their independent strict
validators bound them. Every other response field remains within the exact
allowlist and serialized one-MiB envelope ceiling. Unknown names are denied.

The positive created and in-progress tests each use the full source-shaped
default/null envelope. The in-progress node first establishes the required
created state, then validates the full in-progress event. The negative matrix
contains seven explicitly named mutations for each state: non-empty list,
mapping, string, null output, non-null mapping usage, malformed string usage,
and a generated 30-MB output value. Each negative node verifies the supplied
canary is absent from validator evidence.

The unchanged maximum proof still drives a valid 64-event strict lifecycle,
validates the three-item/three-MiB terminal against the exact four-MiB
derivation, and passes the same terminal through the bounded Local framer.

## Regression and obligation contract

The independent literal map is
`LOCAL_CODING_SSE_OBLIGATION_TO_TEST_NODE`, and the independently literal
required-ID set is `LOCAL_CODING_SSE_REQUIRED_OBLIGATION_IDS`, both in
`tests/unit/test_local_coding_sse_framing.py`. Exact set equality, no duplicate
or unknown IDs, safe test paths, and no anonymous parameter IDs are asserted.
The map contains 58 required obligation IDs and 51 unique mapped nodes,
including separately named created/in-progress positive and all 14 negative
progress siblings.

Verbose collection of the framer/Codex/Responses E2E map set found 250 nodes;
all 51 distinct mapped nodes were directly executed with a safe disposable
`TEST_DATABASE_URL`, with zero skips and `missing=[]`.

The original 17 Objective-163 regression groups remain covered: normal and
fragmented streams; CRLF and multiline data; ignored fields; exact four-MiB
typed maximum; line/frame/joined-data/segment limits; unterminated and
malformed EOF; parse-error codes; parser error/close/cancellation; incremental
many-event state; Objective-162 lifecycle/replay/privacy; content encoding;
and pre-/post-output accounting. Additional c nodes cover the exact serving
source fact, created/in-progress positives, every progress negative sibling,
and the full excluded-field audit.

Final local counts:

| Suite | Collected | Passed |
| --- | ---: | ---: |
| `test_local_coding_sse_framing.py` | 28 | 28 |
| `test_local_coding_server_module.py` | 40 | 40 |
| `test_provider_streaming_sse.py` | 2 | 2 |
| `test_responses_codex_streaming_tools.py` | 196 | 196 |
| `test_v1_responses_quota.py` | 82 | 82 |
| OAP, agentic, and provider governance | 13 | 13 |
| focused total | 361 | 361 |
| complete Responses official-client E2E on fresh c PostgreSQL | 26 | 26 |
| required PostgreSQL integration files | 3 | 3 |
| distinct mapped-node execution | 51 | 51 |

The exact final commands were the focused unit/governance command, the full
`tests/e2e/test_openai_python_client_responses.py` command, the two required
PostgreSQL integration files, and the independent verbose collection/direct
execution harness recorded by the c order. Ruff format/check, compilation,
fixture JSON validation/digests, and whitespace checks passed.

## Accounting, cleanup, and safety

The fresh c PostgreSQL database reconciled to 26 finalized and 4 released
reservations, zero gateway keys with reserved cost/tokens, and zero pending
accounting ledgers. It was dropped by exact name. The PostgreSQL inventory then
confirmed zero remaining `slaif_oap163%` databases. The established Gateway
pre-output release and post-output estimated-interruption laws remain
unchanged; no raw response/output/usage content enters accounting metadata,
diagnostics, logs, metrics, audit rows, OAP evidence, or client errors.

One routine test correction occurred: the first isolated in-progress positive
node was attempted without its required preceding created state. The test was
corrected to establish that state explicitly; the complete progress matrix and
full focused suite then passed. No product defect, protected call, real
provider request, Local/Qwen/vLLM process, GPU, real email, deployment,
release, certification, compliance, or Codex evidence-tool action occurred.

## Implementation-head GitHub checks

All ten required checks were observed SUCCESS on implementation head
`acc88bcf17d383210994f656ca94959a0b2e8b2e`:

- Analyze (javascript-typescript)
- Analyze (python)
- Analyze Python
- CodeQL
- Docker Compose smoke
- Documentation hygiene
- OpenAI-compatible E2E tests
- Playwright browser smoke
- PostgreSQL integration tests
- Unit, lint, and migration head

No required implementation-head check was skipped, pending, cancelled,
blocked, or missing. Strategic must independently recheck the final report
head before any merge decision; coding has not merged or enabled auto-merge.

## Documentation impact and limitations

Updated `docs/provider-forwarding-contract.md` and
`docs/responses-compatibility.md` to document the source-emitted progress
`output=[]`/`usage=null` contract, absent-field compatibility, and the
separate completed validators. The a/b architecture, security, accounting,
streaming, compatibility, and agentic documentation remains unchanged from
the earlier immutable implementation history. README remains unchanged.

This is a static exact-pair validator/resource-boundary qualification using
model-free source facts, synthetic streams, loopback mocks, and disposable
PostgreSQL. It is not live vLLM/Qwen/Codex inference qualification, Local
deployment qualification, production certification, security certification,
compliance attestation, provider-invoice truth, release approval, or merge
authorization. Generic non-Local streaming paths remain outside this focused
continuation. The exact public source used for the progress fact is the
[pinned vLLM serving source](https://raw.githubusercontent.com/vllm-project/vllm/6e448d0ea9bf3d88d898b65449ca6dc2aec170ac/vllm/entrypoints/openai/responses/serving.py).

PROGRESS-OUTPUT-EMPTY-ONLY = YES
PROGRESS-USAGE-NULL-ONLY = YES
ALL-EXCLUDED-RESPONSE-FIELDS-BOUNDED = YES
VLLM-0271-PROGRESS-SOURCE-PINNED = YES
MAXIMUM-TYPED-EVENT-WITHIN-FRAMER = YES
OBJECTIVE-163-REGRESSION-ACCEPTED = YES
TASK-DATABASES-CLEANED = YES
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO

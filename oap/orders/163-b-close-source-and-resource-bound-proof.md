# OAP Work Order — 163-b

PR mode: `AMEND_EXISTING_PR`

## Objective

Complete Objective 163 on existing PR #300 in one consolidated correction.
Preserve the sound Local-owned raw-byte framer and Gateway accounting behavior,
but repair every exact source/derivation/resource-evidence defect identified by
strategic review. Do not publish another intermediate engineering report or
request another suffix: resolve all routine findings, rerun the full bounded
gate, self-review skeptically, and report only the final merge candidate.

No protected inference, Local/Qwen mutation, or generic provider rewrite.

## Reconciled state

- Repository `ulfe-lmi/slaif-api-gateway`; PR #300 is the unique Objective-163
  PR, OPEN/non-draft/mergeable; branch
  `oap/163-local-coding-sse-framing-bounds`; base/main
  `5ea38325ef3a3ebc69524b4679b795fab0c52935`.
- Starting immutable 163-a report/current PR head:
  `fc39f6874c8239b37e0904f9c966572f6f771695`.
- 163-a implementation parent:
  `e6f26db8ef27eb0657aaaad1d4b0571b97eb0e4b`.
- 163-a report-only SELF topology and exact strategic order/active bytes are
  verified; all implementation paths are within the a-order allowlist.
- Retain: incremental raw identity-byte parsing, LF/CRLF and chunk splits,
  bounded line/frame/data state, strict UTF-8/object JSON, `[DONE]`, final EOF
  dispatch, safe provider error codes, Local-only integration, and the proven
  pre-output release/post-output estimated-interruption accounting law.
- Do not rewrite 163-a report or create a new PR.

## Finding 1 — exact vLLM 0.27.1 response envelope is currently broken

163-a added a response-envelope allowlist but did not derive it from the exact
vLLM model. vLLM `v0.27.1`, tag commit
`6e448d0ea9bf3d88d898b65449ca6dc2aec170ac`, file
`vllm/entrypoints/openai/responses/protocol.py`, SHA-256
`6aeabf69dbc924b238172b505730a8a8321b50a819891d2a72a690963c970fba`,
defines `ResponsesResponse` with these 32 serialized model fields:

```text
id created_at incomplete_details instructions metadata model object output
parallel_tool_calls temperature tool_choice tools top_p background
max_output_tokens max_tool_calls previous_response_id prompt reasoning
service_tier status text top_logprobs truncation usage user presence_penalty
frequency_penalty kv_transfer_params ec_transfer_params input_messages
output_messages
```

Pydantic `model_dump(mode="json", by_alias=True)` does not implicitly omit
default/null fields. The a allowlist is missing legitimate fields including
`background`, `prompt`, `top_logprobs`, `user`, both penalties, transfer params,
and input/output messages, while admitting names not defined by this exact
model (`error`, `store`, and `prompt_cache_key`). It would reject the reviewed
provider's normal full progress/completed envelopes.

Fix the allowlist/field-state contract from exact source. Add a canonical
content-free source fixture such as
`tests/fixtures/codex/0.149.0/vllm-0.27.1-responses-response-envelope.json`
pinning tag/commit/file hash, exact field names, and safe type/null/default
classes. Test its digest and exact equality to the production allowlist.

At minimum, prove a full source-shaped `response.created`,
`response.in_progress`, and `response.completed` envelope with every emitted
default/null field passes the exact strict validator. Require
`input_messages`, `output_messages`, `kv_transfer_params`, and
`ec_transfer_params` to be absent/null on the accepted Gateway path unless
source plus current Local request configuration proves a bounded non-null
shape is intentionally supported. Remove unreviewed response-only names.
Unknown names and over-bound values remain denied.

Do not import/initialize vLLM or a model. Public source inspection and synthetic
source-shaped values are sufficient.

## Finding 2 — the semantic maximum is four MiB per actual event, not five

163-a sums a reasoning-summary event together with a terminal response that
contains reasoning/function/message output, then calls the result one semantic
event. Those values are not co-resident in one accepted exact-pair SSE event.
The strict Local profile does not accept a non-empty reasoning summary inside
the terminal reasoning output item; its source lifecycle has an empty summary.
The a “maximum-event” test feeds only the framer and constructs a terminal
shape the typed validator rejects.

For the current exact profile, derive the maximum of actual event families:

- an individual delta/done/item event is at most the existing one-MiB
  semantic item/cumulative ceiling;
- a completed terminal may contain at most three accepted output items with at
  most three MiB aggregate content/arguments;
- its non-output/usage envelope is at most one MiB; therefore
- the maximum co-resident semantic event budget is four MiB.

Unless a different exact-source proof establishes another co-resident shape,
set:

```text
MAX_CODEX_TYPED_RESPONSE_OUTPUT_ITEMS = 3
MAX_CODEX_TYPED_RESPONSE_OUTPUT_BYTES = 3 * 1,048,576
MAX_CODEX_TYPED_RESPONSE_SEMANTIC_BYTES = 4 * 1,048,576
```

Remove the new generic reasoning-summary retention/accounting changes from a
unless independently necessary for the exact Local profile; a separate summary
event already fits below the four-MiB event ceiling. Keep the existing semantic
validator strict and content-minimizing.

Replace the synthetic maximum test with real typed validation:

- drive a valid exact response lifecycle establishing up to the permitted
  reasoning/function/message item states;
- use existing per-delta limits to accumulate maximum legal item payloads;
- build a source-shaped terminal with empty reasoning summary, three valid
  output items, three MiB aggregate output, and a one-MiB bounded envelope;
- require the exact `ResponsesStreamEventValidator` to accept it; and
- serialize that same accepted terminal using worst-case escaping, then require
  the framer's joined-data/line/frame inequalities to contain it.

Also cover the maximum progress envelope and maximum individual item/delta
families. A framer-only JSON parse is not proof that a typed event is valid.

## Finding 3 — exact frame arithmetic and segment rationale

`_joined_data_bytes` already includes the one inserted newline between data
segments. The a formula adds those newlines again. For `N` CRLF `data:` lines,
the exact maximum raw contribution is:

```text
sum(value bytes) + N * len("data: \r\n")
= joined_data_bytes - (N - 1) + N * 8
```

Then add only the explicitly reviewed ignored-field allowance and blank CRLF
delimiter. If the corrected four-MiB design and current allowances remain, the
expected constants are:

```text
joined data / json input = 25,296,896
line = 25,296,903
frame = 25,573,379
```

Use code expressions and tests for the equation, not copied literals. Update
all docs atomically.

Tie the 2,048 data-segment limit to an explicit reviewed rationale. The exact
vLLM producer emits one JSON data record per event; multi-line data support is
compatibility tolerance. If retaining 2,048, express and document it as a
finite conservative allowance derived from the 64-part semantic cardinality
times a named 32-lines-per-part framing allowance, and prove provider/client/
route data cannot raise it. Do the same for the 256-KiB ignored-field allowance
(for example, an explicit multiple of an existing semantic delta/item bound).
Do not leave either as an unexplained magic number.

## Finding 4 — clear retained content on every failure

The a framer closes the upstream response on exceptions but does not clear its
current `_line`/data-segment buffers when UTF-8/JSON/overflow/cancellation
raises. A caller retaining the framer/generator can therefore retain a complete
bounded malformed frame after failure.

Add one central failure cleanup path that clears all content-bearing current
line/frame/data state before or while closing the response, preserves numeric
peak statistics, and re-raises the original exception/cancellation. Expose
content-free current-state byte/segment counters if needed for tests. Prove
every parse/overflow error and cancellation leaves current retained bytes and
segments at zero, while peak counters remain within configured ceilings.

## Finding 5 — test real consumer-task cancellation

The a cancellation test uses an upstream iterator that raises
`CancelledError`; it does not cancel a consumer task blocked inside the byte
stream. Add a blocking fake stream, start actual consumption in an asyncio
task, wait until iteration is active, cancel that consumer task, require the
same `CancelledError` to propagate, and prove prompt response/stream close,
zero retained content state, and no background task remains. Keep the existing
generator-`aclose` and parser-error close tests.

## Finding 6 — exercise the actual production ceilings

The a one-byte-over cases use only reduced test limits. Keep fast small-limit
coverage, but also incrementally stream exact production-bound cases without
prebuilding an all-stream buffer:

- a valid source-shaped typed event close to the real joined-data/line/frame
  ceiling succeeds;
- a production line rejects on the first byte beyond
  `MAX_SSE_LINE_BYTES`;
- production joined data rejects on the first byte beyond
  `MAX_SSE_JOINED_DATA_BYTES` without entering `json.loads`;
- a production frame made from bounded comments/ignored fields plus data
  rejects on the first byte beyond `MAX_SSE_FRAME_BYTES`; and
- production segment cardinality rejects at `MAX_SSE_DATA_SEGMENTS + 1` while
  byte state remains bounded.

Use chunk generators/repeated chunks to keep the test producer itself bounded.
Instrument/monkeypatch JSON parsing where needed to prove overflow happens
before parse. Record safe numeric peaks only.

## Finding 7 — make the obligation contract independent and exact

The a file has one mapping and asserts only that it is non-empty/path-prefixed.
It has no independent literal required-ID set, so omissions cannot be detected.

- Add a separately literal required obligation-ID set and require exact set
  equality, no duplicate/unknown/missing IDs, no anonymous parameter IDs, and
  safe paths.
- Expand it for every b finding above: exact source fields/full envelope,
  typed maximum event/progress/item families, corrected arithmetic/rationales,
  failure-state clearing, actual task cancellation, and each production limit.
- Outside pytest, collect every mapped exact node and mechanically require
  `missing=[]`; execute all distinct mapped nodes. Do not map one parameterized
  sibling as proof of another.

## Finding 8 — clean the disposable database

The a report says its final disposable PostgreSQL database was retained. Drop
that exact task-owned database after reconciling it, create fresh uniquely named
databases for b verification, and drop/confirm absence of every a/b task-owned
database before report publication. Never touch any other database.

## Acceptance and verification

The final result must satisfy all original 163-a requirements plus every b
finding. Run:

- complete framer, Local adapter, provider-SSE, strict Codex stream, Responses
  quota, and relevant governance test files;
- all exact Objective-162 zero/ordinary function, reasoning/message/terminal,
  replay/privacy regressions;
- complete Responses official-client E2E on a fresh disposable PostgreSQL
  database;
- Local Coding/provider-diagnostics PostgreSQL integration with actual
  execution;
- independent verbose collection and direct execution of every mapped node;
- pinned Ruff check/format, compilation, fixture JSON/digest, whitespace,
  allowed-path, source-pin, no-secret/no-content, and task-resource cleanup
  checks.

Require every normal GitHub check SUCCESS on the b implementation head before
a PASSED report; strategic requires every check again on the immutable report
head before merge. Do not run the HPC harness, real Codex verifier, Local/Qwen,
protected inference, or real provider traffic.

## Exact allowed paths

Only these may change in b:

- `app/slaif_gateway/modules/servers/local_coding/sse_framing.py`
- `app/slaif_gateway/providers/streaming.py`
- `tests/fixtures/codex/0.149.0/vllm-0.27.1-responses-response-envelope.json`
- `tests/unit/test_local_coding_sse_framing.py`
- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/e2e/test_openai_python_client_responses.py`
- `AGENTIC_CLIENT_INTEGRATION.md`
- `docs/module-architecture.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`
- `docs/openai-compatibility.md`
- `docs/compatibility-matrix.md`
- `docs/security-model.md`
- `docs/accounting.md`
- `docs/streaming-live-burn-margin.md`
- `oap/active`
- `oap/orders/163-b-close-source-and-resource-bound-proof.md`
- `oap/reports/163-b-close-source-and-resource-bound-proof.md`

The accepted adapter integration and provider error/accounting implementation
remain unchanged unless a b test proves a narrowly necessary correction; if so,
`app/slaif_gateway/modules/servers/local_coding/adapter.py` is additionally
authorized only for that exact fix and must be explained. Integration test
files are verification-only. No other app/test/doc/config/schema/migration/
dependency/CI/client-module/server-identity/historical OAP/Local/Qwen path may
change.

## Non-goals and hard boundaries

- No valid lifecycle relaxation, event rewriting, whole-response buffering,
  generic OpenAI/OpenRouter streaming change, route-configurable bound increase,
  16-KiB policy, or acceptance-harness policy.
- No Local/Qwen/provider/model/GPU/service/profile/credential/network/protected
  action; no production, release, deploy, certification, or compliance claim.
- No schema, dependency, endpoint, hosted-tool, identity, replay, pricing, quota,
  retention, or content-storage expansion.
- No coding merge/auto-merge, extra PR, rewritten a report, or another
  intermediate suffix/report for routine engineering.

## Immutable report

After skeptical self-review and complete correction, publish exactly
`oap/reports/163-b-close-source-and-resource-bound-proof.md` with
`RESULT=PASSED|FAILED`, literal implementation head, and
`Report publication commit: SELF`. A PASSED report requires all findings and
original requirements solved, every required local/CI check successful, all
task DBs/resources cleaned, and no unresolved engineering defect. Final commit
is report-only with implementation first parent and remote PR #300 head before
response `OK`.

Report exact topology/scope; source fixture/digest/full 32-field result; typed
maximum-event construction and actual validator success; corrected numeric
derivation/equations/rationales; production overflow peaks and pre-JSON proof;
failure-state clearing/cancel/close; 17-group plus b obligation mapping,
collection/execution and `missing=[]`; E2E/PostgreSQL accounting/privacy;
Objective-162 regressions; all corrected failures; CI; docs; cleanup; and limits.

Required labels:

```text
VLLM-0271-FULL-ENVELOPE-ACCEPTED = YES|NO
MAXIMUM-TYPED-EVENT-WITHIN-FRAMER = YES|NO
EXACT-FOUR-MIB-DERIVATION = YES|NO
PRODUCTION-CEILING-OVERFLOW-PROVEN = YES|NO
FAILURE-STATE-CLEARED = YES|NO
REAL-CONSUMER-TASK-CANCELLATION = YES|NO
OBLIGATION-CONTRACT-COMPLETE = YES|NO
UPSTREAM-CLOSE-AND-ACCOUNTING-ACCEPTED = YES|NO
OBJECTIVE-162-LIFECYCLES-REGRESSION-ACCEPTED = YES|NO
TASK-DATABASES-CLEANED = YES|NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

Strategic independently verifies and merges only the final, exact report head.
No downstream protected handoff follows this objective.

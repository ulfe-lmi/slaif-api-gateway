# OAP Work Order — 163-a

PR mode: `CREATE_NEW_PR`

## Objective

Implement and qualify a bounded incremental SSE decoder/framer for the
production `local-coding-v1` upstream path so line, frame, joined data, UTF-8,
and JSON parsing memory are all finitely bounded before the typed Responses
validator runs.

This is a new hardening objective. Do not reopen Objective 162, alter valid
Codex/vLLM lifecycle semantics, modify Local/Qwen, or use protected inference.

Engineering failures discovered during this round are work to solve within
163-a. Continue through root-cause analysis, implementation, regression
failures, and corrections before publishing the immutable report. Do not stop,
publish an intermediate BLOCKED/NO-GO report, or request a suffix merely for a
routine defect, parser complication, test failure, or implementation decision.
Only a genuine external authority/safety boundary permits escalation.

## Business and security reason

The current Local Coding adapter uses `httpx.Response.aiter_lines()`, appends
every decoded line to `pending_lines`, waits for a blank delimiter, then calls
`parse_sse_lines`, joins all `data:` values, and finally calls `json.loads`.
That sequence permits one unbounded line, one unbounded multi-line frame, one
unbounded joined payload, or an unterminated EOF frame to consume memory before
the typed validator can apply its semantic limits. Local's byte proxy does not
close this Gateway-side availability gap.

The fix belongs at the Gateway transport/framing boundary. It must preserve
valid streaming without buffering the complete response and must fail through
the existing provider-error/accounting law without leaking upstream content.

## Reconciled authoritative state

- Repository: `ulfe-lmi/slaif-api-gateway`; default/base branch `main`.
- Exact activation base/current remote main:
  `5ea38325ef3a3ebc69524b4679b795fab0c52935`, normal merge of Objective 162 /
  PR #299. Parents are prior main `d142fd7...` and final 162-c report
  `923270d...`; tree `1ede9cea41c566b141441ad9a3122133d5fc1ff6`.
- Objective 162 is terminally merged. Shared `oap/active` intentionally remains
  terminal `162-c`; timing-ledger resolution and Local handback are complete.
- All normal PR-head and post-merge main checks for Objective 162 succeeded.
- No Objective-163 PR or `oap/163-*` remote branch exists.
- Existing open PRs #291, #250, and #224 are unrelated; do not reuse or modify
  them. PR #291 is the old Objective-155 evidence branch and remains DIRTY.
- `main` has no configured branch protection; this order still requires the
  complete strategic check/review gate.
- The only release remains prerelease `v0.1.0-rc.1`. No release/deployment/
  certification/compliance action is authorized.
- The shared checkout is detached and contains prior strategic-authored OAP
  activation files. Preserve it and every unrelated worktree/catalog artifact;
  create a clean coding-owned Objective-163 branch/worktree from remote main.
- Create exactly one PR. Suggested branch:
  `oap/163-local-coding-sse-framing-bounds`; suggested title:
  `OAP 163: Bound Local Coding SSE framing before parsing`.

## Required reading and exact current defect

Read current `AGENTS.md`, `OAP-COMMUNICATION-coding-agent.md`,
`AGENTIC_CLIENT_INTEGRATION.md`, this order, final 162-c report, and the current
module/Responses/provider/security/accounting contracts. Inspect at minimum:

- `app/slaif_gateway/modules/servers/local_coding/adapter.py`;
- `app/slaif_gateway/providers/streaming.py`;
- Local Coding route/module contracts and response-gateway accounting flow;
- exact vLLM 0.27.1 Responses response/event models and the existing source
  fixtures/pins; and
- all affected unit/integration/E2E tests.

Verified current facts to re-confirm:

- `LocalCodingAdapter._stream_response_events` uses unbounded
  `response.aiter_lines()` and `pending_lines`.
- `parse_sse_lines` accumulates `data_lines`, joins them with newline, and then
  invokes `json.loads`; it has no size/count contract.
- HTTPX 0.28.1's `aiter_lines` uses its own incremental line decoder, so an
  arbitrarily long unterminated line may accumulate before adapter code sees a
  line.
- Typed stream limits currently include 65,536-byte individual deltas,
  1,048,576-byte item/cumulative text, 262,144-byte encrypted-reasoning items,
  1,048,576-byte cumulative encrypted reasoning, 64 content parts, bounded
  identifiers/indexes, and finite detailed-usage arrays.
- Full vLLM Responses progress/completed events may include a response envelope
  echoing bounded request facts such as instructions/tools as well as terminal
  output and usage. Raw JSON escaping and SSE prefixes/delimiters add bytes
  above semantic UTF-8 limits.
- Audit any currently accepted optional/envelope value that is not itself type/
  size/cumulatively bounded (including response-envelope fields and optional
  obfuscation). An accidental unbounded semantic allowance is not a reason to
  choose an enormous frame limit.

## Bound derivation contract

Do not copy the old acceptance observer's arbitrary 16 KiB event limit or any
other unexplained constant.

Before finalizing code, produce a checked derivation table in source comments,
tests, and documentation that accounts for:

- each intentionally supported Local/Codex event family;
- maximum semantic payload bytes and part/item cardinality;
- the exact vLLM/OpenAI response-envelope fields intentionally accepted;
- worst-case JSON escaping expansion from bounded UTF-8 content;
- bounded IDs, field names, punctuation, SSE `data:` prefixes, inserted
  multi-line newlines, comments/ignored fields, delimiter, and fixed structural
  overhead;
- maximum line bytes, total wire-frame bytes, and joined data bytes separately;
  and
- the largest value `json.loads` may receive and the peak decoder-owned state.

The hard ceiling must be static/reviewed and cannot be raised by a provider,
client, route, response header, or environment variable. A route value may
only narrow it if source review genuinely requires that feature; do not add
configurability merely for convenience.

If the current typed validator permits an unbounded ignored field or a
cardinality/cumulative combination incompatible with a defensible finite frame
bound, tighten that semantic contract coherently to the actual reviewed
vLLM/OpenAI profile. Do not weaken typed validation, silently drop legitimate
events, invent a provider exception, or raise the transport limit to preserve
accidental unbounded acceptance. Any tightening must have explicit positive and
negative tests and honest documentation.

The final tests must mechanically prove that every intentionally maximum-sized
semantic event serializes within the framing/data/line ceilings under
worst-case escaping, and that the one-byte-over cases fail before oversized
state is retained or JSON parsing is entered.

## Required implementation behavior

### 1. Bounded incremental byte framing

Replace the Local adapter's `aiter_lines`/`pending_lines` path with a focused
incremental byte framer (a small Local-owned helper/module is preferred over a
generic framework unless shared code is genuinely necessary).

It must:

- consume streaming bytes incrementally and scan network chunks for LF without
  first constructing an unbounded text line;
- support LF and CRLF, arbitrary network chunk boundaries, a delimiter split
  across chunks, and a UTF-8 code point split across chunks;
- enforce the line ceiling before extending retained line state;
- enforce total wire-frame and joined data ceilings before retaining another
  segment/newline or creating a joined payload;
- keep comment/ignored-field bytes within the frame bound even though their
  content is not forwarded;
- avoid per-line list overhead that can grow independently of byte bounds (for
  example millions of empty `data:` lines); bound both bytes and any retained
  segment/count state;
- validate UTF-8 strictly only after a complete bounded line/payload is
  available, rejecting malformed/incomplete sequences rather than replacement
  decoding;
- call `json.loads` only on a bounded complete data string;
- yield/discard one event at a time and reset all event-local state, never
  retaining an all-stream history; and
- expose only fixed numeric/debug state needed for tests, never content.

Account for HTTP content decoding. Either consume identity/raw bytes and fail
closed before iteration on unsupported `Content-Encoding`, or implement
incremental decompression whose decoded output is bounded before allocation/
retention. Do not rely on an API that may inflate compressed input into an
unbounded decoded chunk before the framer checks it. Preserve the reviewed
Local Coding response behavior.

### 2. SSE compatibility

Preserve the current data-only OpenAI-compatible SSE contract:

- `data:` with optional one following space;
- multiple `data:` lines joined with exactly one newline;
- comment lines beginning `:` ignored semantically but counted for framing;
- empty LF/CRLF line dispatches an event;
- other SSE fields remain ignored as currently documented, but are bounded;
- complete final pending data event at EOF is dispatched without requiring a
  blank delimiter;
- comment/ignored-only EOF state produces no event;
- `[DONE]` remains recognized where this path emits it;
- emitted `ParsedSSEEvent.data`, normalized `raw_event`, JSON mapping and
  provider usage/request-ID behavior remain compatible for valid input; and
- no whole-response buffering or event rewriting beyond the existing
  data-only normalization occurs.

Define incomplete/malformed EOF precisely. A complete bounded final `data:`
JSON event may succeed; an overlong line/frame/data value, invalid UTF-8,
invalid/non-object JSON (except exact `[DONE]`), dangling invalid bytes, or an
otherwise malformed data event must fail safely.

### 3. Provider error, close, and accounting law

Map framing/UTF-8/JSON failures to `ProviderResponseParseError` or the closest
existing safe provider-domain abstraction with closed low-cardinality codes
that distinguish at least malformed versus line/frame/data overflow where that
distinction is useful. Messages/errors/diagnostics must not contain raw lines,
JSON, IDs, text, arguments, reasoning, credentials, endpoints, or arbitrary
exception strings.

Ensure the upstream response/byte stream is closed promptly on overflow,
malformation, generator cancellation, and consumer disconnect. Preserve
`CancelledError` and normal async-generator close behavior; do not swallow
cancellation or leave background tasks/listeners.

Through the actual Gateway stream orchestration, prove:

- failure before any forwarded/token-bearing event releases/finalizes the
  reservation through the existing provider-failure law and leaves zero
  pending/reserved state;
- failure after a forwarded/token-bearing event follows existing estimated
  interrupted accounting, emits only the established safe client error, never
  a success terminal, and leaves zero pending state; and
- raw malformed/oversized content never enters logs, metrics, audit, ledger
  metadata, OAP evidence, or client errors.

Do not change PostgreSQL schema/accounting semantics or make Redis authoritative.

### 4. Typed validator consistency only where required

Do not relax, bypass, reorder, or move the typed Responses validator. The
framer is an earlier resource boundary, not a substitute for semantic
validation.

If bound derivation requires tightening unbounded response-envelope,
obfuscation, terminal-output cardinality, or cumulative semantic fields, make
the smallest profile-correct change in `providers/streaming.py`. Preserve the
exact Codex 0.149 module-version-4 zero-argument lifecycle, ordinary function
lifecycle, reasoning/message lifecycle, replay candidates, usage checks, and
all default/other-profile denials. No client/server module version bump is
needed when valid wire behavior is unchanged; if source proves otherwise,
document and test the exact reason rather than silently changing identity.

## Mandatory regression matrix

Use only synthetic `httpx`/fake async byte streams, loopback mocks, and
disposable PostgreSQL. No Local process, Qwen, model, GPU, protected endpoint,
or real provider call.

Tests must prove at least:

1. a normal valid Responses SSE stream across ordinary chunks;
2. one valid event fragmented byte-by-byte or into very small chunks;
3. CRLF framing, including a split CR/LF boundary;
4. multi-line `data:` reconstructed with exact newline semantics;
5. comments before/between data lines and ignored fields remain compatible and
   frame-bounded;
6. a fully valid typed event near the justified framing ceiling succeeds;
7. exact one-byte-over line, frame, and joined-data cases reject before
   oversized retention/JSON parsing;
8. an extremely long unterminated line rejects at the first over-bound byte;
9. many individually small data lines whose combined frame/data exceeds the
   bound reject with bounded retained segment/count state;
10. EOF dispatches a complete valid final pending event;
11. EOF with malformed JSON, invalid/dangling UTF-8, or incomplete framing
    fails safely, while comment/ignored-only EOF produces no event;
12. invalid UTF-8, invalid JSON, and non-object JSON use the closed provider
    parse-error contract without echo;
13. cancellation, consumer `aclose`, and parser error close the upstream stream
    promptly and leave no task/resource running;
14. many valid bounded events are yielded incrementally and decoder-owned peak
    state stays within one event/line/data bound rather than total stream size;
15. exact Objective-162 Codex/vLLM zero-argument and ordinary function,
    reasoning, message, usage, terminal, replay, and privacy tests continue to
    pass;
16. unsupported content encoding or bounded decompression behavior is tested
    according to the selected design; and
17. pre-output and post-output malformed/oversized Gateway paths preserve the
    correct zero-pending accounting and safe client error behavior.

Use a literal obligation-to-test-node map with stable descriptive parameter
IDs. Collect and execute every mapped node; require independent required/mapped
set equality, no anonymous IDs, and `missing=[]`. Do not claim one generic node
proves multiple unexecuted parameter siblings.

## Verification economy and full gate

Run locally:

- complete new framer/Local adapter tests;
- complete `tests/unit/test_local_coding_server_module.py`,
  `tests/unit/test_provider_streaming_sse.py`, and affected typed-validator/
  Responses quota files;
- exact Objective-162 zero/ordinary function regression nodes plus relevant
  reasoning/message/terminal nodes;
- complete `tests/e2e/test_openai_python_client_responses.py` on fresh
  disposable PostgreSQL;
- relevant Local Coding/PostgreSQL streaming/accounting integration tests with
  actual execution, not skips;
- OAP/module/agentic governance;
- pinned Ruff check/format for changed Python, compilation, JSON validation,
  `git diff --check`, allowed-path and no-secret scans.

Normal GitHub CI is the full Gateway gate. Require every normal check SUCCESS
on the implementation head before a PASSED report; strategic independently
requires every check again on the immutable report head before merge. Do not
run the HPC 128-worker harness, protected inference, or unrelated real-client
verifiers. Skipped/pending/missing/cancelled/blocked/not-run required evidence
is not a pass.

## Exact allowed paths

Only these paths may change:

- `app/slaif_gateway/modules/servers/local_coding/adapter.py`
- `app/slaif_gateway/modules/servers/local_coding/sse_framing.py`
- `app/slaif_gateway/providers/streaming.py`
- `tests/unit/test_local_coding_server_module.py`
- `tests/unit/test_local_coding_sse_framing.py`
- `tests/unit/test_provider_streaming_sse.py`
- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/unit/test_v1_responses_quota.py`
- `tests/integration/test_local_coding_server_module_postgres.py`
- `tests/integration/test_provider_diagnostics_postgres.py`
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
- `README.md`
- `oap/active`
- `oap/orders/163-a-bound-local-coding-sse-framing.md`
- `oap/reports/163-a-bound-local-coding-sse-framing.md`

Create the new framer and its test file only if that separation improves the
focused design; otherwise keep the implementation in the adapter and omit the
unused files. Update only contracts whose behavior/limits/error semantics
change. README may remain unchanged only with the exact required report reason
that the top-level endpoint/support claim is unchanged.

No configuration, route-contract, schema/migration, dependency/lock, provider
adapter outside Local Coding, client module/version/fixture, Local server
identity/signing, admin/CLI, deployment, CI workflow, Objective-160/161/162
verifier/evidence, or historical order/report may change.

## Non-goals and hard boundaries

- No Local Coding repository, Qwen/vLLM, model, service, profile, credential,
  port, network, firewall, VPN, or protected-system mutation.
- No real provider/protected inference or repeated diagnostic.
- No generic streaming rewrite for OpenAI/OpenRouter; their separate
  `aiter_lines` paths are outside this objective.
- No whole-response buffering, provider-event rewriting, typed-validator
  weakening, arbitrary 16 KiB production limit, or acceptance-harness policy.
- No new package/dependency, dynamic module/plugin system, authority expansion,
  hosted tool, endpoint, identity/replay fallback, pricing/quota/schema change,
  content storage, release, deploy, certification, compliance claim, coding
  merge, or auto-merge.

## Publication and immutable report

Commit the unchanged strategic 163-a order and exact `oap/active` with the
bounded implementation on the new branch. Create exactly one Objective-163 PR.
Before reporting, perform a skeptical self-review of the production diff,
boundary derivation, all 17 regression groups, resource close/accounting, docs,
and actual test collection; fix every routine defect on the same branch.

Publish exactly `oap/reports/163-a-bound-local-coding-sse-framing.md` once with
`RESULT=PASSED|FAILED`, literal implementation head, and
`Report publication commit: SELF`. A PASSED report requires no unresolved
engineering/test/CI defect. The final commit changes only that report, has the
implementation head as first parent, and is verified as remote PR head before
response `OK`.

The report must include:

- exact PR/base/branch/commits/topology and allowed path diff;
- root cause from HTTPX bytes through line/frame/data/JSON/typed validation;
- exact numeric limits and mechanical derivation/inequality table;
- any semantic tightening and why every intended maximum event still fits;
- all 17 regression groups with stable nodes, collection/execution counts and
  `missing=[]`;
- peak decoder-owned line/frame/data/segment state and incremental-many-event
  evidence without retaining content;
- exact provider error codes, prompt close/cancellation, pre/post-output
  accounting, zero pending, privacy/no-echo evidence;
- exact Objective-162 lifecycle regressions and unchanged client/server
  authority/version claims;
- local commands/counts/failures corrected and every implementation-head CI
  check conclusion;
- documentation impact, setup/cleanup, and honest limitations;
- no protected/real-provider/Local/Qwen action.

Required labels:

```text
PREPARSE-LINE-BOUND-ENFORCED = YES|NO
PREPARSE-FRAME-BOUND-ENFORCED = YES|NO
PREPARSE-DATA-AND-JSON-BOUND-ENFORCED = YES|NO
BOUND-DERIVATION-CONSISTENT-WITH-TYPED-VALIDATOR = YES|NO
INCREMENTAL-MANY-EVENT-STATE-BOUNDED = YES|NO
UPSTREAM-CLOSE-AND-CANCELLATION-ACCEPTED = YES|NO
ACCOUNTING-ZERO-PENDING-ACCEPTED = YES|NO
OBJECTIVE-162-LIFECYCLES-REGRESSION-ACCEPTED = YES|NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

Strategic independently reviews the report, implementation, derivation, tests,
CI, security/privacy/accounting, docs, and mergeability. Merge is strategic-only.
After merge, verify remote main and merged-main CI; no downstream protected
handoff is part of this objective.

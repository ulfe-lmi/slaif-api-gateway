# Objective 161-a order — Codex 0.149 assistant output history

## Objective and stopping rule

Create one new Gateway Objective-161 PR from exact current `main` and implement
the minimum version-owned request-policy capability required for real Codex
0.149.0 to replay a prior assistant message whose content contains the exact
bounded part `{"type":"output_text","text":...}`. Preserve that part as
assistant history and count its text through the ordinary request limits.

This is a prove-before-fix objective. Before changing any production path,
reproduce the actual same-session Codex continuation against the unchanged
Gateway base. If the reproduction does not prove the exact mechanism and safe
failure below, publish `RESULT=FAILED` and stop without changing production
behavior. If any later real-Codex run reveals another unreviewed history shape,
publish the first bounded safe class and stop; do not broaden this objective.

No protected credential, Qwen request, provider inference, real production
service, release, cutover, merge, or auto-merge is authorized.

## Authoritative current state

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Round: `161-a`; create exactly one new PR. Do not amend another PR.
- Base branch: `main` at exact commit
  `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- Base tree: `51172ea7dba29046825c3555120c61765608972e`.
- Accepted Gateway app tree:
  `bd536a282362cc549cc0c5518db8e743af667b63`.
- Historical Objective-155 equivalent implementation:
  `acea2af4ca0f4586fc159c91607e1848f53f1107`.
- New branch: `oap/161-codex-assistant-output-history`.
- No Objective-161 branch or PR existed at activation.
- Objective 160 is terminal: PR #297 merged at
  `910ddaa23763883c07f5d2065662eb1157deb9f1`; exact non-report implementation
  `9d247e7f3d8fd6a588976840c4657181b7486b81`; immutable final report head
  `e15008fd0f920aa81ccd5c0d425caf26f7f61b75`; all ten report-head checks
  successful.
- Historical PR #291 remains open at
  `45eeeb538e95ab3ae1d4d6e78ffb654e0e496fa2` and is out of scope. Do not
  reopen, amend, rebase, close, comment on, merge, or enable auto-merge for it.
- Unrelated Dependabot PRs #224 and #250 are out of scope.
- Gateway `main` currently has no GitHub branch-protection rule. This does not
  waive any OAP review or check gate.
- The only published Gateway release is the historical prerelease
  `v0.1.0-rc.1`; Objective 161 makes no release claim.

External Local Coding state is read-only authority:

- Repository: `ulfe-lmi/slaif-local-coding`.
- PR #7 is open, non-draft, mergeable/clean, with successful `test` check.
- Frozen head: `5aec2beccc07432d45e936b82952abf52dfb10d8`.
- Frozen implementation parent:
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`.
- Active/report state: `005-q`.
- The immutable 005-q report records `missing=[]`, 29 selected obligations
  passed, `first_failure=C3.1`, and `retry_count=0`. Its first full-image turn
  passed; the resumed crop/history turn was rejected by Gateway before Local
  with code `responses_input_content_part_not_supported`, parameter
  `input[5].content[0].type`, and part type `output_text` on an assistant
  message.
- Do not modify, commit, push, comment on, merge, or change active/report state
  in the Local repository or PR #7. A detached task-owned checkout or clean
  clone pinned to the exact head may be read and executed only for the bounded
  synthetic cross-contract proof below.

Abort and report any discrepancy in the exact Gateway base, existing
Objective-161 PR/branch state, or frozen Local head before implementation.

Current source also has a separate compact-input path that recognizes both
`input_text` and `output_text`. That path is not authority to relax ordinary
Responses create validation. Objective 161 must use only the compiled,
server-selected client-dialect fact described below.

## Required contracts and source authority

Read the repository governance and only the applicable current contracts before
editing, including:

- `AGENTS.md` and `OAP-COMMUNICATION-coding-agent.md`;
- `AGENTIC_CLIENT_INTEGRATION.md`;
- `app/slaif_gateway/modules/contracts.py`;
- `app/slaif_gateway/modules/clients/codex_0149.py`;
- `app/slaif_gateway/modules/servers/registry.py`;
- `app/slaif_gateway/services/responses_gateway.py`;
- `app/slaif_gateway/services/responses_request_policy.py`;
- `docs/codex-compatibility.md`, `docs/compatibility-matrix.md`,
  `docs/responses-compatibility.md`, `docs/provider-forwarding-contract.md`,
  `docs/security-model.md`, and `docs/accounting.md`;
- the exact Local 005-q order/report at frozen PR #7 head when needed to
  reproduce the bounded mechanism, without retaining its raw content.

Primary client authority is exactly:

- package `@openai/codex@0.149.0`;
- tag `rust-v0.149.0`;
- commit `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`.
- previously verified task-controlled binary SHA-256
  `bbc3341e44c9ead340ed9570c17be936e37870f570751a941699ffd04d672827`.

Architecture-only corroborating authority is exact stable Codex 0.153.4 at
tag `rust-v0.153.4`, commit
`3d2ee51ca2d5db578f328aa75e20aa22c0197c9a`. Record source paths and immutable
provenance for the continuing mechanism: `ContentItem::OutputText`, message
content ownership, `response.output_item.done` deserialization, accumulated
`Prompt.input` cloning, absence of assistant-output rewriting, and the
non-OpenAI metadata cleanup that does not rewrite output text. The alpha
`rust-v0.154.0-alpha.3` may be noted as corroboration only if independently
verified, but must not become an acceptance dependency.

Do not register, select, test, or claim compatibility for Codex 0.153/0.154.
Future versions require their own `AGENTIC_CLIENT_INTEGRATION.md` onboarding.

## Exact allowed paths

Only these paths may change in Objective 161-a:

- `app/slaif_gateway/modules/contracts.py`
- `app/slaif_gateway/modules/clients/codex_0149.py`
- `app/slaif_gateway/services/responses_request_policy.py`
- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_client_modules.py`
- `tests/unit/test_responses_request_policy.py`
- `docs/codex-compatibility.md`
- `docs/compatibility-matrix.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`
- `docs/accounting.md`
- `oap/active`
- `oap/orders/161-a-codex-0149-assistant-output-history.md`
- `oap/reports/161-a-codex-0149-assistant-output-history.md`

The new verifier and its unit test are required names. Do not modify the
accepted Objective-160 verifier, existing Codex fixtures, Local server module,
pair registry, Gateway orchestration, replay/HMAC implementation, database,
schema/migrations, dependencies/lockfiles, CI/workflows, or agent doctrine.
If the exact bounded behavior cannot be implemented within this list, publish
`RESULT=FAILED` with the safe reason and stop.

## A. Mandatory prove-before-fix reproduction

Before editing any `app/` path, add the repository-owned verifier and pure unit
coverage, then execute the verifier against the unchanged base application at
exact `910ddaa23763883c07f5d2065662eb1157deb9f1` (whose relevant non-report
implementation is `9d247e7f...`). Preserve a distinct pre-fix verifier commit
or equally mechanical Git topology proving no production path had changed.

The synthetic bounded topology is:

```text
real task-controlled Codex 0.149.0
  -> unchanged clean Gateway
       -> signed fake Local
            -> fake provider
```

Use task-local Codex installation/provenance, a private temporary home and
workspace, numeric loopback, disposable PostgreSQL, fixed synthetic secrets,
hard request/event/body/time bounds, and both request and stream retries set to
zero. Do not use a real Local service, protected service, Qwen, provider key,
or external inference.

The first turn must naturally create one normal assistant output-message
lifecycle. Continue/resume that exact Codex session through the actual client;
do not hand-construct the continuation. The resumed turn must include the
synthetic image/crop action needed to exercise the 005-q history path.

Observe only bounded structural facts from the actual second Gateway request
and prove all of:

- prior assistant history is present;
- the enclosing message role is exactly `assistant`;
- the relevant content part type is exactly `output_text`;
- its text is a nonempty Unicode string, while the value is never retained;
- clean Gateway rejects before Local with status/error shape appropriate to
  safe invalid-request handling;
- error code is exactly `responses_input_content_part_not_supported`;
- parameter identifies the content-part type and, for the reproduced request,
  is exactly `input[5].content[0].type` if the task-controlled shape remains
  identical to 005-q;
- fake-Local request count does not advance for the rejected turn;
- no retry occurs.

Do not retain or print prompt text, image bytes, assistant text, IDs, call IDs,
credentials, headers, request bodies, SSE payloads, arbitrary errors, DB URLs,
temporary paths, or endpoints. Output only a fixed result line and closed
codes/booleans/count classes. Unit tests must prove the observer, redaction,
bounds, zero-retry command, natural resume command, error projection, and
cleanup behavior.

If any required fact differs, do not edit production behavior. Publish the
bounded mismatch and stop.

## B. Version-owned production behavior

After A succeeds, implement the behavior through
`ResponsesClientPolicySpec` using a default-empty declarative content-type fact
with semantics equivalent to
`assistant_history_content_types: frozenset[str] = frozenset()`. The exact
field name may differ, but it must express which part types may legitimately
occur in retained assistant history for one reviewed client dialect. A
client-supplied value must never populate or widen it.

Set the fact to exactly `frozenset({"output_text"})` only in
`CODEX_0149_POLICY_SPEC`. Production selection must
continue to derive from the already-reviewed exact
`codex-0.149-responses-v1 -> local-coding-v1` pair. Generic request-policy code
must not contain a scattered concrete module/version/server-name check. Prove
that OpenAI-default, Codex 0.147, arbitrary compatible clients, arbitrary
servers, future Codex profiles, wrong pairings, and hosted routes remain false
or unreachable.

Extend ordinary Responses create-message content validation so an
`output_text` part is accepted only when all of these are true:

- selected client policy explicitly enables assistant output history;
- enclosing message role is exactly `assistant`;
- production selection is the reviewed exact Codex-0.149/Local-Coding pair;
- the part is a mapping with exactly the fields `type` and `text`;
- `type` is exactly `output_text`;
- `text` is valid nonempty Unicode text;
- existing per-part, per-item, total text, item-count, material, and request
  byte limits all pass.

Return the canonical part exactly as `{"type":"output_text","text":...}`.
Do not rewrite it to `input_text`, delete it, synthesize another history form,
or create provider-state/response/conversation/item identifiers. It is
transient validated model input only and must flow into the ordinary text-byte
and token-estimation machinery.

## C. Fail-closed negative and authority behavior

Focused tests must prove rejection of `output_text` for user, system, and
developer roles, and rejection for all client policies without the explicit
fact. Also reject:

- empty or non-string text;
- missing `type` or `text`;
- any unexpected field, including annotations or logprobs;
- unreviewed status or phase fields;
- refusal or any other unapproved output content type;
- image, file, or audio output content;
- tool-call shapes disguised as message content;
- malformed message/content shapes;
- excessive content-part count, per-part/per-item text bytes, total request
  bytes, item count, image/file material, or other existing request bounds;
- arbitrary output-item shapes and all wrong pair/server/profile selections.

Use existing safe error classes and precise parameters. The clean-base
pre-fix reproduction must keep its exact error code. Negative candidate tests
must not expose values.

Assistant `output_text` is content, not capability or authority. It must not
affect hosted/external tool authority, local function/custom-tool ownership,
call-ID HMACs, item-ID no-downgrade, HMAC rotation, reasoning replay, signed
identity, route/provider/model selection, key permissions, rate limits,
pricing, quota reservation/finalization, accounting categories, audit, or
privacy authority.

## D. Unchanged Local cross-contract proof

After policy/unit gates pass, use only the exact unchanged Local PR #7 head
`5aec2beccc07432d45e936b82952abf52dfb10d8` in a detached task-owned checkout
or clean clone. Verify the commit and clean status before and after. Do not
write to its tracked files or GitHub state.

With synthetic content and a fake downstream provider, prove through actual
Gateway signing and actual Local code that:

- candidate Gateway accepts and signs the bounded assistant history request;
- unchanged Local accepts the separate service Bearer and signed request;
- Local image/tool/constitution processing preserves the assistant history
  item semantically and does not corrupt, rewrite, delete, or reinterpret it;
- the fake downstream provider receives exactly one bounded assistant message
  part of type `output_text`, with nonempty text classification only;
- no extra identity, authority, hosted-tool, route, provider, pricing, quota,
  replay, or accounting fact is introduced;
- Gateway public bearer, raw identity input, secrets, and content are absent
  from retained evidence.

Retain only fixed versions/commits, counts, booleans, field/type/role enums,
relationship classes, and safe terminal states. This is fake cross-contract
evidence, not protected acceptance.

## E. Exact-client final fake acceptance

After all pure, unit, PostgreSQL, stream, replay, privacy, and Local
cross-contract gates pass, run exactly one final zero-retry repository-owned
acceptance:

```text
real task-local Codex 0.149.0
  -> candidate Gateway Objective 161
       -> unchanged actual-code Local boundary at 5aec2be...
            -> strict fake Qwen/provider
```

The one final run must naturally perform, in order:

1. first synthetic vision turn;
2. normal assistant output-message lifecycle;
3. same-session Codex resume/history request;
4. prior assistant `output_text` retained by real Codex;
5. new synthetic image/crop request;
6. Gateway bounded acceptance and normal signing;
7. Local admission and unchanged pipeline processing;
8. fake-provider receipt of the expected structural shape;
9. normal terminal SSE/usage lifecycle and PostgreSQL finalization;
10. successful Codex exit with zero retry.

Require exact bounded success output defined by the new verifier, at least two
Gateway admissions, the expected Local/provider call progression, finalized
reservation/ledger rows with zero pending, and complete task-owned cleanup.
No prompts, images, output text, bodies, events, IDs, credentials, endpoints,
or arbitrary failures may enter output or the report.

Do not rerun this final candidate acceptance after an unreviewed failure. A
known test-harness defect may be corrected only if it is entirely inside the
allowed verifier/test paths and the report clearly records chronology; any new
client dialect or product behavior requires strategic continuation.

## F. Required regressions and verification

Run complete affected files, not selected positive cases:

- `tests/unit/test_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_client_modules.py`
- `tests/unit/test_responses_request_policy.py`
- `tests/unit/test_responses_codex_multiturn_replay.py`
- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/unit/test_local_coding_server_module.py`
- `tests/unit/test_codex_0149_local_roundtrip.py`
- `tests/e2e/test_openai_python_client_responses.py`

Run these complete repository-standard disposable PostgreSQL suites with no
required skip/xfail/failure:

- `tests/integration/test_codex_client_modules_postgres.py`
- `tests/integration/test_codex_replay_references_postgres.py`
- `tests/integration/test_local_coding_server_module_postgres.py`
- `tests/integration/test_accounting_finalization_postgres.py`

Also require:

- the unchanged Objective-160 exact-client fake verifier succeeds, proving its
  ID-less function/custom replay and terminal assistant lifecycle contract;
- visible ID-less reasoning, `encrypted_content:null`, ID-less function/custom
  calls, call-ID-HMAC same-key ownership, wrong-item-ID no-downgrade, HMAC
  rotation, signed Local identity, exact pair selection, tool filtering,
  reasoning/function/message SSE machines, and failure cleanup remain green;
- OpenAI-default and Codex 0.147 request-policy regressions remain green;
- text bytes from accepted assistant history are included in canonical
  material and conservative input-token/request estimates;
- no accounting schema or semantics change, and failed pre-admission requests
  create no reservation/ledger/replay side effects;
- Ruff check and format-check on changed Python, Python compilation, JSON/doc
  source/provenance validation, `git diff --check`, and exact allowed-path
  proof;
- scans/tests exclude raw content, request/SSE bodies, identities, call/item
  IDs, prompts, images, assistant text, credentials, and arbitrary errors from
  logs, audit, accounting metadata, metrics, verifier output, and report;
- all normal Gateway CI and CodeQL checks are successful on the exact final
  report head. Expected matrix: Unit/lint/migration head, both Python analyses,
  JavaScript/TypeScript Code Quality, PostgreSQL integration, OpenAI-compatible
  E2E, Playwright smoke, Docker Compose smoke, documentation hygiene, and
  repository CodeQL.

Skipped, xfailed, missing, pending, cancelled, neutral, stale-head, or
environment-blocked required evidence is not a pass. Do not run an unrelated
complete local suite unless needed to reproduce a required matrix failure.

## Documentation requirements

Update the allowed documents to state only implemented facts:

- exact Codex 0.149/Local pair accepts bounded prior assistant `output_text`
  history without rewriting;
- policy is default-false and remains disabled for every other profile;
- content is transient, bounded, included in normal input estimation, and
  excluded from retained evidence;
- no authority, replay, identity, route, provider, hosted-tool, quota, pricing,
  or accounting semantics changed;
- exact Local cross-contract and exact-Codex fake evidence are synthetic only;
- protected acceptance remains NO;
- stable Codex 0.153.4 source still exhibits the mechanism, but no 0.153/0.154
  module, compatibility, qualification, or selected-version claim exists.

Include the exact documentation-impact statement required by `AGENTS.md` in
the report. Do not alter release-readiness or certification language.

## Non-goals and frozen boundaries

Do not:

- modify Local Coding, Qwen, protected hosts/services, or their configuration;
- use protected credentials or call protected/authenticated/model/inference/
  vision routes;
- touch, amend, reopen, comment on, close, merge, or auto-merge PR #291;
- register or claim Codex 0.153/0.154 support;
- globally allow `output_text`, refusal, annotations, logprobs, or arbitrary
  output/history shapes;
- change Local/hosted tool separation, replay ownership, HMAC behavior,
  identity, routing, provider selection, permissions, rate limits, pricing,
  quota/accounting, privacy, schema/migrations, dependencies, or CI;
- reopen or rewrite Objective-155/160 evidence, fixtures, orders, or reports;
- create provider state or implement conversation-history rewriting;
- merge, enable auto-merge, release, deploy, cut over, certify, or activate a
  later Gateway objective.

## PR and publication contract

Create exactly one new PR from exact base `910ddaa...` using branch
`oap/161-codex-assistant-output-history`. The PR title/body must identify
Objective 161, the exact base, prove-before-fix mechanism, default-false policy
scope, frozen Local head, fake-only acceptance, and protected prohibition.
Coding never merges or enables auto-merge.

After final implementation head exists, required local evidence passes, and
all required GitHub checks on that implementation are green, publish exactly:

`oap/reports/161-a-codex-0149-assistant-output-history.md`

The immutable report must include:

- `RESULT=PASSED` or `RESULT=FAILED`;
- literal `Implementation head SHA: <pre-report commit>`;
- `Report publication commit: SELF`;
- exact base/branch/PR/head topology and allowed-path diff;
- chronology and commit proof that A preceded all production changes;
- clean-base exact-Codex failure facts and fake-Local non-advance;
- neutral policy fact, exact 0.149 ownership, negative profile/role/shape/
  limit matrix, semantic preservation, and accounting-byte evidence;
- immutable 0.153.4 source provenance with explicit no-support limitation;
- unchanged Local `5aec2be...` cross-contract result and clean-state proof;
- exact one final candidate fake result, zero retries, lifecycle/accounting/
  cleanup facts, and bounded retained-evidence statement;
- complete required test/check results with no missing required gate;
- security, privacy, replay, identity, hosted-tool, quota/accounting, docs,
  protected-traffic, release, and scope statements;
- these exact lifecycle labels:

```text
IMPLEMENTED = YES|NO
TESTED = YES|NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = YES|NO
LOCAL-CROSS-CONTRACT-ACCEPTED = YES|NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

`PROTECTED-ACCEPTED` must remain `NO` regardless of other results. The report
commit must change only that report, have the literal implementation head as
its first parent, and be the verified remote PR head. Verify all report claims
and final-head checks, write exactly two bytes `OK` to `response.fifo`, and
return to the blocking control FIFO. Strategic review alone may merge.

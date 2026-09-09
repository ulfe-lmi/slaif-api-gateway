# OAP Work Order — 161-p

PR mode: `AMEND_EXISTING_PR`

## Objective and controlling human decision

Implement the bounded Section-B assistant-history compatibility change from
161-a on the existing Objective-161 PR. This is a production implementation
round. The business outcome is that legitimate retained assistant
`output_text` from the reviewed Codex 0.149/Local pairing passes ordinary
Responses create validation without losing its meaning or escaping limits.

The human has explicitly determined that prove-before-fix is satisfied by the
combined accepted evidence: immutable Local 005-q's real Codex 0.149
same-session vision failure, exact Gateway source ownership, and exact Codex
source/package/native provenance. Local's first full-image turn succeeded;
resumed crop/history was rejected before Local with
`responses_input_content_part_not_supported`,
`input[5].content[0].type`, assistant `output_text`, and zero retry.
The ordinary Gateway create validator owns that rejection; the separate
compact path already recognizes output_text; Codex retains legitimate prior
assistant output. Later rounds provide no contradictory ownership evidence.

This decision supersedes 161-a's requirement for a new successful Gateway
pre-fix reproduction and the diagnostic-only restrictions of earlier rounds.
Do not rerun any terminal 161-a through 161-o execution, including 161-c.
Do not spend this continuation diagnosing import/interpreter/verifier/
accounting harness behavior unless it directly blocks post-fix acceptance.
Write focused production and negative tests first, implement the minimum
production change, then prove it with unchanged-Local fake integration.
An unrelated Objective-161 verifier failure must be reported separately and
must not prevent product implementation or sufficient direct acceptance.

## Reconciled software and orchestration state

- Repository: `ulfe-lmi/slaif-api-gateway`; unique Objective-161 PR #298,
  https://github.com/ulfe-lmi/slaif-api-gateway/pull/298.
- Branch: `oap/161-codex-assistant-output-history`; base `main` exactly
  `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- Starting PR head / immutable 161-o report commit:
  `2ca0232fffc290ebb9ceb4220ad54cba31dd799d`.
- Its literal implementation first parent:
  `cc3a7bf5bd7ef46985509f2830f61cc2ae0fecae`.
- Report: `oap/reports/161-o-localize-import-dispatch-and-accounting.md`.
  RESULT=FAILED; report-only topology verified; all ten report-head checks
  SUCCESS. One diagnostic failed at imports/attribute before Gateway, Local,
  or accounting. It establishes no product acceptance.
- PR #298 is OPEN, non-draft, CLEAN/mergeable, with no reviews, review comments,
  or auto-merge. Current changes are transcript, verifier, and verifier tests;
  production paths remain unchanged.
- Current main has no branch-protection rule; OAP review/check gates still
  apply. Historical prerelease `v0.1.0-rc.1` is unchanged.
- PRs #291, #250, and #224 are unrelated and out of scope.
- Local repository: `ulfe-lmi/slaif-local-coding`, PR #7 OPEN, non-draft,
  CLEAN, test check SUCCESS. Frozen report head:
  `5aec2beccc07432d45e936b82952abf52dfb10d8`; implementation parent:
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`. OAP 005-q is immutable.
- Shared activation root is
  `/home/ubuntu/codex-work/slaif-api-gateway`; it is a stale detached checkout
  with strategic activation files. The existing coding worktree is
  `/home/ubuntu/codex-work/slaif-api-gateway-161`.
  Preserve unrelated state; incorporate the exact shared order/active bytes
  using coding-owned Git execution. Strategic did not reset or switch Git.

Verify these identities before implementation. On a material topology or
frozen-Local discrepancy, report it rather than choosing another target.
Never create a second Objective-161 PR.

## Required reading and exact allowed paths

Read current repository AGENTS.md, OAP-COMMUNICATION-coding-agent.md,
AGENTIC_CLIENT_INTEGRATION.md, 161-a Sections B-F, module contracts, selected
Codex module, pair registry, request policy, Gateway policy selection, and
applicable compatibility, provider-forwarding, security, accounting contracts.
The human decision and this current order govern conflicts with prior orders.

Only these paths may change:

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
- `oap/orders/161-p-implement-assistant-output-history-policy.md`
- `oap/reports/161-p-implement-assistant-output-history-policy.md`

Implement direct bounded fake acceptance in the allowed verifier/test paths,
reusing existing helpers by import without changing their tracked files.
Do not change the pair registry, Local module, Gateway orchestration,
Objective-160 verifier/fixtures, replay/HMAC, schema/migrations, dependencies,
CI, governance, or any activated order/report other than adding this round.

## Production requirements and tests first

Before production edits, add and run focused tests that fail for the currently
missing positive behavior and exercise strict negatives. Record this ordinary
test-first evidence; no new synthetic pre-fix Codex execution is required.

1. Add a default-empty declarative fact to ResponsesClientPolicySpec with
   semantics `assistant_history_content_types: frozenset[str] = frozenset()`.
   Only CODEX_0149_POLICY_SPEC enables exactly `frozenset({"output_text"})`.
   The fact is compiled, server-selected policy, never client-controlled.
2. Retain the existing exact production pairing
   `codex-0.149-responses-v1 -> local-coding-v1`. Generic policy consumes the
   fact without concrete client-version/server-name branching. Prove default,
   OpenAI, Codex 0.147, future/unknown clients, wrong pairings, and hosted
   routes remain disabled or unreachable.
3. Ordinary Responses create accepts an output_text part only inside a message
   whose role is exactly assistant, under that explicitly enabled policy.
   The part must be a mapping with exactly type and text; type is output_text;
   text is valid nonempty Unicode string. Reject invalid Unicode safely.
4. Preserve canonical `{"type":"output_text","text":...}` exactly; no rewrite
   to input_text, deletion, conversation-state synthesis, or new identifiers.
5. Include text in ordinary per-part/per-item/total text bytes, canonical
   request material, conservative input-token estimates, and all request
   limits. Prove multibyte Unicode and boundary/over-boundary cases.
6. Use existing safe validation errors and precise parameter paths without
   exposing values. Keep existing input_text and compaction semantics.

Strict tests must cover user/system/developer roles; absent/default/disallowed
policy and wrong pair/route selection; empty/non-string/invalid Unicode text;
missing type/text; extra annotations/logprobs/status/phase or other fields;
refusal/image/file/audio/unapproved output types; disguised tool calls;
malformed message/content; item/part count, per-item/total bytes, image/file
material and request bounds. Include the exact input[5].content[0] assistant
history shape as a bounded synthetic positive. Existing negative inputs must
remain rejected before forwarding and without reservation/ledger/replay
side effects.

Assistant text grants no capability. Preserve tool ownership/filtering,
local-versus-hosted separation, same-key replay HMAC and rotation, item-ID
no-downgrade, reasoning replay, signed identity, route/model/provider selection,
key permissions, pricing, quota/accounting, audit, and content privacy.

## Required post-fix acceptance with unchanged Local

After focused production and negative tests pass, run a reproducible bounded
integration through actual candidate Gateway admission/signing and actual Local
code pinned to the frozen PR #7 head, with only a strict fake downstream.
Use a detached task-owned Local clone/checkout; verify exact commit and clean
tracked status before and after. Do not change Local code or GitHub state.

The direct integration must prove:

- a synthetic retained assistant output_text history request is accepted by
  the selected Gateway pair, signed normally, and admitted by actual Local;
- separate service Bearer and signed identity remain valid at Local;
- Local's normal constitution/tool/image processing preserves the assistant
  history semantically, with exactly the expected bounded assistant part at
  fake-provider receipt; compare text transiently and report only equality;
- the part remains output_text, nonempty Unicode, with no extra fields;
- normal terminal response/SSE and usage accounting complete, PostgreSQL
  reservations/ledger finalize exactly once, and no pending state remains;
- corresponding invalid role/shape/policy requests fail closed with no Local/
  provider advancement and no accounting/replay side effects;
- expected replay facts follow unchanged production behavior, and identity,
  hosted tools, retries, logging, and cleanup retain existing boundaries.

Exercise the strongest practical fake composition, including first-turn
assistant output followed by retained history and synthetic image/crop content
where existing helpers support it. A direct bounded synthetic continuation is
explicitly acceptable for proving the changed production boundary.

After core evidence passes, attempt the real task-local exact Codex 0.149
same-session vision/resume flow if practical using existing package/native
provenance and unchanged Local. Do not require a fresh pre-fix run.
Both client request and stream retry counts must be zero. Keep bounded
process/event/body/request/time limits and complete cleanup.

If the existing Objective-161 verifier fails for an unrelated harness reason,
record the exact safe limitation and real-client acceptance NO separately.
Do not abandon or withhold the production change. Use the required direct
integration above as the acceptance path authorized by the human.
Only make verifier corrections needed for post-fix evidence; do not launch
another general diagnostic sequence. If correcting an accounting assertion,
derive exact expected counts from unchanged production code and actual bounded
observations; never relax it to arbitrary nonzero or modify product accounting.
Document test/run chronology and any harness correction; no blind retries.
A newly discovered product/dialect mismatch remains a failed acceptance and
must not be hidden by the verifier exception.

## Verification and documentation

Run these complete affected test files with exact collected/executed counts:

- `tests/unit/test_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_client_modules.py`
- `tests/unit/test_responses_request_policy.py`
- `tests/unit/test_responses_codex_multiturn_replay.py`
- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/unit/test_local_coding_server_module.py`
- `tests/unit/test_codex_0149_local_roundtrip.py`
- `tests/e2e/test_openai_python_client_responses.py`

Run complete disposable PostgreSQL suites:

- `tests/integration/test_codex_client_modules_postgres.py`
- `tests/integration/test_codex_replay_references_postgres.py`
- `tests/integration/test_local_coding_server_module_postgres.py`
- `tests/integration/test_accounting_finalization_postgres.py`

Require the unchanged `scripts/verify_codex_0149_local_roundtrip.py`
Objective-160 fake verifier. Preserve ID-less function/custom/reasoning,
encrypted_content:null, SSE lifecycle, replay/HMAC and signed-identity
regressions. Run OAP governance, changed-Python Ruff check/format/compilation,
documentation hygiene, diff whitespace and exact allowed-path checks.
Do not run unrelated complete local suites. Required skips, xfails, missing,
pending, cancelled, or stale evidence are not passes. The explicitly allowed
legacy Objective-161 verifier limitation is a reported exception, not a pass.

Update the five allowed docs to describe only the exact implemented pairing,
preserved bounded output_text, default-empty policy, ordinary text estimation,
transient content, unchanged authority/accounting, actual fake evidence, and
protected acceptance NO. Carry forward exact 0.149 source provenance; no new
0.153/0.154 compatibility or qualification claims. Include the repository's
required documentation-impact statement in the report.

## Setup, privacy, and frozen boundaries

Routine task-owned Python 3.12 dev environment, npm exact Codex package,
loopback fake listeners, and disposable PostgreSQL are authorized. Use
repository-standard setup; do not mutate global environments or production
DATABASE_URL. No protected service/credential, real Qwen/provider/inference,
production system, real email, Local mutation, deployment, release, or cutover.

Retain only fixed source commits/versions, tests/checks, enums, bounded counts,
booleans, relationships, and safe terminal states. Do not print or retain
prompts, output/reasoning text, media, request/SSE bodies, tool payloads, raw
IDs/HMACs, credentials, headers, endpoints, DB URLs/rows/amounts, private paths,
environment/package output, tracebacks, or arbitrary errors in reports/logs.
Synthetic data may exist transiently inside bounded tests and private state;
clean up every task-owned listener, process, database and temporary root.

## PR, immutable report, and handoff

Commit the unchanged strategic 161-p order/active along with bounded work to
the existing PR #298. Update that PR title/body to accurately describe the
production fix, accepted human pre-fix evidence, exact policy scope, frozen
Local fake evidence, verifier limitation if any, and protected prohibition.
Do not create another PR, merge, or enable auto-merge.

Before report publication require all ten normal checks SUCCESS on the exact
pushed implementation head: Unit/lint/migration, Analyze JavaScript/TypeScript,
Analyze Python, Analyze (python), PostgreSQL integration, OpenAI-compatible
E2E, Playwright, Docker Compose, Documentation hygiene, and CodeQL.

Publish exactly
`oap/reports/161-p-implement-assistant-output-history-policy.md` once with
RESULT=PASSED or RESULT=FAILED. PASSED requires the production boundary,
strict negatives, required regressions, direct unchanged-Local integration,
privacy/accounting/cleanup, docs and implementation checks to pass. It may
coexist with EXACT-CODEX-0.149-FAKE-ACCEPTED=NO only for the separately evidenced
unrelated Objective-161 harness limitation authorized above.

Include literal implementation SHA mechanically verified from Git/GitHub;
`Report publication commit: SELF`; base/branch/PR/diff/topology; tests-first
evidence and exact final counts; human accepted pre-fix basis; policy/negative/
limits/accounting proofs; frozen Local clean-state and direct integration
results; real-client attempt or explicit practical limitation; all check
results, docs, privacy, cleanup, skips and deviations. Never copy stale counts.

Required labels:

```text
PREFX-PROOF-ACCEPTED-BY-HUMAN = YES
IMPLEMENTED = YES|NO
TESTED = YES|NO
DIRECT-BOUNDED-FAKE-ACCEPTED = YES|NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = YES|NO
LOCAL-CROSS-CONTRACT-ACCEPTED = YES|NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

The final report commit changes only that report and has the literal reported
implementation head as first parent. Verify it is remote PR #298 head before
sending exact response OK. Report-head checks may still be pending; strategic
will verify all final-head checks and independently review before any merge.
Return to the permanent coding control-wake helper after response.

After Gateway strategic acceptance and merge, strategic will hand back to
Local OAP-005 for the full fake matrix and bounded protected matrix. That later
handoff does not authorize protected traffic or Local mutation in this round.

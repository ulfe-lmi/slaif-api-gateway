# OAP Work Order — 161-q

PR mode: `AMEND_EXISTING_PR`

## Objective and authority

Close the concrete post-fix review and CI gates for Objective 161 while
preserving the production compatibility change implemented by 161-p.
This is bounded acceptance/test/documentation work on the same PR.

The human's accepted Local 005-q + Gateway ownership + exact Codex evidence
satisfies prove-before-fix. No fresh pre-fix run, import-diagnostic sequence,
or retry of a terminal earlier round is required or authorized.
The human explicitly permits sufficient direct bounded fake integration if
the legacy Objective-161 real-client verifier remains impractical.
Do not broaden the client dialect or revisit that risk decision.

## Verified state and strategic findings

- Repository `ulfe-lmi/slaif-api-gateway`; unique Objective-161 PR #298,
  OPEN, non-draft, mergeable/UNSTABLE, no reviews/threads/auto-merge.
- Branch `oap/161-codex-assistant-output-history` onto exact main
  `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- Starting head / immutable 161-p FAILED report:
  `3debd25d48ef5f7e686446504a33eea21c3ee416`.
- Literal implementation first parent:
  `899bd57e6eef49149d54c65838cf25d043e34a55`.
- Report is `oap/reports/161-p-implement-assistant-output-history-policy.md`;
  report-only topology and exact unchanged shared order bytes are verified.
- All ten report-head checks are terminal: nine SUCCESS; Unit/lint/migration
  FAILURE. Implementation CI run 34341422103 independently shows only
  `test_obligation_evaluator_reports_exact_empty_missing_list` failing:
  app_tree and the changed Codex module, contracts, request policy, and client
  module test blobs differ from the fixed Objective-160 snapshot.
- Production review confirms the default-empty fact, exactly output_text in
  CODEX_0149_POLICY_SPEC, assistant-role gate, exact fields, valid Unicode,
  semantic preservation, and ordinary byte estimation/limits.
- Direct 161-p fake acceptance reports one synthetic request through actual
  Gateway and Local, one invalid-role rejection, and nonpending accounting.
  Its observer verifies preserved text. However, its accounting predicate
  checks nonpending counts rather than exact finalized states, it has no
  direct-mode unit tests, its image is the placeholder base64 AAAA, and Local
  commit/clean checks alone do not attest the code loaded by the subprocess.
- 161-p's EXACT-CODEX-0.149-FAKE-ACCEPTED=YES is not established for the new
  vision/history path. The actual real-client success it names is unchanged
  Objective-160's separate two-turn fake regression. No new exact-client
  same-session vision/resume acceptance was reported.
- 161-p's collection/pass/skip/fail arithmetic is inconsistent. Its report
  omits concrete test-first chronology. Preserve that report; correct claims
  in this round with actual evidence, never invented reconstruction.
- Codex compatibility docs say exactly one output_text part, while the policy
  intentionally preserves normal bounded content arrays. Correct the docs,
  not the accepted production semantics.
- Frozen Local `ulfe-lmi/slaif-local-coding` PR #7 remains OPEN/CLEAN with
  successful test check at report head
  `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`. Local OAP 005-q is immutable.
- Main, historical prerelease v0.1.0-rc.1, and unrelated PRs #291/#250/#224
  remain unchanged/out of scope. No branch-protection rule exists; OAP
  review/check gates still apply.

Reconcile these identities before work. Shared activation root is
`/home/ubuntu/codex-work/slaif-api-gateway`; coding worktree is
`/home/ubuntu/codex-work/slaif-api-gateway-161`. Preserve unrelated state and
copy/commit the exact strategic-authored activation bytes using coding-owned
Git execution. Never create a second Objective-161 PR.

## Exact allowed paths and reading

Read current AGENTS.md, coding OAP protocol, applicable integration/contracts,
161-p order/report, the failing Objective-160 evaluator/test, and the direct
161-p verifier before editing.

Only these paths may change:

- `tests/unit/test_codex_0149_local_roundtrip.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `tests/unit/test_responses_request_policy.py`
- `tests/unit/test_codex_client_modules.py`
- `scripts/verify_codex_0149_assistant_output_history.py`
- `docs/codex-compatibility.md`
- `docs/compatibility-matrix.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`
- `docs/accounting.md`
- `oap/active`
- `oap/orders/161-q-close-production-acceptance-and-ci.md`
- `oap/reports/161-q-close-production-acceptance-and-ci.md`

This explicitly authorizes the named Objective-160 unit-test correction;
161-p's prohibition on that test is superseded for this narrow purpose.
The Objective-160 verifier, historical hashes/manifest, fixtures, orders and
reports stay byte-identical. All app/ production files stay byte-identical to
899bd57. No Local, registry, orchestration, replay/HMAC, accounting, schema,
dependency, CI, or governance modification. If new production behavior is
needed, report the precise boundary for strategic review.

## A. Repair the historical snapshot unit test without rewriting history

The failing test runs a historical exact-tree evaluator against an evolving
production checkout. Make that unit test hermetic against a controlled
snapshot of the evaluator's filesystem/Git inputs. Keep the original
evaluate_obligations function and its immutable hashes unchanged.

Use test-local temporary filesystem fixtures and narrow monkeypatch seams for
Git/blob inputs where necessary; exercise the real evaluator, never stub its
return value. The passing fixture must yield exactly missing=[]; negative
mutations must independently prove wrong app tree, changed/missing protected
blobs, required files, forbidden historical machinery, and doctrine links
remain detectable with precise fixed names. Verify the real blob-hash helper
on known bytes separately if that helper is substituted in the fixture.

Do not refresh hashes to current HEAD, remove the historical assertion,
xfail/skip it, teach it to accept arbitrary missing entries, or globally
monkeypatch production or runtime acceptance. Keep the exact original
historical evaluator callable for archival audits. Explain that immutable
historical attestation and current behavioral regression serve different test
purposes; production regression tests and normal CI continue testing current
code.

## B. Complete focused enabled-policy negatives

Extend production tests under the actual enabled 0.149 policy, using explicit
expected error codes/parameters rather than a broad allowed-error set:

- exact input[5].content[0] assistant output_text is preserved and counted;
- multiple bounded output_text parts and mixed already-supported input_text
  remain valid; no artificial one-part restriction;
- user/system/developer roles, default/OpenAI/0.147 and policy fact absent;
- missing type/text, empty/non-string/invalid Unicode text;
- extra annotations/logprobs/status/phase and arbitrary extra fields;
- refusal/output image/file/audio and disguised tool-call parts;
- malformed messages/content, part/item counts, exact-limit and over-limit
  multibyte per-item and total text, canonical/request-material bounds;
- unknown/future profiles, wrong server pair and hosted selection fail closed
  through the existing selection path. Reuse unchanged pair/authority tests
  where they already prove the exact case and cite the test.

Retain ordinary input_text, compact, replay, HMAC, signed identity, tool
filtering, and accounting regressions. Tests must not weaken a product rule
to make the evidence pass.

## C. Finish direct post-fix acceptance with unchanged Local

Keep the direct synthetic approach; no new real-Codex execution is required
in this round. Report new same-session exact-client acceptance NO and carry
Objective-160's prior exact-client result only as its separate regression.

Strengthen the existing direct mode with finite source-directed changes:

1. Attest the actual Local module loaded by the subprocess to the frozen
   checkout/source, using a task-owned environment and explicit source
   resolution. Verify exact HEAD and clean tracked status both before and
   after. A checkout path alone is not runtime source attestation. Report only
   fixed commit and match booleans; keep paths/package output private.
2. Reuse the verifier's valid bounded synthetic full/crop PNG fixtures.
   Exercise two direct Gateway requests through actual Local: first user image
   to normal assistant terminal output, then bounded retained assistant text
   plus the crop request. Preserve first response text transiently for the
   second request and compare semantic equality at fake-provider receipt.
   This is direct synthetic history evidence, not a real Codex resume claim.
   Keep each assistant part exactly type/text; do not replay unreviewed fields.
3. At the actual fake provider prove first/full and second/crop classification,
   exact expected request counts, normal service authorization, assistant
   role/type/text equality, and absence of extra authority fields. Parse the
   bounded terminal SSE sufficiently to prove completed lifecycle and usage;
   a substring match alone is insufficient. Use zero retries.
4. Query PostgreSQL for exact finalized reservation/ledger states and linkage,
   zero pending, expected two successful requests, and unchanged replay counts.
   Snapshot before each invalid request and require full equality after it.
   Nonpending is not equivalent to finalized. Keep amounts, IDs and row data
   private; report only fixed counts/status/relationship booleans.
5. Run invalid-role and malformed-extra-field cases through the same composed
   Gateway, plus a default/disallowed policy admission case using existing
   setup. Require exact safe 4xx, no Local/provider advancement, and no
   reservation/ledger/replay side effects. Do not change pairing registry.
6. Add direct-mode unit tests for observer success and mutations (rewritten/
   missing/extra history, wrong role/text/auth, image mismatch, extra request),
   terminal/usage/accounting predicate failures, source mismatch, command-mode
   conflicts, body/time limits, closed error output and cleanup.
7. Make every direct-mode failure emit a closed fixed code without arbitrary
   traceback/message/content. Ensure socket reads have time bounds, oversized
   bodies are rejected rather than silently truncated, subprocess termination
   is reaped even after kill, listeners/threads stop, disposable DB is dropped,
   and cleanup failure cannot be reported as success.

Run the improved direct acceptance after focused tests pass. Ordinary bounded
test/harness development is authorized; record corrections and execution
chronology. Do not conduct a pre-fix diagnostic run or blindly retry a product
mismatch. A new product/dialect boundary remains a failed gate.

## D. Verification, corrections, and docs

Run the complete four changed/affected unit files above and the unchanged
multiturn replay, streaming tools, and Local server module unit files.
Run the complete Responses E2E file with its disposable database configured so
required evidence does not silently skip. Keep exact machine-collected
collected/passed/failed/skipped counts per command; explain any optional global
CI skip by test identifier/reason instead of counting it as success.

161-p's eight PostgreSQL tests and unchanged Objective-160 exact-client fake
regression may be carried forward with exact source/head provenance because
all production and that verifier remain unchanged. Fresh direct acceptance
must query actual PostgreSQL as specified above; normal new-head CI reruns
the full PostgreSQL matrix. Rerun additional focused DB cases only if a change
or failure calls that evidence into question.

Run OAP governance, pinned repository Ruff check/format, compilation, doc
hygiene, diff whitespace and allowed-path proof. Do not perform an unrelated
complete local suite; normal CI supplies the broad matrix.

Correct all five allowed docs as necessary: bounded arrays may contain exact
output_text parts, each with only type/text, under only the selected pair;
existing input_text remains supported. State direct synthetic acceptance
separately from unchanged Objective-160 client regression. New real-client
vision/resume and protected acceptance remain unestablished. Never change a
release or broader Codex-version claim.

In the new report explicitly correct 161-p's exact-client label and arithmetic,
state the safe limits of its placeholder-image/nonpending-count evidence,
and provide accurate new counts and actual test-first chronology if retained
evidence supports it. If old chronology/counts cannot be reconstructed, state
that precisely and use current verified results. Do not edit 161-p.

## Boundaries and publication

Routine task-owned Python 3.12 dev setup, frozen Local installation/checkout,
loopback fake services and disposable PostgreSQL are authorized. Do not read
protected credentials or call real Local/Qwen/provider/inference/production
services; no real email, merge, auto-merge, deployment or release.

Keep prompts, assistant/reasoning text, media, bodies/events, tool payloads,
IDs/HMACs, credentials, headers, DB URLs/rows/amounts, paths, environment/package
output and arbitrary errors out of logs/reports/evidence. Retain only safe
fixed versions/commits, booleans, enums, bounded counts and terminal results.
Clean up every task-owned resource and preserve unrelated work.

Commit unchanged strategic order/active and bounded changes to PR #298.
Update its body around the final production behavior and accurate acceptance.
Before a PASSED report, all required evidence and all ten implementation-head
GitHub checks must be SUCCESS. A remaining required failure means FAILED.

Publish exactly `oap/reports/161-q-close-production-acceptance-and-ci.md`
once with RESULT=PASSED|FAILED, literal mechanically verified implementation
head SHA, Report publication commit: SELF, exact topology/scope, review-finding
closure, unchanged app/Objective-160/frozen-Local proof, corrections,
test counts/checks, direct acceptance and accounting evidence, docs impact,
privacy/cleanup/skips/limitations, and:

```text
PREFX-PROOF-ACCEPTED-BY-HUMAN = YES
IMPLEMENTED = YES
TESTED = YES|NO
DIRECT-BOUNDED-FAKE-ACCEPTED = YES|NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
OBJECTIVE-160-FAKE-REGRESSION-ACCEPTED = YES|NO
LOCAL-CROSS-CONTRACT-ACCEPTED = YES|NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

The final publication commit changes only the report, has the literal reported
implementation first parent, and must be remote PR #298 head before exact
response OK. Strategic verifies every final-head check and independently
reviews before merge. Return to the permanent coding control-wake helper.

After Gateway acceptance/merge, strategic hands back to Local OAP-005 for its
full fake and bounded protected matrices; this order authorizes neither that
Local activation nor protected traffic.

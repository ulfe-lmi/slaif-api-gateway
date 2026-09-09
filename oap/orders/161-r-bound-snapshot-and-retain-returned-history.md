# OAP Work Order — 161-r

PR mode: `AMEND_EXISTING_PR`

## Objective

Close two concrete review defects in the new test/evidence code on PR #298:
limit the historical evaluator's synthetic snapshot to its explicit inputs,
and derive the direct continuation's assistant text from the actual first
Gateway response. Preserve the already implemented production policy.

Human-accepted pre-fix proof remains sufficient. No new pre-fix execution,
legacy import diagnosis, real-Codex run, or production change is required.
This is a finite source-directed correction and one post-fix direct acceptance.

## Reconciled state

- Repository `ulfe-lmi/slaif-api-gateway`; PR #298 is the unique Objective-161
  PR, OPEN, non-draft, mergeable, no reviews/threads/auto-merge.
- Branch `oap/161-codex-assistant-output-history`; exact main/base
  `910ddaa23763883c07f5d2065662eb1157deb9f1`.
- Starting immutable 161-q PASSED report/current PR head:
  `ab1d04fb958cd531bf13b83e2becca26dad4503c`.
- Report: `oap/reports/161-q-close-production-acceptance-and-ci.md`.
- Literal implementation first parent:
  `fcabf10dbe04bff3c2b0b449c3131f879dc351fe`.
- Report-only topology, exact shared order bytes, allowed scope verified.
  All ten implementation checks SUCCESS; require reconciliation of completing
  report-head checks before work and record their actual states.
- 161-q reports 629/629 affected tests, 8/8 PostgreSQL, 8/8 governance,
  improved direct two-request acceptance. Its new exact-client label is NO;
  the separate unchanged Objective-160 regression is YES.
- All app/ production and Objective-160 verifier/fixtures remain identical to
  production parent `899bd57e6eef49149d54c65838cf25d043e34a55`.
- Local `ulfe-lmi/slaif-local-coding` PR #7 remains frozen at report head
  `5aec2beccc07432d45e936b82952abf52dfb10d8`, implementation parent
  `64e50172ee02563e2b021554f6b0d345cc7dfdec`, OPEN/CLEAN with test SUCCESS.
- Main, release v0.1.0-rc.1 and unrelated PRs #291/#250/#224 are unchanged.
- Shared activation root:
  `/home/ubuntu/codex-work/slaif-api-gateway`; coding worktree:
  `/home/ubuntu/codex-work/slaif-api-gateway-161`. Preserve unrelated files
  and commit the unchanged strategic order/active through coding-owned Git.

Verify identities; never create another PR or mutate Local/GitHub history.

## Reading and exact allowed paths

Read current governance/coding protocol, 161-q order/report, and the exact
affected functions before edits.

Only these may change:

- `tests/unit/test_codex_0149_local_roundtrip.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `scripts/verify_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-r-bound-snapshot-and-retain-returned-history.md`
- `oap/reports/161-r-bound-snapshot-and-retain-returned-history.md`

All production, policy tests, docs, Objective-160 verifier/hashes/fixtures,
earlier orders/reports, Local, dependencies, DB/schema, CI and governance stay
unchanged. Report docs checked/no update needed because accepted product
behavior and claims are unchanged; explain only the evidence correction.

## Required corrections

### 1. Bound the historical test snapshot

The q helper uses `shutil.copytree(_ORIGINAL_REPO_ROOT, ...)`, which can copy
unrelated or ignored content such as local credentials/catalogs and virtual
environments into pytest temporary roots. Replace it with a finite allowlist
of regular source/test/fixture/doctrine files actually needed by the real
evaluator, or build those inputs synthetically. Do not enumerate/copy the
whole repository and do not expand the ignore list as the solution.

Preserve the narrow Git/blob seams, unchanged historical evaluator/hashes,
real blob-hash check, positive missing=[], and all mutation checks. This is
a unit simulation of a controlled historical snapshot, not current-code
historical attestation.

Add a test with unrelated nested content and a sentinel ignored file in a
synthetic source root proving neither is read/copied; require exact destination
membership. Reject symlink escape for any copied allowlisted input. Keep
filesystem effects entirely inside task-owned temporary roots.

### 2. Retain the actual returned assistant text

q constructs second_body before first_response and hard-codes its history
text. Change the bounded terminal parser to validate and return the first
response's completed assistant output text transiently. Validate the relevant
role/type/string and consistency of output-text done/content/item/completed
events; retain existing sequence/usage/bounds checks. Use only exact type/text
when constructing the second request after that first response succeeds.

The fake provider's first response supplies the synthetic text. The second
request must take text from the actual first Gateway response, and the fake
provider must compare the retained text with what it actually emitted.
Print/report only semantic-equality booleans. No unreviewed response fields
may be copied into assistant request history. If first response is malformed,
fail before the second request.

Add focused mutations proving changed/inconsistent/missing/invalid first
output text cannot produce a passing history comparison, plus a successful
case using a non-default synthetic text to prevent a constant bypass.
Do not claim actual Codex resume; this remains direct bounded synthetic proof.

### 3. Complete the existing bounded direct controls

- Remove the redundant assignment that overwrites after_invalid_role after
  both invalid requests. Compare the original per-request snapshots at their
  correct boundaries and test a first-invalid side effect is detected.
- Set a finite read timeout on accepted fake-upstream sockets and classify
  timeout/short-body/invalid input as closed fixed failures without traceback.
  Keep daemon-thread/process/listener cleanup bounded; no successful report
  while task-owned resources remain running.
- Reject direct-mode/legacy-diagnostic flag conflicts in argument parsing.
  Add focused tests for these controls; do not run legacy diagnostic modes.

## Acceptance and test economy

Run the two complete affected unit files, governance, pinned Ruff check/format,
compilation, whitespace, and exact allowed-path checks. Use a task-private dev
environment and disposable PostgreSQL. Preserve environment/source separation;
no protected credentials or external inference.

Run the corrected two-request direct acceptance using unchanged frozen Local.
Require actual first returned text retained in the crop/history request, exact
source/clean-state checks, normal signing/service authorization, full/crop PNG,
two finalized reservations/ledgers, zero pending/replay, safe invalid requests
without provider/accounting advancement, zero retries and complete cleanup.

Carry 161-q's production/policy/stream/replay/E2E/PostgreSQL regression evidence
forward with exact hashes because those paths are unchanged. Normal CI runs
the full matrix on the new implementation and report commits. Do not rerun
an unrelated full local suite or the unchanged real-Codex verifier.

No strict negative or new product mismatch may be hidden as harness success.
Record actual command counts, failures/corrections, and acceptance chronology.

## Privacy, immutable reporting and merge gate

Task-local Python/dev setup, loopback fake services, detached read-only frozen
Local and disposable DB are authorized. No real Local/Qwen/provider/protected
service, production, real email, Local mutation, release/deploy, merge or
auto-merge. Retain only fixed source commits, safe counts/enums/booleans and
terminal states, never content, bodies, media, IDs/HMACs, secrets, paths,
environment/package output, DB rows/amounts or arbitrary errors.

Commit unchanged r order/active and bounded work on PR #298. Before PASSED,
require the corrected direct proof, focused tests and all ten implementation-
head checks SUCCESS. Publish exactly
`oap/reports/161-r-bound-snapshot-and-retain-returned-history.md` once with
RESULT=PASSED|FAILED, literal verified implementation SHA, Report publication
commit: SELF, topology/scope/source preservation, closure of these exact
review findings, tests/counts/checks, actual retained-response equality,
privacy/cleanup/docs impact and accurate limits.

Do not rewrite q. Clarify that q's fixed-constant comparison proved bounded
assistant input preservation, while r additionally proves the first returned
response is the source of retained history. Preserve new exact-client and
protected acceptance NO; carry Objective-160 regression separately.

Required lifecycle labels:

```text
PREFX-PROOF-ACCEPTED-BY-HUMAN = YES
IMPLEMENTED = YES
TESTED = YES|NO
DIRECT-BOUNDED-FAKE-ACCEPTED = YES|NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
OBJECTIVE-160-FAKE-REGRESSION-ACCEPTED = YES
LOCAL-CROSS-CONTRACT-ACCEPTED = YES|NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```

The report publication is report-only with literal implementation first parent,
verified remote PR #298 head before response OK. Return to the permanent
coding control-wake helper. Strategic independently reviews and verifies every
required report-head check before merge. Following Gateway acceptance/merge,
Local OAP-005 receives the handback for its full fake and bounded protected
matrices; no such Local/protected activation is authorized here.

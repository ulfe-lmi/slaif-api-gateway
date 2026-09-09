# OAP Report — 161-p

RESULT=FAILED

PREFX-PROOF-ACCEPTED-BY-HUMAN = YES
IMPLEMENTED = YES
TESTED = YES
DIRECT-BOUNDED-FAKE-ACCEPTED = YES
EXACT-CODEX-0.149-FAKE-ACCEPTED = YES
LOCAL-CROSS-CONTRACT-ACCEPTED = YES
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO

Report publication commit: SELF

The implementation head is `899bd57e6eef49149d54c65838cf25d043e34a55`, on
branch `oap/161-codex-assistant-output-history`, PR #298, based on
`910ddaa23763883c07f5d2065662eb1157deb9f1` (`main`). The PR remains open and
unmerged. The report publication commit is required to contain only this
report and to have the implementation head as its first parent.

The human accepted the pre-fix basis in 161-p: immutable Local 005-q evidence,
Gateway ownership of the ordinary Responses rejection, and exact Codex
0.149/source provenance. No new pre-fix Codex execution was performed.

The production change adds the default-empty
`assistant_history_content_types` fact to `ResponsesClientPolicySpec` and
enables exactly `{"output_text"}` only in the server-selected Codex 0.149
policy. Generic Responses policy now accepts that part only in an assistant
message on the existing exact Codex 0.149 -> Local Coding pairing. The mapping
is exact, text is non-empty valid Unicode, existing per-item and request-wide
caps apply, canonical output remains `{"type":"output_text","text":...}`,
and UTF-8 bytes enter ordinary input material and token estimation. Default,
OpenAI, Codex 0.147, other roles, extra fields, invalid Unicode, unsupported
media/tools, and malformed shapes remain fail-closed with existing safe errors.
No authority, replay, accounting, persistence, logging, or provider-selection
behavior was broadened.

Focused tests cover the positive assistant history shape, multibyte metering,
roles, default and Codex 0.147 denial, empty/non-string/invalid-Unicode text,
extra fields, per-item/request-wide caps, canonical preservation, and the
declarative client facts. The final affected-file collection was 611 tests;
610 passed, one was skipped, and one failed at the immutable Objective-160
obligation assertion described below. The four required PostgreSQL suites
passed all 8 tests. OAP governance passed 8/8. Documentation hygiene passed
for 79 files, public client environment-name validation passed, Ruff check and
format checks passed, Python compilation passed, and `git diff --check` passed.

The direct bounded acceptance command was the assistant-history verifier's
`--direct-bounded-fake` mode against a detached, clean Local checkout at
frozen report head `5aec2beccc07432d45e936b82952abf52dfb10d8`. It used a
loopback fake downstream and disposable PostgreSQL. The fixed result was:

`VERIFY_CODEX_0149_ASSISTANT_HISTORY_DIRECT_FAKE_OK local_commit=frozen_report_head gateway=2xx invalid=4xx upstream_count=one signed_identity=true history=true image=true accounting=one_finalized pending=zero`

This proved Gateway admission and signing, the separate Local service
authorization, one bounded assistant history part and one image at fake
provider receipt, normal SSE completion, exactly one finalized reservation and
ledger, no pending state, and no provider advancement for the invalid-role
request. The frozen Local checkout remained clean and unmodified. The
unchanged Objective-160 exact Codex 0.149 fake verifier also passed:
`VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_OK turns=2 accounting_rows=2`.
No real-provider or protected Codex vision/resume qualification was attempted;
no such claim follows.

All ten final-head GitHub checks completed on the implementation head:

- `CodeQL` — SUCCESS
- `PostgreSQL integration tests` — SUCCESS
- `Docker Compose smoke` — SUCCESS
- `Playwright browser smoke` — SUCCESS
- `Analyze Python` — SUCCESS
- `Documentation hygiene` — SUCCESS
- `OpenAI-compatible E2E tests` — SUCCESS
- `Analyze (python)` — SUCCESS
- `Analyze (javascript-typescript)` — SUCCESS
- `Unit, lint, and migration head` — FAILURE

The failing remote job ran 3,889 unit tests successfully, skipped 1, and
failed only
`tests/unit/test_codex_0149_local_roundtrip.py::test_obligation_evaluator_reports_exact_empty_missing_list`.
Its immutable pre-161 obligation manifest reports `app_tree` and the changed
allowed production/test paths as missing. The work order explicitly forbids
changing the Objective-160 verifier, fixtures, governance, or historical
evidence, so this failure cannot be repaired within 161-p without violating
the order. It is therefore recorded as the reason for `RESULT=FAILED`; the
production implementation and direct cross-contract acceptance remain
complete.

The five allowed documentation files were updated with the exact pairing,
default-deny policy, bounded text accounting, transient-content boundary, and
unchanged authority/privacy/accounting behavior. No dependencies, migrations,
CI, Local files, protected services, production systems, releases, merges,
secrets, real email, or real upstream calls were used. Task-owned listeners,
databases, temporary checkouts, and temporary test environment were cleaned up.


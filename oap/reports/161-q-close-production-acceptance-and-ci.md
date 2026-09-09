# OAP Report — 161-q

RESULT=PASSED

PREFX-PROOF-ACCEPTED-BY-HUMAN = YES
IMPLEMENTED = YES
TESTED = YES
DIRECT-BOUNDED-FAKE-ACCEPTED = YES
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
OBJECTIVE-160-FAKE-REGRESSION-ACCEPTED = YES
LOCAL-CROSS-CONTRACT-ACCEPTED = YES
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO

Report publication commit: SELF

The q implementation head is `fcabf10dbe04bff3c2b0b449c3131f879dc351fe`,
on branch `oap/161-codex-assistant-output-history`, PR #298, based on
`910ddaa23763883c07f5d2065662eb1157deb9f1` (`main`). The PR remains open and
unmerged. The q continuation preserves production implementation parent
`899bd57e6eef49149d54c65838cf25d043e34a55`; `git diff` confirms no app/
production file changed in q. The report publication commit must contain only
this report and have the q implementation head as its first parent.

161-p's accepted human pre-fix basis remains authoritative. No fresh pre-fix
run, import-diagnostic sequence, or terminal earlier-round retry was run. The
161-p report remains immutable. This report corrects its acceptance arithmetic
and exact-client label with current q evidence; it does not rewrite that prior
record.

The historical Objective-160 obligation unit test is now hermetic. It copies a
controlled temporary snapshot, uses narrow test-local Git/blob seams, runs the
real evaluator, and verifies the real blob-hash helper on known bytes. The
positive snapshot returns exactly `missing=[]`. Independent mutations detect
wrong app-tree input, changed protected blobs, missing required files,
forbidden historical machinery, and missing doctrine links with fixed names.
Historical hashes and the Objective-160 verifier remain byte-identical.

Enabled-policy coverage now proves the exact `input[5].content[0]` assistant
history shape, multiple bounded `output_text` parts mixed with existing
`input_text`, exact and over-limit multibyte text, absent/default/0.147 policy
facts, roles, malformed and extra fields, invalid Unicode, refusal/media/audio
and disguised tool parts. The accepted production semantics remain unchanged:
bounded arrays can contain exact `type`/`text` output parts under only the
selected Codex 0.149 -> Local Coding pair, and normal `input_text` remains
supported.

The strengthened direct bounded acceptance used the unchanged Local checkout
at frozen report head `5aec2beccc07432d45e936b82952abf52dfb10d8`. It attested
the subprocess import source before serving and verified exact HEAD and clean
tracked state before and after. Two synthetic requests traversed actual
Gateway and Local: a full PNG request followed by retained assistant text and
a crop PNG request. The fake downstream observed full/crop classification,
exact assistant role/type/text semantics, service authorization on both
requests, and no extra authority fields. Ordered terminal SSE and detailed
usage were parsed. Two invalid requests (wrong role and extra field) returned
exact safe 4xx responses while provider count, PostgreSQL state, and replay
state remained unchanged. The fixed result was:

`VERIFY_CODEX_0149_ASSISTANT_HISTORY_DIRECT_FAKE_OK local_commit=frozen_report_head source=true gateway=2xx_two invalid=two_4xx upstream_count=two signed_identity=true history=true semantic_equal=true image=full_crop accounting=two_finalized pending=zero replay=zero`

The accounting predicate required exactly two finalized reservations and
ledgers, zero pending/released/failed state, and zero replay references. The
unchanged Objective-160 exact Codex fake regression passed separately:
`VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_OK turns=2 accounting_rows=2`. No new exact
Codex 0.149 same-session vision/resume run was performed, so the new exact
client label is deliberately `NO`; the Objective-160 result is not reused as
that claim. No protected acceptance or real-provider qualification follows.

The complete q affected matrix collected 629 tests and passed all 629:

- `tests/unit/test_codex_0149_local_roundtrip.py`: 14;
- `tests/unit/test_codex_0149_assistant_output_history.py`: 119;
- `tests/unit/test_responses_request_policy.py`: 214;
- `tests/unit/test_codex_client_modules.py`: 39;
- `tests/unit/test_responses_codex_multiturn_replay.py`: 44;
- `tests/unit/test_responses_codex_streaming_tools.py`: 136;
- `tests/unit/test_local_coding_server_module.py`: 40;
- `tests/e2e/test_openai_python_client_responses.py`: 23.

The four required PostgreSQL suites passed all 8 tests. OAP governance passed
8/8. Ruff check and format, Python compilation, documentation hygiene for 79
files, whitespace, and the exact allowed-path proof passed. All ten final-head
GitHub checks on `fcabf10dbe04bff3c2b0b449c3131f879dc351fe` completed
successfully: Unit/lint/migration, PostgreSQL integration, OpenAI-compatible
E2E, Playwright, Docker Compose, Documentation hygiene, Analyze Python, Analyze
(python), Analyze (javascript-typescript), and CodeQL.

The five allowed documentation files now describe bounded arrays, exact
per-part fields, existing `input_text` support, the selected pairing, direct
synthetic acceptance, the separate Objective-160 regression, and the absence
of new real-client/protected claims. No app/production, Local, registry,
orchestration, replay/HMAC, accounting, schema, dependency, CI, governance,
release, or historical verifier file was changed. No protected credentials,
real provider, real email, production service, or raw request/event/content
data was used or retained. Task-owned databases, Local checkout, listeners,
temporary environment, and test resources were cleaned up.


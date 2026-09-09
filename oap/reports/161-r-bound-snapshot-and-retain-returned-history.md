# OAP Report — 161-r

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

The r implementation head is `50dcc3b85d614eb1d0c6196595bf22ef5779f846`,
on branch `oap/161-codex-assistant-output-history`, PR #298, based on
`910ddaa23763883c07f5d2065662eb1157deb9f1` (`main`). Its first parent is q
head `fcabf10dbe04bff3c2b0b449c3131f879dc351fe`; all app/production files
remain byte-identical to production implementation parent
`899bd57e6eef49149d54c65838cf25d043e34a55`. The PR remains open and
unmerged. The report publication commit must contain only this report and
have the r implementation head as its first parent.

161-q's human-accepted pre-fix basis, bounded production behavior, 629/629
affected matrix, PostgreSQL evidence, Objective-160 regression, and q direct
proof remain unchanged. No pre-fix, real-Codex, or legacy diagnostic run was
performed in r.

The historical evaluator snapshot now copies only a finite allowlist of the
source/test/fixture/doctrine files consumed by the real evaluator. It does not
copy the repository, ignored content, catalogs, credentials, virtual
environments, or unrelated nested files. Regular-file and resolved-path checks
reject symlink escapes. Unit coverage proves exact destination membership and
an ignored sentinel/unrelated nested file exclusion. The real evaluator still
returns `missing=[]` for the controlled snapshot, the real blob-hash helper is
verified on known bytes, and independent app-tree, protected-blob, required
file, forbidden-machinery, and doctrine-link mutations retain precise fixed
obligations.

The direct verifier now parses the complete bounded terminal SSE lifecycle and
returns the first response's actual assistant output text only after validating
role, output-text types, non-empty valid Unicode text, consistency across delta,
done, content, item, completed output, and usage. The fake provider emits a
non-default synthetic text. The second request is constructed only after that
returned text is validated, with exactly the selected `type`/`text` fields.
Focused mutations prove changed, missing, inconsistent, wrong-role, and
invalid returned text cannot pass. The direct observer compares the retained
text against the text it emitted, while preserving full/crop image checks,
source attestation, exact two finalized reservations/ledgers, zero pending and
replay state, two invalid safe 4xx requests with unchanged snapshots, bounded
socket reads, subprocess cleanup, and fixed failure output. Its fixed result
was:

`VERIFY_CODEX_0149_ASSISTANT_HISTORY_DIRECT_FAKE_OK local_commit=frozen_report_head source=true gateway=2xx_two invalid=two_4xx upstream_count=two signed_identity=true history=true semantic_equal=true image=full_crop accounting=two_finalized pending=zero replay=zero`

The fresh r affected unit files collected 138 tests and passed all 138:

- `tests/unit/test_codex_0149_local_roundtrip.py`: 15;
- `tests/unit/test_codex_0149_assistant_output_history.py`: 123.

The q evidence carried forward without production changes: 629/629 affected
tests, 8/8 required PostgreSQL tests, 8/8 OAP governance, the unchanged
Objective-160 fake regression
`VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_OK turns=2 accounting_rows=2`, and q's
successful direct acceptance. All ten r implementation-head GitHub checks
completed successfully: Unit/lint/migration, PostgreSQL integration,
OpenAI-compatible E2E, Playwright, Docker Compose, Documentation hygiene,
Analyze Python, Analyze (python), Analyze (javascript-typescript), and CodeQL.

No new exact Codex 0.149 same-session vision/resume run was performed, so
`EXACT-CODEX-0.149-FAKE-ACCEPTED = NO` remains explicit. The separate
Objective-160 fake regression is retained as its own acceptance. Protected
acceptance, real provider inference, merge, release, and production claims
remain absent.

No documentation update was needed in r because product behavior and claims
were unchanged; q already corrected the five compatibility/accounting/security
documents. No production, Local, registry, orchestration, replay/HMAC,
accounting, schema, dependency, CI, governance, earlier report, or historical
verifier file changed. No protected credentials, raw content, request/event
bodies, IDs/HMACs, database rows, real email, or external inference were used
or retained. Task-owned Local checkout, test environment, listeners, and
temporary resources were cleaned up.


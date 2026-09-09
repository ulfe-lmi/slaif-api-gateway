# OAP Coding-Agent Report — 161-a

## Status

RESULT=FAILED

Implementation head SHA: 9e9de4fe3bd1e12747021b4a98ab04aa474ea655
Report publication commit: SELF

Objective 161-a stopped at the mandatory prove-before-fix boundary. The
verifier reproduced the clean Gateway rejection of Codex 0.149 assistant
`output_text` history, but its required synthetic image/crop predicate was not
proved. No production behavior was changed.

## Authoritative topology

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR: #298, `oap/161-codex-assistant-output-history`
- Base: `main` at `910ddaa23763883c07f5d2065662eb1157deb9f1`
- Activation commit: `b4a95d7` (exact `oap/active` and 161-a order only)
- Starting implementation head after activation: `b4a95d7`
- Final verifier-only implementation head: `9e9de4fe3bd1e12747021b4a98ab04aa474ea655`
- New PR: yes; merge: no; auto-merge: no
- Historical PR #291: untouched
- Allowed implementation files changed: the new verifier
  `scripts/verify_codex_0149_assistant_output_history.py` and its new unit
  test `tests/unit/test_codex_0149_assistant_output_history.py` only. No
  `app/` file, dependency, fixture, database schema, Local file, or Qwen file
  changed.

The activation order and `oap/active` were committed byte-for-byte as
`b4a95d7`; the order was not edited after activation. The report is the only
file changed by this publication commit.

## Prove-before-fix evidence

The task-local Codex package was verified as `@openai/codex@0.149.0`, with
request and stream retries set to zero. The synthetic run used the unchanged
Gateway base, a signed fake Local, a fake downstream SSE provider, disposable
PostgreSQL, and a private temporary Codex home/workspace. No protected
credential, Qwen service, real provider, or production service was contacted.

The natural client sequence reached two successful Gateway/Local turns for the
first Codex session (function call/result followed by an assistant message),
then one resumed Gateway request. Safe facts from the resumed request were:

| Predicate | Result |
| --- | --- |
| Gateway request/status progression | `200,200,400` |
| Fake Local request progression | exactly `2`, both signed; no rejected-turn advance |
| Retry | none; one resumed request |
| Gateway error code | `responses_input_content_part_not_supported` |
| Error parameter | `input[5].content[0].type` |
| Prior assistant message role | exactly `assistant` |
| Prior content-part type | exactly `output_text` |
| Prior text | nonempty bounded valid-Unicode string; value discarded |
| Image/crop input-part classes | `zero,zero,zero` across the bounded request projections |

The exact code/parameter/history facts prove the pre-fix rejection mechanism.
The command contained the bounded resume image option, but the actual
Gateway-bound request projections contained no image part. Therefore the
required 005-q image/crop continuation was not established, and no production
relaxation is authorized by this round.

No raw prompt, image, assistant text, body, SSE payload, identity, item ID,
call ID, credential, endpoint, database URL, or arbitrary subprocess error was
retained or printed. The verifier emitted only the fixed failure class
`history_projection_image_count_zero_sequence_zero_zero_zero`.

## Verification

- New verifier unit tests: 6 passed.
- New verifier compilation: passed.
- Ruff check on changed Python: passed.
- Ruff format check on changed Python: passed.
- Exact pre-fix verifier at the final verifier head: failed closed with the
  bounded image-projection class above.
- No Local 005-q cross-contract acceptance run: not run because section A
  failed before the production-fix boundary.
- No PostgreSQL product integration, final fake acceptance, or protected
  acceptance run: not run.

Remote PR #298 checks for the final verifier head were:

- Unit, lint, and migration head: FAILED.
- PostgreSQL integration tests: SUCCESS.
- OpenAI-compatible E2E tests: SUCCESS.
- Playwright browser smoke: SUCCESS.
- Docker Compose smoke: SUCCESS.
- Documentation hygiene: SUCCESS.
- Analyze Python: SUCCESS.
- Analyze (python): SUCCESS.
- Analyze (javascript-typescript): SUCCESS.
- CodeQL: SUCCESS.

The unit failure is an immutable governance conflict, not a product test
failure: `tests/unit/test_oap_governance.py` requires the exact order first
line `# OAP Work Order — 161-a` and the literal `PR mode: `CREATE_NEW_PR``,
while the activated strategic order begins `# Objective 161-a order — Codex
0.149 assistant output history` and does not contain that phrase. The order
is strategic-owned and was preserved unchanged; neither it nor the governance
test was modified.

## Required lifecycle labels

IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO

## Scope, privacy, and documentation

No Gateway production behavior, assistant-history policy, Local behavior,
provider behavior, replay/HMAC, identity, route, tool authority, quota,
pricing, accounting, schema, dependency, or CI behavior was changed. No
documentation was changed because the version-owned behavior was not
implemented. Documentation impact: no implemented compatibility claim is
made; protected acceptance remains `NO`.

Cleanup of the verifier’s disposable roots, fake Local, PostgreSQL database,
Codex installation, workspace, and private artifacts completed through its
bounded cleanup paths. No protected traffic occurred. The strategic model must
resolve the immutable-order governance conflict and the missing image/crop
wire evidence before any continuation considers a production correction.

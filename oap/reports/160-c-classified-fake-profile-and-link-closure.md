# Objective 160-c report — classified fake profile and link closure

RESULT=FAILED

160-c continued existing PR #297 only. It corrected the permanent doctrine
link evaluator, made the Gateway observer's already-captured classes
observable in a finite failure code, and ran exactly one classified exact-Codex
diagnostic. The diagnostic did not prove a verifier configuration mismatch and
did not establish a safe product error contract. The order therefore required
failure publication and stopping. No final fake acceptance retry and no
protected/provider/Qwen/real Local Coding request was made.

## OAP and PR topology

- Repository: `ulfe-lmi/slaif-api-gateway`
- Base: `main` at `07ae3cce21c52654bdec1f50bc7e5da9c59082c6`
- Existing PR: #297, branch `oap/160-idless-tool-replay-clean-stack`, open
- 160-a immutable report/start head: `e6c7ea11318ad870f2c0aa792b8b360b53591cb7`
- 160-b immutable report/start head: `84ee7fe9f6bc7e7dab8948fcdfb530d820af55f6`
- 160-c activation commit: `ea8c0247003284d0286dd7c73cc617aa8654df8e`
- 160-c implementation head: `0785631b081c5a653cb76d8298115ae848f1ed92`
- Report publication commit: SELF
- No merge and no auto-merge

The activation commit contains only the exact `oap/active` selector and 160-c
order. The implementation diff after activation contains only:

- `scripts/verify_codex_0149_local_roundtrip.py`
- `tests/unit/test_codex_0149_local_roundtrip.py`

No app, product, documentation, accepted test blob, fixture, Local, Qwen,
schema, migration, or Objective-155 path changed in 160-c.

## Doctrine-link correction and tests

The evaluator now checks the actual authority locations: the root
`AGENTS.md` reference to `AGENTIC_CLIENT_INTEGRATION.md`, plus resolving
`../AGENTIC_CLIENT_INTEGRATION.md` links in `docs/module-architecture.md`,
`docs/responses-compatibility.md`, and `docs/compatibility-matrix.md`. The
incorrect check for unrelated provider/security filenames inside `AGENTS.md`
was removed.

Pure mutation tests remove each required location in turn and prove the exact
fixed missing class. The clean evaluator result was exactly:

```text
missing=[]
```

The evaluator uses local immutable blob/tree facts and does not depend on
GitHub, OAP reports, mutable branches, protected resources, or external
services.

## Classified exact-Codex diagnostic

After the complete verifier unit preflight passed, exactly one task-local
`@openai/codex@0.149.0` diagnostic ran against the real Gateway candidate, a
bounded fake Local endpoint, and disposable PostgreSQL using numeric loopback
and zero retries. The sole emitted line was:

```text
VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_FAILED code=gateway_requests_one_status_5xx_error_other_shape_error_server_exception_none_profile_stream_true_function_custom_web_search_input_message
```

This bounded projection means: one Gateway Responses request; a 5xx status
class; no allowlisted Gateway error code; server-error response shape; no
observer exception; and the exact bounded request-profile class
`stream_true_function_custom_web_search_input_message`. Fake Local received no
admitted request. The result is not a proven verifier model-catalog,
key/route, prompt, fake-server, environment, or observer mismatch, and it is
not sufficient to claim a new Gateway product contract. No correction to
product behavior was authorized and no final fake two-turn run was attempted.

The diagnostic retained no raw request/response body, prompt, description,
schema, argument, result, identifier, call ID, credential, URL, header, or
exception text. Its projection is bounded to fixed count/status/error/profile/
shape/exception classes.

## Product and exact evidence carried forward

Product `G_clean` remains the accepted 160-a implementation:

- `d625af9eb3df45c163342a05e03cda2d3dd0d7c4`
- exact app tree `bd536a282362cc549cc0c5518db8e743af667b63`
- empty mechanical app diff from accepted `acea2af4ca0f4586fc159c91607e1848f53f1107`

The six production blobs, five permanent test blobs, unchanged Responses E2E
blob, and five permanent fixture blobs were reverified against the immutable
160-a targets. The 160-a PostgreSQL replay integration, full Responses E2E,
security, identity, stream, accounting, privacy, and historical-machinery
evidence remains unchanged and is carried forward only as already-recorded
evidence; it is not upgraded by this failed diagnostic.

## Verification

- Compact verifier unit file: 10 passed
- Verifier Ruff: PASS
- Verifier Python compilation: PASS
- `git diff --check`: PASS
- Product/app tree and exact blob evaluator: PASS, `missing=[]`
- Analyze (javascript-typescript): PASS
- Analyze (python): PASS
- Analyze Python: PASS
- CodeQL: PASS
- Docker Compose smoke: PASS
- Documentation hygiene: PASS
- OpenAI-compatible E2E tests: PASS
- Playwright browser smoke: PASS
- PostgreSQL integration tests: PASS
- Unit, lint, and migration head: PASS

All ten required checks were green on implementation head
`0785631b081c5a653cb76d8298115ae848f1ed92` before this report-only commit.

## Cleanup and boundaries

The exact task-local root `/tmp/slaif-160c-check.JOOeZw` was removed by
validated non-trash deletion and verified absent. The final PostgreSQL check
found zero databases with the `slaif_gateway_160_` prefix. No protected
runtime reference or provider credential was created or read. No protected,
provider, Qwen, or real Local Coding request was made.

The truthful outcome is an unresolved Gateway-side 5xx during the local fake
diagnostic, not a verifier, Local, Qwen, provider, or ownership conclusion.
This report makes no acceptance, release, production, or broad compatibility
claim. Strategic review must determine any later continuation; PR #297 was not
merged.

# Objective 160-d report — valid Local service fixture and final fake

RESULT=PASSED

160-d corrected the verifier-only Local service credential fixture identified
by source correlation, added the exact closed error-code vocabulary, and ran
the one authorized final exact-Codex fake acceptance. The fake acceptance
passed. No protected, provider, Qwen, or real Local Coding service was
contacted.

## OAP and PR topology

- Repository: `ulfe-lmi/slaif-api-gateway`
- Base: `main` at `07ae3cce21c52654bdec1f50bc7e5da9c59082c6`
- Existing PR: #297, branch `oap/160-idless-tool-replay-clean-stack`, open
- Prior immutable 160-c report/start: `123f598cf920183e1f56a275194bbfe50d1f7227`
- 160-d activation commit: `69c965815d2e7d2be34f230287097c73fb564397`
- 160-d implementation head: `9d247e7f3d8fd6a588976840c4657181b7486b81`
- Report publication commit: SELF
- No merge and no auto-merge

The activation commit contains only the exact 160-d `oap/active` selector and
order. The implementation diff after activation contains only:

- `scripts/verify_codex_0149_local_roundtrip.py`
- `tests/unit/test_codex_0149_local_roundtrip.py`

No app, product, documentation, accepted test blob, fixture, Local, Qwen,
schema, migration, or Objective-155 path changed in 160-d.

## Credential fixture correction

The prior fixed Local service token was 29 ASCII bytes and therefore failed the
accepted `validate_local_coding_secret()` contract before network access. It
was replaced with one unconditional fixed printable-ASCII synthetic token in
the accepted 32–4096-byte range. The Local service, signing, and derivation
fixtures are each printable ASCII, within the accepted bound, and pairwise
distinct. No credential value is included in this report.

The source-reviewed `local_coding_service_credential_invalid` code is now in
the bounded Gateway diagnostic vocabulary. Pure tests prove that it remains
visible as an allowlisted class while unknown codes remain `other`.

## Final fake acceptance

After the complete verifier preflight passed (12 unit tests, Ruff, and
compilation), exactly one zero-retry task-local `@openai/codex@0.149.0`
acceptance ran against the frozen Gateway app, a bounded signed fake Local
endpoint, and disposable PostgreSQL over numeric loopback. The fixed verifier
result was exactly:

```text
VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_OK turns=2 accounting_rows=2
```

The successful run proved:

- task-local Codex package/executable provenance and version `0.149.0`;
- request and stream retry settings were both zero;
- two Gateway Responses admissions and two signed fake-Local requests;
- a first function lifecycle with a syntactically valid non-Codex-prefixed
  item ID;
- actual Codex continuation omission of the item ID while preserving the
  mandatory call ID;
- one approved local function execution and one adjacent matching output;
- Gateway same-key call-ID HMAC replay ownership without fabricated IDs;
- a second normal assistant-message lifecycle and normal SSE closes;
- two finalized reservations and two finalized ledgers with zero pending;
- signed body/header verification, service-authentication substitution, and
  no public bearer forwarding;
- no hosted-tool authority, raw-value evidence, protected resource, or
  external service.

The verifier retained only bounded counters, booleans, structural classes, and
fixed codes. It did not emit or persist prompts, bodies, descriptions, schemas,
arguments, results, IDs, call IDs, credentials, endpoints, headers, or
arbitrary exception text.

## Frozen product and carried-forward evidence

Product `G_clean` remains the accepted implementation
`d625af9eb3df45c163342a05e03cda2d3dd0d7c4`, with exact app tree
`bd536a282362cc549cc0c5518db8e743af667b63` and empty mechanical app diff
from accepted `acea2af4ca0f4586fc159c91607e1848f53f1107`.

The six production blobs, five permanent test blobs, unchanged Responses E2E
blob, and five permanent fixture blobs remain exact. The 160-a PostgreSQL
replay, full Responses E2E, identity, stream, accounting, security, privacy,
and historical-machinery evidence is unchanged and is carried forward only as
previously recorded evidence.

## Verification and CI

- Compact verifier unit file: 12 passed
- Verifier Ruff: PASS
- Verifier Python compilation: PASS
- `git diff --check`: PASS
- Product/app tree and exact blob checks: PASS
- `evaluate_obligations()`: `missing=[]`
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
`9d247e7f3d8fd6a588976840c4657181b7486b81` before report publication.

## Cleanup and boundaries

The exact task-local root `/tmp/slaif-160d-check.Hv1oS8` was removed by
validated non-trash deletion and verified absent. The final PostgreSQL check
found zero databases with the `slaif_gateway_160_` prefix. No protected
runtime reference or provider credential was created or read. No protected,
provider, Qwen, or real Local Coding request was made.

This report records clean fake acceptance only. It is not a protected
qualification, release, production-certification, or broad compatibility
claim. Local OAP-005/protected acceptance remains a separate strategic handoff;
PR #297 was not merged.

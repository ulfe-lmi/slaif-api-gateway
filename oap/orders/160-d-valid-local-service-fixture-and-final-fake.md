# OAP Work Order — 160-d

## Objective

Continue Objective 160 on existing PR #297 solely to correct the compact
verifier's invalid 29-byte synthetic Local service credential, add the exact
source-reviewed safe error code, and run one final exact-Codex fake two-turn
acceptance.

No product behavior change is authorized. Product
`G_clean=d625af9eb3df45c163342a05e03cda2d3dd0d7c4` and accepted app tree
`bd536a282362cc549cc0c5518db8e743af667b63` remain frozen.

## Verified diagnosis and state

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Existing PR: #297, branch `oap/160-idless-tool-replay-clean-stack`, base
  `07ae3cce21c52654bdec1f50bc7e5da9c59082c6`.
- PR mode: `AMEND_EXISTING_PR`.
- Immutable 160-c FAILED report/current head:
  `123f598cf920183e1f56a275194bbfe50d1f7227`.
- 160-c verifier implementation:
  `0785631b081c5a653cb76d8298115ae848f1ed92`.
- 160-c classified one request as 5xx/server-error/other with no observer
  exception and zero fake-Local requests.
- The verifier constant `local-roundtrip-service-token` is exactly 29 ASCII
  bytes.
- Accepted `validate_local_coding_secret()` requires printable ASCII length
  32–4096. `LocalCodingAdapter._validate_secret_roles()` applies it to the
  provider-row service credential and raises fixed
  `local_coding_service_credential_invalid` before network.
- That fixed code was absent from the verifier's closed Gateway code set, so
  the diagnostic correctly fell back to `other`.
- This proves a verifier fixture/configuration defect, not a Gateway product
  defect. PR #291, Local, Qwen, protected systems, and all accepted blobs are
  unchanged.

Do not create another PR, merge, or enable auto-merge.

## Allowed paths

- `scripts/verify_codex_0149_local_roundtrip.py`
- `tests/unit/test_codex_0149_local_roundtrip.py`
- `oap/active`
- `oap/orders/160-d-valid-local-service-fixture-and-final-fake.md`
- `oap/reports/160-d-valid-local-service-fixture-and-final-fake.md`

No other path may change.

## Required correction

1. Replace the 29-byte service-token fixture with one unconditional fixed
   printable-ASCII synthetic value of at least 32 and at most 4096 bytes.
2. Keep service, signing, derivation, Gateway HMAC, admin, and one-time-secret
   fixture roles pairwise distinct where their contracts require it. Do not
   derive/retry/randomize the service token.
3. Add a pure test proving each Local service/signing/derivation fixture meets
   the accepted length/ASCII contract and the three roles are distinct.
4. Add exact source-reviewed
   `local_coding_service_credential_invalid` to the closed Gateway diagnostic
   code vocabulary and test that it is retained while an unknown code remains
   `other`.
5. Preserve observer ownership, actual doctrine-link checks, self-contained
   blob anchors, `evaluate_obligations()==[]`, bounded request projection,
   exact Codex provenance, zero retries, signed-body checks, replay/accounting
   predicates, privacy, and cleanup.

Do not change the synthetic request/tool/profile to steer around any unrelated
failure. The service credential is the only source-proven correction.

## Final fake acceptance

After complete pure/unit preflight passes, execute exactly one zero-retry:

`task-local @openai/codex@0.149.0 -> real frozen Gateway app -> fake Local`

with numeric loopback and disposable PostgreSQL only.

Acceptance requires the exact success line:

`VERIFY_CODEX_0149_LOCAL_ROUNDTRIP_OK turns=2 accounting_rows=2`

and all of:

- exact task-local package/executable/version provenance;
- two Gateway requests and two signed fake-Local requests;
- first function lifecycle with non-Codex-prefixed item ID;
- actual client omits item ID, preserves call ID, executes one approved local
  tool, and sends adjacent matching output;
- Gateway authenticates via existing same-key call-ID HMAC and never fabricates
  an item ID;
- final assistant-message lifecycle and normal close;
- two finalized reservations, two finalized ledgers, zero pending;
- no public bearer forwarding, hosted authority, raw-value evidence, retry,
  observer exception, protected resource, or external service.

If this final run fails for any new reason, publish its exact closed safe class
and stop. Do not make another verifier or product correction in 160-d.

## Verification

- Run complete `tests/unit/test_codex_0149_local_roundtrip.py` including token,
  allowlist/fallback, observer, link mutation, manifest, output/privacy, and
  cleanup tests.
- Run Ruff check, Python compilation, and `git diff --check` on the two files.
- Prove non-OAP diff from `0785631...` is exactly the two verifier files.
- Reverify `evaluate_obligations()==[]`, product `G_clean`, app tree, six
  production/five test/five fixture blobs, and historical machinery absence.
- Carry forward unchanged 160-a product/replay/PostgreSQL/E2E evidence only
  after blob verification.
- Require all ten GitHub checks successful on the exact final report head.

No required evidence may be skipped, xfailed, pending, cancelled, missing, or
environment-blocked.

## Non-goals

Do not modify app/product, accepted tests/fixtures, docs, doctrine, Local Coding,
Qwen, schema/migrations, PR #291, or main. Do not make protected/provider calls,
add Objective-155 machinery, begin generic refactoring, merge, or auto-merge.

## Immutable report

Publish exactly:

`oap/reports/160-d-valid-local-service-fixture-and-final-fake.md`

It must include:

- `RESULT=PASSED` or `RESULT=FAILED`;
- exact topology/report-only facts;
- old/new synthetic credential length classes and source contract;
- closed error-code test and unknown fallback;
- unchanged actual link evaluator with `missing=[]`;
- exact final fake command result and all turn/replay/accounting/privacy
  predicates;
- frozen product `G_clean`, app/test/fixture blobs, and historical absence;
- focused tests/lint/compile/diff and all ten final report-head checks;
- cleanup, documentation impact, and Local OAP-005/release limitations.

The implementation commit may change only the two verifier files. Publish one
report-only commit whose first parent is that implementation and whose only
changed path is the report. Continue to identify `d625af9...` as product
`G_clean` and the verifier head separately.

Verify remote PR head and all claims, write exactly `OK` to the response FIFO,
and return to one blocking control-FIFO read. Do not contact Local PR #7;
strategic handles the final handoff after acceptance/merge.

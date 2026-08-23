# OAP Work Order — 149-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/149-facial-adapter-qualification`
Base: `main @ 1505dcbc36fa43e3d890d8c68fd6aa151470560e`
Title: `test: qualify facial scoring adapter boundaries and operator evidence`

## Objective and reason

Close the bounded evidence and operator-documentation gap for the merged
`facial-manipulation-scoring` mini-adapter. Prove through focused mock and
PostgreSQL evidence that the adapter remains inside normal gateway
authentication, policy, request/rate/concurrency, quota, accounting, audit,
privacy, and key-revocation boundaries. Provide a reproducible, credential-free
operator setup description without claiming live deployment qualification.

This is a post-MVP extension and the terminal proposed objective in the facial
mini-adapter chain. It does not authorize a live score request: no credential
has been supplied by the human, so live native qualification must be reported
as not run.

## Reconciled current state

- Objective 148 is terminal: PR #283 merged at
  `2026-08-23T16:33:02Z` as `1505dcbc36fa43e3d890d8c68fd6aa151470560e`.
- The merged adapter accepts one supported base64 image data URL on
  non-streaming `POST /v1/chat/completions`, translates it to multipart
  `/v1/score`, and returns a safe single-choice response with zero tokens.
- The merged foundation owns fixed `0 EUR` request pricing, one-request/zero-
  token reservation, PostgreSQL finalization/release, and normal key/policy/
  rate/concurrency/audit boundaries. The adapter owns none of those controls.
- The current service health and OpenAPI observations were refreshed at
  activation: both candidate origins answer healthy and their OpenAPI SHA-256
  is `8e77d16fb308d354bac8e84bfa7ba90c8cf77b8df644d59e391d7b68aa023832`.
  No score request was made.
- The operator docs already distinguish HTTPS preference from explicitly
  audited internal HTTP. No service address, provider row, credential, image,
  data URL, or live result is in the repository.

## Bounded requirements

1. Add focused PostgreSQL-backed evidence for a configured
   `facial_scoring`/`module` route and fixed EUR pricing that proves one
   reserved request, zero reserved/final tokens, exact `0 EUR` estimated and
   actual cost, successful finalization, and failed downstream release.
   Exercise the existing request-limit, concurrency/fence, revocation, and
   audit boundaries where the test infrastructure supports them; do not add a
   second quota/accounting implementation.
2. Extend focused mocked Chat compatibility evidence to cover the public model
   with one synthetic image data URL, scored and unscorable native results,
   safe native 4xx/5xx/timeout/malformed outcomes, stream rejection, and
   unsupported Responses/legacy/remote/multiple-image/tools/non-image forms.
   Use the existing TestClient/RESPX or official-client-equivalent harness;
   never call the actual facial service.
3. Extend operator documentation with a non-secret setup example: provider
   slug `facial_scoring`, kind `module`, operator-selected base URL, server
   environment variable `FACIAL_SCORING_API_KEY`, finite timeout,
   `max_retries=0`, public route `facial-manipulation-scoring`, exact narrow
   Chat capability metadata, and a fixed pricing row of `0 EUR` per request.
   State plainly that zero price does not remove request/rate/concurrency,
   quota, revocation, expiry, audit, or failed-attempt controls.
4. Document the current evidence classification as mocked/PostgreSQL
   qualification only. Live score qualification is `NOT RUN` because no
   authorized credential exists; do not imply endpoint reachability, model
   accuracy, authenticity, calibration, certification, production readiness,
   or SLA from the mocks or health observations.
5. Correct only directly evidenced defects in the adapter or its boundary
   documentation. Any such fix must remain on this PR and within the paths
   below; do not broaden into a provider abstraction, new API, calibration,
   moderation, or release program.

## Explicit non-goals

- No live credential access, live `/v1/score` request, production route/provider
  row, endpoint rollout, deployment change, or production database mutation.
- No Responses, legacy Completions, streaming, remote image fetching,
  persistence, calibration, thresholding, moderation, retraining, or new API.
- No raw API key, image bytes, data URL, native payload, unbounded score,
  service address, or client text in logs, fixtures, reports, OAP, or committed
  configuration.
- No changes to `ARCHITECTURE.md`, release tags, MVP claims, or unrelated
  provider behavior.

## Exact allowed paths

```text
docs/configuration.md
docs/compatibility-matrix.md
docs/provider-forwarding-contract.md
tests/integration/test_facial_scoring_adapter_postgres.py
tests/integration/test_facial_scoring_adapter_qualification_postgres.py
tests/unit/test_facial_scoring_adapter.py
tests/unit/test_v1_chat_completions_forwarding.py
oap/orders/149-a-facial-adapter-qualification-and-operator-evidence.md
oap/reports/149-a-facial-adapter-qualification-and-operator-evidence.md
oap/active
```

No other path may change. The new PostgreSQL test file is the only new test
path authorized; existing tests may be amended only for the listed evidence.

## Acceptance criteria

- Focused PostgreSQL evidence proves exact zero-EUR/zero-token success and
  safe failed-request release, and records only safe route/provider/request
  metadata. It demonstrates that request limits, concurrency/fencing,
  revocation, expiry, and audit controls remain gateway-owned; no image,
  data URL, native response, credential, or raw client content is persisted.
- Mocked compatibility evidence covers scored and unscorable output, all
  bounded error paths, and the supported/unsupported request matrix without
  any actual facial-service call.
- Operator documentation is sufficient to configure the module without a
  committed secret or hardcoded deployment address and explains the
  `0 EUR`/unlimited-access distinction and HTTP audit boundary.
- Static privacy/security inspection finds no forbidden credential, image,
  data URL, native payload, service address, or unbounded output in changed
  files or test evidence.
- The final report clearly separates mock/PostgreSQL proof from the unrun live
  qualification and makes no production or accuracy claim.

## Required verification

Run focused checks on the final implementation head:

```text
python -m pytest \
  tests/unit/test_facial_scoring_adapter.py \
  tests/unit/test_v1_chat_completions_forwarding.py -q
python -m pytest \
  tests/integration/test_facial_scoring_adapter_postgres.py \
  tests/integration/test_facial_scoring_adapter_qualification_postgres.py -q
python -m ruff check \
  tests/unit/test_facial_scoring_adapter.py \
  tests/unit/test_v1_chat_completions_forwarding.py \
  tests/integration/test_facial_scoring_adapter_postgres.py \
  tests/integration/test_facial_scoring_adapter_qualification_postgres.py
git diff --check
```

CI is required on the final PR head. Skipped, pending, missing, cancelled, or
environment-blocked checks are not passes. Inspect final diff, report parent/
tree, mock HTTP calls, database rows, audit metadata, and negative evidence.

## Report and publication contract

The coding agent must create exactly one PR for 149-a, never merge or enable
auto-merge, and publish the immutable report only after implementation commits
are pushed. The report publication commit must change only
`oap/reports/149-a-facial-adapter-qualification-and-operator-evidence.md` and
must identify the exact final head, evidence commands/results, privacy and
accounting boundaries, and the explicit live-test-not-run status.

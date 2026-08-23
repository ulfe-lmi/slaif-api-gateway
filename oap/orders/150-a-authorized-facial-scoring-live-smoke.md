# OAP Work Order — 150-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/150-facial-live-qualification`
Base: `main @ fc6e163b091439e880019877e5fd08fbfa3de7ed`
Title: `docs: record authorized facial scoring live smoke evidence`

## Objective and reason

Record the first explicitly authorized live smoke evidence for the reviewed
`facial_scoring` native service after the human supplied a testing credential.
The adapter implementation and its mocked/PostgreSQL gateway qualification are
already merged by objectives 148 and 149. This round closes only the evidence
classification gap created by the previously unrun native smoke.

The human-authorized preflight used the operator-selected service origin,
`X-API-Key`, one disposable synthetic 1x1 PNG multipart upload in the native
`image` field, and no client gateway credential. It returned HTTP 200 with the
native `unscorable` result and reason `no_face_detected`. This proves that the
testing credential was accepted and that the native endpoint returned the
reviewed response shape for a valid multipart request; it does not prove a
positive facial score, model accuracy, authenticity, calibration, or production
readiness.

## Reconciled current state

- Objective 149-a is terminal in PR #284, merged as `fc6e163`.
- The merged adapter accepts exactly one supported image data URL on
  non-streaming `POST /v1/chat/completions`, translates it to native multipart,
  and maps scored or unscorable results to an OpenAI-shaped response.
- Existing mock and disposable-PostgreSQL evidence remains authoritative for
  gateway policy, quota, accounting, audit, privacy, and failure boundaries.
- The live native preflight was explicitly authorized by the human in this
  turn. The credential was used transiently and is not available to the
  repository or normal CI.

## Bounded requirements

1. Update the facial-module compatibility and operator documentation to record
   the authorized live native smoke as `PASS` for credential acceptance,
   multipart transport, and safe native schema handling. State that the result
   was `unscorable/no_face_detected`, so no positive score qualification was
   established.
2. Keep the qualification classification precise: mocked HTTP plus PostgreSQL
   gateway evidence, and one authorized live native smoke. Do not claim live
   gateway end-to-end qualification, model accuracy, authenticity, calibration,
   certification, production readiness, or an SLA.
3. Preserve the existing operator contract: provider slug `facial_scoring`,
   kind `module`, operator-selected origin, `FACIAL_SCORING_API_KEY`, finite
   timeout, `max_retries=0`, exact public model, Chat Completions only, one
   data-URL image, fixed `0 EUR`, and normal gateway controls.
4. Publish an immutable report that records the evidence classification,
   sanitized result, exact final head, and all negative/security/privacy
   boundaries. The report must not reproduce the credential, endpoint address,
   image bytes, data URL, client key, raw request, or raw response body.

## Explicit non-goals and safety boundaries

- Do not make another live request unless the explicitly supplied testing key
  is present through a secure out-of-band environment mechanism; never place it
  in an order, report, fixture, log, command output, commit, or CI setting.
- Do not add a production provider row, deployment change, endpoint rollout,
  credential rotation, health probe, retry, or new API surface.
- Do not add a positive-score fixture, claim model quality, or use a real
  person's image. The disposable synthetic image is transport evidence only.
- Do not enable Responses, legacy Completions, streaming, remote image fetch,
  persistence, calibration, moderation, retraining, or token pricing.
- Do not change runtime adapter code, migrations, `ARCHITECTURE.md`, release
  claims, or unrelated providers.

## Exact allowed paths

```text
docs/configuration.md
docs/compatibility-matrix.md
docs/provider-forwarding-contract.md
oap/orders/150-a-authorized-facial-scoring-live-smoke.md
oap/reports/150-a-authorized-facial-scoring-live-smoke.md
oap/active
```

No other path may change. The report publication commit must be the final
report-only `SELF` commit and must change only the report path.

## Acceptance criteria

- The three named documentation surfaces distinguish mocked/PostgreSQL
  qualification from the authorized live native smoke and retain all current
  limitations.
- The report records HTTP 200, native `unscorable`, and `no_face_detected`
  without exposing secret or content material. It explicitly says that no
  positive score or model-quality claim follows.
- No changed file contains the credential, service address, image bytes, data
  URL, raw request, raw response, or client authorization value.
- Existing zero-EUR/zero-token accounting and gateway-control statements remain
  unchanged and honest.
- Exactly one PR is created for 150-a. The coding agent does not merge or
  enable auto-merge.

## Required verification

```text
git diff --check
python -m pytest tests/unit/test_facial_scoring_adapter.py tests/unit/test_v1_chat_completions_forwarding.py -q
python -m ruff check tests/unit/test_facial_scoring_adapter.py tests/unit/test_v1_chat_completions_forwarding.py
```

Also inspect the final diff for credential, endpoint, image, data-URL, raw
payload, and scope leakage. CI required checks must be green on the final
report head. No live call is required from CI; the sanitized live result above
is the authorized external evidence for this objective.

## Report and publication contract

The report must identify objective 150-a, PR, base, branch, activation commit,
implementation head, report publication `SELF` commit, exact evidence
classification, verification commands/results, and negative evidence. It must
state that the live smoke used an explicitly human-authorized testing key but
must not reveal the key or any raw request/response/image material. The coding
agent must publish the report only after implementation documentation commits
are pushed, and must return exact `OK` through the response FIFO.

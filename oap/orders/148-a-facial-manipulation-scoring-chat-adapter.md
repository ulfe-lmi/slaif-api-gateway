# OAP Work Order — 148-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/148-facial-manipulation-scoring-adapter`
Base: `main @ 67561d7718af2eac0947b6f1ae31051df59356ca`
Title: `feat: add facial-manipulation-scoring Chat adapter`

## Objective and business reason

Implement the human-authorized facial-manipulation-scoring mini-adapter on the
merged native-module foundation. The gateway must accept one narrowly bounded
OpenAI-shaped Chat Completions image request, translate the image data URL to
the facial service's native multipart contract, and translate the native score
to an ordinary non-streaming Chat Completions response while retaining the
gateway's existing authentication, policy, quota, rate, concurrency, audit,
accounting, and revocation owners.

This is a post-MVP extension. It does not reopen the completed SME MVP, change
`ARCHITECTURE.md`, or claim general OpenAI compatibility for the native facial
service.

## Reconciled current state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Objective 147 is terminal: PR #282 merged at
  `2026-08-23T15:53:15Z` as `67561d7718af2eac0947b6f1ae31051df59356ca`.
- The merged module foundation provides `ModuleAdapter`, a reviewed static
  registry, `kind=module`, fixed-request Chat billing, zero-token reservation,
  and module streaming rejection. The facial registry is still empty and no
  facial adapter or downstream score call exists.
- The normal Chat path authenticates and applies request policy, resolves the
  route, enforces capabilities, reserves quota/rate/concurrency, calls the
  adapter, and lets PostgreSQL-owned accounting finalize or release the
  reservation. The adapter must remain inside that boundary.
- The current Chat request policy already bounds message/image counts and data
  URL size, but generic remote-image rejection is intentionally scoped to
  `openai_compatible`; this module must independently reject remote image
  references and malformed image data before native contact.
- Both candidate service addresses currently answer healthy:
  `http://maelstrom1.lmi.link:8000` and `http://10.8.132.72:8000`. Their
  `/openapi.json` documents are identical with SHA-256
  `8e77d16fb308d354bac8e84bfa7ba90c8cf77b8df644d59e391d7b68aa023832`.
  No authorized score request was made and no service credential is available
  to this objective.

## Verified native contract and operator endpoint decision

The service contract observed at activation is:

- `POST /v1/score`
- `multipart/form-data` required field: `image`
- credential header: `X-API-Key`
- success JSON: `ScoreResult` with `status` exactly `scored` or `unscorable`,
  nullable `score` bounded to `[0, 1]`, `score_type`, `higher_means`, nullable
  `reason`, and image/model/preprocessing metadata
- native errors use an `ErrorResponse` containing bounded `error.code` and
  `error.message`

The recommended operator-configured `base_url` is
`http://maelstrom1.lmi.link:8000`; `http://10.8.132.72:8000` is an equivalent
internal-network alternative if the gateway deployment cannot resolve the
hostname. Neither address may be hardcoded, committed as a provider row, or
used by tests. The adapter appends the native `/v1/score` path to the selected
operator base URL. A real score request remains out of scope.

Required operator values, supplied out of band and never committed:

```text
provider: facial_scoring
kind: module
base_url: operator-selected facial service origin
api_key_env_var: FACIAL_SCORING_API_KEY
public model/route: facial-manipulation-scoring
pricing: request_price=0, currency=EUR
max_retries: 0
```

The provider row, route, pricing row, credential, and endpoint activation are
operator setup only and are not created by this PR.

## Bounded implementation requirements

1. Add a statically registered `facial_scoring` module under
   `app/slaif_gateway/modules/facial_scoring/`, built on the existing
   `ModuleAdapter` contract. Registration must be source-controlled and
   explicit; unknown identifiers, arbitrary imports, user-supplied classes,
   and dynamic plugins must still fail closed.
2. Support only `POST /v1/chat/completions` through the public model
   `facial-manipulation-scoring`. Responses API routes and legacy
   `/v1/completions` remain unsupported and must fail closed before a facial
   service call. The adapter's inherited unsupported endpoint methods are not
   to be widened.
3. Extract exactly one `messages[*].content[*]` part of type `image_url`.
   Require a strict, non-empty base64 data URL using only `image/png`,
   `image/jpeg`, `image/webp`, or `image/gif`; use the gateway's existing
   bounded image/data-URL limits and independently validate base64 before
   decoding. A single image may be accompanied by ordinary text content, but
   text is not sent to the native service and is never logged or persisted.
4. Reject before native contact, with a safe client-facing error, malformed or
   oversized data URLs, invalid base64, empty payloads, remote `http`/`https`
   URLs, `file://` references, unsupported media types, zero or multiple
   images, text-only requests, audio/file/video content, tool calls, and
   unrelated message/content shapes. Preserve field-level safe parameters;
   never include the URL, decoded bytes, request body, or native body in the
   error.
5. Translate the decoded bytes to one multipart field named exactly `image`.
   Derive a safe fixed filename/media type from the validated media type; do
   not forward client filenames or other request fields. POST to the
   configured base URL plus `/v1/score` with `X-API-Key` loaded only from
   `FACIAL_SCORING_API_KEY` through the existing provider configuration
   mechanism. Never forward the client `Authorization` header or any gateway
   credential.
6. Use `max_retries=0` for this module. Use finite connect/read/write/total
   timeouts derived from the configured provider timeout, disable redirects,
   and map transport timeouts to the existing provider-timeout error. Do not
   add a retry loop, fallback endpoint, or live health/score probe.
7. Treat native 4xx/5xx, transport errors, timeout, empty/non-JSON responses,
   and malformed `ScoreResult` shapes as safe existing provider errors. Use
   the repository's bounded diagnostic/sanitization helpers where applicable;
   never log, store, or return raw native error or response bodies.
8. Validate native success responses without inventing labels or semantics.
   For `status=scored`, require a finite numeric score in `[0, 1]` and use the
   native `score_type` (defaulting only to its documented
   `uncalibrated_model_score` value). For `status=unscorable`, do not emit a
   score; include only a bounded, control-character-sanitized native `reason`
   when present. Do not claim probability, authenticity, calibration,
   certainty, moderation, or a threshold decision.
9. Return one ordinary non-streaming Chat Completions choice with public model
   `facial-manipulation-scoring`, zero prompt/completion/total token usage,
   and content in this form for scored results:
   `Score: 0.8234 (type: uncalibrated_model_score)`.
   An unscorable result must use a documented bounded explanatory form without
   inventing a score or type. The adapter must return the existing
   `ProviderResponse` envelope so normal gateway accounting remains the owner.
10. Preserve the merged fixed-request module billing behavior: exact `0 EUR`,
    one reserved request, zero reserved/final tokens, normal PostgreSQL ledger
    and quota finalization, rate/concurrency/revocation/expiry controls, and
    safe failure-release accounting. The adapter must not reserve, finalize,
    audit, or persist anything itself.
11. Configure/document the route capability boundary using existing route
    metadata: text plus image input enabled as needed for the single-image
    request; streaming, tools, audio, files, multiple choices, hosted tools,
    structured outputs, and non-default controls disabled. Streaming must be
    rejected before adapter invocation even if stale route metadata says true.

## Explicit non-goals

- No Responses API, legacy Completions API, streaming, tools, audio, files,
  batching, multiple choices, remote image fetching, or client-supplied native
  multipart.
- No image persistence, score indexing, content/reasoning storage, raw native
  response logging, or image bytes in fixtures/reports.
- No live score request, API key, production provider row, route activation,
  deployment change, endpoint health check in application code, or production
  database access.
- No model retraining, score calibration, label invention, threshold policy,
  moderation decision, human-review workflow, or claim of certification.
- No generic plugin loader, dynamic import, provider credential fallback, or
  change to `ARCHITECTURE.md`, release state, or unrelated provider behavior.

## Exact allowed paths

```text
app/slaif_gateway/modules/__init__.py
app/slaif_gateway/modules/facial_scoring/__init__.py
app/slaif_gateway/modules/facial_scoring/adapter.py
app/slaif_gateway/providers/factory.py
app/slaif_gateway/services/chat_completion_route_capabilities.py
docs/configuration.md
docs/compatibility-matrix.md
docs/openai-compatibility.md
docs/provider-forwarding-contract.md
tests/unit/test_facial_scoring_adapter.py
tests/unit/test_module_provider.py
tests/unit/test_provider_factory.py
tests/unit/test_chat_completion_route_capabilities.py
tests/unit/test_v1_chat_completions_forwarding.py
tests/integration/test_facial_scoring_adapter_postgres.py
oap/orders/148-a-facial-manipulation-scoring-chat-adapter.md
oap/reports/148-a-facial-manipulation-scoring-chat-adapter.md
oap/active
```

No other application, migration, configuration, fixture, or documentation path
may change. Existing tests may be amended only for the new reviewed module
registration/capability behavior named above.

## Acceptance criteria

- A mock HTTP service receives exactly one request for a valid single-image
  data URL, at `/v1/score`, with multipart field `image`, decoded bytes, the
  expected safe media type/filename, and exactly `X-API-Key`; no client
  `Authorization` header is present.
- The mock receives no request for remote URLs, `file://`, malformed/empty/
  oversized/unsupported data URLs, invalid base64, zero/multiple images,
  text-only, audio/file/video, tools, multiple choices, stream, Responses, or
  legacy Completions inputs.
- Scored native JSON maps to one public Chat choice with model
  `facial-manipulation-scoring`, four-decimal score formatting, native score
  type, and zero token usage. Unscorable native JSON never emits a score or
  invented label.
- Native 4xx/5xx, malformed JSON/schema, timeout, redirect, and transport
  failures map to safe existing gateway errors, release failed reservations,
  and retain no raw image/native body/credential evidence.
- Fixed pricing remains exact `0 EUR`; successful accounting is zero-token and
  zero-cost while one-request reservation, PostgreSQL accounting, rate,
  concurrency, policy, quota, audit, expiry, and revocation semantics remain
  intact. Tests prove blocked policy/quota/concurrency requests never reach the
  mock service.
- The diff contains no hardcoded candidate endpoint, API key, image bytes/data
  URL, raw native payload, or production row. Documentation distinguishes the
  implemented adapter from the unqualified/unactivated operator setup.

## Required verification

Run focused checks on the final implementation head:

```text
python -m pytest \
  tests/unit/test_facial_scoring_adapter.py \
  tests/unit/test_module_provider.py \
  tests/unit/test_provider_factory.py \
  tests/unit/test_chat_completion_route_capabilities.py \
  tests/unit/test_v1_chat_completions_forwarding.py -q
python -m pytest tests/integration/test_facial_scoring_adapter_postgres.py -q
python -m ruff check app/slaif_gateway/modules app/slaif_gateway/providers/factory.py \
  app/slaif_gateway/services/chat_completion_route_capabilities.py \
  tests/unit/test_facial_scoring_adapter.py tests/unit/test_module_provider.py \
  tests/unit/test_provider_factory.py tests/unit/test_chat_completion_route_capabilities.py \
  tests/unit/test_v1_chat_completions_forwarding.py \
  tests/integration/test_facial_scoring_adapter_postgres.py
python -m compileall -q app/slaif_gateway/modules
git diff --check
```

CI is required on the final PR head. Skipped, pending, missing, cancelled, or
environment-blocked checks are not passes. Inspect the final diff for raw
credential/content leakage, redirects, retries, URL hardcoding, provider
header forwarding, accounting bypass, and changes outside this order.

## Security, privacy, accounting, and operator evidence

- No credentials, images, data URLs, or raw native payloads may appear in
  source, tests, logs, fixtures, reports, OAP, or committed configuration.
- Mock HTTP evidence must use synthetic bytes and a non-secret test key. A
  live service health observation is not a score qualification and must not be
  repeated by application tests.
- The service endpoint and `FACIAL_SCORING_API_KEY` are operator inputs only.
  The recommended hostname and private-IP alternative are documented as
  configuration choices, not embedded defaults.
- The final report must state that no authorized live score call occurred and
  must publish only safe schema/behavior evidence.

## Report and publication contract

The coding agent must create exactly one new PR for 148-a, never merge or
enable auto-merge, and push implementation commits before publishing the final
report. The report publication commit must change only
`oap/reports/148-a-facial-manipulation-scoring-chat-adapter.md`, identify the
final PR head and exact changed paths, and include local/CI, security,
privacy, accounting, compatibility, and operator-boundary evidence. The
activated order and `oap/active` are immutable after activation.

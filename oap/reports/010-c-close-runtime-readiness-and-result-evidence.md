# OAP Coding-Agent Report — 010-c

## Work order

- Identifier: `010-c`
- Work-order file:
  `oap/orders/010-c-close-runtime-readiness-and-result-evidence.md`
- Work-order SHA-256:
  `500dc8ae8dec579ec2e679337d13c5c0ac3b48e76ee4041ecb804cc415654a9e`
- Numeric objective: `010`
- PR mode: `AMEND_EXISTING_PR`

## Status

IMPLEMENTED

## Executive summary

Objective 010-c closes the three narrow findings from strategic review without
changing the accepted 010-a/010-b support boundary or profile-v2 layout.

Positive qualification now calls the existing strict Responses runtime
capability parser for the exact ordinary and compact operations it claims
ready. The positive fixture includes `responses.text=true`; missing/false text,
unknown nested Responses flags, and non-boolean nested values fail closed for
both route types with the fixed
`responses_runtime_capabilities_invalid` reason. All prior pair, metadata,
gates, limits, provider, ranking, pricing, accounting, and FX checks remain.

Both direct pilot-key creation result paths now receive a deterministic
allowlisted Responses-policy summary. The browser plaintext-once result and the
direct send-now/enqueue result show only the five canonical capability names
and `function`/`custom` local tool types. Email results still suppress
plaintext, and ordinary/no-policy, template, and rotation paths omit the
section.

The standalone profile verifier now accepts no arguments and rejects every
extra argument with one fixed safe error that does not reflect operator text.
Its truthful invocation completed successfully with the same private,
ephemeral numeric-loopback boundary. Profile base-URL rendering also rejects
raw whitespace anywhere in the URL.

The claim remains only `protocol_qualified` for Codex 0.147.0 and bundled
`gpt-5.6-sol`; `real_provider_e2e=false`. No real provider, real gateway,
production system, hosted tool, MCP/connector, or external tool path was used.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- Remote `main` at activation and implementation:
  `250ee751cffb8cc7632aaa793385eaa498ed6d08`
- Starting objective-010 branch head / 010-b report commit:
  `c29f8633b132e53ee160e256d19967562b0d4b6e`
- Implementation head SHA:
  `bd77e0c4b774732c513562a6357b75fd93535c82`
- Implementation-head first parent:
  `c29f8633b132e53ee160e256d19967562b0d4b6e`
- Implementation-head commit message:
  `[OAP 010-c] Close Codex readiness evidence gaps`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Report commit first parent: same as Implementation head SHA
- PR number: `235`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/235`
- PR title: `[OAP 010] Manage Codex qualification and user profiles`
- PR state at report drafting: `OPEN`, non-draft, GitHub `MERGEABLE` / `CLEAN`
- Base branch: `main`
- Head branch: `oap/010-codex-model-catalog-profile-admin-capability`
- Objective-010 PR count: exactly one, PR #235
- Created a new PR this turn: NO
- Amended the existing objective PR this turn: YES
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Runtime-aligned qualification evidence

The qualification service reuses
`enforce_responses_route_capabilities()` rather than interpreting the complete
nested Responses map independently.

For the exact ordinary `/v1/responses` candidate, the runtime call requires:

- `responses.text=true`;
- stateless operation;
- streaming metadata and route streaming support;
- the request-envelope, client-tools, streaming-tool-events, encrypted-
  reasoning-replay, and compaction gates;
- strict `codex_limits` through the fully gated operation flags;
- strict known boolean nested Responses metadata, so unknown or non-boolean
  flags are rejected by the runtime parser.

For the exact `/v1/responses/compact` candidate, the runtime call requires:

- `responses.text=true`;
- `responses.compact=true`;
- the same five Codex gates and strict limits;
- the same strict known-boolean nested-map parsing.

The existing granular low-cardinality reasons remain, with one additional
fixed `responses_runtime_capabilities_invalid` reason. Runtime exception text,
raw metadata, model/provider text, URLs, and arbitrary values are never added
to the DTO. Direct drift coverage calls the runtime enforcement function with
the same positive ordinary and compact maps and exact operation flags; both
must pass before the pair can remain the positive fixture.

The following preexisting positive conditions remain unchanged:

- exact enabled reciprocal `/v1/responses` and `/v1/responses/compact` UUIDs;
- exact provider, requested model, upstream model, and match type;
- exact pinned 13-field `codex_qualification` declaration;
- route endpoint/visibility/streaming semantics;
- both rows winning ordinary provider-constrained runtime ranking;
- enabled provider;
- complete active per-endpoint pricing, Codex accounting metadata, and FX when
  required;
- strict route-local numeric limits.

## Creation-result summary and privacy evidence

The direct create workflow derives its result summary from the already
validated `parsed_input.responses_policy` after fresh pilot readiness and
before rendering. The helper returns a DTO only when both lists exactly match
the reviewed Codex preset, and returns only:

```text
allowed_capabilities:
- codex_request_envelope
- codex_client_tools
- codex_streaming_tool_events
- codex_encrypted_reasoning_replay
- codex_compaction

allowed_local_tool_types:
- function
- custom
```

The templates iterate those fixed tuples. They do not serialize raw JSON or
render version fields, arbitrary keys, arbitrary metadata, prompts, content,
route/pricing data, URLs, credentials, or secrets.

Focused route/template tests prove:

- a successful direct pilot validates readiness before `KeyService` mutation;
- the plaintext-once result shows the key exactly once and shows every fixed
  policy name;
- the direct send-now result shows the same policy names but contains no
  plaintext key;
- an ordinary direct plaintext result omits the Responses policy section;
- an ordinary direct email result omits the section and still contains no
  plaintext;
- both templates condition the allowlisted summary and contain no `tojson`
  serialization path;
- the preexisting stale-readiness and widened/unbounded input tests still prove
  rejection before mutation.

Template-created keys and rotations do not receive this direct pilot summary
context, so their existing behavior remains unchanged. GitHub's broad unit,
integration, E2E, and browser checks also passed.

## Honest verifier and URL evidence

The verifier interface is exactly:

```text
.venv/bin/python scripts/verify_codex_profile.py
```

`parse_verifier_arguments()` accepts only an empty argument sequence. Any
option or positional input raises the fixed safe `Verifier accepts no
arguments.` error without reflecting the supplied text, and the runtime does
not start. Unit tests cover a former `--base-url` shape, an unknown option, and
secret-looking operator text without invoking Codex.

The verifier itself continues to allocate its own ephemeral numeric-loopback
port. It does not accept an operator URL, fixed port, provider endpoint, or
gateway endpoint. The renderer's separate user-facing gateway base-URL
validation now rejects every raw Unicode whitespace character in addition to
the existing scheme, loopback, credentials, query, fragment, control,
canonical-path, percent, backslash, and secret-looking checks. Focused tests
cover a space in the hostname and path.

Pinned client:

```text
/usr/bin/codex --version: codex-cli 0.147.0
fixture SHA-256: 436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432
```

Final exact command:

```text
.venv/bin/python scripts/verify_codex_profile.py
```

Safe output:

```text
RESULT=OK
CLI_VERSION=0.147.0
CLI_VERSION_MATCHED=true
PROFILE_V2_APPLIED=true
MODEL_MATCHED=true
PROVIDER_MATCHED=true
BUNDLED_CATALOG_USED=true
V1_COMPACTION_SELECTED=true
REQUEST_COUNT=1
CONTENT_ENCODING_ABSENT=true
LOOPBACK_ONLY=true
RAW_PAYLOADS_PERSISTED=false
```

Elapsed wall time was 1.23 seconds. The single final run used the unchanged
private temporary `CODEX_HOME`, two credential-free profile-v2 files, child-
only fixed dummy key, dead external proxies, numeric-loopback exception, and
bounded in-memory validation. No raw request, response, prompt, completion,
tool content, subprocess output, or dummy value was printed or persisted.

## Changes and exact paths

The implementation commit changes only these 16 order-allowed paths:

```text
AGENTS.md
app/slaif_gateway/api/admin.py
app/slaif_gateway/services/codex_qualification.py
app/slaif_gateway/web/templates/keys/create_result.html
app/slaif_gateway/web/templates/keys/email_delivery_result.html
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/configuration.md
docs/database-schema.md
docs/security-model.md
oap/active
oap/orders/010-c-close-runtime-readiness-and-result-evidence.md
scripts/verify_codex_profile.py
tests/unit/test_admin_key_create_routes.py
tests/unit/test_admin_key_create_templates.py
tests/unit/test_codex_qualification.py
```

`oap/active` is exactly `010-c`; the matching order is unique. Every earlier
order/report remains unchanged. The final report-publication commit adds only
`oap/reports/010-c-close-runtime-readiness-and-result-evidence.md`.

## Local verification

- `.venv/bin/python -m pytest -q tests/unit/test_codex_qualification.py tests/unit/test_admin_key_create_routes.py tests/unit/test_admin_key_create_templates.py`:
  PASSED — 94 tests in the final run, 15.38 seconds; zero
  failures/errors/skips.
- `.venv/bin/python -m pytest -q tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py`:
  PASSED — 17 tests in 2.68 seconds before report drafting and 4.21 seconds
  after staging the report; zero failures/errors/skips.
- `.venv/bin/ruff check app/slaif_gateway/services/codex_qualification.py app/slaif_gateway/api/admin.py scripts/verify_codex_profile.py tests/unit/test_codex_qualification.py tests/unit/test_admin_key_create_routes.py tests/unit/test_admin_key_create_templates.py`:
  PASSED.
- `.venv/bin/python -m compileall -q app/slaif_gateway/services/codex_qualification.py app/slaif_gateway/api/admin.py scripts/verify_codex_profile.py tests/unit/test_codex_qualification.py tests/unit/test_admin_key_create_routes.py tests/unit/test_admin_key_create_templates.py`:
  PASSED.
- Final truthful no-argument manual verifier: PASSED as recorded above.
- Fixture SHA-256: PASSED —
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.
- Exact branch, active pointer, unique order, prior-report immutability, allowed
  paths, local/remote implementation head, and commit parentage: PASSED.
- Product `git diff --check`: PASSED. Staged checking reported only the
  unchanged strategic 010-c order's second blank line at EOF. Its exact digest
  is recorded above; the coding agent preserved those strategic bytes. All
  product/report paths passed independent whitespace checks.
- Full local unit suite: NOT RUN — prohibited by focused test economy; GitHub
  CI owns broad routine coverage.
- Local PostgreSQL/integration suites: NOT RUN — prohibited; no schema,
  migration, or local database write was required.
- Local E2E and Playwright/browser matrix: NOT RUN — prohibited by the active
  order.
- Local Docker/Compose and HPC suites: NOT RUN — prohibited by the active
  order.
- Real provider/gateway/hosted-tool smoke: NOT RUN — prohibited; objective 011
  owns the real provider-through-gateway boundary.

## GitHub CI / checks

All ten checks completed successfully for implementation head
`bd77e0c4b774732c513562a6357b75fd93535c82`, observed after exact 30-second
wait blocks:

- `Analyze (javascript-typescript)`: SUCCESS — 43s.
- `Analyze (python)`: SUCCESS — 1m43s.
- `Analyze Python`: SUCCESS — 1m12s.
- `CodeQL`: SUCCESS — 3s.
- `Docker Compose smoke`: SUCCESS — 49s.
- `Documentation hygiene`: SUCCESS — 4s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m21s.
- `Playwright browser smoke`: SUCCESS — 1m20s.
- `PostgreSQL integration tests`: SUCCESS — 2m10s.
- `Unit, lint, and migration head`: SUCCESS — 2m00s.
- In-scope CI repair required: NO.
- All implementation-head checks green at report drafting: YES.
- Fresh report-head checks may run after SELF publication; the response FIFO
  remains withheld until the remote report head and its checks are verified.

## Documentation impact

Updated only affected passages in `AGENTS.md`,
`docs/codex-compatibility.md`, `docs/compatibility-matrix.md`,
`docs/configuration.md`, `docs/database-schema.md`, and
`docs/security-model.md`. They now state the runtime-parser/text baseline,
strict nested Responses map, safe direct-result summary, plaintext suppression,
no-argument verifier, and URL-whitespace boundary. They preserve the exact
two-file profile-v2 layout and do not claim real provider E2E, pilot completion,
full compatibility, or production certification.

## Local setup / dependencies

- Packages/tools/services installed or configured: NONE.
- `sudo`-level setup performed: NONE.
- Durable local setup changes: NONE.
- Existing repository `.venv` and pinned `/usr/bin/codex` were used.
- No user/repository Codex configuration was modified.

## Safety, privacy, and scope confirmations

- Unrelated files changed: NO.
- Earlier order/report bytes changed: NO.
- Production secrets accessed: NO.
- Production systems accessed: NO.
- Real provider/gateway or side-effecting external tool called: NO.
- Gateway/admin key actually created or mutated during verification: NO.
- User `~/.codex` or repository `.codex` modified: NO.
- Replacement/partial model catalog created: NO.
- Raw request, response, prompt, completion, body, tool payload, API key,
  provider key, gateway key, or arbitrary policy/pricing metadata printed,
  persisted, or committed: NO.
- Existing accounting, HMAC, schema, migrations, and content-storage boundaries
  changed: NO.
- Required focused tests skipped: NO.
- Every broad/local or real-provider suite not run is listed explicitly above.
- Scope deviation or contract weakening: NO.
- Extra objective-010 PR created: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- `.local-provider-catalog/` accessed, modified, staged, or committed: NO.
- Report-publication commit changes only this report: YES, verified before the
  FIFO response.

## Final safety statement

This turn amended only PR #235, preserved the immutable 010-a/010-b history,
kept the claim at local `protocol_qualified` with
`real_provider_e2e=false`, and performed no merge or auto-merge action.
Coding-agent `OK` after remote SELF and report-head verification means only
that this execution turn, immutable report, and claimed GitHub state are
published; it does not mean the work is accepted.

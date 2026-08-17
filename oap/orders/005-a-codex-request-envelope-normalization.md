# OAP Work Order — 005-a

## Objective

Implement the first runtime Codex slice: safely accept, bound, privacy-filter,
account for, and canonically reconstruct the non-tool request-envelope elements
observed in the pinned Codex CLI 0.147.0 fixture, behind explicit per-key and
per-route gates.

Do not enable Codex client tools/namespaces, tool-dependent `tool_choice`, new
stream events, or full Codex compatibility.

## GitHub state

- Numeric objective: `005`; round: `005-a`; PR mode: `CREATE_NEW_PR`.
- Repository: `ulfe-lmi/slaif-api-gateway`; base: `main`.
- Starting `main`: `f2cc5dbed94d9a0a84f5cbb3f1343e57f4f9877e`.
- Objective 004/PR #229 is merged.
- Required branch: `oap/005-codex-request-envelope-normalization`.
- Required title: `[OAP 005] Normalize gated Codex request envelopes`.
- Expected unrelated open PR: Dependabot #224 only.

Create exactly one PR. Continuations amend it.

## Captured authority and scope boundary

The immutable 004 fixture is
`tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`, SHA-256
`436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.

This PR handles only:

- `client_metadata`;
- exact `include` support;
- `parallel_tool_calls`;
- `prompt_cache_key`;
- `reasoning.context`/`reasoning.effort`;
- `text.verbosity`;
- message item `id`.

The pinned source uses `include=["reasoning.encrypted_content"]`,
Responses-lite `parallel_tool_calls=false`, `reasoning.context="all_turns"`,
opaque cache/client identifiers, `store=false`, and `stream=true`.

`additional_tools`, namespaces/nested client tools, and tool-dependent
`tool_choice` remain rejected for 006. Tool/reasoning/output-item stream events
remain rejected for 007–008. Do not identify Codex by spoofable headers.

## Immutable baseline requirement

The 004 fixture contains the pre-005 compatibility baseline and is fully digest
pinned. It must remain byte-identical. `scripts/capture_codex_protocol.py`
currently imports evolving runtime constants to reproduce that diff; freeze its
classifier to clearly named 004-baseline constants/logic copied from pre-005
main. Live verify must still match the old fixture after runtime policy changes.
Post-005 current behavior belongs to new runtime tests/docs.

## Governing instructions and start

Read full `AGENTS.md`, OAP protocol, Codex/Responses/accounting/forwarding/
security/template contracts, pinned fixture/source, request policy/gateway,
route capability, normalized payload, and focused tests.

Verify GitHub/main, PR #229 merge, no objective-005 PR, clean worktree, and
unchanged fixture digest. The strategic model atomically published this order
and `oap/active=005-a`; they must be the only dirty paths and must be committed
unchanged. Create the branch from current `origin/main`. Preserve all unrelated
local state.

## Allowed paths

Implementation commits may change only:

```text
AGENTS.md
app/slaif_gateway/services/key_template_service.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/services/responses_route_capabilities.py
app/slaif_gateway/services/upstream_payloads.py
app/slaif_gateway/services/upstream_request_contracts.py
docs/accounting.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
oap/active
oap/orders/005-a-codex-request-envelope-normalization.md
scripts/capture_codex_protocol.py
tests/unit/test_codex_protocol_capture.py
tests/unit/test_key_template_service.py
tests/unit/test_responses_codex_envelope.py
tests/unit/test_responses_request_policy.py
tests/unit/test_responses_route_capabilities.py
tests/unit/test_upstream_payload_reconstruction.py
```

Final report-only commit may add only
`oap/reports/005-a-codex-request-envelope-normalization.md`.

Do not edit the fixture, API schema, database/migrations, settings,
dependencies/lock, provider adapters, CI, deployment, pricing/catalog, README,
prior OAP history, or unrelated paths.

## Dual capability gate

Add one shared capability: `codex_request_envelope`.

- Key: sanitized `responses_policy.allowed_capabilities` must explicitly
  contain it. Ordinary endpoint/model permission, missing/malformed policy, and
  existing keys default deny.
- Template vocabulary may carry it only when explicitly supplied; never add it
  to defaults/calibration-derived templates.
- Route: add it to known Responses capabilities, default `false`; require
  `capabilities.responses.codex_request_envelope=true`.
- Detect the envelope from new body fields, `text.verbosity`, or message `id`,
  never headers/model alone.
- Key/shape denial occurs before route/DB work. Route denial occurs before
  Redis, pricing, quota reservation, or provider forwarding.

Add a default-false policy argument such as
`allow_codex_request_envelope`. Non-Codex policy entrypoints remain unchanged.
Use a stable safe key-denial code such as
`responses_codex_envelope_not_allowed`.

## Field policy

### `include`

Require the exact bounded singleton `reasoning.encrypted_content` (or
deterministically canonicalize duplicates to it). Reject all other types,
values, and counts. Forward the canonical list. This does not enable new stream
events.

### `parallel_tool_calls`

Require/forward boolean. It never bypasses tool validation or enables tools.

### `reasoning`

Require an object containing only `effort` and optional `context`, with at least
one member and a bounded canonical size. Effort allowlist: `none`, `minimal`,
`low`, `medium`, `high`, `xhigh`, `max`, `ultra`. Context is omitted or exact
`all_turns`. Reconstruct/forward; never store/log values or encrypted content.

### `prompt_cache_key`

Require a non-empty opaque UTF-8 string, conservatively capped at no more than
256 bytes. Forward exactly; never parse, persist, hash for identity, log, audit,
export, meter as identity, or echo.

### `text.verbosity`

Compose with existing `text.format`; accept `low|medium|high` only under the
dual gate. Unknown text members remain denied. Reconstruct/forward.

### message `id`

Permit only on supported message items under the dual gate. Require non-empty
conservative ASCII identifier syntax, max 128 characters, no whitespace,
control, URL, or secret-like value. Reconstruct/forward. Never store/log/audit/
export/echo; it grants no state/storage authority.

### `client_metadata`

Require a small object with conservative key-count and total/key/value caps.
Accept only pinned Codex installation/session/thread/window/turn metadata key
vocabulary from the tagged source. Values must be strings. Do not parse embedded
turn-metadata JSON because it may contain workspace URLs/tool mappings. After
validation, **drop the entire field**: never forward, persist, log, audit,
meter, hash, export, or echo it. Presence still triggers both gates.

### Accounting

Conservatively count provider-forwarded envelope and message-ID bytes in input
estimation and expose safe field names/counts only through existing estimation
evidence. Dropped client metadata is size-capped but is not provider-billed
input. Preserve hard output caps, quota reservation/finalization, live-burn,
and provider final usage truth.

### Remain rejected

Even with both gates: `additional_tools`, namespace/nested Codex tools,
tool-dependent `tool_choice`, unknown envelope/metadata fields, background,
arbitrary include, hosted/MCP authority, storage expansion, and new SSE events.

## Canonical upstream reconstruction

Add these policy-approved fields to the normalized Responses dataclass,
normalized allowlist, and canonical builder:

```text
include
parallel_tool_calls
prompt_cache_key
reasoning
```

`text` carries only approved `format`/`verbosity`; message `id` remains only in
canonical validated input. `client_metadata` must not exist in the normalized
contract. Never forward raw body/denylist output. Preserve model substitution
and deep-copy isolation.

## Required tests

Create `tests/unit/test_responses_codex_envelope.py` and extend only needed
focused existing tests. Cover:

1. ordinary Responses unchanged/default deny;
2. key-only, route-only, missing/malformed gates deny;
3. both gates allow a synthetic tool-free pinned-envelope projection;
4. exact reconstructed provider body/model substitution and omitted
   `client_metadata`/raw unknowns;
5. exhaustive field positive/invalid type/value/key/size/control cases;
6. tools/namespaces/additional_tools/tool-dependent choice still reject;
7. key/unknown denial before route/Redis/pricing/quota/provider and route denial
   before Redis/pricing/quota/provider;
8. conservative estimation increases with envelope/IDs but records no values;
9. logs/errors/metrics/audit/ledger-safe metadata contain none of the privacy
   canaries;
10. explicit template capability propagation, no default, hosted/storage still
    denied;
11. route default false, explicit true works, unknown flags fail;
12. normalized builders deep-copy/reject unapproved fields;
13. full captured profile remains not compatible only because separate tool/
    namespace/tool-choice/stream gaps remain;
14. immutable 004 classifier/SHA/live verify remain exact after freezing its
    baseline constants.

Use synthetic canaries and mocked providers only. No real upstream.

## Documentation

Update `AGENTS.md` and Codex, Responses, provider-forwarding, accounting,
security, and compatibility-matrix contracts with exact dual-gate, field
forward/drop, privacy, estimation, baseline-vs-current, and remaining-gap
semantics. Status is partial envelope support, **not Codex-compatible**. Do not
update README before a tool loop works.

## Non-goals

- No tools/namespaces (006), stream/reasoning/tool events (007–008), full Codex
  E2E, hosted/MCP/background/WebSocket, or compatibility claim.
- No client metadata forwarding/storage/logging.
- No schema/migration/settings/dependency/CI/admin UI/fixture change.
- No real provider/production/staging/catalog action.
- No full local suite, integration, E2E, browser, Docker, or HPC.
- No second PR, merge, or auto-merge by coding agent.

## Human test economy and focused verification

Run only:

```bash
.venv/bin/python scripts/capture_codex_protocol.py verify-live --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline --fixture tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
.venv/bin/python -m pytest tests/unit/test_responses_codex_envelope.py -q
.venv/bin/python -m pytest tests/unit/test_responses_request_policy.py -q
.venv/bin/python -m pytest tests/unit/test_responses_route_capabilities.py -q
.venv/bin/python -m pytest tests/unit/test_upstream_payload_reconstruction.py -q
.venv/bin/python -m pytest tests/unit/test_key_template_service.py -q
.venv/bin/python -m pytest tests/unit/test_codex_protocol_capture.py -q
.venv/bin/python -m pytest tests/unit/test_documentation_contract_drift.py -q
.venv/bin/python -m pytest tests/unit/test_oap_governance.py -q
.venv/bin/ruff check app/slaif_gateway/services/responses_request_policy.py app/slaif_gateway/services/responses_route_capabilities.py app/slaif_gateway/services/responses_gateway.py app/slaif_gateway/services/upstream_request_contracts.py app/slaif_gateway/services/upstream_payloads.py app/slaif_gateway/services/key_template_service.py scripts/capture_codex_protocol.py tests/unit/test_responses_codex_envelope.py tests/unit/test_responses_request_policy.py tests/unit/test_responses_route_capabilities.py tests/unit/test_upstream_payload_reconstruction.py tests/unit/test_key_template_service.py tests/unit/test_codex_protocol_capture.py
git diff --check
sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
git status --short
```

No broad local suite. Rerun only an affected focused command. GitHub CI supplies
broad evidence.

## Acceptance criteria

1. Tool-free pinned envelope projection passes only with both gates.
2. Approved fields are bounded/reconstructed; client metadata is dropped.
3. Unknown/authority/tool gaps fail before required side effects.
4. Privacy canaries never enter provider/log/error/persisted/metric surfaces.
5. Accounting estimates forwarded envelope/ID material without values.
6. Immutable fixture/SHA/live verify remain exact through a frozen baseline.
7. Full profile remains honestly not compatible pending 006–008.
8. Focused checks and all final GitHub checks pass; no broad suite/provider call.
9. One PR/allowed paths only; coding agent never merges.
10. Final report-only commit satisfies OAP parent/path rules.

## GitHub/report requirements

Commit unchanged order/pointer with implementation, push required branch, and
create one non-draft PR with exact title. PR body explains gates, forward/drop,
immutable baseline separation, remaining blockers, tests, and no compatibility
claim. Inspect real standard checks; pending/missing/failed is not green.

Publish one immutable report at
`oap/reports/005-a-codex-request-envelope-normalization.md` with literal
implementation SHA, `Report publication commit: SELF`, exact behavior/tests/
ordering/privacy/fixture evidence, broad suites not run, docs impact, and no
merge. Final commit must have implementation head as first parent and only the
report path; push/verify/signal exact `OK`.

If immutable evidence, tool denial, privacy, or ordering cannot be preserved,
report a blocker rather than broaden. Do not merge under any circumstance.

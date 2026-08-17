# OAP Coding-Agent Report — 005-a

## Work order

- Identifier: 005-a
- Work-order file: `oap/orders/005-a-codex-request-envelope-normalization.md`
- Numeric objective: 005
- PR mode: CREATED_NEW_PR

## Status

COMPLETE

## Executive summary

Implemented the first bounded runtime Codex slice for the non-tool Responses
request envelope. The gateway now accepts only the approved pinned envelope
shape when both the authenticated key and resolved route explicitly grant the
shared default-off `codex_request_envelope` capability. It validates,
canonicalizes, reconstructs, and conservatively estimates approved forwarded
fields while validating and dropping all `client_metadata` before normalized
provider construction.

This remains partial request-envelope support, not Codex compatibility.
Responses-lite `additional_tools`, namespace/nested client tools,
tool-dependent `tool_choice`, and new reasoning/tool/output-item stream events
remain fail-closed for objectives 006 through 008.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 230
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/230
- PR state at report time: OPEN, ready for review, not draft
- Base branch: `main`
- Head branch: `oap/005-codex-request-envelope-normalization`
- Starting remote SHA: `f2cc5dbed94d9a0a84f5cbb3f1343e57f4f9877e`
- Implementation head SHA: `8d0152977bbd3a6d7457c8ce44449ab0655738b6`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `8d0152977bbd3a6d7457c8ce44449ab0655738b6` (`Normalize gated Codex request envelopes`)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Auto-merge enabled: NO
- Merge performed: NO

## Changes made

- Added shared Responses capability `codex_request_envelope`, known to route
  parsing and defaulting to `false`.
- Required an explicit, well-formed
  `responses_policy.allowed_capabilities` key grant before policy admission and
  an independent explicit route grant before Redis, pricing, quota, or
  provider work.
- Detected the envelope from body fields, `text.verbosity`, or supported
  message-item `id`, never from headers or model names.
- Bounded and canonically reconstructed exact
  `include=["reasoning.encrypted_content"]`, boolean `parallel_tool_calls`,
  opaque UTF-8 `prompt_cache_key` up to 256 bytes, required allowlisted
  `reasoning.effort` with optional exact `context="all_turns"`, composed
  `text.verbosity`, and conservative ASCII message IDs up to 128 characters.
- Accepted only the pinned Codex installation/session/thread/window/turn
  client-metadata vocabulary with key/value/count/total caps, did not parse
  embedded turn metadata, and dropped the complete field after validation.
- Added approved envelope fields to normalized Responses reconstruction with
  deep-copy isolation; `client_metadata` is absent from the normalized contract.
- Counted forwarded envelope and message-ID material conservatively in input
  estimation while exposing only safe field names and aggregate byte/token
  counts. Dropped client metadata is not counted as provider input.
- Preserved all existing hard output, quota, live-burn, provider-final-usage,
  storage, tool, hosted-authority, and streaming-event boundaries.
- Froze the objective-004 capture classifier to copied, clearly named baseline
  constants so runtime evolution cannot rewrite the immutable capture result.
- Allowed explicit key-template propagation of the new capability without
  adding it to template or calibration-derived defaults.

## Files changed

- `AGENTS.md`
- `app/slaif_gateway/services/key_template_service.py`
- `app/slaif_gateway/services/responses_gateway.py`
- `app/slaif_gateway/services/responses_request_policy.py`
- `app/slaif_gateway/services/responses_route_capabilities.py`
- `app/slaif_gateway/services/upstream_payloads.py`
- `app/slaif_gateway/services/upstream_request_contracts.py`
- `docs/accounting.md`
- `docs/codex-compatibility.md`
- `docs/compatibility-matrix.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`
- `oap/active`
- `oap/orders/005-a-codex-request-envelope-normalization.md`
- `scripts/capture_codex_protocol.py`
- `tests/unit/test_key_template_service.py`
- `tests/unit/test_responses_codex_envelope.py`
- `tests/unit/test_responses_request_policy.py`
- `tests/unit/test_upstream_payload_reconstruction.py`

## Acceptance-criteria evidence

### Criterion 1 — dual-gated tool-free projection

- Result: PASSED
- Evidence: focused runtime tests prove every envelope signal defaults to key
  denial, malformed/missing policies never grant access, the route defaults
  false, route-only/key-only configurations deny, and both explicit gates allow
  the synthetic pinned tool-free projection.

### Criterion 2 — bounded canonical forwarding and metadata drop

- Result: PASSED
- Evidence: exhaustive type/value/enum/control/size tests cover each field;
  normalized reconstruction substitutes the resolved model, canonicalizes
  duplicates, deep-copies nested values, rejects unapproved raw fields, and
  contains no `client_metadata` member.

### Criterion 3 — denial ordering and authority preservation

- Result: PASSED
- Evidence: key/shape failures occur before route or database work; route
  denial occurs before Redis, pricing, quota reservation, and provider calls.
  Tools, namespaces, additional tools, tool-dependent choice, background,
  hosted/MCP authority, and storage expansion remain denied.

### Criterion 4 — privacy surfaces

- Result: PASSED
- Evidence: synthetic client-metadata, cache-key, and message-ID canaries prove
  local validation errors do not echo values; client metadata never reaches the
  provider; and logs, returned responses, safe estimation evidence, finalized
  ledger results, and metric inputs contain none of the canaries. Accounting
  finalization discards the transient policy object rather than persisting it.

### Criterion 5 — conservative accounting

- Result: PASSED
- Evidence: approved forwarded envelope and message IDs increase the input
  estimate; evidence contains only aggregate bytes/tokens and approved field
  names. Client metadata is capped and dropped without provider-input billing.

### Criterion 6 — immutable capture baseline

- Result: PASSED
- Evidence: fixture SHA-256 remains
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`;
  the classifier no longer imports evolving runtime constants; live verification
  returned `VERIFY_LIVE_OK status=not_compatible`.

### Criterion 7 — honest remaining gaps

- Result: PASSED
- Evidence: focused tests and documentation keep the full captured profile
  `not_compatible` because separate tool/namespace/tool-choice and stream-event
  gaps remain. No README or compatibility claim was added.

### Criterion 8 — focused and remote verification

- Result: PASSED
- Evidence: every mandated focused local command passed, no prohibited broad
  local suite was run, and all ten observed GitHub checks succeeded for the
  literal implementation head.

### Criterion 9 — one PR and allowed paths only

- Result: PASSED
- Evidence: exactly one objective-005 PR exists, PR #230; the implementation
  commit contains only the work order's allowed paths; no merge or auto-merge
  action occurred.

### Criterion 10 — OAP publication shape

- Result: PASSED
- Evidence: this immutable report records the literal implementation head and
  `SELF`; its publication commit is constrained to this report path with the
  implementation head as first parent.

## Local verification

- `.venv/bin/python scripts/capture_codex_protocol.py verify-live --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline --fixture tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED — `VERIFY_LIVE_OK status=not_compatible`.
- `.venv/bin/python -m pytest tests/unit/test_responses_codex_envelope.py -q`: PASSED; rerun after the final reasoning/privacy tightening also passed.
- `.venv/bin/python -m pytest tests/unit/test_responses_request_policy.py -q`: PASSED; rerun after the final reasoning requirement also passed.
- `.venv/bin/python -m pytest tests/unit/test_responses_route_capabilities.py -q`: PASSED.
- `.venv/bin/python -m pytest tests/unit/test_upstream_payload_reconstruction.py -q`: PASSED.
- `.venv/bin/python -m pytest tests/unit/test_key_template_service.py -q`: PASSED.
- `.venv/bin/python -m pytest tests/unit/test_codex_protocol_capture.py -q`: PASSED.
- `.venv/bin/python -m pytest tests/unit/test_documentation_contract_drift.py -q`: PASSED.
- `.venv/bin/python -m pytest tests/unit/test_oap_governance.py -q`: PASSED.
- Exact work-order-scoped `.venv/bin/ruff check ...` command: PASSED on the final implementation.
- `git diff --check`: PASSED before commit.
- `sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED — exact required digest.
- `git status --short`: PASSED — only the intended allowlisted paths were present before the implementation commit; clean after commit.
- Broad local suite, integration, E2E, browser, Docker, and HPC: NOT RUN — explicitly prohibited by the work order; GitHub CI supplied the broad evidence.
- Real upstream/provider smoke: NOT RUN — prohibited; tests used synthetic canaries and mocked providers only.

## GitHub CI / required checks

- Check state observed for implementation head: all observed checks completed successfully; PR merge state `CLEAN`.
- `Analyze (javascript-typescript)`: SUCCESS.
- `Analyze (python)`: SUCCESS.
- `Analyze Python`: SUCCESS.
- `CodeQL`: SUCCESS.
- `Unit, lint, and migration head`: SUCCESS.
- `PostgreSQL integration tests`: SUCCESS.
- `OpenAI-compatible E2E tests`: SUCCESS.
- `Playwright browser smoke`: SUCCESS.
- `Docker Compose smoke`: SUCCESS.
- `Documentation hygiene`: SUCCESS.
- All required checks green for the implementation head at report drafting: yes.
- Report-only commit may trigger fresh checks: strategic model must verify the `SELF` commit without rewriting this report.

## Local setup / dependencies

- Packages/tools/services installed or configured: none.
- Temporary evidence setup: a read-only clone of OpenAI Codex tag
  `rust-v0.147.0` was inspected under `/tmp` for the pinned client-metadata
  vocabulary; it is outside the repository and not committed.
- `sudo`-level setup performed: none.
- Durable setup changes committed/documented: none.

## Documentation

Updated the durable implementation constitution and Codex, Responses,
provider-forwarding, accounting, security, and compatibility-matrix contracts.
They document exact dual gates, approved forwarded/dropped fields, privacy and
estimation rules, immutable-baseline versus current-runtime semantics, and the
remaining objectives 006–008 gaps. Status is explicitly partial envelope
support and not Codex-compatible. README was not changed.

## Safety and scope confirmations

- Unrelated files changed: no.
- `.local-provider-catalog/` modified, staged, or committed: no.
- Production secrets accessed: no project/provider secrets; authenticated `gh`
  was used for the authorized GitHub publication and its token remained masked.
- Production systems accessed: no application production/staging/catalog
  systems; only the authorized canonical GitHub repository was updated.
- Required tests skipped/not run: no required focused command was skipped;
  broader local suites were intentionally not run under the order's test economy.
- Scope deviation: no.
- Extra PR created for same numeric objective: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order and `oap/active` edited by coding agent: NO; both strategic
  inputs were committed unchanged.
- Report-publication commit changes only this report file: yes.

## Known limitations / blockers

- No blocker for this execution turn.
- The full pinned Codex profile remains intentionally incompatible until
  separate objectives implement and approve Responses-lite additional tools,
  namespaces/nested tool shapes, tool-dependent choice, and the required
  reasoning/tool/output-item stream events.
- The report-containing `SELF` commit may start fresh CI; its state is not
  predicted or represented as the already-observed implementation-head result.

## Recommended strategic follow-up

Independently verify this immutable report commit, its first parent and
report-only path, inspect PR #230 and any checks triggered by `SELF`, then make
the acceptance/continuation decision. The coding agent must not merge.

# OAP Coding-Agent Report — 007-a

## Work order

- Identifier: 007-a
- Work-order file: `oap/orders/007-a-codex-streaming-tool-event-roundtrip.md`
- Numeric objective: 007
- PR mode: CREATED_NEW_PR

## Status

BLOCKED

## Executive summary

Implemented the bounded Codex CLI 0.147.0 streaming client-tool round trip on
PR #232. The implementation adds the third default-deny key/route capability,
strict request-scoped typed-SSE validation, exact declared call/output replay,
expanded provisional live-burn counting, and a side-effect-free two-request
loopback verifier. The isolated verifier completed with two requests, an exact
immutable first request, one client-executed `functions.exec` custom-tool
round trip, a matched safe result, and a final assistant sequence.

The turn is blocked by the activated strategic order itself. Initial-round OAP
governance requires the literal **PR mode:** `CREATE_NEW_PR` declaration in an `NNN-a` order,
but the immutable 007-a order contains only `Objective/round 007-a;
CREATE_NEW_PR`. The coding-agent protocol prohibits modifying activated orders
and requires their exact bytes to be committed unchanged. The required local
governance test and GitHub unit job therefore fail. No merge or auto-merge was
performed.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 232
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/232
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/007-codex-streaming-tool-event-roundtrip`
- Starting remote SHA: `e93fe2ff753392f26c84d468e6b9d18e8afc7365`
- Implementation head SHA: `01e794a0ae21ed36bfbd37660c9015c760f51e9d`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `01e794a0ae21ed36bfbd37660c9015c760f51e9d`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made

- Added `codex_streaming_tool_events` as a known Responses route capability and
  explicit key-template capability. It defaults false, is never calibration
  enabled, requires both prior Codex capabilities in a template, and requires
  all three capabilities independently on the key and route at runtime.
- Enforced the third key denial before route/database work and the third route
  denial before Redis, pricing, quota reservation, or provider work.
- Added a request-scoped Responses stream validator for bounded
  created/in-progress, output-item added/done, function-argument delta,
  custom-input delta, reasoning summary-part/text, reasoning-text, output-text,
  and completed events. It validates exact request declarations, event order,
  item/call IDs, indexes, cumulative values, caps, and linkage frame by frame.
- Converted unknown, malformed, mismatched, hosted-authority, duplicate/orphan,
  provider failure/incomplete, and error events to a safe gateway failure. The
  successful completed event remains held until accounting finalization.
- Added stateless deep-copied replay for exact declared function calls and the
  pinned `functions.exec` custom call with exactly linked outputs. The pinned
  Code Mode custom output supports its bounded exact `input_text` part list;
  other arrays and authority remain denied.
- Expanded Responses provisional live-burn counting to output text, function
  arguments, custom input, reasoning summary text, and reasoning text. Matching
  done values do not double count deltas, and the threshold-crossing event is
  withheld. Provider final usage remains authoritative; missing usage,
  provider failure, or disconnect after counted output finalizes as estimated
  interrupted accounting.
- Added the manual-only `scripts/verify_codex_tool_roundtrip.py` verifier and
  focused unit coverage for gate matrices, event validation, replay, failure,
  live-burn, accounting ordering, privacy, and harness purity.

## Files changed

- `AGENTS.md`
- `app/slaif_gateway/providers/streaming.py`
- `app/slaif_gateway/services/key_template_service.py`
- `app/slaif_gateway/services/responses_gateway.py`
- `app/slaif_gateway/services/responses_request_policy.py`
- `app/slaif_gateway/services/responses_route_capabilities.py`
- `app/slaif_gateway/services/responses_streaming_live_burn.py`
- `docs/accounting.md`
- `docs/codex-compatibility.md`
- `docs/compatibility-matrix.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`
- `oap/active`
- `oap/orders/007-a-codex-streaming-tool-event-roundtrip.md`
- `scripts/verify_codex_tool_roundtrip.py`
- `tests/unit/test_key_template_service.py`
- `tests/unit/test_responses_codex_client_tools.py`
- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/unit/test_responses_route_capabilities.py`
- `tests/unit/test_responses_streaming_live_burn.py`

## Acceptance-criteria evidence

### Three independent gates and request ordering

- Result: PASSED for implementation; objective acceptance blocked by the order
  governance defect.
- Evidence: focused key/route matrix tests cover every key and route combination,
  third-key denial before route/database work, third-route denial before later
  services, conservative defaults, and explicit template propagation.

### Event allowlist, validation, failure, and completion ordering

- Result: PASSED.
- Evidence: the focused stream tests exercise all approved event families,
  exact function/custom/reasoning/message shapes, incremental cumulative
  linkage, unknown/malformed/oversized/duplicate/orphan/mismatched denial, safe
  provider failure conversion, frame-before-forward ordering, and completed
  event hold until final accounting.

### Replay and client execution ownership

- Result: PASSED.
- Evidence: exact declared function and `functions.exec` calls replay only with
  one matching output. Tests reject undeclared names, wrong namespaces/types,
  duplicates, orphans, mismatched IDs, authority markers, and size overrun;
  reconstructed inputs are deep copies and all canonical bytes are metered.
  SLAIF never executes client tools.

### Live-burn, accounting, and failure truth

- Result: PASSED.
- Evidence: output-text, function-argument, custom-input, reasoning-summary,
  and reasoning-text paths are counted; matching done events are deduplicated;
  threshold events are withheld. Focused gateway tests prove estimated
  interrupted finalization after output followed by missing usage, provider
  error, or disconnect. Final provider usage/cost remains authoritative.

### Privacy and harmless live evidence

- Result: PASSED.
- Evidence: the manual verifier used exact `/usr/bin/codex` 0.147.0, a private
  temporary home and work directory, a fixed dummy key, an isolated numeric
  `127.0.0.1` listener, no user config/auth/plugins/MCP/provider network, and
  exactly two in-memory requests. The first request matched the immutable
  fixture. The only client-side action was the fixed side-effect-free Code Mode
  expression `text("SAFE_TOOL_RESULT")`; its call/output matched, followed by
  the final assistant sequence. Raw request/response/tool/assistant/subprocess
  payloads were neither printed nor persisted.

### Documentation and compatibility claim

- Result: PASSED.
- Evidence: repository, Codex, Responses, forwarding, accounting, security,
  and compatibility contracts document the third gate, exact event/replay
  boundary, downstream-client execution ownership, accounting/privacy rules,
  harmless verifier, and remaining state/reasoning replay, Codex compaction,
  and full CLI-to-gateway E2E gaps. Status remains explicitly not
  Codex-compatible and makes no production claim. `README.md` is unchanged.

## Local verification

- `.venv/bin/python scripts/verify_codex_tool_roundtrip.py --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline`: PASSED — `RESULT=OK`, `REQUEST_COUNT=2`, `FIRST_REQUEST_MATCHES_FIXTURE=true`, `TOOL_CATEGORY=custom`, `TOOL_NAMESPACE=functions`, `TOOL_NAME=exec`, `TOOL_OUTPUT_MATCHED=true`, `FINAL_ASSISTANT_SEQUENCE=true`, `NETWORK_SCOPE=127.0.0.1`, `RAW_PAYLOADS_PERSISTED=false`.
- `.venv/bin/python -m pytest tests/unit/test_responses_codex_streaming_tools.py -q`: PASSED — 46 tests.
- `.venv/bin/python -m pytest tests/unit/test_responses_codex_client_tools.py -q`: PASSED — 47 tests.
- `.venv/bin/python -m pytest tests/unit/test_responses_request_policy.py -q`: PASSED — 189 tests.
- `.venv/bin/python -m pytest tests/unit/test_responses_route_capabilities.py -q`: PASSED — 53 tests.
- `.venv/bin/python -m pytest tests/unit/test_responses_streaming_live_burn.py -q`: PASSED — 18 tests.
- `.venv/bin/python -m pytest tests/unit/test_key_template_service.py -q`: PASSED — 16 tests.
- `.venv/bin/python -m pytest tests/unit/test_codex_protocol_capture.py -q`: PASSED — 21 tests.
- `.venv/bin/python -m pytest tests/unit/test_documentation_contract_drift.py -q`: PASSED — 9 tests.
- `.venv/bin/python -m pytest tests/unit/test_oap_governance.py -q`: FAILED — 7 passed, 1 failed. `test_initial_round_declares_new_pr_and_one_objective_one_pr` requires the literal **PR mode:** `CREATE_NEW_PR` declaration in the immutable active order.
- `.venv/bin/ruff check app/slaif_gateway/providers/streaming.py app/slaif_gateway/services/responses_gateway.py app/slaif_gateway/services/responses_request_policy.py app/slaif_gateway/services/responses_route_capabilities.py app/slaif_gateway/services/responses_streaming_live_burn.py app/slaif_gateway/services/key_template_service.py scripts/verify_codex_tool_roundtrip.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_request_policy.py tests/unit/test_responses_route_capabilities.py tests/unit/test_responses_streaming_live_burn.py tests/unit/test_key_template_service.py tests/unit/test_codex_protocol_capture.py`: PASSED.
- `git diff --check`: PASSED.
- `sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED — `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.
- Broad local suite, integration, E2E, browser, Docker, and HPC: NOT RUN — explicitly prohibited by the active order; GitHub CI supplied broad evidence.

## GitHub CI / required checks

- Check state observed for implementation head: 8 successful, 1 failed, 1 pending at report drafting.
- `CodeQL/Analyze (javascript-typescript)`: SUCCESS.
- `CodeQL/Analyze (python)`: SUCCESS.
- `CodeQL/Analyze Python`: SUCCESS.
- `CodeQL`: SUCCESS.
- `CI/Documentation hygiene`: SUCCESS.
- `CI/Docker Compose smoke`: SUCCESS.
- `CI/OpenAI-compatible E2E tests`: SUCCESS.
- `CI/PostgreSQL integration tests`: SUCCESS.
- `CI/Unit, lint, and migration head`: FAILURE — failed at `Run unit tests in parallel`; local focused reproduction identifies the immutable order's missing required `PR mode` literal. GitHub withheld the completed job log while the overall run remained pending.
- `CI/Playwright browser smoke`: PENDING — remained in `Install Chromium` after roughly 15 minutes; browser tests had not started.
- All required checks green for the implementation head at report drafting: no.
- Report-only commit may trigger fresh checks: strategic model must verify the `SELF` commit without rewriting this report.

## Local setup / dependencies

- Packages/tools/services installed or configured: none; existing `.venv`,
  `/usr/bin/codex`, Git, and authenticated `gh` were used.
- `sudo`-level setup performed: none.
- Durable setup changes committed/documented: none.

## Documentation

- Documentation impact: updated all seven required implementation contracts;
  `README.md` remained unchanged. The documents explicitly retain partial/not-
  compatible status and describe gates, event/replay limits, client execution
  ownership, live-burn/accounting/error/privacy behavior, harmless loopback
  evidence, and remaining gaps.

## Safety and scope confirmations

- Unrelated files changed: no.
- Production secrets accessed: no.
- Production systems accessed: no.
- Required tests skipped/not run: yes — broad local suite/integration/E2E/
  browser/Docker/HPC were explicitly prohibited; every listed focused command
  ran, with the one governance failure reported above.
- Scope deviation: no implementation scope deviation. The immutable strategic
  order defect prevents successful acceptance.
- Extra PR created for same numeric objective: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order and `oap/active` edited by coding agent: NO — exact strategic
  bytes were committed unchanged.
- Report-publication commit changes only this report file: yes.

## Known limitations / blockers

- The immutable active 007-a order lacks the exact governance-required
  **PR mode:** `CREATE_NEW_PR` declaration. The coding agent is forbidden to modify an
  activated order. This causes the required local OAP governance test and the
  GitHub unit job to fail.
- Browser smoke was pending in Chromium installation at report drafting.
- Broader Codex state/reasoning replay, Codex compaction, full CLI-to-gateway
  E2E, hosted tools/MCP/connectors, gateway tool execution, provider-side
  authorization, background/WebSocket behavior, and any production/release
  compatibility claim remain out of scope.

## Recommended strategic follow-up

Activate a 007 continuation that deliberately publishes a governance-compliant
work order and amends PR #232 without changing the already-published 007-a
order. Re-run the governance test and verify all PR-head checks before any
acceptance or merge decision.

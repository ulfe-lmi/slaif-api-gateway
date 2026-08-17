# OAP Coding-Agent Report — 004-a

## Work order

- Identifier: 004-a
- Work-order file:
  `oap/orders/004-a-codex-protocol-capture-golden-fixtures.md`
- Numeric objective: 004
- PR mode: CREATED_NEW_PR
- Active-pointer SHA-256:
  `e350189b4889970afe3c1b281b880ad1d0609df8153eb0cf06bf39f9a51486cf`
- Active-order SHA-256:
  `808efb7b175d0386ac72f7748d141041880e7e2b073023ad145b1b1b4be90677`

## Status

COMPLETE

## Executive summary

Objective 004-a added a manually invoked, version-pinned protocol-capture tool
and deterministic golden fixture for the Codex CLI 0.147.0,
`gpt-5.6-sol`, `api-key-responses-baseline` target. Two deliberate live runs
used a private temporary environment, dummy authentication, an empty working
directory, and one numeric `127.0.0.1` ephemeral listener. No real provider or
production service was contacted.

The fixture records only sanitized structural evidence. The observed request
was one `POST /v1/responses` with JSON content, redacted authorization
presence, and no `Content-Encoding`. Codex accepted the fixed loopback
`response.created` and `response.completed` SSE sequence. The current gateway
comparison reproducibly reports `not_compatible`; the capture does not enable
Codex, providers, routes, tools, quotas, or accounting.

The implementation also documents the future user-level configuration,
compression distinction, privacy boundary, and append-only version-upgrade
workflow. Eighteen capture tests, nine documentation-contract tests, eight OAP
governance tests, targeted Ruff, whitespace checks, and the required bounded
scans passed. The expected CLI-version mismatch failed safely before listener
binding, Codex execution, or fixture writing. Broad local suites were not run,
as required by the work-order test-economy boundary.

Exactly one ready PR, #229, was created from authoritative `origin/main`. Its
implementation head is
`93c05f9411fcd924a7c0218620e0fe89e059803f`. At report drafting all ten GitHub
checks on that implementation head were successful. No merge or auto-merge
action occurred.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- Canonical origin: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- PR number: 229
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/229
- PR title: `[OAP 004] Capture Codex Responses protocol baseline`
- PR state at report time: OPEN, non-draft
- PR merge state at report time: CLEAN and MERGEABLE
- Base branch: `main`
- Head branch: `oap/004-codex-protocol-capture-golden-fixtures`
- Starting `origin/main` SHA:
  `b87171e75e46d12b3edfcaa4f938882c797ee293`
- Implementation head SHA: `93c05f9411fcd924a7c0218620e0fe89e059803f`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `93c05f9411fcd924a7c0218620e0fe89e059803f`
    (`Capture Codex 0.147.0 Responses protocol`)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes, PR #229
- Amended existing PR this turn: no
- Objective-004 PR count at implementation-head verification: exactly one
- Merge performed: NO
- Auto-merge enabled: NO

## Starting-state reconciliation

- Canonical remote `main` and the required objective start both resolved to
  `b87171e75e46d12b3edfcaa4f938882c797ee293`, the merged PR #228 head.
- No objective-004 PR or branch existed before this turn. The only unrelated
  open PR was Dependabot PR #224; it was not reused or modified.
- The activated pointer contained exactly `004-a`, exactly one matching order
  resolved, and no 004-a report collision existed.
- The strategic pointer/order and intentional bootstrap state were preserved.
  Unrelated `.local-provider-catalog/` generated state was not modified,
  staged, cleaned, reset, stashed, or committed.
- The canonical origin was correct and authenticated `gh` access was active as
  `jpers1`.

## Pinned source and capture identity

- Installed executable: `/usr/bin/codex`
- Installed version output: `codex-cli 0.147.0`
- Official release/source tag: `rust-v0.147.0`
- Tagged source commit:
  `be6e8eac029b183056b7e4402879f15d2c85f61b`
- Bundled model: `gpt-5.6-sol`
- Capture profile: `api-key-responses-baseline`
- Wire API: Responses
- Fixture path:
  `tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`
- Fixture SHA-256:
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`
- Fixture size: 31,097 bytes
- Fixture compatibility status: `not_compatible`

Official evidence was pinned to the Codex 0.147.0 release/tag, its request
compression tests, model-catalog schema/bundled model data, loopback Responses
server, and request-construction source. User configuration documentation was
checked against official Codex configuration documentation.

## Changes made

- Added `scripts/capture_codex_protocol.py` with explicit `capture
  --write-fixture`, `verify-live`, and pure `validate` modes.
- Enforced exact executable version, model, profile, and output-path pinning.
  Version mismatch is checked before temporary setup, socket binding, Codex
  execution, or fixture writing.
- Isolated live execution in private temporary `CODEX_HOME`, `HOME`, and XDG
  paths with an empty work directory, ignored user config/rules, no MCP/plugin
  state, a child environment allowlist, dummy auth only, and retries disabled.
- Added a bounded one-request numeric-loopback HTTP/SSE server with method,
  path, header, encoding, length, JSON, request-count, timeout, subprocess, and
  SSE acceptance checks.
- Kept raw request and subprocess data memory-only and emitted fixed safe error
  categories. The sanitizer allowlists structural shapes and omits content,
  authorization values, descriptions, schema property names/defaults/examples,
  grammar values, prompts, instructions, client IDs, and raw data.
- Captured allowlisted non-free-text bundled-model metadata from the pinned
  binary in the same isolated environment.
- Derived the gateway comparison from the captured fixture and current
  Responses policy constants, with safe reason codes and deterministic
  canonical JSON.
- Added 18 pure unit tests. Imports and ordinary pytest never execute Codex,
  bind a socket, write a fixture, or make a network call.
- Added the Codex compatibility document and updated the compatibility matrix,
  Responses contract, security model, and narrow AGENTS governance exception.
- Submitted the strategic-authored 004-a pointer and order unchanged with the
  implementation commit.

## Files changed

Implementation commit:

- `AGENTS.md`
- `docs/codex-compatibility.md`
- `docs/compatibility-matrix.md`
- `docs/responses-compatibility.md`
- `docs/security-model.md`
- `oap/active` (strategic-authored bytes committed unchanged)
- `oap/orders/004-a-codex-protocol-capture-golden-fixtures.md`
  (strategic-authored bytes committed unchanged)
- `scripts/capture_codex_protocol.py`
- `tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`
- `tests/unit/test_codex_protocol_capture.py`

Report-publication commit:

- `oap/reports/004-a-codex-protocol-capture-golden-fixtures.md`

No runtime gateway module, route, registry, capability, schema, migration,
dependency, lock, configuration, CI, deployment, provider-catalog, pricing,
release, prior OAP transcript, or unrelated path changed.

## Safe observed structural summary

- Request count/method/path: exactly one `POST /v1/responses`.
- Request content: `application/json`; authorization present and redacted;
  `Content-Encoding` absent.
- Top-level fields: `client_metadata`, `include`, `input`, `model`,
  `parallel_tool_calls`, `prompt_cache_key`, `reasoning`, `store`, `stream`,
  `text`, and `tool_choice`.
- Input structure included `additional_tools` plus developer/user `message`
  items with `input_text` content; message instances carrying `id` were
  observed structurally without retaining identifier values or text.
- Tool namespaces: `functions` and `collaboration`.
- Safe tool names: `exec`, `wait`, `request_user_input`, `followup_task`,
  `interrupt_agent`, `list_agents`, `send_message`, `spawn_agent`, and
  `wait_agent`. These names are evidence, not an execution allowlist.
- Mock response: fixed `response.created` then `response.completed`; Codex
  exited successfully and accepted it.
- Bundled-model evidence contains only allowlisted identifiers, booleans,
  numeric limits, enum-like values, and structural field presence. Free-text
  descriptions/instructions were not retained.

Current gateway compatibility findings:

- Overall: `not_compatible`.
- Supported stream events: `response.created` and `response.completed`.
- Supported content type: `input_text`.
- Rejected top-level fields/reasons:
  - `client_metadata`: `responses_field_not_supported`
  - `include`: `responses_multimodal_not_supported`
  - `parallel_tool_calls`: `responses_tools_not_supported`
  - `prompt_cache_key`: `responses_state_not_supported`
  - `reasoning`: `responses_field_not_supported`
  - `text.verbosity`: `responses_field_not_supported`
  - `tool_choice`: `responses_tool_choice_invalid`
- Rejected input structures/reasons:
  - `additional_tools`: `responses_input_item_type_not_supported`
  - message instances with captured unsupported shape:
    `responses_input_item_invalid`
- Both namespaces and every captured nested tool are rejected with
  `responses_hosted_tool_not_supported` under the current fail-closed
  comparison.

The API-key request had no `Content-Encoding`. Documentation keeps this
separate from Codex's tagged ChatGPT-backend zstd behavior; it does not infer
that every Codex authentication/backend mode is uncompressed.

## Acceptance-criteria evidence

### Criterion 1 — Exact pinned evidence through loopback only

- Result: PASSED
- Evidence: both live runs required exact installed 0.147.0, model
  `gpt-5.6-sol`, and profile `api-key-responses-baseline`; each used one
  numeric loopback listener with dummy auth and no provider URL/key.

### Criterion 2 — Deterministic, bounded, sanitized fixture

- Result: PASSED
- Evidence: live verification was canonical-JSON-equivalent to the checked-in
  31,097-byte fixture with SHA-256 `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.
  Parser caps, strict structural allowlists, unit tests, and both mandated
  canary scans prove the bounded persistence contract; no canary matched.

### Criterion 3 — Compression result is accurately bounded

- Result: PASSED
- Evidence: fixture header evidence records absent request
  `Content-Encoding`; docs explicitly distinguish API-key mode from tagged
  ChatGPT-backend zstd behavior.

### Criterion 4 — Model metadata allowlist

- Result: PASSED
- Evidence: the pinned bundled catalog is reduced to selected identifiers,
  booleans, numeric limits, enum-like values, and structural field presence;
  tests reject unexpected free-text or altered identity.

### Criterion 5 — Live match and pre-capture mismatch refusal

- Result: PASSED
- Evidence: `verify-live` returned `VERIFY_LIVE_OK
  status=not_compatible`; the 0.146.0 expected-version negative test exited 1
  with the safe mismatch message before binding, capture, or write.

### Criterion 6 — Honest reproducible compatibility diff

- Result: PASSED
- Evidence: capture and live verification both derived `not_compatible`; the
  safe field, input, namespace, and tool rejection names/reason codes are
  recorded above and in the fixture.

### Criterion 7 — No Codex/network activity in normal tests

- Result: PASSED
- Evidence: the 18 pure capture tests mock side effects and prove import/no
  action. All three focused pytest commands, Ruff, and diff hygiene passed.

### Criterion 8 — Accurate future configuration and upgrade workflow

- Result: PASSED
- Evidence: `docs/codex-compatibility.md` gives future standard
  `OPENAI_API_KEY` plus `model_provider`/`[model_providers.slaif]`/
  `wire_api = "responses"` configuration while stating the profile is not
  currently compatible. Upgrades require a new version directory/fixture and
  review; old fixtures are never overwritten.

### Criterion 9 — Existing trust and governance contracts remain intact

- Result: PASSED
- Evidence: no runtime, provider-secret, content-storage, quota/accounting,
  capability, HPC, CI, deployment, or OAP protocol behavior was weakened. The
  AGENTS exception is limited to explicit manual capture/verify actions.

### Criterion 10 — One scoped PR and immutable report

- Result: PASSED
- Evidence: PR #229 is the only objective-004 PR. Its implementation commit
  contains exactly the ten permitted non-report paths. This `SELF` commit
  changes only the required report and has the literal implementation head as
  first parent. No merge or auto-merge action occurred.

## Local verification

- `/usr/bin/codex --version`: PASSED — `codex-cli 0.147.0`.
- `.venv/bin/python scripts/capture_codex_protocol.py capture --codex-binary
  /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile
  api-key-responses-baseline --output
  tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
  --write-fixture`: PASSED — `CAPTURE_OK
  fixture_sha256=436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432
  status=not_compatible`.
- `.venv/bin/python scripts/capture_codex_protocol.py verify-live
  --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model
  gpt-5.6-sol --profile api-key-responses-baseline --fixture
  tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED —
  `VERIFY_LIVE_OK status=not_compatible`; fixture was not rewritten.
- `.venv/bin/python scripts/capture_codex_protocol.py verify-live
  --codex-binary /usr/bin/codex --expected-cli-version 0.146.0 --model
  gpt-5.6-sol --profile api-key-responses-baseline --fixture
  tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED
  EXPECTED NEGATIVE — exit 1,
  `CAPTURE_ERROR: Codex CLI version does not match the requested pinned
  version.`; no listener binding, Codex execution, or write occurred.
- `.venv/bin/python -m pytest tests/unit/test_codex_protocol_capture.py -q`:
  PASSED — 18 passed.
- `.venv/bin/python -m pytest tests/unit/test_documentation_contract_drift.py
  -q`: PASSED — 9 passed.
- `.venv/bin/python -m pytest tests/unit/test_oap_governance.py -q`: PASSED —
  8 passed.
- `.venv/bin/ruff check scripts/capture_codex_protocol.py
  tests/unit/test_codex_protocol_capture.py`: PASSED — `All checks passed!`.
- `git diff --check`: PASSED.
- `rg -n "CAPTURED, NOT YET CODEX-COMPATIBLE|0.147.0|rust-v0.147.0|wire_api|Content-Encoding|not_compatible" docs/codex-compatibility.md docs/responses-compatibility.md docs/compatibility-matrix.md tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`:
  PASSED — required status/version/tag/wire/compression/result evidence found.
- `rg -n "SLAIF_CAPTURE_PROMPT_CANARY_DO_NOT_PERSIST|SLAIF_CAPTURE_TOKEN_CANARY_DO_NOT_PERSIST" tests/fixtures/codex docs/codex-compatibility.md`:
  PASSED — no matches.
- `git status --short`: PASSED — only approved objective paths before explicit
  staging; clean after the implementation commit and push.

The fixture/docs scan for the implementation's additional internal canaries
also had no matches. No raw capture was printed for absence proof.

Explicitly NOT RUN locally per the work order:

- full unit suite;
- product-contract suite beyond the named documentation test;
- integration suite;
- E2E suite;
- Playwright/browser suite;
- Docker/Compose suite;
- HPC/supercomputer harness;
- real upstream tests.

GitHub CI supplied broad regression evidence on the implementation head.

## GitHub CI / required checks

Check state observed for implementation head
`93c05f9411fcd924a7c0218620e0fe89e059803f`: 10 SUCCESS, 0 FAILURE,
0 PENDING, 0 CANCELLED, 0 SKIPPED.

- `Unit, lint, and migration head`: SUCCESS — 1m48s.
- `Analyze (javascript-typescript)`: SUCCESS — 41s.
- `Analyze Python`: SUCCESS — 1m01s.
- `Analyze (python)`: SUCCESS — 1m38s.
- `PostgreSQL integration tests`: SUCCESS — 2m13s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m23s.
- `Playwright browser smoke`: SUCCESS — 1m25s.
- `Docker Compose smoke`: SUCCESS — 54s.
- `Documentation hygiene`: SUCCESS — 7s.
- `CodeQL`: SUCCESS — 2s.
- All required checks green for the implementation head at report drafting:
  yes.
- Report-only commit may trigger fresh checks: strategic model must verify the
  `SELF` commit without rewriting this report.

## Local setup / dependencies

- Packages/tools/services installed or configured: none during this objective;
  the required `/usr/bin/codex` 0.147.0 and repository `.venv` were already
  present.
- `sudo`-level setup performed: none.
- Durable setup changes committed/documented: none.
- Temporary resources: private temporary directories and one ephemeral
  loopback listener per deliberate capture, automatically removed/closed.
- External database, Redis, Docker, browser, provider, email, catalog, or
  upstream service used locally: none.

## Documentation

Documentation updated: `AGENTS.md`, `docs/codex-compatibility.md`,
`docs/compatibility-matrix.md`, `docs/responses-compatibility.md`, and
`docs/security-model.md`.

The documentation labels the evidence **CAPTURED, NOT YET
CODEX-COMPATIBLE**, gives a future OpenAI-compatible client configuration,
records exact capture/verification commands and upgrade rules, explains
API-key versus ChatGPT-backend compression, and specifies the memory-only/raw
data and sanitized-fixture privacy boundary. It does not claim production
certification or current Codex compatibility.

## Safety and scope confirmations

- Unrelated files changed: no.
- Production secrets accessed: no.
- Production systems accessed: no.
- Real provider or upstream traffic: no.
- Real gateway/provider key used: no; dummy loopback authentication only.
- Raw request/header/body/subprocess artifact persisted or printed: no.
- Existing `.local-provider-catalog/` artifacts modified or committed: no.
- Required tests skipped/not run: no. Broad suites were explicitly NOT RUN
  under the work-order test-economy instruction; GitHub CI ran its standard
  broad matrix.
- Scope deviation: no.
- Runtime/provider behavior changed: no.
- Extra PR created for same numeric objective: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order and `oap/active` edited by coding agent: NO.
- Report-publication commit changes only this report file: yes.

## Known limitations / blockers

- No blocker to this evidence-capture objective.
- The captured profile remains intentionally `not_compatible`. Current
  fail-closed rejections are evidence for future separately activated work,
  not defects to bypass in this objective.
- The fixture is pinned only to Codex CLI 0.147.0,
  `gpt-5.6-sol`, and the named API-key Responses profile. It must not be
  generalized to later CLI/model/profile/backend combinations without a new
  versioned capture and review.
- No real upstream inference smoke or gateway runtime compatibility test ran;
  both were explicit non-goals.

## Recommended strategic follow-up

Independently verify the `SELF` report commit, fixture privacy/structure,
focused commands, and final-head GitHub checks. The strategic model decides
whether objective 004 is accepted and whether any separately scoped objective
005 through 011 should be activated. Do not treat this capture as authority to
enable Codex or merge this PR.

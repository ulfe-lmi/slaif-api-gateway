# OAP Coding-Agent Report — 004-b

## Work order

- Identifier: 004-b
- Work-order file: `oap/orders/004-b-pin-fixture-integrity-validation.md`
- Numeric objective: 004
- PR mode: AMENDED_EXISTING_PR
- Active-pointer SHA-256:
  `7b3bee6dfa5f3be8d2f07cf1804fcd2046e0cb81096ab24490593a67a6bd6e7a`
- Active-order SHA-256:
  `8e28ca7e1f83f5463883025f4738f97d8b143e371939e1c38c781f6742a2231e`

## Status

COMPLETE

## Executive summary

Objective 004-b closes the independently identified fixture-integrity gap in
PR #229. The capture tool now pins the entire canonical sanitized Codex fixture
to the approved SHA-256 after all existing semantic and privacy checks. Any
appended, removed, or changed canonical content fails with one fixed safe error
that echoes neither injected content nor a computed digest.

The single validation implementation is reached by `capture_live()` before a
fixture can return to the write path, by both sides of `verify-live`, and by
pure `validate`. Three new deep-copy mutation tests prove that an unknown
nested free-text/secret canary, removal of a harmless catalog member, and a
subtle parameter-schema discriminator change all fail specifically at the
canonical integrity gate. The unmodified checked-in fixture still validates.

Exactly one permitted in-memory loopback recapture passed with
`VERIFY_LIVE_OK status=not_compatible`. No capture/write action ran. The
fixture was not edited and remains exactly 31,097 bytes with SHA-256
`436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.
Pure validation, 21 capture tests, 8 OAP-governance tests, targeted Ruff, diff
hygiene, and the no-fixture-diff check passed. Broad local suites were not run
under the explicit test-economy boundary.

PR #229 was amended in place at implementation head
`c30fd106f0444995a54e2d5193f4cc8011bfdb35`. It remained the sole
objective-004 PR, open, non-draft, cleanly mergeable, and without auto-merge.
All ten GitHub checks on the implementation head were successful. No new PR or
merge action occurred.

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
- Starting remote PR head SHA:
  `99203f526956f7797ee1ce415ee6d66086b9d857`
- Prior implementation head SHA:
  `93c05f9411fcd924a7c0218620e0fe89e059803f`
- Implementation head SHA: `c30fd106f0444995a54e2d5193f4cc8011bfdb35`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commit pushed this round:
  - `c30fd106f0444995a54e2d5193f4cc8011bfdb35`
    (`Pin Codex fixture canonical integrity`)
- All PR commits before this report commit:
  - `93c05f9411fcd924a7c0218620e0fe89e059803f`
    (`Capture Codex 0.147.0 Responses protocol`)
  - `99203f526956f7797ee1ce415ee6d66086b9d857`
    (`Publish OAP 004-a execution report`)
  - `c30fd106f0444995a54e2d5193f4cc8011bfdb35`
    (`Pin Codex fixture canonical integrity`)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes, PR #229
- Objective-004 PR count at implementation-head verification: exactly one
- Merge performed: NO
- Auto-merge enabled: NO

## Starting-state reconciliation

- Local HEAD, the remote objective branch, and GitHub PR #229 all resolved to
  required starting report head
  `99203f526956f7797ee1ce415ee6d66086b9d857` before editing.
- PR #229 was open, non-draft, cleanly mergeable, based on `main`, headed by the
  required objective branch, and had no auto-merge request.
- All ten checks on the 004-a report head were successful.
- Exactly one objective-004 PR existed. Unrelated Dependabot PR #224 was not
  reused or modified.
- The only dirty paths were strategic-authored `oap/active=004-b` and the
  uniquely matching 004-b order. Their bytes were preserved.
- No 004-b report collision existed.
- The 004-a report commit's first parent, sole changed path, Git blob, and local
  bytes were verified against the immutable transcript.
- The fixture began at the approved SHA and 31,097-byte size.
- `.local-provider-catalog/`, user Codex config/auth, local secrets, and
  unrelated state were not touched.

Immutable transcript hashes:

- 004-a order:
  `808efb7b175d0386ac72f7748d141041880e7e2b073023ad145b1b1b4be90677`
- 004-a report:
  `3dafff8ad5331951059090979b8e753d63a5631ffcb626e586b6944edc689b98`
- 004-b order:
  `8e28ca7e1f83f5463883025f4738f97d8b143e371939e1c38c781f6742a2231e`

## Changes made

- Added `APPROVED_CANONICAL_FIXTURE_SHA256` with the independently approved
  digest and kept it non-configurable by CLI/environment.
- Added one fixed safe integrity error message.
- Extended `validate_fixture()` after all existing semantic, compatibility,
  allowlist, and forbidden-content checks to SHA-256 the complete
  `canonical_json_bytes(fixture)` document and require the exact approved
  digest.
- Reused the existing call topology: `capture_live()` validates before return,
  `_load_fixture()` validates checked-in data, `verify-live` validates both
  live and checked-in documents, and pure `validate` calls `_load_fixture()`.
- Added an independent test-side digest pin and exact digest assertion for the
  checked-in fixture.
- Added integrity tests for an appended unknown nested canary, removal of an
  otherwise optional catalog member, and mutation of a deep tool parameter
  schema primitive discriminator without changing identity/path.
- Asserted integrity failures contain only the fixed message and contain
  neither injected content nor the mutation's computed digest.
- Minimally documented the approved SHA, full-document validation semantics,
  non-configurable pin, and explicit reviewed re-pin requirement for future
  structural drift.
- Submitted the strategic-authored 004-b active pointer and order unchanged in
  the continuation implementation commit.

## Files changed

Continuation implementation commit:

- `docs/codex-compatibility.md`
- `oap/active` (strategic-authored bytes committed unchanged)
- `oap/orders/004-b-pin-fixture-integrity-validation.md`
  (strategic-authored bytes committed unchanged)
- `scripts/capture_codex_protocol.py`
- `tests/unit/test_codex_protocol_capture.py`

Report-publication commit:

- `oap/reports/004-b-pin-fixture-integrity-validation.md`

The checked-in fixture and all 004-a history remain byte-identical. No other
documentation, runtime/API module, policy, provider, route, quota/accounting,
schema, migration, dependency, lock, configuration, CI, deployment,
provider-catalog, pricing, release, prior report, or unrelated path changed.

## Acceptance-criteria evidence

### Criterion 1 — Complete canonical fixture integrity is pinned

- Result: PASSED
- Evidence: `validate_fixture()` computes SHA-256 over the complete canonical
  JSON bytes after existing checks and compares it to the exact approved
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`
  constant. There is no CLI or environment override.

### Criterion 2 — Appended and subtle structural mutations fail safely

- Result: PASSED
- Evidence: deep-copy tests append unknown nested content, remove a harmless
  structural member, and modify a deep schema primitive discriminator. Each
  bypasses earlier selected semantic checks and fails with exactly the fixed
  canonical integrity message.

### Criterion 3 — Existing fixture and live recapture pass unchanged

- Result: PASSED
- Evidence: pure validation returned `FIXTURE_VALID
  status=not_compatible`; the one permitted live in-memory recapture returned
  `VERIFY_LIVE_OK status=not_compatible`. `git diff --exit-code` proved the
  fixture was not changed, and SHA/size remained exact.

### Criterion 4 — Errors echo neither injected content nor digest

- Result: PASSED
- Evidence: the mutation-test helper independently computes each altered
  document digest, asserts the exact fixed error string, and asserts both the
  digest and optional injected canary are absent from it.

### Criterion 5 — Existing 004-a behavior remains green

- Result: PASSED
- Evidence: every existing test was retained; the focused file increased from
  18 to 21 passing tests. The compatibility result remains `not_compatible`,
  the live fixture still matches, and sanitizer/privacy assertions remain
  unchanged.

### Criterion 6 — Only allowed paths changed; fixture bytes are identical

- Result: PASSED
- Evidence: implementation commit `c30fd106…db35` changes exactly the five
  work-order-authorized paths. The fixture has no diff and remains 31,097 bytes
  at the approved SHA.

### Criterion 7 — Existing PR amended without merge/auto-merge

- Result: PASSED
- Evidence: PR #229 advanced from `99203f5…d857` to implementation head
  `c30fd106…db35`. It is the sole objective-004 PR; no replacement/new PR,
  merge, or auto-merge action occurred.

### Criterion 8 — Immutable report and GitHub merge gate

- Result: PASSED
- Evidence: all ten checks on the literal implementation head were successful.
  This report is the sole path in the `SELF` commit, whose first parent is the
  implementation head. Remote head, parent, changed path, blob, and exact bytes
  are verified before FIFO `OK`. Fresh report-head checks remain subject to the
  protocol's independent strategic verification rule.

## Local verification

- `.venv/bin/python scripts/capture_codex_protocol.py verify-live
  --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model
  gpt-5.6-sol --profile api-key-responses-baseline --fixture
  tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED —
  `VERIFY_LIVE_OK status=not_compatible`; in-memory loopback only, fixture not
  rewritten.
- `.venv/bin/python scripts/capture_codex_protocol.py validate --fixture
  tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED —
  `FIXTURE_VALID status=not_compatible`.
- `.venv/bin/python -m pytest tests/unit/test_codex_protocol_capture.py -q`:
  PASSED — 21 passed.
- `.venv/bin/python -m pytest tests/unit/test_oap_governance.py -q`: PASSED —
  8 passed.
- `.venv/bin/ruff check scripts/capture_codex_protocol.py
  tests/unit/test_codex_protocol_capture.py`: PASSED — `All checks passed!`.
- `git diff --check`: PASSED.
- `git diff --exit-code --
  tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED —
  no fixture diff.
- `sha256sum
  tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED —
  exact approved SHA.
- `wc -c
  tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`: PASSED —
  31,097 bytes.
- `git status --short`: PASSED — exactly the five approved continuation paths
  before explicit staging; clean after implementation commit and push.

The pure focused checks were run once before the single live verify during
development and the order's exact final focused sequence was run afterward.
No capture/write action ran.

Explicitly NOT RUN locally per the work order:

- capture/write action;
- full unit suite;
- documentation-contract test outside the specified 004-b matrix;
- integration suite;
- E2E suite;
- Playwright/browser suite;
- Docker/Compose suite;
- HPC/supercomputer harness;
- real upstream/provider tests.

GitHub CI supplied the repository's broad regression evidence on the
implementation head.

## GitHub CI / required checks

Check state observed for implementation head
`c30fd106f0444995a54e2d5193f4cc8011bfdb35`: 10 SUCCESS, 0 FAILURE,
0 PENDING, 0 CANCELLED, 0 SKIPPED.

- `Unit, lint, and migration head`: SUCCESS — 2m01s.
- `Analyze (javascript-typescript)`: SUCCESS — 46s.
- `Analyze Python`: SUCCESS — 1m07s.
- `Analyze (python)`: SUCCESS — 1m41s.
- `PostgreSQL integration tests`: SUCCESS — 2m05s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m27s.
- `Playwright browser smoke`: SUCCESS — 1m46s.
- `Docker Compose smoke`: SUCCESS — 56s.
- `Documentation hygiene`: SUCCESS — 7s.
- `CodeQL`: SUCCESS — 2s.
- All required checks green for the implementation head at report drafting:
  yes.
- Report-only commit may trigger fresh checks: strategic model must verify the
  `SELF` commit without rewriting this report.

## Local setup / dependencies

- Packages/tools/services installed or configured: none.
- `sudo`-level setup performed: none.
- Durable setup changes committed/documented: none.
- Temporary resources: one private temporary Codex environment and one
  ephemeral numeric loopback listener for the explicitly required live verify;
  both were removed/closed automatically.
- External database, Redis, Docker, browser, provider, email, catalog, or
  upstream service used locally: none.

## Documentation

Documentation updated: `docs/codex-compatibility.md`.

The document now records the approved canonical fixture SHA-256 and states
that pure validation and live paths pin the full canonical document after
semantic/privacy checks. It explains that structural drift requires a new
versioned reviewed fixture plus explicit code/documentation pin and cannot
silently overwrite existing evidence. Compatibility status and captured
findings remain unchanged.

## Safety and scope confirmations

- Unrelated files changed: no.
- Fixture bytes changed: no.
- Prior OAP order/report changed: no.
- Production secrets accessed: no.
- Production systems accessed: no.
- Real provider/upstream traffic: no.
- Human Codex config/auth accessed or modified: no.
- Capture/write action executed: no.
- Raw content, injected canary, or computed mutation digest echoed by errors:
  no.
- Existing `.local-provider-catalog/` artifacts modified or committed: no.
- Required tests skipped/not run: no. Broad suites were explicitly NOT RUN by
  order; GitHub CI ran its standard matrix.
- Scope deviation: no.
- Runtime/provider/policy/accounting behavior changed: no.
- Extra PR created for same numeric objective: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- Activated order and `oap/active` edited by coding agent: NO.
- Report-publication commit changes only this report file: yes.

## Known limitations / blockers

- No blocker to this fixture-integrity continuation.
- The pinned profile remains `not_compatible`; this round changes evidence
  integrity only and does not authorize or implement Codex gateway behavior.
- The exact SHA intentionally binds validation to this one 0.147.0/model/
  profile canonical document. Legitimate future drift requires a separate
  reviewed versioned fixture and code/documentation pin.
- No capture/write, real provider smoke, or broad local suite ran; those were
  explicit non-goals.

## Recommended strategic follow-up

Independently verify the `SELF` report commit, report parent/path/bytes, the
unchanged fixture SHA/size, fixed-message mutation behavior, live in-memory
verify result, and final-head checks. The strategic model decides acceptance,
continuation, or merge; the coding agent has not merged or enabled auto-merge.

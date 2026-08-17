# OAP Work Order — 004-b

## Objective

Close the fixture-integrity gap found by independent strategic privacy review:
pin the complete canonical sanitized golden SHA-256 so any appended, removed,
or structurally altered content fails validation before fixture write or live
verification. Amend PR #229 only.

Do not create a new PR, recapture/write the fixture, relax sanitization, or run
a broad local suite.

## GitHub objective state

- Numeric objective: `004`
- Execution round: `004-b`
- PR mode: `AMEND_EXISTING_PR`
- Existing PR: `#229`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/229`
- Required head branch: `oap/004-codex-protocol-capture-golden-fixtures`
- Base branch: `main`
- Starting remote PR head:
  `99203f526956f7797ee1ce415ee6d66086b9d857`
- Prior implementation head:
  `93c05f9411fcd924a7c0218620e0fe89e059803f`
- Existing fixture SHA-256:
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`
- Prior round: `004-a`, complete
- Repository: `ulfe-lmi/slaif-api-gateway`

PR #229 is the sole objective-004 PR. Amend it; never create another PR.

## Review finding

The checked-in fixture itself passed a privacy-first strategic scan:

- 31,097 bytes;
- 489 string values;
- longest string value 39 characters;
- no whitespace-bearing/free-text string values;
- no absolute paths, URLs, email addresses, bearer values, secret-like values,
  prompt/token canaries, or instruction/AGENTS markers.

The capture generator also validates exact version/model/profile and sanitizes
raw data before persistence. However, `validate_fixture()` currently checks
selected invariants rather than the complete canonical document. A manually
appended unknown field such as `capture.unexpected_raw` could pass those
selected checks if it avoided the few fixed canaries. This is inconsistent with
the promised altered-fixture failure and append-only golden integrity.

The complete fixture is intentionally pinned to one CLI/source/model/profile,
so an exact canonical SHA check is the correct fail-closed boundary.

## Governing instructions and start

Re-read `AGENTS.md`, the coding-agent protocol, immutable 004-a order/report,
the capture script/test/fixture/docs, and this order.

Verify PR #229 remains open/non-draft on the required branch at the exact
starting head. The strategic model has atomically published this order and
`oap/active=004-b`; those must be the only dirty paths. Preserve their bytes.

Do not touch user Codex config/auth, PR #224, `.local-provider-catalog/`, or
unrelated state.

## Allowed path scope

Implementation/governance commits may change only:

```text
docs/codex-compatibility.md
oap/active
oap/orders/004-b-pin-fixture-integrity-validation.md
scripts/capture_codex_protocol.py
tests/unit/test_codex_protocol_capture.py
```

The final report-only commit may add only:

```text
oap/reports/004-b-pin-fixture-integrity-validation.md
```

Do not edit the fixture, 004-a history, other docs/tests, runtime, dependencies,
CI, schemas, configuration, or any unrelated path.

## Required implementation

### A. Pin the complete canonical fixture

Add a clearly named constant in `scripts/capture_codex_protocol.py` for the
exact approved canonical fixture SHA-256:

```text
436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432
```

After all semantic/safety checks in `validate_fixture()`, compute SHA-256 over
`canonical_json_bytes(fixture)` and require an exact match. On mismatch, raise a
fixed safe `CaptureError` that contains no fixture values and no computed hash.

This validation must execute:

- inside `capture_live()` before it returns a fixture to the write path;
- for `verify-live` live in-memory capture and checked-in fixture load;
- for pure `validate`.

The existing call topology may already provide those locations through
`validate_fixture()`; keep one canonical implementation rather than duplicate
checks.

The result must be:

- same-version same-profile canonical live output: passes;
- manually appended/removed/changed content: fails;
- repackaged or structurally drifting 0.147.0 output: fails before overwrite;
- future version: still fails at version pinning before capture;
- no raw value/hash echo in errors.

Do not make the digest configurable by CLI flag or environment. A new approved
fixture/version requires an explicit reviewed code/doc change.

### B. Strengthen focused tests

In `tests/unit/test_codex_protocol_capture.py`:

- assert the pinned digest constant equals the independently recorded SHA;
- append an unknown nested field with a synthetic free-text/secret canary to a
  deep copy and prove validation fails with only the fixed integrity message;
- remove a harmless-looking structural member and prove validation fails;
- modify a discriminator/tool/field shape without changing identity/path and
  prove validation fails;
- prove the unmodified checked-in fixture still validates;
- prove the failure string contains neither injected content nor computed
  digest.

Keep every existing test. Normal pytest must not execute Codex, bind a socket,
or write the real fixture.

### C. Document integrity semantics

Update `docs/codex-compatibility.md` minimally with the approved fixture
SHA-256 and explain that pure validation and live capture pin the full canonical
document, not only selected fields. Structural drift requires a new versioned,
reviewed fixture/code pin and cannot overwrite existing evidence silently.

Do not change compatibility status or any captured finding.

## Explicit non-goals

- No fixture content change or new capture profile/version.
- No gateway runtime, policy, route, provider, accounting, schema, config,
  dependency, CI, or deployment change.
- No sanitizer weakening or new persisted discriminator/free text.
- No real provider/user auth/config access.
- No capture/write action.
- No full unit, integration, E2E, browser, Docker, or HPC suite.
- No second PR, merge, or auto-merge by the coding agent.

## Focused verification only

Run one in-memory loopback verify because digest enforcement now sits on that
path; do not rewrite the fixture:

```bash
.venv/bin/python scripts/capture_codex_protocol.py verify-live \
  --codex-binary /usr/bin/codex \
  --expected-cli-version 0.147.0 \
  --model gpt-5.6-sol \
  --profile api-key-responses-baseline \
  --fixture tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
```

Then run only:

```bash
.venv/bin/python scripts/capture_codex_protocol.py validate \
  --fixture tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
.venv/bin/python -m pytest tests/unit/test_codex_protocol_capture.py -q
.venv/bin/python -m pytest tests/unit/test_oap_governance.py -q
.venv/bin/ruff check scripts/capture_codex_protocol.py tests/unit/test_codex_protocol_capture.py
git diff --check
sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
git status --short
```

The SHA must remain exactly the approved value. Do not run capture/write or any
broad local suite. GitHub CI supplies broad evidence.

## Acceptance criteria

1. Complete canonical fixture integrity is pinned to the approved SHA.
2. Unknown appended content and subtle structural mutation fail safely.
3. The existing fixture and one live in-memory recapture pass unchanged.
4. No injected content or digest is echoed by validation errors.
5. Existing 004-a capture/privacy/compatibility tests remain green.
6. Only allowed paths change and fixture bytes remain identical.
7. PR #229 is amended; no second PR, merge, or auto-merge occurs.
8. Final immutable report parent/path and all GitHub merge-gate checks pass.

## GitHub and report requirements

Push all non-report commits to the existing branch/PR and inspect actual
GitHub checks. Pending/missing/failed is not green. Never merge.

Publish exactly one immutable report at
`oap/reports/004-b-pin-fixture-integrity-validation.md` with the complete OAP
format, literal implementation SHA, `Report publication commit: SELF`, exact
focused/live-verify results, unchanged fixture SHA/size, broad-suite NOT RUN
list, docs impact, and safety/scope confirmations.

The final report-only commit must have the implementation head as first parent
and change only the new report. Push/verify it, signal exact `OK`, and return to
the listener.

If canonical live output does not match the approved digest, do not rewrite or
re-pin it in this round. Publish a truthful blocker for strategic review.

Do not merge under any circumstance.

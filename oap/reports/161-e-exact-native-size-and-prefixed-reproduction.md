# OAP Coding-Agent Report — 161-e

## Work order

- Identifier: 161-e
- Work-order file: `oap/orders/161-e-exact-native-size-and-prefixed-reproduction.md`
- Numeric objective: 161
- PR mode: `AMENDED_EXISTING_PR`

## Status

FAILED

## Executive summary

The 161-d native-size discrepancy was corrected by replacing the guessed
128 MiB maximum with exact public byte-size equality: `258322048` bytes. The
size predicate runs before hashing or invocation, the exact native digest and
all prior provenance gates remain enforced, and synthetic tests inject only
small bounded expected sizes. The complete task-local package preflight passed
with both version probes. The one newly authorized zero-retry reproduction was
then run exactly once from the clean implementation head and terminated with
the fixed safe result `VERIFY_CODEX_0149_ASSISTANT_HISTORY_BASE_FAILED
code=unexpected_other`. No accepted Gateway progression or reproduction
predicate was established. The run was not repeated and no verifier/test
mutation followed it.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 298
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/298
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/161-codex-assistant-output-history`
- Starting remote SHA: `b26a016a2b753ce5a33d6bafaeec344b32c5060b`
- Implementation head SHA: `2d67a2c8d5cd5c0c5831fb45a09cac4c9522bc4b`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `2d67a2c8d5cd5c0c5831fb45a09cac4c9522bc4b`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes
- Merge performed: NO

## Changes made

- Added the exact public native artifact size `258322048` bytes.
- Required native size equality before hashing or version probing, with a fixed
  `codex_native_size_invalid` diagnostic.
- Kept the hard read ceiling at the exact public size and rejected invalid,
  boolean, zero, and oversized synthetic size injections.
- Preserved exact package manifests, npm integrities, launcher link and digest,
  native path and digest, Linux x64 checks, executable/file-shape checks,
  exact version probes, and the `.bin/codex` reproduction entrypoint.
- Added one-byte-under, one-byte-over, and invalid-size injection tests.
- Preserved the strategic 161-e order and `oap/active` bytes unchanged.

## Files changed

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-e-exact-native-size-and-prefixed-reproduction.md`

## Acceptance-criteria evidence

### Exact provenance preflight

- Root distribution: PASS — `@openai/codex@0.149.0`.
- Linux x64 alias and platform distribution: PASS — alias
  `@openai/codex-linux-x64` to `npm:@openai/codex@0.149.0-linux-x64`, with
  Linux/x64 manifest facts.
- npm package-lock integrity: PASS — both exact public expected values.
- Launcher: PASS — exact relative link, 7236-byte size, executable regular
  resolved target, and SHA-256
  `134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477`.
- Native target: PASS — exact source-selected path, regular non-symlinked
  executable file, exact size `258322048`, and SHA-256
  `bbc3341e44c9ead340ed9570c17be936e37870f570751a941699ffd04d672827`.
- Source mapping: PASS — tag `rust-v0.149.0`, commit
  `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`, target
  `x86_64-unknown-linux-musl`.
- Version probes: PASS — launcher and native output matched the exact bounded
  `codex-cli 0.149.0` line.
- Task-local package preflight: PASS — no Gateway request.

### One reproduction

- Reproduction count: exactly one.
- Reproduction command: `env -u TEST_DATABASE_URL -u DATABASE_URL
  -u RUN_UPSTREAM_TESTS ENABLE_EMAIL_DELIVERY=false python
  scripts/verify_codex_0149_assistant_output_history.py`.
- Result: FAILED — fixed terminal result
  `VERIFY_CODEX_0149_ASSISTANT_HISTORY_BASE_FAILED code=unexpected_other`.
- Gateway progression `200,200,400`: NOT ESTABLISHED.
- Full-image and resumed-crop wire predicates: NOT ESTABLISHED.
- Assistant-history projection and expected rejection: NOT ESTABLISHED.
- Fake Local two-request lifecycle: NOT ESTABLISHED.
- Rejected-turn no-side-effect proof: NOT ESTABLISHED.
- No second reproduction was run.

## Local verification

- `python -m pytest tests/unit/test_codex_0149_assistant_output_history.py -q`: PASSED — 61 tests.
- `python -m pytest tests/unit/test_oap_governance.py -q`: PASSED — 8 tests.
- `python -m py_compile scripts/verify_codex_0149_assistant_output_history.py tests/unit/test_codex_0149_assistant_output_history.py`: PASSED.
- `ruff check scripts/verify_codex_0149_assistant_output_history.py tests/unit/test_codex_0149_assistant_output_history.py`: PASSED.
- `ruff format --check scripts/verify_codex_0149_assistant_output_history.py tests/unit/test_codex_0149_assistant_output_history.py`: PASSED.
- `git diff --check`: PASSED.
- Exact allowed-path proof: PASSED — implementation commit changed only the
  two allowed Python paths plus `oap/active` and the unchanged 161-e order.
- Report collision check: PASSED — no 161-e report existed before publication.
- Exact package preflight: PASSED.
- One real reproduction: FAILED with the fixed safe terminal result above.

## GitHub CI / required checks

- Check state observed for implementation head `2d67a2c8d5cd5c0c5831fb45a09cac4c9522bc4b`: all ten required checks SUCCESS.
- `Unit, lint, and migration head`: SUCCESS.
- `Analyze (javascript-typescript)`: SUCCESS.
- `Analyze Python`: SUCCESS.
- `Analyze (python)`: SUCCESS.
- `PostgreSQL integration tests`: SUCCESS.
- `OpenAI-compatible E2E tests`: SUCCESS.
- `Playwright browser smoke`: SUCCESS.
- `Docker Compose smoke`: SUCCESS.
- `Documentation hygiene`: SUCCESS.
- `CodeQL`: SUCCESS.
- All required checks green for the implementation head at report drafting: yes.
- Report-only commit may trigger fresh checks: strategic model must verify the
  SELF commit without rewriting this report.

## Documentation

Documentation checked, no update needed because this round changes only
verifier provenance and makes no implemented compatibility claim.

## Safety and scope confirmations

- Unrelated files changed: no.
- Production secrets accessed: no.
- Production systems accessed: no.
- Real upstream/provider calls: no.
- Real email: no.
- Production Gateway behavior changed: no.
- Prompt, completion, assistant text, reasoning, media, request/response
  bodies, headers, credentials, signatures, endpoints, database URLs, private
  paths, package-manager output, and arbitrary errors retained in evidence: no.
- Required evidence not established: yes — the single reproduction terminated
  before emitting accepted scenario evidence; no retry or rerun was allowed.
- Scope deviation: no.
- Extra PR created for same numeric objective: NO.
- PR merged by coding agent: NO.
- Activated order and `oap/active` edited by coding agent: NO.
- Report-publication commit changes only this report file: yes.

## Known limitations / blockers

The exact provenance contract passed, but the one authorized pre-fix
reproduction ended with the fixed safe `unexpected_other` terminal result before
the required Gateway/Local acceptance evidence was available. The verifier
does not expose arbitrary failure details under the privacy boundary. A future
continuation must independently decide how to diagnose or repair that bounded
verifier failure; this round cannot rerun or mutate it.

PREFX-PROVENANCE-ACCEPTED = YES
PREFX-REPRODUCTION-ACCEPTED = NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO

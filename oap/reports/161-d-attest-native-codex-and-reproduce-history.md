# OAP Coding-Agent Report — 161-d

## Work order

- Identifier: 161-d
- Work-order file: `oap/orders/161-d-attest-native-codex-and-reproduce-history.md`
- Numeric objective: 161
- PR mode: `AMENDED_EXISTING_PR`

## Status

FAILED

## Executive summary

The verifier now attests the exact task-local `@openai/codex@0.149.0` root
launcher and the source-selected Linux x64 native executable through bounded,
fail-closed package, lockfile, path, digest, mode, size, and version checks.
Synthetic topology and failure coverage passes. The authorized task-local npm
preflight reached the exact public package and failed at the required native
size ceiling: the digest-matching native executable is regular, non-symlinked,
and executable, but its size class is oversized relative to the explicit
128 MiB maximum in 161-d. The bound was not weakened. The one real
zero-retry reproduction was not started.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 298
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/298
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/161-codex-assistant-output-history`
- Starting remote SHA: `b564a33e72c4d2e91ba15133cf26c5df97bba865`
- Implementation head SHA: `e6b2f94b9999dca6aa857706c79d80eff81261e7`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `e6b2f94b9999dca6aa857706c79d80eff81261e7`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes
- Merge performed: NO

## Changes made

- Added one typed provenance attestation for the exact Linux x64 runtime.
- Validated the root manifest, platform alias manifest, npm package-lock v3
  entries, exact `.bin/codex` relative link, launcher digest, native target,
  native digest, executable mode, bounded sizes, and exact version output.
- Kept the launcher as the invoked Codex entrypoint and returned only typed
  internal launcher/native paths.
- Added synthetic positive, topology, lock-integrity, runtime, file-shape,
  digest, version, privacy, and no-broad-search tests.
- Preserved the strategic 161-d order and `oap/active` bytes unchanged.

## Files changed

- `scripts/verify_codex_0149_assistant_output_history.py`
- `tests/unit/test_codex_0149_assistant_output_history.py`
- `oap/active`
- `oap/orders/161-d-attest-native-codex-and-reproduce-history.md`

## Acceptance-criteria evidence

### Provenance and preflight

- Root distribution identity: PASS — `@openai/codex@0.149.0`.
- Root launcher mapping: PASS — `bin.codex = bin/codex.js`.
- Linux x64 optional alias: PASS — `@openai/codex-linux-x64` maps to
  `npm:@openai/codex@0.149.0-linux-x64`.
- Platform distribution identity: PASS — distribution `@openai/codex`, version
  `0.149.0-linux-x64`, OS `linux`, CPU `x64`.
- npm package-lock integrity: PASS — both exact public expected integrity
  values matched.
- Launcher link: PASS — `../@openai/codex/bin/codex.js`.
- Launcher SHA-256: PASS —
  `134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477`.
- Native target: PASS —
  `node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex`.
- Native SHA-256: PASS —
  `bbc3341e44c9ead340ed9570c17be936e37870f570751a941699ffd04d672827`.
- Native file type and mode: PASS — regular, non-symlinked, executable.
- Native size ceiling: FAIL — oversized relative to the required 128 MiB
  maximum, so the verifier stopped before version probes.
- Source pin: PASS — `rust-v0.149.0`, commit
  `758ef40f50c1a458425c7cfbf1eb12cbc07af0b0`, target
  `x86_64-unknown-linux-musl`.
- Pre-fix reproduction: NOT RUN — zero real reproduction runs; the required
  provenance preflight did not complete.

### Reproduction predicates

- Full-image Gateway progression: NOT RUN.
- Resumed crop/history rejection: NOT RUN.
- Fake Local lifecycle and no-side-effect rejection: NOT RUN.
- Provider inference or protected traffic: NOT RUN.

## Local verification

- `python -m py_compile scripts/verify_codex_0149_assistant_output_history.py tests/unit/test_codex_0149_assistant_output_history.py`: PASSED.
- `pytest tests/unit/test_codex_0149_assistant_output_history.py -q`: PASSED — 58 tests.
- `pytest tests/unit/test_oap_governance.py -q`: PASSED — 8 tests.
- `ruff check scripts/verify_codex_0149_assistant_output_history.py tests/unit/test_codex_0149_assistant_output_history.py`: PASSED.
- `ruff format --check scripts/verify_codex_0149_assistant_output_history.py tests/unit/test_codex_0149_assistant_output_history.py`: PASSED.
- `git diff --check`: PASSED.
- Exact allowed-path proof: PASSED — implementation commit changed only the
  two allowed Python paths plus `oap/active` and the unchanged 161-d order.
- Report collision check: PASSED — no 161-d report existed before publication.
- Task-local npm provenance preflight: FAILED — fixed safe code
  `codex_native_invalid`, caused by the required native size ceiling.
- Initial system-Python pytest collection: BLOCKED — missing `structlog`;
  isolated development environment was installed and the targeted suites
  then passed as recorded above.

## GitHub CI / required checks

- Check state observed for implementation head `e6b2f94b9999dca6aa857706c79d80eff81261e7`: all ten required checks SUCCESS.
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

## Local setup / dependencies

- Installed the repository development dependencies in an isolated temporary
  environment because the system Python was externally managed and lacked
  `structlog`.
- Performed no apt-based PostgreSQL setup and no production setup.
- Performed task-local npm installation only for the bounded provenance
  preflight; package-manager output was not retained.

## Documentation

Documentation checked, no update needed because this round changes only
verifier provenance and makes no implemented compatibility claim.

## Safety and scope confirmations

- Unrelated files changed: no.
- Production secrets accessed: no.
- Production systems accessed: no.
- Real upstream/provider calls: no.
- Real email: no.
- Gateway, fake Local, and fake provider reproduction traffic: no; reproduction
  was not started.
- Prompt, completion, assistant text, image data, request/response bodies,
  headers, credentials, signatures, endpoints, database URLs, private paths,
  package-manager output, and arbitrary errors retained in evidence: no.
- Required tests skipped/not run: yes — the real reproduction was not run
  because the mandated native size predicate failed; version probes and all
  reproduction predicates are explicitly NOT RUN.
- Scope deviation: no; the native bound was preserved exactly.
- Extra PR created for same numeric objective: NO.
- PR merged by coding agent: NO.
- Activated order and `oap/active` edited by coding agent: NO.
- Report-publication commit changes only this report file: yes.

## Known limitations / blockers

The exact published native artifact has the accepted digest and topology but is
oversized relative to the 161-d 128 MiB maximum. The strategic work order and
the public artifact therefore cannot both satisfy the required preflight. No
reproduction result is claimed. A future continuation must resolve that
contract discrepancy before authorizing another real run.

## Recommended strategic follow-up

Review the explicit 128 MiB native-size ceiling against the exact accepted
`@openai/codex@0.149.0` Linux x64 artifact. This report remains FAILED and
immutable; no code or test mutation was made after the preflight failure.

PREFX-PROVENANCE-ACCEPTED = NO
PREFX-REPRODUCTION-ACCEPTED = NO
IMPLEMENTED = NO
TESTED = NO
EXACT-CODEX-0.149-FAKE-ACCEPTED = NO
LOCAL-CROSS-CONTRACT-ACCEPTED = NO
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO

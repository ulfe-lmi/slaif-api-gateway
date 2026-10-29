# OAP Coding-Agent Report — 205-a

## Work order
- Identifier: 205-a
- Work-order file: `oap/orders/205-a-cli-field-workflow-qualification.md`
  (committed unchanged; sha256
  `fbe45f7760041744af0a822fd8e776803a161a8760ae65ba7f94a8e5b4763886`)
- `oap/active` pointer: value `205-a` (5 bytes, no trailing newline),
  committed unchanged; sha256
  `e032abe21bfa4e8f2e5b4748dd0e0f228110fc6ae6939972c48f7872dcba8b68`
- Numeric objective: 205
- PR mode: CREATED_NEW_PR

## Status
PARTIAL

## Executive summary
Qualified the installed `slaif-gateway` console for order section 12
outcomes 1, 2, 3, 4, and 6 through subprocess CLI invocations on an owned,
payload-verified installation (wheel of accepted source
`5e59a023154bfebc998ef4e0a7089a3151fda0e2`) against an owned labeled
PostgreSQL 16 container with a loopback synthetic SMTP sink. The final
byte-matched module run is 6/6 PASS, 0 skip (outcomes 1-4, 6 plus the
installed-identity DoD0 acceptance check). Outcomes 5, 7, 8, 9, 10, 11 and
the runtime-configuration (`config show`) evidence are NOT executed and
remain mandatory. A confirmed NEW CLI privacy gap (credential-shaped
numeric input echoed completely in `set-lazy-throttling` usage stderr,
exit 2, per independent ROOT installed probes) requires product edits that
active 205-a does not permit; it is reported here, unfixed, and deferred to
the root-reserved same-PR 205-b continuation. No product/runtime/schema/
migration/settings/CI byte was changed; no merge; no auto-merge.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 361
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/361
- PR state at report time: OPEN
- Base branch: `main` at `5e59a023154bfebc998ef4e0a7089a3151fda0e2`
- Head branch: `oap/205-cli-field-workflow-qualification`
- Starting remote SHA: `5e59a023154bfebc998ef4e0a7089a3151fda0e2`
- Implementation head SHA: `142d9089fe54fad5101e02b711b6523b9f75b4c2`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `7d26ae7774a5ebcab93745024f4ce7f4950e560e` — order + active +
    qualification module + fixture README + verification record (5 files)
  - `142d9089fe54fad5101e02b711b6523b9f75b4c2` — `docs/verification/README.md`
    navigation index entry (1 file)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes (#361, the unique objective-205 PR)
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
1. `oap/orders/205-a-cli-field-workflow-qualification.md` + `oap/active` —
   committed unchanged (byte hashes above verified against the staged
   objects before committing).
2. `tests/integration/test_cli_field_installed_workflow.py` (new, bounded,
   requirement-indexed) — owned session fixture: payload-verified wheel
   reuse or fresh build with exact installed-payload verification and
   ACTUAL wheel SHA recorded; shallow-safe pinned-source fetch; per-run
   unique labeled PostgreSQL 16 container (loopback-only port, tmpfs data
   dir, ownership/labels/tmpfs inspected before migrations, exact-ID
   removal in teardown after label re-check); scrubbed-subprocess CLI
   invocation from an owned operator directory outside the checkout;
   per-argument safe transcript projection with known-secret substitution;
   loopback SMTP sink. Executed outcomes: DoD0 installed identity; DoD1
   lookup/bounded paging + full-bearer refusal; DoD2 effective policy +
   route explanation; DoD3 institution/owner/cohort record operations with
   duplicate/refusal/conflict negatives; DoD4 exact student/beta + two chat
   clones (dry-run plans, one secure channel per execute, canonical export
   parity incl. nontrivial Codex/Responses pin, inheritance columns,
   zero copied usage/ownership, source unchanged, exact-repeat dedup,
   stale/unknown-field refusals, deny-all providers); DoD6 rates + bounded
   lazy configuration (actual ceilings, overbound/unknown-mode refusals,
   reject/clear) + exact-37 cohort batch (cohort plan, stale refusal after
   installed new-member create with zero changes/audits, explicit UUID
   re-review, exact 37 audits). Draft (not wired): `ProviderMock` /
   `GatewayServer` helpers for outcomes 5-11.
3. `tests/fixtures/cli_field_workflow/README.md` (new) — fixture
   provenance, ownership, identity, IO substitutions, limitations,
   reproducible invocation.
4. `docs/verification/2026-10-29-cli-field-installed-workflow.md` (new) —
   honest PARTIAL per-outcome verification record with JUnit chronology,
   ROOT evidence attribution, and the 205-b scope boundary.
5. `docs/verification/README.md` — standard newest-first navigation entry
   (required by `scripts/check_documentation.py`).

No product, runtime, schema, migration, model, settings/default,
dependency/lockfile, CI/workflow, provider, acceptance/permission,
accounting, replay, worker, auth, UI, or prior test/OAP order/report byte
was changed.

## Files changed
- `oap/orders/205-a-cli-field-workflow-qualification.md` (new, unchanged)
- `oap/active` (`204-c` -> `205-a`, 5 bytes, no newline)
- `tests/integration/test_cli_field_installed_workflow.py` (new)
- `tests/fixtures/cli_field_workflow/README.md` (new)
- `docs/verification/2026-10-29-cli-field-installed-workflow.md` (new)
- `docs/verification/README.md` (+9-line navigation entry)

## Acceptance-criteria evidence (order section 12, eleven outcomes)

Final module run: `205a-final2` JUnit (2026-10-29T13:55Z), 6 tests,
0 failures, 0 errors, 0 skipped, 216.98 s, pytest exit 0. This is the only
run whose test bytes equal the committed test file (the single delta after
the prior green `205a-final` run was removal of one unused local
assignment — non-behavioral ruff hygiene).

| # | Outcome | Result | Evidence |
|---|---------|--------|----------|
| 1 | Identities: list/show by UUID/public-ID/exact owner email, bounded paging, full-bearer refusal without echo | EXECUTED PASSED | `test_dod1_lookup_and_bounded_paging` |
| 2 | Effective policy + route explanation (configured vs inherited sources, unlimited vs inherited limits, allow-list/enabled-route intersection) | EXECUTED PASSED | `test_dod2_effective_policy_and_route_explanation` |
| 3 | Record operations: institution/owner/cohort create/list/show once, duplicate refusal, owner move preservation, cohort edit omission/clear, bad-UUID/no-reason/conflict negatives | EXECUTED PASSED | `test_dod3_record_operations` |
| 4 | Exact student/beta + TWO chat clones (parity incl. nontrivial pin, inheritance, dedup, stale/unknown-field refusal, deny-all providers) | EXECUTED PASSED | `test_dod4_exact_student_beta_and_chat_clones` |
| 5 | Discovery grant + real filtered `GET /v1/models` through installed gateway | UNPROVEN — NOT EXECUTED | no gateway process yet (205-b) |
| 6 | Rates, bounded lazy, exact-37 batch (stale refusal, UUID re-review, exact audits) | EXECUTED PASSED | `test_dod6_rates_lazy_and_exact37_batch` |
| 7 | Two configured completion services (`providers add`, disabled, zero retries) | UNPROVEN — NOT EXECUTED | 205-b |
| 8 | Explicit activation + stable route edit | UNPROVEN — NOT EXECUTED | 205-b |
| 9 | One-time delivery lifecycle (real loopback SMTP send, consumption, safe retries) | UNPROVEN — NOT EXECUTED | sink armed, flow not in module (205-b) |
| 10 | Gateway-recorded failure investigations | UNPROVEN — NOT EXECUTED | no gateway/diagnostics arming yet (205-b) |
| 11 | Reviewed replay maintenance (`codex replay inspect/extend`) | UNPROVEN — NOT EXECUTED | 205-b |

Additional order requirement — `config show --json`/text + invalid-Settings
no-echo probe: UNPROVEN — NOT EXECUTED (205-b).

## JUnit chronology (overlapping slice runs; never summed)

| Artifact (UTC 2026-10-29) | tests | failures | failing cases |
|---|---|---|---|
| `205a-slice1` 12:45 | 4 | 0 | — |
| `205a-slice2` 12:53 | 6 | 2 | DoD4, DoD6 |
| `205a-slice3` 13:04 | 6 | 2 | DoD4, DoD6 |
| `205a-slice4` 13:16 | 6 | 2 | DoD4, DoD6 |
| `205a-slice5` 13:21 | 6 | 2 | DoD4, DoD6 |
| `205a-slice6` 13:25 | 6 | 2 | DoD4, DoD6 |
| `205a-slice7` 13:32 | 6 | 2 | DoD4, DoD6 |
| `205a-slice8` 13:37 | 6 | 1 | DoD6 |
| `205a-slice9` 13:45 | 6 | 1 | DoD6 (stale-batch oracle: installed boundary reports `key_batch_stale`, not generic `command_failed`) |
| `205a-final` 13:50 | 6 | 0 | — |
| `205a-final2` 13:55 | 6 | 0 | — (byte-matched final) |

Intermediate failures were draft-iteration harness/oracle corrections in
the NEW test file (seed field fidelity, clone source fixtures, metadata
column names, error-code mapping, lazy stored-state assertions); each was
corrected in the test file and re-run. They are not product failures and
are not summed as unique cases. Zero skips in every run.

## Installation identity (executed)
- Source: `5e59a023154bfebc998ef4e0a7089a3151fda0e2` (remote `main`);
  pinned shallow-safely in an owned pristine archive.
- Selected wheel: `slaif_api_gateway-0.1.0-py3-none-any.whl`, actual
  SHA256 `5c5bbdb405c7b84f4434a3cfc28f6c15cae2c4947f61d32540149e61b3f6ec55`;
  installed payload file set verified exactly against the selected wheel
  payload; the wheel is a wheel of the accepted product commit, and this
  report/test-only head is documented as such.
- Owned venv: `/tmp/slaif205/venv2` (Python 3.12.15); console
  `/tmp/slaif205/venv2/bin/slaif-gateway`; package file
  `/tmp/slaif205/venv2/lib/python3.12/site-packages/slaif_gateway/__init__.py`
  (asserted inside the venv on every run by DoD0).
- Migrations from the pristine pinned source to `0026` head: 33 public
  tables + `request_diagnostics` asserted before seeding.
- Owned PostgreSQL 16 container per run: unique name `slaif205a-<token>`,
  labels incl. `slaif205a.order=205-a`, loopback-only port, tmpfs data dir;
  verified after the final run: NO container with label
  `slaif205a.order=205-a` remains (exact-ID removal after label re-check).
- Generated credentials: random, memory/0600-only, substituted/masked in
  every retained projection; retained artifacts carry booleans/hashes only.
  No real OpenAI/OpenRouter, real client, real SMTP, or Redis.

## ROOT independent evidence (root runs — credited separately from the
## agent pytest evidence above)
- `205-qualification-baseline.json` — 466 product paths / 1724 non-allowed
  paths baseline of the accepted tree (order-cited).
- `205-installed-lazy-numeric-canary-probe.json` — actual installed CLI:
  both `set-lazy-throttling` numeric flags echo a complete generated
  credential-shaped canary in usage stderr, exit 2 (boolean-only receipt).
- `205-installed-new-numeric-surface-canary-probe.json` — actual installed
  CLI: 17 argument positions across the SELECTED new/extended
  lookup/clone/lazy/provider/route/replay families echo complete generated
  credential-shaped values, all exit 2 (boolean metadata only). Bounded
  probe of the selected families; NOT a blanket legacy-CLI audit claim.
- `205-numeric-privacy-scope-decision.json` — root scope decision reserving
  the narrow 205-b numeric-parsing fix (preserving retry-0/offset-0/signed
  priority/None, existing validators, and all eleven outcomes) on the same
  205 PR.
- Root-verified installation: 432 application files byte-identical to
  accepted source `5e59a02` (only 4 empty `.gitkeep` placeholders omitted);
  root enforced private (0600) creation for generated fixture credentials —
  the final fixture asserts 0600 for its password file.
- Root review aids: `/tmp/slaif205-root/early-installed-workflow-review.md`
  (items 1-9), `/tmp/slaif205-root/clone-batch-slice-review.md`, source
  command map `205-cli-command-planning-checkpoint-20261029.json`.

## Product scope boundary (deferred to same-PR 205-b)
The confirmed NEW CLI privacy gap (credential-shaped numeric input echoed
completely before the command body runs) requires product edits, which
active 205-a explicitly does not permit; no product byte was touched. The
ordinary usage-error law itself (native Typer `BadParameter` -> exit 2,
stderr, no JSON payload, even with `--json`) is documented 197 behavior:
the module asserts the fixed refusal and unchanged state, and does NOT
treat non-JSON usage output alone as a defect or weaken actual bounds.

## Local verification
- `env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app NO_COLOR=1 /tmp/slaif192-coding-venv/bin/python -m pytest tests/integration/test_cli_field_installed_workflow.py -p no:cacheprovider -q --junitxml=/tmp/slaif205/205a-final2.xml`: PASSED — exit 0, 6 tests, 0 failures, 0 errors, 0 skipped (JUnit authoritative; repository addopts suppress the console summary)
- `python -m ruff check tests/integration/test_cli_field_installed_workflow.py`: PASSED (clean)
- `git diff --check`: PASSED (clean)
- `python scripts/check_documentation.py`: PASSED (`DOCUMENTATION_CHECK=OK files=132`; required the README navigation entry committed in `142d908`)
- `python -m pytest tests/unit/test_oap_governance.py`: PASSED — 9 tests, 0 failures, 0 skipped, exit 0
- Container cleanup after final run: verified — no labeled `slaif205a.order=205-a` container remains

## GitHub CI / required checks
- Check state observed for implementation head `142d908`: NOT OBSERVED at
  report drafting (freshly pushed; per the order, no redundant wait on IMPL
  checks that SELF supersedes)
- All required checks green for the implementation head at report drafting: no
- Report-only commit may trigger fresh checks: strategic model must verify
  the `SELF` commit without rewriting this report

## Local setup / dependencies
- Packages/tools/services: owned Python 3.12 venv (`/tmp/slaif205/venv2`)
  with the built wheel + package dependencies; Docker (owned PostgreSQL 16
  container only); no apt/system mutation
- `sudo`-level setup performed: none
- Durable setup changes committed/documented: none (owned /tmp artifacts
  only)

## Documentation
Documentation updated: docs/verification/2026-10-29-cli-field-installed-workflow.md, tests/fixtures/cli_field_workflow/README.md, docs/verification/README.md
- The order's broader documentation duties (cli-reference,
  cli-field-administration, deployment, full operator transcripts for all
  eleven outcomes) are NOT complete; they accompany the executed evidence
  in the same-PR 205-b continuation.

## Safety and scope confirmations
- Unrelated files changed: no (only the six paths listed; protected
  untracked `CODEX-SESSIONS.md` / `codex.sh` preserved uncommitted at their
  verified hashes; ignored catalogs/worktrees untouched)
- Production secrets accessed: no
- Production systems accessed: no
- Required tests skipped/not run: yes — outcomes 5, 7, 8, 9, 10, 11 and the
  config-show evidence are not implemented/executed yet (see Status and
  Known limitations); no test was skipped within the executed module (0
  skips in every run)
- Scope deviation: no — the numeric-echo gap is a reported product
  discovery handled by the order's explicit PARTIAL handoff path, not an
  edit outside scope
- Extra PR created for same numeric objective: NO (single PR #361)
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO (committed
  byte-unchanged)
- Report-publication commit changes only this report file: yes (verified via
  staged diff before committing)

## Known limitations / blockers
1. Outcomes 5, 7, 8, 9, 10, 11 and the runtime-configuration evidence are
   UNPROVEN — not executed. The provider-mock/gateway-server helpers are
   drafted in the module but not wired; the SMTP sink is armed but the
   one-time delivery lifecycle is not yet exercised. ALL ELEVEN remain
   mandatory and unmet for objective completion.
2. Confirmed NEW CLI privacy gap (credential-shaped numeric input echoed in
   usage stderr; root probes: 2 `set-lazy-throttling` flags + 17 positions
   across the selected new/extended families) is unresolved by design of
   this handoff and requires the root-reserved 205-b product fix.
3. No measured wait/admission performance claim; configuration
   qualification only. No real provider/client/mail/Redis anywhere.
4. This is fictional owned-fixture qualification, not production,
   release, security, or compliance certification.

## Recommended strategic follow-up
Activate bounded 205-b on the same PR #361 carrying the narrow numeric
parsing fix (per `205-numeric-privacy-scope-decision.json`) plus completion
of outcomes 5, 7-11, the config-show evidence, and the remaining operator
documentation, then the final fresh-installation full-module run.

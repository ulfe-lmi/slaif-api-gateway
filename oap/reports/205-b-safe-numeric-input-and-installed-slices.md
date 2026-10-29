# OAP Coding-Agent Report — 205-b

## Work order
- Identifier: 205-b
- Work-order file: `oap/orders/205-b-safe-numeric-input-and-installed-slices.md`
  (committed unchanged in `420fb8f`; sha256
  `bba137e1824441fbf85493d93838e70d1be996d0c34675423ce455a97a0cd1db`)
- `oap/active` pointer: value `205-b` (5 bytes, no trailing newline),
  committed unchanged in `420fb8f`; sha256
  `0c113a44f766d07675aecea8b248619077809e28c7381ea0dadd376f07cd41e6`
- Numeric objective: 205
- PR mode: CONTINUE_EXISTING_PR (unique PR #361)

## Status
PARTIAL

## Executive summary
Executed the bounded 205-b round on the unique objective-205 PR #361:
(1) fixed the confirmed no-echo numeric CLI defect with one shared
conversion helper applied at the 17 observed positions across the five
allowed CLI surfaces; (2) added the new boundary unit module
(`tests/unit/test_cli_numeric_privacy.py`, 110 cases) and verified the
seven affected existing CLI unit files unchanged (136 PASS); (3)
re-pinned the installed-CLI qualifier to the fixed source commit
`420fb8f`, built an ACTUAL wheel from that committed source into a
fresh owned Python 3.12.15 venv, and re-qualified the first-six-case
slice (outcomes 1-4 and 6 plus the DoD0 installed-identity acceptance)
6/6 PASS, 0 skip, against an owned labeled PostgreSQL 16 container;
(4) after CI on the implementation head exposed a TEST-side
terminal-renderer oracle problem in the new module (76 of 110 cases
under the GHA colored narrow terminal), repaired it inside the allowed
test file using the established project renderer-stable pattern — no
product message or behavior changed. Outcomes 5, 7, 8, 9, 10, 11, the
`config show` evidence, persisted safe requirement-indexed operator
transcript export, and the final fresh-installation all-eleven run are
NOT executed and remain mandatory; they are carried forward to later
same-PR 205 suffixes. All 205-a order/report bytes are immutable. No
merge, no auto-merge.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 361
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/361
- PR state at report time: OPEN (MERGEABLE)
- Base branch: `main` at `5e59a023154bfebc998ef4e0a7089a3151fda0e2`
- Head branch: `oap/205-cli-field-workflow-qualification`
- Starting remote SHA: `5e59a023154bfebc998ef4e0a7089a3151fda0e2`
- Implementation head SHA: `0bd5b88a435daa06e939d0709fd361e75b850659`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `420fb8f6d9377f569d126d08f4c9e4146fc7250b` — no-echo numeric CLI
    input: shared conversion helper + 17 bounded positions (5 CLI files)
    + unchanged 205-b order + `oap/active` + new unit module (8 files)
  - `0e4c22994e689524cd03e4f1ae8f991293ffbf20` — pin qualifier to the
    fixed source (`SOURCE_SHA` -> `420fb8f`; stale-venv installed-payload
    gate; wheel-extract reuse; scrubbed setup env) + 4 doc files (5 files)
  - `99989fed9bca7dc33d58b44fde362f11b3207d62` — renderer-stable terminal
    in the numeric privacy unit module (1 file, test-only)
  - `0bd5b88a435daa06e939d0709fd361e75b850659` — record the CI renderer
    chronology in the verification record (1 file, docs-only)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes (#361, the unique objective-205 PR)
- Merge performed: NO

## Changes made
1. `app/slaif_gateway/cli/common.py` — new `parse_int_option(...)`:
   fixed no-echo whole-number conversion mirroring the installed
   Typer/Click `int` semantics exactly (same int payload for every
   previously accepted value); invalid input (non-numeric text, floats,
   bool-like words, blanks, recognized credential shapes, over-limit
   digit strings) fails with the fixed message `<option> must be a
   whole number` — naming only the option, never the value — before any
   database, provider, queue, or SMTP access.
2. The 17 observed positions: `app/slaif_gateway/cli/keys.py` (clone
   `--validity-duration-seconds`; list `--limit`/`--offset`;
   `set-lazy-throttling` `--max-wait-seconds`/`--max-waiting-requests`),
   `app/slaif_gateway/cli/providers.py` (add/update
   `--timeout-seconds`/`--max-retries`), `app/slaif_gateway/cli/routes.py`
   (update-only: `--codex-context-window-tokens`,
   `--codex-default-max-output-tokens`, `--codex-max-output-tokens`,
   `--media-image-tokens`, `--media-video-tokens`,
   `--media-video-frames`, `--priority`; `add --priority` untouched),
   `app/slaif_gateway/cli/codex_replay.py` (extend `--ttl-seconds`).
   Flag spellings/defaults/help, omission-vs-explicit semantics, existing
   domain constraints/ceilings, mixed-mode/clear guards, services,
   permissions, audit atomicity, and replay authority are unchanged.
3. `tests/unit/test_cli_numeric_privacy.py` (new in `420fb8f`;
   renderer-stable repair in `99989fe`) — 110 cases: 17 canary positions
   (fixed refusal, complete canary absent from stdout/stderr/logs, no
   traceback, no operation-layer reach), 17x4 invalid-shape refusals
   with boolean-only failure representations and DEBUG-level caplog
   absence, 8 valid payload controls (int types, explicit-0 vs omitted
   `None`, signed route priority, bounded-lookahead paging), and 17
   shared-helper Click-parity/fixed-error cases.
4. `tests/integration/test_cli_field_installed_workflow.py` (bounded,
   test-only) — `SOURCE_SHA` -> `420fb8f`; a previously reused venv is
   rejected and replaced when its installed payload differs from the
   SELECTED wheel; wheel-extraction dir safely reusable on the
   stale-candidate -> fresh-build path; setup subprocesses (build venv,
   `python -m build`, fresh-venv creation, `pip install`) run with a
   scrubbed environment (no inherited `PYTHONPATH`) and neutral `pip`
   cwd so the source-tree egg-info cannot make pip treat the same-version
   wheel as already installed.
5. Docs: `tests/fixtures/cli_field_workflow/README.md`,
   `docs/verification/2026-10-29-cli-field-installed-workflow.md` (205-b
   section incl. CI renderer chronology), `docs/verification/README.md`
   (205 entry), `docs/cli-reference.md` (bounded no-echo numeric section).
6. `oap/orders/205-b-safe-numeric-input-and-installed-slices.md` +
   `oap/active` — committed unchanged (byte hashes above verified against
   the staged objects before committing).

No schema, migration, key-policy, settings/default, dependency/lockfile,
CI/workflow, profile, provider, accounting, replay, worker, auth, UI, or
prior test/OAP order/report byte was changed. `99989fe` and `0bd5b88`
change no product byte.

## Product fix semantics and bounded malformed-value error difference
- Conversion happens at the CLI boundary BEFORE DB/service mutation; it
  distinguishes `0` from omitted (`None`); positive-only fields keep the
  EXISTING domain constraints/ceilings; signed route priority keeps
  0/negative values; no invalid input is silently coerced to a default.
- Bounded error difference (documented in `docs/cli-reference.md`):

| Command / option(s) | Channel | Exit |
|---|---|---|
| `keys clone --validity-duration-seconds` | JSON `{"error":{"code":"invalid_parameter",...}}` inside the command's existing safe error handler | 1 |
| all other 16 positions | native Typer usage refusal, fixed message, stderr, no JSON payload (even with `--json`) | 2 |

- Missing/unknown-option errors and all other error channels are
  unchanged; this is not a promise that all Typer usage errors become
  JSON. The ordinary usage-error law itself (exit 2, stderr, no JSON,
  even with `--json`) is documented 197 behavior and is asserted, not
  treated as a defect.

## Acceptance-criteria evidence (order section 12, eleven outcomes)

Installed first-six-case slice re-qualified on the fixed wheel: JUnit
`205b-installed-slice` (2026-10-29T14:39:06Z), 6 tests, 0 failures, 0
errors, 0 skipped, 242.46 s, pytest exit 0.

| # | Outcome | Result | Evidence |
|---|---------|--------|----------|
| 1 | Identities: list/show by UUID/public-ID/exact owner email, bounded paging, full-bearer refusal without echo | EXECUTED PASSED (re-qualified on fixed wheel) | `test_dod1_lookup_and_bounded_paging` |
| 2 | Effective policy + route explanation | EXECUTED PASSED (re-qualified) | `test_dod2_effective_policy_and_route_explanation` |
| 3 | Record operations (institution/owner/cohort, duplicates, refusals, conflicts) | EXECUTED PASSED (re-qualified) | `test_dod3_record_operations` |
| 4 | Exact student/beta + TWO chat clones (parity, dedup, stale/unknown-field refusals) | EXECUTED PASSED (re-qualified) | `test_dod4_exact_student_beta_and_chat_clones` |
| 5 | Discovery grant + real filtered `GET /v1/models` through installed gateway | UNPROVEN — NOT EXECUTED | carried forward to later same-PR suffix |
| 6 | Rates, bounded lazy, exact-37 batch | EXECUTED PASSED (re-qualified) | `test_dod6_rates_lazy_and_exact37_batch` |
| 7 | Two configured completion services (`providers add`, disabled, zero retries) | UNPROVEN — NOT EXECUTED | carried forward |
| 8 | Explicit activation + stable route edit | UNPROVEN — NOT EXECUTED | carried forward |
| 9 | One-time delivery lifecycle (loopback SMTP send, consumption, safe retries) | UNPROVEN — NOT EXECUTED | sink armed, flow not wired; carried forward |
| 10 | Gateway-recorded failure investigations | UNPROVEN — NOT EXECUTED | carried forward |
| 11 | Reviewed replay maintenance (`codex replay inspect/extend`) | UNPROVEN — NOT EXECUTED | carried forward |

Additional order requirement — `config show --json`/text + invalid-Settings
no-echo probe: UNPROVEN — NOT EXECUTED (carried forward).

DoD0 installed-identity acceptance: EXECUTED PASSED in the slice
(`test_dod0_installed_identity`).

## JUnit evidence (agent pytest; overlapping runs never summed)

| Artifact (UTC 2026-10-29) | scope | result | sha256 |
|---|---|---|---|
| `205b-numeric-privacy-2` 14:32 | NEW module, 17 positions + controls | 110 PASS, 0 fail/skip, 33.13 s | `33e7d67b7c59267307d18f7117ecbcc8f67c90f40ec412e3c910691794385715` |
| `205b-ci-repro` 15:02 | NEW module under forced-color narrow CI-like terminal (pre-repair repro) | 76 FAIL / 34 PASS, 0 skip | `bed28b5cedece4d28f514e97dee0533c718ea0043f681b99b96602159962d9f0` |
| `205b-ci-fixed` 15:03 | NEW module under forced-color narrow CI-like terminal (post-repair) | 110 PASS, 0 fail/skip, 28.20 s | `035b279f4994038523bd8e9133f339f3963680025660574bcaf0e85a51aa29f0` |
| `205b-numeric-privacy-3` 15:04 | NEW module, normal NO_COLOR local env (post-repair) | 110 PASS, 0 fail/skip, 28.24 s | `aeaf706f350a8bd4a2b7e1fbcb0f0bbb5a9155f9da0fb1bf007c9dcd604d76bb` |
| `205b-existing-cli` 14:20 | 7 affected existing CLI unit files (unchanged bytes) | 136 PASS, 0 fail/skip, 62.79 s | `ab70adace897ca02343c50f42d5eeaa7623a89020b544a2479518aa30c3503c2` |
| `205b-installed-slice` 14:39 | installed first-six-case slice, owned PG 16 | 6 PASS, 0 fail/skip, 242.46 s | `f4d7d6fcf9d471cfa3748bb652b5b509250917ffb8799d02246cfd0bc83b8db3` |
| `205b-governance` 14:53 | `tests/unit/test_oap_governance.py` | 9 PASS, 0 fail/skip | `9a10f6b30bfdc332f64022717779f8d1cbd2ddf2de76d995590db15eca1d24a1` |

The `205b-ci-repro` row is a deliberately preserved failed-run
reproduction (it matches the CI failure count exactly); it is not a pass
and is not summed with the others.

## CI failure chronology (implementation heads, preserved)

- CI run 40892694064 (head `420fb8f`, job 123513442090 "Unit, lint, and
  migration head", 2026-10-29): 76 failed / 6434 passed / 1 skipped in
  172.49 s. ALL 76 failures are in the NEW privacy module: 75
  "fixed option-level refusal message missing" (15 panel-rendered
  positions x 1 canary + 4 invalid shapes) + 1 positive-limit literal
  assertion. Every other job in the run was green. The app renders Click
  usage errors through a rich error panel whose ANSI styling (GHA forces
  terminal color) and width-dependent wrapping broke raw substring
  comparisons; the local NO_COLOR wide-terminal run had passed.
- CI run 40896109400 (head `0e4c229`): same unit job, same 76 failed /
  6434 passed / 1 skipped (162.64 s); other jobs pass/pending.
- Test-only repair `99989fe` (established project renderer-stable
  pattern: `TERM_ENV` COLUMNS=220/NO_COLOR=1 per invocation + ANSI-strip
  /whitespace-normalized fixed-reason comparison; RAW canary/exit/no-op/
  no-echo/caplog assertions intact; no product message/behavior change);
  focused module re-verified 110/110 under the CI-like terminal and the
  normal local env (rows above). No 136-file or installed-six rerun was
  needed for a test-only fix.

## Installation identity (executed)
- Source: `420fb8f6d9377f569d126d08f4c9e4146fc7250b` (the 205-b
  implementation commit), pinned shallow-safely in an owned pristine
  archive. Shallow archival verified in owned scratch (fresh depth-1
  clone of origin lacks the commit; narrow `git fetch --depth 1 origin
  <SHA>`; `git archive` payload tree `1213f89b985f514204821790d79ddb2b24710b76`
  equals the local commit tree; no reset/switch/clean/stash of coding
  state).
- Wheel: `slaif_api_gateway-0.1.0-py3-none-any.whl`, actual selected
  SHA256 `042eb23ac7042d2e77c4af4dca6d80d52f0968a328b33d03c8d0f825c07dad6f`,
  built from that exact committed source. No bit-identical ZIP claim.
- Fresh owned venv: `/tmp/pytest-of-janezp/pytest-1559/slaif205-field0/venv`
  (Python 3.12.15), package in site-packages, outside the checkout,
  `PYTHONPATH` absent. The stale 205-a venv (`/tmp/slaif205/venv2`) was
  rejected by the new installed-payload-vs-selected-wheel gate and
  replaced — a matching path/version alone is never treated as usable.
- ROOT independently verified the fixed installation: all 432
  wheel/source/installed application files match committed `420fb8f`
  (root evidence, not an agent run).
- Schema clarification: at the `0026` migration head the database holds
  34 public tables = 33 product tables (including `request_diagnostics`)
  + `alembic_version`. Objective 205 adds NO new schema, NO key-policy
  migration, and NO migration of any kind; the 0026 full-round upgrade
  distinction of the order is unchanged.

## Failed-run chronology (installed slice, preserved; not passes)
Before the green slice, two earlier attempts each produced 6 setup
ERRORs: (a) `FileExistsError` in the wheel-extraction step on the
stale-candidate -> fresh-build path (fixture needed `exist_ok` on the
owned extraction dir), and (b) the fresh owned venv failing its identity
check because setup subprocesses inherited `PYTHONPATH=app`, making pip
treat the same-version wheel as already installed. Both were
fixture-setup defects corrected in the NEW test file. The original
failed XML/log paths were subsequently REUSED by the green run
(overwritten); the failed-run metadata/hash/cause is preserved in the
root receipt `205-b-setup-and-interim-evidence.json`. No reconstruction
or repeat was performed.

## ROOT independent evidence (root runs — credited as root, not agent pytest)
- `205-b-early-root-helper-probe.json` — source-level helper probe: 8
  Click-parity + 2 omission/default + 8 fixed-error controls (no DB; not
  installed proof).
- `205-b-root-fixed-wheel-installed-identity.json` — fixed installed
  identity: 432 wheel/source/installed app files match committed
  `420fb8f`, Python 3.12.15, outside-checkout with `PYTHONPATH` absent.
- `205-b-root-fixed-installed-numeric-probe.json` — actual installed
  17-position canary probe on the fixed wheel: ALL PASS (fixed numeric
  refusal, nonzero exit, complete canary absent, no traceback, no
  `command_failed`).
- `205-b-installed-slice-evidence.json` — final six-PASS slice receipt
  with actual selected wheel SHA256 and identity facts.
- `205-b-setup-and-interim-evidence.json` — preserved failed first-six
  setup-ERROR metadata/hash/cause and the adjusted 110-PASS unit run.
- Earlier 205-a receipts (`205-installed-lazy-numeric-canary-probe.json`,
  `205-installed-new-numeric-surface-canary-probe.json`,
  `205-numeric-privacy-scope-decision.json`) document the defect and the
  bounded fix scope.

## Local verification
- `env -u DATABASE_URL -u TEST_DATABASE_URL GITHUB_ACTIONS=true TERM=xterm-256color PYTHONPATH=app <venv> -m pytest tests/unit/test_cli_numeric_privacy.py -p no:cacheprovider -q --junitxml=/tmp/slaif205/205b-ci-fixed.xml` (forced-color narrow CI-like terminal): PASSED — exit 0, 110 tests, 0 failures, 0 errors, 0 skipped
- `env -u DATABASE_URL -u TEST_DATABASE_URL PYTHONPATH=app NO_COLOR=1 <venv> -m pytest tests/unit/test_cli_numeric_privacy.py -p no:cacheprovider -q --junitxml=/tmp/slaif205/205b-numeric-privacy-3.xml` (normal local env): PASSED — exit 0, 110 tests, 0 failures, 0 errors, 0 skipped
- Affected existing CLI units (7 files, unchanged): 136 PASS, 0 skip (JUnit `205b-existing-cli`)
- Installed first-six-case slice: 6 PASS, 0 skip (JUnit `205b-installed-slice`)
- `python -m ruff check` (touched files): PASSED (clean)
- `git diff --check`: PASSED (clean)
- `python scripts/check_documentation.py`: PASSED (`DOCUMENTATION_CHECK=OK files=132`)
- `python -m pytest tests/unit/test_oap_governance.py`: PASSED — 9 tests, 0 failures, 0 skipped (JUnit `205b-governance`)
- Container cleanup after the slice: verified — no container with label
  `slaif205a.order=205-a` remains (exact-ID removal after label re-check)
- Generated credentials: random, memory/0600-only, substituted/masked in
  every retained projection; retained artifacts carry booleans/hashes
  only. No real OpenAI/OpenRouter, real client, real SMTP, or Redis.

## GitHub CI / required checks
- Check state observed for implementation head `0bd5b88`: CI run
  40898327893 and CodeQL run 40898328016 IN FLIGHT (not concluded) at
  report drafting; per the order, no redundant wait on IMPL checks that
  SELF supersedes. No pass is inferred from pending state.
- All required checks green for the implementation head at report
  drafting: no
- Report-only commit may trigger fresh checks: strategic model must
  verify the `SELF` commit without rewriting this report

## Local setup / dependencies
- Packages/tools/services: owned Python 3.12 venvs (build venv + fresh
  installed venv under the pytest temp tree) with the built wheel +
  package dependencies; Docker (owned PostgreSQL 16 container only); no
  apt/system mutation
- `sudo`-level setup performed: none
- Durable setup changes committed/documented: none (owned /tmp artifacts
  only)

## Documentation
Documentation updated: docs/verification/2026-10-29-cli-field-installed-workflow.md, tests/fixtures/cli_field_workflow/README.md, docs/verification/README.md, docs/cli-reference.md
- The verification record's 205-b section carries the fix scope/semantics,
  bounded error difference, evidence rows, failed-setup chronology, CI
  renderer chronology, 34-table clarification, root receipts, and the
  carry-forward table. The order's broader documentation duties
  (deployment/cli-field-administration notes, whole-round completion
  prose, full operator transcripts for all eleven outcomes) are NOT
  complete; they accompany the executed evidence in the later same-PR
  continuations.

## Safety and scope confirmations
- Unrelated files changed: no (only the paths listed under Changes made;
  protected untracked `CODEX-SESSIONS.md` / `codex.sh` preserved
  uncommitted at their order-stated hashes
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda` /
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`;
  ignored catalogs/worktrees untouched)
- Production secrets accessed: no
- Production systems accessed: no
- Required tests skipped/not run: yes — outcomes 5, 7, 8, 9, 10, 11 and
  the config-show evidence are not executed yet (see Status and Known
  limitations); no test was skipped within the executed runs (0 skips in
  every JUnit row above)
- Scope deviation: no — the renderer repair stayed inside the allowed
  new test file with the established project pattern; no product,
  framework, or extra path was touched
- Extra PR created for same numeric objective: NO (single PR #361)
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO (committed
  byte-unchanged)
- Report-publication commit changes only this report file: yes (verified
  via staged diff before committing)

## Known limitations / blockers
1. Outcomes 5, 7, 8, 9, 10, 11 and the runtime-configuration
   (`config show`) evidence are UNPROVEN — not executed. The
   provider-mock/gateway-server helpers are drafted in the module but
   not wired; the SMTP sink is armed but the one-time delivery lifecycle
   is not yet exercised. ALL ELEVEN remain mandatory and unmet for
   objective completion.
2. The safe requirement-indexed argv/output/exit projections and run
   identity are IN MEMORY only; no persisted operator transcript file is
   written or exported by the fixture in this round. Persistence is
   carried forward to the next same-PR qualifier; the final fresh
   all-eleven run must export it. This report does not claim any
   persisted transcript exists.
3. The final fresh-installation all-eleven module run has NOT been
   executed; the six executed cases overlap the 205-a outcomes (re-
   qualified on the fixed wheel) and are not summed with the 205-a runs.
4. CI for the final implementation head was in flight at report time;
   the 76-failure history of heads `420fb8f`/`0e4c229` is preserved
   above, and the focused module is verified green under the CI-like
   terminal locally. No pass is claimed for the in-flight run.
5. No measured wait/admission performance claim; configuration
   qualification only. No real provider/client/mail/Redis anywhere.
6. This is fictional owned-fixture qualification, not production,
   release, security, or compliance certification.

## Recommended strategic follow-up
Activate the next bounded same-PR 205 suffix after strategic review:
carry forward outcomes 5, 7-11, the config-show evidence, the persisted
safe requirement-indexed operator transcript export, and the final
fresh-installation all-eleven run on the same unique PR #361.

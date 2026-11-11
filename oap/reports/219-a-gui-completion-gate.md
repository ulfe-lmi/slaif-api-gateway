# 219-a immutable report — whole-GUI completion gate (test/fixture/doc corrections only)

## Identity and activation

- Objective: 219, identifier `219-a` (CREATE_PR); ONE PR #376, branch
  `oap/219-gui-completion-gate`; OPEN at publication, never merged, no
  auto-merge.
- Order: `oap/orders/219-a-gui-completion-gate.md` (29,183 bytes,
  SHA-256 `78cf72bed89e783fe068c002928cf08eac70ecbba12d09530c52dd4364d5d4e7`),
  committed byte-unchanged with the active pointer in
  `07396b0d` (root-authored, bytes immutable).
- Active pointer: `oap/active` = exactly the five bytes `219-a`
  (no trailing newline; SHA-256
  `488e48ad14a54dd4f1c4120834aa06c0f7244422edaa84b50b9e6fcf80493bf9`),
  unchanged.
- Base/remote main: `663c673494d4c0daeb4d5b1269b428ee13277448`
  (merged PR #375 / predecessor objective 218: terminal).
- The ONE exact control `OK` was already consumed and validated by the
  canonical detached control waiter before this execution turn began
  (OAP_CONTROL_OK_RECEIVED handoff). No `control.fifo` read, wait, or
  signal occurred in this turn; no further control wait is armed until
  this report is published and the response OK has been sent.
- Protected untracked local files preserved BY HASH ONLY (never staged,
  never modified): `CODEX-SESSIONS.md`
  (`5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`),
  `codex.sh` (`66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`),
  `uv.lock` (`d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`).

## Publication topology

Implementation head SHA: 00737d176c9e13efee5d6e01f0062f7f0781175c
Report publication commit: SELF

- Three append-only commits over base main `663c6734` (no amend, no
  force-push):
  - `07396b0d` — 219-a: Strategic activation (order + active,
    byte-unchanged, root-authored);
  - `45893daa` — 219-a: whole-GUI field guidance, calibration JSON
    download, visual consolidation (the FROZEN product code for this
    gate; no product file is touched after this commit);
  - `00737d17` (implementation head) — 219-a: whole-GUI completion gate
    (test/fixture/doc corrections only): the new focused unit module,
    the new real-Chromium browser module, the new opt-in installed
    workflow gate, the test-only worker driver error-report seam, the
    fixture corrections, and the documentation updates with real
    evidence.
- This report-only SELF commit has SOLE parent the literal
  implementation head `00737d176c9e13efee5d6e01f0062f7f0781175c` and
  its diff contains ONLY this report file.
- PR #376: https://github.com/ulfe-lmi/slaif-api-gateway/pull/376
  (base `main`, head `oap/219-gui-completion-gate` at
  `00737d176c9e13efee5d6e01f0062f7f0781175c`; title "219-a: whole-GUI
  completion gate (test/fixture/doc corrections only)").
- GitHub checks at publication (2026-11-11 ~09:33Z): "Documentation
  hygiene" SUCCESS; "Unit, lint, and migration head", "Analyze
  Python", "Analyze (javascript-typescript)", "Analyze (python)",
  "PostgreSQL integration tests", "OpenAI-compatible E2E tests",
  "Playwright browser smoke", "Docker Compose smoke" pending. Root
  verifies final-head checks, review, and the guarded merge.

## What this delivers (bounded)

The whole-GUI completion gate for the 218/219 admin surfaces, with
product code FROZEN: every change in the implementation head is test,
fixture, driver-seam, or documentation work, all in this ONE PR.

- **Focused unit module** (NEW
  `tests/unit/test_admin_gui_completion_219.py`, 6 tests): the exact-unit
  calibration JSON projection/serialization law, the safe
  no-store/non-rotating calibration download gates and
  credential/content-alias refusal, the whole-field linked-help render
  audit (real rendered associations, unique IDs, validation recovery,
  no-JS), and the visual-consolidation render contexts.
- **Real-Chromium browser module** (NEW
  `tests/browser/test_admin_gui_completion_219.py`, 5 tests): focused
  real-browser conditional help, keyboard-only, no-JS, and
  desktop/narrow (~420 px) rendered states for the guidance,
  calibration download, and consolidation surfaces (real uvicorn +
  owned PG; no Redis/Celery).
- **Installed workflow gate** (NEW
  `tests/integration/test_gui_parity_installed_workflow.py`, 17 tests,
  opt-in TEST-ONLY flag `RUN_GUI_PARITY_INSTALLED_WORKFLOW=1`): isolated
  wheel built from the checkout and installed into a SEPARATE venv
  (no PYTHONPATH override; product origins verified from the installed
  site-packages), real uvicorn API and real solo Celery worker from the
  installed package, owned PG16/Redis7 (loopback ports, identity-
  verified before use), synthetic provider mock and SMTP sink only.
  Coverage: installed identity receipt; login secret-canary and process
  configuration; key policy configuration round trip; rate limits and
  explanations; reviewed clone; reviewed batch and safe repeat;
  route/provider; content-free diagnostics; replay inspect/extend;
  compatibility; usage/export/pricing/FX; email delivery lifecycle with
  the one-time-secret retry law (retry-eligible only while the secret is
  unconsumed; `confirm_send_test` explicit); accounting operations;
  sealed catalog refresh through the real worker (proposal with
  USD->EUR 0.92 exact-Decimal conversion law, strict import preview,
  refresh-mode collect with server-exported sealed baseline, run
  verify, reviewed two-step superadmin apply with exact warning
  acknowledgements and committed route writes, baseline export
  document, safe-repeat no-op); account list/create/reset with the
  role boundary; calibration JSON download plus same-page confirmed
  template creation; and the negative matrix (unauthorized,
  wrong-CSRF/session/actor, tampered/expired review, validation
  recovery, full-response/log/audit secret canaries — usable full
  gateway keys only, never key names).
- **Test-only worker driver seam**
  (`tests/integration/_catalog_refresh_worker_driver.py`): env-gated
  `SLAIF219_WORKER_ERROR_REPORT` wrapper recording the worker exception
  class/message/traceback (the product task wrapper lawfully collapses
  worker faults to a fixed `internal_error` code; the seam exists so a
  sealed-run failure is diagnosable without weakening product
  behavior).
- **Fixture corrections (root causes, all in the gate test):**
  - private (0700) modes for the fixture workflow dir and custody root
    (the seal-key parent and the custody gate both refuse
    group/other-writable directories);
  - a continuous worker stdout drain after readiness (the 64 KiB pipe
    filled and blocked the solo worker mid-job);
  - per-run reset of the fixture OWN custody subtrees
    (`jobs/`, `proposals/`, `runs/`, `uploads/` inside the fixture's
    own `/tmp/slaif219/installed-workflow/custody` only) so every run
    starts from a documented empty custody;
  - fresh-job wait binding: `test_13` snapshots pre-existing job ids
    and every `_wait_job` skips them — a stale terminal job of the same
    family can never shadow the job the current run created (this was
    the recurring "collect refused / no collect job" failure: the new
    proposal was still active when the test believed it had finished,
    tripping the lawfully enforced one-active-job capacity);
  - refresh-mode collect on the seeded deployment: bootstrap
    collect/apply is lawfully refused on a populated catalog
    (`apply_bootstrap_not_empty`), so the sealed baseline is exported
    from the configured target at collect time per the accepted 217
    legacy rule, and the reviewed apply then lawfully commits.
- **Documentation:** `docs/admin-usability.md`, `docs/configuration.md`,
  `docs/MISSING_GUI_FUNCTIONALITY.md` (status), and the ONE incremental
  `docs/verification/gui-cli-parity.md` evidence section with the real
  commands, exits, counts, and JUnit paths below.

## Evidence (owned local fixtures, honest labels)

All commands ran from the checkout with the existing qualified venv
`/tmp/slaif216-qualification-venv` (Python 3.12.15); every actual
pytest exit was captured immediately to a `.rc` file before any
display command; no masked pipeline status is reported.

1. Focused changed-component unit list — the order's exact command
   (219 module + usability inventory + SLAIF design + record-choices +
   calibration summary service + CLI calibration + OAP governance):
   `env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL
   /tmp/slaif216-qualification-venv/bin/python -m pytest
   tests/unit/test_admin_gui_completion_219.py
   tests/unit/test_admin_usability_inventory.py
   tests/unit/test_admin_slaif_design.py
   tests/unit/test_admin_record_choices.py
   tests/unit/test_calibration_summary_service.py
   tests/unit/test_cli_calibration.py
   tests/unit/test_oap_governance.py -q -p no:cacheprovider`
   — 240/240 passed (per-module: 219 module 6, usability inventory
   124, SLAIF design 12, record-choices 78, calibration summary 6, CLI
   calibration 5, OAP governance 9), actual pytest exit 0,
   2026-11-11 09:00:13Z; JUnit
   `/tmp/slaif219/junit-unitlist-219-final.xml`.
2. Real-Chromium Playwright module (order's exact command):
   `env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL
   /tmp/slaif216-qualification-venv/bin/python -m pytest
   tests/browser/test_admin_gui_completion_219.py -m playwright -q -p
   no:cacheprovider` — 5/5 passed, 0 skipped, actual pytest exit 0,
   2026-11-11 08:06:04Z (product code frozen since 03:03:34Z, so the
   run is final-code evidence); JUnit
   `/tmp/slaif219/junit-browser-219.xml`.
3. Documentation contract/asof/inventory/logo/product-scope/RC2 checks
   (the six modules actually touched by the docs changes): 59 passed,
   actual pytest exit 0, 2026-11-11 09:32:31Z; log
   `/tmp/slaif219/docschecks-final.log`.
4. Scoped Ruff (repo pin E4/E7/E9/F, line-length 100; ruff 0.16.7) over
   the four changed/new Python files (`_catalog_refresh_worker_driver.py`,
   `test_gui_parity_installed_workflow.py`, `test_admin_gui_completion_219.py`
   unit and browser): exit 0. `git diff --check`: clean.
5. THE ONE final installed workflow — the order's exact command:
   `env -u DATABASE_URL -u TEST_DATABASE_URL -u TEST_REDIS_URL
   RUN_GUI_PARITY_INSTALLED_WORKFLOW=1
   /tmp/slaif216-qualification-venv/bin/python -m pytest
   tests/integration/test_gui_parity_installed_workflow.py -q -p
   no:cacheprovider --junit-xml=/tmp/slaif219/junit-installed-workflow.xml`
   — 17/17 passed, 0 skipped, actual pytest exit 0, finished
   2026-11-11 09:32:00Z; JUnit
   `/tmp/slaif219/junit-installed-workflow.xml`.
   Installed identities: wheel
   `slaif_api_gateway-0.1.0-py3-none-any.whl` SHA-256
   `ab7cff488570b6db6db1015e8954c473aca481e3947c24bdcb273441519d8e6b`
   (package version 0.1.0), built from the checkout at source commit
   `00737d176c9e13efee5d6e01f0062f7f0781175c` (tree
   `1e8e7057b94fb52c66442c07e49cda0788b380d4`); API and worker product
   origins verified at run time from the installed venv:
   package `/tmp/slaif219/installed-workflow/venv/lib/python3.12/site-
   packages/slaif_gateway/__init__.py`, worker module
   `/tmp/slaif219/installed-workflow/venv/lib/python3.12/site-
   packages/slaif_gateway/workers/tasks_catalog_refresh.py`. Fixture
   identities: owned PG16 and Redis7 instances (loopback-only ports,
   unique owner labels, created and verified before use, torn down in
   fixture teardown), synthetic `ProviderMock` and `SmtpSink`
   (127.0.0.1), seal key `21`*32 in the fixture workflow dir, custody
   root `/tmp/slaif219/installed-workflow/custody` (private mode).

Debug history (honest): before the final run, focused debug runs
(installed-debug1..17, probe runs) exposed and corrected four fixture
defects — custody/seal parent-directory modes, the worker stdout pipe
block, stale terminal-job shadowing of fresh jobs, and the
bootstrap-on-populated-catalog refusal (corrected to the lawful
refresh flow). The final run above is the single full-workflow
execution against final code; no earlier debug run is claimed as final
evidence.

## Limitations

- Local gate only: this qualification proves the installed
  workflow against owned synthetic fixtures (synthetic provider,
  synthetic SMTP sink, loopback owned PG/Redis). It is NOT a release,
  deployment, production, live-provider, or live-mail claim, and no
  universal-compatibility, invoice-replacement, or release-readiness
  claim follows.
- Operator-only exceptions (full incoming captures remain operator-
  local; host secret generation/mounts, DB migrations, first-admin /
  break-glass, research executables, arbitrary profile files, and
  deployment) remain operator controls, per the order.
- The legacy whole-GUI audit surface beyond this gate's scope remains
  deferred to later objectives (220+), not this PR.

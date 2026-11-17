# OAP 226-b — Final Report (versioned Codex declaration history:
final integration and qualification)

Report publication commit: SELF

## Commit topology

- b activation commit:
  `52a6974c817f70dd4f3f47a44b4615f990cfff36` ("226-b: commit
  root-authored activation bytes (order + active pointer)"), sole
  parent the a SELF
  `3083f7f42e66b8aa84cb4ddd9c49f2f9debfe35e`; committed the
  root-authored order
  `oap/orders/226-b-codex-tool-history-integration.md` and the exact
  `oap/active` = `226-b` pointer unchanged, FIRST.
- a identities re-verified at report time: a implementation
  `d0b9b0c10e24c4f3aaa1ea6fe6e757369f5692e8`; a order SHA256
  `ced7b31d32a5c92adc9ab1342f96bc19bad718ae906789f13c74cb8e58193d09`;
  a report SHA256
  `8b2203bfafbf34711dd496d06a29ca0c86b81837daf009cea183c42e07b49997`
  — both byte-identical to the order's recorded values; neither a
  order nor a report was edited.
- Runtime evolution on the same branch (all primary-authored):
  `867bc0f097fbc3af712f0b37dfc393821880460a` (unqualified runtime
  checkpoint incl. the fifth preset) → `bdf5a7da9ba50030ea30518cff05f617a7d9bc2a`
  (fixed runtime: replay ownership law, ID-less gating, empty-catalog
  facts, codec-refusal accounting seam) → `6a63971e` (formal wiring
  regressions) → `6470e5d9` (placement guard into the shared pure
  preparation) → `ef6fe594` (precise fixed wire codes through the
  prepared-estimate wrapper) → `da03e671` / `ae5774e6` (doc
  consolidation and root doc corrections) →
  `f4723fd76dfc0404268f195efb102ae88ff0acaf` (materialize bound
  per-call namespace in the provider copy: source + 3 focused unit
  regressions) → `f43794e0` (call-identity translation wording).
- Secondary PG qualification, integrated by cherry-pick of ONLY the
  four test-only commits (each touches solely
  `tests/integration/test_codex_tool_history_postgres.py`):
  `50b9f18e3a326a5fbcfa817bd968b99849947127` ← `194f11c1`,
  `2d67555c4ec72e0925e6db1e0acded7892fd6966` ← `d1642b1b`,
  `3a039d0a511487d1664ec8600be393d766439bb4` ← `5c186c9d`,
  `b96ab72247c5df406c99467d7015afbd7960f526` ← `9839d974`.  The
  secondary's copied source commit `23d66f8a` was SKIPPED (the
  original `f4723fd7` is already on the branch; root verified app
  trees identical apart from one comment, Python AST identical).
- `8a831a2b1dcfdad664a9b4816fc684d27cd04b5e`: test-only correction of
  the two stale shipped-preset inventory expectations in
  `tests/unit/test_compatibility_presets.py` (fifth preset
  `codex-0.167.1`); all validation/export/overwrite assertions
  preserved; no runtime or pin changes.
- Implementation head (sole SELF parent):
  `55e7cb0a5e8e5d41336ca8ad9fbf8ccdc0244676` (docs-only final
  evidence record; sole parent `8a831a2b…`, tree
  `4886dc158463a8310f4ea33da819245dd9d19de6`).
- This report: report-only SELF, sole parent = the implementation
  head, sole diff = this file.

## Existing PR state (AMEND_EXISTING_PR)

- PR #386
  https://github.com/ulfe-lmi/slaif-api-gateway/pull/386 — created in
  round a, OPEN at report time, base `main`, branch
  `oap/226-codex-tool-history`, remote head verified exact
  `55e7cb0a5e8e5d41336ca8ad9fbf8ccdc0244676` before this report
  commit.  No second PR was opened; no merge or auto-merge by coding
  agents.  The PR body was updated at the implementation head with
  final behavior, root cause, tests/failures/skips, migration and
  rollback.
- 226-a publication honesty note (per order): the a immutable report
  was committed 16 seconds BEFORE PR #386 creation (17:22:01 versus
  17:22:17 UTC), contrary to the required publication order; that
  sequence is preserved and is not claimed compliant.  This b
  publication describes the already-existing PR #386 and follows the
  protocol (implementation and PR state published before the report).
- Protected untracked files re-verified unchanged at report time:
  `CODEX-SESSIONS.md` SHA256
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
  `codex.sh` SHA256
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
  `uv.lock` SHA256
  `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
  None staged, none committed.

## Exact tested identities

- Client module `codex-0.162-responses-v1`; new operator profile DATA
  `profiles/codex-0.167.1.json`, DATA revision `16`, canonical
  identity digest (loader
  `load_codex_profile_file(...).digest`, not a file checksum)
  `cff9f7b56966eb2068fdbeb203fe04ac32890e34524200372c2d3f2a30e566ed`.
- Migration source `codex-0.167.0` (revision 15) digest
  `9634f95de985d8c06fd0b09af3358ae589a14b828d4d4c357d4f98bcafec6a5d`;
  packaged default `codex_0162.json` (revision 8) digest
  `1d1e5b05587d1a8bf1f90057e43e357b7b3627dc3268ec09108e5fafa52e6d11`
  — both unchanged.
- Registered pairs only: `local-coding-v1`, `local-coding-vLLM`,
  `configured-upstream-llm`; no new route/backend, no permission or
  schema changes.
- Pinned upstream source: official Codex CLI `rust-v0.167.1`, source
  commit `0a94398fa60c4fac0e7659e4213a0a36e613dd46` (verified
  byte-identical root-fetched copies, round a).
- One profile revision per process (one-shot guarded bootstrap); the
  15→16 migration requires the NEW engine (scoped runbook example in
  `docs/upgrade-runbook.md`); rollback data-only or binary with drain
  and restart of every process — no same-process canary.

## Factual results (evidence index)

Full narrative in
`docs/verification/2026-11-16-codex-tool-history.md` (single
consolidated record; no duplicate inventories).

- Reused round-a accepted evidence (NOT rerun): shared helper suite
  54 + adapter suites 103 = 157 focused cases (root-run at the round-a
  checkpoint); those cases do not cover the b marker seam or
  pure-preview wiring.
- Round-b wiring module
  `tests/unit/test_codex_tool_history_replay_wiring.py`: **45**
  passed, including the bound-namespace materialization regressions
  (two distinct namespace-less histories → distinct provider bodies;
  resolved-vs-implicit parity across native and portable
  preparations; prepared estimate includes the materialized
  namespace).
- Changed-component suites at the final integrated code head
  `8a831a2b`: wiring 45 + request policy 214 + upstream LLM adapter
  57 = **316** passed; 0162/0149 roundtrip + local vLLM suites
  **125** passed (441 total, both runs exit 0).
- Owned disposable PostgreSQL 16 (container `slaif-oap226-pg16`,
  `127.0.0.1:33934`, database `slaif226test`; DSN only via a 0600 env
  file, never printed; no production DB; provider HTTP mocked; no
  provider calls): secondary-owned acceptance module **22** cases
  passed on the corrected source (owned-row HMAC route/provider
  denials before quota/provider, qualified ID-less positive +
  unowned/other-key/wrong-route negatives, codec settlement with
  usage settled exactly once and fixed 502 after settlement, all five
  owned nonempty-history success kinds with per-codec wire identity,
  preserve-identity regression, missing key/route grant negatives
  with zero reservation/ledger writes, rev15→rev16 migration
  dry-run/apply/idempotency + drifted-digest negative); **11** passes
  REUSED (not re-run, unchanged modules) from the isolated matrix at
  `194f11c1` (`test_codex_replay_references_postgres.py` 2,
  `test_local_coding_server_module_postgres.py` 3,
  `test_accounting_finalization_postgres.py` 6).  Total: **33**
  unique PG cases.
- Full unit suite ONCE at the final integrated code head
  (`.venv/bin/python -m pytest tests/unit -o addopts=`, no
  production DB environment): **8185 passed, 1 skipped**, exit 0
  (16m20s).  The single skip is the optional live-plumbing test
  `test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`
  (Codex 0.148 CLI binary unavailable in this environment); no real
  Codex CLI was installed or run and the skip is preserved.
- Intermediate hosted-CI unit result at code head `f43794e0` (CI run
  `43973480725`, unit job `133671381058`): 8183 passed, 1 skipped,
  2 failed — both failures were stale shipped-preset inventory
  expectations (the fifth preset shipped at `867bc0f0`), fixed
  test-only at `8a831a2b`; the corrected module then passed 86/86
  locally and is inside the final full-unit run.
- Final hygiene at the implementation head: Ruff (project gate)
  clean; `scripts/check_documentation.py` OK (139 files);
  `git diff --check` clean; OAP governance suite 10/10.
- Final-head hosted CI at this report SELF commit: **PENDING
  strategic verification; not claimed passed before publication.**

## Boundaries and NOT RUN

- Bounded CREATE-only client-tool lifecycle; compact remains
  create-only for this module (local coding auxiliary endpoint
  denied); frozen 0.147/OpenAI compact unchanged.  No hosted-tool
  authority, no gateway execution, no stored tool content, no new
  unqualified route/backend, no permissions, no database schema
  change.
- Admission estimation is a conservative prepared-body byte
  approximation (`ceil(bytes/3)`), not an exact tokenizer
  measurement or a mathematical no-overrun promise; legacy profiles
  keep their exact old estimator and ordering.
- NOT RUN: real private-client reproduction, any real Codex CLI
  install/run, real upstream inference, actual operator key
  migration/rotation, deployment/release, final-head hosted CI
  (pending).  Mocked HTTP paths are distinguished from actual
  inference throughout; synthetic gateway-key canaries only.

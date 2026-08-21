# OAP Work Order — 022-f

PR mode: `CONTINUE_EXISTING_PR`

## Objective and reason

Restore a green final PR #248 head by updating the two pre-existing synthetic
Codex profile fixtures to the stricter explicit-safe catalog contract introduced
in 022-d. Do not weaken production validation or rerun expensive phase gates.

Start immediately; read the failing test names/log and their local fixture
builders only. No reconnaissance.

## Verified continuation state

- `main` is `4ad592e190f6bfa1a8878814519569b6ce7e59a2`.
- PR #248 report head is
  `8a5560760175c5a2011631bca97c4725cdacdc66`; first-parent implementation is
  `98e40685569d44e0fafc75095f7a6215ee042b8c`.
- Hermetic and configured-provider live-plumbing phases pass; live Qwen
  variables are absent; candidate remains mocked/unregistered/live-false.
- All completed non-unit checks reported by 022-e passed. The prior
  Unit/lint/migration run had 3301 passed, 1 skipped, and exactly 2 failures in
  synthetic catalog-profile tests because their safe test catalogs omit the
  now-required explicit `supports_search_tool=false` facts. Confirm the exact
  current failure output before editing; skipped/missing checks are not passes.
- Production validator behavior is intentional: text candidate catalogs must
  explicitly deny search, parallel calls, reasoning summaries, and patch
  authority.
- `oap/active` is `022-f`. Amend PR #248 only; never merge or auto-merge.

## Allowed paths

```text
tests/unit/test_codex_profile_registry.py
tests/unit/test_codex_qualification.py
oap/active
oap/orders/022-f-qwen38-text-codex-qualification.md
oap/reports/022-f-qwen38-text-codex-qualification.md
```

One exact adjacent synthetic fixture test path is allowed only if it is one of
the two failing tests and must be reported. No application/script/docs change.

## Requirements

1. Update only the failing synthetic replacement-catalog builders/fixtures to
   declare the complete explicit safe facts required by the current validator:
   search false, parallel tool calls false, reasoning summaries false, no patch
   authority, plus any already-required text/context/threshold fields. Preserve
   their original test intent and unregistered status.
2. Do not loosen `_validate_catalog_artifact`, add defaults, skip tests, alter
   the Qwen candidate, or change runtime behavior.
3. Run the exact two prior failures first, then focused registry/qualification/
   candidate tests, scoped Ruff if imports changed, and `git diff --check`.
   Do not rerun Codex, PostgreSQL, Redis, browser, or a full local suite.
4. Push the implementation and require all final-report-head GitHub checks to
   pass. Verify all PR review threads are resolved and no new thread exists.

## Non-goals

No live call, registry promotion, production code change, new feature, phase
gate rerun, migration, release, or broad local suite.

## Publication

Commit the test correction, then publish one immutable
`oap/reports/022-f-qwen38-text-codex-qualification.md` report-only final commit
with literal implementation head and `Report publication commit: SELF` on PR
#248. Report exact prior failures, focused results, full final-head check table,
and review-thread state. Verify remote head, signal exact response-FIFO `OK`,
and return to one control wait. Never merge.

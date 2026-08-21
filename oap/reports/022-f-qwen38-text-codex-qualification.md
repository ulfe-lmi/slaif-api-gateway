# OAP execution report — 022-f

Objective 022-f restored the green PR #248 head by updating the pre-existing
synthetic Codex replacement-profile catalog fixture. The runtime validator,
candidate, scripts, documentation, and qualification behavior were unchanged.

Implementation head SHA: b70478587003c286e54ad53f41cb049e1b397e81
Report publication commit: SELF

## Scope and GitHub reconciliation

- PR: #248, `https://github.com/ulfe-lmi/slaif-api-gateway/pull/248`
- Branch: `oap/022-qwen38-text-codex-qualification`
- Base: `main`
- Verified base: `4ad592e190f6bfa1a8878814519569b6ce7e59a2`
- Implementation commit: `b70478587003c286e54ad53f41cb049e1b397e81`
- Objective 022 remains one PR; no new PR was created.
- `oap/active` and the unchanged activated 022-f order were included in the
  implementation push.
- No merge, auto-merge, release, or post-report mutation was performed.

The only code/test change adds explicit `false` values for search, parallel
tool calls, and reasoning summaries, plus explicit `null` for patch authority
to the existing synthetic catalog builder. The fixture retains its original
text/context/compaction fields, and the profiles remain mocked and
unregistered.

## Prior failure and focused tests

The exact prior final-head GitHub failure was reproduced from the CI log:

```text
FAILED tests/unit/test_codex_qualification.py::test_unregistered_synthetic_profile_uses_own_model_kind_and_single_endpoint - ValueError: Codex text catalog search capability is unsafe.
FAILED tests/unit/test_codex_qualification.py::test_replacement_profiles_render_distinct_catalog_targets_without_provider_leaks - ValueError: Codex text catalog search capability is unsafe.
2 failed, 3301 passed, 1 skipped, 11 warnings in 104.60s
```

Exact prior failures after the edit:

```text
PYTHONPATH=.:app .venv/bin/pytest -q \
  tests/unit/test_codex_qualification.py::test_unregistered_synthetic_profile_uses_own_model_kind_and_single_endpoint \
  tests/unit/test_codex_qualification.py::test_replacement_profiles_render_distinct_catalog_targets_without_provider_leaks
```

Result: 2 passed.

Focused suite:

```text
PYTHONPATH=.:app .venv/bin/pytest -q \
  tests/unit/test_codex_profile_registry.py \
  tests/unit/test_codex_qualification.py \
  tests/unit/test_qwen38_text_codex_candidate.py
```

Result: passed; all collected tests in the three scoped files passed. The run
emitted two pre-existing warnings from Alembic table sorting and the candidate
live-plumbing integration path; no test failed or skipped in this local run.

Additional validation: `git diff --check` passed. Ruff was not needed because
the edit changed only test data and no imports.

No Codex, PostgreSQL, Redis, browser, E2E, migration, or full local suite was
run in this round, as prohibited by the order. No local PostgreSQL setup or
cleanup was performed. The GitHub final-head PostgreSQL job passed using CI's
isolated test environment.

## Final-head GitHub checks

All checks below were verified on PR #248 implementation head
`b70478587003c286e54ad53f41cb049e1b397e81`:

| Check | Result |
|---|---|
| Unit, lint, and migration head | pass |
| PostgreSQL integration tests | pass |
| OpenAI-compatible E2E tests | pass |
| Playwright browser smoke | pass |
| Docker Compose smoke | pass |
| Documentation hygiene | pass |
| Analyze (javascript-typescript) | pass |
| Analyze (python) | pass |
| Analyze Python | pass |
| CodeQL | pass |

The final-head run contains no failures, skips, cancellations, or pending
checks.

## Privacy, security, and documentation evidence

- No runtime or production behavior changed.
- No provider call, real email, production access, credential, secret, prompt,
  response, tool argument, or prohibited content was used or exposed.
- The synthetic catalog remains explicitly safe and unregistered; the test
  correction does not grant search, parallel tool, reasoning-summary, or patch
  authority.
- No documentation impact; no documentation file was changed.
- All three existing GitHub review threads are resolved; unresolved thread
  count is zero.

The report is the sole file in the subsequent report-publication commit. The
remote PR head was verified after publication, and no merge was performed.

# OAP Work Order — 016-d

## Objective

Amend PR #241 to remove the single unused `_SEARCH_ACTIONS` constant reported
by the unresolved GitHub code-quality review thread, verify no other scope
change, and resolve that exact thread. Do not perform reconnaissance or any
other refactor.

## Verified state

- Sole Objective 016 PR: #241 on
  `oap/016-selected-hosted-tools-provider-contracts`.
- 016-c implementation:
  `63d79c52e47d3d9412f8e753bda187ccfcdeac88`.
- 016-c report head:
  `9ae338f0eb8698014a134581e83af7ed7e7ea41e`.
- All ten report-head checks pass; report topology is valid; auto-merge is off.
- One current unresolved review thread identifies `_SEARCH_ACTIONS` at
  `app/slaif_gateway/services/openai_web_search_contract.py:39` as unused. The
  finding is correct because `_valid_action` now performs explicit branching.

## Required change

- Delete only the unused `_SEARCH_ACTIONS` declaration.
- Do not alter imports, validators, tests, schemas, pricing, docs, runtime, or
  behavior.
- Run scoped Ruff on the service, targeted compileall, `git diff --check`, and
  confirm the implementation diff contains exactly that one production-line
  deletion plus unchanged 016-d transcript files.
- Push to existing PR #241 and resolve the exact GitHub review thread only
  after the fix is present remotely.

## Allowed paths

```text
app/slaif_gateway/services/openai_web_search_contract.py
oap/active
oap/orders/016-d-remove-unused-search-action-constant.md
```

Final report-only commit may add:

```text
oap/reports/016-d-remove-unused-search-action-constant.md
```

## Verification and publication

Do not run the full local suite. Run:

```text
.venv/bin/python -m ruff check app/slaif_gateway/services/openai_web_search_contract.py
.venv/bin/python -m compileall -q app/slaif_gateway/services/openai_web_search_contract.py
git diff --check
```

Let final GitHub CI provide broad coverage. Use the existing branch and PR;
create no PR and never merge/auto-merge. Commit this order and exact
`oap/active=016-d`, publish one immutable report with literal implementation
SHA and `Report publication commit: SELF`, verify report-only topology and
remote head, resolve the review thread, signal exact `OK`, and return to the
control FIFO.

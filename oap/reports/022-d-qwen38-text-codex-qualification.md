# OAP 022-d report — Qwen3.8 Codex 0.148 hardening

Implementation head SHA: d87f7a9be46199b3d2f5c27a0a8bc742061b358e
Report publication commit: SELF

## Result

Objective 022-d corrections are implemented on PR #248. The 0.148 authority
bypass is removed. The successful hermetic phase now records observed request
phases, ordered typed-SSE events, stable sanitized item/call relationships,
taxonomy, route/key gates, credential-boundary facts, and exact accounting
facts. The candidate is `mocked_qualification=true`, remains outside the
production `CODEX_PROFILE_REGISTRY`, and remains `live_qualification=false`.

## Authority and catalog evidence

The actual 0.148 capture identified only these legitimate scanner exceptions:

- `functions.exec_command.parameters.properties.shell`
- `functions.request_user_input.parameters.properties.questions.items.properties.header`

The scanner remains active for every tool in both the `functions` and
`multi_agent_v1` taxonomies. Table-driven focused negatives cover every 0.148
tool with `server_url`, `authorization`, `headers`, and `approval` nested
shapes; all receive the fixed provider-authority rejection. The exact
taxonomy, route/key gates, local-function distinction, schema limits, and
provider-hosted rejection remain enforced.

Catalog validation now applies control/URL/secret/byte checks to bounded model
strings and reasoning labels, requires null-only availability/upgrade/model
message metadata, and rejects text-catalog search, parallel-call, reasoning
replay, and patch-authority drift. The candidate catalog remains text-only with
empty base instructions and no hosted authority.

## Exact verification

- `PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_qwen38_text_codex_candidate.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_request_policy.py` — 318 passed (13 + 116 + 189 collected); only the known Alembic path-separator and SQLAlchemy table-cycle warnings occurred during the disposable plumbing test.
- `PYTHONUNBUFFERED=1 PYTHONPATH=app .venv/bin/python scripts/verify_qwen38_text_codex.py` — `RESULT=LIVE_TARGET_ABSENT`, `LIVE_TARGET_PRESENT=false`, `REAL_PROVIDER_CALLED=false`, `HERMETIC_PHASE=true`, `ACCOUNTING_PROVED=true`, `PRIVACY_PROVED=true`, and exactly one `LIVE_QUALIFIED=false` line.
- `PYTHONUNBUFFERED=1 PYTHONPATH=app .venv/bin/python - <<'PY'` followed by `from scripts import verify_qwen38_text_codex as verifier` and `print(verifier.run_local_live_plumbing_phase())` — passed with Codex 0.148.0, two requests, accounting/privacy proofs, `real_provider_called=true`, and `loopback_only=true`.
- `.venv/bin/ruff check` over the changed registry, policy, gateway, verifier, and focused test files — passed.
- `PYTHONPATH=app .venv/bin/python -m compileall -q app scripts/verify_codex_gateway_e2e.py scripts/verify_qwen38_text_codex.py` — passed.
- `git diff --check` — passed.

No full local suite was run.

## Hermetic PostgreSQL, Redis, and accounting

The verifier self-provisioned a unique user-owned PostgreSQL 16 cluster under
`/tmp`, bound only to `127.0.0.1` with a generated port/database/socket, ran
migrations, and stopped it with fast `pg_ctl` cleanup. It did not use
`DATABASE_URL`, Docker, sudo, or the system cluster. Redis was a private
ephemeral local process and was cleaned up by its bounded context manager.

The actual observed accounting facts were:

- two finalized reservations and two finalized successful ledgers;
- HTTP statuses `(200, 200)` and no ledger error types;
- usage `(input=1, cached=0, output=1, reasoning=0, total=2)` for each request;
- key totals: 2 requests, 4 tokens, EUR `0.000006000` cost, zero reserved
  requests/tokens/cost, and zero pending reservations;
- each ledger cost EUR `0.000003000`, with ledger/key cost agreement and EUR
  currency.

## Codex and privacy evidence

The actual installed binary reported exactly `codex-cli 0.148.0`. Codex ran
with isolated `CODEX_HOME`, without overriding child `HOME`, and used
workspace-write. The observed tool turn created the exact file marker
`SLAIF_QWEN38_FILE_OK`, then completed the tool-output continuation and final
marker `SLAIF_QWEN38_CODEX_OK`. The configured public model was rewritten to
the upstream `qwen3.8-27b`; loopback provider requests had substituted auth,
sanitized headers, and no content encoding.

The sanitized observed fixture is pinned at:

`96a05bf2f0ddd88b0f2b048589e71005aea120f7cd74c06ced4c7c4bf20f4f89`

The durable canary scan found no gateway key, provider key, marker, prompt,
response, argument, workspace path, or other prohibited raw content in the
database. No real LAN target, real upstream provider, or real email was used.

## Live path

The direct `httpx.post(<LAN>/responses)` implementation was removed. The live
runner now creates the disposable PostgreSQL/Redis/SLAIF stack, stores the
validated target as the provider row, puts the supplied credential only in a
dedicated server-side environment variable, and runs Codex against SLAIF. A
successful Codex file-marker turn plus final usage/accounting/privacy proof is
required before `REAL_PROVIDER_CALLED=true`; no redirect or retry is enabled.

The separate local plumbing command exercised that branch against a distinct
numeric-loopback provider and proved Codex → SLAIF → configured provider. With
live variables absent, the main verifier runs hermetic only and reports live
absence. A live evidence pass may emit `LIVE_EVIDENCE_PASSED=true`, while the
single `LIVE_QUALIFIED=false` line remains because the candidate is not
registered and no human LAN evidence was supplied.

## GitHub and scope

PR #248 is the unique Objective 022 PR, base `main`, head branch
`oap/022-qwen38-text-codex-qualification`, open and mergeable. The prior dual
import review thread was fixed and resolved; no new review thread was present
after the implementation push. Auto-merge is null/disabled and no merge or
release action was performed.

At report preparation, GitHub checks on the implementation head were still in
progress: Unit/lint/migration, PostgreSQL integration, OpenAI-compatible E2E,
Playwright, Docker Compose, CodeQL, and documentation checks. The completed
documentation hygiene check was successful; all other pending/in-progress
checks are intentionally not described as passed. Only the bounded candidate,
policy, verifier, fixture, order, and focused-test paths were changed.

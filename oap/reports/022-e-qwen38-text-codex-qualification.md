# OAP 022-e report — dynamic live accounting preparation

Implementation head SHA: 98e40685569d44e0fafc75095f7a6215ee042b8c
Report publication commit: SELF

## Result

The live runner now uses the real Codex → SLAIF → configured-provider path
without constructing or starting `ScriptedOpenAIMock` for a human LAN target.
The hermetic path retains its exact two-request fixed accounting assertions.
The local plumbing branch uses the same live accounting path with a separately
configured numeric-loopback provider and explicit local-zero pricing.

The candidate remains mocked-conformant, unregistered, and live-false. No LAN
variables were present and no real LAN/provider/email call was made.

## Dynamic accounting evidence

Hermetic mode still requires exactly:

- two finalized successful reservations and ledgers;
- usage `(1,0,1,0,2)` for each request;
- two requests, four tokens, EUR `0.000006000`, and EUR `0.000003000` per
  ledger;
- zero reserved totals and zero pending reservations.

Live and local-plumbing mode seeds complete Codex accounting metadata with all
input/output/reasoning/cache multipliers set to local zero pricing. It requires
two finalized successful ledgers, positive bounded input/output/total usage for
both serial turns, key token/request totals equal to ledger sums, exact zero
key and ledger costs, zero reservations, and no error status. It does not
compare live usage to hermetic mock constants.

## Exact focused verification

- `PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_qwen38_text_codex_candidate.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_request_policy.py` — 319 passed.
- `PYTHONUNBUFFERED=1 PYTHONPATH=app .venv/bin/python scripts/verify_qwen38_text_codex.py` — `RESULT=LIVE_TARGET_ABSENT`, `REAL_PROVIDER_CALLED=false`, `HERMETIC_PHASE=true`, `ACCOUNTING_PROVED=true`, `PRIVACY_PROVED=true`, and exactly one `LIVE_QUALIFIED=false` line.
- `PYTHONUNBUFFERED=1 PYTHONPATH=app .venv/bin/python - <<'PY'` with `from scripts import verify_qwen38_text_codex as verifier` and `print(verifier.run_local_live_plumbing_phase())` — passed with two requests, dynamic zero-cost accounting/privacy proofs, `real_provider_called=true`, and `loopback_only=true`.
- `.venv/bin/ruff check scripts/verify_qwen38_text_codex.py tests/unit/test_qwen38_text_codex_candidate.py` — passed.
- `PYTHONPATH=app .venv/bin/python -m compileall -q scripts/verify_qwen38_text_codex.py` — passed.
- `git diff --check` — passed.

The focused accounting tests cover fixed hermetic values separately from live
dynamic values and reject missing usage, zero counters, nonzero costs, and
non-final ledger statuses. One Codex-dependent plumbing unit test is skipped
when `/usr/bin/codex` is absent; the explicit local plumbing command above ran
it successfully on this machine.

## PostgreSQL, Redis, and privacy

Each local phase used the bounded user-owned temporary PostgreSQL 16 cluster
and private ephemeral Redis setup. The cluster was bound to loopback, used a
generated port/database/socket, ran migrations, and was stopped with fast
cleanup. No `DATABASE_URL`, Docker, sudo, system cluster, or destructive
database setup was used.

The live path stores a supplied provider credential only in the dedicated
server-side environment variable and configures zero provider retries. Codex
talks only to SLAIF; SLAIF rewrites the public model to `qwen3.8-27b`. File and
final markers plus accounting/privacy checks are required before a live pass
can emit `REAL_PROVIDER_CALLED=true` or `LIVE_EVIDENCE_PASSED=true`. The
single `LIVE_QUALIFIED=false` line remains until later promotion authority.

The hermetic structural fixture remains unchanged and pinned to:

`96a05bf2f0ddd88b0f2b048589e71005aea120f7cd74c06ced4c7c4bf20f4f89`

No secrets, prompts, responses, tool arguments, credentials, workspace paths,
or marker contents are persisted in the fixture or durable database evidence.

## Review and CI state

PR #248 remains the unique Objective 022 PR, open, mergeable, based on `main`,
with auto-merge disabled. The two new mixed-import review threads were fixed
and resolved; the earlier thread is also resolved, and no unresolved/new
thread was present at report preparation.

Final-head GitHub checks: PostgreSQL integration, OpenAI-compatible E2E,
Playwright, Docker Compose, documentation hygiene, and CodeQL all passed. The
Unit/lint/migration check ran 3301 passed and 1 skipped but failed 2 synthetic
catalog-profile tests because the earlier 022-d registry validator requires
explicit `supports_search_tool=false` metadata absent from those synthetic
fixtures. This round’s order explicitly forbids runtime registry changes, so
that out-of-scope failure is preserved for a subsequent authorized order; it
is not reported as passed. No merge, release, or post-report mutation was
performed.

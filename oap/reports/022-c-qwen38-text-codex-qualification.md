# OAP 022-c report — Qwen3.8 text Codex 0.148 qualification

Implementation head SHA: b8d7a607eee1641d3fe832abae2256e09fc63ebc
Report publication commit: SELF

## Result

The bounded hermetic qualification phase passed. It used the installed Codex
CLI `0.148.0`, a private PostgreSQL 16 cluster, private Redis, the real SLAIF
gateway process, and a numeric-loopback OpenAI-compatible provider. The
candidate remains unregistered and live qualification remains false because no
authorized live target variables were present.

The phase observed two upstream requests, a workspace-write function-tool
execution producing the exact marker `SLAIF_QWEN38_FILE_OK`, a tool-output
continuation, and the final marker `SLAIF_QWEN38_CODEX_OK`. The typed SSE
validator accepted the actual Codex 0.148 function and multi-agent namespace
taxonomy. The structural fixture remains sanitized and deterministic with
fixture SHA `952c6f39532d9b1543cfeb537eabaea4259f6e13b045cf250064897be88342bc`.

## Exact verification

- `PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_qwen38_text_codex_candidate.py tests/unit/test_responses_request_policy.py` — 103 passed.
- `PYTHONPATH=app .venv/bin/python scripts/verify_qwen38_text_codex.py` — `RESULT=LIVE_TARGET_ABSENT`, `HERMETIC_PHASE=true`, `ACCOUNTING_PROVED=true`, `PRIVACY_PROVED=true`, `REAL_PROVIDER_CALLED=false`.
- `.venv/bin/ruff check app/slaif_gateway/services/codex_profile_registry.py app/slaif_gateway/services/responses_request_policy.py app/slaif_gateway/services/responses_gateway.py scripts/verify_codex_gateway_e2e.py scripts/verify_qwen38_text_codex.py tests/unit/test_qwen38_text_codex_candidate.py` — passed.
- `PYTHONPATH=app .venv/bin/python -m compileall -q app scripts/verify_codex_gateway_e2e.py scripts/verify_qwen38_text_codex.py` — passed.

The focused suite also covers exact candidate registration boundaries, fixture
sanitization, private target URL rejection, PostgreSQL command construction,
and hermetic-then-distinct-live orchestration. No broad local suite was run.

## Database and service evidence

When `TEST_DATABASE_URL` was absent, the verifier created a unique user-owned
temporary PostgreSQL cluster under `/tmp`, bound it to `127.0.0.1` with a
unique port and socket directory, created one generated database, ran the
migrations, and stopped the cluster with `pg_ctl ... stop -m fast` before
removing the exact temporary root. It did not use `DATABASE_URL`, Docker, the
system cluster, sudo, or destructive database setup. Redis was a private
temporary local process and was stopped by its bounded context manager.

PostgreSQL remained authoritative: two requests finalized, outstanding
reservations were zero, and the accounting proof passed. No real provider call
or real email was made.

## Live target and privacy

The live variables were absent, so the distinct live runner was not invoked.
If both explicitly authorized private numeric `SLAIF_QWEN38_TEXT_BASE_URL` and
`SLAIF_QWEN38_TEXT_API_KEY` are supplied, the hermetic phase runs first and a
separate bounded target call is required before `REAL_PROVIDER_CALLED=true` and
`LIVE_QUALIFIED=true` can be reported. Public, credential-bearing, query,
fragment, percent-encoded, malformed, and non-private target URLs are rejected.

The verifier stores only structural fixture facts. It does not persist or
print gateway keys, upstream credentials, prompts, responses, tool arguments,
workspace paths, or marker contents. The privacy sentinel check passed for the
gateway key, upstream key, and both marker strings.

## Scope and review state

This round adds the unregistered Qwen3.8 text candidate catalog/profile,
Codex 0.148 client-tool taxonomy admission, independent version checking,
private PostgreSQL provisioning, actual hermetic qualification orchestration,
and the separate live-target seam. Documentation impact is limited to the
existing candidate qualification/configuration status; no production or
release claim is made.

PR #248 remains open, mergeable, and unmerged. Auto-merge is not enabled.
GitHub CI was queued or in progress at report preparation: Unit/lint/migration,
PostgreSQL integration, OpenAI-compatible E2E, Playwright, Docker Compose,
documentation hygiene, and CodeQL checks. Pending or in-progress checks are
not reported as passed. No merge, release, or direct-main push was performed.

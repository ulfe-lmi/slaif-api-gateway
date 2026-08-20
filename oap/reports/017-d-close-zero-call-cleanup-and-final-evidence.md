# OAP 017-d execution report

Implementation head SHA: e0c537d004e1f70f87c1759ea490450e6e822234
Report publication commit: SELF

## Scope

Amended PR #242 on `oap/017-external-tool-security-accounting-e2e`; no new PR,
merge, or auto-merge was created or enabled. The activated `oap/active` value
remains `017-d`, and the exact activated order is included in the implementation
commit.

The implementation restores authoritative zero-call completed web-search
outcomes when pricing is valid, keeps missing pricing and incomplete/failed
lifecycle evidence non-authoritative, resolves an external fence after
pre-provider streaming construction failure, and uses one content-free action
validator for `search`, `open_page`, and `find_in_page`. The gateway integration
matrix covers provider failure, missing usage, malformed output, hosted-stream
success, malformed hosted stream, same-key fence rejection, construction
failure cleanup, ordinary success, and content-free fence/hold behavior.

## Verification

- Focused unit command: `pytest tests/unit/test_openai_web_search_contract.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_request_policy.py tests/unit/test_v1_responses_quota.py tests/unit/test_external_tool_fence.py tests/unit/test_external_tool_hold.py tests/unit/test_pricing.py -q -ra`; 459 collected and passed, zero skips.
- PostgreSQL gateway command: `TEST_DATABASE_URL=postgresql+asyncpg://ubuntu@/slaif_oap_017d_test_1787264398 pytest tests/integration/test_responses_external_tool_postgres.py -q -ra`; 10 collected and passed, zero skips. PostgreSQL was created with `sudo -n -u postgres createdb -O ubuntu`, used only through the isolated `TEST_DATABASE_URL`, and dropped with `sudo -n -u postgres dropdb --if-exists`; cleanup status was 0.
- Responses client E2E command: `TEST_DATABASE_URL=postgresql+asyncpg://ubuntu@/slaif_oap_017d_e2e_test_1787264459 ENABLE_EMAIL_DELIVERY=false pytest tests/e2e/test_openai_python_client_responses.py -q -ra`; 18 collected and passed, zero required skips. The disposable database was dropped with status 0.
- Scoped Ruff, Python compilation, and `git diff --check` passed.
- A preliminary disposable database named `slaif_oap_017d_gateway_1787264352` was refused by the test safety guard and then dropped; it produced no test evidence and is not counted as a pass.

The PostgreSQL gateway tests asserted released counters, one failed ledger,
fence state, Redis release, content-free persistence, and hosted streaming
terminal withholding. Existing focused Responses quota tests also cover
provider-construction cleanup, finalization failure recovery, and client
disconnect interruption paths. No full local, browser, Docker, HPC, or
provider suite was run; routine broad coverage is delegated to GitHub CI.

## Safety and privacy

No real OpenAI/OpenRouter calls, production systems, real email, or secrets were
used. Provider and content canaries were asserted absent from responses and
retained evidence. No provider payload, URL, query, argument, result, prompt,
credential, or diagnostic content was added to durable hold/accounting state.
PostgreSQL remained authoritative; Redis was used only for transient release
observation.

## GitHub state

The exact review thread `PRRT_kwDOSLm-qM6a-QSh` was resolved after the import
style fix was pushed. At report preparation, all ten fresh checks for the
implementation head were successful: Unit/lint/migration, PostgreSQL
integration, OpenAI-compatible E2E, Playwright browser smoke, Docker Compose
smoke, documentation hygiene, and the four CodeQL checks. The PR remained open
with auto-merge disabled. This report does not authorize merge or release.

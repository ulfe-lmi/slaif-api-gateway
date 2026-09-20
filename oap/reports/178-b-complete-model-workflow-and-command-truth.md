# OAP Coding-Agent Report — 178-b

## Work order
- Identifier: 178-b
- Work-order file: `oap/orders/178-b-complete-model-workflow-and-command-truth.md`
  (committed unchanged; md5 `d3e955b987103e74243db826b6739321` before and after commit)
- Numeric objective: 178
- PR mode: AMEND_EXISTING_PR (PR #315, no new PR, no objective switch)

## Status
COMPLETE

## Executive summary
This round closes the concrete acceptance failures that independent strategic
review found in the 178-a front door, without changing runtime behavior.
QUICKSTART milestone 2 now ends with an executable, output-capped
`OpenAI().chat.completions.create(...)` request (the maintainer's required
outcome), with `/v1/models` explicitly labeled LOCAL discovery and the
inference call explicitly labeled EXTERNAL, the server-side credential placed
at the milestone-2 boundary, the qualified `openai==3.14.1` SDK pin, an honest
statement of the ten-row pricing-bootstrap friction, and a substantial
shortening (345 → 312 lines). README's mixed shell/Python fence is now
separate executable fences; INSTALL.md carries verified command and interface
truth (host-interface port publication, no app-level `/readyz` or `/metrics`
auth in the local default topology, exact `docker-refresh.sh --pull` /
`--env-only` semantics, observed post-recreation health-probe race with bounded
retry, a distinct production upgrade outline with verified `--force-recreate`
dependency behavior, and no "only migration path" wording); CONTRIBUTING.md
documents the venv plus required `.env` template copy for `docker compose
config`, verified from a fresh disposable clone; the operator guide now places
`--cohort-id` on `keys create` (not `owners create`), gives a concrete
verified pricing-replacement procedure (per-row dashboard Edit; import is
create-only; the CLI has no row-update command), aligns build/secret/startup
ordering, fixes docs-home navigation, and points the rc-beta preamble at the
current verification index with the old record labeled historical. Every
corrected command was read from source/help; the documented model workflow was
executed on disposable PostgreSQL state with the exact documented snippets run
against a live app with a mocked upstream (`MOCK_HARNESS=OK`); the
placeholder-to-reviewed pricing procedure was executed on separate disposable
state with all ten rows updated and the confirmed import execute blocked
(`PRICING_PROCEDURE=OK`); the provider-free quickstart plus local model
discovery was executed literally from a NEW disposable clone of the exact
final implementation head (`['gpt-4o-mini']`, no upstream call); and the fresh
contributor setup was verified in a NEW disposable environment. Live provider
inference was NOT RUN. No runtime, deployment, dependency, or historical/OAP
path changed. Live provider calls: NOT RUN. Merge: NO. Tag/release: NO.

## Independent review findings and how this round closes them
The 178-a report claimed COMPLETE; independent strategic review subsequently
found concrete acceptance failures. The 178-a order and report are immutable
and are not rewritten here. Findings and closure:
- "Milestone 2 must SEND A MODEL REQUEST, not stop at model discovery" —
  closed: milestone 2 step 5 is an executable bounded
  `chat.completions.create(...)` in root QUICKSTART (step 4 verifies local
  discovery first); regression assertion
  `test_quickstart_milestone_two_documents_credentialed_model_call` pins the
  invariants (executable call present, `openai==3.14.1` pin, LOCAL/EXTERNAL
  labels, credential at the boundary, no "no live provider inference" claim).
- "Label `/v1/models` as LOCAL and inference as EXTERNAL; credential at the
  boundary; keep the two key worlds distinct" — closed: explicit labels in
  milestone 2 intro and each step; `OPENAI_UPSTREAM_API_KEY` is set at
  milestone 2 step 1 as "the only step that needs a real key";
  `OPENAI_API_KEY` is always described as the gateway-issued client key.
- "Executable model-call code in root QUICKSTART, not only a deep link; small
  output cap; qualified SDK pin" — closed: the Python heredoc is in root
  QUICKSTART, `max_completion_tokens=100`, `gpt-4o-mini`, `openai==3.14.1`;
  compatibility is not extended to the unpinned latest SDK.
- "Shorten substantially; move nonessential detail to INSTALL/operator
  guide" — closed: 345 → 312 lines; placeholder branch, FX example, rotation
  cautions, non-interactive admin, and tutorial detail live in
  `docs/first-time-operator-guide.md` / `INSTALL.md`.
- "README mixed shell/Python fence" — closed: separate `bash` and `python`
  fences with execution context (validated by the fence syntax check).
- "INSTALL false 'internal/allowlisted' claims for local `/readyz`/`/metrics`"
  — closed: the local Compose API port is documented as published on host
  interfaces; `/readyz` has no auth/IP dependency at the application route;
  local `/metrics` denies all callers by stock `METRICS_REQUIRE_AUTH=true`
  plus empty allowlist; production NGINX allow/deny behavior is kept distinct.
  No exposure change in code.
- "Actual copy/paste local update commands; health-probe race; production
  upgrade distinct from local helper; `--force-recreate` behavior; no 'only
  migration path' wording" — closed in INSTALL.md with verified behavior
  (`--pull` requires clean tracked main; `--env-only` skips
  build/migrations; bounded retry confirms health without hiding persistent
  errors; `--force-recreate <svc>` verified by synthetic Compose experiment to
  recreate only the named service with the DB volume untouched; production
  outline separates `alembic upgrade head` from the CLI path).
- "CONTRIBUTING installs into system Python and runs Compose config without
  the required `.env`" — closed: venv documented as the required environment;
  `cp .env.example .env` documented before `docker compose config`; verified
  from a fresh disposable clone (config exits 1 without `.env`, 0 after the
  copy).
- "`--cohort-id` belongs to `keys create`, not `owners create`; pricing
  replacement left the reader trapped" — closed: guide corrected (regression
  assertion `test_operator_guide_places_grouping_flags_on_their_commands`),
  and the concrete per-row Edit procedure is documented and verified
  end-to-end (`PRICING_PROCEDURE=OK`), including proof that dashboard import
  is create-only.
- "docs-home navigation and rc-beta preamble staleness" — closed: the
  compatibility stub is no longer a prominent Getting-started choice
  (intentional reachability retained lower down), configuration is linked
  directly from Getting started, and the rc-beta preamble uses the current
  verification index with the old record explicitly historical.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 315
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/315
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/178-documentation-productization`
- Starting remote SHA: `70f16102d975e3d59268f71de8ff1efd37432d3c` (remote `main`)
- Round start SHA (178-a report head, sole first-parent base of this round):
  `a7f1a78a25599a6eb1b320a3ff6eb9aa20fe60fc`
- Implementation head SHA: `10bdea6d58501e6bc0f5d7eef0ec75e436269e8f`
  (git describe `v0.1.0-rc.1-738-g10bdea6`)
- Report publication commit: SELF
- Remote PR head after report publication: SELF (verified against GitHub)
- Commits pushed before the report commit (this round):
  - `d3b7d74cacf2258d1d878ca5865fdf2f07dae0d8` —
    `oap: activate 178-b complete model workflow and command truth`
    (strategic order + `oap/active`, bytes unchanged)
  - `9a36b70955fe1ac8d98c80b4da67e8144e8644c0` —
    `obj178: complete the model workflow and command truth` (R1–R5 corrections)
  - `10bdea6d58501e6bc0f5d7eef0ec75e436269e8f` —
    `obj178: document the verified pricing-replacement procedure`
    (operator-guide pricing section corrected to the verified truth)
- Report commit first parent: `10bdea6d58501e6bc0f5d7eef0ec75e436269e8f`
  (implementation head)
- Created a new PR this turn: no
- Amended existing PR this turn: yes (PR #315)
- Merge performed: NO
- Tag/release created: NO
- `oap/active` after activation: exactly 5 bytes `178-b`, no trailing newline

## Changes made (per correction)
### R1 — Milestone 2 sends a model request; shorter quickstart
- `QUICKSTART.md` (345 → 312 lines). Milestone 1 remains genuinely
  provider-free through admin login. Milestone 2 now: (1) set
  `OPENAI_UPSTREAM_API_KEY` in `.env` ("the only step that needs a real key")
  and apply with `./scripts/docker-refresh.sh --env-only`; (2) bootstrap local
  catalog metadata with a reviewed pricing file (one recommended path; the
  placeholder branch moved to the operator guide), with an honest evaluation
  friction note: the default catalog has ten models and the bootstrap requires
  a pricing row for every selected model even if the key uses one; there is no
  single-model bootstrap switch today; a bounded single-model evaluation
  bootstrap is flagged as reasonable future work (not implemented); (3) create
  an owner and a narrow key (`--valid-days 30 --cost-limit-eur 5.00
  --request-limit-total 100 --allowed-endpoint /v1/models
  --allowed-endpoint /v1/chat/completions --allowed-model gpt-4o-mini`);
  (4) verify LOCAL model discovery with a disposable host venv pinned to
  `openai==3.14.1` and standard `OPENAI_API_KEY`/`OPENAI_BASE_URL`; (5) send
  one bounded EXTERNAL `chat.completions.create(...)` with
  `max_completion_tokens=100` and display the response. The LOCAL/EXTERNAL
  distinction is stated in the milestone intro and per step.
- Host Python/venv prerequisite stated for the client workflow only.
- README: concise first-screen audience sentence (SMEs, institutions,
  research/workshop teams) added.
- `docs/README.md`: Getting-started wording now says first success is local
  boot and then an explicitly credentialed model call (no provider-free
  inference promise); configuration linked directly from Getting started.
- `tests/unit/test_documentation_inventory.py`: new regression test
  `test_quickstart_milestone_two_documents_credentialed_model_call`.

### R2 — README runnable examples
- `README.md`: the single fence mixing shell exports with Python code was
  split into a `bash` fence (exports + verification commands) and a `python`
  fence (the `openai==3.14.1` client code), each with its execution context;
  the example is not presented as successful without its prerequisites. All
  fences in the in-scope docs pass the syntax validator (bash `bash -n`,
  Python `compile`).

### R3 — INSTALL command and interface truth
- `INSTALL.md` (149 → 238 lines): local Compose port publication is documented
  as published on host interfaces (trusted local evaluation environment, not a
  hardened public deployment); `/readyz` is stated to have no auth/IP
  dependency at the application route in the local default topology (no NGINX
  in front locally); local `/metrics` denies all callers via stock
  `METRICS_REQUIRE_AUTH=true` with an empty allowlist; production NGINX
  allow/deny behavior is described separately as the production control.
- Exact local update commands: `./scripts/docker-refresh.sh --pull` requires a
  clean tracked `main` checkout and runs pull/build/migrations/recreate;
  `--env-only` skips build and migrations and only applies `.env` changes to
  the app containers. The observed post-recreation health-probe race is
  documented with a bounded wait/retry that confirms `/healthz` and `/readyz`
  without hiding persistent errors (a persistent failure re-runs migrations).
- Prerequisites are path-accurate: provider-free boot needs no host Python;
  the selected host-SDK tutorial and the production secret instructions need
  host Python.
- Production upgrade is distinct from the local helper: an executable
  controlled outline on disposable/reviewed target code (backup/rehearsal
  links, image build, explicit one-shot `alembic upgrade head` with success
  check, recreate of the correct services/profiles, health/readiness). The
  generic runbook's default Compose commands are not presented as the full
  production sequence. `--force-recreate <service>` dependency behavior was
  inspected (synthetic Compose experiment: the named service was recreated,
  the postgres container and its volume ID were untouched) and the outline
  prefers bounded commands that do not recreate DB/Redis.
- The inaccurate "slaif-gateway db upgrade is the only migration path"
  wording is removed; the CLI path and the `alembic upgrade head` path are
  both documented precisely.

### R4 — Contributor bootstrap from a fresh clone
- `CONTRIBUTING.md` (62 → 88 lines): venv is the required environment
  (`python3 -m venv .venv`, `. .venv/bin/activate`,
  `python -m pip install -e ".[dev]"`) because standard externally managed
  Linux Pythons refuse system installs; the Compose validation section
  documents that the development Compose file references `.env`
  (`env_file`) and fails without it, so `cp .env.example .env` precedes
  `docker compose config --quiet`; the docs-patch focused set
  (`check_documentation.py`, `git diff --check`) is distinguished from the
  full unit suite, and no provider credentials, running services, or database
  are required for the docs/unit/lint/config checks.

### R5 — Operator-guide accuracy and navigation
- `docs/first-time-operator-guide.md` (584 → 634 lines): `--institution-id`
  is documented on `owners create` and `--cohort-id` on `keys create`
  (verified against both CLI `--help` outputs); build/secret/startup ordering
  and client Python prerequisites align with QUICKSTART (single recommended
  sequence); the "Replacing existing pricing rows" section documents the
  verified supported procedure: row IDs from `pricing list`, per-row
  `/admin/pricing/<pricing-rule-id>/edit` with reviewed prices and a required
  audit reason (audited as `pricing_rule_updated`), plus the create-only
  import semantics (`duplicate` for an identical validity window, `overlap`
  for an overlapping window, `update` only for non-overlapping windows;
  execution never overwrites) and the absence of a CLI row-update command.
- `docs/README.md`: the compatibility stub is no longer among the prominent
  Getting-started choices (retained lower in the file for intentional
  reachability); configuration is linked directly from Getting started.
- `docs/rc-beta.md`: the current-facing preamble now directs readers to the
  current verification index and labels the August 2026 record explicitly
  historical; the historical body and its as-of data are unchanged.

## Files changed (this round, `a7f1a78` → `10bdea6`)
- `QUICKSTART.md`
- `README.md`
- `INSTALL.md`
- `CONTRIBUTING.md`
- `docs/README.md`
- `docs/first-time-operator-guide.md`
- `docs/deployment-production.md`
- `docs/rc-beta.md`
- `tests/unit/test_documentation_inventory.py`
- `oap/orders/178-b-complete-model-workflow-and-command-truth.md` (new, unchanged after activation)
- `oap/active` (strategic bytes `178-b`)
- `oap/reports/178-b-complete-model-workflow-and-command-truth.md` (this report, new)

All paths are within the work order's allowed list. No other paths changed
this round; `docs/deployment.md`, `scripts/check_documentation.py`,
`tests/unit/test_documentation_contract_drift.py`, and
`tests/unit/test_documentation_asof.py` (allowed in 178-b) were not touched
again in this round.

## Verification item 1 — Documented model workflow on disposable state; mocked Chat execution
Environment: disposable PostgreSQL 16 container `obj178-mockpg-173212`
(127.0.0.1:15997), database `slaif_mock` (dropped and recreated for the
record run), in-process app on a random 127.0.0.1 port, respx-mocked
`api.openai.com` (mock wiring is test instrumentation, not an installation
dependency).
- Real CLI executed: `db upgrade` (alembic head `0024_quota_reservation_accounting_facts`),
  `bootstrap openai-completions-catalog --pricing-file <reviewed-test CSV> --apply`,
  `providers list` / `routes list` / `pricing list` (10 rows), `owners create`,
  `keys create` (exact quickstart flags; plaintext shown once).
- Exact snippets extracted from QUICKSTART.md and executed against the live
  app with the gateway-issued key:
  - models snippet: printed `['gpt-4o-mini']`; **0 upstream calls** (LOCAL
    discovery confirmed by the mock counter).
  - chat snippet: printed the mocked completion
    (`Hello from the 178-b mocked upstream.`); **exactly 1 upstream call**,
    request carried `model=gpt-4o-mini`, `max_completion_tokens=100`, and the
    **provider key substituted** by the gateway (the gateway key never
    appears upstream; no gateway-key leak).
- Record: `MOCK_HARNESS=OK` (log `/tmp/obj178-mock-harness.log`, task-owned
  disposable artifact).
- Supplementing focused official-client E2E fixtures (mocked upstream,
  disposable `slaif_e2e_test` database):
  `test_openai_python_client_chat_completions_env_e2e`,
  `test_openai_python_client_models_list_empty_for_no_allowed_models`,
  `test_openai_python_client_generic_chat_streaming_final_usage_e2e` —
  **3 passed in 8.17s** (log `/tmp/obj178-e2e-rerun.log`).
- No real provider key, no real provider call, no real email.

## Verification item 2 — Placeholder-to-reviewed pricing procedure on separate disposable state
Environment: same disposable PostgreSQL container, separate database
`slaif_pricing_test` (dropped and recreated for the record run).
- Placeholder bootstrap created 10 zero-priced rows (`STAGE=before
  pricing_rows=10 zero_input_rows=10`); admin created; real CSRF/session
  dashboard login verified (bad-CSRf control and anonymous denial verified in
  the same session).
- Per-row Edit path (the documented in-place replacement): for all 10 rows,
  GET `/admin/pricing/<id>/edit`, submit the reviewed per-million prices with
  the required audit reason; all 10 POSTs returned the success redirect.
  Root cause of an earlier 400 in a debug iteration was a harness artifact:
  the rendered `pricing_metadata` textarea is HTML-escaped
  (`&#34;`) and the first extraction script POSTed the escaped entities
  verbatim; a real browser unescapes before submit. The corrected harness
  unescapes form values; the application behaved correctly in both cases.
- Effective prices verified from `pricing list` for all 10 rows against the
  reviewed test assumptions (gpt-4o-mini: input `0.190000000`, output
  `0.580000000`).
- Create-only import proof: preview of the same reviewed CSV classified all 10
  rows `overlap` (0 `create`, 0 `duplicate`) against the existing enabled
  rows, and a confirmed execute (`confirm_import=true` + reason) was
  all-or-nothing blocked: `created=0 updated=0 errors=10`,
  "Import blocked. No pricing rows were written"; final state unchanged
  (10 rows, reviewed prices intact). Code-level confirmation:
  `build_pricing_import_execution_plan` marks every non-`create`
  classification blocked ("pricing import execution only creates new rows").
- Record: `PRICING_PROCEDURE=OK` (log `/tmp/obj178-pricing-procedure.log`,
  task-owned disposable artifact).

## Verification item 3 — New clean-room at the exact final implementation head
New disposable clone of `10bdea6d58501e6bc0f5d7eef0ec75e436269e8f` in
`/tmp/obj178-cleanroom-180734-rt` (directory name = unique Compose project
`obj178-cleanroom-180734-rt`; no shared image/env/DB/secret reuse). Literal
documented path (logs `/tmp/obj178-cleanroom-run.log`,
`/tmp/obj178-cleanroom-continue.log`, `/tmp/obj178-cleanroom-final.log`,
key material redacted in-place):
1. `git rev-parse HEAD` = implementation head; `git status --short` clean;
   `git describe --tags` = `v0.1.0-rc.1-738-g10bdea6`.
2. `cp .env.example .env` + `chmod 600 .env` (mode verified `600`).
3. `docker compose build` (api/worker/scheduler images built for the unique
   project).
4. Literal `run-cli` helper defined; `secrets generate hmac --version 1
   --write`, `secrets generate admin-session --write`, `secrets generate
   one-time --write`, `secrets validate-env` → all three `OK` lines.
5. `docker compose up -d postgres redis mailpit`; `docker compose run --rm
   api slaif-gateway db upgrade` → Alembic 0001 → 0024 applied.
6. `docker compose up -d api worker scheduler`.
7. `curl --fail http://localhost:8000/healthz`: the first probe raced
   container startup (connection reset), per the documented race; the bounded
   retry then succeeded. Final state: `/healthz` → `{"status":"ok"}` and
   `/readyz` → `{"status":"ok","database":"ok","schema":"ok","redis":"ok",
   "alembic_current":"0024_quota_reservation_accounting_facts",
   "alembic_head":"0024_quota_reservation_accounting_facts"}`.
8. First administrator via the interactive hidden prompt (pty driver; the
   password never appears in shell history or output) → rc=0.
9. Real CSRF/session dashboard login: bad CSRF token rejected (400),
   correct token + credentials → 303 + working session with the admin
   visible; wrong-password control returned 401 with the generic message
   "Invalid email or password." (no account-specific leak).
10. Milestone 2, steps 2–4 (provider-free up to local discovery): the stock
    `.env` has no upstream key (by design — no real credential exists for
    this task); the reviewed-pricing bootstrap was applied with explicit
    test-assumption prices (`routes: 10 created, 0 exists, 0 conflicts`;
    `pricing: 10 created, 0 exists, 0 missing, 0 conflicts`); owner + narrow
    key created with the exact quickstart flags.
11. `python3 -m venv .venv-client` + `openai==3.14.1` (version printed
    `3.14.1`); standard env vars pointed at `http://localhost:8000/v1`;
    the documented models snippet printed `['gpt-4o-mini']` — LOCAL, with no
    upstream call possible (no provider key configured).
12. `docker compose down` (non-destructive); `docker volume rm
    obj178-cleanroom-180734-rt_postgres-data
    obj178-cleanroom-180734-rt_redis-data` → `NO_OWNED_VOLUMES_REMAIN`; no
    owned containers remain.
- Milestone 2 step 5 (the EXTERNAL inference call) was NOT RUN: it requires a
  real server-side provider credential; its behavior is covered by the mocked
  execution in verification item 1. The `docker-refresh.sh --env-only` step 1
  was likewise not executed (nothing to apply without a real key).
- Transparency: two disposable-harness driver bugs occurred during the run
  and were corrected without any application mutation: (a) a quoted shell
  heredoc that failed to expand `$PWD` in a helper call (owner-id fetch);
  (b) a key-extraction regex that omitted the `.`-separated secret component
  of the one-time key (the key format is
  `sk-slaif-<public_id>.<secret>`; format read from
  `app/slaif_gateway/utils/crypto.py`). The first created key's plaintext was
  partially visible in the raw driver output; that log line was redacted in
  place, and the key is unusable because the test database was destroyed in
  step 12. The second narrow key was created and used; its plaintext never
  appears in the evidence.

## Verification item 4 — Fresh contributor setup and Compose config
New disposable clone of the implementation head in
`/tmp/obj178-contrib-180734/repo` (no shared `.env`; tree clean):
- `python3 -m venv .venv`, `. .venv/bin/activate`,
  `python -m pip install -e ".[dev]"` → success (fresh venv, `openai 3.14.1`
  among installed packages); `slaif-gateway --help` works from the venv.
- `docker compose config --quiet` WITHOUT `.env` → exit 1,
  `env file .../.env not found` (the documented hard requirement).
- `cp .env.example .env` then `docker compose config --quiet` → exit 0.
- `python scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=89`.
- `git diff --check` → clean.
- Docs-patch focused pytest (the three documentation test files) →
  **39 passed in 3.66s**.
- Shell/Python snippet syntax validation over all in-scope docs on the fresh
  clone → `SNIPPET_CHECK=OK` (bash `bash -n` + Python `compile`).
- No services started, no provider credentials, no database required.

## Verification item 5 — Checkers, focused tests, Ruff, SBOM, whitespace
At the final implementation head `10bdea6` (primary checkout):
- `python scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=89`
  (also on the fresh contributor clone).
- Focused 10-file selection (exact 178-a work-order selection):
  `test_documentation_inventory.py`, `test_documentation_contract_drift.py`,
  `test_documentation_asof.py`, `test_product_scope_docs.py`,
  `test_rc2_feature_scope_docs.py`, `test_oap_governance.py`,
  `test_local_docker_debug_ux.py`,
  `test_cli_bootstrap_openai_completions_catalog.py`, `test_cli_secrets.py`,
  `test_cli_keys_secret_output.py` → **98 passed in 10.17s** (178-a's 96
  plus the two new 178-b regression assertions).
- `ruff check` over the changed Python
  (`scripts/check_documentation.py`,
  `tests/unit/test_documentation_inventory.py` and the app tree) →
  `All checks passed!`.
- `python scripts/check_sbom.py` → `SBOM_CHECK=OK components=60`.
- `git diff --check` → clean.
- Snippet syntax validator over in-scope docs → `SNIPPET_CHECK=OK`.

## Verification item 6 — Scope, runtime/history identity
- This-round paths (`a7f1a78` → `10bdea6`): the 11 paths listed under
  "Files changed" (excluding this report, which lands in the SELF commit);
  every path is within the allowed list.
- Cumulative runtime/deployment/dependency diff from starting main
  `70f1610` to `10bdea6` over `app/`, `migrations/`, `Dockerfile`,
  `docker-compose.yml`, `docker-compose.production.yml`, `deploy/`, `nginx/`,
  `pyproject.toml`, `requirements*.txt`, `Makefile`, `alembic.ini`,
  `.env.example`, `.dockerignore`, `VERSION`, `sbom/`, `.github/` → **empty**.
- Historical/OAP immutability: `oap/orders/178-a-documentation-productization.md`
  and `oap/reports/178-a-documentation-productization.md` byte-identical to
  the 178-a report head (empty diff); `docs/verification/`, `docs/releases/`,
  `docs/security/`, prior orders/reports, `.github/`, `sbom/` unchanged this
  round; no workflow or SBOM changes.
- `oap/active` = exactly 5 bytes `178-b` (no trailing newline); the 178-b
  order file md5 is unchanged (`d3e955b987103e74243db826b6739321`).
- README's descriptive packaged-byte exception (from 178-a) remains the only
  descriptive exception; no packaged bytes changed this round.

## Verification item 7 — CI
- Implementation head `10bdea6` (inspected before this report): all ten
  final-head checks `completed | success` — `Unit, lint, and migration head`,
  `PostgreSQL integration tests`, `OpenAI-compatible E2E tests`,
  `Playwright browser smoke`, `Docker Compose smoke`, `Documentation
  hygiene`, `Analyze (python)`, `Analyze (javascript-typescript)`, `Analyze
  Python`, `CodeQL`.
- Earlier round commits `9a36b70` and `d3b7d74`: all runs `completed |
  success`.
- Report-head CI: PENDING at report publication time (the report commit is
  new to GitHub); pending is reported honestly, not treated as passed. The
  strategic model should confirm report-head checks before merge.
- No expensive integrated qualification or full local matrix was run (explicit
  work-order scope).

## Command audit
Every corrected command was read from source or live `--help` before being
documented or executed: `slaif-gateway pricing` group (add/list/show/
disable-model/import; no row-update command), `pricing list` output
formatting (`Numeric(18,9)` → 9 decimal places), `owners create`
(`--institution-id`), `keys create` (`--cohort-id`, one-time plaintext key),
`bootstrap openai-completions-catalog` flags and `exists`/`conflict`
semantics, `secrets generate|validate-env`, `db upgrade` (Alembic), the
admin dashboard pricing Edit/Import/Preview/Execute handlers and form
parsers, `_classify_existing` (`duplicate`/`overlap`/`update`/`disabled`/
`create`) and `build_pricing_import_execution_plan` (create-only), the
`/admin/login` handler (generic 401 "Invalid email or password.", 400 for
expired/invalid CSRF), the pricing edit template (HTML-escaped textarea
content), and `generate_gateway_key` (key format). The `--force-recreate`
dependency behavior was inspected with a synthetic Compose experiment
(named service recreated; postgres container and volume ID untouched).

## Truthful UX friction and deferred product recommendation
- Catalog bootstrap friction (stated honestly in QUICKSTART and the operator
  guide): the default OpenAI-completions catalog contains ten models, and the
  bootstrap requires a reviewed pricing row for every selected model even
  when the evaluation key permits one. No single-model bootstrap switch exists
  and none was invented or implemented. Recommendation (bounded future work,
  outside this objective): a single-model evaluation bootstrap flag that
  restricts the imported rows to the explicitly named model.
- The ten-row placeholder-to-reviewed replacement is a per-row dashboard
  operation today (ten Edit submissions). A batch update path (CLI
  `pricing update` or a dashboard bulk edit) would reduce operator toil; not
  implemented, not required by this order.

## Known limitations / blockers
- Live provider inference NOT RUN (no real credential; mocked execution and
  E2E fixtures only).
- Report-head CI pending at publication (see item 7).
- The 128-worker HPC qualification remains NOT RUN for this branch (unchanged
  from the verified baseline; documentation-only changes do not alter runtime
  behavior, and the order excludes integrated qualification).
- No RC2 release/tag or production-certification claim follows.

## Safety and scope confirmations
- No merge performed; PR #315 left OPEN for strategic review.
- No tag/release created.
- No second PR for objective 178; no 179 pre-activation work.
- 178-a order/report and all prior OAP artifacts immutable (byte-identical).
- No runtime, deployment, dependency, workflow, or SBOM changes; no
  application defect was found (the one observed 400 was a harness artifact,
  documented under verification item 2).
- No real provider calls, no real email, no production systems, no shared
  `.env` read, no protected credentials used, no global prune.
- All disposable state destroyed: `slaif_pricing_test` and `slaif_mock`
  databases remain on the task-owned disposable container (to be dropped with
  it); clean-room containers and both owned volumes removed; no shared
  repository state touched.
- No secrets committed; one-time key material redacted from evidence logs.

## Local setup / dependencies
- Primary checkout `.venv` (existing shared task environment) for the focused
  pytest/ruff/doc-checker runs; harness venv `/tmp/obj178-hv`
  (openai 3.14.1, respx, uvicorn, httpx) for the mock/pricing/clean-room
  drivers; fresh contributor venv under
  `/tmp/obj178-contrib-180734/repo/.venv`; fresh clean-room client venv under
  `/tmp/obj178-cleanroom-180734-rt/.venv-client` (openai 3.14.1).
- Disposable PostgreSQL 16 container `obj178-mockpg-173212`
  (127.0.0.1:15997) with task-owned databases only.

## Documentation
- All in-scope docs pass the documentation checker (links, anchors,
  reachability, brand, as-of rules) at `files=89`.
- `docs/rc-beta.md` historical body and as-of data unchanged; only the
  current-facing preamble was corrected.

## Recommended strategic follow-up
- Confirm report-head checks on PR #315 (pending at publication).
- Consider a bounded single-model evaluation bootstrap as a future objective
  (explicitly out of scope here).
- Consider a batch pricing-update path (CLI `pricing update` or dashboard
  bulk edit) to reduce the ten-row replacement toil.
- The post-PR-220 128-worker HPC qualification for `main` remains an
  outstanding repository-level item, unaffected by this documentation
  objective.

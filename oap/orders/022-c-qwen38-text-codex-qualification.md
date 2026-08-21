# OAP Work Order — 022-c

PR mode: `CONTINUE_EXISTING_PR`

## Objective and reason

Make the Objective 022 verifier self-contained and execute the actual hermetic
phase on PR #248. Strategic review provisioned two private PostgreSQL clusters
and proved the current script fails before Codex: first because its reported
`PYTHONPATH=app` cannot import `scripts`, then because it reuses the legacy
capture helper whose raw-version constant is pinned to 0.147.0. The script also
still routes a present live target through the loopback mock and always reports
`REAL_PROVIDER_CALLED=false`.

Start implementation now. Do not defer again on `TEST_DATABASE_URL`; build the
bounded private dependency path described below and run it. Read only the
named functions and concrete failures; no broad reconnaissance or full suites.

## Verified continuation state

- `main` is `4ad592e190f6bfa1a8878814519569b6ce7e59a2`.
- PR #248 remains the unique Objective 022 PR on
  `oap/022-qwen38-text-codex-qualification`, report head
  `9b3a18a7b931cfd29c19d7344a39331708753adc`, implementation parent
  `165f36dc5b12c5130255c17c1e565953f9628ce0`.
- 022-b implemented orchestration but did not execute it. Strategic execution
  against a fresh numeric-loopback PostgreSQL 16 cluster found:
  1. `PYTHONPATH=app` raises `ModuleNotFoundError: scripts` at
     `_candidate_runtime_modules()`;
  2. with repo root added, `capture.verify_codex_version()` rejects actual
     `/usr/bin/codex --version` = `codex-cli 0.148.0` because that helper also
     requires its immutable 0.147 raw-version constant.
- Both strategic test clusters were stopped and moved to trash. Docker daemon
  access is unavailable, but unprivileged
  `/usr/lib/postgresql/16/bin/{initdb,pg_ctl,createdb}` and local
  `redis-server` are available.
- Live Qwen variables remain absent; no LAN call is authorized in this round.
- One unresolved review thread flags dual import style for
  `codex_profile_registry`; fix it in code and resolve only after obsolete.
- `oap/active` is `022-c`. Amend PR #248 only; never merge or auto-merge.

## Allowed paths

Use the smallest necessary subset of the 022-a/022-b allowed paths. No new
migration, admin/RBAC, vision, hosted-tool, or unrelated provider path.

## Required corrections and execution

### 1. Self-provision a private PostgreSQL dependency

- When an explicit validated `TEST_DATABASE_URL` is absent, create a private
  PostgreSQL 16 cluster under a unique `tempfile` directory using the installed
  `initdb`/`pg_ctl` binaries, trust auth, current unprivileged user, one reserved
  numeric-loopback port, and a unique database name containing `test`.
- Start only on `127.0.0.1`, build the canonical asyncpg URL internally, and
  pass it through the existing safe database validator. Do not use the system
  cluster, repo `.env`, Docker volumes, production names, `DATABASE_URL`, sudo,
  or a shared database.
- Bound startup/readiness/stop time, log only into the temp root, stop the
  private server in `finally`, and remove only the exact validated temp root.
  Reuse the existing private Redis helper. Unit-test command construction,
  target validation, cleanup-on-failure, and fixed failure output without
  actually spawning PostgreSQL.

### 2. Use an exact independent Codex 0.148 version boundary

- Add a small candidate-local checker for exact stdout
  `codex-cli 0.148.0` and exact parsed version `0.148.0`; do not mutate or weaken
  the historical 0.147 capture constants/functions.
- Invoke the script successfully using the documented
  `PYTHONPATH=app` command from the repository root. Use the same guarded
  import style as existing scripts so `scripts.*` helpers resolve in both
  direct execution and tests.
- Reduce every unexpected import/process/database/Codex/gateway failure to a
  fixed low-cardinality error code. No traceback, exception text, URL, path,
  prompt/output/tool data, or environment value may reach stdout/stderr.
- Remove the dual-import review finding and resolve its thread after the code
  is corrected.

### 3. Execute and derive the hermetic evidence

- Run the private PostgreSQL + private Redis + real SLAIF + numeric-loopback
  provider + actual Codex 0.148 phase in this round. Do not report completion
  until the process ran or a new external dependency fails after the two known
  defects are fixed.
- Use only `CODEX_HOME`/task-specific child variables; do not overwrite the
  process-wide `HOME`. Use a workspace mode that permits the exact disposable
  marker file and prove the marker exists with bounded exact content before
  cleanup.
- The loopback provider must drive an ordinary serial shell/function call that
  creates the marker, accept the real Codex tool-output continuation, and then
  produce the final marker. Candidate catalog/tool metadata and mock SSE must
  match what Codex 0.148 actually accepts; no hard-coded custom-tool path may be
  claimed as a shell/file-marker proof unless it actually executes the marker.
- Seed complete local-zero Codex pricing metadata and verify the injected
  candidate route is ready under `CodexQualificationService` before invoking
  Codex. The key's local-tool allowlist must equal the candidate claim.
- Derive the structural fixture from observed request facts, actual request/
  event/tool ordering, placeholder relationships, and verified boundary facts.
  Do not write fixed counts unrelated to captured data. Commit only sanitized
  output; pin candidate fixture SHA only after the run passes.
- Prove two accounted requests, exact token/component totals from final usage,
  key/ledger agreement, zero pending reservations, gateway/provider/model/auth
  boundaries, loopback-only peers, final/tool/file markers, and durable canary
  absence. Set `mocked_qualification=true` only after this passes; candidate
  remains unregistered and `live_qualification=false`.

### 4. Separate and implement the live path

- Split hermetic and live orchestration. With live variables absent, run the
  hermetic phase and report `LIVE_TARGET_ABSENT` plus hermetic facts.
- With both live variables present, first require hermetic success, then build a
  distinct disposable SLAIF provider pointing to the validated human LAN URL
  and using the supplied credential only as the server-side upstream env-var.
  Do not start/queue the loopback provider for the live call.
- Run the one bounded Codex file-marker/final-marker interaction through SLAIF
  to the real target, then verify final usage/accounting/privacy and report
  `REAL_PROVIDER_CALLED=true` only after an observed backend-bound call. Any
  failure leaves the profile unregistered/live-false and returns fixed failure.
- Pure tests must inject separate hermetic/live runners and prove a present
  target invokes both in order; the current test that merely calls
  `run_hermetic_phase(runner=...)` is insufficient.

## Non-goals

No actual LAN call while variables are absent, production registration, vision,
Chat translation, search/hosted/MCP tools, parallel calls, freeform patch,
encrypted reasoning, remote compaction, schema migration, release claim, or
full local suite.

## Acceptance and verification

1. Direct `PYTHONPATH=app .venv/bin/python scripts/verify_qwen38_text_codex.py`
   self-provisions dependencies and completes one actual Codex 0.148 → SLAIF →
   loopback tool/file/final phase with fixed safe output.
2. Candidate output limits/compaction are coherent; route readiness, pricing,
   accounting, reservations, privacy, credential substitution, and loopback
   boundaries are proven from real hermetic facts.
3. The committed fixture is generated from that run, meaningful, deterministic,
   digest-pinned, and contains no raw content/secret/URL/path.
4. Present live variables invoke a distinct live runner in pure tests; absent or
   unsafe values never make a live call.
5. Candidate becomes mocked-conformant only, remains unregistered/live-false.
6. Run focused candidate/verifier/qualification tests, one hermetic phase,
   scoped Ruff/compileall, `git diff --check`, and routine GitHub CI—no full
   local suite.

## Publication

Commit implementation, then publish one immutable
`oap/reports/022-c-qwen38-text-codex-qualification.md` report-only final commit
with literal implementation head and `Report publication commit: SELF` on PR
#248. Report actual command/result, private dependency lifecycle, exact version,
marker/request/event/accounting/privacy safe facts, generated fixture SHA,
live-variable absence, review-thread state, focused tests, and final-head checks.
Verify remote head, signal exact response-FIFO `OK`, and return to one control
wait. Never merge.

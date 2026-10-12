# OAP Execution Report — 181-e: Restore sqlalchemy[asyncio] runtime install

## Identity

- Objective: 181 — authoritative catalog collection (SAME PR 318, branch `oap/181-authoritative-catalog-collection`)
- Round: **181-e** (AMEND_EXISTING_PR), selected by `oap/active` = `181-e`
- Order: `oap/orders/181-e-restore-sqlalchemy-async-runtime-install.md` (strategic-authored; committed byte-unchanged in the implementation commit; file sha256 `30376e96a379ca12236c46fd0e58123b3f7665eeceb5e39277f77c89ee185606`)
- `oap/active` exact bytes (verified with `od -c` before publication): `1 8 1 - e` — 5 bytes, no newline; committed byte-unchanged
- Starting PR/local head (181-d immutable report head, pre-round): `5e8655c38e30d9a816b9404fbc268ef784784f81`; its first parent `1ae62c38ae30ccbb37924a451a718f58ec8fafd2` is the 181-d implementation
- Implementation head: `2913321669d4c51251aaa5079fe6a3d5e1515462` (5 files, +155/−3)
- Report publication commit: SELF (first parent = implementation head `2913321669d4c51251aaa5079fe6a3d5e1515462`)
- Canonical `main`: `6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf` (unchanged)
- PR 318 at report time: OPEN, MERGEABLE, `mergeStateStatus: CLEAN`, head `2913321669d4c51251aaa5079fe6a3d5e1515462` (verified via `gh pr view 318 --json headRefOid` after push), `autoMergeRequest: null` (preserved; no merge, no auto-merge)
- Strategic inputs (read-only): `workorders/OBJECTIVE-181-D-STRATEGIC-REVIEW.md` (D1–D4 accepted at `1ae62c3`; the Docker Compose smoke failure identified as the SQLAlchemy 2.1.4 greenlet-metadata drift and the bounded dependency continuation scoped) and the strategic AP-E3 isolation correction (loopback-bound host ports in the scratch setup — applied and verified, see AP-E3).

## Status

**COMPLETE** — the bounded 181-e dependency declaration repair is implemented, verified in two clean runtime-only environments and in a full local Docker Compose reproduction of the formerly failing boundary, and pushed; GitHub CI at the implementation head is 10/10 SUCCESS, including the previously failing `Docker Compose smoke`.

## Executive summary

SQLAlchemy 2.1 moved `greenlet` out of the default install and behind the `asyncio` extra (official primary installation contract: https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html#asyncio-platform-installation-notes). The runtime image (`pip install .`) therefore resolved SQLAlchemy 2.1.4 without `greenlet`, and the explicit migration step failed with `ImportError: The SQLAlchemy asyncio module requires that the Python 'greenlet' library is installed` (181-d CI, job 114918517536; repeated on rerun and report-head job 114922275227).

This round declares the already-required bridge in BOTH runtime-only dependency declarations: `sqlalchemy` → `sqlalchemy[asyncio]` in `pyproject.toml` and `requirements.txt` (the dev file inherits the runtime file and was not edited). No version pin or downgrade, no other dependency, no Dockerfile/Compose/CI/schema/source change. A bounded runtime install/build note was added to `docs/deployment.md`. The formerly failing Docker boundary was reproduced end-to-end locally against the exact code snapshot with an owned, uniquely named, loopback-only Compose project and a fresh disposable synthetic database, and all ten required GitHub checks now pass at the implementation head.

Objective 181 remains NOT closed by this round: transport budgets/connection/encoding closure, actual collection versus intact replay, and exact tooling identity remain REQUIRED in later same-PR continuations; 182/183/184 unchanged.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 318
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/318
- PR state at report time: OPEN
- Base branch: `main` (`6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf`)
- Head branch: `oap/181-authoritative-catalog-collection`
- Starting remote SHA: `5e8655c38e30d9a816b9404fbc268ef784784f81`
- Implementation head SHA: `2913321669d4c51251aaa5079fe6a3d5e1515462`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `2913321669d4c51251aaa5079fe6a3d5e1515462` (single commit; push `5e8655c..2913321`)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes (PR 318)
- Merge performed: NO

## Changes made

1. `pyproject.toml`: the runtime dependency string `"sqlalchemy"` → `"sqlalchemy[asyncio]"` (single line; the `dev` extra and all other dependencies unchanged; existing version policy untouched — no pin, no downgrade).
2. `requirements.txt`: the runtime-only line `sqlalchemy` → `sqlalchemy[asyncio]` (single line; all other lines unchanged).
3. `docs/deployment.md`: one bounded runtime install/build dependency note in the Local Docker Compose section stating that the async database stack uses SQLAlchemy's asyncio extension which requires the `greenlet` bridge, that both runtime declarations therefore use `sqlalchemy[asyncio]`, that a runtime-only install without dev extras must include `greenlet`, and that a bare `sqlalchemy` declaration fails the explicit migration step with the exact ImportError. No feature/release claims; no operator command changed.
4. Committed the strategic-authored 181-e order and the exact 5-byte `oap/active` (`181-e`) unchanged with the implementation.

`requirements-dev.txt` inherits the runtime file (`-r requirements.txt`) and needed no edit, as the order specifies.

## Files changed

Implementation commit `2913321` only (5 files, +155/−3):

- `pyproject.toml` (1 dependency line)
- `requirements.txt` (1 dependency line)
- `docs/deployment.md` (1 bounded note)
- `oap/orders/181-e-restore-sqlalchemy-async-runtime-install.md` (strategic-authored, committed unchanged)
- `oap/active` (exact strategic bytes `181-e`, committed unchanged)

No other tracked path changed (verified by the commit stat). No test was added that merely asserts the dependency string (explicitly disallowed); the evidence is the live installations and the Docker reproduction below.

## Acceptance-criteria evidence

### AP-E1 — both runtime declarations request the asyncio extra; no unrelated changes
- Result: PASS.
- Evidence: literal round diff `git diff 5e8655c38e30d9a816b9404fbc268ef784784f81 2913321669d4c51251aaa5079fe6a3d5e1515462 --name-only` = exactly the five files above. The two dependency diffs are single-line substitutions (`-  "sqlalchemy",` / `+  "sqlalchemy[asyncio]",` in pyproject.toml; `-sqlalchemy` / `+sqlalchemy[asyncio]` in requirements.txt). The 181-d pricing/authority fixes, PostgreSQL accounting truth, and local/hosted-tool boundaries are untouched code-wise (no app/ or alembic/ changes in this commit); GitHub CI's PostgreSQL integration, E2E, and unit/lint suites re-verified them green at this head (10/10).

### AP-E2 — clean runtime-only environments contain greenlet and execute the asyncio bridge
- Result: PASS (two distinct clean environments; both removed after recording, per the setup/cleanup duty).
- Evidence — environment A (project declaration): fresh venv from the uv-managed Python 3.12.15 (`/home/janezp/.local/share/uv/python/cpython-3.12.15-linux-x86_64-gnu/bin/python3.12 -m venv /tmp/slaif-181e-venv-pyproject`; no system site-packages, run with `env -u PYTHONPATH`), installed from the actual project with `pip install --no-cache-dir .` (runtime deps only — no dev/browser packages). Recorded: Python 3.12.15, SQLAlchemy 2.1.4, greenlet 3.5.6 (pip metadata). `import sqlalchemy.ext.asyncio` OK; executed the actual bridge without any DB connection — `greenlet_spawn` (canonical import path in SQLAlchemy 2.1.4: `sqlalchemy.util.concurrency`) awaited a sync callable returning an explicit synthetic value: `BRIDGE_OK value= 42`.
- Evidence — environment B (requirements declaration): second fresh venv (`... -m venv /tmp/slaif-181e-venv-reqs`), installed with `pip install --no-cache-dir -r requirements.txt`. Recorded: SQLAlchemy 2.1.4, greenlet 3.5.6; `sqlalchemy.ext.asyncio` import OK; bridge execution `ENVB_BRIDGE_OK bridge-ok`.
- No packages were uninstalled from the shared strategic/dev venv; both AP-E2 venvs were created fresh and removed after recording (reproducible from the recorded commands).

### AP-E3 — formerly failing Docker boundary reproduced against the final code, loopback-isolated
- Result: PASS (full local reproduction; then complete cleanup of only this test's resources).
- Evidence: owned scratch `/tmp/slaif-181e-docker-smoke` (outside both repositories) containing an exact code snapshot of the implementation head via `git archive 2913321669d4c51251aaa5079fe6a3d5e1515462` (1343 tracked files; unchanged runtime Dockerfile) and a synthetic `.env` derived from `.env.example`. Isolation, including the strategic mid-round correction: unique project name `slaif181esmoke` (unique network `slaif181esmoke_default`, unique volumes `slaif181esmoke_postgres-data`/`slaif181esmoke_redis-data`, unique image tags); after the strategic correction ALL host port mappings were loopback-bound — resolved config verified via `docker compose config --format json` showing `host_ip: 127.0.0.1` for api 18101, postgres 15493, redis 16393, mailpit 10205/8105 (nginx not started; its mapping also loopback-set to 18080) — without printing any synthetic secret value; fresh disposable synthetic database `slaif_181e_smoke` (unique synthetic PG user/password, only migrated inside this project); `ENABLE_EMAIL_DELIVERY=false`, `ENABLE_SCHEDULED_RECONCILIATION=false`; no upstream credentials provided; no real `.env`, no host port 5432, no apt PostgreSQL, no other stack touched.
- Sequence (mirroring the CI job): `docker compose config --quiet` OK → `docker compose build` OK (api/worker/scheduler) → `up -d postgres redis mailpit` all healthy → in-image check `docker compose run --rm api python -c ...` executed the greenlet bridge: `IMAGE_BRIDGE_OK 42 2.1.4 3.5.6` → the formerly failing explicit migration `docker compose run --rm api slaif-gateway db upgrade` SUCCEEDED through the full chain, and `slaif-gateway db current` reports `0024_quota_reservation_accounting_facts (head)` → `up -d api worker scheduler` → `curl http://127.0.0.1:18101/healthz` = `{"status":"ok"}` and `curl http://127.0.0.1:18101/readyz` = `{"status":"ok","database":"ok","schema":"ok","redis":"ok","alembic_current":"0024_quota_reservation_accounting_facts","alembic_head":"0024_quota_reservation_accounting_facts"}` (first attempt).
- Cleanup: `docker compose down -v --remove-orphans` plus removal of the three project images; post-cleanup residual check returned empty for containers, networks, volumes, and `slaif181esmoke-*` images; the scratch directory (including the synthetic `.env`) was removed. No pre-existing container/image/network/volume was touched.

### AP-E4 — governance tests, Ruff, docs checker, round diff, and final-head CI
- Result: PASS.
- Evidence: `tests/unit/test_oap_governance.py`: 8 passed (0.33s); `ruff check app tests`: All checks passed; `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK files=91`; `git diff --check 5e8655c38e30d9a816b9404fbc268ef784784f81`: clean. GitHub CI at the implementation head: 10/10 SUCCESS (table in the next section), including `Docker Compose smoke` (1m1s) — the gate that failed at `1ae62c3`. Per the order, the full local unit/PG/Redis/browser/HPC matrix was NOT run locally, and the already-accepted 333 focused semantic tests were not repeated without a new related concern (this commit changes no tested code).

## Local verification

- Environment A (clean runtime-only, project install): install command `python3.12 -m venv <dir> && env -u PYTHONPATH <dir>/bin/pip install --no-cache-dir .` — **PASSED**: greenlet 3.5.6 present, `sqlalchemy.ext.asyncio` import OK, `greenlet_spawn` bridge returned explicit synthetic value 42 with no DB connection; versions Python 3.12.15 / SQLAlchemy 2.1.4 / greenlet 3.5.6.
- Environment B (clean runtime-only, `pip install --no-cache-dir -r requirements.txt`): **PASSED**: same versions, bridge OK (`bridge-ok`).
- Local Docker Compose reproduction (owned scratch, unique project, loopback-only ports, disposable synthetic DB): **PASSED** end-to-end (see AP-E3 for the exact steps and recorded outputs), including the formerly failing explicit migration step.
- `python -m pytest tests/unit/test_oap_governance.py`: **PASSED — 8 passed**
- `python -m ruff check app tests`: **PASSED — All checks passed!**
- `python scripts/check_documentation.py`: **PASSED — DOCUMENTATION_CHECK=OK files=91**
- `git diff --check 5e8655c38e30d9a816b9404fbc268ef784784f81`: **CLEAN**
- Full local unit/PG/Redis/browser/HPC matrix: **NOT RUN** — explicitly out of scope for this round per the order (the narrow runtime-only install and the failed Docker-matrix reproduction are the required evidence; GitHub CI re-ran the full matrix at this head, 10/10).

## GitHub CI / required checks

Check state observed for implementation head `2913321669d4c51251aaa5079fe6a3d5e1515462` (all resolved before report drafting):

- `Docker Compose smoke`: **SUCCESS** (1m1s) — run 38283655073, job 114926711952
- `Unit, lint, and migration head`: **SUCCESS** (2m7s)
- `PostgreSQL integration tests`: **SUCCESS** (2m24s)
- `OpenAI-compatible E2E tests`: **SUCCESS** (1m35s)
- `Playwright browser smoke`: **SUCCESS** (2m55s)
- `Documentation hygiene`: **SUCCESS** (8s)
- `Analyze Python`: **SUCCESS** (1m31s)
- `CodeQL`: **SUCCESS** — `Analyze (python)` SUCCESS (2m26s), `Analyze (javascript-typescript)` SUCCESS (37s)
- All required checks green for the implementation head at report drafting: **yes — 10/10**
- Report-only commit may trigger fresh checks: strategic model must verify the `SELF` commit without rewriting this report.

## Local setup / dependencies

- Packages/tools/services installed or configured: two fresh owned venvs for AP-E2 (uv-managed Python 3.12.15; runtime-only installs from the project and from `requirements.txt`) and the Docker smoke images/containers for AP-E3. ALL removed after recording (venvs deleted; containers/network/volumes/images deleted and residual-checked; scratch directory deleted). The strategic test venv `/tmp/slaif-181c-strategic-venv` and the repo `.venv` (broken symlink, left untouched) were only used for governance/ruff/docs commands — no package changes anywhere.
- Public package/image downloads (PyPI, official postgres/redis/mailpit/nginx images) and the official SQLAlchemy asyncio installation-notes doc read were used, as authorized; no protected credentials, private files, production imports/deployments, inference, real email, tags/releases; no synthetic secret values or DB URLs are reproduced in this report (safe versions/status/counts only).
- `sudo`-level setup performed: none. No apt PostgreSQL; no host shared 5432 access.
- Durable setup changes committed/documented: the `docs/deployment.md` runtime install/build note (the intended documentation change of this order).

## Documentation

Documentation impact: `docs/deployment.md` gains one bounded note in the Local Docker Compose section documenting that the async database stack requires the `greenlet` bridge, that both runtime-only declarations now use `sqlalchemy[asyncio]`, that a runtime-only install must therefore include `greenlet`, and the exact migration-step failure a bare `sqlalchemy` declaration produces. No feature or release claims; no ordinary operator command changed (the explicit `slaif-gateway db upgrade` sequence is unchanged). `scripts/check_documentation.py` OK (91 files). No other documentation path changed.

## Safety and scope confirmations

- Unrelated files changed: no — the implementation commit touches exactly the five allowed paths; untracked `CODEX-SESSIONS.md`, `codex.sh` preserved (not committed); ignored `.codex/`, `.local-provider-catalog/`, and unrelated worktrees untouched.
- Production secrets accessed: no. Production systems accessed: no.
- Required tests skipped/not run: yes — full local unit/PG/Redis/browser/HPC matrix not run locally (out of scope per the order); GitHub CI ran the full matrix at this head (10/10 SUCCESS).
- Scope deviation: no — no source/runtime/pricing/accounting/hosted-policy/route-resolution/schema/migration/test/workflow/Dockerfile/Compose/AGENTS/protocol changes; no transport/capture repair folded in; no test added that merely asserts the dependency string; the scratch Compose setup used ONLY environment-level temporary values (the tracked Compose file is unchanged) and incorporated the strategic loopback correction.
- Extra PR created for same numeric objective: NO
- PR merged by coding agent: NO (`autoMergeRequest: null` preserved; no merge action of any kind)
- Activated order and `oap/active` edited by coding agent: NO (order sha256 `30376e96a379ca12236c46fd0e58123b3f7665eeceb5e39277f77c89ee185606` and exact 5-byte active `181-e` verified before publication and committed byte-unchanged)
- Report-publication commit changes only this report file: yes (verified by staged diff before the commit)
- Real upstream/provider calls: none. No real email. No inference. No production DB. No tags/releases.
- Report layout redesign: none — follows the established 181-x report structure

## Known limitations / blockers

- No CI blockers remain: all ten required checks are SUCCESS at the implementation head.
- Objective 181 is NOT closed by this round: transport budgets/connection/encoding closure, actual collection versus intact replay, and exact tooling identity remain REQUIRED in later same-PR continuations. Objectives 182 (isolated Codex), 183 (atomic audited apply/accounting), 184 (final administrator workflow) remain pending; no 182 while 181 is unresolved.
- The local Docker proof used the local Docker socket (server 29.1.3) with a uniquely named owned project and disposable volumes; it is additional evidence alongside the authoritative Docker CI gate, not a substitute for it.

## Recommended strategic follow-up

Factual recommendation only: with the dependency gate green, the next same-PR continuation can proceed to the remaining REQUIRED 181 items (transport budgets/connection/encoding closure, actual collection versus intact replay, exact tooling identity) per the strategic plan; merge of PR 318 remains the strategic model's delegated decision after independent final-head verification.

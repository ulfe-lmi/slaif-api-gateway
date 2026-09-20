# OAP Coding-Agent Report — 178-c

## Work order
- Identifier: 178-c
- Work-order file: `oap/orders/178-c-production-upgrade-and-owned-cleanup.md`
  (committed unchanged; md5 `01875270a2d7e436e293626730cb1342` before and
  after commit)
- Numeric objective: 178
- PR mode: AMEND_EXISTING_PR (PR #315, no new PR, no objective switch)

## Status
COMPLETE

## Executive summary
This round closes the remaining executable-documentation and cleanup gaps on
Objective 178. The production upgrade documentation is now one concrete
bounded outline that is fail-closed by construction: a documented
`set -euo pipefail` subshell in which the one-shot migration runs in the
foreground and its exit status is the gate before any service replacement,
the public Nginx proxy is refreshed after the API swap (the checked-in
`nginx/production.conf` uses a static `proxy_pass http://api:8000` with no
resolver, so the proxy can keep the old container's address), the optional
`async` services have a concrete named command, and local/production
project-namespace isolation is described accurately. The sequence mechanics
were validated on a task-owned synthetic Compose fixture: the success gate
permits the restart chain, a failed migration stops the subshell with the app
untouched, the stopped one-shot is observable only via `ps --all`, the stale
proxy demonstrably 502s on the old address while the loopback diagnostic
succeeds, the DB container/volume identity stays intact, and app/async/proxy
are recreated. The production `/metrics` wording is corrected to the
checked-in truth (the proxy does not expose or proxy the endpoint; no status
is invented) while the accurate local application-settings 403 explanation is
preserved; QUICKSTART now links the bounded health-probe recovery at the
`--env-only` point, and the speculative future-bootstrap recommendation left
the beginner prose (the concrete ten-row prerequisite stays; the
recommendation lives in this report's follow-up). All still-existing
Objective-178 task-owned state was identified, ownership-verified, and
removed (mock PostgreSQL container and its data volume, task-owned images,
credential-bearing /tmp scripts/clones/venvs), with redacted evidence logs
retained; the 178-b report's "all disposable state destroyed" claim is
explicitly corrected and superseded here (that report is immutable and
untouched). Provider-free milestone 1 was re-executed from a NEW task-owned
clone of the exact final implementation head. No runtime, deployment,
dependency, workflow, or historical/OAP path changed. Live provider calls:
NOT RUN. Merge: NO. Tag/release: NO.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 315
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/315
- PR state at report time: OPEN, MERGEABLE
- Base branch: `main`
- Head branch: `oap/178-documentation-productization`
- Starting remote SHA: `70f16102d975e3d59268f71de8ff1efd37432d3c` (remote `main`)
- Round start SHA (178-b report head, first-parent base of this round):
  `56a9d307fbb25b6b3f2248c210f431964b371589`
- Implementation head SHA: `fc1b66e30a94e8cf7e046cd119def462da5631b5`
  (git describe `v0.1.0-rc.1-741-gfc1b66e`)
- Report publication commit: SELF
- Remote PR head after report publication: SELF (verified against GitHub)
- Commits pushed before the report commit (this round):
  - `9ad2e2512f6a89ca9ffe88e25bd2caaec5010ffb` — `oap: activate 178-c production upgrade and owned cleanup`
    (strategic order + `oap/active`, bytes unchanged)
  - `fc1b66e30a94e8cf7e046cd119def462da5631b5` —
    `obj178: make the production upgrade fail-closed and finish owned
    cleanup truth` (C1/C2 documentation corrections + regression tests)
- Report commit first parent: `fc1b66e30a94e8cf7e046cd119def462da5631b5`
- Created a new PR this turn: no
- Amended existing PR this turn: yes (PR #315)
- Merge performed: NO
- Tag/release created: NO
- `oap/active` after activation: exactly 5 bytes `178-c`, no trailing newline

## Changes made (per correction)
### C1 — Executable, fail-closed production upgrade documentation
`INSTALL.md` (the outline is now a linkable `### Production upgrade
(controlled outline)` section) and `docs/deployment-production.md` (new
`## Upgrading` section pointing at the single canonical copy):
- The sequence is one documented subshell with `set -euo pipefail`: any
  failed step exits non-zero and stops the sequence in place; traffic is
  never moved on after a failed migration. No success gate is left to a
  comment.
- The one-shot migration is `docker compose -f docker-compose.production.yml
  run --rm --no-deps migrations` in the foreground; its exit status is the
  gate before `up -d --force-recreate api`. The doc states explicitly that a
  bare `docker compose ps` omits stopped containers (so
  `ps migrations` + "wait for Completed (0)" is not a check), that a
  `up -d` one-shot must be observed with `ps --all migrations`
  (`Exited (0)`/`Exited (1)`), and that `run --rm` leaves no container
  behind.
- After the API replacement, `up -d --force-recreate nginx` refreshes the
  public proxy, with the checked-in reason (`nginx/production.conf` static
  `proxy_pass http://api:8000`, no resolver: Nginx keeps the address
  resolved at config load). Loopback readiness is explicitly not presented
  as proof of the user-facing path.
- The optional async services get the concrete named command
  `docker compose -f docker-compose.production.yml --profile async up -d
  --force-recreate worker scheduler`, flagged as only for `async`-profile
  deployments (running it on a non-async deployment would start them).
- Production and local definitions are documented as sharing the default
  project namespace per checkout (directory basename), with separate
  checkouts or explicit `-p` project names required to operate both.
- `--force-recreate <service>` semantics (named service only; PostgreSQL/
  Redis keep their containers; the named volume `postgres_data` is preserved)
  are retained, now with the explicit "never recreate DB/Redis to force a
  migration or restart" rule. The `api` → `migrations`
  `service_completed_successfully` dependency condition is documented as the
  fail-closed backstop (a previously failed migrations service container
  makes `up -d api` re-run the migration and hold the API).
- Downtime is described as two brief bounded windows (API recreation, Nginx
  recreation) with a persistent-failure stop rule.
- Backup/rehearsal prerequisites (upgrade runbook link), explicit human
  deployment authority, file-backed secrets, and TLS are preserved as
  preconditions; the RC-beta checklist pointer retains its "local command
  form" disclaimer. No runtime changes, no new deployment helper.

### C2 — Exact interface and recovery wording
- INSTALL's Interface exposure: "The default production Nginx configuration
  denies `/metrics` (403)" replaced with the checked-in truth — the
  production Nginx configuration does not expose or proxy `/metrics` (no
  metrics location in `nginx/production.conf`; the qualification-only Compose
  override permits metrics solely from the API container's loopback). No
  status is invented. The local paragraph's accurate application-settings
  explanation (stock `METRICS_REQUIRE_AUTH=true` + empty
  `METRICS_ALLOWED_IPS` → 403 at the application route) is preserved
  unchanged.
- The health-probe recovery in INSTALL's Local refresh now carries a stable
  heading (`#### Health probe after recreation`), and QUICKSTART's
  milestone-2 step 1 links to it immediately after `docker-refresh.sh
  --env-only`, so the observed startup-race outcome is actionable where a
  beginner sees it.
- QUICKSTART's evaluation-friction note keeps the concrete ten-row
  prerequisite and the factual "no single-model bootstrap switch today"
  boundary; the speculative future-improvement sentence is removed from the
  beginner prose. The recommendations remain in the report (below) only.

### C3 — Complete owned cleanup; corrected durable record
- Identified, ownership-verified, and removed all still-existing
  Objective-178 task-owned runtime state:
  - Container `obj178-mockpg-173212` (image `postgres:16`), after
    confirming no live connections on 127.0.0.1:15997 and that no dependent
    test run remains.
  - Its task-owned data volume
    `0d7569acac142222e3a4be3d75ba25253cd7ab65e3938c3c903c5ebb11888e64`
    (volume inspect showed `obj178-mockpg-173212` as the sole consumer).
  - Task-owned images: `obj178-cleanroom-142611-{api,worker,scheduler}`,
    `obj178-cleanroom-180734-rt-{api,worker,scheduler}`,
    `repo-{api,worker,scheduler}` (built under the interim `repo` project
    name during the 178-b clean-room).
  - Credential-bearing temporary artifacts: harness/procedure/debug scripts
    (containing test HMAC/session/one-time secrets, a fake upstream key, and
    a test admin password), both 178 clean-room/contributor clones with
    generated-`.env` runtime secrets and their venvs, the 178-b harness
    venv, raw dashboard HTML dumps, test CSVs, and non-evidence logs.
- Unrelated resources verified untouched: `slaif-155f-*` containers, the
  shared worktree environment, `.local-provider-catalog/`. No global prune.
- Retained: safe redacted evidence logs only (see "Local setup /
  dependencies"); no generated keys, admin passwords, cookies, raw pages, or
  live test data remain in retained artifacts (the two clean-room logs that
  briefly exposed one-time key material were redacted in place in the 178-b
  round and re-verified for this cleanup).
- Correction of the 178-b durable record (this report supersedes the
  affected statements; the 178-b report file is immutable and unchanged):
  1. 178-b's "All disposable state destroyed" was inaccurate: the mock
     PostgreSQL container and its two task-owned databases remained running
     until now. They are now removed (proof above). Post-178-c state: zero
     task-owned containers, networks, volumes, or images.
  2. 178-b's packaged-byte statement: `README.md` was changed during 178-b,
     so descriptive packaged README/metadata bytes DID change on that
     branch; the correct statement is that executable/deployment/dependency
     bytes were unchanged (empty cumulative diff over the runtime paths),
     not whole-image or zero-packaged-byte identity.
  3. 178-b's HPC framing: the historical post-PR-220 128-worker
     non-execution is carried as a dated limitation of the verified baseline,
     not as newly reopened release work for this documentation pass. The
     human accepted the existing qualified chain and explicitly prohibited
     another full integrated run here; this report creates no new
     128-worker gate.

## Verification — C1 fixture evidence (task-owned synthetic Compose)
Fixture: `/tmp/obj178c-fixture` (Compose project `obj178c-fixture`, image
`nginx:alpine` only), mirroring the documented sequence: `db` (named
volume `obj178c-fixture_fixture-data`), `app` (the "api", published
diagnostic port), `migrate` (one-shot, `depends_on db`), `worker`/
`scheduler` (`profiles: [async]`), `proxy` (static `proxy_pass` baked at
container creation, like `nginx/production.conf` without a resolver).
Results (log `/tmp/obj178c-fixture-run.log`):
- Success path: foreground `run --rm --no-deps migrate` (exit 0) passed the
  gate; `app` recreated (container ID changed); `--profile async` recreated
  worker + scheduler; proxy refresh restored the public path (200).
- Stale-proxy mechanics (C1.2): after the app was replaced at a new address
  (172.18.0.3 → 172.18.0.7, old address parked by a placeholder), the direct
  diagnostic call returned 200 while the unrefreshed proxy returned 502 —
  `STALE_PROXY_DEMONSTRATED`. The proxy refresh then restored 200.
- DB identity: db container ID and volume name unchanged across the entire
  success path (`db_same=yes volume_same=yes`).
- Failure path: `run --rm --no-deps migrate` (exit 1) inside the
  `set -euo pipefail` subshell → subshell rc=1, the app was NOT recreated
  (container ID unchanged), and no step after the gate executed.
- Stopped-state observability: a leftover one-shot
  (`obj178c-fixture-migrate-run-*`) appears in `docker compose ps --all` as
  `Exited (1)` and in plain `docker compose ps` as zero rows
  (`plain ps migrate rows=0`).
- Fixture teardown: `down -v --remove-orphans` (with `--profile async` for
  the profile-scoped services) left no containers, networks, or volumes
  (negative queries recorded).
- One fixture-setup note: profile-scoped services are invisible to a
  profile-less `docker compose down`; the teardown used the profile to
  remove them. This matches the documented profile semantics.
No real provider/TLS production requests; the fixture is a bounded
command-mechanics check, not a production qualification harness.

## Verification — new exact-head clean-room (provider-free milestone 1)
New task-owned clone of the exact final implementation head
`fc1b66e30a94e8cf7e046cd119def462da5631b5` (`v0.1.0-rc.1-741-gfc1b66e`) in
`/tmp/obj178c-cleanroom` (Compose project of the same name; no shared
image/env/DB/secret reuse). Literal documented path (log
`/tmp/obj178c-cleanroom-run.log`, no secrets in the log — verified):
1. `git rev-parse HEAD` = implementation head; tree clean.
2. `cp .env.example .env` + `chmod 600 .env` (mode verified `600`).
3. `docker compose build` (api/worker/scheduler built).
4. Literal `run-cli` helper; `secrets generate hmac --version 1 --write`,
   `admin-session --write`, `one-time --write`; `secrets validate-env` → all
   `OK` lines.
5. `docker compose up -d postgres redis mailpit`; `docker compose run --rm
   api slaif-gateway db upgrade` → Alembic 0001 → 0024.
6. `docker compose up -d api worker scheduler`.
7. `/healthz` (first probe raced startup — the documented race — bounded
   retry) → `{"status":"ok"}`; `/readyz` →
   `{"status":"ok","database":"ok","schema":"ok","redis":"ok",
   "alembic_current":"0024_quota_reservation_accounting_facts",
   "alembic_head":"0024_quota_reservation_accounting_facts"}`.
8. First administrator via the interactive hidden prompt (pty driver;
   password never echoed; driver asserts no echo) → rc=0.
9. Real CSRF/session dashboard login: bad CSRF token rejected (400),
   wrong password rejected with the generic 401 message, correct
   credentials → 303 + working session with the admin visible.
10. `docker compose down` (non-destructive); `docker volume rm
    obj178c-cleanroom_postgres-data obj178c-cleanroom_redis-data` →
    `NO_OWNED_VOLUMES_REMAIN`; the clone (with its generated `.env`) was then
    deleted. Milestone 2 (model call) was NOT re-run: see "Reused versus new
    evidence".

## Verification — reused versus new evidence (byte-identity proofs)
- Model-call snippets: `git diff 56a9d30..fc1b66e -- QUICKSTART.md` shows
  exactly two hunks (the recovery link and the friction-note trim); the
  `models.list` and `chat.completions.create` heredocs, the
  `openai==3.14.1` pin, and the bootstrap/owner/key commands are byte
  identical to the 178-b head. 178-b's `MOCK_HARNESS=OK` and E2E fixture
  evidence are referenced, not re-run.
- Pricing-replacement instructions: `docs/first-time-operator-guide.md` is
  not in this round's diff (byte identical); 178-b's
  `PRICING_PROCEDURE=OK` evidence is referenced, not re-run.
- Provider/accounting code: empty cumulative runtime diff (below).
- Contributor setup inputs: `git diff 56a9d30..fc1b66e -- CONTRIBUTING.md
  pyproject.toml .env.example docker-compose.yml
  docker-compose.production.yml` is empty, so 178-b's fresh-contributor
  verification (venv + `pip install -e ".[dev]"`, compose-config negative/
  positive, docs-focused 39 passed) remains valid on unchanged inputs; the
  documented version boundary `openai==3.14.1` is retained in QUICKSTART
  (untouched by this round's hunks).

## Verification — checkers and scope
At the final implementation head `fc1b66e` (primary checkout):
- `python scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=89`
  (includes the new cross-file anchors `#production-upgrade-controlled-outline`
  and `#health-probe-after-recreation`).
- Focused documentation unit files + governance
  (`test_documentation_inventory.py`, `test_documentation_contract_drift.py`,
  `test_documentation_asof.py`, `test_oap_governance.py`) → **49 passed in
  2.51s** (includes the two new 178-c regression tests:
  `test_install_production_upgrade_is_fail_closed_and_proxy_refreshed`,
  `test_quickstart_links_refresh_race_to_install_recovery`).
- Changed-Python Ruff (`tests/unit/test_documentation_inventory.py`) →
  `All checks passed!`.
- `git diff --check 70f16102d975e3d59268f71de8ff1efd37432d3c..fc1b66e` →
  clean.
- `python scripts/check_sbom.py` (no regeneration) →
  `SBOM_CHECK=OK components=60`.
- This-round paths (`56a9d30` → `fc1b66e`): `INSTALL.md`, `QUICKSTART.md`,
  `docs/deployment-production.md`, `tests/unit/test_documentation_inventory.py`,
  `oap/orders/178-c-production-upgrade-and-owned-cleanup.md` (unchanged after
  activation), `oap/active` (strategic bytes `178-c`) — every path within
  the allowed list. The operator guide was not needed and is untouched.
- Cumulative diff from `70f16102d975e3d59268f71de8ff1efd37432d3c` to
  `fc1b66e` over app/, migrations/, Dockerfile, docker-compose.yml,
  docker-compose.production.yml, deploy/, nginx/, pyproject.toml,
  requirements*.txt, Makefile, alembic.ini, .env.example, .dockerignore,
  VERSION, sbom/, .github/ → **empty**. No script changes beyond the
  original documentation checker; no non-documentation tests changed
  (the single test file change is a documentation regression).
- Historical/OAP immutability: 178-a and 178-b orders and reports
  byte-identical (empty diff from the round start); `docs/verification/`,
  `docs/releases/`, `docs/security/`, `.github/`, `sbom/`, `scripts/`
  unchanged this round.
- `oap/active` = exactly 5 bytes `178-c`; 178-c order md5 unchanged
  (`01875270a2d7e436e293626730cb1342`).

## Verification — original AP verdicts (178-a/b, reaffirmed)
- AP-1..AP-8 of 178-a remain applicable and were not regressed: the
  front-door architecture, distinct quickstart/install roles, copy/paste
  command truth, task navigation, historical immutability, exact-head
  clean-room, checker/CI gates, and runtime/deployment/dependency identity
  all hold at this head (evidence above). C1–C3 close the outstanding 178-b
  findings without reopening accepted work.

## GitHub CI / required checks
- Implementation head `fc1b66e` (inspected before this report): all ten
  final-head checks `completed | success` — `Unit, lint, and migration
  head`, `PostgreSQL integration tests`, `OpenAI-compatible E2E tests`,
  `Playwright browser smoke`, `Docker Compose smoke`, `Documentation
  hygiene`, `Analyze (python)`, `Analyze (javascript-typescript)`,
  `Analyze Python`, `CodeQL`.
- 178-b report head `56a9d30`: all runs `completed | success` (the
  previously in-progress runs completed green).
- Report-head CI: PENDING at report publication time (the report commit is
  new to GitHub); pending is reported honestly, not treated as a pass.
- No expensive integrated qualification or full local matrix was run
  (explicit work-order scope).

## Truthful UX friction and deferred product recommendations
- The ten-model reviewed-pricing bootstrap remains a real setup cost: every
  selected model needs a pricing row even when one model is used.
  Recommendation (bounded future work, outside this objective): a
  single-model evaluation bootstrap flag restricting imported rows to the
  named model.
- The placeholder-to-reviewed replacement remains ten per-row dashboard
  Edit submissions. Recommendation (bounded future work): a batch update
  path (CLI `pricing update` or dashboard bulk edit).
- The post-PR-220 128-worker HPC qualification is carried as a dated
  limitation of the verified baseline (the human-accepted qualified chain);
  this documentation pass neither reopens it nor adds a new gate.

## Known limitations / blockers
- Live provider inference NOT RUN (no real credential; 178-b's mocked
  execution and E2E fixtures remain the evidence for the model call).
- Report-head CI pending at publication (see CI section).
- The C1 fixture validates command mechanics on synthetic services; it is
  not a production qualification, and no TLS/production request was made.

## Local setup / dependencies
- Primary checkout `.venv` for the focused pytest/ruff/doc-checker runs.
- Retained redacted evidence logs (no credentials in any retained file):
  `/tmp/obj178-mock-harness.log`, `/tmp/obj178-pricing-procedure.log`,
  `/tmp/obj178-cleanroom-run.log`, `/tmp/obj178-cleanroom-continue.log`
  (redacted), `/tmp/obj178-cleanroom-final.log` (redacted),
  `/tmp/obj178-contrib-run.log`, `/tmp/obj178-contrib-neg.log`,
  `/tmp/obj178-e2e-rerun.log`, `/tmp/obj178b-fifo-ok-marker` /
  `/tmp/obj178b-fifo-ok.log`, and this round's
  `/tmp/obj178c-fixture-run.log`, `/tmp/obj178c-fixture-ps-plain.txt`,
  `/tmp/obj178c-fixture-ps-all.txt`, `/tmp/obj178c-cleanroom-run.log`.
- All task-owned containers, networks, volumes, and images removed (final
  negative queries: no `obj178*`/`obj178c*` containers, networks, volumes,
  or images remain).

## Safety and scope confirmations
- No merge performed; PR #315 left OPEN for strategic review.
- No tag/release created; no auto-merge enabled.
- No second PR for objective 178; no 179 pre-activation work.
- 178-a/178-b orders and reports and all prior OAP artifacts immutable
  (byte-identical).
- No runtime, deployment, dependency, workflow, or SBOM changes; no
  application defect found; no runtime fix made.
- No real provider calls, no real email, no production/protected
  credentials, no shared `.env` read, no global prune.
- Unrelated resources untouched (`slaif-155f-*`, shared worktree,
  `.local-provider-catalog/`).
- No secrets committed; no credentials in retained evidence; one-time key
  material redacted; test admin passwords exist only in deleted drivers.

## Recommended strategic follow-up
- Confirm report-head checks on PR #315 (pending at publication).
- Consider the bounded single-model evaluation bootstrap and the batch
  pricing-update path as future objectives (explicitly out of scope here).
- The dated baseline limitation (post-PR-220 128-worker qualification)
  remains a repository-level record, unchanged by this pass.

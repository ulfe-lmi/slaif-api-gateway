# OAP Coding-Agent Report — 178-d

## Work order
- Identifier: 178-d
- Work-order file: `oap/orders/178-d-final-upgrade-command-correction.md`
  (committed unchanged in the activation commit; md5
  `ba8e741943889c1194a102d4f58e017f`, verified at report time)
- Numeric objective: 178
- PR mode: AMEND_EXISTING_PR (PR #315, no new PR, no objective switch)

## Status
COMPLETE

## Executive summary
This round closes the final five command-level errors in the production
upgrade documentation on PR #315. The published upgrade block is now the
order's prescribed canonical block, byte-identical to it (verified by
extraction; block md5 `279554084a5c160baa3d27fc9e1851c0`; `bash -n` rc=0;
no angle-bracket placeholders), framed by the honest preamble the order
required (existing checkout at the reviewed candidate revision; retained
project name, file-backed secrets, volumes, configured ports, and TLS;
PostgreSQL/Redis already running and healthy; backup/rehearsal and
preflight first; maintenance downtime until the final public check passes;
prompts are concrete operator inputs; no `.env` sourcing or credential
printing) and by rewritten mechanics bullets (project-name binding,
quiesce plus fail-closed stop with the upgrade-runbook
rollback/forward-recovery pointer, migration exit-status gate, `--no-deps`
semantics with the `service_completed_successfully` backstop,
`--wait --wait-timeout 120` plus an in-container `/readyz` probe, static
proxy refresh, retried public HTTPS check as the final verdict, explicit
no-zero-downtime/no-automatic-rollback wording, and documented tool
version floors). The exact published block's command control flow was
proven on a task-owned synthetic fixture (51 PASS / 0 FAIL): build
failure stops before quiescence; migration failure leaves app/proxy/jobs
stopped without replacement and infrastructure untouched; a failed public
check is non-zero and replaces only the named services while invoking the
public curl with the exact trusted arguments (no `-k`/`--insecure`);
success and the `async=no` branch preserve the DB marker row and volume
identity and never start the async jobs. The original provider-free
milestone 1 was re-executed from a NEW clone of the exact implementation
head (`CLEANROOM_MILESTONE1_DONE`). All 13 remaining task-owned image
tags (three left over from 178-c plus ten from this round) were removed
only after ownership/consumer verification, correcting 178-c's
image-cleanup wording here — in this new report only. No runtime,
deployment, dependency, workflow, or SBOM change. Live provider calls:
NOT RUN. Merge: NO. Tag/release: NO.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 315
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/315
- PR state at report time: OPEN, MERGEABLE
- Base branch: `main`
- Head branch: `oap/178-documentation-productization`
- Starting remote SHA: `70f16102d975e3d59268f71de8ff1efd37432d3c` (remote
  `main`; re-verified via `git ls-remote origin refs/heads/main` at report
  time)
- Round start SHA (178-c report head, first-parent base of this round):
  `063d5c512e975cf34a9ed6a14f9e475533cea543`
- 178-d activation commit: `db90caa9026100eb0a2751beffabc62213072d01`
- Implementation head SHA: `3959b16571e89dd0e0a4fb7fa58be81226800b59`
  (git describe `v0.1.0-rc.1-744-g3959b16`)
- Report publication commit: SELF
- Remote PR head after report publication: SELF (verified against GitHub)
- Commits pushed before the report commit (this round, exactly two):
  - `db90caa9026100eb0a2751beffabc62213072d01` —
    `oap: activate 178-d final upgrade command correction` (strategic
    order + `oap/active`, bytes unchanged)
  - `3959b16571e89dd0e0a4fb7fa58be81226800b59` —
    `obj178: correct the production upgrade commands to the verified
    fail-closed design`
- Report commit first parent: `3959b16571e89dd0e0a4fb7fa58be81226800b59`
- Created a new PR this turn: no
- Amended existing PR this turn: yes (PR #315)
- Merge performed: NO
- Tag/release created: NO
- `oap/active` after activation: exactly 5 bytes `178-d`
  (`31 37 38 2d 64`), no trailing newline
- Every SHA above was re-verified with `git rev-parse` before publication

## Changes made (per finding closure)
### F1 — No invalid shell placeholders (finding 1)
- `cd <checkout containing the pinned candidate code>` (invalid shell)
  removed; the published block is exactly the prescribed canonical block.
- No unquoted angle-bracket placeholder occurs anywhere in executable
  shell: the extracted published block contains no `<` at all.
- `bash -n` on the ACTUAL final block passes (rc=0), both in this
  round's verification and inside the rewritten regression test.

### F2 — A real public HTTPS command exists (finding 2)
- The old comment claim ("the public port check is the confirmation")
  described a command that did not exist; it is gone.
- The block now ends with the real retried curl to
  `${upgrade_origin%/}/healthz`, and the fixture proved it: the fake curl
  was invoked with the exact trusted argument set and no TLS weakening
  (evidence below), and a failing public check makes the sequence
  non-zero.
- The loopback diagnostics are no longer presented as proof of the
  user-facing path: the in-container `/readyz` `exec` probe is an explicit
  second check after the `--wait` health gate, and the public curl is the
  last statement of the subshell — the sequence's exit status is the
  upgrade verdict.

### F3 — Honest downtime: quiesce before migration, stopped on failure
  (finding 3)
- The "two brief, bounded windows" claim is removed.
- The block now stops ingress and runtime users (`stop nginx api`, plus
  `stop worker scheduler` only in the async branch) BEFORE the schema
  migration; under `set -euo pipefail`, any later failure leaves them
  stopped, and the docs say do not silently restart old software against
  a partly migrated database.
- Downtime is documented as the maintenance window from `stop nginx api`
  until the public check passes, with an explicit "no zero-downtime claim
  and no automatic rollback" statement.
- The failure path points to the reviewed upgrade runbook (restore the
  pre-upgrade database and matching application together, or fix forward
  with a reviewed corrective migration) instead of improvising.

### F4 — Default copy/paste starts no async jobs (finding 4)
- The unconditional `--profile async up -d --force-recreate worker
  scheduler` line and its "remove this line otherwise" comment are gone.
- The existing deployment's async usage is determined by the third prompt
  (`upgrade_async`, validated to `yes`/`no`); worker/scheduler are
  stopped and recreated only inside the explicit branch, so the default
  copy/paste starts no async jobs.

### F5 — No dependency-triggered re-migration or proxy ambiguity
  (finding 5)
- Every replacement `up` uses `--no-deps`, so Compose neither re-runs the
  one-shot migration to satisfy `api`'s
  `condition: service_completed_successfully` dependency nor recreates
  PostgreSQL/Redis; the explicit successful foreground migration remains
  the single migration of the sequence.
- The API replacement blocks with `--wait --wait-timeout 120` until the
  container reports healthy, then an in-container `exec` reads `/readyz`
  as a second probe.
- Nginx is recreated only after the API is healthy (checked-in
  `nginx/production.conf` static `proxy_pass http://api:8000`, no
  resolver).
- The retried public HTTPS check (bounded retries, no `--insecure`) is the
  final statement; PostgreSQL/Redis remain running throughout.

### Preamble, prose alignment, and regression test
- `INSTALL.md` preamble states, before the block, exactly the order's
  required framing: existing production checkout at the reviewed
  candidate revision; retained project name/secrets/volumes/ports/TLS;
  PostgreSQL/Redis already running and healthy; backup/restore rehearsal
  and fail-closed preflight first (the preflight block moved ahead of the
  outline); maintenance downtime until all checks pass; prompts are
  concrete operator inputs, not shell placeholders; no secret `.env`
  sourcing and no credential printing.
- Post-block mechanics bullets rewritten to match the final sequence
  (project-name binding via `docker compose ls`/project label; quiesce +
  fail-closed stop + runbook recovery; migration exit-status gate;
  `--no-deps` semantics and the dependency-condition backstop;
  `--wait --wait-timeout 120` + in-container readyz probe; static proxy
  refresh; retried public HTTPS as the verdict; honest downtime). Removed:
  the old alternative service sequence, the ps-based status discussion,
  the unconditional async line, and the unsupported downtime claim.
- Tool versions documented where options demand them: verified on
  Compose 2.40.3 and curl 8.5.0; `--wait`/`--wait-timeout` require
  Docker Compose v2.1.1+; `--retry-all-errors` requires curl 7.71.0+.
- `docs/deployment-production.md`: the summary parenthetical was
  realigned to the final mechanics (quiesce, exit-status gate,
  `--no-deps` replacement with API health wait, proxy refresh, retried
  public HTTPS readiness check); no other change.
- `tests/unit/test_documentation_inventory.py`:
  `test_install_production_upgrade_is_fail_closed_and_proxy_refreshed`
  rewritten to extract the actual published block (the unique fenced bash
  block in the outline opening a subshell), assert no `<`, run a real
  `bash -n`, assert the order quiesce → migration gate → API → readyz
  probe → proxy → public curl, assert the `--no-deps`/`--wait` lines, the
  branch-gated async (old unconditional line absent), no `-k`/
  `--insecure`, and the absence of the abandoned 178-c strings
  (`<checkout`, "remove this line otherwise", `ps --all`, "two brief,
  bounded windows").

### Literal final upgrade block (as published in INSTALL.md)
Byte-identical to the order's prescribed block (both md5
`279554084a5c160baa3d27fc9e1851c0`; extraction verified programmatically);
`bash -n` rc=0; no angle brackets.

```bash
(
  set -euo pipefail
  read -r -p 'Existing production Compose project name: ' upgrade_project
  read -r -p 'Public HTTPS origin (for example https://gateway.example.org): ' upgrade_origin
  read -r -p 'Does this deployment already use the async profile? [yes/no]: ' upgrade_async
  test -n "$upgrade_project"
  case "$upgrade_origin" in https://*) ;; *) echo 'HTTPS origin required' >&2; exit 1 ;; esac
  case "$upgrade_async" in yes|no) ;; *) echo 'Answer yes or no' >&2; exit 1 ;; esac
  upgrade_compose=(docker compose -p "$upgrade_project" -f docker-compose.production.yml)
  if [ "$upgrade_async" = yes ]; then upgrade_compose+=(--profile async); fi

  "${upgrade_compose[@]}" build
  "${upgrade_compose[@]}" stop nginx api
  if [ "$upgrade_async" = yes ]; then "${upgrade_compose[@]}" stop worker scheduler; fi
  "${upgrade_compose[@]}" run --rm --no-deps migrations
  "${upgrade_compose[@]}" up -d --no-deps --force-recreate --wait --wait-timeout 120 api
  "${upgrade_compose[@]}" exec -T api python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/readyz", timeout=5).read()'
  if [ "$upgrade_async" = yes ]; then
    "${upgrade_compose[@]}" up -d --no-deps --force-recreate worker scheduler
  fi
  "${upgrade_compose[@]}" up -d --no-deps --force-recreate nginx
  curl --fail --silent --show-error --retry 10 --retry-all-errors --retry-delay 1 \
    --retry-max-time 60 --connect-timeout 5 --max-time 10 "${upgrade_origin%/}/healthz"
)
```

## Verification — fixture evidence (task-owned synthetic Compose, credential-free)
Fixture: Compose project `obj178d-fix` (postgres, redis, api, nginx,
one-shot `migrations`, profile-scoped `worker`/`scheduler`), driven by a
task-owned fake `curl` on PATH that captures the public call verbatim; a
DB marker row proves data identity and a named volume proves volume
identity. The driver executed the ACTUAL published block (extracted from
INSTALL.md at the implementation head, bytes=1470) against the fixture.
Results (`/tmp/obj178d-fixture-run.log`: `FIXTURE_PASS=51
FIXTURE_FAIL=0` → `FIXTURE_ALL_OK`):
- A) Build failure → non-zero (rc=1) BEFORE quiescence: all four running
  services still running, none recreated, public curl never invoked.
- B) Migration failure → non-zero (rc=1): api/nginx/worker/scheduler
  stopped (quiesced) and NOT replaced; postgres/redis containers and all
  infrastructure untouched; public curl never invoked.
- C) Failed public check → non-zero (rc=1): api/nginx/worker/scheduler
  replaced (new container IDs) and back up; infrastructure untouched;
  fake curl invoked exactly once with `--fail --silent --show-error
  --retry 10 --retry-all-errors --retry-delay 1 --retry-max-time 60
  --connect-timeout 5 --max-time 10
  https://gateway.fixture.local/healthz` (evidence
  `/tmp/obj178d-evidence/fake-curl.log`), no `-k`/`--insecure`; volume
  identity unchanged.
- D) Success → exit 0: named services replaced and running; DB marker row
  intact; volume identity unchanged; namespace holds exactly the 6
  services plus the setup one-shot migrations (`Exited (0)`).
- E) `async=no` → exit 0: worker/scheduler never started by the block;
  api/nginx replaced; DB data and volume identity intact across the
  profile-scoped down/up and the upgrade.
No real provider/TLS production requests: the public check ran against a
local trusted fixture origin via the fake curl. This is a bounded
command-mechanics check, not a production qualification harness.

## Verification — new exact-head clean-room (provider-free milestone 1)
New task-owned clone of the exact implementation head
`3959b16571e89dd0e0a4fb7fa58be81226800b59`
(`v0.1.0-rc.1-744-g3959b16`) with no shared image/env/DB/secret reuse
(log `/tmp/obj178d-cleanroom-run.log`; generated password verified absent
from the log):
1. `git rev-parse HEAD` = implementation head; port preflight OK
   (15432/16379/1025/8025/8000 free).
2. `.env.example` → `.env`, mode 600; `docker compose build` (layers
   CACHED).
3. Three secrets generated through the `run-cli` helper (`docker compose
   run -d --user 1000` mounting the 600 `.env`, poll until exit, rc=0);
   `secrets validate-env` → all OK lines.
4. `up -d postgres redis mailpit`; `db upgrade` → Alembic 0001 → 0024.
5. `up -d api worker scheduler`; ready after attempt 2; `/healthz` ok;
   `/readyz` → `{"status":"ok","database":"ok","schema":"ok","redis":"ok",
   "alembic_current":"0024_quota_reservation_accounting_facts",
   "alembic_head":"0024_quota_reservation_accounting_facts"}`.
6. First administrator via the interactive hidden prompt (pty driver;
   password never echoed) → `ADMIN_CREATE_OK rc=0`.
7. Real CSRF/session dashboard login: bad CSRF token rejected (400),
   wrong password rejected with the generic 401 message, correct
   credentials → 303 + working session (`DASHBOARD_LOGIN_OK`).
8. Non-destructive `down`; both owned volumes removed →
   `NO_OWNED_VOLUMES_REMAIN`; clone deleted (`CLONE_REMOVED`) →
   `CLEANROOM_MILESTONE1_DONE`.
Milestone 2 (model call) was NOT re-run: see "Reused versus new evidence".

## Verification — reused versus new evidence (byte-identity proofs)
- `git diff 063d5c5..3959b16 -- QUICKSTART.md README.md
  CONTRIBUTING.md docs/first-time-operator-guide.md` is empty: the model-
  call snippets (including the `openai==3.14.1` pin, verified present at
  QUICKSTART line 256), the pricing-replacement instructions, the
  contributor-setup inputs, and the README wording are byte-identical
  from round start to implementation head. 178-b's `MOCK_HARNESS=OK`,
  E2E-fixture, and `PRICING_PROCEDURE=OK` evidence is referenced, not
  re-run.
- Provider/accounting code: empty cumulative runtime diff (below).

## Verification — checkers and scope
At the final implementation head `3959b16` (primary checkout; re-verified
at report time):
- `python scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK
  files=89`.
- Focused documentation unit files + governance
  (`test_documentation_inventory.py`, `test_documentation_asof.py`,
  `test_documentation_contract_drift.py`, `test_oap_governance.py`) →
  **49 passed**.
- Changed-Python Ruff (`tests/unit/test_documentation_inventory.py`) →
  `All checks passed!`.
- `git diff --check 063d5c5..3959b16` → clean.
- `python scripts/check_sbom.py` (no regeneration) → `SBOM_CHECK=OK
  components=60`.
- This-round paths (`063d5c5` → `3959b16`): `INSTALL.md`,
  `docs/deployment-production.md`, `tests/unit/test_documentation_inventory.py`,
  `oap/orders/178-d-final-upgrade-command-correction.md` (unchanged after
  activation), `oap/active` (strategic bytes `178-d`) — every path within
  the allowed list; no other path touched.
- Cumulative diff from `70f16102d975e3d59268f71de8ff1efd37432d3c` to
  `3959b16571e89dd0e0a4fb7fa58be81226800b59` over app/, migrations/,
  Dockerfile, docker-compose.yml, docker-compose.production.yml, deploy/,
  nginx/, pyproject.toml, requirements*.txt, Makefile, alembic.ini,
  .env.example, .dockerignore, VERSION, sbom/, .github/ → **empty**.
  This round made zero script/workflow/dependency/SBOM changes; the only
  `scripts/` diff since main is the inherited
  `scripts/check_documentation.py` (+25/-1, from the 178-a commit
  `ea0b040`).
- Cumulative `oap/` state from starting main: `M oap/active` plus
  additions of the 178-a/178-b/178-c/178-d orders and the 178-a/178-b/
  178-c reports — no historical record edited.
- Historical/OAP immutability: 178-a/178-b/178-c orders and reports
  byte-identical from round start (absent from this round's diff);
  `docs/verification/`, `docs/releases/`, `docs/security/`, `.github/`,
  `sbom/`, `scripts/` unchanged this round.
- `oap/active` = exactly 5 bytes `178-d`; 178-d order md5
  `ba8e741943889c1194a102d4f58e017f` unchanged.

## Verification — original AP verdicts (178-a/b, reaffirmed)
- AP-1..AP-8 of 178-a remain applicable and were not regressed: the
  front-door architecture, distinct quickstart/install roles, copy/paste
  command truth (now the byte-identical canonical block with a real
  public check), task navigation, historical immutability, exact-head
  clean-room, checker/CI gates, and runtime/deployment/dependency
  identity all hold at this head (evidence above). F1–F5 close the
  outstanding 178-c command-level findings without reopening accepted
  work.

## GitHub CI / required checks
- Round start `063d5c512e975cf34a9ed6a14f9e475533cea543` (re-queried at
  report time, as the order requires): all ten final-head checks
  `completed | success` — `Unit, lint, and migration head`, `PostgreSQL
  integration tests`, `OpenAI-compatible E2E tests`, `Playwright browser
  smoke`, `Docker Compose smoke`, `Documentation hygiene`, `Analyze
  (python)`, `Analyze (javascript-typescript)`, `Analyze Python`, `CodeQL`.
- Implementation head `3959b16571e89dd0e0a4fb7fa58be81226800b59`: all
  ten final-head checks `completed | success` (same ten checks).
- Report-head CI: PENDING at report publication time (the report commit
  is new to GitHub); pending is reported honestly, not treated as a pass.
- No expensive integrated qualification or full local matrix was run
  (explicit work-order scope).

## Corrected 178-c image-cleanup claim (stated here only)
- The 178-c report said all task-owned images were removed, but three
  tags remained: `obj178c-cleanroom-api`, `obj178c-cleanroom-worker`,
  `obj178c-cleanroom-scheduler`. The 178-c report is immutable and
  untouched; this correction is recorded here, in the new 178-d report
  only.
- Those three, plus this round's ten image tags (`obj178d-fix-*`,
  `obj178d-cleanroom-*`, `obj178d-probe*` — 13 total), were removed in
  this round only after ownership/consumer verification (no live
  consumers; one stuck task-owned one-shot container was force-stopped
  and removed before its image was pruned).
- Final negative queries: no `obj178*`/`obj178c*`/`obj178d*` containers,
  networks, volumes, or images remain. No global prune; no unrelated
  image removed.

## Post-test cleanup (final-state queries)
- `/tmp/obj178d-evidence/final-state.txt`: zero task-owned containers,
  volumes, or images; the two pre-existing `slaif-155f` containers
  preserved; the three `openrouter-*` workspace worktrees untouched;
  `.local-provider-catalog/` untouched.
- Task-owned /tmp drivers, scripts, clones, and generated password files
  removed. Safe redacted evidence logs retained (no credentials in any
  retained file): `/tmp/obj178d-fixture-run.log`,
  `/tmp/obj178d-fixture-run-attempt1.log` (superseded first harness
  attempt), `/tmp/obj178d-fixture-run-detail.log`,
  `/tmp/obj178d-fixture-driver.out`, `/tmp/obj178d-cleanroom-run.log`,
  `/tmp/obj178d-cleanroom-driver.out`, `/tmp/obj178d-upgrade-block.sh`
  (extracted published block), and `/tmp/obj178d-evidence/`
  (`scope.txt`, `cumulative.txt`, `final-state.txt`, `fake-curl.log`,
  `fixture-ps-plain.txt`, `fixture-ps-all.txt`).

## Known limitations / blockers
- Live provider inference NOT RUN (no real credential; 178-b's mocked
  execution and E2E fixtures remain the evidence for the model call).
- Report-head CI pending at publication (see CI section).
- The fixture validates command mechanics on synthetic services with a
  fake curl; it is not a production qualification, and no real
  TLS/production request was made.
- Documented tool floors are the verified versions, not guarantees for
  other versions.

## Local setup / dependencies
- Primary checkout `.venv` for the focused pytest/ruff/doc-checker runs.
- Docker for the task-owned fixture and clean-room milestones only.

## Safety and scope confirmations
- No merge performed; PR #315 left OPEN for strategic review.
- No tag/release created; no auto-merge enabled.
- No second PR for objective 178; no 179 pre-activation work.
- 178-a/178-b/178-c orders and reports and all prior OAP artifacts
  immutable (byte-identical from round start).
- No runtime, deployment, dependency, workflow, or SBOM changes; no
  application defect found; no runtime fix made.
- No real provider calls, no real email, no production/protected
  credentials, no shared `.env` read, no global prune.
- Unrelated resources untouched (`slaif-155f-*`, shared worktree,
  `.local-provider-catalog/`).
- No secrets committed; the fixture used placeholder credentials only
  (removed with the fixture); the clean-room generated password is absent
  from the log and the clone is deleted.

## Recommended strategic follow-up
- Confirm report-head checks on PR #315 (pending at publication).
- The bounded deferred product recommendations carried from 178-c
  (single-model evaluation bootstrap; batch pricing-update path) remain
  open future objectives, explicitly out of scope here.
- No release, RC2, production, security, or compliance claim, and no
  128-worker qualification claim, follows from this round.

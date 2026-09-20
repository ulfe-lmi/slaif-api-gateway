# OAP Coding-Agent Report — 178-e

## Work order
- Identifier: 178-e
- Work-order file: `oap/orders/178-e-version-and-failure-state-truth.md`
  (committed unchanged in the activation commit; md5
  `8c0d10c7f4cbb5d4485bff2726164f67`, verified before and after commit;
  byte-identical to the strategic-side copy at activation time)
- Numeric objective: 178
- PR mode: AMEND_EXISTING_PR (PR #315, no new PR, no objective switch)

## Status
COMPLETE

## Executive summary
This round applies the final factual corrections to INSTALL's production
upgrade prose on PR #315 and finishes exact owned-network cleanup. The
accepted production command block is UNTOUCHED and proven byte-identical to
the 178-d implementation head (extraction-verified, md5
`279554084a5c160baa3d27fc9e1851c0` at both heads). The false combined
Compose version floor is replaced by the order's supported claim (verified
on Compose 2.40.3 / curl 8.5.0; `up --wait-timeout` requires Compose
2.17.0+ per the cited release; `--retry-all-errors` requires curl 7.71.0+;
explicitly not a whole-deployment claim for older versions), and both
overclaims that ingress/runtime "stay stopped until every check passes" /
"a failure at any later step leaves them stopped" are corrected to the
exact staged failure-state truth: a failed migration leaves them stopped;
after a successful migration, services restart in stages and a later
readiness/public-HTTPS failure stops further commands but does not
automatically stop already-restarted services or roll back. The original
provider-free quickstart was re-executed from a NEW disposable clone of the
exact implementation head using the LITERAL documented `run-cli` helper
(foreground `run --rm --no-deps --user uid:gid`), the documented
`db upgrade` and `admin create` commands, and a pty-driven hidden admin
prompt (`CLEANROOM_MILESTONE1_DONE`). The two verified empty prior-round
networks (`obj178d-cleanroom_default`, `obj178d-probe3_default`) and all
this-round task-owned state were removed after ownership/consumer
verification; final obj178-prefix arrays are all empty. No
runtime/deployment/dependency/workflow/SBOM/test change. Live provider
calls: NOT RUN. Merge: NO. Tag/release: NO.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 315
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/315
- PR state at report time: OPEN, MERGEABLE
- Base branch: `main`
- Head branch: `oap/178-documentation-productization`
- Starting remote SHA: `70f16102d975e3d59268f71de8ff1efd37432d3c` (remote
  `main`; re-verified via `git ls-remote` at round start)
- Round start SHA (178-d report head, first-parent base of this round):
  `152e3927b06549658c01fd942df3a5d2aa1db060`
- 178-e activation commit: `99e0f1e014172265cecf8a36e2475fd5431383e6`
- Implementation head SHA: `b26ed802f97ea51f06b202255941afa9d4ee0afb`
  (git describe `v0.1.0-rc.1-747-gb26ed80`)
- Report publication commit: SELF
- Remote PR head after report publication: SELF (verified against GitHub)
- Commits pushed before the report commit (this round, exactly two):
  - `99e0f1e014172265cecf8a36e2475fd5431383e6` —
    `oap: activate 178-e version and failure state truth` (strategic order
    + `oap/active`, bytes unchanged)
  - `b26ed802f97ea51f06b202255941afa9d4ee0afb` —
    `obj178: correct the upgrade version floors and failure-state truth`
    (INSTALL.md prose only)
- Report commit first parent: `b26ed802f97ea51f06b202255941afa9d4ee0afb`
- Created a new PR this turn: no
- Amended existing PR this turn: yes (PR #315)
- Merge performed: NO
- Tag/release created: NO
- `oap/active` after activation: exactly 5 bytes `178-e`
  (`31 37 38 2d 65`), no trailing newline
- Every SHA above was re-verified with `git rev-parse` before publication

## Changes made (INSTALL.md prose only; no shell block edit)
### Correction 1 — Supported version floor (replaces false combined floor)
Old text (removed):
"Verified on Compose 2.40.3 and curl 8.5.0; `up --wait` / `--wait-timeout`
require Docker Compose v2.1.1 or newer, and `--retry-all-errors` requires
curl 7.71.0 or newer."
New text (published, exactly the order's supported claim with the required
link):
"This sequence was verified on Docker Compose 2.40.3 and curl 8.5.0. It
requires [Compose 2.17.0](https://github.com/docker/compose/releases/tag/v2.17.0)
or newer for `up --wait-timeout`, and curl 7.71.0 or newer for
`--retry-all-errors`. Those flag requirements are not a claim that the
complete deployment was tested on every older version."
Primary-source basis (per the order's strategic verification): the Compose
v2.17.0 release explicitly introduces `--wait-timeout` (PR #10276);
`cmd/compose/up.go` at v2.1.1 has `--wait` but NO `--wait-timeout`, so
2.1.1 is no longer described as sufficient for the block.

### Correction 2 — Failure-state truth (both overclaiming places)
- Preamble: "ingress and the runtime users are quiesced before the schema
  migration and stay stopped until every check in the sequence passes, so
  the maintenance window lasts until the final public check succeeds"
  replaced by the exact staged meaning: it stops ingress and the runtime
  users before the migration; a failed migration leaves them stopped;
  after a successful migration, services restart in stages; a later
  readiness or public HTTPS failure stops further commands but does not
  automatically stop services already restarted or roll back the
  deployment; inspect the failed step and follow the recovery runbook
  before treating the upgrade as complete; the maintenance window ends
  only when the final public check passes.
- Mechanics bullet: "With `set -euo pipefail`, a failure at any later step
  leaves them stopped" replaced by the precise form: a failed migration
  leaves them stopped (the subshell halts at the migration gate); after a
  successful migration, services restart in stages and a later readiness
  or public HTTPS failure stops further commands but does not stop
  services already restarted; the existing "inspect the failed step"
  recovery-runbook pointer (restore pre-upgrade database + matching
  application together, or fix forward with a reviewed corrective
  migration) is preserved.
- Directly adjacent sentences were reviewed; the existing correct
  "no zero-downtime claim and no automatic rollback" sentence, the
  downtime-window sentence ("from `stop nginx api` until the public check
  passes"), and the "sequence's exit status is the upgrade verdict"
  sentence are consistent with the corrected explanation and were left
  unchanged. No repeated warning sections or new service procedure.

### Diff shape
`git diff 99e0f1e..b26ed80 -- INSTALL.md`: exactly three prose hunks
(+23/-13). No other path changed this round.

## Verification — literal command block byte-identity (required)
The published upgrade block was extracted programmatically from
`INSTALL.md` at both the 178-d implementation head
(`3959b16571e89dd0e0a4fb7fa58be81226800b59`) and this round's
implementation head (`b26ed802f97ea51f06b202255941afa9d4ee0afb`):
- Byte-identical: YES (`block byte-identical: True`).
- md5 at both heads: `279554084a5c160baa3d27fc9e1851c0`.
The prior 51/0 fixture evidence (178-d) is cited and NOT re-run, per the
order.

## Verification — fresh exact-head quickstart (provider-free milestone 1)
New disposable clone of the exact implementation head
`b26ed802f97ea51f06b202255941afa9d4ee0afb` (`v0.1.0-rc.1-747-gb26ed80`)
in `/tmp/obj178e-cleanroom` (fresh clone; no shared .env/secrets/DB from
prior tasks; port preflight OK: 15432/16379/1025/8025/8000/8080 free).
Log: `/tmp/obj178e-cleanroom-run.log` (generated password verified absent
from the log):
1. Clone HEAD = implementation head; tree clean.
2. `cp .env.example .env && chmod 600 .env`; mode verified `600`.
3. `docker compose build` — documented literal command; build layers
   CACHED (ordinary Docker behavior); api/worker/scheduler Built.
4. The DOCUMENTED LITERAL `run-cli` helper, unmodified
   (`docker compose run --rm --no-deps --user "$(id -u):$(id -g)" -v
   "$PWD:/workspace" -w /workspace api "$@"`), ran the four documented
   foreground secret commands:
   `run-cli slaif-gateway secrets generate hmac --version 1 --env-file
   .env --write`, `... admin-session ...`, `... one-time ...`,
   `run-cli slaif-gateway secrets validate-env --env-file .env` →
   `SECRETS_RC hmac=0 admin-session=0 one-time=0 validate=0` and all OK
   lines. No detached `run -d`/hard-coded-UID transport was substituted;
   the commands were called as documented literals.
5. `docker compose up -d postgres redis mailpit`; documented literal
   `docker compose run --rm api slaif-gateway db upgrade` → Alembic 0001
   → 0024.
6. `docker compose up -d api worker scheduler`; `/healthz` first probe
   raced startup (documented race, rc=56) → attempt 2:
   `{"status":"ok"}`; `/readyz` →
   `{"status":"ok","database":"ok","schema":"ok","redis":"ok",
   "alembic_current":"0024_quota_reservation_accounting_facts",
   "alembic_head":"0024_quota_reservation_accounting_facts"}`.
7. First administrator via the documented literal `docker compose run
   --rm api slaif-gateway admin create --email admin@example.org
   --display-name "Gateway administrator"`, hidden prompts supplied by a
   pty driver (raw/echo-off pty; a 2-second settle before each typed
   input; driver timing only — the command is the documented literal) →
   `ADMIN_CREATE rc=0`; admin record returned (email, display name,
   role `admin`, `is_superadmin: False`).
8. Dashboard login negatives/positive (fresh anonymous clients): bad CSRF
   token → 400; wrong password → 401 with the generic message; correct
   credentials → 200 with the admin visible → `DASHBOARD_LOGIN_OK`.
9. Non-destructive `docker compose down`; both owned volumes removed →
   `NO_OWNED_VOLUMES_REMAIN`; clone deleted (`CLONE_REMOVED`) →
   `CLEANROOM_MILESTONE1_DONE`.

Transparency note (driver-level, not repository-level): two earlier
clean-room attempts of this round hung at the hidden password prompt due
to a driver-side pty input-timing race (input typed before the in-image
`getpass` terminal transition settled); minimal plumbing tests in the
same environment proved input delivery and termios-protected hidden
reads work over the pty→Docker TTY chain (a `cat` test and a bash
`read -s` test both delivered byte-exactly), and the attempts'
contaminated local logs (the driver's pty echoed the generated one-time
passwords) were deleted. All state from those attempts was fully torn
down (containers, volumes) before the final run. The final run used only
documented literal commands and left no state except retained safe
evidence.

## Verification — checkers and scope
At the final implementation head `b26ed80` (primary checkout, re-verified
at report time):
- `python scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK
  files=89`.
- Focused documentation unit files + governance
  (`test_documentation_inventory.py`, `test_documentation_asof.py`,
  `test_documentation_contract_drift.py`, `test_oap_governance.py`) →
  **49 passed**.
- `git diff --check 99e0f1e..b26ed80` → clean.
- `python scripts/check_sbom.py` (no regeneration) → `SBOM_CHECK=OK
  components=60`.
- This-round paths (`152e392` → `b26ed80`): `INSTALL.md` only, plus the
  activation-commit files `oap/orders/178-e-version-and-failure-state-truth.md`
  (unchanged after activation) and `oap/active` (strategic bytes
  `178-e`) — every path within the four-path allowed list. No
  tests/checker/other-docs/runtime/deployment/dependency change.
- Cumulative runtime/deployment/dependency diff from starting main
  `70f16102d975e3d59268f71de8ff1efd37432d3c` to `b26ed80` remains
  **empty** (no script/workflow/dependency/SBOM changes; the only
  `scripts/` diff since main is the inherited
  `scripts/check_documentation.py` from 178-a).
- Historical/OAP immutability: 178-a/b/c/d orders and reports
  byte-identical from round start (absent from this round's diff).
- `oap/active` = exactly 5 bytes `178-e`; 178-e order md5
  `8c0d10c7f4cbb5d4485bff2726164f67` unchanged.

## Verification — reused versus new evidence (identity proofs)
- `git diff 152e392..b26ed80 -- QUICKSTART.md README.md CONTRIBUTING.md
  docs/first-time-operator-guide.md` is empty: model-call snippets
  (including the `openai==3.14.1` pin), pricing-replacement instructions,
  contributor-setup inputs, and README wording are byte-identical. 178-b's
  `MOCK_HARNESS=OK` / `PRICING_PROCEDURE=OK` and 178-d's 51/0 fixture and
  clean-room evidence are cited, not re-run (milestone 1 was re-run this
  round as the human's hard condition; milestone 2 was not re-run).

## Verification — original AP verdicts (178-a/b, reaffirmed)
- AP-1..AP-8 of 178-a remain applicable and were not regressed: the
  front-door architecture, distinct quickstart/install roles, copy/paste
  command truth (the accepted canonical block, byte-identical), task
  navigation, historical immutability, exact-head clean-room (fresh this
  round), checker/CI gates, and runtime/deployment/dependency identity
  all hold at this head.

## GitHub CI / required checks
- Round start `152e3927b06549658c01fd942df3a5d2aa1db060` (re-queried at
  round start): all ten final-head checks `completed | success`.
- Implementation head `b26ed802f97ea51f06b202255941afa9d4ee0afb`: all
  ten final-head checks `completed | success` — `Unit, lint, and
  migration head`, `PostgreSQL integration tests`, `OpenAI-compatible E2E
  tests`, `Playwright browser smoke`, `Docker Compose smoke`,
  `Documentation hygiene`, `Analyze (python)`, `Analyze
  (javascript-typescript)`, `Analyze Python`, `CodeQL`.
- Report-head CI: PENDING at report publication time (the report commit
  is new to GitHub); pending is reported honestly, not treated as a pass.

## Corrected 178-d network-absence claim (stated here only)
- The 178-d report's final-state query did not enumerate networks, and two
  EMPTY task-owned networks remained: `obj178d-cleanroom_default` and
  `obj178d-probe3_default`. Independently inspected labels confirm
  projects `obj178d-cleanroom` and `obj178d-probe3`; both had zero
  container endpoints at inspection (verified twice). The 178-d report is
  immutable and untouched; this correction is recorded here only.
- Both networks were removed in this round after that verification.

## Final cleanup (arrays after ALL Docker commands)
`/tmp/obj178e-evidence-final-state.txt` (queried after all
Docker/fixture/clean-room commands; no task Docker command ran after the
snapshot):
- Containers (running + stopped) with `obj178` prefix: `[] empty`
- Volumes with `obj178` prefix: `[] empty`
- Networks with `obj178` prefix: `[] empty`
- Images with `obj178` prefix: `[] empty` (this round's three
  `obj178e-cleanroom-*` images removed after ownership/consumer
  verification: zero consumers each)
- Preserved: the two pre-existing `slaif-155f-postgres-*` containers
  (both in their prior `Exited (255) 2 weeks ago` state, untouched);
  workspace worktrees (`openrouter-*`, `slaif-*`) untouched;
  `.local-provider-catalog/` untouched. No global prune.
- Retained safe redacted evidence (no credentials in any retained file):
  `/tmp/obj178e-cleanroom-run.log`, `/tmp/obj178e-evidence-final-state.txt`,
  plus the prior round's 178-d evidence set. Task-owned /tmp
  drivers/scripts and the two contaminated attempt logs removed.

## Known limitations / blockers
- Live provider inference NOT RUN (no real credential; 178-b's mocked
  execution and E2E fixtures remain the evidence for the model call).
- Report-head CI pending at publication (see CI section).
- The clean-room proves the documented local quickstart path; it is not a
  production deployment or an upgrade of a live production project.
- The documented version floors are flag-level requirements verified
  against the cited primary sources; older-version deployment behavior is
  not claimed.

## Local setup / dependencies
- Primary checkout `.venv` for the focused pytest/doc-checker runs.
- Docker for the clean-room milestone (disposable project
  `obj178e-cleanroom`, fully torn down).

## Safety and scope confirmations
- No merge performed; PR #315 left OPEN for strategic review.
- No tag/release created; no auto-merge enabled.
- No second PR for objective 178; no 179 pre-activation work.
- 178-a/b/c/d orders and reports and all prior OAP artifacts immutable
  (byte-identical from round start).
- No runtime, deployment, dependency, workflow, test, or SBOM changes;
  the command block is byte-identical; no application defect found.
- No real provider calls, no real email, no production/protected
  credentials, no shared `.env` read, no global prune.
- Unrelated resources untouched (`slaif-155f-*`, shared worktree,
  `.local-provider-catalog/`).
- No secrets committed; the clean-room generated password is absent from
  the retained log; the contaminated attempt logs (driver pty echo of two
  one-time clean-room passwords) were deleted, and the disposable
  databases/volumes holding them were removed; the documented
  `.env.example`-derived `.env` lived only in the deleted clone.

## Recommended strategic follow-up
- Confirm report-head checks on PR #315 (pending at publication).
- This objective's corrections complete Objective 178's documentation
  scope if the strategic review accepts the AP-1..AP-8 and factual/
  cleanup gates above.
- No release, RC2, production, security, or compliance claim, and no
  128-worker qualification claim, follows from this round.

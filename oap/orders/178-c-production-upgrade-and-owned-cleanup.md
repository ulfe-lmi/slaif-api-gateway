# OAP Work Order — 178-c

PR mode: `AMEND_EXISTING_PR`

## Objective and reason

Finish Objective 178's remaining executable-documentation and cleanup gaps on
PR #315. Independent review accepts the corrected model-call milestone,
credential distinction, contributor setup, and verified pricing-replacement
path. Do not reopen that work or enlarge product scope. Correct the newly
documented production upgrade sequence and complete task-owned cleanup.

## Reconciled live state

Verified 2026-09-20 after the exact 178-b response OK:

- Repository `ulfe-lmi/slaif-api-gateway`; main
  `70f16102d975e3d59268f71de8ff1efd37432d3c` unchanged.
- Unique open Objective 178 PR #315,
  https://github.com/ulfe-lmi/slaif-api-gateway/pull/315.
- Base `main`, branch `oap/178-documentation-productization`.
- Report/PR head `56a9d307fbb25b6b3f2248c210f431964b371589`;
  its first parent `10bdea6d58501e6bc0f5d7eef0ec75e436269e8f` is the
  implementation head. GitHub confirms publication changed only the new
  178-b report. No submitted reviews at inspection; PR is MERGEABLE.
- Shared active before activation `178-b`; clean tracked tree.
- Independent checks: 98 focused tests passed in 10.29s, docs OK files=89,
  SBOM OK components=60, diff whitespace clean, runtime/deployment/dependency
  paths and beta-readiness unchanged from starting main, 178-b order hash
  `aea895297e412571dcea96abc81d3d67697618975d03962a3d3d797436e616df`.
- Final-head CI was still running at initial inspection (unit, integration,
  Python analysis pending, other jobs successful). Re-query live state; no
  pending result is a pass. All ordinary final-head checks/rollup remain gates.
- Existing `/tmp/obj178-mock-harness.log` contains `MOCK_HARNESS=OK`;
  `/tmp/obj178-pricing-procedure.log` contains `PRICING_PROCEDURE=OK`;
  clean-room cleanup log contains `NO_OWNED_VOLUMES_REMAIN` for that project.
- However `docker ps -a` still shows `obj178-mockpg-173212` running. Inspection
  identifies image `postgres:16` and task-owned data volume
  `0d7569acac142222e3a4be3d75ba25253cd7ab65e3938c3c903c5ebb11888e64`.
  This is distinct from the correctly cleaned provider-free Compose project.

Amend this same PR starting from its current head. Preserve all prior orders,
reports and commits. Coding agent never merges or enables auto-merge.

## Exact allowed paths

- `INSTALL.md`
- `docs/deployment-production.md`
- `QUICKSTART.md` (a direct link to existing refresh-race recovery only;
  optional remove speculative future-product recommendation from beginner
  prose while retaining the concrete ten-row prerequisite)
- `docs/first-time-operator-guide.md` (only directly matching upgrade/refresh
  references if needed)
- `tests/unit/test_documentation_inventory.py` (only a meaningful regression
  for a corrected documentation requirement if useful)
- `oap/orders/178-c-production-upgrade-and-owned-cleanup.md` (unchanged)
- `oap/active` (unchanged strategic bytes `178-c`)
- `oap/reports/178-c-production-upgrade-and-owned-cleanup.md` (new)

All other product paths remain unchanged. Task-owned disposable test scripts
and redacted evidence may remain outside Git only until scoped cleanup.

## C1 — Executable, fail-closed production upgrade documentation

The newly added INSTALL outline is not sufficient:

1. `docker compose ... ps migrations` omits stopped containers. Installed
   `docker compose ps --help` explicitly requires `--all` for those. A comment
   "wait for Completed (0)" is not a reliable success gate; ordinary Compose
   displays an exited state, and the next shell line is not automatically
   blocked on failure.
2. Recreating API without reloading/recreating NGINX may leave the proxy
   using the old container address. `nginx/production.conf` uses static
   `proxy_pass http://api:8000` without dynamic DNS resolution. Update the
   sequence so the public HTTPS proxy is refreshed after API replacement;
   diagnostic loopback success alone does not prove the user-facing path.
3. Optional async services need actual commands with service names, not just
   "add --profile async" to commands which still name only API/migrations.
4. Production and local files do not automatically form separate project
   namespaces in the same checkout. Describe them as separate definitions,
   with separate checkout/project-name selection if operating both; do not
   imply the filename alone isolates projects or volumes.

Document ONE concrete bounded production upgrade outline using existing
Compose behavior, preserving backup/rehearsal prerequisites, explicit human
deployment authority, file secrets, and TLS. Make migration completion a real
exit-status gate before application restart, with downtime/quiescence
appropriate to this single-appliance deployment. A foreground one-shot
`run --rm` or a correctly awaited service is acceptable; inspect `--no-deps`,
`up`/`run` and cleanup behavior. Do not accidentally recreate DB/Redis to
force a migration or restart traffic after a failed migration. A failed step
must stop the sequence (e.g. a documented subshell with `set -e`, not a
comment). Preserve named data volumes, confirm both readiness and public HTTPS
health, and handle optional async services explicitly. Keep the outline
concise; detailed steps can be canonical in deployment-production with INSTALL
linking them. No runtime changes or new deployment helper.

Validate the documented sequence on task-owned synthetic Compose services
where practical: successful one-shot migration allows restart; failing
migration prevents it; stopped migration status is observable; backing DB
container/volume identity remains intact; intended app/async/proxy services
are recreated. This is a small command-mechanics fixture, not the expensive
production qualification harness. Never test these commands against protected
or production deployments.

## C2 — Exact interface and recovery wording

- INSTALL currently claims production NGINX denies `/metrics` with 403.
  The checked-in nginx/production.conf has no metrics location or explicit
  deny block. Say the production proxy does not expose/proxy the metrics
  endpoint; do not invent an exact 403 status. Preserve the accurate
  application-settings explanation for the local metrics route separately.
- After QUICKSTART's `docker-refresh.sh --env-only`, link directly to
  INSTALL's bounded health-probe recovery section so the observed nonzero
  startup-race outcome is actionable at the point a beginner sees it.
- Keep future single-model/bootstrap/batch-pricing recommendations in the
  report; the beginner only needs the current actionable prerequisites.

## C3 — Complete owned cleanup and correct the durable record

178-b's report says "All disposable state destroyed" while acknowledging two
databases remain in a running task-owned container. Independently verified
runtime state agrees they remain. Do not edit the immutable report; this
round must explicitly correct/supersede that cleanup claim with actual proof.

Identify all still-existing Objective 178 test-owned containers, networks,
volumes and credential-bearing temporary artifacts; verify ownership before
removal. In particular remove `obj178-mockpg-173212` and its above named
data volume after ensuring no dependent test is using them. Do not touch
the unrelated `slaif-155f-*` containers, shared worktree environment,
.local-provider-catalog or other unrelated resources. No global prune.
Inspect mounts and consumers before removing volumes. Report exact owned
identities removed and final negative queries. Preserve only safe redacted
evidence; no generated keys, admin passwords, cookies, raw pages, or live
test data should remain in artifacts claimed cleaned.

Also correct two misleading 178-b report statements in this NEW report:
- README changed during 178-b, so descriptive packaged README/metadata bytes
  did change; executable/deployment/dependency bytes did not. Do not claim
  whole-image byte identity or zero packaged-byte change.
- Historical post-PR-220 HPC nonexecution is not newly reopened release work.
  The human accepted the existing qualified chain and explicitly prohibited
  another full integrated run for this documentation pass. Carry the dated
  limitations accurately; do not invent a fresh 128-worker gate.

## Verification and acceptance

Original AP-1 through AP-8 remain applicable; C1–C3 close the outstanding
findings. No full local matrix or integrated production harness.

- After all non-report commits are pushed, execute provider-free milestone 1
  from a NEW task-owned clone of the EXACT final implementation SHA, including
  config/secret generation/build/infrastructure/migrations/startup/health/
  readiness/first admin/CSRF-session login/non-destructive stop and final
  owned-resource cleanup. This remains the human's exact-head hard condition.
  No hidden setup fixes; safe drivers may supply interactive responses.
- Model-call snippets, provider/accounting code and pricing-replacement
  instructions need not be re-tested if unchanged; prove relevant byte identity
  and refer to 178-b's mocked and pricing evidence without claiming a new run.
- Fresh contributor setup need not repeat if its inputs remain unchanged;
  prove that identity and retain the existing test's actual version boundary.
- Verify C1 command mechanics with bounded disposable fixtures and source/help
  inspection; record successful and failing migration behavior and proxy/async
  action. No real provider/TLS production requests; synthetic local endpoint
  or source/fixture checks suffice for this document correction.
- `python scripts/check_documentation.py`, focused documentation unit files
  plus `tests/unit/test_oap_governance.py`, changed-Python Ruff if applicable,
  `git diff --check <starting-main> <implementation>`,
  `python scripts/check_sbom.py` without regeneration.
- Empty cumulative diff from `70f16102` over app/migrations/Dockerfile/both
  Compose files/deploy/nginx/pyproject/requirements/Makefile/alembic/.env.example/
  .dockerignore/VERSION/.github/sbom, no script changes beyond the original
  documentation checker, no non-documentation tests, all historical bodies and
  previous OAP orders/reports unchanged. Full allowed-path classification.
- All nine stable final-head checks plus CodeQL rollup required for merge;
  report-time pending is not a pass. Re-query implementation and report head.

## Setup, boundaries and report publication

Same disposable setup authority as 178-a/b. No live provider calls, real
email, production/protected credentials, shared .env reading, global prune,
runtime/dependency/deployment modification, tag/release or Objective 179 work.
If a genuine application defect prevents the documented existing behavior,
report rather than fix it in this PR.

Report exact starting and implementation SHAs, same PR identity, changed paths,
C1–C3 and original AP verdicts, final-head clean-room safe commands/results,
fixture evidence, corrected cleanup/README/HPC statements, identity proof,
reused versus new evidence, checks and pending states. All claimed GitHub
implementation state must already be pushed before drafting the report.
Atomically publish exactly one immutable 178-c report with implementation SHA
and `Report publication commit: SELF`; final report-only commit's first parent
equals that SHA, only this report differs, and the pushed PR head equals SELF
at response time. No mutation after publication. Write exact two bytes OK to
response FIFO, leave PR #315 OPEN, never merge/auto-merge.

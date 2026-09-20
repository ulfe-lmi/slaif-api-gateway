# OAP Work Order — 178-e

PR mode: `AMEND_EXISTING_PR`

## Purpose and reconciled state

Make only the final factual corrections to INSTALL's prose and finish exact
owned-network cleanup. The actual production command block is accepted and
MUST remain byte-identical; no redesign or new behavior.

Live verified 2026-09-20:
- main `70f16102d975e3d59268f71de8ff1efd37432d3c` unchanged.
- Unique open PR #315, branch `oap/178-documentation-productization`, base main.
- Report head `152e3927b06549658c01fd942df3a5d2aa1db060`; first parent
  implementation `3959b16571e89dd0e0a4fb7fa58be81226800b59`; report-only
  publication independently verified via GitHub.
- Active `178-d`, clean tracked tree. All 10 final-head checks SUCCESS.
- Independent focused tests 49 passed in 2.54s; docs OK files=89, SBOM OK
  components=60; runtime/deployment/dependency diff empty, order hash intact.
- Upgrade fixture log verified FIXTURE_PASS=51 FIXTURE_FAIL=0 and
  FIXTURE_ALL_OK; exact-head clean-room log verified admin/login/health and
  CLEANROOM_MILESTONE1_DONE.
- No task-owned containers/images/volumes remain, but two EMPTY task-owned
  networks remain: `obj178d-cleanroom_default`, `obj178d-probe3_default`.
  Independently inspected labels confirm projects `obj178d-cleanroom` and
  `obj178d-probe3`; both have zero container endpoints. Thus the 178-d report's
  network-absence claim is inaccurate. Correct only in this new report.

## Allowed paths (strict)

- `INSTALL.md` (only the factual prose corrections below; no shell block edit)
- `oap/orders/178-e-version-and-failure-state-truth.md` (unchanged)
- `oap/active` (strategic `178-e` unchanged)
- `oap/reports/178-e-version-and-failure-state-truth.md` (new immutable report)

No tests/checker/other docs/runtime/deployment/dependency change. Same PR only;
never merge/auto-merge/tag/release or begin 179. All earlier 178 boundaries and
history immutability remain in force. No fresh product judgment is needed.

## Exact prose corrections

1. Replace the false combined Compose version floor with this supported claim:

   "This sequence was verified on Docker Compose 2.40.3 and curl 8.5.0.
   It requires Compose 2.17.0 or newer for `up --wait-timeout`, and curl
   7.71.0 or newer for `--retry-all-errors`. Those flag requirements are not
   a claim that the complete deployment was tested on every older version."

   Link Compose 2.17.0 to
   https://github.com/docker/compose/releases/tag/v2.17.0.
   Strategic primary-source verification: release body explicitly introduces
   `--wait-timeout` via PR #10276. `cmd/compose/up.go` at v2.1.1 has `--wait`
   but NO `--wait-timeout`. Do not describe 2.1.1 as sufficient for the block.

2. Correct both places claiming all runtime/ingress "stay stopped until every
   check passes" / "a failure at any later step leaves them stopped".
   Use this exact meaning, without changing the commands:

   "The procedure stops ingress and runtime users before migration. A failed
   migration leaves them stopped. After a successful migration, services
   restart in stages; a later readiness or public HTTPS failure stops further
   commands but does not automatically stop services already restarted or
   roll back the deployment. Inspect the failed step and follow the recovery
   runbook before treating the upgrade as complete. The maintenance window
   ends only when the final public check passes."

   Preserve the existing correct no-zero-downtime/no-automatic-rollback claim
   and recovery link. No repeated warning sections or new service procedure.

3. Correct any directly adjacent sentence that would contradict that precise
   failure-state explanation. No unrelated copy edits.

## Exact verification and cleanup

- Verify the command block byte-for-byte unchanged from 3959b16 and use its
  prior 51/0 fixture evidence; do NOT re-run/recreate that fixture. All
  QUICKSTART/README/contributor/pricing/runtime inputs also remain unchanged;
  cite existing mocked model/pricing/contributor evidence with identity proof.
- Run docs checker, existing focused documentation tests plus governance,
  cumulative diff --check and SBOM checker. No broad local suites. Verify
  every changed path against the four-path list; old OAP/history unchanged.
- Preserve the human's hard condition: after final non-report commit/push,
  execute the provider-free quickstart from a NEW disposable clone of that
  exact implementation head. Use the literal documented `run-cli` helper and
  the documented foreground `--rm --no-deps --user uid:gid` secret commands;
  do not substitute detached `run -d`/hard-coded UID transport and call the
  altered command literal. A PTY driver may supply hidden admin responses.
  Build caches are ordinary Docker behavior, but no prior task runtime image,
  .env, secret or database may replace the documented build/setup. Record
  build/config/secrets/migrations/startup/health/readiness/admin/login/cleanup.
- Remove the two verified empty prior networks, and this round's task-owned
  containers/networks/volumes/credential-bearing files after testing. Verify
  labels and endpoint/consumer absence first; no global prune. Preserve all
  unrelated slaif-155f resources, shared workspace and provider catalogs.
- FINAL cleanup queries must run after all Docker/fixture/clean-room commands:
  enumerate ALL resources with `obj178` prefixes, not just the latest project.
  Include containers, volumes, networks, images. Record actual remaining
  names (empty arrays if empty). Never assert absence from a query omitting
  networks. Don't start another task Docker command after this snapshot.
  Report accurate retained safe artifacts; do not rewrite prior reports.

## Publication and acceptance

These corrections complete Objective 178 only if original AP-1..AP-8 and the
above factual/cleanup gates pass. Report exact SHAs, same PR identity, actual
small diff, literal byte-identity proof, primary version source, failure-state
truth, fresh exact-head quickstart evidence, final cleanup arrays, corrected
178-d network claim, docs/tests/SBOM/CI results and inherited limitations.

Implementation must already be committed/pushed before report drafting. One
new immutable 178-e report, literal implementation SHA, `Report publication
commit: SELF`; report-only final commit has that SHA as parent and is the
remote PR head at signal time. Inspect final-head CI without rewriting the
report; pending is not passed. Send exact two-byte OK on response FIFO. Leave
PR #315 open for strategic decision. No post-report mutation.

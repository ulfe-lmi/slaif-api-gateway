# OAP Work Order — 178-d

PR mode: `AMEND_EXISTING_PR`

## Objective and verified state

Close the remaining command-level errors in the new production upgrade
documentation on existing PR #315. Preserve all accepted productization work.
This is a final bounded correction, not new product/deployment functionality.

Verified 2026-09-20 after exact 178-c response OK:

- Repository `ulfe-lmi/slaif-api-gateway`; unchanged main
  `70f16102d975e3d59268f71de8ff1efd37432d3c`.
- Unique open PR #315, base main, branch `oap/178-documentation-productization`.
- PR/report head `063d5c512e975cf34a9ed6a14f9e475533cea543`; first parent
  `fc1b66e30a94e8cf7e046cd119def462da5631b5`; GitHub confirms report-only
  publication. Shared active `178-c`, clean tracked tree. PR MERGEABLE.
- Documentation checker OK files=89, SBOM OK components=60; report-head CI
  initially pending and must be re-queried. No acceptance from pending checks.
- Independent inspection found fixture markers STALE_PROXY_DEMONSTRATED and
  db_same=yes volume_same=yes; exact-head clean-room log names fc1b66e and
  successful health/readiness/login plus NO_OWNED_VOLUMES_REMAIN.
- No obj178 containers, networks or volumes remain. Three harmless built
  image tags DO remain: obj178c-cleanroom-api, obj178c-cleanroom-worker,
  obj178c-cleanroom-scheduler. This contradicts 178-c's all-images-removed
  wording; correct it in this new report, never edit the old report.

Same PR only. Do not create a new PR, merge, auto-merge, tag, release or work
on 179. Original 178-a/b/c runtime, privacy, provider and history boundaries
remain binding.

## Exact allowed paths

- `INSTALL.md`
- `docs/deployment-production.md` (only link/summary alignment if needed)
- `tests/unit/test_documentation_inventory.py` (adjust production outline
  regression to validate the final behavior, not abandoned command strings)
- `oap/orders/178-d-final-upgrade-command-correction.md` (unchanged)
- `oap/active` (unchanged strategic bytes `178-d`)
- `oap/reports/178-d-final-upgrade-command-correction.md` (new)

No other changes. In particular QUICKSTART and its accepted model-call
examples, README, contributor guide and pricing instructions remain unchanged.

## Exact findings to close

1. `cd <checkout containing the pinned candidate code>` in the published
   Bash block is invalid shell syntax. No unquoted angle-bracket placeholders
   may occur in executable shell. Run `bash -n` on the actual final block.
2. The comment says the public port check confirms the HTTPS path, but no
   public HTTPS command exists. Include and fixture-test the real command.
3. A generic upgrade cannot keep the old API/workers processing while schema
   migration runs and claim only two brief bounded downtime windows. This
   single-appliance procedure must quiesce ingress and runtime users before
   migration, keep them stopped on failure, and describe maintenance downtime
   honestly. No zero-downtime or automatic rollback claim.
4. Default copy/paste must not start optional async jobs. Determine whether the
   EXISTING deployment uses async and branch explicitly, not a comment telling
   the reader to delete a line.
5. Avoid dependency-triggered second migrations and proxy re-resolution
   ambiguity. After the explicit successful foreground migration, replace the
   named services with `--no-deps`, wait for API health, check readiness, then
   recreate NGINX and verify trusted HTTPS. Infrastructure remains running.

## Prescribed replacement command design

Use the following structure as the canonical block. State before it: execute
from the EXISTING production checkout at the reviewed candidate revision;
retain its existing project name, secrets, volumes, configured ports and TLS;
PostgreSQL/Redis must already be running/healthy; perform backup/restore
rehearsal and preflight first; maintenance downtime lasts until all checks
pass. The prompts are concrete user inputs, not shell placeholders. Do not
source secret .env into shell or print credentials.

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

Inspect installed Compose and curl help to verify these options and exact
interactions; document required tool versions where the options demand them.
This is a prescribed design, not permission to publish an untested snippet.
If an option is incompatible, make the smallest equivalent correction and
explain its evidence. Do not expand the paragraph into a deployment harness.
Do not weaken TLS verification (`-k`) or add provider traffic to the check.

The named services/array/profile must refer to the same existing project on
every line. Never operate on a guessed production namespace. If any step
fails, the subshell stops; do not silently restart old software against a
partly migrated DB. Point to reviewed rollback/forward-recovery guidance.
Remove old alternative service sequences, ps-based status discussion and
unconditional async lines that compete with this canonical block. A concise
explanation of migration exit status, no-deps, API health/readiness and proxy
refresh is sufficient. Remove the unsupported bounded-downtime claim.

## Verification and final evidence

- Extract the ACTUAL published upgrade Bash block, run `bash -n`, then test
  command control flow with task-owned doubles/fixture. Prove: build failure
  stops before quiescence; migration failure leaves app/proxy/jobs stopped
  without restarting them; success restarts only configured services;
  async=no never starts worker/scheduler; public HTTPS curl is invoked and a
  failure makes the sequence nonzero; exact namespace is reused; DB/Redis
  container and volume unchanged. Existing synthetic fixture evidence can
  support unchanged Compose semantics. Use fake curl for no-network control
  flow or a local trusted test certificate, never real production TLS/provider
  calls. No expensive qualification harness.
- Do not add implementation-mirroring tests for shell comments. Existing
  documentation regression must match the final concrete sequence and an
  actual syntax check; fixture evidence covers execution.
- After all non-report edits are committed/pushed, run original provider-free
  milestone 1 from a NEW clone of the EXACT final implementation SHA (build,
  fresh config/secrets, migrations, API, health/readiness, interactive first
  admin, real CSRF/session login, non-destructive stop and owned cleanup).
  This is the human's final-head acceptance condition; no hidden repair.
- Model snippets, pricing replacement and contributor setup are unchanged:
  show byte identity and reuse the prior successful evidence honestly. No
  rerun of those workflows or full local suites is needed.
- Docs checker, three documentation unit files + governance, changed-Python
  Ruff, cumulative diff --check, SBOM check; required final-head CI/rollup.
- Re-prove cumulative empty runtime/deployment/dependency diff from starting
  main; no script/workflow/dependency/SBOM changes; no existing historical/OAP
  record edits. README descriptive byte changes inherited from earlier rounds
  stay explicitly separate from executable identity and whole-image claims.
- After ALL this round's tests, remove task-owned containers/networks/volumes
  and generated credential files. Remove the remaining three obj178c images
  and this round's images only after ownership/consumer verification, or
  explicitly report retained harmless image tags accurately. Do not claim
  absence without checking the final post-test state. No global prune or
  unrelated image removal. Preserve unrelated slaif-155f resources and shared
  workspace state. Keep only safe redacted evidence logs.

## Setup, report and immutable publication

Same disposable authority as prior rounds. No shared .env read, no protected
credentials, real providers/email/production, runtime changes or new product
features. If the prescribed existing behavior cannot work without product
changes, stop and report the exact issue instead of widening scope.

Report exact main/round-start/implementation SHAs, same PR identity, actual
changed paths, closure of findings 1–5, literal final upgrade block and its
syntax/fixture results, exact-head clean-room proof, reused evidence identity,
post-test cleanup queries, corrected 178-c image-cleanup claim, AP outcomes,
runtime/history identity and exact check states. No vague perfection claims.

Commit/push all non-report state first. Publish exactly one new immutable
178-d report with literal implementation SHA and `Report publication commit:
SELF`; final commit changes only that report and has the implementation SHA
as first parent. Verify pushed PR head is SELF, inspect final-head checks
without rewriting the report, then send exact two-byte OK on response FIFO.
Leave PR #315 OPEN; never merge/auto-merge/tag/release.

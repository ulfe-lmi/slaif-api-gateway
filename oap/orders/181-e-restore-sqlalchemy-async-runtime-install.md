# OAP Work Order — 181-e

## Objective and business reason

Restore the already-required SQLAlchemy asyncio dependency in runtime-only
installations so the existing Docker migration/readiness smoke works again.
Continue SAME Objective181 PR318; this is a bounded prerequisite discovered by
181-d CI, not a new feature or new PR. No transport/capture repair is folded in.
Those and exact tooling identity remain REQUIRED later on PR318; full182–184
administrator-refresh mandate remains unchanged. No182 while181 is unresolved.

## Verified state and authority

Reconciled2026-10-12 around17:09–17:13UTC:
- main6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf, unchanged.
- PR mode: `AMEND_EXISTING_PR`; uniqueObjective181 PR318 OPEN/MERGEABLE,
  base main, branch oap/181-authoritative-catalog-collection; title unchanged.
- Starting report/head5e8655c38e30d9a816b9404fbc268ef784784f81, first parent
  implementation1ae62c38ae30ccbb37924a451a718f58ec8fafd2. Publication changes only
  the immutable181-dreport. Tracked worktree clean; preserve unrelated untracked
  CODEX-SESSIONS.md/codex.sh, ignored .codex/.local-provider-catalog/worktrees.
- Active181-d/order/report exact; orderSHA256
  f138eb986987f438425012bd9979e0bd9934c52c45aa2154624b3d735ace189a.
- Sole strategic helper9720 returned RESPONSE_OK_EXACT/exit0 and CLOSED.
  Codingpane%9/pid1703557 verified; its single controlwaiter local57396 is idle.
  Strategicpane%8/pid1700208 verified. Reverify before new synchronization.
- D1–D4 independently ACCEPTED on exactGitarchivesnapshot: all1341files match;
  333focusedtestsPASS25.81s, zero defaultDNS, two actually-applied midnight
  challengesPASS2.15s, semantic/supplied-bypass probes correct; Ruff/docs91/diff
  clean. Review: strategic workorders/OBJECTIVE-181-D-STRATEGIC-REVIEW.md.
- All10 implementation AND report-head check outcomes resolved: nineSUCCESS,
  DockerComposeSmokeFAILURE. This is not a pass or merge-ready state.
- UnrelatedDependabotPR319 remains open/untouched. Ruleset23580289 active,
  deletion/non-fast-forward prohibited, no bypassactors. No change-request
  review; only prereleasev0.1.0-rc.1; no release/tag/production authority.

Human has authorized ordinary OAP resumption with the tested Qwen agent in%9.
Read this complete order and applicable maintained coding constitution/protocol,
dependency/install/Docker contracts and the cited strategic review. Use the
migrated /home/janezp roots and objective-neutral permanent startup. Do not
restart historical181-c/d or rewrite their reports. GitHub is software truth.

## Exact failure and required change

GitHub Docker job114918517536 (run38281163491, implementation1ae62c3) built the
runtime image with SQLAlchemy2.1.4 and no greenlet, then failed the explicit
migration step on missing greenlet. It repeated on an agent-requested rerun
and on report-head job114922275227/run38282310992. Runtime Dockerfile installs
`python -m pip install .`; pyproject.toml and requirements.txt both declare bare
sqlalchemy. None of those files changed in181-d. Development dependencies can
mask the missing bridge, so a dev-venv pass alone is insufficient.

Strategy independently inspected SQLAlchemy2.1.4 metadata: greenlet is required
only under extra==asyncio. Official primary installation contract:
https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html#asyncio-platform-installation-notes
Version2.1 moved greenlet out of the default install. Existing async database
architecture already needs this bridge. This is an explicit runtime dependency
declaration repair, not an API/accounting/schema change.

Change ONLY the SQLAlchemy runtime dependency declaration to sqlalchemy[asyncio]
in BOTH pyproject.toml and requirements.txt. Keep existing version policy and
all other dependencies unchanged; requirements-dev.txt inherits the runtime
file and needs no edit. Do not pin/downgrade old SQLAlchemy merely to avoid
expressing the required extra. Do not add an unrelated package/version/lockfile,
runtime workaround, startup import bypass, Dockerfile/Compose or CI relaxation.
Add a brief relevant runtime-install/build note to docs/deployment.md, without
new feature/release claims or changing ordinary operator commands.

## Exact allowed paths

- pyproject.toml (only sqlalchemy -> sqlalchemy[asyncio] dependency string)
- requirements.txt (only corresponding SQLAlchemy dependency string)
- docs/deployment.md (bounded runtime install/build dependency note only)
- oap/orders/181-e-restore-sqlalchemy-async-runtime-install.md (unchanged)
- oap/active (exact strategic five-byte181-e)
- oap/reports/181-e-restore-sqlalchemy-async-runtime-install.md (new immutable)

No other tracked paths. No source/runtime/pricing/accounting/hosted-policy/route
resolution/schema/migration/test/workflow/Docker/Compose/AGENTS/protocol changes.
No transport/capture/Codex researcher/final wrapper/archival evidence changes.
Owned scratch installation/verification scripts outside repositories are allowed;
do not add tests that merely assert the dependency string.

## Observable acceptance and focused verification

AP-E1: both runtime declarations request the asyncio extra; literal diffs show
no unrelated dependency or behavior changes. Existing pricing/authority fixes,
PostgreSQL accounting truth and local/hosted-tool boundaries remain unchanged.

AP-E2: a CLEAN Python>=3.12 runtime-only environment, installed from the actual
project without dev/browser packages or inherited PYTHONPATH/site-packages,
contains greenlet and imports SQLAlchemy asyncio. Execute the actual greenlet
async bridge (e.g. greenlet_spawn returning an explicit synthetic value) without
any DB connection. Record install command, Python/SQLAlchemy/greenlet versions
and result. Also verify the requirements.txt runtime install in a distinct clean
environment or a comparably isolated runtime-only boundary. Do not uninstall
packages from the shared strategic/dev venv to simulate this condition.

AP-E3: reproduce the formerly failing Docker boundary against the final code
using a uniquely named OWNED local Compose project in owned scratch, from an
exact code snapshot and .env.example with synthetic test configuration only.
Build the unchanged runtime Dockerfile, verify asyncio/greenlet imports in the
image, start its own postgres/redis/mailpit, run explicit migrations, start
api/worker/scheduler, and verify /healthz and /readyz. Use the exact local Docker
socket explicitly; never touch other stacks, global cleanup or real .env.
Use unique networks/volumes/project names and free loopback-bound API ports;
temporary scratch overrides may suppress other host ports. Database migration
is allowed ONLY inside this project's new disposable synthetic database. Disable
real email/scheduled jobs and provide no upstream credentials or inference.
Clean up ONLY resources created for this test after recording results. No apt
PostgreSQL install, host shared5432 access or production DB. If an actual local
environment obstacle cannot be resolved inside this boundary, report it exactly
and use authoritative DockerCI evidence, never label a missing local proof pass.

AP-E4: existing OAP governance tests, Ruff, documentation checker and round
`git diff --check 5e8655c38e30d9a816b9404fbc268ef784784f81` pass; normal final-head
GitHubCI, especially DockerComposeSmoke, is verified. No full local unit/PG/
Redis/browser/HPC matrix: the narrow runtime-only install and failed Docker
matrix reproduction are the evidence this dependency boundary needs. Do not
repeat already accepted333semantic tests without a new related concern.

## Setup, boundaries and report publication

Own routine isolated venv/build/Compose setup and cleanup. Working managed
Python3.12.15 and strategic testvenv remain available; use own fresh environments
for AP-E2 and leave existing packages/state untouched. Dockerlocal server29.1.3
is available; preserve all unrelated containers/images/networks/volumes. Public
package/image downloads and official dependency-doc reads are authorized; no
protected credentials, private files, production imports/deployments, inference,
real email, tags/releases or real-secret/URL publication. Keep synthetic secret
values/DBURLs out of committed OAP reports; safe versions/status/counts suffice.

Amend ONLY PR318; no new PR, merge or auto-merge. Commit/push strategic order
and active unchanged with intended changes; preserve old reports. Inspect actual
CI and repair in-scope failures if needed; report truthful failures/pending.
After all implementation is pushed, record literal Implementation head SHA and
Report publication commit: SELF. Atomically publish exactly one named report,
final report-only commit, first parent equal to implementation, push/verify same
remote PR head, then send exact two bytes OK/no newline to the migrated response
FIFO and close the descriptor. No mutation after publication. Return to one
control helper with verified TMUX_PANE=%9. Report actual runtime/Docker/CI evidence,
docs/setup/cleanup, exact scope and remaining181 transport/capture limitations.
